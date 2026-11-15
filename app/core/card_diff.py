"""
DelugeHub — Compare a scanned SD card to a backup ZIP.

Stdlib only (zipfile + zlib). backup.py imports PySide6, so this module
stays importable from the CI which only has lxml and pytest.

Nothing here writes to the card or to the ZIP.
"""
import zlib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


# Names BackupWorker skips, plus the two DelugeHub sidecar files.
# Duplicated here so this module does not import app.core.backup (PySide6).
_IGNORE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "FIRMWARE.BIN",
    "delugyhub_backup.json",
    ".delugyhub_pending.json",
}

_TYPE_BY_PREFIX = (
    ("SONGS/", "Song"),
    ("KITS/", "Kit"),
    ("SYNTHS/", "Synth"),
    ("SAMPLES/", "Sample"),
)


@dataclass
class DiffRow:
    kind: str          # "neu" | "fehlt" | "geändert"
    file_type: str     # "Song" | "Kit" | "Synth" | "Sample"
    rel_path: str


@dataclass
class CardDiff:
    rows: list = field(default_factory=list)
    unchanged: int = 0
    cancelled: bool = False


def _norm_rel(name: str) -> str:
    rel = name.replace("\\", "/").lstrip("/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _ignored(rel: str) -> bool:
    if not rel or rel.endswith("/"):
        return True
    return rel.split("/")[-1] in _IGNORE_NAMES


def _matches(rel: str, prefixes) -> bool:
    return any(rel.startswith(prefix) for prefix in prefixes)


def _file_type(rel: str) -> str:
    for prefix, label in _TYPE_BY_PREFIX:
        if rel.startswith(prefix):
            return label
    return ""


def _crc32_file(path: Path) -> int:
    crc = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
    return crc & 0xFFFFFFFF


def diff_card_against_zip(
    sd_root: Path,
    zip_path: Path,
    prefixes,
    is_cancelled=None,
) -> CardDiff:
    """
    Classify files under ``prefixes`` as new, missing or changed.

    Identical files (same size and CRC-32) are counted on ``unchanged``
    and left out of ``rows``. ``delugyhub_backup.json``,
    ``.delugyhub_pending.json`` and the backup ignore-names produce no row.
    """
    root = Path(sd_root)
    result = CardDiff()
    prefix_list = list(prefixes or [])

    card_files = {}
    if root.exists():
        for path in root.rglob("*"):
            if is_cancelled and is_cancelled():
                result.cancelled = True
                return result
            if not path.is_file():
                continue
            try:
                rel = _norm_rel(str(path.relative_to(root)))
            except ValueError:
                continue
            if _ignored(rel) or not _matches(rel, prefix_list):
                continue
            card_files[rel] = path

    zip_infos = {}
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            for info in archive.infolist():
                if is_cancelled and is_cancelled():
                    result.cancelled = True
                    return result
                rel = _norm_rel(info.filename)
                if _ignored(rel) or not _matches(rel, prefix_list):
                    continue
                zip_infos[rel] = info
    except (OSError, zipfile.BadZipFile):
        return result

    for rel in sorted(set(card_files) | set(zip_infos)):
        if is_cancelled and is_cancelled():
            result.cancelled = True
            result.rows.clear()
            result.unchanged = 0
            return result
        on_card = rel in card_files
        in_zip = rel in zip_infos
        file_type = _file_type(rel)
        if on_card and not in_zip:
            result.rows.append(DiffRow("neu", file_type, rel))
            continue
        if in_zip and not on_card:
            result.rows.append(DiffRow("fehlt", file_type, rel))
            continue
        card_path = card_files[rel]
        info = zip_infos[rel]
        try:
            card_size = card_path.stat().st_size
        except OSError:
            result.rows.append(DiffRow("geändert", file_type, rel))
            continue
        if card_size != info.file_size:
            result.rows.append(DiffRow("geändert", file_type, rel))
            continue
        try:
            card_crc = _crc32_file(card_path)
        except OSError:
            result.rows.append(DiffRow("geändert", file_type, rel))
            continue
        if card_crc != (info.CRC & 0xFFFFFFFF):
            result.rows.append(DiffRow("geändert", file_type, rel))
        else:
            result.unchanged += 1
    return result
