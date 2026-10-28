"""Language specification container dataclass and registry lookup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LangSpec:
    id: str
    name: str
    extensions: tuple[str, ...]
    std_libs: frozenset[str]
    entry_files: tuple[str, ...]
    package_manifests: tuple[str, ...]
    license_files: tuple[str, ...]
    import_res: tuple[re.Pattern[str], ...]
    comment_res: tuple[str, ...]
    dynamic_import_res: tuple[re.Pattern[str], ...] = ()
    package_manager: str | None = None
    verify_command: str | None = None
    lockfiles: tuple[str, ...] = ()
    system_include_paths: tuple[Path, ...] = ()
    stdlib_prefixes: tuple[str, ...] = ()
    gpl_licenses: tuple[str, ...] = ("GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0")


def list_specs() -> list[LangSpec]:
    """Return all registered non-Python language specifications."""
    from yoink.lang.specs import ALL_SPECS

    return list(ALL_SPECS)


_ALIASES: dict[str, str] = {
    "py": "python",
    "python3": "python",
    "js": "jsts",
    "ts": "jsts",
    "javascript": "jsts",
    "typescript": "jsts",
    "jsx": "jsts",
    "tsx": "jsts",
    "node": "jsts",
    "golang": "go",
    "rs": "rust",
    "c": "cpp",
    "c++": "cpp",
    "cxx": "cpp",
    "cc": "cpp",
    "cs": "csharp",
    "c#": "csharp",
    "dotnet": "csharp",
    "rb": "ruby",
    "kt": "kotlin",
    "ex": "elixir",
    "exs": "elixir",
}


def normalize_lang_id(lang: str) -> str:
    low = lang.strip().lower()
    return _ALIASES.get(low, low)


def get_spec(lang: str) -> LangSpec | None:
    """Retrieve LangSpec instance matching language ID (or alias)."""
    norm = normalize_lang_id(lang)
    for spec in list_specs():
        if spec.id == norm:
            return spec
    return None


__all__ = ["LangSpec", "get_spec", "list_specs", "normalize_lang_id"]
