from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.labels import DocItemLabel

from tradutor_pdf.pipeline import Block, BlockType, Extractor

logger = logging.getLogger(__name__)

_LABEL_TO_BLOCK_TYPE: dict[DocItemLabel, BlockType] = {
    DocItemLabel.TITLE: BlockType.HEADING,
    DocItemLabel.SECTION_HEADER: BlockType.HEADING,
    DocItemLabel.TEXT: BlockType.PARAGRAPH,
    DocItemLabel.PARAGRAPH: BlockType.PARAGRAPH,
    DocItemLabel.LIST_ITEM: BlockType.LIST_ITEM,
    DocItemLabel.CODE: BlockType.CODE,
    DocItemLabel.TABLE: BlockType.TABLE,
    DocItemLabel.PICTURE: BlockType.IMAGE,
    DocItemLabel.FOOTNOTE: BlockType.FOOTNOTE,
    DocItemLabel.FORMULA: BlockType.FORMULA,
}


class DoclingExtractor(Extractor):
    """Extracts structural blocks from PDF documents using Docling without OCR."""

    def __init__(self, do_ocr: bool = False) -> None:
        self.do_ocr = do_ocr
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = do_ocr

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
    ) -> list[Block]:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source PDF file not found: {source}")

        logger.info(
            "Extracting blocks from %s (pages=%s, ocr=%s)",
            source.name,
            pages,
            self.do_ocr,
        )

        convert_kwargs: dict[str, Any] = {}
        if pages is not None:
            convert_kwargs["page_range"] = pages

        result = self._converter.convert(source, **convert_kwargs)
        doc = result.document

        blocks: list[Block] = []
        block_idx = 0

        for item, level in doc.iterate_items():
            label = getattr(item, "label", None)
            block_type = _LABEL_TO_BLOCK_TYPE.get(label, BlockType.UNKNOWN)

            # Get text content
            content = ""
            if hasattr(item, "text") and item.text:
                content = item.text.strip()
            elif hasattr(item, "export_to_markdown"):
                content = item.export_to_markdown().strip()

            if not content:
                continue

            # Determine page number
            page_no = 1
            prov = getattr(item, "prov", None)
            if prov and len(prov) > 0 and hasattr(prov[0], "page_no"):
                page_no = prov[0].page_no

            metadata: dict[str, Any] = {
                "label": label.value if hasattr(label, "value") else str(label),
                "level": level,
            }
            if block_type == BlockType.HEADING and hasattr(item, "level"):
                metadata["heading_level"] = item.level

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

        logger.info("Extracted %d blocks from %s", len(blocks), source.name)
        return blocks
