"""Root conftest for sleep-timer plugin tests.

Registers the plugin directory as a Python package named 'sleep_timer'
so that relative imports in __init__.py (from .timer, from .store) work
correctly during testing.
"""

import importlib.util
import sys
from pathlib import Path

_plugin_dir = Path(__file__).resolve().parent

# 1. Add plugin dir AND tests dir to sys.path
if str(_plugin_dir) not in sys.path:
    sys.path.insert(0, str(_plugin_dir))
_tests_dir = _plugin_dir / "tests"
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))

# 2. Pre-register submodules under the 'sleep_timer' namespace
#    Module must be in sys.modules BEFORE exec_module (dataclass needs it)
for _name in ("timer", "store"):
    _mod_name = f"sleep_timer.{_name}"
    if _mod_name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(
            _mod_name, str(_plugin_dir / f"{_name}.py")
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules[_mod_name] = _mod
            _spec.loader.exec_module(_mod)

# 3. Register __init__.py as package 'sleep_timer'
if "sleep_timer" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "sleep_timer",
        str(_plugin_dir / "__init__.py"),
        submodule_search_locations=[str(_plugin_dir)],
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        _mod.__path__ = [str(_plugin_dir)]
        _mod.__package__ = "sleep_timer"
        sys.modules["sleep_timer"] = _mod
        _spec.loader.exec_module(_mod)
