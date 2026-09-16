"""
Tests for app.core.volume_utils.apply_sequential_replacements.

kit_manager._cap_pad_volumes and batch_hub._do_cap_pad_volumes called
`sources_block.replace(old_tag, new_tag, 1)` once per over-threshold pad,
threading the progressively-edited block through the loop. For two pads
sharing the exact same volume hex, this empirically still lands each
replacement on the correct, distinct pad (verified below) - because an
already-replaced occurrence disappears from the search space, so the next
`.replace(..., 1)` call naturally finds the next one.

The real fragility is structural, not something reproduced here: the
reset-to-0 search has no anchor, so it can only be trusted to stay
correct as long as every `old_tag` occurrence in the block belongs to
the pad caller intended (same order as `caps`/`findall("sound")`
produced them). apply_sequential_replacements removes that assumption
entirely by tracking a monotonically advancing search position, so each
replacement only ever consumes the next not-yet-processed occurrence in
document order - matching the already-safe pattern kit_manager's
_normalize_volumes used, and consolidating three copies of nearly
identical replace-loop code (kit_manager x2, batch_hub) into one place.
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
apply_sequential_replacements = volume_utils.apply_sequential_replacements


def test_two_pads_with_identical_volume_both_get_updated():
    # Pad1 and Pad3 share the exact same over-threshold hex value; Pad2 is
    # a different, unrelated value that must stay untouched.
    block = (
        '<sound name="Pad1"><defaultParams volume="0x7FFFFFFF"/></sound>'
        '<sound name="Pad2"><defaultParams volume="0x11111111"/></sound>'
        '<sound name="Pad3"><defaultParams volume="0x7FFFFFFF"/></sound>'
    )
    replacements = [
        ('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"'),
        ('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"'),
    ]

    new_block, changed = apply_sequential_replacements(block, replacements)

    assert changed == 2
    assert new_block == (
        '<sound name="Pad1"><defaultParams volume="0x4CCCCCCC"/></sound>'
        '<sound name="Pad2"><defaultParams volume="0x11111111"/></sound>'
        '<sound name="Pad3"><defaultParams volume="0x4CCCCCCC"/></sound>'
    )


def test_monotonic_search_never_revisits_an_earlier_position():
    # A stale/foreign occurrence of the *new* target value sitting earlier
    # in the block must not confuse the search: apply_sequential_replacements
    # only ever looks forward from where the previous match ended, so it
    # can't be fooled into re-editing something before that point.
    block = (
        '<sound name="Decoy"><defaultParams volume="0x4CCCCCCC"/></sound>'
        '<sound name="Pad1"><defaultParams volume="0x7FFFFFFF"/></sound>'
    )
    replacements = [('volume="0x7FFFFFFF"', 'volume="0x4CCCCCCC"')]

    new_block, changed = apply_sequential_replacements(block, replacements)

    assert changed == 1
    assert new_block == (
        '<sound name="Decoy"><defaultParams volume="0x4CCCCCCC"/></sound>'
        '<sound name="Pad1"><defaultParams volume="0x4CCCCCCC"/></sound>'
    )


def test_no_match_returns_unchanged_text_and_zero_count():
    block = '<sound volume="0x11111111"/>'
    new_block, changed = apply_sequential_replacements(block, [('volume="0xDEADBEEF"', 'x')])
    assert new_block == block
    assert changed == 0


def test_replacements_preserve_unrelated_text():
    block = 'A volume="0xAAAAAAAA" B volume="0xBBBBBBBB" C'
    new_block, changed = apply_sequential_replacements(
        block, [('volume="0xAAAAAAAA"', 'volume="0x00000000"')]
    )
    assert changed == 1
    assert new_block == 'A volume="0x00000000" B volume="0xBBBBBBBB" C'
