"""
DelugeHub — Settings Module
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QFileDialog, QComboBox, QCheckBox,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal
from pathlib import Path

APP_VERSION = "2.0.3"


class SettingsModule(QWidget):
    sd_path_changed = Signal(str)
    theme_changed = Signal(str)
    auto_scan_changed = Signal(bool)   # ← was missing, auto_scan was never saved

    def __init__(self, settings: dict):
        super().__init__()
        self._settings = settings
        self._build_ui()

    def _build_ui(self):
        # Äußeres Layout: nur Header + ScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 0)
        outer.setSpacing(0)

        # --- Header (bleibt fest, scrollt nicht mit) ---
        title = QLabel("⚙️  Einstellungen")
        title.setObjectName("PageTitle")
        subtitle = QLabel("App-Konfiguration und Pfade")
        subtitle.setObjectName("PageSubtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)
        outer.addSpacing(16)

        # --- ScrollArea für alle Karten ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 16, 24)
        layout.setSpacing(20)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # --- SD Card Path ---
        layout.addWidget(self._section("SD-CARD"))
        sd_card = self._make_card()
        sd_layout = QVBoxLayout(sd_card)
        sd_layout.setContentsMargins(16, 14, 16, 14)
        sd_layout.setSpacing(10)

        sd_row = QHBoxLayout()
        sd_label = QLabel("SD-Card Pfad:")
        sd_label.setFixedWidth(140)
        self._sd_input = QLineEdit(self._settings.get("sd_path", ""))
        self._sd_input.setPlaceholderText("Pfad zur SD-Card oder Ordner…")
        browse_btn = QPushButton("Durchsuchen")
        browse_btn.setObjectName("SecondaryButton")
        browse_btn.setFixedWidth(120)
        browse_btn.clicked.connect(self._browse_sd)
        sd_row.addWidget(sd_label)
        sd_row.addWidget(self._sd_input)
        sd_row.addWidget(browse_btn)
        sd_layout.addLayout(sd_row)

        apply_sd_btn = QPushButton("Pfad übernehmen")
        apply_sd_btn.setFixedWidth(160)
        apply_sd_btn.clicked.connect(self._apply_sd_path)
        sd_layout.addWidget(apply_sd_btn, alignment=Qt.AlignRight)
        layout.addWidget(sd_card)

        # --- Theme ---
        layout.addWidget(self._section("ERSCHEINUNGSBILD"))
        theme_card = self._make_card()
        theme_layout = QHBoxLayout(theme_card)
        theme_layout.setContentsMargins(16, 14, 16, 14)

        theme_lbl = QLabel("Theme:")
        theme_lbl.setFixedWidth(140)
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Dark", "Light"])
        self._theme_combo.setCurrentText(self._settings.get("theme", "Dark").capitalize())
        self._theme_combo.setFixedWidth(160)
        self._theme_combo.currentTextChanged.connect(
            lambda t: self.theme_changed.emit(t.lower())
        )
        theme_layout.addWidget(theme_lbl)
        theme_layout.addWidget(self._theme_combo)
        theme_layout.addStretch()
        layout.addWidget(theme_card)

        # --- Scan Options ---
        layout.addWidget(self._section("SCAN OPTIONEN"))
        scan_card = self._make_card()
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(16, 14, 16, 14)
        scan_layout.setSpacing(8)

        self._auto_scan_cb = QCheckBox("Beim Start automatisch scannen")
        self._auto_scan_cb.setChecked(self._settings.get("auto_scan", False))
        # Emit signal immediately when toggled so MainWindow can persist it.
        self._auto_scan_cb.toggled.connect(self._on_auto_scan_toggled)
        scan_layout.addWidget(self._auto_scan_cb)

        layout.addWidget(scan_card)

        # --- About ---
        layout.addWidget(self._section("ÜBER"))
        about_card = self._make_card()
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(16, 14, 16, 14)
        about_layout.setSpacing(4)

        for text, style in [
            (f"DelugeHub v{APP_VERSION}", "font-weight: bold; font-size: 15px;"),
            ("All-in-One Synthstrom Deluge SD-Card Manager", "color: #888888;"),
            ("Open Source — MIT License", "color: #1E6FBB; font-size: 12px;"),
            ("Community Project — delugecommunity.com", "color: #888888; font-size: 12px;"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(style)
            about_layout.addWidget(lbl)

        layout.addWidget(about_card)
        layout.addStretch()

    def _section(self, title: str) -> QLabel:
        lbl = QLabel(title)
        lbl.setObjectName("SectionTitle")
        return lbl

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _browse_sd(self):
        path = QFileDialog.getExistingDirectory(self, "SD-Card Ordner wählen", "")
        if path:
            self._sd_input.setText(path)
            self._apply_sd_path()

    def _apply_sd_path(self):
        path = self._sd_input.text().strip()
        if path:
            self._settings["sd_path"] = path
            self.sd_path_changed.emit(path)

    def _on_auto_scan_toggled(self, checked: bool):
        self._settings["auto_scan"] = checked
        self.auto_scan_changed.emit(checked)

    def get_settings(self) -> dict:
        return {
            "sd_path": self._sd_input.text().strip(),
            "theme": self._theme_combo.currentText().lower(),
            "auto_scan": self._auto_scan_cb.isChecked(),
        }
