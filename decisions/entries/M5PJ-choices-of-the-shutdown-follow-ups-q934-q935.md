# M5PJ — Choices of the shutdown follow-ups, Q934 and Q935

**Status:** proposed, 2026-11-27 (agent; applies Q934 and Q935 of the user; commit to dom/shutdown-followups).

## Decision

The user did not decide these details. [`recorder.md`](../../specs/recorder.md) 9.1 items 7 to 9 state them.

1. **Second Ctrl-C** (item 9): `__main__` wraps `uvicorn.Server.handle_exit`; at a second SIGINT or SIGBREAK it sets
   `force_exit` and the global kill flag. The first signal does as before.
2. **A second Ctrl-Break is a second Ctrl-C**, as item 3 handles Ctrl-Break as Ctrl-C (uvicorn alone takes only a
   second SIGINT as `force_exit`).
3. **The bound is 8 s** from the second signal to the end of each process (a `pace` half), 60 s in the blocking
   half (Q619).
4. **The holds that the test checks:** no frame ring can be attached, the port binds, the take folder renames, its
   take lock can be taken. The locks of `CameraStatus` end with the processes.
5. **The Windows Ctrl-C of the test** goes to a hidden console of the server through `GenerateConsoleCtrlEvent`; the
   child turns Ctrl-C on for that console (`SetConsoleCtrlHandler(None, False)`), as a terminal has it.
6. **A record start while the groups close** (item 7): `CameraGroupManager.start_recording_all_groups` refuses it
   with 409 "The cameras close: no recording starts" while its `closing` flag is set.
7. **Requests cut by the limit** (item 8): the tests cancel an apply in its start loop, a search in its wait loop
   and an apply in its detection; nothing is left with camera processes. The THREAD case of the apply is a strict
   `xfail` and a question for the user; nothing is fixed.

## Reason

1. Q934 wants every process to end; the kill flag is the existing signal for that, and the camera processes and
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
