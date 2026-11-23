---
name: verify-on-other-systems
description: Use this skill when a task needs a fact from a system other than the one that you work on (another OS, or hardware that your system does not have), for example a codec, driver or camera check, before you propose a script, a probe or a manual step for a person, and before you add a script that names or guards for a system.
---

# Verify on other systems

This skill uses ASD-STE100 Simplified Technical English.
The rules of [`AGENTS.md`](../../../AGENTS.md#other-systems-only-through-certify) also apply.

## Steps

1. Do not write a script or a manual step for a person to run on another system. Name the check of
   `skellycam.certify(level)` that gives the fact (`specs/certify.md`).
2. If no check gives the fact, add a check to the spec and to the self-test. Sections 5.5 and 5.6
   of the skellycertify contract (step 7) tell when a check can exist, its level and its safety
   rules.
3. Mark the fact `[NV]` (not verified) in the spec, and put it in
   [`open-work.md`](../../../decisions/open-work.md).
4. Tell the user which certify report will give the result.
5. Exception: a CI runner with no device can still run the checks that need no device, for example
   the portable tests. Use CI only for what it can check.
6. A script outside the product code that names or guards for a system has the comment
   `script-purpose: <kind> ...` in one of its first 5 lines. Use one of these kinds:
   - `certify-check <name>`: the script serves this certify check. `<name>` is a check name as
     `specs/certify.md` writes it, for example `<label>:usb3-trial`, not a filled-in name.
   - `local-study (<what>)`: a measurement on your own system. Its result is a fact about your
     system only. Mark it not verified for each other system.
   - `tool (<what>)`: the script builds, formats or checks files. It tests no product behaviour.
   - `ci (<workflow>)`: only the workflow `.github/workflows/<workflow>` runs it, with no device.
   The markers `certify-check: <name>` and `other-systems: not applicable (<reason>)` are not valid.
   `tools/check_other_systems.py` refuses each other script that names or guards for a system.
7. To add a check, follow the sections "5.5 How a package adds a check" and "5.6 When a check can
   exist, and its level" of `report-format.md` of the skellycertify repository. Then write the name
   in `specs/certify.md`, in the same commit as the script or before it.
