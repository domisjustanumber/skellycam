#!/usr/bin/env python3
"""Refuse a new script for a person to run on a system that is not the test machine (decision VV4Q).

Usage::

    python tools/check_other_systems.py [FILE ...]   # the given files
    python tools/check_other_systems.py              # the files that the commit adds (the pre-commit hook)
    python tools/check_other_systems.py --all        # each tracked file (the doc test and CI)

The Windows lab machine of the project is the only test machine. A test on another system runs only
through the self-test ``skellycam.certify(level)`` and its report. The tool refuses a script that
looks like a manual step for another system, one line for each file, and exits 1. It is the primary
mechanical check of the rule. It cannot see a proposal in chat; the rule and the skill
``verify-on-other-systems`` cover that.

- It checks only a script file (``SCRIPT_SUFFIXES``) outside ``EXEMPT_PATHS`` and outside a
  ``tests`` folder. The product code, its tests, the docs site and the CI workflows can name other
  systems. A CI runner with no cameras is allowed for what it can check.
- It refuses a script when a part of its path is a name in ``OTHER_SYSTEM_NAMES``, or when a Python
  script compares ``sys.platform`` to a value that is not in ``LAB_PLATFORMS``. A guard that stops
  a lab script on other systems compares to a lab value, so it passes. Set ``LAB_PLATFORMS`` for
  the repo.
- It passes the script when one of its first ``MARKER_LINES`` lines has ``certify-check: <name>``
  (the certify check that the script serves) or ``other-systems: not applicable (<reason>)``.
- The default mode checks only the files that the commit adds. ``--all`` checks each tracked file.
  It misses a shell or Markdown instruction, a renamed file and a script with no script suffix.

Exit codes: 0 when no file is refused, 1 when a file is refused, 2 for a usage error. Standard
library only.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

LAB_PLATFORMS: tuple[str, ...] = ("win32",)
EXEMPT_PATHS: tuple[str, ...] = ("skellycam/", "skellycam-ui/", "skellycam-docs/", ".github/")
SCRIPT_SUFFIXES = frozenset(".py .sh .bash .zsh .command .ps1".split())
OTHER_SYSTEM_NAMES = frozenset({"mac", "macos", "linux"})
MARKER_LINES = 5
MARKER = re.compile(r"certify-check:\s*\S|other-systems:\s*not applicable\s*\(\s*[^)\s][^)]*\)")
GUARD = re.compile(r"""sys\.platform\s*(==|!=|\.startswith\()\s*["']([^"']*)["']""")


def git(root: Path, *args: str) -> list[str]:
    exe = shutil.which("git")
    if exe is None:
        raise SystemExit("git is not on the PATH")
    out = subprocess.run([exe, "-C", str(root), *args], capture_output=True, check=True)  # noqa: S603
    return [n for n in out.stdout.decode("utf-8").split("\0") if n]


def added_files(root: Path) -> list[str]:
    return git(root, "diff", "--cached", "--name-only", "--diff-filter=A", "-z")


def tracked_files(root: Path) -> list[str]:
    return git(root, "ls-files", "-z")


def reason_of(rel: str, root: Path, lab: tuple[str, ...] = LAB_PLATFORMS) -> str | None:
    """Why the script looks like a manual step for another system, or None."""
    path = PurePosixPath(rel)
    if path.suffix.lower() not in SCRIPT_SUFFIXES or rel.startswith(EXEMPT_PATHS) or "tests" in path.parts[:-1]:
        return None
    file = root / rel
    if not file.is_file():
        return None
    # shortcut: reads the working-tree file, not the staged blob, as check_camera_media.py does.
    text = file.read_text(encoding="utf-8", errors="replace")
    if any(MARKER.search(line) for line in text.splitlines()[:MARKER_LINES]):
        return None
    names = OTHER_SYSTEM_NAMES & set(re.split(r"[^a-z0-9]+", rel.lower()))
    if names:
        return f"its path names another system ({', '.join(sorted(names))})"
    if path.suffix.lower() == ".py":
        for op, value in GUARD.findall(text):
            if not value.startswith(lab):
                return f"it has a guard for another system (sys.platform {op.rstrip('(')} {value!r})"
    return None


def check(paths: list[str], root: Path, lab: tuple[str, ...] = LAB_PLATFORMS) -> list[str]:
    """The refusal lines for the given repo-relative paths."""
    refused = []
    for rel in sorted({PurePosixPath(p.replace("\\", "/")).as_posix() for p in paths}):
        reason = reason_of(rel, root, lab)
        if reason:
            refused.append(
                f"{rel}: {reason}: test other systems only through skellycam.certify (see AGENTS.md, Project"
                " Rules); add a certify check, or put 'certify-check: <name>' or 'other-systems: not"
                f" applicable (<reason>)' in the first {MARKER_LINES} lines"
            )
    return refused


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refuse a manual script for another system.")
    parser.add_argument("files", nargs="*", help="repo-relative files; default: the files that the commit adds")
    parser.add_argument("--all", action="store_true", help="check each tracked file")
    args = parser.parse_args(argv[1:])
    if args.all and args.files:
        parser.error("give --all or files, not both")
    root = Path.cwd()
    paths = tracked_files(root) if args.all else args.files or added_files(root)
    refused = check(paths, root)
    if refused:
        print("\n".join(refused))
        return 1
    print(f"other systems: no findings ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
