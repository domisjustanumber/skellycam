#!/usr/bin/env python3
"""Refuse CRLF line ends in the files of the git index (decision 0001).

Usage::

    python tools/check_line_ends.py [ROOT]

Each text file of each repository uses LF line ends, on each system. The line
``* text=auto eol=lf`` of ``.gitattributes`` makes git write LF into the index and into each
working tree, also when ``core.autocrlf`` is set. The tool reads ``git ls-files --eol`` and
reports each file whose index text has a CRLF line end (``i/crlf``) or mixed line ends
(``i/mixed``). It exits 1 when it reports a file. A binary file is not reported, and a path that
``.gitattributes`` sets to ``-text`` is not reported: for example a golden file that a test
compares byte for byte. Such a line must come after the kit block of ``.gitattributes``. To repair the
index, run ``git add --renormalize .`` and commit the result by itself. The pre-commit hook runs
the tool on the index of the commit, and the doc test runs it in CI. Standard library and the
git CLI only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BAD = ("i/crlf", "i/mixed")


def crlf_files(root: Path) -> list[str]:
    """The paths of the index whose text has a CRLF line end or mixed line ends."""
    git = shutil.which("git")
    if git is None:
        raise SystemExit("git is not on the PATH")
    out = subprocess.run(  # noqa: S603
        [git, "-C", str(root), "ls-files", "--eol", "-z"], capture_output=True, check=True
    )
    found = []
    for row in out.stdout.decode("utf-8").split("\0"):
        info, _, path = row.partition("\t")
        fields = info.split()
        if path and fields[0] in BAD and "attr/-text" not in fields:
            found.append(path)
    return sorted(found)


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd()
    found = crlf_files(root)
    if found:
        print("\n".join(f"{p}: CRLF line ends in the index; run `git add --renormalize .`" for p in found))
        return 1
    print("line ends: LF in each text file of the index")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
