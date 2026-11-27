# 75CF — Decision of the user on the shutdown of the server

**Status:** absorbed into
[`specs/recorder.md#91-the-end-of-the-server-process`](../../specs/recorder.md#91-the-end-of-the-server-process),
2026-11-27 (commit to dom/server-shutdown; was accepted, 2026-11-27 (user, Q907)).

## Decision

The user wrote on 2026-11-27 (Q907): "a small lane, spec and test first, and soon: check whether the product server
hangs at shutdown when a client resets its connection (uvicorn waiting for a lost connection), and give it a
shutdown time limit if so; the same lane looks at the blocked queue feeder thread (likely the websocket log queue
that nobody reads after the connections close)."

1. **Q907.** A small lane, spec and tests first. It checks whether the product server hangs at its shutdown when a
   client resets its connection. If so, the shutdown of the server gets a time limit. The same lane looks at the
   blocked feeder thread of a queue.

## Reason

The words of the user, above. A test server of the preview tests hung in its stop after a browser reset its
connection, with no time limit. The product server builds its `uvicorn.Config` with no
`timeout_graceful_shutdown`, and the Electron app waits for the exit of the server with no time limit. The limit, its
mechanism and the other choices of the lane are proposed in
[ADR-06PW](06PW-choices-of-the-shutdown-limit-lane.md).
