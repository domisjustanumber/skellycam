"""T-REC-40 to T-REC-49: the connection tests (specs/recorder.md, sections 10 and 12.1).

They come with the connection commit, after step 3a of phase 3 is joined [R10], and use the fake
source of the capture tests (`specs/windows-capture.md` section 16.1). That fake source and the
shared loop of step 3a are not on this branch yet. Thus each test is skipped with that reason. Each
docstring gives the test and its pass criterion of section 12.2, so that the connection commit
writes the body. T-REC-38 and T-REC-39 are not used (12.6).
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="connection test: comes with the connection commit after step 3a of phase 3 is joined "
           "(specs/recorder.md sections 10 and 12.1, R10); it needs the shared loop and the fake source of step 3a")


def not_written():
    pytest.fail("the connection commit writes this test (specs/recorder.md section 10)")


def test_t_rec_40_full_queue_waits_and_gives_gap_rows():
    """T-REC-40 [D26, D27]: three fake cameras in the shared loop at 30 fps; the writer of one is held
    2 s. All three loops wait; after it, each camera's next row has `gap`; for each camera the sum of
    the gaps of `source_frame_number` equals the increase of `replaced_count`; equal rows."""
    not_written()


def test_t_rec_41_no_decode_for_the_recorder():
    """T-REC-41 [D9, ring 8.2]: record with and without a BGR ring; count `cv2.imdecode` calls on the
    loop thread and on the decode thread. No decode for the recorder; one decode per frame on the
    decode thread only when a BGR ring exists."""
    not_written()


def test_t_rec_42_cut_off_jpeg_gives_a_placeholder_row():
    """T-REC-42 [R3, M1]: the fake delivers a cut-off JPEG during a take. A placeholder on a `missing`
    row; the previous image is not stored again; no decode call."""
    not_written()


def test_t_rec_43_dead_camera_runs_to_the_end_of_the_take():
    """T-REC-43 [R2, M1, D38]: three fakes record; one gives device removed at frame 300. That camera
    is `dead`; its process runs to the end of the take and writes placeholders; its MKV is closed
    normally; every CSV and MKV has the same rows and blocks; `camera_dead` in the manifest; no
    recording info JSON."""
    not_written()


def test_t_rec_44_hang_ends_the_process_and_the_take_level_completes_its_file():
    """T-REC-44 [R4, M5]: a bounded call of one fake hangs during a take. The failure is reported; the
    process ends within 1 s of the report; the take level completes its short file after the join;
    the others record to the stop."""
    not_written()


def test_t_rec_45_stop_response_and_microphone_refusal_over_http():
    """T-REC-45 [R5, C1]: start and stop a take over HTTP with fake sources (not port 53117); then a
    start request with `mic_device_index` 0. The stop response has each field of
    `StopRecordingResponse` with the values of 8.2; the second start gets HTTP 422 with the text of
    section 10 item 13."""
    not_written()


def test_t_rec_46_inserted_dht_is_in_the_ring_and_the_mkv():
    """T-REC-46 [M6]: a fake sends a JPEG with no DHT. The ring slot and the MKV block hold the same
    bytes, with the inserted DHT; the row has no flag for it."""
    not_written()


def test_t_rec_47_row_0_is_group_frame_gate_count_plus_3():
    """T-REC-47 [review B4, M7]: two fakes start a take at gate count 100. Row 0 of each camera is
    group frame 103."""
    not_written()


def test_t_rec_48_stall_watch_stall_end_and_failed_state():
    """T-REC-48 [agent 32, C5, C6]: two OpenCV fakes record; the writer of one is held 3 s; then a fake
    writer is held past the stall limit and then released; then held for good. Case 1: neither camera
    is marked `dead`, also the one that waited at the gate (5.2); case 2: the take ends with
    `take_error`, the camera stays `ready`; case 3: the camera is `failed`, stage `recording`, reason
    "disk stall", and "apply again" reopens it."""
    not_written()


def test_t_rec_49_playback_list_marks_new_takes():
    """T-REC-49 [C7]: list the playback recordings with one old recording and one new take; ask for
    the videos of the new take. Both are listed; the new take has `needs_new_player: true`; the old
    video list endpoint gives HTTP 409 with the mark text for it; no endpoint of the take folder
    itself is blocked."""
    not_written()
