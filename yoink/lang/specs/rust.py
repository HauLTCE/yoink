"""Rust spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="rust",
    extensions=(".rs",),
    import_re=(
        r"\bmod\s+(?P<mod>\w+)\s*;",
        r"\buse\s+(?P<mod>crate::[^;]+|super::[^;]+|self::[^;]+|[A-Za-z_][\w:]*)",
    ),
    namespace_re=None,
    defn_res=(
        r"\bfn\s+{sym}\s*(?:<[^>]*>)?\s*\(",
        r"\b(?:struct|enum|trait|union)\s+{sym}\b",
        r"\bimpl(?:<[^>]*>)?\s+(?:[\w:]+\s+for\s+)?{sym}\b",
        r"\b(?:const|static|type)\s+{sym}\b",
        r"\bmod\s+{sym}\b",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset({"std", "core", "alloc"}),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("Cargo.toml",),
)
