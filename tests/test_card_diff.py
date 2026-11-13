"""Card vs backup ZIP: new, missing, changed, and an unchanged counter."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._helpers import load_core_module

card_diff = load_core_module("card_diff")
diff_card_against_zip = card_diff.diff_card_against_zip

PREFIXES = ("SONGS/", "KITS/", "SYNTHS/", "SAMPLES/")


def test_four_classes_and_sidecar_is_ignored(tmp_path):
    root = tmp_path / "sd"
    (root / "SONGS").mkdir(parents=True)
    (root / "SAMPLES").mkdir()
    (root / "SONGS" / "same.XML").write_bytes(b"<song>same</song>")
    (root / "SONGS" / "changed.XML").write_bytes(b"<song>AAAA</song>")
    (root / "SAMPLES" / "new.wav").write_bytes(b"NEWWAVDATA")
    (root / "delugyhub_backup.json").write_text("{}", encoding="utf-8")

    zip_path = tmp_path / "backup.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("SONGS/same.XML", b"<song>same</song>")
        archive.writestr("SONGS/changed.XML", b"<song>BBBB</song>")
        archive.writestr("SONGS/gone.XML", b"<song>gone</song>")
        archive.writestr("delugyhub_backup.json", b"{}")
        archive.writestr("SAMPLES/old.wav", b"OLD")

    result = diff_card_against_zip(root, zip_path, PREFIXES)
    seen = {(row.rel_path, row.kind) for row in result.rows}

    assert ("SAMPLES/new.wav", "neu") in seen
    assert ("SONGS/gone.XML", "fehlt") in seen
    assert ("SONGS/changed.XML", "geändert") in seen
    assert ("SAMPLES/old.wav", "fehlt") in seen
    assert not any(row.rel_path == "SONGS/same.XML" for row in result.rows)
    assert not any("delugyhub_backup.json" in row.rel_path for row in result.rows)
    assert result.unchanged == 1
    assert len(result.rows) == 4
