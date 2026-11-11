# Camera capture and recording: phased plan

2026-11-11, revision 3.3 · status: **proposed, for Dom's review.** This plan draws on the USB camera study (`usb_cameras/`), the recording upgrade study (`skellycam_recording/recording_upgrade/`) and the frame ring buffer study (`frame_ring_buffer/`). It is not the recording study's `PLAN.md` (that study's step 5). It adds no new measurements. The only new checks are reads of code, lockfiles and package indexes on 2026-11-11 (§2, §7).

**Labels:** **[M]** measured (result file), **[S]** primary source, **[C]** code read, **[I]** inferred, **[NV]** not verified. All [M] results come from one Windows 11 machine (Gerald). Linux and macOS have had no hardware run.

**Revision history:**
- **Rev 3.3 (2026-11-11, later session):** versions pinned exactly (D13). phase 1 is built on upstream `main`, which freemocap pins (D8). Gain has no per-model cap table: the exposure step measures noise against gain and stops raising gain where noise gets worse (D9). White balance is locked at its start value like the other controls, and checked against a loaded calibration (D10). The geometry and image controls are locked at whatever value the camera starts with, and recorded; when a loaded calibration's values differ, the user is asked (D11). Power-line frequency follows local mains, and AE priority is 0 (D12). Upstream `sfn26` noted (§5).
- **Rev 3.2:** tests split into TP1–TP4. Manual control only, with gain pinned in the exposure step. TP2 runs lockstep only, with all cameras at the lowest common rate; the new timing sync and mixed-rate tests are phase 2. Kiyo Pro wedges are handled, not diagnosed. skelly_synchronize findings added for imported cameras (2.8).
- **Rev 3.1:** all decisions resolved (§6): `mjpeg_qsv` first; the freemocap-ui player, freemocap's Python floor and OpenCV 5 go in phase 2, handled by a freemocap-repo session; no server-side decode.
- **Rev 3:** H.264 is dropped. Every recording, export and derived video is JPEG, I-frame only by nature. This removes the hardware H.264 detector, WebCodecs video decode in the UI and its GPU-process crash risk (§2.3), the NVENC session cap and H.264 royalties.
- **Rev 2:** I-frames only, the "halve" export dropped, package bumps added.

## 1. Rules and decisions this plan is built on

| Rule or decision | When |
|---|---|
| Tier 0 only: no registry or driver changes, no UVC PTS/SCR | 2026-11-08/09 |
| Native Python where possible (ctypes/comtypes), no compiled extension unless needed | 2026-11-08 |
| Target A (SSIM-Y 0.9961, about 52 dB) is the quality point | 2026-11-10 |
| I-frames only, everywhere. Long-GOP is forbidden anywhere | 2026-11-11 |
| **JPEG only, everywhere. No H.264 or HEVC** in recordings, exports, playback copies or freemocap outputs | 2026-11-11 |
| Python 3.13, and all packages bumped to latest as part of this work | 2026-11-11 |
| **No auto modes during a mocap session:** auto-exposure, auto gain and autofocus off, manual control only. Gain is pinned in the exposure step, not a separate control | 2026-11-11 |
| **Focus is automatic, with no manual focus controls:** focus is found automatically (proposed target: the ChArUco board at the subject's position), then locked for the session | 2026-11-11 |
| Phase 1 changes skellycam only. Phase 2 also changes freemocap: the raw-JPEG ring buffer option and the timing/lockstep changes | 2026-11-11 |

## 2. What the rules mean in practice

### 2.1 One format: JPEG in MKV with a sidecar

| Camera stream | How it is stored | Encoder | Cost vs the H.264 intra option it replaces (target A) |
|---|---|---|---|
| **MJPEG** (C922, C930e, generic; the Kiyo's MJPEG modes) | The camera's JPEG bytes, unchanged (passthrough) | none | +31–45 % bytes against `h264_nvenc` intra re-encodes (those were 0.69–0.76× passthrough, at lower fidelity) [M] (`results/intra_compare/FINDINGS.md` §3.1). No decode, no encode, no second generation of loss |
| **Raw** (YUY2/NV12; of the test cameras, only the Kiyo has one inside the 720-line, ≥ 30 fps scope [M]) | JPEG encoded at target A | `mjpeg_qsv` (16 × 1080p30 at 0.92 cores [M]), else libjpeg-turbo in worker processes (16 at ≥ 2.81 cores [M]) | 1.7–1.9× the bytes of H.264 intra (libjpeg-turbo 4:2:2 basis) [M] (EI §2.12) |

What dropping H.264 removes:
- **The hardware H.264 encoder detector.** What's left is a small check: does `mjpeg_qsv` open and produce a valid JPEG? Otherwise use libjpeg-turbo.
- **WebCodecs video decode in the UI**, with its GPU-process crash risk (§2.3).
- **The NVENC 12-session cap.**
- **H.264 patent-pool royalties.** Baseline JPEG has no listed patents [S] (EI §2.7).
- **The question of AMD/Apple encoder settings,** which were known only from source code. JPEG on those machines uses libjpeg-turbo on the CPU, which runs everywhere.

What stays:
- **The licence review before shipping.** The stock PyAV wheel still bundles GPL libx264/libx265 even though they go unused, and deleting them breaks `import av` [M] (EI §2.7).
- **Lossless and Bayer formats stay deferred.** The only exact option measured was `h264_nvenc` lossless. If a camera ever needs lossless, that reopens a non-JPEG codec.
- **Playback outside the app:** whether common external players open MJPEG-in-MKV is [NV].

### 2.2 How JPEG-in-MKV plays

`<video>`, MSE and the WebCodecs `VideoDecoder` all reject MJPEG in every container, in E35, E45 and Chrome 156 [M] (`results/chromium_codecs/FINDINGS.md` C1, C2). The player that works never gives the MKV to a media element [M] (C27, C28):
- Each frame's JPEG sits in the MKV as one unbroken run of bytes. The sidecar records its offset and size.
- To show a frame, the page fetches exactly those bytes with an HTTP Range request (byte-identical: 300 sequential and 150 random fetches per browser).
- It decodes them as a still image with `ImageDecoder` and draws the image on a canvas.
- One master clock picks each camera's frame. Seeks were 800/800, steps 976/976, and playback had 0 mismatches in 1200 draws per browser.

Two facts about the code today:
- **skellycam** hides the problem: its playback route transcodes any file `<video>` can't play into a long-GOP libx264 `.web.mp4` copy [C] (`skellycam/api/http/playback/playback_router.py:115-139`, `skellycam/utilities/transcode_to_h264.py:24-27`). Phase 1 removes this.
- **freemocap** has no transcode step, and freemocap-ui plays with `<video>` [C]. **With JPEG only, freemocap-ui can play no new recording until it gets the canvas player.** freemocap's processing is unaffected: OpenCV reads of index-timestamped MKV were exact in 18/18 files [M] (EI §2.1–2.2). Accepted under D2: the freemocap-ui player comes in phase 2.

### 2.3 Why JPEG avoids the scrub crash
- **The crash happened in the WebCodecs `VideoDecoder` path.** That decode runs in Chromium's GPU process. Without a GPU-to-CPU sync point, the GPU process crashed in 21 of 24 scrub configs, and in 12/12 runs of the earlier bench loop. After 3 crashes Chromium turned off hardware video decode for the session [M] (`results/intra_playback/gapfill/GF10_wc_scrub_memory.md` §4).
- **The JPEG path uses `ImageDecoder`, the image decoder, not the video decoder.** No JPEG scrub or sync config crashed, and no JPEG scrub config went above 901,812 GPU `private_kb` [M] (`intra_playback/FINDINGS.md` F22). The JPEG scrub was timed: 58 frames/s at 8 cameras, which is the harness's input limit, at 3.05–3.20 cores [M] (F23).
- **The remaining risk is in the app's own code:** holding decoded images without closing them, and unbounded prefetch. A real component over a long session has not been tested (TP4).

### 2.4 Python 3.13 and the packaging change it forces on freemocap
- PyAV 19.0.2 needs Python ≥ 3.12 [S]. freemocap's `requires-python` is `>=3.11` and its lock resolves from 3.11 [C] (`freemocap/pyproject.toml:6`, `freemocap/uv.lock:3`). So the PyAV bump alone forces freemocap to raise its minimum Python.
- `setproctitle==1.3.3` has no cp313 wheel in either lock (lockfile scan); 1.3.8 is current [S, index].
- What 3.13 gains on Windows [S]/[M] (`usb_cameras/docs/windows_timer_resolution.md`):
  - `time.monotonic()` moves to QPC (used in `websocket_server.py:242`);
  - `time.time_ns()` stops lagging UTC (it anchors UTC in `timebase_mapping.py:22-23`).
- Decided under D3: the freemocap-repo session raises freemocap's floor in phase 2. Until then freemocap stays on its current skellycam pin.

### 2.5 Package bumps: what "latest" involves
Checked 2026-11-11 with `uv tree --outdated --depth 1` and `npm outdated`. **uv shows only the newest versions that support Python 3.11** (that's why it lists PyAV 18.1.0, not 19.0.2), so the check must be re-run after the floor moves to 3.13.

- **Python (skellycam):**
  - Major versions: `opencv-contrib-python` 4.12 → 5.0, `polars` 1.43 → 2.1, `numpydantic` 1.10 → 2.0, `pillow` 12 → 13, `websockets` 16 → 17.
  - Minor versions: `numpy` 2.2 → 2.4, `fastapi` 0.139 → 0.162, `uvicorn`, `pydantic`, `msgspec`, `beartype`, `cv2-enumerate-cameras`, `sounddevice`, `tzlocal`, `setproctitle`, and the dev tools (`ruff` 0.15 → 0.17, `pytest`, `pyinstaller`, `poethepoet`, `pip-tools`, `pytest-asyncio`).
  - Plus `av` → 19.0.2.
- **npm (skellycam-ui):**
  - Major versions: **Electron 35 → 45**, TypeScript 5.9 → 7.0, Vite 7 → 8, `@vitejs/plugin-react` 4 → 6, `vite-plugin-electron` 0.28 → 1.2, `vite-plugin-electron-renderer` 0.14 → 1.0, `react-router-dom` 6 → 7, `react-resizable-panels` 2 → 4, `react-i18next` 16 → 18, `cross-env` 7 → 10.
  - The rest are minor versions.
- **Two bumps with study evidence or freemocap reach:**
  - **Electron 45** is one of the three runtimes the playback study ran (E35, E45, Chrome 156). Its JPEG results match E35 [M] (F24).
  - **OpenCV 5** reaches into freemocap. skellycam pins `opencv-contrib-python==4.12.*` [C], and freemocap leaves it unpinned and uses it for calibration. Decided under D6: phase 2.
- **The rule for phase 1 (D13, Dom, 2026-11-11):** every version is pinned exactly, with no ranges: Python 3.13.13 (`.python-version` and `requires-python`), every direct and dev dependency in `pyproject.toml` (`==`), the git sources by commit, the build backend, every skellycam-ui package (no `^`/`~`; `.npmrc` sets `save-exact`), and the CI actions and toolchains. Lockfiles pin the transitive dependencies. A bump changes one pin per commit. freemocap can only consume phase-1 skellycam with matching pins, which is phase 2 anyway (D3).

### 2.6 Playback cost of the JPEG canvas player
Source: `results/intra_playback/FINDINGS.md` F18–F23 and `bench/bench_tables.md` (E45, 1080p30, quiet run 2026-11-09/10). The clips were 600-frame loops of `mjpeg_qsv` re-encoded JPEGs (about 207 kB vs a 192 kB camera mean), run in a harness page, not skellycam-ui.

**Playback with all cameras synced:**

| Path | Cameras | Electron CPU (cores) | Memory, all Electron processes (MB) | Slowest camera (fps) | Frames apart across cameras, max |
|---|---|---|---|---|---|
| `<video>` per camera (today's design, H.264 files) | 4 | 0.28–0.36 | 872–1054 | 19.2–21.5 | 2–3 |
| `<video>` per camera (today's design, H.264 files) | 8 | 0.44–0.55 | 1372–1550 | 10.2–13.2 | 147–245 |
| **JPEG Range + `ImageDecoder`, master clock** | 4 | **0.77** | **714** | 29.9 | 0 |
| **JPEG Range + `ImageDecoder`, master clock** | 8 | **1.44** | **987** | 29.9 | 0 |

**Scrubbing at 8 cameras:** `ImageDecoder` showed 58 frames/s (the harness limit) at 3.05–3.20 cores. `<video>` showed 17–46 frames/s.

**Seek latency (p50):** `ImageDecoder` 4.6 ms, `<video>` 8.5–14.1 ms.

**Not measured:**
- the cameras' own JPEG bytes, timed (tested only for correctness, at 720p);
- 720p and 60 fps;
- 16 cameras;
- sessions longer than 8–15 s;
- skellycam-ui and its real backend serving byte ranges;
- other GPUs and CPUs;
- scrub capacity above 58 frames/s;
- killed files (NG07);
- overlay drawing on the player (NG03).

## 3. Phase 1: skellycam only

### 3.1 The contract with freemocap stays fixed
- The ring buffer: its layout, name-based attach and decoded BGR payload.
- The lockstep gate and equal per-camera frame counts.
- The timestamp CSVs: the existing columns keep today's meaning. New columns may be added.
- `camera_id` values and file-name patterns.
- Recordings readable by OpenCV.
- No exceptions. freemocap keeps its current skellycam pin until its phase-2 session (D2, D3).

### 3.2 Work packages

| # | Package | Contents | Evidence | Depends on |
|---|---|---|---|---|
| 1.0 | **Python 3.13 + package bumps** | `.python-version` 3.13 and `requires-python`; `av==19.0.2`; every Python and npm package to latest (§2.5), with majors one at a time and tests run after each. Electron 45. CI on 3.13. every version pinned exactly (D13), including `opencv-contrib-python==5.0.0.93` | §2.4, §2.5; PyAV 19 releases the GIL around header/trailer/close too [M] (EI §2.5) | — |
| 1.1 | **Small fixes** | Fix the ISO 8601 column (it applies the UTC offset twice) [M]. Fix the C930e exposure loss (set the format once, before exposure) [M]. Fix Windows AUTO exposure, which locks instead (fixed upstream on `sfn26`) [C]. Store a `retrieve_blocked` flag | `usb_cameras/docs/timestamp_accuracy_options.md` §7.2; `skellycam_exposure_review.md` §3.2 | — |
| 1.2 | **Recording reliability inside skellycam** | Ring study ranks 9 (drop the `copy.copy` in `put_data`: 54.1 → 58.8–59.0 fps [M]), 3, 4, 5, 1 and 10. None of them change the ring layout | `frame_ring_buffer/docs/frame_ring_buffer_summary.md` | — |
| 1.3 | **MF capture backend (Windows)** | Pure-Python MF source reader (comtypes), native format, converters off, behind a capture interface. Decode at source to BGR for the ring (unchanged), and keep the JPEG bytes for the recorder. Controls come from the MF source and are read back and checked on the image, with per-camera rules. **The exposure step turns auto-exposure, auto gain and autofocus off**, then runs the exposure step and the board autofocus (TP1). **Gain is chosen inside the same exposure step**, not exposed as a separate control. Its upper limit is measured on the live image from noise against gain, with no per-model cap table (D9). skellycam handles no gain today [C]. **Controls lock (D10–D12):** AWB off; power-line frequency set to local mains; AE priority 0; white balance, zoom, pan, tilt and the image controls (brightness, contrast, saturation, sharpness, gamma, backlight compensation) locked at the values the camera starts with. All of these are read back and recorded, and they're checked against a loaded calibration. The C930e resets exposure and gain at stream start, so both are re-applied after the first frame [M]. OpenCV leaves the Windows capture path. DirectShow via the ffmpeg CLI only if TP1's reliability part demands it | MF 400/400 + 100/100 cycles on 4 cameras; pymf = wincam on 3 cameras; OpenCV no first frame in 2 s [M] (`usb_cameras/WINDOWS_RUN_20261110_EXEC_SUMMARY.md`) | TP1 (camera IDs) |
| 1.4 | **JPEG encoder choice (raw streams only)** | **`mjpeg_qsv` first** (Dom, 2026-11-11): open it, encode one frame at the camera's mode, decode it, and check the quality is at A. Feed it full-range input: expand the camera's limited-range YUY2 first, or the JPEGs come out washed out [M] (`hw_accel_target/FINDINGS.md` F2). Otherwise use libjpeg-turbo in worker processes. Cache the choice; the user can force libjpeg-turbo. `mjpeg_qsv` returns each packet 3 calls later [M], so up to 3 frames sit in the encoder at a crash (T-KILL) | §2.1; `intra_compare/FINDINGS.md` §2.5 | 1.0 |
| 1.5 | **New recording writer** | One writer thread per camera in the camera process, fed by a bounded queue that counts drops. MKV with `flush_packets=1`. Container timestamps = frame index at the nominal rate. **MJPEG stream → passthrough; raw stream → JPEG encode at A (1.4).** Binary sidecar, one fixed record per frame: frame number, capture times in integer ns, CRC, offset, size, plus a header with format, encoder and stable camera key. **Removes every H.264 writer in skellycam:** the MSMF `cv2.VideoWriter` path, `PyavVideoWriter` (libx264), the libx264 re-encode in `video_audio_remuxer.py:69` (audio is muxed by stream copy instead) and `transcode_to_h264.py` | MKV+fp lost 1 frame per kill, 0 torn frames on cuts; MP4 keeps 0 [M]; torn JPEG decoded silently 5/6, CSV read wrong 6/24 [M]; 0 drops in 77/77 write cells to 16 × 1080p60 [M] (EI §2.2, §2.5) | 1.3, 1.4 |
| 1.6 | **Timestamps without changing what freemocap reads** | Per frame: MF arrival QPC, MF sample time, and today's stamp computed as now. At finalisation, build the timestamp CSVs from the sidecar and **add** columns: fitted camera time (offline lattice fit, start-up exclusion, change-point segments, `fit_unreliable` flag), drop/repeat flags, provenance. The existing columns are unchanged | Fit ≤ 0.56 ms vs flash, one 30 s run [M]; today 4.6–16 ms [M] (`timestamp_accuracy_options.md` §1) | 1.5 |
| 1.7 | **Crash recovery** | On the next start: remux unfinalised files (about 0.9 s/GB), then rebuild the CSVs and info JSON from the sidecar. Today a crash leaves **no** timestamps [C] | EI §2.2; `skellycam_recording/REPORT.md` §1 | 1.5 |
| 1.8 | **Overlays out of the video** | Stop the record-time burn-in, which today is drawn into the only copy [C]. Write a `.skov` sidecar (29.3 µs/frame, CRC'd) [M]. The UI draws overlays on the same canvas as the frame | EI §2.3 | 1.5 |
| 1.9 | **skellycam-ui canvas player** | Replace `SyncedVideoPlayer`'s `<video>` + `frame / fps`, and remove the `.web.mp4` transcode route. One master clock drawing every camera to a canvas, picking the frame at or before the clock (PREV) from sidecar times. Byte-range fetch by sidecar offset + `ImageDecoder`, with every decoded image closed and prefetch bounded. Accept HTTP 200 without `Content-Range` under `file://` | §2.2, §2.6; master clock spread 0 in 28/28, PREV 0 mismatches in 48/48 [M] (EI §2.9) | 1.5 |
| 1.10 | **Export with burned-in overlays** | Burn the `.skov` overlays into a copy, written as JPEG in MKV with its sidecar | EI §2.3 | 1.8 |
| 1.11 | **Bandwidth guidance** | Topology mapper (USB 2.0 root-port domains, per-mode bandwidth slot cache, refused-start classification). The UI says which port to move a camera to | `usb_cameras/docs/xplat_capture_plan.md` §5 [M on Intel; policy table for other vendors] | 1.3 |
| 1.12 | **Linux and macOS (phase 1b)** | Keep OpenCV capture until the native backends (V4L2 ctypes; AVFoundation + CoreMediaIO controls) pass hardware runs. Meanwhile they use the new writer with JPEG encode of decoded frames, because OpenCV gives no JPEG bytes there | `usb_cameras/docs/capture_stack_options_plan.md`; `macos_uvc_controls_review.md` [d, no hardware run] | L/M hardware suites |

### 3.3 Test plans for phase 1

Four separate test plans, run in order, each building on the one before (Dom, 2026-11-11). Two release checks sit beside them.

**Live-camera modes in scope** (MJPEG, ≥ 30 fps, as listed by the cameras [M] `usb_cameras/results/windows/Gerald/suite_20261111T040003Z/mjpeg_modes.json`):

| Camera | 720p30 | 720p60 | 1080p30 | 1080p60 |
|---|---|---|---|---|
| Razer Kiyo Pro | ✓ | ✓ | ✓ | ✓ |
| Logitech C922 | ✓ | ✓ | ✓ | – |
| Logitech C930e | ✓ | – | ✓ | – |
| Generic 4c4a:4a55 | ✓ (delivers ~25.7 fps [M]) | – | ✓ | – |

USB 2.0 bandwidth allows about one max-slot MJPEG camera per USB 2.0 root port [M] (`usb_cameras/REPORT.md` finding 16), so multi-camera sets follow the topology mapper's port plan (1.11).

#### TP1: Camera controls and frame extraction (real cameras)
Runs against the phase-1 MF backend (1.3), not only the probes. It reuses the suite tests W-MJPEG, W-FMT, W-CTRL-LIST, W-CTRL-EFFECT, W-AUTO, W-CYC and W-ID. Pass thresholds are the G-MJPEG / G-CTRL rows of `usb_cameras/docs/xplat_capture_plan.md` §3.

| Part | What is tested |
|---|---|
| Frame extraction | Every in-scope mode on every camera: the camera's own JPEG bytes (header hash against the MF reference), strict decode, delivered fps against requested, first frame within 2 s. The Kiyo Pro raw mode through the encoder choice (1.4). |
| **Manual control only: exposure (with gain), white balance, focus** | Every test first turns **auto-exposure, auto gain and autofocus off** (exposure is also capped at the frame period: manual −4 dropped the C922 and C930e to 16.0 fps and the Kiyo Pro to 19.4 fps even with auto-exposure priority 0 [M], `usb_cameras/docs/exposure_gain_tradeoff.md`), then tests manual control only (Dom, 2026-11-11). **Exposure step:** AE off, manual exposure set, and gain chosen in the same step from measured noise (D9); gain is not a separate control. **White balance and the other controls:** locked at their start values (D10, D11), power-line frequency set to local mains, AE priority 0 (D11, D12). For each setting: listed with the descriptor's range; set → read back (within one step); visible effect in the image (exposure at 25/50/75 % of range → luma; gain also checked, set → read back → luma at 10/50/90 % with exposure fixed; WB → R/B ratio, and the start value held after AWB is switched off; zoom, pan, tilt and the image controls unchanged from their start values through the whole step; focus with AF off → sharpness); set before and after stream start; held through stream start (the C930e resets exposure **and gain** at stream start [M], so the exposure step re-applies both after the first frame); kept across close/reopen; 3/3 runs. W-CTRL-EFFECT already measures these effects [C] (`suite/windows/tests/w_ctrl_effect.py`). |
| **Auto stays off (no drift)** | AE, auto gain and AF are switched off and verified off by reading back the auto flags. **New:** during a 10-minute stream, and across stop/start, the exposure, gain and focus readbacks and the image (luma, sharpness) must stay constant. The camera must not change exposure or focus by itself during a mocap session. Auto-mode on/off recovery (the old W-AUTO checks) is no longer a product test. The suite still restores each camera's as-found state at the end, as housekeeping. |
| **Exposure step** | Tests T1–T5 in `usb_cameras/docs/exposure_gain_tradeoff.md`: noise against gain at equal brightness (grey card and slanted edge, dark frames), JPEG bytes against gain, real exposure time and blur (rotating disk), the delivered-fps ceiling for every exposure step, and the exposure step end to end (3 light levels × motion presets × 30/60 fps; ceiling and cap respected, add-light warning, re-applied after stop/start, 10 min without drift). The results check the in-step noise rule (D9) against the full grid. They don't produce a per-model cap table. **New:** a calibration-mismatch case: load a calibration whose stored control values differ from the camera's start values, and check that the user is asked and that nothing is changed silently (D11). |
| **Board autofocus** | Tests F1–F11 in `usb_cameras/docs/focus_setting_options.md`: full focus map per camera and distance; board autofocus 10× on a stand and 10× hand-held (≥ 95 % of the best sharpness from a full sweep, values within ±2 fine steps, time within estimate + 50 %); all cameras in parallel; the lock held for 10 min, across 10 stop/starts and 10 close/reopens; restore after restart, replug, port move and reboot; how far fx, fy and distortion move with focus offsets; fixed-focus skip; failure handling; detecting a focus change mid-session. |
| Open/close reliability | ≥ 381 failure-free cycles per camera, in-process and new-process (≥ 99 % claim); multi-camera MF all-at-once vs DirectShow all-at-once; the Kiyo Pro wedge is detected and reported (first-sample timeout, then `0x8007001F`). |
| Camera IDs (T-ID) | MF device path → today's `camera_id`, no streaming. |
| Kiyo Pro wedge: **handle, record, don't revive, don't diagnose** (Dom, 2026-11-11) | Every test must expect the Kiyo Pro to wedge (a first-sample timeout, then `0x8007001F`), roughly once per ~1,000 stream starts [I]. **On a wedge:** mark the Kiyo Pro dead for the rest of the run; skip its remaining cells, rated "not run (wedged)"; keep testing the other cameras. **No revival attempts:** no re-probes, re-opens, device restarts or resets; the background poller stops polling it. **Record, for later diagnosis only:** time, plug-in age, run and test step, the last command and its arguments, every error code and timeout, the other cameras open at that moment and through which API, the Frame Server clients and camera-holding processes, the USB topology (controller, hub, port, speed), and the stream starts since plug-in. Nothing further. The diagnostic test arms in `usb_cameras/docs/kiyo_pro_wedge_research.md` §9 are **not run**. |

Product change (package 1.3): skellycam's exposure step turns AE, auto gain and AF off and pins gain; the UI has no separate gain control. **Exposure step** (`usb_cameras/docs/exposure_gain_tradeoff.md`): gain starts at the camera's default, which is 0, the minimum and lowest-noise value, on the Kiyo Pro, C922 and C930e [M]. The step picks the longest exposure at or below a ceiling: the smaller of a motion-blur limit (e.g. about 2 ms for 2 px of blur at 2–3 m/s at 720p [arith]) and the frame period (−5 at 30 fps, −6 at 60 fps [M]). If the image is still too dark, it raises gain. At each gain probe it also measures temporal noise on the live image and stops where relative noise (σ/μ in the mid-tones) starts to grow faster than gain alone explains, where detail drops, or where luma stops rising. Past that limit it warns the user to add light. There is no per-model cap table (Dom, 2026-11-11; `usb_cameras/docs/exposure_gain_tradeoff.md` §5.2a). Gain stays an output of the exposure step, not a control. At equal brightness, gain raised noise 1.3–2× and JPEG size 0–5 % [M, one evening scene]. Published pose benchmarks show motion blur hurts trackers more than noise does [S]. The generic camera's gain does nothing visible and resets to 4 at every start [M]. The measured rule stops it at once (luma doesn't rise), so it needs no special case. **Focus** (`usb_cameras/docs/focus_setting_options.md`): **skellycam focuses on the ChArUco board itself.** The camera's AF stays off. skellycam steps the focus value coarse then fine, scores sharpness only inside the detected board, picks the middle of the flat top of the curve, locks it and verifies it on the image. This runs with the board held still where the subject will stand, before calibration, with all cameras in parallel: estimated 20–35 s including the Kiyo Pro [I, from measured settle times]. The camera's own AF is not used, because UVC 1.0 cannot aim it at the board and its readback is unreliable on the Kiyo Pro and the C922 [M]. The locked values are stored with the calibration, keyed by camera identity, and re-applied and checked on every open. Any focus change means recalibrating. The fixed-focus generic camera is skipped. The Kiyo Pro needs ≥ 1.5 s after each stream start before its lens reaches the set value [M]. Auto modes are not used while a mocap session runs. **White balance, geometry and image controls** are locked at the values the camera starts with, not reset to defaults, and stored with the camera config and the calibration. On loading a calibration whose stored values don't match, skellycam tells the user which controls differ and asks what to do; it never changes them silently (D11). Today skellycam handles no gain at all [C], and its Windows AUTO exposure mode locks the exposure instead of enabling auto [C] (`usb_cameras/docs/skellycam_exposure_review.md` §3.2).

#### TP2: Recording with real cameras at mixed frame rates and resolutions
Builds on TP1: same backend, with manual controls set and verified first. Real cameras only. **Phase 1 runs every set under today's lockstep timing sync only, with all cameras at the lowest common frame rate.** Testing the new timing sync at mixed rates is phase-2 work (2.2) (Dom, 2026-11-11).

| Set | Cameras in one recording, all at the lowest common frame rate |
|---|---|
| U1 | all four at 720p30 |
| U2 | all four at 1080p30 |
| M1 | mixed resolutions: Kiyo Pro 1080p30 + C922 720p30 + C930e 720p30 + generic 720p30 |
| M2 | mixed resolutions: Kiyo Pro 1080p30 + C922 720p30 + C930e 1080p30 + generic 1080p30 |
| M3 | Kiyo Pro raw mode at 30 fps (`mjpeg_qsv`, then a repeat with libjpeg-turbo) + C922 720p30 + C930e 720p30 + generic 720p30 |

- Each set: 3 × 60 s, plus one 10-minute run.
- Measured per camera: delivered fps against requested; frames written against frames captured; drops (writer queue, plus gaps found by the timestamp fit); writer queue depth and write latency p99.9; CPU per process; disk MB/s; sidecar CRC check; OpenCV read exactness after finalising; timestamp CSVs and the lattice fit at each camera's own rate.
- Crash (T-KILL): hard kills during M1 and M3. Frames lost per kill for passthrough and for `mjpeg_qsv` (3-frame hold-back); killed files repair, play in skellycam-ui and read in OpenCV.
- **Lockstep runs never mix 60 and 30 fps** (Dom, 2026-11-11): all cameras start at the lowest common frame rate. The generic camera delivers about 25.7 fps when 30 is requested [M], so lockstep paces the whole group to it. Record how many frames each camera loses at the gate (it dropped 14 % of the C930e's frames beside the generic camera [M]).

#### TP3: Total throughput with simulated cameras (CPU load)
Builds on TP2: the same capture pipeline and writer, fed by simulated cameras that replay real camera JPEGs (taken from TP2 recordings) at real frame pacing. This is NG11 / the former T-E2E.
- Camera counts: 4, 8, 12, 16, then upward until something fails, to find the knee.
- Modes: 720p30, 720p60, 1080p30, 1080p60, and mixes like TP2's.
- Load switched on and off: decode at source to BGR for the ring; the live-view UI relay; raw-camera JPEG encode streams (`mjpeg_qsv` up to its limit of about 31 × 1080p30 [M], then libjpeg-turbo).
- Measured: CPU per process and in total, drops, write latency p99.9, disk MB/s, Defender CPU.
- Quiet machine (Gerald), plus one low-end machine.

#### TP4: Playback
skellycam-ui's real canvas player, on TP2's real mixed-rate recordings and TP3's 16-camera simulated recordings, plus T-KILL's killed files (NG07) and overlays drawn on the canvas (NG03).
- At 4, 8 and 16 cameras; 720p30, 720p60, 1080p30 and 1080p60.
- Measured: CPU (GPU process listed separately), memory, shown fps, seek latency, scrub rate above 58/s, and memory growth over a 30-minute play-and-scrub soak.
- Run on Gerald plus one low-end laptop, serving byte ranges through skellycam's FastAPI route vs Electron `protocol.handle`.
- **CPU-saving variants, each against the plain main-thread `ImageDecoder` baseline:**
  - (a) decode in Web Workers (1 per camera and a fixed pool of 2–4), with `ImageBitmap`s transferred to the main thread;
  - (b) reduced-size decode for small tiles (`ImageDecoder` / `createImageBitmap` at ½ and ¼ size), measuring whether Chromium uses libjpeg-turbo's scaled IDCT, i.e. whether CPU falls with size;
  - (c) no fetch or decode for hidden or off-screen tiles;
  - (d) an `OffscreenCanvas` in a worker that draws as well as decodes.
- Record whether any platform reports a JPEG decode accelerator (`jpegDecodeAcceleratorSupported`).

#### Release checks
- **T-FMC:** a freemocap posthoc run on phase-1 lockstep recordings, with outputs identical in structure to today's.
- **T-BUMP:** the full test suite plus one real recording after each major package bump.

## 4. Phase 2: skellycam and freemocap

| # | Package | Contents | Evidence |
|---|---|---|---|
| 2.1 | **Option: raw JPEG over the ring** | Ring v2: variable-size payload slots, per-slot seqlock, per-reader cursors (ring ranks 6, 11, 15). The camera publishes the JPEG bytes (about 163 kB at 1080p [M]) instead of BGR (6.2 MB); freemocap's readers decode. The recorder becomes a lossless ring reader (rank 7). It is behind an option, and BGR stays the default until freemocap's decode cost is measured. freemocap: ring attach, decode in the camera node, frame metadata dtype | 0 torn reads vs 39,854–41,834 [M]; decoupled recorder 59.82/59.95 fps (synthetic cameras) [M]; passthrough recorder CPU 19–20 % vs 924–954 % [M] (ring summary) |
| 2.2 | **Timing and lockstep** | Build the new timing sync in skellycam and make it the default, removing the gate: each camera runs at its native rate, every frame is written with its capture times, and group slots are assembled by time, with per-camera `frame_status` (fresh/repeated/missing). The existing time column becomes the slot time, and the fitted camera time from 1.6 becomes the camera's time. freemocap: `RecordingGroupTiming.resolve`, skellycam's `recording_timing_reader`, `FRAME_METADATA_DTYPE`, about 11 equal-count sites, and the realtime 1€ filter using capture time | Today the gate silently drops 14 % of the C930e's frames next to the generic camera [M]. Without lockstep, a stall drifted 606 ms while frame-count checks still passed [M], so slot assembly must flag it |
| 2.3 | **freemocap-ui canvas player** (D2: ported by a session in the freemocap repo, after the skellycam-ui player is built and tested) | The player from 1.9, shared between the two UIs (they are near copies today [C]) | §2.2 |
| 2.4 | **JPEG-only rule in freemocap** | The annotated-video writer tries `avc1`, then `mp4v`, then `MJPG` through `cv2.VideoWriter` [C] (`freemocap/core/pipeline/posthoc/video_node.py:339-345`); switch it to JPEG in MKV with a sidecar. skelly_synchronize's outputs also break the rule: see 2.8 | rule §1 |
| 2.5 | **freemocap packaging and bumps** (freemocap-repo session) | `requires-python >=3.13` and `.python-version` 3.13 (D3), relock against phase-1 skellycam, OpenCV 5 (D6), and freemocap's lock and UI to latest | §2.4, §2.5 |
| 2.6 | **Stable camera keys in file names and configs** | Serial, else port path, replacing index-based ids where freemocap parses them (`extract_camera_id_from_video_path.py`) | `usb_cameras/REPORT.md` findings 22–23 [M] |
| 2.7 | **2D time interpolation before triangulation** | Interpolate each camera's 2D track to a common time, with a rolling-shutter row term | Needs the A5 strobe rig: light-to-stamp bias between models 4.4–30.7 ms over 6 runs, unstable [M] |
| 2.8 | **Imported cameras with no sync (GoPro etc.)** | **Today** [C]: freemocap's import route (`api/http/mocap/mocap_router.py`) either only checks that frame counts are equal, or runs **skelly_synchronize**, the `skelly_synchronize` package from the **`freemocap/skellysync`** repo, branch `philip/rewrite`, pinned at `0231c41` in freemocap's `uv.lock`. skelly_synchronize finds **one offset per video**, by audio cross-correlation against a reference video (the default) or by the first brightness flash. If frame rates differ it **re-encodes every video to the lowest rate** (`ffmpeg -r`). It trims every video to a shared start and frame count with `ffmpeg -i … -ss … -frames:v N out.mp4`, which names no codec, so ffmpeg's default MP4 encoder re-encodes the video (long-GOP libx264 if the ffmpeg on PATH has it [I]). No drift correction. freemocap then pairs cameras by frame index. **Breaks the rules:** the outputs are long-GOP re-encodes with a second generation of loss. **Playback:** a separate `<video>`-based import player (Dom, 2026-11-11, as read from his reply). Its known risks: long-GOP seeking was error-prone in tests (libx264 GOP in fMP4 showed frames 2 behind and 2/10 seeks; HEVC in MP4 7/10 seeks [M], C9); HEVC has no software decode in Chromium [M] (F10); 8 `<video>` elements stalled [M] (F21). **Open, for the freemocap session:** keep the originals untouched and write a sync sidecar (offset, trim range, method, confidence) instead of re-encoding; correct clock drift with a second sync point (independent clocks drift up to ~30 ms over 10 min at 50 ppm [I]); combine with webcams through 2.2's time-based slots. **JPEG-only scoping:** `skellysync_jpeg/SCOPE.md` (2026-11-11) compares Design A (JPEG-in-MKV output, ~3–5 weeks in skellysync) with Design B (keep originals plus a sync sidecar, days in skellysync, more work in freemocap). It estimates JPEG at A at roughly 1–17× an action camera's source size (e.g. 4K60: ~112–480 GB/h against 27–54 GB/h), and lists 11 open decisions. It also found two skellysync bugs: a 30 s ffmpeg trim timeout, and the audio reattach ignoring the WAV for stereo sources | `skellysync` checkout `skelly_synchronize/core/pipeline/stages.py`, `core/backends/ffmpeg.py`; `chromium_codecs/FINDINGS.md` C9; `intra_playback/FINDINGS.md` F10, F21 |

Exit tests for phase 2:
- freemocap realtime and posthoc on unequal frame counts and dropped frames;
- TP2's sets re-run under the new timing sync, plus the mixed-rate sets (Kiyo Pro 1080p60 + C922 720p60 + C930e 720p30 + generic 720p30; Kiyo Pro 1080p60 + C922 720p60 + C930e 1080p30 + generic 1080p30; Kiyo Pro raw mode at its native rate + C922 720p60 + C930e 720p30 + generic 720p30). Compare per-camera frame counts, drops, slot assembly and `frame_status` with the phase-1 lockstep runs;
- freemocap's decode cost per camera with the JPEG ring;
- the A5 rig for the cross-camera bias, before 2.7;
- for 2.8: seek and step exactness of real GoPro H.264 and HEVC files in the `<video>` import player; sync error against a flash or clap ground truth at the start and at the end of a 10-minute or longer recording (clock drift).

## 5. Not doing
- **Any H.264, HEVC, AV1 or VP9**, intra or otherwise (rule).
- **Long-GOP anywhere** (rule).
- **A size-reducing export** (§1).
- **The `.web.mp4` transcode-on-play** (§2.2).
- **WebCodecs video decode** in either UI (§2.3).
- **Server-side (Python) decode for playback**, GPU-accelerated or not. Decoded 1080p frames are 6–8 MB, against about 163 kB of JPEG: about 1.5–2 GB/s for 8 × 30 fps, against about 39 MB/s. The frames also make a GPU → host → socket → renderer → GPU round trip, and the decode would add load to the capture server [I, from frame sizes; not benchmarked]. Decode stays in the UI. Dropped by Dom, 2026-11-11.
- **nvJPEG:** its licence terms are split, it showed no capacity gain over libjpeg-turbo on Gerald, and it missed A on CPU-decoded input [M] (EI §2.6, §2.7).
- **Capture:** OpenCV for capture; PyAV as the main capture path (wrong format on the Kiyo, synthesized timestamps [M]); libusb/WinUSB (driver swap); UVC PTS/SCR; the openpnp-capture branches; WinRT. **Upstream `sfn26`** (2026-10-30 to 11-10) makes a Rust/OpenPNP backend, `skellycam-rust`, a required build dependency, and its recorder pipes MJPEG to ffmpeg and re-encodes to libx264 [C] (`skellycam-rust/src/recording/recorder.rs:1-44` on `upstream/sfn26`). Phase 1 doesn't build on it (D8). Its libx264 recorder breaks the JPEG-only rule if it reaches `main`.
- **Recording:** plain MP4 or MOV; a folder of JPEGs; a custom container; record-time burn-in; jellyfin-ffmpeg; lossless or Bayer formats (deferred until a camera needs them).

## 6. Decisions

All resolved (Dom, 2026-11-11):

| # | Decision | Consequence |
|---|---|---|
| D1 | JPEG only | §2.1 |
| Encoder | Raw cameras: **Intel `mjpeg_qsv` first**, libjpeg-turbo fallback | Package 1.4 must expand limited-range YUY2 to full range before `mjpeg_qsv`, or the JPEGs come out washed out [M] (`results/hw_accel_target/FINDINGS.md` F2). T-KILL must measure its 3-frame hold-back. |
| D2 | **The freemocap-ui canvas player waits for phase 2.** Build and test the skellycam-ui player in phase 1; a session in the freemocap repo ports it in phase 2. | freemocap-ui cannot play recordings made by phase-1 skellycam until phase 2. freemocap's processing is unaffected. |
| D3 | **freemocap's Python floor goes to 3.13 in phase 2,** done by the freemocap-repo session | Phase-1 skellycam (Python 3.13, PyAV 19) cannot be resolved by freemocap's current lock, so **freemocap keeps its current skellycam pin until its phase-2 session** (§2.4). |
| D4 | No H.264 encoders to choose between | — |
| D5 | No size-reducing export | — |
| D6 | **OpenCV 5 in phase 2** | Phase-1 skellycam pins `opencv-contrib-python==5.0.0.93` (D13; it moved together with numpy 2.5). freemocap moves to the same pin in phase 2. |
| — | No server-side decode for playback | §5 |
| — | Tests are split into TP1 controls and frame extraction, TP2 real-camera recording at mixed rates, TP3 simulated-camera throughput and TP4 playback | §3.3 |
| — | All tests turn auto-exposure, auto gain and autofocus off and test manual control only; gain is pinned in the exposure step, not a separate control | §3.3 TP1, 1.3 |
| — | Kiyo Pro wedges are handled, recorded and left alone: no revival, no diagnosis | §3.3 TP1 |
| — | Imported cameras: separate `<video>`-based import player (as read from Dom's reply) | §4, 2.8 |
| D8 | **Phase 1 is built on upstream `main`** (Dom, 2026-11-11, later session). freemocap's `pyproject.toml` pins skellycam `branch = "main"` [C] (`freemocap/pyproject.toml:43`), not `development-streaming` | Feature branch off `upstream/main`. `main` is 57 commits behind `sfn26` and 27 behind `development-streaming` [C, `git rev-list` 2026-11-11] |
| D9 | **No per-model gain caps:** the gain limit is measured on the live image in the exposure step, from noise against gain (Dom) | `exposure_gain_tradeoff.md` §5.2a; T1 checks the rule instead of producing caps |
| D10 | **White balance follows the D11 rule:** white balance is pinned at the value it has when the camera starts, like the other controls. If AWB is on at start, its current value is read, AWB is switched off and that value is held. A mismatch with a loaded calibration is shown to the user, who chooses (Dom; replaces an earlier one-shot-AWB answer) | 1.3; TP1 calibration-mismatch case. Risk [I]: read right at stream start, AWB may not have converged yet; the start value is still what gets pinned and recorded |
| D11 | **Zoom, pan, tilt and image controls locked at the camera's start values**, not defaults. Recorded with the config and the calibration; a mismatch when loading a calibration is shown to the user, who chooses what to do (Dom) | 1.3; TP1 calibration-mismatch case |
| D12 | **Power-line frequency = local mains; AE priority = 0** (Dom) | 1.3 |
| D13 | **Versions pinned exactly, no ranges** (Dom, 2026-11-11), for Python, Python packages, npm packages, git sources, the build backend and CI tooling | §2.5; replaces the earlier "raise a minimum only" rule |
| D7 | Phase 1 tests lockstep only: TP2 never mixes frame rates, and all cameras start at the lowest common rate. The new timing sync and its mixed-rate tests are phase 2 (2.2) | §3.3 TP2, §4 |

## 7. Sources
- `skellycam_recording/recording_upgrade/EXECUTIVE_SUMMARY.md` and `results/EVIDENCE_INDEX.md`. Note: EI §2.12 and executive summary §4.3 compare passthrough with H.264 made from different (YUY2) captures; the same-source figures are in `results/intra_compare/FINDINGS.md` §3.1.
- `results/chromium_codecs/FINDINGS.md` (C1, C2, C27, C28); `results/intra_playback/FINDINGS.md` (F18–F24) and `bench/bench_tables.md`; `results/intra_playback/gapfill/GF10_wc_scrub_memory.md`.
- `usb_cameras/REPORT.md`, `usb_cameras/WINDOWS_RUN_20261110_EXEC_SUMMARY.md`, `usb_cameras/results/windows/Gerald/suite_20261111T040003Z/summary.md` (G-RAW), `usb_cameras/docs/capture_stack_options_plan.md`, `timestamp_accuracy_options.md`, `xplat_capture_plan.md`, `chromium_comparison.md`, `macos_uvc_controls_review.md`, `windows_timer_resolution.md`, `skellycam_exposure_review.md`.
- `frame_ring_buffer/docs/frame_ring_buffer_summary.md`; `skellycam_recording/REPORT.md`.
- Code, lockfiles and package indexes read 2026-11-11:
  - skellycam: `pyproject.toml`, `uv.lock`, `api/http/playback/playback_router.py`, `utilities/transcode_to_h264.py`, `core/recorders/video_audio_remuxer.py`, `core/recorders/videos/{video_recorder,pyav_video_writer}.py`, `skellycam-ui/package.json`, `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx`;
  - freemocap: `pyproject.toml`, `uv.lock`, `freemocap-ui/src/components/playback/usePlaybackController.ts`, `api/http/playback/playback_router.py`, `api/http/mocap/mocap_router.py`, `core/pipeline/posthoc/video_node.py`, `utilities/extract_camera_id_from_video_path.py`;
  - `uv tree --outdated --depth 1` (skellycam) and `npm outdated` (skellycam-ui).
