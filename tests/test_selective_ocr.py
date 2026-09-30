from pathlib import Path

import pypdfium2 as pdfium
import typst
from fpdf import FPDF

from tradutor_pdf.extraction.docling_extractor import (
    DoclingExtractor,
    partition_page_range,
)


def test_partition_page_range_empty():
    assert partition_page_range(5, 3, set()) == []


def test_partition_page_range_single_page():
    assert partition_page_range(1, 1, set()) == [(1, 1, False)]
    assert partition_page_range(1, 1, {1}) == [(1, 1, True)]


def test_partition_page_range_homogeneous():
    assert partition_page_range(1, 5, set()) == [(1, 5, False)]
    assert partition_page_range(1, 5, {1, 2, 3, 4, 5}) == [(1, 5, True)]


def test_partition_page_range_heterogeneous():
    # 1: False, 2: True, 3: False, 4: True
    segments = partition_page_range(1, 4, {2, 4})
    assert segments == [
        (1, 1, False),
        (2, 2, True),
        (3, 3, False),
        (4, 4, True),
    ]

    # Contiguous groups
    segments2 = partition_page_range(1, 10, {3, 4, 5, 8})
    assert segments2 == [
        (1, 2, False),
        (3, 5, True),
        (6, 7, False),
        (8, 8, True),
        (9, 10, False),
    ]


def test_docling_extractor_properties():
    ext_no_ocr = DoclingExtractor(do_ocr=False)
    assert ext_no_ocr.do_ocr is False
    assert ext_no_ocr._ocr_converter is None
    assert ext_no_ocr._converter is ext_no_ocr._no_ocr_converter

    ext_auto = DoclingExtractor(do_ocr="auto", ocr_languages=["eng"])
    assert ext_auto.do_ocr == "auto"
    assert ext_auto.ocr_languages == ("eng",)
    assert ext_auto._ocr_converter is None


def test_docling_extractor_selective_ocr(tmp_path: Path):
    # Page 1: digital text
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(text="Digital Chapter One", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(
        0, 8, "This is digital text on page 1 that should be parsed without OCR."
    )
    p1_path = tmp_path / "p1.pdf"
    pdf.output(str(p1_path))

    # Page 2: rasterized / scanned image
    typ_p2 = tmp_path / "p2.typ"
    typ_p2.write_text(
        "= Scanned Architecture\n\nThis is scanned text extracted via Tesseract OCR engine.\n"
    )
    pdf2_bytes = typst.compile(typ_p2)
    doc2 = pdfium.PdfDocument(pdf2_bytes)
    pil_p2 = doc2.get_page(0).render(scale=2.0).to_pil()
    doc2.close()

    p2_scanned_path = tmp_path / "p2_scanned.pdf"
    pil_p2.save(str(p2_scanned_path), format="PDF")

    # Combine into mixed PDF
    mixed = pdfium.PdfDocument.new()
    d1 = pdfium.PdfDocument(str(p1_path))
    d2 = pdfium.PdfDocument(str(p2_scanned_path))
    mixed.import_pages(d1)
    mixed.import_pages(d2)

    mixed_pdf_path = tmp_path / "mixed.pdf"
    mixed.save(str(mixed_pdf_path))
    mixed.close()
    d1.close()
    d2.close()

    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(do_ocr="auto", assets_dir=assets_dir)
    blocks = extractor.extract(mixed_pdf_path)

    assert len(blocks) >= 2

    # Check page 1 blocks
    p1_blocks = [b for b in blocks if b.page == 1]
    assert len(p1_blocks) >= 1
    assert any("Digital Chapter" in b.content for b in p1_blocks)
    assert all(b.metadata.get("ocr") is False for b in p1_blocks)

    # Check page 2 blocks (must have ocr=True)
    p2_blocks = [b for b in blocks if b.page == 2]
    assert len(p2_blocks) >= 1
    assert any(
        "Scanned Architecture" in b.content or "scanned text" in b.content.lower()
        for b in p2_blocks
    )
    assert all(b.metadata.get("ocr") is True for b in p2_blocks)
