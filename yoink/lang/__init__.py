"""Per-language spec tables + generic resolution."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

SUPPORTED: tuple[str, ...] = (
    "python",
    "csharp",
    "jsts",
    "go",
    "rust",
    "java",
    "cpp",
    "ruby",
    "php",
)


@dataclass(frozen=True)
class LangSpec:
    id: str
    extensions: tuple[str, ...]
    import_re: tuple[str, ...]
    namespace_re: str | None
    defn_res: tuple[str, ...]
    stdlib_prefixes: tuple[str, ...]
    stdlib_names: frozenset[str]
    comment_res: tuple[str, ...]
    flat_sep: str
    flat_import_first: bool
    init_file: str | None
    marker_files: tuple[str, ...]


def get_spec(lang_id: str) -> LangSpec:
    """Load the LangSpec for lang_id from yoink.lang.specs.<lang_id>."""
    if lang_id not in SUPPORTED:
        raise KeyError(f"unsupported language: {lang_id}")
    mod = importlib.import_module(f"yoink.lang.specs.{lang_id}")
    return mod.LANG_SPEC  # type: ignore[no-any-return]
