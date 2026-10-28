"""Kotlin language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

KOTLIN_STDLIB = frozenset({
    "kotlin", "kotlinx.coroutines", "java", "javax", "jdk",
})

KOTLIN_SPEC = LangSpec(
    id="kotlin",
    name="Kotlin",
    extensions=(".kt", ".kts"),
    std_libs=KOTLIN_STDLIB,
    stdlib_prefixes=("kotlin.", "java.", "javax.", "jdk."),
    entry_files=("Main.kt", "App.kt", "Application.kt"),
    package_manifests=("build.gradle.kts", "build.gradle", "pom.xml", "settings.gradle.kts"),
    license_files=("LICENSE", "LICENSE.txt"),
    import_res=(
        re.compile(r"""^\s*import\s+([A-Za-z0-9_.*]+)(?:\s+as\s+[A-Za-z0-9_]+)?""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="gradle",
    verify_command="kotlinc",
    lockfiles=("gradle.lockfile",),
)
