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
[`camera-requests.md`](../../specs/camera-requests.md) state each one:

1. The group rate of a request is 60 fps when the request selects a camera whose `framerate` is within
   0.5 fps of 60.
2. The configs from before the request: each camera of the group after the apply gets its config from
   before the request, else the config of the request. Each gets `framerate` 30.
3. The fall back is an apply of these configs (`CameraGroup.apply`), with no whole-request check and no
   clear of the group warnings. It writes the `rate_fallback` items into `group_warnings` before the
   reopen. A fall back at the start-up also puts them in the apply response. The item has no `control`.
4. The text forms of `rate_fallback`, also for a camera that failed at `set mode` (no measured rate):
   `The group runs at 30 fps. Camera a1b2 could not set its 60 fps mode.`
5. The watch thread of the group finds the fall back that a search starts. It examines only cameras in
   `AUTO` whose ended search (`held.count` of the status) came after the request at 60 fps. It stops when
   the fall back starts, when no camera is `starting`, `waiting`, `adjusting` or `checking`, at the next
   apply request of the user, and at the close.
6. The watch thread starts the fall back on the event loop of the group. The log gets its failure.
7. Known limit: the fall back does not refuse an apply request of the user that comes between its start
   and the reopen.
8. T-REQ-19 reads the reason at 60 fps in the log, because the fall back replaces the status.
9. The UI: `chosenRate`, `rateRequestConfigs`, `rateFallbackText` and `checkingRate` in
   `skellycam-ui/src/store/slices/cameras/rate-choice.ts`. A pick sends each camera of the group with the
   new rate, and no camera that is not in the group.
10. The selector is disabled during a recording and while a camera is `starting`, `waiting` or
    `adjusting`. The option 60 fps is disabled when `can60` is false, with the reasons as its tooltip.
    `SegmentedControl` gets an optional `disabled` field for each option.
11. `rateChoice` treats an empty `supported_modes` as no 60 fps mode. It gives a reason text for a camera
    with 59.94 fps against 60. The reasons are in English only.
12. The UI takes a `rate_fallback` item of the live state only while no apply request of the UI runs. It
    then sets 30 in each desired config and keeps the text as the note under the selector until the next
    pick or detection.
13. "Checking 60 fps…" shows while a camera of the group is `starting`, `waiting`, `adjusting` or
    `checking`, and the choice is 60 fps or the live state holds a `rate_fallback` item.
14. New tests T-REQ-77 to T-REQ-83 for these choices.

## Reason

1. 0.5 fps is the tolerance of 2.5 for a 60 fps mode, so the server and the UI agree.
2. A camera that the request does not name runs at the group rate too: else the group has two rates.
3. One apply path keeps the waits, the restarts and the states of 8.2 and 8.3. The group warnings must
   survive the reopen and "apply again" of the fall back (1.5).
4. A `set mode` failure has no measured rate, and the spec text needs one.
5. `held.count` is written in the same status write as the search result. The search count goes up
   before the search writes `running`, so it can show a stale result for a short time.
6. The end of a take after an error uses the same path, so the fall back has no new thread.
9. The smallest request that changes only the rate, with no other camera opened or closed.
12. A live state that was sent before the server cleared the item must not undo a new pick.
13. The spec wants the text during the whole check, also during the fall back.

## Alternatives rejected

1. A group field for the rate in the API: [Q13] keeps the field of each camera.
2. A new lock between the fall back and the apply request of the user: a larger change for a short
   window that 8.3 already narrows.
3. A fall back after each search at 60 fps, also after "Search again": the spec ties the fall back to a
   request at 60 fps.
