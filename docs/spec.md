# yoink — Engineering Contract

Binding spec for all implementers. The proposal lives at `proposal/PROPOSAL.md` (context; this file is the contract).

## Product

yoink = surgical feature extractor. Point at a repo + symbol → computes the minimal code needed to carry that feature out — as a bundle dir, one flat file, or a doctor report. Never lies about completeness: every extraction ships a manifest stating what's included, external, and unresolved.

**Safety invariant: yoink NEVER imports or executes target code during analysis. Pure static analysis only.** The only code execution ever is `--test`, always user-initiated, run in a sandboxed temp dir with a denylist + `safety.execute` policy (never|ask|always).

## Scope this run (v0.9 target — everything except real language parsing)

- Source languages: **Python (full stdlib `ast` pipeline)** + **generic text-mode** for `csharp`, `jsts`, `go`, `rust`, `java`, `cpp`, `ruby`, `php`. No tree-sitter, no real parsers for non-Python — regex-driven import graphs only.
- Output is ALWAYS in the original source language. No translation, no `--lang` flag this run.
- Generic text-mode = per-language spec tables (import regexes, namespace/std-lib prefixes, defn patterns) → file-granular closure → files that still work in that language.
- Modes: `bundle` (default, file-granular), `flat` (one file, same language — Python: symbol-level slice; other langs: import-hoist + topo-concat), `doctor` (analysis only), `--zip`.
- Sources: local path (required), `gh:owner/repo[@ref]`, `https://github.com/...` — clone into content-hashed cache.
- `--test` sandboxed verify, `--strict`, `--json`, `--force`, `--max-depth`, `yoink.toml` config, `yoink cache` commands.
- Library API: `yoink.api.extract()` / `analyze()`.

## Tech

- Python 3.11+ (dev box runs 3.13). stdlib + `tomllib`. Third-party: `typer>=0.12`, `rich>=13`, `pytest>=8`. NO other deps — no tree-sitter this run.
- Package: `yoink/` (src layout NOT used — flat `yoink/` package at repo root, `pyproject.toml` with `[tool.setuptools]`). Tests in `tests/`.
- Console script: `yoink = "yoink.cli:app"`.

## Non-negotiables (every file)

1. **Minimal comments — when you do comment, write a BAD comment** (unhelpful, obvious, or snarky one-liner, e.g. `# magic`, `# this works don't ask`, `# yes really`). No doc-comment essays; short docstrings on public API only.
2. **No Claude/AI attribution anywhere** — commits, code, docs, no co-author trailers.
3. No `import` of target code; no `exec`/`eval` on analyzed code.
4. Honesty: unresolved refs are first-class output, never silently dropped.
5. Type hints on public functions; `from __future__ import annotations` allowed.
6. All paths cross-platform (Windows + POSIX). No `os.path` string concat — `pathlib`.
7. Cache dir: `YOINK_CACHE` env override, else `~/.yoink/cache` (dev/test must never touch real `~/.yoink` — fixtures set `YOINK_CACHE` to tmp).

## Locked interfaces (cross-file contract)

```python
# yoink/model.py — frozen dataclasses, the shared vocabulary
@dataclass(frozen=True) class Source:      # kind: "local"|"gh"|"url", display str, ref: str|None
@dataclass(frozen=True) class ModuleInfo:  # name, path: Path, package: str|None, is_pkg_init: bool
@dataclass(frozen=True) class ImportEdge:  # importer, module(raw-or-resolved), names: tuple[(name,asname)], level: int, kind, lineno
@dataclass(frozen=True) class SymbolEdge:  # module, name, lineno — a name used that the module did not define
@dataclass(frozen=True) class Defn:        # name, kind: "func"|"class"|"assign"|"import", lineno, end_lineno, decorators: tuple
@dataclass(frozen=True) class Unresolved:  # file, lineno, name, kind, detail
# kinds: dynamic_import | getattr_dynamic | star_import | unresolvable_name | plugin | resource | native
# Language ids (plain str): python|csharp|jsts|go|rust|java|cpp|ruby|php|unknown
# For non-python, ModuleInfo.name = posix rel path w/o ext (e.g. "src/Foo/Bar"); ImportEdge.module = raw import text

@dataclass class ModuleGraph:              # language: str, modules: dict[str,ModuleInfo], imports: list[ImportEdge], symbols: list[SymbolEdge], defns: dict[str,list[Defn]], unresolved: list[Unresolved]
@dataclass class ExternalDep:              # name, version: str|None, evidence: str
@dataclass class Closure:                  # target, language, resolution: "ast"|"text", modules: set[str], external: list[ExternalDep], stdlib: set[str], unresolved: list[Unresolved], depth_hit: bool
@dataclass class EmitResult:               # files: list[Path], warnings: list[str], output_dir: Path
@dataclass class VerifyResult:             # status: "passed"|"failed"|"not_run"|"skipped", command: str|None, detail: str, exit_code: int|None

# yoink/lang/specs — per-lang data table shape (yoink/lang/specs/<lang>.py each exports LANG_SPEC: LangSpec)
@dataclass(frozen=True) class LangSpec:
    id: str                                  # "csharp"
    extensions: tuple[str, ...]              # (".cs",)
    import_re: tuple[str, ...]               # regexes; group "mod" = raw import text
    namespace_re: str | None                 # group "ns" = declared namespace/package (csharp/java/php/go)
    defn_res: tuple[str, ...]                # regexes locating a definition of symbol; use {sym} placeholder, re.escaped at use
    stdlib_prefixes: tuple[str, ...]         # ("System.",) for csharp; empty for most
    stdlib_names: frozenset[str]             # exact names (jsts builtins, go "fmt", ruby stdlib…)
    comment_res: tuple[str, ...]             # line+block comment strippers applied before scanning imports
    flat_sep: str                            # banner between files in flat concat, "//" or "#" style
    flat_import_first: bool                  # hoisted imports go at very top
    init_file: str | None                    # "__init__.py" for python else None
    marker_files: tuple[str, ...]            # (".csproj","package.json","go.mod","Cargo.toml","pom.xml","build.gradle","Gemfile","composer.json") for detection

# yoink/lang/resolve.py (owned by graph pkg)
def find_symbol_candidates(root: Path, mods: dict[str,ModuleInfo], spec: LangSpec, symbol: str) -> list[tuple[str,int]]
    # → [(module_name, score)] strong: defn_re hit(100) | filename stem==symbol(60) | content contains(10)
def resolve_import(mods: dict[str,ModuleInfo], spec: LangSpec, importer: str, raw: str) -> str | None
    # generic: raw text → in-repo module name or None; per-lang rules below

# yoink/lang/detect.py
def detect_language(root: Path) -> str      # extension histogram over gitignore-respecting walk + marker-file boost; tie→"unknown"

# pipeline (yoink/api.py) — no lang param; output language == detected source language
def extract(source, target, *, mode="bundle", out=None, flat_name=None,
            zip_out=False, test_cmd=None, strict=False, max_depth=None, config=None,
            cache_dir=None, force=False, verbose=False) -> Manifest
def analyze(source, target, *, max_depth=None, config=None, cache_dir=None) -> Closure  # doctor

# errors (yoink/errors.py): YoinkError(base); AcquireError; SourceNotFoundError;
#   SymbolNotFoundError(candidates: list[str]); ParseError; EmitError; VerifyError;
#   ConfigError; SafetyError; StrictModeError
```

## Manifest — `yoink.manifest.json` (schema v1)

```json
{
  "yoink_version": "1.0.0",
  "schema_version": 1,
  "source": {"kind": "local", "repo": "<display>", "ref": null, "commit": null, "license": "MIT|null", "language": "csharp", "target": "pkg.mod:func"},
  "resolution": "ast|text",
  "mode": "bundle|flat|doctor",
  "output": {"files": ["rel/path.py"], "lines": 412},
  "modules": ["pkg.mod"],
  "stdlib": ["re", "pathlib"],
  "external_deps": [{"name": "requests", "version": "2.31.0", "evidence": "requirements.txt"}],
  "unresolved": [{"file": "helpers.py", "line": 87, "kind": "getattr_dynamic", "name": "x", "detail": "..."}],
  "untranslated": [],
  "verified": {"status": "not_run", "command": null, "passed": null, "detail": ""},
  "warnings": ["module-level side effects in config.py pulled wholesale"],
  "created": "<iso8601>"
}
```

## Behavior details (exact)

- **Target spec:** `pkg.mod:symbol`, `pkg.mod` (whole module), or bare `symbol` → unique-match search across module map; ambiguous → `SymbolNotFoundError` with `candidates`.
- **Graph edges:** `import x`, `import x.y as z`, `from x import a as b`, relative `from . import`, `from .sibling import`, `if TYPE_CHECKING:` blocks (kind=type_checking → recorded, NOT pulled), try/except ImportError conditional imports (kind=conditional → pulled, warning), `__import__`/`importlib.import_module` with literal → resolved; non-literal → unresolved `dynamic_import`. `getattr(var, str)` non-literal → `getattr_dynamic`. `from x import *` → `star_import` unresolved + resolve what `x.__all__`/module defns expose. Names used but never bound → `unresolvable_name`.
- **Re-export chains:** `from a import b` where `a` itself re-exports — follow to the defining module; closure pulls the chain.
- **Closure:** BFS from target, depth cap `--max-depth` (config `extract.max_depth`, default 12); over-cap → `depth_hit` + warning, not an error.
- **External classification:** import root not in module map → stdlib (`sys.stdlib_module_names`) else third-party; versions from `requirements*.txt`, `pyproject.toml`, `setup.cfg`/`setup.py` (regex parse), `Pipfile`.
- **bundle emit:** preserving original package layout under `--out`; synthesize `__init__.py` files on the dependency path only (empty or re-export); write manifest.
- **flat emit:** symbol-granular tree-shake + topo order + safe rename on collision; modules with top-level side effects (any non-def/assign/import top-level stmt) pulled wholesale + manifest warning; imports synthesized: `import a.b` style at top; output single `<flat_name>.py`.
- **doctor:** prints tree + externals + unresolved; `--json` emits Closure as JSON; exit 0 always (unless `--strict` and unresolved → exit 2).
- **--strict:** unresolved refs → exit code 2 after emitting; still writes.
- **--test:** copy extraction to `tempfile.mkdtemp()`, run user cmd via `subprocess` with `shell=False` (`shlex.split`), 300s timeout, denylist `rm -rf /`, `format`, `mkfs`, `dd of=/dev` → SafetyError; `safety.execute=never` → refuse; `ask` → prompt unless `--yes`/`--force` or non-tty (then refuse); result → `verified`.
- **acquire:** local path must exist → `AcquireError`; `gh:` → `git clone` into `<cache>/repos/<sha256[:16] of normalized url+ref>`; `git rev-parse HEAD` → manifest `commit`; offline + cached → reuse; license: find `LICENSE*`/`COPYING*` root file → SPDX guess (MIT/Apache-2.0/GPL-3.0/BSD-3-Clause/other) → manifest + GPL → warning.
- **config:** `yoink.toml` nearest ancestor of cwd; `[extract] granularity|external|max_depth`, `[safety] execute`, `[output] dir`; CLI flags override config; bad toml/keys → `ConfigError`.
- **zip:** emit to temp then `zipfile` → `<out>.zip` or `yoink-bundle-<target>.zip` default name; manifest inside too.
- **gitignore walk:** honor `.gitignore` + `.yoinkignore` (own parser: `*`,`**`,`?`,leading `/`,trailing `/` dir-only,`!` negation — layered like git); always skip `.git`, `__pycache__`, `.venv`, `node_modules`, `dist`, `build`, `*.egg-info`, `.yoink-cache`.
- **module map:** `foo.py`→`foo`, `foo/__init__.py`→`foo`, `foo/bar.py`→`foo.bar`; root package dir (the one containing setup.py/pyproject/src layout handled: `src/` stripped); non-package loose dirs treated as namespace-ish roots mapping to bare names.

## Generic (non-Python) language pipeline

Pipeline identical to Python; only the graph builder + symbol resolution differ.

- **Detection:** `detect_language()` = extension histogram over the gitignore-respecting file walk (`.py`→python, `.cs`→csharp, `.ts/.tsx/.js/.jsx/.mjs/.cjs`→jsts, `.go`→go, `.rs`→rust, `.java`→java, `.c/.h/.cpp/.hpp/.cc/.cxx`→cpp, `.rb`→ruby, `.php`→php); marker files break ties/boost (`*.csproj`→csharp, `package.json`→jsts, `go.mod`→go, `Cargo.toml`→rust, `pom.xml|build.gradle`→java, `Gemfile`→ruby, `composer.json`→php). Unknown/mixed → "unknown" → bundle any explicitly-named target paths, graph empty, warning.
- **Module naming (non-Python):** `ModuleInfo.name` = repo-relative posix path minus extension (`src/Foo/Bar`). `package` = nearest ancestor dir. File-name collisions disambiguated by full path — names are unique by construction.
- **Target spec (non-Python):** bare `symbol` → `find_symbol_candidates` scoring (defn_re hit 100 > filename stem 60 > content contains 10); top score wins; tied top scores → `SymbolNotFoundError(candidates)`. `path:symbol` = file anchor + symbol verify (warning if not found). Explicit `src/Foo/Bar.cs` path → that file only. Whole-dir target `src/Foo/` unsupported — error.
- **Generic import graph:** scan each file for `spec.import_re` matches (comments stripped via `comment_res` first) → `ImportEdge(module=raw_text, kind="static")`. `resolve_import` maps raw→in-repo module:
  - **csharp:** `using Foo.Bar;` → namespace→file map built from `namespace_re` decls + directory fallback (`Foo/Bar.cs`, `Bar.cs` basename match); `using static`, `using X = ...` alias handled (alias rhs resolved); `System.*` → stdlib; `global using` ignored-kind but still resolved.
  - **jsts:** `import ... from 'path'` / `require('path')` / `export ... from 'path'` / dynamic `import('lit')` (literal only → kind dynamic unresolved if non-literal); relative `./x` → resolve `.ts/.tsx/.js/.jsx/.mjs/.cjs` + `/index.*`; bare specifier → `node_modules` external (strip `@scope/`→`@scope/pkg` name); TS `import type` → kind type_checking (recorded, not pulled).
  - **go:** import block + single imports; last path segment matches package dir name in-repo → edge; `strings|fmt|...` no-dot first-segment → stdlib; `import .`/`import _` still resolved.
  - **rust:** `mod foo;` → sibling `foo.rs` or `foo/mod.rs`; `use crate::a::b`/`use super::`/`use self::` → in-repo path resolve; `use <ext>::` → external crate (from `Cargo.toml [dependencies]`); `#[macro_use] extern crate` → external.
  - **java:** `package a.b` decl ↔ `a/b/Class.java`; `import a.b.C` → in-repo `a/b/C.java`; `java.*|javax.*` → stdlib; `import static` resolved same way.
  - **cpp:** `#include "rel.h"` → in-repo resolve relative to file then repo root; `#include <x>` → stdlib; `using namespace` recorded not pulled.
  - **ruby:** `require_relative 'p'` → `p.rb` relative; `require 'x'` → in-repo search by basename/path suffix else external gem (`Gemfile`); `load` → dynamic unresolved.
  - **php:** `use Foo\Bar` → `Foo/Bar.php` (PSR-4 from `composer.json` autoload psr-4 map when present, else dir-name match); `require|include(_once)?` literal rel path → resolve; variable require → dynamic unresolved.
- **Symbol edges (generic):** none (no defn tables beyond regexes) — `symbols=[]`; `SymbolEdge`/`Defn` unused.
- **Closure (generic):** BFS file-level over resolved edges; raw imports not matching stdlib/in-repo → `external` (name = raw spec, evidence = manifest file or "import"); unresolved = dynamic forms only.
- **Generic flat emit:** `flat_emit_generic(graph, closure, lang, out_path)` → strip comment-only dupes? No — concat original file contents in topo order, each preceded by `flat_sep` banner line `==== <name> ====`; hoisted unique import lines at top when `flat_import_first`; dedupe identical import lines. Output `flat_name`+lang ext.
- **Warnings (generic):** always add `"resolution: text — regex-based graph for <lang>, verify imports"`; unresolved-during-pull entries get kind `unresolvable_name` detail `"excluded or unresolvable in text mode"`.

## Fixtures required (tests/fixtures/repos/)

`reexport_chain` (a→b→c re-export), `side_effects` (top-level print/call — flat must pull wholesale), `star_wars` (`from x import *`, `__all__`), `cond_import` (try/except), `type_check` (TYPE_CHECKING-only import must NOT pull), `dyn` (`__import__(var)`, `importlib.import_module(f"{x}")`), `deep_pkg` (nested pkgs + relative imports `..`), `loose` (scripts no __init__), `external_dep` (imports `requests` + requirements.txt pins it), `cycle` (a↔b circular), `stdlib_mix`, `monkey` (function patching across modules), `ambiguous` (two mods define `run`), `ns_pkg` (namespace package), `submod` (target `pkg.mod` whole-module pull), `gitignored` (ignored file must not be pulled).

Non-Python: `csharp_lib` (2-namespace lib: `Acme.Core/Util.cs` uses `Acme.Data/Store.cs` via `using Acme.Data;` + `using System;` + 3rd file not needed), `jsts_lib` (`src/a.ts` imports `./b`, `b` re-exports `./c`, external `lodash`, `import type` edge), `go_lib` (2 internal pkgs + `fmt`), `rust_lib` (`mod` chain + `use crate::` + `serde` in Cargo.toml), `generic_flat` (csharp, flat emit → hoisted usings + concat).

## Tests (pytest, tmp_path everywhere, `YOINK_CACHE`→tmp)

Unit per module + end-to-end: `yoink fixture_repo --grab sym` → manifest + files exist; flat → `ast.parse` OK + `exec` in isolated ns defines target; doctor `--json` parses; strict exit 2 on unresolved; `--test` on a fixture with real test file passes; zip contains manifest; gh: clone path mocked/monkeypatched (no network in tests); config precedence test; gitignore test.

## Repo layout (target)

```
pyproject.toml  README.md  LICENSE(existing)  .gitignore
yoink/{__init__,errors,model,util,gitignore,modulemap,manifest,config}.py
yoink/acquire/{__init__,local,git,cache,license}.py
yoink/lang/{__init__,detect}.py  yoink/lang/specs/{__init__,csharp,jsts,go,rust,java,cpp,ruby,php}.py
yoink/graph/{__init__,base,python_ast,generic}.py  yoink/lang/resolve.py
yoink/closure.py  yoink/slice.py
yoink/emit/{__init__,bundle,flat,zip}.py
yoink/verify.py  yoink/report.py  yoink/api.py  yoink/cli.py
tests/{conftest.py, fixtures/repos/..., test_*.py}
```
