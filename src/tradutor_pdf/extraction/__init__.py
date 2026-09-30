from tradutor_pdf.extraction.cleaner import (
    clean_blocks,
    dehyphenate_text,
    remove_repeated_headers_footers,
)
from tradutor_pdf.extraction.detection import (
    detect_pages_needing_ocr,
    is_page_text_layer_usable,
)
from tradutor_pdf.extraction.docling_extractor import (
    DoclingExtractor,
    partition_page_range,
)

__all__ = [
    "DoclingExtractor",
    "clean_blocks",
    "dehyphenate_text",
    "detect_pages_needing_ocr",
    "is_page_text_layer_usable",
    "partition_page_range",
    "remove_repeated_headers_footers",
]
