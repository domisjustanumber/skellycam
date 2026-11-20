# EQY4 — Base the work on upstream sfn26 without Rust

**Status:** accepted, 2026-11-20 (user).

## Decision

The user decided these items on 2026-11-20:

- The work is based on upstream `sfn26`. Merge it. Keep our side for the camera layer and the
  recorder.
- Remove every Rust part in one follow-up commit. The Rust commits stay in the history.
- Pull requests go against upstream `development`.
- Port these items from `sfn26`: the USB link of each camera, the start-failure explanation, the
  `PUT` pause and `POST` record-stop contract, and the restore of the settings when the exposure
  search fails.
- Drop these items of `sfn26`: the old-loop fixes, one timestamps file per camera, and MJPEG modes
  through Rust.

## Reason

The user does not keep any part of the Rust implementation on this branch.
