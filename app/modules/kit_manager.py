"""
DelugeHub — Kit Manager Module
Browse kits, view pad assignments, re-assign samples, normalize and cap volumes.
"""
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QLineEdit, QSplitter, QGridLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex, Kit
from ..core.staging import StagingStore, PendingChange, ChangeType


class PadWidget(QFrame):
    """A single pad cell in the kit grid."""
    clicked = Signal(int)

    def __init__(self, pad_number: int):
        super().__init__()
        self._pad_number = pad_number
        self.setObjectName("Card")
        self.setFixedSize(88, 72)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        num_lbl = QLabel(str(pad_number + 1))
        num_lbl.setAlignment(Qt.AlignRight)
        num_lbl.setStyleSheet("color: #555577; font-size: 10px;")

        self._name_lbl = QLabel("—")
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setStyleSheet("font-size: 10px; color: #AAAAAA;")

        layout.addWidget(num_lbl)
        layout.addWidget(self._name_lbl, 1)

    def set_sample(self, name: str, has_file: bool = True):
        short = name[:10] + "…" if len(name) > 10 else name
        self._name_lbl.setText(short)
        self._name_lbl.setToolTip(name)
        if has_file:
            self.setObjectName("CardAccent")
        else:
            self.setObjectName("CardError")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self._pad_number)
        super().mousePressEvent(event)


class KitManagerModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._kits: list[Kit] = []
        self._current_kit: Optional[Kit] = None
        self._pads: list[PadWidget] = []
        self._history = None
        self._staging: Optional[StagingStore] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._lbl("🥁  Kit Manager", "PageTitle"))
        col.addWidget(self._lbl("Kits durchsuchen, Pad-Zuweisungen bearbeiten, Volumes normalisieren", "PageSubtitle"))
        hdr.addLayout(col)
        hdr.addStretch()

        root.addLayout(hdr)
        root.addSpacing(14)

        # Toolbar
        tb = QFrame()
        tb.setObjectName("Card")
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Kits suchen…")
        self._search.textChanged.connect(self._filter)

        self._rename_btn = QPushButton("✏ Umbenennen")
        self._rename_btn.setObjectName("SecondaryButton")
        self._rename_btn.clicked.connect(self._rename_selected)
        self._rename_btn.setEnabled(False)

        self._dupe_btn = QPushButton("📋 Duplizieren")
        self._dupe_btn.setObjectName("SecondaryButton")
        self._dupe_btn.clicked.connect(self._duplicate_selected)
        self._dupe_btn.setEnabled(False)

        self._norm_btn = QPushButton("🔊 Normalisieren")
        self._norm_btn.setObjectName("SecondaryButton")
        self._norm_btn.setToolTip(
            "WAV-Dateien analysieren (RMS) und Pad-Volumes angleichen,\n"
            "sodass alle Pads gleich laut klingen."
        )
        self._norm_btn.clicked.connect(self._normalize_volumes)
        self._norm_btn.setEnabled(False)

        self._cap_master_btn = QPushButton("⬇ Master")
        self._cap_master_btn.setObjectName("SecondaryButton")
        self._cap_master_btn.setToolTip(
            "Kit-Master-Volume auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt, Werte darunter bleiben unverändert."
        )
        self._cap_master_btn.clicked.connect(self._cap_kit_master)
        self._cap_master_btn.setEnabled(False)

        self._cap_pads_btn = QPushButton("⬇ Pads")
        self._cap_pads_btn.setObjectName("SecondaryButton")
        self._cap_pads_btn.setToolTip(
            "Alle Pad-Volumes auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt, Werte darunter bleiben unverändert."
        )
        self._cap_pads_btn.clicked.connect(self._cap_pad_volumes)
        self._cap_pads_btn.setEnabled(False)

        self._import_btn = QPushButton("⬇ Importieren")
        self._import_btn.setObjectName("SecondaryButton")
        self._import_btn.setToolTip("Kit-XML aus Dateisystem importieren")
        self._import_btn.clicked.connect(self._import_kit)

        self._delete_btn = QPushButton("🗑")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setToolTip("Ausgewähltes Kit löschen")
        self._delete_btn.setFixedWidth(34)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)

        tb_layout.addWidget(QLabel("🔎"))
        tb_layout.addWidget(self._search, 1)
        tb_layout.addWidget(self._rename_btn)
        tb_layout.addWidget(self._dupe_btn)
        tb_layout.addWidget(self._norm_btn)
        tb_layout.addWidget(self._cap_master_btn)
        tb_layout.addWidget(self._cap_pads_btn)
        tb_layout.addWidget(self._import_btn)
        tb_layout.addWidget(self._delete_btn)
        root.addWidget(tb)
        root.addSpacing(8)

        # Splitter: kit list | pad grid + detail
        splitter = QSplitter(Qt.Horizontal)

        # Kit list table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Kit Name", "Pads", "Fehlend"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.Interactive)
        hv.setSectionResizeMode(2, QHeaderView.Interactive)
        self._table.setColumnWidth(1, 55)
        self._table.setColumnWidth(2, 80)
        self._table.setMinimumWidth(240)
        self._table.itemSelectionChanged.connect(self._on_kit_selected)
        splitter.addWidget(self._table)

        # Right panel: pad grid + pad detail
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(12)

        # Pad grid (4x4 = 16 pads)
        grid_frame = QFrame()
        grid_frame.setObjectName("Card")
        grid_layout_outer = QVBoxLayout(grid_frame)
        grid_layout_outer.setContentsMargins(12, 12, 12, 12)

        self._kit_title = QLabel("Kein Kit ausgewählt")
        self._kit_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        grid_layout_outer.addWidget(self._kit_title)

        grid_container = QWidget()
        self._grid_layout = QGridLayout(grid_container)
        self._grid_layout.setSpacing(6)

        for i in range(16):
            pad = PadWidget(i)
            pad.clicked.connect(self._on_pad_click)
            self._pads.append(pad)
            row, col = divmod(i, 4)
            grid_row = 3 - row
            self._grid_layout.addWidget(pad, grid_row, col)

        grid_layout_outer.addWidget(grid_container)
        right_layout.addWidget(grid_frame)

        # Pad detail
        self._pad_detail = QFrame()
        self._pad_detail.setObjectName("Card")
        pd_layout = QVBoxLayout(self._pad_detail)
        pd_layout.setContentsMargins(12, 12, 12, 12)
        pd_layout.setSpacing(6)

        pd_layout.addWidget(self._lbl("Pad Details", "SectionTitle"))
        self._pad_info = QLabel("Klicke auf ein Pad")
        self._pad_info.setStyleSheet("color: #888888; font-size: 12px;")
        self._pad_info.setWordWrap(True)

        self._reassign_btn = QPushButton("🎵  Sample neu zuweisen")
        self._reassign_btn.setEnabled(False)
        self._reassign_btn.clicked.connect(self._reassign_pad)

        pd_layout.addWidget(self._pad_info)
        pd_layout.addWidget(self._reassign_btn)

        right_layout.addWidget(self._pad_detail)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self._status = QLabel("—")
        self._status.setObjectName("StatusLabel")
        root.addSpacing(6)
        root.addWidget(self._status)

        from ..widgets.pending_panel import PendingPanel
        self._pending_panel = PendingPanel(
            "kit_manager", StagingStore(),
            rescan_fn=self.request_rescan.emit
        )
        root.addWidget(self._pending_panel)

        self._selected_pad: Optional[int] = None

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    def set_history(self, history):
        self._history = history

    def set_staging(self, staging: StagingStore):
        self._staging = staging
        if hasattr(self, '_pending_panel'):
            self._pending_panel._staging = staging
            self._pending_panel.refresh()

    def update_index(self, index: SDCardIndex):
        self._index = index
        self._kits = index.kits
        self._populate_table(self._kits)
        self._status.setText(f"{len(self._kits)} Kits")

    def _populate_table(self, kits: list[Kit]):
        self._table.setRowCount(0)
        for k in kits:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(k.name)
            name_item.setData(Qt.UserRole, k)
            self._table.setItem(row, 0, name_item)

            self._table.setItem(row, 1, QTableWidgetItem(str(k.pad_count)))

            missing_item = QTableWidgetItem(str(len(k.missing_samples)))
            if k.has_missing_samples:
                missing_item.setForeground(QColor("#E74C3C"))
            else:
                missing_item.setForeground(QColor("#2ECC71"))
            self._table.setItem(row, 2, missing_item)

    def _filter(self):
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            self._table.setRowHidden(row, text != "" and item and text not in item.text().lower())

    def _selected_kit(self) -> Optional[Kit]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _on_kit_selected(self):
        kit = self._selected_kit()
        has = kit is not None
        self._rename_btn.setEnabled(has)
        self._dupe_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        self._norm_btn.setEnabled(has)
        self._cap_master_btn.setEnabled(has)
        self._cap_pads_btn.setEnabled(has)
        if kit:
            self._current_kit = kit
            self._show_kit_pads(kit)

    def _show_kit_pads(self, kit: Kit):
        self._kit_title.setText(f"🥁  {kit.name}")
        for pad in self._pads:
            pad.set_sample("—", True)
            pad.setObjectName("Card")
            pad.style().unpolish(pad)
            pad.style().polish(pad)

        for i, ref in enumerate(kit.sample_refs[:16]):
            if i < len(self._pads):
                name = Path(ref.path.replace("\\", "/")).stem
                self._pads[i].set_sample(name, ref.exists)

    def _on_pad_click(self, pad_index: int):
        self._selected_pad = pad_index
        if not self._current_kit:
            return

        refs = self._current_kit.sample_refs
        if pad_index < len(refs):
            ref = refs[pad_index]
            status = "✅ Vorhanden" if ref.exists else "❌ Fehlt"
            self._pad_info.setText(
                f"Pad {pad_index + 1}\n"
                f"Sample: {ref.path.split('/')[-1]}\n"
                f"Pfad: {ref.path}\n"
                f"Status: {status}"
            )
        else:
            self._pad_info.setText(f"Pad {pad_index + 1}\n(Kein Sample zugewiesen)")
        self._reassign_btn.setEnabled(True)

    def _reassign_pad(self):
        if self._selected_pad is None or not self._current_kit or not self._index:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Sample für Pad {self._selected_pad + 1} wählen",
            str(self._index.root_path / "SAMPLES"),
            "Audio Files (*.wav *.aif *.aiff);;All Files (*)"
        )
        if not file_path:
            return

        new_path = Path(file_path)
        try:
            new_rel = str(new_path.relative_to(self._index.root_path)).replace("\\", "/")
        except ValueError:
            QMessageBox.warning(self, "Fehler", "Datei muss auf der SD-Card liegen.")
            return

        kit = self._current_kit
        refs = kit.sample_refs
        if self._selected_pad < len(refs):
            old_rel = refs[self._selected_pad].path
            from ..core.file_ops import update_xml_path
            if update_xml_path(kit.file_path, old_rel, new_rel):
                self._status.setText(f"✅  Pad {self._selected_pad + 1} → {new_path.name}")
                self.request_rescan.emit()
        else:
            QMessageBox.information(self, "Info", "XML-Schreiben für neue Pads noch nicht implementiert.")

    def _rename_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        new_name, ok = QInputDialog.getText(self, "Kit umbenennen", "Neuer Name:", text=kit.name)
        if not ok or not new_name.strip():
            return
        new_path = kit.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.RENAME,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_name=f"{new_name.strip()}.XML",
            ))
            self._status.setText(f"⏳  Umbenennen vorgemerkt: {kit.name} → {new_name}")
            self._pending_panel.refresh()
        else:
            try:
                kit.file_path.rename(new_path)
                self._status.setText(f"✅  Umbenannt → {new_name}")
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _duplicate_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        new_name, ok = QInputDialog.getText(self, "Kit duplizieren", "Name:", text=f"{kit.name}_copy")
        if not ok or not new_name.strip():
            return
        new_path = kit.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        try:
            shutil.copy2(str(kit.file_path), str(new_path))
            self._status.setText(f"✅  Dupliziert → {new_name}")
            self.request_rescan.emit()
            if self._history:
                from ..core.history import Action
                import shutil as _shutil
                _src, _dst = kit.file_path, new_path
                self._history.push(Action(
                    description=f"Kit dupliziert: {new_name}",
                    undo_fn=lambda p=_dst: p.unlink() if p.exists() else None,
                    redo_fn=lambda s=_src, d=_dst: _shutil.copy2(str(s), str(d)),
                ))
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        reply = QMessageBox.question(
            self, "Löschen",
            f"'{kit.name}' löschen?\n(Erst gespeichert wenn du 'Speichern' drückst)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.DELETE,
                file_path=kit.file_path,
                source_module="kit_manager",
            ))
            self._status.setText(f"⏳  Zum Löschen vorgemerkt: {kit.name}")
            self._pending_panel.refresh()
        else:
            try:
                kit.file_path.unlink()
                self._status.setText(f"🗑  Gelöscht: {kit.name}")
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _normalize_volumes(self):
        kit = self._selected_kit()
        if not kit or not self._index:
            return

        reply = QMessageBox.question(
            self, "Volumes normalisieren (Audio-Analyse)",
            f"Pad-Volumes in '{kit.name}' per RMS-Analyse angleichen?\n\n"
            "• Jede WAV-Datei wird analysiert\n"
            "• Der lauteste Pad behält sein Volume\n"
            "• Leisere Pads werden proportional angehoben\n"
            "• Pads ohne vorhandenes Sample werden übersprungen",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        sound_sources = root.find("soundSources")
        if sound_sources is None:
            QMessageBox.warning(self, "Fehler", "Keine <soundSources> in diesem Kit gefunden.")
            return

        pads = []
        for sound in sound_sources.findall("sound"):
            osc1 = sound.find("osc1")
            if osc1 is None:
                continue

            file_name = osc1.get("fileName", "").strip()
            if not file_name:
                fname_elem = osc1.find("fileName")
                if fname_elem is not None:
                    file_name = (fname_elem.text or "").strip()

            if not file_name:
                continue

            rel = file_name.replace("\\", "/").lstrip("/")
            abs_path = self._index.root_path / rel
            if not abs_path.exists():
                continue

            dp = sound.find("defaultParams")
            if dp is None:
                continue

            vol_attr = dp.get("volume", "").strip()
            if vol_attr:
                vol_format = "attr"
                current_vol = vol_attr
            else:
                vol_elem = dp.find("volume")
                if vol_elem is None or not (vol_elem.text or "").strip():
                    continue
                vol_format = "elem"
                current_vol = vol_elem.text.strip()

            pads.append({
                "abs_path": abs_path,
                "current_vol": current_vol,
                "vol_format": vol_format,
                "rms": None,
                "new_vol": None,
            })

        if not pads:
            QMessageBox.information(
                self, "Info",
                "Keine Pads mit vorhandenen Samples und Volume-Werten gefunden."
            )
            return

        try:
            import soundfile as sf
            import numpy as np
        except ImportError:
            QMessageBox.warning(
                self, "Fehlende Bibliothek",
                "soundfile ist nicht installiert.\n\n"
                "Bitte im Terminal ausführen:\n"
                "  pip install soundfile"
            )
            return

        for pad in pads:
            try:
                data, _ = sf.read(str(pad["abs_path"]), dtype="float32", always_2d=True)
                mono = np.mean(data, axis=1)
                rms = float(np.sqrt(np.mean(mono ** 2)))
                pad["rms"] = rms if rms > 1e-8 else None
            except Exception:
                pad["rms"] = None

        valid_pads = [p for p in pads if p["rms"] is not None]
        if not valid_pads:
            QMessageBox.warning(
                self, "Fehler",
                "Konnte keine Sample-Dateien analysieren.\n"
                "Prüfe ob die WAV/AIFF-Dateien lesbar sind."
            )
            return

        def vol_to_amp(hex_str: str) -> float:
            v = int(hex_str, 16)
            if v >= 0x80000000:
                v -= 0x100000000
            return (v + 2_147_483_648) / 4_294_967_295

        def amp_to_vol(amp: float) -> str:
            amp = max(0.0, min(1.0, amp))
            v = int(amp * 4_294_967_295) - 2_147_483_648
            return f"0x{v & 0xFFFFFFFF:08X}"

        target_rms = max(p["rms"] for p in valid_pads)
        for pad in valid_pads:
            gain = target_rms / pad["rms"]
            new_amp = min(vol_to_amp(pad["current_vol"]) * gain, 1.0)
            pad["new_vol"] = amp_to_vol(new_amp)

        import re
        text, enc = _read_xml(kit.file_path)

        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            QMessageBox.warning(self, "Fehler", "<soundSources>-Block nicht im XML gefunden.")
            return

        sources_block = sources_match.group(1)
        changed = 0
        for pad in valid_pads:
            if pad["new_vol"] and pad["new_vol"] != pad["current_vol"]:
                if pad["vol_format"] == "attr":
                    old_tag = f'volume="{pad["current_vol"]}"'
                    new_tag = f'volume="{pad["new_vol"]}"'
                else:
                    old_tag = f'<volume>{pad["current_vol"]}</volume>'
                    new_tag = f'<volume>{pad["new_vol"]}</volume>'

                new_block = sources_block.replace(old_tag, new_tag, 1)
                if new_block != sources_block:
                    sources_block = new_block
                    changed += 1

        if changed == 0:
            self._status.setText("ℹ  Keine Änderungen nötig — alle Pads bereits auf gleicher Lautstärke.")
            return

        start, end = sources_match.start(1), sources_match.end(1)
        new_text = text[:start] + sources_block + text[end:]

        skipped = len(pads) - len(valid_pads)
        skip_note = f" ({skipped} ohne Sample übersprungen)" if skipped else ""
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: {changed} Pad-Volume(s) normalisiert{skip_note}.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  {changed} Pad-Volume(s) normalisiert (RMS-Analyse){skip_note}."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _import_kit(self):
        if not self._index:
            QMessageBox.warning(self, "Kein SD-Ordner", "Bitte zuerst einen SD-Card-Ordner laden.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Kit importieren", "", "XML Files (*.xml *.XML)")
        if not path:
            return
        dest = self._index.root_path / "KITS" / Path(path).name
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

    # ── Volume-Cap Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _vol_to_display(hex_str: str) -> float:
        """Deluge hex volume string → display value 0–50."""
        v = int(hex_str, 16)
        if v >= 0x80000000:
            v -= 0x100000000           # unsigned → signed
        return ((v + 2_147_483_648) / 4_294_967_295) * 50

    @staticmethod
    def _display_to_vol(display: float) -> str:
        """Display value 0–50 → Deluge hex volume string."""
        amp = max(0.0, min(1.0, display / 50.0))
        v = int(amp * 4_294_967_295) - 2_147_483_648
        return f"0x{v & 0xFFFFFFFF:08X}"

    def _cap_kit_master(self):
        kit = self._selected_kit()
        if not kit:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Kit-Master begrenzen",
            "Maximale Lautstärke für Kit-Master (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        dp = root.find("defaultParams")
        if dp is None:
            self._status.setText("ℹ  Kein <defaultParams> im Kit-Root gefunden.")
            return

        vol_str = dp.get("volume", "").strip()
        vol_format = "attr"
        if not vol_str:
            vol_elem = dp.find("volume")
            if vol_elem is not None:
                vol_str = (vol_elem.text or "").strip()
                vol_format = "elem"

        if not vol_str:
            self._status.setText("ℹ  Kein Volume-Wert im Kit-Master gefunden.")
            return

        current_display = self._vol_to_display(vol_str)
        if current_display <= threshold:
            self._status.setText(
                f"ℹ  Kit-Master liegt bei {current_display:.1f}/50 — kein Cap nötig."
            )
            return

        new_hex = self._display_to_vol(threshold)
        text, enc = _read_xml(kit.file_path)

        sources_pos = text.find('<soundSources>')
        pre_block  = text[:sources_pos] if sources_pos >= 0 else text
        post_block = text[sources_pos:] if sources_pos >= 0 else ""

        if vol_format == "attr":
            old_tag, new_tag = f'volume="{vol_str}"', f'volume="{new_hex}"'
        else:
            old_tag = f'<volume>{vol_str}</volume>'
            new_tag = f'<volume>{new_hex}</volume>'

        new_pre = pre_block.replace(old_tag, new_tag, 1)
        if new_pre == pre_block:
            self._status.setText("ℹ  Volume-Wert konnte nicht im XML gefunden werden.")
            return

        new_text = new_pre + post_block
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: Kit-Master {current_display:.1f}/50 → {threshold}/50.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  Kit-Master: {current_display:.1f}/50 → {threshold}/50 ({new_hex})."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _cap_pad_volumes(self):
        kit = self._selected_kit()
        if not kit:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Pad-Volumes begrenzen",
            "Maximale Lautstärke pro Pad (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        import re
        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        sound_sources = root.find("soundSources")
        if sound_sources is None:
            self._status.setText("ℹ  Keine <soundSources> in diesem Kit gefunden.")
            return

        caps = []
        for sound in sound_sources.findall("sound"):
            dp = sound.find("defaultParams")
            if dp is None:
                continue
            vol_str = dp.get("volume", "").strip()
            vol_format = "attr"
            if not vol_str:
                vol_elem = dp.find("volume")
                if vol_elem is not None:
                    vol_str = (vol_elem.text or "").strip()
                    vol_format = "elem"
            if vol_str and self._vol_to_display(vol_str) > threshold:
                caps.append((vol_str, self._display_to_vol(threshold), vol_format))

        if not caps:
            self._status.setText(
                f"ℹ  Alle Pad-Volumes bereits ≤ {threshold}/50 — kein Cap nötig."
            )
            return

        text, enc = _read_xml(kit.file_path)

        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            QMessageBox.warning(self, "Fehler", "<soundSources>-Block nicht gefunden.")
            return

        sources_block = sources_match.group(1)
        changed = 0
        for current_hex, new_hex, fmt in caps:
            if fmt == "attr":
                old_tag, new_tag = f'volume="{current_hex}"', f'volume="{new_hex}"'
            else:
                old_tag = f'<volume>{current_hex}</volume>'
                new_tag = f'<volume>{new_hex}</volume>'
            new_block = sources_block.replace(old_tag, new_tag, 1)
            if new_block != sources_block:
                sources_block = new_block
                changed += 1

        if changed == 0:
            self._status.setText("ℹ  Keine Änderungen vorgenommen.")
            return

        start, end = sources_match.start(1), sources_match.end(1)
        new_text = text[:start] + sources_block + text[end:]
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: {changed} Pad-Volume(s) auf max. {threshold}/50.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  {changed} Pad-Volume(s) auf max. {threshold}/50 begrenzt."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
