"""
Tests for volume_utils.replace_default_params_volumes.

Pad volume edits used to search the whole <soundSources> block for the
next copy of a volume literal. An earlier sound that was not in the edit
list (missing sample, under the cap) shared that literal and got rewritten
instead of the sound the caller meant.

updates[i] lines up with the i-th <sound>. None leaves that sound alone.
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


volume_utils = _load_core_module("volume_utils")
replace_default_params_volumes = volume_utils.replace_default_params_volumes


def test_two_pads_with_identical_volume_both_get_updated():
    block = (
        '<sound name="Pad1"><defaultParams volume="0x7FFFFFFF"/></sound>'
        '<sound name="Pad2"><defaultParams volume="0x11111111"/></sound>'
        '<sound name="Pad3"><defaultParams volume="0x7FFFFFFF"/></sound>'
    )
    updates = [
        ('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"'),
        None,
        ('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"'),
    ]

    new_block, changed = replace_default_params_volumes(block, updates)

    assert changed == 2
    assert new_block == (
        '<sound name="Pad1"><defaultParams volume="0x4CCCCCCC"/></sound>'
        '<sound name="Pad2"><defaultParams volume="0x11111111"/></sound>'
        '<sound name="Pad3"><defaultParams volume="0x4CCCCCCC"/></sound>'
    )


def test_skipped_earlier_sound_with_the_same_volume_stays():
    # The first sound is omitted (missing sample / failed analysis) but
    # carries the same hex the second sound is supposed to change.
    block = (
        '<sound name="Missing"><defaultParams volume="0x7FFFFFFF"/></sound>'
        '<sound name="Target"><defaultParams volume="0x7FFFFFFF"/></sound>'
    )
    updates = [
        None,
        ('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"'),
    ]

    new_block, changed = replace_default_params_volumes(block, updates)

    assert changed == 1
    assert '<sound name="Missing"><defaultParams volume="0x7FFFFFFF"/></sound>' in new_block
    assert '<sound name="Target"><defaultParams volume="0x4CCCCCCC"/></sound>' in new_block


def test_volume_outside_default_params_is_not_a_candidate():
    block = (
        '<sound name="Pad1">'
        '<osc1 volume="0x7FFFFFFF"/>'
        '<defaultParams volume="0x7FFFFFFF"/>'
        '</sound>'
    )
    updates = [('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"')]

    new_block, changed = replace_default_params_volumes(block, updates)

    assert changed == 1
    assert '<osc1 volume="0x7FFFFFFF"/>' in new_block
    assert '<defaultParams volume="0x4CCCCCCC"/>' in new_block


def test_no_match_returns_unchanged_text_and_zero_count():
    block = '<sound name="Pad1"><defaultParams volume="0x11111111"/></sound>'
    new_block, changed = replace_default_params_volumes(
        block, [('volume="0xDEADBEEF"', 'volume="0x00000000"')]
    )
    assert new_block == block
    assert changed == 0
