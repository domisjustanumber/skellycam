# 1T0S — Choices of step 4: one frame rate for the group and the fall back to 30 fps

**Status:** proposed, 2026-11-21 (agent of step 4; the user gave the go-ahead to build step 4 on that day).

## Decision

Step 4 builds part 2 of [`camera-requests.md`](../../specs/camera-requests.md): one frame rate control
for the camera group, and the one fall back of the group from 60 fps to 30 fps. These rules are
decisions of the user. This entry does not decide them again:

- A group has one frame rate, and each camera of the group runs at it. The UI has one frame rate
  control at the top of the camera list in place of one control for each camera ([F1], [Q13] of
  [ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md)).
- The UI offers only modes of 30 fps and more. 29.97 fps counts as 30 ([F3]; item 8 of
  [ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md)).
- When a camera in Auto finds no exposure value that keeps 60 fps, the group falls back to 30 fps one
  time, not again and again, with a warning ([H4], kept by
  [ADR-6QFG](6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md); restated by the
  user on 2026-11-21 as Q489).
- The UI text of a slow camera is exactly "Camera is slow. Try adding more light". The numbers are only
  in the detail of the API and in the log ([G3], [H5]).
- The server applies a request at once. The results come through the live status ([H1]).

The agent made these choices where the spec gave no rule. Sections 2.4a and 2.8 of
[`camera-requests.md`](../../specs/camera-requests.md) state each one in full:

1. A request is at 60 fps when it selects a camera at 60 fps, within 0.5 fps.
2. The fall back configs: the config of each group camera from before the request, else the config of
   the request, each at 30 fps.
3. The fall back is an apply of these configs, with no whole-request check and no clear of the group
   warnings. Its `rate_fallback` items (no `control`) go into `group_warnings` before the reopen.
4. The texts of `rate_fallback`, also for a `set mode` failure, for a search with no measured rate and
   for no exposure value. The rates and the exposure come from the time of the failure.
5. The watch thread of the group finds the fall back that a search of the request starts
   (`held.count`). It stops at the fall back, when no camera is busy, at an apply request of the user,
   at a search on request and at the close.
6. The fall back that the watch finds runs on the event loop of the group.
7. One group flag `request_runs` covers each user apply with its start-up fall back, and each fall back.
   While it is set, an apply, a record start and a search on request get HTTP 409. A request count
   stops a fall back of the watch for an older request.
8. T-REQ-19 reads the reason at 60 fps in the log.
9. A pick sends each group camera with its applied config and the new rate, and keeps the unapplied
   edits of the list. A failed pick sets the choice to the rate of the group in the live state.
10. The selector options are disabled buttons during a recording and while a camera is busy; 60 fps
    also when `can60` is false. The reason is a visible text, named by `aria-describedby`.
11. An empty `supported_modes` has no 60 fps mode. A reason text for 59.94 against 60. English only.
12. The UI takes only a new `rate_fallback` text of the live state: 30 fps and a note under the selector.
13. "Checking 60 fps…" from a sent pick of 60, or a new fall back item while a camera is busy, until a
    live state has no busy camera. After a pick with a camera in `AUTO` the next live state decides.
14. A fall back does not run during a take, a record start or a close, as the user decided that a rate
    change never disturbs a recording.
15. "Update Cameras" resends a camera whose desired rate differs from its applied rate. A detection gives
    each camera the current choice.

The tests T-REQ-84 to T-REQ-97 check these choices.

## Reason

1. 0.5 fps is the tolerance of 2.5, so the server and the UI agree.
2. Else the group has two rates.
3. One apply path keeps the waits and states of 8.2 and 8.3; the items must survive the reopen (1.5).
4. The spec text needs a measured rate, and a later read can see the new mode.
5. `held.count` comes in the same status write as the search result.
7. Two applies on one group at the same time gave two rates and a dead camera, and a stale fall back
   undid a later request (two independent reviews). The check and the set of the flag have no wait
   between them. The count still covers a fall back of the watch that a finished request replaced.
9. A pending edit can make the server refuse the whole pick.
10. A CSS class still lets Enter and Space work, and a disabled button cannot show a tooltip to the
    keyboard.
12. An old live state must not undo a new pick or bring back a cleared note.
13. A later search on request is not a check of 60 fps.
14. A late watch round started a fall back during a take in the review.
15. Else the user gets HTTP 422 with no way to send the rate again.

## Alternatives rejected

1. A group field for the rate in the API: [Q13] keeps the field of each camera.
2. An `asyncio.Lock` that queues a second request: the user then waits for a change that can take 30 s
   with no answer. A 409 with a reason answers at once.
3. A fall back after a search on request at 60 fps: the spec ties the fall back to a request.
