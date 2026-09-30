from __future__ import annotations

import logging

from tradutor_pdf.pipeline import Block, BlockType, Chunk, Segmenter

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Rough estimation of token count from text using word count heuristic."""
    words = text.split()
    if not words:
        return 0
    return max(1, int(len(words) * 1.3))


def block_to_markdown(block: Block) -> str:
    """Convert an individual block to its basic markdown representation."""
    if block.type == BlockType.HEADING:
        level = block.metadata.get("heading_level", 2)
        # Constrain heading level between 1 and 6
        hashes = "#" * max(1, min(6, int(level)))
        return f"{hashes} {block.content}"
    elif block.type == BlockType.LIST_ITEM:
        return f"- {block.content}"
    elif block.type == BlockType.CODE:
        lang = block.metadata.get("language", "")
        return f"```{lang}\n{block.content}\n```"
    elif block.type == BlockType.IMAGE:
        alt = block.metadata.get("alt", "image")
        src = block.content or ""
        return f"![{alt}]({src})"
    else:
        return block.content


class NaiveSegmenter(Segmenter):
    """Naive segmenter that groups blocks into chunks based on maximum token count."""

    def segment(
        self,
        blocks: list[Block],
        max_tokens: int = 800,
    ) -> list[Chunk]:
        if not blocks:
            return []

        chunks: list[Chunk] = []
        current_blocks: list[Block] = []
        current_tokens = 0
        chunk_idx = 0

        def build_chunk(b_list: list[Block], c_id: int) -> Chunk:
            orig_text = "\n\n".join(block_to_markdown(b) for b in b_list)
            p_start = min(b.page for b in b_list)
            p_end = max(b.page for b in b_list)
            t_count = estimate_tokens(orig_text)
            return Chunk(
                id=f"chunk-{c_id}",
                blocks=list(b_list),
                original_text=orig_text,
                page_start=p_start,
                page_end=p_end,
                token_count=t_count,
                status="pending",
            )

        for block in blocks:
            b_md = block_to_markdown(block)
            b_tokens = estimate_tokens(b_md)

            if current_blocks and (current_tokens + b_tokens > max_tokens):
                chunks.append(build_chunk(current_blocks, chunk_idx))
                chunk_idx += 1
                current_blocks = [block]
                current_tokens = b_tokens
            else:
                current_blocks.append(block)
                current_tokens += b_tokens

        if current_blocks:
            chunks.append(build_chunk(current_blocks, chunk_idx))

        logger.info(
            "Segmented %d blocks into %d chunks (max_tokens=%d)",
            len(blocks),
            len(chunks),
            max_tokens,
        )
        return chunks
