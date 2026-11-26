# V8RS — Pause freezes the UI display only

**Status:** absorbed into
[`specs/camera-requests.md#13b-the-search-at-an-open`](../../specs/camera-requests.md#13b-the-search-at-an-open),
[`specs/camera-requests.md#111-tests`](../../specs/camera-requests.md#111-tests),
[`specs/windows-capture.md#94-wait-for-the-others-d21`](../../specs/windows-capture.md#94-wait-for-the-others-d21),
[`specs/preview-4b.md#56-the-grid-and-the-camera-list`](../../specs/preview-4b.md#56-the-grid-and-the-camera-list),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user)).

## Decision

The user decided these items on 2026-11-20 (question Q495):

- Pause is a freeze of the UI display only. The server has no public pause route: `PUT /group/all/pause`
  is removed. This changes the `PUT` pause item of
  [ADR-EQY4](EQY4-base-the-work-on-upstream-sfn26-without-rust.md). The `POST` record-stop item stays.
- The internal pause of the cameras stays (the orchestrator pause and unpause, the flags, the loop branch),
  because the record start uses it.
- In the UI, the Pause button, the menu item and Shift+Space freeze the display only. They work during a
  recording and do not change it. The "PAUSED" overlay stays. Un-pause shows the current frame.

## Reason

The pause of the user is for the view. The cameras and a recording must go on.
