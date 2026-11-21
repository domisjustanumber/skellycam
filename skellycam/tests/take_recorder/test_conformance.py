"""T-REC-37: the conformance subset of skellyfileformat (specs/recorder.md, section 12.3).

The test exports `pyproject.toml` and `tests/conformance/` of the pinned commit from a checkout of
the skellyfileformat repository with `git archive` into `tmp_path`. It does not change that checkout.
It runs the test functions that use the fixture `writer` and not `reader` (`sff_select.py`), with
the adapter `sff_adapter.py`, and compares each result with the hand-written table `sff_expected.py`.

The checkout is `../skellyfileformat` next to this repository, or the folder in
`SKELLYFILEFORMAT_DIR` (the CI job sets it). When neither holds the pinned commit, the test is
skipped with the reason.
"""

import io
import os
import re
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from skellycam.tests.take_recorder.children import REPO_ROOT
from skellycam.tests.take_recorder.sff_expected import EXPECTED, SFF_COMMIT

HOW = ("clone the skellyfileformat repository next to this repository (`../skellyfileformat`), or set "
       f"SKELLYFILEFORMAT_DIR to a checkout of it, with commit {SFF_COMMIT} in its history")


def checkout():
    """The skellyfileformat checkout that holds the pinned commit, or None."""
    candidates = [os.environ.get("SKELLYFILEFORMAT_DIR", ""), str(REPO_ROOT.parent / "skellyfileformat")]
    for candidate in filter(None, candidates):
        folder = Path(candidate)
        if not folder.is_dir():
            continue
        found = subprocess.run(["git", "-C", str(folder), "cat-file", "-e", f"{SFF_COMMIT}^{{commit}}"],  # noqa: S607
                               capture_output=True, check=False)
        if found.returncode == 0:
            return folder
    return None


def export(folder, target):
    data = subprocess.run(["git", "-C", str(folder), "archive", "--format=tar", SFF_COMMIT, "pyproject.toml",  # noqa: S607
                           "tests/conformance"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(target, filter="data")


def outcomes(junit):
    """{test name: "pass" | "fail" | "skip"} from a JUnit XML report."""
    results = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        tags = {child.tag for child in case}
        results[case.get("name")] = "fail" if tags & {"failure", "error"} else "skip" if "skipped" in tags else "pass"
    return results


def expected_for(name):
    for pattern, result, reason in EXPECTED:
        if re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), name):
            return pattern, result, reason
    return None


def test_t_rec_37_conformance_subset(tmp_path):
    """T-REC-37 (12.3, agent 28): run the conformance subset of skellyfileformat at commit
    c1028ef185be86f0ac6ccf7f9ac2ce76def13f2d through `sff_adapter.py`. The results are exactly the
    expected results of 12.3: each listed test passes, fails or is skipped as listed, each collected
    test is listed, and each row of the table matches a collected test."""
    folder = checkout()
    if folder is None:
        pytest.skip(f"the pinned skellyfileformat checkout is not available: {HOW}")
    root = tmp_path / "skellyfileformat"
    export(folder, root)
    junit = tmp_path / "conformance.xml"
    path = os.pathsep.join(filter(None, [str(REPO_ROOT), os.environ.get("PYTHONPATH", "")]))
    env = dict(os.environ, SKELLYFILEFORMAT_ADAPTER="skellycam.tests.take_recorder.sff_adapter", PYTHONPATH=path)
    command = [sys.executable, "-m", "pytest", str(root / "tests" / "conformance"), "-p",
               "skellycam.tests.take_recorder.sff_select", "-p", "no:cacheprovider", "--rootdir", str(root), "-c",
               str(root / "pyproject.toml"), f"--junitxml={junit}", "-q", "-o", "junit_family=xunit2"]
    run = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, check=False, timeout=1800)  # noqa: S603
    assert junit.is_file(), f"the conformance run wrote no report:\n{run.stdout[-3000:]}\n{run.stderr[-3000:]}"
    results = outcomes(junit)
    assert results, f"no conformance test was collected:\n{run.stdout[-3000:]}"
    faults, matched = [], set()
    for name, result in sorted(results.items()):
        row = expected_for(name)
        if row is None:
            faults.append(f"{name}: {result}, but section 12.3 does not list it")
            continue
        matched.add(row[0])
        if result != row[1]:
            faults.append(f"{name}: {result}, expected {row[1]}" + (f" ({row[2]})" if row[2] else ""))
    for pattern, _, _ in EXPECTED:
        if pattern not in matched:
            faults.append(f"{pattern}: listed in 12.3, but not collected")
    assert faults == [], "\n".join(faults) + f"\n\n{run.stdout[-3000:]}"
