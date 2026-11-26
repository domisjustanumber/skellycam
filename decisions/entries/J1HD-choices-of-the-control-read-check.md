# J1HD — Choices of the agent for the certify check of the control read and the rule that follows from it

**Status:** proposed, 2026-11-25 (agent; builds Q811 of
[ADR-5PAR](5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md); commit to
dom/exclusive-access-spec).

## Decision

`certify.md` 20.9 marks each item as [R n].

1. The check `<label>:control-read:gaps` runs 30 s with the read of 11.4 on, then 30 s with it off. The off half uses
   a new product setting `SKELLYCAM_CONTROL_READ=0` in the session child, as `SKELLYCAM_RESTORE_CONTROLS=0` does for
   the restore.
2. The pass rule: no read overlaps a frame interval above 100 ms (the gap rule of U16), or the stream with no read
   has such gaps too (then the camera, not the read, makes them). A hung read is `fail` `hung`. The reason code is
   `read-gap`; the numbers are `reads`, `read_ms_p50`, `read_ms_max`, `gap_at_read_max_ms`, `gap_no_read_max_ms` and
   `reads_over_limit`; the limit `control_read_gap_ms` is in `details.limits`.
3. The local row of a `full` run gets `control_read` `ok` or `harms`; a reviewed report can add the limit code
   `control-read-harms` to the shipped row.
4. A harmed model pauses the read during a take on each build, not only on a build with no control monitor: the
   harm comes from the requests, whatever finds the changes.
5. The check runs in phase D, for the first unit of each model, and adds about 60 s for each model to a full run.
6. The tests T-CAP-146 (the rule) and T-CERT-149 (the check).

## Reason

Q811 asks for a check for each model and a rule that follows from it; the user did not fix its form. A run with the
read off is the baseline that tells a gap of the read from a gap of the camera.

## Open work

[open-work.md](../open-work.md)
