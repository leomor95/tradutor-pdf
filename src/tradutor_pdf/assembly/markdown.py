from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from tradutor_pdf.config import find_project_root
from tradutor_pdf.pipeline import Assembler, Block, BlockType, Chunk

logger = logging.getLogger(__name__)


def compute_file_sha256(path: Path) -> str:
    """Compute the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_default_output_path(source_path: Path, sha256_hash: str | None = None) -> Path:
    """Return the default output path in .cache/<sha256>/output/<stem>.pt-BR.md."""
    source = Path(source_path)
    if sha256_hash is None:
        if source.is_file():
            sha256_hash = compute_file_sha256(source)
        else:
            sha256_hash = hashlib.sha256(source.name.encode("utf-8")).hexdigest()

    cache_dir = find_project_root() / ".cache" / sha256_hash / "output"
    output_filename = f"{source.stem}.pt-BR.md"
    return cache_dir / output_filename


def format_block_for_markdown(block: Block) -> str:
    """Format an individual block for Markdown assembly, respecting complex tables and assets."""
    if block.type == BlockType.TABLE:
        html_content = block.metadata.get("html", "")
        # Use HTML if the table is complex (contains merged cells via colspan or rowspan)
        if html_content and (
            "colspan" in html_content
            or "rowspan" in html_content
            or block.metadata.get("is_complex")
        ):
            return html_content
        return block.content.strip()

    elif block.type == BlockType.IMAGE:
        alt = block.metadata.get("alt", "image")
        src = block.content.strip()
        if src.startswith("![") and "](" in src:
            return src
        return f"![{alt}]({src})"

    elif block.type == BlockType.CODE:
        content = block.content.strip()
        if content.startswith("```"):
            return content
        lang = block.metadata.get("language", "")
        return f"```{lang}\n{content}\n```"

    elif block.type == BlockType.FORMULA:
        content = block.content.strip()
        if content.startswith("$$"):
            return content
        return f"$$\n{content}\n$$"

    return block.content.strip()


def format_chunk_for_markdown(chunk: Chunk, output_dir: Path | None = None) -> str:
    """Format a single chunk for Markdown, ensuring image assets are copied to output_dir/assets."""
    if output_dir is not None:
        for block in chunk.blocks:
            if block.type == BlockType.IMAGE and block.metadata.get("image_path"):
                src_img = Path(block.metadata["image_path"])
                if src_img.is_file():
                    dest_img = output_dir / block.content
                    try:
                        if dest_img.resolve() != src_img.resolve():
                            dest_img.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src_img, dest_img)
                    except OSError as exc:
                        logger.warning(
                            "Could not copy image asset %s -> %s: %s",
                            src_img,
                            dest_img,
                            exc,
                        )

    # Untranslated / skipped chunks
    if chunk.status == "skipped" or (
        chunk.blocks and all(not b.translatable for b in chunk.blocks)
    ):
        block_parts = [format_block_for_markdown(b) for b in chunk.blocks]
        return "\n\n".join(p for p in block_parts if p)
    elif chunk.translated_text is not None and chunk.status == "translated":
        return chunk.translated_text.strip()
    else:
        return chunk.original_text.strip()


class MarkdownAssembler(Assembler):
    """Assembles translated chunks into a Markdown document incrementally or all at once.

    Re-inserts untranslated blocks (tables, images, code, formulas) in their
    original document positions, formats complex tables with HTML where needed,
    ensures image assets are copied to the output directory, and supports incremental
    appending as chunks are completed.
    """

    def init_incremental(self, output_path: Path, clear: bool = True) -> Path:
        """Initialize the output markdown file, optionally clearing it if starting fresh."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if clear or not out.exists():
            out.write_text("", encoding="utf-8")
        return out

    def append_chunk(self, chunk: Chunk, output_path: Path) -> None:
        """Append a completed chunk to the output markdown file incrementally."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        content = format_chunk_for_markdown(chunk, output_dir=out.parent).strip()
        if not content:
            return

        existing = out.read_text(encoding="utf-8") if out.exists() else ""
        if existing.strip():
            new_text = f"{existing.rstrip('\n')}\n\n{content}\n"
        else:
            new_text = f"{content}\n"
        out.write_text(new_text, encoding="utf-8")

    def sync_incremental(self, chunks: list[Chunk], output_path: Path) -> Path:
        """Write all available chunks in order to output markdown file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Assembling %d chunks into markdown file: %s", len(chunks), out)

        parts: list[str] = []
        for chunk in chunks:
            chunk_text = format_chunk_for_markdown(chunk, output_dir=out.parent)
            if chunk_text:
                parts.append(chunk_text)

        final_md = "\n\n".join(parts)
        if final_md:
            final_md += "\n"

        out.write_text(final_md, encoding="utf-8")
        logger.info("Saved translated markdown (%d bytes) to %s", len(final_md), out)
        return out

    def assemble(
        self,
        chunks: list[Chunk],
        output_path: Path,
    ) -> Path:
        return self.sync_incremental(chunks, output_path)
