# H7PX — Choices of the agent for the USB 3 capability on macOS and the three-state fact

**Status:** proposed, 2026-11-23 (agent; Q629, on the answer of the user in ADR-BG8P).

## Decision

An agent wrote the macOS part, the three-state fact and the order of the sources of section 3.6.13 of
[`specs/certify.md`](../../specs/certify.md), the field `usb3_capable` of the list of known cameras (9.4), the
test T-CERT-114 and the probe
[`scripts/probe_usb3_capability_macos.py`](../scripts/probe_usb3_capability_macos.py) with the tests of its
parsers in [`scripts/tests/test_probe_usb3_capability_macos.py`](../scripts/tests/test_probe_usb3_capability_macos.py),
on the answer of the user in [ADR-BG8P](BG8P-decision-of-the-user-on-the-any-language-camera-name.md). These
choices replace item 10 of [ADR-M7JC](M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md).
The spec marks them [A, pending Q629]. "Not:" gives the rejected alternative.

1. `usb3_capable` has the values `yes`, `no`, `possible` and `null`, with `usb3_capable_source` (`os`, `list`,
   `bcd`). Not: `true`, `false`, `null` (a certain "no" from `bcdUSB` 0x0200 would be lost).
2. The order: the fact of the system, then the known list, then `bcdUSB`. Not: the known list first (a fact of
   the system is better than a fact of the model).
3. `bcdUSB` 0x0200 or 0x0201 on a USB 2 link gives `no`; 0x0210 or higher gives `possible`. Not: no answer from
   `bcdUSB`.
4. The milder notice `camera-maybe-faster-usb-port` for `possible` on a USB 2 link. Not: no notice (the person
   learns nothing), or the notice of a fact (a guess presented as a fact).
5. The optional field `usb3_capable` of `known_cameras.json`, seeded with the Kiyo Pro `true` and the C922 and
   the C930e `false`. Not: a second list file.
6. The macOS methods ranked: the known list, the BOS request with no open, `bcdUSB`, the IORegistry keys,
   `system_profiler`. Certify uses the BOS request only after the probe shows on a Mac that it answers and that
   the camera keeps working. Not: `USBDeviceOpenSeize` as libusb does (it asks the driver of the camera to let
   go); not an `IOUSBHostObject` (it opens a user client).
7. Before the BOS request the probe checks the function table of the interface (vendor id, product id, release
   number), and sends nothing on a difference. Not: trust the slot numbers alone (a wrong slot could reset the
   device).
8. The probe uses the standard library only, prints no serial, location or path, and prints an error as its class
   name. Not: a probe with PyObjC or libusb (an install on the Mac of the user).

## Reason

A known model gets an exact fact on each system, an unknown model gets the best fact the system gives without
an open of the device, and a guess gives only a mild text.
