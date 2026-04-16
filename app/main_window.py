"""
DelugeHub — Main Window
Sidebar navigation, module panel switching, SD-card scan integration.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QFileDialog, QStackedWidget,
    QProgressBar, QApplication, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, QEvent

from .theme import get_theme
from .core.sd_scanner import ScanWorker
from .core.staging import StagingStore
from .modules.dashboard import DashboardModule
from .modules.lost_sample_finder import LostSampleFinderModule
from .modules.sample_manager import SampleManagerModule
from .modules.song_manager import SongManagerModule
from .modules.kit_manager import KitManagerModule
from .modules.synth_editor import SynthEditorModule
from .modules.batch_hub import BatchHubModule
from .modules.backup_sync import BackupSyncModule
from .modules.settings_module import SettingsModule, APP_VERSION


MODULES = [
    ("dashboard",          "🏠", "Dashboard"),
    ("song_manager",       "🎵", "Song Manager"),
    ("kit_manager",        "🥁", "Kit Manager"),
    ("synth_editor",       "🎹", "Synth Editor"),
    ("sample_manager",     "📁", "Sample Manager"),
    ("lost_sample_finder", "🔍", "Lost Sample Finder"),
    ("batch_hub",          "⚡", "Batch Hub"),
    ("backup_sync",        "💾", "Backup & Sync"),
    ("settings",           "⚙️", "Einstellungen"),
]

_SIDEBAR_EXPANDED_W = 220
_SIDEBAR_COLLAPSED_W = 52


class NavButton(QPushButton):
    def __init__(self, icon: str, label: str):
        super().__init__(f"  {icon}  {label}")
        self._icon = icon
        self._label = label
        self.setObjectName("NavButton")
        self.setProperty("active", "false")
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)

    def set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_collapsed(self, collapsed: bool):
        if collapsed:
            self.setText(self._icon)
            self.setObjectName("NavButtonCollapsed")
        else:
            self.setText(f"  {self._icon}  {self._label}")
            self.setObjectName("NavButton")
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DelugeHub")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 820)

        self._settings = self._load_settings()
        self._current_theme = self._settings.get("theme", "dark")
        self._index = None
        self._scan_worker = None
        self._nav_buttons: dict[str, NavButton] = {}
        self._sidebar_collapsed = False
        self._staging = StagingStore()

        self._build_ui()
        self._apply_theme(self._current_theme)

        if self._settings.get("sd_path") and self._settings.get("auto_scan", False):
            self._start_scan(self._settings["sd_path"])

    # ── Settings persistence ───────────────────────────────────────────────
    def _settings_path(self) -> Path:
        return Path.home() / ".delugyhub" / "settings.json"

    def _load_settings(self) -> dict:
        p = self._settings_path()
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        return {"theme": "dark", "sd_path": "", "auto_scan": False}

    def _save_settings(self):
        p = self._settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._settings, indent=2))

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._stack.setObjectName("ContentArea")
        body.addWidget(self._stack, 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_status_bar())
        self._build_modules()
        self._navigate("dashboard")

        # Scan overlay — floats over the content stack
        self._scan_overlay = self._build_scan_overlay()
        self._scan_overlay.setParent(self._stack)
        self._scan_overlay.hide()
        self._stack.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Keep the scan overlay sized to match the content area."""
        if obj is self._stack and event.type() == QEvent.Resize:
            self._scan_overlay.setGeometry(self._stack.rect())
        return super().eventFilter(obj, event)

    def _build_scan_overlay(self) -> QFrame:
        overlay = QFrame()
        overlay.setObjectName("ScanOverlay")
        outer = QVBoxLayout(overlay)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("ScanOverlayCard")
        card.setFixedSize(300, 130)
        card_layout = QVBoxLayout(card)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(14)

        scan_lbl = QLabel("⟳  Scanne SD-Card…")
        scan_lbl.setObjectName("ScanOverlayLabel")
        scan_lbl.setAlignment(Qt.AlignCenter)

        self._overlay_progress = QProgressBar()
        self._overlay_progress.setFixedWidth(240)
        self._overlay_progress.setFixedHeight(8)
        self._overlay_progress.setValue(0)

        self._overlay_msg = QLabel("")
        self._overlay_msg.setObjectName("StatusLabel")
        self._overlay_msg.setAlignment(Qt.AlignCenter)

        card_layout.addWidget(scan_lbl)
        card_layout.addWidget(self._overlay_progress, 0, Qt.AlignCenter)
        card_layout.addWidget(self._overlay_msg)
        outer.addWidget(card)
        return overlay

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("💾"))

        sd_lbl = QLabel("SD-Card:")
        sd_lbl.setObjectName("SDPathLabel")
        layout.addWidget(sd_lbl)

        sd_path = self._settings.get("sd_path") or ""
        self._sd_path_label = QLabel(sd_path or "Nicht ausgewählt")
        self._sd_path_label.setObjectName("SDPathValue")
        self._sd_path_label.setMaximumWidth(480)
        self._sd_path_label.setToolTip(sd_path)
        layout.addWidget(self._sd_path_label)

        select_btn = QPushButton("Ordner wählen")
        select_btn.setObjectName("SecondaryButton")
        select_btn.setFixedHeight(32)
        select_btn.setFixedWidth(130)
        select_btn.clicked.connect(self._browse_sd_path)
        layout.addWidget(select_btn)

        self._scan_btn = QPushButton("⟳  Scannen")
        self._scan_btn.setFixedHeight(32)
        self._scan_btn.setFixedWidth(110)
        self._scan_btn.clicked.connect(self._trigger_scan)
        layout.addWidget(self._scan_btn)

        layout.addStretch()


        return bar

    def _build_sidebar(self) -> QWidget:
        self._sidebar = QWidget()
        self._sidebar.setObjectName("Sidebar")
        self._sidebar.setFixedWidth(_SIDEBAR_EXPANDED_W)

        layout = QVBoxLayout(self._sidebar)
        layout.setContentsMargins(8, 0, 8, 16)
        layout.setSpacing(2)

        # Collapse toggle at the very top
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 8, 0, 0)
        self._sidebar_title = QLabel("DelugeHub")
        self._sidebar_title.setObjectName("AppTitle")
        self._collapse_btn = QPushButton("‹")
        self._collapse_btn.setObjectName("CollapseButton")
        self._collapse_btn.setFixedSize(28, 28)
        self._collapse_btn.setToolTip("Sidebar einklappen")
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.clicked.connect(self._toggle_sidebar_collapse)
        top_row.addWidget(self._sidebar_title)
        top_row.addStretch()
        top_row.addWidget(self._collapse_btn)
        layout.addLayout(top_row)

        self._sidebar_sub = QLabel(f"v{APP_VERSION}  •  Deluge Manager")
        self._sidebar_sub.setObjectName("AppSubtitle")
        layout.addWidget(self._sidebar_sub)

        self._sidebar_sep = QFrame()
        self._sidebar_sep.setFrameShape(QFrame.HLine)
        self._sidebar_sep.setStyleSheet("color: #0F3460;")
        layout.addWidget(self._sidebar_sep)
        layout.addSpacing(8)

        for key, icon, label in MODULES[:-1]:
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda checked, k=key: self._navigate(k))
            self._nav_buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #0F3460;")
        layout.addWidget(sep2)

        key, icon, label = MODULES[-1]
        btn = NavButton(icon, label)
        btn.clicked.connect(lambda: self._navigate("settings"))
        self._nav_buttons["settings"] = btn
        layout.addWidget(btn)

        return self._sidebar

    def _toggle_sidebar_collapse(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        collapsed = self._sidebar_collapsed

        self._sidebar.setFixedWidth(_SIDEBAR_COLLAPSED_W if collapsed else _SIDEBAR_EXPANDED_W)
        self._sidebar.setObjectName("SidebarCollapsed" if collapsed else "Sidebar")
        self._sidebar.style().unpolish(self._sidebar)
        self._sidebar.style().polish(self._sidebar)

        self._sidebar_title.setVisible(not collapsed)
        self._sidebar_sub.setVisible(not collapsed)
        self._sidebar_sep.setVisible(not collapsed)

        self._collapse_btn.setText("›" if collapsed else "‹")
        self._collapse_btn.setToolTip(
            "Sidebar ausklappen" if collapsed else "Sidebar einklappen"
        )

        for btn in self._nav_buttons.values():
            btn.set_collapsed(collapsed)

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self._status_label = QLabel("Bereit — bitte SD-Card auswählen und scannen.")
        self._status_label.setObjectName("StatusLabel")

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setVisible(False)

        self._pending_lbl = QLabel("Keine ausstehenden Änderungen")
        self._pending_lbl.setObjectName("StatusLabel")

        self._save_all_btn = QPushButton("💾 Alle speichern")
        self._save_all_btn.setFixedHeight(24)
        self._save_all_btn.setVisible(False)
        self._save_all_btn.clicked.connect(self._save_all_pending)

        layout.addWidget(self._status_label)
        layout.addStretch()
        layout.addWidget(self._pending_lbl)
        layout.addWidget(self._save_all_btn)
        layout.addWidget(self._progress_bar)
        return bar

    def _build_modules(self):
        self._modules: dict[str, QWidget] = {}

        def reg(key, widget):
            self._modules[key] = widget
            self._stack.addWidget(widget)
            return widget

        # Dashboard
        dash = reg("dashboard", DashboardModule())
        dash.request_scan.connect(self._trigger_scan)
        dash.navigate_to.connect(self._navigate)

        # Song Manager
        songs = reg("song_manager", SongManagerModule())
        songs.request_rescan.connect(self._trigger_scan)
        songs.navigate_to.connect(self._navigate)
        songs.set_staging(self._staging)

        # Kit Manager
        kits = reg("kit_manager", KitManagerModule())
        kits.request_rescan.connect(self._trigger_scan)
        kits.set_staging(self._staging)

        # Synth Editor
        synths = reg("synth_editor", SynthEditorModule())
        synths.request_rescan.connect(self._trigger_scan)
        synths.set_staging(self._staging)

        # Sample Manager
        samples = reg("sample_manager", SampleManagerModule())
        samples.request_rescan.connect(self._trigger_scan)

        # Lost Sample Finder
        lsf = reg("lost_sample_finder", LostSampleFinderModule())
        lsf.request_rescan.connect(self._trigger_scan)

        # Batch Hub
        batch = reg("batch_hub", BatchHubModule())
        batch.request_rescan.connect(self._trigger_scan)
        batch.set_staging(self._staging)

        # Backup & Sync
        backup = reg("backup_sync", BackupSyncModule())
        if self._settings.get("sd_path"):
            backup.set_sd_root(self._settings["sd_path"])

        # Settings
        settings_mod = reg("settings", SettingsModule(self._settings))
        settings_mod.sd_path_changed.connect(self._on_sd_path_changed)
        settings_mod.theme_changed.connect(self._apply_theme)
        settings_mod.auto_scan_changed.connect(self._on_auto_scan_changed)

    # ── Navigation ─────────────────────────────────────────────────────────
    def _navigate(self, key: str):
        if key not in self._modules:
            return
        self._stack.setCurrentWidget(self._modules[key])
        for k, btn in self._nav_buttons.items():
            btn.set_active(k == key)
        names = {m[0]: m[2] for m in MODULES}
        self.setWindowTitle(f"DelugeHub — {names.get(key, key)}")

    # ── Scan ───────────────────────────────────────────────────────────────
    def _browse_sd_path(self):
        path = QFileDialog.getExistingDirectory(self, "SD-Card Ordner wählen", "")
        if path:
            self._on_sd_path_changed(path)

    def _on_sd_path_changed(self, path: str):
        self._settings["sd_path"] = path
        self._sd_path_label.setText(path)
        self._sd_path_label.setToolTip(path)
        backup = self._modules.get("backup_sync")
        if backup:
            backup.set_sd_root(path)
        sd_root = Path(path)
        self._staging.set_sd_root(sd_root)
        self._check_pending_on_startup(sd_root)
        self._save_settings()
        self._start_scan(path)

    def _trigger_scan(self):
        path = self._settings.get("sd_path", "")
        if not path:
            self._browse_sd_path()
            return
        self._start_scan(path)

    def _start_scan(self, path: str):
        root = Path(path)
        if not root.exists():
            QMessageBox.warning(self, "Pfad nicht gefunden", f"Pfad existiert nicht:\n{path}")
            return

        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.cancel()
            self._scan_worker.wait()

        self._scan_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)

        # Show scan overlay over the content area
        self._overlay_progress.setValue(0)
        self._overlay_msg.setText("")
        self._scan_overlay.setGeometry(self._stack.rect())
        self._scan_overlay.show()
        self._scan_overlay.raise_()

        self._scan_worker = ScanWorker(root)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()
        self._status_label.setText(f"Scanne {root.name}…")

    def _on_scan_progress(self, pct: int, msg: str):
        self._progress_bar.setValue(pct)
        self._overlay_progress.setValue(pct)
        self._overlay_msg.setText(msg)
        self._status_label.setText(msg)

    def _on_scan_finished(self, index):
        self._index = index
        self._scan_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._scan_overlay.hide()

        missing = index.total_missing_refs
        self._status_label.setText(
            f"✓  {len(index.songs)} Songs  •  {len(index.kits)} Kits  •  "
            f"{len(index.synths)} Synths  •  {len(index.samples)} Samples  •  "
            f"{'⚠ ' + str(missing) + ' fehlend' if missing else '✅ alle Samples OK'}"
        )

        # Push index to all modules
        for key, module in self._modules.items():
            if hasattr(module, "update_index"):
                module.update_index(index)

        self._navigate("dashboard")

    def _on_scan_error(self, msg: str):
        self._scan_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._scan_overlay.hide()
        self._status_label.setText(f"⚠  Scan-Fehler: {msg}")
        QMessageBox.critical(self, "Scan-Fehler", msg)

    def _on_auto_scan_changed(self, enabled: bool):
        self._settings["auto_scan"] = enabled
        self._save_settings()

    # ── Staging ────────────────────────────────────────────────────────────
    def _refresh_pending_badge(self):
        count = self._staging.count()
        if count == 0:
            self._pending_lbl.setText("Keine ausstehenden Änderungen")
            self._save_all_btn.setVisible(False)
        else:
            self._pending_lbl.setText(f"⏳ {count} Änderung{'en' if count != 1 else ''} ausstehend")
            self._save_all_btn.setVisible(True)

    def _save_all_pending(self):
        reply = QMessageBox(self)
        reply.setWindowTitle("Alle Änderungen speichern")
        reply.setText(f"{self._staging.count()} Änderungen speichern?")
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

        success, failed = self._staging.apply_all(dest_root)
        self._refresh_pending_badge()
        self._trigger_scan()
        QMessageBox.information(self, "Gespeichert",
            f"✅ {success} gespeichert." + (f"  ⚠ {failed} Fehler." if failed else ""))

    def _check_pending_on_startup(self, sd_root: Path):
        if self._staging.load_from_disk(sd_root):
            count = self._staging.count()
            reply = QMessageBox.question(
                self, "Gespeicherte Änderungen",
                f"Es gibt {count} Änderungen aus der letzten Session.\n"
                "Wiederherstellen oder verwerfen?",
                QMessageBox.RestoreDefaults | QMessageBox.Discard
            )
            if reply == QMessageBox.Discard:
                self._staging.clear_all()
                self._staging.delete_disk_file()
            self._refresh_pending_badge()

    # ── Theme ──────────────────────────────────────────────────────────────
    def _toggle_theme(self):
        new = "light" if self._current_theme == "dark" else "dark"
        self._apply_theme(new)

    def _apply_theme(self, theme: str):
        self._current_theme = theme
        self._settings["theme"] = theme
        QApplication.instance().setStyleSheet(get_theme(theme))
        self._save_settings()

    # ── Cleanup ────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._save_settings()
        if self._scan_worker and self._scan_worker.isRunning():
            self._scan_worker.cancel()
            self._scan_worker.wait()
        super().closeEvent(event)
