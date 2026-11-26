# 6YGH — The user accepts as built the choices of fix lanes 4 and 5 and of the certify entries

**Status:** accepted, 2026-11-25 (user; the supervisor asked Q752 to Q757, Q759 to Q762 and Q770 in a grilling
session; commit to dom/exclusive-access-spec).

## Decision

The words of the user: "Q28 - yes and again ensure those certify tests are written ... Otherwise agree to all".
Each item accepts the choice as built and as the entry states it. "8CP7-5" is item 5 of ADR-8CP7.

1. **Q752, Q753, Q754 (session Q24 to Q26).** Q-A (the restore file by hashed key), Q-B (the take rate as a sum over a
   sum) and Q-C (the pace step on CI) of [ADR-HQE5](HQE5-choices-of-fix-lane-4.md). Known gap of Q-A: a host that
   builds its own `CameraGroupManager` without the app server gets no restore that survives a crash.
2. **Q755 (Q27).** Items 1 to 4 of [ADR-DC43](DC43-choices-of-fix-lane-5.md); item 3 as built (no caller needs the
   process gone at the return). The Windows Server key `2025Server 24H2` stays [NV].
3. **Q756 (Q28).** The remaining items of [ADR-KY81](KY81-certify-spec-choices-of-the-agent.md). The numbers are
   starting values. The certify tests of these items must be written: the lanes of Q772 and Q776
   ([ADR-N6X6](N6X6-decisions-of-the-user-on-the-build-lanes-of-2026-11-25.md)) do it.
4. **Q757 (Q29).** 8CP7-5 ([ADR-8CP7](8CP7-certify-spec-draft-3-choices-of-the-agent.md)): one full block for each
   model.
5. **Q759 (Q31).** 8CP7-3b = FC1C-14 ([ADR-FC1C](FC1C-choices-of-the-spec-integration.md)): when a model counts as
   checked.
6. **Q760 (Q32).** 8CP7-6 with FC1C-6 and FC1C-7: the auto-exposure checks at the base rate and at 60 fps, and the
   waits.
7. **Q761 (Q33).** FC1C-15 as built: the quick hang check runs only when 10 s of the 30 s are left.
8. **Q762 (Q34).** 8CP7 items 3a, 9, 11, 12, 13 and the codes of 15; FC1C items 1, 2, 3, 5, 8 to 12 and 16 to 19.
9. **Q770 (Q42).** 8CP7-14; the estimate of FC1C-15 replaces the one of 8CP7-15.

The five proposed entries keep their status in this commit. The read path is near 90 % of its limit, so their move
waits for a clean-up (open work).

## Reason

Each item is built and tested, and none has an alternative that the user prefers.

## Open work

[open-work.md](../open-work.md)
