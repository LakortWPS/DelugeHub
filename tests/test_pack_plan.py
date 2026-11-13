"""Pack plan: selected songs plus only the kits, synths and samples they use."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._helpers import load_core_module

models = load_core_module("models")
load_core_module("file_ops")
xml_parser = load_core_module("xml_parser")

Song = models.Song
Kit = models.Kit
SampleRef = models.SampleRef
SDCardIndex = models.SDCardIndex
build_pack_plan = xml_parser.build_pack_plan
pack_target_rejected = xml_parser.pack_target_rejected


SONG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<song>
  <kit presetName="MyKit">
    <soundSources>
      <sound name="OtherKit">
        <osc1 fileName="SAMPLES/kick.wav"></osc1>
      </sound>
    </soundSources>
  </kit>
</song>
"""


def test_plan_includes_preset_kit_and_sample_not_pad_name(tmp_path):
    root = tmp_path / "sd"
    (root / "SONGS").mkdir(parents=True)
    (root / "KITS").mkdir()
    (root / "SAMPLES").mkdir()

    kick = root / "SAMPLES" / "kick.wav"
    kick.write_bytes(b"KICK")
    song_path = root / "SONGS" / "Tune.XML"
    song_path.write_text(SONG_XML, encoding="utf-8")
    kit_path = root / "KITS" / "MyKit.XML"
    kit_path.write_text("<kit/>", encoding="utf-8")
    other_path = root / "KITS" / "OtherKit.XML"
    other_path.write_text("<kit/>", encoding="utf-8")

    present = SampleRef(path="SAMPLES/kick.wav", abs_path=kick, exists=True)
    missing = SampleRef(
        path="SAMPLES/missing.wav",
        abs_path=root / "SAMPLES" / "missing.wav",
        exists=False,
    )
    song = Song(file_path=song_path, name="Tune", sample_refs=[present, missing])
    index = SDCardIndex(
        root_path=root,
        songs=[song],
        kits=[
            Kit(file_path=kit_path, name="MyKit", sample_refs=[present]),
            Kit(file_path=other_path, name="OtherKit"),
        ],
    )

    plan = build_pack_plan(index, [song])
    rels = {item.rel_path.replace("\\", "/") for item in plan.files}

    assert "SONGS/Tune.XML" in rels
    assert "KITS/MyKit.XML" in rels
    assert "SAMPLES/kick.wav" in rels
    assert "KITS/OtherKit.XML" not in rels
    assert any("missing.wav" in label for label in plan.missing)
    assert not any("missing" in item.rel_path for item in plan.files)
    assert sum(1 for item in plan.files if item.rel_path.endswith("kick.wav")) == 1


def test_unresolved_preset_and_slot_file(tmp_path):
    root = tmp_path / "sd"
    (root / "SONGS").mkdir(parents=True)
    (root / "KITS").mkdir()
    song_path = root / "SONGS" / "Slot.XML"
    song_path.write_text(
        '<song><kit presetSlot="5" presetSubSlot="0"></kit>'
        '<kit presetName="Nope"></kit></song>',
        encoding="utf-8",
    )
    slot_path = root / "KITS" / "KIT005A.XML"
    slot_path.write_text("<kit/>", encoding="utf-8")
    song = Song(file_path=song_path, name="Slot")
    index = SDCardIndex(
        root_path=root,
        songs=[song],
        kits=[Kit(file_path=slot_path, name="KIT005A")],
    )

    plan = build_pack_plan(index, [song])
    rels = {item.rel_path.replace("\\", "/") for item in plan.files}
    assert "KITS/KIT005A.XML" in rels
    assert any(label.startswith("Preset nicht als Datei gefunden") for label in plan.unresolved_presets)


def test_pack_target_rejected_for_card_itself_and_parents(tmp_path):
    root = tmp_path / "sd"
    root.mkdir()
    (root / "SONGS").mkdir()
    other = tmp_path / "other"
    other.mkdir()

    assert pack_target_rejected(root, root) is True
    assert pack_target_rejected(root, root / "SONGS") is True
    assert pack_target_rejected(root, tmp_path) is True
    assert pack_target_rejected(root, other) is False
