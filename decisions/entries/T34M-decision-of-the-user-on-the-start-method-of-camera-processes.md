# T34M — Decision of the user on the start method of camera processes (Q651)

**Status:** accepted, 2026-11-23 (user; the supervisor asked the question and relayed the answer).

## Decision

The user decided on 2026-11-23: "Q651 agree". The question as put to the user: "Do you accept this route: the
library leaves the global setting alone, skellycam's own app sets spawn, a fork start on Linux is refused with a
clear reason, and FreeMoCap adds one line at the top of its `__main__`?", later narrowed to "Should fix round 4 go
ahead with skellycam's half only, with nothing decided for FreeMoCap?".

1. `import skellycam` does not set the global start method of `multiprocessing`.
2. The program entry point of skellycam sets `spawn`.
3. A start of a camera process with `fork` on Linux is refused with a clear reason that names the fix.
4. Nothing is decided for FreeMoCap. The words of the user: "I think this needs to be part of a wider review of how
   the whole of freemocap works on linux".

[`unix-capture.md`](../../specs/unix-capture.md) 4.12 states it. The choices of the agent that build it (the reason
code and its text, the place of the check, `forkserver`, the test session) are in
[ADR-HQE5](HQE5-choices-of-fix-lane-4.md) (proposed).

## Reason

CI run 45214740615: on Linux a forked camera process of a main process that had decoded video with PyAV waited for
FFmpeg threads that the fork did not copy, and never answered. A start method set at `import skellycam` did not
reach a host that made a `multiprocessing` object first (FreeMoCap makes its log queue first), and it stopped a
host from setting the method after the import (the review of 2026-11-23).

## Alternatives rejected

- A `spawn` context object inside skellycam for each shared object: the host gives objects of its own context to
  the camera processes (the kill flag, the log queue of `skellylogs`, the objects of the FreeMoCap workers), and a
  lock of the `fork` context cannot go to a `spawn` child. It needs an API change of two repositories.
- `spawn` set at `import skellycam`: the two faults above.

## Open work

[open-work.md](../open-work.md)
