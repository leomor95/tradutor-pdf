from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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


class MainWindow(QMainWindow):
    """Main application window for Tradutor de PDF."""

    def __init__(
        self,
        worker_factory: Callable[[Path], TranslationWorker] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.worker_factory = worker_factory
        self.current_worker: TranslationWorker | None = None

        self.setWindowTitle("Tradutor de PDF")
        self.resize(620, 380)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(15)

        # Header title
        self.header_label = QLabel("Tradutor de PDF (EN → pt-BR)")
        self.header_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #222222;"
        )
        root_layout.addWidget(self.header_label)

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
        root_layout.addLayout(status_layout)

    def start_translation(self, pdf_path: Path) -> None:
        if self.current_worker and self.current_worker.isRunning():
            logger.warning("Translation already in progress. Ignoring new request.")
            return

        logger.info("Initiating translation for %s", pdf_path)
        self.drop_area.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setStyleSheet("color: #0b63ce; font-size: 13px;")
        self.status_label.setText(f"Iniciando tradução de {pdf_path.name}...")

        if self.worker_factory:
            self.current_worker = self.worker_factory(pdf_path)
        else:
            self.current_worker = TranslationWorker(source_path=pdf_path)

        self.current_worker.progress.connect(self._on_progress)
        self.current_worker.status_changed.connect(self._on_status_changed)
        self.current_worker.finished.connect(self._on_finished)
        self.current_worker.failed.connect(self._on_failed)

        self.current_worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            pct = int((done / total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{pct}% ({done}/{total})")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")

    def _on_status_changed(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_finished(self, output_path: Path) -> None:
        logger.info("Translation finished: %s", output_path)
        self.drop_area.setEnabled(True)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("100% Concluído")
        self.status_label.setStyleSheet("color: #1b8a36; font-size: 13px;")
        self.status_label.setText(f"Tradução salva com sucesso em:\n{output_path}")
        self.current_worker = None

    def _on_failed(self, error_message: str) -> None:
        logger.error("Translation error: %s", error_message)
        self.drop_area.setEnabled(True)
        self.status_label.setStyleSheet("color: #d32f2f; font-size: 13px;")
        self.status_label.setText(f"Erro na tradução: {error_message}")
        self.current_worker = None
