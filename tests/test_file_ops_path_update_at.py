"""
Tests for app.core.file_ops.compute_xml_path_update_at

kit_manager._reassign_pad used compute_xml_path_update() (whole-file,
ALL occurrences) to repoint one pad's sample reference. If two pads
reference the exact same sample file - a common case, e.g. two pads
both using the same kick sample - reassigning just one pad silently
changed EVERY pad using that sample, since old_rel isn't unique to the
pad being edited.

compute_xml_path_update_at() fixes this by replacing only the n-th
(0-based, document-order) occurrence of old_rel, so the caller can target
exactly the pad it means to change.
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
compute_xml_path_update_at = file_ops.compute_xml_path_update_at


def test_reassigning_one_pad_does_not_touch_another_pad_with_same_sample(tmp_path):
    f = tmp_path / "KIT000.XML"
    original = (
        '<sound name="Pad1"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
        '<sound name="Pad2"><osc1 type="square"></osc1></sound>'
        '<sound name="Pad3"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
    )
    f.write_text(original, encoding="utf-8")

    # Pad3 is the 2nd (0-based index 1) occurrence of kick.wav in document order.
    result = compute_xml_path_update_at(
        f, "SAMPLES/KICK/kick.wav", "SAMPLES/SNARE/snare.wav", occurrence_index=1
    )

    assert result is not None
    new_text, _enc = result
    assert new_text == (
        '<sound name="Pad1"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
        '<sound name="Pad2"><osc1 type="square"></osc1></sound>'
        '<sound name="Pad3"><osc1 fileName="SAMPLES/SNARE/snare.wav"></osc1></sound>'
    )
    # Pad1's identical reference must be untouched.
    assert new_text.count("SAMPLES/KICK/kick.wav") == 1


def test_occurrence_index_zero_targets_the_first_pad(tmp_path):
    f = tmp_path / "KIT000.XML"
    original = (
        '<sound name="Pad1"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
        '<sound name="Pad3"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
    )
    f.write_text(original, encoding="utf-8")

    result = compute_xml_path_update_at(
        f, "SAMPLES/KICK/kick.wav", "SAMPLES/SNARE/snare.wav", occurrence_index=0
    )

    assert result is not None
    new_text, _enc = result
    assert new_text == (
        '<sound name="Pad1"><osc1 fileName="SAMPLES/SNARE/snare.wav"></osc1></sound>'
        '<sound name="Pad3"><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>'
    )


def test_backslash_variant_is_matched_and_replaced_with_matching_style(tmp_path):
    f = tmp_path / "KIT000.XML"
    original = r'<sound><osc1 fileName="SAMPLES\KICK\kick.wav"></osc1></sound>'
    f.write_text(original, encoding="utf-8")

    result = compute_xml_path_update_at(
        f, "SAMPLES/KICK/kick.wav", "SAMPLES/SNARE/snare.wav", occurrence_index=0
    )

    assert result is not None
    new_text, _enc = result
    assert r'SAMPLES\SNARE\snare.wav' in new_text


def test_out_of_range_occurrence_index_returns_none(tmp_path):
    f = tmp_path / "KIT000.XML"
    f.write_text(
        '<sound><osc1 fileName="SAMPLES/KICK/kick.wav"></osc1></sound>', encoding="utf-8"
    )

    result = compute_xml_path_update_at(
        f, "SAMPLES/KICK/kick.wav", "SAMPLES/SNARE/snare.wav", occurrence_index=1
    )
    assert result is None


def test_missing_file_returns_none():
    missing = Path("/nonexistent/KIT000.XML")
    result = compute_xml_path_update_at(missing, "a", "b", occurrence_index=0)
    assert result is None
