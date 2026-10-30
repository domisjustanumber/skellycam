# ESP32 sync and timing rig (DRAFT)

A bench instrument to replace the monitor-flash ground truth (`../timing/VERIFY_method.md`). It is
built from a classic ESP32 DevKit, an LED strobe, an optional LED time-code bar, and optional FSIN
trigger outputs. Every edge it emits is timestamped on one ESP32 clock, and that clock is tied to
the host clock (QPC on Windows, CLOCK_MONOTONIC on Linux) over the serial link.

This folder implements a first draft of the rig design ([DESIGN.md](DESIGN.md)) used by the gap-filling test plan
([../docs/test_gap_plan.md](../docs/test_gap_plan.md)). The design
estimates a ground-truth floor of about 10–30 µs, against the flash method's measured ~0.5 ms. That
figure is an estimate and has not been measured.

## Status

| Item | State |
| --- | --- |
| Firmware `esp32_sync_rig/esp32_sync_rig.ino` | **Compiles, never flashed, never run.** Built on 2026-10-30 with arduino-cli 1.2.0 and the Arduino-ESP32 core 3.2.0 (ESP-IDF v5.4) for `esp32:esp32:esp32`, with `--warnings all`. Result: exit 0, 345,778 bytes of flash (26%), 21,156 bytes of RAM (6%). The only warnings are 6 `-Wmissing-field-initializers` from the IDF macro `MCPWM_GEN_COMPARE_EVENT_ACTION_END()`. A variant build with `-DCAP1_ROLE=1 -DUSE_RX_EDGE_CAPTURE=0` also compiles (exit 0). Build output went to a temp folder outside the repo. |
| Host script `host/esp32_clock_sync.py` | `--help` and `python -m py_compile` pass. `--self-test` passes on synthetic pings (12.5 ppm true drift → 12.509 ppm fitted). **Never run against a device.** |
| Hardware | Nothing built, nothing measured. No timing figure on this page is a measurement. |
| Analysis code (`timing/rig/` in the plan) | Not written. |

## Files

```
sync_rig/
  README.md                          this file
  esp32_sync_rig/esp32_sync_rig.ino  firmware (Arduino-ESP32 3.x, calls IDF 5 MCPWM / SPI drivers)
  host/esp32_clock_sync.py           PEP 723 script: PING/PONG clock correlation -> results/<platform>/<host>/sync_rig_clock/
```

## How it maps to the goals

| Goal | What the rig gives | Mode |
| --- | --- | --- |
| G1 sync (exposure alignment) | It **measures** each camera's exposure phase. It does not align exposures. A single strobe pulse lights a white card for every camera at once. Each camera shows a lit row band, and the bottom edge of that band gives the start of exposure: s0 = t_strobe − r_bottom·L. Δφ = s0_A − s0_B, tracked over time, gives the phase and drift between cameras. Only FSIN (hardware trigger, cameras with a sync input) can **align** exposures, and the rig drives FSIN too. | strobe, FSIN |
| G2 timestamp accuracy | A per-frame true exposure start in ESP32 time. The PING/PONG clock fit maps it to QPC or CLOCK_MONOTONIC, so each timestamp source (MF sample time, host arrival, UVC PTS/SCR) can be scored for **absolute** latency as well as offset-only jitter. | strobe + clock sync |
| M1 exposure control | Band height = actual exposure E for each frame, so the rig confirms whether a requested exposure was applied, and in which frame. It also covers the C930e re-apply open item. | strobe |
| M2 format control | Measures the rolling-shutter line time L and the readout for each format, resolution and fps (double strobe). It does not test whether a format can be set. | strobe (`gap_us`) |
| M3 focus control | Side check: LED spot size in the bar gives a sharpness value for every frame. If autofocus is still active, the spot size drifts. | bar |
| G3 MJPEG, G4 IDs, G5 bandwidth | Not addressed by the rig. | n/a |

The rig does not open a camera. Camera captures that run alongside it on Gerald must still go through
`tools/camlock.py`.

## Bill of materials (phase 0 first)

Phase 0 is strobe only, about $10, and answers G1, M1 and line time on its own. Build it before the LED bar.

| Part | Qty | Notes |
| --- | --- | --- |
| ESP32-WROOM-32 DevKitC (classic ESP32, CP2102 or CH340) | 1 | Already on hand. The upgrade path is an ESP32-S3-DevKitC-1 for USB SOF lock (not in this draft) |
| Strobe LED, 1–3 W **green or deep red, no phosphor**, on a star with a small heatsink and a diffuser | 1 | Not white: phosphor decays slowly. Not IR: webcam IR-cut filters block it |
| AO3400A logic-level N-MOSFET (R_DS(on) specified at V_GS = 2.5 V) | 1 + 1 per FSIN camera | Not IRLZ44N-class parts |
| Strobe current resistor, ~1.8 Ω 3 W (≈1 A from 5 V at V_f ≈ 3.2 V) | 1 | Size it for your LED's V_f and pulse rating |
| 2200 µF low-ESR + 10 µF ceramic at the strobe LED | 1 | |
| 100 kΩ gate pull-downs, 47–100 Ω gate series resistors, 10 kΩ /OE pull-up | — | |
| 1 A polyfuse on the strobe rail, 500 mA on the LED rail | 2 | Backstop if a gate sticks on |
| 5 V 3 A supply (+ 3.3 V 1 A regulator for the bar LEDs) | 1 | LED current never comes from the DevKit or the PC's USB |
| Matte white foam board (A2), black flock or tape | — | Card must fill the full image height of every camera |
| 8-channel 24 MHz USB logic analyzer | 1 | Needed for bring-up: checks LE, STROBE, FSIN and SYNC timing |
| *Bar (phase 3):* STP16CP05 / TLC5926 / MBI5026 16-channel constant-current sink | 8 | **Driver VDD from 3.3 V** (at 5 V, V_IH = 3.5 V is above the ESP32's 3.3 V) |
| *Bar:* red AlGaInP 3 mm diffused (or 0805) LEDs | ~130 | Monochrome only. Never addressable LEDs (WS2812, APA102) |
| *Bar:* R_ext trimmer + 0.1 µF per driver, 10 µF per 2 drivers | — | Set brightness with R_ext only. **Never PWM-dim** |
| *FSIN (phase 5):* ULN2803A as an alternative to one MOSFET per camera | 1 | FSIN+ to +5 V, FSIN− to the sink |
| *Optional:* BPW34 photodiode + 10 kΩ | 1 | Optical rise-time check with a scope |

## Wiring (classic DevKit)

Pins avoided: strapping pins 0/2/5/12/15, flash pins 6–11, GPIO14 (outputs PWM at boot) and
16/17 (PSRAM on WROVER). GPIO34–39 are input-only and have no internal pulls.

| Function | GPIO | Connects to | Notes |
| --- | --- | --- | --- |
| SPI SCLK | 18 | driver CLK | VSPI IOMUX pin, 33 Ω series resistor |
| SPI MOSI | 23 | driver SDI (first driver) | no CS; LE does the latching |
| LE (latch) | 21 | all drivers' LE **and** a wire to GPIO34 | MCPWM0 timer 0, 1 µs pulse every `STEP` µs |
| /OE | 22 | all drivers' /OE | 10 kΩ pull-up to 3.3 V (bar dark at boot). Firmware only switches it, never PWMs it |
| STROBE gate | 25 | MOSFET gate via 47–100 Ω, 100 kΩ to GND, **and** a wire to GPIO35 | MCPWM0 timer 1 |
| FSIN 1 gate | 26 | FSIN sink MOSFET (or ULN2803A input) | MCPWM0 timer 2 gen A. Wire to GPIO34 instead of LE when built with `CAP1_ROLE=1` |
| FSIN 2 gate | 27 | second FSIN sink | identical waveform |
| Capture: LE or FSIN loopback | 34 | wire from GPIO21 (default) or GPIO26 | capture channel 1 |
| Capture: STROBE loopback | 35 | wire from GPIO25 | capture channel 0, both edges |
| Capture: UART RX start bit | 39 | wire from GPIO3 (U0RXD, driven by the bridge's TX) | capture channel 2. With `USE_RX_EDGE_CAPTURE=0`, channel 2 moves to GPIO19 (internal pull-down, nothing wired) |
| Internal sync | 4 | **leave unconnected** | software pulse at START that aligns the three MCPWM timers. Useful as a logic-analyzer trigger |
| Button | 32 | push button to GND | internal pull-up. Sends `EV BTN` |
| Status LED | 33 | LED + resistor to GND | on while outputs run |
| Photodiode (optional) | 36 | BPW34 + 10 kΩ | reserved; this draft does not read it |
| Spare | 13, 19 (16, 17 on WROOM only) | | 19 is used when `USE_RX_EDGE_CAPTURE=0` |

**Unwired captures float.** If a loopback wire to 34, 35 or 39 is missing, fit a 100 kΩ pull-down to GND
on that pin. A floating pin can produce bogus events and a stream of interrupts.

Bar chain: ESP32 → driver 0 → … → driver 7. Channel 0 is driver 0 OUT0. F LEDs use channels 0–99,
Gray bits 100–119, fiducials 120–123 and the mode bit 124. Mount the F bar **horizontally**, along the
image rows, with the Gray row directly below it. The bit order is unverified. To check it, send
`STEP 32000` then `MODE CODE`; the lit F LED should walk 0 → 99.

Ground: common ground between the ESP32 and the LED and strobe supplies, with a star point at the
supply. Keep the strobe return current out of the DevKit ground. FSIN optocouplers isolate the
cameras.

## Flashing

The commands below were not run against a board; only `compile` was run.

```
arduino-cli compile --fqbn esp32:esp32:esp32 research/usb_cameras/sync_rig/esp32_sync_rig
arduino-cli upload  --fqbn esp32:esp32:esp32 -p COM5 research/usb_cameras/sync_rig/esp32_sync_rig
```

Arduino IDE: board "ESP32 Dev Module", core **3.x** (the sketch `#error`s on 2.x and on non-ESP32 targets).
Build switches can be set from the command line, for example:
`--build-property "compiler.cpp.extra_flags=-DCAP1_ROLE=1 -DUSE_RX_EDGE_CAPTURE=0"`.

## Serial protocol

The link runs at 921600 baud, 8N1, one ASCII command per line, case-insensitive. A leading `#tag`
token is echoed in front of the reply. Replies are `OK <CMD> …` or `ERR <CMD> <reason>`. Lines that
start with `EV` are unsolicited events, and the host must skip them while waiting for a reply.
Nothing autostarts: at boot every output is held low and the bar is dark.

| Command | Reply / effect |
| --- | --- |
| `PING <host_ns>` | `PONG <host_ns> <esp_us_rx> <esp_us_tx> <E\|B>`. `esp_us_rx` is the start bit of the PING's first byte: `E` means captured on GPIO39, `B` means estimated from the read time minus the line's serialization time. `esp_us_tx` is esp_timer read just before the PONG enters the empty TX FIFO |
| `STATUS` | one line of `key=value`: run state, config, counters, `late`, `evq_ovf`, anchor residual, xtal/APB/CPU clocks, `boot_id`, `esp_us` |
| `VERSION`, `HELP` | |
| `MODE CODE [step_us]` | bar shows the time code, strobe off, (re)start |
| `MODE STROBE <period_us> <width_us> <phase_us> [gap_us]` | strobe on, bar dark, (re)start. `gap_us` > 0 adds a second pulse `gap_us` after the first (rise to rise) |
| `MODE OFF` | same as `STOP` |
| `STEP <us>` | fine-bar step / LE period, 50–32767 µs. Takes effect at START |
| `BAR CODE\|ALLON\|ALLOFF\|DARK` | live. ALLON/ALLOFF are the normalization frames; ALLOFF keeps the fiducials lit |
| `STROBE <period_us> <width_us> <phase_us> [gap_us]` / `STROBE OFF` | takes effect at START. Limits: period 1000–65535 µs, width ≤ 500 µs, duty ≤ 1 %, phase < period, width < gap |
| `FSIN <period_us> <width_us> [phase_us]` / `FSIN OFF` | takes effect at START |
| `START` / `STOP` | START re-syncs all outputs from one edge and defines a new epoch |
| `ANCHOR` | re-anchors the capture timer to esp_timer now, and re-arms the LE anchor event |
| `EVENTS ON\|OFF` | turns EV output on or off; the host script switches it off during ping runs |

Phase reference: the **epoch** is the first LE rising edge after START. Strobe pulse 1 rises at
epoch + phase + j·period, and FSIN rises at epoch + phase + j·period. The firmware commands these
times; the captured loopback edges show what actually happened.

| Event | Meaning (all times are esp_timer nanoseconds: µs since boot × 1000, with sub-µs detail from the 80 MHz capture timer) |
| --- | --- |
| `EV B <boot_id> <fw> <ver> hw_ok=<0\|1>` | boot. A new boot_id means the clock fit restarts |
| `EV S <k> <t_rise_ns> <t_fall_ns>` | strobe pulse k since START, captured on GPIO35 (in double mode, consecutive k alternate between pulse 1 and pulse 2) |
| `EV F <k> <t_rise_ns>` | FSIN rise (only with `CAP1_ROLE=1`) |
| `EV A <k> <t_rise_ns>` | LE edge k. k = 0 is the epoch; later ones only after `ANCHOR` |
| `EV K <cap_ticks64> <esp_ns> <resid_ns> <half_ns>` | capture-timer anchor, once a second |
| `EV E LATE <count> <k>` | the bar render missed the next LE, so stale or half-shifted data was latched (flagged, never silent) |
| `EV E OVF <count>` / `EV E INIT …` / `EV E ANCHOR …` | event queue overflow, or an init or anchor failure |
| `EV BTN <esp_ns>` | button press |

## Clock correlation (host)

```
uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --list-ports
uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --port COM5 --duration 60 --rate 50
uv run --script research/usb_cameras/sync_rig/host/esp32_clock_sync.py --self-test
```

The script holds DTR and RTS low on open so the DevKit does not reset (some drivers pulse them anyway;
`--allow-reset` skips this). It waits for `EV B`, then sends VERSION and STATUS and `EVENTS OFF`,
and pings with a jittered schedule so the pings do not lock to the 1 ms USB frame. It busy-polls
`in_waiting` and stamps each PONG when its first bytes arrive.

For each ping, delay = RTT − ESP32 turnaround, and offset = ((rx − t1) + (tx − t4))/2. The script
keeps the minimum-delay ping in each 1 s window, then fits a least-squares line through those
minima to get the offset at a reference time and the drift in ppm.

It writes `results/<platform>/<hostname>/sync_rig_clock/result_<utc>.json`, following
`../README.md` (`test`, `platform`, `hostname`, `utc_started`, `command`, `environment`, `cameras`
(empty), `device`, `parameters`, `measurements`), plus `pings_<utc>.csv` with every raw ping.

What the numbers mean:
- `residual_std_us` is the repeatability of the mapping.
- `asymmetry_bound_us` (min delay / 2) bounds the **unknown absolute bias**. Min-RTT filtering
  cannot remove it.
- Two offsets are reported. The second assumes the bridge forwards the PONG only after its last byte.
  A ~50-byte reply takes ~0.54 ms to serialize at 921600 baud, so the two differ by ~0.27 ms. Only
  an independent reference can tell which is right. The ESP32-S3 SOF lock in the plan (option 4) is
  that reference.

Expected accuracy for this path (design estimate, not measured): absolute ±0.1–0.5 ms, repeatability
~20–100 µs. For G1, M1 and line time, the clock fit is not needed at all: those use only differences
between captured edges and image rows.

## Bring-up checklist (P0, before any camera run)

1. Flash. `STATUS` should show `cap_res_hz=80000000` and `apb_hz=80000000`, and
   `anchor_half_ns` should be a few hundred ns to ~1 µs.
2. Logic analyzer on 4 (SYNC), 21 (LE), 25 (STROBE), 26 (FSIN): send `STROBE 33333 50 1000`,
   `FSIN 20800 100 0`, `START`. Check the following:
   - LE period = STEP, and pulse = 1 µs.
   - Strobe width = 50 µs, and its rise is 1000 µs after an LE rise.
   - There are no stray pulses around the SYNC edge.
   - Double strobe: `STROBE 33333 50 1000 10000` gives a second rise 10 ms after the first.
3. Compare the `EV S` / `EV A` differences with the analyzer, to confirm the capture loopback and the 64-bit unwrapping.
4. Run `esp32_clock_sync.py` for 60 s, three times, once with each USB topology (direct root port, through a hub).
5. Then the plan's P0 camera checks: band visible on C922, C930e and generic at 720p30 MJPEG, w = 50 µs, dark room;
   echo-band check; L for each camera.

## Design deviations (versus the plan's rig design)

1. **Command syntax.** The protocol uses plain words (`MODE STROBE …`, `PING …`), as asked for this draft, instead of the
   `<STEP:us>` / `<PROTO:2>` framing. The optional `#tag` echo keeps protocol-2-style matching possible.
2. **One PWM resolution, 2 MHz (0.5 µs ticks), for all three timers,** instead of 10 MHz for LE and 1 MHz for the strobe.
   All three then fit one MCPWM group prescaler, and the strobe and FSIN timers can run up/down.
   Commands take whole µs.
3. **Strobe and FSIN timers count up/down.** A double pulse (4 edges) then fits one cycle using only the operator's two
   comparators. The cost is a maximum period of 65,535 µs, which covers 30 fps (33.3 ms) and 48 Hz FSIN.
4. **No `SWEEP:ppm` command.** For an equivalent-time sweep, set the period directly, for example camera period + 33 µs. Integer µs
   periods give ~30 ppm granularity at 33 ms.
5. **Timer alignment uses a GPIO sync source on spare GPIO4,** with io_loop_back, pulsed by software at START. An IDF 5.x
   soft-sync source binds to a single timer.
6. **Reported timebase is esp_timer** (64-bit µs), as this task asked. The design wanted the capture timer itself. Captured
   edges keep 12.5 ns resolution relative to each other, but their mapping to esp_timer has a fixed offset of about
   the soft-catch bracket (`anchor_half_ns`, expected ≲ 1 µs). The rate is assumed nominal, because both clocks come
   from APB. The once-a-second anchors report any residual drift as `resid_ns`.
7. **Capture channel 1 (GPIO34) is LE *or* FSIN, chosen at compile time** (`CAP1_ROLE`), not switched at run time. Two
   outputs wired to one input would short.
8. **The bar is rendered on the LE *falling* edge** (comparator ISR), not on timer-empty. This ensures the latch has
   closed before the next pattern is shifted in.
9. **The strobe/FSIN phase is relative to the first LE edge after START.** Changing a period or phase needs START,
   which starts a new epoch.
10. Event lines carry an `EV` prefix and times in esp ns, and PONG has a fourth token (`E`/`B`).
11. Not implemented: the event-log parser and the analysis pipeline (`timing/rig/`), the photodiode ADC, the S3 SOF lock,
    LCD_CAM DMA for the bar, and pinning the Arduino loop away from the render core.

## Known limitations and open TODOs

- **Hardware behaviour assumed, not verified.** All of these are taken from IDF headers and the reasoning in the
  comments, and each needs checking with the analyzer:
  - whether an MCPWM sync load fires compare/zero events;
  - the sync-to-timer propagation delay (it shows up as a constant phase error, which the loopback captures);
  - IDF's non-continuous force behaviour on release;
  - `mcpwm_timer_set_period` halving `period_ticks` in up/down mode.
- **Render deadline.** At 100 µs steps, the render is a 10 kHz ISR plus a task switch plus a ~13 µs SPI transfer
  on core 1, alongside the Arduino loop. At 50 µs, `EV E LATE` may appear. This is unmeasured.
- **RX edge capture cost.** It interrupts on every falling edge of incoming serial traffic (up to ~5 per byte). The capture ISRs are
  placed on core 0 to keep that load off the render core.
- **Anchor misattribution.** A soft-catch anchor could take an RX edge's time if a byte arrives within the same
  µs. TODO: reject anchors whose residual jumps by more than a few µs.
- **Counter wrap.** `le_events` is 32-bit, so it wraps after 4.97 days at 100 µs. The Gray counter wraps after 2.9 h; resolve that from host time.
- **Reply serialization.** The host stamps the PONG when its first chunk arrives. When the bridge forwards the reply
  is unknown, which is why two offsets are reported. FTDI bridges need the latency timer set to 1 ms.
- **DevKit reset.** The DevKit may still reset on port open with some drivers. A new `boot_id` means the old clock fit
  no longer applies.
- **Bar bit order** in the driver chain is unverified (see Wiring).
- **Build P0 first.** Check that a 20 mA LED lit for 100 µs is visible to the webcams at gain in the dark, and that the
  strobe band is visible, before building 120 channels.
- **S3 port** (SOF lock, native USB): pins are in the design. The `#error` guard blocks non-ESP32 targets until
  that port exists.
- No RocSync code is used here. RocSync is MPL-2.0 (checked 2026-10-30; see `../docs/rocsync_review.md`), which
  can be combined with skellycam's AGPL if its decoder is reused later.
