"""Language spec tables. Each <lang>.py exports LANG_SPEC: LangSpec."""

from __future__ import annotations

from yoink.lang import LangSpec

PYTHON_SPEC = LangSpec(
    id="python",
    extensions=(".py",),
    import_re=(),  # python uses ast, not regex
    namespace_re=None,
    defn_res=(
        r"^\s*(?:async\s+)?def\s+{sym}\s*\(",
        r"^\s*class\s+{sym}\b",
        r"^\s*{sym}\s*=",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset(),
    comment_res=(r"#.*$",),
    flat_sep="#",
    flat_import_first=True,
    init_file="__init__.py",
    marker_files=("pyproject.toml", "setup.py", "setup.cfg"),
)

__all__ = ["PYTHON_SPEC", "LangSpec"]
