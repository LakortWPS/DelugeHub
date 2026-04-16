"""
DelugeHub — PendingPanel Widget
Zeigt ausstehende Änderungen eines Moduls an.
Erscheint nur wenn Änderungen vorhanden sind.
"""
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog, QMessageBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal

from ..core.staging import StagingStore


class PendingPanel(QFrame):
    """
    Kleines Panel am unteren Rand eines Moduls.
    Zeigt die pending Changes des jeweiligen Moduls.
    Wird automatisch ein-/ausgeblendet.
    """
    changes_applied = Signal()    # nach erfolgreichem Speichern
    changes_discarded = Signal()  # nach Verwerfen

    def __init__(self, module_name: str, staging: StagingStore,
                 rescan_fn: Optional[Callable] = None):
        super().__init__()
        self._module = module_name
        self._staging = staging
        self._rescan_fn = rescan_fn
        self.setObjectName("PendingPanel")
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame#PendingPanel { background: #1A2A1A; border: 1px solid #2ECC71;"
            " border-radius: 6px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("⏳ 0 ausstehende Änderungen")
        self._title.setStyleSheet("color: #2ECC71; font-weight: bold;")

        self._save_btn = QPushButton("💾 Speichern")
        self._save_btn.setFixedHeight(28)
        self._save_btn.clicked.connect(self._on_save)

        self._discard_btn = QPushButton("↩ Verwerfen")
        self._discard_btn.setObjectName("SecondaryButton")
        self._discard_btn.setFixedHeight(28)
        self._discard_btn.clicked.connect(self._on_discard)

        header.addWidget(self._title)
        header.addStretch()
        header.addWidget(self._save_btn)
        header.addWidget(self._discard_btn)
        layout.addLayout(header)

        # Liste
        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        self._list.setStyleSheet("background: transparent; border: none; color: #CCCCCC;")
        layout.addWidget(self._list)

    def refresh(self):
        """Aktualisiert die Anzeige. Blendet Panel aus wenn keine Änderungen."""
        changes = self._staging.get_for_module(self._module)
        self._list.clear()

        for c in changes:
            item = QListWidgetItem(f"  • {c.display_name}")
            item.setData(Qt.UserRole, c.file_path)
            self._list.addItem(item)

        count = len(changes)
        self._title.setText(f"⏳ {count} ausstehende Änderung{'en' if count != 1 else ''}")
        self.setVisible(count > 0)

    def _on_save(self):
        from PySide6.QtWidgets import QDialog, QRadioButton, QDialogButtonBox

        # Einfacher Dialog: Original überschreiben oder Ordner wählen
        reply = QMessageBox(self)
        reply.setWindowTitle("Änderungen speichern")
        reply.setText("Wo sollen die Änderungen gespeichert werden?")
        btn_original = reply.addButton("Original überschreiben", QMessageBox.AcceptRole)
        btn_export   = reply.addButton("In anderen Ordner exportieren…", QMessageBox.ActionRole)
        reply.addButton("Abbrechen", QMessageBox.RejectRole)
        reply.exec()

        dest_root = None
        if reply.clickedButton() == btn_export:
            folder = QFileDialog.getExistingDirectory(self, "Zielordner wählen", "")
            if not folder:
                return
            dest_root = Path(folder)
        elif reply.clickedButton() != btn_original:
            return

        success, failed = self._staging.apply_for_module(self._module, dest_root)
        self.refresh()
        self.changes_applied.emit()
        if self._rescan_fn:
            self._rescan_fn()

        msg = f"✅ {success} Änderungen gespeichert."
        if failed:
            msg += f"  ⚠ {failed} Fehler."
        QMessageBox.information(self, "Gespeichert", msg)

    def _on_discard(self):
        changes = self._staging.get_for_module(self._module)
        if not changes:
            return
        reply = QMessageBox.question(
            self, "Verwerfen",
            f"{len(changes)} Änderung(en) verwerfen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._staging.clear_module(self._module)
            self.refresh()
            self.changes_discarded.emit()
