"""Language detection: extension histogram + marker-file boost."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from yoink.gitignore import iter_files, load_ignore

# marker weight ~= this many files
_MARKER_WEIGHT = 15

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".ts": "jsts",
    ".tsx": "jsts",
    ".js": "jsts",
    ".jsx": "jsts",
    ".mjs": "jsts",
    ".cjs": "jsts",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "cpp",
    ".h": "cpp",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".rb": "ruby",
    ".php": "php",
}

_MARKER_TO_LANG: tuple[tuple[str, str], ...] = (
    ("*.csproj", "csharp"),
    ("*.sln", "csharp"),
    ("package.json", "jsts"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("Gemfile", "ruby"),
    ("composer.json", "php"),
)


def detect_language(root: Path) -> str:
    """Return the dominant language id under root, or "unknown"."""
    root = Path(root)
    ignored = load_ignore(root)
    counts: dict[str, int] = {}
    for f in iter_files(root, ignored):
        lang = _EXT_TO_LANG.get(f.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
        for pat, mlang in _MARKER_TO_LANG:
            if fnmatch.fnmatchcase(f.name, pat):
                counts[mlang] = counts.get(mlang, 0) + _MARKER_WEIGHT
    if not counts:
        return "unknown"
    best = max(counts.values())
    tops = [k for k, v in counts.items() if v == best]
    if len(tops) != 1:
        return "unknown"  # tie
    return tops[0]
