"""JS/TS spec."""

from __future__ import annotations

from yoink.lang import LangSpec

_NODE_BUILTINS = (
    "assert", "buffer", "child_process", "cluster", "console", "constants",
    "crypto", "dgram", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream",
    "string_decoder", "timers", "tls", "tty", "url", "util", "v8", "vm",
    "worker_threads", "zlib",
)

LANG_SPEC = LangSpec(
    id="jsts",
    extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
    import_re=(
        r"(?:import|export)\s+[^'\"]*?from\s*['\"](?P<mod>[^'\"]+)",
        r"require\s*\(\s*['\"](?P<mod>[^'\"]+)",
        r"import\s*['\"](?P<mod>[^'\"]+)",
        r"import\s*\(\s*['\"](?P<mod>[^'\"]+)",
    ),
    namespace_re=None,
    defn_res=(
        r"\b(?:function\s*\*?\s*|class\s+|const\s+|let\s+|var\s+|interface\s+|type\s+|enum\s+){sym}\b",
        r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function\s*\*?\s*|class\s+|const\s+|let\s+|var\s+|interface\s+|type\s+|enum\s+){sym}\b",
        r"\b{sym}\s*=\s*(?:async\s*)?\(",
    ),
    stdlib_prefixes=(),
    stdlib_names=frozenset(_NODE_BUILTINS) | frozenset("node:" + b for b in _NODE_BUILTINS),
    comment_res=(r"//.*$", r"/\*.*?\*/"),
    flat_sep="//",
    flat_import_first=True,
    init_file=None,
    marker_files=("package.json",),
)
