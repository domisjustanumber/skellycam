# CR85 — Decisions of the user on the certify test lane

**Status:** absorbed into
[`specs/certify.md#46-light-too-dark-to-judge-a`](../../specs/certify.md#46-light-too-dark-to-judge-a),
[`specs/certify.md#15-reason-codes-proposed-skellycamreason_codesmd-a`](../../specs/certify.md#15-reason-codes-proposed-skellycamreason_codesmd-a),
[`specs/certify.md#17-test-list-of-the-certify-code`](../../specs/certify.md#17-test-list-of-the-certify-code),
[`specs/certify.md#192-the-review-fixes-and-format-160-u`](../../specs/certify.md#192-the-review-fixes-and-format-160-u),
[`skellycam/tests/certify/test_certify_cases.py`](../../skellycam/tests/certify/test_certify_cases.py),
[`skellycam/tests/certify/report_rules.py`](../../skellycam/tests/certify/report_rules.py),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-25 (user, Q817 to Q823)).

## Decision

The user answered the questions of the certify test lane
([ADR-ZRA6](ZRA6-choices-of-the-certify-test-lane.md)) on 2026-11-25. With these answers the user accepts the
choices of ADR-ZRA6. Q819 changes its item 4.

1. Q817: 19.2 items 8 and 13 of `specs/certify.md` win. A crash of the session child blames no check: the running
   check is `not-run` `crashed` with `exit_code`. The text of T-CERT-15 changes to match.
2. Q818: the reason code `no-frame` is accepted. Section 15 of the spec names it.
3. Q819: `too-bright` follows the dark rule of 4.6. A pass stays `pass`. `too-bright` replaces only a fail.
4. Q820: `bad-output` uses the rule of a time-out (19.2 item 8), as built: the running check is `fail` only when
   the checks that ran belong to one camera or to the group and are not the open.
5. Q821: the self-check lane (Q48) builds the product key `rate_luma_mean` (3.5.15 P5), test first. It also finds
   why certify gets no diagnostics dict of a camera that fails its start-up rate check.
6. Q822: the not-built lists of `skellycam/core/certify/catalog.py` follow the spec: Q598 (two take rows), Q612
   (no `system:disk-benchmark`), Q617 (no 60 fps exposure or Auto check), and the checks of 3.6.11, 3.6.12 and
   3.6.13. T-CERT-91 and T-CERT-121 test them.
7. Q823: the class name of an exception is allowed in `evidence.reasons` (section 15: "any"). It is never a notice
   code.

## Reason

These are the answers of the user to questions 1 to 6 of the first report of the lane and question 7 of its
second report.

## Open work

[open-work.md](../open-work.md)
