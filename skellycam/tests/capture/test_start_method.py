"""The start method of a camera process (specs/unix-capture.md 4.12) [ADR-HQE5] and the skip guard of the workflows
(4.11).

CI run 45214740615 (Linux): each camera process forked after T-REC-31 freed a PyAV `VideoReformatter` of the main
process at once, waited in `sws_freeContext` for FFmpeg threads that the fork did not copy, and never answered.
"""

import logging
import multiprocessing
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from skellycam.tests.capture.capture_session import capture_app, capture_logs, product, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_python(code: str) -> str:
    """Run `code` in a fresh interpreter (the start method is per process) and give its last line of output."""
    process = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                             cwd=str(REPO_ROOT))
    assert process.returncode == 0, process.stderr[-3000:]
    return process.stdout.strip().splitlines()[-1]


def test_the_entry_point_sets_spawn_before_any_multiprocessing_object():
    """4.12 (a): the first statements of `skellycam/__main__.py` import `multiprocessing` and set `spawn`, before any
    other import; an import of the entry module in a fresh interpreter gives `spawn` on each system."""
    import ast

    tree = ast.parse((REPO_ROOT / "skellycam" / "__main__.py").read_text(encoding="utf-8"))
    body = [node for node in tree.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))]
    assert isinstance(body[0], ast.Import) and [alias.name for alias in body[0].names] == ["multiprocessing"]
    assert isinstance(body[1], ast.If) and "set_start_method" in ast.unparse(body[1])
    assert run_python("import skellycam.__main__, multiprocessing; "
                      "print(multiprocessing.get_start_method(allow_none=True))") == "spawn"


def test_the_package_sets_no_start_method():
    """4.12: `import skellycam` sets no start method (the host owns it)."""
    assert run_python("import multiprocessing, skellycam; print(multiprocessing.get_start_method(allow_none=True))") \
        == "None"


def test_a_host_can_set_the_start_method_after_the_import():
    """4.12 (b), case B of the review: a host sets the start method after `import skellycam`, as before the lane."""
    assert run_python("import multiprocessing, skellycam; multiprocessing.set_start_method('spawn'); "
                      "print(multiprocessing.get_start_method())") == "spawn"


def test_a_camera_process_of_a_fork_host_is_refused_with_its_code(monkeypatch):
    """4.12 (c): with the start method `fork` (a host that made a multiprocessing object first, on Linux), the start of a
    camera process is refused: the camera is `failed` at once with `start-method-fork` and the text of the fix, and no
    process starts; the apply request does not wait for the limit of 30 s. Here the method is given to the check."""
    from skellycam.core.camera import camera_worker

    monkeypatch.setattr(camera_worker, "start_method", lambda: "fork")
    started = time.monotonic()
    with capture_app(monkeypatch, [FakeScript()], workers="process") as app:
        app.detect()
        camera_id = app.factory.camera_ids[0]
        response = app.apply([app.config(camera_id)])
        assert response.status_code == 200, response.text
        status = app.status(camera_id)
        assert status["state"] == "failed"
        assert status["failure"]["code"] == "start-method-fork"
        assert "set_start_method('spawn')" in status["failure"]["reason"]
        assert app.worker(camera_id).worker.pid is None
    assert time.monotonic() - started < 25


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="fork is the default only on Linux")
def test_on_linux_a_queue_made_before_the_import_fixes_fork():
    """4.12 (c), case A of the review: on Linux a host that makes a `multiprocessing.Queue` before `import skellycam`
    has the method `fork`; the check of the camera start sees `fork` (so it refuses, as the test above shows)."""
    assert run_python("import multiprocessing; queue = multiprocessing.Queue(); import skellycam; "
                      "print(multiprocessing.get_start_method())") == "fork"


def decode_a_video_with_pyav(folder):
    """What T-REC-31 and the player do in the main process: encode and decode a short video with PyAV, with a
    conversion to BGR (a `VideoReformatter` with FFmpeg slice threads)."""
    import av

    path = folder / "probe.mkv"
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mjpeg", rate=30)
        stream.width, stream.height, stream.pix_fmt = 640, 480, "yuvj420p"
        for k in range(10):
            image = np.full((480, 640, 3), 10 * k, np.uint8)
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="bgr24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    with av.open(str(path)) as container:
        frames = [frame.to_ndarray(format="bgr24") for frame in container.decode(video=0)]
    assert len(frames) == 10


def test_a_camera_process_starts_after_a_video_decode_in_the_main_process(monkeypatch, tmp_path):
    """4.12 (CI run 45214740615): the main process decodes a video with PyAV; then two camera processes start. Each
    is `ready`. With `fork` on Linux each one hung at its start ("no answer from the camera process in 30 s")."""
    decode_a_video_with_pyav(tmp_path)
    with capture_app(monkeypatch, [FakeScript(), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        assert all(app.state(camera_id) == "ready" for camera_id in app.factory.camera_ids)


def test_a_replaced_status_array_stays_in_the_main_process():
    """4.12: a camera process opens each shared array by its name while it starts (spawn on Linux and macOS). The main
    process keeps the arrays of the last two replacements of `reset_for_start`, never pickles that list, and frees
    older ones (each holds file descriptors)."""
    module = product("skellycam.core.camera_group.camera_status")
    status = module.CameraStatus()
    generations = []
    for _ in range(5):
        generations.append([getattr(status, name) for name in module.ARRAYS])
        status.reset_for_start()
    assert len(status.retired) == 2 * len(module.ARRAYS)
    kept = [id(array) for array in status.retired]
    assert [id(array) for array in generations[-2] + generations[-1]] == kept
    assert not any(id(array) in kept for array in generations[0])
    assert "retired" not in status.__getstate__()


def test_the_certify_session_sees_the_end_of_a_child_that_psutil_reaped():
    """4.12: `kill_tree` reaps the session child with psutil. `_ChildSession.alive()` reads the sentinel, so it sees
    the end; on POSIX `Process.is_alive()` of a child that another call reaped stays True (the cancel never ended)."""
    run = product("skellycam.core.certify.run")
    session = object.__new__(run._ChildSession)
    session.process = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(60,), daemon=True)
    session.process.start()
    try:
        assert session.alive()
        run.kill_tree(session.process.pid)
        deadline = time.monotonic() + 10
        while session.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not session.alive()
    finally:
        if session.process.is_alive():
            session.process.kill()


def report(nodeid, skipped=True, **extra):
    return SimpleNamespace(nodeid=nodeid, skipped=skipped, **extra)


def test_the_skip_guard_fails_a_skip_under_a_guarded_path():
    """4.11: `SKELLYCAM_NO_SKIP` names `test_connection.py`. A skip of one of its tests is a guarded skip; a skip of
    another file, a passed test and an expected failure (`xfail`) are not."""
    from skellycam.tests import skip_guard

    paths = skip_guard.guarded_paths("skellycam/tests/take_recorder/test_connection.py, skellycam/tests/preview")
    assert paths == ["skellycam/tests/take_recorder/test_connection.py", "skellycam/tests/preview"]
    guarded = "skellycam/tests/take_recorder/test_connection.py::test_t_rec_44"
    assert skip_guard.is_guarded_skip(report(guarded), paths)
    assert skip_guard.is_guarded_skip(report("skellycam/tests/preview/test_x.py::test_y"), paths)
    assert not skip_guard.is_guarded_skip(report("skellycam/tests/take_recorder/test_connection2.py::t"), paths)
    assert not skip_guard.is_guarded_skip(report(guarded, skipped=False), paths)
    assert not skip_guard.is_guarded_skip(report(guarded, wasxfail="pace"), paths)
    assert not skip_guard.is_guarded_skip(report(guarded), [])


@pytest.mark.parametrize("module", ["pytestmark", "allow_module_level", "importorskip"])
def test_the_skip_guard_fails_a_run_with_a_module_skip(tmp_path, module):
    """4.11 (M2 of the review): a skip of a whole guarded module fails the run, in each form: `pytestmark`,
    `pytest.skip(..., allow_module_level=True)` (a collect report) and `pytest.importorskip` (a collect report). The run
    also has one passing test of another file."""
    import os

    bodies = {
        "pytestmark": "import pytest\npytestmark = pytest.mark.skip(reason='x')\ndef test_a():\n    pass\n",
        "allow_module_level": "import pytest\npytest.skip('not here yet', allow_module_level=True)\ndef test_a():\n    pass\n",
        "importorskip": "import pytest\npytest.importorskip('no_such_module_xyz')\ndef test_a():\n    pass\n",
    }
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_guarded.py").write_text(bodies[module], encoding="utf-8")
    (tmp_path / "test_other.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    env = {**os.environ, "SKELLYCAM_NO_SKIP": "test_guarded.py"}
    process = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "skellycam.tests.conftest", "-p",
                              "no:cacheprovider", str(tmp_path)], capture_output=True, text=True, timeout=120,
                             cwd=str(tmp_path), env=env)
    assert process.returncode == 1, process.stdout[-2000:]
    assert "skipped under a guarded path" in process.stdout
