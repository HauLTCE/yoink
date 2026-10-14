"""yoink.manifest.json (schema v1) dataclass + serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from yoink import __version__
from yoink.model import ExternalDep, Unresolved, VerifyResult
from yoink.util import iso_now


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
    yoink_version: str = __version__
    schema_version: int = 1
    source: ManifestSource | dict = field(default_factory=ManifestSource)
    resolution: str = "ast"
    mode: str = "bundle"
    output: ManifestOutput | dict = field(default_factory=ManifestOutput)
    modules: list[str] = field(default_factory=list)
    stdlib: list[str] = field(default_factory=list)
    external_deps: list[ExternalDep | dict] = field(default_factory=list)
    unresolved: list[Unresolved | dict] = field(default_factory=list)
    untranslated: list = field(default_factory=list)
    verified: ManifestVerified | VerifyResult | dict = field(default_factory=ManifestVerified)
    warnings: list[str] = field(default_factory=list)
    created: str = field(default_factory=iso_now)

    def to_dict(self) -> dict:
        """Serialize to schema v1 dict, keys in spec order."""
        return {
            "yoink_version": self.yoink_version,
            "schema_version": self.schema_version,
            "source": _source_to_dict(self.source),
            "resolution": self.resolution,
            "mode": self.mode,
            "output": _output_to_dict(self.output),
            "modules": list(self.modules),
            "stdlib": list(self.stdlib),
            "external_deps": [dep_to_dict(d) for d in self.external_deps],
            "unresolved": [unresolved_to_dict(u) for u in self.unresolved],
            "untranslated": list(self.untranslated),
            "verified": _verified_to_dict(self.verified),
            "warnings": list(self.warnings),
            "created": self.created,
        }

    def write(self, path: Path) -> Path:
        """Write manifest JSON (indent 2) to path, creating parents."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def dep_to_dict(dep: ExternalDep | dict) -> dict:
    """ExternalDep -> {name, version, evidence}."""
    if isinstance(dep, dict):
        return {"name": dep.get("name"), "version": dep.get("version"), "evidence": dep.get("evidence", "")}
    return {"name": dep.name, "version": dep.version, "evidence": dep.evidence}


def unresolved_to_dict(u: Unresolved | dict) -> dict:
    """Unresolved -> {file, line, kind, name, detail} (lineno maps to 'line')."""
    if isinstance(u, dict):
        return {
            "file": u.get("file"),
            "line": u.get("line", u.get("lineno")),
            "kind": u.get("kind"),
            "name": u.get("name"),
            "detail": u.get("detail", ""),
        }
    return {"file": u.file, "line": u.lineno, "kind": u.kind, "name": u.name, "detail": u.detail}


def _source_to_dict(source: ManifestSource | dict) -> dict:
    if isinstance(source, dict):
        return {
            "kind": source.get("kind"),
            "repo": source.get("repo"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
            "license": source.get("license"),
            "language": source.get("language"),
            "target": source.get("target"),
        }
    return {
        "kind": source.kind,
        "repo": source.repo,
        "ref": source.ref,
        "commit": source.commit,
        "license": source.license,
        "language": source.language,
        "target": source.target,
    }


def _output_to_dict(output: ManifestOutput | dict) -> dict:
    if isinstance(output, dict):
        return {"files": list(output.get("files", [])), "lines": output.get("lines", 0)}
    return {"files": list(output.files), "lines": output.lines}


def _verified_to_dict(verified: ManifestVerified | VerifyResult | dict) -> dict:
    if isinstance(verified, dict):
        return {
            "status": verified.get("status", "not_run"),
            "command": verified.get("command"),
            "passed": verified.get("passed"),
            "detail": verified.get("detail", ""),
        }
    if isinstance(verified, ManifestVerified):
        return {
            "status": verified.status,
            "command": verified.command,
            "passed": verified.passed,
            "detail": verified.detail,
        }
    passed: bool | None = None
    if verified.status == "passed":
        passed = True
    elif verified.status == "failed":
        passed = False
    return {
        "status": verified.status,
        "command": verified.command,
        "passed": passed,
        "detail": verified.detail,
    }
