# F6C3 — Decisions of the user on the certify report fields

**Status:** accepted, 2026-11-23 (user; questions Q557 to Q559 after the analysis of 2026-11-21 of the
certify report).

## Decision

The user decided these items on 2026-11-23. They are not built.

1. **Q557.** The module report of certify gets eight additions: the commit and the tree state; the
   failure facts of the product on each failed or hung camera row (native code, native domain, call,
   stage, failed calls, first failure code); a start time and a duration for each check; a camera
   inventory (USB link, controller, hub depth, firmware revision, driver, mode list); frame timing on
   each row that measures a rate, on each operating system; the warning codes of the take, the
   position of the first gap and the exit codes; the CPU load during the open and the take; the
   exposure and gain context on the settings rows.
2. **Q558.** A salted local hash is a stable id of a camera unit, so that two runs on one system can
   be compared unit by unit. The `camera_id` itself stays forbidden in a report.
3. **Q559.** Certify keeps the camera logs of the last run on the system of the person. Certify never
   sends them.

[`specs/certify.md`](../../specs/certify.md) section 3.5 holds the fields. The names, places and
bounds there are choices of the agent in
[ADR-NQ77](NQ77-choices-of-the-certify-report-fields.md) (proposed).

## Reason

The report said which check failed, but rarely why. A developer with no access to the system of the
person could not find the cause of most failures from the report alone.
