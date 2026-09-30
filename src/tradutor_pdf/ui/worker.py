from __future__ import annotations

import inspect
import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

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
from tradutor_pdf.pipeline import Assembler, Chunk, Extractor, Segmenter, Translator
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.prompt import PROMPT_VERSION
from tradutor_pdf.translation.translator import OllamaTranslator
from tradutor_pdf.ui.errors import validate_pdf_file
from tradutor_pdf.ui.utils import MovingAverageEstimator

logger = logging.getLogger(__name__)


class TranslationWorker(QThread):
    """Executes the translation pipeline in a background thread with checkpointing and resumption."""

    progress = Signal(int, int)  # (done, total)
    stage_changed = Signal(
        str
    )  # "Extraindo" | "OCR" | "Segmentando" | "Traduzindo" | "Montando"
    page_progress = Signal(int, int, str)  # (current_page, total_pages, stage_name)
    eta_updated = Signal(float)  # Remaining seconds
    status_changed = Signal(str)  # Status description in pt-BR
    finished = Signal(Path)  # Path to generated Markdown file
    failed = Signal(str)  # Failure message
    cancelled = Signal()  # Cancelled by user

    def __init__(
        self,
        source_path: Path,
        output_path: Path | None = None,
        settings: Settings | None = None,
        extractor: Extractor | None = None,
        segmenter: Segmenter | None = None,
        translator: Translator | None = None,
        assembler: Assembler | None = None,
        checkpoint_store: CheckpointStore | None = None,
        on_conflict: str = "reuse",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.output_path = Path(output_path) if output_path else None
        self.settings = settings or load_settings()

        self.extractor = extractor or DoclingExtractor(
            do_ocr="auto",
            ocr_languages=self.settings.ocr.languages,
            min_text_chars=self.settings.ocr.min_chars,
        )
        self.segmenter = segmenter or SemanticSegmenter()
        self.translator = translator or OllamaTranslator(
            model=self.settings.translation.model,
            target_language=self.settings.translation.target_language,
            temperature=self.settings.translation.temperature,
        )
        self.assembler = assembler or MarkdownAssembler()
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.on_conflict = on_conflict

    def run(self) -> None:
        try:
            validate_pdf_file(self.source_path)
            total_pages = get_pdf_page_count(self.source_path)

            # Checkpoint conflict handling
            if self.checkpoint_store.has_checkpoint(self.source_path):
                existing_manifest = self.checkpoint_store.load_manifest(
                    self.source_path
                )
                if existing_manifest:
                    model_changed = (
                        existing_manifest.model != self.settings.translation.model
                    )
                    prompt_changed = existing_manifest.prompt_version != PROMPT_VERSION
                    if (
                        model_changed or prompt_changed
                    ) and self.on_conflict == "restart":
                        logger.info("Restarting translation from scratch as requested.")
                        self.checkpoint_store.clear(self.source_path)

            self.checkpoint_store.init_manifest(
                source_path=self.source_path,
                total_pages=total_pages,
                model=self.settings.translation.model,
                prompt_version=PROMPT_VERSION,
                target_language=self.settings.translation.target_language,
            )

            def _on_extraction_page(
                start_page: int, end_page: int, stage_name: str
            ) -> None:
                self.stage_changed.emit(stage_name)
                self.page_progress.emit(start_page, total_pages, stage_name)
                if start_page == end_page:
                    self.status_changed.emit(
                        f"{stage_name} página {start_page} de {total_pages}..."
                    )
                else:
                    self.status_changed.emit(
                        f"{stage_name} páginas {start_page}-{end_page} de {total_pages}..."
                    )

            self.stage_changed.emit("Extraindo")
            self.page_progress.emit(1, total_pages, "Extraindo")
            self.status_changed.emit("Extraindo texto do documento...")
            logger.info("Starting pipeline for %s", self.source_path)

            try:
                sig = inspect.signature(self.extractor.extract)
                if "on_page_progress" in sig.parameters:
                    blocks = self.extractor.extract(
                        self.source_path, on_page_progress=_on_extraction_page
                    )
                else:
                    blocks = self.extractor.extract(self.source_path)
            except (TypeError, ValueError):
                blocks = self.extractor.extract(self.source_path)

            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            self.stage_changed.emit("Segmentando")
            self.page_progress.emit(1, total_pages, "Segmentando")
            self.status_changed.emit("Segmentando trechos para tradução...")
            max_tokens = self.settings.translation.chunk_max_tokens
            chunks = self.segmenter.segment(blocks, max_tokens=max_tokens)

            total_chunks = len(chunks)
            dest = self.output_path or get_default_output_path(self.source_path)

            if total_chunks == 0:
                self.status_changed.emit("Nenhum texto encontrado no PDF.")
                final_path = self.assembler.assemble([], dest)
                self.progress.emit(0, 0)
                self.finished.emit(final_path)
                return

            # Sync any already completed chunks to output markdown on resume
            completed_so_far = 0
            for chunk in chunks:
                if self.checkpoint_store.is_chunk_completed(self.source_path, chunk.id):
                    chunk.translated_text = (
                        self.checkpoint_store.load_chunk_translation(
                            self.source_path, chunk.id
                        )
                    )
                    chunk.status = "translated"
                    completed_so_far += 1

            if completed_so_far > 0 and hasattr(self.assembler, "sync_incremental"):
                ready_chunks = [
                    c
                    for c in chunks
                    if self.checkpoint_store.is_chunk_completed(self.source_path, c.id)
                ]
                self.assembler.sync_incremental(ready_chunks, dest)
                logger.info(
                    "Resumed from checkpoint with %d/%d chunks already completed",
                    completed_so_far,
                    total_chunks,
                )

            self.progress.emit(completed_so_far, total_chunks)

            self.stage_changed.emit("Traduzindo")
            estimator = MovingAverageEstimator(window_size=10)
            prev_chunk: Chunk | None = None
            for idx, chunk in enumerate(chunks):
                if self.isInterruptionRequested():
                    logger.info("Pipeline cancelled by user.")
                    self.cancelled.emit()
                    return

                page_info = f"página {chunk.page_start}"
                if chunk.page_start != chunk.page_end:
                    page_info = f"páginas {chunk.page_start}-{chunk.page_end}"

                self.page_progress.emit(chunk.page_start, total_pages, "Traduzindo")

                # Skip if already translated in checkpoint
                if self.checkpoint_store.is_chunk_completed(self.source_path, chunk.id):
                    if chunk.status == "translated":
                        prev_chunk = chunk
                    continue

                msg = f"Traduzindo trecho {idx + 1} de {total_chunks} ({page_info})..."
                self.status_changed.emit(msg)

                prev_context = (
                    (prev_chunk.original_text, prev_chunk.translated_text)
                    if prev_chunk and prev_chunk.translated_text
                    else None
                )

                t0 = time.perf_counter()
                self.translator.translate(chunk, previous_context=prev_context)
                duration = time.perf_counter() - t0
                estimator.record(duration)

                remaining = total_chunks - (idx + 1)
                est_seconds = estimator.estimate_remaining(remaining)
                if est_seconds is not None:
                    self.eta_updated.emit(est_seconds)

                # Atomically save to checkpoint
                self.checkpoint_store.save_chunk(self.source_path, chunk, index=idx)

                # Incrementally append to output Markdown
                if hasattr(self.assembler, "append_chunk"):
                    self.assembler.append_chunk(chunk, dest)

                if chunk.status == "translated":
                    prev_chunk = chunk

                self.progress.emit(idx + 1, total_chunks)

            if self.isInterruptionRequested():
                self.cancelled.emit()
                return

            self.eta_updated.emit(0.0)
            self.stage_changed.emit("Montando")
            self.page_progress.emit(total_pages, total_pages, "Montando")
            self.status_changed.emit("Finalizando montagem do Markdown...")
            final_path = self.assembler.assemble(chunks, dest)
            self.checkpoint_store.mark_completed(self.source_path)

            self.status_changed.emit("Tradução concluída com sucesso!")
            self.finished.emit(final_path)

        except Exception as exc:
            logger.exception("Pipeline failed")
            self.failed.emit(str(exc))
