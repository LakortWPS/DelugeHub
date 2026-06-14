"""
DelugeHub — Data Models
Represents all Deluge SD-Card content types.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SampleRef:
    """A reference to a sample file inside an XML."""
    path: str                  # path as stored in XML (relative to SD root)
    abs_path: Optional[Path]   # resolved absolute path (None if missing)
    exists: bool = False

    @property
    def is_missing(self) -> bool:
        return not self.exists


@dataclass
class Song:
    file_path: Path
    name: str
    bpm: float = 0.0
    time_signature_numerator: int = 4
    time_signature_denominator: int = 4
    track_count: int = 0
    sample_refs: list[SampleRef] = field(default_factory=list)
    raw_xml: Optional[str] = None

    @property
    def missing_samples(self) -> list[SampleRef]:
        return [s for s in self.sample_refs if s.is_missing]

    @property
    def has_missing_samples(self) -> bool:
        return len(self.missing_samples) > 0


@dataclass
class Kit:
    file_path: Path
    name: str
    pad_count: int = 0
    sample_refs: list[SampleRef] = field(default_factory=list)
    pad_refs: list[Optional[SampleRef]] = field(default_factory=list)
    raw_xml: Optional[str] = None

    @property
    def missing_samples(self) -> list[SampleRef]:
        return [s for s in self.sample_refs if s.is_missing]

    @property
    def has_missing_samples(self) -> bool:
        return len(self.missing_samples) > 0


@dataclass
class Synth:
    file_path: Path
    name: str
    osc1_type: str = "square"
    osc2_type: str = "square"
    filter_type: str = "lpf"
    sample_refs: list[SampleRef] = field(default_factory=list)
    raw_xml: Optional[str] = None

    @property
    def missing_samples(self) -> list[SampleRef]:
        return [s for s in self.sample_refs if s.is_missing]


@dataclass
class Sample:
    file_path: Path
    name: str
    size_bytes: int = 0
    sample_rate: int = 44100
    channels: int = 1
    bit_depth: int = 16
    duration_seconds: float = 0.0
    referenced_by: list[Path] = field(default_factory=list)

    @property
    def is_used(self) -> bool:
        return len(self.referenced_by) > 0

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


@dataclass
class SDCardIndex:
    """Full index of a scanned Deluge SD card."""
    root_path: Path
    songs: list[Song] = field(default_factory=list)
    kits: list[Kit] = field(default_factory=list)
    synths: list[Synth] = field(default_factory=list)
    samples: list[Sample] = field(default_factory=list)
    scan_errors: list[str] = field(default_factory=list)

    @property
    def total_missing_refs(self) -> int:
        count = 0
        for s in self.songs:
            count += len(s.missing_samples)
        for k in self.kits:
            count += len(k.missing_samples)
        for sy in self.synths:
            count += len(sy.missing_samples)
        return count

    @property
    def files_with_missing(self) -> list:
        result = []
        for s in self.songs:
            if s.has_missing_samples:
                result.append(s)
        for k in self.kits:
            if k.has_missing_samples:
                result.append(k)
        for sy in self.synths:
            if sy.missing_samples:
                result.append(sy)
        return result

    @property
    def unused_samples(self) -> list[Sample]:
        return [s for s in self.samples if not s.is_used]

    @property
    def total_sample_size_mb(self) -> float:
        return sum(s.size_mb for s in self.samples)
