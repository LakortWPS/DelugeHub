"""
DelugeHub — Backup & Sync Module
Create, manage, and restore backups of the Deluge SD card.
"""
from pathlib import Path
from typing import Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QProgressBar, QSplitter, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from ..core.backup import (
    BackupWorker, load_backup_history, list_zip_contents,
    restore_from_backup, BackupEntry
)


class RestoreWorker(QThread):
    """Background thread for restore operations so the UI stays responsive."""
    progress = Signal(int, str)
    finished = Signal(dict)   # {"restored": int, "failed": int}
    error = Signal(str)

    def __init__(self, zip_path: Path, dest_path: Path,
                 files: list | None = None):
        super().__init__()
        self.zip_path = zip_path
        self.dest_path = dest_path
        self.files = files

    def run(self):
        try:
            result = restore_from_backup(
                self.zip_path,
                self.dest_path,
                files=self.files,
                progress_cb=lambda p, m: self.progress.emit(p, m),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class BackupSyncModule(QWidget):
    def __init__(self):
        super().__init__()
        self._sd_root: Optional[Path] = None
        self._backup_dir: Optional[Path] = None
        self._entries: list[BackupEntry] = []
        self._worker = None          # BackupWorker
        self._restore_worker = None  # RestoreWorker
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        # Header + Backup-Ordner inline
        hdr = QHBoxLayout()
        hdr.setSpacing(16)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(self._lbl("💾  Backup & Sync", "PageTitle"))
        col.addWidget(self._lbl("SD-Card sichern, Verlauf verwalten, selektiv wiederherstellen", "PageSubtitle"))
        hdr.addLayout(col)

        hdr.addStretch()

        dir_lbl = QLabel("Backup-Ordner:")
        dir_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        self._backup_dir_edit = QLineEdit()
        self._backup_dir_edit.setPlaceholderText("Ziel-Ordner für Backups…")
        self._backup_dir_edit.setFixedWidth(280)
        self._backup_dir_edit.setFixedHeight(28)
        self._backup_dir_edit.textChanged.connect(self._on_backup_dir_changed)
        dir_browse = QPushButton("…")
        dir_browse.setObjectName("SecondaryButton")
        dir_browse.setFixedSize(28, 28)
        dir_browse.clicked.connect(self._browse_backup_dir)

        hdr.addWidget(dir_lbl)
        hdr.addWidget(self._backup_dir_edit)
        hdr.addWidget(dir_browse)

        root.addLayout(hdr)
        root.addSpacing(10)

        # Main splitter (horizontal: left panel | right panel)
        splitter = QSplitter(Qt.Horizontal)

        # Left panel: vertical splitter (create card | history)
        left_vsplit = QSplitter(Qt.Vertical)
        left_vsplit.setContentsMargins(0, 0, 8, 0)

        # ── Create backup card ─────────────────────────────────────────────
        create_card = QFrame()
        create_card.setObjectName("Card")
        create_layout = QVBoxLayout(create_card)
        create_layout.setContentsMargins(16, 12, 16, 12)
        create_layout.setSpacing(8)

        create_layout.addWidget(self._lbl("BACKUP ERSTELLEN", "SectionTitle"))

        label_row = QHBoxLayout()
        label_row.addWidget(QLabel("Bezeichnung:"))
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText(f"Backup {datetime.now().strftime('%Y-%m-%d')}")
        label_row.addWidget(self._label_edit)
        create_layout.addLayout(label_row)

        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel("Notizen:"))
        self._notes_edit = QLineEdit()
        self._notes_edit.setPlaceholderText("Optional…")
        notes_row.addWidget(self._notes_edit)
        create_layout.addLayout(notes_row)

        self._exclude_samples_cb = QCheckBox("Ohne Samples-Ordner (schneller, kleiner)")
        self._exclude_samples_cb.setToolTip(
            "Sichert nur SONGS, KITS, SYNTHS.\n"
            "Samples sind meist 90% des Speicherplatzes."
        )
        create_layout.addWidget(self._exclude_samples_cb)

        self._create_btn = QPushButton("💾  Backup jetzt erstellen")
        self._create_btn.setObjectName("SuccessButton")
        self._create_btn.setMinimumHeight(40)
        self._create_btn.clicked.connect(self._create_backup)
        create_layout.addWidget(self._create_btn)

        left_vsplit.addWidget(create_card)

        # ── Backup history ─────────────────────────────────────────────────
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(0, 4, 0, 0)
        history_layout.setSpacing(8)

        history_layout.addWidget(self._lbl("BACKUP-VERLAUF", "SectionTitle"))

        refresh_btn = QPushButton("🔄  Verlauf laden")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setMinimumHeight(32)
        refresh_btn.clicked.connect(self._load_history)
        history_layout.addWidget(refresh_btn)

        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(["Datum", "Bezeichnung", "Größe", "Dateien"])
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history_table.verticalHeader().setVisible(False)
        hv = self._history_table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Interactive)
        hv.setSectionResizeMode(1, QHeaderView.Stretch)
        hv.setSectionResizeMode(2, QHeaderView.Interactive)
        hv.setSectionResizeMode(3, QHeaderView.Interactive)
        self._history_table.setColumnWidth(0, 130)
        self._history_table.setColumnWidth(2, 75)
        self._history_table.setColumnWidth(3, 75)
        self._history_table.itemSelectionChanged.connect(self._on_backup_selected)
        history_layout.addWidget(self._history_table, 1)

        # History actions
        hist_btn_row = QHBoxLayout()
        self._restore_btn = QPushButton("♻  Wiederherstellen")
        self._restore_btn.setObjectName("SuccessButton")
        self._restore_btn.setMinimumHeight(32)
        self._restore_btn.setMinimumWidth(140)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._restore_selected)

        self._delete_backup_btn = QPushButton("🗑  Backup löschen")
        self._delete_backup_btn.setObjectName("DangerButton")
        self._delete_backup_btn.setMinimumHeight(32)
        self._delete_backup_btn.setMinimumWidth(130)
        self._delete_backup_btn.setEnabled(False)
        self._delete_backup_btn.clicked.connect(self._delete_selected_backup)

        hist_btn_row.addWidget(self._restore_btn)
        hist_btn_row.addWidget(self._delete_backup_btn)
        hist_btn_row.addStretch()
        history_layout.addLayout(hist_btn_row)

        left_vsplit.addWidget(history_widget)
        left_vsplit.setStretchFactor(0, 0)   # create card: feste Größe
        left_vsplit.setStretchFactor(1, 1)   # history: wächst mit

        splitter.addWidget(left_vsplit)

        # Right: backup contents
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        right_layout.addWidget(self._lbl("BACKUP INHALT", "SectionTitle"))

        self._contents_tree = QTreeWidget()
        self._contents_tree.setHeaderLabel("Dateien im Backup")
        right_layout.addWidget(self._contents_tree, 1)

        self._backup_info = QLabel("Kein Backup ausgewählt.")
        self._backup_info.setStyleSheet("color: #888888; font-size: 12px;")
        self._backup_info.setWordWrap(True)
        right_layout.addWidget(self._backup_info)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        # Progress
        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)

        self._status = QLabel("Bereit.")
        self._status.setObjectName("StatusLabel")

        root.addSpacing(8)
        root.addWidget(self._progress)
        root.addWidget(self._status)

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    # ── SD root from main window ───────────────────────────────────────────
    def set_sd_root(self, path: str):
        if path:
            self._sd_root = Path(path)
            # Default backup dir
            default_backup = Path.home() / "DelugeHub_Backups"
            if not self._backup_dir_edit.text():
                self._backup_dir_edit.setText(str(default_backup))

    def _on_backup_dir_changed(self, text: str):
        if text:
            self._backup_dir = Path(text)
            self._load_history()

    def _browse_backup_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Backup-Ordner wählen", "")
        if path:
            self._backup_dir_edit.setText(path)

    # ── Create backup ──────────────────────────────────────────────────────
    def _create_backup(self):
        if not self._sd_root or not self._sd_root.exists():
            QMessageBox.warning(self, "Fehler", "Keine SD-Card ausgewählt oder Pfad nicht gefunden.")
            return

        if not self._backup_dir:
            QMessageBox.warning(self, "Fehler", "Bitte zuerst einen Backup-Ordner wählen.")
            return

        label = self._label_edit.text().strip() or f"Backup {datetime.now().strftime('%Y-%m-%d')}"
        notes = self._notes_edit.text().strip()

        self._create_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._worker = BackupWorker(
            self._sd_root, self._backup_dir, label, notes,
            exclude_samples=self._exclude_samples_cb.isChecked()
        )
        self._worker.progress.connect(lambda p, m: (
            self._progress.setValue(p),
            self._status.setText(m)
        ))
        self._worker.finished.connect(self._on_backup_done)
        self._worker.error.connect(self._on_backup_error)
        self._worker.start()

    def _on_backup_done(self, zip_path: Path):
        self._progress.setVisible(False)
        self._create_btn.setEnabled(True)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        self._status.setText(f"✅  Backup erstellt: {zip_path.name} ({size_mb:.1f} MB)")
        self._load_history()

    def _on_backup_error(self, msg: str):
        self._progress.setVisible(False)
        self._create_btn.setEnabled(True)
        QMessageBox.critical(self, "Backup-Fehler", msg)

    def _on_restore_done(self, result: dict):
        self._progress.setVisible(False)
        self._restore_btn.setEnabled(True)
        self._status.setText(
            f"✅  {result['restored']} Dateien wiederhergestellt"
            + (f"  |  ⚠ {result['failed']} Fehler" if result["failed"] else "")
        )

    def _on_restore_error(self, msg: str):
        self._progress.setVisible(False)
        self._restore_btn.setEnabled(True)
        QMessageBox.critical(self, "Restore-Fehler", msg)

    # ── History ────────────────────────────────────────────────────────────
    def _load_history(self):
        if not self._backup_dir:
            return
        self._entries = load_backup_history(self._backup_dir)
        self._history_table.setRowCount(0)
        for entry in self._entries:
            row = self._history_table.rowCount()
            self._history_table.insertRow(row)

            ts_item = QTableWidgetItem(entry.timestamp_str)
            ts_item.setData(Qt.UserRole, entry)
            self._history_table.setItem(row, 0, ts_item)
            self._history_table.setItem(row, 1, QTableWidgetItem(entry.label))
            self._history_table.setItem(row, 2, QTableWidgetItem(f"{entry.size_mb:.0f} MB"))
            self._history_table.setItem(row, 3, QTableWidgetItem(str(entry.file_count)))

        self._status.setText(f"{len(self._entries)} Backups gefunden.")

    def _on_backup_selected(self):
        rows = self._history_table.selectedItems()
        has = len(rows) > 0
        self._restore_btn.setEnabled(has)
        self._delete_backup_btn.setEnabled(has)

        if has:
            item = self._history_table.item(rows[0].row(), 0)
            entry: BackupEntry = item.data(Qt.UserRole)
            self._show_backup_contents(entry)

    def _show_backup_contents(self, entry: BackupEntry):
        self._contents_tree.clear()
        files = list_zip_contents(entry.path)

        # Build tree
        folders: dict[str, QTreeWidgetItem] = {}
        for f in files:
            parts = f.split("/")
            parent = self._contents_tree.invisibleRootItem()
            for i, part in enumerate(parts[:-1]):
                key = "/".join(parts[:i+1])
                if key not in folders:
                    item = QTreeWidgetItem(parent, [f"📁 {part}"])
                    folders[key] = item
                    parent = item
                else:
                    parent = folders[key]
            QTreeWidgetItem(parent, [f"  {parts[-1]}"])

        info = (f"📅 {entry.timestamp_str}\n"
                f"📝 {entry.label}\n"
                f"📁 {entry.file_count} Dateien\n"
                f"💾 {entry.size_mb:.1f} MB\n"
                f"📂 Quelle: {entry.sd_root or '—'}")
        if entry.notes:
            info += f"\n📋 {entry.notes}"
        self._backup_info.setText(info)

    # ── Restore ────────────────────────────────────────────────────────────
    def _restore_selected(self):
        rows = self._history_table.selectedItems()
        if not rows:
            return
        item = self._history_table.item(rows[0].row(), 0)
        entry: BackupEntry = item.data(Qt.UserRole)

        if entry.exclude_samples:
            QMessageBox.information(
                self, "Hinweis",
                "Dieses Backup enthält keinen Samples-Ordner.\n"
                "Nur SONGS, KITS und SYNTHS werden wiederhergestellt."
            )

        if not self._sd_root:
            dest = QFileDialog.getExistingDirectory(self, "Wiederherstellungs-Ziel wählen", "")
            if not dest:
                return
            dest_path = Path(dest)
        else:
            reply = QMessageBox.question(
                self, "Backup wiederherstellen",
                f"Backup '{entry.label}' auf\n{self._sd_root}\nwiederherstellen?\n\n"
                "WARNUNG: Existierende Dateien werden überschrieben!",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            dest_path = self._sd_root

        self._restore_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._restore_worker = RestoreWorker(entry.path, dest_path)
        self._restore_worker.progress.connect(
            lambda p, m: (self._progress.setValue(p), self._status.setText(m))
        )
        self._restore_worker.finished.connect(self._on_restore_done)
        self._restore_worker.error.connect(self._on_restore_error)
        self._restore_worker.start()

    def _delete_selected_backup(self):
        rows = self._history_table.selectedItems()
        if not rows:
            return
        item = self._history_table.item(rows[0].row(), 0)
        entry: BackupEntry = item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self, "Backup löschen",
            f"Backup '{entry.label}' ({entry.size_mb:.0f} MB) löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            entry.path.unlink()
            self._status.setText(f"🗑  Backup gelöscht: {entry.label}")
            self._load_history()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
