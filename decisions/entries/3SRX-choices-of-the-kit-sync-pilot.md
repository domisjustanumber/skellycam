# 3SRX — Choices of the kit sync pilot

**Status:** proposed, 2026-11-23 (agent; waits for the user).

## Decision

An agent made these choices when it applied [ADR-X1T8](X1T8-two-way-kit-sync-adoption.md) at kit
commit 47545bc (round 1), 57a878c and 05a3d2d (round 2), 617fbf4 (round 3) and 89cd90b (round 4).
Each one waits for the user.

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
5. **The citations of ADR-N2NH.** The kit text cites no entry of a repository. So one repository
   line after the skill block `log-change-rules` cites ADR-N2NH for its two rules. Kit 05a3d2d says
   "a heading of a normative document" again. The test `test_the_pr_branch_is_upstream_development` moves from the
   kit test file to `tools/tests/test_repo_values.py`, with a test of the index limit 24,000.
6. **Q655.** At 47545bc the kit put the branch placeholder between backticks, so no value gave
   "upstream `development`". Kit 57a878c has the value `DEFAULT_BRANCH_TEXT` with no backticks
   around it. `kit.toml` sets it to "upstream `development`", and the two skill lines say that now.
   `target_branch` and `SECRET_SCAN_BRANCHES` keep the bare names.
7. **gitleaks.** The rule `generic-api-key` reports the SHA-256 of the unit
   `.github/workflows/secrets.yml` in `kit.toml`. Round 1 added a reviewed allowlist after the kit
   block of `.gitleaks.toml`. Kit 57a878c has the same allowlist in its block, so round 2 deleted the
   copy.
8. **The other-systems check.** `tools/check_other_systems.py` reads `exempt_paths`,
   `certify_spec`, `self_test` and `certify_contract` from the table `[check_other_systems]` of
   `kit.toml` with `tools/kit_config.py`, as the kit tools do: a missing table, an unknown key or a
   wrong type stops it. With no `kit.toml`: `.github/`, `specs/certify.md`, "the self-test of the project"
   and "the certify contract". `[values]` holds `SELF_TEST`, `CERTIFY_SPEC` and `CERTIFY_REPO` for
   the Markdown units, as `DEFAULT_BRANCH` is next to `target_branch`. `FIRST_PARTS` and `GENERIC`
   stay in the code, because the name lookup changes later (Q650). The test file of the check names
   no repository; `test_repo_values.py` tests the values of this repository.
9. **`CLAUDE.md`.** The manifest of the kit has no unit `CLAUDE.md`, so `kit.toml` needs no `skip`.
   No `CLAUDE.md` is created ([ADR-XT31](XT31-kit-adoption-choices-camera-media-check-and-fills.md)).
10. **CI.** No new step: `doc-checks.yml` runs `pytest tools/tests`, and the kit test
    `tools/tests/test_kit_sync.py` runs `check`.
11. **uv (Q656).** The agent reads the words of the user "the same version of uv as every other
    repo" as: each uv pin of this repository ends at the version of the kit. The kit text pins
    `doc-checks.yml` to 0.13.7. The other 9 lines of 5 workflows and 2 lines of 2 specs moved from
    0.13.9 to 0.13.7 in round 3, after the merge of the branches that change those workflows, as the
    supervisor scheduled. A decided entry that names 0.13.9 does not change. The local uv 0.13.7
    reads `uv.lock` with no change.
12. **Line ends.** At 3dc5377b4, `decisions/historical.md` was the one text file whose blob held CR
    (CRLF lines). The marker edit of round 1 (79ea16e96) made it LF in git. It stays LF, because LF
    is now the rule of the user (ADR-X1T8 item 8). `git add --renormalize .` changed no file. A line
    `*.ai binary` after the kit block of `.gitattributes` keeps the CR bytes of
    `shared/skellycam-logo/skellycam-logo.ai`. In round 3, `tools/check_line_ends.py --refresh` wrote
    the 885 CRLF files of the pilot worktree again with LF.
13. **Values tests.** `kit.toml` has a `[check_links]` table with the kit defaults.
    `test_repo_values.py` pins the golden paths (none), the allow lists of the private-data check
    (by count and SHA-256) and the docs of the link check. `kit_config.py` stops a tool when its
    table is missing, so the test does not check the table names.

## Reason

Each choice changes no rule of the user and keeps the behaviour of the tools. Items 2 and 7 keep
what git ignores and what gitleaks reports. Item 11 waits for the branches that change the same
workflow lines, so that their merges do not conflict. Item 8 makes the four other-systems units hold no
repository value, as the kit test "no repository value in a kit unit" needs.

## Alternatives rejected

- In round 1, a backtick in the value of the branch (item 6): the supervisor said not to work
  around the kit.
- Adding the other-systems units to the kit now: `propose` writes into the kit checkout, which
  another session owns.

## Open work

See [open-work.md](../open-work.md).
