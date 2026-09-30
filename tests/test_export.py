from pathlib import Path

import pytest

from tradutor_pdf.export.markdown import MarkdownExporter
from tradutor_pdf.pipeline import Exporter


def test_markdown_exporter_protocol():
    exporter = MarkdownExporter()
    assert isinstance(exporter, Exporter)


def test_markdown_exporter_copies_file_and_assets(tmp_path: Path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    assets_dir = source_dir / "assets"
    assets_dir.mkdir()

    md_file = source_dir / "doc.pt-BR.md"
    md_file.write_text("# Teste\n![img](assets/img.png)", encoding="utf-8")

    img_file = assets_dir / "img.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    dest_dir = tmp_path / "out"
    exporter = MarkdownExporter()
    exported_path = exporter.export(
        md_file, output_format="md", destination_dir=dest_dir
    )

    assert exported_path == dest_dir / "doc.pt-BR.md"
    assert exported_path.is_file()
    assert exported_path.read_text(encoding="utf-8") == md_file.read_text(
        encoding="utf-8"
    )

    copied_asset = dest_dir / "assets" / "img.png"
    assert copied_asset.is_file()
    assert copied_asset.read_bytes() == b"\x89PNG\r\n\x1a\nfakeimage"


def test_markdown_exporter_custom_target_file(tmp_path: Path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    md_file = source_dir / "doc.md"
    md_file.write_text("# Teste", encoding="utf-8")

    target_file = tmp_path / "custom" / "my_document.md"
    exporter = MarkdownExporter()
    exported_path = exporter.export(md_file, destination_dir=target_file)

    assert exported_path == target_file
    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == "# Teste"


def test_markdown_exporter_missing_file_raises(tmp_path: Path):
    exporter = MarkdownExporter()
    with pytest.raises(FileNotFoundError):
        exporter.export(tmp_path / "nonexistent.md", destination_dir=tmp_path / "out")
