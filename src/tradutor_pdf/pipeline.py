from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    IMAGE = "image"
    CODE = "code"
    FOOTNOTE = "footnote"
    FORMULA = "formula"
    UNKNOWN = "unknown"


@dataclass
class Block:
    """Represents an extracted structural block from a document."""

    id: str
    type: BlockType
    content: str
    page: int
    translatable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """Represents a segment of text/blocks to be translated as a unit."""

    id: str
    blocks: list[Block] = field(default_factory=list)
    original_text: str = ""
    translated_text: str | None = None
    page_start: int = 1
    page_end: int = 1
    token_count: int = 0
    status: str = "pending"  # pending, translated, error, skipped
    error_message: str | None = None


@dataclass
class Document:
    """Represents a full or windowed document undergoing translation."""

    source_path: Path
    sha256: str
    total_pages: int
    blocks: list[Block] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Extractor(Protocol):
    """Protocol for extracting structural blocks from a PDF document."""

    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
    ) -> list[Block]:
        """Extract blocks from the document, optionally restricted to a page range."""
        ...


@runtime_checkable
class Segmenter(Protocol):
    """Protocol for grouping extracted blocks into translatable chunks."""

    def segment(
        self,
        blocks: list[Block],
        max_tokens: int = 800,
    ) -> list[Chunk]:
        """Group blocks into chunks respecting semantic boundaries and token limits."""
        ...


@runtime_checkable
class Translator(Protocol):
    """Protocol for translating a single chunk of text."""

    def translate(
        self,
        chunk: Chunk,
        previous_context: str | None = None,
    ) -> str:
        """Translate chunk content to target language, returning translated text."""
        ...


@runtime_checkable
class Assembler(Protocol):
    """Protocol for assembling translated chunks and assets into final Markdown."""

    def assemble(
        self,
        chunks: list[Chunk],
        output_path: Path,
    ) -> Path:
        """Recombine translated and untranslated content into Markdown file."""
        ...


@runtime_checkable
class Exporter(Protocol):
    """Protocol for converting Markdown into destination format (PDF/EPUB/MD)."""

    def export(
        self,
        markdown_path: Path,
        output_format: str,
        destination_dir: Path,
    ) -> Path:
        """Export Markdown document to destination directory in specified format."""
        ...
