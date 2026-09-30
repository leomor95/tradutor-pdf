from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc.labels import DocItemLabel

from tradutor_pdf.assembly.markdown import get_default_output_path
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


class DoclingExtractor(Extractor):
    """Extracts structural blocks from PDF documents using Docling without OCR."""

    def __init__(
        self,
        do_ocr: bool = False,
        assets_dir: Path | None = None,
    ) -> None:
        self.do_ocr = do_ocr
        self.assets_dir = Path(assets_dir) if assets_dir else None

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = do_ocr
        pipeline_options.generate_picture_images = True
        pipeline_options.heading_hierarchy_options.enabled = True

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
        assets_dir: Path | None = None,
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

        target_assets_dir = (
            Path(assets_dir)
            if assets_dir is not None
            else (
                self.assets_dir or (get_default_output_path(source).parent / "assets")
            )
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

            # Determine page number
            page_no = 1
            prov = getattr(item, "prov", None)
            if prov and len(prov) > 0 and hasattr(prov[0], "page_no"):
                page_no = prov[0].page_no

            metadata: dict[str, Any] = {
                "label": label.value if hasattr(label, "value") else str(label),
                "level": level,
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
                    img_obj = item.get_image(doc)
                    if img_obj is not None:
                        img_save_path = target_assets_dir / img_filename
                        img_obj.save(img_save_path, "PNG")
                        metadata["image_path"] = str(img_save_path)

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

        logger.info("Extracted %d blocks from %s", len(blocks), source.name)
        return blocks
