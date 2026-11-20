# Open work

This file holds the open work of the [decision log](README.md). Read the items that apply to your
task. Delete an item when its work is done. The PR that closes an item records the result.

- **The fills that wait for the user.** The user must decide
  [ADR-4A7H](entries/4A7H-other-fills-of-the-kit-adoption.md) and
  [ADR-NMM1](entries/NMM1-design-of-the-camera-media-check.md).
- **Lower the index limit again.**
  [ADR-N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md) raised
  `INDEX_LIMIT` from 14,000 to 24,000 characters until the clean-up. In the clean-up, the user
  decides each `proposed` entry. Then the small choice entries of the agents are merged into one
  entry for each step on the merged branch. After that, lower `INDEX_LIMIT` again. If the index
  fills again first, give the user the bigger restructurings of decision 4 of ADR-N2NH.
- **Private-data findings.** `tools/check_private_data.py` reports 3 lines in upstream files: an
  email address in `skellycam-ui/src/hooks/floatingOnboarding.tsx` and in
  `skellycam-ui/src/hooks/useDraggableTooltips.tsx`, and a user path in
  `skellycam/tests/reference_recordings/README.md`. The user decides each redaction. Until then,
  `test_repository_has_no_private_data` fails, and a commit that changes one of these files stops
  ([ADR-PEJ0](entries/PEJ0-scope-of-the-private-data-check.md)).
- **Phase 2 of the frame ring.** [ADR-50G8](entries/50G8-phase-2-frame-ring-spec.md) accepts
  [`specs/frame-ring.md`](../specs/frame-ring.md). The tests of step 2a (T-RING-01 to 33) are in
  `skellycam/tests/frame_ring/`. They use the API of
  [ADR-9G2W](entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md), which the
  user accepted with clarifications, corrections and decisions on the 2a code (items 52 to 67) on
  2026-11-18 and 2026-11-19. Run the T-RING-34 and T-RING-35 set with
  `uv run pytest -m ring_portable skellycam/tests/frame_ring`.
  Run the timed and kill tests with `-m ring_slow`. `SKELLYCAM_RING_FULL=1` gives the durations of
  the spec, for example 60 s for each slot count of T-RING-08. T-RING-49 needs cameras and is not
  written.
  - Done: the code of step 2a is complete. This is the ring package
    `skellycam/core/ipc/frame_ring/`, the rings in `CameraGroup` (session start and close,
    recreation, `ring_infos`), the `cv2.imencode` feed of the OpenCV loop (recorder first), the
    interim relay (item 4), the performance page (item 5) and the deletions of section 2.1. The
    test helper `FakeCapture` stays alive until the process ends, because OpenCV 5.1.0 crashes when
    the garbage collector frees a subclass of `cv2.VideoCapture`.
  - Step 2b (the BGR ring and the decode stage). The user approved the build on 2026-11-19
    (item 63). The failing tests of step 2b (T-RING-36 to 47) are in
    `skellycam/tests/frame_ring/test_bgr_ring.py`, `test_decode_stage.py` and
    `test_bgr_camera.py`. They use the API of
    [ADR-5MYA](entries/5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md),
    which the user accepted on 2026-11-19, with the four decisions of
    [ADR-467Z](entries/467Z-step-2b-self-check-stop-opencv-threads-and-yuv-conversion.md).
    One more test in `test_bgr_camera.py` checks that a mode change (7.5) recreates the BGR ring
    with the new shape (user, 2026-11-19).
    T-RING-48 has no test of its own: it runs the T-RING-36 tests (marker `ring_portable`) on ARM.
    Run the 2b tests with
    `uv run pytest skellycam/tests/frame_ring/test_bgr_ring.py skellycam/tests/frame_ring/test_decode_stage.py skellycam/tests/frame_ring/test_bgr_camera.py`.
    Add `-m "not ring_slow"` for a short run.
  - Done: the code of step 2b (2026-11-19). This is `decode.py` of the ring package,
    BGR support in `FrameRingWriter` and `FrameRingReader`, `CameraConfig.bgr_ring`, the BGR rings
    of `create_session_rings` and the hand-over in the OpenCV loop. The entry
    [ADR-E817](entries/E817-choices-of-the-2b-code.md) holds the choices of the code.
  - Expected failure until phase 3: T-RING-46 (libjpeg warnings) fails on Windows. The OpenCV 5.1.0 wheel has its own
    C runtime, so a redirect of descriptor 2 does not reach libjpeg there (ADR-E817 item 7). The
    limit stays off on Windows until phase 3 (user, 2026-11-19). A possible fix: the main process
    gives each camera process a pipe as its stderr before OpenCV loads. The Linux code was checked in WSL without OpenCV.
  - Done: the measurements M5 to M7 of section 11.3 on Windows
    ([ADR-ETJ1](entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md)). M8 (Apple Silicon) is open.
  - Open: the BGR read at 1080p does not meet its target (p99 3.13 to 4.05 ms, target 3 ms). The
    user decided on 2026-11-19 that the reader does not change in phase 2. A read call that copies
    into a buffer of the reader waits for the first consumer that reads the BGR ring.
  - Done: T-RING-31 is retired with the phase 2 loop. T-CAP-49 checks its rule on the shared loop
    ([ADR-PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) W8).
  - Fact, 2026-11-18: the four-camera comparison of the timing. Before is commit 0a66994c3, after
    is commit 8a1f9b517. Each had two runs of 60 s, with a 720p30 MJPG request, lockstep and
    four cameras (Logitech C922, Logitech C930e, Razer Kiyo Pro and a generic camera), lights on.
    The values below are before (run 1 and 2), then after (run 1 and 2).
    - Frames per camera: 1548 and 1547, then 1548 and 1548.
    - Group frame rate: 25.76 and 25.76, then 25.76 and 25.77.
    - Median spread of the grab times between cameras: 0.205 and 0.189 ms, then 0.183 and 0.194 ms.
    - The step that copied a frame to the old ring now holds the JPEG encode and the capture check.
      Median: 1.02 and 1.24 ms, then 1.87 and 1.81 ms. 95th percentile: 1.58 and 1.92 ms, then
      3.39 and 3.41 ms.
    - Whole processing of a frame, median: 2.86 and 3.24 ms, then 3.97 and 3.91 ms.
    - No traceback. Four JPEG rings of 27,779,072 bytes each, 111,116,288 bytes in total. The
      largest frame is 0.10 to 0.22 of its slot. There was no oversize frame, no cut-off frame, no
      capture-error frame and no failed ring write.
    - An earlier pair of runs the same day in a dim room gave 8.00 frames per second before and
      after. The cause is not verified.
    - The result files are in the research branch `dom/research` of this repository. They are not
      committed there yet.
  - The user runs T-RING-49, the optional four-camera smoke test. It needs cameras.
  - T-RING-34 (Apple Silicon) is on hold. It goes into the certify suite of a later task and is not
    run by hand now (item 67). The job `ring-portable` of `.github/workflows/ring-arm64.yml` runs T-RING-35 and T-RING-48 on
    each push to `dom/native-jpeg` ([ADR-7DE6](entries/7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md)).
    It has not run yet.
  - The measurements M4 and M8 of section 11.3 are not done. Phase 2 makes them before it fixes a
    performance number.
  - Section 13 of the spec holds the open questions.
- **Phase 3 (Windows native capture).** The user decided D1 to D49 on 2026-11-19
  ([ADR-EN7A](entries/EN7A-phase-3-windows-capture-decisions.md)). D23 and D38 replace two statements
  of the plan. The spec [`specs/windows-capture.md`](../specs/windows-capture.md) and its test list
  T-CAP-01 to T-CAP-91 are accepted
  ([ADR-4CQC](entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)). The user answered the
  questions of three drafts on 2026-11-19 (fifteen answers)
  ([ADR-QKX1](entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)). The user accepted
  the revised spec on 2026-11-19, with its 64 agent choices (section 18). Section 17.2 of the spec
  lists seven differences from the ring spec.
  - The failing tests of step 3a are in `skellycam/tests/capture/`, with the fake source
    `fake_source.py`. They use the API of
    [ADR-HP7D](entries/HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md), which the user
    accepted on 2026-11-19 with the answers U16 to U23
    ([ADR-HB4Z](entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)). Next:
    the product code of step 3a.
  - Done: the user decided items 65 to 78 of section 18 of the spec, and W1 to W8 after the review of
    the 3a code ([ADR-PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md)).
  - The user decides the proposed entries of the 3a code:
    [ADR-S6HT](entries/S6HT-choices-of-the-3a-loop-code.md),
    [ADR-MA22](entries/MA22-choices-of-the-media-foundation-source-of-step-3a.md) and
    [ADR-6EKB](entries/6EKB-choices-of-the-3a-review-fixes.md) (items 79 to 90 of section 18).
  - Done: W8 deleted the phase 2 loop. Its tests moved to the shared loop or were retired
    ([ADR-037V](entries/037V-completion-of-w8-the-phase-2-loop-and-its-tests.md), which the user
    decides). The `README.md` of `skellycam/tests/reference_recordings/` still names the deleted
    tests; it changes after the redaction decision of that file.
  - Run the fake-source tests with
    `uv run pytest skellycam/tests/capture -m "not camera_hardware and not capture_local"`. The
    hardware tests run only with `SKELLYCAM_HARDWARE=1`. The workflow
    `.github/workflows/capture.yml` (section 15: Windows, Linux and macOS) ran one time, on
    d8989972d. Its failures and their fixes are in
    [ADR-BM73](entries/BM73-fixes-of-the-first-ci-run-of-the-capture-workflow.md), which the user
    decides. The second run (6d496aa24) failed T-CAP-86 on Linux, T-CAP-108 and T-CAP-85 on macOS;
    the fixes and the choices for the user are in
    [ADR-FTC3](entries/FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md). The
    next run must show T-CAP-86 and T-CAP-108 pass, and the place of the T-CAP-85 gap on macOS. The
    macOS job also runs the portable ring tests.
  - The start method on Linux: Python 3.13 forks the camera processes from the main process, which
    has threads (the server and the watch of each group). The product does not mix contexts. Spawn
    on each system is a decision of the user
    ([ADR-BM73](entries/BM73-fixes-of-the-first-ci-run-of-the-capture-workflow.md), F3).
  - Phase 0 (the user, through the certify suite): the Linux and macOS hardware tests T-CAP-92 to
    T-CAP-98.
  - Phase 7: the parity table of section 16.7 of the spec is the to-do list for Linux and macOS
    (14 tests with no counterpart yet).
- **Support virtual cameras.** Detection shows a virtual camera with `virtual=True`, and a request
  that names it gets HTTP 422
  ([ADR-PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) W5,
  [ADR-MA22](entries/MA22-choices-of-the-media-foundation-source-of-step-3a.md) item 9). A later task
  makes a virtual camera selectable.
- **Phase 5 step 5a (the new recorder).** The user decided R1 to R12 on 2026-11-19
  ([ADR-VPF8](entries/VPF8-phase-5-recorder-decisions.md)), and M1 to M10 and C1 to C7 the same
  day ([ADR-J3QP](entries/J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md)).
  R1 to R4 and M1 to M5 replace U4, U5 and U12 from the connection of step 5a. The user accepted
  the spec [`specs/recorder.md`](../specs/recorder.md) and its test list on 2026-11-20
  ([ADR-Z3Y7](entries/Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md),
  [ADR-Q03C](entries/Q03C-phase-5-step-5a-recorder-spec-and-test-list.md)). The failing tests are
  in `skellycam/tests/take_recorder/`. They use the API of the proposed entry
  [ADR-QEQ8](entries/QEQ8-python-api-of-the-recorder-as-the-5a-tests-assume-it.md), which waits for
  the user. The product code of step 5a is in `skellycam/core/take_recorder/`. Its choices are in the
  proposed entry [ADR-T24F](entries/T24F-choices-of-the-5a-recorder-code.md). The measurements of
  R11 on Windows are in [ADR-8RES](entries/8RES-r11-measurements-of-the-5a-recorder.md). The user
  keeps 3 s and 10 s as starting values
  ([ADR-C6DE](entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md) D2). Open: T-REC-STALL on
  a slow disk (USB, spinning) on the hardware of the user, and the D3 detection on Linux and macOS.
  Run the benchmarks with `SKELLYCAM_BENCH=1` and
  `SKELLYCAM_BENCH_OUT` set to a folder outside the repository. The merged list of proposed skellyfileformat changes
  F-1 to F-10 for the recorder and the player (section 13) still waits for the user (R6).
  Done: the connection to the shared loop and the edits of section 14 of the spec in
  `specs/windows-capture.md`; U4, U5 and U12 are removed
  ([ADR-YNM2](entries/YNM2-connection-of-the-take-recorder-to-the-shared-loop.md), which the user
  decides). Next: the first hardware run of the new recorder (a take with three cameras; an ended
  camera process in place of an unplug), and the take in the new player and in Blender.
- **Phase 6a (the canvas player for new takes).** The user decided Y1 to Y7 on 2026-11-19
  ([ADR-J2BQ](entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)). The user accepted the spec
  [`specs/player.md`](../specs/player.md) (revision 2) and its test list T-PLAY-01 to T-PLAY-72 on
  2026-11-20 ([ADR-YV3V](entries/YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md)). The
  39 agent choices of section 16 stay in
  [ADR-4K7V](entries/4K7V-phase-6a-player-spec-and-test-list.md). The player gives three items to the
  merged format list of the recorder spec (section 13).
  - The failing tests of 6a are in `skellycam-ui/src/player/tests/` and
    `skellycam-ui/src/components/playback/tests/`. Run `npm run test:player:unit` and
    `npm run test:player:browser` in `skellycam-ui/`. The benchmarks T-PLAY-65 to T-PLAY-70 run by
    hand with `playwright.player-bench.config.ts`. The TypeScript names that the tests assume wait for
    the user ([ADR-4MJ4](entries/4MJ4-typescript-names-of-the-player-as-the-6a-tests-assume-them.md)).
  - The `xvfb` version of `.github/workflows/player.yml` is not verified. The unit tests ran on Node
    26.13.1 on the Windows test machine only.
  - The product code of 6a is on `dom/player` (2026-11-20). Its corrections and choices wait for the
    user ([ADR-1ACK](entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)). Some tests
    still fail; the report of the code lists each one. The recorder spec needs one sentence for a
    `camera_dead` detail that does not parse (item 4 of ADR-1ACK).
- **The full reader result and the conformance run of the JavaScript reader.** They come with step 6c
  (L2 of [ADR-4HNY](entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)).
- **Option B for the take files of the player (not part of 6a).** Review how the Python server can
  serve the take files with a performance on par with the Electron handler of 6a: threads, process
  splits, no request log and no folder listing on the route, `Cache-Control: no-store` and the
  expose header (user, Y2 of [ADR-J2BQ](entries/J2BQ-phase-6-player-decisions-y1-to-y7.md); section
  14.4 of [`specs/player.md`](../specs/player.md)). The measured gap at 16 cameras × 60 fps × 150 kB:
  the bare FastAPI route was 4 % short and 25 % short behind the logging middleware.
- **Phase 4 (live preview).** The user decided P1 to P7 and answered A1 to A8 on 2026-11-19
  ([ADR-G651](entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)). The user accepted the step 4a
  spec [`specs/preview.md`](../specs/preview.md) and its test list T-PRV-01 to T-PRV-24 on 2026-11-19
  ([ADR-WB08](entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md)). The agent
  choices of its section 13 wait for the user
  ([ADR-162X](entries/162X-step-4a-preview-spec-and-agent-choices.md)).
  - The tests of step 4a (T-PRV-01 to T-PRV-24) are in `skellycam/tests/preview/`, with the
    helpers of spec section 9.1 in `preview_helpers.py`. Run them with
    `uv run pytest skellycam/tests/preview`. The product code of step 4a is done. The user decides
    its choices ([ADR-MZ02](entries/MZ02-choices-of-the-4a-code.md)). The measurements M-PRV-1 to
    M-PRV-5 are done on Windows
    ([ADR-HDC9](entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md)). Open: M-PRV-4
    on Linux. The user must confirm the target of A10 of
    [ADR-G651](entries/G651-phase-4-live-preview-decisions-p1-to-p7.md): 19 %, not the 12 % of the
    first run.
  - The user decides
    [ADR-24FZ](entries/24FZ-python-api-of-the-preview-sender-as-the-4a-tests-assume-it.md): the
    Python items that the failing tests of step 4a use and that the spec does not fix.
  - Step 4b: the user answered the questions Q1 to Q13 of the spec
    [`specs/preview-4b.md`](../specs/preview-4b.md), decided the PR target (upstream
    `development`), accepted the spec in principle and gave the go-ahead for its tests, not its
    code, on 2026-11-20
    ([ADR-VYS7](entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).
    Revision 3 has the full test list (section 7.4). Next: the failing 4b tests, on top of
    `dom/integration` when it exists (section 2). The user decides Q14 (section 12.3: the take
    writes the list number as `os_index`) and the agent choices
    ([ADR-EE0E](entries/EE0E-step-4b-preview-spec-and-agent-choices.md),
    [ADR-R1TD](entries/R1TD-revision-2-of-the-step-4b-preview-spec.md),
    [ADR-W674](entries/W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md)).
    The supervisor decides the two open points of section 12.2: the 4a commits in
    `dom/integration`, and the change of section 6 of `AGENTS.md` to upstream `development`.
- **The `sfn26` integration on `dom/integration`.** The user decided the base on 2026-11-20
  ([ADR-EQY4](entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md)). The agent choices wait
  for the user ([ADR-6T78](entries/6T78-choices-of-the-sfn26-integration.md)). Open:
  - D1 of [ADR-EN7A](entries/EN7A-phase-3-windows-capture-decisions.md) says that no merge of `sfn26`
    is planned. The spec has a changed-on note.
  - Section 12.2 of [`specs/preview-4b.md`](../specs/preview-4b.md) says that `AGENTS.md` names
    `development-streaming`; it does not any more.
  - The DirectShow open order of `sfn26` (item 1 of ADR-6T78) waits for a check on the cameras.
  - The UI does not show the USB link or the `start_failure` warning item.
  - Not verified: real cameras, Linux, macOS and the installer build.
- **The certify run of skellycam.** The spec [`specs/certify.md`](../specs/certify.md) is draft 3.
  The user decided [ADR-GVC0](entries/GVC0-certify-decisions-of-the-user.md),
  [ADR-KG00](entries/KG00-certify-decisions-of-the-user-on-draft-2.md),
  [ADR-C5BR](entries/C5BR-macos-approach-probes-in-certify.md) and
  [ADR-BVK7](entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md). The choices of the agents
  wait for the user: [ADR-KY81](entries/KY81-certify-spec-choices-of-the-agent.md) (the items that the
  later entries do not rule) and [ADR-8CP7](entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md),
  with the 11 questions of section 14 of the spec. The spec is written against format 1.4.0 of the
  contract `skellycertify` (commit `1c9c191`). Question 6 waits for the owner of the contract (a
  `partial` item and a reviewed row). The specs `camera-requests.md`, `unix-capture.md` and `certify.md` are
  merged on `dom/integration`. A cross-spec review found differences; their fixes follow.
