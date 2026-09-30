import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure isolated cache, temporary and model directories (RNF24)
_root_dir = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("XDG_CACHE_HOME", str(_root_dir / ".cache"))
os.environ.setdefault("HF_HOME", str(_root_dir / ".cache" / "hf"))
os.environ.setdefault("UV_CACHE_DIR", str(_root_dir / ".cache" / "uv"))
os.environ.setdefault("OLLAMA_MODELS", str(_root_dir / "models"))
os.environ.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

_tmp_dir = _root_dir / ".cache" / "tmp"
_tmp_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TMPDIR", str(_tmp_dir))
os.environ.setdefault("TEMP", str(_tmp_dir))
os.environ.setdefault("TMP", str(_tmp_dir))

import tempfile

tempfile.tempdir = str(_tmp_dir)

from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    get_default_output_path,
)
from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.config import Settings, load_settings
from tradutor_pdf.extraction.docling_extractor import (
    DoclingExtractor,
    get_pdf_page_count,
)
from tradutor_pdf.logging_setup import setup_logging, timed_stage
from tradutor_pdf.pipeline import (
    Assembler,
    Chunk,
    Extractor,
    Segmenter,
    Translator,
)
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.prompt import PROMPT_VERSION
from tradutor_pdf.translation.translator import OllamaTranslator

logger = logging.getLogger("tradutor_pdf")


def run_cli(
    pdf_path: Path,
    output_path: Path | None = None,
    settings: Settings | None = None,
    extractor: Extractor | None = None,
    segmenter: Segmenter | None = None,
    translator: Translator | None = None,
    assembler: Assembler | None = None,
    checkpoint_store: CheckpointStore | None = None,
    on_conflict: str = "ask",
) -> Path:
    """Execute the full translation pipeline in CLI mode with checkpointing and resumption."""
    source = Path(pdf_path)
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo PDF não encontrado: {source}")

    current_settings = settings or load_settings()
    current_extractor = extractor or DoclingExtractor(
        do_ocr="auto",
        ocr_languages=current_settings.ocr.languages,
        min_text_chars=current_settings.ocr.min_chars,
    )
    current_segmenter = segmenter or SemanticSegmenter()
    current_translator = translator or OllamaTranslator(
        model=current_settings.translation.model,
        target_language=current_settings.translation.target_language,
        temperature=current_settings.translation.temperature,
    )
    current_assembler = assembler or MarkdownAssembler()
    store = checkpoint_store or CheckpointStore()

    total_pages = get_pdf_page_count(source)

    # Checkpoint conflict detection
    if store.has_checkpoint(source):
        existing_manifest = store.load_manifest(source)
        if existing_manifest:
            model_changed = (
                existing_manifest.model != current_settings.translation.model
            )
            prompt_changed = existing_manifest.prompt_version != PROMPT_VERSION
            if model_changed or prompt_changed:
                action = on_conflict
                if action == "ask":
                    if sys.stdin.isatty():
                        resp = (
                            input(
                                f"[AVISO] O modelo ou a versão do prompt foram alterados desde a última execução.\n"
                                f"Modelo salvo: {existing_manifest.model} (atual: {current_settings.translation.model})\n"
                                f"Deseja reaproveitar os trechos já traduzidos? [S/n]: "
                            )
                            .strip()
                            .lower()
                        )
                        action = "restart" if resp.startswith("n") else "reuse"
                    else:
                        action = "reuse"

                if action == "restart":
                    print(
                        "[INFO] Reiniciando tradução a partir do zero conforme solicitado."
                    )
                    store.clear(source)
                else:
                    print("[INFO] Reaproveitando trechos já traduzidos do checkpoint.")

    store.init_manifest(
        source_path=source,
        total_pages=total_pages,
        model=current_settings.translation.model,
        prompt_version=PROMPT_VERSION,
        target_language=current_settings.translation.target_language,
    )

    with timed_stage("Extração / OCR"):
        blocks = current_extractor.extract(source)

    with timed_stage("Segmentação"):
        chunks = current_segmenter.segment(
            blocks, max_tokens=current_settings.translation.chunk_max_tokens
        )

    total_chunks = len(chunks)
    print(f"[INFO] Documento dividido em {total_chunks} trechos para tradução.")

    dest = output_path or get_default_output_path(source)

    # Sync any previously translated chunks
    completed_chunks = 0
    for chunk in chunks:
        if store.is_chunk_completed(source, chunk.id):
            chunk.translated_text = store.load_chunk_translation(source, chunk.id)
            chunk.status = "translated"
            completed_chunks += 1

    if completed_chunks > 0 and hasattr(current_assembler, "sync_incremental"):
        ready_chunks = [c for c in chunks if store.is_chunk_completed(source, c.id)]
        current_assembler.sync_incremental(ready_chunks, dest)
        print(
            f"[INFO] Checkpoint retomado: {completed_chunks}/{total_chunks} trechos já concluídos."
        )

    with timed_stage("Tradução"):
        prev_chunk: Chunk | None = None
        for idx, chunk in enumerate(chunks):
            page_info = f"pág. {chunk.page_start}"
            if chunk.page_start != chunk.page_end:
                page_info = f"págs. {chunk.page_start}-{chunk.page_end}"

            if store.is_chunk_completed(source, chunk.id):
                if chunk.status == "translated":
                    prev_chunk = chunk
                continue

            print(f"[INFO] Traduzindo trecho {idx + 1}/{total_chunks} ({page_info})...")
            prev_context = (
                (prev_chunk.original_text, prev_chunk.translated_text)
                if prev_chunk and prev_chunk.translated_text
                else None
            )
            current_translator.translate(chunk, previous_context=prev_context)

            # Persist chunk to checkpoint
            store.save_chunk(source, chunk, index=idx)

            # Append chunk incrementally to Markdown output
            if hasattr(current_assembler, "append_chunk"):
                current_assembler.append_chunk(chunk, dest)

            if chunk.status == "translated":
                prev_chunk = chunk

    with timed_stage("Montagem"):
        final_path = current_assembler.assemble(chunks, dest)
        store.mark_completed(source)

    return final_path


def main(argv: list[str] | None = None) -> int:
    """Application entrypoint for tradutor-pdf."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        description="Tradutor de PDF (EN -> pt-BR) com LLM local",
    )
    parser.add_argument(
        "--cli",
        type=Path,
        metavar="ARQUIVO.pdf",
        help="Executa a tradução em modo CLI (sem interface gráfica).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        metavar="SAIDA.md",
        help="Caminho do arquivo Markdown de saída (opcional).",
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignora qualquer checkpoint existente e reinicia a tradução do zero.",
    )
    parser.add_argument(
        "--convert",
        type=Path,
        metavar="ARQUIVO",
        help="Converte um documento entre PDF, MD e EPUB sem executar tradução.",
    )
    parser.add_argument(
        "--to",
        type=str,
        metavar="FORMATO",
        help="Formato de destino para conversão (md, pdf, epub).",
    )

    args = parser.parse_args(argv)
    log = setup_logging()

    if args.convert:
        if not args.to:
            print(
                "[ERRO] É necessário especificar o formato de destino com --to (ex.: --to md, --to pdf, --to epub)",
                file=sys.stderr,
            )
            return 1
        from tradutor_pdf.export.converter import DocumentConverter

        try:
            converter = DocumentConverter()
            out_file = converter.convert(
                input_path=args.convert,
                target_format=args.to,
                destination=args.output,
            )
            print(f"[OK] Arquivo convertido com sucesso para: {out_file}")
            return 0
        except Exception as exc:
            log.exception("Falha na conversão de formato")
            print(f"[ERRO] Falha na conversão: {exc}", file=sys.stderr)
            return 1

    if args.cli:
        log.info("Executando tradução em modo CLI para %s", args.cli)
        try:
            on_conflict = "restart" if args.restart else "ask"
            out_path = run_cli(
                args.cli,
                output_path=args.output,
                on_conflict=on_conflict,
            )
            print(f"[OK] Tradução concluída com sucesso: {out_path}")
            return 0
        except Exception as exc:
            log.exception("Falha na tradução via CLI")
            print(f"[ERRO] Falha na tradução: {exc}", file=sys.stderr)
            return 1
    else:
        from PySide6.QtWidgets import QApplication

        from tradutor_pdf.ui.main_window import MainWindow

        app = QApplication(sys.argv[:1])
        window = MainWindow()
        window.show()
        return app.exec()
