"""
DelugeHub — Backup & Restore
ZIP-based SD card backups with history and selective restore.
"""
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import logging

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)

BACKUP_META_FILE = "delugyhub_backup.json"
IGNORE_PATTERNS = {".DS_Store", "Thumbs.db", "desktop.ini", "FIRMWARE.BIN"}


@dataclass
class BackupEntry:
    path: Path
    timestamp: datetime
    label: str
    sd_root: str
    size_bytes: int = 0
    file_count: int = 0
    notes: str = ""
    exclude_samples: bool = False

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def timestamp_str(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d  %H:%M")


def load_backup_history(backup_dir: Path) -> list[BackupEntry]:
    """Scan backup_dir for all .zip backups with metadata."""
    entries = []
    if not backup_dir.exists():
        return entries

    for zf in sorted(backup_dir.glob("*.zip"), reverse=True):
        meta = _read_meta_from_zip(zf)
        if meta:
            entries.append(BackupEntry(
                path=zf,
                timestamp=datetime.fromisoformat(meta.get("timestamp", "2000-01-01")),
                label=meta.get("label", zf.stem),
                sd_root=meta.get("sd_root", ""),
                size_bytes=zf.stat().st_size,
                file_count=meta.get("file_count", 0),
                notes=meta.get("notes", ""),
                exclude_samples=meta.get("exclude_samples", False),
            ))
        else:
            # ZIP without meta — still include
            try:
                ts = datetime.fromtimestamp(zf.stat().st_mtime)
                entries.append(BackupEntry(
                    path=zf,
                    timestamp=ts,
                    label=zf.stem,
                    sd_root="",
                    size_bytes=zf.stat().st_size,
                ))
            except Exception:
                pass
    return entries


def _read_meta_from_zip(zf_path: Path) -> Optional[dict]:
    try:
        with zipfile.ZipFile(zf_path, "r") as z:
            if BACKUP_META_FILE in z.namelist():
                return json.loads(z.read(BACKUP_META_FILE))
    except Exception:
        pass
    return None


def list_zip_contents(zf_path: Path) -> list[str]:
    """List all files inside a backup ZIP."""
    try:
        with zipfile.ZipFile(zf_path, "r") as z:
            return [n for n in z.namelist() if n != BACKUP_META_FILE]
    except Exception:
        return []


def restore_from_backup(zf_path: Path, dest_root: Path,
                        files: Optional[list[str]] = None,
                        progress_cb=None) -> dict:
    """
    Restore files from a backup ZIP to dest_root.
    files: if None, restore everything; otherwise restore only these paths.
    Returns {"restored": int, "failed": int}
    """
    restored = 0
    failed = 0
    try:
        with zipfile.ZipFile(zf_path, "r") as z:
            names = [n for n in z.namelist()
                     if n != BACKUP_META_FILE and not n.endswith("/")]
            if files is not None:
                names = [n for n in names if n in files]

            total = len(names)
            for i, name in enumerate(names):
                try:
                    target = dest_root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    restored += 1
                except Exception as e:
                    log.error(f"restore failed for {name}: {e}")
                    failed += 1
                if progress_cb:
                    progress_cb(int((i + 1) / max(total, 1) * 100),
                                f"Restore: {Path(name).name}")
    except Exception as e:
        log.error(f"restore_from_backup error: {e}")
    return {"restored": restored, "failed": failed}


class BackupWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(Path)
    error = Signal(str)

    def __init__(self, sd_root: Path, backup_dir: Path, label: str,
                 notes: str = "", exclude_samples: bool = False):
        super().__init__()
        self.sd_root = sd_root
        self.backup_dir = backup_dir
        self.label = label
        self.notes = notes
        self.exclude_samples = exclude_samples
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = self._do_backup()
            if not self._cancelled:
                self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _do_backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now()
        safe_label = "".join(c for c in self.label if c.isalnum() or c in "-_ ")
        filename = f"{ts.strftime('%Y%m%d_%H%M%S')}_{safe_label}.zip"
        zip_path = self.backup_dir / filename

        # Collect all files to backup
        all_files = []
        for f in self.sd_root.rglob("*"):
            if not f.is_file() or f.name in IGNORE_PATTERNS:
                continue
            if self.exclude_samples:
                try:
                    rel = f.relative_to(self.sd_root)
                    if rel.parts[0].upper() == "SAMPLES":
                        continue
                except ValueError:
                    pass
            all_files.append(f)

        total = len(all_files)
        self.progress.emit(0, f"Starte Backup ({total} Dateien)…")

        file_count = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zf:
            for i, f in enumerate(all_files):
                if self._cancelled:
                    break
                try:
                    arcname = str(f.relative_to(self.sd_root)).replace("\\", "/")
                    zf.write(f, arcname)
                    file_count += 1
                except Exception as e:
                    log.warning(f"backup skip {f}: {e}")

                pct = int((i + 1) / max(total, 1) * 95)
                self.progress.emit(pct, f"Backup: {f.name}")

            # Write metadata
            meta = {
                "timestamp": ts.isoformat(),
                "label": self.label,
                "sd_root": str(self.sd_root),
                "file_count": file_count,
                "notes": self.notes,
                "exclude_samples": self.exclude_samples,
                "version": "1.0",
            }
            zf.writestr(BACKUP_META_FILE, json.dumps(meta, indent=2))

        self.progress.emit(100, "Backup abgeschlossen.")
        return zip_path
