"""Display order for table columns. No Qt imports — safe to load in CI."""
from __future__ import annotations

import re

# Blank and the em dash used for missing values ("—") sort as empty.
_EMPTY = {"", "\u2014"}
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)")
_SIZE_RE = re.compile(
    r"([+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+))\s*([kmg]?b)?",
    re.IGNORECASE,
)
# Same 1024-based steps the tables use when they format KB / MB.
_SIZE_FACTOR = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 ** 2,
    "GB": 1024 ** 3,
}


class _Descending:
    """Reverse one key without reversing the original-index tie break."""

    def __init__(self, value):
        self.value = value

    def __lt__(self, other: _Descending) -> bool:
        return other.value < self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Descending) and self.value == other.value


def natural_key(text, kind: str):
    """Comparable key for ``text``, ``number``, or ``size``.

    Blank and ``—`` return ``None`` (empty). Empty sorts first when
    ascending and last when descending. Equal keys are left for the
    caller to break with the original index.
    """
    raw = "" if text is None else str(text).strip()
    if raw in _EMPTY:
        return None
    if kind == "text":
        return _text_key(raw)
    if kind == "number":
        return _number_key(raw)
    if kind == "size":
        return _size_key(raw)
    raise ValueError(f"unknown sort kind: {kind}")


def sorted_positions(rows, originals, column: int, state: int, kind: str) -> list[int]:
    """Indices of ``rows`` in display order.

    ``state`` 0 keeps ``originals`` (the order from the last fill).
    ``state`` 1 is ascending, ``state`` 2 is descending. Ties keep
    the original index, including when descending.
    """
    if len(rows) != len(originals):
        raise ValueError("rows and originals must have the same length")
    state = int(state)
    if state not in (0, 1, 2):
        raise ValueError("sort state must be 0, 1, or 2")
    positions = list(range(len(rows)))
    if state == 0:
        positions.sort(key=lambda index: originals[index])
        return positions

    def sort_key(index: int):
        key = natural_key(_cell(rows[index], column), kind)
        original = originals[index]
        if state == 1:
            if key is None:
                return (0, 0, original)
            return (1, key, original)
        if key is None:
            return (1, 0, original)
        return (0, _Descending(key), original)

    positions.sort(key=sort_key)
    return positions


def _cell(row, column: int) -> str:
    if column < 0 or column >= len(row):
        return ""
    value = row[column]
    if value is None:
        return ""
    return str(value)


def _text_key(text: str) -> tuple:
    parts = re.split(r"(\d+)", text.casefold())
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _number_key(text: str):
    if not _NUMBER_RE.fullmatch(text):
        return None
    value = float(text.replace(",", "."))
    if value.is_integer():
        return int(value)
    return value


def _size_key(text: str):
    match = _SIZE_RE.fullmatch(text)
    if match is None:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "B").upper()
    value = number * _SIZE_FACTOR[unit]
    if value.is_integer():
        return int(value)
    return value
