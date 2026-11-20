"""Hardware tests of step 3a: T-CAP-51 to T-CAP-60 and T-CAP-88 (specs/windows-capture.md, 16.1 to 16.4).

Each test has the marker `camera_hardware` and runs only with `SKELLYCAM_HARDWARE=1`, on the word of
the user. Lights on, unless a test says else. Two tests need a person: T-CAP-55 needs a dark room
(`SKELLYCAM_HARDWARE_DARK=1`), and T-CAP-58 needs an unplug (`SKELLYCAM_HARDWARE_UNPLUG=1`).
T-CAP-54, T-CAP-55 and T-CAP-59 record results; they have no pass value (16.3).
"""

import os
import subprocess
import sys
import textwrap
import time

import pytest

from skellycam.tests.capture.capture_hardware import (
    GOOD, LABELS, SLOW_REASON, hardware_app, kiyo_pro_rule, label_of, mode_list_follows_7_3, record_result)
from skellycam.tests.capture.capture_session import (
    RingWatcher, Spies, StateWatcher, capture_logs, digest, placeholders_to_the_stop, product, sfn_gaps,
    stop_line_count, take_rows)
from skellycam.tests.capture.fake_source import MEDIA_FOUNDATION_VIDEO_GUID, spec_camera_id

pytestmark = [pytest.mark.camera_hardware,
              pytest.mark.skipif(sys.platform != "win32", reason="the step 3a cameras run on Windows")]

PREDICTED_57 = {"C922": {-7: "ready", -6: "ready", -5: "ready", -4: "too_slow"},
                "C930e": {-7: "ready", -6: "ready", -5: "ready", -4: "too_slow"},
                "Kiyo Pro": {-7: "ready", -6: None, -5: "too_slow", -4: "too_slow"}}  # 10.5; None: recorded only


def instance_part(path):
    """The device instance part of a device path: the part before the interface class GUID (14.2, U1)."""
    return path.lower().split("#{")[0]


def open_alone(app, label, test_id, **config):
    camera_id = app.camera_id(label)
    response = app.apply([app.config(camera_id, **config)])
    assert response.status_code == 200, response.text
    app.wait_state(camera_id, "ready", "failed", "dead")
    return camera_id, app.status(camera_id)


def test_t_cap_51_detection_with_four_cameras(monkeypatch):
    """T-CAP-51, sections 7.1 to 7.3 [D11, D14]: detect with four cameras connected; then detect again
    while two of them stream. Four cameras with new IDs and the `supported_modes` of 7.3; the
    streaming cameras show no arrival gap above 100 ms."""
    with hardware_app(monkeypatch) as app:
        cameras = list(app.devices.values())
        assert sorted(app.devices) == sorted(LABELS), f"connected: {[c['name'] for c in cameras]}"
        for camera in cameras:
            assert MEDIA_FOUNDATION_VIDEO_GUID in camera["path"].lower(), "not a Media Foundation link"
            assert camera["camera_id"] == spec_camera_id(camera["path"])
            mode_list_follows_7_3(camera["supported_modes"])
        streaming = [app.camera_id("C922"), app.camera_id("C930e")]
        assert app.apply([app.config(cid) for cid in streaming]).status_code == 200
        for camera_id in streaming:
            app.wait_state(camera_id, "ready")
        watchers = [RingWatcher(app.ring_name(cid)) for cid in streaming]
        try:
            time.sleep(1.0)
            t0 = time.perf_counter_ns()
            again = app.detect()
            t1 = time.perf_counter_ns()
            time.sleep(1.0)
        finally:
            for watcher in watchers:
                watcher.stop()
        gaps = {label: w.largest_gap_s(t0 - 10**8, t1 + 10**8) for label, w in zip(("C922", "C930e"), watchers)}
        record_result("T-CAP-51", detection_s=(t1 - t0) / 1e9, gaps_s=gaps, cameras=[c["name"] for c in again])
        # The four test cameras, by the labels of the harness (USB IDs first); a software camera (for
        # example NDI) is virtual or has no label (first hardware run of 3a).
        tested = sorted(label_of(c) for c in again if not c.get("virtual") and label_of(c))
        assert tested == sorted(LABELS), f"detected again: {[c['name'] for c in again]}"
        assert all(gap <= 0.1 for gap in gaps.values()), gaps


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_52_native_jpeg_untouched(monkeypatch, label):
    """T-CAP-52, sections 4.2, 5.1 and 6 [D2, D12, D48]: open the C922, the C930e and the Kiyo Pro at
    1280x720 MJPG 30 through Media Foundation, one at a time. Each reaches `ready`; for 300 frames the
    ring payload is byte-equal to the bytes that the callback copied; the rate check passes.

    A THREAD worker, so that a spy on `CaptureWaitingPlace.put` sees the bytes of the callback."""
    source_module = product("skellycam.core.camera.capture.source")
    copied = {}
    original_put = source_module.CaptureWaitingPlace.put

    def spy_put(place, frame):
        copied[frame.source_frame_number] = digest(frame.payload)
        return original_put(place, frame)

    monkeypatch.setattr(source_module.CaptureWaitingPlace, "put", spy_put)
    with hardware_app(monkeypatch, workers="thread") as app:
        with kiyo_pro_rule(app, label, "T-CAP-52"):
            spies = Spies(monkeypatch, app)
            camera_id, status = open_alone(app, label, "T-CAP-52")
            assert status["state"] == "ready", status
            assert abs(status["measured_fps"] - 30.0) <= 0.9
            app.wait(lambda: len(spies.of("jpeg", camera_id)) >= 300, "300 ring frames")
            writes = spies.of("jpeg", camera_id)[:300]
            assert all(copied.get(e["sfn"]) == e["hash"] for e in writes), "a ring payload is not the camera JPEG"
            record_result("T-CAP-52", camera=label, measured_fps=status["measured_fps"])


def test_t_cap_53_generic_camera_fails_the_rate_check(monkeypatch):
    """T-CAP-53, section 10.1 [D24, D25]: open the generic camera at 1280x720 MJPG 30. `failed`, stage
    `rate check`, the reason of 10.4 with a measured rate near 25.76 ("near": within 0.5 fps)."""
    with hardware_app(monkeypatch) as app:
        camera_id, status = open_alone(app, "generic", "T-CAP-53")
        record_result("T-CAP-53", status=status)
        assert status["state"] == "failed" and status["failure"]["stage"] == "rate check", status
        match = SLOW_REASON.match(status["failure"]["reason"])
        assert match and match.group(1) == "30.00" and abs(float(match.group(2)) - 25.76) <= 0.5


RATES_54 = [(label, 30.0) for label in LABELS] + [("C922", 60.0), ("Kiyo Pro", 60.0)]


@pytest.mark.parametrize(("label", "rate"), RATES_54, ids=[f"{l} {r:g}" for l, r in RATES_54])
def test_t_cap_54_each_offered_mjpg_rate_at_720p(monkeypatch, label, rate):
    """T-CAP-54, sections 10.1 and 16.3 [D49, U11]: each camera at each offered MJPG rate at 1280x720: 30
    on each camera, 60 on the C922 and the Kiyo Pro. For each rate: the measured rate and the check
    result are recorded; a camera that fails gives the reason of 10.4. No pass value."""
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-54"):
            camera_id, status = open_alone(app, label, "T-CAP-54", framerate=rate)
            record_result("T-CAP-54", camera=label, rate=rate, state=status["state"],
                          measured_fps=status.get("measured_fps"), failure=status.get("failure"))
            if status["failure"] and status["failure"]["stage"] == "rate check":
                assert SLOW_REASON.match(status["failure"]["reason"]), status["failure"]


@pytest.mark.skipif(os.environ.get("SKELLYCAM_HARDWARE_DARK") != "1", reason="needs a dark room: SKELLYCAM_HARDWARE_DARK=1")
@pytest.mark.parametrize("label", LABELS)
def test_t_cap_55_dark_room_with_auto_exposure(monkeypatch, label):
    """T-CAP-55, section 16.3 [D49]: each camera opened in a dark room with auto exposure. For each
    camera: state, measured rate and reason are recorded; no traceback. A THREAD worker, so that the
    log records of the camera are in this process."""
    with capture_logs() as logs, hardware_app(monkeypatch, workers="thread") as app:
        with kiyo_pro_rule(app, label, "T-CAP-55"):
            camera_id, status = open_alone(app, label, "T-CAP-55", exposure_mode="AUTO")
            record_result("T-CAP-55", camera=label, state=status["state"], measured_fps=status.get("measured_fps"),
                          failure=status.get("failure"))
    assert not logs.tracebacks(), logs.tracebacks()


def test_t_cap_56_camera_in_use_by_another_program(monkeypatch):
    """T-CAP-56, section 6.7 [D13]: another program holds the C930e; apply a group with it and the C922.
    The C930e is `failed` with "in use by another program"; the C922 is `ready`.

    The other program is a Python process that holds the C930e through OpenCV DirectShow."""
    from cv2_enumerate_cameras import enumerate_cameras
    import cv2

    held = [c for c in enumerate_cameras(cv2.CAP_DSHOW) if "c930e" in c.name.lower()]
    assert held, "the C930e has no DirectShow device"
    script = textwrap.dedent(f"""
        import cv2, sys, time
        capture = cv2.VideoCapture({held[0].index}, cv2.CAP_DSHOW)
        ok = capture.isOpened() and capture.read()[0]
        print("holding" if ok else "failed", flush=True)
        while ok:
            capture.read()
    """)
    holder = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "holding"
        with hardware_app(monkeypatch) as app:
            c930e, c922 = app.camera_id("C930e"), app.camera_id("C922")
            assert app.apply([app.config(c930e), app.config(c922)]).status_code == 200
            app.wait_state(c930e, "failed")
            app.wait_state(c922, "ready")
            assert app.status(c930e)["failure"]["reason"] == "in use by another program"
    finally:
        holder.kill()
        holder.wait(10)


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_57_exposure_steps_while_open(monkeypatch, label):
    """T-CAP-57, sections 10.2 and 10.5 [D32]: exposure steps -7, -6, -5, -4 on each camera while open.
    Each change gives `checking`, then `ready` or `too_slow` as table 10.5 predicts; the Kiyo Pro at
    -6 is recorded. The camera opens at -8, so that -7 is a change."""
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-57"):
            camera_id, status = open_alone(app, label, "T-CAP-57", exposure=-8)
            assert status["state"] == "ready", status
            for exposure, predicted in PREDICTED_57[label].items():
                watcher = StateWatcher(app, camera_id)
                try:
                    assert app.apply([app.config(camera_id, exposure=exposure)]).status_code == 200
                    app.wait(lambda: "checking" in watcher.first, f"checking at {exposure}")
                    app.wait(lambda: app.state(camera_id) in ("ready", "too_slow"), f"the check at {exposure}")
                finally:
                    watcher.stop()
                status = app.status(camera_id)
                record_result("T-CAP-57", camera=label, exposure=exposure, state=status["state"],
                              measured_fps=status["measured_fps"])
                if predicted is not None:
                    assert status["state"] == predicted, f"{label} at {exposure}: {status['state']}"


@pytest.mark.skipif(os.environ.get("SKELLYCAM_HARDWARE_UNPLUG") != "1", reason="needs a person to unplug: SKELLYCAM_HARDWARE_UNPLUG=1")
def test_t_cap_58_unplug_during_a_recording(monkeypatch, tmp_path):
    """T-CAP-58, sections 5.7 and 8.2 [D38, U4]: record with the C922 and the C930e; the user unplugs
    the C922 at 20 s. The C922 is `dead` at once; the C930e records to the stop; changed by step 5a
    (recorder.md section 14): the manifest has `camera_dead` for the C922, and its file has placeholders
    to the stop [M1, M8]. "At once": within 0.5 s of its last ring frame."""
    with hardware_app(monkeypatch) as app:
        c922, c930e = app.camera_id("C922"), app.camera_id("C930e")
        assert app.apply([app.config(c922), app.config(c930e)]).status_code == 200
        for camera_id in (c922, c930e):
            app.wait_state(camera_id, "ready")
        ring = RingWatcher(app.ring_name(c922))
        watcher = StateWatcher(app, c922)
        try:
            assert app.record_start(tmp_path).status_code == 200
            print("\nT-CAP-58: unplug the C922 in 20 s", flush=True)
            app.wait(lambda: "dead" in watcher.first, "the C922 is unplugged", timeout=120)
            last_arrival = ring.frames[-1][1]
            assert (watcher.first["dead"] - last_arrival) / 1e9 <= 0.5
            time.sleep(10)
            assert app.state(c930e) == "recording"
            assert app.record_stop().status_code == 200
        finally:
            watcher.stop()
            ring.stop()
        dead, rows = placeholders_to_the_stop(tmp_path, c922)
        record_result("T-CAP-58", dead=dead, rows=len(rows))


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_59_sample_time_against_arrival_time(monkeypatch, label):
    """T-CAP-59, sections 4.2 and 5.4 [D28, agent 10]: compare `sample_ns` and `arrival_ns` for 300 frames
    per camera. The difference is recorded per camera; the source applies the `NO_SAMPLE_NS` rule of
    4.2 as the recorded values require."""
    no_sample = product("skellycam.core.ipc.frame_ring").NO_SAMPLE_NS
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-59"):
            camera_id, status = open_alone(app, label, "T-CAP-59")
            assert status["state"] == "ready", status
            ring = RingWatcher(app.ring_name(camera_id))
            try:
                app.wait(lambda: len(ring.frames) >= 300, "300 ring frames")
            finally:
                ring.stop()
    frames = ring.frames[:300]
    differences = [(arrival - sample) / 1e6 for _, arrival, _, sample in frames if sample != no_sample]
    record_result("T-CAP-59", camera=label, frames=len(frames), with_sample_time=len(differences),
                  arrival_minus_sample_ms=dict(min=min(differences, default=None), max=max(differences, default=None),
                                               median=sorted(differences)[len(differences) // 2] if differences else None))
    marked = [k for k, f in enumerate(frames) if f[3] == no_sample]
    if marked:
        assert all(f[3] == no_sample for f in frames[marked[0]:]), "NO_SAMPLE_NS must stay for the rest of the open"
    assert all(0 <= d <= 200 for d in differences), "a sample time after the arrival or 200 ms before it was kept"


def test_t_cap_60_comparison_run_native_loop(monkeypatch, tmp_path):
    """T-CAP-60, section 16.4 [D48, U3, agent 40]: the comparison run of 16.4, native run: the C922, the
    C930e and the Kiyo Pro at 1280x720 MJPG 30 fps, lockstep, one recording of 60 s. Equal frame counts
    across cameras; a group rate from 29.7 to 30.3; for each camera, the gaps of `source_frame_number`
    equal the increase of its `replaced_count`, both from the first frame in the gate. The OpenCV
    reference run is a separate run in a second worktree (16.4). A THREAD worker for the spies."""
    with capture_logs() as logs, hardware_app(monkeypatch, workers="thread") as app:
        spies = Spies(monkeypatch, app)
        ids = [app.camera_id(label) for label in GOOD]
        assert app.apply([app.config(cid) for cid in ids]).status_code == 200
        for camera_id in ids:
            app.wait_state(camera_id, "ready")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(60.0)
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        app.client.delete("/skellycam/camera/group/close/all")
        summary = stopped.json()[0]
        counts = {cid: len(take_rows(tmp_path, cid)) for cid in ids}
        replaced = {cid: (stop_line_count(logs.messages(), cid), sfn_gaps([e["sfn"] for e in spies.of("jpeg", cid)]))
                    for cid in ids}
        record_result("T-CAP-60", counts=counts, summary=summary, replaced_and_gaps=replaced)
        assert len(set(counts.values())) == 1, counts
        assert 29.7 <= summary["mean_framerate"] <= 30.3, summary
        assert all(count == gaps for count, gaps in replaced.values()), replaced


@pytest.mark.parametrize("label", GOOD)
def test_t_cap_88_opencv_finds_the_device_of_the_link(monkeypatch, label):
    """T-CAP-88, section 14.2 [U1]: with `SKELLYCAM_WINDOWS_CAPTURE=opencv` in the new loop, open the
    C922, the C930e and the Kiyo Pro. Each opens the DirectShow device whose device instance part
    equals that of the Media Foundation link that detection named for its `camera_id`, and the
    friendly names agree. A THREAD worker, so that a spy sees the `OpenedMode` of the source."""
    from cv2_enumerate_cameras import enumerate_cameras
    import cv2

    opencv_source = product("skellycam.core.camera.capture.opencv_source")
    opened = []
    original_open = opencv_source.OpenCVSource.open

    def spy_open(source, request):
        mode = original_open(source, request)
        opened.append(mode)
        return mode

    monkeypatch.setattr(opencv_source.OpenCVSource, "open", spy_open)
    with hardware_app(monkeypatch, workers="thread", source="opencv") as app:
        with kiyo_pro_rule(app, label, "T-CAP-88"):
            link, name = app.devices[label]["path"], app.devices[label]["name"]
            camera_id, status = open_alone(app, label, "T-CAP-88")
            assert opened, "the OpenCV source did not open"
            directshow = {c.path.lower(): c.name for c in enumerate_cameras(cv2.CAP_DSHOW) if c.path}
            device_path = opened[-1].device_path
            record_result("T-CAP-88", camera=label, link=link, directshow_path=device_path)
            assert instance_part(device_path) == instance_part(link)
            assert directshow.get(device_path.lower()) == name
