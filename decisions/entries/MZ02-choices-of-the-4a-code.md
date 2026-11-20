# MZ02 — Choices of the 4a code that the spec and ADR-24FZ do not fix

**Status:** superseded by [68JT](68JT-step-4a-choices-of-the-preview-sender.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent)).

## Decision

The code of step 4a follows [`specs/preview.md`](../../specs/preview.md) and
[ADR-24FZ](24FZ-python-api-of-the-preview-sender-as-the-4a-tests-assume-it.md). The code is in
`skellycam/api/websocket/preview_relay.py`. An agent made the choices below.

1. **Type check of the manager.** `PreviewRelay.__init__` has the decorator `typing.no_type_check`.
   The hint `CameraGroupManager` stays, and its import is under `TYPE_CHECKING`. Thus beartype does
   not check the manager at run time, and the fake manager of the tests is valid.
2. **Hint of the calculator.** `ServerFramerateCalculator.update` accepts an `int` or a `float` for
   `capture_timestamp_ns`. The ring `arrival_ns` is an `int`, and beartype refuses an `int` for a
   `float` hint.
3. **Order in `run`.** Each loop does a pass, then a tick when one is due, then waits for 10 ms or
   for a ready message. The first tick comes in the first loop. The next tick is due 0.25 s after
   the start of the previous tick. The wait is `asyncio.timeout` around `asyncio.Event.wait`.
4. **`closing`.** A pass reads `closing` again before each camera. Thus a pass that waits on a send
   reads nothing after `closing` becomes `True`.
5. **A ready message** wakes `run` only when it changes the camera from not ready to ready.
6. **A send that raises** ends `run` with that exception. `run` catches nothing. The caller ends the
   other tasks of the connection, as the test route and `WebsocketServer.run` do.
7. **The calculator of a camera** has the camera id as its `source_name`. Thus
   `delivered_framerate.framerate_source` is the camera id.
8. **A tick for a camera with no state** makes the state with the rule of step 1 of 4.3, as a pass
   does.
9. **`clear()`** of each calculator comes when the tick builds its message, before the sends. No
   other code feeds the calculators between the two, so the result is the same as a `clear()`
   after the send.

## Reason

- Each choice is the smallest that the tests and the spec need.
- Item 1: 24FZ item 1 makes the readers and the manager duck typed. A protocol class or `object`
  as the hint is more code or less information for the reader.
- Item 6: the send functions of `WebsocketServer` already send nothing on a closed websocket, and
  its tasks end through `_signal_shutdown`.

## Alternatives rejected

- Catch `WebSocketDisconnect` in `run`, as the old relay does: `run` then needs the exception types
  of the websocket, and the send functions are injected.
- A tick in its own task: two coroutines would then read the rings and send.

## Open work

See [open-work.md](../open-work.md).
