"""Dataclasses and serialization logic for yoink.manifest.json (schema v1)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from yoink.model import ExternalDep, Unresolved, VerifyResult


@dataclass
class ManifestSource:
    kind: str = "local"
    repo: str = ""
    ref: str | None = None
    commit: str | None = None
    license: str | None = None
    language: str = "unknown"
    target: str = ""


@dataclass
class ManifestOutput:
    files: list[str] = field(default_factory=list)
    lines: int = 0


@dataclass
class ManifestVerified:
    status: str = "not_run"
    command: str | None = None
    passed: bool | None = None
    detail: str = ""


@dataclass
class Manifest:
    yoink_version: str
    schema_version: int = 1
    source: ManifestSource | dict[str, Any] = field(default_factory=ManifestSource)
    resolution: str = "ast"
    mode: str = "bundle"
    output: ManifestOutput | dict[str, Any] = field(default_factory=ManifestOutput)
    modules: list[str] = field(default_factory=list)
    stdlib: list[str] = field(default_factory=list)
    external_deps: list[ExternalDep | dict[str, Any]] = field(default_factory=list)
    unresolved: list[Unresolved | dict[str, Any]] = field(default_factory=list)
    untranslated: list[Any] = field(default_factory=list)
    verified: ManifestVerified | VerifyResult | dict[str, Any] = field(default_factory=ManifestVerified)
    warnings: list[str] = field(default_factory=list)
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        def _conv(obj: Any) -> Any:
            if is_dataclass(obj) and not isinstance(obj, type):
                return {k: _conv(v) for k, v in asdict(obj).items()}
            if isinstance(obj, Path):
                return obj.as_posix()
            if isinstance(obj, (list, tuple, set, frozenset)):
                return [_conv(x) for x in obj]
            if isinstance(obj, dict):
                return {str(k): _conv(v) for k, v in obj.items()}
            return obj

        return _conv(self)


def write_manifest(manifest: Manifest, path: Path) -> None:
    """Write formatted JSON manifest file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Manifest:
    """Deserialize JSON file into Manifest instance."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    src = data.get("source", {})
    out = data.get("output", {})
    ver = data.get("verified", {})
    return Manifest(
        yoink_version=data.get("yoink_version", "2.0.0"),
        schema_version=data.get("schema_version", 1),
        source=ManifestSource(**src) if isinstance(src, dict) else src,
        resolution=data.get("resolution", "ast"),
        mode=data.get("mode", "bundle"),
        output=ManifestOutput(**out) if isinstance(out, dict) else out,
        modules=list(data.get("modules", [])),
        stdlib=list(data.get("stdlib", [])),
        external_deps=[
            ExternalDep(**d) if isinstance(d, dict) else d
            for d in data.get("external_deps", [])
        ],
        unresolved=[
            Unresolved(**u) if isinstance(u, dict) else u
            for u in data.get("unresolved", [])
        ],
        untranslated=list(data.get("untranslated", [])),
        verified=ManifestVerified(
            status=ver.get("status", "not_run"),
            command=ver.get("command"),
            passed=ver.get("passed"),
            detail=ver.get("detail", ""),
        )
        if isinstance(ver, dict)
        else ver,
        warnings=list(data.get("warnings", [])),
        created=data.get("created", ""),
    )
