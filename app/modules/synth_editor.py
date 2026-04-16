"""
DelugeHub — Synth Editor Module
Browse synths, edit parameters, randomize, export/import.
"""
import random
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QLineEdit, QSplitter, QComboBox, QSlider, QScrollArea,
    QGridLayout, QSizePolicy, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex, Synth


# ── Deluge value helpers ─────────────────────────────────────────────────
def hex_to_norm(hex_str: str) -> float:
    """Convert Deluge hex param (0x00000000–0xFFFFFFFF) to 0.0–1.0."""
    try:
        val = int(hex_str, 16) & 0xFFFFFFFF
        return val / 0xFFFFFFFF
    except Exception:
        return 0.5


def norm_to_hex(val: float) -> str:
    """Convert 0.0–1.0 to Deluge hex string."""
    val = max(0.0, min(1.0, val))
    return f"0x{int(val * 0xFFFFFFFF):08X}"


def rand_hex(lo: float = 0.0, hi: float = 1.0) -> str:
    return norm_to_hex(random.uniform(lo, hi))


# ── Param slider widget ─────────────────────────────────────────────────────
class ParamSlider(QWidget):
    valueChanged = Signal(float)  # normalized 0-1

    def __init__(self, label: str, value: float = 0.5):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setObjectName("ParamLabel")

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1000)
        self._slider.setValue(int(value * 1000))
        self._slider.valueChanged.connect(lambda v: self.valueChanged.emit(v / 1000))

        self._val_lbl = QLabel(f"{value:.2f}")
        self._val_lbl.setFixedWidth(36)
        self._val_lbl.setObjectName("ParamValue")
        self._slider.valueChanged.connect(lambda v: self._val_lbl.setText(f"{v/1000:.2f}"))

        layout.addWidget(lbl)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._val_lbl)

    def set_value(self, val: float):
        self._slider.setValue(int(max(0, min(1, val)) * 1000))


# ── Synth Editor ────────────────────────────────────────────────────────
class SynthEditorModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._synths: list[Synth] = []
        self._current_synth: Optional[Synth] = None
        self._param_sliders: dict[str, ParamSlider] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._lbl("🎹  Synth Editor", "PageTitle"))
        col.addWidget(self._lbl("Synths durchsuchen, Parameter bearbeiten, Randomizer", "PageSubtitle"))
        hdr.addLayout(col)
        hdr.addStretch()

        self._import_btn = QPushButton("⬇  Importieren")
        self._import_btn.clicked.connect(self._import_synth)
        self._import_btn.setFixedHeight(36)
        hdr.addWidget(self._import_btn)
        root.addLayout(hdr)
        root.addSpacing(14)

        # Toolbar
        tb = QFrame()
        tb.setObjectName("Card")
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Synths suchen…")
        self._search.textChanged.connect(self._filter)

        self._rand_btn = QPushButton("🎲  Randomizer")
        self._rand_btn.setToolTip("Zufälligen Synth generieren")
        self._rand_btn.clicked.connect(self._randomize)
        self._rand_btn.setEnabled(False)

        self._save_btn = QPushButton("💾  Speichern")
        self._save_btn.setObjectName("SuccessButton")
        self._save_btn.clicked.connect(self._save_params)
        self._save_btn.setEnabled(False)

        self._rename_btn = QPushButton("✏  Umbenennen")
        self._rename_btn.setObjectName("SecondaryButton")
        self._rename_btn.clicked.connect(self._rename_selected)
        self._rename_btn.setEnabled(False)

        self._dupe_btn = QPushButton("📋  Duplizieren")
        self._dupe_btn.setObjectName("SecondaryButton")
        self._dupe_btn.clicked.connect(self._duplicate_selected)
        self._dupe_btn.setEnabled(False)

        self._export_btn = QPushButton("📦  Exportieren")
        self._export_btn.setObjectName("SecondaryButton")
        self._export_btn.clicked.connect(self._export_selected)
        self._export_btn.setEnabled(False)

        self._delete_btn = QPushButton("🗑")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setFixedWidth(36)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)

        tb_layout.addWidget(QLabel("🔎"))
        tb_layout.addWidget(self._search, 1)
        tb_layout.addWidget(self._rand_btn)
        tb_layout.addWidget(self._save_btn)
        tb_layout.addWidget(self._rename_btn)
        tb_layout.addWidget(self._dupe_btn)
        tb_layout.addWidget(self._export_btn)
        tb_layout.addWidget(self._delete_btn)
        root.addWidget(tb)
        root.addSpacing(8)

        # Splitter: list | params
        splitter = QSplitter(Qt.Horizontal)

        # Synth list
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Name", "OSC1", "Filter"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.Interactive)
        hv.setSectionResizeMode(2, QHeaderView.Interactive)
        self._table.setColumnWidth(1, 75)
        self._table.setColumnWidth(2, 70)
        self._table.setMinimumWidth(220)
        self._table.setMaximumWidth(300)
        self._table.itemSelectionChanged.connect(self._on_synth_selected)
        splitter.addWidget(self._table)

        # Parameter editor (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        param_widget = QWidget()
        self._param_layout = QVBoxLayout(param_widget)
        self._param_layout.setSpacing(12)
        self._param_layout.setContentsMargins(12, 0, 12, 12)
        scroll.setWidget(param_widget)
        self._build_param_editor()
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self._status = QLabel("—")
        self._status.setObjectName("StatusLabel")
        root.addSpacing(6)
        root.addWidget(self._status)

    def _build_param_editor(self):
        layout = self._param_layout

        self._synth_title = QLabel("Kein Synth ausgewählt")
        self._synth_title.setObjectName("SynthTitle")
        layout.addWidget(self._synth_title)

        # OSC 1
        osc1_group = self._make_group("OSC 1")
        osc1_layout = QVBoxLayout(osc1_group)
        osc1_layout.setSpacing(4)

        osc1_row = QHBoxLayout()
        self._osc1_type = QComboBox()
        self._osc1_type.addItems(["square", "sine", "saw", "triangle", "analog square", "analog saw", "sample", "wavetable"])
        osc1_row.addWidget(QLabel("Typ:"))
        osc1_row.addWidget(self._osc1_type)
        osc1_row.addStretch()
        osc1_layout.addLayout(osc1_row)

        self._add_slider("osc1_volume", "Volume", 1.0, osc1_layout)
        self._add_slider("osc1_transpose", "Transpose", 0.5, osc1_layout)
        self._add_slider("osc1_pulsewidth", "Pulse Width", 0.5, osc1_layout)

        # OSC 2
        osc2_group = self._make_group("OSC 2")
        osc2_layout = QVBoxLayout(osc2_group)
        osc2_layout.setSpacing(4)

        osc2_row = QHBoxLayout()
        self._osc2_type = QComboBox()
        self._osc2_type.addItems(["square", "sine", "saw", "triangle", "analog square", "analog saw", "sample", "wavetable", "none"])
        osc2_row.addWidget(QLabel("Typ:"))
        osc2_row.addWidget(self._osc2_type)
        osc2_row.addStretch()
        osc2_layout.addLayout(osc2_row)
        self._add_slider("osc2_volume", "Volume", 0.5, osc2_layout)
        self._add_slider("osc2_transpose", "Transpose", 0.5, osc2_layout)

        # Filter
        filter_group = self._make_group("Filter")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setSpacing(4)

        filter_row = QHBoxLayout()
        self._filter_type = QComboBox()
        self._filter_type.addItems(["lpf12", "lpf24", "hpf12", "hpf24", "bandpass"])
        filter_row.addWidget(QLabel("Typ:"))
        filter_row.addWidget(self._filter_type)
        filter_row.addStretch()
        filter_layout.addLayout(filter_row)
        self._add_slider("filter_cutoff", "Cutoff", 0.8, filter_layout)
        self._add_slider("filter_resonance", "Resonance", 0.2, filter_layout)
        self._add_slider("filter_morph", "Morph", 0.0, filter_layout)

        # Envelope 1 (Amplitude)
        env1_group = self._make_group("Envelope 1 (Amp)")
        env1_layout = QVBoxLayout(env1_group)
        env1_layout.setSpacing(4)
        self._add_slider("env1_attack", "Attack", 0.1, env1_layout)
        self._add_slider("env1_decay", "Decay", 0.3, env1_layout)
        self._add_slider("env1_sustain", "Sustain", 0.7, env1_layout)
        self._add_slider("env1_release", "Release", 0.2, env1_layout)

        # Envelope 2 (Filter/Mod)
        env2_group = self._make_group("Envelope 2 (Mod)")
        env2_layout = QVBoxLayout(env2_group)
        env2_layout.setSpacing(4)
        self._add_slider("env2_attack", "Attack", 0.0, env2_layout)
        self._add_slider("env2_decay", "Decay", 0.5, env2_layout)
        self._add_slider("env2_sustain", "Sustain", 0.0, env2_layout)
        self._add_slider("env2_release", "Release", 0.3, env2_layout)

        # LFO 1
        lfo1_group = self._make_group("LFO 1")
        lfo1_layout = QVBoxLayout(lfo1_group)
        lfo1_layout.setSpacing(4)

        lfo1_row = QHBoxLayout()
        self._lfo1_shape = QComboBox()
        self._lfo1_shape.addItems(["sine", "triangle", "square", "saw", "saw up", "random"])
        lfo1_row.addWidget(QLabel("Shape:"))
        lfo1_row.addWidget(self._lfo1_shape)
        lfo1_row.addStretch()
        lfo1_layout.addLayout(lfo1_row)
        self._add_slider("lfo1_rate", "Rate", 0.3, lfo1_layout)

        # Volume / Pan
        mix_group = self._make_group("Volume / Pan / FX")
        mix_layout = QVBoxLayout(mix_group)
        mix_layout.setSpacing(4)
        self._add_slider("volume", "Volume", 1.0, mix_layout)
        self._add_slider("pan", "Pan", 0.5, mix_layout)
        self._add_slider("portamento", "Portamento", 0.0, mix_layout)

        for group in [osc1_group, osc2_group, filter_group,
                      env1_group, env2_group, lfo1_group, mix_group]:
            layout.addWidget(group)
        layout.addStretch()

    def _make_group(self, title: str) -> QGroupBox:
        return QGroupBox(title)

    def _add_slider(self, key: str, label: str, default: float, parent_layout):
        s = ParamSlider(label, default)
        parent_layout.addWidget(s)
        self._param_sliders[key] = s

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    # ── Public API ────────────────────────────────────────────────────────
    def update_index(self, index: SDCardIndex):
        self._index = index
        self._synths = index.synths
        self._populate_table(self._synths)
        self._status.setText(f"{len(self._synths)} Synths")

    def _populate_table(self, synths: list[Synth]):
        self._table.setRowCount(0)
        for s in synths:
            row = self._table.rowCount()
            self._table.insertRow(row)
            name_item = QTableWidgetItem(s.name)
            name_item.setData(Qt.UserRole, s)
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, QTableWidgetItem(s.osc1_type))
            self._table.setItem(row, 2, QTableWidgetItem(s.filter_type))

    def _filter(self):
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            self._table.setRowHidden(row, text != "" and item and text not in item.text().lower())

    def _selected_synth(self) -> Optional[Synth]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _on_synth_selected(self):
        synth = self._selected_synth()
        has = synth is not None
        self._rand_btn.setEnabled(has)
        self._save_btn.setEnabled(has)
        self._rename_btn.setEnabled(has)
        self._dupe_btn.setEnabled(has)
        self._export_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        if synth:
            self._current_synth = synth
            self._load_params(synth)

    def _load_params(self, synth: Synth):
        self._synth_title.setText(f"🎹  {synth.name}")
        idx = self._osc1_type.findText(synth.osc1_type)
        if idx >= 0:
            self._osc1_type.setCurrentIndex(idx)
        idx = self._osc2_type.findText(synth.osc2_type)
        if idx >= 0:
            self._osc2_type.setCurrentIndex(idx)

        # Nutzt _parse_xml_robust für Deluge-Firmware-Quirks
        try:
            from ..core.xml_parser import _parse_xml_robust
            root = _parse_xml_robust(synth.file_path)
            if root is None:
                self._status.setText(f"XML konnte nicht geladen werden: {synth.name}")
                return

            def get_val(path: str, default: float = 0.5) -> float:
                el = root.find(path)
                if el is not None:
                    text = el.text or el.get("value", "")
                    if text.startswith("0x") or text.startswith("0X"):
                        return hex_to_norm(text)
                return default

            mappings = {
                "osc1_volume": ".//osc1/volume",
                "osc1_transpose": ".//osc1/transpose",
                "osc1_pulsewidth": ".//osc1/pulseWidth",
                "osc2_volume": ".//osc2/volume",
                "osc2_transpose": ".//osc2/transpose",
                "filter_cutoff": ".//lpf/frequency",
                "filter_resonance": ".//lpf/resonance",
                "filter_morph": ".//lpf/morph",
                "env1_attack": ".//envelope1/attack",
                "env1_decay": ".//envelope1/decay",
                "env1_sustain": ".//envelope1/sustain",
                "env1_release": ".//envelope1/release",
                "env2_attack": ".//envelope2/attack",
                "env2_decay": ".//envelope2/decay",
                "env2_sustain": ".//envelope2/sustain",
                "env2_release": ".//envelope2/release",
                "lfo1_rate": ".//lfo1/rate",
                "volume": ".//volume",
                "pan": ".//pan",
                "portamento": ".//portamento",
            }
            for key, xml_path in mappings.items():
                if key in self._param_sliders:
                    val = get_val(xml_path, 0.5)
                    self._param_sliders[key].set_value(val)

            ft_el = root.find(".//lpf")
            if ft_el is not None:
                mode = ft_el.get("mode", "0")
                ft_map = {"0": "lpf12", "1": "lpf24", "2": "hpf12", "3": "hpf24"}
                ft_text = ft_map.get(mode, "lpf12")
                idx = self._filter_type.findText(ft_text)
                if idx >= 0:
                    self._filter_type.setCurrentIndex(idx)

            lfo_el = root.find(".//lfo1/shape")
            if lfo_el is not None and lfo_el.text:
                idx = self._lfo1_shape.findText(lfo_el.text.strip())
                if idx >= 0:
                    self._lfo1_shape.setCurrentIndex(idx)

        except Exception as e:
            self._status.setText(f"XML lesen fehlgeschlagen: {e}")

    def _save_params(self):
        if not self._current_synth:
            return

        mappings: dict[str, str] = {
            "osc1_volume":     ".//osc1/volume",
            "osc1_transpose":  ".//osc1/transpose",
            "osc1_pulsewidth": ".//osc1/pulseWidth",
            "osc2_volume":     ".//osc2/volume",
            "osc2_transpose":  ".//osc2/transpose",
            "filter_cutoff":   ".//lpf/frequency",
            "filter_resonance":".//lpf/resonance",
            "filter_morph":    ".//lpf/morph",
            "env1_attack":     ".//envelope1/attack",
            "env1_decay":      ".//envelope1/decay",
            "env1_sustain":    ".//envelope1/sustain",
            "env1_release":    ".//envelope1/release",
            "env2_attack":     ".//envelope2/attack",
            "env2_decay":      ".//envelope2/decay",
            "env2_sustain":    ".//envelope2/sustain",
            "env2_release":    ".//envelope2/release",
            "lfo1_rate":       ".//lfo1/rate",
            "volume":          ".//volume",
            "pan":             ".//pan",
            "portamento":      ".//portamento",
        }

        try:
            from ..core.file_ops import _read_xml, _write_xml
            from ..core.xml_parser import _parse_xml_robust

            # Nutzt _parse_xml_robust statt ET.parse — unterstützt alle Deluge-Firmware-Quirks
            root = _parse_xml_robust(self._current_synth.file_path)
            if root is None:
                QMessageBox.warning(self, "Fehler", "XML konnte nicht gelesen werden.")
                return

            replacements: list[tuple[str, str]] = []

            for key, xpath in mappings.items():
                if key not in self._param_sliders:
                    continue
                el = root.find(xpath)
                if el is None:
                    continue
                old_hex = (el.text or "").strip()
                if not (old_hex.lower().startswith("0x")):
                    continue
                new_val = self._param_sliders[key]._slider.value() / 1000.0
                new_hex = norm_to_hex(new_val)
                if old_hex != new_hex:
                    replacements.append((old_hex, new_hex))

            if not replacements:
                self._status.setText(f"ℹ  Keine Änderungen: {self._current_synth.name}")
                return

            text, enc = _read_xml(self._current_synth.file_path)
            for old_hex, new_hex in replacements:
                text = text.replace(old_hex, new_hex, 1)

            _write_xml(self._current_synth.file_path, text, enc)
            self._status.setText(f"✅  Gespeichert: {self._current_synth.name}")

        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Speichern fehlgeschlagen: {e}")

    def _randomize(self):
        if not self._current_synth or not self._index:
            return
        new_name, ok = QInputDialog.getText(
            self, "Randomizer", "Name für den zufälligen Synth:",
            text=f"{self._current_synth.name}_rnd"
        )
        if not ok or not new_name.strip():
            return

        new_path = self._current_synth.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return

        try:
            from ..core.file_ops import _read_xml, _write_xml
            text, enc = _read_xml(self._current_synth.file_path)

            rand_tags = [
                "frequency", "resonance", "attack", "decay", "sustain", "release",
                "rate", "pan"
            ]
            for tag in rand_tags:
                rand_val = rand_hex(0.05, 0.95)
                text = re.sub(
                    rf'(<{tag}>)\s*0x[0-9A-Fa-f]+\s*(</{tag}>)',
                    rf'\g<1>{rand_val}\2',
                    text
                )

            osc_types = ["square", "sine", "saw", "triangle"]
            new_type = random.choice(osc_types)
            text = re.sub(r'(<type>)(square|sine|saw|triangle)(</type>)',
                         rf'\g<1>{new_type}\3', text, count=1)

            _write_xml(new_path, text, enc)
            self._status.setText(f"✅  Zufälliger Synth erstellt: {new_name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _rename_selected(self):
        synth = self._selected_synth()
        if not synth:
            return
        new_name, ok = QInputDialog.getText(self, "Umbenennen", "Neuer Name:", text=synth.name)
        if not ok or not new_name.strip():
            return
        new_path = synth.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        try:
            synth.file_path.rename(new_path)
            self._status.setText(f"✅  Umbenannt → {new_name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _duplicate_selected(self):
        synth = self._selected_synth()
        if not synth:
            return
        new_name, ok = QInputDialog.getText(self, "Duplizieren", "Name:", text=f"{synth.name}_copy")
        if not ok or not new_name.strip():
            return
        new_path = synth.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        try:
            shutil.copy2(str(synth.file_path), str(new_path))
            self._status.setText(f"✅  Dupliziert → {new_name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_selected(self):
        synth = self._selected_synth()
        if not synth:
            return
        reply = QMessageBox.question(self, "Löschen", f"'{synth.name}' löschen?", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            synth.file_path.unlink()
            self._status.setText(f"🗑  Gelöscht: {synth.name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _export_selected(self):
        synth = self._selected_synth()
        if not synth or not self._index:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Synth exportieren", f"{synth.name}.XML", "XML (*.XML *.xml)"
        )
        if not dest:
            return
        try:
            shutil.copy2(str(synth.file_path), dest)
            self._status.setText(f"✅  Exportiert: {Path(dest).name}")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _import_synth(self):
        if not self._index:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Synth importieren", "", "XML Files (*.xml *.XML)")
        if not path:
            return
        dest = self._index.root_path / "SYNTHS" / Path(path).name
        if dest.exists():
            reply = QMessageBox.question(self, "Überschreiben?", f"'{dest.name}' existiert. Überschreiben?", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        try:
            shutil.copy2(path, str(dest))
            self._status.setText(f"✅  Importiert: {dest.name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
