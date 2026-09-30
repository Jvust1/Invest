"""Load vendored upstream packages without making them hard dependencies."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

def load_vendor(package: str, module: str | None = None):
    """Import a package from third_party/ when present in a source checkout."""
    root = Path(__file__).resolve().parents[1] / "third_party" / package
    if root.is_dir() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module(module or package)
