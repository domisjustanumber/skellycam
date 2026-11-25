# Open work

This file holds the open work of the [decision log](README.md). Read the items that apply to your
task. Delete an item when its work is done. The PR that closes an item records the result.

- **Images in the camera media check.**
  [ADR-XT31](entries/XT31-kit-adoption-choices-camera-media-check-and-fills.md):
  `tools/check_camera_media.py` must refuse a PNG, GIF, WebP or SVG file, and allow each chart,
  diagram or UI screenshot by its path. Today it prints a reminder only. Its docstring and the
  `commit-files` skill change with it.
- **An exact name lookup in `tools/check_other_systems.py`.** On 2026-11-23 (Q649) the user asked
  how the lookup of a `certify-check` name can be exact, and what it means that it is not. Today it
  takes the code spans of `specs/certify.md` with the form of a check name (item 6 of
  [ADR-K9B7](entries/K9B7-design-of-the-other-systems-rule-skill-and-check.md)). The supervisor puts
  the options to the user. A later entry changes the lookup source.
- **The index after the clean-up.**
  [ADR-N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md) raised
  `INDEX_LIMIT` from 14,000 to 24,000 characters until the clean-up. On 2026-11-20 the user ruled
  that the limit is 24,000 (ADR-XT31), and the small choice entries of this branch were merged into
  one entry for each step. The merge of `dom/recorder-connection` brought F8C0 (proposed; it does not
  fit in ADR-P98T) and 82AA (accepted). 3WCA (`dom/3bc-tests`) joins the step entries when its
  branch merges. If the index fills again, give
  the user the bigger restructurings of decision 4 of ADR-N2NH.
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
  - Open: the BGR read at 1080p does not meet its target (p99 3.13 to 4.05 ms, target 3 ms). The
    user decided on 2026-11-19 that the reader does not change in phase 2. A read call that copies
    into a buffer of the reader waits for the first consumer that reads the BGR ring.
  - Fact, 2026-11-18: the four-camera comparison of the timing of step 2a
    ([evidence](evidence/four-camera-timing-of-step-2a-20261118.md)).
  - The user runs T-RING-49, the optional four-camera smoke test. It needs cameras.
  - T-RING-34 (Apple Silicon) is on hold. It goes into the certify suite of a later task and is not
    run by hand now (item 67). The job `ring-portable` of `.github/workflows/ring-arm64.yml` runs T-RING-35 and T-RING-48 on
    each push to `dom/native-jpeg` ([ADR-7DE6](entries/7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md)).
    It has not run yet.
  - The measurements M4 and M8 of section 11.3 are not done. Phase 2 makes them before it fixes a
    performance number.
  - Section 13 of the spec holds the open questions.
- **Phase 3 (Windows native capture).** The spec [`specs/windows-capture.md`](../specs/windows-capture.md) and
  its test list are accepted ([ADR-4CQC](entries/4CQC-phase-3-windows-capture-spec-and-test-list.md),
  [ADR-2GS1](entries/2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md)).
  - Open: section 15 must name the macOS timing step (BM73 7); item 90 of section 18 is stale.
  - The `README.md` of `skellycam/tests/reference_recordings/` still names the deleted tests of the
    phase 2 loop (W8); it changes after the redaction decision of that file.
  - Run the fake-source tests with
    `uv run pytest skellycam/tests/capture -m "not camera_hardware and not capture_local"`. The
    hardware tests run only with `SKELLYCAM_HARDWARE=1`. The macOS job of `.github/workflows/capture.yml`
    also runs the portable ring tests. It runs only by hand
    ([ADR-N14T](entries/N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md)).
  - Phase 7: the parity table of section 16.7 of the spec is the to-do list for Linux and macOS
    (14 tests with no counterpart yet).
- **Support virtual cameras.** Detection shows a virtual camera with `virtual=True`, and a request
  that names it gets HTTP 422
  ([ADR-PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) W5,
  [ADR-MA22](entries/MA22-choices-of-the-media-foundation-source-of-step-3a.md) item 9). A later task
  makes a virtual camera selectable.
- **Phase 5 step 5a (the new recorder).** The spec [`specs/recorder.md`](../specs/recorder.md) and its test list
  are accepted ([ADR-Z3Y7](entries/Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md),
  [ADR-P98T](entries/P98T-step-5a-choices-of-the-recorder-and-its-connection.md)). The tests are in
  `skellycam/tests/take_recorder/`, the code in `skellycam/core/take_recorder/`. The measurements of
  R11 on Windows are in [ADR-8RES](entries/8RES-r11-measurements-of-the-5a-recorder.md). The user
  keeps 3 s and 10 s as starting values
  ([ADR-C6DE](entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md) D2). Open: T-REC-STALL on
  a slow disk (USB, spinning) on the hardware of the user, and the D3 detection on Linux and macOS.
  Run the benchmarks with `SKELLYCAM_BENCH=1` and
  `SKELLYCAM_BENCH_OUT` set to a folder outside the repository.
  Next: the take in the new player and in Blender.
- **Phase 6a (the canvas player for new takes).** The spec [`specs/player.md`](../specs/player.md) (revision 2)
  and its test list are accepted ([ADR-YV3V](entries/YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md),
  [ADR-4D94](entries/4D94-step-6a-choices-of-the-canvas-player.md)).
  - The failing tests of 6a are in `skellycam-ui/src/player/tests/` and
    `skellycam-ui/src/components/playback/tests/`. Run `npm run test:player:unit` and
    `npm run test:player:browser` in `skellycam-ui/`. The benchmarks T-PLAY-65 to T-PLAY-70 run by
    hand with `playwright.player-bench.config.ts`.
  - The `xvfb` version of `.github/workflows/player.yml` is not verified. The unit tests ran on Node
    26.13.1 on the Windows test machine only.
  - The product code of 6a is on `dom/player` (2026-11-20). Some tests still fail; the report of the
    code lists each one. The recorder spec needs one sentence for a `camera_dead` detail that does
    not parse (item 4 of ADR-1ACK).
  - ADR-4D94 changes the player: no `picked-take-folders.json` in 6a (section 5.3 and item 6 of the
    spec must change); `xvfb` from the runner image (section 12.6 must change); a `.gitignore`
    exception for `skellycam-ui/src/player/`.
- **The full reader result and the conformance run of the JavaScript reader.** They come with step 6c
  (L2 of [ADR-4HNY](entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)).
- **Option B for the take files of the player (not part of 6a).** Review how the Python server can
  serve the take files with a performance on par with the Electron handler of 6a: threads, process
  splits, no request log and no folder listing on the route, `Cache-Control: no-store` and the
  expose header (user, Y2 of [ADR-J2BQ](entries/J2BQ-phase-6-player-decisions-y1-to-y7.md); section
  14.4 of [`specs/player.md`](../specs/player.md)). The measured gap at 16 cameras × 60 fps × 150 kB:
  the bare FastAPI route was 4 % short and 25 % short behind the logging middleware.
- **Phase 4 (live preview).** The step 4a spec [`specs/preview.md`](../specs/preview.md) and its test list are
  accepted ([ADR-WB08](entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md),
  [ADR-68JT](entries/68JT-step-4a-choices-of-the-preview-sender.md)).
  - The tests of step 4a (T-PRV-01 to T-PRV-24) are in `skellycam/tests/preview/`, with the
    helpers of spec section 9.1 in `preview_helpers.py`. Run them with
    `uv run pytest skellycam/tests/preview`. The measurements
    M-PRV-1 to M-PRV-5 are done on Windows
    ([ADR-HDC9](entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md)). Open: M-PRV-4
    on Linux. The user must confirm the target of A10 of
    [ADR-G651](entries/G651-phase-4-live-preview-decisions-p1-to-p7.md): 19 %, not the 12 % of the
    first run.
  - Step 4b: the user answered the questions Q1 to Q13 of the spec
    [`specs/preview-4b.md`](../specs/preview-4b.md), decided the PR target (upstream
    `development`), accepted the spec in principle and gave the go-ahead for its tests, not its
    code, on 2026-11-20
    ([ADR-VYS7](entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).
    Revision 3 has the full test list (section 7.4). The user accepted Q14 and the agent choices
    ([ADR-RA16](entries/RA16-step-4b-choices-of-the-preview-ui.md)). The failing 4b tests are written on
    `dom/preview-4b-tests` ([ADR-70WD](entries/70WD-failing-tests-of-step-4b-and-the-names-they-assume.md)). The
    user accepted their names and answered Q824 to Q836
    ([ADR-NA1N](entries/NA1N-answers-of-the-user-to-the-questions-of-the-step-4b-tests.md)); revision 4 of the
    spec holds the answers. Run the quick ones with
    `npm run test:player:unit` in `skellycam-ui/` and
    `uv run pytest skellycam/tests/preview tools/tests/test_camera_message_fixture.py -m "not pace"`. Not run yet:
    T-PRV-28 and T-PRV-29 (heavy real-time runs), the component tests T-PRV-43, 44, 47 to 50 and T-PLAY-44
    (`npm run test:player:browser`), the benchmarks T-PRV-51 and T-PRV-52 (by hand). Not done: the CI changes of
    7.8, in their own PR; T-PRV-25 runs only in the capture jobs (Q836). After the first run of T-PRV-49, look at
    it again (Q835). The 4b code must also change `skellycam/tests/capture/test_group_watch.py`, which uses
    `get_latest_ring_payload` (item 5). Next: the product code of 4b, after a go-ahead of the user.
- **The `sfn26` integration on `dom/integration`.** The user decided the base on 2026-11-20
  ([ADR-EQY4](entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md)), and accepted the
  agent choices ([ADR-6T78](entries/6T78-choices-of-the-sfn26-integration.md)). Open:
  - The DirectShow open order of `sfn26` (item 1 of ADR-6T78) waits for a check on the cameras.
  - The UI does not show the `start_failure` warning item.
  - Not verified: real cameras, Linux, macOS and the installer build.
- **The certify run of skellycam.** The spec [`specs/certify.md`](../specs/certify.md) is draft 3. The first code is in `skellycam/core/certify/` (section 19 of the
  spec), and a first real quick run was done on 2026-11-21. Open: the checks that are `not-run`
  `not-built` (the status line of the spec). The choices of the agents
  wait for the user: [ADR-KY81](entries/KY81-certify-spec-choices-of-the-agent.md) (the items that the
  later entries do not rule), [ADR-8CP7](entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md)
  and [ADR-FC1C](entries/FC1C-choices-of-the-spec-integration.md),
  with the open questions of section 14 of the spec.
- **Certify report fields, decided 2026-11-23, not built**
  ([ADR-F6C3](entries/F6C3-decisions-of-the-user-on-the-certify-report-fields.md)). The fields, the
  kept logs are in section 3.5 of the spec, in the slim form of Q594, with the build order of 3.6.7 (Q626) and
  the tests T-CERT-77 to T-CERT-90. The unit id is removed (Q595). The user accepted the choices of the agent
  ([ADR-NQ77](entries/NQ77-choices-of-the-certify-report-fields.md)) and the build order on 2026-11-23
  ([ADR-10HT](entries/10HT-acceptance-of-the-certify-report-field-choices-and-the-build-order.md)).
- **Certify report shape, decided 2026-11-23, not built**
  ([ADR-H2A0](entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md),
  [ADR-BW5M](entries/BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md)). Section 3.6 of the spec holds
  the shape of quick and full, the two verdicts, the fixes B1 and the commit (first in the build order of 3.6.7),
  and the tests T-CERT-91 to T-CERT-132. Each question of this shape is decided (Q591 to Q629): the user
  accepted the choices of the agent ([ADR-MEE1](entries/MEE1-choices-of-the-certify-report-shape.md),
  [ADR-DBF8](entries/DBF8-choices-of-the-certify-names-verdicts-and-checks.md) by Q627 of
  [ADR-63D9](entries/63D9-decisions-of-the-user-on-the-processors-the-build-order-and-the-certify-choices.md);
  [ADR-M7JC](entries/M7JC-choices-of-the-any-language-camera-name-and-the-usb-capability.md) by Q628;
  [ADR-H7PX](entries/H7PX-choices-of-the-usb-3-capability-on-macos-and-the-three-state-fact.md) by Q629).
  - The name rule of Q596 depends on a change of the wording of rule 16 of section 6 of the contract, for the
    name of the list of known cameras, the fixed class texts and a name in any script. The contract owner decides
    it; it is pending. The relay already keeps a name in any script (the answer of the contract owner).
  - Not verified: the hub flag of Windows on hardware (a Kiyo Pro on a USB 2 port), the kernel release of
    `bos_descriptors` on Linux, and each macOS method of 3.6.13. The trial `<label>:usb3-trial` at the end of a
    full run on macOS and Linux reports each method (Q629); after its reports show that the request to the camera
    is safe or not, the user decides whether it moves to the detection or goes. There is no stand-alone probe:
    certify is the only way that tests run on other systems (the user, Q629).
  - Later work, not specified: an optional question to the person, "What make and model is this?".
  - The sign-off checks `<label>:cycles`, `group:take-30`, `group:contention` and `group:open` (Q599, Q610), and
    `group:restore-after-kill` when the product keeps the "before" values on disk (Q608, Q615).
  - Q616: more certify runs on the test system calibrate the limit of `group:in-step` (one frame period today).
  - The limits of 3.6.6 rest on two cameras and three runs: `near_arrival_p5_ms` -50 ms and the take rate limit
    of 2 %. They are not calibrated.
  - A fault of the product: a log line prints the full path of the evidence file with the text of a
    `FileNotFoundError`. The path can hold the user name. The kept logs are never sent (3.5.11).
  - The user decided the proposals of the gap review as Q624a to Q624m
    ([ADR-493E](entries/493E-decisions-of-the-user-on-the-certify-check-drops-and-additions.md)). Focus matters
    for calibration boards: `control:focus:sharpness` and `control:autofocus` come back when they have a pass
    rule (Q624d). `group:preview-during-take` waits for the preview UI of step 4b.
  - Named only, not specified: codec checks from the H.264 study (which encoders exist and work, the stream limits
    of each hardware encoder per GPU model with the sustained number and the crossover to the CPU, and what the
    Electron UI can decode). The user wants them in certify if the study finds answers.
- **Decided 2026-11-21, not built**
  ([ADR-TFD7](entries/TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md)):
  a role flag in place of the `parent_process()`
  guards.
- **Deferred by the user (2026-11-23).** At 60 fps the exposure search never tries a value longer
  than the frame period. The product switches low light compensation off after each open.
- **Fix lane 4 follow-ups** ([ADR-HQE5](entries/HQE5-choices-of-fix-lane-4.md)).
  - The user decides Q-A (the restore file), Q-B (the take rate as a sum over a sum) and Q-C (the pace step).
  - Certify: `group:restore-after-kill` (Q615) can use the restore file with a folder of its own run.
  - FreeMoCap reads `framerate_stats.median` from the old `*_stats.json`, not from the stop response; a reader of
    new takes must use `mean_framerate` (Q609).
  - The CI runs with `spawn`, the skip guard and the pace steps have run on Linux and Windows. macOS is not done: its
    jobs run only by hand ([ADR-N14T](entries/N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md)).
  - FreeMoCap on Linux ([ADR-T34M](entries/T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md)):
    nothing is decided. The user: "I think this needs to be part of a wider review of how the whole of freemocap
    works on linux"; the freemocap session does that review. A candidate for it: a call of
    `multiprocessing.set_start_method("spawn")` at the top of `freemocap/__main__.py`, before
    `create_websocket_log_queue()`, so that its own workers also spawn on Linux, as on Windows. After this change of
    skellycam, FreeMoCap on Linux opens no camera until it sets the start method: its method is `fork`, and skellycam
    refuses each camera process with `start-method-fork` (`unix-capture.md` 4.12). This is the decision of the
    user; the fix of FreeMoCap belongs to the wider Linux review. Not verified on Linux.
- **Fix lane 5 follow-ups** ([ADR-DC43](entries/DC43-choices-of-fix-lane-5.md)).
  - The user decides items 1 to 4. Windows Server `os.label`: `Windows 2025Server 24H2` [NV].
  - `stop_after_frame=200` tests that wait for `ready` have the risk of T-UNX-95.
- **Fix lane 7 follow-ups** ([ADR-R394](entries/R394-choices-of-fix-lane-7.md),
  [ADR-2SX2](entries/2SX2-acceptance-of-the-choices-of-fix-lane-7-and-its-follow-ups.md)).
  - The pubsub leak (item 2 of ADR-2SX2) is fixed by [ADR-4CAF](entries/4CAF-choices-of-the-close-of-the-queues-of-a-group.md)
    (`windows-capture.md` 5.9, T-CAP-114).
  - The T-UNX-98 thread (item 3 of ADR-2SX2) is fixed in the test helpers by
    [ADR-JC4X](entries/JC4X-choices-of-the-gate-probe-of-a-second-app-on-the-test-clock.md).
  - Question for the user (not decided by [ADR-ZT5F](entries/ZT5F-acceptance-of-the-choices-of-fix-lane-8.md) item 3):
    does `test_status_locks.py::test_a_live_but_slow_holder_and_torn_json_never_raise[writes with no lock]` move to
    `pace`, or stay as it is? It fails 1 in 20 on 2 cores (real time; JC4X item 3).
  - macOS [NV]: the runner's open-file limit, and that its errors came from this leak. A run of the macOS jobs by
    hand gives the result.
