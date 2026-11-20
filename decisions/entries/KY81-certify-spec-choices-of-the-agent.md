# KY81 — Certify spec draft 2, its test list and the choices of the agent

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent wrote the draft spec [`specs/certify.md`](../../specs/certify.md) (draft 2) with its test list
T-CERT-01 to T-CERT-40, on the decisions of [ADR-GVC0](GVC0-certify-decisions-of-the-user.md). The
agent made these choices. The spec marks them [A]. The user decides the open ones through the 9
questions of section 14 of the spec.

1. Processes: the caller holds no camera driver; one detection child; one session child that runs the
   product `CameraGroupManager` with the native source only; a camera that hung is never opened again
   (2.1, 2.3).
2. The phases A to H of 2.3: the "before" values first; the risky checks last (phase F: in-use, 60 fps,
   group take at 60, cycles, macOS endpoint 0); then the restore and a plain open of each camera
   (phase G), also after a cancel.
3. The product path: each check uses only the product calls of 2.2, on the three systems.
4. Backend strings `media-foundation`, `v4l2`, `avfoundation`; names `cam.<backend>.<vid>-<pid>.<n>`,
   `group:`, `system:`, `self:`, `probe:`; no sections; flat `numbers` (3.1, 3.2).
5. Five claim checks for each camera (opens, rate, settings stick, native JPEG, records); the row with
   `partial` and `in use` through one format change 1.3.0, or the way with no change (3.3).
6. Quick: one apply, one live exposure change from -7 to -8 for the settings check, the JPEG check on
   frames that the run already has, a take of 3 s, an own limit of 45 s, the restore in the product
   (section 4).
7. `DARK_LUMA = 24`, not calibrated (4.6).
8. The disk check and the disk benchmark of 6.3 (1 GiB, 4 MiB blocks, fsync each second, at most 30 s).
9. The self-checks of section 7, with `self:server-gone` and `self:ring`.
10. The after-run states `healthy`, `restored`, `not-restored`, `replug`, carried by cleanup rows
    `release:<label>` with fixed reason codes that the app turns into the notice (8.3); the risk
    sentence in `system_changes` (8.4).
11. Camera name cleaning and the privacy additions of 9.4; the work folder and its cleanup (9.5).
12. Linux and macOS: the assumption checks of 10.2, the diagnostics D-1 to D-11 that the native
    sources must give (10.3), three probes (10.4), the isolation rules (10.5), and `clock` and
    `sequence` in quick (10.6).
13. The evidence file `camera_evidence.json`, its use in the product, the prompt and the rule from a
    report to a release (section 11).
14. The list of what skellycam tests and leaves to other modules (section 12).
15. The reason codes of section 15 and the product gaps of section 13.

## Reason

Section 1 of the spec gives the start question: does the native capture of skellycam work on this
system with these cameras, and if not, why. Each choice serves one part of that question, at the
lowest time that still separates the camera, the USB connection, the system, the light and another
program.

## Evidence

The spec cites the measurements of branch `dom/research`: the first hardware run of step 3a, the
free-run log with its 60 fps test, the Windows results of 2026-11-10 to 2026-11-13, the cross-platform
plan of 2026-11-06 and the Linux and macOS runbooks of the research suites. It also cites the facts of
the real-camera run of 2026-11-20 and the facts of the contract that the supervisor relayed.

## Open work

See [open-work.md](../open-work.md).
