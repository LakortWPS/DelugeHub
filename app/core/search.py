"""
DelugeHub — Global Search

Pure, UI-independent search over a scanned SDCardIndex. Used by the top-bar
search field in main_window.py to find Songs/Kits/Synths/Samples by name or
file path and to figure out which module a result should navigate to.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import SDCardIndex


# Maps a result "kind" to the module key used by MainWindow._navigate()
KIND_TO_MODULE = {
    "song": "song_manager",
    "kit": "kit_manager",
    "synth": "synth_editor",
    "sample": "sample_manager",
}

# Display icons per kind (kept here so the UI layer stays trivial)
KIND_ICON = {
    "song": "🎵",
    "kit": "🥁",
    "synth": "🎹",
    "sample": "📁",
}


@dataclass
class SearchResult:
    kind: str          # "song" | "kit" | "synth" | "sample"
    name: str
    file_path: Path
    module_key: str


def search_index(index: SDCardIndex, query: str, limit: int = 20) -> list[SearchResult]:
    """
    Search Songs/Kits/Synths/Samples in `index` for `query`.

    Matches case-insensitively against the item's name and its file path.
    Returns at most `limit` results, ordered: songs, kits, synths, samples,
    each group in the order they appear in the index.

    Returns an empty list if `index` is None or `query` is blank.
    """
    if index is None:
        return []

    q = query.strip().lower()
    if not q:
        return []

    results: list[SearchResult] = []

    def _matches(name: str, file_path: Path) -> bool:
        return q in name.lower() or q in str(file_path).lower()

    for song in index.songs:
        if len(results) >= limit:
            return results
        if _matches(song.name, song.file_path):
            results.append(SearchResult("song", song.name, song.file_path, KIND_TO_MODULE["song"]))

    for kit in index.kits:
        if len(results) >= limit:
            return results
        if _matches(kit.name, kit.file_path):
            results.append(SearchResult("kit", kit.name, kit.file_path, KIND_TO_MODULE["kit"]))

    for synth in index.synths:
        if len(results) >= limit:
            return results
        if _matches(synth.name, synth.file_path):
            results.append(SearchResult("synth", synth.name, synth.file_path, KIND_TO_MODULE["synth"]))

    for sample in index.samples:
        if len(results) >= limit:
            return results
        if _matches(sample.name, sample.file_path):
            results.append(SearchResult("sample", sample.name, sample.file_path, KIND_TO_MODULE["sample"]))

    return results


def module_key_for_path(index: Optional[SDCardIndex], path) -> Optional[str]:
    """
    Map an XML path to the module key MainWindow._navigate() expects.

    The lookup goes through the scanned index (songs, then kits, then
    synths), not through the parent folder name. A hit returns
    song_manager, kit_manager or synth_editor. Anything else — including
    a sample path — returns None so the caller can stay on the current
    page.
    """
    if index is None or path is None:
        return None
    try:
        target = Path(path)
    except TypeError:
        return None

    for song in index.songs:
        if song.file_path == target:
            return KIND_TO_MODULE["song"]
    for kit in index.kits:
        if kit.file_path == target:
            return KIND_TO_MODULE["kit"]
    for synth in index.synths:
        if synth.file_path == target:
            return KIND_TO_MODULE["synth"]
    return None
