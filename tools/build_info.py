"""The build file of skellycam (specs/certify.md 3.5.2, 3.5.15 P7) [ADR-0Z6Q].

The wheel build writes `skellycam/build_info.json`, `{"commit": "<40 hex>", "tree_modified": <bool>}`, from git at
build time. `tree_modified` is `true` when `git status --porcelain` is not empty. The file goes into the build
folder of the wheel, never into the source tree. With no git answer the build writes no file, and certify then
writes `null` for both values. A run of skellycam reads the file and never runs git.

`BuildPy` is the `build_py` command of setuptools (`[tool.setuptools.cmdclass]` of `pyproject.toml`). An editable
install writes no file.
"""

import json
import re
import subprocess
from pathlib import Path

FILE = Path("skellycam") / "build_info.json"
ROOT = Path(__file__).resolve().parents[1]


def build_info(root, run=subprocess.run) -> dict | None:
    """The commit and the tree state of the git work tree `root`, or None when git does not answer."""
    try:
        commit = run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True,
                     timeout=60).stdout.strip()
        status = run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True,
                     timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        return None
    return {"commit": commit, "tree_modified": bool(status.strip())}


def write(build_lib, root, run=subprocess.run) -> Path | None:
    """Write the build file into `build_lib`; return its path, or None when git does not answer."""
    info = build_info(root, run)
    if info is None:
        return None
    path = Path(build_lib) / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info), encoding="utf-8")
    return path


try:
    from setuptools.command.build_py import build_py as _build_py
except ImportError:  # the doc checks run without setuptools
    _build_py = object


class BuildPy(_build_py):
    def run(self):
        super().run()
        if not getattr(self, "editable_mode", False):
            write(self.build_lib, ROOT)
