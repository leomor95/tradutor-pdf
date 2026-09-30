from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from tradutor_pdf.config import find_project_root
from tradutor_pdf.pipeline import Assembler, Chunk

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


class MarkdownAssembler(Assembler):
    """Assembles translated chunks into a final Markdown document."""

    def assemble(
        self,
        chunks: list[Chunk],
        output_path: Path,
    ) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Assembling %d chunks into markdown file: %s", len(chunks), out)

        parts: list[str] = []
        for chunk in chunks:
            # Use translated text if available, otherwise fallback to original
            if chunk.translated_text is not None and chunk.status in (
                "translated",
                "skipped",
            ):
                content = chunk.translated_text.strip()
            else:
                content = chunk.original_text.strip()

            if content:
                parts.append(content)

        final_md = "\n\n".join(parts)
        if final_md:
            final_md += "\n"

        out.write_text(final_md, encoding="utf-8")
        logger.info("Saved translated markdown (%d bytes) to %s", len(final_md), out)
        return out
