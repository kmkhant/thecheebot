"""Load ``scripts/*.py`` as importable modules so they can be tested.

The scripts are not a package (they are run directly, and insert the project
root on ``sys.path`` themselves), so tests load them by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str) -> ModuleType:
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - bad filename
        raise ImportError(f"cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    # Register before executing: dataclasses (and pickling) resolve a module by
    # name from sys.modules, and fail with a cryptic AttributeError otherwise.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module
