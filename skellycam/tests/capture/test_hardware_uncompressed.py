"""Hardware tests of step 3b: T-CAP-68 and T-CAP-69 (specs/windows-capture.md, sections 2.2, 13 and 16).

Each test has the marker `camera_hardware` and runs only with `SKELLYCAM_HARDWARE=1`, on the word of
the user, on the Windows development machine (16.7: no counterpart on Linux and macOS until phase 7,
reason e). Lights on. The real Quick Sync check and encoder run: the machine has Intel Quick Sync.

The modes are those of 2.2 item 2: the C930e and the C922 offer YUY2 at 1280x720 only up to 10 fps
(`research/frame_ring_buffer/yuy2_range/FINDINGS.md`, branch `dom/research`).
"""

import sys
import time

import pytest

from skellycam.tests.capture.capture_hardware import hardware_app, kiyo_pro_rule, record_result
from skellycam.tests.capture.capture_session import (
    Spies, capture_logs, column, recording_info, recording_info_json, sfn_gaps, stop_line_count)

pytestmark = [pytest.mark.camera_hardware,
              pytest.mark.skipif(sys.platform != "win32", reason="the step 3b cameras run on Windows")]

# label: (format, width, height, the range of the yuy2_range evidence)
MODES_68 = {"C922": ("YUY2", 640, 480, "limited"), "C930e": ("YUY2", 640, 480, "limited"),
            "Kiyo Pro": ("YUY2", 1280, 720, "full"), "generic": ("NV12", 1280, 720, "full")}


@pytest.mark.parametrize("label", list(MODES_68))
def test_t_cap_68_uncompressed_mode_on_each_camera(monkeypatch, tmp_path, label):
    """T-CAP-68, sections 2.2 and 13 [D2, U11]: YUY2 640x480 at 30 on the C922 and the C930e; YUY2
    1280x720 at 30 on the Kiyo Pro; NV12 1280x720 at 30 on the generic camera. Each reaches `ready` or
    fails with a reason; the range decision agrees with the yuy2_range evidence; Quick Sync is used on
    the development machine.

    The range decision is read from the recording info of a take of 2 s (11.6). "Quick Sync is used":
    the status `jpeg_encoder` is "quick_sync" (ADR-3WCA)."""
    fmt, width, height, expected_range = MODES_68[label]
    with hardware_app(monkeypatch) as app:
        with kiyo_pro_rule(app, label, "T-CAP-68"):
            camera_id = app.camera_id(label)
            config = app.config(camera_id, width=width, height=height, framerate=30.0, capture_fourcc=fmt)
            response = app.apply([config])
            assert response.status_code == 200, response.text
            app.wait_state(camera_id, "ready", "failed", "dead")
            status = app.status(camera_id)
            if status["state"] != "ready":
                record_result("T-CAP-68", camera=label, mode=[fmt, width, height], state=status["state"],
                              failure=status.get("failure"))
                assert status["failure"] and status["failure"]["reason"], status
                return
            assert app.record_start(tmp_path).status_code == 200
            time.sleep(2.0)
            assert app.record_stop().status_code == 200
            decided = recording_info_json(tmp_path)["capture"][camera_id]["input_range"]
            record_result("T-CAP-68", camera=label, mode=[fmt, width, height], state="ready",
                          measured_fps=status.get("measured_fps"), jpeg_encoder=status.get("jpeg_encoder"),
                          input_range=decided)
            assert decided == expected_range
            assert status["jpeg_encoder"] == "quick_sync"


GROUP_69 = {"C922": ("YUY2", 640, 480), "C930e": ("MJPG", 1280, 720), "Kiyo Pro": ("YUY2", 1280, 720)}


def test_t_cap_69_recording_with_uncompressed_cameras(monkeypatch, tmp_path):
    """T-CAP-69, section 2.2 item 3 [D2, D18]: a recording with one mode rate for the group (30) and at
    least one camera in an uncompressed mode gives equal frame counts, a group rate within 1 % of the
    mode rate, no lost frame that the replaced-frame count does not explain, and no encoder fallback.

    The group: the C922 in YUY2 640x480, the C930e in MJPG 1280x720 and the Kiyo Pro in YUY2
    1280x720, all at 30 fps; one recording of 60 s, as T-CAP-60. "No encoder fallback": the stop line
    of each uncompressed camera has `encoder fallbacks` 0 (ADR-3WCA). A THREAD worker for the spies."""
    with capture_logs() as logs, hardware_app(monkeypatch, workers="thread") as app:
        spies = Spies(monkeypatch, app)
        ids = {label: app.camera_id(label) for label in GROUP_69}
        configs = [app.config(ids[label], width=w, height=h, framerate=30.0, capture_fourcc=fmt)
                   for label, (fmt, w, h) in GROUP_69.items()]
        assert app.apply(configs).status_code == 200
        for camera_id in ids.values():
            app.wait_state(camera_id, "ready")
        assert app.record_start(tmp_path).status_code == 200
        time.sleep(60.0)
        stopped = app.record_stop()
        assert stopped.status_code == 200, stopped.text
        app.client.delete("/skellycam/camera/group/close/all")
        summary = stopped.json()[0]
        info = recording_info(tmp_path)
        counts = {label: len(column(info.camera_timestamps_file_path_from_camera_id(cid), "connection_frame_number"))
                  for label, cid in ids.items()}
        replaced = {label: (stop_line_count(logs.messages(), cid), sfn_gaps([e["sfn"] for e in spies.of("jpeg", cid)]))
                    for label, cid in ids.items()}
        fallbacks = {label: stop_line_count(logs.messages(), ids[label], word="encoder fallbacks")
                     for label, (fmt, _, _) in GROUP_69.items() if fmt != "MJPG"}
        record_result("T-CAP-69", counts=counts, summary=summary, replaced_and_gaps=replaced, fallbacks=fallbacks)
        assert len(set(counts.values())) == 1, counts
        assert 29.7 <= summary["mean_framerate"] <= 30.3, summary
        assert all(count == gaps for count, gaps in replaced.values()), replaced
        assert all(count == 0 for count in fallbacks.values()), fallbacks
