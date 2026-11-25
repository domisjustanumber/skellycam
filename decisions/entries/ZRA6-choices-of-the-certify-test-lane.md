# ZRA6 — Choices of the certify test lane

**Status:** proposed, 2026-11-25 (agent of the certify test lane).

## Decision

The user decided this work as Q772, Q773 and Q775 (session Q44, Q45 and Q47 of 2026-11-25). Another entry records
those decisions. This entry holds only the choices of the agent where the spec is silent or unclear.

1. `no-frame` is a new reason code. `settings-stick:image-effect` is `not-run` `no-frame` when it has no frame at
   -7 or at -8. Before, it was `too-dark`. `skellycam/REASON_CODES.md` and `catalog.REASON_CODES` hold the code.
   Section 15 of `specs/certify.md` does not name it yet.
2. A rate check with no measured brightness keeps its `fail` (`rate-low`). `too-dark` needs a mean below
   `DARK_LUMA`.
3. A black frame (mean 0 at -7) that does not change is `too-dark`, not `no-frame`.
4. `too-bright` does not change: a frame above 230 at -7 is `not-run` `too-bright`, also when the image check
   would pass. Q773 changed the dark side only.
5. The dark rule is two pure functions of `skellycam/core/certify/catalog.py`: `in_the_dark` and `image_effect`.
   The limits of 4.3 and 4.6 move there from `session.py`.
6. The `rate` row reads its brightness from the D-3 key `rate_luma_mean` (3.5.15 P5), because a failed
   start-up rate check writes no ring frame (19.1 item 7). P5 is not built, so T-CERT-09 is a strict `xfail`.
7. `bad-output` is an event of the session child that is not a pair of a known kind and a value of its form, or
   an event that does not unpickle. The drive loop then stops, and the session gets the grace stop of a time-out.
   The running check is `fail` `bad-output` by the rule of a time-out (19.2 item 8). Phase G gets the limit of a
   crash. The run writes no record row.
8. A crash of the session child gives `exit_code` on each `not-run` `crashed` row (T-CERT-78 in 3.6). The row
   stays `not-run`, by 19.2 items 8 and 13.
9. `_native_capture` of `run.py` sets the native source. The thread session of the tests calls it too. Thus
   T-CERT-32 runs the product factory and shows that the OpenCV source is never created. On Linux and macOS the
   test is skipped until phase 7 (Q777).
10. T-CERT-30: the test validator `report_rules.py` refuses a reason, a notice code or an evidence reason that is
    not in `REASON_CODES.md`. The class name of an exception passes (section 15). Thus each run test checks the
    rule.
11. The not-built lists of `catalog.py` drop the checks of Q624: `timings`, `control:focus:sharpness`,
    `control:autofocus`, `control:white-balance`, `control:power-line`, `system:backend` and
    `system:virtual-cameras`. They have `self:scale-3` and `self:scale-12` in place of `self:scale-4` and
    `self:scale-8`.
12. A test that needs a fault in the session child plants it with a picklable fake factory. The factory changes
    the child when the child unpickles it (`ChildFault` of `test_certify_cases.py`). The product has no hook.
13. In the spec, the example of 3.6.9 and the virtual-camera line of 3.4 lose the names of Q624, and the "Today"
    column of section 13 states the code of 2026-11-25.

## Reason

- A missing frame is not a dark room. Two causes need two codes, so a reader can tell them apart.
- A fail with no measured light has no proof of a dark room, so it keeps its fail.
- Pure functions are tested with no camera and no session.
- The session child is a child process that runs a group of checks. The contract gives `bad-output` to such a child
  [C 2.5]. A broken session is a fault of skellycam, not of a camera. So the rule of a time-out applies, and a fault
  of the run writes no record row.
- A fault planted through the factory runs in the real child, with the real queue and the real kill.

## Consequences

- T-CERT-09 passes only after P5. Today the session gets no diagnostics dict of a camera that failed its start-up
  rate check when it judges the open (found by the test, not fixed).
- T-CERT-15 says `fail` `crashed` for the exit with code 5, and 19.2 says that a crash blames no check. The test
  follows 19.2.

## Alternatives rejected

- The brightness of the last ring frames for a slow camera: the ring has no frame of a camera that failed its
  start-up rate check.
- A test hook in the product for the faults of T-CERT-15: the fake factory does the same with no product code.
- A wider fix of the not-built lists (the take rows of Q598, the disk benchmark of Q612, the checks of 3.6.11 and
  3.6.12 that are not listed): it is more than the scope of Q772.

## Open work

[open-work.md](../open-work.md)
