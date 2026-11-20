# 68JT — Step 4a choices of the preview sender: spec items, Python API for the tests, code

**Status:** accepted, 2026-11-20 (user: accepted through the review sheets of 2026-11-20; commit to
dom/integration).

## Decision

This entry supersedes [ADR-162X](162X-step-4a-preview-spec-and-agent-choices.md),
[ADR-24FZ](24FZ-python-api-of-the-preview-sender-as-the-4a-tests-assume-it.md) and
[ADR-MZ02](MZ02-choices-of-the-4a-code.md). Each of their items is below. The user ruled no item of
step 4a directly. Each item is accepted through the review sheets of 2026-11-20.

By a link to the heading that states it:

- 162X 1 to 27: [`preview.md` 13](../../specs/preview.md#13-choices-of-the-agent), items 1 to 27
  (item 7 there is exact: `last_tried` is the last frame read with any result except `LAPPED`).

As text (the Python items that the 4a tests use and the choices of the 4a code; the spec does not
fix them):

- 24FZ 1: `PreviewRelay` uses only `read`, `read_newest`, `oversize_count` and `skipped_count` of a
  reader in `ring_readers`, and does not check its type.
- 24FZ 2: the object of `send_json` is encoded with `msgspec.json`, as
  `WebsocketServer._send_msgspec_json` does; a dict, a list and a `msgspec.Struct` are valid.
- 24FZ 3: a tick read that gives `NOT_YET_WRITTEN`, `LAPPED`, `MISSING`, `CORRUPT` or `CLOSED` feeds
  nothing to `rate` and raises nothing; only `OK`, `FLAGGED` and `OVERSIZE` feed it.
- 24FZ 4: the sender logs through `logging`, to a logger that propagates to the root logger; the
  ERROR record of 3.3 holds the camera id as text.
- 24FZ 5: `ServerFramerateCalculator(source_name, max_observations=200)` keeps `update`, `clear`
  and `current_framerate`; its duration deque has `maxlen` 1000; the count of durations is
  `current_framerate.calculation_window_size`.
- 24FZ 6: `oversize_count` and `skipped_count` are properties with no setter.
- 24FZ 7: `handle_text` runs on the event-loop thread of `run`; the fake client of the tests calls
  it with `loop.call_soon` after the send returns.
- 24FZ 8: `run` ends when its task is cancelled; it does not catch `CancelledError`.
- MZ02 1: `PreviewRelay.__init__` has `typing.no_type_check`; the hint `CameraGroupManager` stays,
  imported under `TYPE_CHECKING`.
- MZ02 2: `ServerFramerateCalculator.update` takes an `int` or a `float` `capture_timestamp_ns`.
- MZ02 3: each loop of `run` does a pass, then a tick when one is due (the first in the first loop,
  then 0.25 s after the start of the last tick), then waits 10 ms or for a ready message
  (`asyncio.timeout` around `asyncio.Event.wait`).
- MZ02 4: a pass reads `closing` again before each camera.
- MZ02 5: a ready message wakes `run` only when it changes the camera from not ready to ready.
- MZ02 6: a send that raises ends `run` with that exception; the caller ends the other tasks of the
  connection.
- MZ02 7: the calculator of a camera has the camera id as `source_name`, so
  `delivered_framerate.framerate_source` is the camera id.
- MZ02 8: a tick for a camera with no state makes the state by step 1 of 4.3.
- MZ02 9: `clear()` of each calculator comes when the tick builds its message, before the sends.

No item of these entries is stale, and no later ruling overturns one.

## Reason

The user accepted these items through the review sheets of 2026-11-20. Each old entry keeps the
reasons of its items. The Rules allow no partial supersession, so this entry places each old item.

## Open work

See [open-work.md](../open-work.md).
