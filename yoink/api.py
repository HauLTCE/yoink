"""High-level Python API orchestrating the full yoink extraction & analysis pipeline."""

from __future__ import annotations

from pathlib import Path

from yoink import __version__
from yoink.acquire import acquire
from yoink.acquire.license import detect_license
from yoink.closure import compute_closure
from yoink.config import Config, load_config
from yoink.emit import emit_bundle, emit_flat, emit_zip
from yoink.errors import SourceNotFoundError, StrictModeError
from yoink.gitignore import load_ignore
from yoink.graph import build_graph, resolve_target
from yoink.lang import LangSpec, get_spec, normalize_lang_id
from yoink.lang.detect import detect_language
from yoink.lang.resolve import _mods_root
from yoink.manifest import (
    Manifest,
    ManifestOutput,
    ManifestSource,
    ManifestVerified,
    write_manifest,
)
from yoink.model import Closure, EmitResult, ModuleGraph, ModuleInfo, VerifyResult
from yoink.modulemap import build_module_map
from yoink.util import iso_now, posix_rel, read_text
from yoink.verify import run_verification

_GPL_FAMILY = ("gpl", "lgpl", "agpl")

_DEFAULT_FLAT_EXT: dict[str, str] = {
    "python": ".py",
    "jsts": ".ts",
    "go": ".go",
    "rust": ".rs",
    "cpp": ".cpp",
    "csharp": ".cs",
    "java": ".java",
    "php": ".php",
    "ruby": ".rb",
    "kotlin": ".kt",
    "swift": ".swift",
    "dart": ".dart",
    "scala": ".scala",
    "lua": ".lua",
    "elixir": ".ex",
}


def _get_spec_or_none(language: str) -> LangSpec | None:
    return get_spec(language)


def _module_map(root: Path, language: str) -> dict[str, ModuleInfo]:
    ignored = load_ignore(root)
    if language == "python":
        return build_module_map(root, ignored)
    spec = get_spec(language)
    if spec is None:
        return {}
    return _mods_root(root, spec, ignored)


def _build_graph(root: Path, language: str, mods: dict[str, ModuleInfo]) -> ModuleGraph:
    return build_graph(root, language, mods)


def _resolve_target(
    mods: dict[str, ModuleInfo],
    graph: ModuleGraph,
    target: str,
    language: str,
) -> tuple[str | None, str | None]:
    return resolve_target(mods, graph, target, language)


def _compute_closure(
    graph: ModuleGraph,
    target_module: str | None,
    target_symbol: str | None,
    source_root: Path,
    spec: LangSpec | None,
    max_depth: int | None,
    allow_gpl: bool,
) -> Closure:
    return compute_closure(
        graph,
        target_module,
        target_symbol,
        source_root=source_root,
        spec=spec,
        max_depth=max_depth,
        allow_gpl=allow_gpl,
    )


def yoink(
    source: str | Path,
    *,
    symbol: str | None = None,
    out: Path | str | None = None,
    mode: str = "bundle",
    ref: str | None = None,
    language: str | None = None,
    max_depth: int | None = None,
    allow_gpl: bool = False,
    test: str | None = None,
    strict: bool = False,
    emit_manifest: bool = True,
    force: bool = False,
    as_zip: bool = False,
    flat_name: str | None = None,
    config: Config | None = None,
) -> tuple[Manifest, EmitResult, VerifyResult]:
    """Run the full extraction pipeline: acquire -> detect -> map -> graph -> resolve -> closure -> emit -> verify."""
    src_str = str(source)
    if ref and "@" not in src_str and not Path(src_str).exists():
        src_str = f"{src_str}@{ref}"

    checkout_path, src_obj, commit_sha = acquire(src_str)
    if not checkout_path.exists():
        raise SourceNotFoundError(f"source path does not exist: {checkout_path}")

    cfg = config or load_config(checkout_path)
    eff_max_depth = max_depth if max_depth is not None else cfg.max_depth

    lang = normalize_lang_id(language) if language else detect_language(checkout_path)
    spec = _get_spec_or_none(lang)
    mods = _module_map(checkout_path, lang)
    graph = _build_graph(checkout_path, lang, mods)

    if symbol:
        target_mod, target_sym = _resolve_target(mods, graph, symbol, lang)
    else:
        target_mod, target_sym = (next(iter(sorted(mods.keys()))), None) if mods else (None, None)

    closure = _compute_closure(
        graph,
        target_mod,
        target_sym,
        checkout_path,
        spec,
        eff_max_depth,
        allow_gpl=allow_gpl,
    )

    if strict and closure.unresolved:
        names = ", ".join(f"{u.file}:{u.lineno}:{u.name}" for u in closure.unresolved)
        raise StrictModeError(f"strict mode failed on unresolved references: {names}")

    out_dir = Path(out) if out is not None else Path(cfg.out_dir or "./yoink_out")
    out_dir = out_dir.resolve()

    emit_res = EmitResult(output_dir=out_dir)
    if mode == "bundle":
        emit_res = emit_bundle(
            graph,
            closure,
            checkout_path,
            out_dir,
            granularity=cfg.granularity,
            force=force,
        )
    elif mode == "flat":
        ext = _DEFAULT_FLAT_EXT.get(lang, ".txt")
        if target_mod and target_mod in mods:
            ext = mods[target_mod].path.suffix or ext
        fname = flat_name or f"yoinked_{target_sym or 'bundle'}{ext}"
        flat_path = out_dir if out_dir.suffix else (out_dir / fname)
        emit_res = emit_flat(
            graph,
            closure,
            checkout_path,
            flat_path,
            spec=spec,
            target_symbol=target_sym,
            target_module=target_mod,
        )
    elif mode == "doctor":
        emit_res = EmitResult(files=[], warnings=[], output_dir=out_dir)

    total_lines = 0
    rel_files: list[str] = []
    for fpath in emit_res.files:
        total_lines += len(read_text(fpath).splitlines())
        rel_files.append(posix_rel(fpath, emit_res.output_dir))

    ver_res = VerifyResult(status="not_run")
    if test and mode != "doctor":
        ver_res = run_verification(emit_res.output_dir, test, policy=cfg.execute)

    lic = detect_license(checkout_path)
    manifest = Manifest(
        yoink_version=__version__,
        schema_version=1,
        source=ManifestSource(
            kind=src_obj.kind,
            repo=src_obj.display,
            ref=src_obj.ref,
            commit=commit_sha,
            license=lic,
            language=lang,
            target=closure.target,
        ),
        resolution=closure.resolution,
        mode=mode,
        output=ManifestOutput(files=rel_files, lines=total_lines),
        modules=sorted(closure.modules),
        stdlib=sorted(closure.stdlib),
        external_deps=list(closure.external),
        unresolved=list(closure.unresolved),
        untranslated=[],
        verified=ManifestVerified(
            status=ver_res.status,
            command=ver_res.command,
            passed=(ver_res.status == "passed") if ver_res.status in ("passed", "failed") else None,
            detail=ver_res.detail,
        ),
        warnings=list(emit_res.warnings),
        created=iso_now(),
    )

    if emit_manifest and mode in ("bundle", "flat"):
        manifest_dir = emit_res.output_dir
        manifest_path = manifest_dir / "yoink.manifest.json"
        write_manifest(manifest, manifest_path)

    if as_zip and mode in ("bundle", "flat"):
        zip_file = emit_zip(emit_res.output_dir)
        emit_res.files.append(zip_file)

    return manifest, emit_res, ver_res


def extract(
    target: str,
    repo: str | Path = ".",
    out: str | Path = "./yoink_out",
    *,
    mode: str = "bundle",
    language: str | None = None,
    allow_gpl: bool = True,
    force: bool = True,
    as_zip: bool = False,
    strict: bool = False,
) -> tuple[Manifest, EmitResult, VerifyResult]:
    """Convenience function matching `yoink.extract(target, repo=..., out=...)`."""
    return yoink(
        repo,
        symbol=target,
        out=out,
        mode=mode,
        language=language,
        allow_gpl=allow_gpl,
        force=force,
        as_zip=as_zip,
        strict=strict,
    )


def analyze(
    target: str,
    repo: str | Path = ".",
    *,
    language: str | None = None,
    allow_gpl: bool = True,
    max_depth: int | None = None,
) -> Closure:
    """Analyze a target symbol/module in `repo` and return its `Closure` without emitting files."""
    checkout_path, _, _ = acquire(str(repo))
    lang = normalize_lang_id(language) if language else detect_language(checkout_path)
    spec = _get_spec_or_none(lang)
    mods = _module_map(checkout_path, lang)
    graph = _build_graph(checkout_path, lang, mods)
    target_mod, target_sym = _resolve_target(mods, graph, target, lang)
    return _compute_closure(
        graph,
        target_mod,
        target_sym,
        checkout_path,
        spec,
        max_depth=max_depth,
        allow_gpl=allow_gpl,
    )


__all__ = ["yoink", "extract", "analyze"]
