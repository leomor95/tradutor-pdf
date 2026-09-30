from pathlib import Path

from tradutor_pdf.pipeline import (
    Assembler,
    Block,
    BlockType,
    Chunk,
    Document,
    Exporter,
    Extractor,
    Segmenter,
    Translator,
)


class DummyExtractor:
    def extract(
        self, source_path: Path, pages: tuple[int, int] | None = None
    ) -> list[Block]:
        return []


class DummySegmenter:
    def segment(self, blocks: list[Block], max_tokens: int = 800) -> list[Chunk]:
        return []


class DummyTranslator:
    def translate(self, chunk: Chunk, previous_context: str | None = None) -> str:
        return "traduzido"


class DummyAssembler:
    def assemble(self, chunks: list[Chunk], output_path: Path) -> Path:
        return output_path


class DummyExporter:
    def export(
        self, markdown_path: Path, output_format: str, destination_dir: Path
    ) -> Path:
        return destination_dir / f"output.{output_format}"


def test_pipeline_protocols_runtime_checkable() -> None:
    assert isinstance(DummyExtractor(), Extractor)
    assert isinstance(DummySegmenter(), Segmenter)
    assert isinstance(DummyTranslator(), Translator)
    assert isinstance(DummyAssembler(), Assembler)
    assert isinstance(DummyExporter(), Exporter)


def test_pipeline_data_structures() -> None:
    block = Block(
        id="b1",
        type=BlockType.PARAGRAPH,
        content="Hello world",
        page=1,
        translatable=True,
    )
    assert block.type == BlockType.PARAGRAPH
    assert block.translatable is True

    chunk = Chunk(
        id="c1",
        blocks=[block],
        original_text="Hello world",
        page_start=1,
        page_end=1,
        token_count=2,
    )
    assert chunk.status == "pending"
    assert len(chunk.blocks) == 1

    doc = Document(
        source_path=Path("sample.pdf"),
        sha256="abc123hash",
        total_pages=10,
        blocks=[block],
        chunks=[chunk],
    )
    assert doc.total_pages == 10
    assert doc.sha256 == "abc123hash"
