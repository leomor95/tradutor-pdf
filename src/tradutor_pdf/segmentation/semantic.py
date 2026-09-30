from __future__ import annotations

import logging
import re

from tradutor_pdf.pipeline import Block, BlockType, Chunk, Segmenter

logger = logging.getLogger(__name__)

NON_TRANSLATABLE_TYPES = {
    BlockType.CODE,
    BlockType.TABLE,
    BlockType.IMAGE,
    BlockType.FORMULA,
}


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count from text using word count heuristic."""
    words = text.split()
    if not words:
        return 0
    return max(1, int(len(words) * 1.3))


def block_to_markdown(block: Block) -> str:
    """Convert an individual block to its structural Markdown representation."""
    if block.type == BlockType.HEADING:
        level = block.metadata.get("heading_level", 1)
        try:
            lvl_int = max(1, min(6, int(level)))
        except (ValueError, TypeError):
            lvl_int = 1
        hashes = "#" * lvl_int
        return f"{hashes} {block.content}"

    elif block.type == BlockType.LIST_ITEM:
        text = block.content.strip()
        # If text already starts with bullet or number, normalize
        if re.match(r"^(\*|-|\+|\d+\.)\s+", text):
            return text
        return f"- {text}"

    elif block.type == BlockType.CODE:
        lang = block.metadata.get("language", "")
        return f"```{lang}\n{block.content}\n```"

    elif block.type == BlockType.TABLE:
        return block.content

    elif block.type == BlockType.IMAGE:
        alt = block.metadata.get("alt", "image")
        src = block.content or ""
        return f"![{alt}]({src})"

    elif block.type == BlockType.FORMULA:
        return f"$$\n{block.content}\n$$"

    elif block.type == BlockType.FOOTNOTE:
        return f"[^{block.id}]: {block.content}"

    else:
        return block.content


class SemanticSegmenter(Segmenter):
    """Semantic segmenter that groups blocks into chunks respecting syntactic boundaries.

    Ensures paragraphs and list items are not split across chunks and separates
    non-translatable blocks (tables, images, code, formulas) so they are preserved
    intact without being sent to the translation engine.
    """

    def segment(
        self,
        blocks: list[Block],
        max_tokens: int = 800,
        start_chunk_idx: int = 0,
    ) -> list[Chunk]:
        if not blocks:
            return []

        # Ensure non-translatable flags are consistently set
        for block in blocks:
            if block.type in NON_TRANSLATABLE_TYPES:
                block.translatable = False

        chunks: list[Chunk] = []
        current_translatable_blocks: list[Block] = []
        current_tokens = 0
        chunk_idx = start_chunk_idx

        def flush_translatable() -> None:
            nonlocal chunk_idx, current_translatable_blocks, current_tokens
            if not current_translatable_blocks:
                return

            orig_text = "\n\n".join(
                block_to_markdown(b) for b in current_translatable_blocks
            )
            p_start = min(b.page for b in current_translatable_blocks)
            p_end = max(b.page for b in current_translatable_blocks)
            t_count = estimate_tokens(orig_text)

            chunk = Chunk(
                id=f"chunk-{chunk_idx}",
                blocks=list(current_translatable_blocks),
                original_text=orig_text,
                page_start=p_start,
                page_end=p_end,
                token_count=t_count,
                status="pending",
            )
            chunks.append(chunk)
            chunk_idx += 1
            current_translatable_blocks = []
            current_tokens = 0

        for block in blocks:
            if not block.translatable:
                # Flush any pending translatable blocks before non-translatable block
                flush_translatable()

                # Build standalone chunk for non-translatable block
                b_md = block_to_markdown(block)
                chunks.append(
                    Chunk(
                        id=f"chunk-{chunk_idx}",
                        blocks=[block],
                        original_text=b_md,
                        translated_text=b_md,
                        page_start=block.page,
                        page_end=block.page,
                        token_count=estimate_tokens(b_md),
                        status="skipped",
                    )
                )
                chunk_idx += 1
                continue

            # Translatable block
            b_md = block_to_markdown(block)
            b_tokens = estimate_tokens(b_md)

            # If adding this block exceeds max_tokens and we already have blocks, flush
            if current_translatable_blocks and (current_tokens + b_tokens > max_tokens):
                flush_translatable()

            current_translatable_blocks.append(block)
            current_tokens += b_tokens

        flush_translatable()

        logger.info(
            "Semantically segmented %d blocks into %d chunks (max_tokens=%d)",
            len(blocks),
            len(chunks),
            max_tokens,
        )
        return chunks
