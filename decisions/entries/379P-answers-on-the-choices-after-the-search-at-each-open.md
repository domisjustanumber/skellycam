# 379P — Answers of the user on the choices B4 to B13: the apply does not wait for the search

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor; commit to dom/requests-spec).

## Decision

The user decided these items on 2026-11-20 about the choices of
[ADR-4Z7T](4Z7T-choices-after-the-search-at-each-open.md).
[`specs/camera-requests.md`](../../specs/camera-requests.md) cites them as [H1] to [H8].

- **H1. B4 is rejected.** An apply request, or another request that opens cameras, does not wait for
  the exposure searches. It answers when the cameras are open and streaming (about 4 s, as today).
  The cameras in Auto are then `adjusting`. The found values and the warnings arrive through the live
  status (the `app_state` message of the websocket). A recording cannot start until each camera has
  left `adjusting`.
- **H2. B5 is accepted.** "Update Cameras" searches only the new or the reopened camera. The other
  cameras keep running with their values.
- **H3. B6 is accepted.** A search that fails at an open leaves the camera running at its previous
  value. The check judges it `ready` or `too_slow`. The search never makes a camera `failed`.
- **H4. B7 is accepted.** At 60 fps, a camera in Auto that finds no value that holds 60 fps starts
  the one fall back of the group to 30 fps.
- **H5. B8.** The camera row of the UI shows exactly "Camera is slow. Try adding more light". The
  measured numbers ("declared 30.00 fps, measured 25.76 fps") stay in the detail of the API and in
  the log, not in the row. The warnings keep their own texts.
- **H6. B10 is accepted.** The camera number decides only the order of the cameras in the take. No
  new field goes into the take files.
- **H7. B13 is accepted.** The default exposure mode of `CameraConfig()` in the API is Auto.
- **H8. Pause stays.** The public pause route and the pause button of the UI stay. The user wants a
  pause to look at a frozen frame.

The user also confirmed that decision G9 of
[ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md) decides item 6 of
[ADR-FTC3](FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md): a camera is
virtual also by its link `\\?\root#` or `\\?\swd#vcamdevapi#`. FTC3 is not edited.

The other parts of 4Z7T stay proposed. These include the second case of B7 (the check after the
search fails) and the removal of " Or choose 30 fps." of B8.

## Reason

- The decisions of the user of 2026-11-20. The relay gave a reason only for H8: the user wants to
  look at a frozen frame.
- The reasons of B5 to B13 are in ADR-4Z7T.

## Open work

See [open-work.md](../open-work.md).
