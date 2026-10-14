"""PHP spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="php",
    extensions=(".php",),
    import_re=(
        r"\buse\s+(?P<mod>[A-Za-z_][\w\\]*(?:\s+as\s+\w+)?)\s*;",
        r"\b(?:require|include)(?:_once)?\s*\(?\s*['\"](?P<mod>[^'\"]+)",
    ),
    namespace_re=r"\bnamespace\s+(?P<ns>[A-Za-z_][\w\\]*)\s*;",
    defn_res=(
        r"\b(?:class|interface|trait|enum)\s+{sym}\b",
        r"\bfunction\s+{sym}\s*\(",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset(),
    comment_res=(r"//.*$", r"#.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("composer.json",),
)
