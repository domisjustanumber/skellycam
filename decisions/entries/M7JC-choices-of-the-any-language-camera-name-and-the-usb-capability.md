# M7JC — Choices of the agent for the camera name in any language and the USB 3 capability

**Status:** absorbed into
[`specs/certify.md#363-the-details-objects`](../../specs/certify.md#363-the-details-objects),
[`specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629`](../../specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629),
[`specs/certify.md#94-privacy-and-camera-names-u-a`](../../specs/certify.md#94-privacy-and-camera-names-u-a),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-23 (user; Q628 of ADR-BG8P, except item 10, which
ADR-H7PX replaces; commit to dom/certify-4; was proposed, 2026-11-23 (agent))).

## Decision

An agent wrote the name rule of 9.4 and section 3.6.13 of [`specs/certify.md`](../../specs/certify.md), with the
tests T-CERT-94 and T-CERT-114, on the answers of the user in
[ADR-63D9](63D9-decisions-of-the-user-on-the-processors-the-build-order-and-the-certify-choices.md). These
choices replace item 18 of [ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md) and items 2 and 9 of
[ADR-DBF8](DBF8-choices-of-the-certify-names-verdicts-and-checks.md). The spec marks them [A, pending Q628].
"Not:" gives the rejected alternative.

1. For a new USB id the name is the firmware product text only; the display name of the OS is not copied, and
   `name_os` goes. Not: both texts (a person or the OS can set or translate the display name).
2. The filter keeps exactly the set of the relay (L, M, N of any script, the space and its signs), after NFKC,
   and joins the spaces. Not: the stricter set with no `: / ; = % ?` (the pattern tests refuse each path, URL and
   email form).
3. The direction marks are removed; another character of Cf, Cc, Co, Cs or Cn gives `Camera vvvv:pppp`. Not:
   replace them with a space (a control character tells a damaged or a crafted text).
4. The cut at 60 code points moves back before a base character with marks; at most 240 bytes in UTF-8. Not: a
   cut at a byte count (it splits a letter).
5. A word with letters of two scripts gives `Camera vvvv:pppp`; the script is the first word of the Unicode
   name. Not: a confusables table (a new data file for a rare case).
6. A user or host name of 3 code points or more is refused anywhere; one of 1 or 2 only as a whole word. Not: a
   substring test for each length (a one-letter user name would blank most names).
7. The order: no USB id first, then the Apple words, then the list, then the firmware text. Not: the Apple words
   first (a camera with no USB id never has its text copied, in any order).
8. The key `usb3_capable` (`true`, `false`, `null`) and the notice only with `true` on a `USB 2` link. Not: the
   notice from `bcd_usb` (pure USB 2 cameras declare 0x0210).
9. Linux reads the capability from sysfs `bos_descriptors`; with no such file the value is `null`. Not: a BOS
   request through usbfs (it needs write access to the device node).
10. macOS gives `null` for now. Not: an `IOUSBHostObject` (it opens a user client to the device).
11. No streaming throughput test; the inventory facts and `group:contention` answer the question. Not: a stream
    of each camera at each mode (minutes of opens, the main cause of a wedge).

## Reason

The rule must work for any language (Q625 refused). Each choice keeps the name from a source that a person does
not set, keeps out of the report each character that could change the Markdown around it, and reads only facts
that need no open of the device.
