# 8CP7 — Certify spec draft 3: the choices of the agent

**Status:** proposed, 2026-11-20 (agent).
Accepted in part by [ADR-6YGH](6YGH-acceptance-of-the-as-built-choices-of-fix-lanes-4-and-5-and-of-certify.md) on 2026-11-25: items 3a, 3b, 5, 6, 9, 11 to 14 and the codes of 15 (Q757 to Q762, Q770).

## Decision

An agent wrote draft 3 of [`specs/certify.md`](../../specs/certify.md), with the test list T-CERT-01
to T-CERT-67, on the decisions of [ADR-GVC0](GVC0-certify-decisions-of-the-user.md),
[ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md),
[ADR-C5BR](C5BR-macos-approach-probes-in-certify.md) and
[ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md), against format 1.4.0 of the contract
(`skellycertify` commit `1c9c191`). The agent made these choices. The spec marks them [A]. The
questions of section 14 of the spec ask the user about the open ones.

1. The split of each check into one test each, with the names `<label>:<group>:<condition>` (3.3,
   3.4, 4 to 8, 10.2), and the summary item computed from the named checks of five groups (3.4,
   question 1).
2. One summary item for each model; the check `<model>:units`; `module` on each camera check (the
   item name) and `Disk` on the disk checks; a reviewed model is `skipped` with `reviewed` in quick
   [C 2.7].
3. The local record `camera_checks.json` in the skellycam base folder (2.5): the key (USB id, backend,
   ABI, OS key, level); a `quick` and a `full` row; the fields `item`, `gate` and `controls` (route
   and result); a row only for an item `pass`, `partial` or `fail` (question 3); `nousb:<cleaned
   name>`; a damaged file counts as empty; an upgrade of skellycam does not make a row stale (question
   2); `details.unchecked` and `details.cameras[].checked` in the plan.
4. Phases A to H of 2.3 for the order of point 6 of ADR-KG00.
5. One camera block of `full` for each model; `same-model` for the other units (5.1, question 4).
6. The Auto checks `auto-exposure:searched` and `auto-exposure:holds-rate` at `<base>` and at 60, the
   wait of 25 s, `exposure_search.count`, the codes `auto-not-searched` and `auto-search-failed`, and
   the 60 fps fall back as `fail` `rate-low` with `fell_back` (5.3, 8.2, question 11).
7. Progress (9.6): a message before each step that runs in a child or touches a camera; none for a
   roll-up or computed check; a wait of up to 100 ms (question 9).
8. `cameras-busy` (9.7) only for a camera group in the calling process; then also the checks that do
   not touch a camera are `not-run` (question 10).
9. An interrupted run (9.8): each ended check in a progress message also carries `reason`, `module`
   and `numbers` (question 5).
10. The gate of 11.3 as nine roll-up checks `<model>:gate:<step>` and `<model>:gate`, at the base mode
    only, as the user ruled; the same gate for `verified` (11.5); the request to the owner of the
    contract about a `partial` item and a reviewed row (question 6).
11. The names and values of the diagnostics of `specs/unix-capture.md` at `75e030ef6`; `process-ended`
    reported as `crashed`; `system:kernel`; `usb_alt`; the product `usb_link` value; the answers of
    section 18.
12. The macOS approach probes of 10.7: the names `probe:<model>:<approach>[:<control>]`, the two
    kinds of probe of 10.4, the order and phases, the proof rule for a control by direction (luma
    ratio at least 1.1) and for a JPEG (DQT and DHT against the VID:PID reference), `b3-nil` and
    `b4-apple-jpeg` as `record-only`, the `approaches` field per control, the drop rules per control
    only through a maintainer-accepted row, the time limits of the probe children, and the time
    estimates.
13. `setting-lost-on-reopen` means that the config value did not read back at a later open; the
    direction rule of `settings-stick:image-effect` on a unitless route (`luma_ratio < 0.97`).
14. `test_media_dir` is accepted and not used; the disk figure stays in `numbers`; `risks` and
    `total` in the plan; the quick self-check runs only when quick checks a camera model (question
    8); phase G opens each camera also after a cancel (question 7).
15. The estimates `30 + N/4` s for quick and those of section 16; the codes `same-model`,
    `scale-too-short`, `not-camera-jpeg`, `frame-gap`, `ring-lapped`, `not-applicable`,
    `no-reference`; the notice codes `camera-wedged` and `camera-not-restored`; the sentence of
    `rate-low` is the product text.

## Reason

Each choice puts a decision of the user or a rule of the contract into a rule that a test can check,
at the lowest cost in time, or makes this spec agree with the other specs where they name the same
fact.

## Evidence

The spec cites `report-format.md` of `skellycertify` at commit `1c9c191` (format 1.4.0),
`specs/unix-capture.md` at `75e030ef6` on branch `dom/unix-capture-spec`,
`specs/camera-requests.md` at `511dc0914` on branch `dom/requests-spec`, a desk research list of the
macOS approaches, and a cross-spec review of 2026-11-20 that the supervisor gave (not tracked).

## Open work

See [open-work.md](../open-work.md).
