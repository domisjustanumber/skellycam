# 24FZ — Python API of the preview sender, as the 4a tests assume it

**Status:** proposed, 2026-11-19 (agent).

## Decision

[ADR-WB08](WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md) accepts
[`specs/preview.md`](../../specs/preview.md). Section 7 of the spec gives the module, the names and
the constructor of the sender. Section 5.2 gives the two reader properties. The failing tests of
step 4a in `skellycam/tests/preview/` also use the items below. The spec does not fix them. An
agent chose them.

1. **Readers by duck typing.** `PreviewRelay` uses only `read`, `read_newest`, `oversize_count` and
   `skipped_count` of a reader in `ring_readers`. It does not check the type of the reader. The tests
   put a spy (a wrapper of a real reader) and a stub reader there.
2. **The object of `send_json`.** The tests encode it with `msgspec.json`, as
   `WebsocketServer._send_msgspec_json` does. Thus a dict, a list and a `msgspec.Struct` (for example
   `CurrentFramerate` in `delivered_framerate`) are valid. The client gets the JSON of section 6.2.
3. **A tick read with no frame.** When `read_newest` gives `NOT_YET_WRITTEN`, `LAPPED`, `MISSING`,
   `CORRUPT` or `CLOSED`, the tick feeds nothing to `rate` and raises nothing. It feeds `rate` only
   from `OK`, `FLAGGED` and `OVERSIZE`.
4. **Log records.** The sender writes its records through the Python `logging` module, to a logger
   that propagates to the root logger. The ERROR record of section 3.3 holds the camera id as text.
5. **`ServerFramerateCalculator`.** It keeps its constructor `(source_name, max_observations=200)`,
   `update`, `clear` and `current_framerate`. Its duration deque keeps `maxlen` 1000. The tests read
   the count of durations from `current_framerate.calculation_window_size`.
6. **Reader properties.** `oversize_count` and `skipped_count` are properties with no setter. An
   assignment raises `AttributeError`.
7. **Threads.** `handle_text` runs on the event-loop thread of `run`. The test route calls it there.
   The fake client of the fake tests calls it with `loop.call_soon`, after the send returns.
8. **Cancel.** `run` ends when its task is cancelled. It does not catch `CancelledError` and continue.

## Reason

- The tests must fix one form for each call and each value that they read. The user decides the API
  before the code, as for
  [ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md).
- Each item is the smallest that the tests need. The spec fixes the rest.
- Item 2 lets 4b give `send_json` the existing send function of `WebsocketServer` with no change.

## Consequences

- The tests read the behaviour, not the state of section 4.2. For example, "camera A is ready" is
  "a new frame of A goes out before its safety net".
- T-PRV-19 runs its passes through `run`. The stub reader gives the tick no frame, and the spy counts
  only the calls of `read`, so the tick reads do not count.

## Alternatives rejected

- A method for one pass (T-PRV-19 "calls the passes directly"): the spec names no such call. A new
  public method only for a test is more API.
- A read-only view of the state of section 4.2: the behaviour shows each state change that the tests
  need.
- A fake clock: the spec names no clock seam, and its pass criteria are in real time. The tests use
  the real clock with the loose limits of section 9.2.

## Open work

See [open-work.md](../open-work.md).
