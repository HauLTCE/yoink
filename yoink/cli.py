"""CLI interface for yoink (supports Typer when installed, with zero-dependency argparse fallback)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from yoink import __version__
from yoink.api import analyze as api_analyze
from yoink.api import yoink as api_yoink
from yoink.errors import StrictModeError, YoinkError
from yoink.report import print_doctor, print_error, print_result

try:
    import typer

    _HAS_TYPER = True
except ImportError:
    typer = None  # type: ignore[assignment]
    _HAS_TYPER = False


def _run_extract(
    src: str = ".",
    grab: Optional[str] = None,
    mode: str = "bundle",
    bundle: bool = False,
    flat: bool = False,
    doctor: bool = False,
    out: Optional[Path] = None,
    zip_out: bool = False,
    flat_name: Optional[str] = None,
    language: Optional[str] = None,
    test: Optional[str] = None,
    strict: bool = False,
    allow_gpl: bool = False,
    json_out: bool = False,
    max_depth: Optional[int] = None,
    force: bool = False,
) -> int:
    eff_mode = "flat" if flat else ("doctor" if doctor else ("bundle" if bundle else mode))
    try:
        if eff_mode == "doctor" and grab:
            closure = api_analyze(
                grab,
                repo=src,
                language=language,
                allow_gpl=allow_gpl or True,
                max_depth=max_depth,
            )
            if strict and closure.unresolved:
                raise StrictModeError("unresolved references detected in strict mode")
            print_doctor(closure, json_mode=json_out)
            return 0

        manifest, emit_res, _ = api_yoink(
            src,
            symbol=grab,
            out=out,
            mode=eff_mode,
            language=language,
            max_depth=max_depth,
            allow_gpl=allow_gpl,
            test=test,
            strict=strict,
            force=force,
            as_zip=zip_out,
            flat_name=flat_name,
        )
        print_result(manifest, emit_res.output_dir, json_mode=json_out)
        return 0
    except StrictModeError as e:
        print_error(e)
        return 2
    except YoinkError as e:
        print_error(e)
        return 1


def _run_analyze(
    target: str,
    repo: str = ".",
    language: Optional[str] = None,
    json_out: bool = False,
    strict: bool = False,
) -> int:
    try:
        closure = api_analyze(target, repo=repo, language=language, allow_gpl=True)
        print_doctor(closure, json_mode=json_out)
        if strict and closure.unresolved:
            return 2
        return 0
    except YoinkError as e:
        print_error(e)
        return 1


if _HAS_TYPER:
    app = typer.Typer(
        name="yoink",
        help="Surgical feature extractor: pull a symbol plus its dependency closure out of a repo.",
        add_completion=False,
    )

    def _version_callback(value: bool) -> None:
        if value:
            typer.echo(f"yoink {__version__}")
            raise typer.Exit(0)

    @app.command("extract")
    def cmd_extract(
        src: str = typer.Argument(".", help="Source repository path, gh:owner/repo[@ref], or git URL."),
        grab: Optional[str] = typer.Option(None, "--grab", "-g", help="Target symbol/module."),
        mode: str = typer.Option("bundle", "--mode", "-m", help="Output mode: bundle, flat, or doctor."),
        bundle: bool = typer.Option(False, "--bundle", help="Shortcut for --mode bundle."),
        flat: bool = typer.Option(False, "--flat", help="Shortcut for --mode flat."),
        doctor: bool = typer.Option(False, "--doctor", help="Shortcut for --mode doctor."),
        out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output directory or file path."),
        zip_out: bool = typer.Option(False, "--zip", help="Package emitted output into a .zip archive."),
        flat_name: Optional[str] = typer.Option(None, "--flat-name", help="Custom filename for --flat mode."),
        language: Optional[str] = typer.Option(None, "--lang", "-l", help="Explicit language override."),
        test: Optional[str] = typer.Option(None, "--test", help="Post-extract verification command."),
        strict: bool = typer.Option(False, "--strict", help="Exit with code 2 if unresolved references exist."),
        allow_gpl: bool = typer.Option(False, "--allow-gpl", help="Permit extraction from GPL/LGPL/AGPL repositories."),
        json_out: bool = typer.Option(False, "--json", help="Emit structured JSON output."),
        max_depth: Optional[int] = typer.Option(None, "--max-depth", help="Max BFS traversal depth."),
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite non-empty output directory."),
        version: Optional[bool] = typer.Option(
            None, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
        ),
    ) -> None:
        code = _run_extract(
            src=src,
            grab=grab,
            mode=mode,
            bundle=bundle,
            flat=flat,
            doctor=doctor,
            out=out,
            zip_out=zip_out,
            flat_name=flat_name,
            language=language,
            test=test,
            strict=strict,
            allow_gpl=allow_gpl,
            json_out=json_out,
            max_depth=max_depth,
            force=force,
        )
        if code != 0:
            raise typer.Exit(code)

    @app.command("analyze")
    def cmd_analyze(
        target: str = typer.Argument(..., help="Target symbol or module to analyze."),
        repo: str = typer.Option(".", "--repo", "-r", help="Repository path or URL."),
        language: Optional[str] = typer.Option(None, "--lang", "-l", help="Explicit language override."),
        json_out: bool = typer.Option(False, "--json", help="Emit JSON report."),
        strict: bool = typer.Option(False, "--strict", help="Exit with code 2 on unresolved references."),
    ) -> None:
        code = _run_analyze(target=target, repo=repo, language=language, json_out=json_out, strict=strict)
        if code != 0:
            raise typer.Exit(code)
else:
    app = None


def _main_argparse(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args_list:
        print(f"yoink {__version__}")
        return 0

    parser = argparse.ArgumentParser(prog="yoink", description="Surgical feature extractor.")
    sub = parser.add_subparsers(dest="subcmd")

    p_ex = sub.add_parser("extract", help="Extract a symbol or module closure.")
    p_ex.add_argument("src", nargs="?", default=".")
    p_ex.add_argument("--grab", "-g", default=None)
    p_ex.add_argument("--mode", "-m", default="bundle")
    p_ex.add_argument("--bundle", action="store_true")
    p_ex.add_argument("--flat", action="store_true")
    p_ex.add_argument("--doctor", action="store_true")
    p_ex.add_argument("--out", "-o", default=None)
    p_ex.add_argument("--zip", dest="zip_out", action="store_true")
    p_ex.add_argument("--flat-name", default=None)
    p_ex.add_argument("--lang", "-l", dest="language", default=None)
    p_ex.add_argument("--test", default=None)
    p_ex.add_argument("--strict", action="store_true")
    p_ex.add_argument("--allow-gpl", action="store_true")
    p_ex.add_argument("--json", dest="json_out", action="store_true")
    p_ex.add_argument("--max-depth", type=int, default=None)
    p_ex.add_argument("--force", "-f", action="store_true")

    p_an = sub.add_parser("analyze", help="Analyze a target symbol's closure.")
    p_an.add_argument("target")
    p_an.add_argument("--repo", "-r", default=".")
    p_an.add_argument("--lang", "-l", dest="language", default=None)
    p_an.add_argument("--json", dest="json_out", action="store_true")
    p_an.add_argument("--strict", action="store_true")

    # Support shorthand `yoink <src> --grab <sym>` without explicit subcommand
    if not args_list or args_list[0] not in ("extract", "analyze", "-h", "--help"):
        args_list = ["extract", *args_list]

    ns = parser.parse_args(args_list)
    if ns.subcmd == "analyze":
        return _run_analyze(
            target=ns.target,
            repo=ns.repo,
            language=ns.language,
            json_out=ns.json_out,
            strict=ns.strict,
        )
    return _run_extract(
        src=ns.src,
        grab=ns.grab,
        mode=ns.mode,
        bundle=ns.bundle,
        flat=ns.flat,
        doctor=ns.doctor,
        out=Path(ns.out) if ns.out else None,
        zip_out=ns.zip_out,
        flat_name=ns.flat_name,
        language=ns.language,
        test=ns.test,
        strict=ns.strict,
        allow_gpl=ns.allow_gpl,
        json_out=ns.json_out,
        max_depth=ns.max_depth,
        force=ns.force,
    )


def main() -> None:
    if _HAS_TYPER and len(sys.argv) > 1 and sys.argv[1] in ("extract", "analyze", "--help", "-h", "--version"):
        app()
    else:
        sys.exit(_main_argparse())


if __name__ == "__main__":
    main()
