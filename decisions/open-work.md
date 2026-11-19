# Open work

This file holds the open work of the [decision log](README.md). Read the items that apply to your
task. Delete an item when its work is done. The PR that closes an item records the result.

- **The fills that wait for the user.** The user must decide
  [ADR-4A7H](entries/4A7H-other-fills-of-the-kit-adoption.md),
  [ADR-NMM1](entries/NMM1-design-of-the-camera-media-check.md) and
  [ADR-4CQC](entries/4CQC-phase-3-windows-capture-spec-and-test-list.md).
- **Private-data findings.** `tools/check_private_data.py` reports 3 lines in upstream files: an
  email address in `skellycam-ui/src/hooks/floatingOnboarding.tsx` and in
  `skellycam-ui/src/hooks/useDraggableTooltips.tsx`, and a user path in
  `skellycam/tests/reference_recordings/README.md`. The user decides each redaction. Until then,
  `test_repository_has_no_private_data` fails, and a commit that changes one of these files stops
  ([ADR-PEJ0](entries/PEJ0-scope-of-the-private-data-check.md)).
- **CI on PRs to `development-streaming`.** `.github/workflows/test.yml` runs on PRs to `main` and
  `development` only, so the package tests do not run on a PR to `development-streaming`, the PR
  branch of [ADR-S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md). A CI change needs the
  user.
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
  - Known failure: T-RING-31 (idle CPU, limit 2 % of one core) fails (items 60 and 65). On
    2026-11-18, the paused loop used 3.9 to 7.0 % of one core on a Windows test machine. The user
    dropped the redesign of the wait of the OpenCV loop, because native capture deletes that loop.
    The test applies to the native capture loop from phase 3, and it stays a known failure until
    then. Windows counts CPU time in steps of 15.6 ms.
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
  T-CAP-01 to T-CAP-79 are proposed
  ([ADR-4CQC](entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)). They wait for the user,
  with 45 agent choices (section 18) and 8 questions (section 19). No product code or test code is
  written before the user accepts the spec. Section 17.2 of the spec lists four changes of the ring
  spec that it needs.
