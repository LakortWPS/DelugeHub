"""
DelugeHub — PendingPanel Widget
Zeigt ausstehende Änderungen eines Moduls an.
Erscheint nur wenn Änderungen vorhanden sind.
"""
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QDialog, QPlainTextEdit,
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
        self._history = None
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
        self._list.itemDoubleClicked.connect(self._show_xml_diff)
        layout.addWidget(self._list)

    def set_history(self, history) -> None:
        """Same ActionHistory main_window passes to the owning module."""
        self._history = history

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
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QVBoxLayout, QLabel as _QLabel
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Änderungen speichern")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl = _QLabel("Wo sollen die Änderungen gespeichert werden?")
        layout.addWidget(lbl)

        btn_box = QDialogButtonBox()
        btn_original = btn_box.addButton("Original überschreiben", QDialogButtonBox.AcceptRole)
        btn_export   = btn_box.addButton("In anderen Ordner exportieren…", QDialogButtonBox.ActionRole)
        btn_cancel   = btn_box.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        btn_box.rejected.connect(dlg.reject)
        btn_original.clicked.connect(dlg.accept)
        btn_export.clicked.connect(dlg.accept)
        layout.addWidget(btn_box)

        clicked = [None]

        def _track(b):
            clicked[0] = b

        btn_original.clicked.connect(lambda: _track("original"))
        btn_export.clicked.connect(lambda: _track("export"))

        dlg.exec()

        dest_root = None
        if clicked[0] == "export":
            folder = QFileDialog.getExistingDirectory(self, "Zielordner wählen", "")
            if not folder:
                return
            dest_root = Path(folder)
        elif clicked[0] != "original":
            return

        report = self._staging.apply_for_module(self._module, dest_root)
        if dest_root is None and self._history is not None:
            self._push_delete_undo(report.trashed)
        self.refresh()
        self.changes_applied.emit()
        if self._rescan_fn:
            self._rescan_fn()

        msg = f"✅ {report.success} Änderungen gespeichert."
        if report.failures:
            shown = "\n".join(report.failures[:8])
            extra = ""
            if len(report.failures) > 8:
                extra = f"\n… und {len(report.failures) - 8} weitere"
            msg += f"\n\nNicht gespeichert:\n{shown}{extra}"
        QMessageBox.information(self, "Gespeichert", msg)

    def _push_delete_undo(self, trashed) -> None:
        from ..core.history import Action, move_to_trash, restore_from_trash
        for original, trash in trashed:
            state = [trash]
            self._history.push(Action(
                description=f"Gelöscht: {original.name}",
                undo_fn=lambda st=state, op=original: restore_from_trash(st[0], op),
                redo_fn=lambda st=state, op=original: st.__setitem__(0, move_to_trash(op)),
            ))

    def _show_xml_diff(self, item: QListWidgetItem) -> None:
        """Line diff of a staged XML edit against the file currently on disk."""
        import difflib
        from ..core.file_ops import _read_xml
        from ..core.staging import ChangeType

        path = item.data(Qt.UserRole)
        change = next(
            (c for c in self._staging.get_for_module(self._module) if c.file_path == path),
            None,
        )
        if change is None or change.change_type != ChangeType.XML_EDIT or not change.new_content:
            return
        try:
            old, _enc = _read_xml(path)
        except Exception:
            old = ""
        diff_lines = difflib.unified_diff(
            old.splitlines(),
            change.new_content.splitlines(),
            fromfile="bisher",
            tofile="vorgemerkt",
            lineterm="",
        )
        text = "\n".join(diff_lines) or "(kein Textunterschied)"

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Änderung — {path.name}")
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        layout.addWidget(view)
        dialog.resize(720, 480)
        dialog.exec()

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
