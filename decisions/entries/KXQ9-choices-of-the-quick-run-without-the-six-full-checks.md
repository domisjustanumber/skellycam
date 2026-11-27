# KXQ9 — Choices of the quick certify run without the six full checks (Q902), and the 8CP7 check (Q853)

**Status:** proposed, 2026-11-27 (agent; the certify lane builds Q902 of
[ADR-Y2RN](Y2RN-decisions-of-the-user-on-the-size-floor-review-and-certify-quick-runs.md) item 5 and checks Q853 of
[ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md); waits for the user).

## Decision

The user decided Q902: a quick certify run leaves out the six full-only checks of Q593 (`image-effect`,
`not-reencoded`, `size`, `ring-equals-mkv`, `source-equals-ring`, `gaps-explained`). The user did not say what a
quick report holds for them. The agent made these choices. Section 3.6.1 of
[`specs/certify.md`](../../specs/certify.md) states them.

1. **The form in a quick report.** Each of the six is left out as a check that the level does not have: not planned
   (not in `details.checks` of the plan, not counted in `total`), no row in `checks` (also no `not-run` row), not in
   `details.not_built`, no progress message, not counted in `numbers.checks` of a `<label>:not-reached` row, and
   never the B1 row. This is the rule of the clock checks of quick on Media Foundation and of the camera block of a
   second unit (MEE1 4). The report shape, its field names, its schema and the meaning of each reason code do not
   change.
2. **The work stays.** The quick session still waits for the hash set of the first `ready` and still computes the
   six; it drops their rows and their progress messages. Thus the quick estimate of 4.7 does not change, and the
   steps are the same code in both levels. A later change can skip that work in quick, with a measurement first.
3. **This part of build step 5 comes first, alone.** The rest of step 5 of 3.6.7 (`<label>:detect`, `<model>:units`,
   `group:take` with two rows, `system:recording-space`, `group:in-step`) is not built.
4. **The tests.** T-CERT-153 is new. T-CERT-151 case (1) runs at `full`, and case (2) at both levels. The helper of
   the tests that lists the checks of the five groups takes the level.
5. **8CP7 is not absorbed (Q853).** The specs state most items of
   [ADR-8CP7](8CP7-certify-spec-draft-3-choices-of-the-agent.md), with the later changes of the user. Three items
   differ from later text of the spec, and the user accepted each item on 2026-11-25, after that text:
   - 8CP7-6 names the Auto checks at 60 fps (accepted by Q760); Q617 (2026-11-23) removed them (3.6.11).
   - 8CP7-3 keys a camera with no USB id by `nousb:<cleaned name>` (as built; accepted by Q762); 2.5 gives the raw
     name (DBF8 15, Q627), which build step 8 builds.
   - 8CP7-7 sends no progress message for a roll-up or a computed check (accepted as built by Q814); 9.6 (H0BQ) and
     the code send one before each check.

   The entry stays `accepted` until the user says which text wins (the question of open work).

## Reason

- Item 1: Q593 moves the six to full, and 3.6.2 lists quick with no such row. A `not-run` row would make each quick
  item `partial` (3.4 rule 4), so a smoke test could never pass. A `not_built` name would be false: the checks have
  code.
- Item 2: the smallest change. The six use frames that the run already has (4.4), so the time is the wait for the
  hash set only.
- Item 5: absorbing an entry means that the specs state each of its rules. These three items have two accepted
  texts, so the agent cannot choose.

## Alternatives rejected

- The six as `not-run` with a new reason code in quick: a change of the meaning of the report and of the codes, and
  each quick item `partial`.
- Skip the hash wait in quick now: it changes the timing of the ready step with no measurement.

## Open work

[open-work.md](../open-work.md)
