# S222 — Answers to the bootstrap questions of the kit adoption

**Status:** superseded by [2S1P](2S1P-bootstrap-answers-with-binding-specs.md), 2026-11-20 (commit to
dom/index-limit; was accepted, 2026-11-17 (user; commit to dom/native-jpeg; was proposed, 2026-11-17
(agent))).

## Decision

The user asked for the adoption of the agents and ADR kit of freemocap/project in skellycam. Step 1
of the kit guide asks the user eight questions. An agent filled the answers, and the user accepted
them on 2026-11-17.

1. **Public.** The repository is public. The private-data rule applies.
2. **PR branch.** `development-streaming`, the upstream branch of `dom/native-jpeg`. It is in
   `TARGET_BRANCH` of `tools/check_decision_log.py`, in `AGENTS.md` and in the Rules of the index.
   `.github/workflows/test.yml` runs on PRs to `main` and `development`, so `secrets.yml` runs on PRs
   to `main`, `development` and `development-streaming`.
3. **PR kinds.** The kit default: code, docs and CI.
4. **Normative documents.** None in addition to `AGENTS.md`, the skills, the Rules and the tool
   docstrings. The placeholder clause is deleted from the Rules of the index.
5. **Sibling repos.** skellytracker and skellyfileformat use the same decision-log rules. Each keeps
   its own copy.
6. **ASD-STE100.** The kit default: yes.
7. **Push.** The kit default: no push without the approval of the user.
8. **Modules.** None. `skellycam-ui/` and `skellycam-docs/` have no `AGENTS.md` and no log.
9. **AI attribution.** The kit rule of `AGENTS.md` section 6 applies in skellycam: no AI
   attribution, for example no `Co-Authored-By:` trailer, in a commit or a PR. The two commits that
   adopted the kit have such a trailer. They are not rewritten.

The other fills of the adoption, and the untracked `CLAUDE.md`, wait for the user in
[ADR-4A7H](4A7H-other-fills-of-the-kit-adoption.md).

## Reason

- The user, 2026-11-17, accepted items 1 to 8 as written.
- The user, 2026-11-17: no AI attribution in skellycam commits from now on.

## Consequences

- `.github/workflows/test.yml` does not run on a PR to `development-streaming`
  ([open-work.md](../open-work.md)).

## Open work

See [open-work.md](../open-work.md).
