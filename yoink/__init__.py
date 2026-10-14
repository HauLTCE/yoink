"""yoink — surgical feature extractor."""

__version__ = "1.0.0"

__all__ = ["__version__", "extract", "analyze"]


def __getattr__(name: str):
    # lazy so importing yoink doesn't drag in api.py deps early
    if name in ("extract", "analyze"):
        from yoink import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
