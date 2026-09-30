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


def test_docling_extractor_headings_and_lists():
    fixture_pdf = Path("tests/fixtures/headings_lists.pdf")
    assert fixture_pdf.is_file()

    extractor = DoclingExtractor(do_ocr=False)
    blocks = extractor.extract(fixture_pdf)

    headings = [b for b in blocks if b.type == BlockType.HEADING]
    lists = [b for b in blocks if b.type == BlockType.LIST_ITEM]

    assert len(headings) >= 3
    # Check heading levels
    levels = [h.metadata.get("heading_level") for h in headings]
    assert 1 in levels
    assert 2 in levels
    assert len(lists) >= 3


def test_docling_extractor_tables_and_images(tmp_path: Path):
    fixture_pdf = Path("tests/fixtures/tables_images.pdf")
    assert fixture_pdf.is_file()

    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(do_ocr=False, assets_dir=assets_dir)
    blocks = extractor.extract(fixture_pdf)

    tables = [b for b in blocks if b.type == BlockType.TABLE]
    images = [b for b in blocks if b.type == BlockType.IMAGE]

    assert len(tables) >= 1
    assert not tables[0].translatable
    assert "Connection Pool" in tables[0].content or "Component" in tables[0].content

    assert len(images) >= 1
    assert not images[0].translatable
    assert images[0].content.startswith("assets/")
    # Check image was saved to disk
    saved_images = list(assets_dir.glob("*.png"))
    assert len(saved_images) >= 1


def test_docling_extractor_code_blocks():
    fixture_pdf = Path("tests/fixtures/code_blocks.pdf")
    assert fixture_pdf.is_file()

    extractor = DoclingExtractor(do_ocr=False)
    blocks = extractor.extract(fixture_pdf)

    code_blocks = [b for b in blocks if b.type == BlockType.CODE]
    assert len(code_blocks) >= 1
    assert not code_blocks[0].translatable
    assert any(
        "process_batch" in b.content or "export WORKER_ENV" in b.content
        for b in code_blocks
    )


def test_get_pdf_page_count():
    from tradutor_pdf.extraction.docling_extractor import get_pdf_page_count

    fixture_10p = Path("tests/fixtures/benchmark_10p.pdf")
    assert get_pdf_page_count(fixture_10p) == 10

    fixture_1p = Path("tests/fixtures/simple.pdf")
    assert get_pdf_page_count(fixture_1p) == 1


def test_docling_extractor_iter_windows():
    fixture_10p = Path("tests/fixtures/benchmark_10p.pdf")
    extractor = DoclingExtractor(do_ocr=False, default_window_size=3)

    windows = list(extractor.iter_windows(fixture_10p, window_size=3))
    # 10 pages in windows of 3: (1, 3), (4, 6), (7, 9), (10, 10)
    assert len(windows) == 4
    assert windows[0][0] == (1, 3)
    assert windows[1][0] == (4, 6)
    assert windows[2][0] == (7, 9)
    assert windows[3][0] == (10, 10)

    # Check block IDs are contiguous
    all_blocks = []
    for _pr, w_blocks in windows:
        all_blocks.extend(w_blocks)

    block_ids = [b.id for b in all_blocks]
    expected_ids = [f"b{i}" for i in range(len(all_blocks))]
    assert block_ids == expected_ids
    assert len(all_blocks) > 0


def test_docling_extractor_images_not_kept_in_memory(tmp_path: Path):
    fixture_pdf = Path("tests/fixtures/tables_images.pdf")
    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(do_ocr=False, assets_dir=assets_dir)
    blocks = extractor.extract(fixture_pdf)

    image_blocks = [b for b in blocks if b.type == BlockType.IMAGE]
    assert len(image_blocks) >= 1

    for img_block in image_blocks:
        # metadata must contain image_path string, never PIL Image or raw bytes
        img_path_str = img_block.metadata.get("image_path")
        assert isinstance(img_path_str, str)
        assert Path(img_path_str).is_file()
        assert "image" not in img_block.metadata
        assert "img_obj" not in img_block.metadata
