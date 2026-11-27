# 75CF — Decision of the user on the shutdown of the server

**Status:** accepted, 2026-11-27 (user, Q907).

## Decision

The user wrote on 2026-11-27: "Q906-907 agree".

1. **Q907.** The question was: a small lane, spec and test first, and soon. It checks whether the product server
   hangs at its shutdown when a client resets its connection (uvicorn that waits for a lost connection). If so, the
   shutdown gets a time limit. The same lane looks at the blocked feeder thread of a queue.

Q907 is also item 18 of ADR-BPP8 on `dom/preview-4b-tests` (Q906, item 17, is the limit of its test server). At the
merge of the two branches, this entry and that item must keep one home: one of them points to the other.

## Reason

The words of the user, above. A test server of the preview tests hung in its stop after a browser reset its
connection. The product server builds its `uvicorn.Config` with no `timeout_graceful_shutdown`, and the Electron app
waits for the exit of the server with no time limit. The lane found no hang of the product (0 of 39 runs), so this
branch builds no limit; the choices and the open question are in
[ADR-06PW](06PW-choices-of-the-shutdown-limit-lane.md).
