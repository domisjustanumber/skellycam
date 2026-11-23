# NQ77 — Choices of the agent for the certify report fields

**Status:** accepted, 2026-11-23 (user; Q572 of ADR-10HT; commit to dom/certify-4; was proposed, 2026-11-23
(agent)).

## Decision

An agent wrote section 3.5 of [`specs/certify.md`](../../specs/certify.md) and the tests T-CERT-77 to
T-CERT-90 on the decisions of the user in
[ADR-F6C3](F6C3-decisions-of-the-user-on-the-certify-report-fields.md). The agent made these choices.
The spec marked them [A]. The user accepted them as a set on 2026-11-23 (Q572 of
[ADR-10HT](10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md)). The spec now
marks them [U Q572].

1. Names: `first_fail_code` (not `first_code`), `stage` (not `fail_stage`), `cpu_cores_used` and
   `cpu_share_p95` of 6.1, `driver_kind` as a closed vocabulary (no provider name), `bcd_usb` and
   `bcd_device` as 4 hex digits.
2. `details.cameras` is a list of objects with `label`, the form of the plan.
3. `seconds` on each row is the time of the check; the take length becomes `take_seconds`, the
   benchmark time `write_seconds`; `t_start_s` counts from `perf_counter_ns` at the call.
4. A D-3 counter on a window row is the change in the window (`records`, `clock`, `sequence`,
   `time-gaps`).
5. The failure facts are on each row whose reason is a product failure code, also `rate-low` and
   `camera-in-use`; `exit_code` on each `crashed` and `hung` row.
6. New product keys: `first_fail_code` and `exit_code` (D-5); the rate window keys (D-3); the call
   names `reader-release`, `control-release`, `set-controls` (`unix-capture.md` 4.6.2, 4.6.3).
7. The rate row gets `exposure`, `exposure_before` and `exposure_before_auto`; the settings rows get
   the range and the gain at -7 and -8.
8. `take_warnings` is a list of manifest codes that `REASON_CODES.md` lists; `take_error_kind`,
   `take_error_camera`, `free_gb`.
9. The unit id: 8 hex digits of HMAC-SHA256 with a 32-byte key in `certify_unit_key` of the base
   folder, over the identity string of the `camera_id`; no expiry; a deleted key resets the ids.
10. The logs: `certify_logs/` of the base folder, replaced at the start of each run that holds the
    lock, kept after a cancel or a crash, each file cut to its last 1 MiB, at most 64 files;
    `details.logs_kept`.
11. Size bounds: 128 KiB for a full report of four cameras, 48 KiB for a quick one (indent 1).
12. The build order of 3.5.15: the product changes P1 to P4 first.

## Reason

Each choice keeps one name for one fact, reuses the names that the spec already lists, and fits
format 1.6.0 and 1.7.0 of the contract with no change.
