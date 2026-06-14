"""
Tests for app.core.synth_utils.randomize_synth_xml

Fix #3: synth_editor._randomize computed ONE rand_hex() value per tag NAME
and substituted it into ALL occurrences of that tag via re.sub with a
static replacement string. A synth XML can contain the same tag multiple
times (e.g. <pan> for osc1 and osc2) - these all received the IDENTICAL
random value instead of being randomized independently.

randomize_synth_xml() must give each tag OCCURRENCE its own random value.
"""
import re
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


synth_utils = _load_core_module("synth_utils")
randomize_synth_xml = synth_utils.randomize_synth_xml
hex_to_norm = synth_utils.hex_to_norm
norm_to_hex = synth_utils.norm_to_hex
rand_hex = synth_utils.rand_hex


SYNTH_XML = (
    "<sound>\n"
    "  <osc1>\n"
    "    <type>square</type>\n"
    "    <pan>0x00000000</pan>\n"
    "  </osc1>\n"
    "  <osc2>\n"
    "    <type>saw</type>\n"
    "    <pan>0x00000000</pan>\n"
    "  </osc2>\n"
    "  <envelope1>\n"
    "    <attack>0x00000000</attack>\n"
    "    <release>0x00000000</release>\n"
    "  </envelope1>\n"
    "</sound>\n"
)

RAND_TAGS = ["attack", "release", "pan"]


def test_duplicate_tags_get_independent_values():
    result = randomize_synth_xml(SYNTH_XML, RAND_TAGS, lo=0.05, hi=0.95)

    pans = re.findall(r"<pan>(0x[0-9A-Fa-f]+)</pan>", result)
    assert len(pans) == 2
    # The previous implementation reused ONE rand_hex() value for every
    # occurrence of a tag - both <pan> values would be identical (and equal
    # to a single sampled hex). With independent randomization, getting the
    # exact same 32-bit hex value twice by chance is astronomically
    # unlikely, so this assertion reliably catches the old bug.
    assert pans[0] != pans[1]


def test_values_are_replaced_and_in_range():
    result = randomize_synth_xml(SYNTH_XML, RAND_TAGS, lo=0.05, hi=0.95)

    for tag in RAND_TAGS:
        for hex_val in re.findall(rf"<{tag}>(0x[0-9A-Fa-f]+)</{tag}>", result):
            norm = hex_to_norm(hex_val)
            assert 0.05 <= norm <= 0.95
            assert hex_val != "0x00000000"


def test_osc_type_randomized():
    osc_types = ["square", "sine", "saw", "triangle"]
    result = randomize_synth_xml(SYNTH_XML, RAND_TAGS, osc_types=osc_types)

    types_found = re.findall(r"<type>(\w+)</type>", result)
    assert len(types_found) == 2
    # Only the FIRST <type> is touched (count=1).
    assert types_found[0] in osc_types
    assert types_found[1] == "saw"


def test_unrelated_tags_untouched():
    result = randomize_synth_xml(SYNTH_XML, RAND_TAGS)
    assert "<osc1>" in result
    assert "<envelope1>" in result


def test_rand_hex_roundtrip():
    h = rand_hex(0.0, 1.0)
    assert h.startswith("0x")
    assert len(h) == 10
    norm = hex_to_norm(h)
    assert 0.0 <= norm <= 1.0
    assert norm_to_hex(norm) == h or abs(hex_to_norm(norm_to_hex(norm)) - norm) < 1e-6
