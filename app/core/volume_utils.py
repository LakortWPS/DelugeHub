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
