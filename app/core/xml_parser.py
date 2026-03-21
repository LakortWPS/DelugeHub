"""
DelugeHub — XML Parser
Parses Deluge XML files (Songs, Kits, Synths) and extracts metadata + sample references.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import logging

from .models import Song, Kit, Synth, SampleRef

log = logging.getLogger(__name__)

SAMPLE_ATTRIBUTES = [
    "fileName",
    "filePath",
]

SAMPLE_TAGS = [
    "audioFile",
    "sample",
    "osc",
]


def _collect_sample_refs(root: ET.Element, sd_root: Path) -> list[SampleRef]:
    """Walk entire XML tree and collect every sample file reference."""
    refs = []
    seen = set()

    for elem in root.iter():
        # Check attributes like fileName="SAMPLES/..."
        for attr in SAMPLE_ATTRIBUTES:
            val = elem.get(attr, "")
            if val and _looks_like_sample_path(val):
                if val not in seen:
                    seen.add(val)
                    refs.append(_make_ref(val, sd_root))

        # Also check direct text of <fileName> tags
        if elem.tag in ("fileName", "filePath", "audioFileHolder"):
            txt = (elem.text or "").strip()
            if txt and _looks_like_sample_path(txt):
                if txt not in seen:
                    seen.add(txt)
                    refs.append(_make_ref(txt, sd_root))

    return refs


def _looks_like_sample_path(val: str) -> bool:
    """Heuristic: does this string look like a sample path?"""
    val_lower = val.lower()
    audio_exts = (".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg")
    return any(val_lower.endswith(ext) for ext in audio_exts)


def _make_ref(path_str: str, sd_root: Path) -> SampleRef:
    """Create a SampleRef, checking if the file actually exists."""
    # Normalize: remove leading slash or SAMPLES/
    normalized = path_str.replace("\\", "/").lstrip("/")
    abs_path = sd_root / normalized
    return SampleRef(
        path=path_str,
        abs_path=abs_path,
        exists=abs_path.exists(),
    )


def _parse_bpm(root: ET.Element) -> float:
    """
    Extract BPM from a Deluge song XML.

    Deluge stores tempo in several formats across firmware versions:
      • <songParams bpm="120.0" .../>   (older firmware, plain float attribute)
      • <bpm>120.0</bpm>                (some versions, plain float text)
      • <tempo>0x1E000000</tempo>       (newer firmware, BPM * 2^24 as hex)
      • bpm="120" on the root element   (legacy fallback)
    """
    # 1. songParams bpm attribute (most common in older firmware)
    song_params = root.find(".//songParams")
    if song_params is not None:
        try:
            val = float(song_params.get("bpm", ""))
            if val > 0:
                return round(val, 2)
        except ValueError:
            pass

    # 2. <bpm> as plain float text
    bpm_elem = root.find(".//bpm")
    if bpm_elem is not None and bpm_elem.text:
        txt = bpm_elem.text.strip()
        if not txt.lower().startswith("0x"):
            try:
                val = float(txt)
                if val > 0:
                    return round(val, 2)
            except ValueError:
                pass

    # 3. <tempo> as hex (BPM encoded as BPM * 2^24)
    tempo_elem = root.find(".//tempo")
    if tempo_elem is not None and tempo_elem.text:
        txt = tempo_elem.text.strip()
        if txt.lower().startswith("0x"):
            try:
                raw = int(txt, 16) & 0xFFFFFFFF
                bpm = raw / (1 << 24)
                if 10 < bpm < 999:
                    return round(bpm, 2)
            except ValueError:
                pass

    # 4. Root-level bpm attribute (legacy)
    try:
        val = float(root.get("bpm", ""))
        if val > 0:
            return round(val, 2)
    except ValueError:
        pass

    return 0.0


def parse_song(file_path: Path, sd_root: Path) -> Optional[Song]:
    """Parse a Deluge SONG XML file."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        num = 4
        denom = 4

        # BPM — multi-format parser handles all known Deluge firmware variants.
        bpm = _parse_bpm(root)

        # Time signature
        ts = root.find(".//timeSignature")
        if ts is not None:
            try:
                num = int(ts.get("numerator", 4))
                denom = int(ts.get("denominator", 4))
            except ValueError:
                pass

        # Track count — try Deluge tag names across firmware versions:
        #   <instrumentTrack>  (most common, newer firmware)
        #   <audioTrack>       (audio clip tracks)
        #   <track>            (older firmware)
        #   <instrument>       (legacy)
        track_count = 0
        for tag in (".//instrumentTrack", ".//audioTrack",
                    ".//track", ".//instrument"):
            found = root.findall(tag)
            if found:
                track_count = len(found)
                break

        sample_refs = _collect_sample_refs(root, sd_root)

        return Song(
            file_path=file_path,
            name=file_path.stem,
            bpm=bpm,
            time_signature_numerator=num,
            time_signature_denominator=denom,
            track_count=track_count,
            sample_refs=sample_refs,
        )
    except ET.ParseError as e:
        log.error(f"XML parse error in {file_path}: {e}")
        return None
    except Exception as e:
        log.error(f"Error parsing song {file_path}: {e}")
        return None


def parse_kit(file_path: Path, sd_root: Path) -> Optional[Kit]:
    """Parse a Deluge KIT XML file."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Count sound sources (pads)
        sounds = root.findall(".//sound") or root.findall(".//kitRow")
        pad_count = len(sounds)

        sample_refs = _collect_sample_refs(root, sd_root)

        return Kit(
            file_path=file_path,
            name=file_path.stem,
            pad_count=pad_count,
            sample_refs=sample_refs,
        )
    except Exception as e:
        log.error(f"Error parsing kit {file_path}: {e}")
        return None


def parse_synth(file_path: Path, sd_root: Path) -> Optional[Synth]:
    """Parse a Deluge SYNTH XML file."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        osc1_type = "square"
        osc2_type = "square"
        filter_type = "lpf"

        # OSC types
        oscs = root.findall(".//osc")
        if len(oscs) >= 1:
            osc1_type = oscs[0].get("type", "square")
        if len(oscs) >= 2:
            osc2_type = oscs[1].get("type", "square")

        # Filter type
        lpf = root.find(".//lpf")
        hpf = root.find(".//hpf")
        if lpf is not None:
            filter_type = "lpf"
        elif hpf is not None:
            filter_type = "hpf"

        sample_refs = _collect_sample_refs(root, sd_root)

        return Synth(
            file_path=file_path,
            name=file_path.stem,
            osc1_type=osc1_type,
            osc2_type=osc2_type,
            filter_type=filter_type,
            sample_refs=sample_refs,
        )
    except Exception as e:
        log.error(f"Error parsing synth {file_path}: {e}")
        return None
