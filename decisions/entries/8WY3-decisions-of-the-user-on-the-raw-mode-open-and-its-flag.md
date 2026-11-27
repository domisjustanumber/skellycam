# 8WY3 — Decisions of the user on the raw-mode open and its flag (Q845, Q846)

**Status:** absorbed into
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
2026-11-26 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-26 (user, relayed by the supervisor)).

## Decision

The words of the user on 2026-11-26: "Q845 - what impact will this have on GPU acceleration of
encode/decode of either JPEG or h.264? ... Otherwise agree to Q842-855", then "agree to all".

1. **Q845.** Items 1 to 4 of
   [ADR-N72V](N72V-choices-of-the-raw-mode-open-and-the-yuyv-format.md) are accepted as written: YUY2
   before NV12; one INFO log line for each open of the raw mode; the main process does not refuse the
   request; the take records the opened format. The order of YUY2 and NV12 stays a one-line change.
2. **Q846.** No UI flag shows the raw-mode open. The log line and the `capture_format` of the take are
   enough for now.

## Reason

- The user decided both items.
