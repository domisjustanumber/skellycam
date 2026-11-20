# 8CP7 — Certify spec draft 3: the choices of the agent

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent wrote draft 3 of [`specs/certify.md`](../../specs/certify.md), with the test list T-CERT-01
to T-CERT-57, on the decisions of [ADR-GVC0](GVC0-certify-decisions-of-the-user.md),
[ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md) and
[ADR-C5BR](C5BR-macos-approach-probes-in-certify.md), against format 1.3.0 of the contract
(`skellycertify` commit `f7a1831`). The agent made these choices. The spec marks them [A]. The
questions of section 14 of the spec ask the user about the open ones.

1. The row of a unit (3.3), in order: `skipped-busy`, `fail`, `record-only`, `pass`, `partial`. A
   base pass with a claim that did not pass or could not judge (for example `too-dark`) is `partial`,
   as the contract defines `partial`. The check `<label>` gives `partial` as `record-only` with the
   reason `partial`.
2. One summary item for each model from the rows of its units (3.3, question 1); the check
   `<model>:units`; `module` on each camera check (the item name) and `Disk` on the disk checks; no
   use of `skipped` with `reviewed`.
3. The record of checked models (2.5): the file `checked_models.json` in the folder `certify/` of the
   skellycam data folder; the key is the USB id, the backend and the OS key (question 2); a row only
   for an item `pass`, `partial` or `fail` (question 3); `nousb` and the cleaned name for a camera
   with no USB ids; a damaged file counts as empty; `details.unchecked` and
   `details.cameras[].checked` in the plan. The record does not change which cameras `certify()`
   checks.
4. Phases A to H of 2.3 for the order of point 6 of ADR-KG00. With the restore in the product, phase
   A needs no open, and phase G of quick needs no open.
5. One camera block of `full` for each model; `same-model` for the other units (5.1, question 4).
6. The check `<label>:auto-exposure:<w>x<h>@60`, the number `searches` and the code
   `auto-not-searched` (5.3, question 6).
7. Progress (9.6): a message before each step that runs in a child or touches a camera; none for a
   computed check; a wait of up to 100 ms to keep 10 messages each second (question 7).
8. `cameras-busy` (9.7) only for a camera group in the calling process; then also the checks that do
   not touch a camera are `not-run` with it (question 8).
9. An interrupted run (9.8): each ended check in a progress message also carries `reason`, `module`
   and `numbers`, and freemocap writes the report from its progress file (question 5).
10. One record file `camera_checks.json` of the Linux and macOS spec for the checked models and the
    local pass; a `quick` row marks a model as checked, and only a `full` row with `pass` or
    `partial` is a local pass (2.5, 11.3, question 9).
11. The alignment with the Linux and macOS spec draft 2: its diagnostics keys and values, call
    names, failure codes and `abi` taken as they are, with `process-ended` reported as `crashed`;
    `system:kernel`; `usb_alt`; one `controls` and one `timings` check; the keys `restore_ok` and
    `restore_failed`; the answers of section 18.1 and the 7 differences of 18.2 (question 10).
12. The macOS approach probes of 10.7 for the ruling of ADR-C5BR: the names
    `probe:<model>:<approach>`, the two kinds of probe of 10.4, the order and phases, the proof rules
    for a control and for a JPEG, the `jpeg_reference` and `approaches` fields of the evidence file,
    the drop rules only through a maintainer-accepted row, and the time estimates (questions 11 and
    13).
13. `setting-lost-on-reopen` means that the config value did not read back at a later open.
14. `test_media_dir` is accepted and not used. The disk figure stays in `numbers`, not in a
    `benchmark` item. Only a `pass` item counts toward `verified`.
15. The estimates `30 + N/4` s for quick and those of section 16; the codes `same-model`,
    `not-linux`, `auto-not-searched` and `partial`; the sentence of `rate-low` is the product text;
    the two other contract requests wait for the user (question 12).

## Reason

Each choice puts a decision of the user or a rule of the contract into a rule that a test can check,
at the lowest cost in time, or makes this spec agree with the Linux and macOS spec where the two specs
name the same fact.

## Evidence

The spec cites `report-format.md` of `skellycertify` at commit `f7a1831` (the head of `main` on
2026-11-20, format 1.3.0), and `specs/unix-capture.md`, draft 1, on branch `dom/unix-capture-spec`,
sections 4.4.10, 4.5, 4.6 and 4.9 of draft 2 (commit `d08de113a`), and a desk research list of the
macOS approaches that the supervisor gave (not tracked).

## Open work

See [open-work.md](../open-work.md).
