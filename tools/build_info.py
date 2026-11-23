"""The build file of skellycam (specs/certify.md 3.5.2, 3.5.15 P7) [ADR-0Z6Q items 6 and 16, ADR-056Z Q647].

Each build carries `skellycam/build_info.json`, `{"commit": "<40 hex>", "tree_modified": <bool>}`. The value comes
from git at build time: `tree_modified` is `true` when `git status --porcelain` is not empty. A commit comes only
from the git work tree whose top is the source root; a source tree inside another repository gives none. A run of
skellycam reads the file and never runs git.

- `BuildPy` (the `build_py` command of setuptools) writes the file into the build folder of a wheel. With no git
  answer, it copies a valid file of the source tree: the file of an sdist. An editable install writes no file.
- `Sdist` (the `sdist` command) writes the file into the tree of the sdist. It reads git before setuptools makes
  the release tree inside the source root, so that new folder does not count as a change.
- `python tools/build_info.py --require` writes the file into the source tree, for the installer build of CI. It
  ends with exit code 1 when git gives no commit.

An error of git, also a text that does not decode, gives "no commit known". The build never fails for the file.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

FILE = Path("skellycam") / "build_info.json"
ROOT = Path(__file__).resolve().parents[1]
COMMIT = re.compile(r"[0-9a-f]{40}")


def _git(run, root, *args) -> str:
    return run(["git", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace", check=True,
               timeout=60).stdout


def build_info(root, run=subprocess.run) -> dict | None:
    """The commit and the tree state of the git work tree whose top is `root`, or None."""
    try:
        top = _git(run, root, "rev-parse", "--show-toplevel").strip()
        if not top or Path(top).resolve() != Path(root).resolve():
            return None
        commit = _git(run, root, "rev-parse", "HEAD").strip()
        status = _git(run, root, "status", "--porcelain")
        if not COMMIT.fullmatch(commit):
            return None
        return {"commit": commit, "tree_modified": bool(status.strip())}
    except Exception:
        return None


def read(path) -> dict | None:
    """A valid build file, or None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if (isinstance(data, dict) and set(data) == {"commit", "tree_modified"} and isinstance(data["commit"], str)
            and COMMIT.fullmatch(data["commit"]) and isinstance(data["tree_modified"], bool)):
        return data
    return None


def write(target, root, run=subprocess.run, info=None) -> Path | None:
    """Write the build file into `target`: `info`, else from git in `root`, else from a valid file of `root`.
    Returns its path, or None with no value. It never raises."""
    try:
        info = info or build_info(root, run) or read(Path(root) / FILE)
        if info is None:
            return None
        path = Path(target) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(info), encoding="utf-8")
        return path
    except Exception:
        return None


try:
    from setuptools.command.build_py import build_py as _build_py
    from setuptools.command.sdist import sdist as _sdist
except ImportError:  # the doc checks run without setuptools
    _build_py = _sdist = object


class BuildPy(_build_py):
    def run(self):
        super().run()
        if not getattr(self, "editable_mode", False):
            write(self.build_lib, ROOT)


class Sdist(_sdist):
    def make_release_tree(self, base_dir, files):
        # the release tree is inside the source root: read the tree state before setuptools makes it
        info = build_info(ROOT)
        super().make_release_tree(base_dir, files)
        write(base_dir, ROOT, info=info)


def main(argv=None) -> int:
    """`--require`: the installer build of CI; no commit is an error."""
    args = sys.argv[1:] if argv is None else argv
    info = build_info(ROOT)
    if info is None:
        print("build_info: git gives no commit for the source root", file=sys.stderr)
        return 1 if "--require" in args else 0
    path = write(ROOT, ROOT)
    print(f"build_info: {FILE.as_posix()} with commit {info['commit']}, tree_modified {info['tree_modified']}")
    return 0 if path is not None else 1


if __name__ == "__main__":
    sys.exit(main())
