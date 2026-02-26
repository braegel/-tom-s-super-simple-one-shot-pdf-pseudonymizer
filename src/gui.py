"""
PDF Anonymizer – Modern PyQt6 GUI with drag & drop, API key settings,
and one-click anonymisation workflow.

Design: Dark theme with turquoise accents, smooth animations, clear
visual states (idle → processing → success/error), and a clickable
drop zone that doubles as a progress indicator.
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
    QGraphicsOpacityEffect,
    QSpacerItem,
)
from PyQt6.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    pyqtProperty,
    QSize,
    QSettings,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
)
from PyQt6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QPalette,
    QColor,
    QPainter,
    QPen,
    QBrush,
    QLinearGradient,
    QRadialGradient,
    QMouseEvent,
)

try:
    from ai_engine import (
        detect_entities, assign_variables, generate_natural_replacements,
        MODE_ANONYMIZE, MODE_PSEUDO_VARS, MODE_PSEUDO_NATURAL,
    )
    from pdf_processor import extract_text, redact_pdf, get_page_count
except ImportError as _imp_err:
    _import_error = _imp_err
    MODE_ANONYMIZE = "anonymize"
    MODE_PSEUDO_VARS = "pseudo_vars"
    MODE_PSEUDO_NATURAL = "pseudo_natural"
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


def save_mode(mode: str):
    s = _settings()
    s.setValue("processing_mode", mode)


def load_mode() -> str:
    s = _settings()
    return s.value("processing_mode", MODE_PSEUDO_VARS)


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

TURQUOISE       = "#00CED1"
TURQUOISE_MID   = "#00A5A8"
TURQUOISE_DARK  = "#008B8B"
TURQUOISE_GLOW  = "#00E5E8"

BG_DARK         = "#0d1117"
BG_CARD         = "#161b22"
BG_SURFACE      = "#21262d"
BG_HOVER        = "#30363d"

BORDER          = "#30363d"
BORDER_FOCUS    = "#00CED1"

TEXT_PRIMARY    = "#f0f6fc"
TEXT_SECONDARY  = "#8b949e"
TEXT_MUTED      = "#6e7681"

SUCCESS         = "#3fb950"
ERROR           = "#f85149"
WARNING         = "#d29922"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
/* ── Global ────────────────────────────────────────────── */
QMainWindow {{
    background-color: {BG_DARK};
}}
QWidget#centralWidget {{
    background-color: {BG_DARK};
}}
QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 13px;
    background: transparent;
}}

/* ── Typography ────────────────────────────────────────── */
QLabel#titleLabel {{
    color: {TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.5px;
}}
QLabel#titleAccent {{
    color: {TURQUOISE};
    font-size: 24px;
    font-weight: 700;
}}
QLabel#subtitleLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    line-height: 1.5;
}}
QLabel#dropIcon {{
    font-size: 56px;
    background: transparent;
}}
QLabel#dropLabel {{
    color: {TEXT_PRIMARY};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#dropHint {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#fileLabel {{
    color: {TURQUOISE};
    font-size: 13px;
    font-weight: 600;
    padding: 4px 0px;
}}
QLabel#statusLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
QLabel#stepLabel {{
    color: {TURQUOISE};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#providerPill {{
    color: {TURQUOISE};
    background-color: rgba(0, 206, 209, 0.08);
    border: 1px solid rgba(0, 206, 209, 0.25);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#successLabel {{
    color: {SUCCESS};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#errorLabel {{
    color: {ERROR};
    font-size: 13px;
    font-weight: 600;
}}

/* ── Buttons ───────────────────────────────────────────── */
QPushButton {{
    background-color: {TURQUOISE_DARK};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {TURQUOISE_MID};
}}
QPushButton:pressed {{
    background-color: {TURQUOISE};
    color: {BG_DARK};
}}
QPushButton:disabled {{
    background-color: {BG_SURFACE};
    color: {TEXT_MUTED};
}}
QPushButton#settingsBtn {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#settingsBtn:hover {{
    color: {TEXT_PRIMARY};
    border-color: {TEXT_SECONDARY};
    background-color: {BG_SURFACE};
}}
QPushButton#selectBtn {{
    background-color: transparent;
    color: {TURQUOISE};
    border: 1px solid {TURQUOISE_DARK};
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
}}
QPushButton#selectBtn:hover {{
    background-color: rgba(0, 206, 209, 0.1);
    border-color: {TURQUOISE};
}}
QPushButton#selectBtn:disabled {{
    color: {TEXT_MUTED};
    border-color: {BORDER};
    background-color: transparent;
}}
QPushButton#openFolderBtn {{
    background-color: transparent;
    color: {SUCCESS};
    border: 1px solid rgba(63, 185, 80, 0.4);
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 12px;
}}
QPushButton#openFolderBtn:hover {{
    background-color: rgba(63, 185, 80, 0.1);
    border-color: {SUCCESS};
}}

/* ── Progress ──────────────────────────────────────────── */
QProgressBar {{
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {TEXT_PRIMARY};
    background-color: {BG_SURFACE};
    max-height: 8px;
    min-height: 8px;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {TURQUOISE_DARK}, stop:1 {TURQUOISE_GLOW});
    border-radius: 4px;
}}

/* ── Inputs ────────────────────────────────────────────── */
QComboBox {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
}}
QComboBox:focus {{
    border-color: {TURQUOISE_DARK};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    selection-background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    outline: none;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QLineEdit {{
    background-color: {BG_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {TURQUOISE_DARK};
}}
QLineEdit:focus {{
    border-color: {TURQUOISE_DARK};
}}
QLineEdit[valid="true"] {{
    border-color: {SUCCESS};
}}

/* ── Groups ────────────────────────────────────────────── */
QGroupBox {{
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 20px 16px 12px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {TEXT_PRIMARY};
}}

/* ── Dialog ────────────────────────────────────────────── */
QDialog {{
    background-color: {BG_DARK};
}}

/* ── Status bar ────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG_CARD};
    color: {TEXT_MUTED};
    font-size: 11px;
    border-top: 1px solid {BORDER};
    padding: 2px 8px;
}}

/* ── Mode selector ────────────────────────────────────── */
QComboBox#modeSelector {{
    background-color: {BG_SURFACE};
    color: {TURQUOISE};
    border: 1px solid rgba(0, 206, 209, 0.25);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    min-width: 280px;
}}
QComboBox#modeSelector:hover {{
    border-color: {TURQUOISE};
    background-color: rgba(0, 206, 209, 0.06);
}}
QComboBox#modeSelector:focus {{
    border-color: {TURQUOISE};
}}

/* ── Drop zone ─────────────────────────────────────────── */
QFrame#dropZone {{
    background-color: {BG_CARD};
    border: 2px dashed {BORDER};
    border-radius: 16px;
}}
QFrame#dropZone:hover {{
    border-color: {TURQUOISE_DARK};
    background-color: rgba(0, 206, 209, 0.03);
}}
QFrame#dropZone[dragOver="true"] {{
    border-color: {TURQUOISE};
    border-style: solid;
    background-color: rgba(0, 206, 209, 0.06);
}}
QFrame#dropZone[processing="true"] {{
    border-color: {TURQUOISE_DARK};
    border-style: solid;
}}
QFrame#dropZone[success="true"] {{
    border-color: {SUCCESS};
    border-style: solid;
    background-color: rgba(63, 185, 80, 0.04);
}}
QFrame#dropZone[error="true"] {{
    border-color: {ERROR};
    border-style: solid;
    background-color: rgba(248, 81, 73, 0.04);
}}

/* ── Scrollbar (thin) ──────────────────────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background-color: {BG_HOVER};
    border-radius: 3px;
    min-height: 30px;
}}
"""


# ---------------------------------------------------------------------------
# Animated drop zone with visual states
# ---------------------------------------------------------------------------

class DropZone(QFrame):
    """Drop zone that accepts PDF files and shows processing states."""
    file_dropped = pyqtSignal(str)
    clicked = pyqtSignal()

    STATE_IDLE = "idle"
    STATE_PROCESSING = "processing"
    STATE_SUCCESS = "success"
    STATE_ERROR = "error"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(240)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._state = self.STATE_IDLE

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setObjectName("dropIcon")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        # Primary label
        self.primary_label = QLabel()
        self.primary_label.setObjectName("dropLabel")
        self.primary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.primary_label)

        # Secondary label
        self.secondary_label = QLabel()
        self.secondary_label.setObjectName("dropHint")
        self.secondary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.secondary_label)

        # Step indicator (shown during processing)
        self.step_label = QLabel()
        self.step_label.setObjectName("stepLabel")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step_label.setVisible(False)
        layout.addWidget(self.step_label)

        # Progress bar (inside the drop zone)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setMaximumWidth(320)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.set_state(self.STATE_IDLE)

    def set_state(self, state: str, detail: str = ""):
        self._state = state
        # Reset all dynamic properties
        for prop in ("dragOver", "processing", "success", "error"):
            self.setProperty(prop, False)

        if state == self.STATE_IDLE:
            self.icon_label.setText("\U0001F4C4")  # document emoji
            self.primary_label.setText("PDF hier ablegen")
            self.secondary_label.setText("oder klicken, um eine Datei auszuwählen")
            self.secondary_label.setVisible(True)
            self.step_label.setVisible(False)
            self.progress_bar.setVisible(False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAcceptDrops(True)

        elif state == self.STATE_PROCESSING:
            self.setProperty("processing", True)
            self.icon_label.setText("\U0001F50D")  # magnifying glass
            self.primary_label.setText("Wird verarbeitet …")
            self.secondary_label.setVisible(False)
            self.step_label.setVisible(True)
            self.step_label.setText(detail or "Initialisiere …")
            self.progress_bar.setVisible(True)
            self.setCursor(Qt.CursorShape.WaitCursor)
            self.setAcceptDrops(False)

        elif state == self.STATE_SUCCESS:
            self.setProperty("success", True)
            self.icon_label.setText("\u2705")  # check mark
            self.primary_label.setText("Anonymisierung abgeschlossen")
            self.primary_label.setStyleSheet(f"color: {SUCCESS};")
            self.secondary_label.setText(detail or "")
            self.secondary_label.setVisible(bool(detail))
            self.step_label.setVisible(False)
            self.progress_bar.setVisible(False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAcceptDrops(True)

        elif state == self.STATE_ERROR:
            self.setProperty("error", True)
            self.icon_label.setText("\u274C")  # cross mark
            self.primary_label.setText("Fehler aufgetreten")
            self.primary_label.setStyleSheet(f"color: {ERROR};")
            self.secondary_label.setText("Klicken oder neue Datei ablegen, um es erneut zu versuchen")
            self.secondary_label.setVisible(True)
            self.step_label.setVisible(False)
            self.progress_bar.setVisible(False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAcceptDrops(True)

        # Re-apply style to pick up property changes
        if state != self.STATE_PROCESSING:
            self.primary_label.setStyleSheet("")  # reset inline override
        if state == self.STATE_SUCCESS:
            self.primary_label.setStyleSheet(f"color: {SUCCESS};")
        elif state == self.STATE_ERROR:
            self.primary_label.setStyleSheet(f"color: {ERROR};")

        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_progress(self, value: int):
        self.progress_bar.setValue(value)

    def set_step(self, text: str):
        self.step_label.setText(text)

    # -- Events --

    def mousePressEvent(self, event: QMouseEvent):
        if self._state != self.STATE_PROCESSING:
            self.clicked.emit()

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
# Worker thread
# ---------------------------------------------------------------------------

class AnonymizeWorker(QThread):
    progress = pyqtSignal(int)           # 0-100
    status = pyqtSignal(str)             # status text
    step = pyqtSignal(str)               # step indicator  (1/4, 2/4 …)
    entity_count = pyqtSignal(int)       # number of entities found
    finished_ok = pyqtSignal(str)        # output path
    finished_err = pyqtSignal(str)       # error message

    def __init__(self, pdf_path: str, output_path: str, provider: str, api_key: str, mode: str = MODE_PSEUDO_VARS):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.provider = provider
        self.api_key = api_key
        self.mode = mode

    def run(self):
        try:
            # Step 1 – extract text
            self.step.emit("Schritt 1/4  –  Text extrahieren")
            self.status.emit("Text wird aus dem PDF extrahiert …")
            self.progress.emit(5)
            text = extract_text(self.pdf_path)

            # Step 2 – AI entity detection
            self.step.emit("Schritt 2/4  –  KI-Analyse")
            self.status.emit("KI analysiert den Text …")
            self.progress.emit(10)

            def _ai_progress(pct):
                self.progress.emit(10 + int(pct * 0.30))

            entities = detect_entities(
                self.provider, self.api_key, text,
                progress_callback=_ai_progress,
            )

            if not entities:
                self.entity_count.emit(0)
                self.status.emit("Keine personenbezogenen Daten gefunden.")
                self.progress.emit(100)
                import shutil
                shutil.copy2(self.pdf_path, self.output_path)
                self.finished_ok.emit(self.output_path)
                return

            self.entity_count.emit(len(entities))

            # Step 3 – assign labels (variables / natural replacements)
            replacements = None
            if self.mode == MODE_PSEUDO_NATURAL:
                self.step.emit("Schritt 3/4  –  Natürliche Ersetzungen generieren")
                self.status.emit(f"{len(entities)} Entitäten erkannt – generiere Ersetzungen …")
                self.progress.emit(42)
                replacements = generate_natural_replacements(
                    self.provider, self.api_key, entities,
                )
            else:
                self.step.emit("Schritt 3/4  –  Variablen zuweisen")
                self.status.emit(f"{len(entities)} Entitäten erkannt …")
                self.progress.emit(42)

            entity_map = assign_variables(entities, mode=self.mode, replacements=replacements)

            # Step 4 – redact PDF
            mode_label = {
                MODE_ANONYMIZE: "anonymisieren",
                MODE_PSEUDO_VARS: "pseudonymisieren",
                MODE_PSEUDO_NATURAL: "pseudonymisieren",
            }.get(self.mode, "verarbeiten")
            self.step.emit(f"Schritt 4/4  –  PDF {mode_label}")
            self.status.emit("PDF wird geschrieben …")

            def _pdf_progress(pct):
                self.progress.emit(45 + int(pct * 0.50))

            redact_pdf(
                self.pdf_path, self.output_path, entity_map,
                mode=self.mode, progress_callback=_pdf_progress,
            )

            self.progress.emit(100)
            self.finished_ok.emit(self.output_path)

        except Exception as e:
            self.finished_err.emit(f"{e}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Settings dialog (polished)
# ---------------------------------------------------------------------------

PROVIDER_NAMES = {
    "openai":    "OpenAI (GPT-5.2)",
}
PROVIDER_KEYS = ["openai"]
PROVIDER_PLACEHOLDERS = {
    "openai":    "sk-...",
}


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setMinimumWidth(500)
        self.setStyleSheet(STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(18)
        layout.setContentsMargins(28, 28, 28, 24)

        # -- Header --
        header = QLabel("Einstellungen")
        header.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: 700;")
        layout.addWidget(header)
        desc = QLabel("Hinterlegen Sie Ihren OpenAI API-Key. Es wird GPT-5.2 verwendet.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(desc)

        layout.addSpacing(4)

        # -- Model info --
        model_label = QLabel("Modell:  GPT-5.2")
        model_label.setStyleSheet(
            f"color: {TURQUOISE}; font-size: 13px; font-weight: 600; "
            f"background-color: rgba(0, 206, 209, 0.08); "
            f"border: 1px solid rgba(0, 206, 209, 0.25); "
            f"border-radius: 8px; padding: 8px 14px;"
        )
        layout.addWidget(model_label)

        layout.addSpacing(4)

        # -- API key --
        keys_group = QGroupBox("OpenAI API-Key")
        keys_layout = QFormLayout(keys_group)
        keys_layout.setSpacing(10)

        self.key_field = QLineEdit(load_api_key("openai"))
        self.key_field.setPlaceholderText("sk-...")
        self.key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_field.setMinimumHeight(36)
        self.key_field.textChanged.connect(self._on_key_changed)
        keys_layout.addRow("API-Key:", self.key_field)

        layout.addWidget(keys_group)
        layout.addStretch()

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.setObjectName("selectBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Speichern")
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self.save_and_close)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_key_changed(self):
        """Give a green border hint when the key field has content."""
        has_value = bool(self.key_field.text().strip())
        self.key_field.setProperty("valid", has_value)
        self.key_field.style().unpolish(self.key_field)
        self.key_field.style().polish(self.key_field)

    def save_and_close(self):
        save_api_key("openai", self.key_field.text().strip())
        save_provider("openai")
        self.accept()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Anonymizer")
        self.setMinimumSize(640, 560)
        self.resize(720, 620)
        self.setStyleSheet(STYLESHEET)

        self.worker = None
        self.current_pdf: str | None = None
        self._last_output: str | None = None
        self._entity_count = 0

        # Central widget
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(32, 24, 32, 16)
        main_layout.setSpacing(0)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(8)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        t1 = QLabel("PDF ")
        t1.setObjectName("titleLabel")
        title_layout.addWidget(t1)
        t2 = QLabel("Anonymizer")
        t2.setObjectName("titleAccent")
        title_layout.addWidget(t2)
        title_layout.addStretch()
        header.addLayout(title_layout, stretch=1)

        # Provider pill
        self.provider_pill = QLabel()
        self.provider_pill.setObjectName("providerPill")
        self._update_provider_pill()
        header.addWidget(self.provider_pill, alignment=Qt.AlignmentFlag.AlignVCenter)

        header.addSpacing(8)

        settings_btn = QPushButton("Einstellungen")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.clicked.connect(self.open_settings)
        header.addWidget(settings_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        main_layout.addLayout(header)
        main_layout.addSpacing(4)

        # Subtitle
        subtitle = QLabel(
            "Automatische KI-gestützte Anonymisierung personenbezogener Daten in PDFs.  "
            "Voraussetzung: Das PDF muss Texterkennung (OCR) enthalten."
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(12)

        # ── Mode selector ──
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_label = QLabel("Modus:")
        mode_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 600;")
        mode_row.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("modeSelector")
        self.mode_combo.addItem("Anonymisieren  (nur Schwärzen)", MODE_ANONYMIZE)
        self.mode_combo.addItem("Pseudonymisieren  (Variablen)", MODE_PSEUDO_VARS)
        self.mode_combo.addItem("Pseudonymisieren  (Natürlich)", MODE_PSEUDO_NATURAL)
        # Restore saved mode
        saved_mode = load_mode()
        for i in range(self.mode_combo.count()):
            if self.mode_combo.itemData(i) == saved_mode:
                self.mode_combo.setCurrentIndex(i)
                break
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()

        main_layout.addLayout(mode_row)
        main_layout.addSpacing(12)

        # ── Drop zone ──
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.on_file_selected)
        self.drop_zone.clicked.connect(self.browse_pdf)
        main_layout.addWidget(self.drop_zone, stretch=1)
        main_layout.addSpacing(12)

        # ── Bottom bar (file info + buttons) ──
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self.file_label = QLabel("Keine Datei ausgewählt")
        self.file_label.setObjectName("fileLabel")
        self.file_label.setWordWrap(True)
        bottom.addWidget(self.file_label, stretch=1)

        self.open_folder_btn = QPushButton("Ordner öffnen")
        self.open_folder_btn.setObjectName("openFolderBtn")
        self.open_folder_btn.setVisible(False)
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        bottom.addWidget(self.open_folder_btn)

        self.select_btn = QPushButton("PDF auswählen")
        self.select_btn.setObjectName("selectBtn")
        self.select_btn.clicked.connect(self.browse_pdf)
        bottom.addWidget(self.select_btn)

        main_layout.addLayout(bottom)
        main_layout.addSpacing(4)

        # ── Status bar ──
        self.statusBar().showMessage("Bereit")
        self._update_statusbar_idle()

    # -- Helpers --

    def _update_provider_pill(self):
        has_key = bool(load_api_key("openai"))
        if has_key:
            self.provider_pill.setText("GPT-5.2")
        else:
            self.provider_pill.setText("GPT-5.2  (kein Key)")
            self.provider_pill.setStyleSheet(
                f"color: {WARNING}; background-color: rgba(210, 153, 34, 0.08); "
                f"border: 1px solid rgba(210, 153, 34, 0.25); "
                f"border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 600;"
            )
            return
        self.provider_pill.setStyleSheet("")  # reset to default from stylesheet

    def _update_statusbar_idle(self):
        prov = load_provider()
        has_key = bool(load_api_key(prov))
        if has_key:
            self.statusBar().showMessage("Bereit  –  PDF ablegen oder auswählen")
        else:
            self.statusBar().showMessage("Bitte zuerst einen API-Key in den Einstellungen hinterlegen")

    def _on_mode_changed(self):
        mode = self.mode_combo.currentData()
        save_mode(mode)

    def _current_mode(self) -> str:
        return self.mode_combo.currentData() or MODE_PSEUDO_VARS

    def _set_processing(self, active: bool):
        """Lock/unlock UI during processing."""
        self.select_btn.setEnabled(not active)
        self.mode_combo.setEnabled(not active)

    def _open_output_folder(self):
        if self._last_output:
            folder = os.path.dirname(self._last_output)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')

    # -- Slots --

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._update_provider_pill()
            self._update_statusbar_idle()

    def browse_pdf(self):
        if self.worker and self.worker.isRunning():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "PDF-Datei auswählen", "", "PDF-Dateien (*.pdf)"
        )
        if path:
            self.on_file_selected(path)

    def on_file_selected(self, path: str):
        if self.worker and self.worker.isRunning():
            return
        self.current_pdf = path
        self._last_output = None
        self.open_folder_btn.setVisible(False)
        name = os.path.basename(path)
        self.file_label.setText(name)
        self.statusBar().showMessage(f"Geladen: {name}")
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
                f"Bitte hinterlegen Sie zuerst einen API-Key für\n"
                f"{PROVIDER_NAMES.get(provider, provider)} in den Einstellungen.",
            )
            self.open_settings()
            api_key = load_api_key(load_provider())
            if not api_key:
                return

        # Ask for output location
        mode = self._current_mode()
        default_dir = load_output_dir() or os.path.dirname(self.current_pdf)
        base = os.path.splitext(os.path.basename(self.current_pdf))[0]
        suffix = "anonymisiert" if mode == MODE_ANONYMIZE else "pseudonymisiert"
        default_name = f"{base}_{suffix}.pdf"
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Anonymisiertes PDF speichern unter",
            os.path.join(default_dir, default_name),
            "PDF-Dateien (*.pdf)",
        )
        if not output_path:
            self.drop_zone.set_state(DropZone.STATE_IDLE)
            return

        save_output_dir(os.path.dirname(output_path))

        # Enter processing state
        self._set_processing(True)
        self.drop_zone.set_state(DropZone.STATE_PROCESSING, "Initialisiere …")
        self._entity_count = 0

        # Launch worker
        self.worker = AnonymizeWorker(self.current_pdf, output_path, provider, api_key, mode=mode)
        self.worker.progress.connect(self.drop_zone.set_progress)
        self.worker.step.connect(self.drop_zone.set_step)
        self.worker.status.connect(lambda s: self.statusBar().showMessage(s))
        self.worker.entity_count.connect(self._on_entity_count)
        self.worker.finished_ok.connect(self.on_success)
        self.worker.finished_err.connect(self.on_error)
        self.worker.start()

    def _on_entity_count(self, count: int):
        self._entity_count = count

    def on_success(self, output_path: str):
        self._set_processing(False)
        self._last_output = output_path

        out_name = os.path.basename(output_path)
        if self._entity_count > 0:
            mode = self._current_mode()
            action = "anonymisiert" if mode == MODE_ANONYMIZE else "pseudonymisiert"
            detail = f"{self._entity_count} Entitäten {action}  →  {out_name}"
        else:
            detail = f"Keine PII-Daten gefunden  →  Kopie erstellt als {out_name}"

        self.drop_zone.set_state(DropZone.STATE_SUCCESS, detail)
        self.file_label.setText(out_name)
        self.open_folder_btn.setVisible(True)
        self.statusBar().showMessage(f"Gespeichert: {output_path}")

        # Open the PDF in the default viewer
        self._open_pdf(output_path)

        # Reset to idle after 8 seconds so the user can drop the next file
        QTimer.singleShot(8000, self._reset_to_idle)

    def _open_pdf(self, path: str):
        """Open the PDF in the system's default PDF viewer."""
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", path])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass  # silently ignore if no viewer is available

    def on_error(self, msg: str):
        self._set_processing(False)
        self.drop_zone.set_state(DropZone.STATE_ERROR)
        self.statusBar().showMessage("Fehler bei der Verarbeitung")

        QMessageBox.critical(
            self,
            "Fehler",
            f"Bei der Verarbeitung ist ein Fehler aufgetreten:\n\n{msg}",
        )

        # Reset to idle after closing the error dialog
        QTimer.singleShot(500, self._reset_to_idle)

    def _reset_to_idle(self):
        if self.worker and self.worker.isRunning():
            return  # still processing a new file
        if self.drop_zone._state in (DropZone.STATE_SUCCESS, DropZone.STATE_ERROR):
            self.drop_zone.set_state(DropZone.STATE_IDLE)
            self.file_label.setText("Keine Datei ausgewählt")
            self.current_pdf = None
            self._update_statusbar_idle()


# ---------------------------------------------------------------------------
# Dependency check & entry point
# ---------------------------------------------------------------------------

def _check_dependencies() -> str | None:
    missing = []
    try:
        import fitz
    except ImportError:
        missing.append("PyMuPDF  (pip install PyMuPDF)")
    try:
        import openai
    except ImportError:
        missing.append("openai  (pip install openai)")
    if _import_error is not None and not missing:
        missing.append(str(_import_error))
    if missing:
        return "Fehlende Abhängigkeiten:\n\n" + "\n".join(f"  •  {m}" for m in missing)
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

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(TURQUOISE))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(BG_DARK))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_CARD))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    app.setPalette(palette)

    # Default font
    font = app.font()
    font.setFamily("Segoe UI, SF Pro Display, system-ui, sans-serif")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
