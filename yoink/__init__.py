"""yoink - surgical feature extractor."""

from __future__ import annotations

__version__ = "2.0.0"

__all__ = ["__version__", "yoink", "extract", "analyze"]


def __getattr__(name: str):
    # lazy so importing yoink doesn't drag in api.py deps early
    if name in ("yoink", "extract", "analyze"):
        from yoink import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
