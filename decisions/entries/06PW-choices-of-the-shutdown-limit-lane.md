# 06PW — Choices of the shutdown limit lane

**Status:** proposed, 2026-11-27 (agent; applies Q907 of
[ADR-75CF](75CF-decision-of-the-user-on-the-shutdown-of-the-server.md); commit to dom/server-shutdown).

## Decision

The user did not decide these details. [`recorder.md`](../../specs/recorder.md) 9.1 states them.

1. **No connection limit is built.** Q907 asks for a limit only if the product hangs. The product did not hang
   (0 of 39 runs, Evidence). A first version of the lane added a limit of 5 s (`timeout_graceful_shutdown`) all the
   same; a review found that the limit can leave a take unfinished (open work), so this branch takes it out. The
   full work with the limit is kept, not merged, on the branch `dom/server-shutdown-limit` for the user to decide.
2. **The exit does not wait for the feeder thread of the websocket log queue** (9.1 item 1): `entry_point()` calls
   `get_websocket_log_queue().cancel_join_thread()` after `configure_logging`.
3. **One DEBUG line for each suppressed `ConnectionResetError`** (9.1 item 2), with the message of the context.
   The handler stays.
4. **The tests** (9.1 item 3). `test_server_exit.py` starts the real server with `server_exit_child.py` (no
   telemetry, no bytecode pass, a temporary base folder and log file) on a port that the test holds, and checks that
   the process ends with an error code. `test_entry_point.py` checks the cancel.

## Reason

1. The words of Q907 and the first rule of the user: a recording must not be lost. A limit cancels the request
   tasks that still run, and a cancelled take stop leaves the manifest `recording` (open work). With no hang found,
   the limit has no gain to weigh against that. The 5 s of the first version came from the brief of the
   supervisor, not from the user: the 5 s of the user (Q906) is for the test server `ui_server.py`.
2. With no open websocket, nobody reads the queue. The feeder thread then waits in `_send_bytes` on a full pipe,
   and the exit handler `_cleanup_log_queue` of `skellylogs` waits for it with `join_thread`. The records that the
   cancel drops at the exit have no reader.
3. The handler hid the 10054 error of the stop of the test server. The default level is TRACE (`LOG_LEVEL` of
   `skellycam/__init__.py`), so the DEBUG line shows in the console and in the log file.
4. A port-in-use start is the case that hung (Evidence); the test makes it with no camera and no race.

## Evidence

Windows 11, CPython 3.13.18, uvicorn 0.54.0, Chromium 1255 of Playwright (headless). The scripts are local
(scratchpad) and not tracked: a wrapper of `skellycam/__main__.py` with the patches of item 4 and a probe that
prints when `_call_connection_lost` raises, and a driver that connects a client, ends it, calls `/shutdown` and
times the exit of the process.

- **No hang of the product with reset clients: 0 of 39 runs.** Exit 0.18 s to 1.16 s after the answer of
  `/shutdown` (the period of the worker monitor is 1 s). Clients: a normal close (1), a socket reset with
  `SO_LINGER` 0 before `/shutdown` (1) and after it (4), a close frame 1001 then a reset (4), a killed client process
  (4), and a Chromium page that stays open (8), is killed with its process tree (8) or closes with 1001 (8). The
  probe never printed: no `ConnectionResetError` in `_call_connection_lost`. A plain asyncio server with eight
  orders of reset, close and write gave no case either. The test server that hung (3 of 20 stops) sent a preview
  stream to the browser and closed the websockets itself; the product with no camera sends no preview stream.
- **The port in use: 3 of 3 runs did not end in 20 s.** The stacks: the main thread in
  `skellylogs.configure_logging._cleanup_log_queue` → `Queue.join_thread` → `_finalize_join` → `Thread.join`; the
  feeder thread of the websocket log queue in `queues._feed` → `connection._send_bytes`. The startup logs fill the
  pipe before a websocket reads it.
- **An idle server**: after 10 s with no websocket, the feeder thread waited for new items
  (`queues._feed` in `wait`), and the exit took 1.11 s.
- The port-in-use test and the test of the cancel failed before the code change and pass after it.

## Alternatives rejected

- **A connection limit of 5 s now** (`dom/server-shutdown-limit`). Not built: see Reason 1 and open work.
- **`os._exit` for a `SystemExit` in `entry_point()`.** It covers only that path; the cancel covers each exit.
