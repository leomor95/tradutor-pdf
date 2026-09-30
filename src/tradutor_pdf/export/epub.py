from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import pypandoc

logger = logging.getLogger(__name__)


def extract_title_from_markdown(content: str, default: str = "Documento") -> str:
    """Extract a suitable document title from Markdown content."""
    # Check for frontmatter title
    fm_match = re.search(
        r"^---\s*\n.*?title:\s*[\"']?([^\"'\n]+)[\"']?.*?\n---", content, re.DOTALL
    )
    if fm_match:
        return fm_match.group(1).strip()

    # Check for first H1 header
    h1_match = re.search(r"^#\s+([^\n#]+)", content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    # Check for first H2 header
    h2_match = re.search(r"^##\s+([^\n#]+)", content, re.MULTILINE)
    if h2_match:
        return h2_match.group(1).strip()

    return default


def validate_epub(epub_path: Path) -> tuple[bool, str]:
    """Validate EPUB file using project-local or system epubcheck.

    Returns (is_valid, output_message).
    """
    epub_file = Path(epub_path).resolve()
    if not epub_file.is_file():
        return False, f"EPUB file not found: {epub_file}"

    # Search for project bin/epubcheck wrapper
    repo_root = Path(__file__).resolve().parents[3]
    local_epubcheck = repo_root / "bin" / "epubcheck"

    cmd: list[str]
    if local_epubcheck.is_file() and os_access_executable(local_epubcheck):
        cmd = [str(local_epubcheck), str(epub_file)]
    elif shutil.which("epubcheck"):
        cmd = ["epubcheck", str(epub_file)]
    else:
        logger.warning("epubcheck executable not found for validation.")
        return True, "epubcheck executable not found; validation skipped"

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        is_valid = proc.returncode == 0
        return is_valid, proc.stdout
    except (subprocess.SubprocessError, OSError) as exc:
        logger.error("Failed to run epubcheck: %s", exc)
        return False, str(exc)


def os_access_executable(path: Path) -> bool:
    import os

    return os.access(path, os.X_OK)


class EpubExporter:
    """Exports Markdown documents to EPUB via Pandoc with metadata, TOC, and assets."""

    def __init__(self, lang: str = "pt-BR"):
        self.lang = lang

    def export(
        self,
        markdown_path: Path,
        output_format: str = "epub",
        destination_dir: Path | str = Path("."),
        title: str | None = None,
    ) -> Path:
        """Export Markdown file to EPUB at destination."""
        source_file = Path(markdown_path).resolve()
        if not source_file.is_file():
            raise FileNotFoundError(f"Source markdown file not found: {source_file}")

        dest = Path(destination_dir).resolve()
        if dest.suffix.lower() == ".epub":
            target_file = dest
            target_dir = dest.parent
        else:
            target_dir = dest
            out_stem = source_file.stem
            target_file = target_dir / f"{out_stem}.epub"

        target_dir.mkdir(parents=True, exist_ok=True)

        content = source_file.read_text(encoding="utf-8")
        doc_title = title or extract_title_from_markdown(
            content,
            default=source_file.stem.replace("_", " ").title(),
        )

        # Resource path includes source markdown parent and its assets folder
        resource_paths = [str(source_file.parent)]
        assets_dir = source_file.parent / "assets"
        if assets_dir.is_dir():
            resource_paths.append(str(assets_dir))

        extra_args = [
            "--toc",
            "--toc-depth=3",
            "-M",
            f"title={doc_title}",
            "-M",
            f"lang={self.lang}",
            f"--resource-path={':'.join(resource_paths)}",
        ]

        logger.info(
            "Converting %s to EPUB %s (title=%r)", source_file, target_file, doc_title
        )
        pypandoc.convert_file(
            str(source_file),
            to="epub",
            outputfile=str(target_file),
            extra_args=extra_args,
        )

        return target_file
