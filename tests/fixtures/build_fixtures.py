import io
from pathlib import Path

import pypdfium2 as pdfium
import typst
from PIL import Image

FIXTURES_DIR = Path(__file__).resolve().parent
SOURCES_DIR = FIXTURES_DIR / "sources"

FIXTURE_NAMES = [
    "headings_lists",
    "tables_images",
    "code_blocks",
    "footnotes",
    "two_columns",
    "technical_en",
]


def build_standard_fixtures() -> None:
    print(f"Building standard fixtures from {SOURCES_DIR}...")
    for name in FIXTURE_NAMES:
        typ_file = SOURCES_DIR / f"{name}.typ"
        pdf_file = FIXTURES_DIR / f"{name}.pdf"
        if not typ_file.is_file():
            raise FileNotFoundError(f"Missing typst source: {typ_file}")

        print(f"Compiling {typ_file.name} -> {pdf_file.name}...")
        pdf_bytes = typst.compile(typ_file, root=SOURCES_DIR)
        pdf_file.write_bytes(pdf_bytes)
        print(f"  Generated {pdf_file.name} ({len(pdf_bytes)} bytes)")


def build_scanned_fixture() -> None:
    typ_file = SOURCES_DIR / "scanned.typ"
    pdf_file = FIXTURES_DIR / "scanned.pdf"
    print(f"Compiling {typ_file.name} -> {pdf_file.name} (10 rasterized pages)...")
    pdf_bytes = typst.compile(typ_file, root=SOURCES_DIR)
    doc = pdfium.PdfDocument(pdf_bytes)
    total_pages = len(doc)
    assert total_pages == 10, f"Expected 10 pages in scanned.typ, got {total_pages}"

    images: list[Image.Image] = []
    for i in range(total_pages):
        page = doc.get_page(i)
        img = page.render(scale=2.0).to_pil().convert("RGB")
        images.append(img)
        page.close()
    doc.close()

    images[0].save(
        pdf_file,
        format="PDF",
        save_all=True,
        append_images=images[1:],
    )
    for img in images:
        img.close()
    print(f"  Generated {pdf_file.name} ({pdf_file.stat().st_size} bytes)")


def build_mixed_fixture() -> None:
    typ_file = SOURCES_DIR / "mixed.typ"
    pdf_file = FIXTURES_DIR / "mixed.pdf"
    print(f"Compiling {typ_file.name} -> {pdf_file.name} (mixed digital/scanned)...")
    pdf_bytes = typst.compile(typ_file, root=SOURCES_DIR)
    doc = pdfium.PdfDocument(pdf_bytes)
    assert len(doc) == 4, f"Expected 4 pages in mixed.typ, got {len(doc)}"

    final_doc = pdfium.PdfDocument.new()
    for i in range(4):
        if i in (1, 3):  # rasterized scanned pages
            page = doc.get_page(i)
            img = page.render(scale=2.0).to_pil().convert("RGB")
            page.close()
            buf = io.BytesIO()
            img.save(buf, format="PDF")
            img.close()
            scan_doc = pdfium.PdfDocument(buf.getvalue())
            final_doc.import_pages(scan_doc)
            scan_doc.close()
        else:  # digital pages with selectable text and images
            temp_doc = pdfium.PdfDocument(pdf_bytes)
            final_doc.import_pages(temp_doc, [i])
            temp_doc.close()

    doc.close()
    final_doc.save(str(pdf_file))
    final_doc.close()
    print(f"  Generated {pdf_file.name} ({pdf_file.stat().st_size} bytes)")


def build_book_100p_fixture() -> None:
    pdf_file = FIXTURES_DIR / "book_100p.pdf"
    if not pdf_file.is_file():
        from scripts.gen_big_pdf import generate_synthetic_pdf

        print(f"Generating {pdf_file.name} (100 pages)...")
        generate_synthetic_pdf(pdf_file, total_pages=100)


def build_all_fixtures() -> None:
    build_standard_fixtures()
    build_scanned_fixture()
    build_mixed_fixture()
    build_book_100p_fixture()


if __name__ == "__main__":
    build_all_fixtures()
