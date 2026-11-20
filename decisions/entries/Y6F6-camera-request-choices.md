# Y6F6 — Choices of the camera requests spec

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent wrote [`specs/camera-requests.md`](../../specs/camera-requests.md) from the decisions of
the user in [ADR-C4FZ](C4FZ-camera-requests.md). The agent made these choices A1 to A32. Section 4
of the spec holds the same list, and its sections give the detail. Section 5 of the spec holds the
questions Q1 to Q14. The user decides them.

1. The auto exposure of the camera is never used, also not at the start-up.
2. The search runs at each start-up of an `AUTO` camera: connect, reopen, "apply again".
3. A change of a running camera from `MANUAL` to `AUTO` runs the search on the open stream.
4. 10 delivered frames after the set call returned, then the brightness frame, as sfn26.
5. The rate window: from the 10th to the 40th frame after the set, 30 intervals.
6. The early decision of the check after a live change, for each value, with 30 frames.
7. The offset step applies only to a value that also kept the rate. Else the nearest value stays.
8. "Add light" when the brightness at the brightest value that kept the rate is below 64.
9. The time limit of a search is 20 s.
10. The config keeps `exposure_mode: "AUTO"`, and `exposure` holds the held value.
11. On a running camera, the control thread does the sets and the loop measures. The read each
    second waits.
12. Each camera searches on its own. In the gate, the 10th and 40th frames are the first taken
    frames at or after those counts.
13. A new state `adjusting`: preview and gate as `ready`; a recording and a changed config of that
    camera are refused; after the search, the state goes to `checking`.
14. The ready limit of 15 s does not count the search.
15. `RECOMMEND` in a request is read as `AUTO`.
16. The fall back to 30 fps uses the held values and runs no search.
17. The endpoint `POST /camera/group/exposure/auto`, its response and codes, the status field
    `exposure_search`, and the warning kinds `add_light` and `exposure_search_failed` with their
    texts.
18. The three texts of the reason of a slow camera.
19. Linux and macOS: no mode choice and no search until phase 7. The button gets HTTP 422.
20. No rate above 60 fps is offered.
21. The UI writes one rate to each camera config. No group field.
22. The UI never sends -1 or 0. The API keeps them. `CameraConfigFramerate.tsx` goes. The UI default
    is 30.
23. The real 60 fps check is the start-up rate check at 60 fps. No other probe.
24. The fall back is in the main process, one time, only for the stages `set mode` and
    `rate check`, with the warning `rate_fallback`.
25. Only the UI keeps the last fall back text, for the app run.
26. No rate class for 59.94 with 60. 60 fps is then not offered.
27. The field `usb_link` with the values `USB 1`, `USB 2`, `USB 3`, `unknown`.
28. The label sends no request to the camera: only the connection-information calls at the hub.
29. Port the sfn26 module as `skellycam/core/device_detection/usb_link.py`.
30. On Windows, a bounded lookup of 1 s for each camera in the detection child.
31. The chip `USB ?` for `unknown`. No chip for a virtual camera.
32. The link "Search again" for one camera in the camera settings, and the optional body
    `camera_ids` of the endpoint.

## Reason

The spec gives the reason of each choice in the section that the list of its section 4 names. The
main reasons:

- A1: the search tries each value anyway; the value that a camera reports in auto may not be real;
  the auto exposure of the camera changes the frame rate
  (`research/usb_cameras/docs/free_run_log_20261120.md` §9 on branch `dom/research`).
- A4, A5: in the tests of the check after a live change, a skip of 3 or more frames and a window of
  30 to 90 frames gave 0 false alarms in 119 changes (`specs/windows-capture.md` 10.5).
- A7: the C922 at 60 fps keeps the rate only at -7. The offset step without the guard would give -8,
  at 29.7 fps.
- A21: the one-rate rule already refuses two rates in one request, and the capture layer reads the
  rate of each camera config. No API change.

## Open work

See [open-work.md](../open-work.md).
