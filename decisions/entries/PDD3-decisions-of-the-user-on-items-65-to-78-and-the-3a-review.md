# PDD3 — Decisions of the user on items 65 to 78 and on the review of the 3a code

**Status:** accepted, 2026-11-20 (user, 2026-11-19 and 2026-11-20, relayed by the supervisor; commit to dom/native-jpeg).

## Decision

The user decided these points on 2026-11-19 and 2026-11-20, after the join of the two code branches
of step 3a and an independent review of that code. They correct
[`specs/windows-capture.md`](../../specs/windows-capture.md), which marks each one [Wn] and lists
them in section 20. They add to [ADR-HB4Z](HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md).

1. **W1.** Items 65 to 78 of section 18 of the spec are accepted as written, except as W2 and W3
   change them.
2. **W2.** The first part of item 76 is rejected. When OpenCV reports no frame rate, the start-up
   check still measures the rate over the warm-up frames 6 to 90. It compares the rate with the
   requested rate of the config, and with 30 fps for "auto" (-1 or 0). The limit is 3 %. A slower
   camera fails at start-up, as on Windows. The status reports the measured rate. This replaces the
   part of D46 that runs the check only with a reported rate.
3. **W3.** Item 75: the warning of different real rates on OpenCV is a log record at WARNING and an
   item of the `warnings` list of the apply response, with the kind `mixed_rate`.
4. **W4.** Step 3a adds `replaced_count` to the status of each camera. It counts from the first
   frame that the camera takes in the gate (5.2).
5. **W5.** Detection shows a virtual camera with `virtual: true`. A request that names a virtual
   camera gets HTTP 422. Support of virtual cameras is a later task (open work).
6. **W6.** Detection stores and shows the device `path` as the OS gives it. Only the input of the
   `camera_id` hash is in lower case.
7. **W7.** skellycam reconfigures `stdout` and `stderr` to UTF-8 at its entry point and in each
   worker process, before the logging is configured.
8. **W8.** The phase 2 camera loop is dead code. Delete it, and the code that only it uses, together
   with T-RING-31, which tests only that loop. T-CAP-49 checks the same rule ("a paused camera does
   not spin") on the shared loop. A dated note at T-RING-31 in
   [`specs/frame-ring.md`](../../specs/frame-ring.md) records the retirement.

## Reason

- W2: a camera that delivers less than the requested rate must not pass in silence on Linux and
  macOS, when OpenCV gives no rate.
- W3: a consumer must see the warning in the response, as for the rate class of U15.
- W4, W5, W6: the review found that the status, the detection and the docs did not agree on these
  points.
- W7: a piped console on Windows is cp1252, and each log line with the box-drawing prefix of
  skellylogs then fails with "--- Logging error ---".
- W8: no camera process runs the phase 2 loop. A test of it measures code that no user runs.

## Consequences

- W2 changes the criteria of T-CAP-44, T-CAP-92, T-CAP-94, T-CAP-97, T-CAP-99 and T-CAP-101.
- W8: the agent of the 3a review found other tests that call the phase 2 loop. The proposed entry
  of the review ([ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md)) records what was done.

## Open work

See [open-work.md](../open-work.md).
