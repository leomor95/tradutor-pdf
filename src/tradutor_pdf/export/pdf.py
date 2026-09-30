from __future__ import annotations

import logging
from pathlib import Path

import pypandoc
import typst

from tradutor_pdf.export.epub import extract_title_from_markdown

logger = logging.getLogger(__name__)

DEFAULT_TYPST_PREAMBLE = """
#set page(
  paper: "a4",
  margin: (x: 2cm, top: 2.5cm, bottom: 2.5cm),
  numbering: "1",
)

#set text(
  font: ("DejaVu Sans", "Liberation Sans", "sans-serif"),
  size: 10pt,
  lang: "pt",
  region: "BR",
)

#set par(justify: true, leading: 0.65em)

// Headings
#show heading.where(level: 1): it => block(
  above: 1.4em,
  below: 0.8em,
  text(weight: "bold", size: 1.4em, it.body)
)
#show heading.where(level: 2): it => block(
  above: 1.2em,
  below: 0.6em,
  text(weight: "bold", size: 1.2em, it.body)
)
#show heading.where(level: 3): it => block(
  above: 1.0em,
  below: 0.5em,
  text(weight: "bold", size: 1.1em, it.body)
)

// Monospace Code Blocks
#show raw: set text(font: ("DejaVu Sans Mono", "Liberation Mono", "monospace"), size: 9pt)
#show raw.where(block: true): it => block(
  fill: rgb("#f6f8fa"),
  stroke: 0.5pt + rgb("#d0d7de"),
  inset: (x: 9pt, y: 7pt),
  radius: 4pt,
  width: 100%,
  it
)

// Inline code
#show raw.where(block: false): box.with(
  fill: rgb("#f6f8fa"),
  inset: (x: 3pt, y: 1pt),
  radius: 2pt,
)

// Table styling
#show table.cell.where(y: 0): set text(weight: "bold")
#set table(
  fill: (col, row) => if row == 0 { rgb("#f0f3f6") } else if calc.even(row) { rgb("#fafbfc") } else { none },
  inset: 6pt,
)

// Figures and images
#show figure.caption: set text(size: 9pt, style: "italic")
"""


class PdfExporter:
    """Exports Markdown documents to PDF via Pandoc and Typst."""

    def __init__(self, preamble: str | None = None, lang: str = "pt-BR"):
        self.preamble = preamble if preamble is not None else DEFAULT_TYPST_PREAMBLE
        self.lang = lang

    def export(
        self,
        markdown_path: Path,
        output_format: str = "pdf",
        destination_dir: Path | str = Path("."),
        title: str | None = None,
    ) -> Path:
        """Export Markdown file to PDF via Typst compilation."""
        source_file = Path(markdown_path).resolve()
        if not source_file.is_file():
            raise FileNotFoundError(f"Source markdown file not found: {source_file}")

        dest = Path(destination_dir).resolve()
        if dest.suffix.lower() == ".pdf":
            target_file = dest
            target_dir = dest.parent
        else:
            target_dir = dest
            out_stem = source_file.stem
            target_file = target_dir / f"{out_stem}.pdf"

        target_dir.mkdir(parents=True, exist_ok=True)

        content = source_file.read_text(encoding="utf-8")
        doc_title = title or extract_title_from_markdown(
            content,
            default=source_file.stem.replace("_", " ").title(),
        )

        logger.info("Converting %s to Typst markup (title=%r)", source_file, doc_title)
        typst_markup = pypandoc.convert_file(
            str(source_file),
            to="typst",
            format="markdown",
        )

        # Assemble full Typst document with styling preamble
        full_typst = f"{self.preamble.strip()}\n\n{typst_markup}"

        logger.info("Compiling Typst to PDF %s", target_file)
        try:
            typst.compile(
                full_typst.encode("utf-8"),
                output=str(target_file),
                root=str(source_file.parent),
            )
        except Exception as exc:
            logger.error("Typst compilation failed: %s", exc)
            raise RuntimeError(f"Typst compilation failed: {exc}") from exc

        return target_file
