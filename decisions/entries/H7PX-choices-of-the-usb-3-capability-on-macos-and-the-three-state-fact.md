# H7PX — Choices for the USB 3 capability on macOS and the three-state fact

**Status:** absorbed into
[`specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629`](../../specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629),
[`specs/certify.md#94-privacy-and-camera-names-u-a`](../../specs/certify.md#94-privacy-and-camera-names-u-a),
[`specs/certify.md#23-order-of-a-run-u-a`](../../specs/certify.md#23-order-of-a-run-u-a),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-23 (user; question Q629 in a revised form; the
supervisor relayed the answer; was proposed, 2026-11-23 (agent))).

## Decision

The user first refused the stand-alone probe of the earlier form of this entry: "the certify process is the only
way any tests are ever run on machines other than this one". Then he agreed ("Q629 agree") to this form: "The
method trial runs inside certify: The three-state fact (yes, no, possible) and the milder notice for "possible"
as before. On macOS and Linux, a record-only check at the end of a full run tries every method and reports each
answer. The request to the camera runs last, followed by a check that the camera is still listed."

[`specs/certify.md`](../../specs/certify.md) 3.6.13 states these rules, with the tests T-CERT-114 and T-CERT-129
to T-CERT-132. They replace item 10 of
[ADR-M7JC](M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md).

1. `usb3_capable` has the values `yes`, `no`, `possible` and `null`, with `usb3_capable_source` (`os`, `list`,
   `bcd`), in the order: the fact of the system, the known list, `bcdUSB`.
2. `bcdUSB` 0x0200 or 0x0201 on a USB 2 link gives `no`; 0x0210 or higher gives `possible`; a SuperSpeed link
   gives `yes`.
3. `camera-usb3-on-usb2-link` fires on `yes`; the milder notice `camera-maybe-faster-usb-port` on `possible`.
4. The optional field `usb3_capable` of `known_cameras.json`: the Kiyo Pro `true`, the C922 and the C930e
   `false`.
5. The trial `<label>:usb3-trial`: full only, macOS and Linux, one row for the first unit of each model, after
   phase G and before phase H; each method that sends nothing first; the request to the camera last (macOS: a
   GET_DESCRIPTOR(BOS) through `IOUSBDeviceInterface::DeviceRequest` with no open; Linux: through usbfs); no
   request when the vendor id, the product id and the release number do not match; then one new listing, with
   `still_listed` and the notice `camera-gone-after-usb-trial` when the camera is gone; `record-only`, no gate,
   no verdict; error class names from a fixed list; no free text, serial, location id, path or product text.
6. A later decision of the user moves the request to the detection or removes the trial, after its reports.
7. No stand-alone probe: the script of the earlier form and its tests are removed; their synthetic samples are
   the samples of T-CERT-114.

## Reason

Certify is the only way that tests run on the systems of other people. A known model gets an exact fact, an
unknown model gets the best fact that the system gives without a request, and the request runs once, last,
with a check that the camera is still there.
