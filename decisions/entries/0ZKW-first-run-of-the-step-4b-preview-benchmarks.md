# 0ZKW — First clean run of the step 4b preview benchmarks T-PRV-51 and T-PRV-52

**Status:** evidence, 2026-11-26 (measured by the code lane of step 4b, Q869 of
[ADR-BPP8](BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md)).

## Decision

No decision. The first clean numbers of section 6 of [`specs/preview-4b.md`](../../specs/preview-4b.md), for the
user. Two targets of 6.3 miss by a small amount: B-1a at F = 30 (worst distinct ratio 0.996, target 1) and B-1b at
F = 60 (ready messages 52.5 each second, target 53.1; `drawnCount` ratio 0.987, target 1). Section 6.4 makes a miss
of B-1b at F = 60 a case for the decision of the user on a worker; a miss of B-1a is a defect of the preview, not a
case for a worker.

## Evidence

Tool: `npx playwright test -c playwright.player-bench.config.ts src/components/camera-views/tests/bench`,
`preview.bench.ts` of `dom/preview-4b-tests` at 490f89cc8, Electron 45.3.4, the Windows test machine (display
refresh R = 59 Hz). Method of 6.2: 8 fake rings of barcode JPEGs at 1920 x 1080 (target 190 kB), a new server and a
new harness app for each run, 3 runs of 2 s warm-up and 60 s measurement. The harness app runs with no Playwright
attached (6.2, Q869). The values are the medians of the 3 runs.

| ID | F = 30 (T-PRV-51) | F = 60 (T-PRV-52) | Target |
|---|---|---|---|
| B-1a wrong camera, behind more than 2 | 0, 0 | 0, 0 (recorded only) | 0, 0 at F = 30 |
| B-1a worst distinct ratio | 0.996 (runs 1.037, 0.996, 0.996) | 1.004 (recorded only) | at least 1 at F = 30 |
| B-1b ready messages each second, lowest camera | 30 | 52.5 (runs 53, 52.5, 52) | at least 0.9 x min(F, R): 27 and 53.1 |
| B-1b `drawnCount` ratio | 1.112 | 0.987 | at least 1 |
| B-2 send-to-ready p95 (p50) | 21.8 ms (17.8 ms) | 30.6 ms (16.5 ms) | at most 50 ms |
| B-3 `TaskDuration` share | 0.193 | 0.380 | at most 0.5 |

Recorded, with no target (medians of the runs): the observer gave 30.0 captures each second; CPU of the page
process 84 % and 168 % of one core, of the GPU process 25 % and 45 %; working set 706 MB and 959 MB; the Python
event-loop thread 0.09 and 0.15 of one core.
