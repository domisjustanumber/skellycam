# K3BX — A certify-check name must be a check name of the certify spec

**Status:** absorbed into
[`AGENTS.md#other-systems-only-through-certify`](../../AGENTS.md#other-systems-only-through-certify),
[`.claude/skills/verify-on-other-systems/SKILL.md#steps`](../../.claude/skills/verify-on-other-systems/SKILL.md#steps),
[`tools/check_other_systems.py`](../../tools/check_other_systems.py),
2026-11-23 (commit to dom/other-systems-rule; was accepted, 2026-11-23 (user, relayed by the supervisor)).

## Decision

1. The marker `certify-check: <name>` of
   [ADR-VV4Q](VV4Q-other-systems-only-through-certify.md) passes the file check only when `<name>`
   is a check name of [`specs/certify.md`](../../specs/certify.md). For another name, the test
   fails.
2. To use a new name, the user or the agent first gets the check added to the spec. The process of
   the skellycertify repository applies to that change.

## Reason

- The user, 2026-11-23 (Q641): "if there is a certify-check name that is not in the certify spec,
  the test must fail, and the user/agent must follow the process in skellycertify to get them added
  to the spec."
- Without the lookup, any marker that an agent writes itself passes a refused script.

## Consequences

- The matching rule for a name, the refusal text and the pointer to the skellycertify process are
  agent choices in [ADR-K9B7](K9B7-design-of-the-other-systems-rule-skill-and-check.md).
