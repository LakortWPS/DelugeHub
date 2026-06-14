"""
Tests for app.core.search.search_index

Feature: global top-bar search/filter — pure matching logic over an
SDCardIndex, independent of the Qt UI (which is not testable in this
sandbox, see tests/test_kit_pad_mapping.py and friends for the pattern).
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_core_module(name):
    full_name = "app.core." + name

    if "app" not in sys.modules:
        pkg = types.ModuleType("app")
        pkg.__path__ = [str(ROOT / "app")]
        sys.modules["app"] = pkg

    if "app.core" not in sys.modules:
        pkg = types.ModuleType("app.core")
        pkg.__path__ = [str(ROOT / "app" / "core")]
        sys.modules["app.core"] = pkg

    path = ROOT / "app" / "core" / (name + ".py")
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType(full_name)
    module.__file__ = str(path)
    module.__package__ = "app.core"
    sys.modules[full_name] = module
    code = compile(source, str(path), "exec")
    exec(code, module.__dict__)
    return module


models = _load_core_module("models")
search_mod = _load_core_module("search")
search_index = search_mod.search_index

Song = models.Song
Kit = models.Kit
Synth = models.Synth
Sample = models.Sample
SDCardIndex = models.SDCardIndex


def _make_index():
    return SDCardIndex(
        root_path=Path("/sd"),
        songs=[
            Song(file_path=Path("/sd/SONGS/Acid Track.XML"), name="Acid Track"),
            Song(file_path=Path("/sd/SONGS/Other Song.XML"), name="Other Song"),
        ],
        kits=[
            Kit(file_path=Path("/sd/KITS/Acid Kit.XML"), name="Acid Kit"),
        ],
        synths=[
            Synth(file_path=Path("/sd/SYNTHS/Lead Synth.XML"), name="Lead Synth"),
        ],
        samples=[
            Sample(file_path=Path("/sd/SAMPLES/acid_loop.wav"), name="acid_loop.wav"),
            Sample(file_path=Path("/sd/SAMPLES/kick.wav"), name="kick.wav"),
        ],
    )


def test_empty_query_returns_no_results():
    index = _make_index()
    assert search_index(index, "") == []
    assert search_index(index, "   ") == []


def test_none_index_returns_no_results():
    assert search_index(None, "acid") == []


def test_case_insensitive_name_match_across_kinds():
    index = _make_index()
    results = search_index(index, "ACID")

    kinds = {r.kind for r in results}
    names = {r.name for r in results}

    assert "song" in kinds
    assert "kit" in kinds
    assert "sample" in kinds
    assert "Acid Track" in names
    assert "Acid Kit" in names
    assert "acid_loop.wav" in names
    # "Other Song" / "Lead Synth" / "kick.wav" must not match
    assert "Other Song" not in names
    assert "Lead Synth" not in names
    assert "kick.wav" not in names


def test_module_key_mapping():
    index = _make_index()
    results = search_index(index, "acid")
    by_kind = {r.kind: r.module_key for r in results}

    assert by_kind["song"] == "song_manager"
    assert by_kind["kit"] == "kit_manager"
    assert by_kind["sample"] == "sample_manager"


def test_match_against_path_not_just_name():
    index = _make_index()
    # "SONGS" appears in the path but not in either song's name
    results = search_index(index, "SONGS")
    assert len(results) == 2
    assert {r.name for r in results} == {"Acid Track", "Other Song"}


def test_limit_caps_total_results():
    index = _make_index()
    # "a" matches everything (case-insensitive substring of paths/names)
    results = search_index(index, "a", limit=2)
    assert len(results) == 2


def test_ordering_songs_kits_synths_samples():
    index = _make_index()
    results = search_index(index, "a", limit=100)
    kinds_seen = [r.kind for r in results]
    # first all songs, then kits, then synths, then samples
    order = {"song": 0, "kit": 1, "synth": 2, "sample": 3}
    seq = [order[k] for k in kinds_seen]
    assert seq == sorted(seq)
