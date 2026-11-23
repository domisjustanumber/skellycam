# 63D9 — Decisions of the user on the self-checks of each processor, the build order and the certify choices

**Status:** absorbed into
[`specs/certify.md#36-the-report-shape-of-quick-and-full-u-q591-to-q599-q608-to-q624`](../../specs/certify.md#36-the-report-shape-of-quick-and-full-u-q591-to-q599-q608-to-q624),
[`specs/certify.md#367-build-order-u-q627-dbf8-17`](../../specs/certify.md#367-build-order-u-q627-dbf8-17),
[`specs/certify.md#3612-drops-and-additions-of-q624-u-q624a-to-q624m`](../../specs/certify.md#3612-drops-and-additions-of-q624-u-q624a-to-q624m),
[`specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629`](../../specs/certify.md#3613-the-usb-3-capability-on-each-system-u-q624k-63d9-q628-q629),
[`specs/certify.md#7-self-checks-with-fake-cameras-phase-e-u-a`](../../specs/certify.md#7-self-checks-with-fake-cameras-phase-e-u-a),
[`specs/certify.md#94-privacy-and-camera-names-u-a`](../../specs/certify.md#94-privacy-and-camera-names-u-a),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-23 (user; a later answer to Q624g and the questions
Q625 to Q627; the supervisor relayed the answer)).

## Decision

The words of the user: "Q624g - keep the ring and idle-processor self-checks on every processor. Q625 - this
needs to work for any language, latin letters only is not sufficient. Q626 - agree. Q627 - agree. USB speed test
- include test you think would be appropriate for this in mac and linux too."

1. **Q624g, reversed.** `self:idle-cpu`, `self:ring:torn` and `self:ring:lapped` run on every processor, not on
   ARM only. This replaces item g of
   [ADR-493E](493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md), which does not change.
2. **Q626.** The build order of [`certify.md`](../../specs/certify.md) 3.6.7 (the fix of B1 and the commit
   fields first, then the report shape, then the product changes P3, P1, P2, P4) replaces the order of Q575 of
   [ADR-10HT](10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md).
3. **Q627.** The user accepts the choices of the agent as a set:
   [ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md) and
   [ADR-DBF8](DBF8-choices-of-the-certify-names-verdicts-and-checks.md) move from proposed to accepted. The spec
   marks them [U Q627, MEE1 n] and [U Q627, DBF8 n]. Not accepted: item 18 of MEE1 and items 2 and 9 of DBF8 (the
   camera names and the USB link notice). The answers below change them, and
   [ADR-M7JC](M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md) (proposed, Q628) holds
   the new choices.
4. **Q625, refused.** The name rule must work for any language. A rule that gives `Camera vvvv:pppp` for each
   name that is not in Latin letters is not sufficient. The new rule is in 9.4 of the spec, for Q628.
5. **The USB speed test.** The notice of a USB 3 camera on a USB 2 link also gets a test on macOS and Linux,
   as the agent thinks appropriate (ADR-M7JC).

## Reason

The self-checks of the ring and of the idle processor test the software on the processor of the person, also on
x86-64. A name rule for Latin letters only gives no name to many cameras outside Europe and America.

## Open work

[open-work.md](../open-work.md)
