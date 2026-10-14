"""Typer entrypoint: `yoink <src> --grab <target>` plus `yoink cache` subcommands."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from yoink import __version__, api
from yoink.acquire.cache import cache_root, clear_cache, list_cached
from yoink.config import load_config
from yoink.errors import StrictModeError, YoinkError
from yoink.model import Closure, ExternalDep, Unresolved
from yoink.report import closure_to_dict, print_doctor, print_error, print_result

# two typer apps: extract_app is single-command so `yoink <src> --grab x` parses
# naturally; `yoink cache ...` is dispatched in app() before typer sees argv.
extract_app = typer.Typer(
    name="yoink",
    help="Surgical feature extractor — grab a symbol + its dependency closure.",
    add_completion=False,
    no_args_is_help=True,
)
cache_app = typer.Typer(
    name="yoink cache",
    help="Manage the cloned-repo cache.",
    add_completion=False,
    no_args_is_help=True,
)


def _pick_mode(mode: str | None, bundle: bool, flat: bool, doctor: bool) -> str:
    picked = [n for n, f in (("bundle", bundle), ("flat", flat), ("doctor", doctor)) if f]
    if len(picked) > 1:
        raise YoinkError(f"conflicting mode flags: {', '.join('--' + p for p in picked)}")
    shortcut = picked[0] if picked else None
    if mode is not None and shortcut is not None and mode != shortcut:
        raise YoinkError(f"conflicting modes: --mode {mode} and --{shortcut}")
    return shortcut or mode or "bundle"


def _manifest_to_closure(manifest, target: str) -> Closure:
    src = manifest.source
    return Closure(
        target=target,
        language=src.language if hasattr(src, "language") else src.get("language", "unknown"),
        resolution=manifest.resolution,
        modules=set(manifest.modules),
        external=[
            ExternalDep(
                name=d.name if hasattr(d, "name") else d.get("name", ""),
                version=d.version if hasattr(d, "version") else d.get("version"),
                evidence=d.evidence if hasattr(d, "evidence") else d.get("evidence", ""),
            )
            for d in manifest.external_deps
        ],
        stdlib=set(manifest.stdlib),
        unresolved=[
            Unresolved(
                file=u.file if hasattr(u, "file") else u.get("file", ""),
                lineno=u.lineno if hasattr(u, "lineno") else u.get("line", 0),
                name=u.name if hasattr(u, "name") else u.get("name", ""),
                kind=u.kind if hasattr(u, "kind") else u.get("kind", ""),
                detail=u.detail if hasattr(u, "detail") else u.get("detail", ""),
            )
            for u in manifest.unresolved
        ],
    )


@extract_app.command()
def _extract(
    src: Optional[str] = typer.Argument(None, help="Local path, gh:owner/repo[@ref], or URL."),
    grab: Optional[str] = typer.Option(None, "--grab", help="Target: pkg.mod:sym | path/File.cs:sym | bare sym."),
    mode: Optional[str] = typer.Option(None, "--mode", help="bundle | flat | doctor"),
    bundle: bool = typer.Option(False, "--bundle", help="Shortcut for --mode bundle."),
    flat: bool = typer.Option(False, "--flat", help="Shortcut for --mode flat."),
    doctor: bool = typer.Option(False, "--doctor", help="Shortcut for --mode doctor."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output directory."),
    zip_out: bool = typer.Option(False, "--zip", help="Also write a .zip of the bundle."),
    flat_name: Optional[str] = typer.Option(None, "--flat-name", help="Flat output filename."),
    test: Optional[str] = typer.Option(None, "--test", help="Post-extract verify command."),
    strict: bool = typer.Option(False, "--strict", help="Exit 2 if unresolved refs."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
    max_depth: Optional[int] = typer.Option(None, "--max-depth", help="BFS depth cap."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing output; skip --test prompt."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Noisier logging."),
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(f"yoink {__version__}")
        raise typer.Exit()
    try:
        if not src:
            raise YoinkError("missing source argument: yoink <src> --grab <target>")
        if not grab:
            raise YoinkError("missing required --grab <target>")
        chosen_mode = _pick_mode(mode, bundle, flat, doctor)
        cfg = load_config()

        if json_out and chosen_mode == "doctor":
            closure = api.analyze(src, grab, max_depth=max_depth, config=cfg)
            print(json.dumps(closure_to_dict(closure), indent=2))
            raise typer.Exit()

        manifest = api.extract(
            src,
            grab,
            mode=chosen_mode,
            out=out,
            flat_name=flat_name,
            zip_out=zip_out,
            test_cmd=test,
            strict=strict,
            max_depth=max_depth,
            config=cfg,
            force=force,
            verbose=verbose,
        )

        if json_out:
            print(json.dumps(manifest.to_dict(), indent=2))
        elif chosen_mode == "doctor":
            closure = api.analyze(src, grab, max_depth=max_depth, config=cfg)
            print_doctor(closure, manifest.to_dict())
        else:
            out_path = Path(out) if out else (Path(cfg.out_dir) if cfg.out_dir else None)
            print_result(manifest, out_path)
    except StrictModeError as e:
        print_error(e)
        raise typer.Exit(code=2)
    except YoinkError as e:
        print_error(e)
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        raise typer.Exit(code=130)


@cache_app.command("list")
def cache_list(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Show cached repo clones."""
    entries = list_cached()
    if json_out:
        print(
            json.dumps(
                [
                    {
                        "key": e["key"],
                        "path": str(e["path"]),
                        "size_mb": e["size_mb"],
                        "mtime": e["mtime"],
                    }
                    for e in entries
                ],
                indent=2,
            )
        )
        return
    if not entries:
        typer.echo("cache empty")
        return
    for e in entries:
        typer.echo(f"{e['key']}  {e['size_mb']:>8.2f} MB  {e['path']}")


@cache_app.command("clear")
def cache_clear() -> None:
    """Delete every cached clone."""
    n = clear_cache()
    typer.echo(f"removed {n} cached repo{'s' if n != 1 else ''}")


@cache_app.command("dir")
def cache_dir() -> None:
    """Print the cache root path."""
    typer.echo(str(cache_root()))


def app() -> None:
    """Console-script entry: dispatch `yoink cache ...` vs the extract app."""
    argv = sys.argv[1:]
    if argv and argv[0] == "cache":
        sys.argv = [sys.argv[0], *argv[1:]]
        cache_app()
        return
    extract_app()


if __name__ == "__main__":
    app()
