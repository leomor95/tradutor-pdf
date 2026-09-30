from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import pypdfium2 as pdfium

logger = logging.getLogger(__name__)


def count_valid_text_chars(text: str) -> int:
    """Count valid alphanumeric characters in text, ignoring control and whitespace."""
    return sum(1 for char in text if char.isalnum())


def is_page_text_layer_usable(
    page: pdfium.PdfPage,
    min_chars: int = 50,
) -> bool:
    """Determine whether a PDF page has a usable selectable text layer.

    A page is considered to have a usable text layer if it contains at least
    min_chars valid alphanumeric characters.
    """
    textpage = None
    try:
        textpage = page.get_textpage()
        raw_text = textpage.get_text_range()
        valid_chars = count_valid_text_chars(raw_text)
        return valid_chars >= min_chars
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to extract text layer from page: %s", exc)
        return False
    finally:
        if textpage is not None:
            with contextlib.suppress(Exception):
                textpage.close()


def detect_pages_needing_ocr(
    source_path: Path | str,
    min_chars: int = 50,
    page_range: tuple[int, int] | None = None,
) -> set[int]:
    """Detect which pages in the PDF document lack a usable text layer and require OCR.

    Args:
        source_path: Path to the PDF document.
        min_chars: Minimum number of valid alphanumeric characters to consider
            the page text layer usable.
        page_range: Optional 1-indexed (start_page, end_page) inclusive range to check.

    Returns:
        Set of 1-indexed page numbers that need OCR.
    """
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"Source PDF file not found: {source}")

    doc = None
    needing_ocr: set[int] = set()
    try:
        doc = pdfium.PdfDocument(str(source))
        total_pages = len(doc)
        start_page = 1 if page_range is None else max(1, page_range[0])
        end_page = (
            total_pages if page_range is None else min(total_pages, page_range[1])
        )

        for page_num in range(start_page, end_page + 1):
            page = None
            try:
                page = doc.get_page(page_num - 1)
                if not is_page_text_layer_usable(page, min_chars=min_chars):
                    needing_ocr.add(page_num)
            finally:
                if page is not None:
                    with contextlib.suppress(Exception):
                        page.close()

        logger.debug(
            "Checked pages %d-%d of %s: %d pages need OCR (%s)",
            start_page,
            end_page,
            source.name,
            len(needing_ocr),
            sorted(needing_ocr),
        )
        return needing_ocr
    finally:
        if doc is not None:
            with contextlib.suppress(Exception):
                doc.close()
