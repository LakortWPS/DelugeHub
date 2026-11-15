"""Firmware tag parsing and earliestCompatibleFirmware ordering."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._helpers import load_core_module

load_core_module("models")
load_core_module("file_ops")
xml_parser = load_core_module("xml_parser")

firmware_sort_key = xml_parser.firmware_sort_key
read_firmware_tags = xml_parser.read_firmware_tags
song_needs_newer_firmware = xml_parser.song_needs_newer_firmware
parse_song = xml_parser.parse_song

SIBLING_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<firmwareVersion>4.1.0</firmwareVersion>\n'
    '<earliestCompatibleFirmware>4.0.0-alpha</earliestCompatibleFirmware>\n'
    '<kit name="Test">\n'
    '  <soundSources>\n'
    '    <sound name="Pad1">\n'
    '      <osc1 fileName="SAMPLES/KICK/kick.wav"></osc1>\n'
    '    </sound>\n'
    '  </soundSources>\n'
    '</kit>\n'
)


def test_alpha_sorts_before_beta_before_release():
    alpha = firmware_sort_key("4.1.0-alpha")
    beta = firmware_sort_key("4.1.0-beta")
    rc = firmware_sort_key("4.1.0-rc")
    release = firmware_sort_key("4.1.0")
    assert alpha < beta < rc < release
    assert firmware_sort_key("4.1.0-nightly") == alpha
    assert firmware_sort_key("") is None
    assert firmware_sort_key("   ") is None


def test_read_sibling_tags_and_attributes():
    firmware, earliest = read_firmware_tags(SIBLING_XML)
    assert firmware == "4.1.0"
    assert earliest == "4.0.0-alpha"

    attrs = '<song firmwareVersion="3.1.0" earliestCompatibleFirmware="3.0.0"></song>'
    assert read_firmware_tags(attrs) == ("3.1.0", "3.0.0")
    assert read_firmware_tags("<song></song>") == ("", "")


def test_only_the_strictly_newer_song_is_marked():
    versions = ["4.0.0", "4.1.0-alpha", "4.0.0"]
    marked = []
    for index, version in enumerate(versions):
        others = [v for i, v in enumerate(versions) if i != index]
        if song_needs_newer_firmware(version, others):
            marked.append(index)
    assert marked == [1]
    assert song_needs_newer_firmware("4.1.0", ["4.1.0", "4.1.0"]) is None
    assert song_needs_newer_firmware("4.0.0", []) is None


def test_parse_song_keeps_attribute_firmware(tmp_path):
    path = tmp_path / "SONG.XML"
    path.write_text(
        '<song firmwareVersion="4.2.0" earliestCompatibleFirmware="4.1.0"></song>',
        encoding="utf-8",
    )
    song = parse_song(path, tmp_path)
    assert song is not None
    assert song.firmware_version == "4.2.0"
    assert song.earliest_compatible == "4.1.0"
