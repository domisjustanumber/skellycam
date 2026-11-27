# 06PW — Choices of the shutdown limit lane

**Status:** proposed, 2026-11-27 (agent; applies Q907 of
[ADR-75CF](75CF-decision-of-the-user-on-the-shutdown-of-the-server.md); commit to dom/server-shutdown).

## Decision

The user did not decide these details. [`recorder.md`](../../specs/recorder.md) 9.1 states them.

1. **The limit is 5 s.** `skellycam/__main__.py` sets `timeout_graceful_shutdown=SHUTDOWN_CONNECTION_LIMIT_S` (5)
   in its `uvicorn.Config`. That is the only `uvicorn.Config` of the product. The other one is in the measurement
   script `decisions/scripts/measure_preview_m_prv.py`, which does not change after its entry.
2. **The limit starts at the first signal to uvicorn** (9.1 item 2). In the path of the shutdown endpoint, that is
   after each take and each protected save. With Ctrl-C, the lifespan end that ends a take runs after the limit; a
   request that still runs after 5 s is cancelled.
3. **The exit does not wait for the feeder thread of the websocket log queue** (9.1 item 4): `entry_point()` calls
   `get_websocket_log_queue().cancel_join_thread()` after `configure_logging`.
4. **One DEBUG line for each suppressed `ConnectionResetError`** (9.1 item 5), with the message of the context.
   The handler stays.
5. **The tests** (9.1 item 6). `test_server_exit.py` starts the real server with `server_exit_child.py`: no
   telemetry, no bytecode pass, a temporary base folder and log file, a free port. A lost connection is made
   portable: the child skips `Server._detach` for the first accepted connection. The test is split as Q669 says,
   and `test_pace_marker.py` names its `pace` half and its blocking half. `test_entry_point.py` checks the cancel.

## Reason

1. 5 s is the value that the user suggested in the brief of the lane. It is longer than an ordinary close of a
   websocket and of an HTTP request. A bigger value that covers the 15 s of a stuck writer only matters on the
   Ctrl-C path (item 2), and it makes each app quit with a lost connection 15 s or more longer.
2. The order of section 9 puts the signal after the close of the groups and the saves, so the limit cannot cut a
   take in the app quit.
3. With no open websocket, nobody reads the queue. The feeder thread then waits in `_send_bytes` on a full pipe,
   and the exit handler `_cleanup_log_queue` of `skellylogs` waits for it with `join_thread`. The records that the
   cancel drops at the exit have no reader.
4. The handler hid the 10054 error of the stop of the test server. A DEBUG line costs nothing at the default
   level and shows the reset in the log file.
5. The proactor fault depends on a race that the product did not show in 39 runs (Evidence). The skipped
   `_detach` gives the same state of the asyncio server on each system, every time.

## Evidence

Windows 11, CPython 3.13.18, uvicorn 0.54.0, Chromium 1255 of Playwright (headless). The scripts are local
(scratchpad) and not tracked: a wrapper of `skellycam/__main__.py` with the patches of item 5 (no `_detach` skip)
and a probe that prints when `_call_connection_lost` raises, and a driver that connects a client, ends it, calls
`/shutdown` and times the exit of the process.

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
- `test_server_exit.py` before the code change: see the commit of the tests.

## Alternatives rejected

- **Detach the transport in the exception handler.** The handler can find the transport through the handle of the
  callback and call `Server._detach`. It fixes only the one known cause, with private names, and it gives no bound
  for any other lost connection.
- **A subclass of `uvicorn.Server` that bounds only `wait_closed()`.** It overrides a private method and keeps the
  unbounded wait for a request.
- **`os._exit` for a `SystemExit` in `entry_point()`.** It covers only that path; the cancel covers each exit.
