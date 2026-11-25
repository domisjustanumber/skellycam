# NA1N — Answers of the user to the questions of the step 4b tests (Q824 to Q836)

**Status:** accepted, 2026-11-25 (user; the supervisor relayed the answers).

## Decision

The user answered Q824 to Q836 (global numbers) on 2026-11-25. His words: "agree to all" (Q811 of the same
set had its own answer). Each answer thus accepts the recommendation of the agent.
[`specs/preview-4b.md`](../../specs/preview-4b.md) revision 4 states them.

1. **Q824.** The names of [ADR-70WD](70WD-failing-tests-of-step-4b-and-the-names-they-assume.md) are accepted.
2. **Q825.** Spec 5.4 and 7.4 use `cameraLabel` and `labelText` of `camera-labels.ts`.
3. **Q826.** The Displayed rate is the rate over the frames drawn in the last 1 s. Spec 5.8 states it.
4. **Q827.** T-PRV-26 is split into a blocking test and a `pace` test.
5. **Q828.** T-PRV-30 searches whole words. Spec 7.7 states it.
6. **Q829.** T-PRV-33 allows 4 to 7 console errors for the seven bad messages.
7. **Q830.** The set-up of T-PRV-44 is accepted. Its wording becomes "three tiles, with no filter on `alive`".
8. **Q831.** T-PRV-47 accepts `DISCONNECTED` or `FAILED`. The console has only the connection errors.
9. **Q832.** "3, 1 and 7" of T-PRV-50 is Oversize 3, Ring skipped 1, Replaced 7. The spec states the mapping.
10. **Q833.** T-PRV-48 expects D, B, C, A after D is added.
11. **Q834.** The benchmark details are accepted: barcode JPEGs of about 172 kB, a new server and a new app for
    each run, and the send-to-ready time starts again at a safety-net resend.
12. **Q835.** T-PRV-49 stays as it is. Look at it again after its first run.
13. **Q836.** T-PRV-25 runs in the capture jobs, which sync the project, and stays in `tools/tests/`.

## Reason

The user, 2026-11-25: "agree to all".

## Open work

See [open-work.md](../open-work.md).
