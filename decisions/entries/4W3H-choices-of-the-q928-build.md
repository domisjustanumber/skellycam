# 4W3H — Choices of the Q928 build: the shield, Ctrl-Break and the tests

**Status:** proposed, 2026-11-27 (agent; applies Q928 of
[ADR-9V4Y](9V4Y-decisions-of-the-user-on-the-shutdown-lane-q924-to-q928.md); commit to dom/server-shutdown-limit).

## Decision

The user did not decide these details. [`recorder.md`](../../specs/recorder.md) 9.1 items 3 to 5 state them.

1. **The shield.** `CameraGroup.start_recording` and `stop_recording` wrap their body (with `_end_lock`) in a task
   (`_shielded`) and await it under `asyncio.shield`. The group keeps the task in `_end_tasks` until it ends. A done
   callback reads its outcome; when the caller was cancelled, a second callback logs an error of the task at ERROR
   with its traceback, except a `RequestRefused` (a caller that was not cancelled gets the error, so no double log).
   `_end_after_error` and `CameraGroup.close` do not change: no request awaits the first, and the close order stays.
2. **A close of all groups** waits for the take lock of each group (`CameraGroup.await_take_end`, `async with
   _end_lock: pass`) before `group.close()`, one group after the other, with no `gather`. So it waits for a start
   that has not set `self.take` yet. The other caller of `group.close()` is the teardown of a group whose start
   failed (`_create_and_start`): no take can run in it. `_end_after_error` and `WorkerRegistry.shutdown_all()`
   call no `group.close()`. A close that is cancelled after the stop leaves its group listed, and the lifespan
   close closes it again; that second close is not tested.
3. **Ctrl-Break is Ctrl-C.** A camera process ignores SIGBREAK as it ignores SIGINT, and `__main__` handles SIGBREAK
   with the handler of SIGINT and SIGTERM. Both are guarded by `hasattr(signal, "SIGBREAK")`.
4. **The tests** (`take_recorder/test_take_end_cancel.py`): a cancel on the event loop of the app, as uvicorn does
   it, of a stop that waits for a held camera, of a close of all groups at that place, and of a start in
   `start_take`; then a close as the lifespan end does. The last test runs the real `__main__` with two fake camera
   processes (`server_take_child.py`), a stop that waits 12 s for its cameras, and a real Ctrl-Break to the process
   group on Windows (SIGINT to the server elsewhere). It fails unless the take end starts before the signal and
   ends after the signal plus 5 s (the child writes those times) and uvicorn logs its cancel. Whether
   `GenerateConsoleCtrlEvent` works on a GitHub Windows runner is not known; the first CI run shows it.
5. **What the limit can cut** is stated in 9.1 item 5 (a request other than a take start or stop) and is not tested.

## Reason

1. The task keeps the lock, so each later end waits for it, and the close gets the 409 that it already handles. The
   reference keeps the task from being collected while no caller awaits it.
2. The take is what must not be lost; the order of the close is outside this lane.
3. A real Ctrl-Break during a take ended each camera process at once (`0xC000013A`): the take ended with
   `camera_dead` for both cameras. uvicorn raises the signal again after `serve()`, and with the default handler the
   server ended with code 3 before `WorkerRegistry.shutdown_all()`.
4. A cancel on the loop is the exact act of uvicorn at its limit and needs no limit to test. The real signal checks
   the whole path on the product.

## Evidence

Windows 11, CPython 3.13.18, uvicorn 0.54.0.

- Before the shield, the three cancel tests failed: the manifest stayed `recording`, `take.finish` never ran. For
  a stop, the frame count of the take was 50 (51 in the close case) and each camera wrote 70 rows: after the cancel
  cleared the first and last frame, each camera ended at the close from frame 0 (`camera_loop._end_take`). This is
  the wrong frame count of the review. The cancelled start never made its take.
- Before the Ctrl-Break fix, the real-signal test failed (exit code 3, `camera_dead` for both cameras, a
  `finished` manifest). After it, the four tests pass and no test process is left.
- With the 5 s limit and the shield taken out again for one run, the real Ctrl-Break during the 8 s stop gave a
  `recording` manifest (46 rows for each camera): the limit cancelled the stop. With the shield it is `finished`.
- Review of 0ed35cfc8, confirmed: a start cancelled in a slow `start_take` and a close at once left a `recording`
  manifest and 1 task (the close took 0.03 s). With the wait for the take lock the close waits for the start and
  stops its take: `finished`, no task left (also after a close that is cancelled while it waits). A full-disk error
  of a stop whose caller was cancelled was logged nowhere before the second callback.
