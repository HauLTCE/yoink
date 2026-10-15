# yoink

**Pull a single feature out of a codebase along with only the code it actually needs.**

Have you ever wanted one function or class from a massive repo without dragging in the whole project? Point `yoink` at a repository and a symbol, and it traces the dependency graph to extract the smallest working slice of code.

You can output the result as a directory bundle that keeps the original package structure, flatten everything into a single file, or run `--doctor` to inspect what would be pulled without writing anything to disk. Every extraction also generates a `yoink.manifest.json` file showing which files were included, which third-party packages you'll need, and any dynamic imports that couldn't be resolved statically.

## Install

Requires Python 3.11 or newer.

```bash
pipx install .

# Or for local development:
pip install -e .

```

## Quickstart

```bash
# Bundle mode (default): keeps the original package layout under --out
yoink ./huge-repo --grab "parsing:parse_invoice" --out ./invoice/

# Flat mode: packs everything into a single file in the source language
# (Python gets symbol-level slicing; other languages get hoisted imports and topologically sorted files)
yoink gh:some/huge-repo@v2.3.1 --grab "Spinner" --flat -o ./out/

# Doctor mode: dry-run analysis. Prints the dependency tree, external packages,
# and unresolved imports without writing any files
yoink ./huge-repo --grab "parsing:parse_invoice" --doctor

# Works across languages (C# input gives you C# output)
yoink gh:acme/widgets --grab "src/Acme.Core/Util.cs:Helper" --flat

# Verify an extraction by copying it to a temp directory and running a test command
yoink ./repo --grab "mod:func" --test "pytest tests/test_func.py"

# Create a .zip archive alongside the output directory
yoink ./repo --grab "mod:func" --zip

```

## CLI Flags

| Flag | What it does |
| --- | --- |
| `--grab <target>` | Target to extract: `pkg.mod:sym`, `path/File.cs:sym`, or a bare symbol name (required) |
| `--mode bundle|flat|doctor` | Choose the output mode explicitly |
| `--bundle` / `--flat` / `--doctor` | Shorthand flags for `--mode` (mutually exclusive) |
| `-o, --out <dir>` | Output directory (defaults to `./yoink-out` or `[output] dir` in `yoink.toml`) |
| `--zip` | Also write a `.zip` archive of the extracted bundle |
| `--flat-name <name>` | Custom filename when using `--flat` |
| `--test "<cmd>"` | Run `cmd` inside a temporary copy of the extracted output (governed by `safety.execute`) |
| `--strict` | Exit with code `2` after extraction if any references couldn't be resolved |
| `--json` | Print the manifest and dependency closure as JSON to stdout |
| `--max-depth <n>` | Maximum dependency traversal depth (default: `12`) |
| `--force` | Overwrite existing output files and skip the `--test` confirmation prompt |
| `-v, --verbose` | Enable verbose logging |
| `--version` | Print version and exit |

**Exit codes:** `0` for success, `1` for errors, `2` when `--strict` is set and unresolved references remain.

## Supported Sources

`yoink` accepts local directories and GitHub repositories:

* **Local path:** `./repo`, `~/repo`, `C:\code\repo`
* **GitHub shorthand:** `gh:owner/repo` or `gh:owner/repo@ref`
* **Git URL:** `https://github.com/owner/repo` or `git@github.com:owner/repo`

Remote repos are cloned into a content-hashed cache directory (`$YOINK_CACHE` if set, otherwise `~/.yoink/cache`). You can manage cached clones with:

```bash
yoink cache list     # list cached repos
yoink cache clear    # delete all cached clones
yoink cache dir      # print the cache directory path

```

## Configuration (`yoink.toml`)

`yoink` looks for a `yoink.toml` file in the current directory or any parent folder. Command-line flags always override config file settings.

```toml
[extract]
granularity = "file"    # file | symbol
external = "list"       # list | bundle | vendor
max_depth = 12

[safety]
execute = "ask"         # never | ask | always (applies to --test)

[output]
dir = "./yoink-out"

```

## The Manifest File

Every `bundle` and `flat` run writes a `yoink.manifest.json` (schema v1) into the output directory so you have a clear record of what was pulled:

* `source`: Where the code came from (source type, repo name, git ref, commit SHA, detected license, language, and target symbol).
* `resolution`: How dependencies were traced (`ast` for Python, `text` for regex-based scanning in other languages).
* `modules`: Internal repo modules pulled into the extraction.
* `stdlib`: Standard library imports detected across the extracted files.
* `external_deps`: Third-party packages required, including best-effort version detection and the manifest file where they were found.
* `unresolved`: Dynamic imports, `getattr` calls, star imports, or missing symbols that couldn't be traced statically. Nothing is dropped silently.
* `verified`: Pass/fail result if you ran `--test`.
* `warnings`: Notes on potential side effects, copyleft licenses, hitting the max depth limit, and similar edge cases.

## Language Support

| Language | Resolution | Details |
| --- | --- | --- |
| Python | `ast` | Full `ast` parsing: handles relative imports, re-export chains, `TYPE_CHECKING` blocks, conditional imports, star imports, and dynamic import detection. |
| C#, JS/TS, Go, Rust, Java, C/C++, Ruby, PHP | `text` | Regex-based import scanning with whole-file extraction. The manifest marks these runs as `resolution: "text"` with a reminder to double-check imports. |

Output always stays in the source language (no cross-language translation).

## Safety

**`yoink` never imports or executes target code while analyzing a repo.** All analysis is static, using `ast.parse` for Python and text scanning for other languages.

Target code only runs if you explicitly pass `--test`. When you do, `yoink` copies the extracted files into an isolated temporary directory (`tempfile.mkdtemp()`), checks the command against a basic denylist (`rm -rf /`, `mkfs`, `dd of=/dev`, etc.), and follows your `safety.execute` policy (`ask` by default).

## Python API

You can also call `yoink` directly from Python:

```python
from yoink import extract, analyze

# Extract files to ./out and get the manifest back
manifest = extract("./repo", "parsing:parse_invoice", mode="bundle", out="./out")

# Run a dry-run analysis without writing files (same as --doctor)
closure = analyze("./repo", "parsing:parse_invoice")

```

## Development

```bash
pip install -e ".[dev]"
pytest

```

Tests live in `tests/` with sample repositories under `tests/fixtures/repos/`. The test suite automatically points `YOINK_CACHE` at a temporary directory so test runs never touch your real `~/.yoink` cache.

```
