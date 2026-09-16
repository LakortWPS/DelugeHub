"""
DelugeHub — Staging Store
Puffert alle destruktiven Änderungen (XML-Edit, Rename, Delete) im RAM
und schreibt sie erst auf expliziten Nutzerbefehl auf Disk.
"""
from __future__ import annotations
import json
import logging
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


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
    # delete: kein extra Feld noetig

    @property
    def display_name(self) -> str:
        name = self.file_path.name
        if self.change_type == ChangeType.RENAME:
            return f"{name} -> {self.new_name}"
        if self.change_type == ChangeType.DELETE:
            return f"{name} (loeschen)"
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


def plan_global_replace(
    xml_files: list[Path], find_text: str, replace_text: str,
    source_module: str = "batch_hub",
) -> list[PendingChange]:
    """
    Build a list of XML_EDIT PendingChanges for a global find/replace across
    xml_files, without writing anything to disk.

    Mirrors the slash-normalization of file_ops.update_xml_path (handles
    both '/' and '\\' path separators), but - unlike update_xml_path -
    does NOT touch the filesystem directly. The caller is expected to push
    the returned changes into a StagingStore so the user can review the
    affected files (and undo) before they are written, instead of every
    matching XML across SONGS/KITS/SYNTHS being overwritten immediately.

    Files that fail to read, or in which neither replacement produces a
    change, are skipped (not included in the result). A file whose result
    would no longer be parseable XML is also skipped — rather than staging
    (and, on Save, writing) a change that could leave the Deluge unable to
    load that file — and logged as a warning so the skip is visible.
    """
    from .file_ops import _read_xml
    from .xml_parser import validate_xml_text

    find_fwd = find_text.replace("\\", "/")
    replace_fwd = replace_text.replace("\\", "/")
    find_bwd = find_text.replace("/", "\\")
    replace_bwd = replace_text.replace("/", "\\")

    changes: list[PendingChange] = []
    for xml_file in xml_files:
        try:
            text, enc = _read_xml(xml_file)
        except Exception:
            continue

        new_text = text.replace(find_fwd, replace_fwd).replace(find_bwd, replace_bwd)

        if new_text == text:
            continue

        error = validate_xml_text(new_text, context=str(xml_file))
        if error is not None:
            log.warning(
                "plan_global_replace: %s uebersprungen - Ergebnis waere kein "
                "gueltiges XML mehr (%s)", xml_file.name, error,
            )
            continue

        changes.append(PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=xml_file,
            source_module=source_module,
            new_content=new_text,
            encoding=enc,
        ))

    return changes


def preview_global_replace(xml_files: list[Path], find_text: str) -> list[tuple[Path, int]]:
    """
    Compute, for each file in xml_files, how many times find_text would be
    replaced by plan_global_replace — without writing anything to disk and
    without building the (potentially large) PendingChange.new_content.

    Used to show the user a preview ("these N files will be changed, with
    this many replacements each") before staging/writing the global replace.

    Uses the same '/' / '\\' normalization as plan_global_replace. Files
    that fail to read, or that contain no match, are omitted from the
    result. Order matches xml_files.
    """
    from .file_ops import _read_xml

    find_fwd = find_text.replace("\\", "/")
    find_bwd = find_text.replace("/", "\\")

    results: list[tuple[Path, int]] = []
    for xml_file in xml_files:
        try:
            text, _enc = _read_xml(xml_file)
        except Exception:
            continue

        count = text.count(find_fwd)
        if find_bwd != find_fwd:
            count += text.count(find_bwd)

        if count > 0:
            results.append((xml_file, count))

    return results


PENDING_FILE = ".delugyhub_pending.json"


class StagingStore:
    """Singleton-aehnlicher Store; eine Instanz pro App."""

    def __init__(self):
        self._changes: dict[Path, PendingChange] = {}   # file_path -> change
        self._sd_root: Optional[Path] = None

    def set_sd_root(self, sd_root: Path) -> None:
        self._sd_root = sd_root

    def add(self, change: PendingChange) -> None:
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

    def apply_all(self, dest_root: Optional[Path] = None) -> tuple[int, int]:
        return self._apply(list(self._changes.values()), dest_root)

    def apply_for_module(self, source_module: str, dest_root: Optional[Path] = None) -> tuple[int, int]:
        changes = self.get_for_module(source_module)
        return self._apply(changes, dest_root)

    def _apply(self, changes: list[PendingChange], dest_root: Optional[Path]) -> tuple[int, int]:
        from .file_ops import _write_xml
        from .history import move_to_trash
        success = failed = 0
        applied_paths = []
        blocked = self._blocked_rename_sources(changes, dest_root)

        for c in changes:
            if c.file_path in blocked:
                failed += 1
                continue
            try:
                target = self._resolve_target(c.file_path, dest_root)

                if c.change_type == ChangeType.XML_EDIT:
                    if dest_root:
                        target.parent.mkdir(parents=True, exist_ok=True)
                    _write_xml(target, c.new_content, c.encoding)

                elif c.change_type == ChangeType.RENAME:
                    new_path = target.parent / c.new_name
                    if dest_root:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(c.file_path), str(new_path))
                    else:
                        c.file_path.rename(new_path)

                elif c.change_type == ChangeType.DELETE:
                    if not dest_root and c.file_path.exists():
                        move_to_trash(c.file_path)

                applied_paths.append(c.file_path)
                success += 1
            except Exception as e:
                log.error("Staging apply fehlgeschlagen (%s): %s", c.file_path.name, e)
                failed += 1

        for p in applied_paths:
            self._changes.pop(p, None)
        self._autosave()
        return success, failed

    def _blocked_rename_sources(
        self, changes: list[PendingChange], dest_root: Optional[Path]
    ) -> set[Path]:
        """
        Refuse RENAME changes whose target filename would silently overwrite
        an existing file - either another file already on disk, or another
        change in this same batch that resolves to the same target name
        (e.g. a batch-rename pattern without {index} collapsing several
        files onto one name). Path.rename()/shutil.copy2() would otherwise
        overwrite the target with no warning and no way to get it back.

        Returns the set of source file_paths whose rename must be skipped.
        """
        rename_changes = [c for c in changes if c.change_type == ChangeType.RENAME]
        if not rename_changes:
            return set()

        targets_by_source: dict[Path, Path] = {}
        target_counts: dict[Path, int] = {}
        for c in rename_changes:
            target = self._resolve_target(c.file_path, dest_root).parent / c.new_name
            targets_by_source[c.file_path] = target
            target_counts[target] = target_counts.get(target, 0) + 1

        blocked: set[Path] = set()
        for c in rename_changes:
            target = targets_by_source[c.file_path]
            if target == c.file_path:
                continue  # no-op rename (new name == current name)
            if target_counts[target] > 1:
                blocked.add(c.file_path)
                log.error(
                    "Staging: Umbenennen von %s uebersprungen - Zielname %s wird "
                    "von mehreren Aenderungen in diesem Batch belegt",
                    c.file_path.name, target.name,
                )
            elif target.exists():
                blocked.add(c.file_path)
                log.error(
                    "Staging: Umbenennen von %s uebersprungen - Zieldatei %s "
                    "existiert bereits",
                    c.file_path.name, target.name,
                )
        return blocked

    def _resolve_target(self, original: Path, dest_root: Optional[Path]) -> Path:
        if dest_root is None or self._sd_root is None:
            return original
        try:
            rel = original.relative_to(self._sd_root)
        except ValueError:
            raise ValueError(
                f"Pfad {original!r} liegt nicht unter SD-Root {self._sd_root!r}"
            )
        return dest_root / rel

    def _autosave(self) -> None:
        if self._sd_root:
            try:
                self.save_to_disk(self._sd_root)
            except OSError as e:
                log.warning("Autosave fehlgeschlagen (%s): %s", self._sd_root, e)

    def save_to_disk(self, sd_root: Path) -> None:
        data = [c.to_dict() for c in self._changes.values()]
        target = sd_root / PENDING_FILE
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(target)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise

    def load_from_disk(self, sd_root: Path) -> bool:
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
