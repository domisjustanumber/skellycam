# 0AMX — A skellycam agent runs propose; the kit session reviews and commits

**Status:** accepted, 2026-11-23 (user, relayed by the supervisor).

## Decision

Q657. Question: "Should a skellycam agent run `propose` from skellycam's side, with the kit session
then reviewing and committing the result in its own repo?" Answer of the user: "yes".

So an agent in skellycam runs `tools/kit_sync.py propose` for a change of kit text. `propose` writes
only into the working tree of the kit checkout. The session of the kit repository reviews the
result, and commits it in that repository. A skellycam agent makes no other change there.

## Reason

The user gave no reason. The path of a change in the kit README ("The path of a change") has the
same order: an entry in the repository, `propose`, then a review in freemocap/project.

## Consequences

- The first use is the rule "other systems only through certify"
  ([ADR-VV4Q](VV4Q-other-systems-only-through-certify.md)): its block, skill, check and test, and its
  hook. The choices of that run are in [ADR-6RVC](6RVC-choices-of-the-first-propose.md).

## Open work

See [open-work.md](../open-work.md).
