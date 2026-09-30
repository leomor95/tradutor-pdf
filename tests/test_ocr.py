import time
from pathlib import Path

import pytest

from tradutor_pdf import run_cli
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.pipeline import BlockType, Chunk, Translator


def test_mixed_pdf_selective_ocr(tmp_path: Path):
    fixture_mixed = Path("tests/fixtures/mixed.pdf")
    assert fixture_mixed.is_file()

    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(do_ocr="auto", assets_dir=assets_dir)
    blocks = extractor.extract(fixture_mixed)

    assert len(blocks) >= 4

    p1_blocks = [b for b in blocks if b.page == 1]
    p2_blocks = [b for b in blocks if b.page == 2]
    p3_blocks = [b for b in blocks if b.page == 3]
    p4_blocks = [b for b in blocks if b.page == 4]

    # Pages 1 & 3: digital text -> ocr=False
    assert len(p1_blocks) >= 1
    assert any("Page 1: Digital Overview" in b.content for b in p1_blocks)
    assert all(b.metadata.get("ocr") is False for b in p1_blocks)

    assert len(p3_blocks) >= 1
    assert any("Page 3: Visual Topology" in b.content for b in p3_blocks)
    assert all(b.metadata.get("ocr") is False for b in p3_blocks)
    # Check image on page 3 was extracted
    image_blocks = [b for b in p3_blocks if b.type == BlockType.IMAGE]
    assert len(image_blocks) >= 1

    # Pages 2 & 4: scanned images -> ocr=True
    assert len(p2_blocks) >= 1
    assert any("Storage Architecture" in b.content for b in p2_blocks)
    assert all(b.metadata.get("ocr") is True for b in p2_blocks)

    assert len(p4_blocks) >= 1
    assert any("Performance Monitoring" in b.content for b in p4_blocks)
    assert all(b.metadata.get("ocr") is True for b in p4_blocks)


@pytest.mark.slow
def test_scanned_pdf_ocr_performance_and_accuracy(tmp_path: Path):
    fixture_scanned = Path("tests/fixtures/scanned.pdf")
    assert fixture_scanned.is_file()

    assets_dir = tmp_path / "assets"
    extractor = DoclingExtractor(do_ocr="auto", assets_dir=assets_dir)

    t0 = time.time()
    blocks = extractor.extract(fixture_scanned)
    elapsed = time.time() - t0

    total_pages = 10
    avg_per_page = elapsed / total_pages

    # RNF10: OCR com média <= 5 s por página
    assert avg_per_page <= 5.0, (
        f"OCR average time per page ({avg_per_page:.2f}s) exceeded 5.0s limit"
    )

    # All blocks on scanned document must have ocr=True
    assert len(blocks) >= 20
    assert all(b.metadata.get("ocr") is True for b in blocks)

    # Verify chapters 1 through 10 are extracted
    for ch in range(1, 11):
        assert any(f"Chapter {ch}:" in b.content for b in blocks), (
            f"Missing Chapter {ch} in OCR blocks"
        )

    # Verify running headers and footers were removed
    block_contents = [b.content for b in blocks]
    assert "Distributed Systems Architecture" not in block_contents
    for p in range(1, 11):
        assert f"Page {p}" not in block_contents
        assert str(p) not in [b.content.strip() for b in blocks]


@pytest.mark.slow
def test_scanned_pdf_full_translation_ca02(tmp_path: Path):
    fixture_scanned = Path("tests/fixtures/scanned.pdf")
    assert fixture_scanned.is_file()

    output_path = tmp_path / "scanned.pt-BR.md"

    class SimpleFakeTranslator(Translator):
        def translate(
            self,
            chunk: Chunk,
            previous_context: tuple[str, str] | None = None,
        ) -> str:
            # Deterministic translation
            translated = (
                chunk.original_text.replace("Chapter", "Capítulo")
                .replace(
                    "Cloud and Distributed Architectures",
                    "Arquiteturas em Nuvem e Distribuídas",
                )
                .replace(
                    "Scalability and High Availability",
                    "Escalabilidade e Alta Disponibilidade",
                )
            )
            chunk.translated_text = translated
            chunk.status = "translated"
            return translated

    final_path = run_cli(
        pdf_path=fixture_scanned,
        output_path=output_path,
        translator=SimpleFakeTranslator(),
    )

    assert final_path.is_file()
    md_content = final_path.read_text(encoding="utf-8")

    # CA02: Um PDF escaneado de 10 páginas gera um MD legível e traduzido
    assert "# Capítulo 1:" in md_content or "Capítulo 1:" in md_content
    assert "Arquiteturas em Nuvem e Distribuídas" in md_content
    assert "# Capítulo 2:" in md_content or "Capítulo 2:" in md_content
    assert "Capítulo 10:" in md_content

    # Running headers and footers should not be present in final MD
    assert "Distributed Systems Architecture" not in md_content
