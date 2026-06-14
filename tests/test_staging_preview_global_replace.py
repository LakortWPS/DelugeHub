"""
Tests for app.core.staging.preview_global_replace

Feature: Global Replace Vorschau (Batch Hub) — before staging/writing a
global find/replace, the user sees a list of affected files with the
number of replacements per file.

preview_global_replace() must:
  - NOT write anything to disk
  - return (file_path, count) only for files that actually contain a match
  - count occurrences of both '/' and '\\' path-separator variants,
    matching the normalization used by plan_global_replace
  - skip files that fail to read
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

staging = _load_core_module("staging")
preview_global_replace = staging.preview_global_replace


def test_only_matching_files_are_listed(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text("<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>", encoding="utf-8")

    f2 = tmp_path / "b.XML"
    f2.write_text("<sound><fileName>SAMPLES/SNARE/other.wav</fileName></sound>", encoding="utf-8")

    results = preview_global_replace([f1, f2], "SAMPLES/KICK/old.wav")

    assert len(results) == 1
    assert results[0][0] == f1
    assert results[0][1] == 1


def test_counts_multiple_occurrences(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text(
        "<a><fileName>SAMPLES/KICK/old.wav</fileName>"
        "<b><fileName>SAMPLES/KICK/old.wav</fileName></b></a>",
        encoding="utf-8",
    )

    results = preview_global_replace([f1], "SAMPLES/KICK/old.wav")

    assert results == [(f1, 2)]


def test_nothing_written_to_disk(tmp_path):
    f1 = tmp_path / "a.XML"
    original = "<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>"
    f1.write_text(original, encoding="utf-8")

    preview_global_replace([f1], "old.wav")

    assert f1.read_text(encoding="utf-8") == original


def test_backslash_variant_is_counted(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text(r"<sound><fileName>SAMPLES\KICK\old.wav</fileName></sound>", encoding="utf-8")

    results = preview_global_replace([f1], "SAMPLES/KICK/old.wav")

    assert results == [(f1, 1)]


def test_no_match_produces_no_entry(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text("<sound><fileName>SAMPLES/SNARE/other.wav</fileName></sound>", encoding="utf-8")

    results = preview_global_replace([f1], "SAMPLES/KICK/old.wav")

    assert results == []


def test_unreadable_file_is_skipped(tmp_path):
    missing = tmp_path / "does_not_exist.XML"
    results = preview_global_replace([missing], "old.wav")
    assert results == []


def test_ordering_matches_input(tmp_path):
    f1 = tmp_path / "a.XML"
    f1.write_text("<x>old.wav</x>", encoding="utf-8")
    f2 = tmp_path / "b.XML"
    f2.write_text("<x>old.wav old.wav</x>", encoding="utf-8")

    results = preview_global_replace([f2, f1], "old.wav")

    assert [r[0] for r in results] == [f2, f1]
    assert [r[1] for r in results] == [2, 1]
