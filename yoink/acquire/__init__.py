"""Source acquisition: local paths and git remotes into a content-hashed cache."""

from __future__ import annotations

from pathlib import Path

from yoink.model import Source

from .git import acquire_git, clone_url, is_local_spec, parse_source
from .local import acquire_local


def acquire(
    source_spec: str,
    cache_dir: Path | None = None,
) -> tuple[Path, Source, str | None]:
    """Resolve a source spec to (checkout_path, Source, commit_sha|None)."""
    src = parse_source(source_spec)
    if src.kind == "local":
        path, source = acquire_local(source_spec)
        return path, source, None
    path, commit = acquire_git(src, clone_url(src), cache_dir)
    return path, src, commit


__all__ = [
    "acquire",
    "acquire_local",
    "acquire_git",
    "parse_source",
    "is_local_spec",
]
