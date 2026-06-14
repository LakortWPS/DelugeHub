"""
Tests for app.core.file_ops.compute_xml_path_update

Fix #5: kit_manager._reassign_pad wrote directly to disk via
update_xml_path() with no staging - reassigning a pad could not be
reviewed or undone like every other destructive kit_manager operation
(_rename_selected, _cap_pad_volumes, etc. all use the staging store).

compute_xml_path_update() must:
  - return (new_text, encoding) when old_rel is found and replaced
  - return None (no change) when old_rel is not present
  - NOT write anything to disk
  - update_xml_path() (the direct-write convenience wrapper) must keep
    working and remain consistent with compute_xml_path_update()
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
compute_xml_path_update = file_ops.compute_xml_path_update
update_xml_path = file_ops.update_xml_path


def test_returns_new_text_and_encoding_without_writing(tmp_path):
    f = tmp_path / "kit.XML"
    original = '<sound><osc1 fileName="SAMPLES/KICK/old.wav"></osc1></sound>'
    f.write_text(original, encoding="utf-8")

    result = compute_xml_path_update(f, "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")

    assert result is not None
    new_text, enc = result
    assert "SAMPLES/KICK/new.wav" in new_text
    assert "old.wav" not in new_text
    # _read_xml tries "utf-8-sig" first; for a BOM-less UTF-8 file this still
    # decodes successfully, so that's the encoding reported back.
    assert enc == "utf-8-sig"

    # Must not have touched the file on disk.
    assert f.read_text(encoding="utf-8") == original


def test_returns_none_when_path_not_found(tmp_path):
    f = tmp_path / "kit.XML"
    f.write_text('<sound><osc1 fileName="SAMPLES/SNARE/x.wav"></osc1></sound>', encoding="utf-8")

    result = compute_xml_path_update(f, "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")
    assert result is None


def test_returns_none_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.XML"
    result = compute_xml_path_update(missing, "old.wav", "new.wav")
    assert result is None


def test_update_xml_path_writes_same_content_as_compute(tmp_path):
    f = tmp_path / "kit.XML"
    original = '<sound><osc1 fileName="SAMPLES/KICK/old.wav"></osc1></sound>'
    f.write_text(original, encoding="utf-8")

    result = compute_xml_path_update(f, "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")
    assert result is not None
    expected_text, enc = result

    changed = update_xml_path(f, "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")
    assert changed is True
    # Read back with the SAME encoding _write_xml used, so a "utf-8-sig"
    # BOM written on disk is stripped symmetrically on read.
    assert f.read_text(encoding=enc) == expected_text


def test_update_xml_path_returns_false_when_no_match(tmp_path):
    f = tmp_path / "kit.XML"
    original = '<sound><osc1 fileName="SAMPLES/SNARE/x.wav"></osc1></sound>'
    f.write_text(original, encoding="utf-8")

    changed = update_xml_path(f, "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")
    assert changed is False
    assert f.read_text(encoding="utf-8") == original
