from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class MarkdownExporter:
    """Exports Markdown documents and their assets to a destination directory."""

    def export(
        self,
        markdown_path: Path,
        output_format: str = "md",
        destination_dir: Path | str = Path("."),
    ) -> Path:
        """Export Markdown file and accompanying assets folder to destination."""
        source_file = Path(markdown_path).resolve()
        if not source_file.is_file():
            raise FileNotFoundError(f"Source markdown file not found: {source_file}")

        dest = Path(destination_dir).resolve()
        if dest.suffix.lower() in (".md", ".markdown"):
            target_dir = dest.parent
            target_file = dest
        else:
            target_dir = dest
            target_file = target_dir / source_file.name

        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy markdown file
        shutil.copy2(source_file, target_file)
        logger.info("Exported markdown file to %s", target_file)

        # Copy assets directory if it exists alongside source markdown
        assets_source = source_file.parent / "assets"
        if assets_source.is_dir():
            assets_dest = target_dir / "assets"
            shutil.copytree(assets_source, assets_dest, dirs_exist_ok=True)
            logger.info("Copied assets from %s to %s", assets_source, assets_dest)

        return target_file
