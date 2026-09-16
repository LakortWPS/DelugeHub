"""
Tests for StagingStore._apply()'s rename-collision guard and
delete-goes-to-trash behavior.

Before this fix:
  - RENAME used Path.rename() with no existence check, so a batch-rename
    pattern producing the same target name for two files (e.g. no
    {index} placeholder) silently overwrote one file with the other,
    and a target colliding with any pre-existing file was also
    overwritten with no warning.
  - DELETE used Path.unlink(), permanently destroying Kit/Song XML files
    with no trash and no way to undo, unlike Sample/Synth deletes which
    already go through history.move_to_trash().
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_core_module(name):
    full_name = "app.core." + name

    if "app" not in sys.modules:
        pkg = types.ModuleType("app")
        pkg.__path__ = [str(ROOT / "app")]
        sys.modules["app"] = pkg

    if "app.core" not in sys.modules:
        pkg = types.ModuleType("app.core")
        pkg.__path__ = [str(ROOT / "app" / "core")]
        sys.modules["app.core"] = pkg

    path = ROOT / "app" / "core" / (name + ".py")
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType(full_name)
    module.__file__ = str(path)
    module.__package__ = "app.core"
    sys.modules[full_name] = module
    code = compile(source, str(path), "exec")
    exec(code, module.__dict__)
    return module


file_ops = _load_core_module("file_ops")
sys.modules["app.core.file_ops"] = file_ops

history = _load_core_module("history")
sys.modules["app.core.history"] = history

staging = _load_core_module("staging")
StagingStore = staging.StagingStore
PendingChange = staging.PendingChange
ChangeType = staging.ChangeType


def _kit(tmp_path, name, content="<kit/>"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_batch_rename_collision_is_blocked_and_files_untouched(tmp_path):
    src_a = _kit(tmp_path, "KIT000.XML", "AAA")
    src_b = _kit(tmp_path, "KIT001.XML", "BBB")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src_a, "kit_manager", new_name="MyKit.XML"))
    store.add(PendingChange(ChangeType.RENAME, src_b, "kit_manager", new_name="MyKit.XML"))

    success, failed = store.apply_all()

    assert success == 0
    assert failed == 2
    # Neither source file was touched or lost.
    assert src_a.read_text(encoding="utf-8") == "AAA"
    assert src_b.read_text(encoding="utf-8") == "BBB"
    assert not (tmp_path / "MyKit.XML").exists()


def test_rename_onto_existing_file_is_blocked(tmp_path):
    src = _kit(tmp_path, "KIT000.XML", "SOURCE")
    existing = _kit(tmp_path, "KIT001.XML", "EXISTING")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src, "kit_manager", new_name="KIT001.XML"))

    success, failed = store.apply_all()

    assert success == 0
    assert failed == 1
    assert src.exists()
    assert src.read_text(encoding="utf-8") == "SOURCE"
    # The pre-existing file must survive with its original content.
    assert existing.read_text(encoding="utf-8") == "EXISTING"


def test_rename_without_collision_still_succeeds(tmp_path):
    src = _kit(tmp_path, "KIT000.XML", "SOURCE")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src, "kit_manager", new_name="RenamedKit.XML"))

    success, failed = store.apply_all()

    assert success == 1
    assert failed == 0
    assert not src.exists()
    assert (tmp_path / "RenamedKit.XML").read_text(encoding="utf-8") == "SOURCE"


def test_delete_moves_file_to_trash_instead_of_destroying_it(tmp_path, monkeypatch):
    trash_root = tmp_path / "_trash"

    def _fake_trash_dir():
        trash_root.mkdir(parents=True, exist_ok=True)
        return trash_root

    monkeypatch.setattr(history, "trash_dir", _fake_trash_dir)
    # staging.py did `from .history import move_to_trash` - reload it so
    # the freshly-monkeypatched trash_dir is the one actually used.
    staging2 = _load_core_module("staging")

    kits_dir = tmp_path / "kits"
    kits_dir.mkdir()
    target = kits_dir / "KIT000.XML"
    target.write_text("IMPORTANT DATA", encoding="utf-8")

    store = staging2.StagingStore()
    store.add(staging2.PendingChange(staging2.ChangeType.DELETE, target, "kit_manager"))

    success, failed = store.apply_all()

    assert success == 1
    assert failed == 0
    assert not target.exists()

    trashed = list(trash_root.glob("KIT000*"))
    assert len(trashed) == 1
    assert trashed[0].read_text(encoding="utf-8") == "IMPORTANT DATA"
