# TC9B — The CI exception of the other-systems rule: a CI runner with no device

**Status:** absorbed into
[`AGENTS.md#other-systems-only-through-certify`](../../AGENTS.md#other-systems-only-through-certify),
[`.claude/skills/verify-on-other-systems/SKILL.md#steps`](../../.claude/skills/verify-on-other-systems/SKILL.md#steps),
2026-11-25 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-23 (user, relayed by the supervisor)).

## Decision

Q660. Question: "Should the kit rule say "a CI runner with no device" in place of "with no camera",
so it fits every repo?" Answer of the user: "Q660 yes".

So the exception of the rule "other systems only through certify"
([ADR-VV4Q](VV4Q-other-systems-only-through-certify.md)) is: "The one exception is a CI runner with
no device. It can still run the checks that need no device." The block `AGENTS.md#other-systems`
and step 5 of the skill `verify-on-other-systems` say this.

## Reason

The rule is kit text for each repository, and not each repository has cameras (the question of the
user).

## Open work

See [open-work.md](../open-work.md).
