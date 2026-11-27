# M5PJ — Choices of the shutdown follow-ups, Q934 and Q935

**Status:** absorbed into
[`specs/recorder.md#91-the-end-of-the-server-process`](../../specs/recorder.md#91-the-end-of-the-server-process),
2026-11-27 (commit to dom/shutdown-followups; was accepted, 2026-11-27 (user, Q992 of
[ADR-XJA8](XJA8-decisions-of-the-user-on-the-shutdown-follow-ups-q990-to-q993.md)); was proposed, 2026-11-27 (agent)).

## Decision

Q992 accepts these choices of the agent. [`recorder.md`](../../specs/recorder.md) 9.1 items 7 to 9 state them.

1. **Second Ctrl-C** (item 9): `abort_on_a_second_ctrl_c` of `__main__` (a module function, so a unit test can check
   it with a fake server and clock) wraps `uvicorn.Server.handle_exit`. Only SIGINT and SIGBREAK are presses; a
   SIGTERM is no first press. A press less than 1 s (`SECOND_CTRL_C_AFTER_S`, monotonic clock) after the last press,
   also a dropped one, is dropped; one 1 s or more after it sets `force_exit` and the global kill flag and sets the
   forced-exit event. A first press after a SIGTERM is dropped (uvicorn would take it as `force_exit`).
2. **A second Ctrl-Break is a second Ctrl-C**, as item 3 handles Ctrl-Break as Ctrl-C (uvicorn alone takes only a
   second SIGINT as `force_exit`).
3. **The bound is 8 s** from the second signal to the end of each process (a `pace` half), 60 s in the blocking
   half (Q619).
4. **The holds that the test checks:** no frame ring can be attached, the port binds, the take folder renames, its
   take lock can be taken. The locks of `CameraStatus` end with the processes.
5. **The Windows Ctrl-C of the test** goes to a hidden console of the server through `GenerateConsoleCtrlEvent`; the
   child turns Ctrl-C on for that console (`SetConsoleCtrlHandler(None, False)`), as a terminal has it.
6. **A record start while the groups close** (item 7): `CameraGroupManager.start_recording_all_groups` refuses it
   with 409 "The cameras close: no recording starts" while its `closing` count is above 0 (one for each close of
   all groups that runs).
7. **Requests cut by the limit** (item 8): the tests cancel an apply in its start loop, a search in its wait loop
   and an apply in its detection; nothing is left. With Q972 the THREAD case passes, and its strict mark goes.
8. **The forced exit** (Q977): a daemon thread, started when the handler is put in place, waits for the event of the
   abort, then `FORCED_EXIT_AFTER_S` (5 s); when the process still runs then, it logs the names of the threads that
   run and calls `os._exit(1)`. The handler starts no thread (a lock of `threading` can be held by the main thread). It also covers a hang in
   the lifespan end, where `shutdown_all()` does not run yet; the camera processes ended at the kill flag.
9. **Blocking checks with no timing:** the unit test of item 1, and in the process test, no camera process ended by
   `WorkerRegistry.shutdown_all()` (the child writes the exit code and the terminate mark of each worker).

## Reason

1. Q934 wants every process to end. The review of e9eef6e1c found that one key press can give two signals; 1 s
   keeps a real second press and drops a repeat; the kill flag is the existing signal for that, and the camera processes and
   the stop that waits for them react to it at once. `force_exit` alone did nothing while the lifespan end ran.
2. A user who presses Ctrl-Break twice wants the same abort.
3. Measured with the rule: each process ended 0.15 s to 0.27 s after the second signal, and the manifest was even
   `finished`; 8 s keeps room for a slow runner and stays under the 10 s of a lost heartbeat (decision L).
4. These are the holds that block a new server or the files of the take.
5. A process group made with `CREATE_NEW_PROCESS_GROUP` gets no Ctrl-C; a console must take it.
6. The start used to reach the closing cameras and gave 500.
7. With camera processes, `ManagedProcess.join` skips a process that never started; the close then ends all.

## Evidence

Windows 11, CPython 3.13.18, uvicorn 0.54.0; the real server with two fake camera processes and a take stop that
waits 12 s for its cameras.

- Before the rule, from the second signal to the end of the last process: Ctrl-C during a stop request 4.1 s
  (manifest `recording`); Ctrl-C during the lifespan stop 12.1 s (the second Ctrl-C did nothing); Ctrl-Break 12.3 s
  in both cases. In each case nothing was left: no process, ring, port, take folder or take lock held.
- The record start during the close: 500 "Cannot change camera state: camera group has stopped." before the rule.
- The cancelled apply with THREAD workers: `RuntimeError: cannot join thread before it is started` in
  `CameraManager.close` and in `WorkerRegistry._reap_all`.
