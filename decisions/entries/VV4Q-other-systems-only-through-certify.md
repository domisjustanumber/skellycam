# VV4Q — Tests on other systems run only through certify

**Status:** accepted, 2026-11-23 (user).

## Decision

1. The Windows lab machine of the project is the only test machine. A test on another system
   runs only through the certify process of the project, `skellycam.certify(level)`, and its report.
2. A check on another system, for example a cross-platform codec check, is a part of the certify
   process. An agent does not write a script or a manual step for a person to run on another system.
3. The rule applies to the machines that a person runs. A CI runner with no cameras stays allowed
   for the checks that it can do.
4. A file check in the pre-commit hook and in CI is the primary mechanical check of the rule.
5. The rule lands in skellycam now. It goes into the shared agents and ADR kit later.

## Reason

- The user, 2026-11-23, on cross-platform codec checks: "that must be part of the certify processes
  we're also working on".
- The user, the same day, on a macOS probe script that an agent proposed for the user to run by
  hand: "the certify process is the only way any tests are ever run on machines other than this
  one".
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
