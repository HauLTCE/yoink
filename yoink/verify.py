"""Sandboxed --test execution with a denylist and a safety policy."""

from __future__ import annotations

import shutil
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from yoink.errors import SafetyError, VerifyError
from yoink.model import VerifyResult

DANGEROUS: tuple[str, ...] = (
    "rm -rf /",
    "mkfs",
    "dd of=/dev",
    ":(){",
    "> /dev/sd",
    "format c:",
)

_TAIL = 2000


def prepare_sandbox(out_dir: Path) -> Path:
    """Copy out_dir contents into a fresh temp dir; return it."""
    box = Path(tempfile.mkdtemp(prefix="yoink-verify-"))
    for child in Path(out_dir).iterdir():
        dest = box / child.name
        if child.is_dir():
            shutil.copytree(child, dest)
        else:
            shutil.copy2(child, dest)
    return box


def _denylisted(command: str) -> str | None:
    low = command.lower()
    for bad in DANGEROUS:
        if bad in low:
            return bad
    return None


def run_verify(
    command: str,
    workdir: Path,
    policy: str = "ask",
    assume_yes: bool = False,
    timeout: int = 300,
) -> VerifyResult:
    """Maybe run `command` in workdir, subject to policy + denylist."""
    if policy == "never":
        return VerifyResult(
            status="skipped", command=command, detail="safety.execute=never", exit_code=None
        )

    hit = _denylisted(command)
    if hit is not None:
        raise SafetyError(f"refusing to run denylisted command (matched {hit!r})")

    if policy == "ask":
        if not assume_yes:
            if not sys.stdin.isatty():
                return VerifyResult(
                    status="skipped",
                    command=command,
                    detail="refused: no tty",
                    exit_code=None,
                )
            try:
                ans = input(f"Run test command '{command}' in {workdir}? [y/N] ")
            except EOFError:
                ans = ""
            if ans.strip().lower() not in ("y", "yes"):
                return VerifyResult(
                    status="skipped",
                    command=command,
                    detail="refused by user",
                    exit_code=None,
                )
    elif policy not in ("always",):
        raise VerifyError(f"unknown safety.execute policy: {policy!r}")

    try:
        argv = shlex.split(command)
    except ValueError as e:
        raise VerifyError(f"cannot parse test command {command!r}: {e}") from e
    if not argv:
        raise VerifyError("empty test command")

    try:
        proc = subprocess.run(
            argv,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as e:
        raise VerifyError(f"command not found: {argv[0]}") from e
    except subprocess.TimeoutExpired:
        return VerifyResult(
            status="failed",
            command=command,
            detail=f"timeout after {timeout}s",
            exit_code=None,
        )

    if proc.returncode == 0:
        return VerifyResult(
            status="passed", command=command, detail="", exit_code=0
        )
    blob = ((proc.stderr or "") + (proc.stdout or "")).strip()
    return VerifyResult(
        status="failed",
        command=command,
        detail=blob[-_TAIL:] or f"exit code {proc.returncode}",
        exit_code=proc.returncode,
    )


__all__ = ["DANGEROUS", "run_verify", "prepare_sandbox"]
