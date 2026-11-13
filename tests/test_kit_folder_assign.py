"""Assign a folder of WAVs onto kit pads without touching a shared sample twice."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._helpers import load_core_module

load_core_module("models")
load_core_module("file_ops")
xml_parser = load_core_module("xml_parser")

assign_folder_to_pads = xml_parser.assign_folder_to_pads
natural_sort_key = xml_parser.natural_sort_key
map_kit_pads_to_samples = xml_parser.map_kit_pads_to_samples
validate_xml_text = xml_parser.validate_xml_text

KIT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<firmwareVersion>4.1.0</firmwareVersion>\n'
    '<earliestCompatibleFirmware>4.0.0-alpha</earliestCompatibleFirmware>\n'
    '<kit name="Test">\n'
    '  <soundSources>\n'
    '    <sound name="Pad1">\n'
    '      <osc1 fileName="SAMPLES/KICK/kick.wav"></osc1>\n'
    '    </sound>\n'
    '    <sound name="Pad2">\n'
    '      <osc1 type="square"></osc1>\n'
    '    </sound>\n'
    '    <sound name="Pad3">\n'
    '      <osc1 fileName="SAMPLES/KICK/kick.wav"></osc1>\n'
    '    </sound>\n'
    '  </soundSources>\n'
    '</kit>\n'
)


def test_assigning_one_kick_pad_leaves_the_other_kick(tmp_path):
    new_text = assign_folder_to_pads(
        KIT_XML,
        ["SAMPLES/SNARE/snare.wav", "SAMPLES/HAT/hat.wav", None],
    )
    root = xml_parser._parse_xml_robust_text(new_text)
    refs = map_kit_pads_to_samples(root, tmp_path)

    assert refs[0] is not None
    assert refs[0].path.replace("\\", "/") == "SAMPLES/SNARE/snare.wav"
    assert refs[1] is not None
    assert refs[1].path.replace("\\", "/") == "SAMPLES/HAT/hat.wav"
    assert refs[2] is not None
    assert refs[2].path.replace("\\", "/") == "SAMPLES/KICK/kick.wav"
    assert validate_xml_text(new_text) is None


def test_natural_sort_puts_pad2_before_pad10():
    names = ["pad10.wav", "pad2.wav", "pad1.wav"]
    assert sorted(names, key=natural_sort_key) == ["pad1.wav", "pad2.wav", "pad10.wav"]
