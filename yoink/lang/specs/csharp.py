"""C# spec."""

from __future__ import annotations

from yoink.lang import LangSpec

LANG_SPEC = LangSpec(
    id="csharp",
    extensions=(".cs",),
    import_re=(
        r"(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?(?P<mod>[A-Za-z_][\w.]*)\s*;",
    ),
    namespace_re=r"namespace\s+(?P<ns>[A-Za-z_][\w.]*)",
    defn_res=(
        r"\b(?:class|interface|struct|enum|record|delegate)\s+{sym}\b",
        r"\b(?:public|private|protected|internal|static|sealed|abstract|partial|new|virtual|override|readonly|extern|async|unsafe|volatile)[\w\s<>\[\],?]*\b{sym}\s*\(",
    ),
    stdlib_prefixes=("System", "Microsoft."),
    stdlib_names=frozenset(),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=(".csproj", "*.sln"),
)
