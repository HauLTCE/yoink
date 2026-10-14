"""Clone cache bookkeeping."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def cache_root(explicit: Path | None = None) -> Path:
    """Resolve the cache dir: explicit > $YOINK_CACHE > ~/.yoink/cache."""
    if explicit is not None:
        root = Path(explicit)
    else:
        env = os.environ.get("YOINK_CACHE")
        root = Path(env) if env else Path.home() / ".yoink" / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def list_cached(cache_dir: Path | None = None) -> list[dict]:
    """List cached repo clones: [{key, path, size_mb, mtime}]."""
    repos = cache_root(cache_dir) / "repos"
    out: list[dict] = []
    if not repos.exists():
        return out
    for child in sorted(repos.iterdir()):
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            mtime = 0.0
        out.append(
            {
                "key": child.name,
                "path": child,
                "size_mb": round(_dir_size(child) / (1024 * 1024), 2),
                "mtime": mtime,
            }
        )
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def clear_cache(cache_dir: Path | None = None) -> int:
    """Remove every cached repo clone; return count removed."""
    repos = cache_root(cache_dir) / "repos"
    n = 0
    if repos.exists():
        for child in repos.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                n += 1
    return n


def cache_size(cache_dir: Path | None = None) -> int:
    """Total bytes under the cache repos dir."""
    repos = cache_root(cache_dir) / "repos"
    return _dir_size(repos) if repos.exists() else 0


__all__ = ["cache_root", "list_cached", "clear_cache", "cache_size"]
