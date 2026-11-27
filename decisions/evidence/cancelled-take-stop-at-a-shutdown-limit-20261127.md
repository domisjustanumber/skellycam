# A cancelled take stop at a shutdown limit (review of 2026-11-27)

Evidence for the open question of [ADR-06PW](../entries/06PW-choices-of-the-shutdown-limit-lane.md): why the
branch `dom/server-shutdown` builds no `timeout_graceful_shutdown`. Code facts at 43f9fa003 with uvicorn 0.54.0. An
independent review found them; the lane agent checked each line in the code.

## What a limit does

1. At the limit, uvicorn cancels each request task that still runs (`uvicorn/server.py` 296-307,
   `t.cancel(...)`). Then it runs the lifespan end (309-311).
2. A cancelled `/record/stop` stops in `CameraGroup._end_take` at
   `await asyncio.to_thread(self._collect_results)` (`camera_group.py` 846). Its `finally` (851-855) sets
   `self.take = None` and resets `first_recording_frame_number` and `last_frame`. So `take.finish` never runs.
3. The lifespan end then calls `group.close()`. It stops a take only when `self.take is not None` (938-944), so it
   does not stop the take again. The manifest stays `recording`.
4. Not verified: a camera that had not reached the last frame may then write a wrong frame count
   (`camera_orchestrator.py` 118-126, `camera_loop.py` 854-883).

## The paths

- Affected: Ctrl-C (SIGINT), Ctrl-Break (SIGBREAK, `server.py` 45-50), a SIGTERM from outside, and the kill flag that
  a fault sets (`websocket_server.py` 243, 272, 323, 381; `camera_group.py` 218): each starts the shutdown of uvicorn
  while a request can still run. Also `DELETE /group/close/all` during a take (its close stops the take in
  `_end_take`), and a `/record/start` that is cancelled inside `asyncio.to_thread(start_take, ...)`
  (`camera_group.py` 685).
- Safe: the shutdown endpoint of the app. `close_then_kill` closes the groups first (under `_end_lock`), then the
  kill flag is set, then the worker monitor waits for `wait_for_recording_save`, and only then it raises SIGTERM.

## A fix for a later lane (suggested by the review)

Run the body of `stop_recording` (and of `start_recording`) as a task under `asyncio.shield`, so a cancelled request
does not cancel the take end. Test first: "Ctrl-C or SIGTERM during a slow stop ends with the manifest `finished`".
Then add the limit.

## A fault that exists today (not from this lane)

A second Ctrl-C sets `force_exit` (`server.py` 354). uvicorn then skips the lifespan end (`server.py` 310), which
ends a running take through the take level. So a second Ctrl-C during a take can already leave the manifest
`recording`.
