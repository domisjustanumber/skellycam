# 8MFJ — Decision of the user on the preview CPU target: 20 % of one core

**Status:** absorbed into [`specs/preview.md#84-targets-of-4a-each-one-to-measure-in-4a`](../../specs/preview.md#84-targets-of-4a-each-one-to-measure-in-4a),
2026-11-25 (commit to dom/exclusive-access-spec; was accepted, 2026-11-25 (user; the supervisor asked Q763 in a
grilling session)).

## Decision

Q763 (session Q35). The target for the event-loop CPU of the preview sender (4 cameras at 1080p30, one client that
keeps up) is at most 20 % of one core. It replaces the 19 % that the supervisor proposed for A10 of
[ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md). The words of the user: "Q35 - 20%". No test enforces
the target.

## Reason

The 12 % of the first run was measured in the legacy mode of uvicorn. The shipping mode measured 13 to 19 % in six
runs, median 16 % ([ADR-HDC9](HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md)). 20 % leaves one
point above the worst run.
