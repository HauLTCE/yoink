from __future__ import annotations

from pathlib import Path

from yoink.gitignore import iter_files, load_ignore


def _ig(root: Path, text: str):
    (root / ".gitignore").write_text(text, encoding="utf-8")
    return load_ignore(root)


def test_star_and_dir(tmp_path: Path):
    ig = _ig(tmp_path, "*.log\nbuild/\n")
    assert ig(tmp_path / "a.log", False)
    assert ig(tmp_path / "build", True)
    assert not ig(tmp_path / "a.py", False)


def test_doublestar(tmp_path: Path):
    ig = _ig(tmp_path, "**/tmp/*.py\n")
    assert ig(tmp_path / "x" / "tmp" / "a.py", False)
    assert not ig(tmp_path / "x" / "a.py", False)


def test_question_mark(tmp_path: Path):
    ig = _ig(tmp_path, "file?.txt\n")
    assert ig(tmp_path / "file1.txt", False)
    assert not ig(tmp_path / "file12.txt", False)


def test_anchored(tmp_path: Path):
    ig = _ig(tmp_path, "/rooted.py\n")
    assert ig(tmp_path / "rooted.py", False)
    assert not ig(tmp_path / "sub" / "rooted.py", False)


def test_negation(tmp_path: Path):
    ig = _ig(tmp_path, "*.py\n!keep.py\n")
    assert ig(tmp_path / "a.py", False)
    assert not ig(tmp_path / "keep.py", False)


def test_nested_layering(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("*.py\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / ".gitignore").write_text("!ok.py\n", encoding="utf-8")
    ig = load_ignore(tmp_path)
    assert ig(tmp_path / "a.py", False)
    assert not ig(sub / "ok.py", False)
    assert ig(sub / "other.py", False)


def test_always_ignored(tmp_path: Path):
    ig = load_ignore(tmp_path)
    for d in (".git", "__pycache__", ".venv", "node_modules", "dist", "build"):
        assert ig(tmp_path / d, True), d
    assert ig(tmp_path / "x.egg-info", True)


def test_yoinkignore(tmp_path: Path):
    (tmp_path / ".yoinkignore").write_text("secret.py\n", encoding="utf-8")
    ig = load_ignore(tmp_path)
    assert ig(tmp_path / "secret.py", False)


def test_iter_files_prunes(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("skip/\n", encoding="utf-8")
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "x.py").write_text("x", encoding="utf-8")
    (tmp_path / "keep.py").write_text("k", encoding="utf-8")
    ig = load_ignore(tmp_path)
    got = {p.name for p in iter_files(tmp_path, ig)}
    assert "keep.py" in got and "x.py" not in got


def test_comments_and_escapes(tmp_path: Path):
    ig = _ig(tmp_path, "# comment\n\\!notneg.py\n")
    assert ig(tmp_path / "!notneg.py", False)
    assert not ig(tmp_path / "x.py", False)
