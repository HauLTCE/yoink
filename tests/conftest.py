from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "repos"

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture()
def fixture():
    def _get(name: str) -> Path:
        p = FIXTURES / name
        assert p.is_dir(), f"fixture missing: {name}"
        return p

    return _get


@pytest.fixture(autouse=True)
def cache_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("YOINK_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


@pytest.fixture()
def make_repo(tmp_path: Path):
    counter = [0]

    def _make(files: dict[str, str], name: str = "") -> Path:
        counter[0] += 1
        root = tmp_path / (name or f"repo{counter[0]}")
        for rel, content in files.items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        return root

    return _make


@pytest.fixture()
def run_cli():
    from typer.testing import CliRunner
    from yoink.cli import extract_app

    runner = CliRunner()

    def _run(*args: str):
        return runner.invoke(extract_app, list(args))

    return _run
