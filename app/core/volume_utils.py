"""
DelugeHub — Volume Utilities
Deluge-spezifische Volume-Kodierung: 32-Bit-Hex ↔ Display-Wert (0–50).

Deluge speichert Lautstärken als vorzeichenbehaftete 32-Bit-Integer in Hex:
    display(0–50) = ((signed_int32 + 2^31) / (2^32 - 1)) * 50
    display 40    ≈ 0x4CCCCCCC
    display 50    =  0x7FFFFFFF  (Maximum)
    display  0    =  0x80000000  (Minimum / Stille)
"""
import re
from typing import Optional


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


# <sound> but not <soundSources>. </sound> but not </soundSources>.
_SOUND_OPEN_RE = re.compile(r"<sound(?=[\s>/])")
_SOUND_CLOSE_RE = re.compile(r"</sound(?=\s*>)")


def _sound_spans(block: str) -> list[tuple[int, int]]:
    """Top-level <sound>…</sound> spans, in document order."""
    spans: list[tuple[int, int]] = []
    pos = 0
    while True:
        match = _SOUND_OPEN_RE.search(block, pos)
        if match is None:
            break
        depth = 1
        i = match.end()
        found_end = None
        while depth > 0:
            nxt_open = _SOUND_OPEN_RE.search(block, i)
            nxt_close = _SOUND_CLOSE_RE.search(block, i)
            if nxt_close is None:
                break
            if nxt_open is not None and nxt_open.start() < nxt_close.start():
                depth += 1
                i = nxt_open.end()
            else:
                depth -= 1
                i = nxt_close.end()
                if depth == 0:
                    found_end = i
        if found_end is None:
            break
        spans.append((match.start(), found_end))
        pos = found_end
    return spans


def _default_params_region(block: str, start: int, end: int) -> Optional[tuple[int, int]]:
    """The <defaultParams> element inside [start, end), including its body."""
    rel = block.find("<defaultParams", start, end)
    if rel < 0:
        return None
    gt = block.find(">", rel, end)
    if gt < 0:
        return None
    if block[gt - 1] == "/":
        return rel, gt + 1
    close = block.find("</defaultParams>", gt, end)
    if close < 0:
        return rel, gt + 1
    return rel, close + len("</defaultParams>")


def replace_default_params_volumes(
    sources_block: str,
    updates: list[Optional[tuple[str, str]]],
) -> tuple[str, int]:
    """
    Apply volume edits inside each sound's own <defaultParams>, in the same
    order as soundSources.findall("sound").

    updates[i] is None when that sound must stay untouched (missing sample,
    already at the target, under the cap). A tuple is the literal to find
    and the literal to write, and it is searched only inside that sound's
    defaultParams element — an earlier sound that shares the same hex is
    not a candidate.

    Returns the modified block and how many sounds actually changed.
    """
    spans = _sound_spans(sources_block)
    text = sources_block
    changed = 0
    last = min(len(spans), len(updates)) - 1
    for i in range(last, -1, -1):
        update = updates[i]
        if not update:
            continue
        old, new = update
        region = _default_params_region(text, spans[i][0], spans[i][1])
        if region is None:
            continue
        ra, rb = region
        segment = text[ra:rb]
        idx = segment.find(old)
        if idx < 0:
            continue
        text = text[: ra + idx] + new + text[ra + idx + len(old) :]
        changed += 1
    return text, changed
