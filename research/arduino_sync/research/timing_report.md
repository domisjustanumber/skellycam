# Arduino Nano/Uno clock accuracy for camera frame sync (MoCapSTR trigger)

## Bottom line

- **No TCXOs on any of these boards.** The genuine Uno R3 and the genuine Nano V3 run the ATmega328P from a Murata CSTCE16M0V53 ceramic resonator. It is not a crystal. Its datasheet tolerance is ±0.5% initial, plus ±0.3% over temperature and ±0.2% aging. One unit was measured at −761 ppm.
- **For keeping the cameras in sync with each other, it does not matter.** All cameras get the same electrical edge, so any oscillator error hits every camera equally.
- **For frame-rate accuracy, it matters only if someone converts frame index to time using the nominal fps.** That includes pairing with an external system that has its own clock. At ±0.5%, a 50 fps stream drifts one full frame (20 ms) from nominal every 4 s. skellycam already timestamps every frame with the host's `perf_counter_ns`, and fitting a line through those timestamps recovers the real rate to better than 1 ppm against the host clock. A one-off measurement fixes it.
- **The firmware adds more timing error than the crystal-vs-resonator choice.** It polls `micros()` (4 µs steps), drives the pin with `digitalWrite`, and is interrupted by ISRs. That gives roughly 4–20 µs of edge jitter (an estimate, not measured) and up to 40 ppm of rate error from integer truncation. Using a hardware timer removes both.

## 1. Clock source per board

| Board | MCU clock source | Spec | Source |
|---|---|---|---|
| Uno R3 (genuine) | ATmega328P: **CSTCE16M0V53-R0 ceramic resonator**. The 16U2 USB chip has a separate 16 MHz crystal that does **not** clock the 328P. | ±0.5% initial, ±0.3% over −20…80 °C, ±0.2% aging (worst case about ±1%) | Official schematic https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf lists "CSTCE16M0V53-R0 16MHZ" and a separate "16MHz" part. Murata data: https://4donline.ihs.com/images/VipMasterIC/IC/MURE/MURE-S-A0001719029/MURE-S-A0001719029-1.pdf and https://sg.element14.com/murata/cstce16m0v53-r0/resonator-smd-16mhz/dp/1401454 |
| Nano V3.3 (genuine) | **CSTCE16M0V53-R0 ceramic resonator** | same as above | Official EAGLE file (NanoV3.3.sch in https://docs.arduino.cc/static/e3c4fe1f9bee7ec63df398422b3257f4/A000005-cad-files.zip) has `name="Y1" deviceset="0011_CSTCE16M0V53-R0"`. The older Nano v2.3 BOM listed a "16MHz +/-20ppm" Abracon crystal: https://www.arduino.cc/en/uploads/Main/ArduinoNanoManual23.pdf |
| Nano clones (CH340G/CH340C) | **Varies by board.** The CH340G needs its own 12 MHz crystal. The CH340C has an internal clock. The 328P side may have either a crystal or a resonator. | Resonator: ±0.5%. Crystal: typically ±20–100 ppm | https://web.mit.edu/6.111/www/f2017/serial/ch340g.pdf, https://forum.arduino.cc/t/arduino-uno-and-nano-ch340g-schematics/972944?page=4. **Not verified per board:** you have to inspect or measure each one. |
| Uno R4 Minima / WiFi (Renesas RA4M1) | A 16 MHz crystal is fitted on the Minima (FTX16.000M12SM3S-30/30), but the Arduino core **runs from the internal HOCO at 48 MHz** and does not use the crystal | HOCO48: 47.52–48.48 MHz at −20…85 °C (±1%) | Core config: `BSP_CFG_CLOCK_SOURCE (BSP_CLOCKS_SOURCE_CLOCK_HOCO)`, `BSP_CFG_XTAL_HZ (0)` in https://github.com/arduino/ArduinoCore-renesas/blob/main/variants/MINIMA/includes/ra_gen/bsp_clock_cfg.h (UNOWIFIR4 is identical). Schematic: https://docs.arduino.cc/resources/schematics/ABX00080-schematics.pdf. Datasheet Table 2.22: https://docs.arduino.cc/resources/datasheets/ra4m1-datasheet.pdf. I found no FLL config in the core. One forum user measured 47.999 MHz (about 20 ppm), anecdotal: https://forum.arduino.cc/t/frequency-counter-for-uno-r4-wanted/1172838 |
| Nano Every (ATmega4809) | **Internal RC oscillator** (OSC20M), with no crystal | ±1.5% at 25 °C/3 V; ±2.0% over 0–70 °C; ±4.0% over the full range; trim step 0.75% | Datasheet table "16/20 MHz Internal Oscillator": https://cdn.sparkfun.com/assets/5/d/2/b/3/DS-ATMega4809.pdf. **This is the worst board for rate accuracy.** |
| Nano ESP32 / ESP32-S3 boards | 40 MHz crystal (required for Wi-Fi) | ±10 ppm per Espressif's reference design | https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/esp-hardware-design-guidelines-en-master-esp32s3.pdf (reference design; I did not check the Nano ESP32 BOM). 3.3 V logic. |
| Nano 33 BLE (nRF52840) | 32 MHz crystal (required for BLE) | ±40 ppm limit cited for nRF52832 | https://devzone.nordicsemi.com/f/nordic-q-a/119156/nrf52832-32-mhz-crystal-aging-epson-fa-128/524085. **Not verified for the nRF52840.** |
| ATmega328P internal RC (reference) | — | ±2% factory at 3 V/25 °C, ±14% over the full range | ATmega328P datasheet Table 28-1: https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf |

**Measured data.** The only rigorous measurement I found is by Joris van Rijn, who used a GPS PPS signal and input capture: https://jorisvr.nl/article/arduino-frequency. He tested one board of each type, and both boards were warm (65–110 °C board temperature).
- Pro Mini with a ceramic resonator: −761 ppm, temperature coefficient −139 Hz/°C, which is **8.7 ppm/°C** (139 / 16e6). Over a 158 h run it wandered across a 286 ppm range. Short-term noise was 43.9 Hz rms per 1 s sample, about 2.7 ppm.
- Duemilanove with a crystal: +105 ppm, +0.97 Hz/°C, which is **0.06 ppm/°C**. Noise was 0.7 Hz rms, about 0.04 ppm.
- Forum figures (rule-of-thumb, not measurements): resonator around 0.3% to 0.5%, good crystal around 10–20 ppm, TCXO around 1–2.5 ppm (https://forum.arduino.cc/t/arduino-with-tcxo/342860).
- The time-nuts mailing list also confirms that Uno and Pro Mini use resonators: https://www.febo.com/pipermail/time-nuts/2014-February/082940.html

**TCXO options, if absolute accuracy were ever needed:**
- A DS3231 RTC module has a TCXO rated ±2 ppm over 0–40 °C and ±3.5 ppm over −40…85 °C, with a 1 Hz or 32 kHz square-wave output (https://www.electronicdesign.com/technologies/components/article/21764107/32768-khz-tcxo-accurate-to-2-ppm-from-0c-to-40c). Its 1 Hz output can go into Timer1 input capture (ICP1, pin D8) so the board measures and corrects its own frequency.
- A GPS PPS signal is better still. The NEO-6M timepulse is listed at 30 ns rms (https://www.altronics.com.au/product/z6318-neo-6m-gps-breakout-module-with-antenna); other sources say 100 ns rms, so this figure conflicts.
- A 16 MHz TCXO such as the FOX924B (2.5 ppm) can replace the resonator as an external clock. This needs a fuse change and is 3.3 V oriented (same forum thread as above).
- **Not verified:** module prices. They are commonly a few dollars for a DS3231 and around $10 for a NEO-6M, but I did not confirm this.

## 2. Firmware timing error (MoCapSTR `trigger_firmware.ino` v1.5.0)

**`micros()` resolution is 4 µs on a 16 MHz AVR.** In `wiring.c` it returns `((m<<8)+t) * (64/clockCyclesPerMicrosecond())`, which is ticks × 4 µs (https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring.c). Each edge fires at the first loop pass where a 4 µs-quantized reading is at or past the target. The firmware's `previousMicros += interval` keeps the long-run mean correct, but individual periods wobble by about ±4 µs. `micros()` wraps every 2³² µs (71.6 min); the firmware's unsigned subtraction handles that correctly.

**Integer truncation of `1000000UL / fps`.** The rate error is relative to the MCU clock:

| fps | Interval used | Actual rate | Error | Drift per hour |
|---|---|---|---|---|
| 30 | 33333 µs | 30.0003 Hz | +10 ppm | 36 ms (1.1 frames) |
| 50 | 20000 µs | exact | 0 | 0 |
| 60 | 16666 µs | 60.0024 Hz | +40 ppm | 144 ms (8.6 frames) |
| 90 | 11111 µs | 90.0009 Hz | +10 ppm | 36 ms (3.2 frames) |
| 120 | 8333 µs | 120.0048 Hz | +40 ppm | 144 ms (17.3 frames) |

These are calculations. They are small next to resonator error but as large as or larger than crystal error. MoCapSTR's own docs say hardware-trigger mode is limited to 50 fps (`CAMERA_SPECS.md`), and that case is exact.

**Latency and jitter sources:**
- **`digitalWrite`:** about 3.4–5 µs, or 80 cycles (https://blog.timodenk.com/port-manipulation-and-arduino-digitalwrite-performance/). A direct port write takes 125 ns. This is mostly a constant delay rather than jitter. The LED write also adds about 4 µs to the high time.
- **Timer0 overflow ISR:** about 6 µs every 1.024 ms (https://avdweb.nl/arduino/timing/timer0-interrupt). It occasionally delays an edge by up to about 6 µs.
- **Loop pass time:** each pass runs `digitalRead`, `millis`, a `stringComplete` check, `micros`, and `serialEventRun`. The edge lands somewhere within one pass, so this adds jitter roughly equal to the pass time. **Not measured; my estimate is about 10–20 µs.**
- **Serial:** the TX and RX buffers are 64 bytes (https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/HardwareSerial.h). One byte at 115200 baud takes 86.8 µs (10/115200).
  - The `<FPS:N>` reply is about 62 bytes, so it fits the buffer and normally does not block.
  - If the TX buffer is already full, `Serial.print` blocks for 86.8 µs per byte.
  - If any stall exceeds one interval, the firmware's re-align branch (`previousMicros = currentMicros`) **drops a pulse and permanently shifts the phase**.
  - String parsing during recording, such as handling `<PING>` or the `<TOGGLE_REC>` button message, adds tens to hundreds of µs to that loop pass (estimate).
- **Pulse width:** the 1 ms pulse is a blocking busy-wait. It is harmless because RX is ISR-buffered.
- **Expected total:** about 4–20 µs peak-to-peak edge jitter while idle, with occasional larger outliers when serial traffic happens during recording. **This needs a logic-analyzer measurement to confirm.**

**Hardware-timer alternative (ATmega328P Timer1):**
- Use Fast PWM mode 15 (TOP = OCR1A) with the output on **OC1B, pin D10 (PB2)**. Mode 15 is the right choice because OCR1A is double-buffered. The datasheet says ICR1-as-TOP "works well when using fixed TOP values" but OCR1A is "clearly a better choice due to its double buffer feature" when changing TOP (same datasheet, Timer1 Fast PWM section).
- Edges are generated by the hardware compare unit, so they are **cycle-exact (62.5 ns granularity) and have zero firmware or ISR jitter**. The remaining jitter is oscillator phase noise, which should be well under 1 µs. **That figure is not verified; it is inferred from the ~2.7 ppm rms per-1 s noise measured on the resonator.**
- With prescaler 8 (0.5 µs ticks), the slowest possible rate is 16e6/8/65536 = 30.5 Hz.

| fps | Prescaler | Ticks | Rate error |
|---|---|---|---|
| 50 | 8 | 40000 | 0 |
| 60 | 8 | 33333 | +10 ppm |
| 90 | 8 | 22222 | +10 ppm |
| 120 | 8 | 16667 | −20 ppm |
| 30 | 64 | 8333 | +40 ppm |

- A fractional-N update brings any of these to an exact long-run mean: in the overflow ISR, alternate TOP between N and N+1 using an accumulator. ISR latency then has no effect on edge timing.
- Count pulses in the TOV1 ISR.
- This requires moving the trigger wire from D2 to D10 (or to D9/OC1A if using mode 14 with fixed TOP).

## 3. Does it matter?

**(a) Sync between cameras: no.** Every camera receives the same edge, so oscillator error is common-mode. What remains is wire propagation (nanoseconds) and differences in each camera's FSIN-to-exposure latency. That latency is likely set by when each sensor's own free-running clock samples the trigger.
- **Not verified:** I found no published FSIN-to-exposure delay or jitter for the InnoMaker OV9281. Arducam's OV9281 docs give only a minimum trigger pulse of at least 2 µs and a 1.8 V trigger level for their MIPI module (https://docs.arducam.com/Raspberry-Pi-Camera/Global-Shutter-Camera/external-trigger/). MoCapSTR's `CAMERA_SPECS.md` says the InnoMaker USB board accepts 3.3–5 V.
- This should be measured, for example by filming an LED driven from the same trigger line.

**(b) Frame-rate accuracy: only when you assume the nominal fps.** Drift from nominal at 50 fps (calculated):

| Clock error | After 1 min | After 10 min | After 1 hr | Time until 1 frame (20 ms) of drift |
|---|---|---|---|---|
| ±0.5% (resonator spec) | 0.30 s / 15 frames | 3.0 s / 150 frames | 18 s / 900 frames | 4 s |
| −761 ppm (measured resonator) | 46 ms / 2.3 frames | 0.46 s / 23 frames | 2.7 s / 137 frames | 26 s |
| ±1% (RA4M1 HOCO spec) | 0.6 s | 6 s | 36 s | 2 s |
| ±2% (Nano Every, 0–70 °C) | 1.2 s | 12 s | 72 s | 1 s |
| 105 ppm (measured crystal) | 6.3 ms | 63 ms | 0.38 s / 19 frames | 190 s |
| 20 ppm crystal | 1.2 ms | 12 ms | 72 ms | 1000 s |
| 2 ppm TCXO | 0.12 ms | 1.2 ms | 7.2 ms | 10000 s |

- A ±0.5% resonator means "50 fps" is really somewhere between 49.75 and 50.25 fps.
- The error is mostly a fixed offset plus temperature drift (8.7 ppm/°C for a resonator, so a 5 °C warm-up is about 43 ppm). That means a calibration against the host clock removes most of it.
- **It matters when:**
  - code computes time as `frame_index / nominal_fps`;
  - files store a nominal fps that a player or analysis tool trusts;
  - you pair with devices on their own clocks (audio interfaces, force plates, EMG, IMUs) and align only at the start.
- **In skellycam specifically:**
  - Every frame already gets a host timestamp (`pre/post_frame_record_ns`).
  - `video_audio_remuxer.py` builds variable-frame-rate PTS from real `perf_counter_ns` timestamps and places audio with a single start offset.
  - However, `video_recorder.py` writes the container with the nominal `self.framerate`. Raw per-camera MP4 durations will therefore be off by the trigger's clock error.
- The host clock is not a perfect reference either. Microsoft says PC crystals are "typically ±30 to 50 ppm", and QPC "isn't synchronized to any external time reference" (https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps).
- **For other measurement systems, the best fix is to share the trigger edge itself** (feed the TTL into the force-plate or EMG DAQ's sync input, or record it on an audio channel). Then the Arduino's absolute accuracy stops mattering entirely.

**(c) Jitter: negligible at the µs level.**
- 20 µs is 0.1% of a 20 ms frame period and 2% of a 1 ms exposure.
- In motion terms, 10 µs at 5 m/s is 0.05 mm, and 20 µs at 10 m/s is 0.2 mm (calculated). Both are far below marker or keypoint error.
- What does matter is **missing or extra pulses and phase jumps**, which the re-align branch causes, because they break frame-index correspondence.

**(d) Mapping trigger edges to host time.**
- USB-serial latency is milliseconds: the FTDI latency timer defaults to 16 ms (https://www.ftdichip.com/old2020/Support/Documents/AppNotes/AN232-04.pdf). USB in general adds "a millisecond or two" (time-nuts post above). The Arduino's `micros()` therefore cannot timestamp host events directly.
- Option 1, round-trip handshake: the host sends a sync command and the Arduino replies with its pulse count and timer time. Keep the samples with the smallest round-trip time and fit a line. With about 1 ms of jitter over 600 s, that gives about 1.7 ppm precision (1e-3 / 600).
- Option 2, regression on existing timestamps: fit the host frame timestamps against frame index. The least-squares slope uncertainty is about σ/(D·√(N/12)). For σ = 2 ms, N = 30,000 frames (10 min at 50 fps) and D = 600 s, that is 0.002/(600·50), about **0.07 ppm**.
- So skellycam can measure the true trigger rate relative to `perf_counter_ns` with no firmware support. What the firmware must provide is a **pulse count**, so that dropped frames can be detected.
- The fitted line also gives exposure-time estimates (offset + k·T) that are cleaner than the USB arrival timestamps.

## 4. Recommendations

1. **Do not require a crystal or TCXO for multi-camera sync.** Do recommend against the Nano Every (±2%) and treat the Uno R4 (±1%) as worse than a 328P resonator board. A crystal board (most CH340 clones, check each board) is a free improvement for nominal-fps fidelity. A TCXO or GPS is only worth it for long sessions that pair with external clocks and have no shared sync line.
2. **Rewrite the firmware to use Timer1 hardware PWM** (mode 15, OC1B/D10, fractional-N TOP), with a pulse counter in the TOV1 ISR. Remove the re-align or skip branch. Keep the serial protocol but make it non-blocking (no `String`, no prints longer than 64 bytes while running).
3. **Add protocol commands:**
   - `<START>` should reply with the counter value and a timer-derived time.
   - `<STATUS>` or `<SYNC>` should return `count,timer_us`.
   - `<STOP>` should return the total pulse count.
   - The host logs its `perf_counter_ns` at send and receive, and compares the pulse count with the frames received per camera to flag drops.
4. **Have the host measure the actual rate and save it in the recording metadata:** the regression slope from frame timestamps, cross-checked against the pulse count divided by elapsed host time. Use it for container fps (or always use VFR PTS from timestamps), and never assume the nominal fps.
5. **Optional one-time calibration:** measure the board's real F_CPU against the host over about 10 minutes (≤2 ppm by the calculation above), store the ppm correction in EEPROM, and pre-scale TOP. Alternatively, wire a DS3231 1 Hz output or a GPS PPS signal to ICP1 (D8) for continuous self-calibration.
6. **To validate:** put a logic analyzer on D2 or D10 to measure jitter, and film an LED driven from the trigger line to measure FSIN-to-exposure skew between cameras. Both are unmeasured so far.

## Not verified

- InnoMaker OV9281 FSIN latency, jitter and input voltage range.
- Loop-pass time and the resulting edge jitter in the current firmware.
- Which oscillator any particular Nano clone has.
- The nRF52840 crystal spec, and what the Nano ESP32 actually has fitted.
- Uno R4 `micros()` resolution.
- Prices of DS3231 and GPS modules.
- Phase noise of the resonator below 1 s.
- Joris van Rijn's measurements are single units at elevated board temperature.

Files I read or downloaded:
- MoCapSTR firmware: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/a9b9d5dd-3ef8-4726-a4e0-a9884ba8c7b5/scratchpad/mocapstr-src/arduino/trigger_firmware/trigger_firmware.ino`
- Datasheets, schematics and the extracted Nano CAD files: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/a9b9d5dd-3ef8-4726-a4e0-a9884ba8c7b5/scratchpad/pdfs/`
- skellycam: `C:/Users/Dom/GitHub/freemocap/skellycam/skellycam/core/recorders/videos/video_recorder.py`, `C:/Users/Dom/GitHub/freemocap/skellycam/skellycam/core/recorders/video_audio_remuxer.py`, `C:/Users/Dom/GitHub/freemocap/skellycam/skellycam/core/timestamps/timebase_mapping.py`