"""The start method of a camera process (specs/unix-capture.md 4.12) [ADR-HQE5] and the skip guard of the workflows
(4.11).

CI run 45214740615 (Linux): each camera process forked after T-REC-31 freed a PyAV `VideoReformatter` of the main
process at once, waited in `sws_freeContext` for FFmpeg threads that the fork did not copy, and never answered.
"""

import multiprocessing
from types import SimpleNamespace

import numpy as np

from skellycam.tests.capture.capture_session import capture_app, product, ready_app_steps
from skellycam.tests.capture.fake_source import FakeScript


def test_the_package_sets_the_start_method_spawn():
    """4.12: after `import skellycam` the start method is `spawn` on each system (Linux used `fork`)."""
    import skellycam  # noqa: F401

    assert multiprocessing.get_start_method() == "spawn"


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
    process keeps each array that `reset_for_start` replaced, and it never pickles that list."""
    status = product("skellycam.core.camera_group.camera_status").CameraStatus()
    old = [status.info, status.controls_before]
    status.reset_for_start()
    assert all(any(array is kept for kept in status.retired) for array in old)
    assert "retired" not in status.__getstate__()


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
