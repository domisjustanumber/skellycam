# 13BB — Decisions of the user on the dark rule, the light data and the certify items of phase 7

**Status:** absorbed into [`specs/certify.md#46-light-too-dark-to-judge-a`](../../specs/certify.md#46-light-too-dark-to-judge-a),
[`specs/certify.md#101-the-decision-and-the-state`](../../specs/certify.md#101-the-decision-and-the-state),
[`specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data`](../../specs/certify.md#20-exclusive-access-the-public-calls-for-freemocap-and-the-light-data),
2026-11-25 (commit to dom/exclusive-access-spec, Q813 of ADR-5PAR; was accepted, 2026-11-25 (user; the supervisor asked Q773, Q774 and Q777 in a grilling session; the answer was "agree to all")).

## Decision

1. **Q773 (session Q45).** The dark rule of certify (a small product change, in the certify lane of Q772): a check
   that passes stays `pass`, also in the dark; `too-dark` replaces only a `fail`; a missing frame or ratio gets its
   own reason; T-CERT-13 gets a dark case, and T-CERT-09 and T-CERT-23 are written. Today the code gives `not-run`
   `too-dark` whenever the brightness at -7 is below `DARK_LUMA`, also after a pass.
2. **Q774 (Q46).** Each certify report records `luma_mean` for each camera and the answer to "lit as usual". The
   limit is set later from the pooled reports. Until then `DARK_LUMA` stays 24 and the report marks it as not
   calibrated (`details.limits.dark_luma`). Spec text and tests only.
3. **Q777 (Q49).** The Linux and macOS certify items wait for phase 7: T-CERT-37, 40, 46, 52 to 57, 60, 62 and 63, and
   the fake layers. They stay `not-built` in the report. On Linux and macOS the certify child would today fall back to
   the OpenCV source; phase 7 fixes this when it sets the capture choice of each OS.

## Reason

1. The code differs from section 4.6 of the spec, and a missing frame is not a dark frame.
2. Nothing collects the data of a calibration today: `luma_mean` is empty exactly when the rate check fails, which is
   the dark case, and the answer is never kept with the brightness.
3. These checks need the native sources, which do not exist yet.

## Open work

[open-work.md](../open-work.md)
