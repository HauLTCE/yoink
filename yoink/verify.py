"""Sandboxed command execution and safety checking for post-extraction verification."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from yoink.errors import SafetyError
from yoink.model import VerifyResult

DANGEROUS: tuple[str, ...] = (
    "rm -rf /",
    "mkfs",
    "dd of=/dev",
    ":(){",
    "> /dev/sd",
    "format c:",
    "chmod -r 777 /",
    "chown -r",
)
_TAIL = 2000


def _denylisted(cmd: str) -> str | None:
    low = cmd.lower().strip()
    for pat in DANGEROUS:
        if pat in low:
            return pat
    return None


def prepare_sandbox(out_dir: Path) -> Path:
    """Create a temporary directory copy of `out_dir` for isolated verification."""
    tmp = Path(tempfile.mkdtemp(prefix="yoink-verify-"))
    dest = tmp / "work"
    shutil.copytree(out_dir, dest, symlinks=False)
    return dest


def run_verification(
    workdir: Path,
    command: str,
    policy: str = "ask",
    assume_yes: bool = False,
    timeout: int = 120,
) -> VerifyResult:
    """Execute verification command inside a temporary sandbox directory."""
    if not command or not command.strip():
        return VerifyResult(status="not_run")

    bad = _denylisted(command)
    if bad is not None:
        raise SafetyError(f"verification command blocked by safety denylist ({bad!r})")

    if policy == "never":
        return VerifyResult(
            status="skipped",
            command=command,
            detail="execution disabled by safety.execute='never'",
        )

    sandbox = prepare_sandbox(Path(workdir))
    try:
        args = shlex.split(command)
        proc = subprocess.run(
            args,
            cwd=sandbox,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
        )
        combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        tail = combined[-_TAIL:] if len(combined) > _TAIL else combined
        status = "passed" if proc.returncode == 0 else "failed"
        return VerifyResult(
            status=status,
            command=command,
            detail=tail,
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(
            status="failed",
            command=command,
            detail=f"command timed out after {timeout}s",
            exit_code=-1,
        )
    except OSError as e:
        return VerifyResult(
            status="failed",
            command=command,
            detail=str(e),
            exit_code=-1,
        )
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)
