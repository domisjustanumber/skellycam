# VV4Q — Tests on other systems run only through certify

**Status:** absorbed into
[`AGENTS.md#other-systems-only-through-certify`](../../AGENTS.md#other-systems-only-through-certify),
[`.claude/skills/verify-on-other-systems/SKILL.md#steps`](../../.claude/skills/verify-on-other-systems/SKILL.md#steps),
[`tools/check_other_systems.py`](../../tools/check_other_systems.py),
2026-11-23 (commit to dom/other-systems-rule; was accepted, 2026-11-23 (user, relayed by the supervisor)).

## Decision

1. You can test only on the system on which the repository is checked out. A test on each other
   system runs only through the certify process of the project, `skellycam.certify(level)`, and
   its report. Windows is not special: a person on macOS or Linux reaches Windows the same way.
2. A check on another system, for example a cross-platform codec check, is a part of the certify
   process. An agent does not write a script or a manual step for a person to run on another system
   to test or verify a fact.
3. The rule applies to the machines that a person runs, not to a CI runner. A CI runner with no
   camera stays allowed for the checks that need no device.
4. A file check in the pre-commit hook and in CI is the primary mechanical check of the rule.
5. The rule lands in skellycam now. It goes into the shared agents and ADR kit later.

## Reason

- The user, 2026-11-23, on cross-platform codec checks: "that must be part of the certify processes
  we're also working on".
- The user, the same day, on a macOS probe script that an agent proposed for the user to run by
  hand: "the certify process is the only way any tests are ever run on machines other than this
  one".
- The user, the same day, asked for "a rule or skill with a suitable hook for this certify rule
  that can go into this repo and back into the agents_and_adr kit".
- The user accepted two questions of the supervisor (relayed): "Is the pre-commit/CI file check the
  primary hook, with the reminder as the only backup?" (item 4), and that the rule lands in
  skellycam now and reaches the kit later (item 5).
- The user, the same day, corrected item 1: "in this case 'other systems' means any system other
  than the one the repo is currently checked out. It's quite likely someone will have this repo
  checked out on a mac or linux machine and need to run checks on windows". The first text of item 1
  named the Windows lab machine as the only test machine. This commit is not pushed, so the entry
  changes in place.
- [`specs/frame-ring.md`](../../specs/frame-ring.md) already put T-RING-34 (Apple Silicon) into the
  certify suite, not into a run by hand.

## Consequences

- CI jobs on macOS, Linux and arm64 runners stay, for example the job of
  [ADR-7DE6](7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md).
- A proposal in chat is not in a file, so no file check sees it. The rule and the skill prevent
  that mistake. The file check only backs them up.
- The choices of the rule text, the skill and the file check are proposed in
  [ADR-K9B7](K9B7-design-of-the-other-systems-rule-skill-and-check.md).

## Open work

See [open-work.md](../open-work.md).
