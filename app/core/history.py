"""
DelugeHub — Action History
Undo/Redo stack (up to 30 steps) for all destructive file operations.

Usage pattern in each module:
    # Before destructive op: capture state
    text_before, enc = _read_xml(path)

    # Perform the op
    _write_xml(path, new_text, enc)

    # Push to history
    if self._history:
        self._history.push(Action(
            description="Volumes normalisiert: KIT000",
            undo_fn=lambda: _write_xml(path, text_before, enc),
            redo_fn=lambda: _write_xml(path, new_text, enc),
        ))
"""
import itertools
import shutil
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional

_trash_counter = itertools.count()

log = logging.getLogger(__name__)

MAX_HISTORY = 30


@dataclass
class Action:
    description: str
    undo_fn: Callable[[], None]
    redo_fn: Optional[Callable[[], None]] = None


class ActionHistory:
    """
    In-memory undo/redo stack.
    Thread-safety: all calls must happen on the Qt main thread.
    """

    def __init__(self):
        self._undo: list[Action] = []
        self._redo: list[Action] = []
        self._on_change: Optional[Callable] = None

    def set_on_change(self, fn: Callable):
        """
        Register callback that fires after every push/undo/redo.
        Signature: fn(can_undo: bool, can_redo: bool, undo_desc: str, redo_desc: str)
        """
        self._on_change = fn

    def push(self, action: Action):
        """Push a new undoable action. Clears the redo stack."""
        self._undo.append(action)
        if len(self._undo) > MAX_HISTORY:
            self._undo.pop(0)
        self._redo.clear()
        self._notify()

    def undo(self) -> Optional[str]:
        """
        Execute the last undo function.
        Returns the action description, or None if stack is empty.
        Raises on undo_fn failure (caller should handle and show error).
        """
        if not self._undo:
            return None
        action = self._undo.pop()
        try:
            action.undo_fn()
        except Exception as e:
            log.error(f"Undo failed for '{action.description}': {e}")
            self._notify()
            raise
        if action.redo_fn:
            self._redo.append(action)
        self._notify()
        return action.description

    def redo(self) -> Optional[str]:
        """
        Re-execute the last undone action.
        Returns the action description, or None if stack is empty.
        """
        if not self._redo:
            return None
        action = self._redo.pop()
        try:
            action.redo_fn()
        except Exception as e:
            log.error(f"Redo failed for '{action.description}': {e}")
            self._notify()
            raise
        self._undo.append(action)
        self._notify()
        return action.description

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_description(self) -> str:
        return self._undo[-1].description if self._undo else ""

    @property
    def redo_description(self) -> str:
        return self._redo[-1].description if self._redo else ""

    def clear(self):
        """Clear both stacks (e.g. after a full rescan that invalidates history)."""
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def _notify(self):
        if self._on_change:
            self._on_change(
                self.can_undo,
                self.can_redo,
                self.undo_description,
                self.redo_description,
            )


# ── Trash helper ────────────────────────────────────────────────────────────

def trash_dir() -> Path:
    """Persistent per-user trash folder. Files here can be restored on Undo."""
    d = Path.home() / ".delugyhub" / "trash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def move_to_trash(path: Path) -> Path:
    """
    Move *path* into the trash folder and return the trash path.
    The trash path is needed to restore the file on Undo.
    Uses a unique suffix to avoid collisions.
    """
    dest = trash_dir() / f"{path.stem}_{next(_trash_counter):08d}{path.suffix}"
    shutil.move(str(path), str(dest))
    log.debug(f"Trashed: {path.name} → {dest.name}")
    return dest


def restore_from_trash(trash_path: Path, original_path: Path):
    """Move a trashed file back to its original location."""
    original_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trash_path), str(original_path))
    log.debug(f"Restored: {trash_path.name} → {original_path}")
