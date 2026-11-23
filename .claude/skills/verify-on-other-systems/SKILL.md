---
name: verify-on-other-systems
description: Use this skill when a task needs a fact from macOS, Linux, a computer that is not the test machine, or hardware that the test machine does not have, for example a codec, driver or camera check, before you propose a script, a probe or a manual step for a person.
---

# Verify on other systems

This skill uses ASD-STE100 Simplified Technical English.
The rules of [`AGENTS.md`](../../../AGENTS.md#other-systems-only-through-certify) also apply.

## Steps

1. Do not write a script or a manual step for a person to run on another system. Name the check of
   `skellycam.certify(level)` that gives the fact ([`specs/certify.md`](../../../specs/certify.md)).
2. If no check gives the fact, add a check to the spec and to the self-test. Make sure that:
   - it is `record-only` until it has a pass rule;
   - it runs in its own child process or with a time limit;
   - it runs after the safe checks if it can block a device;
   - a failure gives `fail` with a reason code, and never stops the run;
   - its values have no free text and no private data;
   - its name is the name that the spec gives.
3. Mark the fact `[NV]` (not verified) in the spec, and put it in
   [`open-work.md`](../../../decisions/open-work.md).
4. Tell the user which certify report will give the result.
5. Exception: a CI runner with no camera can still run the checks that need no device, for example
   the portable tests. Use CI only for what it can check.
6. A script that serves a certify check has the comment `certify-check: <name>` in one of its first
   5 lines. A script that is not a test of another system has the comment
   `other-systems: not applicable (<reason>)`.
   `tools/check_other_systems.py` refuses other scripts that name or guard for another system.
