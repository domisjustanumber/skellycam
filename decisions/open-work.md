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
- **The index limit.** The limit is 24,000 characters (ADR-XT31). If the index fills again, give the
  user the bigger restructurings of decision 4 of
  [ADR-N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md).
- **Phase 2 of the frame ring.** [ADR-50G8](entries/50G8-phase-2-frame-ring-spec.md) accepts
  [`specs/frame-ring.md`](../specs/frame-ring.md). The tests of step 2a (T-RING-01 to 33) are in
  `skellycam/tests/frame_ring/`. They use the API of
  [ADR-9G2W](entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) (`-m ring_slow`, see
  `pyproject.toml`). T-RING-49 is not written.
  - Open: the BGR read at 1080p does not meet its target (p99 3.13 to 4.05 ms, target 3 ms). The
    user decided on 2026-11-19 that the reader does not change in phase 2. A read call that copies
    into a buffer of the reader waits for the first consumer that reads the BGR ring.
  - Fact, 2026-11-18: the four-camera comparison of the timing of step 2a
    ([evidence](evidence/four-camera-timing-of-step-2a-20261118.md)).
  - The user runs T-RING-49, the optional four-camera smoke test. It needs cameras.
  - T-RING-34 (Apple Silicon) is on hold. It goes into the certify suite of a later task and is not
    run by hand now (item 67). The job `ring-portable` of `ring-arm64.yml` runs T-RING-35 and T-RING-48 (item 68).
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
  - Step 3b (section 22, merged). No test of the real `QuickSyncEncoder` or of the raw path
    of Media Foundation; 22.5 not run. The Quick Sync check is [NV] off the development machine until a certify
    report gives `system:quick-sync` (22.7; [ADR-VTW3](entries/VTW3-choices-of-the-quick-sync-check-in-a-child-process.md)).
    Q900 ([ADR-Y2RN](entries/Y2RN-decisions-of-the-user-on-the-size-floor-review-and-certify-quick-runs.md)): the
    next UI lane adds `trackingLimitedByResolution` and `smallestSizeIs640x360` to the other three language
    files. Q809: the 3c tests of `dom/3bc-tests` come later.
  - Phase 7: the parity table of section 16.7 of the spec is the to-do list for Linux and macOS
    (14 tests with no counterpart yet).
- **Support virtual cameras.** Detection shows a virtual camera with `virtual=True`, and a request
  that names it gets HTTP 422
  ([ADR-PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) W5,
  [ADR-MA22](entries/MA22-choices-of-the-media-foundation-source-of-step-3a.md) item 9). A later task
  makes a virtual camera selectable.
- **Phase 5 step 5a (the new recorder).** The spec [`specs/recorder.md`](../specs/recorder.md) and its test list
  are accepted ([ADR-Z3Y7](entries/Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md),
  [ADR-P98T](entries/P98T-step-5a-choices-of-the-recorder-and-its-connection.md)). Open: T-REC-STALL on
  a slow disk (USB, spinning) on the hardware of the user, and the D3 detection on Linux and macOS.
  Next: the take in the new player and in Blender.
- **Phase 6a (the canvas player for new takes).** The spec [`specs/player.md`](../specs/player.md) (revision 2)
  and its test list are accepted ([ADR-YV3V](entries/YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md),
  [ADR-4D94](entries/4D94-step-6a-choices-of-the-canvas-player.md)).
  - The recorder spec needs one sentence for a `camera_dead` detail that does not parse (item 4 of
    ADR-1ACK).
  - Owed to `player.md` (Q851), test first: T-PLAY-62 of `handler.spec.ts` still checks the old list file and
    passes; it is rewritten to 5.3, then the code writes no `picked-take-folders.json`. Also the label (8.4) and a
    `.gitignore` exception for `skellycam-ui/src/player/` that wins over the later `index.ts` lines (4.1).
  - `player.md` lacks about 30 rules of ADR-4D94 (4MJ4 names, 1ACK 7, 9 to 18, 5FBS 12); then absorb it.
- **Step 6c part 1 (v1 playback).** [`specs/player-legacy.md`](../specs/player-legacy.md) revision 6
  is accepted ([ADR-2Z2D](entries/2Z2D-answers-of-the-owner-q800-to-q803-and-acceptance-of-the-v1-playback-spec.md)).
  Next: its failing tests. Open:
  - The skellyspecs pin `fd41818e4` (spec 2.1) resolves only after the owner's yes to push
    `dom/v1-player-rules` (better: a merge to its main).
  - Owed, outside the player: the Origin and Host checks for `/connect` and the other routes (Q748).
  - Later: the Dependabot entries, the upstream watch and its fork settings (spec 10, Q767).
  - The owner decides the patent position separately (Q733).
- **The full reader result and the conformance run of the JavaScript reader.** They come with step 6c
  (L2 of [ADR-4HNY](entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)).
- **Option B for the take files of the player (not part of 6a).** Review how the Python server can
  serve the take files with a performance on par with the Electron handler of 6a: threads, process
  splits, no request log and no folder listing on the route, `Cache-Control: no-store` and the
  expose header (user, Y2 of [ADR-J2BQ](entries/J2BQ-phase-6-player-decisions-y1-to-y7.md); section
  14.4 of [`specs/player.md`](../specs/player.md)). The measured gap at 16 cameras × 60 fps × 150 kB:
  the bare FastAPI route was 4 % short and 25 % short behind the logging middleware.
- **Phase 4 (live preview)** ([`specs/preview.md`](../specs/preview.md), [`specs/preview-4b.md`](../specs/preview-4b.md);
  [ADR-BPP8](entries/BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md)). Open:
  - M-PRV-4 on Linux ([ADR-HDC9](entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md)).
  - Step 4b, after the merge: delete `read_latest_ring_frames` and `_send_json` with their
    spec line and test probe (Q871); rewrite the top of the real-time streaming page (Q873).
  - Soon, spec and test first (Q907): does the product server hang at its shutdown after a client connection reset?
    If so, a shutdown time limit; also the blocked queue feeder thread. After that fix, a
    kill in `PreviewKit.close` fails the test (Q909).
- **The `sfn26` integration on `dom/integration`**
  ([ADR-EQY4](entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md),
  [ADR-6T78](entries/6T78-choices-of-the-sfn26-integration.md)). Open:
  - The DirectShow open order of `sfn26` (item 1 of ADR-6T78) waits for a check on the cameras.
  - The UI does not show the `start_failure` warning item.
  - Not verified: real cameras, Linux, macOS and the installer build.
- **The full stall-watch test** (Q892 of
  [ADR-N2VE](entries/N2VE-decisions-of-the-user-on-the-ci-triage-and-the-stall-watch-code.md), low priority). A later
  small test lane writes it: a real camera loop, a fake camera whose frames stop after a reopen, the watch on the
  same clock (`unix-capture.md` 4.10).
- **Quick certify runs** (Q902, [ADR-Y2RN](entries/Y2RN-decisions-of-the-user-on-the-size-floor-review-and-certify-quick-runs.md)): the next certify lane, spec text and test
  first: a quick run leaves out the six full-only checks of Q593 (image-effect, not-reencoded, size,
  ring-equals-mkv, source-equals-ring, gaps-explained).
- **The certify run of skellycam.** The spec [`specs/certify.md`](../specs/certify.md) is draft 3. The code is in `skellycam/core/certify/` (section 19 of the
  spec). Open: the checks that are `not-run`
  `not-built` (the status line of the spec). Not decided: FC1C items 4 and 13, HQE5 items 2 and 3
  ([ADR-6YGH](entries/6YGH-acceptance-of-the-as-built-choices-of-fix-lanes-4-and-5-and-of-certify.md)). The next
  certify lane checks whether 8CP7 can be absorbed (Q853).
- **Certify report fields, decided 2026-11-23, not built**
  ([ADR-F6C3](entries/F6C3-decisions-of-the-user-on-the-certify-report-fields.md)). The fields, the
  kept logs are in section 3.5 of the spec, in the slim form of Q594, with the build order of 3.6.7 (Q626) and
  the tests T-CERT-77 to T-CERT-90.
- **Certify report shape, decided 2026-11-23, not built**
  ([ADR-H2A0](entries/H2A0-decisions-of-the-user-on-the-certify-report-shape.md),
  [ADR-BW5M](entries/BW5M-decisions-of-the-user-on-the-two-verdicts-and-the-certify-test-set.md)). Section 3.6 of the spec holds
  the shape of quick and full, the two verdicts, the fixes B1 and the commit (first in the build order of 3.6.7),
  and the tests T-CERT-91 to T-CERT-132.
  - The name rule of Q596 depends on a change of the wording of rule 16 of section 6 of the contract, for the
    name of the list of known cameras, the fixed class texts and a name in any script. The contract owner decides
    it; it is pending. The relay already keeps a name in any script (the answer of the contract owner).
  - Not verified: the hub flag of Windows on hardware (a Kiyo Pro on a USB 2 port), the kernel release of
    `bos_descriptors` on Linux, and each macOS method of 3.6.13. The trial `<label>:usb3-trial` at the end of a
    full run on macOS and Linux reports each method (Q629); after its reports show that the request to the camera
    is safe or not, the user decides whether it moves to the detection or goes.
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
- **Certify test lane** ([ADR-ZRA6](entries/ZRA6-choices-of-the-certify-test-lane.md),
  [ADR-CR85](entries/CR85-decisions-of-the-user-on-the-certify-test-lane.md)). Open:
  - Q821, for the self-check lane (Q48), test first: the product key `rate_luma_mean` (3.5.15 P5), and why certify
    gets no diagnostics dict of a camera that fails its start-up rate check. Then T-CERT-09 (a strict `xfail`)
    passes.
  - The run parts of T-CERT-23 (the Auto checks of `full`) and of T-CERT-121 (`details.cameras`) wait for that
    code. T-CERT-32 runs on Windows only until phase 7 (Q777).
  - The frozen case of T-CERT-18 is not proven until T-CERT-90 runs on a real build (item 14 of ADR-ZRA6).
- **Decided 2026-11-21, not built**
  ([ADR-TFD7](entries/TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md)):
  a role flag in place of the `parent_process()`
  guards.
- **Capture timings** ([`specs/capture-timings.md`](../specs/capture-timings.md) steps 1 to 6 and 8 built;
  [ADR-JFG4](entries/JFG4-choices-of-the-capture-timings-build.md) and
  [ADR-W3VD](entries/W3VD-choices-of-the-tile-timings-lane.md) proposed). Open: the timed test
  `test_process_workers.py` (an OK of the user first); M-TIM-1 on the hardware of the user (step 7).
- **Merges (ADR-GZS7).** Each merge runs the tests that no CI job runs on a push (Q841); tests and code merge
  together when they pass (Q815). The FreeMoCap display comes after FreeMoCap moves to the frame-ring API.
- **Deferred by the user (2026-11-23).** At 60 fps the exposure search never tries a value longer
  than the frame period. The product switches low light compensation off after each open.
- **Fix lane 4 follow-ups** ([ADR-HQE5](entries/HQE5-choices-of-fix-lane-4.md)).
  - Certify: `group:restore-after-kill` (Q615) can use the restore file with a folder of its own run.
  - FreeMoCap reads `framerate_stats.median` from the old `*_stats.json`, not from the stop response; a reader of
    new takes must use `mean_framerate` (Q609).
  - macOS: `spawn`, the skip guard and the pace steps have not run in its CI jobs; they run only by hand
    ([ADR-N14T](entries/N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md)).
  - FreeMoCap on Linux ([ADR-T34M](entries/T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md)):
    nothing is decided; the freemocap session does the wider Linux review. A candidate for it:
    `multiprocessing.set_start_method("spawn")` at the top of `freemocap/__main__.py`, before
    `create_websocket_log_queue()`. Until then FreeMoCap on Linux opens no camera: its method is `fork`, and skellycam
    refuses it with `start-method-fork` (`unix-capture.md` 4.12). Not verified on Linux.
- **Fix lane 5 follow-ups** ([ADR-DC43](entries/DC43-choices-of-fix-lane-5.md)): Windows Server `os.label`
  `Windows 2025Server 24H2` [NV]; `stop_after_frame=200` tests that wait for `ready` have the risk of T-UNX-95.
- **Fix lane 7 follow-ups** ([ADR-R394](entries/R394-choices-of-fix-lane-7.md),
  [ADR-2SX2](entries/2SX2-acceptance-of-the-choices-of-fix-lane-7-and-its-follow-ups.md)).
  - macOS [NV]: the runner's open-file limit, and that its errors came from this leak. A run of the macOS jobs by
    hand gives the result.
- **The CI lane** ([ADR-C47T](entries/C47T-choices-of-the-ci-lane.md), proposed). Not run on a runner yet: the D: drive
  step of `recorder-windows`, the uv steps of `player.yml` and the type check of the UI test code.
- **Question for the user: the stall watch under load with THREAD workers.** The `[thread]` case of
  `test_the_watch_ends_no_healthy_camera_under_load` failed once on CI from GIL starvation in the test process, a mode
  that the product does not use ([evidence](evidence/stall-watch-under-load-thread-20261127.md)). Move its check "no
  camera ended" to `pace`, and keep `[process]` blocking? Recommended: yes. (The other way, a change of the
  in-process rule, would weaken the detection of real stalls.) It stays blocking until the user answers.
- **Question for the user: T-PRV-25 and Doc checks.** `doc-checks.yml` syncs only the dev group, and T-PRV-25 imports
  `skellycam`; the `--ignore` of `preview-4b.md` 7.8 (Q836) is in kit text (`kit.toml`), so it needs an entry, a
  `kit_sync.py propose` and a PR to freemocap/project. The other way: move the test into `skellycam/tests/preview/`,
  which reverses "stays in `tools/tests/`" of Q836. Recommended: move the test (one local change; `test.yml` and
  `capture.yml` run it). Doc checks stays red until the user answers.
- **ZEX9** ([ADR-ZEX9](entries/ZEX9-decisions-of-the-user-on-the-housekeeping-of-2026-11-25.md)) becomes `done`
  after the CI result of its item 4.
- **Exclusive access** (accepted, [ADR-5PAR](entries/5PAR-decisions-of-the-user-on-the-control-read-the-holder-and-the-exclusive-access-drafts.md)).
  `windows-capture.md` 21, `unix-capture.md` 4.13 and `certify.md` 20 are accepted. Next: the Windows lane writes the
  failing tests, then the code; Linux and macOS land with phase 7. Owed: the codes `camera_shared` and
  `camera_control_changed` in `recorder.md` 6.6 and the format of skellyspecs; the three warnings in
  `camera-requests.md` 1.5; the line before a take in `preview-4b.md`; a contract field for `details.before_run`.
- **Certify for freemocap** ([ADR-CQ2X](entries/CQ2X-decisions-of-the-user-on-the-overlaps-with-freemocap.md),
  [ADR-13BB](entries/13BB-decisions-of-the-user-on-the-dark-rule-the-light-data-and-the-phase-7-items.md)). The lane
  of Q772 takes `is_model_checked`, the progress state, `CameraGroup.create_without_cameras` (freemocap names the
  attributes it reads; it waits for the close path of `CameraGroup`), the dark rule (T-CERT-09, 13, 23) and the light
  data. The privacy list moves into the contract (its owner). The `fork` of freemocap's certify child stays in the
  Linux review of ADR-T34M.
- **Question for the user (Q907, [ADR-06PW](entries/06PW-choices-of-the-shutdown-limit-lane.md)): a connection limit
  for the shutdown of the server?** No hang was found (0 of 39 runs), so none is built. At a limit, uvicorn cancels the
  requests that still run; a cancelled take stop leaves the manifest `recording` on each path but the shutdown
  endpoint ([evidence](evidence/cancelled-take-stop-at-a-shutdown-limit-20261127.md)). Suggested: first a lane that
  shields the take start and stop, test first, then the limit (kept on `dom/server-shutdown-limit`). The same file
  holds a fault of today: a second Ctrl-C skips the lifespan end.
