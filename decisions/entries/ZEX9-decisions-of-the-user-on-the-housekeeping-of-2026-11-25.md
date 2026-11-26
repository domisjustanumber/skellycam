# ZEX9 — Decisions of the user on the housekeeping of 2026-11-25

**Status:** accepted, 2026-11-25 (user; the supervisor asked Q729 to Q732 and Q751 in a grilling session; "agree to
all"; commit to dom/exclusive-access-spec).

## Decision

1. **Q729 (session Q1).** The 65 camera media files tracked on `dom/research` (57 `.jpghdr` headers with no picture,
   8 frames of the simulated GigE camera) stop being tracked; they stay on disk under an ignore rule; the history
   does not change.
2. **Q730 (Q2).** Section 15 of the plan becomes one line that points to ADR-VHD3 (on `dom/legacy-player`) and the v1
   player spec.
3. **Q731 (Q3).** Push `dom/research` after items 1 and 2.
4. **Q732 (Q4).** Push `dom/integration` with the merge of fix lane 6; the next CI run must show T-CAP-86 and
   T-CAP-108 pass.
5. **Q751 (Q23).** Delete `part_a`, `part_bc` and `legacy` of the temporary H.264 study folder; keep `wasm_build`.

Items 1 to 3 are done (commit 9c40bc816 is on the fork), the push of item 4 is done, and item 5 is done. The status
becomes `done` when the CI result of item 4 is read.

## Reason

No camera frames in git; section 15 repeated ADR-VHD3 with one wrong line; the user approves each push; the study
results are committed.
