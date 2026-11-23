#!/usr/bin/env python3
"""Refuse a new script for a person to run on another system (decisions VV4Q and K3BX).

Usage::

    python tools/check_other_systems.py [FILE ...]   # the given files
    python tools/check_other_systems.py              # the files that the commit adds (the pre-commit hook)
    python tools/check_other_systems.py --all        # each tracked file (the doc test and CI)

You can test only on the system that you work on. You can reach each other system only through the
self-test ``skellycam.certify(level)`` and its report. The tool refuses a script that looks like a
manual step for another system, one line for each file. It is the primary mechanical
check of the rule. It cannot see a proposal in chat; the rule and the skill
``verify-on-other-systems`` cover that. It checks the whole repository, also when you run it from
a subfolder.

- It checks only a script file (``SCRIPT_SUFFIXES``) outside ``EXEMPT_PATHS`` and outside a
  ``tests`` folder. The product code, its tests, the docs site and the CI workflows can name other
  systems. A CI runner with no camera can run the checks that need no device.
- It refuses a script when a part of its path is a name in ``OTHER_SYSTEM_NAMES``. It also refuses
  a Python script that compares ``sys.platform`` with ``==``, ``!=`` or ``in`` to a value that is
  not in ``LAB_PLATFORMS``, that calls ``sys.platform.startswith`` with a value that no lab platform
  starts with, or that compares ``platform.system()`` to a value that is not in ``LAB_SYSTEMS``.
  A guard that stops a lab script on other systems names a lab value, so it passes. Set
  ``LAB_PLATFORMS`` and ``LAB_SYSTEMS`` for the repo.
- It passes the script when one of its first ``MARKER_LINES`` lines is a comment (``#`` or ``//``)
  with ``other-systems: not applicable (<reason>)``, or with ``certify-check: <name>`` (the certify
  check that the script serves) when ``<name>`` is a check name of ``CERTIFY_SPEC`` (decision
  K3BX). A check name is the whole text of a code span of the spec that matches ``CHECK_NAME``:
  ``detect``, or two or more parts joined by ``:``. The first part is a ``<word>`` placeholder, or
  a lower-case letter and then lower-case letters, digits and ``-``. Each other part starts with a
  letter, a digit or a placeholder. So a name matches in the form that the spec writes, for example
  ``<label>:usb3-trial``, and a filled-in name does not. A name that is not in the spec, or a
  missing spec, refuses the script in each mode: the check must be in the spec first
  (``ADD_CHECK_FIRST``).
- The default mode checks the files that the commit adds, with rename detection off: a moved or a
  replaced file is a new file. ``--all`` checks each tracked file.
- It does not catch: an instruction in a shell script or in Markdown (it reads only the path of a
  shell script), a script with no script suffix, a script named for its probe and not for the
  system, a tuple in ``startswith``, a guard with the literal first, ``os.name`` and ``match``. It
  refuses a comment that quotes a guard.

Exit codes: 0 when no file is refused, 1 when a file is refused, 2 for a usage error, outside a git
repository, or with no git. Standard library only.
"""

from __future__ import annotations

import argparse
import codecs
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

LAB_PLATFORMS: tuple[str, ...] = ("win32",)
LAB_SYSTEMS: tuple[str, ...] = ("Windows",)
EXEMPT_PATHS: tuple[str, ...] = ("skellycam/", "skellycam-ui/", "skellycam-docs/", ".github/")
SCRIPT_SUFFIXES = frozenset(".py .sh .bash .zsh .command .ps1".split())
OTHER_SYSTEM_NAMES = frozenset({"mac", "macos", "osx", "darwin", "linux"})
MARKER_LINES = 5
NOT_APPLICABLE = re.compile(r"other-systems:\s*not applicable\s*\(\s*[^)\s][^)]*\)")
CERTIFY_MARKER = re.compile(r"certify-check:\s*(\S+)")
CERTIFY_SPEC = "specs/certify.md"
CODE_SPAN = re.compile(r"`([^`\n]+)`")
_PART = r"(?:[A-Za-z0-9]|<[a-z]+>)(?:[A-Za-z0-9_.@-]|<[a-z]+>)*"
CHECK_NAME = re.compile(rf"detect|(?:<[a-z]+>|[a-z][a-z0-9-]*)(?::{_PART})+")
GUARD = re.compile(
    r"(sys\.platform|platform\.system\(\))\s*"
    r"""(?:(==|!=|\.startswith\()\s*("[^"]*"|'[^']*')|((?:not\s+)?in)\s*([\(\[\{][^)\]\}]*))"""
)
LITERAL = re.compile(r"""["']([^"']*)["']""")
OTHER_SYSTEMS_ADVICE = (
    "test other systems only through skellycam.certify (see AGENTS.md, Project Rules); add a certify check,"
    " or put the comment 'certify-check: <name>' or 'other-systems: not applicable (<reason>)' in the first"
    f" {MARKER_LINES} lines"
)
# The pointer to the process of skellycertify for a new check. Change it here only.
ADD_CHECK_FIRST = (
    "the check must be in specs/certify.md first: add it there (skill verify-on-other-systems); its name"
    " follows section 3.4 (Check) of report-format.md of the skellycertify repository, a new reason code"
    " follows its section 5.4 and goes into skellycam/REASON_CODES.md in the same commit, and a new field,"
    " common reason code, allowed value or summary group needs a format change under its section 8, asked"
    " from the skellycertify maintainers first"
)


class GitError(Exception):
    pass


def git(root: Path, *args: str) -> list[str]:
    exe = shutil.which("git")
    if exe is None:
        raise GitError("git is not on the PATH")
    out = subprocess.run([exe, "-C", str(root), *args], capture_output=True)  # noqa: S603
    if out.returncode:
        raise GitError(out.stderr.decode("utf-8", "replace").strip().splitlines()[0])
    return [n for n in out.stdout.decode("utf-8").split("\0") if n]


def repo_root(cwd: Path) -> Path:
    return Path(git(cwd, "rev-parse", "--show-toplevel")[0].strip())


def added_files(root: Path) -> list[str]:
    return git(root, "diff", "--cached", "--name-only", "--diff-filter=A", "--no-renames", "-z")


def tracked_files(root: Path) -> list[str]:
    return git(root, "ls-files", "-z")


def in_scope(rel: str) -> bool:
    path = PurePosixPath(rel)
    return path.suffix.lower() in SCRIPT_SUFFIXES and not rel.startswith(EXEMPT_PATHS) and "tests" not in path.parts[:-1]


def read_text(file: Path) -> str:
    data = file.read_bytes()
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def other_value(subject: str, op: str, values: list[str], lab: tuple[str, ...]) -> str | None:
    """The value of the guard that names another system, or None."""
    if subject != "sys.platform":
        return next((v for v in values if v not in LAB_SYSTEMS), None)
    if op == ".startswith(":
        return next((v for v in values if not any(p.startswith(v) for p in lab)), None)
    return next((v for v in values if v not in lab), None)


def spec_names(root: Path) -> frozenset[str] | None:
    """The check names of the certify spec, or None when the spec is missing."""
    spec = root / CERTIFY_SPEC
    if not spec.is_file():
        return None
    return frozenset(span for span in CODE_SPAN.findall(read_text(spec)) if CHECK_NAME.fullmatch(span))


def reason_of(
    rel: str, root: Path, lab: tuple[str, ...] = LAB_PLATFORMS, names: frozenset[str] | None = None
) -> tuple[str, str] | None:
    """Why the script is refused and what to do, or None."""
    file = root / rel
    if not in_scope(rel) or not file.is_file():
        return None
    # shortcut: reads the working-tree file, not the staged blob, as check_camera_media.py does.
    text = read_text(file)
    for line in text.splitlines()[:MARKER_LINES]:
        if not line.lstrip().startswith(("#", "//")):
            continue
        if NOT_APPLICABLE.search(line):
            return None
        marker = CERTIFY_MARKER.search(line)
        if marker and names is not None and marker.group(1) in names:
            return None
        if marker:
            where = CERTIFY_SPEC if names is not None else f"{CERTIFY_SPEC} (the file is missing)"
            return f"its certify-check name {marker.group(1)!r} is not a check name of {where}", ADD_CHECK_FIRST
    systems = OTHER_SYSTEM_NAMES & set(re.split(r"[^a-z0-9]+", rel.lower()))
    if systems:
        return f"its path names another system ({', '.join(sorted(systems))})", OTHER_SYSTEMS_ADVICE
    if PurePosixPath(rel).suffix.lower() == ".py":
        for subject, op, literal, op_in, sequence in GUARD.findall(text):
            op = op or " ".join(op_in.split())
            value = other_value(subject, op, LITERAL.findall(literal or sequence), lab)
            if value is not None:
                return f"it has a guard for another system ({subject} {op.strip('.(')} {value!r})", OTHER_SYSTEMS_ADVICE
    return None


def check(paths: list[str], root: Path, lab: tuple[str, ...] = LAB_PLATFORMS) -> list[str]:
    """The refusal lines for the given repo-relative paths."""
    refused = []
    names = spec_names(root)
    for rel in sorted({PurePosixPath(p.replace("\\", "/")).as_posix() for p in paths}):
        found = reason_of(rel, root, lab, names)
        if found:
            refused.append(f"{rel}: {found[0]}: {found[1]}")
    return refused


def relative(arg: str, root: Path) -> str:
    """A file argument as a path relative to the repository root."""
    try:
        return (Path.cwd() / arg).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return arg


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Refuse a manual script for another system.")
    parser.add_argument("files", nargs="*", help="files; default: the files that the commit adds")
    parser.add_argument("--all", action="store_true", help="check each tracked file")
    args = parser.parse_args(argv[1:])
    if args.all and args.files:
        parser.error("give --all or files, not both")
    try:
        root = repo_root(Path.cwd())
        if args.files:
            paths = [relative(f, root) for f in args.files]
        else:
            paths = tracked_files(root) if args.all else added_files(root)
    except GitError as error:
        print(f"other systems: cannot run git here: {error}")
        return 2
    refused = check(paths, root)
    if refused:
        print("\n".join(refused))
        return 1
    print(f"other systems: no findings ({len(paths)} files, {sum(map(in_scope, paths))} scripts in scope)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
