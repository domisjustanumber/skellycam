# MEE1 — Choices of the agent for the shape of the certify report

**Status:** proposed, 2026-11-23 (agent; after the reviews of the report and the conditions of the contract
owner).

## Decision

An agent wrote section 3.6 of [`specs/certify.md`](../../specs/certify.md) and the tests T-CERT-91 to
T-CERT-111 on the decisions of the user in
[ADR-H2A0](H2A0-decisions-of-the-user-on-the-certify-report-shape.md) and
[ADR-BW5M](BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md). The spec marks these
choices [A]. "Not:" gives the rejected alternative.

1. B1: a camera that leaves the run between two steps gets `fail` on its first check with no result, with the
   product code and `module` = its model. Not: a new row `<label>:streams` (one more row for each good camera).
2. `<model>:gate:no-hang` fails for `hung`, `crashed` and `stalled`, not for `device-removed`. Not: `hung` and
   `crashed` only (a stall then leaves `no-hang` `pass`).
3. Only a check with no code leaves `checks`; a built check whose product value is `null` keeps `not-run`
   `not-built`. Not: move the run-time case too.
4. A `same-model` check is not planned and gives no row. Not: keep the `not-run` `same-model` rows.
5. `details.not_built` is `{"camera": [...], "run": [...]}`, sorted, with `base` for the mode. Not: a flat list
   with labels (each name repeats for each camera).
6. `<label>:not-reached` has the reason of its first check and `numbers.checks`; `done` counts it as its checks.
   Not: `done` counts it as one (the progress never reaches `total`).
7. `total` is the count of rows when each planned check gives its own row, with `session:exit`. Not: `total`
   `null`.
8. No `clock:base` on Media Foundation; only the judging check of the pair `sequence` and `time-gaps`. Not: the
   twin `not-run` rows.
9. A `pass` row has no echo of the request; `decoded_by_skellycam` is not written. Not: keep the echoes.
10. Rounding: fps 2 decimals, `free_gb` an integer, ms 1 decimal. Not: full precision.
11. `exit_code` stands on each `crashed` row, also as `null`. Not: leave it out when not known (the contract asks
    for it).
12. The step names of `details.steps`; the CPU only on `open` and `take`. Not: the CPU on each step.
13. The keys of `details.limits`. Not: the limit on each row.
14. `details.cameras[]` has `result`, `failed` (without the label) and `reason`; the exposure range, the "before"
    values and `sample_time_kept` stand there. Not: the full check name in `failed`.
15. `details.gates[]` has `gate`, `failed` and `reason`; a check that is not built counts after a `fail`. Not:
    the cause in `numbers` of the gate row (the contract forbids a check name there).
16. Q598: `csv-rows` goes into `rows-complete` (`rows-differ`), `frame-count` into `group:take:rate`
    (`too-few-frames`); the same for `take-30` and `take-60`. Not: keep `frame-count` as a third row.
17. "Gate not complete" of Q610: the gate `not-run` `not-built`, a full item `partial` at most, and
    `"sign-off": "not-built"` in `gate` of the record row; `risks` of full empty today. Not: a package code in
    `evidence.reasons` (it makes each full report invalid; the contract owner gave a form with no new code).
18. Names: the file `skellycam/core/camera/known_cameras.json`; the firmware text before the OS name; the keys
    `name_os` and `name_usb`; `Continuity` gives the iPhone class. The strict filter of the review fixes and the
    seed list are in ADR-DBF8. Not: the `model` field of `camera_evidence.json` (keyed by OS).
19. `modes`: at most 32 strings of 48 characters, `modes_cut`; the bound 96 KiB for full and 64 KiB for quick
    with eight cameras at the longest form. Not: 64 KiB for the module (97 % of it for a typical eight-camera
    full report, and above it at the longest form).
20. A quick row of the record gives `unproven` at most for exposure (no image check in quick). Not: `works` from
    the read-back and the hold.
21. The sample-minus-arrival numbers stand only on the clock rows. Not: also on `rows-complete`.
22. `clock:near-arrival` passes when `sample_minus_arrival_p5_ms` is -50 ms or more (not calibrated). Not:
    `abs(p95) <= 200 ms` (it cannot fail).
23. `group:take:rate` limit 2 % for a take under 10 s, 1 % from 10 s. Not: the rate from the sample times (Q609
    keeps frames over elapsed time; Media Foundation has no proven clock base, Q585).
24. `group:in-step` is in quick and in full. Not: full only (fewer runs to calibrate the limit).
25. The run lists the cameras with no activation and reads the modes only of the cameras of `cameras`. Not: a new
    option `exclude` (the old option can do it).
26. The app text that offers the logs says that they can hold folder names and camera ids. Not: no text.
27. The pipeline item: the name `<OS>, <backend>, native JPEG`; `details.pipeline`; the kind of each check;
    rule (c) leaves the model items; rule (e) gives `partial` and `not-decided-one-model`; a passing pipeline row
    has the pipeline `module`; a take row goes to a model when one camera caused it. Not: `fail` for rule (e).
28. The local pass of a model also needs a pipeline row with each gate value `pass`, and a verified camera row
    needs `pipeline:gate` `pass`. Not: the model row alone.
29. Q613: a removable or network volume gives the notice `recording-volume-not-fixed`, not `fail`. Not: `fail`
    (many people record to a USB disk that is fast enough).
30. The names `group:cycles`, `group:restore-after-kill`, `long_take`, `group:take-300:*`; `group:cycles` is in
    `pipeline:gate` and a wedge in it counts against the model of the camera. Not: no group cycles row.
31. The build order of 3.6.7: B1 and the commit first, then the report shape, then P3, P1, P2, P4. Not: the
    order of Q575 with P3 first (it leaves B1 and the invalid evidence for later).

## Reason

Each choice keeps the report short, keeps one test in one check, and fits format 1.7.0 with no change.
