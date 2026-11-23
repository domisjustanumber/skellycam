# C5BR — macOS: certify tries each approach for exposure and for the camera's JPEG

**Status:** absorbed into
[`specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a`](../../specs/certify.md#107-macos-the-approach-probes-for-exposure-and-for-the-cameras-jpeg-u-a),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-20 (user, relayed by the supervisor)).

## Decision

The user ruled: on macOS, a certify run must try every approach that might work for exposure control
and for the delivery of the camera's own JPEG, for now. The test is trimmed once a working approach
is found.

The supervisor relayed with the ruling, as the way to apply it in
[`specs/certify.md`](../../specs/certify.md) 10.7:

- The approaches are probes that certify owns. The product uses only what the Linux and macOS
  capture spec (`specs/unix-capture.md` 4.4.10, branch `dom/unix-capture-spec`) allows.
- The safe probes run in the safe part of the run. The endpoint-0 and exclusive-open probes (A5 to A8
  of the approaches list) run in the risky phase at the end.
- The Kiyo Pro runs last in each step. On a wedge, the camera is marked dead and is never revived.
- The probes run once for each camera model, not for each unit, as a model is checked one time on a
  system ([ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md) item 3).

The user accepted the longer macOS full run for now, and A7 and A8 run only after A5 and A6 failed
([ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md)).

## Reason

The macOS paths for a manual exposure and for the camera's own JPEG are not proven on any camera of
this project. One run that tries each approach tells which one works.

## Open work

See [open-work.md](../open-work.md).
