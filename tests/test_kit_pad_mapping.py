"""
Tests for app.core.xml_parser.map_kit_pads_to_samples / parse_kit.pad_refs

Fix #6: kit_manager._show_kit_pads (and _on_pad_click / _reassign_pad) used
kit.sample_refs[:16] to populate the 16 pad slots. sample_refs is built by
_collect_sample_refs(), which walks the WHOLE XML tree and dedupes by path
in first-seen order - it is NOT aligned with pad positions:

  - A kit with 16 sounds but where pad 3 reuses the same sample as pad 1
    only has 15 entries in sample_refs (deduped), so every pad from #3
    onward shows the WRONG sample.
  - A kit where pad 1 has no sample (e.g. a synth/MIDI row) shifts every
    later pad's sample display by one slot.

map_kit_pads_to_samples() must instead walk the <sound>/<kitRow> elements
in document order and return one entry per pad slot (None if that pad has
no sample reference), so kit.pad_refs[i] always corresponds to pad i.
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


xml_parser = _load_core_module("xml_parser")
map_kit_pads_to_samples = xml_parser.map_kit_pads_to_samples
parse_kit = xml_parser.parse_kit


# Kit with 3 pads:
#   pad 0: osc1 -> KICK/kick.wav
#   pad 1: synth pad, no sample reference at all
#   pad 2: osc1 -> KICK/kick.wav  (DUPLICATE of pad 0 -> dropped by _collect_sample_refs's dedup)
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


def _make_root(text):
    import xml.etree.ElementTree as ET
    import re
    body = re.sub(r'<\?xml[^?]*\?>\s*', '', text, count=1)
    wrapper = ET.fromstring(f'<_deluge_root_>{body}</_deluge_root_>')
    for child in wrapper:
        if child.tag not in ("firmwareVersion", "earliestCompatibleFirmware"):
            return child
    return None


def test_pad_refs_aligned_with_pad_positions(tmp_path):
    root = _make_root(KIT_XML)
    pad_refs = map_kit_pads_to_samples(root, tmp_path, max_pads=16)

    assert len(pad_refs) == 16

    # Pad 0 has a sample.
    assert pad_refs[0] is not None
    assert pad_refs[0].path == "SAMPLES/KICK/kick.wav"

    # Pad 1 has NO sample - must be None, not shifted from pad 2/3.
    assert pad_refs[1] is None

    # Pad 2 has the SAME sample as pad 0 (duplicate). Even though
    # _collect_sample_refs would dedupe this away, pad_refs must still
    # report it for pad 2 because it's a real reference on that pad.
    assert pad_refs[2] is not None
    assert pad_refs[2].path == "SAMPLES/KICK/kick.wav"

    # Remaining slots (no sound elements) are None.
    assert all(r is None for r in pad_refs[3:])


def test_sample_refs_dedup_would_misalign_naive_indexing(tmp_path):
    """Sanity check that demonstrates the bug map_kit_pads_to_samples fixes:
    sample_refs (deduped, flat) has fewer entries than there are pads, so
    naive sample_refs[i] indexing would misalign pad 2's display."""
    root = _make_root(KIT_XML)
    sample_refs = xml_parser._collect_sample_refs(root, tmp_path)

    # Only ONE unique sample path across all 3 pads (deduped).
    assert len(sample_refs) == 1
    # But there are 3 pads -> naive sample_refs[2] would be out of range /
    # would not exist, proving sample_refs cannot be used for pad display.
    assert len(sample_refs) < 3


def test_parse_kit_populates_pad_refs(tmp_path):
    f = tmp_path / "KIT001.XML"
    f.write_text(KIT_XML, encoding="utf-8")

    kit = parse_kit(f, tmp_path)
    assert kit is not None
    assert kit.pad_count == 3
    assert len(kit.pad_refs) == 16
    assert kit.pad_refs[0].path == "SAMPLES/KICK/kick.wav"
    assert kit.pad_refs[1] is None
    assert kit.pad_refs[2].path == "SAMPLES/KICK/kick.wav"


def test_kit_with_more_than_16_sounds_truncates(tmp_path):
    sounds = "".join(
        f'<sound name="Pad{i}"><osc1 fileName="SAMPLES/S/{i}.wav"></osc1></sound>\n'
        for i in range(20)
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<firmwareVersion>4.1.0</firmwareVersion>\n'
        '<kit name="Big">\n'
        f'  <soundSources>\n{sounds}  </soundSources>\n'
        '</kit>\n'
    )
    root = _make_root(xml)
    pad_refs = map_kit_pads_to_samples(root, tmp_path, max_pads=16)
    assert len(pad_refs) == 16
    assert pad_refs[15].path == "SAMPLES/S/15.wav"
