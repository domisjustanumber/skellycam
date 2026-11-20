# Y6F6 — Choices of the camera requests spec

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent wrote [`specs/camera-requests.md`](../../specs/camera-requests.md) from the decisions of
the user in [ADR-C4FZ](C4FZ-camera-requests.md). The user then answered the questions Q1 to Q14 of
the first draft; C4FZ holds the answers, and the choices that they decided are not in this list. The
agent made these choices A1 to A23. Section 4 of the spec holds the same list, and its sections give
the detail. The user decides them.

Added on 2026-11-20, after
[ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md): the user decided items 3, 10
and 19, and the names of item 11 (JK79 G5, G6 and G8). The other parts of item 11 stay proposed.
Decision G1 of JK79 replaces the part "It does not search by itself. Its row offers the search." of
item 7, and item 9. Decision G3 replaces the texts of item 12. Item 16 now applies only to a camera
in `MANUAL`, and item 17 gets one more case
([ADR-4Z7T](4Z7T-choices-after-the-search-at-each-open.md) items 1 and 7). The other items stay
proposed.

1. The early decision of the check after a live change, for each value, with 30 frames.
2. The time limit of a search is 20 s.
3. The config keeps `exposure_mode: "AUTO"` with the held value in `exposure`, and the new field
   `exposure_found_at_fps`: the mode rate at which a search found the value, or `None`.
4. The control thread does the sets and the loop measures. The read each second waits.
5. Each camera searches on its own. In the gate, the 10th and 40th frames are the first taken frames
   at or after those counts.
6. The UI copies the held value from each response into its stored settings.
7. A camera in `AUTO` with no held value starts at its `exposure` value (-7 for a new camera). It
   does not search by itself. Its row offers the search.
8. A reopen of a running camera keeps the held value of its current config, not the value of the
   request.
9. A held value found at another rate: the row says "Found at N fps: search again". The
   `rate_fallback` text tells how to reach 60 fps: Manual with a shorter exposure, pick 60 fps, then
   switch to Auto.
10. `RECOMMEND` in a request is read as `AUTO`.
11. The endpoint `POST /camera/group/exposure/auto` with the optional body `camera_ids`, its
    response and codes, the status field `exposure_search`, and the warning kinds `add_light` and
    `exposure_search_failed` with their texts.
12. One set of texts of a slow camera: the `MANUAL` reason adds "or lower the exposure", so that it
    agrees with the `too_slow` row text of the user; the `AUTO` row text is "Too slow at this
    exposure: add light, then search again".
13. Server texts keep camera IDs. The UI replaces each listed ID with `Camera <list number> · <name>`.
14. No rate above 60 fps is offered.
15. The UI never sends -1 or 0. The API keeps them. `CameraConfigFramerate.tsx` goes. The UI default
    is 30.
16. The real 60 fps check is the start-up rate check at 60 fps. No other probe.
17. The fall back runs only for the stages `set mode` and `rate check`, with the warning
    `rate_fallback`.
18. Only the UI keeps the last fall back text, for the app run.
19. The field `usb_link` with the values `USB 1`, `USB 2`, `USB 3`, `unknown`.
20. A virtual camera keeps `usb_link: "unknown"`. The UI shows `virtual` from the flag `virtual` of
    the detection result. No new value.
21. The label sends no request to the camera: only the connection-information calls at the hub.
22. Port the sfn26 module as `skellycam/core/device_detection/usb_link.py`.
23. On Windows, a bounded lookup of 1 s for each camera in the detection child.

## Reason

The spec gives the reason of each choice in the section that the list of its section 4 names. The
main reasons:

- A3, A7: Q3 stops the search at the start-up. The start-up then needs the held value and must know
  whether a search found it. One field holds both facts, and its rate tells when the rate guard of
  the value no longer applies.
- A9: the search needs the open stream at the new rate. A camera whose held value fails at 60 fps
  falls back to 30 fps, so the search cannot run at 60 fps until the camera runs there.
- A12: the user decided the `too_slow` row text "lower the exposure" on the same day. The `MANUAL`
  reason of Q8 then adds that hint, so that the server and the row agree.
- A20: the detection result already has `virtual: true`. A new value of `usb_link` would repeat it.

## Open work

See [open-work.md](../open-work.md).
