from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from yoink.api import analyze, extract
from yoink.errors import AcquireError, StrictModeError, SymbolNotFoundError


def test_e2e_bundle(fixture, tmp_path):
    m = extract(str(fixture("reexport_chain")), "leaf", out=tmp_path / "o")
    d = m.to_dict()
    assert d["source"]["language"] == "python"
    assert (tmp_path / "o" / "yoink.manifest.json").exists()
    assert (tmp_path / "o" / "pkg" / "c.py").exists()


def test_e2e_flat(fixture, tmp_path):
    m = extract(str(fixture("side_effects")), "run", mode="flat", out=tmp_path / "o")
    assert m.output["files"] and (tmp_path / "o").rglob("*.py")


def test_e2e_doctor(fixture):
    c = analyze(str(fixture("reexport_chain")), "leaf")
    assert c.language == "python" and "pkg.c" in c.modules


def test_e2e_ambiguous(fixture):
    with pytest.raises(SymbolNotFoundError) as e:
        extract(str(fixture("ambiguous")), "run", out="/tmp/nope")
    assert e.value.candidates


def test_e2e_strict(fixture, tmp_path):
    with pytest.raises(StrictModeError):
        extract(str(fixture("dyn")), "main", out=tmp_path / "o", strict=True)
    assert (tmp_path / "o" / "yoink.manifest.json").exists()


def test_e2e_zip(fixture, tmp_path):
    extract(str(fixture("reexport_chain")), "leaf", out=tmp_path / "o", zip_out=True)
    zips = list(tmp_path.rglob("*.zip"))
    assert zips
    with zipfile.ZipFile(zips[0]) as z:
        assert "yoink.manifest.json" in z.namelist()


def test_e2e_license(fixture, tmp_path):
    m = extract(str(fixture("csharp_lib")), "Yoink", out=tmp_path / "o")
    assert m.source["license"] == "MIT"


def test_e2e_acquire_missing(tmp_path):
    with pytest.raises(AcquireError):
        extract(str(tmp_path / "nope"), "x", out=tmp_path / "o")


def test_e2e_generic_csharp(fixture, tmp_path):
    m = extract(str(fixture("csharp_lib")), "Yoink", out=tmp_path / "o")
    d = m.to_dict()
    assert d["source"]["language"] == "csharp"
    assert d["resolution"] == "text"
    assert any("Acme" in f or ".cs" in f for f in d["output"]["files"])
