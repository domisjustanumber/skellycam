# 493E — Decisions of the user on the drops and additions of the certify checks

**Status:** accepted, 2026-11-23 (user; questions Q624a to Q624m, question 17 of section 14 of the certify spec;
the supervisor relayed the answer).

## Decision

The words of the user: "Q624f - use 3 as the lower value, and 12 as the upper value. otherwise yes to all of
Q624". The items are not built. [`certify.md`](../../specs/certify.md) section 3.6.12 states them. The choices
of the agent are in [ADR-DBF8](DBF8-choices-of-the-certify-names-verdicts-and-checks.md) (proposed).

- a. Drop the planned `system:backend`: the backend stands one time in `details`.
- b. Drop the planned `system:virtual-cameras`: the `detect` row holds the count.
- c. `control:white-balance` and `control:power-line` become facts of `details.cameras[]`, not checks.
- d. Drop `control:focus:sharpness` and `control:autofocus` until a rule exists.
- e. Merge `<label>:timings` into `cycles` and the step times.
- f. The scale self-check runs at two points: 3 cameras and 12 cameras. The proposal of one check at 8 is
  refused.
- g. `self:idle-cpu`, `self:ring:torn` and `self:ring:lapped` run in certify on ARM processors only; on x86-64
  the test suite proves them.
- h. Read the rule of `identity:stable` and `identity:unique`; drop them only if they served the unit id alone.
- i. Add, quick, pipeline: the recorded MKV opens through the reader of the product, and its frame count equals
  the rows.
- j. Add, full, model, record only at first: bursts, the share of arrival intervals under half a frame period.
- k. Add, quick, system: a camera that declares USB 3 capability on a USB 2 link gives a notice with a cause the
  person can fix. The summed need on one controller waits for `group:contention`.
- l. Add, quick, system: free memory before the open against the need of the rings, and on Linux the size of the
  shared-memory mount.
- m. Add: record, stop, record again (full, pipeline); the preview path during a take (full, planned until the
  preview UI of step 4b exists); the report checks itself before `certify()` returns (quick and full); the camera
  access switch of Windows (quick, system); power facts (full, record only); timer and sleep accuracy (full,
  record only).

## Reason

The gap review of 2026-11-23 found planned checks that repeat a fact of `details` or have no rule, and missing
checks for faults that the person can fix or that break a take.

## Open work

[open-work.md](../open-work.md)
