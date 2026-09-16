"""
Tests for plan_global_replace()'s XML-validity guard.

"Globales Ersetzen" runs a plain substring find/replace across every XML
in SONGS/KITS/SYNTHS with no structural awareness of XML at all. Before
this fix, a find/replace that happened to strip out all of a file's
content (e.g. find_text matching the file's entire body, or a broad
find_text with an empty replace_text) would still get staged and, on
Save, written to disk as syntactically empty/broken XML - something the
Deluge could fail to load.

plan_global_replace() now validates each result the same way the rest of
the app validates a Deluge XML file (the robust parser used everywhere
else, including its lxml recovery pass for firmware quirks) and skips
staging any file whose result would no longer be parseable.
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

xml_parser = _load_core_module("xml_parser")
sys.modules["app.core.xml_parser"] = xml_parser

staging = _load_core_module("staging")
plan_global_replace = staging.plan_global_replace


def test_replace_that_would_empty_the_file_is_not_staged(tmp_path):
    f = tmp_path / "a.XML"
    original = '<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>'
    f.write_text(original, encoding="utf-8")

    # A user accidentally selects (and replaces with nothing) the file's
    # entire meaningful content - the worst realistic global-replace slip.
    changes = plan_global_replace([f], original, "")

    assert changes == []
    # Original file on disk must still be untouched (plan_* never writes).
    assert f.read_text(encoding="utf-8") == original


def test_guard_is_per_file_not_batch_wide(tmp_path):
    # a.XML: the find text is its entire content -> replacing it with ""
    # empties the file, so it must be skipped.
    would_break = tmp_path / "a.XML"
    would_break.write_text('SAMPLES/KICK/old.wav', encoding="utf-8")

    # b.XML: the find text is only a small part of a larger, otherwise
    # untouched document -> the result stays valid XML and must still be
    # staged normally.
    stays_valid = tmp_path / "b.XML"
    stays_valid.write_text(
        '<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>', encoding="utf-8"
    )

    changes = plan_global_replace([would_break, stays_valid], "SAMPLES/KICK/old.wav", "")

    assert len(changes) == 1
    assert changes[0].file_path == stays_valid


def test_normal_path_rename_replace_is_unaffected(tmp_path):
    f = tmp_path / "a.XML"
    f.write_text(
        '<sound><fileName>SAMPLES/KICK/old.wav</fileName></sound>', encoding="utf-8"
    )

    changes = plan_global_replace([f], "SAMPLES/KICK/old.wav", "SAMPLES/KICK/new.wav")

    assert len(changes) == 1
    assert "SAMPLES/KICK/new.wav" in changes[0].new_content
