"""Java language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

JAVA_STDLIB = frozenset({
    "java", "javax", "jdk", "sun", "org.w3c.dom", "org.xml.sax", "org.ietf.jgss",
})

JAVA_SPEC = LangSpec(
    id="java",
    name="Java",
    extensions=(".java",),
    std_libs=JAVA_STDLIB,
    stdlib_prefixes=("java.", "javax.", "jdk.", "sun.", "org.w3c.dom.", "org.xml.sax."),
    entry_files=("Main.java", "App.java", "Application.java"),
    package_manifests=("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"),
    license_files=("LICENSE", "LICENSE.txt"),
    import_res=(
        re.compile(r"""^\s*import\s+(?:static\s+)?([A-Za-z0-9_.*]+)\s*;""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="maven",
    verify_command="javac",
    lockfiles=("gradle.lockfile",),
)
