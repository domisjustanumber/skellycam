# Z7F3 — Choices of fix lane 3

**Status:** proposed, 2026-11-21 (agent; the supervisor gave the items, after real-camera runs).

## Decision

The supervisor gave the items. The agent chose these details:

1. The restore record of a camera that rounds. At the first read of an open, a control of the record takes its
   "before" value from the record when the camera reads the same auto flag as the value that this app set last,
   and, with auto off, a value not more than one step from that value. The step is `c_step` of the range of the
   control at this open (`GetRange` on Media Foundation). A control with no range, or with a step that is not
   above 0, needs the same value. `ControlRestore.read(state, steps)` gets the steps; the Media Foundation source
   reads the ranges before the first control read ([`unix-capture.md`](../../specs/unix-capture.md) 4.7).
2. The user decided on 2026-11-21: a live settings change never restarts a camera. "The user asks to open this
   camera again" is the new list `retry_camera_ids` of the apply request (camera IDs, empty by default). A
   `failed` or `dead` camera, or a camera whose process ended, opens again only when the request names it there;
   any other request leaves it as it is, with its process, config and failure. Only "Update Cameras" of the UI
   fills the list (its `retry` cameras). The fall back to 30 fps (2.4a) names the cameras that failed at 60 fps.
   A camera that the request selects again after an unselect needs no list
   ([`windows-capture.md`](../../specs/windows-capture.md) 8.2, 8.3; [`camera-requests.md`](../../specs/camera-requests.md) 1.8, 2.4a).
3. The user decided on 2026-11-21: a camera whose loop failed for a reason other than a hang gets its own
   settings back at its close. The agent chose the codes with no restore: `stalled`, `hung` and `device-removed`
   (`WEDGE_CODES` of `failure_codes.py`, the wedge of [`certify.md`](../../specs/certify.md) 10.7 item 5). Certify
   gives `camera-not-restored` to a failed camera only for these codes or for `restore_ok` false (8.3).
4. The flag `creating` of `CameraGroupManager`: an apply request that finds no group sets it with no wait after
   that check and clears it at its end; a second such request gets the 409 of `request_runs` with its reason
   ([`camera-requests.md`](../../specs/camera-requests.md) 2.4a item 7).
5. Media Foundation keeps `clock` `unknown`: the source reads only `IMFSample::GetSampleTime`, and nothing that it
   reads names the base. Certify gives `clock:base` `not-run` with the new reason `clock-unknown` (not
   `not-built`, which stays for a null key). `long_intervals` already counted with the mode period (since the
   step 2 fixes); a test now proves it, and `time-gaps` is marked W in `full` ([`certify.md`](../../specs/certify.md) 10.2, 15).

## Reason

1. A Logitech C930e read back manual exposure -8 in the open that set it, and -7 at the next open (the user's
   real-camera run of 2026-11-21). The old rule needed the same value, so the record was dropped, and the close
   of the next open "restored" manual -7: the camera stayed in manual exposure after its process was killed. A
   Logitech C922 read back -8 in both opens. A rounding stays inside one step of the control. A value that another
   program set (T-UNX-92 (b): -3 against -7) is more than one step away, so it still stays.
2. The UI sends each selected camera in a settings apply, also a failed one with its unchanged config, so the
   server cannot tell a retry from the configs. Only an explicit list can. The certify live change (4.3) then
   cannot reopen a camera that dies between its scan and its apply.
3. A camera that failed its rate check stayed at MANUAL -7 (a generic camera at 25.7 fps in a 30 fps mode, the
   first real certify run of 2026-11-21). A stall can be a wedged camera (the Kiyo Pro), so it gets no call.
4. A request with no detection result detects before it makes the group (seconds); a second request in that
   time made a second group on the same cameras.
5. A guess of QPC would be a fact that no code proves. The measured arrival minus sample (0.33 ms and 32 ms,
   [`certify.md`](../../specs/certify.md) 10.2) agrees with QPC but does not prove the base.

## Consequences

1. A value that another program set to not more than one step from the last value of this app now takes the
   "before" values of the record (before: only exactly that value). On the exposure scale of Media Foundation
   (step 1, log2 seconds) that is a change of one stop.
2. "Apply again" with no list no longer reopens a camera. A client other than the UI (for example freemocap) must
   send `retry_camera_ids` to reopen a failed camera. The rate selector no longer reopens a failed camera.
3. A close dict that comes after the close of the group (no `restore_ok`) of a camera that failed with
   `rate-low` now gives no notice: certify trusts the restore of the product there.
5. `<model>:gate:timestamps` cannot pass on Media Foundation while `clock:base` is `not-run`.

## Evidence

1. Code facts: `ControlRestore.read` of `skellycam/core/camera/capture/source.py`; `_set_and_read` of
   `skellycam/core/camera/capture/media_foundation/source.py`. Tests: T-UNX-91 (the case "a camera that rounds",
   the fake field `reopen_shift`) and T-UNX-92 (d), (e) in `skellycam/tests/capture/test_restore.py`, and
   `test_t_unx_92_the_media_foundation_source_gives_the_step_of_get_range_to_the_restore_record`. Each failed on
   the old code for the rule itself (the camera stayed manual -6; the "before" value was the read value).
2. Tests: T-CAP-20 step (0) in `skellycam/tests/capture/test_states.py` and
   `test_the_live_change_does_not_reopen_a_camera_that_died_after_the_scan` in
   `skellycam/tests/certify/test_certify_review2.py`; both failed on the old code (the camera opened again).
3. Tests: T-UNX-95 in `skellycam/tests/capture/test_restore.py`; the two cases of
   `test_review_2_a_failed_camera_that_was_set_is_flagged_only_when_the_product_does_not_restore_it`.
4. Test: `test_t_req_96_two_requests_with_no_group_make_one_group` in `skellycam/tests/capture/test_frame_rate.py`.
5. Test: `test_clock_base_of_a_source_that_cannot_tell_its_clock` in `skellycam/tests/certify/test_certify.py`;
   `test_t_unx_76_long_intervals_count_with_the_period_of_the_granted_mode`.

## Alternatives rejected

1. Record the value that the camera reads at the end of the open too: a killed process has no end of the open,
   and the C930e read -8 to the end of that open; the change came only at the new open. A fixed tolerance of 1:
   a control with a larger step (for example focus) would still lose its record.
2. One request flag `retry: true`: a camera that the UI does not yet show as failed, sent in the same "Update
   Cameras" request, would also open again. A rule from the configs alone (for example "a changed config"): the
   settings apply sends a failed camera with its unchanged config, and a rate pick changes every config.
