import re
from pathlib import Path

from PIL import Image

from tradutor_pdf import run_cli
from tradutor_pdf.assembly.markdown import MarkdownAssembler
from tradutor_pdf.extraction.docling_extractor import DoclingExtractor
from tradutor_pdf.segmentation.semantic import SemanticSegmenter
from tradutor_pdf.translation.translator import OllamaTranslator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_mock_translator(fake_llm):
    """Creates a mock translator that simulates Portuguese translation while preserving Markdown."""

    def mock_handler(prompt: str) -> str:
        prefix = "Translate the following text to pt-BR:\n\n"
        idx = prompt.find(prefix)
        text = prompt[idx + len(prefix) :] if idx != -1 else prompt

        lines = []
        for line in text.splitlines():
            # Keep markdown headers intact with Portuguese suffix
            if line.startswith("#"):
                hashes, rest = line.split(" ", 1)
                lines.append(f"{hashes} {rest} (Traduzido)")
            elif line.startswith("- "):
                lines.append(f"- {line[2:]} (item traduzido)")
            elif re.match(r"^\d+\.\s+", line):
                num, rest = line.split(". ", 1)
                lines.append(f"{num}. {rest} (passo traduzido)")
            elif line.strip():
                lines.append(f"{line} (traduzido)")
            else:
                lines.append(line)
        return "\n".join(lines)

    fake_llm.custom_handler = mock_handler
    return OllamaTranslator(client=fake_llm)


def test_structure_headings_and_lists(fake_llm, tmp_path: Path):
    fixture_pdf = FIXTURES_DIR / "headings_lists.pdf"
    assert fixture_pdf.is_file()

    out_file = tmp_path / "headings_lists.pt-BR.md"
    translator = _make_mock_translator(fake_llm)

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=out_file,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == out_file
    content = out_file.read_text(encoding="utf-8")

    # Verify heading levels
    h1_matches = re.findall(r"^#\s+(.+)$", content, re.MULTILINE)
    h2_matches = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    h3_matches = re.findall(r"^###\s+(.+)$", content, re.MULTILINE)

    assert len(h1_matches) >= 1
    assert "Main Document Title" in h1_matches[0]

    assert len(h2_matches) >= 2
    assert any("Section One" in h for h in h2_matches)
    assert any("Section Two" in h for h in h2_matches)

    assert len(h3_matches) >= 1
    assert any("Subsection" in h for h in h3_matches)

    # Verify lists
    list_items = re.findall(r"^(?:-|\*|\d+\.)\s+(.+)$", content, re.MULTILINE)
    assert len(list_items) >= 5


def test_structure_tables_and_images(fake_llm, tmp_path: Path):
    fixture_pdf = FIXTURES_DIR / "tables_images.pdf"
    assert fixture_pdf.is_file()

    out_file = tmp_path / "tables_images.pt-BR.md"
    translator = _make_mock_translator(fake_llm)

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=out_file,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == out_file
    content = out_file.read_text(encoding="utf-8")

    # Verify table structure (Markdown table columns and cells)
    assert "| Component" in content or "|Component" in content
    assert "| Default Value" in content or "|Default Value" in content
    assert "| Description" in content or "|Description" in content
    assert "Connection Pool" in content
    assert "Write Buffer" in content
    assert "Heartbeat Interval" in content
    assert "Compaction Threads" in content

    # Verify image reference in Markdown
    img_matches = re.findall(r"!\[(.*?)\]\((.*?)\)", content)
    assert len(img_matches) >= 1
    alt_text, rel_img_path = img_matches[0]
    assert "Cluster replication" in alt_text or "image" in alt_text.lower()
    assert rel_img_path.startswith("assets/")

    # Verify image asset file on disk (CA03, CA07)
    img_disk_path = out_file.parent / rel_img_path
    assert img_disk_path.is_file()
    assert img_disk_path.stat().st_size > 0
    # Ensure it's a valid readable image
    with Image.open(img_disk_path) as im:
        assert im.size[0] > 0 and im.size[1] > 0


def test_structure_code_blocks(fake_llm, tmp_path: Path):
    fixture_pdf = FIXTURES_DIR / "code_blocks.pdf"
    assert fixture_pdf.is_file()

    out_file = tmp_path / "code_blocks.pt-BR.md"
    translator = _make_mock_translator(fake_llm)

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=out_file,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == out_file
    content = out_file.read_text(encoding="utf-8")

    # Verify code blocks were preserved in markdown without translation
    assert "def process_batch" in content
    assert "max_retries" in content
    assert "export WORKER_ENV=production" in content

    # Verify inline code and paths were preserved
    assert "/etc/tradutor/settings.toml" in content
    assert "initialize_cluster()" in content
    assert "https://github.com/example/repo" in content
    assert "/var/log/service.log" in content


def test_structure_footnotes(fake_llm, tmp_path: Path):
    fixture_pdf = FIXTURES_DIR / "footnotes.pdf"
    assert fixture_pdf.is_file()

    out_file = tmp_path / "footnotes.pt-BR.md"
    translator = _make_mock_translator(fake_llm)

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=out_file,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == out_file
    content = out_file.read_text(encoding="utf-8")

    # Verify headings and footnote citations
    assert "Consensus Protocols" in content
    assert "Practical Implementations" in content
    assert "Lamport" in content
    assert "Ongaro" in content


def test_structure_two_columns_reading_order(fake_llm, tmp_path: Path):
    fixture_pdf = FIXTURES_DIR / "two_columns.pdf"
    assert fixture_pdf.is_file()

    out_file = tmp_path / "two_columns.pt-BR.md"
    translator = _make_mock_translator(fake_llm)

    result_path = run_cli(
        pdf_path=fixture_pdf,
        output_path=out_file,
        extractor=DoclingExtractor(do_ocr=False),
        segmenter=SemanticSegmenter(),
        translator=translator,
        assembler=MarkdownAssembler(),
    )

    assert result_path == out_file
    content = out_file.read_text(encoding="utf-8")

    # Check reading order: Left column content comes BEFORE right column content
    pos_left_title = content.find("Left Column Architecture")
    pos_left_section = content.find("Primary Replication Path")
    pos_right_title = content.find("Right Column Failover")
    pos_right_section = content.find("Recovery and Compaction")

    assert pos_left_title != -1, "Left Column Architecture missing"
    assert pos_left_section != -1, "Primary Replication Path missing"
    assert pos_right_title != -1, "Right Column Failover missing"
    assert pos_right_section != -1, "Recovery and Compaction missing"

    assert pos_left_title < pos_left_section < pos_right_title < pos_right_section, (
        f"Incorrect reading order across two columns:\n"
        f"Left Title: {pos_left_title}, Left Sec: {pos_left_section}, "
        f"Right Title: {pos_right_title}, Right Sec: {pos_right_section}"
    )
