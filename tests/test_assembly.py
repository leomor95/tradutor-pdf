from pathlib import Path

from tradutor_pdf.assembly.markdown import (
    MarkdownAssembler,
    compute_file_sha256,
    get_default_output_path,
)
from tradutor_pdf.pipeline import Assembler, Chunk


def test_assembler_protocol():
    assembler = MarkdownAssembler()
    assert isinstance(assembler, Assembler)


def test_compute_file_sha256(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("Hello world", encoding="utf-8")
    expected_hash = "64ec88ca00b268e5ba1a35678a1b5316d212f4f366b2477232534a8aeca37f3c"
    assert compute_file_sha256(f) == expected_hash


def test_get_default_output_path(tmp_path: Path):
    sample = tmp_path / "document.pdf"
    sample.write_bytes(b"%PDF-1.4...")
    h = compute_file_sha256(sample)

    out = get_default_output_path(sample)
    assert out.name == "document.pt-BR.md"
    assert h in str(out)
    assert ".cache" in str(out)
    assert "output" in str(out)


def test_assemble_chunks(tmp_path: Path):
    assembler = MarkdownAssembler()
    chunks = [
        Chunk(
            id="c1",
            original_text="# Title",
            translated_text="# Título",
            status="translated",
        ),
        Chunk(
            id="c2",
            original_text="Paragraph",
            translated_text="Parágrafo",
            status="translated",
        ),
        Chunk(
            id="c3",
            original_text="Untranslated text",
            translated_text=None,
            status="pending",
        ),
    ]

    out_file = tmp_path / "sub" / "output.md"
    result_path = assembler.assemble(chunks, out_file)

    assert result_path == out_file
    assert out_file.exists()

    content = out_file.read_text(encoding="utf-8")
    assert "# Título\n\nParágrafo\n\nUntranslated text\n" == content


def test_assemble_preserves_untranslated_blocks_and_assets(tmp_path: Path):
    from tradutor_pdf.pipeline import Block, BlockType

    assembler = MarkdownAssembler()

    # Create dummy source image
    src_img = tmp_path / "cache" / "assets" / "img_001.png"
    src_img.parent.mkdir(parents=True, exist_ok=True)
    src_img.write_bytes(b"\x89PNG\r\n\x1a\n...")

    chunks = [
        Chunk(
            id="c0",
            original_text="# System Design",
            translated_text="# Projeto do Sistema",
            status="translated",
        ),
        Chunk(
            id="c1",
            blocks=[
                Block(
                    id="b1",
                    type=BlockType.TABLE,
                    content="| Param | Val |\n|---|---|\n| T | 10s |",
                    page=1,
                    translatable=False,
                )
            ],
            status="skipped",
        ),
        Chunk(
            id="c2",
            blocks=[
                Block(
                    id="b2",
                    type=BlockType.IMAGE,
                    content="assets/img_001.png",
                    page=1,
                    translatable=False,
                    metadata={
                        "alt": "Cluster Diagram",
                        "image_path": str(src_img),
                    },
                )
            ],
            status="skipped",
        ),
        Chunk(
            id="c3",
            blocks=[
                Block(
                    id="b3",
                    type=BlockType.CODE,
                    content="echo 'hello'",
                    page=1,
                    translatable=False,
                    metadata={"language": "bash"},
                )
            ],
            status="skipped",
        ),
    ]

    out_file = tmp_path / "dest" / "output.pt-BR.md"
    assembler.assemble(chunks, out_file)

    assert out_file.is_file()
    text = out_file.read_text(encoding="utf-8")

    # Verify order and content
    assert "# Projeto do Sistema" in text
    assert "| Param | Val |\n|---|---|\n| T | 10s |" in text
    assert "![Cluster Diagram](assets/img_001.png)" in text
    assert "```bash\necho 'hello'\n```" in text

    # Verify asset was copied to destination directory
    dest_asset = tmp_path / "dest" / "assets" / "img_001.png"
    assert dest_asset.is_file()
    assert dest_asset.read_bytes() == b"\x89PNG\r\n\x1a\n..."


def test_assemble_complex_table_html(tmp_path: Path):
    from tradutor_pdf.pipeline import Block, BlockType

    assembler = MarkdownAssembler()
    html_table = "<table><tr><td colspan='2'>Merged Header</td></tr><tr><td>A</td><td>B</td></tr></table>"
    chunks = [
        Chunk(
            id="c0",
            blocks=[
                Block(
                    id="b0",
                    type=BlockType.TABLE,
                    content="| Simple Fallback |",
                    page=1,
                    translatable=False,
                    metadata={"html": html_table},
                )
            ],
            status="skipped",
        )
    ]

    out_file = tmp_path / "out.md"
    assembler.assemble(chunks, out_file)
    text = out_file.read_text(encoding="utf-8")
    assert html_table in text


def test_incremental_assembly(tmp_path: Path):
    from tradutor_pdf.pipeline import Block, BlockType

    assembler = MarkdownAssembler()
    out_file = tmp_path / "incremental" / "output.pt-BR.md"

    # Initialize file
    assembler.init_incremental(out_file, clear=True)
    assert out_file.is_file()
    assert out_file.read_text(encoding="utf-8") == ""

    # Append first chunk
    c1 = Chunk(
        id="c1",
        original_text="# Title",
        translated_text="# Título Principal",
        status="translated",
    )
    assembler.append_chunk(c1, out_file)
    assert out_file.read_text(encoding="utf-8") == "# Título Principal\n"

    # Append second chunk
    c2 = Chunk(
        id="c2",
        original_text="First paragraph.",
        translated_text="Primeiro parágrafo traduzido.",
        status="translated",
    )
    assembler.append_chunk(c2, out_file)
    expected = "# Título Principal\n\nPrimeiro parágrafo traduzido.\n"
    assert out_file.read_text(encoding="utf-8") == expected

    # Append third chunk with image asset
    src_img = tmp_path / "dummy.png"
    src_img.write_bytes(b"\x89PNG dummy image")
    c3 = Chunk(
        id="c3",
        blocks=[
            Block(
                id="b_img",
                type=BlockType.IMAGE,
                content="assets/dummy.png",
                page=1,
                translatable=False,
                metadata={"alt": "Diagram", "image_path": str(src_img)},
            )
        ],
        status="skipped",
    )
    assembler.append_chunk(c3, out_file)

    text = out_file.read_text(encoding="utf-8")
    assert "![Diagram](assets/dummy.png)" in text
    assert (tmp_path / "incremental" / "assets" / "dummy.png").is_file()
