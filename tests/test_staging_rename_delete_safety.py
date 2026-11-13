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

    report = store.apply_all()

    assert report.success == 0
    assert report.failed == 2
    # Neither source file was touched or lost.
    assert src_a.read_text(encoding="utf-8") == "AAA"
    assert src_b.read_text(encoding="utf-8") == "BBB"
    assert not (tmp_path / "MyKit.XML").exists()


def test_rename_onto_existing_file_is_blocked(tmp_path):
    src = _kit(tmp_path, "KIT000.XML", "SOURCE")
    existing = _kit(tmp_path, "KIT001.XML", "EXISTING")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src, "kit_manager", new_name="KIT001.XML"))

    report = store.apply_all()

    assert report.success == 0
    assert report.failed == 1
    assert src.exists()
    assert src.read_text(encoding="utf-8") == "SOURCE"
    # The pre-existing file must survive with its original content.
    assert existing.read_text(encoding="utf-8") == "EXISTING"


def test_rename_without_collision_still_succeeds(tmp_path):
    src = _kit(tmp_path, "KIT000.XML", "SOURCE")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src, "kit_manager", new_name="RenamedKit.XML"))

    report = store.apply_all()

    assert report.success == 1
    assert report.failed == 0
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

    report = store.apply_all()

    assert report.success == 1
    assert report.failed == 0
    assert not target.exists()

    trashed = list(trash_root.glob("KIT000*"))
    assert len(trashed) == 1
    assert trashed[0].read_text(encoding="utf-8") == "IMPORTANT DATA"
    assert report.trashed == [(target, trashed[0])]

    history.restore_from_trash(report.trashed[0][1], report.trashed[0][0])
    assert target.read_text(encoding="utf-8") == "IMPORTANT DATA"


def test_rename_chain_moves_the_occupant_first(tmp_path):
    src_a = _kit(tmp_path, "A.XML", "AAA")
    src_b = _kit(tmp_path, "B.XML", "BBB")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src_a, "kit_manager", new_name="B.XML"))
    store.add(PendingChange(ChangeType.RENAME, src_b, "kit_manager", new_name="C.XML"))

    report = store.apply_all()

    assert report.success == 2
    assert report.failed == 0
    assert (tmp_path / "B.XML").read_text(encoding="utf-8") == "AAA"
    assert (tmp_path / "C.XML").read_text(encoding="utf-8") == "BBB"
    assert not src_a.exists()


def test_rename_swap_is_blocked(tmp_path):
    src_a = _kit(tmp_path, "A.XML", "AAA")
    src_b = _kit(tmp_path, "B.XML", "BBB")

    store = StagingStore()
    store.add(PendingChange(ChangeType.RENAME, src_a, "kit_manager", new_name="B.XML"))
    store.add(PendingChange(ChangeType.RENAME, src_b, "kit_manager", new_name="A.XML"))

    report = store.apply_all()

    assert report.success == 0
    assert report.failed == 2
    assert src_a.read_text(encoding="utf-8") == "AAA"
    assert src_b.read_text(encoding="utf-8") == "BBB"
    assert report.failures


def test_peek_then_second_edit_keeps_both_replacements(tmp_path):
    f = tmp_path / "KIT000.XML"
    original = (
        '<sound name="A"><osc1 fileName="SAMPLES/A.wav"></osc1></sound>'
        '<sound name="B"><osc1 fileName="SAMPLES/B.wav"></osc1></sound>'
    )
    f.write_text(original, encoding="utf-8")

    first = file_ops.compute_xml_path_update_at(
        f, "SAMPLES/A.wav", "SAMPLES/A2.wav", 0
    )
    assert first is not None
    store = StagingStore()
    store.add(PendingChange(
        ChangeType.XML_EDIT, f, "kit_manager",
        new_content=first[0], encoding=first[1],
    ))
    assert store.peek(f) == first[0]

    second = file_ops.compute_xml_path_update_at(
        f, "SAMPLES/B.wav", "SAMPLES/B2.wav", 0, source_text=store.peek(f),
    )
    assert second is not None
    store.add(PendingChange(
        ChangeType.XML_EDIT, f, "kit_manager",
        new_content=second[0], encoding=second[1],
    ))
    body = store.peek(f)
    assert 'fileName="SAMPLES/A2.wav"' in body
    assert 'fileName="SAMPLES/B2.wav"' in body
