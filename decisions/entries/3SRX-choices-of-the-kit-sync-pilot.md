# 3SRX — Choices of the kit sync pilot

**Status:** proposed, 2026-11-23 (agent; waits for the user).

## Decision

An agent made these choices when it applied [ADR-X1T8](X1T8-two-way-kit-sync-adoption.md) at kit
commit 47545bc. Each one waits for the user.

1. **Open-work clean-up first.** `open-work.md` was at 91 % of its limit. The agent deleted only
   done work: the item "Format sync" (merged, ADR-3B97), the sub-item "Q574 is closed", and the
   median statistic and the sentence "Built now on `dom/fix-lane-3`" of the item of ADR-TFD7 (merged
   with fix lane 3, ADR-Z7F3 item 6).
2. **Markers.** The marker lines go around the present text. The hook `other-systems` moves after the
   block `local-hooks`. The line `!.claude/settings.json` is repeated after the block `ignores`, so
   that the line `.claude/*` of the kit does not ignore it. The block `kit-text` is before the heading
   "Other systems only through certify". The `.githooks/` text and the hook header stay outside the
   blocks.
3. **`--replace`.** The first `pull` refused 9 files and 7 blocks. The agent read each difference
   and gave `--replace` for each: no text of this repository in them is lost, except items 5 and 6.
4. **Text outside the blocks** of `decisions/README.md` takes the form of the kit template: the
   skill `change-decision-log` gives the allowed edits; the list of historical statuses has
   `evidence; replaced by XXXX`; a new line names `evidence.md`. The Evidence section moves to
   `evidence.md`, with its four rows unchanged.
5. **The citations of ADR-N2NH** in two Rules lines are not in the kit form of those rules. The
   rules stay in the skill. The test `test_the_pr_branch_is_upstream_development` moves from the
   kit test file to `tools/tests/test_repo_values.py`, with a test of the index limit 24,000.
6. **Q655.** The kit puts the placeholder of `DEFAULT_BRANCH` between backticks, so a value
   cannot give "upstream `development`" without a backtick in the value. The agent did not do that.
   The two lines say `` `development` `` until the kit changes ([open-work.md](../open-work.md)).
7. **gitleaks.** The rule `generic-api-key` reports the SHA-256 of the unit
   `.github/workflows/secrets.yml` in `kit.toml`. A reviewed allowlist after the kit block of
   `.gitleaks.toml` allows a SHA-256 in `kit.toml` only.
8. **The other-systems check.** `tools/check_other_systems.py` reads `exempt_paths`,
   `certify_spec`, `self_test` and `certify_contract` from the table `[check_other_systems]` of
   `kit.toml`. With no `kit.toml`: `.github/`, `specs/certify.md`, "the self-test of the project"
   and "the certify contract". `[values]` holds `SELF_TEST`, `CERTIFY_SPEC` and `CERTIFY_REPO` for
   the Markdown units, as `DEFAULT_BRANCH` is next to `target_branch`. `FIRST_PARTS` and `GENERIC`
   stay in the code, because the name lookup changes later (Q650). The test file of the check names
   no repository; `test_repo_values.py` tests the values of this repository.
9. **`CLAUDE.md`.** The manifest of the kit has no unit `CLAUDE.md`, so `kit.toml` needs no `skip`.
   No `CLAUDE.md` is created ([ADR-XT31](XT31-kit-adoption-choices-camera-media-check-and-fills.md)).
10. **CI.** No new step: `doc-checks.yml` runs `pytest tools/tests`, and the kit test
    `tools/tests/test_kit_sync.py` runs `check`.

## Reason

Each choice changes no rule of the user and keeps the behaviour of the tools. Items 2 and 7 keep
what git ignores and what gitleaks reports. Item 8 makes the four other-systems units hold no
repository value, as the kit test "no repository value in a kit unit" needs.

## Alternatives rejected

- A value `` development` of upstream `` or a backtick in `DEFAULT_BRANCH` (item 6): a value is a
  name, not Markdown, and the supervisor said not to work around the kit.
- Adding the other-systems units to the kit now: `propose` writes into the kit checkout, which
  another session owns.

## Open work

See [open-work.md](../open-work.md).
