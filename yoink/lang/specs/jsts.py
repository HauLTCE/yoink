"""JavaScript and TypeScript language specification."""

from __future__ import annotations

import re
from yoink.lang import LangSpec

JSTS_STDLIB = frozenset({
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
    "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
    "events", "fs", "fs/promises", "http", "http2", "https", "inspector",
    "module", "net", "os", "path", "path/posix", "path/win32", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream",
    "stream/promises", "stream/web", "string_decoder", "sys", "timers",
    "timers/promises", "tls", "trace_events", "tty", "url", "util", "v8",
    "vm", "wasi", "worker_threads", "zlib",
})

JSTS_SPEC = LangSpec(
    id="jsts",
    name="JavaScript/TypeScript",
    extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"),
    std_libs=JSTS_STDLIB,
    stdlib_prefixes=("node:", "bun:", "deno:"),
    entry_files=("index.ts", "index.tsx", "index.js", "index.mjs", "main.ts", "main.js", "src/index.ts", "src/index.js"),
    package_manifests=("package.json", "tsconfig.json", "jsconfig.json", "deno.json"),
    license_files=("LICENSE", "LICENSE.md", "LICENSE.txt"),
    import_res=(
        # ESM static imports (including multi-line `{ ... } from "mod"`, `import type ... from "mod"`)
        re.compile(r"""\b(?:import|export)\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]""", re.MULTILINE),
        # Side-effect import: `import "mod"`
        re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE),
        # CommonJS require: `require("mod")`
        re.compile(r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    ),
    dynamic_import_res=(
        re.compile(r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    ),
    comment_res=(r"//[^\n]*", r"/\*[\s\S]*?\*/"),
    package_manager="npm",
    verify_command="node --check",
    lockfiles=("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"),
)
