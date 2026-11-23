"""The wheel build writes `skellycam/build_info.json` from git (specs/certify.md 3.5.2, 3.5.15 P7)."""

import json
import subprocess

import build_info
import pytest

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def answers(porcelain):
    def git(args, **options):
        out = COMMIT + "\n" if "rev-parse" in args else porcelain
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
    return git


@pytest.mark.parametrize("porcelain, modified", [("", False), (" M skellycam/app.py\n", True)])
def test_the_build_file_holds_the_commit_and_the_tree_state(tmp_path, porcelain, modified):
    path = build_info.write(tmp_path / "lib", tmp_path, run=answers(porcelain))
    assert path == tmp_path / "lib" / "skellycam" / "build_info.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"commit": COMMIT, "tree_modified": modified}


def test_no_git_answer_writes_no_file(tmp_path):
    def no_git(args, **options):
        raise FileNotFoundError("git")
    assert build_info.write(tmp_path / "lib", tmp_path, run=no_git) is None
    assert not (tmp_path / "lib").exists()

    def not_a_commit(args, **options):
        return subprocess.CompletedProcess(args, 0, stdout="HEAD\n", stderr="")
    assert build_info.write(tmp_path / "lib", tmp_path, run=not_a_commit) is None


def test_the_build_command_is_the_build_py_of_setuptools():
    setuptools = pytest.importorskip("setuptools.command.build_py")
    assert issubclass(build_info.BuildPy, setuptools.build_py)
