# DBF8 — Choices of the agent for the certify checks of Q624 and the fixes of the review

**Status:** proposed, 2026-11-23 (agent; on the decisions of the user in ADR-493E, and the independent review of
the spec at commit 65197a7c6).

## Decision

An agent wrote section 3.6.12 of [`specs/certify.md`](../../specs/certify.md) and the tests T-CERT-112 to
T-CERT-122 on the decisions of the user in
[ADR-493E](493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md), and the fixes of the review
(items 9 to 17, tests T-CERT-123 to T-CERT-128). The spec marks these choices
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
9. The strict name filter of 9.4: NFKC first; the Apple words as whole words (a run of letters or of digits);
   a letter of another script than Latin gives `Camera vvvv:pppp`; a character outside the set gives the same;
   the cut to 60 before the pattern tests of contract rules 1 to 7, 17 and 20; any hit gives the same. Not:
   replace bad characters and remove bad parts (a removal can leave a MAC form, a repeated `www.` or a media
   extension).
10. The seed list of `known_cameras.json`: 046d:085c Logitech C922, 046d:0843 Logitech C930e, 1532:0e05 Razer
    Kiyo Pro. Not: an empty list.
11. The models that count for a pipeline check are those where it judged; rule (b) blames each failing model;
    two models with one stopped early is rule (e). Not: count each tested model.
12. A B1 row makes its model `fail` and follows rule (c); a check of another model that fails in the step of a
    wedge makes that model `partial` with `blocked_by`. Not: blame each model whose check failed.
13. A row has `module` only when its summary item exists; each gate requires only rows with its own `module`.
    Not: the pipeline gate requires the take rows always.
14. The B1 row in or after the take is `rows-complete`; `<model>:gate` needs the cycles of the first unit.
15. Known-bad from `details.gates[].failed` and its reason; the record key `nousb:<os name>`; no
    `take_error_camera` in `numbers`. Not: the gate steps (gone); `Camera (no USB id)` as the key.
16. No count of 0 on a `pass` row; no `exposure_set`, no `luma_at_m7`, no `details.pipeline.result`, no
    `details.gates` item for a gate that only waits for a check with no code. Not: keep them.
17. The build order of 3.6.7, where each step passes its own tests and a part of a test joins later. Not: one
    test in one step only.

## Reason

Each choice keeps the report short and keeps free text out of the report.
