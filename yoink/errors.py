"""Exception tree for yoink."""

from __future__ import annotations


class YoinkError(Exception):
    """Base for all yoink errors."""


class AcquireError(YoinkError):
    """Source could not be fetched/located."""


class SourceNotFoundError(AcquireError):
    """The source path/repo does not exist."""


class SymbolNotFoundError(YoinkError):
    """Target symbol not found, or ambiguous."""

    def __init__(self, symbol: str, candidates: list[str] | None = None) -> None:
        self.symbol = symbol
        self.candidates: list[str] = candidates or []
        msg = f"symbol not found: {symbol}"
        if self.candidates:
            joined = ", ".join(self.candidates)
            msg = f"ambiguous symbol {symbol!r}; candidates: {joined}"
        super().__init__(msg)


class ParseError(YoinkError):
    """Source file could not be parsed."""


class EmitError(YoinkError):
    """Output emission failed."""


class VerifyError(YoinkError):
    """Post-extract verification failed."""


class ConfigError(YoinkError):
    """yoink.toml invalid."""


class SafetyError(YoinkError):
    """Safety policy refused an action."""


class StrictModeError(YoinkError):
    """--strict tripped on unresolved refs."""
