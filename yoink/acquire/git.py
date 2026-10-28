"""Git source parsing and cached clones with hardened argument validation."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from yoink.errors import AcquireError, SafetyError
from yoink.model import Source

from .cache import cache_root

_GH_SHORT = re.compile(r"^gh:(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:@(?P<ref>[A-Za-z0-9_./-]+))?$")
_GH_HTTPS = re.compile(
    r"^https://github\.com/(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"(?:\.git)?(?:@(?P<ref>[A-Za-z0-9_./-]+))?$"
)
_GH_SSH = re.compile(
    r"^git@github\.com:(?P<slug>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"(?:\.git)?(?:@(?P<ref>[A-Za-z0-9_./-]+))?$"
)
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,127}$")
_ALLOWED_SCHEMES = {"https", "http", "ssh", "git"}


def is_local_spec(spec: str) -> bool:
    """True when the spec is (or smells like) a local path."""
    if not spec:
        return True
    s = spec.strip()
    if s.startswith(("gh:", "http://", "https://", "git@", "ssh://", "git://")):
        return False
    if Path(s).expanduser().exists():
        return True
    if s.startswith(("/", "./", "../", "~")) or s.endswith("/"):
        return True
    return bool(_DRIVE.match(s)) or s.startswith("\\\\")


def _validate_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    if ref.startswith("-") or ".." in ref or not _SAFE_REF.match(ref):
        raise SafetyError(f"unsafe git ref rejected: {ref!r}")
    return ref


def _validate_url(url: str) -> str:
    if url.startswith("-"):
        raise SafetyError(f"unsafe git URL rejected: {url!r}")
    if url.startswith("git@"):
        return url
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.netloc:
        raise SafetyError(f"unsupported or unsafe git URL scheme: {url!r}")
    return url


def parse_source(spec: str) -> Source:
    """Parse a source spec into a Source (kind local|gh|url)."""
    spec_s = spec.strip()
    m = _GH_SHORT.match(spec_s)
    if m:
        ref = _validate_ref(m.group("ref"))
        display = f"gh:{m.group('slug')}"
        if ref:
            display += f"@{ref}"
        return Source(kind="gh", display=display, ref=ref)

    for rx in (_GH_HTTPS, _GH_SSH):
        m = rx.match(spec_s)
        if m:
            ref = _validate_ref(m.group("ref"))
            return Source(kind="url", display=spec_s, ref=ref)

    if is_local_spec(spec_s):
        return Source(kind="local", display=spec_s, ref=None)

    # Check if URL has @ref suffix
    ref = None
    base = spec_s
    if "@" in spec_s and not spec_s.startswith("git@"):
        base, ref_part = spec_s.rsplit("@", 1)
        ref = _validate_ref(ref_part)
    _validate_url(base)
    return Source(kind="url", display=spec_s, ref=ref)


def clone_url(src: Source) -> str:
    """Clone URL for a parsed source."""
    if src.kind == "gh":
        slug = src.display[3:].split("@")[0]
        return _validate_url(f"https://github.com/{slug}.git")
    disp = src.display
    if disp.startswith("git@github.com:"):
        slug = disp.split(":", 1)[1].split("@")[0].removesuffix(".git")
        return _validate_url(f"https://github.com/{slug}.git")
    return _validate_url(disp.split("@")[0])


def _sha_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("git")
    if exe is None:
        raise AcquireError("git executable not found on PATH")
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
    return not re.fullmatch(r"[0-9a-fA-F]{7,40}", ref)


def acquire_git(src: Source, url: str, cache_dir: Path | None = None) -> tuple[Path, str]:
    """Clone `url` (at src.ref if given) into the cache; return (dest, commit)."""
    url = _validate_url(url)
    ref = _validate_ref(src.ref)

    root = cache_root(cache_dir)
    repos = root / "repos"
    repos.mkdir(parents=True, exist_ok=True)

    key = _sha_short(f"{url}@{ref or 'default'}")
    dest = repos / key

    if dest.exists() and (dest / ".git").exists():
        return dest, _rev_parse_head(dest)

    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)

    cloned = False
    if ref and _looks_like_ref_name(ref):
        proc = _git(["clone", "--depth", "1", "--branch", ref, "--", url, str(dest)])
        cloned = proc.returncode == 0
        if not cloned and dest.exists():
            shutil.rmtree(dest, ignore_errors=True)

    if not cloned:
        cmd = ["clone", "--", url, str(dest)] if ref else ["clone", "--depth", "1", "--", url, str(dest)]
        proc = _git(cmd)
        if proc.returncode != 0:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            raise AcquireError(f"git clone failed for {url}: {tail}")
        if ref:
            co = _git(["-C", str(dest), "checkout", ref, "--"])
            if co.returncode != 0:
                shutil.rmtree(dest, ignore_errors=True)
                tail = (co.stderr or "").strip()[-500:]
                raise AcquireError(f"git checkout {ref} failed for {url}: {tail}")

    return dest, _rev_parse_head(dest)


__all__ = ["parse_source", "is_local_spec", "clone_url", "acquire_git"]
