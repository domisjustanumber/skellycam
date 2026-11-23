"""Each text file of the index has LF line ends (decision 0001)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import check_line_ends as cle
import pytest

REPO_ROOT = Path(cle.__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on the PATH")


def git(root: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(root.parent))
    subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=Tester", "-c", "user.email=tester@example.invalid", *args],  # noqa: S607
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def test_the_index_of_this_repository_has_only_lf_line_ends() -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    assert cle.crlf_files(REPO_ROOT) == []


def test_crlf_and_mixed_files_are_reported_and_binary_files_are_not(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "lf.md").write_bytes(b"a\nb\n")
    (tmp_path / "crlf.md").write_bytes(b"a\r\nb\r\n")
    (tmp_path / "mixed.md").write_bytes(b"a\r\nb\n")
    (tmp_path / "blob.bin").write_bytes(b"\0\r\n\0")
    (tmp_path / ".gitattributes").write_bytes(b"golden/** -text\n")
    (tmp_path / "golden").mkdir()
    (tmp_path / "golden" / "frame.txt").write_bytes(b"a\r\nb\r\n")
    git(tmp_path, "add", "-A")
    assert cle.crlf_files(tmp_path) == ["crlf.md", "mixed.md"]
    assert cle.main(["check_line_ends.py", str(tmp_path)]) == 1


def test_refresh_writes_the_crlf_files_of_a_clean_worktree_again_and_refuses_a_change(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.autocrlf", "true")
    (tmp_path / "a b.md").write_bytes(b"x\r\ny\r\n")
    (tmp_path / "golden").mkdir()
    (tmp_path / "golden" / "frame.txt").write_bytes(b"g\r\n")
    (tmp_path / ".gitattributes").write_bytes(b"golden/** -text\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "before the rule")
    (tmp_path / ".gitattributes").write_bytes(b"* text=auto eol=lf\ngolden/** -text\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "the rule")
    (tmp_path / "a b.md").write_bytes(b"x\r\ny\r\nlocal\r\n")
    with pytest.raises(SystemExit, match="commit or stash"):
        cle.refresh(tmp_path)
    git(tmp_path, "checkout", "--", "a b.md")
    (tmp_path / "a b.md").write_bytes(b"x\r\ny\r\n")
    assert cle.refresh(tmp_path) == ["a b.md"]
    assert (tmp_path / "a b.md").read_bytes() == b"x\ny\n"
    assert (tmp_path / "golden" / "frame.txt").read_bytes() == b"g\r\n"


def test_the_gitattributes_rule_writes_lf_into_the_index(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.autocrlf", "true")
    (tmp_path / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8")
    (tmp_path / "crlf.md").write_bytes(b"a\r\nb\r\n")
    git(tmp_path, "add", "-A")
    assert cle.crlf_files(tmp_path) == []
