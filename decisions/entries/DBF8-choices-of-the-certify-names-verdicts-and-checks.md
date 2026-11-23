# DBF8 — Choices of the agent for the certify checks of Q624

**Status:** proposed, 2026-11-23 (agent; on the decisions of the user in ADR-493E).

## Decision

An agent wrote section 3.6.12 of [`specs/certify.md`](../../specs/certify.md) and the tests T-CERT-112 to
T-CERT-122 on the decisions of the user in
[ADR-493E](493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md). The spec marks these choices
[A]. "Not:" gives the rejected alternative. The choices of the rest of section 3.6 are in
[ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md).

1. The keys `white_balance`, `white_balance_auto` and `power_line` in `details.cameras[]`. Not: one object
   `controls` (a nested object for three values).
2. The USB link hint is a notice `camera-usb3-on-usb2-link` with no check row; it fires for `bcd_usb` `0210` or
   higher on a `USB 2` link, and its text says "can". Not: a `record-only` row in quick (noise in a smoke test).
3. `system:memory` needs `ring_total_size` of each ring of the product, and the open still runs after a `fail`.
   Not: a fixed 26.5 MiB for each camera (it changes with the mode).
4. `group:take-again` is one check: "a second take works". Not: the two take rows again.
5. `report:rules` checks the report without its own row; the validator moves into the package. Not: keep the
   validator in the tests (the shipped package has no tests).
6. `system:camera-access` on Windows uses the rule of 10.2: with no access each camera is `not-run`
   `no-access`. Not: `fail` (the person can change a setting; the camera is not at fault).
7. `system:power` keeps a closed list of power plans, `other` for a plan of the person. Not: the plan name (the
   person can name a plan).
8. `identity:stable` and `identity:unique` stay: they test the `camera_id` that the product uses for the
   settings, the restore record and the selection of the UI. Not: drop them with the unit id.

## Reason

Each choice keeps the report short and keeps free text out of the report.
