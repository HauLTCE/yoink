# yoink

**Grab any feature from any codebase. Keep what it needs. Drop the other 49,000 lines.**

yoink is a surgical feature extractor: point it at a repo and a symbol, and it computes the minimal set of code needed to carry that feature out — as a directory bundle, a single flat file, or an honest doctor report. Every extraction ships a manifest stating exactly what's included, what's external, and what couldn't be resolved.

## Install

```bash
pipx install .
# or, for development:
pip install -e .
```

Python 3.11+.

## Quickstart

```bash
# Bundle mode (default): preserve package layout under --out
yoink ./huge-repo --grab "parsing:parse_invoice" --out ./invoice/

# Flat mode: one file in the source language (symbol-level slice for Python,
# import-hoist + topo-concat for other languages)
yoink gh:some/huge-repo@v2.3.1 --grab "Spinner" --flat -o ./out/

# Doctor mode: analyze only — tree, externals, unresolved; nothing written
yoink ./huge-repo --grab "parsing:parse_invoice" --doctor

# C# source → C# output (output is always in the source language)
yoink gh:acme/widgets --grab "src/Acme.Core/Util.cs:Helper" --flat

# Sandboxed verify: copy the extraction to a temp dir and run a command
yoink ./repo --grab "mod:func" --test "pytest tests/test_func.py"

# Zip the bundle
yoink ./repo --grab "mod:func" --zip
```

## Flags

| Flag | Meaning |
|---|---|
| `--grab <target>` | `pkg.mod:sym`, `path/File.cs:sym`, or a bare symbol (required) |
| `--mode bundle\|flat\|doctor` | Explicit mode selector |
| `--bundle` / `--flat` / `--doctor` | Shortcut flags (mutually exclusive) |
| `-o, --out <dir>` | Output directory (default `./yoink-out` or `[output] dir` from config) |
| `--zip` | Write a `.zip` of the bundle alongside the output |
| `--flat-name <name>` | Override the flat output filename |
| `--test "<cmd>"` | Run `cmd` in a sandboxed copy of the output (subject to `safety.execute`) |
| `--strict` | Exit 2 after emitting if any refs are unresolved |
| `--json` | Machine-readable manifest/closure on stdout |
| `--max-depth <n>` | BFS depth cap (default 12) |
| `--force` | Overwrite existing output; skip the `--test` confirmation prompt |
| `-v, --verbose` | Noisier logging |
| `--version` | Print version and exit |

Exit codes: `0` ok, `1` error, `2` strict-mode unresolved.

## Sources

- Local path: `./repo`, `C:\code\repo`, `~/repo`
- GitHub shorthand: `gh:owner/repo[@ref]`
- GitHub URL: `https://github.com/owner/repo` (also `git@github.com:owner/repo`)

Remote sources are cloned into a content-hashed cache — `$YOINK_CACHE` if set, else `~/.yoink/cache`. Manage it:

```bash
yoink cache list    # show cached clones
yoink cache clear   # delete them all
yoink cache dir     # print the cache root
```

## `yoink.toml`

Discovered by walking up from the current directory. CLI flags override it.

```toml
[extract]
granularity = "file"    # file | symbol
external = "list"       # list | bundle | vendor
max_depth = 12

[safety]
execute = "ask"         # never | ask | always — applies to --test

[output]
dir = "./yoink-out"
```

## Manifest

Every bundle/flat extraction writes `yoink.manifest.json` (schema v1) into the output directory. It records:

- `source` — kind, repo display, ref, commit SHA, detected license, language, target
- `resolution` — `ast` (Python) or `text` (regex-driven for other languages)
- `modules` — in-repo modules pulled into the closure
- `stdlib` — standard-library imports observed
- `external_deps` — third-party imports with best-effort version + evidence file
- `unresolved` — dynamic imports, getattr tricks, star imports, unresolvable names — never silently dropped
- `verified` — result of `--test` if run
- `warnings` — side effects, copyleft license notes, depth-cap hits, etc.

## Language support

| Language | Resolution | Notes |
|---|---|---|
| Python | `ast` | Full stdlib `ast` pipeline: relative imports, re-export chains, `TYPE_CHECKING`, conditional imports, star imports, dynamic-import detection |
| C#, JS/TS, Go, Rust, Java, C/C++, Ruby, PHP | `text` | Regex-based import graphs + file-granular closure. Honest about it: `resolution: "text"` in the manifest with a verify-imports warning |

Output is always in the source language — no translation in this release.

## Safety invariant

**yoink never imports or executes target code during analysis.** Everything it learns comes from `ast.parse` (Python) or regex scans of file contents (other languages). The only code execution ever is `--test`, which is always user-initiated, always run in a `tempfile.mkdtemp()` sandbox, subject to a denylist (`rm -rf /`, `mkfs`, `dd of=/dev`, …) and the `safety.execute` policy.

## Library API

```python
from yoink import extract, analyze

manifest = extract("./repo", "parsing:parse_invoice", mode="bundle", out="./out")
closure = analyze("./repo", "parsing:parse_invoice")   # doctor, no writes
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests live in `tests/` with fixture repos under `tests/fixtures/repos/`. The suite never touches the real `~/.yoink` — `YOINK_CACHE` is pointed at a tmp dir by the fixtures.
