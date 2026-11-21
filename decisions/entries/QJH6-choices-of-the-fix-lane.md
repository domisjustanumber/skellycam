# QJH6 — Choices of the fix lane of 2026-11-21

**Status:** proposed, 2026-11-21 (agent; the items come from the supervisor, after reviews and real-camera runs).

## Decision

The fix lane makes small fixes. The supervisor gave each rule. The agent made these choices:

1. E. At an open, a camera in `AUTO` sets its held value inside the search values: the values -12 to -5
   that are in the exposure range of the camera, on its step grid. A held value that is not one of them
   is set at the nearest of them. When the range has no search value, the held value is set inside the
   range, as before ([`camera-requests.md`](../../specs/camera-requests.md) 1.3a).
2. F. The warning kind for a camera that cannot join a running group is `cameras_left_out`. The item is
   only in the `warnings` of the apply response that selects that camera, not in a status: the camera
   has no status in the group ([`windows-capture.md`](../../specs/windows-capture.md) 11.3).

## Reason

1. E. A held value of -1 on a camera with the range -11 to -2 opened at -2 (a 250 ms exposure, 4 fps). The
   warm-up failed, so the camera never searched (a real-camera run).
2. F. Before, the apply answered 200 and left the camera out silently. The UI already closes all cameras
   and connects them again in this case, so the item is for the other consumers of the API.

## Alternatives rejected

1. F. The item in `group_warnings` of each running camera: it names a camera that is not on that row.
