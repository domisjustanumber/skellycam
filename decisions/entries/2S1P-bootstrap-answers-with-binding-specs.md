# 2S1P — Answers to the bootstrap questions of the kit adoption, with the specs as normative documents

**Status:** accepted, 2026-11-20 (user: decision 3 of ADR-N2NH changes item 4; the other items are
the accepted items of ADR-S222 with no change; commit to dom/index-limit).

## Decision

This entry supersedes [ADR-S222](S222-bootstrap-answers-of-the-kit-adoption.md). Only item 4
changes. The other items stay as the user accepted them on 2026-11-17.

1. **Public.** The repository is public. The private-data rule applies:
   [`AGENTS.md#8-private-data`](../../AGENTS.md#8-private-data).
2. **PR branch.** `development-streaming`:
   [`AGENTS.md#6-git-rules`](../../AGENTS.md#6-git-rules). It is in `TARGET_BRANCH` of
   `tools/check_decision_log.py`, in `AGENTS.md` and in the Rules of the index.
   `.github/workflows/test.yml` runs on PRs to `main` and `development`, so `secrets.yml` runs on PRs
   to `main`, `development` and `development-streaming`.
3. **PR kinds.** The kit default: code, docs and CI:
   [`AGENTS.md#6-git-rules`](../../AGENTS.md#6-git-rules).
4. **Normative documents.** `AGENTS.md`, the skills, the Rules, the tool docstrings and the specs in
   `specs/` ([ADR-N2NH](N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md) decision 3).
   A decision that a spec states in full can move to [historical.md](../historical.md). Before an
   entry moves, a check, entry by entry, must show that the spec states each rule of that entry. The
   placeholder clause is deleted from the Rules of the index.
5. **Sibling repos.** skellytracker and skellyfileformat use the same decision-log rules. Each keeps
   its own copy.
6. **ASD-STE100.** The kit default: yes:
   [`AGENTS.md#repository-instructions`](../../AGENTS.md#repository-instructions).
7. **Push.** The kit default: no push without the approval of the user:
   [`AGENTS.md#6-git-rules`](../../AGENTS.md#6-git-rules).
8. **Modules.** None. `skellycam-ui/` and `skellycam-docs/` have no `AGENTS.md` and no log.
9. **AI attribution.** No AI attribution in a commit or a PR:
   [`AGENTS.md#6-git-rules`](../../AGENTS.md#6-git-rules). The two commits that adopted the kit have
   such a trailer. They are not rewritten.

The other fills of the adoption, and the untracked `CLAUDE.md`, wait for the user in
[ADR-4A7H](4A7H-other-fills-of-the-kit-adoption.md).

## Reason

- The user, 2026-11-20, decision 3 of
  [ADR-N2NH](N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md): the specs in `specs/`
  become binding text. This changes item 4 of ADR-S222.
- The Rules allow no partial supersession. A new entry restates each item that stays.
- The reasons of the other items are in ADR-S222.

## Consequences

- `.github/workflows/test.yml` does not run on a PR to `development-streaming`
  ([open-work.md](../open-work.md)).

## Open work

See [open-work.md](../open-work.md).
