"""Shared vocabulary: frozen dataclasses every stage passes around."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# language ids: python|csharp|jsts|go|rust|java|cpp|ruby|php|unknown


@dataclass(frozen=True)
class Source:
    kind: str  # "local" | "gh" | "url"
    display: str
    ref: str | None = None


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    package: str | None
    is_pkg_init: bool


@dataclass(frozen=True)
class ImportEdge:
    importer: str
    module: str  # raw-or-resolved
    names: tuple[tuple[str, str | None], ...] = ()
    level: int = 0
    kind: str = "static"
    lineno: int = 0


@dataclass(frozen=True)
class SymbolEdge:
    module: str
    name: str
    lineno: int


@dataclass(frozen=True)
class Defn:
    name: str
    kind: str  # "func" | "class" | "assign" | "import"
    lineno: int
    end_lineno: int
    decorators: tuple[str, ...] = ()


@dataclass(frozen=True)
class Unresolved:
    # kind: dynamic_import | getattr_dynamic | star_import | unresolvable_name | plugin | resource | native
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
    resolution: str  # "ast" | "text"
    modules: set[str] = field(default_factory=set)
    external: list[ExternalDep] = field(default_factory=list)
    stdlib: set[str] = field(default_factory=set)
    unresolved: list[Unresolved] = field(default_factory=list)
    depth_hit: bool = False


@dataclass
class EmitResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_dir: Path = Path(".")


@dataclass
class VerifyResult:
    status: str = "not_run"  # "passed" | "failed" | "not_run" | "skipped"
    command: str | None = None
    detail: str = ""
    exit_code: int | None = None
