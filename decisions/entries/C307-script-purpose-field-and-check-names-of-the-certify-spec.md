# C307 — The script-purpose field, and check names from the certify spec

**Status:** accepted, 2026-11-23 (user, relayed by the supervisor).

## Decision

1. **Q642.** The file check compares a check name with `specs/certify.md` of skellycam. To get a
   new check accepted before it is written there, a person or an agent follows the process of the
   skellycertify repository.
2. **Q643.** Each script outside the product code that names or guards for any system needs a
   field. The commit check and CI check it the same way. There is no exception for the system of
   the author.
3. **Q645.** The field is `script-purpose:`, with one of four kinds. It replaces the markers
   `certify-check: <name>` and `other-systems: not applicable (<reason>)`. Each other kind is
   refused. Only a script that names or guards for a system needs the field.
   - `certify-check <name>`: the script serves this certify check. The name must be in the certify
     spec ([ADR-K3BX](K3BX-certify-check-names-must-be-in-the-certify-spec.md)).
   - `local-study (<what>)`: a measurement on the system of the author. Its result is a fact about
     that system only, and it is "not verified" for each other system.
   - `tool (<what>)`: it builds, formats or checks files. It tests no product behaviour.
   - `ci (<workflow>)`: only a CI workflow with no device runs it.
4. **Q644.** The rules for the admission and the placement of a certify check go into the spec of
   the skellycertify repository, not into skellycam. skellycam points to the sections "5.5 How a
   package adds a check" and "5.6 When a check can exist, and its level" of its `report-format.md`.

## Reason

- Q642, question: "Is it right that the tool checks names against skellycam's `specs/certify.md`,
  and that the skellycertify process is what a person or agent follows to get a new check accepted
  before it is written there?" The user: "Q642 agree".
- Q643, question: "Should every script outside the product code that names or guards for any
  system need a marker, checked the same way at commit and in CI, with no exception for the system
  the author is on?" The user: "Q643, better, but consider a more accurate name for other-systems:
  not applicable (<reason>)". The supervisor read this as acceptance with the name of the marker
  open. The user settled the name in Q645 and did not object.
- Q645, question: "Should the marker be `script-purpose:` with these four kinds, replacing both
  earlier markers?" The user: "Q645 agree".
- Q644, the user: "All of those items must go into the skellycertify spec".

## Consequences

- The choices of the scan scope, the signal patterns, the name lookup and the 5 lines are proposed
  in [ADR-K9B7](K9B7-design-of-the-other-systems-rule-skill-and-check.md).
