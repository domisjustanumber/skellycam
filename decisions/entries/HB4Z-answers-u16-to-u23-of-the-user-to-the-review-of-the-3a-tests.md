# HB4Z — Answers U16 to U23 of the user to the review of the 3a tests

**Status:** absorbed into
[`specs/windows-capture.md#20-decisions-of-the-user-d1-to-d49`](../../specs/windows-capture.md#20-decisions-of-the-user-d1-to-d49),
[`specs/windows-capture.md#15-ci-d47`](../../specs/windows-capture.md#15-ci-d47),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`specs/windows-capture.md#162-test-list`](../../specs/windows-capture.md#162-test-list),
[`specs/windows-capture.md#167-parity-of-the-systems-u22`](../../specs/windows-capture.md#167-parity-of-the-systems-u22),
[`specs/windows-capture.md#18-choices-of-the-agent`](../../specs/windows-capture.md#18-choices-of-the-agent),
2026-11-23 (commit to dom/absorb-2; was accepted, 2026-11-19 (user; commit to dom/native-jpeg)).

## Decision

The user reviewed the failing tests of step 3a and their report on 2026-11-19, and gave eight
answers. They correct [`specs/windows-capture.md`](../../specs/windows-capture.md), which marks each
one [Un] and lists them in section 20. They add to
[ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md) and
[ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md).

1. **U16.** The control read of one time per second and each live control change run on a separate
   thread of the camera process, not on the loop thread. A hung control call can never hold the
   gate. The thread sleeps between reads (no spin). On a hang, the camera still dies as specified:
   report, the file finish of U12 during a recording, hard end. The other cameras lose no frames.
   T-CAP-82 and T-CAP-85 require no gap above 100 ms on the other cameras.
2. **U17.** (a) The warm-up counts the frames that the camera delivers, from the first frame after the
   controls are read back. (b) `measured_fps` in the status is not rounded. (c) The main process
   keeps the last detection result, by `camera_id`, for the whole-request check. (d) T-RING-46 and
   its expected-failure mark change together with the product code of step 3a, because the warning
   pipe moves to the main process. The ring test does not change before that code.
3. **U18.** The whole package `media_foundation/` is Windows only, and it can load `comtypes`
   anywhere. T-CAP-22, T-CAP-23, T-CAP-24 and T-CAP-48 run on the Windows development machine and on
   the Windows CI job, and are skipped on other systems. Their kinds do not change.
4. **U19.** The user accepts
   [ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md), as corrected by U18.
5. **U20.** CI runs on three systems. The capture workflow gets an Apple Silicon macOS job (macOS 15
   or later) for the fake-source tests, the OpenCV-source tests and the portable ring tests. The
   arm64 Linux job stays. No other job waits for the macOS job. For CI, this replaces the plan that
   macOS stays out until phase 0 (D47, D48).
6. **U21.** Each Windows hardware test that does not depend on Media Foundation gets a counterpart
   with the OpenCV source on Linux and macOS: T-CAP-92 to T-CAP-98. They use the same switches,
   select by platform, and are not run now. They run on the Linux and Mac machines of the user on his
   word, in phase 0 through the certify suite. Where OpenCV cannot give what a criterion needs, the
   spec states the criterion that applies. They are not part of the 3a done list.
7. **U22.** The spec has a parity table (16.7): the state of each test on Windows, Linux and macOS.
   It is the to-do list of phase 7.
8. **U23.** More fake-source tests for the OpenCV source, step 3a, on the three CI systems:
   T-CAP-99 to T-CAP-104. They cover the 30 fps floor, the one-rate rule on requested rates and the
   warning for different real rates after the open, the start-up rate check with and without a
   reported rate (D46), a camera that fails at open, a camera that stops during a recording, and the
   auto-exposure warning on Linux.

The user also asked for corrections of the tests and the spec text: a strict T-CAP-05, the exact
wording of the tests in the spec rows, the limits that the fake source produces (16.1), and the
switches of the hardware tests (16.1). An agent made the choices of these corrections. Items 65 to 78
of section 18 of the spec list them. They are not decided by this entry.

## Reason

- U16: in the spec before U16, a hung control read on the loop thread held the gate for 5 s. The
  pass criterion of T-CAP-82 could not be met.
- U17: these points were gaps of the spec; the tests had already used these readings.
- U18: the user wants one rule for the folder: it is Windows only.
- U20 to U23: the user wants tests for Linux and macOS that are similar to the Windows tests, not
  detailed tests for Windows only.

## Open work

See [open-work.md](../open-work.md).
