# S222 — Answers to the bootstrap questions of the kit adoption

**Status:** proposed, 2026-11-17 (agent; waits for the user).

## Decision

The user asked for the adoption of the agents and ADR kit of freemocap/project in skellycam. Step 1
of the kit guide asks the user eight questions. The user has not answered them. An agent filled the
minimum that makes the tools work. Each fill below waits for the user.

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
9. **Other fills.** The purpose paragraph and the path table of `AGENTS.md` section 1, the install
   and test commands of section 3, the exact-version rule of section 4, `info@freemocap.org` (the
   author address in `pyproject.toml`) in `ALLOWED_EMAILS`, `pre-commit==4.6.2` (the version of
   skellytracker and skellyfileformat) in the `dev` group, and `tools/tests` in `testpaths`.
10. **`CLAUDE.md`.** Not tracked. The `.gitignore` of the repository already ignores `CLAUDE.md`. The
    local file holds only `@AGENTS.md`. The user decides whether git tracks it.
11. **AI attribution.** The kit rule in `AGENTS.md` section 6 forbids a `Co-Authored-By:` trailer.
    The skellycam session instructions ask for one, so the commit that adds this file has one. The
    user decides which rule applies in this repository.

## Reason

- The kit guide says: stop until the user answers. The user asked for the adoption, and a later
  session can change each fill when the user answers.
