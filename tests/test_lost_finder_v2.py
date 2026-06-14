"""
Tests for app.core.lost_finder

Fix #1: CSV export of missing-sample reports must always produce
valid, machine-readable CSV - previously a manual f-string built rows
with a missing closing quote, corrupting the file for any consumer.
"""
import csv
import io
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


lost_finder = _load_core_module("lost_finder")
MissingRef = lost_finder.MissingRef
build_missing_samples_csv = lost_finder.build_missing_samples_csv


def make_refs():
    r1 = MissingRef(
        xml_file=Path("Deluge files/SONGS/Track 01.XML"),
        xml_type="song",
        broken_path="SAMPLES/AMBIENCE/missing, sample.wav",
        match=Path("Deluge files/SAMPLES/AMBIENCE/missing, sample.wav"),
        match_confidence="exact",
    )
    r2 = MissingRef(
        xml_file=Path("Deluge files/KITS/01.XML"),
        xml_type="kit",
        broken_path='SAMPLES/weird"name.wav',
        match=None,
        match_confidence="none",
    )
    return [r1, r2]


def test_csv_rows_have_correct_field_count():
    refs = make_refs()
    csv_text = build_missing_samples_csv(refs)
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    assert len(rows) == 3
    header, row1, row2 = rows

    assert header == ["XML-Datei", "Typ", "Fehlender Pfad", "Match", "Konfidenz", "Status"]

    for row in rows:
        assert len(row) == 6

    assert row1[2] == "SAMPLES/AMBIENCE/missing, sample.wav"
    assert row1[5] == "Bereit"

    assert row2[2] == 'SAMPLES/weird"name.wav'
    assert row2[5] == "Offen"


def test_empty_refs_produce_header_only():
    csv_text = build_missing_samples_csv([])
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0][0] == "XML-Datei"
