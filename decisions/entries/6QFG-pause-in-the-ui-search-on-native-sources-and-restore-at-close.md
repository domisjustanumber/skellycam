# 6QFG — Pause in the UI only, the search on the native sources, no manual exposure, the restore at the close

**Status:** absorbed into
[`specs/camera-requests.md#11-the-rule`](../../specs/camera-requests.md#11-the-rule),
[`specs/camera-requests.md#13b-the-search-at-an-open`](../../specs/camera-requests.md#13b-the-search-at-an-open),
[`specs/camera-requests.md#15-api`](../../specs/camera-requests.md#15-api),
[`specs/camera-requests.md#15a-the-texts-of-a-slow-camera`](../../specs/camera-requests.md#15a-the-texts-of-a-slow-camera),
[`specs/camera-requests.md#16-the-auto-exposure-of-the-camera`](../../specs/camera-requests.md#16-the-auto-exposure-of-the-camera),
[`specs/camera-requests.md#17-linux-and-macos-the-opencv-source`](../../specs/camera-requests.md#17-linux-and-macos-the-opencv-source),
[`specs/camera-requests.md#19-edge-cases`](../../specs/camera-requests.md#19-edge-cases),
[`specs/camera-requests.md#24-the-real-60-fps-check-and-the-fall-back`](../../specs/camera-requests.md#24-the-real-60-fps-check-and-the-fall-back),
[`specs/camera-requests.md#35-what-the-label-shows`](../../specs/camera-requests.md#35-what-the-label-shows),
[`specs/camera-requests.md#5c-decisions-of-the-user-of-2026-11-20-third-set`](../../specs/camera-requests.md#5c-decisions-of-the-user-of-2026-11-20-third-set),
[`specs/camera-requests.md#81-the-rule`](../../specs/camera-requests.md#81-the-rule),
[`specs/unix-capture.md#45-exposure-the-source-parts`](../../specs/unix-capture.md#45-exposure-the-source-parts),
[`specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u`](../../specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u),
[`specs/windows-capture.md#71-detection-on-windows-d11`](../../specs/windows-capture.md#71-detection-on-windows-d11),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user, relayed by the supervisor; commit to dom/requests-spec)).

## Decision

This entry supersedes
[ADR-379P](379P-answers-on-the-choices-after-the-search-at-each-open.md). The user decided items K1
to K4 on 2026-11-20. K1 replaces H8 of 379P. Each other item of 379P stays, with its ID (list
below). [`specs/camera-requests.md`](../../specs/camera-requests.md) cites the items as [K1] to [K4].

- **K1. Pause is a display freeze in the UI only.** The pause button, the menu item and Shift+Space
  freeze the image on the screen. The pause works at all times, also while a camera is `adjusting`
  and during a recording. It does not touch the cameras. The public pause route of the server goes.
  The internal pause that the record start uses stays.
- **K2. The search on Linux and macOS.** The exposure search also runs on the native sources of Linux
  and macOS (`unix-capture.md` 4.5, branch dom/unix-capture-spec). The HTTP 422 and "no `adjusting`"
  apply only to a camera whose source is OpenCV, and to a camera of K3.
- **K3. No working exposure control.** A camera with no working route to set its exposure (for
  example on macOS) gets no Manual and no Auto. Its search is skipped, it is never `adjusting`, and
  the warning of the kind `no_manual_exposure` comes. A request that names an exposure for it is not
  refused.
- **K4. The restore at the close.** The restore of the controls at the close of a camera
  (`unix-capture.md` 4.7) is the one call that is allowed to turn the auto exposure of the camera on
  again. It is not a mode: the camera is then closed.

The items of 379P that stay. Each linked heading states them:

- H1 (the apply does not wait for the search), H2, H3:
  [1.3b](../../specs/camera-requests.md#13b-the-search-at-an-open),
  [1.5](../../specs/camera-requests.md#15-api).
- H4: [2.4](../../specs/camera-requests.md#24-the-real-60-fps-check-and-the-fall-back).
- H5: [1.5a](../../specs/camera-requests.md#15a-the-texts-of-a-slow-camera),
  [1.8](../../specs/camera-requests.md#18-ui).
- H6: [8.1](../../specs/camera-requests.md#81-the-rule).
- H7: [1.5](../../specs/camera-requests.md#15-api).
- The note that G9 of [ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md) decides
  item 6 of [ADR-FTC3](FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md):
  [3.5](../../specs/camera-requests.md#35-what-the-label-shows).

K2 and K4 change the text under the headings 1.1, 1.6 and 1.7 of the spec, which ADR-JK79 links for
Q1 and Q11 of ADR-C4FZ. The spec cites this entry next to each changed rule. Thus JK79 is not
superseded.

## Reason

- The decisions of the user of 2026-11-20, after a review of this spec against `unix-capture.md`
  and `certify.md`.
- K1: the user wants the pause to look at a frozen frame.
- The Rules allow no partial supersession. This entry keeps each other item of 379P by a link to the
  heading that states it.

## Open work

See [open-work.md](../open-work.md).
