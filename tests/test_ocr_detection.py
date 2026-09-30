from pathlib import Path

import pypdfium2 as pdfium
import pytest
from fpdf import FPDF
from PIL import Image

from tradutor_pdf.config import ConfigError, OCRConfig, load_settings
from tradutor_pdf.extraction.detection import (
    count_valid_text_chars,
    detect_pages_needing_ocr,
    is_page_text_layer_usable,
)


def test_count_valid_text_chars():
    assert count_valid_text_chars("") == 0
    assert count_valid_text_chars("   \n\r\t  ") == 0
    assert count_valid_text_chars("Hello, World! 123") == 13
    assert count_valid_text_chars("### --- === ***") == 0


def test_is_page_text_layer_usable_digital():
    fixture_pdf = Path("tests/fixtures/simple.pdf")
    assert fixture_pdf.is_file()

    doc = pdfium.PdfDocument(str(fixture_pdf))
    try:
        page = doc.get_page(0)
        try:
            assert is_page_text_layer_usable(page, min_chars=50) is True
            assert is_page_text_layer_usable(page, min_chars=1000) is False
        finally:
            page.close()
    finally:
        doc.close()


def test_detect_pages_needing_ocr_digital_fixture():
    fixture_pdf = Path("tests/fixtures/simple.pdf")
    needing_ocr = detect_pages_needing_ocr(fixture_pdf, min_chars=50)
    assert needing_ocr == set()


def test_detect_pages_needing_ocr_scanned(tmp_path: Path):
    # Create an image-only scanned PDF (no text stream)
    img = Image.new("RGB", (600, 800), color="white")
    scanned_pdf = tmp_path / "synthetic_scanned.pdf"
    img.save(scanned_pdf, format="PDF")

    needing_ocr = detect_pages_needing_ocr(scanned_pdf, min_chars=50)
    assert needing_ocr == {1}


def test_detect_pages_needing_ocr_mixed(tmp_path: Path):
    # Page 1: digital text
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        0, 10, "This is page one with plenty of digital text to exceed the threshold."
    )
    p1_path = tmp_path / "p1.pdf"
    pdf.output(str(p1_path))

    # Page 2: image only
    img = Image.new("RGB", (400, 600), color="white")
    p2_path = tmp_path / "p2.pdf"
    img.save(p2_path, format="PDF")

    # Merge
    merged = pdfium.PdfDocument.new()
    d1 = pdfium.PdfDocument(str(p1_path))
    d2 = pdfium.PdfDocument(str(p2_path))
    merged.import_pages(d1)
    merged.import_pages(d2)

    mixed_path = tmp_path / "mixed_test.pdf"
    merged.save(str(mixed_path))
    merged.close()
    d1.close()
    d2.close()

    # Detect all pages
    needing = detect_pages_needing_ocr(mixed_path, min_chars=50)
    assert needing == {2}

    # Detect range page 1 only
    needing_p1 = detect_pages_needing_ocr(mixed_path, min_chars=50, page_range=(1, 1))
    assert needing_p1 == set()

    # Detect range page 2 only
    needing_p2 = detect_pages_needing_ocr(mixed_path, min_chars=50, page_range=(2, 2))
    assert needing_p2 == {2}


def test_detect_pages_missing_file():
    with pytest.raises(FileNotFoundError):
        detect_pages_needing_ocr(Path("/nonexistent/file.pdf"))


def test_ocr_config_min_chars(tmp_path: Path):
    config = OCRConfig(engine="tesseract", languages=("eng",), min_chars=40)
    assert config.min_chars == 40

    with pytest.raises(ConfigError, match="min_chars"):
        OCRConfig(engine="tesseract", languages=("eng",), min_chars=0)

    toml_file = tmp_path / "settings.toml"
    toml_file.write_text(
        '[ocr]\nengine = "tesseract"\nlanguages = ["eng"]\nmin_chars = 75\n',
        encoding="utf-8",
    )
    settings = load_settings(toml_file)
    assert settings.ocr.min_chars == 75
