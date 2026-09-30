import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure isolated cache and model directories (RNF24)
_root_dir = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("XDG_CACHE_HOME", str(_root_dir / ".cache"))
os.environ.setdefault("HF_HOME", str(_root_dir / ".cache" / "hf"))
os.environ.setdefault("UV_CACHE_DIR", str(_root_dir / ".cache" / "uv"))
os.environ.setdefault("OLLAMA_MODELS", str(_root_dir / "models"))
os.environ.setdefault("OLLAMA_HOST", "127.0.0.1:11434")

from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    get_default_output_path,
)
from tradutor_pdf.config import Settings, load_settings
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.logging_setup import setup_logging, timed_stage
from tradutor_pdf.pipeline import (
    Assembler,
    Chunk,
    Extractor,
    Segmenter,
    Translator,
)
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
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
) -> Path:
    """Execute the full translation pipeline in CLI mode."""
    source = Path(pdf_path)
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo PDF não encontrado: {source}")

    current_settings = settings or load_settings()
    current_extractor = extractor or DoclingExtractor(do_ocr=False)
    current_segmenter = segmenter or SemanticSegmenter()
    current_translator = translator or OllamaTranslator(
        model=current_settings.translation.model,
        target_language=current_settings.translation.target_language,
        temperature=current_settings.translation.temperature,
    )
    current_assembler = assembler or MarkdownAssembler()

    with timed_stage("Extração"):
        blocks = current_extractor.extract(source)

    with timed_stage("Segmentação"):
        chunks = current_segmenter.segment(
            blocks, max_tokens=current_settings.translation.chunk_max_tokens
        )

    total_chunks = len(chunks)
    print(f"[INFO] Documento dividido em {total_chunks} trechos para tradução.")

    with timed_stage("Tradução"):
        prev_chunk: Chunk | None = None
        for idx, chunk in enumerate(chunks):
            page_info = f"pág. {chunk.page_start}"
            if chunk.page_start != chunk.page_end:
                page_info = f"págs. {chunk.page_start}-{chunk.page_end}"

            print(f"[INFO] Traduzindo trecho {idx + 1}/{total_chunks} ({page_info})...")
            prev_context = (
                (prev_chunk.original_text, prev_chunk.translated_text)
                if prev_chunk and prev_chunk.translated_text
                else None
            )
            current_translator.translate(chunk, previous_context=prev_context)
            if chunk.status == "translated":
                prev_chunk = chunk

    dest = output_path or get_default_output_path(source)
    with timed_stage("Montagem"):
        final_path = current_assembler.assemble(chunks, dest)

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

    args = parser.parse_args(argv)
    log = setup_logging()

    if args.cli:
        log.info("Executando tradução em modo CLI para %s", args.cli)
        try:
            out_path = run_cli(args.cli, output_path=args.output)
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
