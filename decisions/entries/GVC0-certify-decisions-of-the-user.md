# GVC0 — Decisions of the user for the certify run of skellycam

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor).

## Decision

The user decided these points for the certify run of skellycam. The draft spec
[`specs/certify.md`](../../specs/certify.md) builds on them and marks them [U].

1. **Levels.** The words of the user, from the certify contract (`report-format.md` of the
   repository `skellycertify`, section 2.7): "Quick must be: No more than 2 minutes total. Not
   require downloading any files not included with the installer ... Be enough to verify a
   recording, a realtime pipeline session, and a post-hoc session can at least start and run
   (whichever is relevant to that module). Full tests are pretty open at this stage and can involve
   downloading test files, taking longer on the system, running full benchmarks."
2. **Quick for skellycam.** For each real camera attached: it is detected with its modes, it opens,
   and it passes the rate check at 30 fps at 720p. Then, with all cameras that passed, one take of 3
   seconds with the new recorder; its files are checked and deleted. The target is under 30 seconds
   for four cameras.
3. **The summary.** The words of the user: "List of webcams (friendly OS names like Logitech C922,
   Razer Kiyo Pro, etc) and pass/fail/record next to each one". The name of a person is removed from
   a camera name before the report exists. The text uses "system", not "machine".
4. **SkellyCam rules that hold everywhere.**
   - Nothing below 30 fps is offered.
   - The exposure modes are Manual and Auto. Auto means that SkellyCam finds a manual value. The
     camera's own auto exposure is never a mode.
   - Virtual cameras are shown but cannot be selected.
   - One frame rate for all cameras. 60 is offered only when every ticked camera passed a real
     60 fps check.
   - A hung camera must cost the other cameras at most 100 ms. The user wants this in the certify
     suite "so we can catch if rules are still valid on older/slower systems".
5. **Fake cameras.** A check on a fake camera proves nothing about a camera model. It is a
   self-check with its own name, never a camera row.
6. **The functions.** skellycam gives the two Python functions `certify` and `certify_plan`. The
   HTTP routes that start a run in the app stay in freemocap.
7. **Product facts of 2026-11-20 that the checks use.**
   - The camera processes notice a dead server after 10 seconds (not 300). They then finish their
     files and release the cameras.
   - The frame rate in a take summary is the frames divided by the elapsed time.
8. **Answers to draft 1 of the spec.** The words of the user:
   - Question 1 (the camera row): "Quick test must include applying settings and if they stick or
     not, can you jpegs. Consider the outstanding unknowns and test drafts you have for Mac and Linux
     to fill this out further. This might necessitate a "partial" result in the summary table."
   - Question 3 (one apply, then a retry alone): "yes, include "in use" as a reported status too".
   - Question 6 (open and close cycles): "yes, single accept before full run. Do the stuff that's
     likely to break the cameras at the end of the run. Ensure anything that gets broken during a run
     is fixed or flagged to the user "e.g. camera <camera name> wedged, please replug"".
   - Question 10 (systems): "the aim of this is to use certify to test out the native capture features
     and see if they work. OpenCV is already fairly proven to work, so no need to test here."
   - Linux and macOS: "certify runs to validate assumptions about linux and mac code. Ideally as much
     real code is implemented as possible now so a single test run provides as much information as
     possible and can be used there and then if the tests pass." So the V4L2 and AVFoundation sources
     are built now, and certify tests the product path, one check for each assumption. A probe is
     allowed only where the product path cannot see a fact, and is record-only. A failing source must
     not break the run or the system. Hot-unplug is not tested.
   - Question 14 (public repository): the fork `https://github.com/domisjustanumber/skellycam` is the
     public repository of skellycam for evidence; the rows wait for the camera record type of the
     contract. "The goal is for certify reports to feed into that repo. When we have sufficient
     evidence to say "yup, native capture works on this OS, or with these cameras" then that gets
     bundled into the code build for the next release. Certify should prompt for new OS versions and
     cameras it hasn't encountered before."
   - Yes to draft 1 questions 2 (quick rate check at manual -7), 4 (`self:hang-100ms` in quick), 5
     (the full selection rule), 7 (a declared mode that never delivers fails its mode check; the row
     stays at its base result), 8 (`too-dark`), 9 (names, `skellycam/REASON_CODES.md`), 11 (options
     `cameras`, `recording_folder`), 12 (cancel order), 13 (a fixed failure code in the product) and 15
     (the app closes its camera groups; ask for a common code `cameras-busy`).
   - New: "ensure a disk performance benchmark is run to get a MB/s figure as well as the "disk is
     fast enough" test when running the full suite."
   - New: "freemocap wants to ensure there is not test overlap with other modules - report what you
     plan on testing to it and it can coordinate that."

The supervisor reads "can you jpegs" as: does the camera give its own JPEG frames, passed through
unchanged, in the capture path of the product. The user must confirm this reading. It is not a
decision.

## Reason

The user gave these points on 2026-11-20, before and after the first draft of the checks.

## Consequences

The agent choices are in [ADR-KY81](KY81-certify-spec-choices-of-the-agent.md).

## Open work

See [open-work.md](../open-work.md).
