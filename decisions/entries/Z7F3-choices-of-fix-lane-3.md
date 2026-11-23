# Z7F3 — Choices of fix lane 3

**Status:** proposed, 2026-11-21 (agent; the supervisor gave the items, after real-camera runs).

## Decision

Items 2, 3 and 6 are decisions of the user of 2026-11-21. The user decided item 1 on 2026-11-23 (Q584): "as
long as the frame rate still passes, a one step exposure tolerance is fine for all cameras". The start-up rate
check of each open covers that condition (T-UNX-91). The user decided on 2026-11-23 (Q585): with `clock:base`
`not-run` `clock-unknown`, `gate:timestamps` requires only `clock:before-arrival` and `clock:near-arrival`; a
declared clock keeps all three. The agent chose the other details:

1. At the first read of an open, a control of the restore record takes its "before" value from the record when
   the camera reads the auto flag that this app set last and, with auto off, a value not more than one step
   from it. The step is `c_step` of the range at this open; with no step above 0, the value must be the same
   ([`unix-capture.md`](../../specs/unix-capture.md) 4.7).
2. A live settings change never restarts a camera. The apply request gets the list `retry_camera_ids`: a
   `failed` or `dead` camera, or one whose process ended, opens again only when the list names it. Only "Update
   Cameras" fills it; the fall back to 30 fps names the cameras that failed at 60 fps, never one with a wedge
   code. The answer names each failed camera that it left alone (`camera_failures` and the warning
   `camera_not_retried`); its stored config takes only the new rate; the UI keeps it at "error" with the edit of
   the user. An ID of the list that does not apply is ignored ([`windows-capture.md`](../../specs/windows-capture.md) 8.3).
3. A camera whose loop failed, or whose source had a stream error, gets its restore at the close, except for the
   wedge codes `stalled`, `hung`, `device-removed` and `process-ended` (`WEDGE_CODES`). Certify gives
   `camera-not-restored` to a failed camera only for these codes (from the status, kept at the scan) or for
   `restore_ok` false ([`certify.md`](../../specs/certify.md) 8.3).
4. With no group, the flag `creating` of `CameraGroupManager` refuses a second apply request with the 409 of
   `request_runs`; a close during its detection (the count `closes`) ends it with a 409
   ([`camera-requests.md`](../../specs/camera-requests.md) 2.4a item 7).
5. Media Foundation keeps `clock` `unknown`; certify gives `clock:base` `not-run` with the new reason
   `clock-unknown` (`not-built` stays for a null key); `time-gaps` is marked W in `full` (certify.md 10.2).
6. The rate of a group frame in the stop response is 1 / the median over the cameras of its frame duration; the
   field names stay ([`recorder.md`](../../specs/recorder.md) 8.2).
7. A lower bound of a timed wait in a test gets 2 ms (`EARLY_S`); the sample-minus-arrival check of the
   Media Foundation stand-in is one-sided. The p99 tests of the ring keep their bounds and `ring_slow`.

## Reason

1. A Logitech C930e read back manual exposure -8 in the open that set it and -7 at the next open, so the record
   was dropped and the camera stayed manual after a kill; a Logitech C922 read -8 in both. A value of another
   program (T-UNX-92 (b): -3 against -7) is still more than one step away.
2. A settings apply of the UI sends each selected camera, also a failed one with its unchanged config, so only
   an explicit list can tell a retry. The certify live change then cannot reopen a camera that dies after its
   scan.
3. A generic camera that failed its rate check (25.7 fps in a 30 fps mode, the first real certify run) stayed
   at MANUAL -7. A stall can be a wedged camera (the Kiyo Pro), so it gets no call.
4. A request with no detection result detects before it makes the group; a second request in that time made a
   second group.
5. The source reads only `IMFSample::GetSampleTime`; nothing that it reads names the base. The measured arrival
   minus sample agrees with QPC but proves no base.
6. One camera with queued frames 0.36 ms apart made a frame of 2778 fps; the mean over the cameras kept most of
   it.
7. A timed wait ended 0.14 ms and 0.4 ms early on a loaded machine. The stand-in stamps the sample time before
   the arrival, so a delay only lowers the value.

## Consequences

1. A value that another program set within one step of the last value of this app now takes the record.
2. A client other than the UI (freemocap) must send `retry_camera_ids` to reopen a failed camera; the rate
   selector no longer reopens one.
3. A late close dict of a camera that failed with `rate-low` gives no notice: certify trusts the product.
6. With two cameras the median is the mean of the two durations: one bursting camera of two gives about 60 fps.

## Evidence

Only the tip of the branch is verified: the commits before the fix of the connection tests do not pass their own
tests, and the history is not rewritten (the review of 2026-11-23).

## Alternatives rejected

1. A record of the value at the end of the open: a killed open has no end, and the C930e changed only at the
   new open. A fixed tolerance of 1: a control with a larger step loses its record.
2. One request flag `retry: true`: a camera that the UI does not yet show as failed would also open again.
6. A median of the rates over the cameras: for two cameras it is the mean of the two rates.
