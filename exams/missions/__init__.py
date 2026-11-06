"""Mission registry. Import order = exam order."""
from __future__ import annotations

import importlib
import pkgutil

_cache: dict = {}


def all_missions() -> dict:
    if not _cache:
        for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
            if m.name[0] in ("m", "x"):
                mod = importlib.import_module(f"{__name__}.{m.name}")
                _cache[mod.MISSION.id] = mod.MISSION
    return _cache
