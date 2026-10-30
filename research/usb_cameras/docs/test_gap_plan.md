# USB camera research: plan to fill the test gaps

Draft plan, 2026-10-30, not yet reviewed by Dom. Paths are relative to `research/usb_cameras/` unless noted.

- **Inputs:**
  - the verified method × goal matrix (summary in [../README.md](../README.md#method-comparison-2026-10-30); full cells and evidence in `results/agent_reports/goal_matrix_gap_plan_wf_30cb7742-77f.json`);
  - the RocSync review ([rocsync_review.md](rocsync_review.md));
  - the ESP32 rig design ([../sync_rig/DESIGN.md](../sync_rig/DESIGN.md)) and draft ([../sync_rig/](../sync_rig/)).
- **How it was written:** by workflow `wf_30cb7742-77f` (draft, completeness critic, revision).
- **Goal numbering** follows the current brief: G1 sync, G2 timestamp, G3 MJPEG, G4 ID, G5 bandwidth, M1 exposure, M2 format, M3 focus. REPORT.md numbers its goals differently.

- Figures marked *est.* are estimates. Nothing in this plan has been measured yet.
- Thresholds marked *proposed* need Dom's sign-off before any cell is rated with them.
- Claims taken from outside the repo are marked *web*, with the source.

---

## 1. Summary

**The decision this plan supports** is which capture stack skellycam moves to:
- **Windows primary:** MF native MJPG with UVC metadata, as a C++ extension.
- **Windows fallback:** PyAV DirectShow `vcodec=mjpeg`.
- **Bandwidth path:** libusb on WinUSB. Use it only if fitting more cameras per link is worth a driver swap.
- **Linux:** V4L2 or libusb.
- **macOS:** AVFoundation.
- **Hardware-trigger track:** FSIN, for G1.

**Already settled on Windows:**
- G3: native MJPEG.
- G4: identity mapping through the MF and DirectShow paths. Stability is still open.

Most of what remains open is the must-haves and the timing ground truth.

**The gaps that most affect the decision:**
1. **M3: focus has never been set on any path Dom would ship.**
   - The usbvideo harnesses only read focus.
   - The only focus write in the whole study was libuvc on WinUSB, on the C930e, and it was checked by readback only.
   - The C922's focus value moved between 0 and 40 across cells, so autofocus was running in every usbvideo test.
2. **M1: exposure has been shown to take effect in only one case:** libuvc with `--controls-after-start` on the C930e. Everywhere else the evidence is readback only.
   - MF on the C930e applied it in 1 of 5 runs.
   - The C930e accepts nothing below −5 through the DS side channel.
   - Every libusb harness except libuvc's after-start mode sets exposure before COMMIT, which is the order that failed.
   - In the MJPEG matrix, exposure was set through the DS filter even in MF cells, so MF's own exposure path is not demonstrated.
   - No stack's own API was tested (OpenCV `CAP_PROP_EXPOSURE`, PyAV, nokhwa).
3. **G1 has never been measured.**
   - "No" is inferred.
   - There is no ground truth without display scan-out, and no run was longer than 30 s.
   - **The study holds two phase-walk figures that contradict each other:**
     - About one frame every 20–25 s. This comes from 10 s delivered-fps differences (30.00 vs 30.04 fps ≈ 1300 ppm). It is almost certainly an artefact of counting or of the 16 ms grid.
     - About one frame every ~14 min. This comes from the PTS-vs-ground-truth rates (+35 ppm for the C930e, −3.9 ppm for the C922, about 39 ppm relative; `timing/VERIFY_method.md` §5).
   - **Until S2 runs, the README may cite only the ppm-derived walk, labelled *derived*.** It must not cite the fps-derived figure.
4. **G2 has a floor of about 0.5 ms and no absolute latency.**
   - The flash method cannot score below about 0.5 ms and cannot give the absolute latency from light to timestamp.
   - Only the MF and libusb sources were scored.
   - The generic camera has not been measured.
   - The SCR→QPC basis holds for only about 2–3.5 s.
   - Nobody has checked whether a DS/KS client can read UVC PTS/SCR at all (`docs/capture_backends_review.md`). That decides whether the PyAV DS fallback can ever do better than G2 "no".
5. **G5 has been measured on the C930e only.**
   - No link has carried three cameras.
   - The cost of a driver swap is not understood.
6. **G4 stability under reboot, replug and port move is untested,** and so is a pair of identical cameras.
7. **MF's Frame Server CPU cost is unmeasured.** It needs elevation (PROGRESS: "Still needs a human"). It bears directly on choosing MF over PyAV DS.
8. **Nothing has run on Linux or macOS hardware.**

**The tests that close them, in priority order:**

| # | Test | Closes | Needs the rig? |
|---|---|---|---|
| 1 | **C3** focus-control matrix (Siemens star; exposure, gain and WB locked) | M3 on every candidate | No |
| 2 | **C1** exposure-control matrix. Per-camera in-range set points; set before vs after start; LogiTune on vs off. The pre-rig pass can rate only "no" or "partial (pending rig)" | M1, plus the C930e item (REPORT further investigation 6, PROGRESS §E) | For "yes" |
| 3 | **R0/R1** ESP32 strobe rig built and validated (V0–V6); later **R2** ESP32-S3 SOF lock (V7) | Prerequisite for every S and T test, and for absolute G2 | n/a |
| 4 | **S1–S3** exposure phase between cameras, ≥ 30 min drift, start alignment and topology; **S6 (opt)** closed-loop steering | G1 for every free-running method | Yes |
| 5 | **T1–T5** every timestamp source scored against the rig; long SCR→QPC runs; C930e modes; generic camera; DS metadata probe | G2 | Yes (T5 feasibility: no) |
| 6 | **X2** Frame Server CPU (elevated) | MF vs PyAV DS choice | No |
| 7 | **B1–B4** WinUSB phase 3, three or more cameras per link, driver-swap strategy, integrity | G5 | No |
| 8 | **I1–I3** controlled reboot, replug and port move; identical pair; open-by-key on each API | G4 | No |
| 9 | **LX / MX** Linux and macOS sessions; **S4** FSIN spike when the OV9281s arrive | Off-Windows cells; the G1 "yes" route | Partly |

**How G1 is rated, and why it needs few runs.**
- A free-running UVC camera's exposure phase belongs to the camera, not to the API. So S1 and S2 run once per camera pair, through MF.
- S3 then tests the one thing an API could change, start-time alignment, on three paths:
  - MF;
  - PyAV DS;
  - libuvc (the one libusb path).
- Only those three rows get **measured** G1 cells. Every other usbvideo and libusb row is rated **"n·i (transferred from S1–S3 on MF)"**, and the plan does not present those as measured.
- G1 is rated by **controllability**, not by a snapshot. Two free-running cameras that happen to land ≤ 1 ms apart in one run are still "no".
- Every cell keeps two things apart:
  - **measures the offset** (G2: the method can timestamp exposure);
  - **aligns the exposure** (G1: the method can move it).
- Dom's assumption (no USB API aligns exposures) is the expected result, and the plan measures it rather than assuming it.
- Routes to G1:
  - S4 (FSIN) is the only open-loop route to "yes".
  - S6 (software phase steering) can reach "partial" at most.

---

## 2. Gap table

**Cell format:** `rating·basis → test`.
- **Rating:** y = yes, p = partial, n = no, ? = unknown, n/a.
- **Basis:** m = measured, i = inferred, w = web, nt = not tested.
- **Markers:**
  - `done`: no test is needed.
  - `out`: out of scope, with the reason in the Note column.
  - `(opt)`: run only if that method is still a candidate.
  - `n·i (tr)`: G1 transferred from S1–S3 on MF, not measured on that path.

| Method | G1 sync | G2 timestamp | G3 MJPEG | G4 ID | G5 bandwidth | M1 exposure | M2 format | M3 focus | Note |
|---|---|---|---|---|---|---|---|---|---|
| OpenCV CAP_DSHOW (today) | n·i (tr) | n·m → T1 (baseline) | n·m done | p·m → I3 | n·m done | p·m → C1 (incl. `CAP_PROP_EXPOSURE`) | p·m → C2 | ? → C3 | Status-quo baseline; scored, not a candidate |
| OpenCV CAP_MSMF | n·i out | n·m out | n·m out | p·m out | n·m out | p·m out | p·m out | ? out | Rejected: 39–41 s open, no JPEG, synthetic pos_msec |
| **MF native MJPG + PTS/SCR** | n·i → S1–S3 (measured) | p·m → T1, T3, T4 | y·m done | y·m → I1, I2 | n·m done | ? → C1, T3 (MF's own IAMCameraControl; the matrix used the DS filter) | y·m → C2 (720p60, YUY2) | ? → C3 | Primary Windows candidate; CPU → X2 |
| MF + MF decoder (NV12) | n·i (tr) | p·m → T1 (parse PTS, opt) | n·m done | y·m (= MF) | n·i done | ? → C1 (same MF source) | y·m → C2 (1080p, 3-cam, opt) | ? → C3 (= MF) | Preview companion to the MF row |
| **PyAV dshow `vcodec=mjpeg`** | n·i → S3 (measured) | n·m → T1, **T5** | y·m done | p/y·m → I1, I3 | n·m done | ? → C1 (DS side channel during the stream) | y·m → C2 | ? → C3 | Fallback candidate; CPU → X2 |
| WinRT MediaFrameReader | n·i out | n·m out | n·m out | y·i out | n·i out | ? out | p·m out | ? out | Rejected: MJPG subtype gives E_INVALIDARG |
| GStreamer mfvideosrc | n·i (tr) | n·m → T1 (opt) | y·m → H1 (opt) | p·m → I3 (opt) | n·i | n·i → C1 side channel (opt) | y·m | n·i → C3 side channel (opt) | Wrapper only; expected = raw MF plus a side channel. CPU out of scope |
| GStreamer ksvideosrc | n·i out | n·m out | y·m out | n·m out | n·i out | n·i out | y·m out | n·i out | Rejected: deprecated, opens every KS filter |
| SDL3 3.4.18 | n·i out | n·m out | y·m out | n·m out | n·i out | ? out | y·m out | ? out | Rejected: name-only ID; enumeration opens every camera |
| nokhwa 0.10.11 (MSMF) | n·i (tr) | n·m → T1 (opt) | y·m → H1 (opt) | p·m → I3 (opt) | n·m | p·m → C1 (opt) | p·m | ? → C3 (opt) | Adds nothing over raw MF. CPU out of scope |
| pygrabber / openpnp-capture | n out | n out | n·m out | n/p out | n out | n/p·i → C1 DS cell | p·m out | n/p·i → C3 DS cell | Decode to RGB, no timestamps. openpnp's control API *is* DS IAMCameraControl, so the C1/C3 DS side-channel cells cover it. CPU out of scope |
| DS minimal graph probe | n·i (tr) | ? → T5 (metadata reachable?) | ? out | y·m | ? out | p·m → C1 (DS) | y·m | ? → C3 (DS) | Reachability probe; T5 extends it |
| **libuvc + patch 0001 (WinUSB)** | n·i → S3 (measured) | p·m → T1, T2 | y·m done | y·m → I1 | y·m → B1, B2 | p·m → C1 | p·m → C2 | p·m → C3 (absolute focus, sharpness) | Bandwidth reference; C930e only so far |
| Python libusb1 streamer | n·i (tr) | p·m → T1 | y·m → B4 | p·m → B1 (C922 serial) | y·m → B2 | p·m → C1 (add after-start) | p·m → C2 | ? → C3 (add focus) | Python prototype |
| pyuvc (PyPI / patched) | n out | n·m out | n / y·m out | n·m out | n / y·m out | p·m out | n / p·m out | ? out | PyPI crashes. Patched build: timestamps 103–129 ms wrong, and the C930e has already shown bandwidth. Not in B1. Revisit only if B1–B3 favour WinUSB and Python is required |
| **Rust uvc_iso (libusb)** | n·i (tr) | p·m → T1 | y·m done | p·m → B1 | y·m → B2 | p·m → C1 | p·m → C2 | ? → C3 (add focus) | Native-core candidate |
| uvc_iso rawusb / nusb fork | out | out | out | out | out | out | out | out | Underruns; no upstream isochronous support |
| libusb enumeration only (usbvideo) | n·m done | n·m done | n·m done | y·m → I1 | n·m done | n·m done | n·m done | n·m done | Identity helper alongside MF/DS |
| Linux V4L2 + uvcvideo | n·i (tr) → LX6 (opt) | p·i → LX2 | y·i → LX1 | y·i → LX3 | n·i → LX4 | p·i → LX5 | y·i → LX5 | ? → LX5 | Likely Linux default |
| Linux libusb / libuvc (udev) | n·i (tr) | p·i → LX2 | y·i → LX1 | p·i → LX3 | y·i → LX4 | p·i → LX5 (libuvc controls) | y·i → LX5 | p·i → LX5 (libuvc controls) | Linux bandwidth path |
| Linux wrappers (PyAV v4l2, linuxpy, v4l2src, libcamera) | n·i (tr) | p·i → LX2 (opt) | y·i → LX1 | p·i → LX3 (opt) | n·i | out | p·i → LX1 | out | Thin layer over V4L2. Controls go through the V4L2 side channel tested in LX5 |
| macOS AVFoundation | n·i (tr) | ? → MX2 | ? → MX1 | p·i → MX3 | n·i → MX4 | ? → MX5 | p·i → MX1 | ? → MX5 | Run MX1 first; it gates the rest. G1 out: drift is a camera property, measured in S2 |
| macOS libusb / libuvc | n·i (tr) | p·i → MX6 → MX6b | p·i → MX6 | p·i → MX6 | p·i → MX6 → MX6b | p·i → MX6b | p·i → MX6b | p·i → MX6b | Every cell depends on whether the claim works (MX6). MX6b runs only if it does |
| macOS PyAV / avfvideosrc | n·i (tr) | ? → MX2 (opt) | n·i → MX1 (opt) | p·i (opt) | n·i | out | p·i | out | Expected to decode. Controls go through the AVFoundation/IOKit side channel tested in MX5 |
| nokhwa on Linux / macOS | out | out | out | out | out | out | out | out | No expected gain |
| **FSIN hardware trigger** | p·i → S4 | p·i → S4 | n/a | n/a | n/a | p·i → S4 (exposure under trigger) | p·i → S4 (format under trigger) | ? → S4 (does the OV9281 have AF?) | The only open-loop route to G1 "yes" |
| UVC still trigger / vendor XU | ? → S5 (opt, generic camera only) | ? → S5 (opt) | ? out | n/a | n/a | n/a | n/a | n/a | XUs out: none is documented as a trigger, and blind XU writes risk device state |
| Software phase steering (any API) | ? → S6 (opt; "partial" at most) | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Closed loop; needs a ground-truth reference running continuously |
| librealsense, libcamera, Qt, OBS, linuxpy, cv2_enumerate_cameras | out | out | out | cv2_enum → I3 | out | out | out | out | librealsense's technique is already in `timing/src/mf_uvc_timing.cpp`; linuxpy is covered by LX (opt); Qt and OBS are not candidates |

---

## 3. Ground-truth upgrade

### 3.1 Choice of instrument

| Instrument | What it measures | Per-frame resolution | Rolling shutter | Host-clock link | Effort | Role |
|---|---|---|---|---|---|---|
| Monitor flash (existing) | Offset-only timing of a source; relative exposure position | ~0.5 ms floor (measured, `timing/VERIFY_method.md`) | Mixed with display scan-out; the ground-truth offset moves 35 ms across image blocks | QPC (display) | Done | Baseline, and the cross-check in V5 |
| **ESP32 strobe** (`sync_rig/`, P0) | s0 (row-0 exposure start), E, line time L, phase between cameras | *est.* 10–30 µs (`sync_rig/README.md`) | Measured: band edges give s0, E and L | Serial ping. Repeatability *est.* 20–100 µs; absolute *est.* ±0.1–0.5 ms, with an unresolved ~0.27 ms serialization ambiguity (two offset hypotheses) | About $15 plus one bench evening | **Main instrument** for S, T and C1 |
| ESP32 LED bar (100 µs one-hot + Gray counter) | Exposure start and end at the bar's rows; coarse time | *est.* 15–30 µs | Bar laid along image rows | Same as the strobe | About $40 plus 1–2 evenings | Independent second method (V4); sharpness side check for C3; global-shutter cameras (S4) |
| **ESP32-S3 SOF lock (R2, later)** | ESP32 time ↔ USB frame number | *est.* ~1–10 µs to SOF | n/a | Settles the ping ambiguity; chains to the C930e SCR without QPC | About $15 plus a firmware port | Absolute G2 latency at the tens-of-µs level; validated in V7 |
| Stock RocSync | Exposure start and end per frame, after the fact | 1 ms LED step. The paper reports 1.34 ms RMSE against Azure Kinect hardware sync (5 runs, 0.38–1.94 ms) (*web*) | Ring spans many rows; the paper says its decoder assumes a global shutter (*web*) | None | PCB build (JLCPCB). Repo HEAD firmware and decoder expect a newer PCB that is not in the repo, so build from commit `5d82ddc` (read from a clone on 2026-10-30) | **Not the bench instrument** |

RocSync sources (*web*); details in [rocsync_review.md](rocsync_review.md):
- https://github.com/BAL-ROCS-BUT-COOL/RocSync (100-LED ring plus a 16-LED binary counter, `hw/` and `fw/` folders), licence MPL-2.0;
- paper: *Sensors* 26(3):1036 (2026), read at https://pmc.ncbi.nlm.nih.gov/articles/PMC12900090/ (the MDPI page returned 403). The paper says "TCXO"; the BOM part is a ±10 ppm crystal.

The `sync_rig/README.md` licence line was updated on 2026-10-30.

**Where RocSync fits:**
- **Do not build it instead of the ESP32 rig.**
  - Its 1 ms steps are coarser than the 0.5 ms floor we are trying to beat.
  - Its ring is a poor match for our ~30 ms rolling-shutter readout.
  - It has no host link, so absolute latency cannot be scored.
  - It has no strobe and no FSIN.
- **What to reuse:**
  - the one-hot "first and last lit LED" decoding, already adopted in the bar design;
  - the homography and `process_frame` structure. MPL-2.0 is file-level copyleft, so it can be combined with skellycam's AGPL.
- **Build it alongside only as a separate, later field-sync track,** for post-hoc ~1 ms alignment of mixed cameras (GoPros, phones). That is a skellycam feature question, not a gap in this research.
- **Optional:** the bar firmware can add a 1 ms-step mode for the same field use.

### 3.2 R0: bring-up (Dom, bench)

- **Hardware:**
  - the P0 strobe only (BOM in `sync_rig/README.md`): one AO3400A, a 1–3 W green LED, a resistor, capacitors, a polyfuse and a white card;
  - the logic analyzer and a BPW34 photodiode.
- **Procedure:**
  1. Flash `sync_rig/esp32_sync_rig/esp32_sync_rig.ino`. It compiles but has never been flashed.
  2. Wire the loopbacks on GPIO34, 35 and 39. Put 100 kΩ pull-downs on any that are not wired.
  3. Run `sync_rig/host/esp32_clock_sync.py` and confirm the PONG and `EV` lines.
- **Draft TODOs to close here:**
  - whether loading a timer on sync fires compare events;
  - the sync propagation delay;
  - how a forced output behaves when released;
  - whether `mcpwm_timer_set_period` halves the period in up/down mode;
  - capture-anchor rejection;
  - the LE-to-render deadline at 100 µs steps (bar only).
- **Time:** *est.* 3–5 h of Dom's time.

### 3.3 R1: validate the rig before using it

**Strobe timing for every camera run.** Never use an exact submultiple of the frame period. A 10 Hz strobe is exactly 1/3 of 30.00 fps, so the band would park on fixed rows.
- Use period = T_cam + 33 µs. This follows `sync_rig/README.md` deviation 4: integer µs, about 30 ppm granularity.
- Per-frame band runs use about 33,366 µs. Sparse runs use 3·T_cam + 33 µs.
- The band then walks every row in about 33 s.
- Rows the band never appears on are flagged as vertical blanking, and strobes that land there are dropped, not scored.
- The 25.7 fps generic camera beats against any strobe period, so it is handled the same way.

| ID | Check | Procedure | Pass (*proposed*) |
|---|---|---|---|
| V0 | **P0 camera check** (`sync_rig/README.md` bring-up step 5) | On Gerald, all three cameras at each planned exposure and gain set point (per camera, from C1's range read), 720p30 MJPEG, w = 50 µs, dark room, detuned strobe. Check: (1) band visible; (2) echo band in frame n+1 (temporal noise reduction); (3) L per camera; (4) the blanking-gap map; (5) band height MJPEG vs YUY2 in the same mode | Band SNR enough for the V3 decoder on every camera × set point. Otherwise raise w or LED current and record it. Any echo band is characterised before S/T scoring |
| V1 | Electrical and optical edges | Logic analyzer (24 MHz) on LE, STROBE, FSIN and SYNC against `EV` timestamps. BPW34 across 10 kΩ on a scope (or the analyzer threshold) for LED rise and fall | Captured edges match the analyzer to ±0.1 µs (relative). Period jitter < 1 µs. Optical rise and fall < 5 µs, no slow tail |
| V2 | Serial clock sync | `esp32_clock_sync.py` for 1 h after a 5 min warm-up, on Gerald. Record RTT_min stability, residual std and drift stability. Check that opening the port does not reset the board (`boot_id`) | Residual std ≤ 50 µs. Fitted ppm stable to ±0.5 ppm over 1 h. `asymmetry_bound_us` **and both offset hypotheses** recorded in every result |
| V3 | Decoder self-test | New `timing/rig/selftest`: render synthetic frames from known s0, E, L, w, gamma and MJPEG quality, including blanking gaps and an echo band, then decode them. Mirrors `selftest_flash_analyze.json` | Recovers s0 and E within 20 µs per frame and L within 0.1%. **Real data is not scored until this passes** |
| V4 | Internal consistency | Double strobe (Δt = 10 ms): L must agree across frames. If the bar is built, compare bar s0 with strobe s0 frame by frame | L coefficient of variation < 0.5%. Bar−strobe std ≤ 30 µs; this becomes the stated rig floor |
| V5 | Against the flash method, C922 | Back-to-back runs at −7 and −9 (both inside the C922's range) scoring C922 MF PTS with both methods. Check band-height E against 7.8 ms (at −7) and L against the measured 30.1–31.5 ms per frame height. Regress PTS−s0 on E | **Per run, the C922 PTS offset from the rig and from the flash agree within the flash floor (~0.5 ms).** The PTS−s0 vs E slope agrees with the flash-derived slope (−1.14·ΔE, finding 12, provisional) within its CI. E = 7.8 ms ± 3%. L in the measured range. **A lower std alone is not a pass** |
| V6 | Absolute-bias rule (not a run) | Until V7 passes, every G2 "absolute" result carries both ping hypotheses (they differ by ~0.27 ms) and `asymmetry_bound_us` | Absolute G2 cells stay **"partial, absolute bias estimated ±X"** until V7 passes. Offset-only and causal cells can be rated without V7 |
| V7 | **R2: ESP32-S3 SOF-lock validation** (when built) | Lock to USB SOF. Over 1 h, compare the SOF-locked ESP32↔host offset with both ping hypotheses. Where available, chain to the C930e SCR | SOF-lock repeatability ≤ 10 µs (*est.* target). One ping hypothesis falls within 50 µs of it and the other does not. Then absolute G2 can be rated "yes" |

**Global-shutter caveat** (needed for S4). A global-shutter sensor such as the OV9281 produces no row band: a frame is either lit or not. For those cameras, use the strobe-phase sweep (FSIN edge + d, with d swept in 50 µs steps) or the LED bar.

**New analysis code** goes in `timing/rig/`, following §F of the rig design ([../sync_rig/DESIGN.md](../sync_rig/DESIGN.md)):
- event-log parser;
- clock correlation;
- tone-curve calibration from a strobe-width sweep;
- band detector with a blanking-gap map;
- band-to-strobe assignment;
- per-frame solve;
- bar decoder;
- scorers.

It also needs adapters that read each harness's `frames.jsonl` and session JSON.

**Truth reference for G2.** Report both:
- **s0**, the row-0 exposure start;
- **t_light**, the mid-exposure of the image's centre row: t_light = s0 + (H/2)·L + E/2.

t_light is the closest single number to "when light hit the sensor" for a rolling-shutter frame, where the readout takes about 30 ms per frame.

---

## 4. Test specs

### Proposed rating thresholds

These map results to table cells. Dom to confirm.

**G1 (rated by controllability, never by a single-run snapshot)**
- **Yes:** the method aligns exposure start across cameras to ≤ 0.1 ms (1σ) **on every start, open loop**, and holds it ≥ 30 min without software correction.
- **Partial:** the method reproduces an alignment within a stated spread (≤ 1 ms) **on demand**, by any of:
  - ≥ 18/20 starts within that spread;
  - a start-mode Δφ distribution in S3 that rejects uniform and is concentrated within that spread;
  - a closed-loop method (S6) that holds the spread for a stated time. Software steering is capped at "partial (software steering, needs a ground-truth reference)".
- **No:** the phase is arbitrary across starts (Δφ consistent with uniform), **whatever a single run's spread happens to be**. A pair that is phase-stable but not controllable is "no", with a note.
- **Wording:** cells say "aligns exposure" (G1) or "measures offset" (G2), and never mix the two.

**G2**
- **Yes:** causal per-frame error ≤ 0.5 ms (1σ) against t_light, **and** an absolute bias known to ±0.5 ms. Absolute requires V7; until then, see V6.
- **Partial:** ≤ 2 ms, or needs a per-camera calibration, or the absolute bias is only estimated.
- **No:** an arrival grid or a synthetic timestamp.

**M1** (rated per camera × path)
- **Yes:** all of:
  - measured E (rig) is within max(0.1 ms, 5%) of the request in ≥ 99% of frames after the change takes effect;
  - the change takes effect within ≤ 5 frames;
  - readback agrees;
  - 3/3 runs on each camera.
- **Partial:** needs a workaround (for example re-applying after start), or works only on some cameras.
- Clamping of an out-of-range request is recorded as **clamp behaviour**, not as "not applied".

**M2**
- **Yes:** all of:
  - the requested mode is negotiated and read back;
  - the delivered frame dimensions match the request (from JPEG SOF0, or the decoded shape);
  - delivered fps is within 1% of the **camera's real rate**, defined as that camera's rate on MF native in the same mode;
  - there is no silent fallback.
- A camera that cannot reach the requested fps on any path is reported as a camera limitation, not a method failure.

**M3**
- **Yes:** all of:
  - with AF off and exposure, gain and WB locked, static-scene sharpness varies by ≤ 2% (CV) over 120 s;
  - no refocus after the target moves;
  - manual focus steps change sharpness around a single peak;
  - readback agrees.

**G4**
- **Yes:** the key survives a reboot and a same-port replug (plus a port move, for cameras with a serial), and the API opens exactly the camera with that key.

**G5**
- **Yes:** the app sets the alt setting or packet size, **and** N ≥ 3 cameras run at full rate on one USB 2.0 link for 10 min, **and** each camera's strict-decode failure rate is no worse than its own usbvideo baseline in the same mode. The generic camera's 1080p strict-decode failures are camera behaviour on every API.

### Rules for every test

- **Locking:** all camera access goes through `tools/camlock.py`.
- **Kiyo:** unplugged at D0 and kept unplugged for the whole campaign. Nothing in this plan needs it, and libusb enumeration (T2a, B1) would otherwise send it GET_DESCRIPTOR(config).
- **No programmatic device restarts. Ask Dom to replug.**
  - Do not use:
    - `naming/win_restart_test.py`;
    - `naming/win_restart_devices_admin.ps1`;
    - `timing/scripts/recover_restart_cameras.ps1`, `recover_restart_cameras2.ps1` or `recover_restart_cameras3.ps1`;
    - any build of `timing/src/devrestart.cpp` (judged by its name; check it before relying on it).
  - `libusb/winusb/install_winusb.ps1` line 91 (`pnputil /restart-device`) must be removed, or put behind a switch that defaults off, **before** B1 or B3 runs (see B1 prerequisites).
  - In `driver_swap/persistence_test.ps1` step 02, always answer `quit`, or delete the `keep` branch. "Keep" tests the vetoed path: it leaves DN_NEED_RESTART and causes MF_E_REBOOT_REQUIRED.
- **Before any UAC that touches a driver or the metadata registry value:**
  - LogiTune updater stopped and LogiTune agent quit from its tray icon;
  - Razer software closed.
- **UAC prompts:** every one is announced first. Any script that writes registry values or installs drivers first does a **dry check** that echoes its target instance IDs, resolved from a fresh `naming` dump. Dom confirms the IDs, and only then does the elevated step run.
- **Re-arrivals and reboots:**
  - I1 and every long run (S2, T1, X1, B2) record device `LastArrivalDate` before and after (as `naming_rerun_20261027` did), plus System-log boot and unexpected-shutdown events.
  - Steps with an unexplained re-arrival or reboot are discarded and re-run, not scored. The generic camera has re-arrived on its own before, and two reboots were never explained.
- **Data handling:**
  - Raw `.mjpeg` and frame dumps go under `C:/Users/Dom/Documents/skellycam-raw/<mirrored results path>/`.
  - Only these go in `results/`: `frames.jsonl`, per-strobe band tables, summary JSON and a few small sample frames.
  - Each run uses a fresh `--out-dir` and never overwrites a result folder that is already cited.
  - Check free disk space before S2, T1, B2 and X1. Budget *est.* ~10 GB per camera-hour of 720p30 MJPEG (to be confirmed from the first run's average frame size) and require twice the estimate free.
- **Outputs:**
  - Results are JSON with the standard fields, in `results/windows/Gerald/<test>/` (or `results/linux/<host>/…`, `results/macos/<host>/…`).
  - Reports are `.md` files under `research/`.
  - Build outputs and other rebuildable files are never committed.
- **Rig-run topology (S1, S2, T1, T3b, T4, C1 rig):**
  - Each camera on its own USB 2.0 link: separate root ports, or the generic camera on the second controller.
  - Record the topology with `bandwidth/win_usb_topology.py --pipes-only` before each run.
  - Pre-check: all cameras in the run deliver frames for 10 s before a long run starts. On every all-3 MF/DS/nokhwa cell so far, the generic camera was refused when it shared a hub with the C930e (0x800718CF).

### G1: synchronisation

**S1. Exposure phase between cameras (snapshot across starts)**
- **Question:** what is the exposure-start phase between free-running cameras, measured without display scan-out, and does it change from one start to the next?
- **Cameras:**
  - C922, C930e and the generic, via MF native (`timing/src/mf_uvc_timing.cpp`, one process per camera);
  - rig-run topology, with the 10 s pre-check;
  - the generic camera runs at 25.7 fps, so report its beat against the others, not a phase.
- **Hardware:**
  - rig P0, after V0–V5 have passed;
  - the card fills the full image height of each camera, at 0.3–0.5 m;
  - dark room; AE, AWB and anti-flicker off;
  - exposures from the per-camera set points.
- **Procedure:**
  - detuned strobe (T_cam + 33 µs), w = 50 µs;
  - 60 s run, repeated 5 times with a fresh stream start each time.
- **Analysis:** s0 per camera per strobe, then Δφ_AB = s0_A − s0_B (mod T), for each start.
- **Rating input:** this feeds the G1 controllability rating together with S3. A small Δφ in one run proves nothing.
- **Harness:** the existing capture tool plus the new `timing/rig/`. Unattended after setup, no admin. *est.* 1 h.

**S2. Phase walk and drift, ≥ 30 min**
- **Question:** what are the relative rates and the wander between camera pairs, and does any pair lock?
- **Setup:** as in S1, with a 60 min sparse detuned strobe, 2 runs. Log CPU temperature or room temperature if available. Check disk space first.
- **Analysis:**
  - linear fit of Δφ(t), giving **relative ppm for each pair**;
  - residual wander (Allan deviation).
- **Report explicitly which prior figure S2 confirms:**
  - the ppm-derived walk (+35 / −3.9 ppm, about one frame per ~14 min), or
  - the 10 s fps-derived "frame every ~20–25 s".
- After S2, only S2's measured walk goes in the README.
- **Reuse:** this data also gives T1's long-run causal PTS→QPC mapping.
- **Harness:** existing plus `timing/rig/`. Unattended. *est.* 2.5 h machine time.

**S3. Start alignment and topology**
- **Question:** does a simultaneous stream start narrow the phase on any API? Does sharing a hub or controller lock cameras to the USB SOF (0 ppm relative)?
- **Methods.** These are the only paths whose G1 cells become measured; every other row is transferred.
  - MF: `bandwidth/build/mf_multi_open.exe --stagger-ms 0|2500 --arrivals --save-dir`.
  - PyAV dshow: threads released by a barrier; new small script.
  - libuvc (patch 0001) during the WinUSB window (B1).
- **Procedure:** 20 start/stop cycles for each start mode (sequential, barrier, 2.5 s stagger), on each topology:
  - (a) same hub: **two cameras only, C922 + C930e**, on usbvideo (and libuvc in D2);
  - (b) different root ports on the same controller: three cameras, if the 10 s pre-check passes;
  - (c) different controllers (Gerald has two): three cameras.
  - Record the topology with `win_usb_topology.py --pipes-only` for each.
- **Analysis:**
  - Δφ distribution per start mode, with a KS test against uniform, and the count of starts within ±1 ms and ±0.1 ms;
  - relative ppm per topology.
  - **Derived, no new run:** how long a "restart until aligned" lottery stays useful, from S2's drift.
- **Decision:**
  - Uniform in every start mode: G1 "no (measured)" for MF, PyAV DS and libuvc.
  - A concentrated distribution meeting the G1 "partial" rule: "partial".
  - Any topology at 0 ± 1 ppm: report "phase-stable but uncontrolled", which is still "no" unless the start phase is also controllable.
- **Harness:** mostly existing; the PyAV barrier script is new. Unattended, but Dom moves cables for (a)/(b)/(c), *est.* 10 min. *est.* 3 h machine time.

**S4. FSIN hardware-trigger spike**
- **Question:** does a shared FSIN edge align exposures, and how tightly? This is the only open-loop test that can produce G1 "yes".
- **Hardware:**
  - ≥ 2 (ideally 4) InnoMaker U20CAM-9281M;
  - rig FSIN outputs: AO3400A or ULN2803A sinks to the opto inputs (+5 V, about 19 mA each);
  - the LED bar or the strobe-phase sweep (global shutter; see §3.3).
- **Procedure.** This replaces the swept-flash part of M0 in `../arduino_sync/PLAN.md`.
  - FSIN at 20.8 ms (48.08 Hz).
  - Sweep the strobe delay d from 0 to 25 ms in 50 µs steps, to map each camera's exposure window.
  - Lockout sweep with the FSIN period from 16 to 30 ms.
  - **Exposure under trigger (M1):** set manual exposure at two values. The swept window width must change by the expected amount. Record readback.
  - **Format under trigger (M2):**
    - resolution and pixel format stay as negotiated (SOF0 check);
    - delivered fps equals the pulse rate;
    - record readback of the negotiated type.
  - The remaining M0 items: the same-handle DSHOW `CT_FOCUS_AUTO` trigger write, the pulse-removal check, and buffers.
  - Note whether the OV9281 board has autofocus. This decides whether M3 applies. *expected:* fixed lens.
- **Analysis:**
  - FSIN→exposure skew per camera, and its spread across cameras;
  - frame-to-frame jitter;
  - lockout as a function of fps, exposure and resolution.
- **Pass (*proposed*):** skew spread ≤ 100 µs and jitter ≤ 50 µs give G1 "yes" for the FSIN row. Otherwise "partial", with the numbers.
- **Harness:**
  - the rig's FSIN timer exists in the draft;
  - the capture code is new (planned in arduino_sync M0).
- **Time:** attended wiring, *est.* 2–3 h of Dom's time; *est.* 1 day total.

**S5 (optional). UVC still-image trigger**
- **Only one camera has it.** In `results/windows/Gerald/naming_rerun_20261027/win_identity_dump/descriptors.json`, only the generic 4C4A:4A55 has `bStillCaptureMethod=2` and `bTriggerSupport=1`. The C922 and C930e show 0/0.
- **Question:** does a still trigger start an exposure, or does it just pick the next frame?
- **Procedure:**
  - DS `IAMVideoControl::SetMode(VideoControlFlag_Trigger)` on the still pin, under usbvideo, with no driver swap;
  - 50 triggers while the rig strobes;
  - measure the latency from the trigger write to the still frame's s0.
- **Expected:** latency uniform over 0–T (the sensor is free-running), so "no".
- **Harness:** new. Unattended, *est.* 2 h. Run it only if time allows.
- **Vendor XUs:** out of scope. None is documented as a trigger, and blind writes risk leaving the device in a bad state.

**S6 (optional). Closed-loop software phase steering**
- **Question:** can a USB-only app *steer* exposure phase without FSIN?
- **Cameras:** C922 + C930e, with the rig running as the reference.
- **Procedure:**
  1. Restart until aligned: stop and start until |Δφ| ≤ target, and count the retries.
  2. Slip the phase deliberately: a temporary dwFrameInterval change (or an exposure change, where it affects frame timing), then return to nominal.
  3. Re-correct whenever drift exceeds the target.
- **Measure:**
  - the spread that can be achieved;
  - how long it holds, against S2's drift;
  - the cost in dropped frames and retries.
- **Rating cap:** "partial (software steering, needs a ground-truth reference)". FSIN stays the only open-loop "yes".
- If S6 is not run, the matrix carries "? out: closed-loop steering not tested".

### G2: timestamp accuracy

**T1. Score every timestamp source against the rig**

**Sources and methods:**

| Method | Sources |
|---|---|
| OpenCV DSHOW | Host time after `read()` (baseline) |
| MF native | OS sample time, host arrival, C922 UVC PTS, C930e SCR |
| MF NV12 (opt) | Parsed PTS |
| PyAV dshow | Default pts, and graph clock (`use_video_device_timestamps=0`); covers the pyav-dshow-graphclock run that was missed |
| libuvc / py-libusb1 / uvc_iso (WinUSB window) | SCR→QPC, back-dated first payload, raw arrival |
| mfvideosrc, nokhwa (opt) | Their PTS / capture_timestamp |

- **Setup:** rig-run topology, the 10 s pre-check and a disk check. Rig clock sync option 2 (serial ping).
- **Procedure:**
  - C922 and C930e, 60 s × 5 runs at three **per-camera, per-path in-range exposures**, read first from IAMCameraControl (DS and MF) or UVC GET_MIN/MAX/RES (libusb);
  - for example: C922 −9, −7, −5 if in range; C930e DS −5, −4, −3;
  - the generic camera is in T4.
- **Analysis**, per source:
  1. offset-only std and MAD (comparable with today's tables);
  2. causal online mapping (sliding window), and the same over S2's 60 min data;
  3. absolute latency to t_light and to s0, under **both** ping hypotheses, rated per V6;
  4. PTS−s0 regressed on E (where PTS sits within the exposure);
  5. whether the C922's ±0.27 ms PTS alternation is resolved.
- Each cell is worded "measures offset to ±X", never "aligns".
- **Pass:** rate each source with the G2 thresholds.
- **Harness:** existing capture tools plus `timing/rig/`; PyAV logging via `frames.jsonl` from `mjpeg/run_one.py`. Unattended.
- **Time:** *est.* 1 night for MF and DS, plus a slot in the WinUSB window for libusb.

**T2. libusb SCR→QPC over long runs (REPORT further investigation 1)**
- **Stage a (now; no WinUSB, no rig; the Kiyo already unplugged):**
  - run `libusb/uvc_capture_test.c --frame-qpc-only 60` with the IOCTL re-sampled or re-anchored every ≤ 2 s;
  - this needs a harness change: periodic `START_TRACKING`, or re-anchoring;
  - quantify the residual of the re-anchored mapping.
- **Stage b (WinUSB window):** C930e (and C922 if B1 succeeds), `--frame-qpc --controls-after-start`, 60 s × 5, scored against the rig.
- **Pass:** a causal SCR→QPC error within the G2 "yes" band over 60 s, or the residual is reported.
- **Harness:** existing, plus the re-anchor patch. Unattended.

**T3. C930e period modes and exposure (REPORT further investigation 6, PROGRESS §E)**
- **Stage a (offline, now):**
  - re-analyse `flash_run1_repositioned`, where the C930e exposure was swept from 2^-8 to 2^-5 s, with `timing/scripts/flash_exposure_scan.py`;
  - the raw data is in `C:/Users/Dom/Documents/skellycam-raw/`;
  - if the conclusions hold across that range, close PROGRESS §E.
- **Stage b (rig):**
  - 10 × 60 s runs, with in-range exposure set before start vs re-applied +0.5 s after start;
  - LogiTune updater stopped (D3b "off" legs) vs running (after it is restored);
  - log the PTS period mode (998,400 vs ~997,230 ticks per frame) and the band-height E for every frame.
- **Question:** does the period mode follow the exposure state? Does the C930e's PTS or SCR become usable?
- **Harness:** existing (`timing/src/mf_uvc_timing.cpp` needs a re-apply option) plus `timing/rig/`.

**T4. Generic camera timing**
- **Procedure:**
  1. Set `MetadataBufferSizeInKB0` on the generic camera's MI_00 interface with `timing/scripts/enable_uvc_metadata.ps1 -Instances <generic MI_00 id> -NoRestart`.
     - **Always pass `-Instances`.** The script's default list starts with the Kiyo (`USB\VID_1532&PID_0E05…`) and holds stale C930e IDs.
     - The ID comes from a fresh naming dump. It is echoed in a dry check before the announced UAC.
     - Then Dom replugs.
  2. Check whether the camera fills PTS/SCR at all.
  3. Score MF OS time, arrival, and PTS if present, against the rig, in dark and bright scenes (the brighter-scene item from the overnight leftovers).
     - Exposures are in-range for the generic camera: −7, −6, −5. −7 is its range minimum.
- **Admin:** UAC plus a replug, batched with B1 step 9 (D2, UAC #5).
- **Time:** *est.* 1.5 h unattended after setup.

**T5. Can DS/KS clients read UVC PTS/SCR? (the gap from `docs/capture_backends_review.md`)**
- **Question:** can the PyAV/DS fallback ever get the camera's own timestamp, or is it limited to arrival time?
- **Procedure:** extend `timing/src/dshow_open_probe.cpp` on the C922, with `MetadataBufferSizeInKB0` already set on its current key:
  - (a) query `IMediaSample2` properties and any attached sample metadata on capture-pin samples;
  - (b) request KS stream metadata on the capture pin through `IKsPropertySet`/`IKsControl` (KSPROPERTY camera-metadata items);
  - (c) compare any values found against MF's PTS for the same frames.
- **Outcome:**
  - If PTS is reachable: score it in T1 and re-rate the PyAV DS G2 cell.
  - If not: the report states that **the DS fallback is limited to G2 arrival time**, with the reason (which interfaces were checked and what each returned).
- **Time:** feasibility in step 1 (no rig, no admin), *est.* 3 h. Scoring, if possible, in D3b.

### G3: native MJPEG

Windows is done for the three in-scope cameras.
- **H1 (opt):** for nokhwa and mfvideosrc, check the JPEG header SHA-1 against MF and run a strict libjpeg-turbo decode. Run it only if either becomes the shipped wrapper. Uses `bandwidth/verify/strict_jpeg_check.py` and the existing header-hash code in `mjpeg/`. Unattended, 30 min.
- **Kiyo Pro:** out of scope (faulty device). Re-include it only if a working replacement is bought.
- **Linux and macOS:** LX1 and MX1.

### G4: unique camera IDs

**I1. Controlled stability (REPORT further investigation 5)**
- **Procedure** (`naming/win_stability_workflow.ps1` is drafted; check that it calls none of the forbidden restart scripts before using it):
  1. Baseline dump.
  2. Reboot (an OS restart started by Dom, not a device restart), then dump.
  3. Same-port replug of each camera, then dump.
  4. Move the C922 and the generic camera to other ports, including the other controller, then dump.
- **Record at every step:** `LastArrivalDate` and boot events. Discard and repeat any step with an unexplained re-arrival.
- **Analysis:** stability of the `camera_identity.py` key, and of the derived MF symlink, DS DevicePath and libusb port chain.
- **Expected:**
  - C922 (has a serial): the key is stable in every step;
  - serial-less cameras: stable across reboot and same-port replug, but changed by a port move (by design).
- **Pass:** the G4 thresholds.
- **Time:** attended, *est.* 45 min of Dom's time.

**I2. Identical-camera pair**
- **Hardware:** two units of one serial-less model (buy a second C930e; see §5).
- **Procedure:**
  - plug both in and confirm they get distinct keys;
  - open each by key on each candidate API;
  - Dom covers one lens at a time;
  - swap their ports and confirm the keys swap.
- **Harness:** new `naming/open_by_key_check.py`, which detects which stream goes dark. Attended, *est.* 20 min.

**I3. Open-by-key on each API**
- **Question:** given a key, does each API's handle open exactly that physical camera?
- **Paths:**
  - MF symlink;
  - PyAV `@device_pnp_…`;
  - libusb port chain;
  - `cv2.VideoCapture(index)` via cv2_enumerate_cameras;
  - optionally nokhwa `CameraIndex::String` and mfvideosrc `device-path`.
- **Procedure:** the same cover-the-lens check, repeated after an index reorder (replug).
- **Harness:** new script, shared with I2. Attended, *est.* 20 min.

### G5: USB bandwidth

**B1. WinUSB phase 3: C922 and generic (PROGRESS §B, REPORT further investigation 2)**

**Hard prerequisites** (all must be done before UAC #2):
- (a) `libusb/winusb/install_winusb.ps1`: remove the `pnputil /restart-device` call at line 91, or put it behind a `-RestartDevice` switch that defaults off. Its replacement is "Dom replugs".
- (b) `rollback_winusb.ps1`: same check. It must contain no device restart.
- (c) `driver_swap/persistence_test.ps1` step 02: delete the `keep` branch, or always answer `quit`.
- (d) `selftest_winusb_common.ps1` passes.
- (e) LogiTune updater stopped (D3a, UAC #1), LogiTune agent quit from its tray icon, Razer software closed. All three are checked again immediately before the UAC.
- (f) Kiyo unplugged.

**Procedure:**
1. Write `libusb/phase3_windows.ps1` (missing). Results go in `results/windows/Gerald/phase3_<camera>_<utc>/`, the PROGRESS §B convention.
2. Dry check: echo the target MI_00 instance IDs from a fresh naming dump.
3. **UAC #2 (announced):** swap both cameras. Then Dom replugs.
4. Per camera:
   - libuvc list, probe and forced-alt sweep (the generic camera has a single alt, 3069 B, so its sweep degenerates);
   - the py-libusb1 streamer;
   - Rust uvc_iso;
   - strict decode;
   - `bandwidth/win_usb_topology.py --pipes-only`.
5. In the same window, run the libusb legs of T1, T2b, C1, C2, C3 and S3, plus B2 and B4.
   - Dom's attended moments in this window: the C3 target move and replug for the libusb legs, and the S3 cable moves.
6. Patched pyuvc: **out**. Its timestamps are 103–129 ms wrong, and the C930e has already shown bandwidth.
7. B3 persistence checks, while on WinUSB.
8. **UAC #4:** rollback. Then Dom replugs.
9. **UAC #5:** metadata re-set.
   - Run `enable_uvc_metadata.ps1 -Instances <new C922 MI_00>,<new C930e MI_00>,<generic MI_00> -NoRestart`, after a dry check that echoes the IDs.
   - This also covers T4.
   - Then Dom replugs.

**Analysis:** `libusb/phase3_analyze.py`.

**Time:** *est.* 1 day of machine time. Dom is needed about 6 times for about 5 min each.

**B2. Three or more cameras on one USB 2.0 link at forced alts**
- **Cameras:**
  - the generic camera's only alt reserves about 62% of the link, so it cannot be squeezed;
  - N ≥ 3 therefore needs multi-alt cameras: the C922 plus two C930e (one more to buy, which also serves I2);
  - also test the generic camera together with one forced-alt camera.
- **Procedure:**
  - 720p30 and 1080p30, a high-detail scene, AF pinned;
  - 10 min per configuration, with a disk check first;
  - strict decode **against each camera's usbvideo baseline**, pipe snapshot, CPU.
- **Pass:** the G5 threshold. Report the maximum N per link against the model's 3–6.
- **Time:** during the B1 window, *est.* 3 h machine time.

**B3. Driver-swap strategy and persistence (PROGRESS §C)**
- **Desk research:**
  - UsbDk: isochronous support through the libusb usbdk backend (*expected:* yes, unverified);
  - libusbK;
  - an INF matching by hardware ID vs a per-instance install.
- **Hardware:** `driver_swap/persistence_test.ps1` (partial), with the prerequisites (a) and (c) from B1 applied and step 02 answered `quit`.
  - Does WinUSB survive an OS reboot? Does it survive a port move done by Dom?
  - Kill the app mid-stream and check what state it leaves behind.
  - After a reboot, quit the LogiTune agent again before continuing. The updater's start type was set to Manual in UAC #1.
- **Decision output:** install once, swap per session, or a helper service. Write it up in `driver_swap/REPORT.md`.
- **Admin:** a UAC prompt per install, within D2 (UAC #3). *est.* 0.5 day of research plus 30 min attended.

**B4. Integrity under load**
- **Procedure:**
  - py-libusb1 streamer and uvc_iso;
  - transfers {2, 4, 8, 16} × packets {8, 32} × CPU {idle, stress};
  - strict decode and error-bit handling.
- **Pass:** 0 corrupt frames emitted at the default settings, under stress.
- **Time:** in the B1 window, unattended, *est.* 2 h.

### M1–M3: the control matrix

Every candidate stack is tested on each camera that has the control:
- exposure on all three cameras;
- focus on the C922 and C930e (the generic camera has no focus control).

**M1 is rated per camera × path.**

| Stack | Exposure path | Focus path | Harness |
|---|---|---|---|
| MF native | IAMCameraControl queried **from the IMFMediaSource** (not the DS filter) | Same, `CameraControl_Focus` | `timing/src/mf_uvc_timing.cpp`; add `--focus-manual N`, `--reapply-after-ms`, `--toggle-every-s`, and a range dump |
| DS side channel during a PyAV stream | IAMCameraControl / IKsControl on the DS filter | Same | `mjpeg/msmf/mf_mjpeg_capture.cpp --controls-only --via-dshow`; add focus *set* (it currently passes set=false); new concurrent-run wrapper |
| OpenCV DSHOW (baseline) | `CAP_PROP_AUTO_EXPOSURE` / `CAP_PROP_EXPOSURE` | `CAP_PROP_AUTOFOCUS` / `CAP_PROP_FOCUS` | `mjpeg/run_one.py` plus new options |
| libuvc (WinUSB) | `uvc_set_ae_mode` / `uvc_set_exposure_abs` with `--controls-after-start` | `uvc_set_focus_auto`, plus **absolute focus (never set so far)** | `libusb/uvc_capture_test.c`, `bandwidth/libuvc_forced_alt/uvc_probe_quality.c` |
| py-libusb1 / uvc_iso | SET_CUR; add an after-start re-apply | Add CT_FOCUS_AUTO / CT_FOCUS_ABSOLUTE | `libusb/py_libusb1/uvc_libusb1_stream.py`, `rust/uvc_iso` |
| V4L2 / libuvc on Linux / AVFoundation | LX5 / MX5 | LX5 / MX5 | Drafts; add focus |

**C1. Exposure**
- **Range read first:** for each camera × path, read IAMCameraControl GetRange (DS and MF) or UVC GET_MIN/MAX/RES/DEF (libusb).
- **Set points:** pick three in-range values per camera × path. For example:
  - C930e DS: −5, −4, −3;
  - generic: −7, −6, −5;
  - C922: −9, −7, −5 if in range.
- **Out-of-range set:** add one deliberately out-of-range set per camera × path, and record the clamp behaviour and readback.
- **Timing of the sets:**
  - (a) before stream start / COMMIT;
  - (b) +0.5 s and +2 s after the first frame;
  - (c) toggle between the lowest and highest in-range set points every 5 s.
- AE priority 0.
- **Factors:** LogiTune running vs stopped (C930e and C922).
  - The pre-rig pass in step 1 runs with LogiTune as found.
  - The rig "off" legs run in D3b.
  - The "on" legs run after the updater is restored (UAC #6).
- **Truth:**
  - *Pre-rig pass (now):* linearized luma ratio at fixed gain, plus the flash step-rise (`timing/scripts/run_flash_test.ps1`, `flash_step_response.py`; libuvc showed about 12 ms vs about 32 ms). **This pass can rate only "no" or "partial (pending rig)".** It cannot reach the max(0.1 ms, 5%) precision.
  - *Rig pass:* band-height E for every frame.
- **Record:** readback after every set; the C930e PTS period mode.
- **Pass:** the M1 threshold for each stack and camera.
- **Time:** unattended. *est.* 3 h pre-rig, plus 3 h on the rig, plus the libusb rows in the B1 window.

**C2. Format**
- **Modes:** {640×480, 1280×720, 1920×1080} × {15, 30, 60 where offered} × {MJPG, YUY2}, on each stack. Includes C922 720p60.
- **Record:**
  - the negotiated type readback;
  - **the width and height of every frame** (JPEG SOF0 for MJPG, buffer size or decoded shape for YUY2), compared with the request;
  - delivered fps over 20 s, compared with the same camera's MF-native rate in the same mode;
  - `silent_format_fallback`;
  - strict decode, against the same camera's usbvideo baseline.
- **Harness changes:** the libusb harnesses hard-code MJPEG, so add `--format yuy2`.
- **Rig (optional):** P1 line time L for the modes skellycam will actually use.
- **Time:** unattended, *est.* 4 h.

**C3. Focus**
- **Target:** an A4 Siemens star on matte paper at about 1 m.
- **Locked first:** exposure, gain and WB are locked (manual, at fixed values) before any sharpness measurement. Otherwise AE or AWB changes confound the metric.
- **Metric:** a new `tools/sharpness.py`: normalised Laplacian variance in the star ROI, plus JPEG frame size. AF previously changed frame size by up to 50%.
- **Steps:**
  1. AF off. Sweep focus_absolute from minimum to maximum in 10 steps, 3 s each, with readback. *Unattended.*
  2. Hold a fixed focus for 120 s on a static scene. Then Dom moves the target between 0.5 and 1.5 m to provoke AF. There should be no refocus, and the readback should stay constant. *Attended: D0 for the usbvideo legs, D2 for the libusb legs.*
  3. Set the focus before vs after stream start. *Unattended.*
  4. Check persistence:
     - across a stream restart (*unattended*);
     - across a replug (*attended: D0 / D2*).
  5. LogiTune running vs stopped.
- **Rig side check (once the bar is built):** LED spot size as a per-frame sharpness value.
- **Pass:** the M3 threshold.
- **Time:** *est.* 2 h pre-rig, plus about 10 min of Dom's time in each of D0 and D2.

### Other Windows items folded in

**X1. MF vs DS soak (REPORT further investigation 10)**
- Both stacks, one process per camera, rig-run topology, for ≥ 1 h, with one mid-stream replug by Dom.
- Log every error, stall and re-arrival.
- This decides the order of primary vs fallback.
- Attended for the replug only.

**X2. Frame Server CPU (PROGRESS: "Still needs a human")**
- **Procedure:**
  - inside the elevated session opened by UAC #1 (D3a), sample per-process CPU for the FrameServer svchost and the capture processes;
  - optionally record an ETW trace (CPU sampling plus the MF/KS providers);
  - cases: 1 camera, then 3 cameras, streaming (i) through MF native and (ii) through PyAV DS;
  - 5 min per case, with CPU frequency logged.
- **Output:** total CPU cost per stack, including Frame Server. MF's measured 0.7–2.2% currently excludes it.
- **Scope:** CPU for nokhwa, GStreamer, SDL3 and openpnp is **out of scope**. They are rejected or optional wrappers; if one becomes the shipped wrapper, fold it into H1.

**U1. Overnight leftovers that can run unattended now**
- `verify_grid_phase.py`;
- CPU repeat runs with CPU frequency logged;
- MF-NV12 and DSHOW-raw at 1080p, with 3 cameras;
- C930e + generic stagger with `--arrivals`;
- C922 1080p@5 repeats;
- JPEG marker-layout check;
- **offline alt-sweep reproductions**, from existing raw data;
- **the libuvc example** (the Kiyo is already unplugged, so the condition is met);
- Docker libuvc build (LX prep);
- the non-Kiyo legs of `kiyo_lens`.

C922 720p60 is covered in C2. Unpatched rawusb is dropped (out).

### Linux session (LX)

A separate machine session.
- *Preferred:* an Ubuntu 24.04 live USB with persistence, booted on Gerald. The xHCI hardware is then the same, and Windows is untouched.
- Otherwise any bare-metal Intel-xHCI PC.
- Not WSL.

The same data-handling and re-arrival rules apply, with the raw-data path on the Linux host.

| ID | Test | Harness | Notes |
|---|---|---|---|
| LX1 | V4L2 mmap MJPEG passthrough; PyAV v4l2 bytes compared with it; strict decode; SOF0 dimensions | `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py`, `run_linux_mjpeg.sh` | G3, M2 |
| LX2 | Buffer timestamp granularity; metadata node PTS/SCR; `hwtimestamps=1` (root); scored against the rig with a CLOCK_MONOTONIC ping (V2 re-run on Linux) | `timing/linux/v4l2_uvc_timing.py`, `run_linux_timing.sh`, `timing/rig/` | G2 |
| LX3 | Identity: by-path, sysfs serial, the `camera_identity` key over reboot, replug and port move; libusb bus → sysfs mapping | `naming/linux_identity.py`, `naming/linux_stability_workflow.sh` | G4 |
| LX4 | `quirks=128` with MJPEG vs YUYV (settles finding 21); libuvc via a udev rule with a forced alt; 3 cameras per link | `bandwidth/linux/uvc_bw_probe.py compare`, `libusb/linux/run_libuvc_linux.sh`, `70-skellycam-uvc.rules` | G5 (sudo) |
| LX5 | Control matrix: exposure before vs after STREAMON (in-range set points plus one out-of-range set), readback plus rig; focus_automatic_continuous / focus_absolute plus the Siemens star (exposure, gain and WB locked); formats. **Two paths: V4L2 controls, and libuvc controls via the udev rule** | Drafts; **add focus** to `v4l2_uvc_timing.py`; **add libuvc control sets** (exposure after start, focus auto/absolute) to `run_libuvc_linux.sh` | M1–M3 for the V4L2 and Linux libusb rows |
| LX6 (opt) | S2 drift under Linux: checks whether the host stack changes anything | `timing/rig/` | G1 (V4L2 row only) |

**Dom's time:** about 1 h (boot, replugs, port moves); the rest is unattended. *est.* 1–2 days total.

### macOS session (MX)

Needs an Apple Silicon Mac on macOS 14 or later and a USB-A hub. Plan for TCC camera-permission prompts, and for `sudo` in MX6.

| ID | Test | Harness |
|---|---|---|
| MX1 | Empty/nil `videoSettings`: are MJPEG bytes reachable at all? Also PyAV avfoundation `vcodec=mjpeg`. **This gates the rest.** | `mjpeg/drafts/macos/avf_mjpeg_probe.py`, `run_macos_mjpeg.sh` |
| MX2 | CMSampleBuffer PTS origin and accuracy against the rig (ping in mach time). Optionally the same for PyAV avfoundation and avfvideosrc PTS | `timing/macos/avf_timing.py`, `run_macos_timing.sh` |
| MX3 | uniqueID / ioreg serial; stability over replug and port move | `naming/macos_identity.py`, `macos_stability_workflow.sh` |
| MX4 | Default behaviour with N cameras on one hub | `bandwidth/macos/avf_multi_open.py` |
| MX5 | Exposure: Locked vs Custom; focus; a UVC control-request side channel through IOKit (new). This side channel also serves the PyAV/avfvideosrc rows | Draft plus a new IOKit probe |
| MX6 | libusb claim, as a user and as root | `libusb/macos/run_libusb_macos.sh` |
| MX6b | **Only if MX6's claim succeeds:** libuvc controls (exposure after start, focus), forced-alt sweep, PTS/SCR scored against the rig | Extend `run_libusb_macos.sh` |

*est.* 1 day; Dom's time 1–2 h.

---

## 5. Equipment and Dom's time

### Shopping list

| Item | Qty | ~Cost (USD) | For |
|---|---|---|---|
| ESP32-WROOM-32 DevKitC | 1 | have | R0 |
| Strobe parts: 1–3 W green LED on a star, AO3400A ×4, 1.8 Ω 3 W resistor, 2200 µF + 10 µF, polyfuses, pull-downs, 5 V 3 A supply | — | ~15–25 | R0, all S/T/C1 |
| 8-channel 24 MHz USB logic analyzer | 1 | ~10–15 | V1 |
| BPW34 photodiode + 10 kΩ (scope if available) | 1 | ~2 | V1 |
| A2 matte white foam board, black flock or tape | — | ~10 | Strobe card |
| Siemens star printout (A4 matte) | 1 | ~0 | C3 |
| Second **C930e** (serial-less, multi-alt; used is fine) | 1–2 | price not checked | I2 identical pair, B2 N ≥ 3 |
| LED bar parts: 8 × 16-channel CC drivers, ~130 red LEDs, perfboard | — | ~40 | V4, C3 side check, S4 (optional phase) |
| ESP32-S3-DevKitC-1 | 1 | ~10–15 | R2 SOF lock, V7, absolute G2 |
| InnoMaker U20CAM-9281M | 2–4 | price not checked | S4 |
| Ubuntu 24.04 live USB stick (≥ 32 GB) | 1 | ~10 | LX |
| External or spare disk space for raw captures (*est.* ≥ 200 GB free) | — | have / check | S2, T1, B2, X1 raw data |
| Access to a Mac | — | — | MX |

**Not recommended for this plan:** building stock RocSync. It belongs to a later field-sync track, if wanted.

### Dom's attended sessions (batched)

UAC prompts are numbered in the order they occur.

| Session | When | Dom's time (*est.*) | Includes |
|---|---|---|---|
| D0 | Now | 25 min | **Unplug the Kiyo for the whole campaign.** Place the Siemens star. C3 step 2 target move and step 4 replug (usbvideo legs) |
| D1 | Bench | 3–5 h | R0 build, flash, logic-analyzer and photodiode checks (V1); V3 and V4 on the bench |
| D3a | Rig on Gerald, **before D2** | 1–1.5 h | Mount the card, strobe and cameras on separate links; V0, V2, V5 (V6 applied). **UAC #1 (announced): stop `LogiTuneUpdaterService` and set its start type to Manual, then run X2 in the same elevated session.** Quit the LogiTune agent from its tray; close Razer software |
| D2 | WinUSB day | ~6 × 5 min across the day | Check that the B1 prerequisites (a)–(f) are done. UAC #2 swap → replug. C3 libusb target move and replug. S3 cable moves for the libusb legs. UAC #3 B3 persistence install(s) (answer `quit`), OS reboot and port move (quit the agent again after the reboot). UAC #4 rollback → replug. UAC #5 metadata re-set (dry check first) on the new C922/C930e keys plus the generic camera → replug |
| D3b | Long rig runs | 20 min | S3 cable moves for the MF/PyAV legs. After the "off" legs of T3b, C1 and C3: **UAC #6 restore the LogiTune updater** (start type back to Automatic, start it; or Dom uses services.msc) and restart the agent; then the "on" legs run |
| D4 | Naming and soak | 1–1.5 h | I1 reboot, replug and port moves; I2 and I3 cover-the-lens checks; X1 mid-stream replug |
| D5 | Linux | ~1 h | Boot the live USB; replugs and port moves |
| D6 | macOS | 1–2 h | Permissions, sudo, replugs |
| D7 | FSIN | 2–3 h | Wire the OV9281 FSIN inputs |

**Total for Windows:** about 8–10 h of Dom's time, most of it the bench build.

---

## 6. Order of execution

| Step | Tests | Depends on | Attended? |
|---|---|---|---|
| 0 | **D0:** unplug the Kiyo; place the star | — | 25 min |
| 1 | U1, T3a (offline), T2a (IOCTL re-anchor), T5 feasibility, C2, C1 pre-rig pass (can rate only "no"/"partial (pending rig)"), C3 usbvideo legs | Step 0; harness edits for focus set, re-apply and the range dump | Mostly unattended |
| 2 | R0, then V1, V3 and V4 on the bench | Parts; D1 | Bench |
| 3 | **D3a:** rig mounted on Gerald; V0, V2, V5 (V6 rule in force); UAC #1 stops the LogiTune updater; X2 | Step 2 passed; MF metadata still set on the current C922/C930e keys | ~1–1.5 h |
| 4 | **D2 WinUSB window:** B1 (prerequisites (a)–(f)), B2, B4, B3 persistence, plus the libusb legs of T1, T2b, C1 (rig), C2, C3 and S3 (libuvc); then rollback and the metadata re-set (UAC #2–#5). **The LogiTune updater stays stopped throughout** | Step 3 (rig validated, updater stopped); second C930e for B2 | Short visits |
| 5 | **D3b:** S1, S2, S3 (MF and PyAV legs), T1 (MF / DS / OpenCV / PyAV), T4, T5 scoring (if feasible), and the "off" legs of T3b, C1 (rig) and C3. Then UAC #6 restores the updater, then the "on" legs of T3b, C1 and C3 | Step 4 done, so instance IDs and metadata keys are final; disk check | Setup, then 1–2 nights unattended |
| 6 | **D4:** I1, I2, I3, X1 | Second C930e; after step 5, so a reboot does not interrupt rig runs | Attended |
| 7 | Optional: H1, S5, S6, the mfvideosrc/nokhwa rows of C1/C3/T1 | Only if those wrappers or routes are still candidates | Unattended (S6 needs the rig) |
| 8 | LX session, then MX session (MX6b only if MX6 succeeds) | Rig is portable; re-run V2 on each OS; drafts updated with focus and libuvc controls | D5, D6 |
| 9 | S4 FSIN; R2 + V7 SOF lock whenever the ESP32-S3 is built | OV9281s; rig FSIN outputs validated in V1 | D7 |
| 10 | Update the REPORT and README tables, write the missing report sections, regenerate this gap table | Each step's results | — |

**Ordering notes:**
- **Rig before WinUSB.** D3a mounts and validates the rig on Gerald and stops the LogiTune updater **before** D2. Two reasons:
  - the libusb legs in D2 are scored on the rig;
  - the stopped updater (and quitting the agent and Razer) is a prerequisite for the WinUSB install. Without it, a vetoed restart leaves DN_NEED_RESTART.
- **WinUSB before the long MF runs.** The rollback creates new instance IDs that need the metadata registry value set again. Doing D2 first means that UAC prompt and replug happen once (UAC #5), and the same prompt covers T4's generic camera.
- **LogiTune order.** The updater stays stopped from UAC #1 through D2 and through the "off" legs in D3b. It is restored (UAC #6) only once those are done, and the "on" legs of T3b, C1 and C3 run last.
- **Phase walk in the README.** Until S2 has run, step 10 (and any interim README edit) cites only the ppm-derived phase walk (about one frame per ~14 min, labelled *derived*). It never cites the 10 s fps-derived "frame every ~20–25 s".
- **Must-haves first.** C3 and the pre-rig C1 pass come first on purpose. They need no new hardware and give early evidence on the two must-haves that most affect the stack choice. M1 "yes" still waits for the rig pass.