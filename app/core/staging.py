"""
DelugeHub — Staging Store
Puffert alle destruktiven Änderungen (XML-Edit, Rename, Delete) im RAM
und schreibt sie erst auf expliziten Nutzerbefehl auf Disk.
"""
from __future__ import annotations
import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class ChangeType(str, Enum):
    XML_EDIT = "xml_edit"
    RENAME   = "rename"
    DELETE   = "delete"


@dataclass
class PendingChange:
    change_type:   ChangeType
    file_path:     Path          # absoluter Original-Pfad
    source_module: str           # "song_manager" | "kit_manager" | ...
    timestamp:     str = field(default_factory=lambda: datetime.now().isoformat())
    # xml_edit
    new_content:   Optional[str] = None
    encoding:      str = "utf-8"
    # rename
    new_name:      Optional[str] = None   # nur Dateiname, kein Pfad
    # delete: kein extra Feld nötig

    @property
    def display_name(self) -> str:
        name = self.file_path.name
        if self.change_type == ChangeType.RENAME:
            return f"{name} → {self.new_name}"
        if self.change_type == ChangeType.DELETE:
            return f"{name} (löschen)"
        return f"{name} (bearbeitet)"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["file_path"] = str(self.file_path)
        d["change_type"] = self.change_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PendingChange":
        d = d.copy()
        d["file_path"] = Path(d["file_path"])
        d["change_type"] = ChangeType(d["change_type"])
        return cls(**d)


PENDING_FILE = ".delugyhub_pending.json"


class StagingStore:
    """Singleton-ähnlicher Store; eine Instanz pro App."""

    def __init__(self):
        self._changes: dict[Path, PendingChange] = {}   # file_path → change
        self._sd_root: Optional[Path] = None

    # ── Konfiguration ──────────────────────────────────────────────────────
    def set_sd_root(self, sd_root: Path) -> None:
        self._sd_root = sd_root

    # ── Änderungen verwalten ───────────────────────────────────────────────
    def add(self, change: PendingChange) -> None:
        """Fügt eine Änderung hinzu. Überschreibt vorherige Änderung an derselben Datei."""
        self._changes[change.file_path] = change
        self._autosave()

    def remove(self, file_path: Path) -> None:
        self._changes.pop(file_path, None)
        self._autosave()

    def clear_module(self, source_module: str) -> None:
        keys = [k for k, v in self._changes.items() if v.source_module == source_module]
        for k in keys:
            del self._changes[k]
        self._autosave()

    def clear_all(self) -> None:
        self._changes.clear()
        self._autosave()

    def get_all(self) -> list[PendingChange]:
        return list(self._changes.values())

    def get_for_module(self, source_module: str) -> list[PendingChange]:
        return [v for v in self._changes.values() if v.source_module == source_module]

    def count(self) -> int:
        return len(self._changes)

    # ── Anwenden ───────────────────────────────────────────────────────────
    def apply_all(self, dest_root: Optional[Path] = None) -> tuple[int, int]:
        """
        Wendet alle Änderungen an.
        dest_root=None  → Original überschreiben
        dest_root=Path  → Dateien in diesen Ordner spiegeln (nur geänderte)
        Gibt (success, failed) zurück.
        """
        return self._apply(list(self._changes.values()), dest_root)

    def apply_for_module(self, source_module: str, dest_root: Optional[Path] = None) -> tuple[int, int]:
        changes = self.get_for_module(source_module)
        return self._apply(changes, dest_root)

    def _apply(self, changes: list[PendingChange], dest_root: Optional[Path]) -> tuple[int, int]:
        from .file_ops import _write_xml
        success = failed = 0
        applied_paths = []

        for c in changes:
            try:
                target = self._resolve_target(c.file_path, dest_root)

                if c.change_type == ChangeType.XML_EDIT:
                    if dest_root:
                        target.parent.mkdir(parents=True, exist_ok=True)
                    _write_xml(target, c.new_content, c.encoding)

                elif c.change_type == ChangeType.RENAME:
                    new_path = target.parent / c.new_name
                    if dest_root:
                        # Kopiere Original unter neuem Namen ins Zielverzeichnis
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(c.file_path), str(new_path))
                    else:
                        c.file_path.rename(new_path)

                elif c.change_type == ChangeType.DELETE:
                    if not dest_root:   # Delete nur im Original-Modus
                        c.file_path.unlink(missing_ok=True)

                applied_paths.append(c.file_path)
                success += 1
            except Exception:
                failed += 1

        # Erfolgreich angewendete aus Store entfernen
        for p in applied_paths:
            self._changes.pop(p, None)
        self._autosave()
        return success, failed

    def _resolve_target(self, original: Path, dest_root: Optional[Path]) -> Path:
        if dest_root is None or self._sd_root is None:
            return original
        rel = original.relative_to(self._sd_root)
        return dest_root / rel

    # ── Persistenz ─────────────────────────────────────────────────────────
    def _autosave(self) -> None:
        if self._sd_root:
            self.save_to_disk(self._sd_root)

    def save_to_disk(self, sd_root: Path) -> None:
        data = [c.to_dict() for c in self._changes.values()]
        (sd_root / PENDING_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_from_disk(self, sd_root: Path) -> bool:
        """Lädt gespeicherte Änderungen. Gibt True zurück wenn Änderungen gefunden."""
        path = sd_root / PENDING_FILE
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._changes = {
                Path(d["file_path"]): PendingChange.from_dict(d)
                for d in data
            }
            return bool(self._changes)
        except Exception:
            return False

    def delete_disk_file(self) -> None:
        if self._sd_root:
            p = self._sd_root / PENDING_FILE
            p.unlink(missing_ok=True)
