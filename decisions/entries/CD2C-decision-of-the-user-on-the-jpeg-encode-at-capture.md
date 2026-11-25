# CD2C — Decision of the user on the JPEG encode at capture

**Status:** accepted, 2026-11-24 (user, relayed by the supervisor).

## Decision

The words of the user on 2026-11-24: "Q689 yes: build the JPEG encode at capture for uncompressed
cameras after fix lane 6 merges, tests first."

Thus step 3b of [`windows-capture.md`](../../specs/windows-capture.md) (sections 13 and 22) is built.
A camera in a YUY2 or NV12 mode gets its frames encoded to JPEG at capture, so each take is JPEG-MKV.
The failing tests come first, then the code.

## Reason

- New takes are JPEG-MKV only, and a camera that gives uncompressed frames must record too.

## Open work

See [open-work.md](../open-work.md).
