"""Git source parsing and cached clones."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from yoink.errors import AcquireError
from yoink.model import Source

from .cache import cache_root

_GH_SHORT = re.compile(r"^gh:(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:@(?P<ref>.+))?$")
_GH_HTTPS = re.compile(
    r"^https?://github\.com/(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?(?:@(?P<ref>.+))?/?$"
)
_GH_SSH = re.compile(
    r"^git@github\.com:(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?(?:@(?P<ref>.+))?$"
)
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def is_local_spec(spec: str) -> bool:
    """True when the spec is (or smells like) a local path."""
    s = spec.strip()
    if not s:
        return False
    if Path(s).expanduser().exists():
        return True
    if s.startswith(("/", "./", "../", "~")) or s.endswith("/"):
        return True
    # windows drive letters and unc
    return bool(_DRIVE.match(s)) or s.startswith("\\\\")


def parse_source(spec: str) -> Source:
    """Parse a source spec into a Source (kind local|gh|url)."""
    m = _GH_SHORT.match(spec)
    if m:
        ref = m.group("ref")
        display = f"gh:{m.group('slug')}"
        if ref:
            display += f"@{ref}"
        return Source(kind="gh", display=display, ref=ref)

    for rx in (_GH_HTTPS, _GH_SSH):
        m = rx.match(spec)
        if m:
            ref = m.group("ref")
            display = spec
            return Source(kind="url", display=display, ref=ref)

    if is_local_spec(spec):
        return Source(kind="local", display=spec, ref=None)

    # whatever, try it as a url anyway
    return Source(kind="url", display=spec, ref=None)


def clone_url(src: Source) -> str:
    """Clone URL for a parsed source."""
    if src.kind == "gh":
        return f"https://github.com/{src.display[3:].split('@')[0]}"
    disp = src.display
    if disp.startswith("git@github.com:"):
        return "https://github.com/" + disp.split(":", 1)[1].removesuffix(".git")
    return disp.split("@")[0]


def _sha_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("git")
    if exe is None:
        raise AcquireError("git not found")
    return subprocess.run(
        [exe, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=False,
    )


def _rev_parse_head(dest: Path) -> str:
    try:
        proc = _git(["-C", str(dest), "rev-parse", "HEAD"])
    except AcquireError:
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def _looks_like_ref_name(ref: str) -> bool:
    # sha-ish refs can't be --branch'd
    return not re.fullmatch(r"[0-9a-fA-F]{7,40}", ref)


def acquire_git(src: Source, url: str, cache_dir: Path | None = None) -> tuple[Path, str]:
    """Clone `url` (at src.ref if given) into the cache; return (dest, commit)."""
    root = cache_root(cache_dir)
    repos = root / "repos"
    repos.mkdir(parents=True, exist_ok=True)

    key = _sha_short(f"{url}@{src.ref or 'default'}")
    dest = repos / key

    if dest.exists() and (dest / ".git").exists():
        return dest, _rev_parse_head(dest)

    if dest.exists():
        # half-written junk from a previous crash
        shutil.rmtree(dest, ignore_errors=True)

    ref = src.ref
    cloned = False
    if ref and _looks_like_ref_name(ref):
        proc = _git(["clone", "--depth", "1", "--branch", ref, url, str(dest)])
        cloned = proc.returncode == 0
        if not cloned and dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

    if not cloned:
        proc = _git(["clone", url, str(dest)] if ref else ["clone", "--depth", "1", url, str(dest)])
        if proc.returncode != 0:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            raise AcquireError(f"git clone failed for {url}: {tail}")
        if ref:
            co = _git(["-C", str(dest), "checkout", ref])
            if co.returncode != 0:
                shutil.rmtree(dest, ignore_errors=True)
                tail = (co.stderr or "").strip()[-500:]
                raise AcquireError(f"git checkout {ref} failed for {url}: {tail}")

    return dest, _rev_parse_head(dest)


__all__ = ["parse_source", "is_local_spec", "clone_url", "acquire_git"]
