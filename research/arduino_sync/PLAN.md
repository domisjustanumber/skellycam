# Arduino FSIN hardware sync — plan of action

Date: 2026-10-25. Scope: skellycam (backend, skellycam-ui, docs), plus the freemocap and freemocap-ui changes it needs.
Source: a review of [MoCapSTR](https://github.com/ZClassified/MoCapSTR) v1.5.x (firmware 1.5.0), research on Arduino Nano/Uno clock accuracy, and a map of skellycam's integration points. Research findings and code claims were checked by AI agents in the same workflow, not by a person: two verifiers checked the clock research (the hardware verifier also saw the UVC trigger report), and two critiques checked the draft against skellycam's code and from a hardware angle (corrected 2026-10-28; was "checked by independent reviewers"). Status: draft, not yet reviewed by a maintainer.

## TL;DR

- **Does clock accuracy matter? Not for keeping the cameras in sync with each other.** One electrical edge drives every camera's FSIN, so any oscillator error hits all cameras identically.
- It matters in two other places:
  1. **Absolute rate.** We fix this by measuring the real rate on the host instead of trusting the nominal fps.
  2. **The InnoMaker ~18–20 ms re-trigger lockout.** We keep a margin by defaulting to 48 Hz.
- **No board in the Nano or Uno family has a TCXO.** Genuine boards use a Murata CSTCE16M0V53 ceramic resonator (about ±0.5% initial, ±1% worst case). Clones may have a ±20–100 ppm crystal or a resonator.
- **Uno R4 and Nano Every are unsupported.** They have no ATmega328P Timer1.
- **The firmware edges come from hardware.** Our firmware "skellysync" generates edges with Timer1 compare outputs on D9/D10, so they are cycle-exact. It also counts pulses and speaks a superset of MoCapSTR's serial protocol. Nothing is copied from the GPL source.
- **Five prerequisite fixes (P1–P5, §5.1) must land before any sync code** (corrected 2026-10-28; was "Four", which left out P5). Each is a bug that exists today:
  1. The config round-trip drops non-hardware fields.
  2. An apply failure kills the backend.
  3. A starved grab records a duplicate frame and kills the backend.
  4. `RecordingTimestampsStats.to_json` is broken.
  5. `pause()` and `unpause()` wait with no timeout, so one camera that never pauses (or never unpauses) hangs the caller.
- **Effort:** v1 is InnoMaker OV9281 on Windows and Linux, about 10 engineer-weeks including a 1-week hardware spike (M0).

---

## 1. Clock accuracy: details

| Clock | Rate error at nominal 48 Hz | Drift per minute | Drift per hour |
|---|---|---|---|
| Resonator, ±0.5% spec | ±0.24 Hz | ±0.3 s | ±18 s |
| Pro Mini, one unit measured warm at −761 ppm | −0.037 Hz | 46 ms | 2.7 s |
| Crystal, 20 ppm | ≈0 | 1.2 ms | 72 ms |
| TCXO, 2 ppm (not on any Nano/Uno) | ≈0 | 0.12 ms | 7.2 ms |

- **Temperature.** The resonator moves about 8.7 ppm/°C (one Pro Mini with a resonator of unspecified make, measured by a third party using the AVR's ±10 °C internal temperature sensor, so approximate; corrected 2026-10-28, was stated as a general resonator figure), and the board warms up after it is plugged in. Pulse indices are therefore assigned **locally** (§4.6), not from one straight-line fit over the whole take.
- **Absolute rate.** It matters only if something uses `frame_index / nominal_fps`, or if other devices (audio, EMG, force plates) are aligned only at the start. The host fits the real rate from its `perf_counter_ns` frame stamps (±30–50 ppm host clock) and from the protocol-2 `<SYNC>` counter. For other instruments, route the same TTL edge into their sync input.
- **Lockout.**
  - +0.5% at 48 Hz gives a 20.73 ms period, which still clears the 20 ms lockout.
  - At a nominal 50 Hz, a fast resonator gives 19.9 ms. Cameras could then reject *different* pulses.
  - M0 measures the real lockout against stream fps, exposure and resolution.
- **Inter-camera skew** (FSIN edge to exposure start) is **unknown and could be up to about 1 ms**. The bridge firmware may gate the trigger to its own timing. M0 and §7 measure it.
- **Baud rate.** 115200 baud at 16 MHz with U2X is +2.1% off. Even combined with a +0.5% (fast) resonator, about +2.6% in total, this stays under the 8N1 limit (corrected 2026-10-28; was "combined with a −0.5% resonator": a slow resonator lowers the total to about +1.6%, so the fast case is the one to check). Keep 115200 for legacy compatibility, and check it on the clone set.

## 2. Scope

| v1 | Later (after v1; corrected 2026-10-28, was "Later (M6)": none of these items is in §9's M6, which is docs, packaging and release only) |
|---|---|
| InnoMaker U20CAM-9281M. Trigger is UVC `CT_FOCUS_AUTO`. FSIN is an opto input, about 19 mA at 5 V, rising edge. | macOS (AVFoundation has no UVC controls); openpnp-capture fork IOKit path |
| Windows DSHOW and Linux V4L2 | Arducam (AE-priority control) |
| ATmega328P @16 MHz Nano/Uno, genuine or clone | In-app flasher, PPS/DS3231 calibration, reference PCB |

**Invariant:** nothing is written to a camera unless the server has set its `trigger_mode` to EXTERNAL. Webcams and groups with sync off behave exactly as today.

## 3. Compatibility and licensing

- **Legacy mode.** Speak MoCapSTR's protocol so existing boxes work unmodified.
  - Commands: `<FPS:N>`, `<PULSE:us>`, `<START>`, `<STOP>`, `<PING>`, `<VERSION>`, plus the unsolicited `<TOGGLE_REC>` from the button.
  - **Each command has a defined terminal line.** `<FPS>` is complete only after `Pulse width (us): P` or `Error:` (the reply is 3 lines, see `trigger_firmware.ino:62-67`).
  - On a timeout, drain the input and resync with PING/PONG before sending anything else.
  - **No commands while pulses run.** The firmware polls `micros()`, so serial handling can shift an edge.
  - The host re-checks `pulse < interval/2` itself.
- **skellysync protocol 2.**
  - Answers `VERSION:2.x.y`, and keeps every legacy command and reply byte for byte, so the MoCapSTR app still works with it.
  - After `<PROTO:2>`: one `OK …`/`ERR …` line per command, with an optional echoed tag (`<SYNC#17>` → `#17 OK SYNC …`).
- **Licensing.**
  - MoCapSTR is GPL-3.0; skellycam is AGPL-3.0-or-later.
  - **We copy nothing.** We reimplement from a written protocol spec, `skellycam-docs/docs/technical/sync-protocol.mdx`. The implementer works from that spec, not from the MoCapSTR source, and we do not ship their `.hex`.
  - Not legal advice.

## 4. Firmware: `firmware/skellysync/skellysync.ino`

**Build guard**
- `#if !defined(__AVR_ATmega328P__) || F_CPU != 16000000L` → `#error`.
- `VERSION` and `STATUS` report the MCU signature and F_CPU.
- One `.hex`, built in CI with `arduino-cli compile`.
- No watchdog: old ATmegaBOOT gets stuck in a WDT reset loop.

**Timing**
- Timer1 fast PWM **mode 14** (TOP = ICR1), outputs **OC1A on D9 and OC1B on D10**. Mode 15 would use OCR1A as TOP and lose D9.
- Non-inverting: the edge rises at BOTTOM. High time is OCR1x+1 ticks, so set `OCR1x = ticks−1` and enforce `2 ≤ ticks ≤ TOP/2`.
- **Single source of truth for the period.** The host computes it in `skellycam/core/sync_device/timer_math.py` and sends `<PERIOD:p,ticks>`. The firmware only validates and echoes it.
  - `<RATE_MILLIHZ:48000>` is a convenience: the firmware picks the smallest p in {8, 64, 256, 1024} with ticks ≤ 65536.
  - Legacy `<FPS:N>` maps to N×1000 mHz.
  - Quantization: 48 Hz → 41667 ticks at p = 8 (−8 ppm).
- **RATE, PERIOD and PULSE are accepted only while stopped or armed.** While running, protocol 2 returns `ERR busy`. This avoids mid-run prescaler glitches and one-off short periods.
- **Counter.**
  - The `TIMER1_COMPA` ISR (the falling edge) increments a 32-bit `n` and advances a 64-bit `tick_base` by the period that just ended.
  - `mcu_ticks = tick_base + TCNT1`, read under `cli()` with a check for a pending interrupt flag.
  - Spec semantics: `n` counts *completed* pulses, so a read during an active pulse excludes that pulse.
- **ARM.**
  - Prescaler off; COM1x = 0; PORTB1/PORTB2 = 0.
  - Clear the OC1x latches by briefly entering Normal mode with FOC1A/FOC1B and COM set to clear.
  - Then select mode 14, load ICR1/OCR1x, and enable COM1x.
- **START** (protocol 2): set TCNT1 = TOP, so the first edge comes within one tick; set n = 0; reply `OK START`. Legacy START keeps MoCapSTR's semantics.
- **STOP and `BURST:N`** are decided in COMPA, so there is almost a full period of slack:
  - On the target pulse, set COM1x = 0 (pins already low), then stop CS1x.
  - Reply `OK STOP n=<total>`.
- **`<SYNC>`** → `OK SYNC n=… t=<hex> top=… p=…`. Safe while running, because the edges come from hardware.
- **`<STATUS>`** → run state, n, period, pulse width, firmware version, MCU signature.

**Other features**
- **Serial:** a fixed 48-byte `<…>` buffer, no `String`, every reply ≤ 60 bytes.
- **Button on D4:** debounced, sends `<TOGGLE_REC>`.
- **D2 legacy mirror:** set by software in the ISR (a few µs of jitter), for **one camera only**. A 4-way MoCapSTR splitter needs a buffer.
- **LED bar** (`<LEDBUS:1,offset_us>`): Timer2, armed from COMPA, writes `n mod 256` to 8 LEDs (A0–A5, D11, D12) at a configurable offset. OCR1B is already busy as the D10 output. The offset is chosen *after* the M0 FSIN-to-exposure sweep.
- **No EEPROM settings and no autostart.** The host always re-sends PROTO, PERIOD, PULSE and ARM after every open.

**Electrical (docs)**

| Topology | Max cameras |
|---|---|
| Direct from ATmega pin (about 19 mA each; pins are characterised at 20 mA) | **1 per pin**, so 2 cameras on D9 + D10 |
| ULN2803/ULN2003 low-side sink: FSIN+ to +5 V, FSIN− to the output (about 13 mA) | 7–8 |
| 74ACT541 (±24 mA per output), series R sized to budget (corrected 2026-10-28; was "74AHCT541 or 74ACT541": the 74AHCT541 is rated only ±8 mA at 5 V, too little for a ~19 mA FSIN) | 4–6 |
| One NPN or N-MOSFET per camera | any |

- Not a 74HCT541: its outputs are rated ±6 mA, with a 70 mA package limit.
- Add a 100 mA polyfuse on USB 5 V.
- For buffered builds, use a powered hub or a separate 5 V supply.
- The opto isolation means no ground loop.

## 5. Backend (skellycam)

### 5.1 Prerequisite fixes (separate PRs, each fixes a bug today)

| # | Fix | Where |
|---|---|---|
| P1 | Copy the non-hardware fields (`use_this_camera`, `capture_fourcc`, `writer_fourcc`, later the trigger fields) from the requested config into the extracted config. Add a round-trip unit test. | `opencv_extract_config.py:35-47`, `opencv_apply_config.py:87-98` |
| P2 | `check_for_new_config` catches `FailedToApplyCameraConfigurationError`, publishes the prior config with an `apply_error` field, and clears `updating`. | `check_for_new_config.py:33-41`. Today: `opencv_apply_config.py:99-103` → kill. |
| P3 | Starvation-tolerant grab via a `GrabResult` (OK / NO_FRAME / DEAD). On NO_FRAME, `continue` so the pause/close/config checks still run; never publish or record a duplicate. In FREE_RUN, 30 consecutive failures raise. Move `frame_durations_seconds` out of the retry loop. | `opencv_camera_loop.py:72-86`. Today the duplicate frame → `video_recorder.py:149-157` raises → `opencv_camera_loop.py:122` calls `kill_everything`. |
| P4 | Fix `RecordingTimestampsStats.to_json`: recarrays via `.tolist()`, RecordingInfo via `model_dump(mode="json")`. | `recording_timestamp_stats.py:123-143` |
| P5 | `pause(timeout_s=3)` and `unpause(timeout_s=3)`. On timeout, reset `should_pause=False` on all cameras, then raise. | `camera_orchestrator.py:58-78` |

### 5.2 New package `skellycam/core/sync_device/`

| File | Contents |
|---|---|
| `sync_device_config.py` | `SyncDeviceConfig` (`enabled`, `port_key`, `rate_hz=48.0`, `pulse_width_us=500`, `toggle_rec_button`), and `SyncDeviceState` (connection, firmware family and version, run/armed, commanded/actual/measured Hz, `needs_reenable`, per-camera trigger state, `last_error`). |
| `serial_protocol.py` | Pure framing and parsing for legacy and protocol 2, including the per-command terminal lines. |
| `sync_serial_connection.py` | pyserial wrapper. **Assumes reset-on-open.** Reads and discards until the banner arrives (timeout 3.5 s, to cover old ATmegaBOOT). Sends PING only after the banner, or after a silent timeout. Always re-sends the full config. Request/response under a lock; a reader thread routes unsolicited lines (`<TOGGLE_REC>`, or a banner meaning a reset). |
| `sync_device_manager.py` | **Owned by `CameraGroupManager`**, so CameraGroup hooks, `to_state_dict` and freemocap reach it without an `app` handle. Async API: `connect`, `enable`, `disable`, `snapshot`, `to_state_dict`. |
| `rate_estimator.py` | Local pulse-index assignment and a sliding-window rate fit (§5.6). |
| `timer_math.py` | Prescaler and TOP math, mirrored by a C header that is unit-tested with host gcc in CI. |

- **Threading.** The serial worker is a daemon `threading.Thread` in the main process, following the WorkerRegistry heartbeat/monitor threads (`worker_registry.py:61-75`). It is not created through `create_worker`.
  - Its loop catches every exception into `state.connection = ERROR` and never touches `global_kill_flag`.
  - `to_state_dict` is wrapped in try/except, because `websocket_server.py:334-337` kills the app on any exception from it.
- **Detection** (`core/device_detection/detect_sync_devices.py`, next to `detect_microphone_devices.py`):
  - `comports()` only; ranked by VID (0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4).
  - **Never opens a port.**
  - Port key: `serial_number` when present, otherwise VID:PID plus pyserial `location`, or `/dev/serial/by-path` on Linux. CH340 boards have no iSerial.
  - "Identify" refuses to run on the currently connected port, because re-opening it resets the board.

### 5.3 Config and ownership of the trigger fields

- `CameraConfig` gains:
  - `trigger_mode: TriggerMode(str, Enum) = FREE_RUN`, with values FREE_RUN and EXTERNAL_FSIN_UVC_FOCUS. A `str` enum, so `recording_info.py:79-86` `json.dumps` works.
  - `trigger_rate_hz: float | None`.
  - `trigger_state`, reported back: FREE_RUN / PENDING / VERIFIED / FAILED.
- **The trigger fields are server-owned.** `create_or_update_camera_group` and `create_and_start_camera_group` overwrite them from SyncDeviceManager, whatever the client sent. **Group create always forces FREE_RUN.** Clients post full configs from both UIs (`camera_router.py:113-124`, `cameras-thunks.ts:107-115`, freemocap-ui `server-urls.ts:49`).
- In the UI zod schema (`cameras-types.ts:35-61`) the fields are optional and read-only. They are excluded from `persistAllCameraSettings` and copy-to-all. The same applies to the freemocap-ui camera slice.
- **Sync binds to the active group.** Multiple groups are effectively impossible today (`camera_group_manager.py:75-100`). When a group closes, set `needs_reenable`; the user re-confirms on the next create.

### 5.4 Camera control (in the camera process, same `VideoCapture`)

- `_apply_trigger_mode(cap, config)` runs inside `apply_camera_configuration` when `trigger_mode` changed.
  - **EXTERNAL.** Manual exposure first (on Linux, `auto_exposure=1` before `focus_automatic_continuous=1`, per the vendor), then `AUTOFOCUS=1`, `FOCUS=0`, then read back. Returns `trigger_state=PENDING`; never raises.
  - **FREE_RUN.** `AUTOFOCUS=0`, then read back.
  - **macOS** returns FAILED with a reason.
- **Linux exposure conflict:** skip the forced auto-exposure (`opencv_apply_config.py:29-35`) when `trigger_mode != FREE_RUN`.
- **Windows fallback.** Only if M0 shows that DSHOW's `Flags_Auto | Flags_Manual` write is ignored: a short-lived `CAP_MSMF` handle matched by device path. It is gated behind a setting.
- **Exposure guard.** Refuse EXTERNAL if exposure + readout > 0.8·T.
- **Stream fps** is fixed at open (`create_cv2_video_capture.py:57-58`). Framerate application on update is disabled (`opencv_apply_config.py:62`). Changing it means re-creating the group. v1 uses the camera's maximum MJPEG fps; a "trigger rate" stream fps is offered only if M0 shows it is safe for the lockout.
- **Buffers.** In trigger mode use 2–4 V4L2 buffers and never drain to the latest frame. On V4L2, arrival time is `CAP_PROP_POS_MSEC` (the driver's monotonic stamp). DSHOW ignores BUFFERSIZE (M0 item).
- **Revert on every exit.** In the `finally` of `opencv_camera_worker_method.py:73-78`, before `release()`: if the camera was EXTERNAL, set `AUTOFOCUS=0` and clear its recovery entry. This covers close, the kill flag and loop exceptions; neither lifespan closes groups gracefully (`app.py:59-67`, freemocap `app.py:355-363`).
- **Hard-kill recovery.**
  - `get_default_skellycam_base_folder_path()/triggered_cameras.json`, keyed by `camera_id`.
  - In `create_cv2_video_capture`, set `AUTOFOCUS=0` before the `read()` at `:71` if the camera is listed, *or* if the first read fails and its name or VID:PID is on a known trigger-capable list.

### 5.5 Loop, orchestrator and sequencing

- **Starvation.** `trigger_starved` is measured only from time spent *inside* `grab()` (threshold `max(3T, 250 ms)`), never from time spent idle in the lock-step gate (`camera_orchestrator.py:105-109`). Lock-step stalls the healthy cameras too, so only the camera actually inside `grab()` starves.
- **Frame-rate reset.** Disable `check_framerate_reset` (`opencv_camera_loop.py:150-170`) in trigger mode, and replace its hard-coded 30 with `config.framerate`.
- **Container fps.** In trigger mode, `handle_recording_updates.py:39-43` passes `trigger_rate_hz`.

**Enable sequence** (`PUT /sync/device`). Returns 409 while any camera is recording.

| Step | Action |
|---|---|
| 1 | Group open and streaming in FREE_RUN. The hard blocker for triggering first is the `read()` check in `create_cv2_video_capture.py:71-81`. |
| 2 | Open the port (reset expected), wait for the banner, negotiate PROTO, send PERIOD/PULSE/ARM, check every ack. |
| 3 | `<START>`: pulses run; free-running cameras ignore them. |
| 4 | Server-side `update_camera_settings` with EXTERNAL for every camera, then `await_extracted_configs`. If any `apply_error` or FAILED: roll back. |
| 5 | **Verify by removing pulses, not by measuring rate.** Lock-step gating and BUFFERSIZE make a free-running camera look triggered. The orchestrator pauses the group; the paused loop runs a *probe* (direct `cap.grab()`, counting into a new `CameraStatus.probe_frames`, leaving `frame_number` untouched). Manager sends `<STOP>`. After 2T, every count must stay 0; a free-running camera keeps producing. Protocol 2: `<BURST:10>` → every count = 10 (tolerance set in M0). Legacy: `<START>` → counts resume. Then START and unpause. |
| 6 | Any failure → all cameras to FREE_RUN, `<STOP>`, report per-camera reasons. |

- **Disable.** Cameras to FREE_RUN (verify frames arrive), `<STOP>` (log n), close the port.
- **Rate change while running.** Disable, then re-enable at the new rate.
- **During a session**, pulses run continuously. The +3-frame stop window (`camera_group.py:192`, `:231`) and finalize both need frames.
- **Recording start.** Inside the existing `pause()`: `snapshot()` (protocol 2: `<SYNC>` with host send/receive ns; legacy: settings only), attached to `RecordingInfo.sync.start`.
- **Recording stop.** The stop snapshot and computed fields are attached to the RecordingInfo returned by the cameras (`camera_group.py:354-361`) *before* `RecordingFinalizer.create`.

### 5.6 Timestamps, metadata and validation

- **Pulse index.** `round(Δt / T_local)` between consecutive good frames, with T_local from a 10 s sliding-window fit. The global slope is reported only as the mean rate.
- **Grab classification.** A grab whose `post_grab − pre_grab` is near zero (the frame was already buffered while the camera waited in the gate) gives only an upper bound on arrival time. It is excluded from the spread test and the rate fit.
- **Alignment monitor.** A main-process task reads multiframes in order via `get_images_by_frame_number` (`camera_group_shared_memory.py:143`) and tolerates ring overwrite. Spread > T/2 between classified arrivals → `alignment_warning`. v1 is detect-and-warn; auto-resync is M3 opt-in.
- **CSV.** Append `trigger.pulse_index`, `trigger.expected_timestamp.ns` and `trigger.residual.ms` at the end of `CAMERA_TIMESTAMPS_CSV_ROW_DTYPE`. `FRAME_METADATA_DTYPE` stays untouched.
- **`RecordingInfo.sync`** holds: firmware, port key, commanded/actual/measured Hz, counter-derived Hz, pulse width, pins, start/stop snapshots, `expected_pulses`, frames per camera, alignment violations, starved intervals, `terminated_reason`.
- **Persisting it.** `recording_finalizer.py:55` saves before timestamps are processed (`:57`), so call `save_to_file` a second time after processing.
- **Validation check 5.** Identical `pulse_index` per frame across cameras, consecutive indices, and |local residual| < T/4. A failure **warns** and sets a stats flag; it does not raise.

### 5.7 Failure handling

| Failure | Detection | Response |
|---|---|---|
| Board unplugged mid-recording | Serial error, or in-grab starvation for more than 1 s | `orchestrator.force_finish_recording`: each camera closes its recorder on its next pass. `terminated_reason="sync_device_lost"`, and the finalizer downgrades checks 2/3 (frame counts can differ by ≤ 1 under lock-step) to warnings with per-camera counts. Cameras go to FREE_RUN. Reconnect by port key; the user re-confirms enable. |
| Reset or brown-out; another process opens the port (IDE, MoCapSTR, ModemManager) | Unexpected banner; `SYNC` shows a counter reset | Same as unplugged |
| One camera gets no trigger | Only that camera starves inside `grab()` | "Check FSIN wiring/polarity"; force-finish if recording |
| Slip or straddle | Alignment monitor; check 5 | Warn and count |
| Rate above lockout | Measured ≈ commanded/2 | Refuse until the rate is lowered |
| Not a sync device / port busy / `EACCES` | No VERSION/PING within 3.5 s / `SerialException` | Clear message; on Linux, name `dialout`, brltty (CH340), and a ModemManager udev rule `ENV{ID_MM_DEVICE_IGNORE}="1"` |

### 5.8 Packaging

- Add `pyserial>=3.5` to `pyproject.toml` and regenerate `uv.lock`.
- Smoke-test `list_ports` in frozen builds; add the `serial.tools.list_ports_*` hiddenimports in `skellycam.spec` if detection comes back empty.

## 6. API and UI

| Endpoint (`api/http/sync/sync_router.py`, `/skellycam/sync`) | Notes |
|---|---|
| `GET /sync/detect` | Mirrors `/camera/microphone/detect` |
| `POST /sync/identify {port_key}` | Refused on the connected port |
| `PUT /sync/device` | Runs §5.5; 409 while recording; 422 with per-camera reasons |
| `GET /sync/status` | Full state, including `pulse_count` |
| `POST /sync/test/burst {n}` | Not while recording |

- **APP_STATE.** `CameraGroupManager.to_state_dict()` adds `sync_device` with low-churn fields only: measured Hz rounded to 3 decimals, and no `pulse_count`, which would force a full resend every second.
- **Events.** `WebsocketMessageType.SYNC_DEVICE_EVENT`: `toggle_rec_button`, `device_lost`, `device_reset`, `camera_starved`, `alignment_warning`.
- **UI.**
  - `SyncDevicePanel.tsx` between `CameraConfigSidebarPanel` and `RecordingInfoPanel` (`LeftSidePanelContent.tsx`): port selector modelled on `MicrophoneSelector`, rate (default 48; warn above 48; hard error at 50 or more; shows the `timer_math` actual rate), pulse width, enable switch, a "re-enable" prompt when `needs_reenable` is set.
  - No group selector.
  - Per-camera Triggered / Free-run / Failed chip.
  - Record is disabled during transitions.
- **`TOGGLE_REC`** is opt-in. It dispatches the normal recording thunk.

## 7. FreeMoCap downstream

- Add `sync_router` to `SKELLYCAM_ROUTERS` (`freemocap/api/routers.py:17-19`).
- Relay `SYNC_DEVICE_EVENT` in freemocap's own `websocket_server.py`.
- Add the sync panel and read-only trigger fields to freemocap-ui's forked camera slice (`cameras-slice.ts`, `cameras-selectors.ts`).
- `get_recording_framerate` (`recording_framerate.py`): prefer `{rec}_info.json → sync.measured_rate_hz`, then the `_stats.json` trigger block (after P4), then the existing CSV median.
- Optional: warn before reconstruction when `alignment_violations > 0`, or trim to the minimum frame count when `terminated_reason` is set.
- freemocap pins skellycam `main`, so this work must merge to main first.

## 8. Testing

**Unit tests (CI)**
- `FakeSyncSerial` emulating legacy 1.5.0 and protocol 2: a reset banner on open, 3-line FPS replies, late replies, an unplug, a spontaneous reset, `TOGGLE_REC`.
- Tests:
  - per-command terminal lines and resync after a timeout;
  - no legacy commands while running;
  - `ERR busy` for RATE while running;
  - `global_kill_flag` never set;
  - port-key fallback with no serial number;
  - `timer_math` matching the C header for 1–240 Hz;
  - `trigger_mode` survives `apply_camera_configuration`;
  - client-sent trigger fields are overridden;
  - an apply exception does not kill the backend;
  - a fake `grab()` failing N times gives no duplicate and correct starvation;
  - `rate_estimator` with a 50–100 ppm warm-up ramp, drops and a one-frame slip;
  - check 5 flags a straddle.

**Hardware-in-the-loop** (genuine and CH340 Nano, ULN2803, 4× InnoMaker, Windows and Ubuntu)
1. Enable/disable ×50.
2. Lockout sweep.
3. 30-minute take at 48 Hz with the LED bar: 0 mismatches.
4. Unplug mid-take.
5. Kill and relaunch.
6. Legacy board works unmodified.
7. `BURST:1000` gives 1000 analyzer edges and `n=1000`.

**Measurements**
- **Logic analyzer** on D9, D10 and D2 during USART traffic and `SYNC`/`STATUS` spam: D9/D10 jitter stays at oscillator level; only D2 and the LED bar jitter.
- **FSIN-to-exposure skew:** a delayed 50 µs flash, swept 0–25 ms around the edge (coarse, then 20 µs steps), per camera.

## 9. Milestones

| ID | Scope | Size | Exit |
|---|---|---|---|
| M0 | Spike. Same-handle DSHOW AUTOFOCUS write and read-back. Does the DSHOW open block in trigger mode? Does Windows restore AUTOFOCUS on replug? Grab-vs-retrieve blocking and the DSHOW latest-sample behaviour. Lockout vs stream fps, exposure and resolution. Skew sweep. Loop period at 48 Hz × 4 cameras while recording (synchronous encode). Slip rate under load with the LED bar. V4L2 select-timeout env behaviour. | 1 wk | Go/no-go per item |
| M1 | P1–P5 prerequisite PRs | 1.5 wk | Unit tests; webcams unaffected |
| M2 | Firmware 2.0, serial driver and fake, detection, protocol spec | 1.5 wk | Analyzer tests and BURST test |
| M3 | Trigger config, server ownership, `_apply_trigger_mode`, enable/verify/rollback, worker-finally revert, recovery, force-finish | 2 wk | HIL 1, 4, 5 |
| M4 | Metadata, local pulse index, alignment monitor, check 5, `save_to_file` order | 1.5 wk | HIL 3: 0 mismatches |
| M5 | API, APP_STATE, events, skellycam-ui and freemocap-ui panels, freemocap router, relay and framerate | 2 wk | End-to-end in both apps on Windows and Linux |
| M6 | Docs (wiring, flashing incl. `arduino:avr:nano:cpu=atmega328old`, Linux udev/brltty, CH340 drivers, optional reset-disable capacitor), packaging, release | 0.5 wk | Release candidate |

## 10. Risks

1. **The DSHOW trigger control may not work on the streaming handle.** Mitigation: the MSMF fallback; worst case, v1 ships Linux-first.
2. **The lockout and skew may be set by bridge firmware.** Mitigation: the M0 sweeps set the defaults, and the UI derives its cap from that data.
3. **Synchronous encode with 4 cameras at 48 Hz may exceed T and cause slips.** Mitigation: the M0 measurement, more buffers, and pulse-index-keyed assembly in v2.
4. **Clone USB-serial quirks.** Mitigation: assume reset-on-open, banner wait, port-key fallback.
5. **Overloaded FSIN wiring.** Mitigation: documented current budget and the ULN reference design.
6. **API churn** from the desired-state refactor. Mitigation: build `/sync` as PUT-style from the start.

## 11. Open questions

1. Is InnoMaker-only v1 on Windows and Linux acceptable?
2. Should P1–P5 ship now as standalone fixes?
3. Should the firmware live in this repo or in a separate `skellysync` repo?
4. Should `TOGGLE_REC` be opt-in by default?
5. Should auto-resync stay off until the LED-bar data supports it?
6. Should we contact ZClassified about co-standardizing protocol 2?

## Corrections applied

- **Config round-trip:** added P1 because `extract_config_from_cv2_capture` drops `trigger_mode` and the fourccs.
- **Server ownership:** trigger fields are now server-owned, forced to FREE_RUN on create, and excluded from UI persistence and copy-to-all, because clients post full configs.
- **Apply failures:** added P2 containment and made `_apply_trigger_mode` return state instead of raising, because apply exceptions kill the backend and the rollback could never run.
- **Verification:** replaced the frame-interval check with a pulse-removal probe while paused (STOP gap plus `BURST:N`). Lock-step gating, BUFFERSIZE and a "trigger" stream fps made the interval check meaningless, and loop frames don't flow while `updating` is set.
- **Starvation:** now measured only inside `grab()`, and force-finish goes through `terminated_reason` with checks downgraded to warnings, because lock-step stalls healthy cameras and the finalizer raises on a 1-frame difference.
- **Shutdown:** trigger revert moved to the camera worker `finally`, and SyncDeviceManager is now owned by CameraGroupManager, because there is no graceful lifespan close.
- **Metadata:** a second `save_to_file` after timestamp processing, the stop snapshot attached before `RecordingFinalizer.create`, and validation is check 5 and warns. `_info.json` was written too early, and the cameras' RecordingInfo copies must match.
- **Downstream framerate:** added P4 (`to_json` fix), and freemocap now reads `_info.json` first, because `_stats.json` is unreliable today.
- **freemocap wiring:** added the router registration, websocket relay and forked-slice work, which the draft missed.
- **Stream fps:** fixed at open; changing it needs a group re-create, because `set(FPS)` on update is disabled.
- **Alignment monitor:** now reads frames in order from shared memory and excludes instant-return grabs, because gating skews grab timestamps.
- **Groups:** sync binds to the active group, the selector is dropped, and `needs_reenable` is added, because multiple groups are effectively impossible.
- **Recording guard:** PUT `/sync/device` returns 409 while recording.
- **Pulse counter:** now counts in COMPA with a `tick_base`, and BURST and STOP are decided in COMPA, because the TOV1 count and stop logic were racy and wrong after rate changes.
- **Live changes:** RATE and PULSE are refused while running, because live prescaler or period changes glitch and risk the lockout.
- **LED bar:** moved to Timer2 with a configurable offset, because OCR1B is busy and the exposure window is unmeasured.
- **Electrical:** fixed to 1 camera per pin; the buffer is now ULN2803 or 74ACT541 instead of 74HCT541 (6 mA) (corrected 2026-10-28; was 74AHCT541, which is rated only ±8 mA), and D2 is single-camera only.
- **Serial open:** reset-on-open is the default with a 3.5 s banner wait, the full config is always re-sent, and EEPROM autostart is dropped, because DTR suppression is unreliable.
- **Port keying:** falls back to VID:PID plus location, with Linux brltty and ModemManager docs, because CH340 boards have no serial number.
- **Legacy parsing:** the 3-line FPS reply and per-command terminal lines are handled, timeouts resync with PING, and protocol 2 gets tags.
- **Pulse index:** assigned locally with a sliding window, because resonator thermal drift breaks a single fit.
- **Buffers:** 2–4 V4L2 buffers and the driver timestamp in trigger mode, because BUFFERSIZE=1 silently skips pulses.
- **Lockout sweep:** now covers stream fps, exposure and resolution, and an exposure guard was added.
- **ARM details:** OC1x latch clearing, `OCR=ticks−1`, and the real reason for mode 14.
- **Firmware build:** added the `#error` guard, a single hex, the old-bootloader FQBN, and no watchdog.
- **Hard-kill recovery:** keyed by `camera_id` under `skellycam_data`, plus a name and VID:PID heuristic.
- **Clock table:** the −761 ppm row is relabelled Pro Mini, R4 and Every are marked unsupported, and skew is now "unknown, up to ~1 ms" with a 0–25 ms sweep.
- **Naming and precedent:** `RATE_MHZ` renamed `RATE_MILLIHZ`, the host is now the source of truth via `<PERIOD>`, and the threading precedent cites the WorkerRegistry threads instead of AudioRecorder.
- **Small fixes:** `TriggerMode` is a `str` Enum, `to_state_dict` is defensive, `pulse_count` is out of APP_STATE, pause timeouts reset `should_pause`, and `frame_durations` moved out of the retry loop.
- **Sequencing rationale and citations:** the hard blocker is `create_cv2_video_capture.py:71-81`, not the drain loop. Line references fixed: `opencv_camera_loop.py:122`, `camera_group.py:192`/`:231`, and `recording_framerate.py`.
- **Missing topics added:** baud error, power and grounding, a second process opening the port, Identify on the live port, Linux control order, and counter semantics in the spec.