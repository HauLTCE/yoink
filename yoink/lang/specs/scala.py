"""Scala language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

SCALA_STDLIB = frozenset({
    "scala", "java", "javax", "jdk",
})

SCALA_SPEC = LangSpec(
    id="scala",
    name="Scala",
    extensions=(".scala", ".sc"),
    std_libs=SCALA_STDLIB,
    stdlib_prefixes=("scala.", "java.", "javax.", "jdk."),
    entry_files=("Main.scala", "src/main/scala/Main.scala"),
    package_manifests=("build.sbt", "build.sc"),
    license_files=("LICENSE",),
    import_res=(
        re.compile(r"""^\s*import\s+([A-Za-z0-9_.*{}=>,\s]+?)(?:\r?\n|;)""", re.MULTILINE),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="sbt",
    verify_command="scalac",
)
