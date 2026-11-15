"""Display-order rules for column sorting. No PySide."""
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


table_sort = _load_core_module("table_sort")
natural_key = table_sort.natural_key
sorted_positions = table_sort.sorted_positions

EM = "\u2014"


def test_three_state_cycle():
    rows = [["c"], ["a"], ["b"]]
    originals = [0, 1, 2]
    assert sorted_positions(rows, originals, 0, 1, "text") == [1, 2, 0]
    assert sorted_positions(rows, originals, 0, 2, "text") == [0, 2, 1]
    assert sorted_positions(rows, originals, 0, 0, "text") == [0, 1, 2]

    scrambled = [["a"], ["c"], ["b"]]
    stamps = [1, 0, 2]
    assert sorted_positions(scrambled, stamps, 0, 0, "text") == [1, 0, 2]
    assert natural_key("a", "text") == natural_key("A", "text")
    assert natural_key("a", "text") < natural_key("b", "text")


def test_number_ten_sorts_after_two():
    assert natural_key("2", "number") < natural_key("10", "number")
    rows = [["10"], ["2"], ["1"], [""]]
    originals = [0, 1, 2, 3]
    assert sorted_positions(rows, originals, 0, 1, "number") == [3, 2, 1, 0]
    assert sorted_positions(rows, originals, 0, 2, "number") == [0, 1, 2, 3]


def test_size_units():
    assert (
        natural_key("512 KB", "size")
        < natural_key("2 MB", "size")
        < natural_key("1 GB", "size")
    )
    rows = [["2 MB"], ["512 KB"], ["1 GB"], [EM]]
    originals = [0, 1, 2, 3]
    assert sorted_positions(rows, originals, 0, 1, "size") == [3, 1, 0, 2]
    assert sorted_positions(rows, originals, 0, 2, "size") == [2, 0, 1, 3]


def test_stable_ties_keep_original_order():
    rows = [["b"], ["a"], ["b"], ["a"]]
    originals = [0, 1, 2, 3]
    assert sorted_positions(rows, originals, 0, 1, "text") == [1, 3, 0, 2]
    assert sorted_positions(rows, originals, 0, 2, "text") == [0, 2, 1, 3]

    shuffled = [["a"], ["b"], ["a"]]
    shuffled_orig = [2, 0, 1]
    assert sorted_positions(shuffled, shuffled_orig, 0, 1, "text") == [2, 0, 1]


def test_blank_and_dash_sort_as_empty():
    assert natural_key("", "text") is None
    assert natural_key("   ", "number") is None
    assert natural_key(EM, "size") is None
    assert natural_key(f"{EM} Kein Match {EM}", "text") is not None
    rows = [["b"], [EM], ["a"], [""]]
    originals = [0, 1, 2, 3]
    assert sorted_positions(rows, originals, 0, 1, "text") == [1, 3, 2, 0]
    assert sorted_positions(rows, originals, 0, 2, "text") == [0, 2, 1, 3]


def test_text_orders_embedded_numbers():
    rows = [["song10"], ["song2"]]
    originals = [0, 1]
    assert sorted_positions(rows, originals, 0, 1, "text") == [1, 0]
