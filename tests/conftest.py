"""
Pytest configuration for the DelugeHub test suite.

NOTE: app/__init__.py and app/core/__init__.py transitively import
PySide6, which cannot be imported in this sandbox (missing
libEGL.so.1). Pure-logic tests therefore load app.core.* submodules
directly via the `_load_core_module` helper pattern (see
test_lost_finder_v2.py and friends) instead of `import app...`.

test_dbg.py and test_lost_finder.py are leftover/corrupted scratch
files from earlier debugging that this sandbox's filesystem will not
let us delete or cleanly overwrite (writes to them produce garbled
content with embedded null bytes, which crashes pytest's traceback
formatter). Skip collecting them entirely.
"""

collect_ignore = ["test_dbg.py", "test_lost_finder.py"]
