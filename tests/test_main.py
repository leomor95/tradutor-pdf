from pathlib import Path
from unittest.mock import MagicMock, patch

from tradutor_pdf import main, run_cli
from tradutor_pdf.pipeline import Block, BlockType, Extractor, Translator


class StubExtractor(Extractor):
    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
    ) -> list[Block]:
        return [
            Block(
                id="b1",
                type=BlockType.PARAGRAPH,
                content="Sample paragraph.",
                page=1,
            )
        ]


class StubTranslator(Translator):
    def translate(
        self,
        chunk,
        previous_context: str | None = None,
    ) -> str:
        res = "Parágrafo de exemplo."
        chunk.translated_text = res
        chunk.status = "translated"
        return res


def test_run_cli_success(tmp_path: Path):
    dummy_pdf = tmp_path / "sample.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4...")
    output_md = tmp_path / "custom_out.md"

    result = run_cli(
        pdf_path=dummy_pdf,
        output_path=output_md,
        extractor=StubExtractor(),
        translator=StubTranslator(),
    )

    assert result == output_md
    assert output_md.exists()
    content = output_md.read_text(encoding="utf-8")
    assert "Parágrafo de exemplo." in content


def test_main_cli_mode(tmp_path: Path):
    dummy_pdf = tmp_path / "sample.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4...")
    output_md = tmp_path / "out.md"

    with patch("tradutor_pdf.run_cli", return_value=output_md) as mock_run_cli:
        ret = main(["--cli", str(dummy_pdf), "-o", str(output_md)])
        assert ret == 0
        mock_run_cli.assert_called_once_with(
            dummy_pdf, output_path=output_md, on_conflict="ask"
        )


def test_main_cli_missing_file_returns_error(tmp_path: Path):
    missing_pdf = tmp_path / "does_not_exist.pdf"
    ret = main(["--cli", str(missing_pdf)])
    assert ret == 1


def test_main_gui_mode():
    with (
        patch("PySide6.QtWidgets.QApplication") as mock_app_cls,
        patch("tradutor_pdf.ui.main_window.MainWindow") as mock_window_cls,
    ):
        mock_app = MagicMock()
        mock_app.exec.return_value = 0
        mock_app_cls.return_value = mock_app

        mock_window = MagicMock()
        mock_window_cls.return_value = mock_window

        ret = main([])
        assert ret == 0
        mock_window.show.assert_called_once()
        mock_app.exec.assert_called_once()
