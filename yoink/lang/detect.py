"""Automatic programming language detection engine across 15 languages."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from yoink.gitignore import iter_files, load_ignore
from yoink.lang import list_specs

# Explicit manifest files and their target language IDs (ordered by specificity)
_MANIFEST_MARKERS: tuple[tuple[str, str], ...] = (
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("pubspec.yaml", "dart"),
    ("Package.swift", "swift"),
    ("mix.exs", "elixir"),
    ("composer.json", "php"),
    ("Gemfile", "ruby"),
    ("build.sbt", "scala"),
    ("pyproject.toml", "python"),
    ("requirements.txt", "python"),
    ("setup.py", "python"),
    ("tsconfig.json", "jsts"),
    ("package.json", "jsts"),
    ("CMakeLists.txt", "cpp"),
    ("vcpkg.json", "cpp"),
    ("pom.xml", "java"),
    ("build.gradle.kts", "kotlin"),
    ("build.gradle", "java"),
)


def detect_language(root: Path) -> str:
    """Inspect project manifests and count file extensions to auto-detect language."""
    root = Path(root).resolve()
    if not root.exists():
        return "unknown"

    ignored = load_ignore(root)
    ext_map: dict[str, str] = {".py": "python", ".pyi": "python"}
    for spec in list_specs():
        for ext in spec.extensions:
            # Note: .h can be C/C++ or ObjC; default to cpp
            ext_map.setdefault(ext, spec.id)

    ext_counts: Counter[str] = Counter()
    marker_hits: Counter[str] = Counter()

    # Check root-level markers first
    for filename, lang_id in _MANIFEST_MARKERS:
        if (root / filename).is_file():
            marker_hits[lang_id] += 3

    for p in root.iterdir() if root.is_dir() else ():
        if p.is_file():
            if p.suffix == ".csproj" or p.suffix == ".sln":
                marker_hits["csharp"] += 4
            elif p.suffix == ".gemspec":
                marker_hits["ruby"] += 3
            elif p.suffix == ".rockspec":
                marker_hits["lua"] += 3

    for file_path in iter_files(root, ignored):
        suffix = file_path.suffix.lower()
        if suffix in ext_map:
            ext_counts[ext_map[suffix]] += 1
        elif suffix == ".csproj":
            marker_hits["csharp"] += 3
        elif suffix == ".rockspec":
            marker_hits["lua"] += 3

    # Special refinement: if build.gradle.kts or pom.xml was present, check whether .kt or .java dominates
    if ext_counts["kotlin"] > 0 and ext_counts["kotlin"] >= ext_counts["java"]:
        if marker_hits["java"] > 0:
            marker_hits["kotlin"] += marker_hits["java"]

    if not ext_counts and not marker_hits:
        return "unknown"

    # Combine extension counts with marker weights so ties in extension counts
    # are deterministically broken by manifest markers (and vice versa).
    all_langs = set(ext_counts.keys()) | set(marker_hits.keys())
    scored = sorted(
        all_langs,
        key=lambda lang: (
            ext_counts[lang] * 2 + marker_hits[lang] * 3,
            marker_hits[lang],
            ext_counts[lang],
            lang == "python",  # deterministic fallback
        ),
        reverse=True,
    )
    return scored[0] if scored else "unknown"
