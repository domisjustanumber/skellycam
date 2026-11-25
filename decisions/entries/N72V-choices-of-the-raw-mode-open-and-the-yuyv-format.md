# N72V — Choices of the raw-mode open and the YUYV format

**Status:** proposed, 2026-11-25 (agent).

## Decision

The user decided Q807 and Q808
([ADR-B95N](B95N-decisions-of-the-user-on-the-raw-mode-open-the-yuyv-format-and-the-3b-choices.md)).
An agent chose the items below. Section 22.2 of
[`specs/windows-capture.md`](../../specs/windows-capture.md) marks each one [N72V n]. T-CAP-154 and
T-CAP-155 test them.

1. **Which raw mode.** When the requested size has both, YUY2 comes before NV12. The rate follows the
   rules of 7.5 for the raw format: the nearest rate within 0.5 fps, or the auto rate of V2.
2. **The log line.** One line at INFO for each open of the raw mode. It holds the camera ID, the words
   "no MJPG mode" and the opened format (`YUY2` or `NV12`). The test reads the format with a pattern.
3. **The whole-request check.** The check of 7.5 in the main process applies the same rule with
   `capture_modes`. Thus the request is not refused with "no mode at 30 fps or more" when the raw mode
   is at the floor.
4. **The format of the take.** `requested.capture_format` is the opened format, not the requested
   format: a camera that opened YUY2 by Q807 records `YUYV`. An MJPG camera records `MJPG`.

## Reason

- Item 1: YUY2 keeps more chroma (4:2:2), and SFF-800 already lists `YUYV`.
- Item 2: a fixed phrase and the format let a consumer and a test find the line.
- Item 3: the main process must not refuse a request that the camera can serve.
- Item 4: the take must say what the camera gave, as `capture.<id>.mode` does (recorder.md 6.7).

## Alternatives rejected

- NV12 before YUY2: NV12 has less chroma and no SFF-800 value yet.
- The requested format in the take: it would say `MJPG` for frames that came from YUY2.

## Open work

See [open-work.md](../open-work.md).
