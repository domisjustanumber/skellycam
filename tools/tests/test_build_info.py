"""The build file of the certify report (specs/certify.md 3.5.2, 3.5.15 P7, T-CERT-134; ADR-0Z6Q items 6 and 16)."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

import build_info
import pytest

COMMIT = "0123456789abcdef0123456789abcdef01234567"
REPO = Path(build_info.__file__).resolve().parents[1]


def answers(porcelain, top):
    def git(args, **options):
        out = str(top) + "\n" if "--show-toplevel" in args else COMMIT + "\n" if "HEAD" in args else porcelain
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
    return git


def no_git(args, **options):
    raise FileNotFoundError("git")


def real_git(folder, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t")
    return subprocess.run(["git", *args], cwd=folder, env=env, check=True, capture_output=True)


def repository(folder):
    folder.mkdir(parents=True, exist_ok=True)
    real_git(folder, "init", "-q")
    (folder / "a.txt").write_text("a", encoding="utf-8")
    real_git(folder, "add", "a.txt")
    real_git(folder, "commit", "-q", "-m", "a")
    return real_git(folder, "rev-parse", "HEAD").stdout.decode().strip()


@pytest.mark.parametrize("porcelain, modified", [("", False), (" M skellycam/app.py\n", True)])
def test_the_build_file_holds_the_commit_and_the_tree_state(tmp_path, porcelain, modified):
    path = build_info.write(tmp_path / "lib", tmp_path, run=answers(porcelain, tmp_path))
    assert path == tmp_path / "lib" / "skellycam" / "build_info.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"commit": COMMIT, "tree_modified": modified}


def test_no_git_answer_writes_no_file(tmp_path):
    assert build_info.write(tmp_path / "lib", tmp_path, run=no_git) is None
    assert not (tmp_path / "lib").exists()

    def not_a_commit(args, **options):
        out = str(tmp_path) if "--show-toplevel" in args else "HEAD\n"
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")
    assert build_info.write(tmp_path / "lib", tmp_path, run=not_a_commit) is None


def test_a_name_that_does_not_decode_never_fails_the_build(tmp_path):
    """M3 of the review: an untracked file with a name that is not ASCII, with `core.quotepath` false."""
    commit = repository(tmp_path / "repo")
    real_git(tmp_path / "repo", "config", "core.quotepath", "false")
    (tmp_path / "repo" / "LŁodz.txt").write_text("x", encoding="utf-8")
    assert build_info.build_info(tmp_path / "repo") == {"commit": commit, "tree_modified": True}

    def broken(args, **options):
        return subprocess.CompletedProcess(args, 0, stdout=None, stderr="")
    assert build_info.build_info(tmp_path, run=broken) is None


def test_a_source_tree_inside_another_repository_gives_no_commit(tmp_path):
    """M4 of the review: `git rev-parse` walks up to a parent repository; only the top of the work tree counts."""
    repository(tmp_path / "outer")
    inner = tmp_path / "outer" / "vendored" / "skellycam-2.0.0"
    inner.mkdir(parents=True)
    assert build_info.build_info(inner) is None
    assert build_info.write(tmp_path / "lib", inner) is None


def test_a_wheel_from_an_sdist_copies_the_file_of_the_sdist(tmp_path):
    """Q647: the sdist carries the file; with no git answer the wheel copies it; a damaged file is not copied."""
    source = tmp_path / "sdist"
    (source / "skellycam").mkdir(parents=True)
    (source / "skellycam" / "build_info.json").write_text(json.dumps({"commit": COMMIT, "tree_modified": False}),
                                                          encoding="utf-8")
    path = build_info.write(tmp_path / "lib", source, run=no_git)
    assert json.loads(path.read_text(encoding="utf-8")) == {"commit": COMMIT, "tree_modified": False}
    (source / "skellycam" / "build_info.json").write_text('{"commit": "x", "tree_modified": false}', encoding="utf-8")
    assert build_info.write(tmp_path / "other", source, run=no_git) is None


def test_a_write_that_fails_gives_no_file_and_no_error(tmp_path):
    blocked = tmp_path / "lib"
    blocked.write_text("a file where the folder must be", encoding="utf-8")
    assert build_info.write(blocked, tmp_path, run=answers("", tmp_path)) is None


def test_the_build_commands_call_write(monkeypatch, tmp_path):
    """`BuildPy.run` writes into the build folder, and not for an editable install; `Sdist` writes into the sdist."""
    pytest.importorskip("setuptools")
    from setuptools.dist import Distribution
    calls = []
    monkeypatch.setattr(build_info, "write", lambda target, root, run=None: calls.append((Path(target), root)))
    monkeypatch.setattr(build_info._build_py, "run", lambda self: None)
    monkeypatch.setattr(build_info._sdist, "make_release_tree", lambda self, base_dir, files: None)
    command = build_info.BuildPy(Distribution())
    command.build_lib = str(tmp_path / "lib")
    command.run()
    assert calls == [(tmp_path / "lib", build_info.ROOT)]
    command.editable_mode = True
    command.run()
    assert len(calls) == 1
    build_info.Sdist(Distribution()).make_release_tree(str(tmp_path / "sdist"), [])
    assert calls[-1] == (tmp_path / "sdist", build_info.ROOT)


def test_the_commands_are_wired_in_pyproject():
    commands = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["cmdclass"]
    assert commands == {"build_py": "tools.build_info.BuildPy", "sdist": "tools.build_info.Sdist"}
    assert build_info.BuildPy.__name__ == "BuildPy" and build_info.Sdist.__name__ == "Sdist"


def test_the_installer_build_carries_the_file():
    """Q647: the CI step writes the file before a step changes the tree, and `skellycam.spec` puts it in `datas`."""
    spec = (REPO / "skellycam.spec").read_text(encoding="utf-8")
    assert "datas.append((build_file, 'skellycam'))" in spec
    workflow = (REPO / ".github" / "workflows" / "build-installers-pyinstaller.yml").read_text(encoding="utf-8")
    step = workflow.index("python tools/build_info.py --require")
    assert step < workflow.index("- name: Write build info") < workflow.index("pyinstaller ./skellycam.spec")
    ignored = subprocess.run(["git", "check-ignore", "-q", "skellycam/build_info.json"], cwd=REPO)
    assert ignored.returncode == 0, "the build file must be ignored, or it makes the tree modified"


def test_require_ends_with_an_error_when_git_gives_no_commit(monkeypatch):
    monkeypatch.setattr(build_info, "build_info", lambda root, run=None: None)
    assert build_info.main(["--require"]) == 1
    assert build_info.main([]) == 0
