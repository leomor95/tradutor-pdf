from pathlib import Path

import pytest
from fpdf import FPDF

from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.pipeline import BlockType, Extractor


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(text="Chapter 1: The Beginning", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(
        w=0,
        h=10,
        text="This is a simple paragraph about Python development and pipelines.",
    )
    output_path = tmp_path / "sample.pdf"
    pdf.output(str(output_path))
    return output_path


def test_docling_extractor_implements_protocol():
    extractor = DoclingExtractor(do_ocr=False)
    assert isinstance(extractor, Extractor)


def test_docling_extractor_missing_file():
    extractor = DoclingExtractor(do_ocr=False)
    with pytest.raises(FileNotFoundError):
        extractor.extract(Path("/nonexistent/file.pdf"))


def test_docling_extractor_extracts_blocks(sample_pdf_path: Path):
    extractor = DoclingExtractor(do_ocr=False)
    blocks = extractor.extract(sample_pdf_path)

    assert len(blocks) >= 2
    heading_blocks = [b for b in blocks if b.type == BlockType.HEADING]
    paragraph_blocks = [b for b in blocks if b.type == BlockType.PARAGRAPH]

    assert len(heading_blocks) >= 1
    assert "Beginning" in heading_blocks[0].content
    assert len(paragraph_blocks) >= 1
    assert "Python development" in paragraph_blocks[0].content
    assert all(b.page == 1 for b in blocks)
