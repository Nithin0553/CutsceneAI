"""Load CineTwin's source-readiness audit without ambiguous module names.

Unreal Studio inserts both `tools/` and `packages/cinetwin/` into sys.path.
Both contain `transfer_readiness.py`. Importing the bare name can resolve to
`tools/transfer_readiness.py` (the CLI wrapper), causing a circular import.
This canonical file loader never mutates the shared `transfer_readiness` key
in sys.modules and never selects the wrapper instead of the semantic audit.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_TARGET = Path(__file__).with_name("transfer_readiness.py").resolve()
_NAME = "_cutsceneai_cinetwin_source_readiness"


def load_source_readiness() -> ModuleType:
    """Return the exact semantic CineTwin implementation or fail explicitly."""
    module = sys.modules.get(_NAME)
    if module is not None:
        path = getattr(module, "__file__", "")
        if Path(path).resolve() != _TARGET:
            raise ImportError("CineTwin source readiness module identity mismatch.")
        if not callable(getattr(module, "audit", None)) or not callable(
            getattr(module, "audit_files", None)
        ):
            raise ImportError("CineTwin source readiness is incompletely initialized.")
        return module
    spec = importlib.util.spec_from_file_location(_NAME, _TARGET)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot locate the canonical CineTwin source readiness module.")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[_NAME] = loaded
    try:
        spec.loader.exec_module(loaded)
        if not callable(getattr(loaded, "audit", None)) or not callable(
            getattr(loaded, "audit_files", None)
        ):
            raise ImportError("CineTwin readiness implementation lacks required methods.")
        return loaded
    except BaseException:
        if sys.modules.get(_NAME) is loaded:
            del sys.modules[_NAME]
        raise
