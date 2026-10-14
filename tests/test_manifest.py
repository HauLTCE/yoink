from __future__ import annotations

import json

from yoink.manifest import Manifest


def test_schema_keys(tmp_path):
    m = Manifest()
    m.source = {"kind": "local", "repo": "r", "ref": None, "commit": None, "license": "MIT", "language": "python", "target": "x"}
    d = m.to_dict()
    for k in ("yoink_version", "schema_version", "source", "resolution", "mode", "output", "modules", "stdlib", "external_deps", "unresolved", "untranslated", "verified", "warnings", "created"):
        assert k in d
    for k in ("kind", "repo", "ref", "commit", "license", "language", "target"):
        assert k in d["source"]
    for k in ("status", "command", "passed", "detail"):
        assert k in d["verified"]


def test_write_roundtrip(tmp_path):
    m = Manifest()
    p = tmp_path / "yoink.manifest.json"
    m.write(p)
    loaded = json.loads(p.read_text())
    assert loaded["schema_version"] == 1
