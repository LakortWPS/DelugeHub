"""Identical-byte sample groups and token-bounded path replacement."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests._helpers import load_core_module

models = load_core_module("models")
file_ops = load_core_module("file_ops")
xml_parser = load_core_module("xml_parser")

Sample = models.Sample
identical_sample_groups = file_ops.identical_sample_groups
preferred_keep_index = file_ops.preferred_keep_index
replace_bounded_sample_path = file_ops.replace_bounded_sample_path
validate_xml_text = xml_parser.validate_xml_text


def test_same_bytes_form_one_group_and_wasted_space_is_one_file(tmp_path):
    same = b"same-bytes"
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    c = tmp_path / "c.wav"
    a.write_bytes(same)
    b.write_bytes(same)
    c.write_bytes(b"different!!")
    samples = [
        Sample(file_path=a, name="a.wav", size_bytes=len(same)),
        Sample(file_path=b, name="b.wav", size_bytes=len(same)),
        Sample(file_path=c, name="c.wav", size_bytes=len(b"different!!")),
    ]

    groups = identical_sample_groups(samples)

    assert len(groups) == 1
    assert len(groups[0].members) == 2
    assert {member.name for member in groups[0].members} == {"a.wav", "b.wav"}
    assert groups[0].wasted_bytes == len(same)


def test_keep_prefers_most_references_then_index_order():
    busy = Sample(file_path=Path("a.wav"), name="a.wav", referenced_by=[Path("s.xml"), Path("k.xml")])
    quiet = Sample(file_path=Path("b.wav"), name="b.wav", referenced_by=[])
    assert preferred_keep_index([quiet, busy]) == 1

    first = Sample(file_path=Path("a.wav"), name="a.wav", referenced_by=[Path("s.xml")])
    second = Sample(file_path=Path("b.wav"), name="b.wav", referenced_by=[Path("k.xml")])
    assert preferred_keep_index([first, second]) == 0


def test_bounded_replace_keeps_bak_suffix_and_stays_valid_xml():
    text = (
        '<kit><osc1 fileName="SAMPLES/a.wav"></osc1>'
        "<extra>SAMPLES/a.wav.bak</extra></kit>"
    )
    new = replace_bounded_sample_path(text, "SAMPLES/a.wav", "SAMPLES/b.wav")
    assert 'fileName="SAMPLES/b.wav"' in new
    assert "SAMPLES/a.wav.bak" in new
    assert "SAMPLES/b.wav.bak" not in new
    assert validate_xml_text(new) is None
