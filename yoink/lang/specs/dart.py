"""Dart / Flutter language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

DART_STDLIB = frozenset({
    "dart:async", "dart:collection", "dart:convert", "dart:core", "dart:developer",
    "dart:ffi", "dart:html", "dart:indexed_db", "dart:io", "dart:isolate",
    "dart:js", "dart:js_interop", "dart:js_util", "dart:math", "dart:mirrors",
    "dart:svg", "dart:typed_data", "dart:ui", "dart:web_audio", "dart:web_gl",
})

DART_SPEC = LangSpec(
    id="dart",
    name="Dart",
    extensions=(".dart",),
    std_libs=DART_STDLIB,
    stdlib_prefixes=("dart:",),
    entry_files=("lib/main.dart", "bin/main.dart", "main.dart"),
    package_manifests=("pubspec.yaml",),
    license_files=("LICENSE",),
    import_res=(
        re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.MULTILINE),
        re.compile(r"""^\s*part\s+of\s+['"]([^'"]+)['"]""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="pub",
    verify_command="dart analyze",
    lockfiles=("pubspec.lock",),
)
