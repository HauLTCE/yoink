"""yoink.toml discovery + parsing."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from yoink.errors import ConfigError

_ALLOWED: dict[str, dict[str, type | tuple[type, ...]]] = {
    "extract": {"granularity": str, "external": str, "max_depth": int},
    "safety": {"execute": str},
    "output": {"dir": str},
}


@dataclass
class Config:
    granularity: str = "file"
    external: str = "list"
    max_depth: int = 12
    execute: str = "ask"
    out_dir: str | None = None


def load_config(start: Path | None = None) -> Config:
    """Nearest-ancestor yoink.toml -> Config; absent file -> defaults."""
    cfg = Config()
    path = _find_config(Path.cwd() if start is None else Path(start))
    if path is None:
        return cfg
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise ConfigError(f"bad yoink.toml at {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"bad yoink.toml at {path}")
    for section_name, section in data.items():
        if section_name not in _ALLOWED:
            raise ConfigError(f"unknown key in {path.name}: {section_name}")
        if not isinstance(section, dict):
            raise ConfigError(f"key {section_name} in {path.name} must be a table")
        for key, value in section.items():
            if key not in _ALLOWED[section_name]:
                raise ConfigError(f"unknown key in {path.name}: {section_name}.{key}")
            expected = _ALLOWED[section_name][key]
            if expected is int:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ConfigError(
                        f"key {section_name}.{key} in {path.name} must be int"
                    )
            elif not isinstance(value, expected):
                want = expected.__name__ if isinstance(expected, type) else expected
                raise ConfigError(
                    f"key {section_name}.{key} in {path.name} must be {want}"
                )
            setattr(cfg, "out_dir" if key == "dir" else key, value)
    return cfg


def _find_config(start: Path) -> Path | None:
    cur = start if start.is_dir() else start.parent
    for d in (cur, *cur.parents):
        p = d / "yoink.toml"
        if p.is_file():
            return p
    return None
