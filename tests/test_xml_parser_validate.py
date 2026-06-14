"""
Tests for app.core.xml_parser.validate_xml_file

Fix #2: BatchHub's "Validate all XMLs" used xml.etree.ElementTree.parse()
directly, which raises ParseError("junk after document element") on every
normal firmware-2.0+ Deluge XML file (multiple top-level elements:
<firmwareVersion>, <earliestCompatibleFirmware>, <kit>/<song>/<sound>).
This falsely flagged perfectly valid, Deluge-readable files as broken.

validate_xml_file() must use the same _parse_xml_robust() the rest of the
app uses, so it agrees with what the app (and the Deluge) can actually read.
"""
import sys
import types
import xml.etree.ElementTree as ET
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
validate_xml_file = xml_parser.validate_xml_file

FIRMWARE2_KIT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<firmwareVersion>4.1.0</firmwareVersion>\n'
    '<earliestCompatibleFirmware>4.0.0-alpha</earliestCompatibleFirmware>\n'
    '<kit name="Test">\n'
    '  <soundSources></soundSources>\n'
    '</kit>\n'
)


def test_firmware2_multiroot_xml_is_valid(tmp_path):
    """A normal firmware-2.0+ Deluge XML (multiple top-level elements) must
    be reported as valid, even though ET.parse() would reject it."""
    f = tmp_path / "00.XML"
    f.write_text(FIRMWARE2_KIT_XML, encoding="utf-8")

    # Sanity check: this is exactly the case that broke with ET.parse().
    raised = False
    try:
        ET.parse(f)
    except ET.ParseError:
        raised = True
    assert raised, "expected ET.parse to choke on multi-root XML (sanity check)"

    # The robust validator must accept it.
    assert validate_xml_file(f) is None


def test_empty_file_is_reported_invalid(tmp_path):
    f = tmp_path / "empty.XML"
    f.write_text("", encoding="utf-8")
    err = validate_xml_file(f)
    assert err is not None
    assert isinstance(err, str)


def test_missing_file_is_reported_invalid(tmp_path):
    f = tmp_path / "does_not_exist.XML"
    err = validate_xml_file(f)
    assert err is not None
