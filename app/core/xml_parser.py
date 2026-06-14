"""
DelugeHub — XML Parser
Parses Deluge XML files (Songs, Kits, Synths) and extracts metadata + sample references.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional
import logging

from .models import Song, Kit, Synth, SampleRef
from .file_ops import _read_xml

# Matches characters that are illegal in XML 1.0
_INVALID_XML_RE = re.compile(
    r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]'
)

log = logging.getLogger(__name__)

_DELUGE_METADATA_TAGS = {'firmwareVersion', 'earliestCompatibleFirmware'}

# Matches unescaped '&' that is not part of a valid XML entity reference
_BARE_AMP_RE = re.compile(r'&(?!(?:amp|lt|gt|apos|quot|#\d+|#x[\da-fA-F]+);)')


def _parse_xml_robust(file_path: Path) -> Optional[ET.Element]:
    """
    Robustly parse a Deluge XML file.

    Handles all known Deluge firmware quirks:

    1. Newer firmware (2.0.0-beta+) writes multiple top-level elements before
       the actual content element, e.g.:
           <?xml version="1.0" encoding="UTF-8"?>
           <firmwareVersion>2.0.0-beta</firmwareVersion>
           <earliestCompatibleFirmware>2.0.0-beta</earliestCompatibleFirmware>
           <sound>...</sound>
       Fix: wrap body in a synthetic root, then find the actual content element.

    2. Some files contain invalid XML 1.0 control characters.
       Fix: strip with regex before parsing.

    3. Some files contain unescaped '&' in attribute values or text content.
       Fix: escape bare '&' to '&amp;'.

    Returns the content Element (e.g. <sound>, <kit>, <song>) or None on failure.
    """
    try:
        text, _ = _read_xml(file_path)
    except Exception as e:
        log.error(f"Cannot read {file_path}: {e}")
        return None

    # 1. Strip invalid XML 1.0 characters
    text = _INVALID_XML_RE.sub('', text)

    # 2. Escape bare '&'
    text = _BARE_AMP_RE.sub('&amp;', text)

    # 3. Strip XML declaration so we can wrap in a synthetic root
    body = re.sub(r'<\?xml[^?]*\?>\s*', '', text, count=1)

    # 4. Wrap in synthetic root to handle multiple top-level elements
    try:
        wrapper = ET.fromstring(f'<_deluge_root_>{body}</_deluge_root_>')
        children = list(wrapper)
        if not children:
            log.error(f"No elements found in {file_path}")
            return None
        # Return the first non-metadata child (the actual content element)
        for child in children:
            if child.tag not in _DELUGE_METADATA_TAGS:
                return child
        return children[-1]
    except ET.ParseError as e:
        # 5. Last resort: lxml with recover=True
        #    Handles genuinely broken files (e.g. missing closing tags due to
        #    Deluge firmware bugs like a missing </modKnobs>).
        #    lxml elements share the same API as stdlib ET (findall, find,
        #    get, iter, tag, text, attrib) so we return them directly —
        #    no re-serialization needed.
        try:
            from lxml import etree as lxml_et
            parser = lxml_et.XMLParser(recover=True, encoding='utf-8')
            lxml_root = lxml_et.fromstring(
                f'<_deluge_root_>{body}</_deluge_root_>'.encode('utf-8'),
                parser=parser,
            )
            children_lxml = list(lxml_root)
            if not children_lxml:
                log.error(f"No elements found in {file_path} (lxml recovery)")
                return None
            for child in children_lxml:
                if child.tag not in _DELUGE_METADATA_TAGS:
                    log.warning(f"Recovered malformed XML via lxml: {file_path}")
                    return child  # lxml element — compatible API, no conversion needed
            log.warning(f"Recovered malformed XML via lxml: {file_path}")
            return children_lxml[-1]
        except Exception as lxml_err:
            log.error(f"lxml recovery also failed for {file_path}: {lxml_err}")
        log.error(f"Error parsing {file_path}: {e}")
        return None


def validate_xml_file(file_path: Path) -> Optional[str]:
    """
    Validate a Deluge XML file using the same robust parser as the rest of
    the app (_parse_xml_robust).

    Returns None if the file is readable/parseable (i.e. DelugeHub and the
    Deluge itself can read it), or a short error message string if it is
    genuinely broken.

    NOTE: do NOT use xml.etree.ElementTree.parse() directly here — normal
    firmware 2.0+ Deluge XML files have multiple top-level elements
    (<firmwareVersion>, <earliestCompatibleFirmware>, <sound>/<kit>/<song>),
    which ET.parse() rejects with "junk after document element" even though
    the file is perfectly valid and readable by the Deluge and the rest of
    this app.
    """
    try:
        root = _parse_xml_robust(file_path)
    except Exception as e:
        return f"{e}"
    if root is None:
        return "Datei konnte nicht gelesen/geparst werden"
    return None


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


def _first_sample_ref_in(elem: ET.Element, sd_root: Path) -> Optional[SampleRef]:
    """Return the first sample reference found anywhere inside elem (incl. itself), or None."""
    for sub in elem.iter():
        for attr in SAMPLE_ATTRIBUTES:
            val = sub.get(attr, "")
            if val and _looks_like_sample_path(val):
                return _make_ref(val, sd_root)

        if sub.tag in ("fileName", "filePath", "audioFileHolder"):
            txt = (sub.text or "").strip()
            if txt and _looks_like_sample_path(txt):
                return _make_ref(txt, sd_root)

    return None


def map_kit_pads_to_samples(root: ET.Element, sd_root: Path, max_pads: int = 16) -> list[Optional[SampleRef]]:
    """
    Build a pad-index-aligned list of sample references for a kit.

    Unlike `_collect_sample_refs` (which walks the whole tree, dedupes by
    path and returns a flat list in first-seen order — not aligned with
    pad positions), this walks the <sound>/<kitRow> elements in document
    order and returns, for each pad slot, the first sample reference found
    inside that specific element (or None if the pad has no sample, e.g. a
    synth/MIDI/CV row).

    The result always has exactly `max_pads` entries so callers can safely
    zip it with a fixed-size pad grid.
    """
    sounds = root.findall(".//sound") or root.findall(".//kitRow")

    pad_refs: list[Optional[SampleRef]] = []
    for sound in sounds[:max_pads]:
        pad_refs.append(_first_sample_ref_in(sound, sd_root))

    while len(pad_refs) < max_pads:
        pad_refs.append(None)

    return pad_refs


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
        root = _parse_xml_robust(file_path)
        if root is None:
            return None

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
    except Exception as e:
        log.error(f"Error parsing song {file_path}: {e}")
        return None


def parse_kit(file_path: Path, sd_root: Path) -> Optional[Kit]:
    """Parse a Deluge KIT XML file."""
    try:
        root = _parse_xml_robust(file_path)
        if root is None:
            return None

        # Count sound sources (pads)
        sounds = root.findall(".//sound") or root.findall(".//kitRow")
        pad_count = len(sounds)

        sample_refs = _collect_sample_refs(root, sd_root)
        pad_refs = map_kit_pads_to_samples(root, sd_root)

        return Kit(
            file_path=file_path,
            name=file_path.stem,
            pad_count=pad_count,
            sample_refs=sample_refs,
            pad_refs=pad_refs,
        )
    except Exception as e:
        log.error(f"Error parsing kit {file_path}: {e}")
        return None


def parse_synth(file_path: Path, sd_root: Path) -> Optional[Synth]:
    """Parse a Deluge SYNTH XML file."""
    try:
        root = _parse_xml_robust(file_path)
        if root is None:
            return None

        osc1_type = "square"
        osc2_type = "square"
        filter_type = "lpf"

        # OSC types - Deluge uses <osc1> / <osc2>, not <osc>.
        # New firmware (3.x+): type as attribute  -> <osc1 type="saw" ...>
        # Old firmware (2.x):  type as child elem -> <osc1><type>saw</type></osc1>
        def _get_osc_type(osc_elem) -> str:
            if osc_elem is None:
                return "square"
            # Attribute format (new firmware)
            t = osc_elem.get("type", "").strip()
            if t:
                return t
            # Child-element format (old firmware)
            type_child = osc_elem.find("type")
            if type_child is not None and (type_child.text or "").strip():
                return type_child.text.strip()
            return "square"

        osc1_type = _get_osc_type(root.find(".//osc1"))
        osc2_type = _get_osc_type(root.find(".//osc2"))

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
