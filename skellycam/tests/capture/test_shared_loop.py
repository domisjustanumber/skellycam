"""T-CAP-05 to T-CAP-12, T-CAP-39, T-CAP-41, T-CAP-44 and T-CAP-87: the shared camera loop
(specs/windows-capture.md, sections 5, 9, 11.1 and 14.1).

The fake-source tests run THREAD workers with a virtual clock. The spies of `capture_session`
see each JPEG ring write, each BGR hand-over, each frame of the old recorder and each
`cv2.imdecode` call. The OpenCV tests use the product `OpenCVSource` with the OpenCV fake, on a virtual clock.
"""

import logging

import pytest

from skellycam.tests.capture.capture_session import (
    OpenCVFakeFactory, CaptureApp, Spies, capture_app, capture_logs, column, digest, read_csv, ready_app_steps,
    sfn_gaps, stop_line_count)
from skellycam.tests.capture.fake_source import FakeScript

RETRIEVE_COLUMNS = ("frame.pre_frame_retrieve.ns", "frame.post_frame_retrieve.ns",
                    "duration.idle_before_retrieve.ns", "duration.during_frame_retrieve.ns")


def ring_flags():
    from skellycam.core.ipc.frame_ring import NO_SAMPLE_NS, FrameFlag

    return FrameFlag, NO_SAMPLE_NS


def timing_csv(directory, camera_id, name="take"):
    from skellycam.core.recorders.videos.recording_info import RecordingInfo

    return RecordingInfo(recording_name=name, recording_directory=str(directory)).camera_timestamps_file_path_from_camera_id(camera_id)


def record(app, spies, directory, frames=30, camera_id=None):
    """Record until the old recorder got `frames` frames, then stop."""
    response = app.record_start(directory)
    assert response.status_code == 200, response.text
    app.wait(lambda: len(spies.of("record", camera_id)) >= frames, f"{frames} recorded frames")
    response = app.record_stop()
    assert response.status_code == 200, response.text
    return response


# ---------------------------------------------------------------------------
# T-CAP-05, T-CAP-06: lockstep with a push source, frame numbers
# ---------------------------------------------------------------------------

def test_t_cap_05_replaced_count_matches_the_gaps(monkeypatch):
    """T-CAP-05, sections 5.2 and 5.3 [D26, D27, agent 49, agent 65]: three fake cameras in one group,
    each in a 30 fps mode. Equal ring frame counts; for each camera, the sum of the gaps of
    `source_frame_number` between taken frames, from the first frame taken in the gate, equals the
    increase of `replaced_count` from that frame; one log line per camera at stop with that count.

    The script (agent 65): the frames of each fake are on one 100 ms grid of the virtual clock. The
    third fake delivers 60 frames per second from 20 s to 30 s of the clock, while the two others hold
    the gate at 30 rounds per second, so about 300 of its frames are replaced. At 30 s it drops one
    frame and goes back to 30 fps. Each fake delivers its last frame at 40 s, so the gate ends on a
    whole round; the stall watch then ends each camera.

    The window ends at 29.995 s: the fake rounds each interval to whole ns, so a window end of 30.0 s
    can take one more 60 fps frame a few ns before 30.0 s and move the fast camera off the grid."""
    grid = dict(align_ms=100.0, stop_at_s=40.005)
    scripts = [FakeScript(**grid), FakeScript(**grid),
               FakeScript(rate_windows=((20.0, 29.995, 60.0),), drop_at_window_end=True, **grid)]
    with capture_logs() as logs, capture_app(monkeypatch, scripts) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        assert app.clock.now_ns() < app.clock.START_NS + 19 * 10**9, "the start-up took past 19 s of the clock"
        app.wait(lambda: all(app.state(cid) in ("dead", "failed") for cid in app.factory.camera_ids),
                 "each fake ran out of frames")
        app.client.delete("/skellycam/camera/group/close/all")
        last = {cid: max(app.factory.logs[cid].frames.values())[0] for cid in app.factory.camera_ids}
        assert max(last.values()) - min(last.values()) < 1_000_000, f"the last frames are not on one round: {last}"
        counts = {cid: len(spies.of("jpeg", cid)) for cid in app.factory.camera_ids}
        assert len(set(counts.values())) == 1, f"ring frame counts differ: {counts}"
        assert min(counts.values()) >= 600, f"less than 20 s of frames in the gate: {counts}"
        replaced = {}
        for camera_id in app.factory.camera_ids:
            sfns = [event["sfn"] for event in spies.of("jpeg", camera_id)]
            replaced[camera_id] = stop_line_count(logs.messages(), camera_id)
            assert replaced[camera_id] == sfn_gaps(sfns), camera_id
        assert replaced[app.factory.camera_ids[2]] >= 200, f"the fast camera lost too few frames: {replaced}"


def test_t_cap_06_frame_numbers_across_a_resolution_change(monkeypatch):
    """T-CAP-06, section 5.3 [D27, agent 5]: run, change the resolution, run again. Ring `frame_number`
    is 0, 1, 2, ... in each ring; `source_frame_number` is the source count; the gate count continues
    across the change."""
    script = FakeScript(modes=((640, 480, 30, 1, "MJPG"), (320, 240, 30, 1, "MJPG")))
    with capture_app(monkeypatch, [script]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.wait_clock(4.0)
        count_before = app.group.cameras.orchestrator.camera_statuses[camera_id].frame_count.value
        response = app.apply([app.config(camera_id, width=320, height=240)])
        assert response.status_code == 200, response.text
        app.wait_state(camera_id, "ready")
        status = app.group.cameras.orchestrator.camera_statuses[camera_id]
        app.wait_clock(2.0)
        app.client.delete("/skellycam/camera/group/close/all")
        writes = spies.of("jpeg", camera_id)
        rings = list(dict.fromkeys(event["ring"] for event in writes))
        assert len(rings) == 2, f"expected two rings, got {rings}"
        log = app.factory.logs[camera_id]
        assert len(log.history) == 2
        for ring, frames in zip(rings, log.history):
            in_ring = [event for event in writes if event["ring"] == ring]
            assert [event["frame_number"] for event in in_ring] == list(range(len(in_ring))), ring
            for event in in_ring:
                assert frames[event["sfn"]][0] == event["arrival_ns"], "sfn is not the source count of the open"
        second = [event for event in writes if event["ring"] == rings[1]]
        assert count_before >= 100
        assert status.frame_count.value >= count_before + len(second) - 1, (
            f"the gate count did not continue: {count_before} at the change, {status.frame_count.value} at the "
            f"end, {len(second)} frames after the change")


# ---------------------------------------------------------------------------
# T-CAP-07 to T-CAP-10: timestamps, order, interim decode, flagged frames
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sample_offset_ms", [-4.0, None], ids=["sample time", "no sample time"])
def test_t_cap_07_slot_and_csv_times(monkeypatch, tmp_path, sample_offset_ms):
    """T-CAP-07, section 5.4 [D28, agent 7]: a fake with scripted arrival and sample times; record 30
    frames. Slot `arrival_ns` and `sample_ns` equal the source values; the CSV time of each recorded
    frame is its `arrival_ns`; a source with no sample time writes `NO_SAMPLE_NS`."""
    _, no_sample = ring_flags()
    with capture_app(monkeypatch, [FakeScript(sample_offset_ms=sample_offset_ms)]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        record(app, spies, tmp_path)
        frames = app.factory.logs[camera_id].frames
        for event in spies.of("jpeg", camera_id):
            assert (event["arrival_ns"], event["sample_ns"]) == frames[event["sfn"]]
            if sample_offset_ms is None:
                assert event["sample_ns"] == no_sample
        times = [int(value) for value in column(timing_csv(tmp_path, camera_id), "timestamp.perf_counter_ns.ns")]
        arrivals = {arrival for arrival, _ in frames.values()}
        assert len(times) == len(spies.of("record", camera_id)) >= 30
        assert all(t in arrivals for t in times), "a CSV time is not the arrival time of a frame"
        assert times == sorted(set(times))


def test_t_cap_08_recorder_then_jpeg_ring_then_bgr(monkeypatch, tmp_path):
    """T-CAP-08, section 5.1 [ring 5.3, D6]: spy on the recorder, the JPEG ring write and the BGR
    hand-over. For each frame: recorder, then JPEG ring, then BGR; a ring write that raises leaves the
    recorder and the next frame unaffected.

    The spies match the events of one frame by `arrival_ns` (one camera)."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        failed = []

        def fail_once(event):
            if not failed and spies.of("record"):
                failed.append(event["arrival_ns"])
                return True
            return False

        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, bgr_ring=True)])
        spies.fail_jpeg_write = fail_once
        record(app, spies, tmp_path, frames=60)
        assert failed, "no ring write was made to fail"
        recorded = [event["arrival_ns"] for event in spies.of("record")]
        assert failed[0] in recorded, "the recorder did not get the frame whose ring write raised"
        next_arrival = recorded[recorded.index(failed[0]) + 1]
        for arrival in recorded[:-1]:
            kinds = [e["kind"] for e in spies.events if e.get("arrival_ns") == arrival
                     and e["kind"] in ("record", "jpeg", "bgr_put")]
            if arrival == failed[0]:
                assert kinds[:2] == ["record", "jpeg"], kinds
            else:
                assert kinds == ["record", "jpeg", "bgr_put"], f"frame at {arrival}: {kinds}"
        assert any(e["arrival_ns"] == next_arrival and not e.get("raised") for e in spies.of("jpeg")), \
            "the next frame did not reach the ring"


@pytest.mark.parametrize("recording", [False, True], ids=["no recording", "recording"])
@pytest.mark.parametrize("bgr_ring", [False, True], ids=["no BGR ring", "BGR ring"])
def test_t_cap_09_one_decode_per_frame_only_when_needed(monkeypatch, tmp_path, recording, bgr_ring):
    """T-CAP-09, section 5.5 [D9, agent 8]: MJPG fake, with and without recording, with and without a
    BGR ring; count `cv2.imdecode` calls. One decode per recorded frame or per frame with a BGR ring,
    else none; the BGR ring frame equals the decoded image."""
    with capture_app(monkeypatch, [FakeScript(modes=((320, 240, 30, 1, "MJPG"),))]) as app:
        spies = Spies(monkeypatch, app, keep_payloads=True)
        camera_id = app.factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, bgr_ring=bgr_ring)])
        if recording:
            record(app, spies, tmp_path, frames=60)
        else:
            app.wait(lambda: len(spies.of("jpeg")) >= 60, "60 ring frames")
        app.client.delete("/skellycam/camera/group/close/all")
        decodes = {}
        for event in spies.of("imdecode"):
            decodes[event["hash"]] = decodes.get(event["hash"], 0) + 1
        recorded = {event["arrival_ns"] for event in spies.of("record")}
        bgr_by_arrival = {event["arrival_ns"]: event for event in spies.of("bgr_put")}
        for event in spies.of("jpeg"):
            expected = 1 if (bgr_ring or event["arrival_ns"] in recorded) else 0
            assert decodes.get(event["hash"], 0) == expected, f"frame {event['sfn']}: {decodes.get(event['hash'], 0)} decodes"
            if bgr_ring and event["arrival_ns"] in bgr_by_arrival:
                assert bgr_by_arrival[event["arrival_ns"]]["hash"] == digest(spies.decode_image(event["payload"]))
        assert not bgr_ring or bgr_by_arrival, "no BGR hand-over"


def test_t_cap_10_cut_off_jpeg_during_a_recording(monkeypatch, tmp_path):
    """T-CAP-10, sections 5.5 and 4 [ring 4, U5]: the fake delivers a cut-off JPEG during a recording.
    The slot is flagged `NO_SOI_EOI`; the decoder call count is 0 for it; the recorder gets the
    previous image; the count is logged at stop.

    The stop line holds the camera ID, the word "flagged" and the count (ADR-HP7D)."""
    import re

    flag, _ = ring_flags()
    with capture_logs() as logs, capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        response = app.record_start(tmp_path)
        assert response.status_code == 200, response.text
        app.wait(lambda: len(spies.of("record")) >= 10, "10 recorded frames")
        source = app.factory.sources[camera_id]
        source.cut_off_next()
        app.wait(lambda: source.cut_frames, "the cut-off frame")
        app.wait(lambda: len(spies.of("record")) >= 40, "40 recorded frames")
        assert app.record_stop().status_code == 200
        cut_sfn = source.cut_frames[0]
        writes = [e for e in spies.of("jpeg") if e["sfn"] == cut_sfn]
        assert len(writes) == 1 and writes[0]["flags"] & flag.NO_SOI_EOI
        assert not [e for e in spies.of("imdecode") if e["hash"] == writes[0]["hash"]], "the cut-off JPEG was decoded"
        records = spies.of("record")
        index = [e["arrival_ns"] for e in records].index(writes[0]["arrival_ns"])
        assert records[index]["hash"] == records[index - 1]["hash"], "the recorder did not get the previous image"
        pattern = re.compile(rf"\b{camera_id}\b.*flagged.*\b1\b|\b{camera_id}\b.*\b1\b.*flagged", re.IGNORECASE)
        assert any(pattern.search(message) for message in logs.messages(logging.INFO)), "no count line at the stop"


# ---------------------------------------------------------------------------
# T-CAP-11, T-CAP-12: discontinuity; start-up order
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["camera drop", "replaced in the waiting place"])
def test_t_cap_11_discontinuity_reaches_the_next_taken_frame(monkeypatch, case):
    """T-CAP-11, sections 4.2, 4.3 and 5.1 [D34, agent 46]: (1) the fake drops a frame on the camera
    side: the next delivered sample has the discontinuity attribute. (2) A sample with the attribute
    is replaced in the waiting place before the loop takes it. In both cases the next taken frame has
    `DISCONTINUITY`; in case 1, `source_frame_number` has no gap; no warning is logged.

    "No warning": no log record at WARNING or above names the camera, up to frame 200. After frame 200
    the fake stops, and the camera is `dead` with a warning (section 12, ADR-PDD3)."""
    flag, _ = ring_flags()
    if case == "camera drop":
        script, marked = FakeScript(drop_before_frames=(150,), stop_after_frame=200), 150
    else:
        script, marked = FakeScript(discontinuity_frames=(160,), burst=(160, 161), stop_after_frame=200), 161
    with capture_logs() as logs, capture_app(monkeypatch, [script]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        app.wait(lambda: any(e["sfn"] >= 200 for e in spies.of("jpeg")), "frame 200 in the ring")
        writes = {e["sfn"]: e for e in spies.of("jpeg")}
        flagged = [sfn for sfn, e in writes.items() if e["flags"] & flag.DISCONTINUITY]
        assert flagged == [marked], f"DISCONTINUITY on {flagged}, expected only on {marked}"
        if case == "camera drop":
            assert 149 in writes and 150 in writes, "a camera drop leaves no gap in source_frame_number"
        else:
            assert 160 not in writes
        warnings = [m for m in logs.messages(logging.WARNING) if camera_id in m and "no frame for 2 s" not in m]
        assert not warnings, warnings


def test_t_cap_12_controls_after_the_first_frame_and_read_back(monkeypatch):
    """T-CAP-12, section 9.1 [D20, agent 44]: a fake with an exposure that resets to -5 when the stream
    starts; config `MANUAL -7`. Call order: open with first frame, set controls, read back, warm-up;
    the config holds the read-back value -7."""
    script = FakeScript(reset_on_stream=(("exposure", -5),))
    with capture_app(monkeypatch, [script]) as app:
        response = ready_app_steps(app)
        camera_id = app.factory.camera_ids[0]
        log = app.factory.logs[camera_id]
        names = log.names()
        first_set = next(i for i, (name, _, detail) in enumerate(log.events)
                         if name == "set_controls" and "exposure" in detail)
        assert names.index("open") < names.index("first_frame") < first_set
        setting = log.events[first_set][2]["exposure"]
        assert (setting.auto, setting.value) == (False, -7)
        assert log.first_sfn_after_readback == 1, "a frame after frame 0 was taken before the controls were set"
        config = response.json()["camera_configs"][camera_id]
        assert (config["exposure_mode"], config["exposure"]) == ("MANUAL", -7)
        assert app.status(camera_id)["controls"]["exposure"] == {"present": True, "auto": False, "value": -7}


# ---------------------------------------------------------------------------
# T-CAP-39: timestamp columns and the camera ID check of the recorder
# ---------------------------------------------------------------------------

def test_t_cap_39_stamped_columns_and_wrong_camera_id(monkeypatch, tmp_path):
    """T-CAP-39, section 5.4 [D41]: record with the fake source and with the OpenCV fake; give the
    recorder a frame with a wrong camera ID. Native CSV has no retrieve columns; OpenCV CSV has them;
    the wrong frame is refused with an error (`ValueError`, ADR-HP7D)."""
    with capture_app(monkeypatch, [FakeScript()]) as app:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        record(app, spies, tmp_path / "native")
        header, _ = read_csv(timing_csv(tmp_path / "native", app.factory.camera_ids[0]))
        assert not set(RETRIEVE_COLUMNS) & set(header), "the native CSV has retrieve columns"
    with pytest.MonkeyPatch.context() as patch:
        factory = OpenCVFakeFactory(patch)
        app = CaptureApp(patch, factory)
        try:
            spies = Spies(patch, app)
            ready_app_steps(app)
            record(app, spies, tmp_path / "opencv")
            header, _ = read_csv(timing_csv(tmp_path / "opencv", factory.camera_ids[0]))
            assert set(RETRIEVE_COLUMNS) <= set(header), "the OpenCV CSV has no retrieve columns"
        finally:
            app.close()
    _wrong_camera_id_is_refused(tmp_path / "wrong")


def _wrong_camera_id_is_refused(directory):
    import multiprocessing
    import time

    from skellycam.core.camera.config.camera_config import CameraConfig
    from skellycam.core.camera.config.image_resolution import ImageResolution
    from skellycam.core.camera.opencv.opencv_helpers.create_initial_frame_recarray import create_initial_frame_rec_array
    from skellycam.core.camera_group.camera_group_ipc import CameraGroupIPC
    from skellycam.core.ipc.pubsub.pubsub_manager import PubSubTopicManager
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from skellycam.core.recorders.videos.video_recorder import VideoRecorder

    ipc = CameraGroupIPC(group_id="t-cap-39", pubsub=PubSubTopicManager(topics={}),
                         extracted_config_subscription=multiprocessing.Queue(),
                         recording_finished_subscription=multiprocessing.Queue(),
                         global_kill_flag=multiprocessing.Value("b", False),
                         heartbeat_timestamp=multiprocessing.Value("d", time.perf_counter()))
    resolution = ImageResolution(width=320, height=240)
    mine = CameraConfig(camera_id="a1b2", camera_index=0, resolution=resolution)
    other = CameraConfig(camera_id="c3d4", camera_index=1, resolution=resolution)
    directory.mkdir(parents=True, exist_ok=True)
    recorder = VideoRecorder.create(recording_info=RecordingInfo(recording_name="wrong", recording_directory=str(directory)),
                                    config=mine)
    try:
        frame = create_initial_frame_rec_array(config=other, ipc=ipc)
        frame.frame_metadata.frame_number[0] = 0
        with pytest.raises(ValueError) as error:
            recorder.record_frame(frame)
        assert "c3d4" in str(error.value) and "a1b2" in str(error.value)
    finally:
        recorder.close()


# ---------------------------------------------------------------------------
# T-CAP-41: exposure modes
# ---------------------------------------------------------------------------

BRIGHTNESS = ((-12, 2), (-11, 4), (-10, 8), (-9, 16), (-8, 32), (-7, 64), (-6, 128), (-5, 200), (-4, 255))


@pytest.mark.parametrize("mode", ["MANUAL", "AUTO", "RECOMMEND"])
def test_t_cap_41_exposure_modes(monkeypatch, mode):
    """T-CAP-41, sections 11.1 and 9.1 [D29, D35, agent 29]: `MANUAL -7`, `AUTO`, `RECOMMEND` with a
    brightness model in the fake. The fake gets the values in log2 seconds; `RECOMMEND` ends in
    `MANUAL` with the value nearest to 127.5 (-6 in this model)."""
    with capture_app(monkeypatch, [FakeScript(brightness=BRIGHTNESS)]) as app:
        camera_id = app.factory.camera_ids[0]
        response = ready_app_steps(app, [app.config(camera_id, exposure_mode=mode, exposure=-7)])
        settings = [s["exposure"] for s in app.factory.logs[camera_id].settings if "exposure" in s]
        assert settings, "the fake got no exposure setting"
        values = [s.value for s in settings if s.value is not None]
        assert all(isinstance(v, int) and -13 <= v <= -1 for v in values), f"not log2 seconds: {values}"
        config = response.json()["camera_configs"][camera_id]
        if mode == "MANUAL":
            assert (settings[0].auto, settings[0].value) == (False, -7)
            assert (config["exposure_mode"], config["exposure"]) == ("MANUAL", -7)
        elif mode == "AUTO":
            assert settings[0].auto is True
            assert config["exposure_mode"] == "AUTO"
        else:
            assert set(range(-12, -3)) <= set(values), f"the search did not try -12 to -4: {sorted(set(values))}"
            assert (config["exposure_mode"], config["exposure"]) == ("MANUAL", -6)


# ---------------------------------------------------------------------------
# T-CAP-44, T-CAP-87: the OpenCV fake under the shared loop (virtual clock)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reported_fps", [30.0, 0.0], ids=["reports 30", "reports 0"])
def test_t_cap_44_opencv_source_under_the_shared_loop(monkeypatch, reported_fps):
    """T-CAP-44, sections 14.1 and 10.1 [D46, D6, U2]: the OpenCV fake under the shared loop, with a
    reported rate of 30 and of 0. Warm-up and rate check in both: with 0, the check uses the requested
    rate (ADR-PDD3 W2), and `measured_fps` is within 3 % of 30; the ring gets a q90 JPEG with no
    burned-in stamp (it decodes to the fake image); the BGR ring gets the OpenCV image.

    "q90, no stamp": each ring JPEG is byte-equal to `cv2.imencode` at quality 90 of an image that the
    fake gave. Virtual clock of the factory (ADR-BM73)."""
    factory = OpenCVFakeFactory(monkeypatch, reported_fps=reported_fps)
    app = CaptureApp(monkeypatch, factory)
    try:
        spies = Spies(monkeypatch, app)
        camera_id = factory.camera_ids[0]
        ready_app_steps(app, [app.config(camera_id, bgr_ring=True)])
        app.wait(lambda: len(spies.of("jpeg")) >= 30, "30 ring frames")
        status = app.status(camera_id)
        capture = factory.captures[camera_id]
        writes = spies.of("jpeg")
        assert writes[0]["sfn"] >= 90, f"the first ring frame is grab {writes[0]['sfn']}: no warm-up"
        assert all(e["hash"] in capture.jpeg_hashes for e in writes), "a ring JPEG is not the q90 JPEG of a fake image"
        puts = [e for e in spies.of("bgr_put") if e["source"] == "BGR"]
        assert puts and all(e["hash"] in capture.image_hashes for e in puts), "the BGR ring did not get the OpenCV image"
        assert status["state"] == "ready" and abs(status["measured_fps"] - 30.0) <= 0.9, status
    finally:
        app.close()


def test_t_cap_87_late_frames_do_not_reopen(monkeypatch):
    """T-CAP-87, sections 14.2 and 5.1 [U2, D8]: shared loop with the OpenCV fake on each OS: 60 frames,
    each 70 ms late (more than 2 x the period). No reopen: the open count stays 1; each ring JPEG
    decodes to the fake image, with no stamp. Virtual clock of the factory (ADR-BM73)."""
    factory = OpenCVFakeFactory(monkeypatch, late_grabs=range(150, 210), late_s=0.070)
    app = CaptureApp(monkeypatch, factory)
    try:
        spies = Spies(monkeypatch, app)
        ready_app_steps(app)
        camera_id = factory.camera_ids[0]
        capture = factory.captures[camera_id]
        app.wait(lambda: capture.grabs >= 240, "the late frames and 30 more")
        assert factory.opens[camera_id] == 1, "the loop reopened the camera"
        writes = spies.of("jpeg")
        assert any(150 <= e["sfn"] < 210 for e in writes)
        assert all(e["hash"] in capture.jpeg_hashes for e in writes), "a ring JPEG is not the q90 JPEG of a fake image"
    finally:
        app.close()
