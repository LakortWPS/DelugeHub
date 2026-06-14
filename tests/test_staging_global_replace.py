"""
Tests for app.core.staging.plan_global_replace

Fix #4: BatchHub's "Globales Ersetzen" used to call update_xml_path()
directly for every XML file across SONGS/KITS/SYNTHS, writing to disk
immediately with no staging/undo - one bad find/replace could corrupt
the entire library with no way back.

plan_global_replace() must:
  - NOT write anything to disk
  - return a PendingChange (XML_EDIT) only for files that actually change
  - handle both '/' and '\\' path-separator variants like update_xml_path
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


# file_ops is imported lazily inside plan_global_replace via `from .file_ops
# import _read_xml` - make sure that resolves to our loaded module too.
file_ops = _load_core_module("file_ops")
sys.modules["app.core.file_ops"] = file_ops

staging = _load_core_module("staging")
plan_global_replace = staging.plan_global_replace
ChangeType = staging.ChangeType


def test_only_matching_files_are_staged(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text("<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>", encoding="utf-8")

    f2 = tmp_path / "b.XML"
    f2.write_text("<sound><fileName>SAMPLES/SNARE/other.wav</fileName></sound>", encoding="utf-8")

    changes = plan_global_replace([f1, f2], "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")

    assert len(changes) == 1
    assert changes[0].file_path == f1
    assert changes[0].change_type == ChangeType.XML_EDIT
    assert "SAMPLES/KICK/new.wav" in changes[0].new_content
    assert "old.wav" not in changes[0].new_content


def test_nothing_written_to_disk(tmp_path):
    f1 = tmp_path / "a.XML"
    original = "<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>"
    f1.write_text(original, encoding="utf-8")

    plan_global_replace([f1], "old.wav", "new.wav")

    # File on disk must be untouched - planning must not write anything.
    assert f1.read_text(encoding="utf-8") == original


def test_backslash_variant_is_handled(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text(r"<sound><fileName>SAMPLES\KICK\old.wav</fileName></sound>", encoding="utf-8")

    changes = plan_global_replace([f1], "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")

    assert len(changes) == 1
    assert "SAMPLES\\KICK\\new.wav" in changes[0].new_content


def test_no_match_produces_no_change(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text("<sound><fileName>SAMPLES/SNARE/other.wav</fileName></sound>", encoding="utf-8")

    changes = plan_global_replace([f1], "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")

    assert changes == []


def test_unreadable_file_is_skipped(tmp_path):
    missing = tmp_path / "does_not_exist.XML"
    changes = plan_global_replace([missing], "old.wav", "new.wav")
    assert changes == []
