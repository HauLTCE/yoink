from __future__ import annotations

import pytest

from yoink.config import Config, load_config
from yoink.errors import ConfigError


def test_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = load_config()
    assert c.granularity == "file" and c.max_depth == 12 and c.execute == "ask"


def test_parse(tmp_path, monkeypatch):
    (tmp_path / "yoink.toml").write_text(
        '[extract]\ngranularity="symbol"\nexternal="vendor"\nmax_depth=5\n'
        '[safety]\nexecute="always"\n[output]\ndir="outx"\n'
    )
    monkeypatch.chdir(tmp_path)
    c = load_config()
    assert c.granularity == "symbol" and c.external == "vendor" and c.max_depth == 5
    assert c.execute == "always" and str(c.out_dir).endswith("outx")


def test_bad_key(tmp_path, monkeypatch):
    (tmp_path / "yoink.toml").write_text('[extract]\nbogus=1\n')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_config()


def test_bad_toml(tmp_path, monkeypatch):
    (tmp_path / "yoink.toml").write_text('not = = toml')
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_config()
