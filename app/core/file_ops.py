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
    """All XML files across SONGS, KITS, SYNTHS (case-insensitive extension)."""
    xmls = []
    for folder in ("SONGS", "KITS", "SYNTHS"):
        d = sd_root / folder
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() == ".xml":
                    xmls.append(f)
    return xmls


def update_xml_path(xml_file: Path, old_rel: str, new_rel: str) -> bool:
    """
    Replace old_rel with new_rel inside xml_file (text-based replacement).
    Handles both forward- and back-slash variants.
    Preserves the original file encoding so the Deluge can still read it.
    Returns True if the file was modified.
    """
    try:
        text, enc = _read_xml(xml_file)
        orig = text

        # Build both slash variants for old and new paths.
        old_fwd = old_rel.replace("\\", "/")
        new_fwd = new_rel.replace("\\", "/")
        old_bwd = old_rel.replace("/", "\\")
        new_bwd = new_rel.replace("/", "\\")

        text = text.replace(old_fwd, new_fwd)
        text = text.replace(old_bwd, new_bwd)

        if text != orig:
            _write_xml(xml_file, text, enc)
            return True
        return False
    except Exception as e:
        log.error(f"update_xml_path failed for {xml_file}: {e}")
        return False


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
