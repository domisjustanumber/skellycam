# BG8P — Decision of the user on the camera name in any language and the USB 3 capability

**Status:** accepted, 2026-11-23 (user; question Q628; the supervisor relayed the answer).

## Decision

The words of the user: "Q628 agree. USB speed test on mac - try a little harder to build a test we can include
into certify to find out this information".

1. **Q628.** The user accepts the choices of
   [ADR-M7JC](M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md) as written: the camera name
   in any script from the firmware product text only, with the filter of 9.4 of
   [`certify.md`](../../specs/certify.md), and the USB 3 capability of 3.6.13 on Windows (the hub flags) and on
   Linux (sysfs `bos_descriptors`). The spec marks them [U Q628].
2. **macOS, not accepted.** Item 10 of M7JC (`usb3_capable` `null` on macOS, no notice) is not accepted. Certify
   must find out on macOS whether a camera is USB 3 capable but runs on a USB 2 link. The choices for it are in
   [ADR-H7PX](H7PX-choices-of-the-usb-3-capability-on-macos-and-the-three-state-fact.md) (proposed, Q629).

## Reason

A known camera model and a new one must both get a name in any language, and the person must learn on each
system that a USB 3 camera runs slower than it can.

## Open work

[open-work.md](../open-work.md)
