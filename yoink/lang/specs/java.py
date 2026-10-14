"""Java spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="java",
    extensions=(".java",),
    import_re=(
        r"\bimport\s+(?:static\s+)?(?P<mod>[A-Za-z_][\w.*]*)\s*;",
    ),
    namespace_re=r"\bpackage\s+(?P<ns>[A-Za-z_][\w.]*)\s*;",
    defn_res=(
        r"\b(?:class|interface|enum|record|@interface)\s+{sym}\b",
        r"\b(?:public|private|protected|static|final|synchronized|abstract|native|strictfp|transient|volatile)[\w\s<>\[\],?]*\b{sym}\s*\(",
    ),
    stdlib_prefixes=("java.", "javax.", "jdk.", "sun."),
    stdlib_names=frozenset(),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("pom.xml", "build.gradle"),
)
