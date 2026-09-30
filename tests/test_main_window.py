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
    window = MainWindow(health_checker=lambda: (True, ""))
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


def test_main_window_cancel_and_resume(qtbot, tmp_path: Path):
    import time

    dummy_pdf = tmp_path / "long_doc.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4...")
    output_md = tmp_path / "long_doc.pt-BR.md"

    class SlowTranslator(Translator):
        def translate(self, chunk, previous_context=None):
            time.sleep(0.1)
            chunk.translated_text = f"PT: {chunk.original_text}"
            chunk.status = "translated"
            return chunk.translated_text

    class MultiBlockExtractor(Extractor):
        def extract(self, source_path, pages=None):
            return [
                Block(id=f"b{i}", type=BlockType.PARAGRAPH, content=f"P {i}", page=i)
                for i in range(1, 10)
            ]

    def make_worker(path: Path) -> TranslationWorker:
        return TranslationWorker(
            source_path=path,
            output_path=output_md,
            extractor=MultiBlockExtractor(),
            translator=SlowTranslator(),
        )

    window = MainWindow(worker_factory=make_worker, auto_prompt_export=False)
    qtbot.addWidget(window)
    window.show()

    window.start_translation(dummy_pdf)
    assert not window.btn_cancel.isHidden()
    assert window.btn_resume.isHidden()

    # Cancel while in progress
    window.cancel_translation()
    qtbot.waitUntil(lambda: not window.btn_resume.isHidden(), timeout=5000)

    assert window.btn_cancel.isHidden()
    assert not window.btn_resume.isHidden()
    assert "cancelada" in window.status_label.text().lower()
    assert window.drop_area.isEnabled()

    # Resume
    window.resume_translation()
    assert not window.btn_cancel.isHidden()
    assert window.btn_resume.isHidden()

    qtbot.waitUntil(
        lambda: window.btn_cancel.isHidden() and window.progress_bar.value() == 100,
        timeout=10000,
    )
    assert window.btn_cancel.isHidden()
    assert window.btn_resume.isHidden()
    if window.current_worker:
        window.current_worker.wait(5000)


def test_main_window_health_check_ollama_down(qtbot):
    msg = "O serviço de tradução local (Ollama) não está em execução. Execute `./scripts/run.sh` no terminal para iniciar o serviço."
    window = MainWindow(health_checker=lambda: (False, msg))
    qtbot.addWidget(window)
    window.show()

    assert not window.drop_area.isEnabled()
    assert not window.banner_frame.isHidden()
    assert "não está em execução" in window.status_label.text()
    assert "`./scripts/run.sh`" in window.banner_label.text()


def test_main_window_health_check_model_missing(qtbot):
    msg = "O modelo 'qwen2.5:7b' não está instalado no Ollama local. Execute `./scripts/setup.sh` no terminal para baixar o modelo configurado."
    window = MainWindow(health_checker=lambda: (False, msg))
    qtbot.addWidget(window)
    window.show()

    assert not window.drop_area.isEnabled()
    assert not window.banner_frame.isHidden()
    assert "não está instalado" in window.status_label.text()
    assert "`./scripts/setup.sh`" in window.banner_label.text()


def test_main_window_health_check_retry(qtbot):
    state = {"healthy": False}

    def checker():
        if state["healthy"]:
            return True, ""
        return False, "Erro temporário"

    window = MainWindow(health_checker=checker)
    qtbot.addWidget(window)
    window.show()

    assert not window.drop_area.isEnabled()
    assert not window.banner_frame.isHidden()

    # Make healthy and click retry
    state["healthy"] = True
    window.btn_retry_health.click()

    assert window.drop_area.isEnabled()
    assert window.banner_frame.isHidden()
    assert "Pronto para traduzir" in window.status_label.text()


def test_check_service_health_function(monkeypatch):
    from tradutor_pdf.translation.ollama_client import check_service_health

    # 1. Connection error
    def mock_list_models_conn_err(self):
        from tradutor_pdf.translation.ollama_client import OllamaConnectionError

        raise OllamaConnectionError("Connection refused")

    monkeypatch.setattr(
        "tradutor_pdf.translation.ollama_client.OllamaClient.list_models",
        mock_list_models_conn_err,
    )
    ok, err = check_service_health()
    assert not ok
    assert "não está em execução" in err
    assert "scripts/run.sh" in err

    # 2. Model missing
    def mock_list_models_ok(self):
        return ["llama3:latest", "mistral:7b"]

    monkeypatch.setattr(
        "tradutor_pdf.translation.ollama_client.OllamaClient.list_models",
        mock_list_models_ok,
    )
    ok, err = check_service_health(model="qwen2.5:7b-instruct-q4_K_M")
    assert not ok
    assert "não está instalado" in err
    assert "scripts/setup.sh" in err

    # 3. Model present
    def mock_list_models_has_model(self):
        return ["qwen2.5:7b-instruct-q4_K_M", "other:latest"]

    monkeypatch.setattr(
        "tradutor_pdf.translation.ollama_client.OllamaClient.list_models",
        mock_list_models_has_model,
    )
    ok, err = check_service_health(model="qwen2.5:7b-instruct-q4_K_M")
    assert ok
    assert err == ""


def test_export_dialog_destination_persistence(qtbot, tmp_path: Path):
    from tradutor_pdf.config import get_last_destination, save_last_destination
    from tradutor_pdf.ui.main_window import ExportDialog

    state_file = tmp_path / "config" / "state.json"
    saved_folder = tmp_path / "previously_saved"
    saved_folder.mkdir(parents=True)
    save_last_destination(saved_folder, state_path=state_file)

    md_file = tmp_path / "test.md"
    md_file.write_text("# Test content", encoding="utf-8")

    dialog = ExportDialog(markdown_path=md_file, state_path=state_file)
    qtbot.addWidget(dialog)

    # Check that it pre-filled with the remembered folder
    assert dialog.dest_edit.text() == str(saved_folder.resolve())

    # Export to a new folder
    new_dest = tmp_path / "new_destination"
    dialog.dest_edit.setText(str(new_dest))
    dialog.rb_md.setChecked(True)

    with qtbot.waitSignal(dialog.accepted, timeout=3000):
        dialog.btn_export.click()

    assert get_last_destination(state_path=state_file) == new_dest.resolve()


def test_conversion_dialog_destination_persistence(qtbot, tmp_path: Path):
    from tradutor_pdf.config import get_last_destination, save_last_destination
    from tradutor_pdf.ui.main_window import ConversionDialog

    state_file = tmp_path / "config" / "state.json"
    first_folder = tmp_path / "folder_alpha"
    first_folder.mkdir(parents=True)
    save_last_destination(first_folder, state_path=state_file)

    src_file = tmp_path / "sample.md"
    src_file.write_text("# Sample", encoding="utf-8")

    dialog = ConversionDialog(state_path=state_file)
    qtbot.addWidget(dialog)

    # Initial dir should be folder_alpha
    assert dialog.dest_edit.text() == str(first_folder.resolve())

    # Set source and new destination
    folder_beta = tmp_path / "folder_beta"
    dialog.src_edit.setText(str(src_file))
    dialog.dest_edit.setText(str(folder_beta))
    dialog.combo_format.setCurrentText("Markdown (.md)")

    with qtbot.waitSignal(dialog.accepted, timeout=3000):
        dialog.btn_convert.click()

    assert get_last_destination(state_path=state_file) == folder_beta.resolve()
