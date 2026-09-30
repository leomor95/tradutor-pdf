from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from tradutor_pdf.checkpoint.store import CheckpointStore
from tradutor_pdf.config import load_settings
from tradutor_pdf.export.converter import DocumentConverter
from tradutor_pdf.translation.prompt import PROMPT_VERSION
from tradutor_pdf.ui.utils import format_eta
from tradutor_pdf.ui.worker import TranslationWorker

logger = logging.getLogger(__name__)


class DropArea(QFrame):
    """Drag-and-drop area that accepts only .pdf files."""

    file_dropped = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.setLineWidth(2)
        self.setStyleSheet(
            """
            DropArea {
                border: 2px dashed #888888;
                border-radius: 8px;
                background-color: #f7f9fa;
                min-height: 180px;
            }
            DropArea[dragActive="true"] {
                border-color: #2b7de9;
                background-color: #eaf2fd;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel("Arraste e solte o arquivo PDF aqui\nou")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-size: 15px; color: #555555;")
        layout.addWidget(self.label)

        self.btn_select = QPushButton("Selecionar arquivo…")
        self.btn_select.setStyleSheet(
            "padding: 8px 16px; font-size: 14px; font-weight: bold;"
        )
        self.btn_select.clicked.connect(self._open_file_dialog)
        layout.addWidget(self.btn_select, alignment=Qt.AlignmentFlag.AlignCenter)

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.isEnabled():
            event.ignore()
            return

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    self._set_drag_active(True)
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        if not self.isEnabled():
            event.ignore()
            return

        urls = event.mimeData().urls()
        if len(urls) == 1:
            file_path = Path(urls[0].toLocalFile())
            if file_path.is_file() and file_path.suffix.lower() == ".pdf":
                event.acceptProposedAction()
                self.file_dropped.emit(file_path)
                return
        event.ignore()

    def _open_file_dialog(self) -> None:
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar documento PDF",
            "",
            "Arquivos PDF (*.pdf)",
        )
        if file_path_str:
            path = Path(file_path_str)
            if path.is_file():
                self.file_dropped.emit(path)


class ExportDialog(QDialog):
    """Dialog allowing user to choose export format (MD, PDF, EPUB) and destination directory."""

    def __init__(
        self,
        markdown_path: Path,
        default_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.markdown_path = Path(markdown_path)
        self.exported_path: Path | None = None

        self.setWindowTitle("Exportar Tradução")
        self.resize(520, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "A tradução foi concluída! Escolha o formato final e a pasta de destino:"
        )
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        # Formats
        form_group = QGroupBox("Formato de Saída", self)
        form_layout = QVBoxLayout(form_group)
        self.rb_pdf = QRadioButton(
            "PDF (.pdf) — Documento formatado para leitura e impressão"
        )
        self.rb_epub = QRadioButton(
            "EPUB (.epub) — Livro digital com sumário navegável"
        )
        self.rb_md = QRadioButton(
            "Markdown (.md) — Texto original com pasta de imagens"
        )
        self.rb_pdf.setChecked(True)
        form_layout.addWidget(self.rb_pdf)
        form_layout.addWidget(self.rb_epub)
        form_layout.addWidget(self.rb_md)
        layout.addWidget(form_group)

        # Destination folder
        dest_group = QGroupBox("Pasta de Destino", self)
        dest_layout = QHBoxLayout(dest_group)
        settings = load_settings()
        initial_dir = default_dir or Path(settings.output.default_dir).expanduser()
        self.dest_edit = QLineEdit(str(initial_dir))
        self.btn_browse = QPushButton("Procurar…")
        self.btn_browse.clicked.connect(self._browse_destination)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(self.btn_browse)
        layout.addWidget(dest_group)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Manter apenas Markdown")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_export = QPushButton("Exportar")
        self.btn_export.setDefault(True)
        self.btn_export.setStyleSheet("font-weight: bold;")
        self.btn_export.clicked.connect(self._do_export)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)

    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar pasta de destino",
            self.dest_edit.text() or "",
        )
        if folder:
            self.dest_edit.setText(folder)

    def _do_export(self) -> None:
        dest_text = self.dest_edit.text().strip()
        target_dir = (
            Path(dest_text).expanduser() if dest_text else self.markdown_path.parent
        )
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(
                self, "Erro", f"Não foi possível criar a pasta de destino:\n{exc}"
            )
            return

        fmt = "pdf"
        if self.rb_epub.isChecked():
            fmt = "epub"
        elif self.rb_md.isChecked():
            fmt = "md"

        try:
            converter = DocumentConverter()
            self.exported_path = converter.convert(
                input_path=self.markdown_path,
                target_format=fmt,
                destination=target_dir,
            )
            self.accept()
        except (RuntimeError, ValueError, OSError) as exc:
            logger.exception("Export failed")
            QMessageBox.critical(
                self, "Erro na Exportação", f"Falha ao exportar documento:\n{exc}"
            )


class ConversionDialog(QDialog):
    """Dialog for converting documents between PDF, MD, and EPUB without translation."""

    def __init__(
        self,
        default_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.converted_path: Path | None = None
        self.setWindowTitle("Converter Arquivo")
        self.resize(520, 260)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Source file
        src_group = QGroupBox("Arquivo de Origem", self)
        src_layout = QHBoxLayout(src_group)
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText(
            "Selecione um arquivo PDF, EPUB ou Markdown..."
        )
        self.btn_browse_src = QPushButton("Selecionar…")
        self.btn_browse_src.clicked.connect(self._browse_source)
        src_layout.addWidget(self.src_edit)
        src_layout.addWidget(self.btn_browse_src)
        layout.addWidget(src_group)

        # Target format
        fmt_group = QGroupBox("Formato de Destino", self)
        fmt_layout = QHBoxLayout(fmt_group)
        self.combo_format = QComboBox()
        self.combo_format.addItems(
            [
                "Markdown (.md)",
                "PDF (.pdf)",
                "EPUB (.epub)",
            ]
        )
        fmt_layout.addWidget(self.combo_format)
        layout.addWidget(fmt_group)

        # Destination folder
        dest_group = QGroupBox("Pasta de Destino", self)
        dest_layout = QHBoxLayout(dest_group)
        settings = load_settings()
        initial_dir = default_dir or Path(settings.output.default_dir).expanduser()
        self.dest_edit = QLineEdit(str(initial_dir))
        self.btn_browse_dest = QPushButton("Procurar…")
        self.btn_browse_dest.clicked.connect(self._browse_destination)
        dest_layout.addWidget(self.dest_edit)
        dest_layout.addWidget(self.btn_browse_dest)
        layout.addWidget(dest_group)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_convert = QPushButton("Converter")
        self.btn_convert.setDefault(True)
        self.btn_convert.setStyleSheet("font-weight: bold;")
        self.btn_convert.clicked.connect(self._do_convert)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_convert)
        layout.addLayout(btn_layout)

    def _browse_source(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo para conversão",
            "",
            "Arquivos Suportados (*.pdf *.epub *.md *.markdown);;PDF (*.pdf);;EPUB (*.epub);;Markdown (*.md *.markdown)",
        )
        if file_path:
            self.src_edit.setText(file_path)

    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar pasta de destino",
            self.dest_edit.text() or "",
        )
        if folder:
            self.dest_edit.setText(folder)

    def _do_convert(self) -> None:
        src_path_str = self.src_edit.text().strip()
        if not src_path_str:
            QMessageBox.warning(self, "Aviso", "Selecione o arquivo de origem.")
            return

        source = Path(src_path_str)
        if not source.is_file():
            QMessageBox.critical(
                self, "Erro", f"Arquivo de origem não encontrado:\n{source}"
            )
            return

        dest_dir_str = self.dest_edit.text().strip()
        target_dir = Path(dest_dir_str).expanduser() if dest_dir_str else source.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        selected_text = self.combo_format.currentText()
        if "PDF" in selected_text:
            target_fmt = "pdf"
        elif "EPUB" in selected_text:
            target_fmt = "epub"
        else:
            target_fmt = "md"

        try:
            converter = DocumentConverter()
            self.converted_path = converter.convert(
                input_path=source,
                target_format=target_fmt,
                destination=target_dir,
            )
            self.accept()
        except (RuntimeError, ValueError, OSError) as exc:
            logger.exception("Conversion failed")
            QMessageBox.critical(
                self, "Erro na Conversão", f"Falha ao converter arquivo:\n{exc}"
            )


class MainWindow(QMainWindow):
    """Main application window for Tradutor de PDF."""

    def __init__(
        self,
        worker_factory: Callable[[Path], TranslationWorker] | None = None,
        auto_prompt_export: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.auto_prompt_export = auto_prompt_export
        self.setWindowTitle("Tradutor de PDF")
        self.resize(640, 420)
        self.current_worker: TranslationWorker | None = None

        self._current_stage: str = ""
        self._current_page: int = 0
        self._total_pages: int = 0
        self._done_chunks: int = 0
        self._total_chunks: int = 0

        # Menu bar
        self._setup_menu()

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(15)

        # Top row: title + Converter button
        top_layout = QHBoxLayout()
        self.header_label = QLabel("Tradutor de PDF (EN → pt-BR)")
        self.header_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #222222;"
        )
        top_layout.addWidget(self.header_label)
        top_layout.addStretch()

        self.btn_convert_dialog = QPushButton("Converter arquivo…")
        self.btn_convert_dialog.setStyleSheet("padding: 5px 12px; font-size: 13px;")
        self.btn_convert_dialog.clicked.connect(self._open_conversion_dialog)
        top_layout.addWidget(self.btn_convert_dialog)
        root_layout.addLayout(top_layout)

        # Drag and drop area
        self.drop_area = DropArea(self)
        self.drop_area.file_dropped.connect(self.start_translation)
        root_layout.addWidget(self.drop_area)

        # Progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("min-height: 20px;")
        root_layout.addWidget(self.progress_bar)

        # Status and info
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Pronto para traduzir.")
        self.status_label.setStyleSheet("color: #444444; font-size: 13px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet(
            "color: #555555; font-size: 13px; font-weight: 500;"
        )
        status_layout.addWidget(self.eta_label)
        root_layout.addLayout(status_layout)

    def _setup_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&Arquivo")

        self.convert_action = QAction("&Converter arquivo…", self)
        self.convert_action.setShortcut("Ctrl+K")
        self.convert_action.triggered.connect(self._open_conversion_dialog)
        file_menu.addAction(self.convert_action)

        file_menu.addSeparator()

        self.exit_action = QAction("&Sair", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.triggered.connect(self.close)
        file_menu.addAction(self.exit_action)

    def _open_conversion_dialog(self) -> Path | None:
        dialog = ConversionDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.converted_path:
                self.status_label.setStyleSheet("color: #1b8a36; font-size: 13px;")
                self.status_label.setText(
                    f"Arquivo convertido com sucesso:\n{dialog.converted_path}"
                )
            return dialog.converted_path
        return None

    def prompt_export(self, markdown_path: Path) -> Path | None:
        """Prompt user with export dialog to choose format and destination folder."""
        dialog = ExportDialog(markdown_path=markdown_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.exported_path:
                self.status_label.setStyleSheet("color: #1b8a36; font-size: 13px;")
                self.status_label.setText(
                    f"Arquivo exportado com sucesso para:\n{dialog.exported_path}"
                )
            return dialog.exported_path
        return None

    def start_translation(self, pdf_path: Path) -> None:
        if self.current_worker and self.current_worker.isRunning():
            logger.warning("Translation already in progress. Ignoring new request.")
            return

        checkpoint_store = CheckpointStore()
        on_conflict = "reuse"
        if pdf_path.is_file() and checkpoint_store.has_checkpoint(pdf_path):
            manifest = checkpoint_store.load_manifest(pdf_path)
            settings = load_settings()
            if manifest and (
                manifest.model != settings.translation.model
                or manifest.prompt_version != PROMPT_VERSION
            ):
                reply = QMessageBox.question(
                    self,
                    "Configuração alterada",
                    "O modelo ou a versão do prompt foram alterados desde a última execução.\n\n"
                    f"Modelo salvo: {manifest.model}\n"
                    f"Modelo atual: {settings.translation.model}\n\n"
                    "Deseja reaproveitar os trechos já traduzidos ou reiniciar a tradução do zero?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.No:
                    on_conflict = "restart"
                    checkpoint_store.clear(pdf_path)

        logger.info("Initiating translation for %s", pdf_path)
        self._current_stage = "Iniciando"
        self._current_page = 0
        self._total_pages = 0
        self._done_chunks = 0
        self._total_chunks = 0

        self.drop_area.setEnabled(False)
        self.eta_label.setText("")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Iniciando…")
        self.status_label.setStyleSheet("color: #0b63ce; font-size: 13px;")
        self.status_label.setText(f"Iniciando tradução de {pdf_path.name}...")

        if self.worker_factory:
            self.current_worker = self.worker_factory(pdf_path)
        else:
            self.current_worker = TranslationWorker(
                source_path=pdf_path,
                checkpoint_store=checkpoint_store,
                on_conflict=on_conflict,
            )

        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.status_changed.connect(self._on_status_changed)
        if hasattr(self.current_worker, "stage_changed"):
            self.current_worker.stage_changed.connect(self._on_stage_changed)
        if hasattr(self.current_worker, "page_progress"):
            self.current_worker.page_progress.connect(self._on_page_progress)
        if hasattr(self.current_worker, "eta_updated"):
            self.current_worker.eta_updated.connect(self._on_eta_updated)
        self.current_worker.finished.connect(self._on_finished)
        self.current_worker.failed.connect(self._on_failed)

        self.current_worker.start()

    def _on_eta_updated(self, seconds: float) -> None:
        if seconds > 0:
            self.eta_label.setText(f"Tempo restante: {format_eta(seconds)}")
        else:
            self.eta_label.setText("")

    def _on_stage_changed(self, stage: str) -> None:
        self._current_stage = stage
        self._update_progress_display()

    def _on_page_progress(
        self, current_page: int, total_pages: int, stage: str
    ) -> None:
        self._current_page = current_page
        self._total_pages = total_pages
        self._current_stage = stage
        self._update_progress_display()

    def _on_progress(self, done: int, total: int) -> None:
        self._done_chunks = done
        self._total_chunks = total
        self._update_progress_display()

    def _update_progress_display(self) -> None:
        stage = self._current_stage or "Processando"
        page_info = (
            f"Página {self._current_page} de {self._total_pages}"
            if self._total_pages > 0 and self._current_page > 0
            else ""
        )

        if stage == "Traduzindo" and self._total_chunks > 0:
            pct = int((self._done_chunks / self._total_chunks) * 100)
            self.progress_bar.setValue(pct)
            if page_info:
                self.progress_bar.setFormat(f"{page_info} — {stage} ({pct}%)")
            else:
                self.progress_bar.setFormat(f"{stage} ({pct}%)")
        elif self._total_pages > 0 and self._current_page > 0:
            pct = int((self._current_page / self._total_pages) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{page_info} — {stage}")
        elif self._total_chunks > 0:
            pct = int((self._done_chunks / self._total_chunks) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{stage} ({pct}%)")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"{stage}…")

    def _on_status_changed(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_finished(self, output_path: Path) -> None:
        logger.info("Translation finished: %s", output_path)
        self.drop_area.setEnabled(True)
        self.eta_label.setText("")
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("100% Concluído")
        self.status_label.setStyleSheet("color: #1b8a36; font-size: 13px;")
        self.status_label.setText(f"Tradução salva com sucesso em:\n{output_path}")
        self.current_worker = None

        if self.auto_prompt_export:
            self.prompt_export(output_path)

    def _on_failed(self, error_message: str) -> None:
        logger.error("Translation error: %s", error_message)
        self.drop_area.setEnabled(True)
        self.eta_label.setText("")
        self.status_label.setStyleSheet("color: #d32f2f; font-size: 13px;")
        self.status_label.setText(f"Erro na tradução: {error_message}")
        self.current_worker = None
