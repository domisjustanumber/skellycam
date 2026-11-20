# 4Z7T — Choices of the camera requests spec after the search at each open

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent changed [`specs/camera-requests.md`](../../specs/camera-requests.md) to agree with the
decisions G1 to G9 of the user in
[ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md). Where the user did not rule,
the agent made these choices B1 to B17. Section 4 of the spec holds the same list, and its sections
give the detail. The user decides them.

Added on 2026-11-20 ([ADR-379P](379P-answers-on-the-choices-after-the-search-at-each-open.md)):
the user rejected item 4 and accepted items 5, 6, 10 and 13, the first case of item 7 and item 8
except " Or choose 30 fps.". The rest stays proposed.

1. A camera in `AUTO` has no start-up rate check. Its open is: `starting` (open to the end of the
   warm-up, with its held value set), `waiting`, then `adjusting` when no selected camera is
   `starting`, then the check of `windows-capture.md` 10.2 in `checking`, then `ready` or `too_slow`. A camera in
   `MANUAL` keeps the start-up order and its start-up rate check.
2. The held value is not a start point: the search tries -12 to -5 in order. The held value is the
   value set at the open, and the value that a failed search sets again.
3. For a camera in `AUTO`, the ready limit of 15 s counts from the open to the end of the warm-up.
   The search keeps its own limit of 20 s (item 2 of ADR-Y6F6). The check after it has its own early
   decision.
4. Rejected by H1: an apply request that opens a camera in `AUTO` returns when each search has
   ended.
5. Only a camera that opens searches. When "Update Cameras" adds or reopens a camera, the other
   cameras get no set call and keep their state.
6. A failed search at an open sets the held value again and gives `exposure_search_failed`. The
   check of `windows-capture.md` 10.2 then judges the camera: `ready` or `too_slow`. A search never makes a camera
   `failed`.
7. At a group rate of 60 fps, the fall back to 30 fps also runs when the search of a camera in
   `AUTO` finds no value that keeps 60 fps, or when the check after its search fails. Each camera in
   `AUTO` then searches again at 30 fps.
8. The server reason of a slow camera keeps its numbers before the text of G3:
   `declared 30.00 fps, measured 25.76 fps. Camera is slow. Try adding more light`. The row text is
   the text of G3 only. The addition " Or choose 30 fps." goes. The warnings `add_light`,
   `exposure_search_failed` and `rate_fallback` keep their own texts.
9. The row text "Found at N fps: search again" and the extra sentence of `rate_fallback` for a value
   found at another rate go. "Auto: no value found yet" replaces "Auto: not searched yet".
10. The UI sets `camera_index` and `camera_name` of each config of an apply request from the current
    detection result. The server keeps the `camera_index` of the request. The recorder uses it for
    the order of `group_position`. No new field in the take files.
11. The rule of G9 is in the capture spec. This spec gives it only as a change to section 7.1 of
    `windows-capture.md`. The UI greys the row of a virtual camera and disables its tick box.
12. Each T-CAP test and each T-REQ test that does not name an exposure mode uses `MANUAL -7`. Thus
    the new default does not change its result.
13. The default of `CameraConfig()` in the API also becomes `AUTO`, with `exposure` -7 and
    `exposure_found_at_fps` `None`. The UI and the API then have one default.
14. After H1, the UI takes the result of a search from the live state. When
    `exposure_search.state` of a camera becomes `"done"`, the UI copies `exposure` and
    `exposure_found_at_fps` of that camera from `configs` of the state into its stored settings.
    This replaces item 6 of ADR-Y6F6 for a search that a response does not carry.
    While a camera is `adjusting`, its tile shows "Setting exposure…" over the preview, and the
    record button is disabled with that tooltip.
15. A client with no websocket reads the same state from a new route `GET /camera/group/state`. It
    returns the object of `state` of the `app_state` message.
16. A pause request while a camera is `adjusting` gets HTTP 409 that names the camera. The UI
    disables the pause button in that time. The button and "Search again" get HTTP 409 while the
    group is paused. A camera that opens while paused searches after the unpause.
17. A fall back that a camera in `AUTO` starts after the apply has answered (H4) runs in the main
    process with no new request. Its `rate_fallback` items go into the status `warnings` of each
    camera that failed at 60 fps, and the configs at 30 fps go into the live state.

## Reason

- B1: G2 needs the preview during the search. A camera in `starting` has no preview and is not in
  the gate. A start-up rate check at the held value would also judge the camera before the search,
  against G1 (b).
- B3: a search of about 10.7 s after a warm-up of 3 s does not fit in 15 s.
- B7: with G1, most cameras are in `AUTO`. A fall back for `MANUAL` cameras only would leave a
  group with an `AUTO` camera that cannot hold 60 fps at 60 fps, against Q10 of ADR-C4FZ.
- B8: decision D25 of [`windows-capture.md`](../../specs/windows-capture.md) puts the declared and
  measured rates in the reason. G3 replaces the hints.
- B13: a default only in the UI would give two defaults.
- B14, B15: H1 puts the result in the live state. The websocket sends that state each second when
  it changes. Today no HTTP route returns it.
- B16: a paused camera takes no frames, so the search cannot measure a rate or a brightness. The
  pause stays (H8).

## Alternatives rejected

- B1: the search in `starting` at step 5 of `windows-capture.md` 9.1, as `RECOMMEND` today: no preview, and the
  ready limit of 15 s.
- B16: a search that waits while the group is paused: its time limit would then need a pause rule.

## Open work

See [open-work.md](../open-work.md).
