"""
DelugeHub — File Operations
All destructive file ops: move, rename, delete samples + auto-update XML references.
"""
import shutil
import logging
from pathlib import Path
from typing import Optional

from .models import SDCardIndex

log = logging.getLogger(__name__)

# Modul-level Cache für XML-Dateilisten (stabil während einer Session)
_xml_file_cache: dict = {}


def invalidate_xml_cache(sd_root=None) -> None:
    """Cache leeren — wird beim Scan-Start aufgerufen."""
    global _xml_file_cache
    if sd_root is None:
        _xml_file_cache.clear()
    else:
        _xml_file_cache.pop(sd_root, None)


# Encodings Deluge firmware is known to write XML files with.
# We try these in order and fall back to latin-1 (which never raises).
_XML_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")


def _read_xml(path: Path) -> tuple[str, str]:
    """
    Read an XML file and return (content, encoding_used).
    Tries UTF-8-BOM, UTF-8, then Latin-1 as a safe fallback.
    Never uses errors='replace', so the round-trip is lossless.
    """
    for enc in _XML_ENCODINGS:
        try:
            return path.read_text(encoding=enc), enc
        except UnicodeDecodeError:
            continue
    # Should be unreachable — latin-1 accepts every byte value.
    raise RuntimeError(f"Could not decode {path} with any known encoding")


def _write_xml(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomarer Schreibvorgang via Temp-Datei + rename."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _all_xml_files(sd_root: Path) -> list[Path]:
    """All XML files across SONGS, KITS, SYNTHS (cached per sd_root)."""
    if sd_root in _xml_file_cache:
        return _xml_file_cache[sd_root]
    xmls = []
    for folder in ("SONGS", "KITS", "SYNTHS"):
        d = sd_root / folder
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() == ".xml":
                    xmls.append(f)
    _xml_file_cache[sd_root] = xmls
    return xmls


# A sample path in Deluge XML is either attribute text (fileName="…") or
# element text (<fileName>…</fileName>). A bare substring match would also
# hit a longer filename that merely starts with the same characters
# (kick.wav inside kick.wav2).
_PATH_BEFORE = {'"', '>'}
_PATH_AFTER = {'"', '<'}


def _path_variants(old_rel: str, new_rel: str) -> tuple[str, str, str, str]:
    old_fwd = old_rel.replace("\\", "/")
    new_fwd = new_rel.replace("\\", "/")
    old_bwd = old_rel.replace("/", "\\")
    new_bwd = new_rel.replace("/", "\\")
    return old_fwd, new_fwd, old_bwd, new_bwd


def _is_bounded_path(text: str, start: int, length: int) -> bool:
    """True when the match sits on an XML attribute or element-text boundary."""
    end = start + length
    before_ok = start > 0 and text[start - 1] in _PATH_BEFORE
    after_ok = end < len(text) and text[end] in _PATH_AFTER
    return before_ok and after_ok


def _next_bounded_path(
    text: str, old_fwd: str, old_bwd: str, pos: int
) -> Optional[tuple[int, int, bool]]:
    """
    Next left-to-right match of old_fwd or old_bwd that is a whole path token.
    Returns (start, length, matched_forward_variant) or None.
    """
    while True:
        idx_fwd = text.find(old_fwd, pos) if old_fwd else -1
        idx_bwd = text.find(old_bwd, pos) if old_bwd and old_bwd != old_fwd else -1
        candidates = []
        if idx_fwd != -1:
            candidates.append((idx_fwd, True, old_fwd))
        if idx_bwd != -1:
            candidates.append((idx_bwd, False, old_bwd))
        if not candidates:
            return None
        idx, is_fwd, matched = min(candidates, key=lambda c: c[0])
        if _is_bounded_path(text, idx, len(matched)):
            return idx, len(matched), is_fwd
        pos = idx + 1


def _replace_bounded_paths(
    text: str, old_fwd: str, new_fwd: str, old_bwd: str, new_bwd: str
) -> str:
    """Replace every bounded occurrence of either slash variant, left to right."""
    parts: list[str] = []
    pos = 0
    while True:
        found = _next_bounded_path(text, old_fwd, old_bwd, pos)
        if found is None:
            parts.append(text[pos:])
            break
        idx, length, is_fwd = found
        parts.append(text[pos:idx])
        parts.append(new_fwd if is_fwd else new_bwd)
        pos = idx + length
    return "".join(parts)


def compute_xml_path_update(xml_file: Path, old_rel: str, new_rel: str) -> Optional[tuple[str, str]]:
    """
    Compute the result of replacing old_rel with new_rel inside xml_file
    (text-based replacement, both forward- and back-slash variants), WITHOUT
    writing anything to disk.

    Only whole path tokens are replaced: the match must be preceded by '"' or
    '>' and followed by '"' or '<'. A shorter path therefore does not rewrite
    the prefix of a longer filename.

    Returns (new_text, encoding) if the replacement would change the file,
    or None if old_rel was not found (no change) or the file could not be
    read. Callers can pass the result into a StagingStore.PendingChange so
    the edit can be reviewed/undone before being written.
    """
    try:
        text, enc = _read_xml(xml_file)
        old_fwd, new_fwd, old_bwd, new_bwd = _path_variants(old_rel, new_rel)
        new_text = _replace_bounded_paths(text, old_fwd, new_fwd, old_bwd, new_bwd)
        if new_text != text:
            return new_text, enc
        return None
    except Exception as e:
        log.error(f"compute_xml_path_update failed for {xml_file}: {e}")
        return None


def update_xml_path(xml_file: Path, old_rel: str, new_rel: str) -> bool:
    """
    Replace old_rel with new_rel inside xml_file (text-based replacement).
    Handles both forward- and back-slash variants.
    Preserves the original file encoding so the Deluge can still read it.
    Writes the change directly to disk (no staging) and returns True if the
    file was modified.
    """
    result = compute_xml_path_update(xml_file, old_rel, new_rel)
    if result is None:
        return False
    text, enc = result
    try:
        _write_xml(xml_file, text, enc)
        return True
    except Exception as e:
        log.error(f"update_xml_path failed for {xml_file}: {e}")
        return False


def _find_nth_path_occurrence(
    text: str, old_fwd: str, old_bwd: str, n: int
) -> Optional[tuple[int, int, bool]]:
    """
    Find the n-th (0-based) bounded occurrence of old_fwd or old_bwd in text,
    scanning strictly left to right across both slash variants combined.
    Returns (start_index, match_length, matched_forward_variant) or None
    if there is no n-th occurrence.
    """
    pos = 0
    count = 0
    while True:
        found = _next_bounded_path(text, old_fwd, old_bwd, pos)
        if found is None:
            return None
        idx, length, is_fwd = found
        if count == n:
            return idx, length, is_fwd
        count += 1
        pos = idx + length


def compute_xml_path_update_at(
    xml_file: Path,
    old_rel: str,
    new_rel: str,
    occurrence_index: int,
    source_text: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """
    Like compute_xml_path_update, but replaces only the occurrence_index-th
    (0-based, left-to-right, forward+backward slash variants combined)
    bounded occurrence of old_rel — not every occurrence, and not a prefix
    of a longer filename.

    Needed wherever old_rel is not guaranteed to be unique to the specific
    element being edited - e.g. two kit pads referencing the exact same
    sample file. A plain compute_xml_path_update() there would repoint
    every pad using that sample, not just the one the caller means to
    change. The caller is responsible for determining occurrence_index
    from the same document-order traversal it used to identify the target
    element (e.g. counting how many earlier pads share the same path).

    source_text, when given, is edited instead of the bytes on disk. Staging
    keeps one pending XML body per file, so a second pad edit has to continue
    from that body. The encoding is still taken from the file on disk when
    it can be read.

    Returns (new_text, encoding) if the occurrence was found and replacing
    it would change the file, or None otherwise.
    """
    try:
        if source_text is None:
            text, enc = _read_xml(xml_file)
        else:
            text = source_text
            try:
                _, enc = _read_xml(xml_file)
            except Exception:
                enc = "utf-8"

        old_fwd, new_fwd, old_bwd, new_bwd = _path_variants(old_rel, new_rel)

        found = _find_nth_path_occurrence(text, old_fwd, old_bwd, occurrence_index)
        if found is None:
            return None
        idx, length, is_fwd = found
        replacement = new_fwd if is_fwd else new_bwd
        new_text = text[:idx] + replacement + text[idx + length:]
        if new_text == text:
            return None
        return new_text, enc
    except Exception as e:
        log.error(f"compute_xml_path_update_at failed for {xml_file}: {e}")
        return None


def find_referencing_xmls(sd_root: Path, rel_path: str) -> list[Path]:
    """Return all XML files that contain rel_path."""
    fwd = rel_path.replace("\\", "/")
    bwd = rel_path.replace("/", "\\")
    results = []
    for xml in _all_xml_files(sd_root):
        try:
            text, _ = _read_xml(xml)
            if fwd in text or bwd in text:
                results.append(xml)
        except Exception:
            pass
    return results


def rename_sample(
    sample_abs: Path, new_name: str, sd_root: Path
) -> tuple[Optional[Path], list[Path]]:
    """
    Rename a sample file and update all XML references.
    The file is renamed FIRST so that a failure during XML updates still
    leaves the SD card in a consistent state (file at new location, XMLs
    may need a follow-up fix — but nothing is lost).
    Returns (new_abs_path, list_of_updated_xmls).
    """
    if not sample_abs.exists():
        return None, []

    new_abs = sample_abs.parent / new_name
    if new_abs.exists():
        log.warning(f"rename_sample: target already exists: {new_abs}")
        return None, []

    old_rel = str(sample_abs.relative_to(sd_root)).replace("\\", "/")
    new_rel = str(new_abs.relative_to(sd_root)).replace("\\", "/")

    # Rename file first — if this fails, XMLs stay correct.
    sample_abs.rename(new_abs)

    # Now update all XML references.
    updated = []
    for xml in _all_xml_files(sd_root):
        if update_xml_path(xml, old_rel, new_rel):
            updated.append(xml)

    log.info(f"Renamed {sample_abs.name} → {new_name} | updated {len(updated)} XMLs")
    return new_abs, updated


def move_sample(
    sample_abs: Path, target_folder: Path, sd_root: Path
) -> tuple[Optional[Path], list[Path]]:
    """
    Move a sample to target_folder and update all XML references.
    The file is moved FIRST so that a failure during XML updates still
    leaves the SD card in a consistent state.
    Returns (new_abs_path, list_of_updated_xmls).
    """
    if not sample_abs.exists():
        return None, []

    new_abs = target_folder / sample_abs.name
    if new_abs == sample_abs:
        return sample_abs, []

    if new_abs.exists():
        log.warning(f"move_sample: target already exists: {new_abs}")
        return None, []

    target_folder.mkdir(parents=True, exist_ok=True)

    old_rel = str(sample_abs.relative_to(sd_root)).replace("\\", "/")
    new_rel = str(new_abs.relative_to(sd_root)).replace("\\", "/")

    # Move file first — if this fails, XMLs stay correct.
    shutil.move(str(sample_abs), str(new_abs))

    # Now update all XML references.
    updated = []
    for xml in _all_xml_files(sd_root):
        if update_xml_path(xml, old_rel, new_rel):
            updated.append(xml)

    log.info(f"Moved {sample_abs.name} → {target_folder.name}/ | updated {len(updated)} XMLs")
    return new_abs, updated


def delete_sample(sample_abs: Path) -> bool:
    """Delete a sample file. Returns True on success."""
    try:
        sample_abs.unlink()
        return True
    except Exception as e:
        log.error(f"delete_sample: {e}")
        return False


def fix_xml_path(xml_file: Path, old_rel: str, new_rel: str) -> bool:
    """Fix a single broken path in one XML file."""
    return update_xml_path(xml_file, old_rel, new_rel)


def batch_fix_paths(fixes: list[tuple[Path, str, str]]) -> dict:
    """
    Apply multiple path fixes across multiple XML files.
    fixes: list of (xml_file, old_rel, new_rel)
    Returns {"fixed": int, "failed": int}
    """
    fixed = 0
    failed = 0
    for xml_file, old_rel, new_rel in fixes:
        if update_xml_path(xml_file, old_rel, new_rel):
            fixed += 1
        else:
            failed += 1
    return {"fixed": fixed, "failed": failed}


def copy_file_to_sd(src: Path, dest: Path) -> bool:
    """Copy an external file onto the SD card. Creates dest parent dirs."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        return True
    except Exception as e:
        log.error(f"copy_file_to_sd: {e}")
        return False
