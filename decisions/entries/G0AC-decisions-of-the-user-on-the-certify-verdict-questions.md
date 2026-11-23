# G0AC — Decisions of the user on four questions of the certify report shape

**Status:** accepted, 2026-11-23 (user; questions Q620 to Q623, the questions 13 to 16 of section 14 of the
certify spec; the supervisor relayed the answer "Q620-Q623 agree").

## Decision

The user decided these items on 2026-11-23. They are not built. [`certify.md`](../../specs/certify.md) sections
3.6.2, 3.6.10, 11.3 and 11.5 mark them.

1. **Q620.** Quick on Linux and macOS keeps its clock rows: `clock:base`, `clock:before-arrival`,
   `clock:near-arrival` and one of `sequence` and `time-gaps`.
2. **Q621.** A failed group take row counts against one model when one camera caused it: the take error names
   that camera, or exactly one camera of the take failed its `rows-complete` while another model passed it.
3. **Q622.** A pipeline check that fails on each tested model counts against the pipeline. The pipeline item
   fails, and the model items do not change.
4. **Q623.** The local pass of a model and its verified row also need `pipeline:gate` `pass`.

These items accept the choices 27 (in part: rule c and the take rows) and 28 of
[ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md). Question 17 of section 14 (the undecided proposals of
the gap review) stays open: the user asked for more detail.

## Reason

A camera that a fault clearly names must not fail the pipeline, and a fault that each camera shows is not a fault
of the cameras. Native capture on a system needs a working pipeline as well as a working model.

## Open work

[open-work.md](../open-work.md)
