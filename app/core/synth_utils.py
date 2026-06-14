"""
DelugeHub — Synth value helpers and randomization.

Pure, UI-independent helpers shared by the Synth Editor.
"""
import random
import re


# ── Deluge value helpers ───────────────────────────────────────────────────
def hex_to_norm(hex_str: str) -> float:
    """Convert Deluge hex param (0x00000000-0xFFFFFFFF) to 0.0-1.0."""
    try:
        val = int(hex_str, 16) & 0xFFFFFFFF
        return val / 0xFFFFFFFF
    except Exception:
        return 0.5


def norm_to_hex(val: float) -> str:
    """Convert 0.0-1.0 to Deluge hex string."""
    val = max(0.0, min(1.0, val))
    return f"0x{int(val * 0xFFFFFFFF):08X}"


def rand_hex(lo: float = 0.0, hi: float = 1.0) -> str:
    return norm_to_hex(random.uniform(lo, hi))


def randomize_synth_xml(text: str, rand_tags: list[str],
                         lo: float = 0.05, hi: float = 0.95,
                         osc_types: list[str] | None = None) -> str:
    """
    Return a copy of `text` with every hex value inside the given tags
    replaced by an independently-randomized value, and (optionally) the
    first <type> element set to a random oscillator type.

    Each matched tag occurrence gets its OWN random value — e.g. if both
    <pan> (osc1) and a second <pan> (osc2) appear in the XML, they are
    randomized independently rather than sharing a single value computed
    once per tag name.
    """
    for tag in rand_tags:
        pattern = re.compile(rf'(<{tag}>)\s*0x[0-9A-Fa-f]+\s*(</{tag}>)')
        text = pattern.sub(lambda m: f"{m.group(1)}{rand_hex(lo, hi)}{m.group(2)}", text)

    if osc_types:
        new_type = random.choice(osc_types)
        text = re.sub(r'(<type>)(square|sine|saw|triangle)(</type>)',
                       rf'\g<1>{new_type}\3', text, count=1)

    return text
