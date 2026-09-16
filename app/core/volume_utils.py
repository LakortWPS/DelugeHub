"""
DelugeHub — Volume Utilities
Deluge-spezifische Volume-Kodierung: 32-Bit-Hex ↔ Display-Wert (0–50).

Deluge speichert Lautstärken als vorzeichenbehaftete 32-Bit-Integer in Hex:
    display(0–50) = ((signed_int32 + 2^31) / (2^32 - 1)) * 50
    display 40    ≈ 0x4CCCCCCC
    display 50    =  0x7FFFFFFF  (Maximum)
    display  0    =  0x80000000  (Minimum / Stille)
"""


def vol_to_display(hex_str: str) -> float:
    """Deluge-Hex-Volume-String → Anzeigewert 0–50."""
    v = int(hex_str, 16)
    if v >= 0x80000000:
        v -= 0x100000000          # unsigned → signed
    return ((v + 2_147_483_648) / 4_294_967_295) * 50


def display_to_vol(display: float) -> str:
    """Anzeigewert 0–50 → Deluge-Hex-Volume-String."""
    amp = max(0.0, min(1.0, display / 50.0))
    v = int(amp * 4_294_967_295) - 2_147_483_648
    return f"0x{v & 0xFFFFFFFF:08X}"


def vol_to_amp(hex_str: str) -> float:
    """Deluge-Hex-Volume-String → lineare Amplitude 0.0–1.0."""
    v = int(hex_str, 16)
    if v >= 0x80000000:
        v -= 0x100000000
    return (v + 2_147_483_648) / 4_294_967_295


def amp_to_vol(amp: float) -> str:
    """Lineare Amplitude 0.0–1.0 → Deluge-Hex-Volume-String."""
    amp = max(0.0, min(1.0, amp))
    v = int(amp * 4_294_967_295) - 2_147_483_648
    return f"0x{v & 0xFFFFFFFF:08X}"


def apply_sequential_replacements(text: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    """
    Apply each (old, new) pair in `replacements` to `text`, one occurrence
    each, in the given order — never searching before the position where
    the previous replacement landed.

    Several pads/clips in the same Kit/Song XML can share the exact same
    literal volume tag text (e.g. an untouched default value repeated on
    multiple pads). A plain `text.replace(old, new, 1)` call always hits
    the FIRST occurrence in the whole text, so calling it once per pad
    without tracking where earlier edits already landed can silently
    rewrite the wrong pad's volume. Anchoring the search position after
    each match keeps every replacement scoped to "the next not-yet-
    consumed occurrence", matching the left-to-right document order the
    caller collected `replacements` in (i.e. the same order as
    `soundSources.findall("sound")`/etc.).

    Returns the modified text and how many replacements actually matched.
    """
    changed = 0
    search_pos = 0
    for old, new in replacements:
        idx = text.find(old, search_pos)
        if idx == -1:
            continue
        text = text[:idx] + new + text[idx + len(old):]
        search_pos = idx + len(new)
        changed += 1
    return text, changed
