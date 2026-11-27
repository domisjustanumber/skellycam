# 06PW — Choices of the shutdown limit lane

**Status:** absorbed into
[`specs/recorder.md#91-the-end-of-the-server-process`](../../specs/recorder.md#91-the-end-of-the-server-process),
2026-11-27 (commit to dom/server-shutdown-limit; was accepted, 2026-11-27 (user, Q924 of
[ADR-9V4Y](9V4Y-decisions-of-the-user-on-the-shutdown-lane-q924-to-q928.md)); was proposed, 2026-11-27 (agent)).

## Decision

Q924 accepts these choices of the lane, subject to the review; the limit comes in the order of Q928.

1. **The exit does not wait for the feeder thread of the websocket log queue** (9.1 item 1): `entry_point()` calls
   `get_websocket_log_queue().cancel_join_thread()` after `configure_logging`.
2. **One DEBUG line for each suppressed `ConnectionResetError`** (9.1 item 2), with the message of the context.
   The handler stays.
3. **The limit is 5 s** (9.1 item 5): `skellycam/__main__.py` sets `timeout_graceful_shutdown=SHUTDOWN_CONNECTION_LIMIT_S`
   (5) in its `uvicorn.Config`, only after the shield of 9.1 item 3. That is the only `uvicorn.Config` of the
   product; the one of `decisions/scripts/measure_preview_m_prv.py` does not change after its entry.
4. **The tests** (9.1 item 4). `test_server_exit.py` starts the real server with `server_exit_child.py` (no
   telemetry, no bytecode pass, a temporary base folder and log file). A server whose port is in use ends with an
   error code. A lost connection is made the same on each system: the child skips `Server._detach` for its first
   connection; the test is split as Q669 says, and `test_pace_marker.py` names both halves. `test_entry_point.py`
   checks the cancel.

## Reason

1. With no open websocket, nobody reads the queue. The feeder thread then waits in `_send_bytes` on a full pipe,
   and the exit handler `_cleanup_log_queue` of `skellylogs` waits for it with `join_thread`. The records that the
   cancel drops at the exit have no reader.
2. The handler hid the 10054 error of the stop of the test server. The default level is TRACE (`LOG_LEVEL` of
   `skellycam/__init__.py`), so the DEBUG line shows in the console and in the log file.
3. The product did not hang (0 of 39 runs), so a first version that added the limit at once was taken out: a review
   found that the limit left a take unfinished on each path but the shutdown endpoint
   ([evidence](../evidence/cancelled-take-stop-at-a-shutdown-limit-20261127.md)). Q928 put the shield first. The 5 s
   came from the brief of the supervisor, not from the user (the 5 s of Q906 is for the test server).
4. A port-in-use start is the case that hung; the skipped `_detach` gives a lost connection with no race.

## Evidence

Windows 11, CPython 3.13.18, uvicorn 0.54.0, Chromium 1255 of Playwright (headless); local scratchpad scripts, not
tracked (a wrapper of `__main__` with a probe on `_call_connection_lost`, and a driver that ends a client, calls
`/shutdown` and times the exit).

- **No hang with reset clients: 0 of 39 runs**, exit 0.18 s to 1.16 s after `/shutdown`. Clients: a normal close
  (1), `SO_LINGER` 0 resets before and after `/shutdown` (1, 4), a close frame 1001 then a reset (4), a killed
  client (4), a Chromium page that stays open, is killed or closes with 1001 (8 each). The probe never printed. The
  test server that hung (3 of 20) sent a preview stream and closed the websockets itself.
- **The port in use: 3 of 3 runs did not end in 20 s.** The main thread waited in
  `_cleanup_log_queue` → `Queue.join_thread`; the feeder thread in `queues._feed` → `connection._send_bytes`.
- **An idle server** with no websocket for 10 s: the feeder waited for items, and the exit took 1.11 s.
- With the cancel and the limit, ten lost-connection runs ended 5.66 s to 5.75 s after `/shutdown`.

## Alternatives rejected

- **Detach the transport in the exception handler**: private names, and it bounds only the one known cause.
- **A subclass of `uvicorn.Server` that bounds only `wait_closed()`**: a private method, and no bound for a request.
- **`os._exit` for a `SystemExit` in `entry_point()`**: only that path; the cancel covers each exit.
