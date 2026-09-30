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


def test_epub_exporter_protocol():
    from tradutor_pdf.export.epub import EpubExporter

    exporter = EpubExporter()
    assert isinstance(exporter, Exporter)


def test_epub_exporter_extract_title():
    from tradutor_pdf.export.epub import extract_title_from_markdown

    assert (
        extract_title_from_markdown("# Título Principal\nConteúdo")
        == "Título Principal"
    )
    assert (
        extract_title_from_markdown("---\ntitle: Frontmatter Title\n---\n# Ignored")
        == "Frontmatter Title"
    )
    assert (
        extract_title_from_markdown("Apenas texto sem título", default="Padrão")
        == "Padrão"
    )


def test_epub_exporter_generates_valid_epub(tmp_path: Path):
    import base64

    from tradutor_pdf.export.epub import EpubExporter, validate_epub

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assets_dir = src_dir / "assets"
    assets_dir.mkdir()

    # Create dummy 1x1 png image
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (assets_dir / "sample.png").write_bytes(png_bytes)

    md_content = """# Arquitetura de Software

Um guia introdutório sobre microsserviços e sistemas distribuídos.

## Componentes

Os componentes principais do sistema incluem:

- Serviço de autenticação
- Processamento de mensagens
- Banco de dados replicado

![Diagrama](assets/sample.png)

### Tabela de Métricas

| Métrica | Valor |
|---|---|
| Latência | 12ms |
| Taxa | 99.9% |
"""
    md_file = src_dir / "software_arch.pt-BR.md"
    md_file.write_text(md_content, encoding="utf-8")

    out_dir = tmp_path / "out"
    exporter = EpubExporter(lang="pt-BR")
    out_file = exporter.export(md_file, destination_dir=out_dir)

    assert out_file == out_dir / "software_arch.pt-BR.epub"
    assert out_file.is_file()
    assert out_file.stat().st_size > 0

    # Validate with epubcheck
    is_valid, report = validate_epub(out_file)
    assert is_valid, f"EPUB validation failed: {report}"


def test_pdf_exporter_protocol():
    from tradutor_pdf.export.pdf import PdfExporter

    exporter = PdfExporter()
    assert isinstance(exporter, Exporter)


def test_pdf_exporter_generates_pdf(tmp_path: Path):
    import base64

    from tradutor_pdf.export.pdf import PdfExporter

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assets_dir = src_dir / "assets"
    assets_dir.mkdir()

    # Create dummy 1x1 png image
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    (assets_dir / "chart.png").write_bytes(png_bytes)

    md_content = """# Relatório Técnico

Documento demonstrativo de exportação PDF via Typst.

## Trecho de Código

```python
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
```

## Tabela de Dados

| Chave | Valor | Observação |
|---|---|---|
| Timeout | 30s | Conexão externa |
| Retries | 3 | Tentativas máximas |

## Ilustração

![Gráfico de Desempenho](assets/chart.png)
"""
    md_file = src_dir / "relatorio.pt-BR.md"
    md_file.write_text(md_content, encoding="utf-8")

    out_dir = tmp_path / "out"
    exporter = PdfExporter()
    out_pdf = exporter.export(md_file, destination_dir=out_dir)

    assert out_pdf == out_dir / "relatorio.pt-BR.pdf"
    assert out_pdf.is_file()
    assert out_pdf.stat().st_size > 0

    # Verify PDF magic header
    pdf_bytes = out_pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-")


def test_pdf_exporter_custom_output_filename(tmp_path: Path):
    from tradutor_pdf.export.pdf import PdfExporter

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    md_file = src_dir / "doc.md"
    md_file.write_text("# Título\n\nTexto simples.", encoding="utf-8")

    target_pdf = tmp_path / "custom_folder" / "custom_name.pdf"
    exporter = PdfExporter()
    res_path = exporter.export(md_file, destination_dir=target_pdf)

    assert res_path == target_pdf
    assert target_pdf.is_file()
    assert target_pdf.read_bytes().startswith(b"%PDF-")


def test_pdf_exporter_missing_file_raises(tmp_path: Path):
    from tradutor_pdf.export.pdf import PdfExporter

    exporter = PdfExporter()
    with pytest.raises(FileNotFoundError):
        exporter.export(tmp_path / "missing.md", destination_dir=tmp_path / "out")


def test_conversion_pdf_to_md_with_s2_fixtures(tmp_path: Path):
    from tradutor_pdf.export.converter import DocumentConverter

    fixtures_dir = Path(__file__).parent / "fixtures"
    fixture_pdf = fixtures_dir / "headings_lists.pdf"
    assert fixture_pdf.is_file(), "headings_lists.pdf fixture missing"

    converter = DocumentConverter()
    out_md = converter.convert(
        fixture_pdf, target_format="md", destination=tmp_path / "headings_lists.md"
    )

    assert out_md.is_file()
    content = out_md.read_text(encoding="utf-8")
    assert "#" in content
    assert len(content) > 100


def test_conversion_tables_images_pdf_to_md_and_epub(tmp_path: Path):
    from tradutor_pdf.export.converter import DocumentConverter
    from tradutor_pdf.export.epub import validate_epub

    fixtures_dir = Path(__file__).parent / "fixtures"
    fixture_pdf = fixtures_dir / "tables_images.pdf"
    assert fixture_pdf.is_file(), "tables_images.pdf fixture missing"

    converter = DocumentConverter()
    # 1. PDF -> MD
    out_md = converter.convert(
        fixture_pdf, target_format="md", destination=tmp_path / "tables_images.md"
    )
    assert out_md.is_file()
    md_content = out_md.read_text(encoding="utf-8")
    assert "|" in md_content or "<table" in md_content

    # Check that assets were extracted
    assets_dir = out_md.parent / "assets"
    assert assets_dir.is_dir()
    image_files = list(assets_dir.glob("*.png"))
    assert len(image_files) > 0

    # 2. MD -> EPUB
    out_epub = converter.convert(
        out_md, target_format="epub", destination=tmp_path / "tables_images.epub"
    )
    assert out_epub.is_file()
    assert out_epub.stat().st_size > 0

    # Validate EPUB with epubcheck
    is_valid, report = validate_epub(out_epub)
    assert is_valid, f"Generated EPUB invalid: {report}"

    # 3. EPUB -> MD
    out_md_from_epub = converter.convert(
        out_epub, target_format="md", destination=tmp_path / "from_epub.md"
    )
    assert out_md_from_epub.is_file()
    assert len(out_md_from_epub.read_text(encoding="utf-8")) > 50

    # 4. MD -> PDF
    out_pdf = converter.convert(
        out_md, target_format="pdf", destination=tmp_path / "tables_images.pdf"
    )
    assert out_pdf.is_file()
    assert out_pdf.read_bytes().startswith(b"%PDF-")


def test_conversion_unsupported_format_raises(tmp_path: Path):
    from tradutor_pdf.export.converter import DocumentConverter

    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("Hello", encoding="utf-8")

    converter = DocumentConverter()
    with pytest.raises(ValueError):
        converter.convert(dummy_file, target_format="md")

    md_file = tmp_path / "test.md"
    md_file.write_text("# Hello", encoding="utf-8")
    with pytest.raises(ValueError):
        converter.convert(md_file, target_format="docx")
