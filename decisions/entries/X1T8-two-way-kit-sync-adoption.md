# X1T8 — Two-way sync with the agents and ADR kit: skellycam is the pilot

**Status:** accepted, 2026-11-23 (user, relayed by the supervisor).

## Decision

The user decided these points on 2026-11-23. The quotes are the words of the user.

1. **Requirement.** "any repo using the kit must be able to sync back to it, and pick up changes from
   the kit into it's version. Not just skellytracker."
2. **Q635 and Q636** ("Q635, Q636 agree"). A session in the freemocap/project repository builds the
   kit side: the tool `kit_sync.py`, the manifest, the tests and the README. skellycam is the pilot,
   and the skellycam session does it. The rule "other systems only through certify"
   ([ADR-VV4Q](VV4Q-other-systems-only-through-certify.md)) lands in skellycam first. It reaches the
   kit later through `propose`.
3. **Q637** ("python 3.13 to match this/all other repos"). The values of each repository move out of
   the tool code into one `kit.toml` that the repository owns. The kit tools need Python 3.13 or
   later.
4. **Q638** ("Q638, Q640 agree"). The winners of the 19 differences between the kit and skellycam,
   as the supervisor listed them to the user:

   | Row | Difference | Winner |
   |---|---|---|
   | 1 | Evidence table in its own `decisions/evidence.md` | Kit. skellycam moves its rows. |
   | 2 | Status `evidence; replaced by XXXX` | Kit |
   | 3 | Change rules in the skill `change-decision-log` | Kit layout, plus rows 6 and 7 in the skill |
   | 4 | `--staged` reminder and its hook | Kit |
   | 5 | Clean-up at 90 % of an index limit too | Kit |
   | 6 | "A spec is binding text; check entry by entry before an absorb" | Merge: into the kit in a general form ("a normative document is binding"); the document list is a repository value |
   | 7 | "Do not shorten the index row of an entry that you did not write" | skellycam, into the kit skill |
   | 8 | `INDEX_LIMIT` 24,000 against 14,000 | Repository value |
   | 9 | The private-data hook checks only the commit files (`--files`) | skellycam, into the kit |
   | 10 | `ALLOWED_LINES` by path, line and hash | The skellycam mechanism, into the kit with an empty list; the rows are repository data |
   | 11 | Skip `package-lock.json` and `.ai` | skellycam, into the kit |
   | 12 | A home folder named `user` is a placeholder | skellycam, into the kit |
   | 13 | No-attribution step in the `commit-files` skill | skellycam, into the kit |
   | 14 | Actions pinned to full SHAs, uv version pinned | The skellycam form, into the kit |
   | 15 | The doc-check job installs only the `dev` group | skellycam, into the kit |
   | 16 | `.githooks/` in place of `pre-commit install` | Repository-owned |
   | 17 | Lint comment on one test line | Kit |
   | 18 | `CLAUDE.md` not tracked in skellycam | Repository-owned ([ADR-XT31](XT31-kit-adoption-choices-camera-media-check-and-fills.md)) |
   | 19 | gitleaks allow lists | Repository data |

5. **Q639** ("Otherwise Q635-Q639 agree"). CI runs only the offline `kit_sync.py check`. The note "a
   newer kit exists" comes only from a local run.
6. **Q655** ("Q655 and 656 agree"). Question: "The kit's text now says "`development`" where
   skellycam's text said "upstream `development`". Should skellycam keep its own wording by making
   the word "upstream" part of its value?" Answer: yes.
7. **Q656.** Question: "Should skellycam keep 0.13.9 until I can show you the rule's source?" The
   first answer was yes ("Q655 and 656 agree"). The user then changed it: "actually for Q656 follow
   that rule, so we are using the same version of uv as every other repo". So `UV_VERSION` in
   `kit.toml` is the value of the `kit.toml` template of the kit.

## Reason

The user gave the reasons in the quotes. One `kit.toml` for each repository keeps each kit tool the
same file in each repository, so a kit change can go to each repository and come back from it.

## Consequences

- The choices of the agent that applied these decisions are in
  [ADR-3SRX](3SRX-choices-of-the-kit-sync-pilot.md).
- The kit commit taken is in the table `[kit]` of `kit.toml`.

## Open work

See [open-work.md](../open-work.md).
