from __future__ import annotations

import pytest

from yoink.acquire import acquire, is_local_spec, parse_source
from yoink.acquire.cache import cache_root, cache_size, clear_cache, list_cached
from yoink.acquire.git import clone_url
from yoink.acquire.license import detect_license
from yoink.errors import AcquireError


def test_local(tmp_path):
    path, src, commit = acquire(str(tmp_path))
    assert src.kind == "local" and path == tmp_path.resolve() and commit is None


def test_local_missing(tmp_path):
    with pytest.raises(AcquireError):
        acquire(str(tmp_path / "nope"))


def test_parse_gh():
    s = parse_source("gh:owner/repo@v1.2")
    assert s.kind == "gh" and s.ref == "v1.2"
    assert clone_url(s) == "https://github.com/owner/repo"


def test_parse_gh_noref():
    s = parse_source("gh:o/r")
    assert s.kind == "gh" and s.ref is None


def test_parse_url():
    s = parse_source("https://github.com/o/r.git@dev")
    assert s.kind == "url" and s.ref == "dev"


def test_parse_ssh():
    s = parse_source("git@github.com:o/r")
    assert s.kind == "url"


def test_is_local(tmp_path):
    assert is_local_spec(str(tmp_path))
    assert is_local_spec("./x")
    assert is_local_spec("~/x")
    assert not is_local_spec("gh:o/r")


def test_detect_license(make_repo):
    mit = make_repo({"LICENSE": "MIT License\n\nPermission is hereby granted, free of charge"})
    assert detect_license(mit) == "MIT"
    gpl = make_repo({"LICENSE": "GNU GENERAL PUBLIC LICENSE\nVersion 3"})
    assert detect_license(gpl) == "GPL-3.0"
    none = make_repo({"x.py": ""})
    assert detect_license(none) is None


def test_cache_ops(tmp_path):
    c = cache_root(tmp_path / "c")
    assert c.is_dir()
    (c / "repos").mkdir(exist_ok=True)
    (c / "repos" / "k1").mkdir()
    (c / "repos" / "k1" / "f").write_text("x")
    assert len(list_cached(c)) == 1
    assert cache_size(c) > 0
    assert clear_cache(c) == 1
    assert len(list_cached(c)) == 0


def test_cache_env(monkeypatch, tmp_path):
    monkeypatch.setenv("YOINK_CACHE", str(tmp_path / "env"))
    assert cache_root() == tmp_path / "env"
