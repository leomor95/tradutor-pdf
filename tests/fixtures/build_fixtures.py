from pathlib import Path

import typst

FIXTURES_DIR = Path(__file__).resolve().parent
SOURCES_DIR = FIXTURES_DIR / "sources"

FIXTURE_NAMES = [
    "headings_lists",
    "tables_images",
    "code_blocks",
    "footnotes",
    "two_columns",
]


def build_all_fixtures() -> None:
    print(f"Building fixtures from {SOURCES_DIR}...")
    for name in FIXTURE_NAMES:
        typ_file = SOURCES_DIR / f"{name}.typ"
        pdf_file = FIXTURES_DIR / f"{name}.pdf"
        if not typ_file.is_file():
            raise FileNotFoundError(f"Missing typst source: {typ_file}")

        print(f"Compiling {typ_file.name} -> {pdf_file.name}...")
        pdf_bytes = typst.compile(typ_file)
        pdf_file.write_bytes(pdf_bytes)
        print(f"  Generated {pdf_file.name} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    build_all_fixtures()
