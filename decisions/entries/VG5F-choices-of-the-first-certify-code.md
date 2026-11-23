# VG5F — Choices of the first certify code (Windows first)

**Status:** absorbed into
[`specs/certify.md#certify-specification-what-a-certify-run-of-skellycam-measures-draft-3`](../../specs/certify.md#certify-specification-what-a-certify-run-of-skellycam-measures-draft-3),
[`specs/certify.md#91-certify_planlevel-a`](../../specs/certify.md#91-certify_planlevel-a),
[`specs/certify.md#191-the-first-code-u`](../../specs/certify.md#191-the-first-code-u),
[`specs/certify.md#192-the-review-fixes-and-format-160-u`](../../specs/certify.md#192-the-review-fixes-and-format-160-u),
2026-11-23 (commit to dom/absorb-2; was accepted, 2026-11-21 (user; commit to dom/accept-choices; was proposed,
2026-11-21 (agent; the user approved the build, the supervisor gave the scope))).

## Decision

The first step builds `skellycam/core/certify/` for [`certify.md`](../../specs/certify.md): `certify`, `certify_plan`,
the quick checks of Windows native capture, the gate roll-ups of a full run, phase G, the record and the report. A
check that is not built is `not-run` `not-built`. The agent made these choices where the spec is silent or unclear:

1. Not built: `group:open` with the retry alone (4.2), `self:hang-100ms:*`, the camera block of `full`, the group,
   system and self checks of `full`. The `full` list has no check of a mode above `<base>`.
2. The plan reads no modes, so its names use `<base>` `1280x720@30`. `total` is the count of the planned checks.
   A quick plan with no camera model to check has `total` 0.
3. A run with no `cameras` option checks each camera that is not reviewed, also a model that is in the record
   (2.4, C 2.7). 9.1 says that such a model gives `total` 0; this step follows 2.4.
4. `time-gaps` is in each list that has `sequence`. With a sequence number it is `not-run` `has-sequence`, a new code.
5. A `clock`, `sequence` or `time-gaps` check whose diagnostics key is null or `unknown` is `not-run` `not-built`.
   The Media Foundation source gives `clock` `unknown` and no `long_intervals`, so the Windows gate cannot pass yet.
6. `clock:near-arrival` passes when the absolute p95 of sample minus arrival is 200 ms or less.
7. A product rate-check failure at the open gives `opens` `pass` and `rate` `fail` with the product code. `too-dark`
   for `rate` is not built: a camera that fails its rate check gives no ring frame.
8. In the summary item, `sequence` `not-run` `no-sequence` counts as passed when `time-gaps` passed, and the reverse.
9. A camera that is not `ready` before the take leaves the group (a record start needs each camera `ready`).
10. The session child clears its parent mark (`multiprocessing.process._parent_process`), because the pubsub of
    the product refuses a camera group in a process with a parent. It sets up logging as a camera process does.
11. A ring watch keeps the SHA-256 of each ring frame by source frame number. A frame that the capture check flagged
    counts as damaged in `native-jpeg:valid`. `ring-equals-mkv` compares each MKV block that is not `missing` with
    the ring hash and with the hash set of the record start; with no compared frame it is `not-run` `ring-lapped`.
12. `gaps-explained`: the rule changed in [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md).
13. A refused run (`cameras-busy`) has no summary item, so its checks have no `module`.
14. Phase G after a stop, a time-out or a crash: the rules changed in [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). The plain open closes with
    `restore=False`.
15. After a time-out or a crash: the rules changed in [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). `full` has one session limit of 240 s in this step.
16. The report has no `id`, and `commit` and `tree_modified` are null, so it is not yet valid as evidence. The
    schema is in [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md). The exit check of the session child is `session:exit`, with no `module`.
17. The record holds `controls.exposure` for the route of the settings checks only.
18. `system_evidence` comes from the `systems` rows of the evidence file.

## Reason

Each choice is the smallest reading that makes the plan, the run and the report agree with the contract and
the decisions of the user, with no change of product code.

## Consequences

- The user kept item 3 on 2026-11-21 (question 1 of [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md)).
- Item 10 changed in [ADR-X8XE](X8XE-choices-of-the-certify-review-fixes-and-format-1-6-0.md).

## Alternatives rejected

- A change of the pubsub guard of the product: other agents change the product at the same time.
- A `time-gaps` check that is only in the report when the source has no sequence number: then `total` could not
  equal the count of the reported checks.
