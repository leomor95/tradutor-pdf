from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence

from tradutor_pdf.pipeline import Block, BlockType

logger = logging.getLogger(__name__)

# Patterns for standalone page number footers
_PAGE_NUMBER_PATTERNS = [
    re.compile(
        r"^\s*(?:page|pág\.?|p\.)?\s*\d+\s*(?:/\s*\d+|of\s*\d+)?\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*[-—–]\s*\d+\s*[-—–]\s*$"),
    re.compile(r"^\s*\[\s*\d+\s*\]\s*$"),
]


# Patterns for chapter and section headings that should not be dropped as running headers
_HEADING_EXEMPT_PATTERN = re.compile(
    r"^\s*(?:chapter|capítulo|section|seção|part|parte)\b",
    re.IGNORECASE,
)


def is_standalone_page_number(text: str) -> bool:
    """Return True if text is purely a page number representation."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return any(pattern.match(cleaned) for pattern in _PAGE_NUMBER_PATTERNS)


def dehyphenate_text(text: str) -> str:
    """Join words hyphenated at line breaks (e.g. 'distrib-\\nuted' -> 'distributed')."""
    if "-" not in text:
        return text

    # Standard word hyphenation across newline: word-\nnext -> wordnext
    pattern_newline = re.compile(r"(\b[a-zA-Z]+)-\s*(?:\r?\n)\s*([a-zA-Z]+)\b")
    return pattern_newline.sub(r"\1\2", text)


def remove_repeated_headers_footers(blocks: Sequence[Block]) -> list[Block]:
    """Filter out repeated running headers and footers across pages."""
    if not blocks:
        return []

    # 1. Filter out items explicitly classified as page_header or page_footer by Docling
    filtered_explicit: list[Block] = []
    for b in blocks:
        label = str(b.metadata.get("label", "")).lower()
        if label in ("page_header", "page_footer"):
            logger.debug("Dropping explicit %s block: %r", label, b.content[:40])
            continue
        filtered_explicit.append(b)

    if not filtered_explicit:
        return []

    # 2. Group blocks by page
    pages_map: dict[int, list[Block]] = {}
    for b in filtered_explicit:
        pages_map.setdefault(b.page, []).append(b)

    total_pages = len(pages_map)

    # 3. Detect repeated headers (first block on each page)
    # and repeated footers (last block on each page)
    header_counts: Counter[str] = Counter()
    footer_counts: Counter[str] = Counter()

    for page_blocks in pages_map.values():
        text_blocks = [
            b for b in page_blocks if b.type in (BlockType.PARAGRAPH, BlockType.HEADING)
        ]
        if not text_blocks:
            continue

        first_b = text_blocks[0]
        first_clean = first_b.content.strip()
        if (
            len(first_clean) < 120
            and "\n" not in first_clean
            and not _HEADING_EXEMPT_PATTERN.match(first_clean)
        ):
            norm_header = re.sub(r"\d+", "#", first_clean.lower())
            header_counts[norm_header] += 1

        last_b = text_blocks[-1]
        last_clean = last_b.content.strip()
        if len(last_clean) < 120 and "\n" not in last_clean:
            norm_footer = re.sub(r"\d+", "#", last_clean.lower())
            footer_counts[norm_footer] += 1

    repeated_headers = {
        norm
        for norm, count in header_counts.items()
        if (total_pages >= 2 and count >= 2)
    }
    repeated_footers = {
        norm
        for norm, count in footer_counts.items()
        if (total_pages >= 2 and count >= 2)
    }

    # 4. Filter blocks
    cleaned_blocks: list[Block] = []
    for p, page_blocks in pages_map.items():
        text_blocks = [
            b for b in page_blocks if b.type in (BlockType.PARAGRAPH, BlockType.HEADING)
        ]
        first_b = text_blocks[0] if text_blocks else None
        last_b = text_blocks[-1] if text_blocks else None

        for b in page_blocks:
            # Check standalone page numbers
            if b.type in (
                BlockType.PARAGRAPH,
                BlockType.HEADING,
            ) and is_standalone_page_number(b.content):
                logger.debug("Dropping page number footer on p.%d: %r", p, b.content)
                continue

            # Check repeated header
            if b is first_b and b.type in (BlockType.PARAGRAPH, BlockType.HEADING):
                norm = re.sub(r"\d+", "#", b.content.strip().lower())
                if norm in repeated_headers:
                    logger.debug(
                        "Dropping running header on p.%d: %r", p, b.content[:40]
                    )
                    continue

            # Check repeated footer
            if b is last_b and b.type in (BlockType.PARAGRAPH, BlockType.HEADING):
                norm = re.sub(r"\d+", "#", b.content.strip().lower())
                if norm in repeated_footers:
                    logger.debug(
                        "Dropping running footer on p.%d: %r", p, b.content[:40]
                    )
                    continue

            cleaned_blocks.append(b)

    return cleaned_blocks


def clean_blocks(
    blocks: Sequence[Block],
    reindex_from: int | None = None,
) -> list[Block]:
    """Apply post-OCR cleaning: dehyphenation and header/footer filtering."""
    if not blocks:
        return []

    # 1. Filter repeated headers and footers
    filtered_blocks = remove_repeated_headers_footers(blocks)

    # 2. Dehyphenate translatable text blocks
    cleaned: list[Block] = []
    for idx, b in enumerate(filtered_blocks):
        new_content = b.content
        if b.type in (
            BlockType.PARAGRAPH,
            BlockType.HEADING,
            BlockType.LIST_ITEM,
            BlockType.FOOTNOTE,
        ):
            new_content = dehyphenate_text(b.content)

        block_id = f"b{reindex_from + idx}" if reindex_from is not None else b.id
        cleaned.append(
            Block(
                id=block_id,
                type=b.type,
                content=new_content,
                page=b.page,
                translatable=b.translatable,
                metadata=dict(b.metadata),
            )
        )

    return cleaned
