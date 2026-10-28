"""Shared domain models exchanged across yoink pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Source:
    kind: str  # "local" | "gh" | "url"
    display: str
    ref: str | None = None


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    package: str | None = None
    is_pkg_init: bool = False


@dataclass(frozen=True)
class ImportEdge:
    importer: str
    module: str
    names: tuple[tuple[str, str | None], ...] = ()
    level: int = 0
    kind: str = "static"  # "static" | "conditional" | "dynamic" | "implicit"
    lineno: int = 0


@dataclass(frozen=True)
class SymbolEdge:
    module: str
    name: str
    lineno: int = 0


@dataclass(frozen=True)
class Defn:
    name: str
    kind: str  # "func" | "class" | "assign" | "import" | "type" | "interface" | "struct" | "enum" | "trait" | "macro"
    lineno: int
    end_lineno: int
    decorators: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unresolved:
    file: str
    lineno: int
    name: str
    kind: str
    detail: str


@dataclass
class ModuleGraph:
    language: str
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    imports: list[ImportEdge] = field(default_factory=list)
    symbols: list[SymbolEdge] = field(default_factory=list)
    defns: dict[str, list[Defn]] = field(default_factory=dict)
    unresolved: list[Unresolved] = field(default_factory=list)


@dataclass
class ExternalDep:
    name: str
    version: str | None = None
    evidence: str = ""


@dataclass
class Closure:
    target: str
    language: str
    resolution: str  # "ast" | "text" | "hybrid"
    modules: set[str] = field(default_factory=set)
    external: list[ExternalDep] = field(default_factory=list)
    stdlib: set[str] = field(default_factory=set)
    unresolved: list[Unresolved] = field(default_factory=list)
    depth_hit: bool = False


@dataclass
class EmitResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path("."))


@dataclass
class VerifyResult:
    status: str = "not_run"  # "passed" | "failed" | "not_run" | "skipped"
    command: str | None = None
    detail: str = ""
    exit_code: int | None = None
