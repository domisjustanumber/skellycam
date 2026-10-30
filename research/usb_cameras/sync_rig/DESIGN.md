# ESP32 timing and sync test rig: design

Scope: this design replaces or adds to the monitor-flash ground truth (`timing/VERIFY_method.md`). It uses a classic ESP32-WROOM-32 DevKit with Arduino-ESP32 core 3.x, which runs on ESP-IDF 5.x, so the IDF drivers (`mcpwm_prelude.h`, `spi_master.h`, `gptimer.h`) can be called from a sketch. Accuracy figures below are **estimates** unless they cite a measured repo result. Nothing here has been built or measured.

Repo files read: `REPORT.md` (findings 7–15, further investigation 1/6/7), `timing/VERIFY_method.md`, `results/windows/Gerald/RERUN_20261027.md` (goal 2 table), `../arduino_sync/PLAN.md` (§1, §4, §8), `../arduino_sync/REPORT.md` (finding 8).

---

## 0. Why the current method stops at ~0.5 ms, and what the rig changes

From `timing/VERIFY_method.md`:
- The ground truth (GT) is a display step at vblank. The time inside an exposure E = 7.8 ms is recovered from partial brightness f through a gamma model. The model error swings by **+180 to −1000 µs across f**, with opposite signs for rising and falling edges. Even a deliberately circular PTS fit leaves 0.49–0.59 ms. So **~0.5 ms is the method floor.**
- The GT offset varies by **35 ms across image blocks**, from rolling shutter plus display scan-out, and the two cannot be separated. Cross-camera "agreement" was therefore a property of where the ROIs sat (§6).
- The C930e exposure was assumed, not confirmed (REPORT finding 11).

The rig fixes these as follows:
1. **Interpolate brightness only inside a short window.** Any brightness interpolation happens inside a 50–100 µs window instead of inside E, so the same model error shrinks by roughly Δ/E (arithmetic in §E).
2. **No scan-out.** An LED or strobe is lit everywhere at the same instant. Rolling shutter becomes a measured, per-camera line time L instead of an unknown mixed with scan-out.
3. **Measure exposure every frame.** E and the exposure start are measured per frame, so M1 (exposure control) is verified directly instead of assumed.
4. **One ESP32 clock.** Every emitted edge is timestamped on the ESP32's timebase, which can be tied to the host clock (§C).

---

## A. Time-code display (LED bar)

### Encoding

A one-hot "chaser" gives the fine time and a Gray-code counter gives the coarse time. RocSync's design is similar, but a straight bar replaces RocSync's ring because of rolling shutter.

**Why one-hot and not binary for the fine time.** A camera row integrates over [s, s+E]. A binary or Gray fine counter that changes many times during E smears into unreadable grey. With a one-hot chaser stepping every Δ:
- every LED that was on during the exposure appears lit;
- the **first lit LED is the exposure start and the last is the exposure end**;
- the partial brightness of the two end LEDs gives a sub-step fraction.

RocSync decodes this way: the first lit LED is the start and the last is the end (see Sources).

| Element | Count | Behaviour |
|---|---|---|
| Fine bar F | 100 LEDs in one straight line | One-hot, advances every Δ = 100 µs (configurable 50 µs–1 ms), wraps every 100·Δ = 10 ms |
| Coarse counter C | 20 LEDs | Gray code `g = n ^ (n >> 1)` of the F revolution count. It increments when F wraps, every 10 ms, so the range is 2^20 × 10 ms ≈ 2.9 h |
| Fiducials | 4 LEDs, always on (DC) | Bar corners, for homography, tilt and orientation. Only 3 of them need to be asymmetric |
| Total switched channels | 120 | 8 × 16-channel drivers = 128 channels; 8 spare, one used as a "mode" bit (bar/strobe/calibration) |

**Decoding coarse time.** Gray code changes one bit per increment, so an exposure that spans one counter increment shows exactly **one** half-lit bit. The value is then k or k+1, and the F bar says where in the exposure the 10 ms boundary fell. That resolves it for any E < 10 ms, which covers the 2^-7 s = 7.8 ms exposure used in every flash run.
- **Longer exposures** (for example the C930e "long state", about a full frame of 33 ms, RERUN goal 2 table): set Δ = 400 µs, giving a 40 ms span. Precision degrades proportionally.
- **Wraps beyond 2.9 h,** or a frame that cannot be decoded, are resolved from the host arrival time mapped through §C. ±5 ms is enough.

### Geometry for rolling shutter

- **Orient the F bar horizontally, along image rows.** All 100 LEDs then fall in one row band and share one exposure window. RocSync's ring spans many rows. Its authors attribute their residual error (mean RMSE 1.34 ms on Azure Kinect) mainly to rolling shutter, and list compensation as future work.
- Put the Gray row directly below the F row, within a few image rows. The single-bit Gray ambiguity rule tolerates the small row offset.
- **Tilt and per-LED row correction.** On the C922, L ≈ 30.8 ms / 720 rows ≈ **43 µs per row**, using the measured 30.1–31.5 ms rolling-shutter span (REPORT finding 12). A bar tilted 1° over 400 px spans about 7 rows, which is a 0.3 ms ramp along the bar. The decoder therefore takes each LED's centroid row from the fiducial homography and moves each LED's sample to a reference row, using the L measured in strobe mode (§B).
- **Physical size.** 100 LEDs at 2.54 mm pitch is a 254 mm bar. For decoding, aim for ≥ 4 px per LED in every camera, so the bar should span ≥ 400 px. At 720p that means about half the frame width.
- **Optional second F bar** at the other end of a tall board, driven by the same channels (two LEDs in series per channel on a 9–12 V LED rail). It gives exposure windows at two rows per frame, and so a per-frame line-time check. This is a v2 feature, not required.

### Rise/fall time, LED choice and drive

- **Drivers.** Use 16-channel constant-current sink shift registers with a latch: STP16CP05, TLC5926 or MBI5026, daisy-chained.
  - All outputs change together on the **LE (latch) edge**. LE comes from a hardware timer, so update instants have no software jitter.
  - The next pattern is shifted in between latches: 128 bits at 10 MHz = 12.8 µs, well inside a 100 µs step.
  - Output switching on these parts is in the 0.1–1 µs range (estimate; check the chosen part's datasheet for t_r/t_f and any staggered output delay). Either way it is **≪ 100 µs**.
- **LEDs.** Use **monochrome AlGaInP red or InGaN green, not white**. White LEDs rely on a phosphor, and some phosphors (for example KSF red) decay over milliseconds. Bare-junction LEDs switch in tens of ns. Diffused 3 mm THT or 0805 SMD both work.
- **Do not use WS2812/SK6812/APA102 addressable LEDs.** They PWM-dim internally at hundreds of Hz to kHz and update through a serial pixel chain, so on a short exposure they show bands and have unknown latency.
- **Never dim by PWM**, either by OE-PWM or in firmware. PWM modulates light in time, which is the very thing being measured. Set brightness with the driver's single R_ext resistor (a trimmer). For partial-brightness interpolation the LEDs must stay unsaturated, so turn R_ext down until the brightest LED sits at about 70% of full scale at the chosen gain.
- **Brightness against short exposure.** An F LED is on for only Δ, so its signal is I × Δ whatever E is, while ambient light grows with E. Work in a dark room with high gain, auto-exposure off, auto-white-balance off, and anti-flicker (power-line frequency) off.
  - **Estimate:** a 20 mA high-brightness LED for 100 µs is clearly visible to a webcam at gain in the dark.
  - **This must be checked first** in phase 0 (§F P0), before building 120 channels.

---

## B. Strobe mode (the main precision instrument)

A single high-power monochrome LED, pulsed for w = 20–200 µs, lights a **matte white card that fills the full image height of every camera**. The F bar can be mounted on the same card.

**Why it works.** Row r exposes over [s0 + r·L, s0 + r·L + E]. A strobe at t_s lights only the rows whose window contains t_s. Each camera therefore shows a **horizontal lit band**:
- bottom edge r_b = (t_s − s0)/L, so **s0 = t_s − r_b·L**, the exposure start of row 0, in ESP32 time;
- top edge r_t = (t_s − E − s0)/L, so **E = (r_b − r_t)·L**.

L comes from a **double strobe** in one frame, with two pulses Δt apart (for example 10 ms): L = Δt / (band separation in rows). It can also come from a slow phase sweep.

What it gives:
1. **G1, real exposure phase across cameras.** One flash is seen by every camera at the same physical instant, with no scan-out and no dependence on rig position. s0_A − s0_B (mod frame period) is the true exposure-phase difference, per frame, over time.
2. **M1, exposure verification.** Band height gives the exposure actually applied, frame by frame, including the frame where a control change takes effect.
3. **Rolling-shutter line time** L, the readout time H·L, linearity (check that L is constant down the frame), and vertical blanking. When E < T − H·L, there are strobe phases that produce no band.

**Equivalent-time sweep.** Set the strobe period to T_cam·(1 + δ), for example δ = 10^-3. The strobe phase then walks about 33 µs per frame and covers a full frame in about 1000 frames (33 s at 30 fps). Free-running drift (tens of ppm) also sweeps it, but slowly.

**Identifying which strobe made a band:**
- Encode identity in the pulse pattern: single pulse versus double pulse with a variable gap.
- Or use the coarse time from the LED bar or host arrival (±5 ms is enough at a 30–40 ms strobe period).

**Light budget.** Every lit row gets the full pulse energy whatever E is.
- **Estimate:** 0.5–1 A into a 1–3 W green star LED (no phosphor) at 0.3–0.5 m from the card, at ≤ 1% duty, gives a strong band at moderate gain.
- Calibrate the camera's tone curve with the strobe itself. Sweep w from 10 to 200 µs at fixed gain; integrated light is proportional to w, so this measures the response curve directly. That removes the a-priori gamma assumption that dominated the flash method's error (`VERIFY_method.md` §1 and §3: "the gamma used matters more than the source").

**ISP artefacts to detect:**
- Temporal noise reduction shows as a weak echo band at the same rows in frame n+1.
- Sharpening causes edge overshoot; use the 50% crossing of a smoothed profile.
- MJPEG 8×8 blocks and chroma subsampling cost some sub-row precision. Repeat key runs in YUY2 at the same resolution, but **L must be measured in each format, resolution and fps actually used**, because a sensor may change readout timing with mode.

---

## C. Tying ESP32 time to host time (QPC / CLOCK_MONOTONIC)

**One timebase.** The ESP32's MCPWM capture timer (APB-clocked; 80 MHz on the classic ESP32) is the timebase. Every edge that matters reaches a capture input through a **loopback wire**: the LE anchor, STROBE, FSIN, and the start bit of each incoming serial ping. These are timestamps of the physical edges, not of the commands. The LE/PWM generators and the capture timer both derive from the same 40 MHz crystal through the PLL, so their ratio is fixed. Verify the timer clocking and capture width in the ESP32 TRM; the IDF page states that the capture resolution equals the APB clock on ESP32.

**Crystal.** ±10 ppm is the commonly cited tolerance for Espressif 40 MHz crystals, but it is **not confirmed for the classic ESP32 or for this DevKit** (forum posts only). It does not matter much: a 10 ppm offset is 0.33 µs per 33 ms frame, and the rate is fitted against the host clock anyway. Over minutes the thermal drift should be < 1 ppm once warm (estimate). Warm the board up for about 5 minutes before runs.

| Option | Hardware | Expected absolute accuracy (estimate) | Expected repeatability (estimate) | Notes |
|---|---|---|---|---|
| 1. LED/strobe only, relative (as today) | none extra | none: one offset fitted per source per run | at the rig floor (§E) | Scores regularity and inter-camera phase. Cannot give absolute latency (light → host). Sufficient for G1 and M1 |
| 2. Serial ping, min-RTT filter, classic DevKit through CP2102/CH340 | none | ±0.1–0.5 ms unknown bias. The path asymmetry is bounded only by RTT_min/2, likely ~0.5–1 ms | ~20–100 µs after min-filtering thousands of pings | Host stamps QPC at write and read. The ESP32 stamps the **RX start-bit edge** on a capture input (not the UART ISR, which fires on FIFO threshold or timeout) and the TX start bit of its reply. Full-speed bulk through a hub's transaction translator quantizes delivery (probably 125 µs / 1 ms steps). FTDI-style latency timers (16 ms default) must be set to 1 ms. No published µs RTT figures for CP2102/CH340 were found, so measure it. The DevKit resets on port open; re-anchor after each open (as PLAN.md §5.2 already assumes) |
| 3. Native USB CDC ping (ESP32-S3 USB-OTG or USB-Serial-JTAG; C3 USB-Serial-JTAG) | S3/C3 board | similar to option 2, slightly better (no UART hop) | ~10–50 µs | Still bulk scheduling; same asymmetry problem |
| 4. **USB SOF lock (ESP32-S3)** | S3 on the **same xHCI controller** as the cameras | ~1–10 µs to the USB frame clock; to QPC limited by the IOCTL mapping (below) | ~1 µs | The S3 timestamps every 1 ms SOF: poll the USB-Serial-JTAG `FRAM_NUM` register (11-bit SOF frame index, present on S3/C3) on core 1, or use a TinyUSB SOF callback on the OTG port (verify API). The host maps frame number to QPC with `IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC`, already used in phase 2. Caveat, measured: REPORT finding 14 found that mapping exact for only ~2–3.5 s, then drifting up to −641 µs over 20 s, and Microsoft documents its predicted accuracy in 125 µs units. **Re-anchor every ≤ 2 s**, and treat the residual as part of the result |
| 4b. SOF domain without QPC | S3 | ~µs | ~µs | UVC SCR pairs camera STC with SOF number. With ESP time ↔ SOF from option 4, camera STC → SOF → ESP time → LED/strobe truth is a chain that **bypasses QPC and the IOCTL drift**. Not usable on the C922, whose device SOF counter is broken (884/s, `VERIFY_method.md` §5); usable on the C930e |
| 5. GPIO into audio line-in (WASAPI QPC position) | sound card | unknown, not researched | unknown | Mentioned only for completeness |

**Recommendation:**
- Start with **options 1 + 2** on the classic DevKit. Option 1 is enough for G1, M1 and line time; option 2 gives sub-ms absolute latency.
- Add **option 4/4b with an ESP32-S3-DevKitC** (about $10–15) when G2 needs absolute latency at the tens-of-µs level.
- Run options 2 and 4 together once. The S3 SOF path then measures the bias of the serial-ping path, so later runs with only a classic ESP32 can be corrected.
- On Linux, ping options 2 and 3 work as on Windows with CLOCK_MONOTONIC. No user-space frame-number ↔ monotonic API was identified in this research (not checked).

---

## D. FSIN trigger output (InnoMaker OV9281 and others)

- Same MCPWM group, a third timer and generator. The period is set in ticks of the same timebase, and FSIN edges are looped back to a capture input, so **FSIN, strobe and LED code share one clock**.
- **Period.** Choose an integer multiple of the LED step so FSIN stays phase-locked to the code. For example 208 × 100 µs = 20.8 ms (48.08 Hz). That clears the ~18–20 ms InnoMaker lockout noted in PLAN.md §1, with the ESP32 crystal contributing ~0 rate error (the 48 Hz default in PLAN.md keeps the margin).
- **Electrical.** The InnoMaker FSIN is an opto input, about 19 mA at 5 V, triggered on the rising edge (PLAN.md §2). A 3.3 V GPIO cannot drive it. Wire FSIN+ to +5 V and FSIN− to a low-side sink: one AO3400A or 2N7002 per camera, or a ULN2803A channel (PLAN.md §4 electrical table). The GPIO going high turns the opto on; check which optical edge the camera triggers on.
- **Skew measurement** (PLAN.md §8 and arduino_sync REPORT finding 8: "unknown, could be up to ~1 ms"). With the strobe band method, **one frame** gives s0 of the triggered camera relative to the captured FSIN edge, so FSIN→exposure skew and its spread across cameras come out per frame. The sweep is needed only to cover blanking. This replaces PLAN.md's planned "delayed 50 µs flash swept 0–25 ms" with a faster equivalent.

---

## E. Expected ground-truth floor: arithmetic (all estimates)

| Error term | Flash method today | Rig, strobe band | Rig, LED bar |
|---|---|---|---|
| Light source timing | vblank fit, 10 µs residual, plus **unknown** scan-out position and LCD response (folded into the 35 ms block variation) | captured edge, ±12.5 ns; MOSFET + LED rise < 1 µs (constant) | LE hardware edge; driver + LED < 1 µs (constant) |
| Brightness-model error | ~1.2 ms peak-to-peak over f, at E = 7.8 ms (`VERIFY_method.md` §1) | edge ramp is only w/L ≈ 50/43 ≈ 1.2 rows; tone curve calibrated by strobe-width sweep | interpolation inside Δ only: 1.2 ms × Δ/E = 1.2 ms × 100/7812 ≈ **15 µs p-p**, likely less with the calibrated curve |
| Quantization | — | row: 43/√12 ≈ 12 µs per edge before sub-row fit; averaging across hundreds of columns gives an estimated ~3–8 µs | one-hot step: 100/√12 ≈ 29 µs without interpolation; ~5–15 µs with |
| Rolling-shutter / position term | **35 ms** variation across blocks, mixed with scan-out | none for s0 (row 0 by construction); L error × r_b. With L to 0.1% (10 ms double strobe ≈ 233 rows, ±0.3 row per edge), the error at row 360 is ~15 µs, and smaller when referenced near the band | L × residual row error after tilt correction: ±0.5 row ≈ ±20 µs unless corrected |
| MJPEG / ISP blur | gamma confounded | ~5–10 µs (estimate) | ~5–10 µs |
| **Per-frame total (1σ)** | **~0.5 ms floor (measured)** | **≈ 10–20 µs** | **≈ 15–30 µs** |
| Host-time mapping (G2 absolute only) | QPC native (display) | +0 (option 1, relative) / +0.1–0.5 ms bias (option 2) / ~1–10 µs plus re-anchored IOCTL residual (option 4) | same |

So the rig's estimated floor is **~20–50× below the flash method** for relative timing, G1 phase and E. For absolute latency it is set by the §C option. This is fine enough to settle REPORT finding 9: whether C922 PTS is really better than a frame counter. The current data cannot tell them apart (both score 0.5 ms), but the C922 PTS ±0.27 ms alternation (`VERIFY_method.md` §3) would be clearly resolved.

---

## F. Test protocols and host analysis

### Protocols

**P0, bring-up** (one evening; strobe parts only; worth doing before the bar is built):
- Logic-analyzer or loopback check of LE, STROBE and FSIN timing.
- Strobe band visible on all three cameras (C922, C930e, generic) at 720p30 MJPEG, at w = 50 µs, in the dark.
- Echo-band check (temporal noise reduction).
- Measure L for each camera.

**P1, line time and readout map** (per camera × format × resolution × fps):
- Double strobe (Δt = 10 ms, w = 50 µs), 300 frames.
- Outputs: L, H·L, linearity residual, vertical blanking.
- Modes: 480p/720p/1080p, 30/60 fps where available, MJPEG and YUY2.
- Expected (labelled): the C922 matches 30.1–31.5 ms at 720p30 (REPORT finding 12). Other modes are unmeasured.

**P2, M1 exposure verification** (includes the C930e re-apply open item, REPORT further investigation 6, PROGRESS section E):
- For each API path (MF IAMCameraControl / DirectShow / KS property, and libusb SET_CUR), set exposure at these moments:
  - (a) before stream start or COMMIT;
  - (b) 0.5 s and 2 s after the first frame;
  - (c) every 5 s, alternating between 2^-9 and 2^-6.
- Record per-frame E from band height, plus the API readback.
- Outputs:
  - did the requested E apply, and in which frame;
  - control-to-effect latency in frames;
  - whether the readback lies (the C930e read back −7 while integrating about a full frame, RERUN goal 2 table).
- Repeat with LogiTune's updater stopped.
- Also log the C930e PTS period mode (998,400 vs ~997,230 ticks per frame) to test the open hypothesis that the mode follows the exposure state.
- **M3 side-check:** with focus fixed, the LED spot size in the bar is a per-frame sharpness metric. Step manual focus through the values and confirm the spot size changes and then stays put. This detects autofocus that was not actually disabled.

**P3, G2 timestamp scoring:**
- C922 + C930e (+ generic), 60 s × 5 runs, at three exposures (2^-9, 2^-7, 2^-5).
- Log every source: MF OS time, host arrival, UVC PTS/SCR from MF metadata, and on WinUSB the libusb SCR and back-dated first payload.
- Truth per frame: s0 (row 0 exposure start), plus mid-exposure and end-of-readout derived from E and L.
- Score each source three ways:
  1. offset-only std/MAD (comparable with today's tables);
  2. causal online mapping;
  3. **absolute latency** (source − exposure start), using §C option 2 or 4.
- Also: regress PTS − s0 on E to test "C922 PTS near end of exposure" (−1.14·ΔE, provisional in REPORT finding 12), and run 60 s windows to re-check the SCR→QPC basis (REPORT further investigation 1).

**P4, G1 sync phase and drift:**
- All cameras view the card; one strobe per ~frame, with δ-sweep off.
- Δφ_AB(t) = s0_A − s0_B (mod T) over 30 min.
- Fit relative rate (ppm), wander, and any lock.
- Variants:
  - simultaneous versus staggered stream start;
  - same hub versus different root port (tests the hypothesis that a camera derives frame timing from USB SOF, which would give 0 ppm relative drift);
  - each capture API.
- **Expected:** free-running, unaligned exposures drifting at tens of ppm. This is inferred from the GT-derived PTS rates of +35 ppm (C930e) and −3.9 ppm (C922) against QPC (`VERIFY_method.md` §5), which would mean a full-frame slip in roughly 20–30 min. That supports Dom's assumption that no USB-side API aligns exposures. The rig measures phase; it does not align it.
- Report the residual after best software pairing: up to T/2 per frame pair, uniform.

**P5, FSIN** (when OV9281s are available): FSIN→exposure skew per camera, its spread across 4 cameras, and the lockout found by sweeping the FSIN period.

### Host analysis code (Python; new `timing/rig/`)

1. **Event-log parser** for the ESP32 serial stream:
   - `S k t_rise t_fall` (strobe), `F k t` (FSIN), `A n t` (LE anchor), `P seq t_rx t_tx` (ping), `E code n` (missed SPI deadline or other fault), `B boot_id`.
   - Use protocol-2 framing from arduino_sync PLAN.md §3 (`<PROTO:2>`, tagged OK/ERR lines) so the serial driver can later be shared with skellysync.
2. **Clock correlation:**
   - min-RTT and lower-envelope filtering of pings;
   - piecewise-linear ESP→QPC fit over a sliding 10 s window, with uncertainty;
   - optionally the SOF-based mapping, re-anchored every ≤ 2 s.
3. **Frame I/O:** strict libjpeg-turbo decode (REPORT finding 19); the camera's frame index, drops from PTS slots, and the per-source timestamps of each frame.
4. **Tone-curve calibration** from strobe-width sweep frames (integrated light ∝ w), per camera at fixed gain.
5. **Strobe band detector:**
   - card ROI → per-row mean across columns;
   - dark subtraction using rows outside the band, or the previous frame;
   - linearize;
   - 50% edges with sub-row interpolation;
   - flag clipped bands (top or bottom edge outside the frame) and echo bands.
6. **Band → strobe assignment** by coarse time (bar Gray code, or mapped host arrival) and pulse pattern.
7. **Per-frame solve:**
   - s0 = t_s − r_b·L and E = (r_b − r_t)·L;
   - L per camera and mode from double-strobe frames, or by regressing r_b on t_s across a sweep;
   - linearity residual.
8. **LED bar decoder:**
   - fiducials → homography → per-LED disc sampling and centroid row;
   - all-on and all-off reference frames (firmware `<ALLON>`/`<ALLOFF>`) to normalize;
   - first and last lit F LED with fractional ends;
   - Gray decode with the single-ambiguous-bit rule;
   - row-correct each LED with L.
   - Output (t_start, t_end) at the bar's row.
9. **Cross-check:** compare bar-derived and strobe-derived s0 per frame. Their difference is an independent estimate of the rig floor.
10. **Scoring and sync reports:** per-source residual std/MAD, causal versus whole-run fit, absolute latency, Δφ_AB(t) with drift fit, per-frame E against requested E.
11. **Synthetic self-test:** render frames from known s0, E, L, w, gamma and MJPEG quality, and check that the decoders recover them. This mirrors `selftest_flash_analyze.json`. The scorer is cleared to run on real data only after it recovers the synthetic truth within the §E budget, so the circularity issues of `VERIFY_method.md` §1 cannot reappear: the truth uses no camera timestamp at all.

### Firmware outline (classic ESP32, Arduino-ESP32 3.x calling IDF 5 APIs)

- **Wi-Fi and Bluetooth off.** Timing work is pinned to core 1.
- **MCPWM group 0, timer 0, the LE master.** Resolution 10 MHz, period 1000 ticks = 100 µs. A generator makes a 1 µs LE pulse at timer zero.
- **`on_empty` ISR** (IRAM): n++, then notify a top-priority render task on core 1. The task builds the 128-bit pattern (F one-hot plus Gray(n/100)) and sends it with `spi_device_polling_transmit` (VSPI, 10 MHz, 16 bytes) before the next LE.
  - A "done" flag is checked in the next ISR; a miss emits `E`. A missed deadline latches stale data, so it is detectable and flagged, never silent.
- **Timer 1, strobe.** 1 MHz resolution, so periods up to 65.5 ms fit a 16-bit tick count; whether the period register is 16-bit on this part should be verified in the TRM. Width and phase are set by command. Firmware refuses w > 500 µs or duty > 1%.
- **Timer 2, FSIN** at the commanded period.
- **Capture channels:**
  - cap0 ← STROBE loopback;
  - cap1 ← FSIN loopback (used for the LE anchor at start-up, before FSIN is enabled);
  - cap2 ← UART RX start bits.
  - Capture ISR: extend the timer to 64-bit and queue the event for serial output at 921600 baud.
- **Commands:** `<STEP:us>`, `<STROBE:period_us,width_us[,gap_us]>`, `<SWEEP:ppm>`, `<FSIN:period_us,width_us>`, `<BAR:0|1>`, `<ALLON>`, `<ALLOFF>`, `<PING#seq>`, `<STATUS>`.
- **No autostart.** All outputs are off at boot (see pull resistors in G).

**ESP32-S3 changes:**
- MCPWM ×2 groups, RMT and LCD_CAM are present (LCD_CAM could DMA the bar pattern with zero CPU, as a v2).
- Native USB enables §C options 3 and 4.
- Strapping pins are 0, 3, 45 and 46. Avoid 19/20 (USB D−/D+), 26–32 (flash), and 33–37 on octal-PSRAM modules (N8R8/N16R8).

**ESP32-C3 changes:**
- **No MCPWM**, so no capture peripheral. LE would come from LEDC and strobe from a gptimer alarm ISR (about µs of jitter, not loop-back captured).
- Single core.
- Strapping pins are 2, 8 and 9; USB is 18/19.
- Usable for the bar, weaker for strobe and timebase. **Use the S3 instead.**

---

## G. BOM, wiring, pins, safety

### BOM (rough prices, USD)

| Part | Qty | ~Cost | Notes |
|---|---|---|---|
| ESP32-WROOM-32 DevKitC | 1 | have | Upgrade path: ESP32-S3-DevKitC-1 (~$10–15) for SOF lock |
| STP16CP05 / TLC5926 / MBI5026, 16-channel constant-current sink | 8 | $8–16 | **Power the driver logic (VDD) from 3.3 V** so ESP32 3.3 V signals meet V_IH. At VDD = 5 V, V_IH = 0.7·VDD = 3.5 V is above 3.3 V |
| Alternative: TPIC6B595 + 1 resistor per LED | 15 | ~$20 | Open-drain; no constant current |
| Red AlGaInP 3 mm diffused (or 0805) LEDs | ~130 | $5 | Monochrome only |
| R_ext trimmers (one per driver), 0.1 µF per driver, 10 µF bulk per 2 drivers | — | $3 | |
| Strobe LED: 1–3 W green (or deep red) on a star, with a small heatsink | 1–2 | $3–6 | No phosphor; a diffuser in front |
| AO3400A logic-level N-MOSFET (R_DS(on) specified at V_GS = 2.5 V) | 4 | $1 | Strobe, plus one FSIN sink per camera. Avoid IRLZ44N-class parts, which are specified only from 4–5 V gate drive |
| Strobe current resistor, about 1.8 Ω 3 W (1 A from 5 V with V_f ≈ 3.2 V) | 1 | $1 | Size for your LED's V_f and pulse rating |
| 2200 µF low-ESR + 10 µF ceramic at the strobe LED | 1 | $2 | Supplies the pulse current locally |
| 100 kΩ gate pull-downs, 47–100 Ω gate series resistors, 10 kΩ OE pull-ups | — | $1 | |
| ULN2803A (alternative for 4–8 FSIN sinks) | 1 | $1 | |
| 5 V 3 A supply plus a separate 3.3 V 1 A regulator for the LED rail | 1 | $8 | LEDs are not powered from the DevKit or the PC's USB |
| 1 A polyfuse on the strobe rail, 500 mA on the LED rail | 2 | $1 | |
| BPW34 photodiode + 10 kΩ (optional optical rise check) | 1 | $2 | Needs a scope, or the ADC for coarse checks only |
| 8-channel 24 MHz USB logic analyzer (optional but valuable) | 1 | $10 | Verifies LE/STROBE/FSIN timing |
| Matte white foam board (A2), black flock or tape, perfboard or PCB | — | $10 | |

**LED rail and thermal.** With red V_f ≈ 2.0 V on a **3.3 V LED rail**, headroom is about 1.3 V. At 20 mA that is 26 mW per lit channel, so 16 lit channels dissipate about 0.4 W per driver. A 5 V rail would dissipate about 1 W per driver with all channels lit, which is too hot in SOIC.
- Running counter LEDs at 10 mA is enough.
- Worst-case total LED current ≈ (1 F + 20 Gray + 4 fiducials) × 20 mA ≈ 0.5 A.

### Classic DevKit pin assignment

Pins avoided:
- strapping 0, 2, 5, 12, 15;
- flash 6–11;
- UART0 1/3, except as the serial link itself;
- 14, which outputs PWM at boot;
- 16/17 on WROVER (PSRAM);
- input-only 34–39, which are used only as inputs.

| Function | GPIO | Notes |
|---|---|---|
| SPI SCLK → driver CLK | 18 | VSPI IOMUX pin; 33 Ω series resistor |
| SPI MOSI → driver SDI | 23 | VSPI IOMUX pin; no CS needed |
| LE (latch), MCPWM0 timer0 generator | 21 | Also looped back to GPIO34 for the start-up anchor |
| /OE (driver output enable) | 22 | 10 kΩ pull-up to 3.3 V, so the bar is dark at boot. Firmware drives it low after init. **Never PWM it** |
| STROBE gate (MCPWM0 timer1 generator) | 25 | 47–100 Ω series and 100 kΩ pull-down at the gate; looped back to GPIO35 |
| FSIN 1 / FSIN 2 gates (MCPWM0 timer2 generators A/B) | 26 / 27 | 100 kΩ pull-downs; one also looped back to GPIO34 after the LE anchor |
| Capture: LE anchor / FSIN loopback | 34 | input-only |
| Capture: STROBE loopback | 35 | input-only |
| Capture: UART RX start bit | 39 | Wire from GPIO3 (RX, driven by the CP2102 TX). External wire, so it does not rely on fanning one GPIO input out in the matrix |
| Photodiode (optional, ADC1) | 36 | input-only |
| Button (start/stop, marks) | 32 | internal pull-up |
| Status LED | 33 | |
| Spare | 4, 13, 16, 17, 19 | |

S3 equivalent (sketch): SCLK 12, MOSI 11, LE 9, /OE 8, STROBE 4, FSIN 5/6, captures 7/15/16, button 17, native USB on 19/20.

### Safety and electrical notes

- **Never drive LEDs from GPIOs directly.** GPIOs drive only the driver logic and MOSFET gates.
- **Strobe current.**
  - Pulse current is limited by a resistor; firmware caps width (500 µs) and duty (1%).
  - Hardware backstops: the 100 kΩ gate pull-down covers boot and reset, and the polyfuse limits a stuck-on gate. A stuck gate at 1 A would put about 1.8 W in the resistor and about 3 W in the LED, so the fuse matters.
  - Check the LED datasheet's pulsed-current rating.
- **Eyes.** Do not stare into the strobe from close range. Avoid IR emitters: they are invisible and webcam IR-cut filters block them anyway.
- **Ground and supply.**
  - Common ground between the ESP32 and the LED and strobe supplies.
  - Keep strobe return current away from the ESP32 ground (star point at the supply).
  - FSIN optos isolate the cameras.
  - Do not feed the rig's LED current through the PC's USB.
  - If the ESP32 shares a hub with cameras, note that its full-speed serial or CDC traffic is negligible bandwidth. For SOF lock it **must** be on the same controller as the cameras under test (Gerald has two controllers, REPORT finding 14).
- **Signal integrity.** For 8 chained drivers over about 30 cm at 10 MHz, keep CLK short, add series termination, and put 0.1 µF at every chip.

---

## How RocSync relates

**What RocSync is.** 100 red+IR LEDs in a ring stepping 1 ms per LED (100 ms per revolution), plus a 16-bit binary counter. A RISC-V MCU with a TCXO, battery powered. An offline Python decoder takes the first and last lit LEDs as exposure start and end. Per-camera drift is fitted linearly with RANSAC, from showing the clock at the start and end of a session. The authors report mean RMSE **1.34 ms** against hardware-synced Azure Kinects, with rolling shutter uncompensated and named as the main residual. Published in Sensors 2026, DOI 10.3390/s26031036.

**How it helps:**
1. It validates the one-hot "first/last lit LED" encoding used in §A.
2. It is a field-ready, ~1 ms post-hoc sync method for real skellycam sessions, including heterogeneous cameras (GoPro, phones) that never need to view the clock at the same time. Worth evaluating as a user-facing tool.
3. Its TCXO is a good idea for the field version. It is not needed for the bench rig, where the clock is fitted against the host.

**Why it is not the bench instrument here:**
- 1 ms steps are 10× coarser than needed.
- The ring spans image rows, so rolling shutter enters the result.
- There is no host-clock link, so absolute latency cannot be scored.
- There is no strobe or exposure-mapping mode.

The rig in this design is a bench version of the same idea: a horizontal 100 µs bar, a strobe, host correlation and FSIN. Its bar could also run a "1 ms step" mode for field use, but RocSync's decoder assumes a ring geometry, so it would not be reused directly. The RocSync license was not checked; check its LICENSE file before reusing any code or hardware files.

## Suggested build order

1. **Phase 0: strobe only.** One MOSFET, one LED, a white card, about $10. This alone answers G1 (phase and drift), M1 (actual E, C930e re-apply) and line time, at an estimated ~10–20 µs.
2. Serial ping correlation (§C option 2).
3. LED bar (§A), as an independent second method and for coarse time.
4. ESP32-S3 SOF lock (§C option 4/4b), for absolute G2 latency at the µs level and to calibrate the ping path.
5. FSIN outputs when the OV9281s are available.

Sources:
- [RocSync repository](https://github.com/BAL-ROCS-BUT-COOL/RocSync)
- [RocSync paper, arXiv:2511.14948](https://arxiv.org/html/2511.14948v1), [PMC version](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12900090/)
- [Zhao & Chen 2009, camera sync with a single binary LED source](https://www.spiedigitallibrary.org/journals/journal-of-electronic-imaging/volume-18/issue-4/040501/High-precision-synchronization-of-video-cameras-using-a-single-binary/10.1117/1.3247860.pdf)
- [esp32.com: main crystal requirements (±10 ppm citation, unconfirmed)](https://esp32.com/viewtopic.php?p=1782), [ESP32-PICO-V3-02 crystal thread](https://esp32.com/viewtopic.php?p=155141)
- [ESP-IDF MCPWM (ESP32)](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/mcpwm.html)
- [Arduino-ESP32 LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html), [arduino-esp32 issue 12157 (shared timers in 3.3.3)](https://github.com/espressif/arduino-esp32/issues/12157)
- [esp32s3 PAC usb_device (FRAM_NUM SOF frame index)](https://docs.rs/esp32s3/0.27.0/esp32s3/usb_device/index.html), [esp32c3 FRAM_NUM](https://docs.rs/esp32c3/latest/src/esp32c3/usb_device/fram_num.rs.html)
- [IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_usb_get_frame_number_and_qpc_for_time_sync)
- [Black Box ToolKit note on FTDI latency timer](https://www.bu.edu/neuroimaging/files/2022/01/Application-Note-for-User-on-Mac-or-Linux-v2.pdf), [Cedrus on USB-serial latency](https://community.cedrus.com/t/usb-to-serial/3374)