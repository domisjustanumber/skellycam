# VTW3 — Choices of the Quick Sync check in a child process and its certify check

**Status:** proposed, 2026-11-26 (agent; the Quick Sync lane builds Q879 of
[ADR-4TBY](4TBY-decisions-of-the-user-on-the-review-of-the-3b-code.md) item 4; waits for the user).

## Decision

The user decided Q879 (ADR-4TBY item 4): the check of the product runs in a child process with a time limit, a hang
or a crash means "no Quick Sync, use OpenCV", and a record-only certify check reports the result and its time. This
entry holds the choices of the lane that the user did not decide. `specs/windows-capture.md` 22.7 and
`specs/certify.md` 3.6.2 state them; a mark [VTW3 n] is item n.

1. **One child mechanism.** The bounded child call of the detection moves from `media_foundation/detect.py` to
   `capture/bounded.py` as `in_child(stage, what, target, args, *, limit_s, name)`. Detection and the Quick Sync
   check use it. The managed worker (`ManagedProcess`) is not used: it is for long-lived workers with a shutdown
   flag and a log queue, and it has no limit for each message.
2. **The calls.** `check_quick_sync(*, limit_s) -> QuickSyncCheck` (`works`, `failure`, `check_ms`, `encode_ms`,
   `exit_code`) runs the encode in a child and never raises an `Exception`. `quick_sync_works() -> bool` stays the
   seam of the manager (22.6 item 6) and of the fakes of the tests, and gives `check_quick_sync().works`.
3. **The limit is 5 s** (`BOUNDED_CALL_LIMIT_S`, the limit of the detection calls), from the start of the child.
4. **The log levels.** An encode that raises or gives no JPEG is the normal answer on a machine with no Intel GPU: one
   INFO line, as before. A time-out, a crash and another error of the child call give one WARNING line that names
   which, and ends with "cv2.imencode is used".
5. **No process left.** The call kills and joins the child after a time-out; a test checks it with `psutil`.
6. **App start.** The app already imports PyAV at its start (`take_recorder/mkv.py`), so the check adds no import
   there. The start of the app and a request with no raw camera start no check child; T-CAP-172 and T-CAP-173 check
   it.
7. **The wait of the request.** About 1.05 s here in place of 0.55 s; at most the limit and the join.
8. **The answer of the manager.** Kept for the app run, also False after a time-out or a crash. Certify does not
   set it.
9. **The certify name** is `system:quick-sync` (3.1: `system:<check>`, a fact or a check of the system).
10. **The level.** Both levels, right after `detect`, also with no camera and after a failed `detect`. It costs about
    1 s of the 30 s of quick. The seconds estimate of 4.7 does not change.
11. **Windows only.** Linux and macOS have no row: the product runs the check only for the Media Foundation source,
    and never on macOS.
12. **The values are in `numbers`**: `works`, `check_ms`, `encode_ms`, `failure`, `exit_code`. They are flat, so
    `details` is not needed (as `system:timer`). `failure` is `null`, `timed-out`, `crashed`, `no-jpeg` (a new code
    of section 15) or the class name of the error, never its text.
13. **No Intel GPU is `works` false, not `not-run`.** `not-run` is for a check that could not judge (3.3). The check
    judged: Quick Sync does not work on this system, and the product uses `cv2.imencode`. A time-out and a crash are
    answers of the same kind. `not-run` is only `cancelled`, `over-budget` and `cameras-busy`.
14. **A cancel during the check** gives `not-run` `cancelled` at once. The run waits for the check on a thread and
    reads the cancel as for `detect`; the child ends at its own limit at the latest.
15. **The tests.** T-CAP-166 to T-CAP-173 (`skellycam/tests/capture/test_quick_sync_child.py`; the child tests are
    `capture_timing`, as the detection child tests) and T-CERT-152. The fake checks are module functions in
    `skellycam/tests/capture/quick_sync_child_fakes.py`, because a `spawn` child imports its target by name. The
    certify tests replace `check_quick_sync` with a fake for each run, so no certify test starts a real check.
16. **No second entry for Q879.** ADR-4TBY item 4 records the words of the user, and it is absorbed into the spec.

## Reason

- One mechanism keeps one place for the limit, the kill and the join, as the brief of the lane asks.
- 5 s is the limit that the user named as an example ("as for camera detection"). The measured check is 1.03 to 1.08
  s here, and the first child start after a pause took 1.17 s for the imports alone, so 5 s leaves room for a slower
  machine. A too-short limit only costs CPU: the camera then uses `cv2.imencode`.
- A WARNING at each first raw request on each machine with no Intel GPU would be noise; a fault of the child is not.
- A check in quick also reaches the systems whose owners run only quick (the pop-up of a new camera model).

## Evidence

- 22.7 item 3, a scratch script (five spawned children per case, Python 3.13.18, `uv.lock`, the development machine,
  2026-11-26): empty child 53 to 59 ms; the encoder imports 492 to 516 ms (1169 ms the first time); the whole check
  1027 to 1079 ms, the encode 545 to 569 ms.
- The built code, no camera: five `check_quick_sync()` calls gave `works` True, `check_ms` 1057 to 1112,
  `encode_ms` 537 to 545. A certify run with `devices=[]` (no detection, no camera) gave `system:quick-sync`
  `record-only`, `works` true, `check_ms` 1061.9 (quick) and 1071.4 (full).

## Alternatives rejected

- `ManagedProcess` as the child: no limit for each message, and a log queue and a shutdown flag that a one-shot
  check does not need.
- The values in `details.quick_sync`: `details` is for values that are not flat (`player-legacy-decode`).
- `full` only: the systems that run only quick would never report Quick Sync.
- `not-run` for a system with no Intel GPU: the check did judge; certify would then hide the most common answer.
- A limit of 2 s: under 2 times the measured time with a cold start.

## Open work

[open-work.md](../open-work.md)
