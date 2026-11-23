"""The marker `pace` (specs/windows-capture.md 16.1; a decision of the user of 2026-11-23, Q619: "A red workflow
should mean a real fault").

A test whose result depends on the pace of the machine or on a wall-clock limit has the marker `pace`. On a real
machine it runs strict. Each workflow runs it in a step of its own with `continue-on-error: true` and
`SKELLYCAM_PACE_MARGIN: "3"`, and leaves it out of its blocking step with `not pace`. This test checks the
registration, the marked tests and each workflow of `.github/workflows/`.
"""

import importlib
import re
import shlex
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PACE_TESTS = [
    ("skellycam.tests.capture.test_bounded_call", "test_t_unx_26_the_bounded_calls_end_within_their_tolerance"),
    ("skellycam.tests.capture.test_media_foundation_source", "test_t_unx_76_the_timing_values_of_the_stand_in"),
    ("skellycam.tests.capture.test_media_foundation_source", "test_f7_the_hung_close_ends_within_its_tolerance"),
    ("skellycam.tests.frame_ring.test_concurrency", "test_t_ring_12_the_writer_timing_is_unchanged_after_a_reader_kill"),
    ("skellycam.tests.frame_ring.test_camera_process", "test_t_ring_23_write_p99_with_four_readers"),
    ("skellycam.tests.take_recorder.test_connection", "test_a_slow_stop_has_a_gap_only_on_the_last_row"),
]
# A test whose failure does not depend on the pace blocks (16.1): the functional halves of the split tests, the
# long-interval test (no bound of time), the slow stop (its row counts are the lock rule), and the tests of item 1
# of fix lane 4 (no answer from a camera process).
NOT_PACE = [
    ("skellycam.tests.capture.test_bounded_call", "test_t_unx_26_generic_bounded_call_with_a_limit"),
    ("skellycam.tests.capture.test_media_foundation_source", "test_t_unx_76_media_foundation_diagnostics"),
    ("skellycam.tests.capture.test_media_foundation_source",
     "test_t_unx_76_long_intervals_count_with_the_period_of_the_granted_mode"),
    ("skellycam.tests.capture.test_media_foundation_source",
     "test_f7_a_hanging_restore_ends_the_close_as_hung_within_its_bound"),
    ("skellycam.tests.frame_ring.test_concurrency", "test_t_ring_12_reader_killed"),
    ("skellycam.tests.frame_ring.test_camera_process", "test_t_ring_23_write_with_four_readers"),
    ("skellycam.tests.take_recorder.test_connection", "test_a_slow_stop_ends_each_camera_at_the_last_frame"),
    ("skellycam.tests.take_recorder.test_connection",
     "test_t_rec_44_hang_ends_the_process_and_the_take_level_completes_its_file"),
    ("skellycam.tests.take_recorder.test_connection", "test_a_busy_main_process_does_not_look_dead"),
]


def marker_names(module, name):
    function = getattr(importlib.import_module(module), name)
    return {mark.name for mark in getattr(function, "pytestmark", [])}


def test_the_marker_is_registered():
    markers = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]["markers"]
    assert any(line.split(":")[0].strip() == "pace" for line in markers), markers


@pytest.mark.parametrize("module, name", PACE_TESTS, ids=[name for _, name in PACE_TESTS])
def test_each_pace_test_has_the_marker(module, name):
    assert "pace" in marker_names(module, name)


def test_the_marked_tests_are_exactly_the_pace_tests():
    """16.1: a `pace` test holds only its bounds of time. No other test of the package has the marker."""
    marked = set()
    for path in (REPO / "skellycam" / "tests").rglob("test_*.py"):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.strip().startswith("@pytest.mark.pace"):
                following = next(text for text in lines[index + 1:] if text.startswith("def test_"))
                marked.add(following.split("(")[0].removeprefix("def "))
    assert marked == {name for _, name in PACE_TESTS}


@pytest.mark.parametrize("module, name", NOT_PACE, ids=[name for _, name in NOT_PACE])
def test_a_test_that_fails_for_another_reason_has_no_marker(module, name):
    assert "pace" not in marker_names(module, name)


def pytest_steps(job):
    """(step, paths, marker expression) of each step of `job` that runs pytest on `skellycam/tests`."""
    found = []
    for step in job.get("steps", []):
        run = step.get("run") or ""
        if "pytest" not in run or "skellycam/tests" not in run:
            continue
        words = shlex.split(run.replace("\n", " "))
        paths = sorted(word for word in words if word.startswith("skellycam/tests"))
        expression = words[words.index("-m") + 1] if "-m" in words else ""
        found.append((step, paths, expression))
    return found


def is_pace_step(step, expression):
    return re.search(r"(?<!not )\bpace\b", expression) is not None and "not pace" not in expression


@pytest.mark.parametrize("workflow", sorted(p.name for p in (REPO / ".github" / "workflows").glob("*.yml")))
def test_each_workflow_runs_the_pace_tests_in_a_step_that_does_not_fail_the_run(workflow):
    jobs = yaml.safe_load((REPO / ".github" / "workflows" / workflow).read_text(encoding="utf-8")).get("jobs", {})
    for job_name, job in jobs.items():
        steps = pytest_steps(job)
        blocking = [(step, paths, expression) for step, paths, expression in steps if not is_pace_step(step, expression)]
        pace = [(step, paths, expression) for step, paths, expression in steps if is_pace_step(step, expression)]
        for step, paths, expression in blocking:
            assert "not pace" in expression, f"{workflow} {job_name}: {step.get('name')} runs the pace tests"
            assert any(set(paths) <= set(other) for _, other, _ in pace), \
                f"{workflow} {job_name}: no pace step for {paths}"
        for step, _, _ in pace:
            assert step.get("continue-on-error") is True, f"{workflow} {job_name}: {step.get('name')}"
            assert (step.get("env") or {}).get("SKELLYCAM_PACE_MARGIN") == "3", f"{workflow} {job_name}"
            assert step.get("if") == "${{ !cancelled() }}", f"{workflow} {job_name}: {step.get('name')}"


def test_the_margin_is_1_on_a_real_machine(monkeypatch):
    pace = importlib.import_module("skellycam.tests.pace")
    monkeypatch.delenv("SKELLYCAM_PACE_MARGIN", raising=False)
    assert pace.margin() == 1.0
    monkeypatch.setenv("SKELLYCAM_PACE_MARGIN", "3")
    assert pace.margin() == 3.0
    monkeypatch.setenv("SKELLYCAM_PACE_MARGIN", "0.5")  # never stricter than the machine of the user
    assert pace.margin() == 1.0
