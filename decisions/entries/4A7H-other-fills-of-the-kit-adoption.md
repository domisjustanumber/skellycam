# 4A7H — Other fills of the kit adoption and the untracked `CLAUDE.md`

**Status:** superseded by [XT31](XT31-kit-adoption-choices-camera-media-check-and-fills.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-17 (agent; waits for the user)).

## Decision

These two items were items 9 and 10 of
[ADR-S222](S222-bootstrap-answers-of-the-kit-adoption.md). The user accepted the other items of
that entry. The user was not asked about these two items, so they wait for the user.

1. **Other fills.** The purpose paragraph and the path table of `AGENTS.md` section 1, the install
   and test commands of section 3, the exact-version rule of section 4, `info@freemocap.org` (the
   author address in `pyproject.toml`) in `ALLOWED_EMAILS`, `pre-commit==4.6.2` (the version of
   skellytracker and skellyfileformat) in the `dev` group, and `tools/tests` in `testpaths`.
2. **`CLAUDE.md`.** Not tracked. The `.gitignore` of the repository already ignores `CLAUDE.md`. The
   local file holds only `@AGENTS.md`. The user decides whether git tracks it.

## Reason

- The kit guide says: stop until the user answers. The user asked for the adoption, and a later
  session can change each fill when the user answers.
