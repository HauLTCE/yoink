from __future__ import annotations

import sys

import pytest

from yoink.errors import SafetyError
from yoink.verify import prepare_sandbox, run_verify

PY = sys.executable


def test_policy_never(tmp_path):
    r = run_verify(f'"{PY}" -c "print(1)"', tmp_path, policy="never")
    assert r.status == "skipped"


def test_denylist(tmp_path):
    with pytest.raises(SafetyError):
        run_verify("rm -rf / whatever", tmp_path, policy="always")


def test_passing(tmp_path):
    r = run_verify(f'"{PY}" -c "exit(0)"', tmp_path, policy="always")
    assert r.status == "passed" and r.exit_code == 0


def test_failing(tmp_path):
    r = run_verify(f'"{PY}" -c "import sys;sys.exit(3)"', tmp_path, policy="always")
    assert r.status == "failed" and r.exit_code == 3


def test_timeout(tmp_path):
    r = run_verify(f'"{PY}" -c "import time;time.sleep(10)"', tmp_path, policy="always", timeout=1)
    assert r.status == "failed" and "timeout" in r.detail.lower()


def test_ask_no_tty(tmp_path, monkeypatch):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    r = run_verify(f'"{PY}" -c "pass"', tmp_path, policy="ask")
    assert r.status == "skipped"


def test_ask_yes(tmp_path):
    r = run_verify(f'"{PY}" -c "pass"', tmp_path, policy="ask", assume_yes=True)
    assert r.status == "passed"


def test_sandbox(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")
    box = prepare_sandbox(src)
    assert (box / "f.txt").exists()
