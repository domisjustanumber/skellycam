# MA22 — Choices of the Media Foundation source of step 3a

**Status:** proposed, 2026-11-19 (agent).

## Decision

The package `skellycam/core/camera/capture/media_foundation/` follows
[`specs/windows-capture.md`](../../specs/windows-capture.md) (section 6 and 7) and
[ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md). An agent made the choices
below. The spec and ADR-HP7D do not fix them.

1. Detection writes `CameraDeviceInfo.path` as the lower-case symbolic link. Thus
   `CameraDeviceInfo.camera_id` gives the `camera_id` of 7.2, and `CameraDeviceInfo` does not
   change.
2. `MediaFoundationSource()` has no argument. The request of `open` holds all the data that the
   source needs. A `source_factory` is `lambda config: MediaFoundationSource()`.
3. For an HRESULT that has no name in `errors.NAMES`, the reason is the code as eight hex digits,
   for example `0xC00D1234`.
4. One bounded call does all of one `set_controls`: each set, then the read-back of all five
   controls (`exposure`, `focus`, `gain`, `white_balance`, `power_line_frequency`).
5. When `OnFlush` does not come within 5 s after `Flush`, the close continues with the next step.
   The prototype does the same.
6. A failed `IMFSample::GetSampleTime` starts the `NO_SAMPLE_NS` rule of 4.2: the source writes
   `NO_SAMPLE_NS` for the rest of the open.
7. When `open` fails without a hang, the source runs the close. When a close step then hangs, `open`
   raises the first failure with `hung=True`, so that the camera process ends hard (6.6).
8. `MF_SOURCE_READERF_ERROR` with a successful HRESULT gives the reason `E_FAIL`.
9. Detection does not remove virtual cameras or devices with no VID and PID. The caller can remove
   them.
10. When `ActivateObject` returns after its time limit, the bounded call shuts down only the new
    `IMFMediaSource`. It does not call `IMFActivate::ShutdownObject`. The camera process ends hard
    after each hang.

## Reason

- Each choice is the smallest change that agrees with the spec and the prototype.
- Item 1: `detect_cameras_devices.py` is not in the scope of this package.
- Item 7: a failure must not hide a hung close step, because only a hard end is safe after a hang.

## Alternatives rejected

- Item 1: `CameraDeviceInfo.camera_id` hashes the lower-case path. That changes the IDs of Linux and
  macOS paths with upper-case letters, and it changes a module outside this package.
- Item 4: one bounded call for each control. The prototype does that, but it starts more threads
  for the read of one time per second.

## Open work

See [open-work.md](../open-work.md).
