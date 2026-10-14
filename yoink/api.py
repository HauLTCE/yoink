"""Library pipeline: acquire -> detect -> map -> graph -> resolve -> closure -> emit/verify."""

from __future__ import annotations

import tempfile
from pathlib import Path

from yoink.acquire import acquire
from yoink.acquire.license import detect_license
from yoink.config import Config
from yoink.errors import EmitError, StrictModeError, YoinkError
from yoink.gitignore import load_ignore
from yoink.lang.detect import detect_language
from yoink.manifest import Manifest, ManifestOutput, ManifestSource, ManifestVerified
from yoink.model import Closure, EmitResult, ModuleGraph, ModuleInfo, Source, VerifyResult
from yoink.verify import prepare_sandbox, run_verify

_GPL_FAMILY = ("gpl", "lgpl", "agpl")


def _get_spec_or_none(language: str):
    if language == "python" or language == "unknown":
        return None
    try:
        from yoink.lang import get_spec

        return get_spec(language)
    except Exception:
        return None


def _module_map(root: Path, language: str) -> dict[str, ModuleInfo]:
    if language == "python":
        from yoink import modulemap

        return modulemap.build_module_map(root)
    ignored = load_ignore(root)
    try:
        from yoink.graph import base as gbase
    except ImportError as e:  # w1a still in flight
        raise YoinkError(f"graph.base unavailable: {e}") from e
    fn = getattr(gbase, "build_generic_module_map", None)
    if fn is None:
        raise YoinkError("graph.base.build_generic_module_map missing")
    return fn(root, ignored)


def _build_graph(root: Path, language: str, mods: dict[str, ModuleInfo]) -> ModuleGraph:
    from yoink.graph import base as gbase

    build = getattr(gbase, "build_graph", None)
    if build is None:
        try:
            from yoink import graph as graph_pkg

            build = getattr(graph_pkg, "build_graph")
        except (ImportError, AttributeError) as e:
            raise YoinkError("graph.build_graph missing") from e
    return build(root, language, mods)


def _resolve_target(
    mods: dict[str, ModuleInfo], graph: ModuleGraph, target: str, language: str
) -> tuple[str | None, str | None]:
    from yoink.graph import base as gbase

    return gbase.resolve_target(mods, graph.defns, target, language)


def _compute_closure(
    graph: ModuleGraph,
    mods: dict[str, ModuleInfo],
    target_module: str | None,
    target_symbol: str | None,
    *,
    max_depth: int,
    source_root: Path,
    spec=None,
) -> Closure:
    import inspect

    from yoink.closure import compute_closure

    kwargs: dict = {"max_depth": max_depth, "source_root": source_root}
    if spec is not None:
        try:
            if "spec" in inspect.signature(compute_closure).parameters:
                kwargs["spec"] = spec
        except (TypeError, ValueError):
            kwargs["spec"] = spec  # introspection failed; try anyway
    return compute_closure(graph, mods, target_module, target_symbol, **kwargs)


def _emit_bundle(
    graph: ModuleGraph,
    closure: Closure,
    source_root: Path,
    out_dir: Path,
    *,
    force: bool,
) -> EmitResult:
    import inspect

    try:
        from yoink.emit import emit_bundle
    except ImportError:
        from yoink.emit.bundle import emit_bundle  # type: ignore[no-redef]
    kwargs: dict = {}
    try:
        if "force" in inspect.signature(emit_bundle).parameters:
            kwargs["force"] = force
    except (TypeError, ValueError):
        kwargs["force"] = force
    return emit_bundle(graph, closure, source_root, out_dir, **kwargs)


def _emit_flat(
    graph: ModuleGraph,
    closure: Closure,
    source_root: Path,
    out_path: Path,
    *,
    spec=None,
) -> EmitResult:
    import inspect

    try:
        from yoink.emit import emit_flat
    except ImportError:
        from yoink.emit.flat import emit_flat  # type: ignore[no-redef]
    kwargs: dict = {}
    if spec is not None:
        try:
            if "spec" in inspect.signature(emit_flat).parameters:
                kwargs["spec"] = spec
        except (TypeError, ValueError):
            kwargs["spec"] = spec
    return emit_flat(graph, closure, source_root, out_path, **kwargs)


def _emit_zip(out_dir: Path, zip_path: Path | None, *, default_name: str) -> Path:
    try:
        from yoink.emit import emit_zip
    except ImportError:
        from yoink.emit.zip import emit_zip  # type: ignore[no-redef]
    return emit_zip(out_dir, zip_path, default_name=default_name)


def _flat_default_name(target: str, language: str, flat_name: str | None) -> str:
    if flat_name:
        return flat_name
    sym = target.split(":")[-1] if ":" in target else target
    sym = sym.split(".")[-1] if "." in sym else sym
    sym = sym.replace("/", "_").replace("\\", "_") or "extract"
    ext = {
        "python": ".py",
        "csharp": ".cs",
        "jsts": ".ts",
        "go": ".go",
        "rust": ".rs",
        "java": ".java",
        "cpp": ".cpp",
        "ruby": ".rb",
        "php": ".php",
    }.get(language, ".txt")
    if sym.endswith(ext):
        return sym
    return f"{sym}{ext}"


def _manifest_for(
    source: Source,
    commit: str | None,
    license_id: str | None,
    language: str,
    target: str,
    resolution: str,
    mode: str,
) -> Manifest:
    return Manifest(
        source=ManifestSource(
            kind=source.kind,
            repo=source.display,
            ref=source.ref,
            commit=commit,
            license=license_id,
            language=language,
            target=target,
        ),
        resolution=resolution,
        mode=mode,
    )


def _populate_from_closure(manifest: Manifest, closure: Closure) -> None:
    manifest.modules = sorted(closure.modules)
    manifest.stdlib = sorted(closure.stdlib)
    manifest.external_deps = list(closure.external)
    manifest.unresolved = list(closure.unresolved)
    if closure.depth_hit:
        manifest.warnings.append("max depth reached — closure truncated")


def _fill_output(manifest: Manifest, result: EmitResult, out_dir: Path) -> None:
    rel_files: list[str] = []
    total_lines = 0
    for f in result.files:
        p = Path(f)
        try:
            rel = p.relative_to(out_dir).as_posix()
        except ValueError:
            rel = p.name
        rel_files.append(rel)
        try:
            total_lines += sum(1 for _ in p.open("r", encoding="utf-8", errors="replace"))
        except OSError:
            pass
    manifest.output = ManifestOutput(files=rel_files, lines=total_lines)


def analyze(
    source: str | Path,
    target: str,
    *,
    max_depth: int | None = None,
    config: Config | None = None,
    cache_dir: Path | None = None,
) -> Closure:
    """Run acquire+graph+closure with no emit; return the Closure (doctor)."""
    cfg = config or Config()
    depth = max_depth if max_depth is not None else cfg.max_depth

    root, src, _commit = acquire(str(source), cache_dir)
    language = detect_language(root)
    mods = _module_map(root, language)
    graph = _build_graph(root, language, mods)
    tmod, tsym = _resolve_target(mods, graph, target, language)
    spec = _get_spec_or_none(language)
    closure = _compute_closure(
        graph, mods, tmod, tsym, max_depth=depth, source_root=root, spec=spec
    )
    closure.target = target
    return closure


def extract(
    source: str | Path,
    target: str,
    *,
    mode: str = "bundle",
    out: Path | str | None = None,
    flat_name: str | None = None,
    zip_out: bool = False,
    test_cmd: str | None = None,
    strict: bool = False,
    max_depth: int | None = None,
    config: Config | None = None,
    cache_dir: Path | None = None,
    force: bool = False,
    verbose: bool = False,
) -> Manifest:
    """Full pipeline; returns the Manifest (also written to disk when emitting)."""
    if mode not in ("bundle", "flat", "doctor"):
        raise EmitError(f"unknown mode: {mode!r}")
    cfg = config or Config()
    depth = max_depth if max_depth is not None else cfg.max_depth

    root, src, commit = acquire(str(source), cache_dir)
    language = detect_language(root)
    mods = _module_map(root, language)
    graph = _build_graph(root, language, mods)
    tmod, tsym = _resolve_target(mods, graph, target, language)
    spec = _get_spec_or_none(language)
    closure = _compute_closure(
        graph, mods, tmod, tsym, max_depth=depth, source_root=root, spec=spec
    )
    closure.target = target

    license_id = detect_license(root)
    manifest = _manifest_for(
        src,
        commit,
        license_id,
        language,
        target,
        closure.resolution,
        mode,
    )
    _populate_from_closure(manifest, closure)

    if language != "python":
        manifest.warnings.append(
            f"resolution: text — regex-based graph for {language}, verify imports"
        )
    if license_id and any(license_id.lower().startswith(p) for p in _GPL_FAMILY):
        manifest.warnings.append(
            f"source license {license_id} is copyleft — check obligations"
        )

    out_dir: Path | None = None
    emit_result: EmitResult | None = None

    if mode == "doctor":
        if out is not None:
            out_dir = Path(out)
            out_dir.mkdir(parents=True, exist_ok=True)
            manifest.write(out_dir / "yoink.manifest.json")
        return manifest

    if out is None:
        configured = cfg.out_dir
        out_dir = Path(configured) if configured else Path.cwd() / "yoink-out"
    else:
        out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "bundle":
        emit_result = _emit_bundle(graph, closure, root, out_dir, force=force)
    else:  # flat
        fname = _flat_default_name(target, language, flat_name)
        flat_path = out_dir / fname
        emit_result = _emit_flat(graph, closure, root, flat_path, spec=spec)

    manifest.warnings.extend(emit_result.warnings)
    _fill_output(manifest, emit_result, out_dir)

    manifest_path = out_dir / "yoink.manifest.json"
    manifest.write(manifest_path)

    if zip_out:
        try:
            zip_path = _emit_zip(out_dir, None, default_name=f"yoink-bundle-{target.replace(':', '_')}")
        except Exception as e:
            raise EmitError(f"zip failed: {e}") from e
        manifest.warnings.append(f"zip written: {zip_path}")

    if test_cmd is not None:
        sandbox = prepare_sandbox(out_dir)
        vres: VerifyResult = run_verify(
            test_cmd, sandbox, policy=cfg.execute, assume_yes=force
        )
        manifest.verified = ManifestVerified(
            status=vres.status,
            command=vres.command,
            passed=(True if vres.status == "passed" else (False if vres.status == "failed" else None)),
            detail=vres.detail,
        )
        manifest.write(manifest_path)

    if strict and closure.unresolved:
        raise StrictModeError(f"{len(closure.unresolved)} unresolved refs")

    return manifest


__all__ = ["extract", "analyze"]
