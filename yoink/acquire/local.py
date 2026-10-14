"""Local filesystem source."""

from __future__ import annotations

from pathlib import Path

from yoink.errors import AcquireError
from yoink.model import Source


def acquire_local(path: str | Path) -> tuple[Path, Source]:
    """Resolve an existing local directory to (path, Source)."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise AcquireError(f"local source not found: {resolved}")
    if not resolved.is_dir():
        raise AcquireError(f"local source is not a directory: {resolved}")
    return resolved, Source(kind="local", display=str(resolved), ref=None)


__all__ = ["acquire_local"]
