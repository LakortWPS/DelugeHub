"""
DelugeHub — XML Parser
Parses Deluge XML files (Songs, Kits, Synths) and extracts metadata + sample references.
"""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import logging

from .models import Song, Kit, Synth, SampleRef
from .file_ops import _find_nth_path_occurrence, _read_xml

# Matches characters that are illegal in XML 1.0
_INVALID_XML_RE = re.compile(
    r'[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]'
)

log = logging.getLogger(__name__)

_DELUGE_METADATA_TAGS = {'firmwareVersion', 'earliestCompatibleFirmware'}

# Matches unescaped '&' that is not part of a valid XML entity reference
_BARE_AMP_RE = re.compile(r'&(?!(?:amp|lt|gt|apos|quot|#\d+|#x[\da-fA-F]+);)')


def _parse_xml_robust_text(text: str, context: str = "<string>") -> Optional[ET.Element]:
    """
    Same robust parsing logic as _parse_xml_robust, but operating on an
    already-loaded string instead of reading a file from disk. Used both
    by _parse_xml_robust itself and by callers that need to validate XML
    text that only exists in memory so far (e.g. a staged edit that has
    not been written to disk yet).

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
            log.error(f"No elements found in {context}")
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
                log.error(f"No elements found in {context} (lxml recovery)")
                return None
            for child in children_lxml:
                if child.tag not in _DELUGE_METADATA_TAGS:
                    log.warning(f"Recovered malformed XML via lxml: {context}")
                    return child  # lxml element — compatible API, no conversion needed
            log.warning(f"Recovered malformed XML via lxml: {context}")
            return children_lxml[-1]
        except Exception as lxml_err:
            log.error(f"lxml recovery also failed for {context}: {lxml_err}")
        log.error(f"Error parsing {context}: {e}")
        return None


def _parse_xml_robust(file_path: Path) -> Optional[ET.Element]:
    """
    Robustly parse a Deluge XML file from disk. See _parse_xml_robust_text
    for the parsing logic itself; this wrapper only handles the file read.
    """
    try:
        text, _ = _read_xml(file_path)
    except Exception as e:
        log.error(f"Cannot read {file_path}: {e}")
        return None
    return _parse_xml_robust_text(text, context=str(file_path))


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


def validate_xml_text(text: str, context: str = "<string>") -> Optional[str]:
    """
    Like validate_xml_file, but for XML text that is only in memory so far
    (e.g. a staged edit before it is written to disk). Returns None if the
    text is parseable via the same robust logic the rest of the app and
    the Deluge itself tolerate, or a short error message if it is broken
    beyond what even the lxml recovery pass can salvage.
    """
    try:
        root = _parse_xml_robust_text(text, context=context)
    except Exception as e:
        return f"{e}"
    if root is None:
        return "Text konnte nicht geparst werden"
    return None


_FW_RE = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([A-Za-z]+)(?:\d+)?)?$",
    re.IGNORECASE,
)
_FW_PRE_RANK = {"alpha": 0, "beta": 1, "rc": 2}
_SOUND_TOKEN_RE = re.compile(r"</sound>|<sound(?:\s[^>]*)?>")
_KITROW_TOKEN_RE = re.compile(r"</kitRow>|<kitRow(?:\s[^>]*)?>")
_OSC1_OPEN_RE = re.compile(r"<osc1(?:\s[^>]*)?>")
_SAMPLE_ATTR_RE = re.compile(
    r"""(?:fileName|filePath)\s*=\s*["']([^"']+)["']"""
)
_SAMPLE_TEXT_RE = re.compile(
    r"<(?:fileName|filePath|audioFileHolder)>\s*([^<]+?)\s*</(?:fileName|filePath|audioFileHolder)>"
)


def read_firmware_tags(text: str) -> tuple:
    """
    Return (firmwareVersion, earliestCompatibleFirmware) from raw Deluge XML.

    Newer firmware writes the two values as sibling elements before the
    content element. Older files put them on the content element as
    attributes. A sibling wins when it is non-empty; otherwise the
    attribute is used. Missing values are empty strings.
    """
    if not text:
        return "", ""
    cleaned = _INVALID_XML_RE.sub("", text)
    cleaned = _BARE_AMP_RE.sub("&amp;", cleaned)
    body = re.sub(r"<\?xml[^?]*\?>\s*", "", cleaned, count=1)
    wrapped = f"<_deluge_root_>{body}</_deluge_root_>"
    wrapper = None
    try:
        wrapper = ET.fromstring(wrapped)
    except ET.ParseError:
        try:
            from lxml import etree as lxml_et
            parser = lxml_et.XMLParser(recover=True, encoding="utf-8")
            wrapper = lxml_et.fromstring(wrapped.encode("utf-8"), parser=parser)
        except Exception:
            return "", ""
    if wrapper is None:
        return "", ""

    firmware = ""
    earliest = ""
    content = None
    for child in list(wrapper):
        if child.tag == "firmwareVersion":
            firmware = (child.text or "").strip()
        elif child.tag == "earliestCompatibleFirmware":
            earliest = (child.text or "").strip()
        elif child.tag not in _DELUGE_METADATA_TAGS and content is None:
            content = child
    if content is not None:
        if not firmware:
            firmware = (content.get("firmwareVersion") or "").strip()
        if not earliest:
            earliest = (content.get("earliestCompatibleFirmware") or "").strip()
    return firmware, earliest


def firmware_sort_key(version: str) -> Optional[tuple]:
    """
    (major, minor, patch, pre) so that 4.1.0-alpha < 4.1.0-beta < 4.1.0-rc < 4.1.0.

    An unknown suffix ranks like alpha. An empty string has no key and
    must not take part in a comparison.
    """
    raw = (version or "").strip()
    if not raw:
        return None
    match = _FW_RE.match(raw)
    if match is None:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    suffix = (match.group(4) or "").lower()
    if not suffix:
        pre = 3
    elif suffix in _FW_PRE_RANK:
        pre = _FW_PRE_RANK[suffix]
    else:
        pre = 0
    return (major, minor, patch, pre)


def firmware_baseline(versions: list) -> str:
    """Raw version string with the highest sort key, or '' when none qualify."""
    best_key = None
    best_raw = ""
    for version in versions:
        key = firmware_sort_key(version)
        if key is None:
            continue
        if best_key is None or key > best_key:
            best_key = key
            best_raw = (version or "").strip()
    return best_raw


def song_needs_newer_firmware(song_version: str, other_versions: list) -> Optional[str]:
    """
    Baseline raw string when song_version is strictly newer than every other
    earliestCompatibleFirmware on the card, otherwise None.

    No other tagged file, or a tie with the card maximum, is not a mark.
    """
    key = firmware_sort_key(song_version)
    if key is None:
        return None
    base = firmware_baseline(other_versions)
    base_key = firmware_sort_key(base)
    if base_key is None or not key > base_key:
        return None
    return base


def natural_sort_key(name: str) -> list:
    """Split digits so pad2.wav sorts before pad10.wav. View/list order only."""
    key = []
    for part in re.split(r"(\d+)", name or ""):
        if part.isdigit():
            key.append((0, int(part)))
        elif part:
            key.append((1, part.lower()))
    return key


@dataclass
class InstrumentPresetRef:
    tag: str
    preset_folder: str = ""
    preset_name: str = ""
    name: str = ""
    preset_slot: Optional[int] = None
    preset_sub_slot: Optional[int] = None


@dataclass
class PackFile:
    abs_path: Path
    rel_path: str
    kind: str
    size_bytes: int


@dataclass
class PackPlan:
    files: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    unresolved_presets: list = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    def count_kind(self, kind: str) -> int:
        return sum(1 for item in self.files if item.kind == kind)


def _optional_int(value) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _preset_from_element(elem) -> InstrumentPresetRef:
    return InstrumentPresetRef(
        tag=elem.tag,
        preset_folder=(elem.get("presetFolder") or "").strip(),
        preset_name=(elem.get("presetName") or "").strip(),
        name=(elem.get("name") or "").strip(),
        preset_slot=_optional_int(elem.get("presetSlot")),
        preset_sub_slot=_optional_int(elem.get("presetSubSlot")),
    )


def collect_instrument_presets(root: ET.Element) -> list:
    """
    Kit elements, and sound elements that are not pads inside soundSources.

    A pad ``<sound name="…">`` is not a synth preset. Embedded instruments
    without a preset file stay in the song; this function only reports the
    reference, it does not invent a file.
    """
    if root is None:
        return []
    parents = {}
    for parent in root.iter():
        for child in list(parent):
            parents[id(child)] = parent
    refs = []
    for elem in root.iter():
        if elem.tag == "kit":
            refs.append(_preset_from_element(elem))
        elif elem.tag == "sound":
            parent = parents.get(id(elem))
            if parent is not None and parent.tag == "soundSources":
                continue
            refs.append(_preset_from_element(elem))
    return refs


def _rel_under_root(path: Path, root: Path) -> Optional[str]:
    try:
        return str(Path(path).relative_to(Path(root))).replace("\\", "/")
    except ValueError:
        return None


def _is_within(path: Path, root: Path) -> bool:
    return _rel_under_root(path, root) is not None


def _preset_candidates(tag: str, folder: str, name: str) -> list:
    top = "KITS" if tag == "kit" else "SYNTHS"
    stem = (name or "").strip()
    if stem.lower().endswith(".xml"):
        stem = stem[:-4]
    if not stem:
        return []
    filename = stem + ".XML"
    folder = (folder or "").replace("\\", "/").strip("/")
    raw = []
    if folder:
        folder_l = folder.lower()
        top_l = top.lower()
        if folder_l == top_l or folder_l.startswith(top_l + "/"):
            raw.append(folder + "/" + filename)
        else:
            raw.append(top + "/" + folder + "/" + filename)
    raw.append(top + "/" + filename)
    seen = set()
    out = []
    for cand in raw:
        key = cand.lower()
        if key not in seen:
            seen.add(key)
            out.append(cand)
    return out


def _slot_stem(tag: str, slot: int, subslot: Optional[int]) -> Optional[str]:
    if slot is None or slot < 0:
        return None
    prefix = "KIT" if tag == "kit" else "SYNT"
    stem = f"{prefix}{int(slot):03d}"
    if subslot is not None and subslot >= 0:
        if subslot > 25:
            return None
        stem += chr(ord("A") + int(subslot))
    return stem


def _preset_label(preset: InstrumentPresetRef) -> str:
    if preset.preset_name:
        if preset.preset_folder:
            return preset.preset_folder.replace("\\", "/").strip("/") + "/" + preset.preset_name
        return preset.preset_name
    if preset.preset_slot is not None:
        stem = _slot_stem(preset.tag, preset.preset_slot, preset.preset_sub_slot)
        return stem or str(preset.preset_slot)
    return preset.tag


def _resolve_preset(preset: InstrumentPresetRef, index) -> tuple:
    """Return (list of (item, kind), had_file_hint)."""
    had_hint = bool(preset.preset_name) or preset.preset_slot is not None
    pool = index.kits if preset.tag == "kit" else index.synths
    kind = "kit" if preset.tag == "kit" else "synth"
    by_rel = {}
    for item in pool:
        rel = _rel_under_root(item.file_path, index.root_path)
        if rel:
            by_rel.setdefault(rel.lower(), item)

    found = []
    seen = set()

    def _add(item):
        key = str(item.file_path)
        if key in seen:
            return
        seen.add(key)
        found.append((item, kind))

    if preset.preset_name:
        for cand in _preset_candidates(preset.tag, preset.preset_folder, preset.preset_name):
            item = by_rel.get(cand.lower())
            if item is not None:
                _add(item)
    if not found and preset.name:
        for item in pool:
            if item.file_path.stem == preset.name:
                _add(item)
    if not found and preset.preset_slot is not None:
        stem = _slot_stem(preset.tag, preset.preset_slot, preset.preset_sub_slot)
        if stem:
            for item in pool:
                if item.file_path.stem.upper() == stem.upper():
                    _add(item)
    return found, had_hint


def pack_target_rejected(sd_root: Path, dest: Path) -> bool:
    """True when dest is the card, inside it, or a parent of the card."""
    try:
        root = Path(sd_root).resolve()
        target = Path(dest).resolve()
    except OSError:
        root = Path(sd_root)
        target = Path(dest)
    if target == root:
        return True
    try:
        target.relative_to(root)
        return True
    except ValueError:
        pass
    try:
        root.relative_to(target)
        return True
    except ValueError:
        pass
    return False


def build_pack_plan(index, songs: list) -> PackPlan:
    """
    Songs plus the kits, synths and samples they reference, each file once.

    Missing samples (exists == False) go to ``missing`` and are not copied.
    A preset name that only appears on a pad inside soundSources does not
    pull that kit or synth in.
    """
    files = {}
    missing = []
    missing_seen = set()
    unresolved = []

    def _add_file(abs_path: Path, kind: str) -> None:
        rel = _rel_under_root(abs_path, index.root_path)
        if not rel:
            return
        key = rel.lower()
        if key in files:
            return
        try:
            size = Path(abs_path).stat().st_size
        except OSError:
            size = 0
        files[key] = PackFile(Path(abs_path), rel, kind, size)

    def _add_samples(refs) -> None:
        for ref in refs or []:
            if ref.exists and ref.abs_path is not None and _is_within(ref.abs_path, index.root_path):
                _add_file(ref.abs_path, "sample")
            elif not ref.exists:
                label = ref.path
                if label not in missing_seen:
                    missing_seen.add(label)
                    missing.append(label)

    for song in songs or []:
        _add_file(song.file_path, "song")
        _add_samples(song.sample_refs)
        root = _parse_xml_robust(song.file_path)
        if root is None:
            continue
        for preset in collect_instrument_presets(root):
            matches, had_hint = _resolve_preset(preset, index)
            if not matches:
                if had_hint:
                    unresolved.append(
                        "Preset nicht als Datei gefunden: " + _preset_label(preset)
                    )
                continue
            for item, kind in matches:
                _add_file(item.file_path, kind)
                _add_samples(item.sample_refs)

    present = {item.rel_path.lower() for item in files.values()}
    missing = [
        label for label in missing
        if label.replace("\\", "/").lstrip("/").lower() not in present
    ]
    return PackPlan(list(files.values()), missing, unresolved)


def _element_spans(text: str, token_re) -> list:
    spans = []
    stack = []
    for match in token_re.finditer(text):
        token = match.group(0)
        if token.startswith("</"):
            if not stack:
                continue
            start = stack.pop()
            spans.append((start, match.end()))
        elif token.rstrip().endswith("/>"):
            spans.append((match.start(), match.end()))
        else:
            stack.append(match.start())
    spans.sort(key=lambda span: span[0])
    return spans


def _pad_spans(text: str) -> list:
    sounds = _element_spans(text, _SOUND_TOKEN_RE)
    if sounds:
        return sounds
    return _element_spans(text, _KITROW_TOKEN_RE)


def _first_path_in_span(text: str, span) -> Optional[str]:
    chunk = text[span[0]:span[1]]
    for regex in (_SAMPLE_ATTR_RE, _SAMPLE_TEXT_RE):
        for match in regex.finditer(chunk):
            value = match.group(1).strip()
            if value and _looks_like_sample_path(value):
                return value
    return None


def _xml_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )


def _osc1_filename_edit(text: str, span, rel: str):
    """Insert fileName on the pad's existing osc1, or None when there is no osc1."""
    start, end = span
    chunk = text[start:end]
    match = _OSC1_OPEN_RE.search(chunk)
    if match is None:
        return None
    tag = match.group(0)
    if re.search(r"\bfileName\s*=", tag) or re.search(r"<fileName\b", chunk):
        return None
    escaped = _xml_attr(rel.replace("\\", "/"))
    abs_start = start + match.start()
    abs_end = start + match.end()
    body = chunk[match.end():]
    close_at = body.find("</osc1>")
    interior = body if close_at < 0 else body[:close_at]
    has_child = "<" in interior
    if tag.endswith("/>"):
        new_tag = tag[:-2].rstrip() + f' fileName="{escaped}"/>'
        return abs_start, abs_end, new_tag
    if has_child:
        return abs_end, abs_end, f"<fileName>{escaped}</fileName>"
    new_tag = tag[:-1].rstrip() + f' fileName="{escaped}">'
    return abs_start, abs_end, new_tag


def _apply_text_edits(text: str, edits: list) -> str:
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def assign_folder_to_pads(xml_text: str, pad_rels: list) -> str:
    """
    Point pad 0..n at the relative paths in pad_rels. None leaves that pad.

    Existing fileName values are replaced at the occurrence that belongs to
    that pad (earlier pads with the same path count), so a shared sample is
    not rewritten on a pad this call does not assign. A pad ``<sound>`` with
    no sample gets fileName on its existing ``<osc1>``. Pads without a
    ``<sound>`` or without ``<osc1>`` are left untouched. One pass, no write.
    """
    if not xml_text:
        return xml_text
    spans = _pad_spans(xml_text)
    current = []
    for span in spans:
        path = _first_path_in_span(xml_text, span)
        current.append(path.replace("\\", "/") if path else None)

    edits = []
    for index, new_rel in enumerate(pad_rels or []):
        if new_rel is None or index >= len(spans):
            continue
        new_fwd = str(new_rel).replace("\\", "/")
        old = current[index]
        if old:
            if old == new_fwd:
                continue
            occurrence = sum(1 for earlier in current[:index] if earlier == old)
            old_bwd = old.replace("/", "\\")
            new_bwd = new_fwd.replace("/", "\\")
            found = _find_nth_path_occurrence(xml_text, old, old_bwd, occurrence)
            if found is None:
                continue
            at, length, is_fwd = found
            replacement = new_fwd if is_fwd else new_bwd
            edits.append((at, at + length, replacement))
        else:
            edit = _osc1_filename_edit(xml_text, spans[index], new_fwd)
            if edit is not None:
                edits.append(edit)
    if not edits:
        return xml_text
    return _apply_text_edits(xml_text, edits)


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
        text, _enc = _read_xml(file_path)
        firmware_version, earliest_compatible = read_firmware_tags(text)
        root = _parse_xml_robust_text(text, context=str(file_path))
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
            firmware_version=firmware_version,
            earliest_compatible=earliest_compatible,
        )
    except Exception as e:
        log.error(f"Error parsing song {file_path}: {e}")
        return None


def parse_kit(file_path: Path, sd_root: Path) -> Optional[Kit]:
    """Parse a Deluge KIT XML file."""
    try:
        text, _enc = _read_xml(file_path)
        firmware_version, earliest_compatible = read_firmware_tags(text)
        root = _parse_xml_robust_text(text, context=str(file_path))
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
            firmware_version=firmware_version,
            earliest_compatible=earliest_compatible,
        )
    except Exception as e:
        log.error(f"Error parsing kit {file_path}: {e}")
        return None


def parse_synth(file_path: Path, sd_root: Path) -> Optional[Synth]:
    """Parse a Deluge SYNTH XML file."""
    try:
        text, _enc = _read_xml(file_path)
        firmware_version, earliest_compatible = read_firmware_tags(text)
        root = _parse_xml_robust_text(text, context=str(file_path))
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
            firmware_version=firmware_version,
            earliest_compatible=earliest_compatible,
        )
    except Exception as e:
        log.error(f"Error parsing synth {file_path}: {e}")
        return None
