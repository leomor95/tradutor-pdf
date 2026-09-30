from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import pypandoc

from tradutor_pdf.assembly.markdown import MarkdownAssembler
from tradutor_pdf.config import Settings, load_settings
from tradutor_pdf.export.epub import EpubExporter
from tradutor_pdf.export.markdown import MarkdownExporter
from tradutor_pdf.export.pdf import PdfExporter
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.pipeline import Assembler, Extractor, Segmenter
from tradutor_pdf.segmentation.semantic import SemanticSegmenter

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {"pdf", "md", "markdown", "epub"}


def normalize_format(fmt: str) -> str:
    """Normalize file format name or extension to canonical string ('pdf', 'md', 'epub')."""
    cleaned = fmt.lower().strip().lstrip(".")
    if cleaned in ("md", "markdown"):
        return "md"
    if cleaned in ("pdf", "epub"):
        return cleaned
    raise ValueError(f"Unsupported format '{fmt}'. Supported: pdf, md, epub")


class DocumentConverter:
    """Converts documents between PDF, MD, and EPUB formats without translation."""

    def __init__(
        self,
        settings: Settings | None = None,
        extractor: Extractor | None = None,
        segmenter: Segmenter | None = None,
        assembler: Assembler | None = None,
        markdown_exporter: MarkdownExporter | None = None,
        epub_exporter: EpubExporter | None = None,
        pdf_exporter: PdfExporter | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.extractor = extractor
        self.segmenter = segmenter or SemanticSegmenter()
        self.assembler = assembler or MarkdownAssembler()
        self.markdown_exporter = markdown_exporter or MarkdownExporter()
        self.epub_exporter = epub_exporter or EpubExporter()
        self.pdf_exporter = pdf_exporter or PdfExporter()

    def convert(
        self,
        input_path: Path | str,
        target_format: str,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert a document to target format (pdf, md, epub) without translation."""
        source = Path(input_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")

        in_fmt = normalize_format(source.suffix)
        out_fmt = normalize_format(target_format)

        if in_fmt == out_fmt:
            if destination is not None:
                dest = Path(destination).resolve()
                if dest.is_dir():
                    target = dest / source.name
                else:
                    target = dest
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                return target
            return source

        if in_fmt == "pdf" and out_fmt == "md":
            return self.pdf_to_md(source, destination)

        if in_fmt == "epub" and out_fmt == "md":
            return self.epub_to_md(source, destination)

        if in_fmt == "md" and out_fmt == "pdf":
            return self.md_to_pdf(source, destination)

        if in_fmt == "md" and out_fmt == "epub":
            return self.md_to_epub(source, destination)

        if in_fmt == "pdf" and out_fmt == "epub":
            return self.pdf_to_epub(source, destination)

        if in_fmt == "epub" and out_fmt == "pdf":
            return self.epub_to_pdf(source, destination)

        raise ValueError(f"Conversion from {in_fmt} to {out_fmt} is not supported.")

    def pdf_to_md(
        self,
        pdf_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert PDF to Markdown without translation by reusing extraction and assembly."""
        source = Path(pdf_path).resolve()
        target_md = self._resolve_target(source, destination, target_ext=".md")
        target_md.parent.mkdir(parents=True, exist_ok=True)

        target_assets = target_md.parent / "assets"
        extractor = self.extractor or DoclingExtractor(
            do_ocr="auto",
            ocr_languages=self.settings.ocr.languages,
            min_text_chars=self.settings.ocr.min_chars,
            assets_dir=target_assets,
        )

        logger.info("Extracting structural blocks from %s...", source)
        blocks = extractor.extract(source)
        logger.info("Extracted %d blocks. Segmenting chunks...", len(blocks))
        chunks = self.segmenter.segment(blocks)

        for chunk in chunks:
            chunk.translated_text = chunk.original_text
            chunk.status = "translated"

        logger.info("Assembling %d chunks into %s...", len(chunks), target_md)
        return self.assembler.assemble(chunks, target_md)

    def epub_to_md(
        self,
        epub_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert EPUB to Markdown using Pandoc, extracting media."""
        source = Path(epub_path).resolve()
        target_md = self._resolve_target(source, destination, target_ext=".md")
        target_md.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Converting EPUB %s to Markdown %s", source, target_md)
        pypandoc.convert_file(
            str(source),
            to="markdown-native_divs-native_spans",
            outputfile=str(target_md),
            extra_args=[f"--extract-media={target_md.parent}"],
        )
        return target_md

    def md_to_pdf(
        self,
        md_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert Markdown to PDF via PdfExporter."""
        source = Path(md_path).resolve()
        dest = destination if destination is not None else source.parent
        return self.pdf_exporter.export(source, destination_dir=dest)

    def md_to_epub(
        self,
        md_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert Markdown to EPUB via EpubExporter."""
        source = Path(md_path).resolve()
        dest = destination if destination is not None else source.parent
        return self.epub_exporter.export(source, destination_dir=dest)

    def pdf_to_epub(
        self,
        pdf_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert PDF to EPUB by chaining PDF->MD and MD->EPUB."""
        source = Path(pdf_path).resolve()
        target_epub = self._resolve_target(source, destination, target_ext=".epub")
        with tempfile.TemporaryDirectory() as td:
            temp_md = Path(td) / f"{source.stem}.md"
            self.pdf_to_md(source, destination=temp_md)
            return self.epub_exporter.export(temp_md, destination_dir=target_epub)

    def epub_to_pdf(
        self,
        epub_path: Path,
        destination: Path | str | None = None,
    ) -> Path:
        """Convert EPUB to PDF by chaining EPUB->MD and MD->PDF."""
        source = Path(epub_path).resolve()
        target_pdf = self._resolve_target(source, destination, target_ext=".pdf")
        with tempfile.TemporaryDirectory() as td:
            temp_md = Path(td) / f"{source.stem}.md"
            self.epub_to_md(source, destination=temp_md)
            return self.pdf_exporter.export(temp_md, destination_dir=target_pdf)

    def _resolve_target(
        self,
        source: Path,
        destination: Path | str | None,
        target_ext: str,
    ) -> Path:
        if destination is None:
            return source.parent / f"{source.stem}{target_ext}"
        dest = Path(destination).resolve()
        if dest.suffix.lower() == target_ext.lower():
            return dest
        return dest / f"{source.stem}{target_ext}"


def convert_document(
    input_path: Path | str,
    target_format: str,
    destination: Path | str | None = None,
) -> Path:
    """Convenience function to convert a document without translation."""
    converter = DocumentConverter()
    return converter.convert(input_path, target_format, destination)
