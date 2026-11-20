# 4Z7T — Choices of the camera requests spec after the search at each open

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent changed [`specs/camera-requests.md`](../../specs/camera-requests.md) to agree with the
decisions G1 to G9 of the user in
[ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md). Where the user did not rule,
the agent made these choices B1 to B13. Section 4 of the spec holds the same list, and its sections
give the detail. The user decides them.

1. A camera in `AUTO` has no start-up rate check. Its open is: `starting` (open to the end of the
   warm-up, with its held value set), `waiting`, then `adjusting` when no selected camera is
   `starting`, then the check of `windows-capture.md` 10.2 in `checking`, then `ready` or `too_slow`. A camera in
   `MANUAL` keeps the start-up order and its start-up rate check.
2. The held value is not a start point: the search tries -12 to -5 in order. The held value is the
   value set at the open, and the value that a failed search sets again.
3. For a camera in `AUTO`, the ready limit of 15 s counts from the open to the end of the warm-up.
   The search keeps its own limit of 20 s (item 2 of ADR-Y6F6). The check after it has its own early
   decision.
4. An apply request that opens a camera in `AUTO` returns when each search of the request has
   ended. While it waits, the status shows `adjusting` and `exposure_search.state: "running"`, the
   tile shows "Setting exposure…" over the preview, and the record button is disabled with that
   text as its tooltip.
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

## Reason

- B1: G2 needs the preview during the search. A camera in `starting` has no preview and is not in
  the gate. A start-up rate check at the held value would also judge the camera before the search,
  against G1 (b).
- B3: a search of about 10.7 s after a warm-up of 3 s does not fit in 15 s.
- B4: one response then carries the held values and the warnings, as for the endpoint of item 11 of
  ADR-Y6F6. Item 6 of ADR-Y6F6 then works with no change.
- B7: with G1, most cameras are in `AUTO`. A fall back for `MANUAL` cameras only would leave a
  group with an `AUTO` camera that cannot hold 60 fps at 60 fps, against Q10 of ADR-C4FZ.
- B8: decision D25 of [`windows-capture.md`](../../specs/windows-capture.md) puts the declared and
  measured rates in the reason. G3 replaces the hints.
- B13: a default only in the UI would give two defaults.

## Alternatives rejected

- B1: the search in `starting` at step 5 of `windows-capture.md` 9.1, as `RECOMMEND` today: no preview, and the
  ready limit of 15 s.
- B4: a return at the end of the start-up: the UI would read each held value from the status.

## Open work

See [open-work.md](../open-work.md).
