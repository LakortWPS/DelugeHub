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


@dataclass
class ApplyReport:
    """Outcome of StagingStore.apply_*. failures stay pending."""
    success: int = 0
    failed: int = 0
    trashed: list[tuple[Path, Path]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


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
    does not pass the strict parser (no lxml recovery) is also skipped —
    rather than staging a body the Deluge could not load — and logged.
    """
    from .file_ops import _read_xml
    from .xml_parser import validate_xml_text_strict

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

        error = validate_xml_text_strict(new_text, context=str(xml_file))
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


def global_replace_rejections(
    xml_files: list[Path], find_text: str, replace_text: str,
) -> list[tuple[Path, str]]:
    """
    Files whose global replace would change the text but fail the strict
    parser. Same slash rules as plan_global_replace. Used to list the skip
    reason before the user confirms.
    """
    from .file_ops import _read_xml
    from .xml_parser import validate_xml_text_strict

    find_fwd = find_text.replace("\\", "/")
    replace_fwd = replace_text.replace("\\", "/")
    find_bwd = find_text.replace("/", "\\")
    replace_bwd = replace_text.replace("/", "\\")

    rejected: list[tuple[Path, str]] = []
    for xml_file in xml_files:
        try:
            text, _enc = _read_xml(xml_file)
        except Exception:
            continue
        new_text = text.replace(find_fwd, replace_fwd).replace(find_bwd, replace_bwd)
        if new_text == text:
            continue
        error = validate_xml_text_strict(new_text, context=str(xml_file))
        if error is not None:
            rejected.append((xml_file, error))
    return rejected


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

    def peek(self, file_path: Path) -> Optional[str]:
        """Staged XML body for file_path, if an XML_EDIT is pending."""
        change = self._changes.get(file_path)
        if change is None or change.change_type != ChangeType.XML_EDIT:
            return None
        return change.new_content

    def apply_all(self, dest_root: Optional[Path] = None) -> ApplyReport:
        return self._apply(list(self._changes.values()), dest_root)

    def apply_for_module(self, source_module: str, dest_root: Optional[Path] = None) -> ApplyReport:
        changes = self.get_for_module(source_module)
        return self._apply(changes, dest_root)

    def _apply(self, changes: list[PendingChange], dest_root: Optional[Path]) -> ApplyReport:
        from .file_ops import _write_xml
        from .history import move_to_trash
        report = ApplyReport()
        applied_paths = []
        blocked, targets = self._blocked_rename_sources(changes, dest_root)
        ordered = self._ordered_renames(changes, targets, blocked)

        for path, reason in blocked.items():
            report.failed += 1
            report.failures.append(reason)
            log.error("Staging: %s", reason)

        runnable = [
            c for c in changes
            if c.change_type != ChangeType.RENAME and c.file_path not in blocked
        ] + ordered

        for c in runnable:
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
                        trash_path = move_to_trash(c.file_path)
                        report.trashed.append((c.file_path, trash_path))

                applied_paths.append(c.file_path)
                report.success += 1
            except Exception as e:
                log.error("Staging apply fehlgeschlagen (%s): %s", c.file_path.name, e)
                report.failed += 1
                report.failures.append(f"{c.file_path.name}: {e}")

        for p in applied_paths:
            self._changes.pop(p, None)
        self._autosave()
        return report

    def _blocked_rename_sources(
        self, changes: list[PendingChange], dest_root: Optional[Path]
    ) -> tuple[dict[Path, str], dict[Path, Path]]:
        """
        Refuse RENAME changes that would overwrite a file which is not itself
        moving out of the way in this batch.

        A chain A→B, B→C is allowed: B leaves before A arrives. A swap
        A→B, B→A is refused, as are two sources that share one target name
        and a target that already exists and is not part of the batch.

        Returns (blocked source → reason, source → target path).
        """
        rename_changes = [c for c in changes if c.change_type == ChangeType.RENAME]
        targets_by_source: dict[Path, Path] = {}
        if not rename_changes:
            return {}, targets_by_source

        target_counts: dict[Path, int] = {}
        for c in rename_changes:
            target = self._resolve_target(c.file_path, dest_root).parent / c.new_name
            targets_by_source[c.file_path] = target
            target_counts[target] = target_counts.get(target, 0) + 1

        blocked: dict[Path, str] = {}
        for c in rename_changes:
            target = targets_by_source[c.file_path]
            if target == c.file_path:
                continue
            if target_counts[target] > 1:
                blocked[c.file_path] = (
                    f"{c.file_path.name}: Zielname {target.name} ist im Batch mehrfach belegt"
                )

        for src in self._rename_cycles(targets_by_source, blocked):
            target = targets_by_source[src]
            blocked[src] = (
                f"{src.name}: Umbenennung würde sich mit {target.name} im Batch tauschen"
            )

        while True:
            progressed = False
            for c in rename_changes:
                if c.file_path in blocked:
                    continue
                target = targets_by_source[c.file_path]
                if target == c.file_path or not target.exists():
                    continue
                occupant_moves = (
                    target in targets_by_source
                    and target not in blocked
                    and targets_by_source[target] != target
                )
                if occupant_moves:
                    continue
                blocked[c.file_path] = (
                    f"{c.file_path.name}: Zieldatei {target.name} existiert bereits"
                )
                progressed = True
            if not progressed:
                break
        return blocked, targets_by_source

    @staticmethod
    def _rename_cycles(
        targets_by_source: dict[Path, Path], blocked: dict[Path, str]
    ) -> set[Path]:
        """Sources that lie on a cycle of in-batch renames (A→B→A)."""
        cyclic: set[Path] = set()
        for start in targets_by_source:
            if start in blocked or start in cyclic:
                continue
            seen: list[Path] = []
            cur = start
            while cur in targets_by_source and cur not in blocked:
                if cur in seen:
                    cyclic.update(seen[seen.index(cur):])
                    break
                seen.append(cur)
                nxt = targets_by_source[cur]
                if nxt == cur:
                    break
                cur = nxt
        return cyclic

    @staticmethod
    def _ordered_renames(
        changes: list[PendingChange],
        targets_by_source: dict[Path, Path],
        blocked: dict[Path, str],
    ) -> list[PendingChange]:
        """
        Rename the file that currently occupies a target name before the
        change that wants that name. Cycles are already in `blocked`.
        """
        remaining = [
            c for c in changes
            if c.change_type == ChangeType.RENAME and c.file_path not in blocked
        ]
        ordered: list[PendingChange] = []
        while remaining:
            progressed = False
            for c in list(remaining):
                target = targets_by_source[c.file_path]
                occupant_pending = any(
                    other.file_path == target and other is not c for other in remaining
                )
                if not occupant_pending:
                    ordered.append(c)
                    remaining.remove(c)
                    progressed = True
            if not progressed:
                for c in remaining:
                    blocked[c.file_path] = (
                        f"{c.file_path.name}: Umbenennung würde sich mit einer "
                        "anderen Datei im Batch tauschen"
                    )
                break
        return ordered

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
