# 10HT — The user accepts the choices of the certify report fields, the meaning of `seconds` and the build order

**Status:** absorbed into
[`specs/certify.md#35-report-fields-that-say-why-a-check-failed-u`](../../specs/certify.md#35-report-fields-that-say-why-a-check-failed-u),
[`specs/certify.md#351-common-rules-u-q572-q573`](../../specs/certify.md#351-common-rules-u-q572-q573),
[`specs/certify.md#3510-the-unit-id-removed-u-q595`](../../specs/certify.md#3510-the-unit-id-removed-u-q595),
[`specs/certify.md#3515-build-order-u-q572-q575`](../../specs/certify.md#3515-build-order-u-q572-q575),
[`specs/certify.md#367-build-order-u-q627-dbf8-17`](../../specs/certify.md#367-build-order-u-q627-dbf8-17),
2026-11-23 (commit to dom/certify-4; was accepted, 2026-11-23 (user; the questions Q572 to Q575, to which the
user answered "agree to all"; commit to dom/certify-4)).

## Decision

The user decided these items on 2026-11-23. They are not built.

1. **Q572.** The user accepts the choices of
   [ADR-NQ77](NQ77-choices-of-the-certify-report-fields.md) (items 1 to 12) as a set.
   [`certify.md`](../../specs/certify.md) section 3.5 marks them [U Q572].
2. **Q573.** `seconds` on each row is the duration of the check. The length of a take goes in
   `take_seconds`. A D-3 counter on a row that measures a window is the change of that counter in the
   window, not the count since the open (items 3 and 4 of ADR-NQ77; `certify.md` 3.5.1).
3. **Q574.** The contract text "These facts identify a model, not one unit" must change so that it
   allows the salted unit id of `certify.md` 3.5.10. skellycam does not change the contract. The
   supervising session asks the skellycertify session for the change. The request went to that session on
   2026-11-23. No answer came yet. This item is open work.
4. **Q575.** The build order: the product changes come first, in the order P3, P1, P2, P4. Then C1 and
   the later steps of `certify.md` 3.5.15 follow. The build starts only after the branch of the third
   fix lane (`dom/fix-lane-3`) is merged into `dom/integration`.

## Reason

1. Each choice of ADR-NQ77 keeps one name for one fact and fits format 1.6.0 and 1.7.0 of the
   contract.
2. The contract gives `seconds` as the time of the check [C 2.5]. A second meaning of one name makes
   two reports hard to compare.
3. The contract belongs to the skellycertify repository. Its owner session changes its text.
4. Without the product changes P1 to P4, the failure facts of a wedge stay `null` (`certify.md`
   3.5.15). A build after the merge starts from a base that holds the fixes of the third fix lane.

## Open work

[open-work.md](../open-work.md)
