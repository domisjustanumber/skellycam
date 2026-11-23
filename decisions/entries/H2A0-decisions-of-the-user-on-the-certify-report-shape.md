# H2A0 — Decisions of the user on the shape of the certify report

**Status:** accepted, 2026-11-23 (user; questions Q591 to Q599 after the review of the certify report; the
supervisor relayed the answers).

## Decision

The user decided these items on 2026-11-23. They are not built. [`certify.md`](../../specs/certify.md) section
3.6 states them; the choices of the agent are in
[ADR-MEE1](MEE1-choices-of-the-certify-report-shape.md) (proposed).

The words of the user: "Otherwise Q591-Q599 agree"; "Q595 agree"; "Agree" (Q596, final form).

1. **Q591.** A check that has no code leaves `checks`. Its name stands one time in `details.not_built`.
2. **Q592.** A camera that cannot go on gets one row `<label>:not-reached` in place of its filled `not-run` rows.
3. **Q593.** Quick is a smoke test. Six checks of each camera move to full: `native-jpeg:not-reencoded`,
   `native-jpeg:source-equals-ring`, `native-jpeg:ring-equals-mkv`, `native-jpeg:size`,
   `settings-stick:image-effect` and `records:gaps-explained`. Quick keeps: detected with an MJPG mode, opens,
   rate, mode granted, a set value reads back and holds, the frames are the camera's own valid JPEG, a take of
   3 s with all rows that decodes.
4. **Q594.** Section 3.5 changes before it is built: the time and the CPU stand one time for each step in
   `details.steps[]`, not on each row; a key of a failure fact is in a row only when it has a value; these keys
   are dropped: `failed_calls`, `window_frames`, `interval_p95_ms` and `exposure` of the rate row,
   `grid_16ms_share`, `grain_ms`, `has_serial`.
5. **Q595.** No unit id: `unit_id`, `unit_ids_new` and the key file `certify_unit_key` are removed. A report only
   needs to say if a camera model works. Units get plain labels that can differ between runs. The permission of
   the contract for a unit id stays unused.
6. **Q596.** Camera names. (1) A USB id in the list of known cameras of the package gives the name of the list.
   (2) A real USB camera with a new id gives the name text of the device through a safety filter. The question
   text that the user agreed to: "plain letters, digits and a few signs only, at most 60 characters, and never a
   string that holds the user name or the computer name". (3) A name with an Apple device word (iPhone, iPad,
   MacBook, iMac, FaceTime, Continuity) is never copied; the report holds a fixed class: "iPhone used as camera",
   "iPad used as camera", "Mac built-in camera". (4) No USB id and no known word: "Camera (no USB id)". (5) is
   withdrawn (see below). For a new USB id the report holds both the display name of the OS and the product text
   of the firmware, where they can be read, each through the same filter. The reason, in the words of the user:
   "we need to know the names of the cameras, so if we find one that does or does not work, we can tell
   end-users". No language model and no name recognition. A question to the person about make and model is later
   work. The generic 4c4a:4a55 has no entry in the list, because many cameras share
   that id. The seed list of the file is a choice of the agent (ADR-DBF8).
   Correction before the first push: point (5), "a human reviewer still sees each report before it is
   public", was a false premise of the supervisor: the relay publishes first (contract 4.1). The user is asked
   to confirm Q596 without it (Q625).
7. **Q597.** The seven rows `<model>:gate:<step>` go. `<model>:gate` and `gate:no-hang` stay. `details` names the
   first check that did not pass, never `numbers` and never a key `reason`. The spec names the checks that each
   gate requires.
8. **Q598.** `group:take` has two rows, not five. Each test that can fail keeps a check that carries its
   failure.
9. **Q599.** The full gate is not a production sign-off until three checks are built and in the gate: repeated
   open and close cycles (`cycles`), a take of 30 s (`group:take-30`), and all cameras together under USB
   contention (`group:contention`, `group:open`).
The later decisions Q608 to Q618 of the same day are in
[ADR-BW5M](BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md). These earlier decisions
still hold: Q585 ([ADR-Z7F3](Z7F3-choices-of-fix-lane-3.md)); the schema id
`skellycertify.report/1.7.0`; the common codes `no-commit` and `modified-tree` with their meaning in the
contract.

**What this entry replaces.** It replaces parts of three accepted entries; their text does not change:

- [ADR-F6C3](F6C3-decisions-of-the-user-on-the-certify-report-fields.md): Q558 (the salted unit id), by Q595;
  the "start time and duration for each check" of Q557, by the time of each step (Q594).
- [ADR-NQ77](NQ77-choices-of-the-certify-report-fields.md): item 9 (the unit id) and the `unit_ids_new` key, by
  Q595; the per-row `t_start_s` and `seconds` of item 3, by Q594; the presence of the failure keys on each failure
  row (item 5), by Q594; the `exposure` of the rate row and the range on the settings rows (item 7), by Q594; the
  seven dropped keys (`failed_calls`, `window_frames`, `interval_p95_ms` of the rate row, `exposure` of the rate
  row, `grid_16ms_share`, `grain_ms`, `has_serial`); the size bounds of item 11, by section 3.6.5 of the spec.
- [ADR-10HT](10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md): the first sentence of
  Q573 (`seconds` on each row), by Q594; Q574 (the request to the skellycertify session), which that session
  answered in its commit `cf9c7a2` and which Q595 makes unused. The rest of Q573 (a counter in a window is the
  change in the window) stays.

## Reason

The review of 2026-11-23 measured the reports: 17 quick rows for each camera, 127 of 261 full rows `not-built`,
and about half of the bytes repeats or filler. The user wants a smoke test in quick, a sign-off or the facts for
a fix in full, no leak of user data, and short reports.

## Open work

[open-work.md](../open-work.md)
