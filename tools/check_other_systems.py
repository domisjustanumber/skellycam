#!/usr/bin/env python3
"""Each script that names or guards for a system states its purpose (decisions VV4Q, K3BX and C307).

Usage::

    python tools/check_other_systems.py [FILE ...]   # the given files
    python tools/check_other_systems.py              # the files that the commit adds (the pre-commit hook)
    python tools/check_other_systems.py --all        # each tracked file (the doc test and CI)

You can test only on the system that you work on. You can reach each other system only through the
self-test of the project (``SELF_TEST``) and its report. The tool is the primary mechanical check of
the rule. It cannot see a proposal in chat; the rule and the skill ``verify-on-other-systems``
cover that. It checks the whole repository, also when you run it from a subfolder. Each mode gives
the same result on each system: no system is special.

The table ``[check_other_systems]`` of ``kit.toml`` in the repository root sets the values of the
repository: ``exempt_paths`` (the path prefixes of the product folders and the CI workflows,
``EXEMPT_PATHS``), ``certify_spec`` (the spec that holds the check names, ``CERTIFY_SPEC``),
``self_test`` (the name of the self-test, ``SELF_TEST``) and ``certify_contract`` (the document of
the certify contract, ``CERTIFY_CONTRACT``). With no ``kit.toml``, the defaults below apply.

- **Scope.** It checks only a script file (``SCRIPT_SUFFIXES``) outside ``EXEMPT_PATHS`` and
  outside a ``tests`` folder. The product code, its tests, the docs site and the CI workflows can
  name systems.
- **Signals.** A script has a signal when a part of its path (split at each character that is not
  a letter or a digit) is a key of ``SYSTEM_NAMES``, or when a Python script compares
  ``sys.platform`` or ``platform.system()`` with a literal: ``==``, ``!=``, ``in``, ``not in`` or
  ``startswith``.
- **The purpose field.** A script with a signal must have, in one of its first ``MARKER_LINES``
  lines, a comment (``#`` or ``//``) ``script-purpose: <kind> ...``. ``KINDS`` are:

  - ``certify-check <name>``: the script serves this certify check. ``<name>`` must be a check name
    of ``CERTIFY_SPEC`` (decision K3BX). Else the check must be added to the spec first
    (``ADD_CHECK_FIRST``).
  - ``local-study (<what>)``: a measurement on the system of the author. Its result is a fact about
    that system only, and it is "not verified" for each other system.
  - ``tool (<what>)``: it builds, formats or checks files. It tests no product behaviour.
  - ``ci (<workflow>)``: only the CI workflow ``.github/workflows/<workflow>`` runs it, with no
    device. The workflow file must exist.

  Each other kind, an empty ``(...)`` and a missing spec are refused. A purpose field is checked
  also on a script with no signal. The old markers ``certify-check: <name>`` and
  ``other-systems: not applicable (<reason>)`` are not valid; the refusal line says so.
- **Check names.** A check name is the whole text of a code span of the spec that matches
  ``CHECK_NAME`` (``detect``, or parts joined by ``:``; a ``<word>`` placeholder counts as one
  part), whose first part is in ``FIRST_PARTS`` and whose other parts are not in ``GENERIC``. So a
  name matches in the form that the spec writes, for example ``<label>:usb3-trial``; a filled-in
  name, a part of a name (``clock:base``) and a name form (``system:<check>``) do not.
- **Modes.** The default mode checks the files that the commit adds, with rename detection off: a
  moved or a replaced file is a new file. ``--all`` checks each tracked file.
- It does not catch: an instruction in a shell script or in Markdown (it reads only the path of a
  shell script), a script with no script suffix, a script named for its probe and not for the
  system, a guard with the literal first, ``os.name`` and ``match``. It finds a signal in a comment
  that quotes a guard.

Exit codes: 0 when no file is refused, 1 when a file is refused, 2 for a usage error, outside a git
repository, or with no git. It reads a file with a UTF-16 BOM as UTF-16. Standard library and the
git CLI only.
"""

from __future__ import annotations

import argparse
import codecs
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath


def kit_values(section: str, keys: set[str]) -> dict:
    """The table ``[section]`` of ``kit.toml`` in the repository root, or {} when there is no file."""
    path = Path(__file__).resolve().parents[1] / "kit.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as file:
        table = tomllib.load(file).get(section, {})
    unknown = sorted(set(table) - keys)
    if unknown:
        raise SystemExit(f"kit.toml [{section}]: unknown keys: {', '.join(unknown)}")
    return table


KIT = kit_values("check_other_systems", {"exempt_paths", "certify_spec", "self_test", "certify_contract"})

# The product folders and the CI workflows, from kit.toml. They can name systems.
EXEMPT_PATHS: tuple[str, ...] = tuple(KIT.get("exempt_paths", [".github/"]))
SCRIPT_SUFFIXES = frozenset(".py .sh .bash .zsh .command .ps1".split())
SYSTEM_NAMES = {
    "win": "Windows",
    "windows": "Windows",
    "win32": "Windows",
    "mac": "macOS",
    "macos": "macOS",
    "osx": "macOS",
    "darwin": "macOS",
    "linux": "Linux",
}
MARKER_LINES = 5
KINDS = ("certify-check", "local-study", "tool", "ci")
PURPOSE = re.compile(r"script-purpose:\s*(\S*)\s*(.*?)\s*$")
TEXT = re.compile(r"\(\s*([^)\s][^)]*?)\s*\)")
OLD_MARKER = re.compile(r"certify-check:|other-systems:")
CERTIFY_SPEC: str = KIT.get("certify_spec", "specs/certify.md")  # The spec that holds the check names.
SELF_TEST: str = KIT.get("self_test", "the self-test of the project")
CERTIFY_CONTRACT: str = KIT.get("certify_contract", "the certify contract")
CODE_SPAN = re.compile(r"`([^`\n]+)`")
_PART = r"(?:[A-Za-z0-9]|<[a-z]+>)(?:[A-Za-z0-9_.@-]|<[a-z]+>)*"
CHECK_NAME = re.compile(rf"detect|(?:<[a-z]+>|[a-z][a-z0-9-]*)(?::{_PART})+")
# The first parts of the name forms of spec 3.1, and of `session:exit`, `report:rules` and `pipeline:gate`.
FIRST_PARTS = frozenset("<label> <model> <name> detect group system self probe session report pipeline release".split())
GENERIC = frozenset("<check> <name> <group> <condition>".split())  # a name form, not a check name
GUARD = re.compile(
    r"(sys\.platform|platform\.system\(\))\s*"
    r"""(?:(==|!=|\.startswith\()\s*("[^"]*"|'[^']*')|((?:not\s+)?in)\s*([\(\[\{][^)\]\}]*))"""
)
PURPOSE_ADVICE = (
    "add the comment 'script-purpose: <kind> ...' in the first"
    f" {MARKER_LINES} lines; the kinds are 'certify-check <name>', 'local-study (<what>)', 'tool (<what>)'"
    f" and 'ci (<workflow>)'; test other systems only through {SELF_TEST} (see AGENTS.md, Project Rules)"
)
# The pointer to the process of the certify contract for a new check. Change it here only.
ADD_CHECK_FIRST = (
    f"the check must be in {CERTIFY_SPEC} first: follow sections 5.5 (How a package adds a check) and 5.6"
    f" (When a check can exist, and its level) of {CERTIFY_CONTRACT} (skill verify-on-other-systems)"
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


def spec_names(root: Path) -> frozenset[str] | None:
    """The check names of the certify spec, or None when the spec is missing."""
    spec = root / CERTIFY_SPEC
    if not spec.is_file():
        return None
    return frozenset(
        span
        for span in CODE_SPAN.findall(read_text(spec))
        if CHECK_NAME.fullmatch(span) and span.split(":")[0] in FIRST_PARTS and not GENERIC & set(span.split(":")[1:])
    )


def signal_of(rel: str, text: str) -> str | None:
    """The signal of the script, or None."""
    systems = sorted({SYSTEM_NAMES[t] for t in re.split(r"[^a-z0-9]+", rel.lower()) if t in SYSTEM_NAMES})
    if systems:
        return f"its path names a system ({', '.join(systems)})"
    if PurePosixPath(rel).suffix.lower() == ".py":
        for subject, op, literal, op_in, sequence in GUARD.findall(text):
            op = op or " ".join(op_in.split())
            return f"it has a system guard ({subject} {op.strip('.(')} {literal or sequence.strip() + ')'})"
    return None


def purpose_error(kind: str, rest: str, root: Path, names: frozenset[str] | None) -> tuple[str, str] | None:
    """Why the purpose field is not valid, and what to do, or None."""
    if kind not in KINDS:
        return f"its script-purpose kind {kind!r} is not one of {', '.join(KINDS)}", PURPOSE_ADVICE
    if kind == "certify-check":
        name = rest.split()[0] if rest else ""
        if names is not None and name in names:
            return None
        where = CERTIFY_SPEC if names is not None else f"{CERTIFY_SPEC} (the file is missing)"
        return f"its certify-check name {name!r} is not a check name of {where}", ADD_CHECK_FIRST
    text = TEXT.fullmatch(rest)
    if not text:
        return f"its script-purpose '{kind}' has no text in brackets", PURPOSE_ADVICE
    workflow = text.group(1)
    if kind == "ci" and ("/" in workflow or "\\" in workflow or not (root / ".github" / "workflows" / workflow).is_file()):
        return f"its script-purpose 'ci' names no file .github/workflows/{text.group(1)}", PURPOSE_ADVICE
    return None


def reason_of(rel: str, root: Path, names: frozenset[str] | None) -> tuple[str, str] | None:
    """Why the script is refused and what to do, or None."""
    file = root / rel
    if not in_scope(rel) or not file.is_file():
        return None
    # shortcut: reads the working-tree file, not the staged blob, as check_camera_media.py does.
    text = read_text(file)
    comments = [line for line in text.splitlines()[:MARKER_LINES] if line.lstrip().startswith(("#", "//"))]
    for line in comments:
        purpose = PURPOSE.search(line)
        if purpose:
            return purpose_error(purpose.group(1), purpose.group(2), root, names)
    signal = signal_of(rel, text)
    if signal is None:
        return None
    if any(OLD_MARKER.search(line) for line in comments):
        signal += "; its marker 'certify-check:' or 'other-systems:' is not valid now"
    return signal, PURPOSE_ADVICE


def check(paths: list[str], root: Path) -> list[str]:
    """The refusal lines for the given repo-relative paths."""
    refused = []
    names = spec_names(root)
    for rel in sorted({PurePosixPath(p.replace("\\", "/")).as_posix() for p in paths}):
        found = reason_of(rel, root, names)
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
    parser = argparse.ArgumentParser(description="Refuse a script for a system with no purpose field.")
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
