# Timestamp anchor test (sync rig strobe)

**Status (2026-11-06): synthetic-tested only. Nothing here has run on hardware.** No camera was opened and no ESP32
was connected while this was written. The capture harness change compiles (MSVC 2022, `/W3`, no warnings).
The synthetic end-to-end self-test and the band unit tests pass (numbers in [Self-test](#self-test-the-gate)).

The test answers one question for each camera × mode × API × timestamp source: **where does the timestamp sit
relative to when light hit the sensor?** It uses the sync rig's LED strobe. The target board is the **M5Stack
AtomS3 Lite** (ESP32-S3, native USB). Its wiring and firmware are in [../../sync_rig/atoms3_sync_rig/](../../sync_rig/atoms3_sync_rig/).
The protocol is the one in [../../sync_rig/README.md](../../sync_rig/README.md) "Serial protocol". The classic-DevKit
firmware speaks the same protocol.

## What is measured

Model per frame k, fitted separately for each capture (stream start) and each source:

```
ts_k = a + b*s0_k + alpha*b*E_k + eps_k
```

| Symbol | Meaning (units: ns) |
|---|---|
| s0_k | exposure start of image row 0, in ESP32 time: s0 = t_c − r_b·L |
| E_k | exposure **measured** from the band height: E = (r_b − r_t)·L. The requested value is never used |
| t_c | strobe centre = (t_rise + t_fall)/2 from the `EV S` loopback capture. With a linear sensor, the 50 % crossing of each band edge sits exactly at t_c, whatever the width w |
| r_t, r_b | top and bottom 50 % band edges, in rows. **Row 0 = top of the decoded image = read out first** |
| L, H, T_ro | line time (row-to-row delay), image rows, readout time T_ro = H·L |
| a, b | absorb the source clock's offset and rate. So alpha needs **no host-clock link**, for any source, including camera-clock PTS/SCR |
| alpha | 0 = the timestamp tracks exposure start; 0.5 = mid-exposure; 1 = exposure end of row 0 = row-0 readout start (fixed-readout rolling shutter). Expected ≈ 1 for anything tied to readout or transfer |

E has to vary inside one capture for alpha to be identifiable. That is why `mf_uvc_timing.exe` now cycles the
exposure during a stream (`--exposure-schedule`).

**K** (host-clock sources, QPC):

- `K_alpha1 = mean(ts − host(s0 + E))` is the deliverable K when alpha ≈ 1.
- `K_alphafit = mean(ts − host(s0 + alpha·E))` is the general form.
- `host()` maps ESP32 time to QPC through the ping fit.
- **K_rel** is K minus the K of a reference camera/source *in the same run*. The ping offset cancels, so only the
  clock rate matters, and K_rel is not "estimated".
- **K_abs** uses the ping fit's offset. It is **estimated**: both ping offsets are reported (first byte and last
  byte of the PONG), with the asymmetry bound. On the AtomS3 the asymmetry source is native USB CDC (bulk IN
  polling), and the PONG RX time is estimated (`B`), because there is no UART RX pin to capture.
- Camera-clock sources (UVC PTS/SCR ticks) get alpha and jitter only. The derived `<name>->qpc_env` source maps
  the ticks to QPC with a whole-run lower envelope against `host_arrival_ns` (non-causal), and then gets a K.

**Downstream formula** (freemocap), for alpha ≈ 1 (QPC ns, mid-exposure of row y):

```
t_light(row y) = ts − K_alpha1 − E/2 + (y/H)·T_ro
```

Deliverable per camera × mode × API × source: alpha (95 % CI), K_rel, K_abs (estimated, both offsets), L, T_ro,
and per-frame jitter (residual std and MAD of the fit). These are in `anchor_analysis.json`
(`measurements.runs[].cameras[].sources`, and `measurements.cross_run` across stream restarts) and in
`anchor_summary.md`.

## Files

| File | Role |
|---|---|
| `rig_session.py` | PEP 723 (pyserial). Opens the rig port with DTR/RTS fixed (no reset), waits for `EV B`, configures `BAR DARK` + `STROBE`, then `START` (immediately or on request). Logs **every** line with host QPC stamps. Interleaves jittered PINGs (events stay on; PONGs are picked out from among the EV lines; extra PONG tokens are kept). Ends with `STOP` and the clock fit. Stop with a stop file, Ctrl+C, `stop` on stdin, or `--duration`. `--simulate` runs against a built-in fake firmware |
| `run_anchor_test.py` | PEP 723 (stdlib). Orchestrator: rig session → N captures of `mf_uvc_timing.exe --save-mjpeg` under `tools/camlock.py`, with the timeout inside the lock → strobe START 2 s after every camera streams and STOP at capture end (a new epoch per capture, used to confirm strobe identity) → result JSON. `--dry-run` prints the commands |
| `analyze_anchor.py` | PEP 723 (numpy, OpenCV). Analysis CLI. Decodes the MJPEG, solves each frame, fits every source, writes JSON, markdown and per-band CSV tables |
| `bands.py` | band detector (DESIGN §F 5) |
| `solve.py` | strobe assignment, per-frame solve, line time, blanking map, echo check (§F 6–7) |
| `score.py` | anchor fit, CIs, K (§F 10) |
| `rigio.py` | event-log and ping parsers, clock fit (imports `sync_rig/host/esp32_clock_sync.py`) (§F 1–2) |
| `frameio.py` | frames.jsonl, session/controls JSON, MJPEG → row profiles, timestamp sources (§F 3) |
| `selftest_anchor.py` | synthetic end-to-end self-test (test plan V3, the gate) |
| `test_bands.py` | unit tests: sub-row accuracy, clipped band, double and merged band, no band in blanking, echo band, noise |

Harness change: `../src/mf_uvc_timing.cpp`

- New options: `--exposure-schedule "-9,-7,-6"`, `--exposure-dwell-s 5`, `--exposure-first-s 1` (first set 1 s after
  the first frame, which covers the C930e drop-before-start quirk in REPORT finding 11), and a per-camera override as
  the 7th `--cam` field, `-5:-4:-3`.
- Sets run on their own thread, so `ReadSample` is never delayed.
- Each set is logged to `<key>.controls.jsonl`: QPC before/after, HRESULT, readback, and a final readback.
- Without the option, behaviour is unchanged.
- Build with `timing\build_mf.bat`. Output goes to `timing/build/`, which is gitignored.

## Hardware setup (Phase 0, strobe only)

1. **Rig.** Build the AtomS3 Lite strobe-only rig: G5 → AO3400A gate, plus a loopback wire G5 → G6; see
   [../../sync_rig/atoms3_sync_rig/README.md](../../sync_rig/atoms3_sync_rig/README.md). Use the Phase 0 BOM in
   [../../sync_rig/README.md](../../sync_rig/README.md): a 1–3 W green or deep-red LED without phosphor, ~1.8 Ω
   3 W, 2200 µF + 10 µF at the LED, a 1 A polyfuse, a 5 V 3 A supply, and a diffuser.
2. **Card.** Use a matte white card that **fills the full image height of every camera**. Point the LED at the
   card, not at the lenses.
3. **Room.** Dark room. Turn off auto-exposure, auto white balance and anti-flicker on every camera. Hold gain
   fixed. The harness does not set gain: check gain readback in `session.json` (`controls.gain`) and keep it
   constant across runs.
4. **Band brightness.** The band plateau must stay **below clipping**: a saturated band moves the 50 % edge by up
   to w/2. Aim for ~50–70 % of full scale; set brightness by LED current or distance, never by PWM.
5. **Strobe width.** Use w ≥ 2·L, so the band edge spans at least two rows. With w = 50 µs:
   - C922 (L ≈ 43 µs): the edge spans 1.2 rows; edge error ≤ 1.6 µs.
   - At L = 64 µs: the edge spans 0.8 rows; edge error up to 7 µs (zero mean; still inside the 20 µs budget).
   - w = 100 µs at L = 64 µs halves it (unit test `test_single_band_subrow`).
   - Duty must stay ≤ 1 %, both pulses counted.
6. **Topology.** Put each camera on its own USB 2.0 link (test plan §4 rig-run topology). Before each session, run
   `uv run --script research/usb_cameras/bandwidth/win_usb_topology.py --pipes-only`. It opens no camera.
7. **Cameras and modes.**
   - First pass: C922, C930e, the generic camera (4C4A:4A55) and the Kiyo Pro (included per the 2026-11-06 test
     rules), all at **1280×720@30 MJPEG**.
   - Then, per camera, the other modes skellycam would use (e.g. 1920×1080@30, 640×480@30).
   - L must be measured in every mode (DESIGN §B).
   - Exposure set points must be in range for each camera. Read the range first from `session.json`
     (`controls.exposure_log2.min/max`). Examples: C922 −9, −7, −6; C930e −5, −4, −3; generic −7, −6, −5; Kiyo:
     read first.
   - The Kiyo's PTS ticks at ~1 kHz, so its PTS jitter floor is ~0.3 ms. The C930e's PTS is synthetic, so use its
     `uvc_scr_stc` (REPORT finding 10).

## Bring-up order (check on hardware before scoring anything)

1. **Self-test first.**
   - `uv run --script research/usb_cameras/timing/rig/selftest_anchor.py` must print `SELF-TEST PASS`.
   - `test_bands.py` must print `8/8 passed`.
2. **Rig alone, no camera.**
   - `rig_session.py --list-ports` must show the VID 303A port.
   - `rig_session.py --port COMx --out-dir <tmp> --duration 60` must run with **no** `EV B` after the first open
     (`--line-state deassert` is the default; if the board stays silent, try `--line-state dtr`).
   - `EV S` lines must arrive about every 33.4 ms.
   - Check `rig_session.json`: `measurements.clock.fit.residual_std_us`, `asymmetry_bound_us`, and
     `rx_src_counts` (expect `B`).
   - Then check the strobe edges against a logic analyzer (test plan V1).
3. **Band visible (V0).**
   - One camera, 720p30, fixed exposure, about 10 s:
     `run_anchor_test.py --port COMx --cam "<cam>,1280,720,30,-7,4500" --seconds 10 --restarts 1 --label v0`.
   - Look at a few frames. You should see a horizontal band, not saturated, and walking down the image.
4. **L run (double strobe)** for each camera × mode (below). L's coefficient of variation should be < 0.5 % (V4).
5. **Echo run and blanking run** for each camera × mode (below), before anchor runs are scored.
6. **Anchor runs.**
   - Check the `epoch_check` in every camera's `bands.assignment`. It must be `consistent: true`.
   - If it is not, the strobe identity is off by whole strobe periods. K would then be off by multiples of
     ~33 ms; alpha is unaffected.

## Run plan (per camera × mode)

All commands are run from the repo root. `<cam>` is the `--cam` symlink substring, e.g. `vid_046d&pid_085c`.

| Step | Command | Notes |
|---|---|---|
| L run | `uv run --script research/usb_cameras/timing/rig/run_anchor_test.py --port COMx --cam "<cam>,1280,720,30,-9,4500" --double --seconds 20 --restarts 1 --label L` | Double strobe, gap 10 ms. Use a short exposure (E < gap − w), so the two bands do not merge |
| Echo run | `... --cam "<cam>,1280,720,30,-7,4500" --strobe-period-us 50033 --seconds 15 --restarts 1 --label echo` | Strobe every 1.5 frames, so frame k+1 leaves frame k's band rows free. The firmware's 65,535 µs period limit rules out the plan's 3·T + 33 µs sparse strobe |
| Blanking run | `... --cam "<cam>,1280,720,30,-9,4500" --strobe-period-us 33666 --seconds 20 --restarts 1 --label blank` | Fast sweep (T + 333 µs) at the shortest exposure. Maps the no-band phases and gives the sweep cross-check of L |
| Anchor runs | `... --cam "<cam>,1280,720,30,auto,4500" --exposure-schedule "-9,-7,-6" --exposure-dwell-s 5 --seconds 240 --restarts 3 --label anchor` | ≥ 3 in-range exposures, 5 s dwell, ~4 min per stream, 3 stream restarts in one rig session. Several cameras can share a run: repeat `--cam`, and put per-camera schedules in the 7th field, e.g. `"vid_046d&pid_0843,1280,720,30,auto,auto,-5:-4:-3"` |

- Default strobe: period = round(1e6/fps) + 33 µs (33,366 µs at 30 fps), width 50 µs, phase 1000 µs.
- Add `--width-us 100` for cameras with L > 50 µs.
- Add `--dry-run` to any command to see exactly what would run.
- Raw MJPEG goes to `%USERPROFILE%\Documents\skellycam-raw\results\windows\<host>\rig_anchor_<UTC>_<label>\`.
- The results folder gets the rig logs, `capture_rNN/` (frames.jsonl, session, controls; ~20 MB per camera per 4 min
  stream) and `result.json`.

## Analysis

```
uv run --script research/usb_cameras/timing/rig/analyze_anchor.py \
    research/usb_cameras/results/windows/<host>/rig_anchor_<UTC>_L \
    research/usb_cameras/results/windows/<host>/rig_anchor_<UTC>_echo \
    research/usb_cameras/results/windows/<host>/rig_anchor_<UTC>_blank \
    research/usb_cameras/results/windows/<host>/rig_anchor_<UTC>_anchor  [--out-dir <dir>]
```

- **Line time.** Double-strobe runs are analysed first. Their L is used for the other runs of the same camera and
  mode. `--line-time-ns KEY=NS` overrides it. Without either, the sweep regression is used (flagged).
- **Options.** `--gamma` (default 2.2, the tone curve to linearize), `--channel luma|green`, `--cols 0.2,0.8`
  (column ROI) and `--thr-frac` (default 0.35).
- **Outputs** go to `<first run>/analysis/`:
  - `anchor_analysis.json` (standard result fields);
  - `anchor_summary.md`;
  - `bands/<run>__<capture>__<key>.csv`, the per-band table (seq, slot, strobe, t_c, r_top, r_bot, clip flags,
    plateau, arrival − readout).
- **Profile cache.** Decoded row profiles are cached next to the raw MJPEG (`_profile_cache/`, outside the repo).

## Proposed pass criteria

- **Gate.** `selftest_anchor.py` passes before any real data is scored (test plan V3). It recovers s0 and E within
  20 µs per frame, L within 0.1 %, alpha within ±0.03, and K within 50 µs on synthetic truth.
- **alpha.** 95 % CI within ±0.05 (`alpha_ci95_halfwidth ≤ 0.05`) for every camera × mode × source that is to be
  rated.
- **K.** `K_alpha1` repeatable to ≤ 0.2 ms across the 3 stream restarts (`cross_run.K_alpha1_range_us ≤ 200`). The
  restarts share one ping fit, so this measures stream-start variation only. Repeat the rig session on another day to
  include ping-fit variation.
- **Rig health.**
  - `epoch_check.consistent` is true in every capture.
  - No `EV E` lines, and `strobe_k_lost` = 0.
  - L's CV < 0.5 % (V4).
  - Echo characterized before S/T scoring (V0).
- **Absolute.** `K_abs` stays "estimated ± asymmetry bound" until the SOF-lock validation (test plan V6/V7). The
  AtomS3 firmware stamps SOF; using that to settle which ping offset is right is not implemented here.

## How to read alpha and K

- **alpha ≈ 1 with a tight CI.** The source is tied to the end of row 0's exposure (readout start). Use
  `t_light(row y) = ts − K_alpha1 − E/2 + (y/H)·T_ro`.
- **alpha ≈ 0 or 0.5.** The source tracks exposure start or mid-exposure. Use `K_alphafit` with
  `t_light(row y) = ts − K_alphafit − (alpha − 0.5)·E + (y/H)·T_ro`.
- **alpha > 1.** The REPORT finding 12 "−1.14 × requested change" pattern. With measured E, this should go away if
  it came from requested ≠ applied exposure. If it stays, readout timing itself moves with E on that sensor.
- **Wide CI with large jitter** (e.g. MF sample time or host arrival on the ~16 ms grid, REPORT finding 7). The
  source cannot locate the exposure. The block bootstrap keeps the CI honest; a plain OLS CI would look falsely tight.
- **K_rel** between cameras in the same run is the offset-free answer for cross-camera alignment. **K_abs** is light
  → QPC, with the ping-path caveat.

## Self-test (the gate)

```
uv run --script research/usb_cameras/timing/rig/selftest_anchor.py          # full, ~3 min
uv run --script research/usb_cameras/timing/rig/selftest_anchor.py --quick  # ~1.5 min
uv run --script research/usb_cameras/timing/rig/test_bands.py
```

What the synthetic world contains:

- **Clocks.** The ESP32 runs 20 ppm fast against QPC. Pings have random path delays. The clock fit used is the real
  one.
- **Frames.**
  - Rendered with exact rolling-shutter strobe overlap, vertical vignetting and ambient light.
  - Camera A has an 8 % temporal-NR echo and vertical sharpening.
  - Tone curve 1/2.2, pixel noise, colour JPEG at quality 80.
  - Fixed-readout sensor.
- **Exposure.** The schedule switches every 5 s with a 2-frame latency, and applied ≠ requested (A integrates 3 %
  short; both cameras quantize E to whole lines).
- **Camera B** differs from A in size, L (64.1 µs), phase and drift, and drops 2 frames.
- **Sources with known anchors:**

| Source | Model |
|---|---|
| `syn_alpha1_ns` | alpha = 1, K = +2.0 / +3.1 ms (cameras A / B), 0.3 ms jitter |
| `syn_alpha05_ns` | alpha = 0.5 |
| `os_timestamp_ns` | 15.625 ms grid |
| `host_arrival_ns` | grid + latency |
| `uvc_pts`, `uvc_scr_stc` | camera clock, ±37/−52 ppm |

- **Runs.** An L run, an echo run, a blanking run, and an anchor run with two stream restarts (one with `--quick`).
  Each capture has a deferred strobe START.

Result of the full run on 2026-11-06 (Gerald, synthetic): see
`results/windows/Gerald/rig_anchor_selftest/selftest_*.json` (`measurements.checks`). It includes per-frame s0/E
errors, L error, alpha, K, the grid-source CI, echo, blanking, the epoch check and exposure per dwell.

## Known limitations

- **Never run on hardware.** The AtomS3 firmware is a separate draft. The `B` (estimated) PONG RX time widens the
  ping asymmetry bound.
- **Strobe identity.** It comes from a physical floor: a frame arrives after its last row is read out, so the
  smallest candidate above (H−1)·L − margin is chosen. The epoch check confirms it.
  - If host arrival trailed readout by more than one strobe period, K would be off by whole periods (~33 ms), and
    `epoch_check` would flag it.
  - With `--no-defer-start` there is no epoch check.
- **Tone curve.** Linearization uses a fixed power law (`--gamma`). The strobe-width-sweep tone calibration
  (DESIGN §F 4) is not implemented. For narrow pulses, a gamma error moves the 50 % edge by at most a fraction of
  w/2, as a constant E bias. That shifts K by alpha·bias and leaves alpha unchanged.
- **Edge sampling.** The edge is under-sampled when w < L (see Hardware setup 5).
- **Clipping.** A saturated band biases the edges.
- **Clipped bands.** A band clipped at the frame top or bottom gives only one edge. Such frames give s0 or s0 + E,
  never E, and are not used in the alpha fit.
- **Overlapping bands.** These come from E > gap in a double strobe, or two strobes in one long exposure. They are
  flagged as `stepped` and not used for E or L.
- **Fixed readout assumption.** "Readout timing does not move with E" is used only to number frame slots and for
  the blanking map, never for alpha.
- **What is not implemented:**
  - causal (online) mappings, test plan T1 analysis 2: the fit here is whole-run;
  - SCR→SOF→host chains;
  - the LED bar decoder;
  - FSIN;
  - YUY2 (the harness captures MJPEG only).
- **Camera-clock K** (`->qpc_env`) inherits the arrival grid through the lower envelope and is non-causal.
- **Firmware limit.** The 65,535 µs strobe-period limit rules out sparse strobes (≥ 2 frame periods) at 30 fps.
  The echo check therefore uses a 1.5-frame period.
- **Several cameras at different fps** share one strobe period. The camera whose fps did not set the period sweeps
  faster or slower. That is fine for anchors, but its sweep L cross-check needs ≥ 2 band wraps.
