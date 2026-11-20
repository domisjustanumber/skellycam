# 4Z7T — Choices of the camera requests spec after the search at each open

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent changed [`specs/camera-requests.md`](../../specs/camera-requests.md) to agree with the
decisions G1 to G9 of the user in
[ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md). Where the user did not rule,
the agent made these choices B1 to B21. Section 4 of the spec holds the same list, and its sections
give the detail. The user decides them. The answers of the user are in
[ADR-6QFG](6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md), which keeps H1 to
H7 of [ADR-379P](379P-answers-on-the-choices-after-the-search-at-each-open.md).

1. A camera in `AUTO` has no start-up rate check. Its open is: `starting` (to the end of the
   warm-up, with its held value set), `waiting`, `adjusting` when no selected camera is `starting`,
   then the check of `windows-capture.md` 10.2 in `checking`, then `ready` or `too_slow`. A camera in
   `MANUAL` keeps the start-up order and its start-up rate check.
2. The held value is not a start point: the search tries -12 to -5 in order. The held value is the
   value set at the open, and the value that a failed search sets again.
3. For a camera in `AUTO`, the ready limit of 15 s counts from the open to the end of the warm-up.
   The search keeps its own limit of 20 s (item 2 of ADR-Y6F6).
4. Rejected (H1): the apply waits for the searches.
5. Decided (H2): only a camera that opens searches.
6. Decided (H3): a failed search at an open goes on to the check; it never makes a camera `failed`.
7. The fall back to 30 fps at 60 fps also runs when the check after the search of a camera in `AUTO`
   fails. The `rate_fallback` text of such a camera uses its trial with the highest rate. (The case
   of a search with no value that holds 60 fps is decided: H4.)
8. The addition " Or choose 30 fps." goes from the server reason. (The rest of the item is decided:
   H5.)
9. The row text "Found at N fps: search again" and the extra sentence of `rate_fallback` for a value
   found at another rate go. "Auto: no value found yet" replaces "Auto: not searched yet".
10. Decided (H6): the camera number decides only the order in the take.
11. The rule of G9 is in the capture spec. This spec gives it only as a change to section 7.1 of
    `windows-capture.md`. The UI greys the row of a virtual camera and disables its tick box.
12. Each T-CAP, T-UNX and T-REQ test that does not name an exposure mode uses `MANUAL -7`. Thus the
    new default does not change its result.
13. Decided (H7): the default of `CameraConfig()` is `AUTO`.
14. The UI takes the result of a search at an open from the live state: when
    `exposure_search.state` of a camera becomes `"done"`, it copies `exposure` and
    `exposure_found_at_fps` from `configs` of the state into its stored settings. While a camera is
    `adjusting`, its tile shows "Setting exposure…", and the record button is disabled with that
    tooltip.
15. A client with no websocket reads the same state from a new route `GET /camera/group/state`.
16. Withdrawn: the pause rules during a search. K1 of ADR-6QFG makes them moot.
17. A fall back that a camera in `AUTO` starts after the apply has answered runs in the main process
    with no new request. Its `rate_fallback` items go into the status `warnings` of each camera that
    failed at 60 fps until the next apply request, and the configs at 30 fps go into the live state.
18. A program that runs `CameraGroupManager` in its own process (certify) starts a search with
    `await CameraGroupManager.search_exposure(camera_ids=None)`. The endpoint of the button calls the
    same method, and it returns the same response.
19. The field `paused` of the state stays. It is true only during the internal pause of a record
    start. The display freeze of the UI (K1) is the pure function `displayedFrame` and never sets it.
20. `exposure_search` gets `count`: the number of searches that the camera started since its process
    started. A client counts the searches with it.
21. A camera of K3 has the start-up rate check of `MANUAL`, the warning text "Camera a1b2 has no
    manual exposure. SkellyCam does not set its exposure." and the row text "No manual exposure on
    this camera".

## Reason

- B1: G2 needs the preview during the search. A camera in `starting` has no preview and is not in
  the gate. A start-up rate check at the held value would also judge the camera before the search,
  against G1 (b).
- B3: a search of about 10.7 s after a warm-up of 3 s does not fit in 15 s.
- B7: keep "60 fps only when proven" (Q10 of ADR-C4FZ).
- B14, B15: H1 puts the result in the live state. The websocket sends that state each second when
  it changes. Today no HTTP route returns it.
- B18: certify has no HTTP server. One method keeps one behaviour for both callers.
- B20: certify must count the searches (`certify.md` 5.3), and polling can miss a short search.

## Alternatives rejected

- B1: the search in `starting` at step 5 of `windows-capture.md` 9.1, as `RECOMMEND` today: no
  preview, and the ready limit of 15 s.
- B20: certify counts the moves into `adjusting` while it polls: it depends on the poll interval.

## Open work

See [open-work.md](../open-work.md).
