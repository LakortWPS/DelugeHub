"""
Test helper: import app.core.* submodules without triggering
app/__init__.py or app/core/__init__.py, both of which (transitively)
import PySide6 — unavailable in the test sandbox (missing libEGL.so.1).

We register lightweight namespace-package stubs for `app` and
`app.core` in sys.modules with __path__ pointing at the real
directories, so the normal import machinery can resolve relative
imports (e.g. `from .models import SampleRef`) inside the real
app/core/*.py files without executing either __init__.py.
"""
import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_core_module(name: str, _force_reload: bool = True):
    """Import and return app.core.<name>, e.g. load_core_module('lost_finder').

    The source is compiled and exec'd directly (bypassing __pycache__)
    so edits made during this session are always picked up, even if a
    stale/corrupted .pyc exists on disk that the sandbox can't delete.
    """
    full_name = f"app.core.{name}"

    if "app" not in sys.modules:
        pkg = types.ModuleType("app")
        pkg.__path__ = [str(ROOT / "app")]
        sys.modules["app"] = pkg

    if "app.core" not in sys.modules:
        pkg = types.ModuleType("app.core")
        pkg.__path__ = [str(ROOT / "app" / "core")]
        sys.modules["app.core"] = pkg

    if not _force_reload and full_name in sys.modules:
        return sys.modules[full_name]

    path = ROOT / "app" / "core" / f"{name}.py"
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType(full_name)
    module.__file__ = str(path)
    module.__package__ = "app.core"
    sys.modules[full_name] = module
    code = compile(source, str(path), "exec")
    exec(code, module.__dict__)
    return module
