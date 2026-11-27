"""T-UNX-70 to T-UNX-72: the diagnostics of each camera, their path to the main process, the counters of
the shared loop and the frame hashes (specs/unix-capture.md 4.2 items 2 and 3, 4.6).

The diagnostics go on their own topic, `TopicTypes.DIAGNOSTICS` (ADR-AC5B item 24). The main process keeps
the newest dict of each camera; `serialize()` and `app_state` hold only the counter subset.

T-UNX-70 runs the fake source in real camera processes (PROCESS workers). The OpenCV fake and the case of a
dict over the limit replace module names of this process, so they run with THREAD workers. T-UNX-71 and
T-UNX-72 run with THREAD workers and the virtual clock; the spies see each ring write and each camera writer
frame.
"""

import hashlib
import json
import pickle
import time

import pytest

from skellycam.tests.capture.capture_session import (
    CaptureApp, OpenCVFakeFactory, Spies, block_payloads, capture_app, capture_logs, product, ready_app_steps)
from skellycam.tests.capture.fake_source import FakeScript

SOURCE_MODULE = "skellycam.core.camera.capture.source"
FRAME_LOG = [[k, k, 1_000_000 + k, 2_000_000 + k, 50_000 + k] for k in range(64)]


def diagnostics_of(app, camera_id):
    return app.group.diagnostics(camera_id)


@pytest.mark.capture_timing  # real camera processes: a new dict each second of real time
def test_t_unx_70_the_diagnostics_path_with_process_workers(monkeypatch):
    """T-UNX-70: a fake whose dict has 64 `frame_log` rows (and 60 hash keys of the loop) in a real camera
    process. A new dict comes each second; the accessors give the full newest dict, under 32 KiB, whole;
    `serialize()` and `app_state` hold only the counter subset; `CameraStatus.info` holds no diagnostics; no
    diagnostics message goes into `finished`."""
    source = product(SOURCE_MODULE)
    from skellycam.core.ipc.pubsub.pubsub_topics import DiagnosticsMessage, RecordingFinishedMessage

    with capture_app(monkeypatch, [FakeScript(diagnostics={"frame_log": FRAME_LOG})], workers="process") as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.wait(lambda: diagnostics_of(app, camera_id).get("sha256_29"), "a dict with 30 hashes", timeout=30)
        seen, deadline = set(), time.monotonic() + 3.5
        while time.monotonic() < deadline:
            seen.add(diagnostics_of(app, camera_id)["frames"])
            time.sleep(0.05)
        assert len(seen) >= 3, f"{len(seen)} different dicts in 3.5 s"
        full = diagnostics_of(app, camera_id)
        assert set(full) == set(source.DIAGNOSTIC_KEYS)
        assert full["frame_log"] == FRAME_LOG
        assert all(full[f"sha256_{i:02d}"] and full[f"sha256_frame_{i:02d}"] is not None for i in range(30))
        assert len(pickle.dumps(DiagnosticsMessage(camera_id=camera_id, diagnostics=full))) < 32 * 1024
        assert app.manager.diagnostics() == {camera_id: full}
        status = app.status(camera_id)
        assert list(status["diagnostics"]) == list(source.COUNTER_KEYS)
        assert status["diagnostics"]["frames"] in seen | {full["frames"]} and status["diagnostics"]["backend"] is None
        state = json.dumps(app.manager.to_state_dict())  # the `state` of the `app_state` message
        assert "frame_log" not in state and "sha256" not in state and '"encoded_by_skellycam"' in state
        info = app.group.cameras.orchestrator.camera_statuses[camera_id].info_dict()
        assert "diagnostics" not in info and "frame_log" not in json.dumps(info)
        assert all(isinstance(message, RecordingFinishedMessage) for message in app.group.finished)


def test_t_unx_70_a_dict_over_the_limit_is_not_sent(monkeypatch):
    """T-UNX-70: a fake whose dict is over 32 KiB: no dict reaches the main process, and the camera process
    logs it one time. The camera runs on."""
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript(diagnostics={"subtypes": "x" * 40_000})]) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.wait_clock(3.0, "three seconds of the camera")
        assert app.group.diagnostics(camera_id) == {} and app.manager.diagnostics() == {camera_id: {}}
        assert app.state(camera_id) == "ready"
        assert app.status(camera_id)["diagnostics"] == {}
    lines = [m for m in logs.messages() if "diagnostics not sent" in m]
    assert len(lines) == 1 and "over the limit" in lines[0], lines


def test_t_unx_70_the_opencv_dict(monkeypatch):
    """T-UNX-70: the OpenCV source gives `backend` `opencv` and null for every other source key."""
    source = product(SOURCE_MODULE)
    factory = OpenCVFakeFactory(monkeypatch)
    app = CaptureApp(monkeypatch, factory)
    try:
        ready_app_steps(app)
        camera_id = factory.camera_ids[0]
        app.wait(lambda: app.group.diagnostics(camera_id), "the first dict")
        full = app.group.diagnostics(camera_id)
        assert full["backend"] == "opencv"
        assert all(full[key] is None for key in source.SOURCE_KEYS if key != "backend"), \
            {key: full[key] for key in source.SOURCE_KEYS if full[key] is not None}
    finally:
        app.close()


def final_dict(app, camera_id, stop):
    """Stop the camera (a stall): it is `dead`, and its last dict holds the counts of each frame it took."""
    stop()
    app.wait_state(camera_id, "dead")
    app.wait(lambda: app.group.diagnostics(camera_id).get("fail_code") == "stalled", "the dict of the failure")
    return app.group.diagnostics(camera_id)


def test_t_unx_71_counters_of_mjpg_passthrough_and_of_a_bgr_ring(monkeypatch):
    """T-UNX-71: MJPG passthrough with the fake source: `encoded_by_skellycam` 0. With a BGR ring:
    `decoded_by_skellycam` is the count of the decodes of the decode stage."""
    for bgr_ring in (False, True):
        with capture_app(monkeypatch, [FakeScript()]) as app:
            spies = Spies(monkeypatch, app)
            camera_id = app.factory.camera_ids[0]
            ready_app_steps(app, [app.config(camera_id, bgr_ring=bgr_ring)])
            app.wait(lambda: len(spies.of("jpeg")) > 60, "frames in the ring")
            full = final_dict(app, camera_id, app.factory.sources[camera_id].stop_now)
            assert full["encoded_by_skellycam"] == 0
            assert full["decoded_by_skellycam"] == (len(spies.of("imdecode")) if bgr_ring else 0)
            if bgr_ring:
                assert full["decoded_by_skellycam"] > 0


def test_t_unx_71_counters_of_the_opencv_source(monkeypatch):
    """T-UNX-71: the OpenCV fake (BGR frames): `encoded_by_skellycam` is the frame count of the ring."""
    factory = OpenCVFakeFactory(monkeypatch)
    app = CaptureApp(monkeypatch, factory)
    try:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = factory.camera_ids[0]
        app.wait(lambda: len(spies.of("jpeg")) > 60, "frames in the ring")
        full = final_dict(app, camera_id, factory.captures[camera_id].stop)
        assert full["encoded_by_skellycam"] == len(spies.of("jpeg", camera_id)) > 60
        assert full["decoded_by_skellycam"] == 0
    finally:
        app.close()


def sha256(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def hash_set(full):
    return [(full[f"sha256_frame_{i:02d}"], full[f"sha256_{i:02d}"]) for i in range(30)]


def test_t_unx_72_frame_hashes(monkeypatch, tmp_path):
    """T-UNX-72: two cameras reach `ready`; one sends no DHT. 30 hashes after the first `ready`, each with its
    `source_frame_number`, each the SHA-256 of the ring slot of that frame; no warm-up frame is hashed; a live
    change that ends in `ready` again does not replace them; a record start gives a new set, each hash the
    SHA-256 of the ring slot and of the MKV block of that frame; `dht_inserted` counts the camera with no DHT."""
    with capture_app(monkeypatch, [FakeScript(), FakeScript(no_dht=True)]) as app:
        spies = Spies(monkeypatch, app, keep_payloads=True)
        ready_app_steps(app)
        with_dht, no_dht = app.factory.camera_ids
        for camera_id in (with_dht, no_dht):
            app.wait(lambda: diagnostics_of(app, camera_id).get("sha256_29"), f"30 hashes of {camera_id}")
        ring = {camera_id: {e["sfn"]: e for e in spies.of("jpeg", camera_id)} for camera_id in (with_dht, no_dht)}
        first = {}
        for camera_id in (with_dht, no_dht):
            full = diagnostics_of(app, camera_id)
            first[camera_id] = hash_set(full)
            assert full["sha256_trigger"] == "ready"
            sfns = [sfn for sfn, _ in first[camera_id]]
            assert sfns == sorted(sfns) and len(set(sfns)) == 30
            assert min(sfns) >= min(ring[camera_id]), "a warm-up frame was hashed"
            for sfn, digest in first[camera_id]:
                assert digest == sha256(ring[camera_id][sfn]["payload"]), sfn
            assert full["dqt_distinct"] == 1 and full["dqt_sha256"]
        assert diagnostics_of(app, with_dht)["dht_present"] is True
        assert diagnostics_of(app, with_dht)["dht_inserted"] == 0
        assert diagnostics_of(app, no_dht)["dht_present"] is False
        assert diagnostics_of(app, no_dht)["dht_inserted"] > 0

        response = app.apply([app.config(with_dht, exposure=-6), app.config(no_dht)])  # a live change
        assert response.status_code == 200, response.text
        app.wait_state(with_dht, "ready")
        app.wait_clock(2.0, "dicts after the live change")
        assert hash_set(diagnostics_of(app, with_dht)) == first[with_dht], "a live change armed the set"

        assert app.record_start(tmp_path).status_code == 200
        for camera_id in (with_dht, no_dht):
            app.wait(lambda: diagnostics_of(app, camera_id).get("sha256_trigger") == "recording"
                     and diagnostics_of(app, camera_id).get("sha256_29"), f"the record set of {camera_id}")
        app.wait_clock(1.0, "frames after the set")
        assert app.record_stop().status_code == 200
        for camera_id in (with_dht, no_dht):
            record_set = hash_set(diagnostics_of(app, camera_id))
            assert record_set != first[camera_id]
            ring_now = {e["sfn"]: e for e in spies.of("jpeg", camera_id)}
            recorded = {e["sfn"]: e for e in spies.of("record", camera_id)}
            blocks = {sha256(payload) for payload in block_payloads(tmp_path, camera_id)}
            for sfn, digest in record_set:
                assert digest == sha256(ring_now[sfn]["payload"]) == sha256(recorded[sfn]["payload"]), sfn
                assert digest in blocks, sfn


@pytest.mark.capture_timing
def test_f4_the_close_dict_reaches_the_main_process(monkeypatch):
    """F4 (the experiment `close_dict_lost.py`): with real camera processes, the dict that each camera sends at
    its close reaches the main process: after the close of the group, `CameraGroupManager.diagnostics()` holds
    `restore_ok`, `restore_failed` and `t_close_ms` of each camera."""
    scripts = [FakeScript(controls=(("exposure", True, True, -6),)), FakeScript(controls=(("exposure", True, True, -6),))]
    with capture_app(monkeypatch, scripts, workers="process") as app:
        ready_app_steps(app)
        assert app.client.delete("/skellycam/camera/group/close/all").status_code == 200
        found = app.manager.diagnostics()
    assert set(found) == set(app.factory.camera_ids)
    for camera_id, data in found.items():
        assert (data["restore_ok"], data["restore_failed"]) == (True, 0), (camera_id, data["restore_ok"])
        assert isinstance(data["t_close_ms"], float), (camera_id, data["t_close_ms"])


def test_f10_a_failure_of_the_main_process_sets_fail_code(monkeypatch):
    """F10: a camera process that ends with no final state (`_mark_ended`): the dict that the main process keeps
    and the counter subset of the status get `fail_code` `process-ended`."""
    with capture_app(monkeypatch, [FakeScript(exit_at="frame:300"), FakeScript()], workers="process") as app:
        ready_app_steps(app)
        ended = app.factory.camera_ids[0]
        app.wait_state(ended, "dead", timeout=30)
        app.wait(lambda: app.group.diagnostics(ended).get("fail_code") == "process-ended", "the fail code")
        assert app.status(ended)["diagnostics"]["fail_code"] == "process-ended"


def test_f10_a_restart_clears_the_counters_and_a_reopen_the_hashes(monkeypatch):
    """F10: "apply again" (`reset_for_start`) clears the counter subset of the status; a reopen clears the D-11
    hashes of the earlier open until its own first `ready`."""
    from skellycam.core.camera_group.camera_status import CameraStatus

    status = CameraStatus()
    status.diagnostics = {"frames": 3}
    status.reset_for_start()
    assert status.diagnostics == {}
    modes = ((640, 480, 30, 1, "MJPG"), (1280, 720, 30, 1, "MJPG"))
    with capture_app(monkeypatch, [FakeScript(modes=modes)]) as app:
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.wait(lambda: diagnostics_of(app, camera_id).get("sha256_29"), "30 hashes")
        loop_module = product("skellycam.core.camera.capture.camera_loop")
        seen = []
        start_up = loop_module.CameraLoop._start_up

        def spy(loop):
            result = start_up(loop)
            seen.append((loop.hash_trigger, list(loop.hashes)))  # at the end of the open, before `ready`
            return result
        monkeypatch.setattr(loop_module.CameraLoop, "_start_up", spy)
        assert app.apply([app.config(camera_id, width=1280, height=720)]).status_code == 200
        app.wait_state(camera_id, "ready")
    assert seen == [(None, [])], seen
