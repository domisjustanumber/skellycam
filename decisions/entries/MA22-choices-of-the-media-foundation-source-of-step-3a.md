# MA22 — Choices of the Media Foundation source of step 3a

**Status:** proposed, 2026-11-19 (agent).

## Decision

The package `skellycam/core/camera/capture/media_foundation/` follows
[`specs/windows-capture.md`](../../specs/windows-capture.md) (section 6 and 7) and
[ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md). An agent made the choices
below. The spec and ADR-HP7D do not fix them.

1. Open: this item waits for the user. Detection writes `path` as Media Foundation gives the
   symbolic link. Only the input of the `camera_id` hash is in lower case (7.2). The result type
   `MediaFoundationDeviceInfo` is a `CameraDeviceInfo` whose `camera_id` hashes the lower-case path,
   because `detect_cameras_devices.py` is not in this package. When `CameraDeviceInfo.camera_id`
   hashes the lower-case path, this type can go.
2. `MediaFoundationSource()` has no argument. The request of `open` holds all the data that the
   source needs. A `source_factory` is `lambda config: MediaFoundationSource()`.
3. For an HRESULT that has no name in `errors.NAMES`, the reason is the code as eight hex digits,
   for example `0xC00D1234`.
4. One bounded call does all of one `set_controls`: each set, then the read-back of the three
   controls of step 3a (`exposure`, `focus`, `gain`, 11.4). A read uses `Get` only, with no
   `GetRange`. During the close, `set_controls` gives each control as absent.
5. When `OnFlush` does not come within 5 s after `Flush`, the close continues with the next step.
   The prototype does the same.
6. A failed `IMFSample::GetSampleTime` starts the `NO_SAMPLE_NS` rule of 4.2: the source writes
   `NO_SAMPLE_NS` for the rest of the open.
7. When `open` fails without a hang, the source runs the close. When a close step then hangs, `open`
   raises the first failure with `hung=True`, so that the camera process ends hard (6.6).
8. `MF_SOURCE_READERF_ERROR` with a successful HRESULT gives the reason `E_FAIL`.
9. Open: this item waits for the user. Detection removes each device whose friendly name contains
   "virtual", as `filter_virtual=True` does today. It does not remove a device with no VID and PID.
10. When `ActivateObject` returns after its time limit, the bounded call shuts down only the new
    `IMFMediaSource`. It does not call `IMFActivate::ShutdownObject`. The camera process ends hard
    after each hang.
11. The main process waits at most `BOUNDED_CALL_LIMIT_S` + 2 s (7 s) for each message of the
    detection child. The child sends a message after its start and after each bounded call. When no
    message comes in time, the main process stops the child and raises a failure with the stage
    `detection`.

## Consequences

Two points wait for the camera tests:

- The source ignores `OnEvent`. When an unplug comes only as an event, the camera is dead after the
  stall limit ("no frame for 2 s"), not at once.
- A failed `ConvertToContiguousBuffer` or `IMFMediaBuffer::Lock` puts an error marker in the waiting
  place. Thus it ends the stream.

## Reason

- Each choice is the smallest change that agrees with the spec and the prototype.
- Items 1 and 9: these are the conservative forms. They keep the path and the filter of today.
- Item 7: a failure must not hide a hung close step, because only a hard end is safe after a hang.

## Alternatives rejected

- Item 1: detection writes the lower-case link as `path`. That changes the path that the OS gives.
- Item 4: one bounded call for each control. The prototype does that, but it starts more threads
  for the read of one time per second.

## Open work

See [open-work.md](../open-work.md).
