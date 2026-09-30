import errno
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from tradutor_pdf.ui.main_window import ConversionDialog, ExportDialog


def test_export_dialog_formats(qtbot, tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Test", encoding="utf-8")

    dialog = ExportDialog(markdown_path=md_file, default_dir=tmp_path)
    qtbot.addWidget(dialog)

    # Defaults to PDF
    assert dialog.rb_pdf.isChecked()
    assert not dialog.rb_epub.isChecked()
    assert not dialog.rb_md.isChecked()

    # Switch to EPUB
    dialog.rb_epub.click()
    assert dialog.rb_epub.isChecked()

    # Switch to Markdown
    dialog.rb_md.click()
    assert dialog.rb_md.isChecked()


def test_export_dialog_cancel(qtbot, tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Test", encoding="utf-8")

    dialog = ExportDialog(markdown_path=md_file, default_dir=tmp_path)
    qtbot.addWidget(dialog)

    with qtbot.waitSignal(dialog.rejected, timeout=3000):
        dialog.btn_cancel.click()


def test_export_dialog_permission_error(qtbot, tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Test", encoding="utf-8")

    dialog = ExportDialog(markdown_path=md_file, default_dir=tmp_path)
    qtbot.addWidget(dialog)

    # Mock permission error on destination directory creation/check
    with (
        patch.object(
            Path,
            "mkdir",
            side_effect=PermissionError(errno.EACCES, "Permission denied"),
        ),
        patch.object(QMessageBox, "critical") as mock_crit,
    ):
        dialog.btn_export.click()
        assert mock_crit.called
        args = mock_crit.call_args[0]
        assert "Sem permissão na pasta de destino" in args[1]
        assert "permissão de escrita" in args[2].lower()


def test_export_dialog_conversion_failure(qtbot, tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Test", encoding="utf-8")

    dialog = ExportDialog(markdown_path=md_file, default_dir=tmp_path)
    qtbot.addWidget(dialog)

    with (
        patch(
            "tradutor_pdf.export.converter.DocumentConverter.convert",
            side_effect=RuntimeError("Typst compilation failed: disk full"),
        ),
        patch.object(QMessageBox, "critical") as mock_crit,
    ):
        dialog.btn_export.click()
        assert mock_crit.called
        args = mock_crit.call_args[0]
        assert "Disco cheio" in args[1]
        assert "libere espaço" in args[2].lower()


def test_conversion_dialog_missing_source(qtbot, tmp_path: Path):
    dialog = ConversionDialog(default_dir=tmp_path)
    qtbot.addWidget(dialog)

    with patch.object(QMessageBox, "warning") as mock_warn:
        dialog.btn_convert.click()
        assert mock_warn.called
        assert "Selecione o arquivo de origem" in mock_warn.call_args[0][2]


def test_conversion_dialog_nonexistent_source(qtbot, tmp_path: Path):
    dialog = ConversionDialog(default_dir=tmp_path)
    qtbot.addWidget(dialog)

    dialog.src_edit.setText(str(tmp_path / "nonexistent.pdf"))
    with patch.object(QMessageBox, "critical") as mock_crit:
        dialog.btn_convert.click()
        assert mock_crit.called
        assert "não encontrado" in mock_crit.call_args[0][2]


def test_conversion_dialog_success_md(qtbot, tmp_path: Path):
    src_file = tmp_path / "input.md"
    src_file.write_text("# Input", encoding="utf-8")

    dialog = ConversionDialog(default_dir=tmp_path)
    qtbot.addWidget(dialog)

    dialog.src_edit.setText(str(src_file))
    dialog.combo_format.setCurrentText("Markdown (.md)")

    out_folder = tmp_path / "converted_out"
    dialog.dest_edit.setText(str(out_folder))

    with qtbot.waitSignal(dialog.accepted, timeout=3000):
        dialog.btn_convert.click()

    assert (out_folder / "input.md").is_file()
