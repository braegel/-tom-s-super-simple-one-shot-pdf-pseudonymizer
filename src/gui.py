"""
PDF Anonymizer – Modern PyQt6 GUI with drag & drop, API key settings,
and one-click anonymisation workflow.
"""

import os
import sys
import json
import traceback
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QMessageBox,
    QDialog,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QFormLayout,
    QFrame,
    QSizePolicy,
    QStatusBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData, QSize, QSettings
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QPalette,
    QColor,
    QPainter,
    QPixmap,
    QAction,
)

try:
    from ai_engine import detect_entities, assign_variables
    from pdf_processor import extract_text, redact_pdf, get_page_count
except ImportError as _imp_err:
    # Will be handled at startup with a friendly message
    _import_error = _imp_err
else:
    _import_error = None


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

SETTINGS_ORG = "PDFAnonymizer"
SETTINGS_APP = "PDFAnonymizer"


def _settings() -> QSettings:
    return QSettings(SETTINGS_ORG, SETTINGS_APP)


def save_api_key(provider: str, key: str):
    s = _settings()
    s.setValue(f"api_keys/{provider}", key)


def load_api_key(provider: str) -> str:
    s = _settings()
    return s.value(f"api_keys/{provider}", "")


def save_provider(provider: str):
    s = _settings()
    s.setValue("selected_provider", provider)


def load_provider() -> str:
    s = _settings()
    return s.value("selected_provider", "openai")


def save_output_dir(path: str):
    s = _settings()
    s.setValue("output_dir", path)


def load_output_dir() -> str:
    s = _settings()
    return s.value("output_dir", "")


# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------

TURQUOISE = "#00CED1"
TURQUOISE_DARK = "#008B8B"
BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
BG_SURFACE = "#0f3460"
TEXT_LIGHT = "#e0e0e0"
TEXT_WHITE = "#ffffff"
ACCENT = "#00CED1"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
QMainWindow {{
    background-color: {BG_DARK};
}}
QWidget#centralWidget {{
    background-color: {BG_DARK};
}}
QLabel {{
    color: {TEXT_LIGHT};
    font-size: 13px;
}}
QLabel#titleLabel {{
    color: {TURQUOISE};
    font-size: 26px;
    font-weight: bold;
}}
QLabel#subtitleLabel {{
    color: {TEXT_LIGHT};
    font-size: 13px;
}}
QLabel#dropLabel {{
    color: {TURQUOISE};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#dropHint {{
    color: #888;
    font-size: 12px;
}}
QLabel#fileLabel {{
    color: {TEXT_WHITE};
    font-size: 14px;
    font-weight: bold;
    padding: 8px;
}}
QPushButton {{
    background-color: {TURQUOISE_DARK};
    color: {TEXT_WHITE};
    border: none;
    border-radius: 6px;
    padding: 10px 24px;
    font-size: 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {TURQUOISE};
    color: {BG_DARK};
}}
QPushButton:disabled {{
    background-color: #333;
    color: #666;
}}
QPushButton#settingsBtn {{
    background-color: transparent;
    color: {TURQUOISE};
    border: 1px solid {TURQUOISE_DARK};
    padding: 6px 16px;
    font-size: 12px;
}}
QPushButton#settingsBtn:hover {{
    background-color: {TURQUOISE_DARK};
    color: {TEXT_WHITE};
}}
QProgressBar {{
    border: 1px solid {TURQUOISE_DARK};
    border-radius: 5px;
    text-align: center;
    color: {TEXT_WHITE};
    background-color: {BG_CARD};
    height: 22px;
    font-size: 12px;
}}
QProgressBar::chunk {{
    background-color: {TURQUOISE};
    border-radius: 4px;
}}
QComboBox {{
    background-color: {BG_SURFACE};
    color: {TEXT_LIGHT};
    border: 1px solid {TURQUOISE_DARK};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    color: {TEXT_LIGHT};
    selection-background-color: {TURQUOISE_DARK};
}}
QLineEdit {{
    background-color: {BG_SURFACE};
    color: {TEXT_LIGHT};
    border: 1px solid {TURQUOISE_DARK};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 13px;
}}
QGroupBox {{
    color: {TURQUOISE};
    border: 1px solid {TURQUOISE_DARK};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}}
QDialog {{
    background-color: {BG_DARK};
}}
QStatusBar {{
    background-color: {BG_CARD};
    color: {TEXT_LIGHT};
    font-size: 11px;
}}
QFrame#dropZone {{
    background-color: {BG_CARD};
    border: 2px dashed {TURQUOISE_DARK};
    border-radius: 16px;
}}
QFrame#dropZone[dragOver="true"] {{
    border-color: {TURQUOISE};
    background-color: {BG_SURFACE};
}}
"""


# ---------------------------------------------------------------------------
# Worker thread for anonymisation
# ---------------------------------------------------------------------------

class AnonymizeWorker(QThread):
    progress = pyqtSignal(int)           # 0-100
    status = pyqtSignal(str)             # status text
    finished_ok = pyqtSignal(str)        # output path
    finished_err = pyqtSignal(str)       # error message

    def __init__(self, pdf_path: str, output_path: str, provider: str, api_key: str):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.provider = provider
        self.api_key = api_key

    def run(self):
        try:
            # Step 1 – extract text
            self.status.emit("Text wird aus dem PDF extrahiert …")
            self.progress.emit(5)
            text = extract_text(self.pdf_path)

            # Step 2 – AI entity detection (with chunking for large texts)
            self.status.emit("KI analysiert den Text auf personenbezogene Daten …")
            self.progress.emit(10)

            def _ai_progress(pct):
                # Map 0-100 of AI progress to 10-40 of overall progress
                self.progress.emit(10 + int(pct * 0.30))

            entities = detect_entities(
                self.provider, self.api_key, text,
                progress_callback=_ai_progress,
            )

            if not entities:
                self.status.emit("Keine personenbezogenen Daten gefunden.")
                self.progress.emit(100)
                # Still produce a copy
                import shutil
                shutil.copy2(self.pdf_path, self.output_path)
                self.finished_ok.emit(self.output_path)
                return

            # Step 3 – assign variables
            self.status.emit(f"{len(entities)} Entitäten erkannt – Variablen werden zugewiesen …")
            self.progress.emit(42)
            entity_map = assign_variables(entities)

            # Step 4 – redact PDF
            self.status.emit("PDF wird anonymisiert …")

            def _pdf_progress(pct):
                # Map 0-100 of pdf progress to 45-95 of overall progress
                self.progress.emit(45 + int(pct * 0.50))

            redact_pdf(self.pdf_path, self.output_path, entity_map, progress_callback=_pdf_progress)

            self.status.emit("Fertig!")
            self.progress.emit(100)
            self.finished_ok.emit(self.output_path)

        except Exception as e:
            self.finished_err.emit(f"{e}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen – API-Keys")
        self.setMinimumWidth(520)
        self.setStyleSheet(STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Info label
        info = QLabel(
            "Hinterlegen Sie hier Ihre API-Keys. Es wird jeweils der Key\n"
            "des ausgewählten Anbieters verwendet."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Provider selection
        prov_group = QGroupBox("Aktiver KI-Anbieter")
        prov_layout = QFormLayout(prov_group)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["OpenAI (ChatGPT)", "Anthropic (Claude)", "Google (Gemini)"])
        provider_map = {"openai": 0, "anthropic": 1, "gemini": 2}
        self.provider_combo.setCurrentIndex(provider_map.get(load_provider(), 0))
        prov_layout.addRow("Anbieter:", self.provider_combo)
        layout.addWidget(prov_group)

        # API keys
        keys_group = QGroupBox("API-Keys")
        keys_layout = QFormLayout(keys_group)

        self.openai_key = QLineEdit(load_api_key("openai"))
        self.openai_key.setPlaceholderText("sk-...")
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        keys_layout.addRow("OpenAI:", self.openai_key)

        self.anthropic_key = QLineEdit(load_api_key("anthropic"))
        self.anthropic_key.setPlaceholderText("sk-ant-...")
        self.anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        keys_layout.addRow("Anthropic:", self.anthropic_key)

        self.gemini_key = QLineEdit(load_api_key("gemini"))
        self.gemini_key.setPlaceholderText("AI...")
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        keys_layout.addRow("Gemini:", self.gemini_key)

        layout.addWidget(keys_group)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Speichern")
        save_btn.clicked.connect(self.save_and_close)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.setStyleSheet(
            f"background-color: transparent; color: {TURQUOISE}; border: 1px solid {TURQUOISE_DARK};"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def save_and_close(self):
        save_api_key("openai", self.openai_key.text().strip())
        save_api_key("anthropic", self.anthropic_key.text().strip())
        save_api_key("gemini", self.gemini_key.text().strip())
        idx = self.provider_combo.currentIndex()
        prov = ["openai", "anthropic", "gemini"][idx]
        save_provider(prov)
        self.accept()


# ---------------------------------------------------------------------------
# Drop zone widget
# ---------------------------------------------------------------------------

class DropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        # Icon-like label
        icon_label = QLabel("📄")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        layout.addWidget(icon_label)

        drop_label = QLabel("PDF hier ablegen")
        drop_label.setObjectName("dropLabel")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop_label)

        hint = QLabel("oder klicken Sie auf „PDF auswählen"")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    # -- Drag & Drop events --

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    self.setProperty("dragOver", True)
                    self.style().unpolish(self)
                    self.style().polish(self)
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.file_dropped.emit(path)
                return


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Anonymizer")
        self.setMinimumSize(600, 520)
        self.resize(680, 580)
        self.setStyleSheet(STYLESHEET)

        self.worker = None
        self.current_pdf: str | None = None

        # Central widget
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(28, 20, 28, 20)
        main_layout.setSpacing(14)

        # Header row
        header = QHBoxLayout()
        title = QLabel("PDF Anonymizer")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()
        settings_btn = QPushButton("⚙  Einstellungen")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(settings_btn)
        main_layout.addLayout(header)

        subtitle = QLabel(
            "Automatische KI-gestützte Anonymisierung personenbezogener Daten in PDFs.\n"
            "Voraussetzung: Das PDF muss bereits Texterkennung (OCR) enthalten."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        main_layout.addWidget(subtitle)

        # Drop zone
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.on_file_selected)
        main_layout.addWidget(self.drop_zone, stretch=1)

        # File info & select button row
        file_row = QHBoxLayout()
        self.file_label = QLabel("Keine Datei ausgewählt")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setWordWrap(True)
        file_row.addWidget(self.file_label, stretch=1)
        select_btn = QPushButton("PDF auswählen")
        select_btn.clicked.connect(self.browse_pdf)
        file_row.addWidget(select_btn)
        main_layout.addLayout(file_row)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Status
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        main_layout.addWidget(self.status_label)

        # Status bar
        self.statusBar().showMessage("Bereit – bitte API-Key in den Einstellungen hinterlegen.")

    # -- Slots --

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            provider = load_provider()
            names = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini"}
            self.statusBar().showMessage(f"Anbieter: {names.get(provider, provider)}   ✓ Einstellungen gespeichert.")

    def browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "PDF-Datei auswählen", "", "PDF-Dateien (*.pdf)"
        )
        if path:
            self.on_file_selected(path)

    def on_file_selected(self, path: str):
        self.current_pdf = path
        name = os.path.basename(path)
        self.file_label.setText(f"📄  {name}")
        self.statusBar().showMessage(f"Datei geladen: {name}")
        # Automatically start processing
        self.start_anonymization()

    def start_anonymization(self):
        if not self.current_pdf:
            return

        # Check API key
        provider = load_provider()
        api_key = load_api_key(provider)
        if not api_key:
            QMessageBox.warning(
                self,
                "Kein API-Key",
                f"Bitte hinterlegen Sie zuerst einen API-Key für "
                f"den ausgewählten Anbieter ({provider}) in den Einstellungen.",
            )
            self.open_settings()
            # Recheck after settings dialog
            api_key = load_api_key(provider)
            if not api_key:
                return

        # Ask for output location
        default_dir = load_output_dir() or os.path.dirname(self.current_pdf)
        base = os.path.splitext(os.path.basename(self.current_pdf))[0]
        default_name = f"{base}_anonymisiert.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Anonymisiertes PDF speichern unter",
            os.path.join(default_dir, default_name),
            "PDF-Dateien (*.pdf)",
        )
        if not output_path:
            return

        # Remember output directory
        save_output_dir(os.path.dirname(output_path))

        # UI state
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Verarbeitung startet …")

        # Launch worker
        self.worker = AnonymizeWorker(self.current_pdf, output_path, provider, api_key)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self.on_success)
        self.worker.finished_err.connect(self.on_error)
        self.worker.start()

    def on_success(self, output_path: str):
        self.progress_bar.setValue(100)
        self.status_label.setText(f"✓  Anonymisierte Datei gespeichert!")
        self.statusBar().showMessage(f"Gespeichert: {output_path}")
        QMessageBox.information(
            self,
            "Fertig",
            f"Die anonymisierte PDF wurde erfolgreich erstellt:\n\n{output_path}",
        )
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.current_pdf = None
        self.file_label.setText("Keine Datei ausgewählt")

    def on_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        QMessageBox.critical(self, "Fehler", f"Bei der Verarbeitung ist ein Fehler aufgetreten:\n\n{msg}")
        self.statusBar().showMessage("Fehler bei der Verarbeitung.")


def _check_dependencies() -> str | None:
    """Return an error message if critical packages are missing, else None."""
    missing = []
    try:
        import fitz
    except ImportError:
        missing.append("PyMuPDF  (pip install PyMuPDF)")
    # AI packages are optional – only the selected provider needs to be present
    # but we check that at least one is available.
    has_any_ai = False
    for mod in ("openai", "anthropic", "google.generativeai"):
        try:
            __import__(mod)
            has_any_ai = True
            break
        except ImportError:
            pass
    if not has_any_ai:
        missing.append(
            "Mindestens ein KI-Paket: openai, anthropic oder google-generativeai\n"
            "  → pip install openai anthropic google-generativeai"
        )
    if _import_error is not None and not missing:
        missing.append(str(_import_error))
    if missing:
        return "Fehlende Abhängigkeiten:\n\n" + "\n".join(f"• {m}" for m in missing)
    return None


def run_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Check dependencies early
    dep_err = _check_dependencies()
    if dep_err:
        QMessageBox.critical(
            None,
            "Fehlende Pakete",
            f"{dep_err}\n\nBitte installieren Sie die fehlenden Pakete:\n"
            f"  pip install -r requirements.txt",
        )
        sys.exit(1)

    # Dark palette base
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_LIGHT))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_LIGHT))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_LIGHT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(TURQUOISE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_DARK))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
