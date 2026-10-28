"""Registry of language specifications across 14 non-Python ecosystems (plus Python AST)."""

from __future__ import annotations

from .cpp import CPP_SPEC
from .csharp import CSHARP_SPEC
from .dart import DART_SPEC
from .elixir import ELIXIR_SPEC
from .go import GO_SPEC
from .java import JAVA_SPEC
from .jsts import JSTS_SPEC
from .kotlin import KOTLIN_SPEC
from .lua import LUA_SPEC
from .php import PHP_SPEC
from .ruby import RUBY_SPEC
from .rust import RUST_SPEC
from .scala import SCALA_SPEC
from .swift import SWIFT_SPEC

ALL_SPECS = (
    JSTS_SPEC,
    GO_SPEC,
    RUST_SPEC,
    CPP_SPEC,
    CSHARP_SPEC,
    JAVA_SPEC,
    PHP_SPEC,
    RUBY_SPEC,
    KOTLIN_SPEC,
    SWIFT_SPEC,
    DART_SPEC,
    SCALA_SPEC,
    LUA_SPEC,
    ELIXIR_SPEC,
)

__all__ = [
    "ALL_SPECS",
    "JSTS_SPEC",
    "GO_SPEC",
    "RUST_SPEC",
    "CPP_SPEC",
    "CSHARP_SPEC",
    "JAVA_SPEC",
    "PHP_SPEC",
    "RUBY_SPEC",
    "KOTLIN_SPEC",
    "SWIFT_SPEC",
    "DART_SPEC",
    "SCALA_SPEC",
    "LUA_SPEC",
    "ELIXIR_SPEC",
]
