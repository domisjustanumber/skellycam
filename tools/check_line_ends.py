#!/usr/bin/env python3
"""Refuse CRLF line ends in the files of the git index (decision 0001).

Usage::

    python tools/check_line_ends.py [ROOT]             # check the index
    python tools/check_line_ends.py --refresh [ROOT]   # write the CRLF files of a clean worktree again

Each text file of each repository uses LF line ends, on each system. The line
``* text=auto eol=lf`` of ``.gitattributes`` makes git write LF into the index and into each
working tree, also when ``core.autocrlf`` is set. The tool reads ``git ls-files --eol`` and
reports each file whose index text has a CRLF line end (``i/crlf``) or mixed line ends
(``i/mixed``). It exits 1 when it reports a file. A binary file is not reported, and a path that
``.gitattributes`` sets to ``-text`` is not reported: for example a golden file that a test
compares byte for byte. Such a line must come after the kit block of ``.gitattributes``. To repair the
index, run ``git add --renormalize .`` and commit the result by itself. The pre-commit hook runs
the tool on the index of the commit, and the doc test runs it in CI.

A working tree that git wrote before the rule keeps its CRLF files. ``--refresh`` writes each of
them again from the index, with LF. Run it in each clean worktree that git wrote before the rule.
It refuses when ``git diff HEAD`` shows a change of a tracked file, so that it cannot delete work:
commit or stash the change first. A file that differs only by its line ends is not a change. git
hides the change of a file marked assume-unchanged or skip-worktree, so the tool refuses such a
file, and it compares the content of each file with the index before it deletes the first one. The
tool does not touch an untracked file. Standard library and the git CLI only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BAD = ("i/crlf", "i/mixed")


def git(root: Path, *args: str, stdin: bytes | None = None) -> bytes:
    exe = shutil.which("git")
    if exe is None:
        raise SystemExit("git is not on the PATH")
    out = subprocess.run([exe, "-C", str(root), *args], input=stdin, capture_output=True, check=True)  # noqa: S603
    return out.stdout


def eol_rows(root: Path) -> list[tuple[list[str], str]]:
    """The fields (``i/...``, ``w/...``, ``attr/...``) and the path of each file of the index."""
    rows = []
    for row in git(root, "ls-files", "--eol", "-z").decode("utf-8").split("\0"):
        info, _, path = row.partition("\t")
        if path:
            rows.append((info.split(), path))
    return rows


def crlf_files(root: Path) -> list[str]:
    """The paths of the index whose text has a CRLF line end or mixed line ends."""
    return sorted(p for f, p in eol_rows(root) if f[0] in BAD and "attr/-text" not in f)


def flagged_paths(root: Path) -> set[str]:
    """The paths that ``git ls-files -v`` marks assume-unchanged (a lower-case tag) or skip-worktree (``S``)."""
    flagged = set()
    for row in git(root, "ls-files", "-v", "-z").decode("utf-8").split("\0"):
        tag, _, path = row.partition(" ")
        if path and (tag.islower() or tag.upper() == "S"):
            flagged.add(path)
    return flagged


def changed_paths(root: Path, paths: list[str]) -> list[str]:
    """The paths whose working file, after the line-end rule, is not the blob of the index."""
    # hash-object reads each file at its path, so it applies the rule of .gitattributes, as git add does.
    worktree = git(root, "hash-object", "--stdin-paths", stdin="\n".join(paths).encode("utf-8")).decode().split()
    # The whole index, with no pathspec: a list of many paths passes the command-line limit of Windows.
    index = {}
    for row in git(root, "ls-files", "-s", "-z").decode("utf-8").split("\0"):
        info, _, path = row.partition("\t")
        if path:
            index[path] = info.split()[1]
    return [p for p, blob in zip(paths, worktree, strict=True) if index.get(p) != blob]


def refresh(root: Path) -> list[str]:
    """Write each CRLF text file of a clean working tree again from the index. Return the paths."""
    # git diff compares the text after the line-end rule, so a file that differs only by CRLF is not a change.
    if git(root, "diff", "--name-only", "HEAD", "--").strip():
        raise SystemExit("line ends: the worktree has changes; commit or stash them, then run --refresh again")
    paths = sorted(p for f, p in eol_rows(root) if f[1] in ("w/crlf", "w/mixed") and "attr/-text" not in f)
    if not paths:
        return paths
    flagged = sorted(flagged_paths(root).intersection(paths))
    if flagged:
        raise SystemExit(
            "line ends: git hides the changes of files marked assume-unchanged or skip-worktree, so --refresh"
            f" does not write them: {', '.join(flagged)}; clear the marks (`git update-index"
            " --no-assume-unchanged --no-skip-worktree <path>`), then run --refresh again"
        )
    # Check every file before the first delete: the content of each file must be the blob of the index.
    changed = changed_paths(root, paths)
    if changed:
        raise SystemExit(f"line ends: these files differ from the index: {', '.join(changed)}; commit or stash them")
    for path in paths:
        (root / path).unlink()
    try:
        git(root, "checkout", "--pathspec-from-file=-", "--pathspec-file-nul", stdin="\0".join(paths).encode("utf-8"))
    except subprocess.CalledProcessError as error:
        # Each deleted file matched the index, so `git checkout` can write it again with no loss.
        raise SystemExit(
            f"line ends: git checkout failed after the delete ({error.stderr.decode(errors='replace').strip()});"
            " the index holds each file: run `git checkout -- .`"
        ) from error
    return paths


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args[:1] == ["--refresh"]:
        root = Path(args[1]).resolve() if len(args) > 1 else Path.cwd()
        print(f"line ends: wrote {len(refresh(root))} files again with LF")
        return 0
    root = Path(args[0]).resolve() if args else Path.cwd()
    found = crlf_files(root)
    if found:
        print("\n".join(f"{p}: CRLF line ends in the index; run `git add --renormalize .`" for p in found))
        return 1
    print("line ends: LF in each text file of the index")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
