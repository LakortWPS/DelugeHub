"""
DelugeHub — SD Card Scanner
Scans a Deluge SD card root directory and builds a full SDCardIndex.
Runs in a QThread so the UI stays responsive.
"""
from pathlib import Path
import logging

from PySide6.QtCore import QThread, Signal

from .models import SDCardIndex, Sample
from .xml_parser import parse_song, parse_kit, parse_synth

log = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg"}


class ScanWorker(QThread):
    """Background worker that scans the SD card."""

    progress = Signal(int, str)      # percent, status message
    finished = Signal(object)        # SDCardIndex
    error = Signal(str)

    def __init__(self, root_path: Path):
        super().__init__()
        self.root_path = root_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            index = self._scan()
            if not self._cancelled:
                self.finished.emit(index)
        except Exception as e:
            self.error.emit(str(e))

    def _scan(self) -> SDCardIndex:
        root = self.root_path
        index = SDCardIndex(root_path=root)

        # --- Collect all files first ---
        self.progress.emit(5, "Sammle Dateien…")
        song_files = _find_files(root / "SONGS")
        kit_files  = _find_files(root / "KITS")
        synth_files = _find_files(root / "SYNTHS")
        sample_files = _find_audio_files(root / "SAMPLES")

        total = len(song_files) + len(kit_files) + len(synth_files) + len(sample_files)
        done = 0

        # --- Parse Songs ---
        self.progress.emit(10, f"Parse {len(song_files)} Songs…")
        for f in song_files:
            if self._cancelled:
                return index
            song = parse_song(f, root)
            if song:
                index.songs.append(song)
            else:
                index.scan_errors.append(f"Fehler beim Parsen: {f.name}")
            done += 1
            pct = 10 + int((done / max(total, 1)) * 60)
            self.progress.emit(pct, f"Song: {f.stem}")

        # --- Parse Kits ---
        self.progress.emit(35, f"Parse {len(kit_files)} Kits…")
        for f in kit_files:
            if self._cancelled:
                return index
            kit = parse_kit(f, root)
            if kit:
                index.kits.append(kit)
            else:
                index.scan_errors.append(f"Fehler beim Parsen: {f.name}")
            done += 1
            pct = 10 + int((done / max(total, 1)) * 60)
            self.progress.emit(pct, f"Kit: {f.stem}")

        # --- Parse Synths ---
        self.progress.emit(55, f"Parse {len(synth_files)} Synths…")
        for f in synth_files:
            if self._cancelled:
                return index
            synth = parse_synth(f, root)
            if synth:
                index.synths.append(synth)
            else:
                index.scan_errors.append(f"Fehler beim Parsen: {f.name}")
            done += 1
            pct = 10 + int((done / max(total, 1)) * 60)
            self.progress.emit(pct, f"Synth: {f.stem}")

        # --- Index Samples ---
        self.progress.emit(72, f"Indexiere {len(sample_files)} Samples…")
        sample_index = {}
        for f in sample_files:
            if self._cancelled:
                return index
            rel = str(f.relative_to(root)).replace("\\", "/")
            s = Sample(
                file_path=f,
                name=f.name,
                size_bytes=f.stat().st_size if f.exists() else 0,
            )
            index.samples.append(s)
            sample_index[rel.lower()] = s
            done += 1
            pct = 10 + int((done / max(total, 1)) * 60)
            self.progress.emit(pct, f"Sample: {f.name}")

        # --- Cross-reference: mark which samples are used ---
        self.progress.emit(85, "Erstelle Referenz-Index…")
        _build_usage_index(index, sample_index)

        self.progress.emit(100, "Scan abgeschlossen.")
        return index


def _find_files(folder: Path, extensions: frozenset = frozenset({".xml"})) -> list[Path]:
    """Return all files inside folder whose suffix (lowercased) is in extensions."""
    if not folder.exists():
        return []
    result = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in extensions:
            result.append(f)
    return sorted(result)


def _find_audio_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    result = []
    for f in folder.rglob("*"):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            result.append(f)
    return sorted(result)


def _build_usage_index(index: SDCardIndex, sample_index: dict):
    """Mark each sample with which files reference it."""
    def process_refs(refs, source_path):
        for ref in refs:
            key = ref.path.replace("\\", "/").lstrip("/").lower()
            if key in sample_index:
                sample_index[key].referenced_by.append(source_path)

    for s in index.songs:
        process_refs(s.sample_refs, s.file_path)
    for k in index.kits:
        process_refs(k.sample_refs, k.file_path)
    for sy in index.synths:
        process_refs(sy.sample_refs, sy.file_path)
