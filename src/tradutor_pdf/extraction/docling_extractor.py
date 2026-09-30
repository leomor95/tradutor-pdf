from __future__ import annotations

import contextlib
import gc
import logging
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.labels import DocItemLabel

from tradutor_pdf.assembly.markdown import get_default_output_path
from tradutor_pdf.config import find_project_root
from tradutor_pdf.extraction.cleaner import clean_blocks
from tradutor_pdf.extraction.detection import detect_pages_needing_ocr
from tradutor_pdf.pipeline import Block, BlockType, Extractor

logger = logging.getLogger(__name__)

_LABEL_TO_BLOCK_TYPE: dict[DocItemLabel, BlockType] = {
    DocItemLabel.TITLE: BlockType.HEADING,
    DocItemLabel.SECTION_HEADER: BlockType.HEADING,
    DocItemLabel.TEXT: BlockType.PARAGRAPH,
    DocItemLabel.PARAGRAPH: BlockType.PARAGRAPH,
    DocItemLabel.CAPTION: BlockType.PARAGRAPH,
    DocItemLabel.LIST_ITEM: BlockType.LIST_ITEM,
    DocItemLabel.CODE: BlockType.CODE,
    DocItemLabel.TABLE: BlockType.TABLE,
    DocItemLabel.PICTURE: BlockType.IMAGE,
    DocItemLabel.FOOTNOTE: BlockType.FOOTNOTE,
    DocItemLabel.FORMULA: BlockType.FORMULA,
}


def get_pdf_page_count(source_path: Path) -> int:
    """Return total number of pages in PDF document without loading entire file."""
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source PDF file not found: {source}")
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(source))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "pypdfium2 could not get page count (%s), falling back to 1", exc
        )
        return 1


def partition_page_range(
    start_page: int,
    end_page: int,
    needing_ocr: set[int],
) -> list[tuple[int, int, bool]]:
    """Partition [start_page, end_page] into contiguous segments of (sub_start, sub_end, needs_ocr)."""
    if start_page > end_page:
        return []

    segments: list[tuple[int, int, bool]] = []
    seg_start = start_page
    seg_ocr = start_page in needing_ocr

    for p in range(start_page + 1, end_page + 1):
        p_ocr = p in needing_ocr
        if p_ocr != seg_ocr:
            segments.append((seg_start, p - 1, seg_ocr))
            seg_start = p
            seg_ocr = p_ocr

    segments.append((seg_start, end_page, seg_ocr))
    return segments


class DoclingExtractor(Extractor):
    """Extracts structural blocks from PDF documents using Docling with streaming page windows and selective OCR."""

    def __init__(
        self,
        do_ocr: bool | str = "auto",
        ocr_languages: tuple[str, ...] | list[str] = ("eng",),
        min_text_chars: int = 50,
        assets_dir: Path | None = None,
        default_window_size: int = 10,
    ) -> None:
        self.do_ocr = do_ocr
        self.ocr_languages = tuple(ocr_languages)
        self.min_text_chars = max(1, min_text_chars)
        self.assets_dir = Path(assets_dir) if assets_dir else None
        self.default_window_size = max(1, default_window_size)

        pipeline_options_no_ocr = PdfPipelineOptions()
        pipeline_options_no_ocr.do_ocr = False
        pipeline_options_no_ocr.generate_picture_images = True
        pipeline_options_no_ocr.heading_hierarchy_options.enabled = True

        self._no_ocr_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options_no_ocr
                )
            }
        )
        self._ocr_converter: DocumentConverter | None = None

    @property
    def _converter(self) -> DocumentConverter:
        """Backward-compatibility property for accessing default converter."""
        if self.do_ocr is True:
            return self._get_ocr_converter()
        return self._no_ocr_converter

    def _get_tessdata_path(self) -> str | None:
        """Resolve isolated tessdata directory, setting TESSDATA_PREFIX if found."""
        if "TESSDATA_PREFIX" in os.environ:
            return os.environ["TESSDATA_PREFIX"]
        candidate = find_project_root() / "bin" / "tessdata"
        if candidate.is_dir():
            path_str = str(candidate.resolve())
            os.environ["TESSDATA_PREFIX"] = path_str
            return path_str
        return None

    def _get_ocr_converter(self) -> DocumentConverter:
        """Lazily initialize and return the OCR-enabled DocumentConverter."""
        if self._ocr_converter is None:
            tessdata_path = self._get_tessdata_path()
            pipeline_options_ocr = PdfPipelineOptions()
            pipeline_options_ocr.do_ocr = True
            pipeline_options_ocr.generate_picture_images = True
            pipeline_options_ocr.heading_hierarchy_options.enabled = True
            pipeline_options_ocr.ocr_options = TesseractCliOcrOptions(
                lang=list(self.ocr_languages),
                path=tessdata_path,
            )
            self._ocr_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options_ocr
                    )
                }
            )
        return self._ocr_converter

    def _extract_sub_range(
        self,
        source: Path,
        sub_pages: tuple[int, int],
        is_ocr: bool,
        target_assets_dir: Path,
        start_block_idx: int,
    ) -> list[Block]:
        """Convert a contiguous slice of pages using the appropriate converter."""
        converter = self._get_ocr_converter() if is_ocr else self._no_ocr_converter
        convert_kwargs: dict[str, Any] = {"page_range": sub_pages}

        result = converter.convert(source, **convert_kwargs)
        doc = result.document

        blocks: list[Block] = []
        block_idx = start_block_idx

        for item, level in doc.iterate_items():
            label = getattr(item, "label", None)
            block_type = _LABEL_TO_BLOCK_TYPE.get(label, BlockType.UNKNOWN)

            # Determine page number
            page_no = sub_pages[0]
            prov = getattr(item, "prov", None)
            if prov and len(prov) > 0 and hasattr(prov[0], "page_no"):
                page_no = prov[0].page_no

            metadata: dict[str, Any] = {
                "label": label.value if hasattr(label, "value") else str(label),
                "level": level,
                "ocr": is_ocr,
            }

            # Content and type specific handling
            content = ""
            if block_type == BlockType.TABLE:
                if hasattr(item, "export_to_markdown"):
                    try:
                        content = item.export_to_markdown(doc=doc).strip()
                    except TypeError:
                        content = item.export_to_markdown().strip()
                elif hasattr(item, "text") and item.text:
                    content = item.text.strip()

                if hasattr(item, "export_to_html"):
                    try:
                        metadata["html"] = item.export_to_html(doc=doc).strip()
                    except TypeError:
                        metadata["html"] = item.export_to_html().strip()

            elif block_type == BlockType.IMAGE:
                target_assets_dir.mkdir(parents=True, exist_ok=True)
                img_filename = f"img_{source.stem}_{block_idx:03d}.png"
                rel_path = f"assets/{img_filename}"
                content = rel_path

                if hasattr(item, "get_image"):
                    img_obj = None
                    try:
                        img_obj = item.get_image(doc)
                        if img_obj is not None:
                            img_save_path = target_assets_dir / img_filename
                            img_obj.save(img_save_path, "PNG")
                            metadata["image_path"] = str(img_save_path)
                    finally:
                        if img_obj is not None:
                            if hasattr(img_obj, "close"):
                                with contextlib.suppress(Exception):
                                    img_obj.close()
                            del img_obj

                alt = ""
                if hasattr(item, "caption_text"):
                    try:
                        alt = (
                            item.caption_text(doc)
                            if callable(item.caption_text)
                            else str(item.caption_text)
                        )
                    except (TypeError, ValueError, AttributeError):
                        alt = ""
                if not alt and hasattr(item, "text") and item.text:
                    alt = item.text.strip()
                metadata["alt"] = alt or f"image_{block_idx}"
                metadata["relative_path"] = rel_path

            elif block_type == BlockType.HEADING:
                if hasattr(item, "text") and item.text:
                    content = item.text.strip()
                elif hasattr(item, "export_to_markdown"):
                    content = item.export_to_markdown().strip()

                h_level = 1
                if hasattr(item, "level") and item.level is not None:
                    try:
                        h_level = max(1, min(6, int(item.level)))
                    except (ValueError, TypeError):
                        h_level = 1
                elif label == DocItemLabel.TITLE:
                    h_level = 1
                elif label == DocItemLabel.SECTION_HEADER:
                    h_level = 2
                metadata["heading_level"] = h_level

            elif block_type == BlockType.CODE:
                if hasattr(item, "text") and item.text:
                    content = item.text.strip()
                elif hasattr(item, "export_to_markdown"):
                    content = item.export_to_markdown().strip()
                lang = (
                    getattr(item, "language", "")
                    or getattr(item, "code_language", "")
                    or ""
                )
                metadata["language"] = lang

            else:
                if hasattr(item, "text") and item.text:
                    content = item.text.strip()
                elif hasattr(item, "export_to_markdown"):
                    content = item.export_to_markdown().strip()

            if not content:
                continue

            translatable = block_type not in (
                BlockType.CODE,
                BlockType.TABLE,
                BlockType.IMAGE,
                BlockType.FORMULA,
            )

            block = Block(
                id=f"b{block_idx}",
                type=block_type,
                content=content,
                page=page_no,
                translatable=translatable,
                metadata=metadata,
            )
            blocks.append(block)
            block_idx += 1

        del doc
        del result
        gc.collect()

        logger.debug(
            "Extracted %d blocks for sub-range %s (ocr=%s) from %s",
            len(blocks),
            sub_pages,
            is_ocr,
            source.name,
        )
        return blocks

    def extract_page_range(
        self,
        source_path: Path,
        pages: tuple[int, int],
        assets_dir: Path | None = None,
        start_block_idx: int = 0,
        on_page_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[Block]:
        """Extract structural blocks from a specific page range [start_page, end_page]."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source PDF file not found: {source}")

        target_assets_dir = (
            Path(assets_dir)
            if assets_dir is not None
            else (
                self.assets_dir or (get_default_output_path(source).parent / "assets")
            )
        )

        if self.do_ocr is False:
            segments = [(pages[0], pages[1], False)]
        elif self.do_ocr is True:
            segments = [(pages[0], pages[1], True)]
        else:  # "auto"
            needing_ocr = detect_pages_needing_ocr(
                source, min_chars=self.min_text_chars, page_range=pages
            )
            segments = partition_page_range(pages[0], pages[1], needing_ocr)

        logger.info(
            "Extracting blocks from %s (pages=%s, segments=%s)",
            source.name,
            pages,
            segments,
        )

        blocks: list[Block] = []
        cur_idx = start_block_idx
        for sub_start, sub_end, is_ocr in segments:
            stage_name = "OCR" if is_ocr else "Extraindo"
            if on_page_progress is not None:
                try:
                    on_page_progress(sub_start, sub_end, stage_name)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("on_page_progress callback error: %s", exc)

            sub_blocks = self._extract_sub_range(
                source=source,
                sub_pages=(sub_start, sub_end),
                is_ocr=is_ocr,
                target_assets_dir=target_assets_dir,
                start_block_idx=cur_idx,
            )
            blocks.extend(sub_blocks)
            cur_idx += len(sub_blocks)

        cleaned_blocks = clean_blocks(blocks, reindex_from=start_block_idx)
        logger.info(
            "Extracted %d total blocks for page range %s from %s (cleaned: %d)",
            len(blocks),
            pages,
            source.name,
            len(cleaned_blocks),
        )
        return cleaned_blocks

    def iter_windows(
        self,
        source_path: Path,
        window_size: int | None = None,
        assets_dir: Path | None = None,
        on_page_progress: Callable[[int, int, str], None] | None = None,
    ) -> Iterator[tuple[tuple[int, int], list[Block]]]:
        """Yield (page_range, blocks) for each window of pages in the PDF document."""
        source = Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"Source PDF file not found: {source}")

        eff_window_size = max(1, window_size or self.default_window_size)
        total_pages = get_pdf_page_count(source)
        cur_block_idx = 0

        for start in range(1, total_pages + 1, eff_window_size):
            end = min(start + eff_window_size - 1, total_pages)
            page_range = (start, end)
            blocks = self.extract_page_range(
                source_path=source,
                pages=page_range,
                assets_dir=assets_dir,
                start_block_idx=cur_block_idx,
                on_page_progress=on_page_progress,
            )
            cur_block_idx += len(blocks)
            yield page_range, blocks

    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
        assets_dir: Path | None = None,
        window_size: int | None = None,
        on_page_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[Block]:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source PDF file not found: {source}")

        if pages is not None:
            return self.extract_page_range(
                source_path=source,
                pages=pages,
                assets_dir=assets_dir,
                start_block_idx=0,
                on_page_progress=on_page_progress,
            )

        eff_window_size = max(1, window_size or self.default_window_size)
        total_pages = get_pdf_page_count(source)

        if total_pages <= eff_window_size:
            return self.extract_page_range(
                source_path=source,
                pages=(1, total_pages),
                assets_dir=assets_dir,
                start_block_idx=0,
                on_page_progress=on_page_progress,
            )

        logger.info(
            "Extracting blocks from %s in streaming windows of %d pages (total %d)",
            source.name,
            eff_window_size,
            total_pages,
        )
        all_blocks: list[Block] = []
        for _page_range, window_blocks in self.iter_windows(
            source_path=source,
            window_size=eff_window_size,
            assets_dir=assets_dir,
            on_page_progress=on_page_progress,
        ):
            all_blocks.extend(window_blocks)

        cleaned_all = clean_blocks(all_blocks, reindex_from=0)
        logger.info(
            "Extracted %d total blocks across all windows from %s (cleaned: %d)",
            len(all_blocks),
            source.name,
            len(cleaned_all),
        )
        return cleaned_all
