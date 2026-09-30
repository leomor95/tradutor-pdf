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
