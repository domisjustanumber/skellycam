# Recording upgrade study: handoff (2026-11-09, 20:45 EST; updated 2026-11-10 08:00)

For a fresh Claude Code session in `C:/Users/Dom/GitHub/freemocap/skellycam` (branch `dom/research`). Paste this to start:

> Read `research/skellycam_recording/recording_upgrade/HANDOFF.md`. Steps 1–4 of section 6 are done. Wait for Dom's review of `results/EVIDENCE_INDEX.md` before starting step 5.

**Update 2026-11-10 08:00 (session a7ea874e):**
- The timed queue ran 23:00–05:36 (run `20261109T230007`): 67/68 items ok. OV-COST timed out and was re-run alone, 05:36–06:13, ok.
- Every touched topic has a new `BENCH.md`. The overview and the flags to carry forward are in `results/BENCH_RUN_2300_SUMMARY.md`.
- Dom decided the quality target: **target A is the primary operating point for now** (section 1.1). **Do not set up the 23:00 trigger again** (section 2 is history).

**Update 2026-11-10 (later):** `EXECUTIVE_SUMMARY.md` in this folder summarises the evidence index and gives proposed recommendations (all inferred). It is not PLAN.md, and step 5 has still not started.

The earlier handoff (13:00) is kept as `HANDOFF_20261109_1300.md` for history. This file replaces it. Session 93366190 (16:36–20:45) did all the daytime work and built the queue; its own 23:00 trigger was cancelled so that two sessions couldn't both run the benches.

## 1. What Dom wants

Deliverable: **`PLAN.md` in this folder, a plan for upgrading skellycam's Python recording workflow, with every statement backed by evidence.**

| # | Goal |
|---|---|
| G1 | Store USB camera JPEGs without transcoding (assume the raw JPEG bytes arrive) |
| G2 | Resumable, crash-tolerant files: a crashed session's recording still plays |
| G3 | Overlays as a separate layer or vector files instead of burned in |
| G4 | Other uncompressed camera formats (Bayer RAW, NV12 and others), recorded intra-only |
| G5 | A wrapper optimized for recording throughput, or proof it doesn't matter enough to give up compatibility |
| G6 | GPU-accelerated encode on as many platforms as possible |
| G7 | Royalty-free codecs where possible (avoid H.264/H.265) |
| G8 | Native playback in the Chromium (Electron) UI |
| G9 | Easy synchronized, frame-accurate playback and scrubbing in the Electron UI |

Implementation is Python. Ideas from the Rust backend (`git show upstream/sfn26:skellycam-rust/src/...`) may be reused.

**Requirements (they override anything else):**
1. **Evidence rule.** No assertion without hard evidence or a test result. Label every claim **measured** (a result file), **source** (primary source: URL, exact quote, access date), **code** (file:line) or **inferred** (minimal, marked). Blogs and forums are leads only. Unverifiable means NOT VERIFIED.
2. **Today's system:** `research/skellycam_recording/results/real_recording_20261109/` is the primary source (verified against code; don't re-check). Full review: `research/skellycam_recording/REPORT.md`.
3. **Hardware target, from Jellyfin's docs** (https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/ and its `/intel`, `/nvidia`, `/amd`, `/apple`, `/rockchip`, `/known-issues` pages), checked against vendor primary sources. The target is a format whose encode is hardware-accelerated on **NVIDIA RTX 3000+** and supported on **most CPUs from 2020 on** (Intel, AMD, Apple, including CPUs with no iGPU). Cover both Quick Sync and NVIDIA.
   - **The target applies to the recording format itself**, not to an export copy.
   - **GPU-compute JPEG encode (nvJPEG on CUDA) counts as hardware-accelerated.**
4. **jellyfin-ffmpeg:** sources only, no tests. The plan needs a **pros/cons table of standard FFmpeg vs jellyfin-ffmpeg** and what options it could provide. Done: `results/jellyfin_ffmpeg/FINDINGS.md`.
5. **Tests use PyAV 19.0.2 (bundled FFmpeg 9.0.2) only.** PyAV 18 results (skellycam venv) are background. The ffmpeg CLI may only inspect files.
6. **Version bumps allowed** if they improve format support. Test in isolation (`uv run --script` with PEP 723 pins; npm only in the scratchpad). Never modify the skellycam venv, `skellycam-ui` or the freemocap repo.
7. **Research stays local:** Markdown in `research/`, never Claude Docs. Don't commit rebuildable files. Media (it shows the room) only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/`. Don't commit unless asked.
8. **Only intra-only formats are in scope** (every frame a keyframe). GOP/inter results are background only.
9. **H.264 intra and HEVC intra are compared head to head with JPEG at matched quality.** G7 still prefers JPEG; the comparison shows what the royalty-free choice costs.
10. **Timed tests run tonight from 23:00, the whole queue to the end** (Dom, 20:25: "run to the end"; estimated finish about 08:03). Dom removed the earlier 3 h cap ("get through all the tests you need to").
11. **No camera access.** Every test uses the frame corpus (section 3). This was checked: no study script opens a capture device.

### 1.1 Quality target: decided 2026-11-10

**Decision (Dom, 2026-11-10): use target A, SSIM-Y 0.9961 (about 52 dB PSNR-Y), as the primary operating point for now.**
- Target B (PSNR-Y 45 dB) stays as the second, compact point. PLAN.md quotes sizes and speeds at A first and gives B as the cheaper alternative.
- **Dom, 2026-11-10: do not run the machine-vision quality test. The evidence below is sufficient.** A stands, and PLAN.md treats it as fixed. The test sketch further down is kept only as a record of what was considered.

**Why target A was chosen** (from `results/intra_compare/NOTES.md` section 5 and `results/intra_compare/camera_jpeg_quality.md`):
1. **It is the quality the cameras already deliver.**
   - measured: the C930e and C922 JPEGs use one fixed quantisation table per set; the nearest IJG quality is q94 for luma and chroma in all four sets (720p and 1080p, both models).
   - measured: libjpeg-turbo q94 (4:2:2) on the same models' raw YUY2 1080p frames gives SSIM-Y 0.99694 / PSNR-Y 52.65 dB (C930e) and 0.99520 / 51.83 dB (C922). Their mean is 0.9961 / 52.24 dB, which is target A.
   - inferred: a recorder that re-encodes at A is about as faithful as storing the camera's own JPEG.
   - So A puts every path on the same footing as G1 passthrough, which is the baseline: passthrough can't be better than the camera's JPEG.
2. **Going above A costs a lot of bytes for little measured gain.**
   - measured: SSIM-Y saturates near A. jpeg_turbo_422 on yuy2_1080p goes from q90 (SSIM-Y 0.9953, 204,402 B) to q95 (0.9962, 327,395 B): +60% bytes for +0.0009 SSIM-Y (`results/intra_compare/curves.md`).
3. **Target B sits where published pose results already show losses.**
   - measured: libjpeg-turbo q50 on yuy2_1080p already gives PSNR-Y 45.6 dB, so target B is about q50 on this content (NOTES.md section 5).
   - source: Poyser, Atapour-Abarghouei and Breckon, "On the Impact of Lossy Image and Video Compression on the Performance of Deep Convolutional Neural Network Architectures", arXiv:2007.14314 (https://ar5iv.labs.arxiv.org/html/2007.14314, accessed 2026-11-10). OpenPose on COCO (mAP over 10 OKS thresholds), pre-trained network: JPEG q95 0.711, q75 0.689, q50 0.655, q15 0.413. Retrained on compressed images: q95 0.711, q75 0.708, q50 0.678, q15 0.654.
   - inferred: B (about q50) is in the range where a pre-trained pose network lost about 8% mAP in that study; A (about q94) is at its q95 reference point. PSNR on our content does not map exactly onto their JPEG levels on COCO, so this is an indication, not a measurement on our data.

**Suggestion for machine vision (YOLO, RTMW): keep A as the floor. Don't go to B for recordings that feed pose estimation until it has been tested.** I don't recommend a target above A.
- **Why not higher:**
  - For MJPEG cameras, the camera's JPEG (about A) is already the best input that exists. A higher re-encode target can't restore detail the camera removed.
  - For YUY2/raw cameras, going above A costs +60% bytes per small SSIM step (point 2).
- **What is NOT VERIFIED:**
  - No published study was found that measures YOLO-pose or RTMW keypoints against JPEG/H.264/HEVC quality at these levels (searches 2026-11-10; leads only):
    - surveillance detection under H.264 and HEVC: arXiv:2211.05805;
    - HRNet AP 0.935 → 0.783 at H.264 CRF 45, far heavier than B: arXiv:2404.12183, "Gait Recognition from Highly Compressed Videos".
  - mAP/OKS is coarse. Triangulation in FreeMoCap depends on per-keypoint pixel error and jitter, which these papers don't report. So "no loss at A" is NOT VERIFIED either.
  - PLAN.md states these two gaps as NOT VERIFIED, next to the recommendation.
- **Considered gap-fill test. NOT TO BE RUN (Dom, 2026-11-10: the evidence so far is sufficient):**
  - Input: uncompressed YUY2 frames of a person, captured by the C922/C930e.
    - The corpus YUY2 sets are 16 frames of the room, probably with nobody in them. Check before using them.
    - New frames need Dom, because study tests have no camera access (section 1, item 11).
  - Encode each frame with jpeg_turbo_422, h264_nvenc and hevc_nvenc at a PSNR-Y sweep: about 40, 45 (B), 48, 52 (A) and 55 dB.
  - Run YOLO-pose (ultralytics) and RTMW (rtmlib, ONNX) on the reference and on each decoded frame.
  - Report per keypoint: pixel displacement from the reference (median, p95, max), confidence change, and missed or extra detections.
  - Pin model and package versions with PEP 723 (rule 6).
  - Decision rule (proposal): the lowest target whose p95 keypoint displacement stays under the models' own frame-to-frame jitter on identical uncompressed frames, measured in the same test. If B passes, B becomes a candidate primary target for pose-only pipelines.

## 2. The 23:00 trigger (DONE 2026-11-09; history only, do not repeat)

It fired at 23:00 in session a7ea874e and started the run in section 5. What follows is the original instruction, kept for the record.

The trigger lives only in this session, so the session must stay open, and it fires only while the session is idle. Load the cron tools with `ToolSearch` `select:CronCreate,CronList`, then create a **one-shot local cron job**:

- `cron`: `"0 23 9 11 *"` (2026-11-09 at 23:00). If you're starting after 23:00 on the 9th, skip the trigger and start the run now (section 5).
- `recurring`: `false`
- `prompt`:

  > It is 23:00: start the timed benchmark run for the recording upgrade study. Read `research/skellycam_recording/recording_upgrade/HANDOFF.md` (sections 1, 5 and 7) and `research/skellycam_recording/recording_upgrade/results/BENCH_QUEUE_2300.md`. Dom asked to RUN THE WHOLE QUEUE TO THE END (all 68 items, estimated finish about 08:03), not stop at 05:00. First check the machine is quiet: Intel UHD 770 `Present True` (if not, the runner skips QSV items; note it), no other heavy processes (other Claude sessions, Parsec/Sunshine, Electron, run_suite.py), CPU under 15% over 10 s. Then launch the runner in the background from the repo root with `uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py --deadline 10:00` and do nothing else heavy on the machine while it runs: only monitor `results/BENCH_RUN_2300_LOG.jsonl` with light checks at long intervals. PyAV 19.0.2 only. If an item hangs past its timeout and the runner doesn't kill it, kill only that item's process tree. When the runner finishes, kill leftover study processes (command line contains recording_upgrade or the session scratchpad), write each topic's BENCH.md from the new JSON with the background-load record and flags, and write `results/BENCH_RUN_2300_SUMMARY.md` (what ran, what was flagged or skipped, headline numbers with file paths).

Then confirm the job with `CronList` and tell Dom the exact fire time it reports (the scheduler may shift a :00 job up to 90 s early; the last one reported 22:59).

Notes:
- A cloud routine (`schedule` skill, RemoteTrigger) won't work: the run needs this machine's GPUs and corpus.
- If the session might be closed overnight, the alternative is a Windows Task Scheduler job running `claude -p "<prompt above>"` in the repo folder. Ask Dom first: it's a system change.
- **Check that the old session is closed.** Session 93366190's trigger was cancelled (CronDelete, 20:45), but its leftover processes would still load the machine.

**What Dom does before 23:00:**
1. Leave this session open and idle, and the PC **unlocked until about 08:00**. The Electron benches need visible windows; the runner keeps the display on.
2. Close other Claude sessions (including 93366190), Parsec and Sunshine (they can hold NVENC sessions), Electron windows, the USB camera suite (`run_suite.py`) and games.

## 3. Machine and tools (Gerald)

- **CPU:** i7-14700K (Raptor Lake-S). 8 P-cores (CPUs 0–15) plus 12 E-cores; the runner pins items to the P-cores.
- **iGPU:** UHD 770, **present again**. It was checked `OK / Present True` at 16:36 and is also present in the 20:40 dry run. Intel driver 32.0.101.7088.
- **GPU:** RTX 3070 (Ampere), driver 610.88. GeForce limit is 12 NVENC sessions, shared with MF and D3D12VA encoders; QSV is outside that pool.
- **Disk:** C: only. **Defender:** real-time protection on (don't change it), daily quick scan scheduled at 02:00; the runner pauses 01:55–02:30.
- **PyAV 19.0.2:** `uv run --script` with `# dependencies = ["av==19.0.2", ...]`.
  - The wheel has libx264 and libx265 (GPL, see `results/licensing/FINDINGS.md`) but no libopenh264, libaom, VAAPI or Vulkan encoders.
  - The skellycam venv (`.venv`, PyAV 18.0.0, OpenCV 4.12) is read-only.
- **Electron:**
  - 35.7.5 (pinned by the UIs): `skellycam-ui/node_modules/electron/dist/electron.exe`.
  - 45.2.3: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe`.
  - Unset `ELECTRON_RUN_AS_NODE` before launching Electron.
- **Chrome:** 156.
- **Scratchpads the queue depends on. Don't delete them before the run ends:**
  - the Electron 45.2.3 path above (session 106dc0c8);
  - the libjpeg-turbo 3.2.1 DLL at `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/ljt321/bin/turbojpeg.dll` (session 93366190; used by JP-ROTATE and PI-JPEG-DECODE).
- **Input frames:** `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/`.
  - Read `index.json`; the builder is `scripts/common/build_corpus.py`.
  - Real C930e/C922 camera JPEGs, unmodified: 720p, about 890 frames each; 1080p etc., 10–19 frames. All 4:2:2 baseline.
  - Two real YUY2 1080p sets, 8 frames each.

## 4. State of each topic

Every topic has `results/<topic>/NOTES.md` and a `FINDINGS.md`.

| Topic (goals) | FINDINGS state | Notes |
|---|---|---|
| jpeg_passthrough (G1, G5) | verified + revised today | |
| write_throughput (G5) | verified + revised | new BENCH.md from the quiet run (2026-11-10); the contaminated one is `BENCH_20261109_contaminated.md` |
| crash_resilience (G2) | verified + revised | |
| overlays (G3) | verified + revised | |
| uncompressed_intra (G4) | verified + revised | re-run 2026-11-10 (items 35, 56, 57); new BENCH.md |
| gpu_encode (G6, G7) | verified + revised | background to hw_accel_target |
| hw_accel_target (G6, G7, target) | verified + revised | per-generation matrix NVIDIA/Intel/AMD/Apple/no-iGPU, Jellyfin vs vendor |
| jellyfin_ffmpeg (req. 4) | verified + revised | pros/cons table |
| chromium_codecs (G8) | verified + revised | E35, E45, Chrome 156 |
| chromium_sync_scrub (G9) | verified + revised | |
| licensing (G7) | verified + revised | |
| python_integration (all) | verified + revised | |
| **intra_compare** (target, G7) | **unverified draft** | matched-quality sweep, `matched_settings.json` |
| **intra_playback** (G8, G9) | **unverified draft** | intra H.264/HEVC vs JPEG path in browsers |

- `FINDINGS.prev_<n>.md` files are earlier versions kept by the saver; they can be deleted once PLAN.md is done.
- Verifier reports are `VERIFY_provenance.md` and `VERIFY_method.md` per topic.

**Headline results so far** (read the FINDINGS for labels and citations; these are pointers, not evidence):
- **Hardware encode intersection** (hw_accel_target): on RTX 3000 plus 2020+ Intel/AMD/Apple, only H.264/HEVC have hardware encode everywhere.
  - RTX 3000 has no AV1 and no VP9 encode; AMD has no JPEG or VP9 encode; Apple has no AV1 or VP9 encode.
  - JPEG has hardware encode via nvJPEG (CUDA) and Intel `mjpeg_qsv` (which writes 4:2:2 when fed YUY2).
  - Machines with no iGPU and no NVIDIA GPU fall back to CPU encode.
- **Matched quality** (intra_compare): at target A on YUY2 1080p, against libjpeg-turbo 4:2:2 (1.00):
  - hevc_qsv 0.39, hevc_nvenc 0.43, h264_nvenc 0.53, h264_qsv 0.59;
  - mjpeg_qsv 1.00, nvJPEG 0.74 (but 1.4–2.2 dB lower PSNR-Y at equal SSIM).

  Pitfall: FFmpeg's default `i_qfactor` codes NVENC/QSV intra frames at 0.8× QP. `matched_settings.json` sets `i_qfactor=1, i_qoffset=0`.
- **Intra playback** (intra_playback):
  - 48 NVENC/QSV intra H.264/HEVC clips seek frame-exactly in E35, E45 and Chrome 156 (4800/4800 per browser), and so does the JPEG path.
  - HEVC has no software decode in Chromium.
  - h264_nvenc needs `flush()` per frame in WebCodecs.
  - The UI can fetch single camera JPEGs out of an MKV by byte range with an index (byte-identical).
  - The UI's current seek rule `(k+0.5)/fps` fails on real VFR timing; use the file's own pts.
- **Passthrough and crash safety:**
  - Camera JPEGs round-trip byte-exact in MKV, fMP4 and AVI.
  - fMP4 with a 1/1e6 time base is the leading container.
  - OpenCV frame-index seeks fail when frames were dropped; seek by sidecar timestamp.
  - MKV with an empty timestamped packet after each frame lost 0 acknowledged frames in 3/3 kills.
  - A torn tail JPEG often decodes silently, so use a CRC'd index sidecar.
- **Chromium:** MJPEG never plays in `<video>`; camera JPEGs decode via ImageDecoder/createImageBitmap.

**Known loose ends to settle in the post-bench verify:**
- gpu_encode FINDINGS says mjpeg_qsv output is 4:2:0. intra_compare shows `yuvj422p` when fed YUY2. The 4:2:0 claim is likely from NV12 input; correct the wording.
- intra_playback matched quality at about 55 dB, with sizes that differ from intra_compare's targets A and B. Keep them separate and say which target each number is at.
- Not yet answered: why the cameras' 1080p JPEGs are much smaller than libjpeg-turbo q94 on the same models' YUY2 frames (scene vs in-camera denoise); and whether libx265 all-intra (Rext profile) plays in Electron.

## 5. Tonight's run (DONE)

**Result (2026-11-10):** see `results/BENCH_RUN_2300_SUMMARY.md` for what ran, the load record, the flags and the headline numbers with file paths.
- Main run `20261109T230007`: 23:00:07–05:36:29, 396.4 min.
  - 67/68 ok; no item load-flagged; no Defender scan during any item.
  - The leftover-process flag on every item listed only the monitoring session's own shells.
- OV-COST hit its 30-minute timeout after 7 of its 8 blocks and wrote no JSON. It was re-run alone (run `20261110T053653`, 36.4 min, ok) from a scratch copy of the queue with a 60-minute timeout. **To do:** raise OV-COST in `make_queue.py` to about 36 min estimate and a 60-minute timeout.
- New `BENCH.md` in intra_compare, intra_playback, jpeg_passthrough, crash_resilience, python_integration, uncompressed_intra, overlays and write_throughput. The old contaminated write_throughput file is now `BENCH_20261109_contaminated.md`.
- **Flags to carry into section 6** (details in the summary, section 3):
  - **libx265 widened the process affinity** from CPUs 0–15 to 0–27 in single-stream items 1–3, so those items are not all P-core-only.
  - **NVENC opens at most 12 sessions**, so read N=16 NVENC rows as 12 streams.
  - **nvJPEG fed decoded camera MJPEG misses target A.**
  - **WebCodecs scrub has hidden errors** (914 in E35) **and GPU-process memory grew to 9–38 GB.**
  - **N=8 `<video>` sync has stalled tiles.**
  - **Tonight's write latencies are higher than the daytime run's** for files and append.
  - **uncompressed_intra has no lossless check** in the timed bench.

The original plan for the run follows.

- **Queue:** `results/BENCH_QUEUE_2300.md` (read it), machine-readable in `results/bench_queue_2300.json`. The JSON is generated by `scripts/bench_runner/make_queue.py`: edit the generator, not the JSON.
  - 68 items, 477.8 min estimated, every item passed `--smoke`.
  - Items 1–23 are the decisive set: matched-quality single-stream encode for all 16 intra paths; 1/4/8/16-stream scaling at 1080p30; Electron 35/45 seek and sync for JPEG vs H.264/HEVC intra; passthrough mux, fsync and fragment cost; the 16-camera write test.
  - Items 24–68 are everything else still in scope, in priority order: recording-writer cost; scrub; repair; long-file open; threading models; 4:2:2 scaling; NVENC lossless and Bayer; overlays; live-view decode; MJPEG→re-encode pipelines; QSV sync; 720p scaling; G4 Bayer/FFV1; and more write tests.
- **Runner:** `scripts/bench_runner/run_queue.py`, launched from the repo root in the background with `--deadline 10:00`.
  - **Dry-run verified** at 20:40 with `--dry-run --dry-start 23:00 --deadline 10:00`: deadline 2026-11-10 10:00, Defender wait 01:53–02:30, no items skipped, planned end 08:03.
  - **Deadline quirk:** `at_today()` moves a deadline to the next day only if it is more than 12 h before the start. With a 23:00 start, use a deadline before 11:00.
  - **What it does:**
    - runs one item at a time with a hard timeout per item (kills the process tree);
    - records 10 s CPU, top processes, nvidia-smi and free disk before each item, and flags any item whose load averaged over 15% (after waiting up to 5 min);
    - logs MsMpEng CPU and Defender scan events per item;
    - pins items to the P-cores and keeps the display on;
    - skips QSV items if the iGPU is absent.
  - **Outputs:**
    - one log line per item in `results/BENCH_RUN_2300_LOG.jsonl`;
    - stdout and stderr in `results/bench_runner/logs/<run_id>/`;
    - each bench's JSON in `results/<topic>/bench/`.
- **To resume after a stop:** `--start-from <id> --deadline HH:MM`. **To run a subset:** `--only id1,id2`.
- **While it runs:** nothing else on the machine. No agents, no workflows, no functional tests. Only light log checks at long intervals; avoid Monitor polling that spins.

## 6. After the run (the rest of the study)

1. **DONE 2026-11-10.** No leftover study processes were found. Every topic's `results/<topic>/BENCH.md` and `results/BENCH_RUN_2300_SUMMARY.md` are written (section 5).
2. **DONE 2026-11-10** (workflow `wf_4bd79ef5-f4e`, 36 agents, 9 topics: intra_compare, intra_playback, jpeg_passthrough, crash_resilience, write_throughput, python_integration, uncompressed_intra, overlays, gpu_encode; saved with the saver). Original instruction: **Update each topic's FINDINGS with the new numbers** (replace contaminated or pending entries), then run **two verifiers** (provenance, method) and **one revise step** per changed topic. Include the unverified **intra_compare** and **intra_playback** drafts and the loose ends in section 4. Agents return FINDINGS text (section 7); the main session saves it.
   Also carry the section 5 flags into the FINDINGS and the verify step.
3. **DONE 2026-11-10** (workflow `wf_06a9baab-c0c`, 52 agents).
   - Two critics and a triage found 32 gaps.
   - 10 were filled (GF01–GF10; evidence in `results/<topic>/gapfill/`), then folded into 13 topics' FINDINGS, verified and revised.
   - The other **22 gaps are NOT started; they wait for Dom's review** (listed in `results/EVIDENCE_INDEX.md` §4). Timed gaps need a quiet machine.
   - Deviation: GF02 ran OpenCV 4.12 / FreeMoCap readers read-only from the skellycam `.venv`; its writers were PyAV 19.0.2.

   Original instruction: **Completeness critic** against G1–G9, the hardware target and the requirements in section 1. Then gap-fill: functional work can run in parallel; timed work runs one item at a time on a quiet machine.
   - Do NOT add the machine-vision quality test from section 1.1; Dom ruled it out on 2026-11-10.
4. **DONE 2026-11-10:** `results/EVIDENCE_INDEX.md` was written, then checked independently (about 740 claims, 30 errors fixed in place; the corrections are in its final section, and the pre-check copy is `EVIDENCE_INDEX.prev_1.md`). **Stop here: Dom reviews before step 5 starts.** Original instruction: **`results/EVIDENCE_INDEX.md`:** per goal, the verified findings, the options ruled out with evidence, and what is still NOT VERIFIED.
5. **Plan workflow:**
   - 3 independent draft plans (compatibility-first, performance-first, simplicity-first);
   - a judge panel;
   - a synthesis into **`PLAN.md`**;
   - an evidence audit tracing every sentence to a labelled source, repeated until clean;
   - a check against every requirement in section 1.

   PLAN.md must include the hardware-target matrix, the JPEG vs H.264/HEVC intra trade-off stated plainly (G7 vs size and hardware), and the standard FFmpeg vs jellyfin-ffmpeg table.
6. Add the study to `research/README.md` and a pointer in `research/skellycam_recording/REPORT.md`. Don't commit unless asked.

## 7. Lessons (avoid repeating them)

- **Subagents can't write `FINDINGS.md`.** A harness guard blocks it; don't work around it.
  - Give FINDINGS agents a schema with a `findings_md` string field.
  - After the workflow ends, run `python workflows/save_findings_from_journal.py <journal.jsonl>`. It maps the label suffix (`findings:<topic>`, `revise:<topic>`) to `results/<topic>/FINDINGS.md` and keeps the replaced file as `FINDINGS.prev_<n>.md`.
  - Some agents put the text in `summary` instead; check the character counts the saver prints.
- **Don't SendMessage to workflow agents.** It spawns a duplicate. Steer them with files they read (for example HANDOFF sections), or let them finish.
- **Timed work needs a quiet machine.** Today's daytime benches were contaminated by other agents and sessions. Only the runner, one item at a time.
- **Folder-of-files read-back is slow because of Defender and Windows Search indexing** (`results/write_throughput/`).
- **Leftover processes:** stopped agents leave Electron, tail and bash processes. Kill only those whose command line contains the study paths.
- **Cost:** today's three workflows used about 8.7M subagent tokens (7 + 28 + 15 agents).
- **Reusable workflow scripts** are in `workflows/`: the CTX block, evidence rule, verifier lenses and the findings→verify→revise pipeline (`recording-upgrade-6a-findings-*.js` and `recording-upgrade-6a-part2-*.js`).

## 8. Key files

- Queue and runner: `results/BENCH_QUEUE_2300.md`, `results/bench_queue_2300.json`, `scripts/bench_runner/{run_queue,make_queue,idle_baseline}.py`.
- Matched settings: `results/intra_compare/matched_settings.json` (target A at top level, target B under `psnr45`).
- Bench requests from verifiers: `results/verifier_bench_requests_wf_eb5ec983.json`. Old manifests: `results/bench_queue_from_wf_2e122ed0.json`.
- Workflow scripts: `workflows/` (first run `wf_2e122ed0-a3f`; today `wf_e4f480ac-cb0`, `wf_eb5ec983-6c1`, `wf_cd65963a-db2`). FINDINGS saver: `workflows/save_findings_from_journal.py`.
- Prior evidence to cite instead of redoing:
  - `research/frame_ring_buffer/prototypes/results/` (p3, p4, p5, p8, p11, p12);
  - `research/usb_cameras/docs/mjpeg_passthrough_summary.md`;
  - `research/usb_cameras/docs/skellycam_timestamps_review.md`;
  - `research/usb_cameras/docs/timestamp_accuracy_options.md`.
- Memory note: `recording-upgrade-study` in the Claude project memory.
