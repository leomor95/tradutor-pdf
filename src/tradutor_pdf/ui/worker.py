from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    get_default_output_path,
)
from tradutor_pdf.config import Settings, load_settings
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.pipeline import Assembler, Extractor, Segmenter, Translator
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.translator import OllamaTranslator

logger = logging.getLogger(__name__)


class TranslationWorker(QThread):
    """Executes the translation pipeline in a background thread."""

    progress = Signal(int, int)  # (done, total)
    status_changed = Signal(str)  # Status description in pt-BR
    finished = Signal(Path)  # Path to generated Markdown file
    failed = Signal(str)  # Failure message

    def __init__(
        self,
        source_path: Path,
        output_path: Path | None = None,
        settings: Settings | None = None,
        extractor: Extractor | None = None,
        segmenter: Segmenter | None = None,
        translator: Translator | None = None,
        assembler: Assembler | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.output_path = Path(output_path) if output_path else None
        self.settings = settings or load_settings()

        self.extractor = extractor or DoclingExtractor(do_ocr=False)
        self.segmenter = segmenter or SemanticSegmenter()
        self.translator = translator or OllamaTranslator(
            model=self.settings.translation.model,
            target_language=self.settings.translation.target_language,
            temperature=self.settings.translation.temperature,
        )
        self.assembler = assembler or MarkdownAssembler()

    def run(self) -> None:
        try:
            if not self.source_path.is_file():
                raise FileNotFoundError(
                    f"Arquivo PDF não encontrado: {self.source_path}"
                )

            self.status_changed.emit("Extraindo texto do documento...")
            logger.info("Starting pipeline for %s", self.source_path)
            blocks = self.extractor.extract(self.source_path)

            if self.isInterruptionRequested():
                return

            self.status_changed.emit("Segmentando trechos para tradução...")
            max_tokens = self.settings.translation.chunk_max_tokens
            chunks = self.segmenter.segment(blocks, max_tokens=max_tokens)

            total_chunks = len(chunks)
            if total_chunks == 0:
                self.status_changed.emit("Nenhum texto encontrado no PDF.")
                dest = self.output_path or get_default_output_path(self.source_path)
                final_path = self.assembler.assemble([], dest)
                self.progress.emit(0, 0)
                self.finished.emit(final_path)
                return

            self.progress.emit(0, total_chunks)

            for idx, chunk in enumerate(chunks):
                if self.isInterruptionRequested():
                    logger.info("Pipeline cancelled by user.")
                    return

                page_info = f"página {chunk.page_start}"
                if chunk.page_start != chunk.page_end:
                    page_info = f"páginas {chunk.page_start}-{chunk.page_end}"

                msg = f"Traduzindo trecho {idx + 1} de {total_chunks} ({page_info})..."
                self.status_changed.emit(msg)

                self.translator.translate(chunk)
                self.progress.emit(idx + 1, total_chunks)

            if self.isInterruptionRequested():
                return

            self.status_changed.emit("Montando Markdown traduzido...")
            dest = self.output_path or get_default_output_path(self.source_path)
            final_path = self.assembler.assemble(chunks, dest)

            self.status_changed.emit("Tradução concluída com sucesso!")
            self.finished.emit(final_path)

        except Exception as exc:
            logger.exception("Pipeline failed")
            self.failed.emit(str(exc))
