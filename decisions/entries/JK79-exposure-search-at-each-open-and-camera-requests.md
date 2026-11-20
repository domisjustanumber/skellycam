# JK79 — Exposure search at each open, one slow-camera text, camera number, `usb_link`, virtual links

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor; commit to dom/requests-spec).

## Decision

This entry supersedes [ADR-C4FZ](C4FZ-camera-requests.md). The user decided items G1 to G9 on
2026-11-20. [`specs/camera-requests.md`](../../specs/camera-requests.md) cites them as [G1] to [G9].
They change these items of C4FZ: E3 (the search runs only when the user asks), E5 (the default
Manual -7), the text of E7, Q3 and Q8. Each other item of C4FZ stays, with its ID (list below).

- **G1. The search at each open.** This reverses the rule "the search runs only when the user asks"
  of E3 and Q3. A camera in Auto runs the exposure search:
  - (a) at each open of that camera;
  - (b) when the user changes the frame rate, before the rate check judges the camera;
  - (c) when the user asks: the button for all cameras, "Search again", or a switch to Auto.

  A camera in Manual keeps the value of the user and never searches. A new camera starts in Auto.
  This replaces E5.
- **G2. During the search.** A search takes about 10 s for each camera at 30 fps. All cameras search
  at the same time. The preview shows, and the state of the camera is `adjusting`. A recording
  cannot start until each camera is done.
- **G3. The text of a slow camera.** In every case, the text is exactly:
  "Camera is slow. Try adding more light". It replaces the texts of Q8 and of the `too_slow` row:
  "Add light or lower the exposure, or set the exposure to Auto." and "Too slow at this exposure:
  lower the exposure".
- **G4. Restated, no change.** The exposure does not change during a take. "Auto" always means that
  SkellyCam finds a manual value with its one-shot search on the open stream. The auto exposure of
  the camera is never a mode.
- **G5. The names of the Auto API.** As items 3 and 11 of
  [ADR-Y6F6](Y6F6-camera-request-choices.md) propose: the config field `exposure_found_at_fps`, the
  endpoint `POST /camera/group/exposure/auto`, the status field `exposure_search`, and the warning
  kinds `add_light` and `exposure_search_failed`. The other parts of item 11 (the body, the
  response, the codes and the texts) stay proposed.
- **G6. Old requests.** A request with `RECOMMEND` is read as Auto (item 10 of ADR-Y6F6). Thus it
  searches at the open (G1).
- **G7. The camera number of a take.** A take uses the camera number of the camera list. The UI
  sends the camera number and the name of the current detection with each apply request. The
  recorder writes the number of the request.
- **G8. The USB link field.** One field `usb_link` with the values `USB 1`, `USB 2`, `USB 3` and
  `unknown`, not `usb_version` (item 19 of ADR-Y6F6).
- **G9. Virtual cameras by their link.** A camera is virtual also by its device link, not only by
  its name. On Windows, that is a link that starts with `\\?\root#` or `\\?\swd#vcamdevapi#`. Thus
  NDI cameras show greyed as "virtual". This is the rule of the detection
  ([`windows-capture.md`](../../specs/windows-capture.md) 7.1). It is the rule that item 6 of
  [ADR-FTC3](FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md) proposes.

The items of C4FZ that stay. Each linked heading states them:

- E1, Q1: [1.1](../../specs/camera-requests.md#11-the-rule),
  [1.6](../../specs/camera-requests.md#16-the-auto-exposure-of-the-camera).
- E3 (the other parts: one shot, the open stream, a held manual value, never during a take), E4, Q2:
  [1.1](../../specs/camera-requests.md#11-the-rule),
  [1.2](../../specs/camera-requests.md#12-when-the-search-runs).
- E2, E6, E7 (not its text), E8, Q4, Q5, Q6:
  [1.3](../../specs/camera-requests.md#13-the-search).
- E9, Q7: [1.4](../../specs/camera-requests.md#14-states-and-the-other-cameras).
- Q11: [1.7](../../specs/camera-requests.md#17-linux-and-macos-the-opencv-source).
- F1 to F4: [2.1](../../specs/camera-requests.md#21-the-rule).
- Q13: [2.2](../../specs/camera-requests.md#22-where-the-value-lives).
- Q9, Q10: [2.4](../../specs/camera-requests.md#24-the-real-60-fps-check-and-the-fall-back).
- Q14: [2.5](../../specs/camera-requests.md#25-when-the-ui-offers-60-fps).
- L1 to L5, Q12: [3.1](../../specs/camera-requests.md#31-the-rule),
  [3.5](../../specs/camera-requests.md#35-what-the-label-shows).

## Reason

- The decisions of the user of 2026-11-20. The relay gave no reason for G1 to G9.
- The Rules allow no partial supersession. This entry keeps each item of C4FZ that stays, by a link
  to the heading that states it. The reasons of those items are in C4FZ.

## Open work

See [open-work.md](../open-work.md).
