# N6X6 — Decisions of the user on the build lanes of 2026-11-25

**Status:** accepted, 2026-11-25 (user; the supervisor asked Q750, Q772, Q775, Q776 and Q780 in a grilling
session; commit to dom/exclusive-access-spec).

## Decision

1. **Q750 (session Q22).** Three lanes off `dom/integration`, each with an Opus agent, a worktree and an independent
   review: the failing tests of the JPEG encode at capture (Q689), the failing tests of the 4b preview UI, and the
   build of the capture timings. Timed tests run in one lane at a time. The user: "Let me know when you want to run
   performance tests, as I am currently connected over sunshine". The v1 player code waits for its spec.
2. **Q772 (Q44).** A certify lane writes the missing tests on fakes: T-CERT-30, 31, 67, the open cases of 28, 49, and
   01, 18, 33. It fixes the stale not-built list (T-CERT-121) and the "Today" column of section 13.
3. **Q775 (Q47).** In that lane, after its tests: the code of T-CERT-15 (`bad-output`, no exit) and the real source
   factory in T-CERT-32.
4. **Q776 (Q48).** After the lane of Q772 merges: move the fake source into the package, build `self:server-gone`,
   `self:crash-take` and `self:hang-100ms`, and write T-CERT-25 and 64.
5. **Q780 (Q52).** Quick tests only until the timing runs of fix lane 7 end; Q776 starts after fix lane 7 merges; the
   lane that merges second resolves `open-work.md`.

## Reason

The lanes are independent; timed tests in parallel skew each other; fix lane 7 changed the fake source.
