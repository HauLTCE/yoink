from __future__ import annotations

import json


def test_doctor_exit0(run_cli, fixture):
    r = run_cli(str(fixture("reexport_chain")), "--grab", "leaf", "--doctor")
    assert r.exit_code == 0, r.output


def test_doctor_json(run_cli, fixture):
    r = run_cli(str(fixture("reexport_chain")), "--grab", "leaf", "--doctor", "--json")
    assert r.exit_code == 0
    json.loads(r.output)


def test_ambiguous_exit1(run_cli, fixture):
    r = run_cli(str(fixture("ambiguous")), "--grab", "run", "--doctor")
    assert r.exit_code == 1


def test_strict_exit2(run_cli, fixture, tmp_path):
    r = run_cli(str(fixture("dyn")), "--grab", "main", "-o", str(tmp_path / "o"), "--strict")
    assert r.exit_code == 2


def test_bundle_writes(run_cli, fixture, tmp_path):
    r = run_cli(str(fixture("reexport_chain")), "--grab", "leaf", "-o", str(tmp_path / "o"))
    assert r.exit_code == 0
    assert (tmp_path / "o" / "yoink.manifest.json").exists()


def test_flat(run_cli, fixture, tmp_path):
    r = run_cli(str(fixture("side_effects")), "--grab", "run", "--flat", "-o", str(tmp_path / "o"))
    assert r.exit_code == 0


def test_version(run_cli):
    r = run_cli("--version")
    assert r.exit_code == 0


def test_mode_conflict(run_cli, fixture, tmp_path):
    r = run_cli(str(fixture("dyn")), "--grab", "main", "--flat", "--doctor", "-o", str(tmp_path / "o"))
    assert r.exit_code == 1


def test_missing_source(run_cli):
    r = run_cli("--grab", "x")
    assert r.exit_code != 0


def test_cache_commands():
    from typer.testing import CliRunner
    from yoink.cli import cache_app

    runner = CliRunner()
    assert runner.invoke(cache_app, ["dir"]).exit_code == 0
    assert runner.invoke(cache_app, ["list"]).exit_code == 0
    assert runner.invoke(cache_app, ["clear"]).exit_code == 0
