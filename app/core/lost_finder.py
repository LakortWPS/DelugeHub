"""
DelugeHub — Lost Sample Finder (Core Logic)
Scans all XML files for broken sample references, finds matches on SD card.
"""
import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

from .models import SDCardIndex, SampleRef

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg"}


@dataclass
class MissingRef:
    """One broken sample reference in one XML file."""
    xml_file: Path           # which XML has the broken ref
    xml_type: str            # "song", "kit", "synth"
    broken_path: str         # the broken path string in the XML
    match: Optional[Path] = None   # auto-matched candidate
    match_confidence: str = ""     # "exact", "fuzzy", "none"
    user_choice: Optional[Path] = None  # manually chosen replacement
    fixed: bool = False

    @property
    def resolution(self) -> Optional[Path]:
        return self.user_choice or self.match

    @property
    def filename(self) -> str:
        return Path(self.broken_path.replace("\\", "/")).name


def build_missing_samples_csv(refs: list[MissingRef]) -> str:
    """
    Build a CSV report of missing sample references as a string.

    Uses the csv module so embedded quotes, commas, or newlines in file
    paths are escaped correctly — the result is always valid, machine-
    readable CSV (fixes a previous bug where manual f-string formatting
    produced rows with an unterminated trailing quote).
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["XML-Datei", "Typ", "Fehlender Pfad", "Match", "Konfidenz", "Status"])
    for ref in refs:
        match_str = str(ref.resolution) if ref.resolution else ""
        status = "Repariert" if ref.fixed else ("Bereit" if ref.resolution else "Offen")
        writer.writerow([
            str(ref.xml_file), ref.xml_type, ref.broken_path,
            match_str, ref.match_confidence, status,
        ])
    return output.getvalue()


def collect_missing_refs(index: SDCardIndex) -> list[MissingRef]:
    """Gather all missing sample references from the index."""
    refs: list[MissingRef] = []
    seen: set[tuple[Path, str]] = set()

    def add(xml_file, xml_type, sample_ref: SampleRef):
        key = (xml_file, sample_ref.path)
        if key not in seen and not sample_ref.exists:
            seen.add(key)
            refs.append(MissingRef(
                xml_file=xml_file,
                xml_type=xml_type,
                broken_path=sample_ref.path,
            ))

    for song in index.songs:
        for sr in song.sample_refs:
            add(song.file_path, "song", sr)

    for kit in index.kits:
        for sr in kit.sample_refs:
            add(kit.file_path, "kit", sr)

    for synth in index.synths:
        for sr in synth.sample_refs:
            add(synth.file_path, "synth", sr)

    return refs


def build_sd_file_index(sd_root: Path) -> dict[str, list[Path]]:
    """
    Build a lowercase-filename → [abs_paths] index of all audio files on SD.
    Scans SAMPLES/ preferentially; falls back to the whole SD root only if
    that folder doesn't exist (avoids false matches from SONGS/KITS/SYNTHS).
    """
    index: dict[str, list[Path]] = {}
    samples_dir = sd_root / "SAMPLES"
    scan_root = samples_dir if samples_dir.exists() else sd_root

    for f in scan_root.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            key = f.name.lower()
            if key not in index:
                index[key] = []
            index[key].append(f)

    return index


def auto_match(ref: MissingRef, file_index: dict[str, list[Path]], sd_root: Path):
    """
    Try to find a matching sample for a broken reference.
    Updates ref.match and ref.match_confidence in place.
    """
    target_name = ref.filename.lower()

    # 1. Exact filename match
    if target_name in file_index:
        candidates = file_index[target_name]
        if len(candidates) == 1:
            ref.match = candidates[0]
            ref.match_confidence = "exact"
            return
        elif len(candidates) > 1:
            # Multiple → pick the one whose relative path is most similar
            best = _best_path_match(ref.broken_path, candidates, sd_root)
            ref.match = best
            ref.match_confidence = "exact_multi"
            return

    # 2. Fuzzy: strip common suffixes/prefixes and try again
    stem = Path(target_name).stem
    fuzzy_matches = []
    for fname, paths in file_index.items():
        fname_stem = Path(fname).stem
        score = _similarity(stem, fname_stem)
        if score >= 0.75:
            for p in paths:
                fuzzy_matches.append((score, p))

    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda x: -x[0])
        ref.match = fuzzy_matches[0][1]
        ref.match_confidence = "fuzzy"
        return

    ref.match = None
    ref.match_confidence = "none"


def auto_match_all(refs: list[MissingRef], sd_root: Path):
    """Run auto_match on every ref in the list."""
    file_index = build_sd_file_index(sd_root)
    for ref in refs:
        if not ref.fixed:
            auto_match(ref, file_index, sd_root)


def _best_path_match(broken_path: str, candidates: list[Path], sd_root: Path) -> Path:
    """Among multiple candidates with same name, pick the closest path."""
    broken_parts = broken_path.replace("\\", "/").lower().split("/")
    best = candidates[0]
    best_score = 0
    for c in candidates:
        try:
            rel = str(c.relative_to(sd_root)).replace("\\", "/").lower()
            parts = rel.split("/")
            # Count common path components
            score = sum(1 for a, b in zip(reversed(broken_parts), reversed(parts)) if a == b)
            if score > best_score:
                best_score = score
                best = c
        except ValueError:
            pass
    return best


def _similarity(a: str, b: str) -> float:
    """Simple character-overlap similarity ratio."""
    if not a or not b:
        return 0.0
    # Longest common subsequence length approximation
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len(shorter) / len(longer)
    # Count matching characters at same positions
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / max(len(a), len(b))


def search_folder_for_missing(refs: list[MissingRef], search_root: Path, sd_root: Path):
    """
    Search a user-specified folder for matches to all missing refs.
    Updates refs with matches found.
    """
    # Build index for the search folder
    local_index: dict[str, list[Path]] = {}
    for f in search_root.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            key = f.name.lower()
            if key not in local_index:
                local_index[key] = []
            local_index[key].append(f)

    for ref in refs:
        if ref.fixed or ref.match:
            continue
        auto_match(ref, local_index, sd_root)
