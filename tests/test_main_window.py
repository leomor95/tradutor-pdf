from pathlib import Path

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from tradutor_pdf.pipeline import Block, BlockType, Extractor, Translator
from tradutor_pdf.ui.main_window import DropArea, MainWindow
from tradutor_pdf.ui.worker import TranslationWorker


class StubExtractor(Extractor):
    def extract(
        self,
        source_path: Path,
        pages: tuple[int, int] | None = None,
    ) -> list[Block]:
        return [
            Block(
                id="b1",
                type=BlockType.HEADING,
                content="Title",
                page=1,
                metadata={"heading_level": 1},
            ),
            Block(
                id="b2",
                type=BlockType.PARAGRAPH,
                content="Paragraph",
                page=1,
            ),
        ]


class StubTranslator(Translator):
    def translate(
        self,
        chunk,
        previous_context: str | None = None,
    ) -> str:
        return f"PT: {chunk.original_text}"


def test_main_window_initial_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert "Tradutor de PDF" in window.windowTitle()
    assert window.drop_area.isEnabled()
    assert window.progress_bar.value() == 0
    assert "Pronto para traduzir" in window.status_label.text()


def test_drop_area_drag_filtering(qtbot, tmp_path: Path):
    drop_area = DropArea()
    qtbot.addWidget(drop_area)

    # 1. Non-pdf file
    mime_txt = QMimeData()
    mime_txt.setUrls([QUrl.fromLocalFile(str(tmp_path / "doc.txt"))])
    event_txt = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime_txt,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    drop_area.dragEnterEvent(event_txt)
    assert not event_txt.isAccepted()

    # 2. Valid PDF file
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4...")
    mime_pdf = QMimeData()
    mime_pdf.setUrls([QUrl.fromLocalFile(str(pdf_file))])
    event_pdf = QDragEnterEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime_pdf,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    drop_area.dragEnterEvent(event_pdf)
    assert event_pdf.isAccepted()


def test_drop_area_drop_event(qtbot, tmp_path: Path):
    drop_area = DropArea()
    qtbot.addWidget(drop_area)

    pdf_file = tmp_path / "valid.pdf"
    pdf_file.write_bytes(b"%PDF-1.4...")

    dropped_paths = []
    drop_area.file_dropped.connect(dropped_paths.append)

    mime_pdf = QMimeData()
    mime_pdf.setUrls([QUrl.fromLocalFile(str(pdf_file))])
    drop_event = QDropEvent(
        QPoint(10, 10),
        Qt.DropAction.CopyAction,
        mime_pdf,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    drop_area.dropEvent(drop_event)

    assert drop_event.isAccepted()
    assert len(dropped_paths) == 1
    assert dropped_paths[0] == pdf_file


def test_main_window_successful_flow(qtbot, tmp_path: Path):
    dummy_pdf = tmp_path / "test.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4...")
    output_md = tmp_path / "test.pt-BR.md"

    def make_worker(path: Path) -> TranslationWorker:
        return TranslationWorker(
            source_path=path,
            output_path=output_md,
            extractor=StubExtractor(),
            translator=StubTranslator(),
        )

    window = MainWindow(worker_factory=make_worker, auto_prompt_export=False)
    qtbot.addWidget(window)

    window.start_translation(dummy_pdf)
    assert not window.drop_area.isEnabled()

    qtbot.waitUntil(lambda: window.drop_area.isEnabled(), timeout=5000)

    assert window.progress_bar.value() == 100
    assert "salva com sucesso" in window.status_label.text()
    assert output_md.exists()


def test_main_window_error_flow(qtbot, tmp_path: Path):
    def make_failing_worker(path: Path) -> TranslationWorker:
        return TranslationWorker(
            source_path=tmp_path / "non_existent.pdf",
        )

    window = MainWindow(worker_factory=make_failing_worker, auto_prompt_export=False)
    qtbot.addWidget(window)

    window.start_translation(tmp_path / "non_existent.pdf")
    qtbot.waitUntil(lambda: window.drop_area.isEnabled(), timeout=5000)

    assert "Erro na tradução" in window.status_label.text()


def test_main_window_menu_and_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    menu_bar = window.menuBar()
    actions = menu_bar.actions()
    assert len(actions) > 0
    file_menu = actions[0].menu()
    assert file_menu is not None
    file_actions = [a.text() for a in file_menu.actions()]
    assert any("Converter" in t for t in file_actions)
    assert any("Sair" in t for t in file_actions)


def test_export_dialog_flow(qtbot, tmp_path: Path):
    from tradutor_pdf.ui.main_window import ExportDialog

    md_file = tmp_path / "doc.pt-BR.md"
    md_file.write_text("# Teste de Exportação\n\nConteúdo.", encoding="utf-8")

    out_folder = tmp_path / "export_dest"
    dialog = ExportDialog(markdown_path=md_file, default_dir=out_folder)
    qtbot.addWidget(dialog)

    # Select EPUB
    dialog.rb_epub.setChecked(True)
    dialog.dest_edit.setText(str(out_folder))

    dialog._do_export()

    assert dialog.exported_path is not None
    assert dialog.exported_path.is_file()
    assert dialog.exported_path.suffix == ".epub"


def test_conversion_dialog_flow(qtbot, tmp_path: Path):
    from tradutor_pdf.ui.main_window import ConversionDialog

    md_file = tmp_path / "doc.md"
    md_file.write_text("# Teste de Conversão\n\nTexto.", encoding="utf-8")

    out_folder = tmp_path / "convert_dest"
    dialog = ConversionDialog(default_dir=out_folder)
    qtbot.addWidget(dialog)

    dialog.src_edit.setText(str(md_file))
    dialog.combo_format.setCurrentText("PDF (.pdf)")
    dialog.dest_edit.setText(str(out_folder))

    dialog._do_convert()

    assert dialog.converted_path is not None
    assert dialog.converted_path.is_file()
    assert dialog.converted_path.suffix == ".pdf"
