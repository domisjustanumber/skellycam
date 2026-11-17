# FINDINGS: audio-to-video sync in skellycam playback (desk test, 2026-11-15)

For Dom's 2026-11-15 instruction: "for the audio tests — ensure you also test how the audio file syncs in playback in skellycam, as this is the most important playback type. Being slightly off in VLC is ok."

**Provenance.** A sub-agent ran this on 2026-11-15, about 13:25–14:30 local, on Windows 11 with an i7-14700K and a 60 Hz display (rAF median 16.7 ms, measured).
- Only synthetic media were used. No camera or microphone was opened, and no device or driver settings were touched.
- WebAudio output went to the default device through a gain of 0, so nothing was audible. The element probe played a silent WAV.
- No source files in skellycam, skellycam-phase1 or freemocap were changed, and there were no git operations.
- skellycam-ui itself was not run, because it has no audio path to test (§1). A harness of the planned design was run instead.

**Labels:** [M] measured here (result file named) · [C: path:line] code read · [P: path] prior evidence · [K] knowledge, not verified · [D] derived arithmetic.

**Versions** [M]:
- Electron 35.7.5 (Chrome 134.0.6998.205), the skellycam-ui `node_modules` binary used read-only.
- Electron 45.2.3 (Chrome 156.0.8078.80), the existing scratch install.
- Python 3.12.13; PyAV 19.0.2 (libavformat/libavcodec 63.1.102, libopus 1.6.1 [P: audio_skellycam/codecs.json]); numpy 2.2.6; soundfile 0.13.1; pillow 11.3.0 (check script only); uv 0.13.7.
- No npm installs.
- AudioContext at 48 kHz: `baseLatency` 10 ms; `outputLatency` 52 ms (E35) / 42 ms (E45) [M].

**Files.**
- Scripts: `research/skellycam_recording/recording_upgrade/scripts/audio_single_file/skellycam_playback/` (`gen_take.py`, `check_take.py`, `run.py`, `analyse.py`, and `electron/main.cjs`, `player.html`, `player.js`, `tap.js`, `elprobe.js`).
- Results: `results/audio_single_file/skellycam_playback/` (`short.json/.csv`, `long.json/.csv`, `naive.json/.csv`, `nofit.json/.csv`, `cont.json/.csv`, `elprobe.json`, `takes.json`).
- Media and raw output (rebuildable): `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file\skellycam_playback\` (`short\`, `long\`, `raw\`).

## 1. skellycam's playback today, and the intended design

**Today, identical (ignoring CRLF) on skellycam-phase1 `dom/capture-recording-phase1` and on skellycam `remotes/upstream/development-streaming`:**
- **No audio playback.**
  - The only media element is `<video … muted …>` [C: skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:648-656, `muted` at :652].
  - There is no `AudioContext`, `AudioDecoder`, `decodeAudioData` or `new Audio` anywhere in `skellycam-ui/src` [C: grep].
  - The only audio UI is the mic selector [C: src/components/recording-info-panel/recording-subcomponents/MicrophoneSelector.tsx].
- **Clock:** the first video is the "leader". The rAF loop reads `leader.currentTime` and takes `frame = currentTime × fps` [C: SyncedVideoPlayer.tsx:367-378]. Followers are re-seeked when more than 2 frames off [C: :417-431].
- **Seeking:** `el.currentTime = frame / fps` on every video [C: :332-340, scrub drag :492-508].
- **Index vs real time:** the player maps frames by index/fps, not by real time. The sidecar timestamps are used only for the overlay text [C: :281-309; loaded in src/contexts/PlaybackContext.tsx:69-71].
- **Audio in recordings:** `video_audio_remuxer.py` would mux WAV into each MP4 as AAC with one start offset [C: skellycam/core/recorders/video_audio_remuxer.py:86-101, AAC :93]. That call is commented out [C: skellycam/core/recorders/recording_finalizer.py:63, same on development-streaming].
- **Phase-1 vs streaming:** phase-1 differs only in the backend route, which adds a `.web.mp4` transcode [C: diff of skellycam/api/http/playback/playback_router.py].

**Intended design (plan):**
- The canvas player replaces `<video>`. It uses one master clock, picks the PREV frame by sidecar time, and fetches JPEG bytes by Range + `ImageDecoder`, over Electron `protocol.handle` [P: research/CAPTURE_AND_RECORDING_PLAN.md WP 1.9].
- Audio is decoded with WebCodecs `AudioDecoder` on packets fetched by Range from a packet table. While audio plays, the master clock follows the audio output. Scrubbing is muted. `<audio>` is the fallback [P: plan §2.8 "Player, one path for both"; audio_skellycam/FINDINGS.md §4.4].
- The design §4.4 gives:
  - clock = t(n_heard) from `getOutputTimestamp().contextTime`;
  - decode a window of −2 s / +10 s;
  - `AudioBufferSourceNode`s scheduled back to back;
  - an 80 ms Opus pre-roll after a seek;
  - not `decodeAudioData` for long files.
- Test plan TP4 B1: flash + click sync at the start, after 30 min and after 20 seeks, within 1 frame [P: plan TP4].

## 2. Harness and method

**Player** (`electron/player.js`, faithful minimal version of the plan; not skellycam-ui):
- **Video:**
  - 3 cameras; per frame, a Range fetch at the sidecar offset → `ImageDecoder` → `drawImage` to a 320×240 tile.
  - The frame drawn is PREV(t): the last frame whose sidecar `arrival_ns` ≤ t, found by binary search.
  - Prefetch 4 frames ahead; at most 8 cached `VideoFrame`s, each closed when evicted.
  - Transport: the hand-written single-range handler of the T-S5 study, through `protocol.handle` [P: scripts/range_transport/electron/main.cjs].
- **Audio engines:**
  - **buf:** whole file → `decodeAudioData` → `AudioBufferSourceNode.start(when, offset)`.
  - **wc (the plan's design):**
    - Index the file at load:
      - WAV: data offset from the header;
      - FLAC: scan for frame syncs, checking the CRC-8 and the frame number;
      - Opus fMP4: walk the `moof`/`tfdt`/`trun` boxes. The `OpusHead` description is built from `dOps`.
    - Decode 1 s chunks, 3 s ahead. WAV PCM goes straight into an `AudioBuffer`; FLAC and Opus go through WebCodecs `AudioDecoder`.
    - Chunks are scheduled back to back at exact sample times.
    - Opus seeks get 80 ms of pre-roll. Output is placed by the decoder's output timestamps, with input timestamps on the untrimmed timeline.
  - **el:** `<audio src>` through the same scheme → `MediaElementSource` (needed for the measurement tap).
- **Master clock (host seconds):** t = map(n), where n is the sample being heard.
  - buf/wc, clock `out` (the plan): n = n0 + (contextTimeAt(rAF timestamp) − when)·48000, with contextTimeAt from `getOutputTimestamp`.
  - Variant `naive`: `ctx.currentTime` instead.
  - el: n = `currentTime`·48000 (today's leader pattern).
  - Variant `ellat`: (`currentTime` − `ctx.outputLatency`)·48000.
- **map:**
  - `fit` = the CSV footer fit, t = t0 + (n − off − n0)·1e9/rate_hz;
  - `nofit` = first-row `adc_ns` + nominal 48 kHz;
  - `off` = CSV `file_sample_offset` (312 for pre-skip 0, else 0).
- **Play:** audio starts 100 ms ahead (`when` aligned to a sample). Until then the clock holds at the seek target.

**Synthetic takes** (`gen_take.py`; self-checked by `check_take.py`: barcodes, flashes and every click exact, [M]):
- **Short take, 60 s, 3 cameras.**
  - MJPEG MKV with index pts (time base 1/30) and one CSV sidecar per video: `index,frame_number,arrival_ns,byte_offset,byte_size`.
  - Real rates 29.97, 30·(1 + 50 ppm) and 25.7 fps, so index pts are wrong by design.
  - Arrival jitter N(0, 1.5 ms) plus 1 % spikes of 6–15 ms; 0.3 % of frames dropped.
  - Each frame carries a 20-bit barcode of its index. A white flash comes about once a second.
- **Audio, mono 48 kHz.**
  - Device clock +10 ppm against the host (fitted: +9.53 ppm on the 60 s take, +10.0007 ppm on the 60 min take; fit error at the end ≤ 0.01 ms [M, takes.json]).
  - A one-sample click at the host time of each camera-0 flash frame.
  - Four files from one source: WAV `rf64=auto`; native FLAC `frame_size=1024`; Opus 128 kbit/s fragmented MP4 (one fragment per packet, pre-skip 312); and the same bytes with pre-skip patched to 0 (`opus/preskip0.patch`).
  - Each has its own `<file>.csv` (§3.1 layout of the WAV/FLAC findings, plus a fit footer). The ps0 CSV says `file_sample_offset=312`.
- **Long take, 60 min, 1 camera:** 107,559 frames, 3,598 clicks.

| | WAV | FLAC | Opus fMP4 |
|---|---|---|---|
| Long-take size | 346 MB | 193 MB | 74 MB |
| Notes | | | 180k fragments; no `edts`; `tfdt` from 0 includes priming; `dOps` PreSkip 312 [M] |

**Measurement:**
- **Click output time A:** an AudioWorklet tap just before the destination reports the context frame of each click peak. A = the performance time at which that frame is output, from `getOutputTimestamp`.
- **Flash draw time V:** the rAF timestamp of the tick that drew the camera-0 flash frame, with the barcode read back from the decoded image.
- **av_ms = A − V.** < 0 means audio is heard before the flash frame is drawn.
- **clock_ms = A − P\*,** where P\* is when the player's clock crossed the flash frame's sidecar time (linear between ticks). This removes the 0–1 vsync quantisation of the draw. It is the error of content + schedule + clock.
- **Calibration:**
  - Clicks scheduled at known frames were detected at exactly that frame: 0 samples in 5/5 checks in every run.
  - WAV is the reference: clock_ms ≤ 0.24 ms.
  - An offline content check per run located the clicks in the PCM each engine would schedule, against the truth.
- **Limits of the method:**
  - A uses Chromium's own `outputLatency` estimate, and V is a draw time, not when the frame reaches the screen. Compositor/scan-out latency (probably 1–2 vsyncs [K]) and the device's true latency are not in these numbers.
  - For buf/wc, clock_ms uses the same `getOutputTimestamp` mapping as A. So it checks file timing, pre-skip, fit, scheduling and decoder placement, not the device latency itself.
  - For el, clock_ms is independent: `currentTime` against the tap.

**Plans:**
- **Short take:** play from 0.2 s for 8 s → seek forward to 40 s, play 5 s → seek back to 12 s, play 5 s → scrub 20 random positions 60 ms apart (paused, muted) → play from 50 s for 5 s. That is 22 flashes per run.
- **Long take:** 0.2 s → 1800 s → 3540 s → 300 s → scrub 10 positions over the hour → 2400 s, 4–5 s each.
- **Continuous play:** 10 min from 60 s on the long take. These 4 runs ran in parallel.

## 3. Results

### 3.1 Sync per format × API (fit, clock `out`) [M: short.json, long.json]
Content error is 0 samples in every buf/wc run on both takes, all four formats. That includes Opus after seeks with pre-roll, and ps0 with the CSV offset applied. Every flash paired with its click: 0 unpaired. Barcode mismatches: 0.

| Format | API | E35 av_ms mean [min, max] | E45 av_ms mean [min, max] | clock_ms abs max (short / long, both E) | Long take av_ms mean (E35 / E45) |
|---|---|---|---|---|---|
| WAV | wc | −7.1 [−13.9, −1.9] | −10.6 [−16.3, −0.4] | 0.18 / 0.24 | −9.6 / −7.5 |
| WAV | buf | −7.3 [−16.6, 0.0] | −9.7 [−14.6, −5.4] | 0.14 / 0.21 | −8.1 / −7.3 |
| FLAC | wc | −7.4 [−12.6, −4.8] | −8.1 [−16.0, −2.6] | 0.14 / 0.14 | −8.8 / −7.4 |
| FLAC | buf | −11.5 [−16.5, −7.5] | −11.4 [−14.7, −8.2] | 0.12 / 0.15 | −9.8 / −7.9 |
| Opus fMP4 | wc | −10.4 [−16.6, −0.9] | −11.3 [−15.7, −8.1] | 0.13 / 0.16 | −7.1 / −7.6 |
| Opus fMP4 | buf | −9.8 [−16.7, 0.0] | −9.0 [−14.6, −1.7] | 0.13 / 0.98 | −10.9 / −10.5 |
| Opus ps0 (+ CSV offset) | wc | −7.7 [−16.5, −0.1] | −5.5 [−16.6, −0.1] | 0.13 / 0.16 | −5.7 / −5.7 |
| Opus ps0 (+ CSV offset) | buf | −11.0 [−16.6, −0.6] | −4.7 [−11.1, −1.5] | 0.14 / 0.94 | −9.6 / −8.8 |
| any | el (`currentTime` clock) | +46 to +51 | +38 to +40 | 60.6 (clock mean +56.6 to +57.5 E35, +47.3 to +48.1 E45) | +47 to +49 / +38 to +42 |

- **buf/wc:** av_ms always lies in (−16.7, 0] ms: the next-vsync draw of a PREV player at 60 Hz. clock_ms is about 0. **That is the whole result: no format moves the audio in this design.**
- **After seeks:** per-segment means stay inside the same band (e.g. E45 Opus wc −14.5, −10.4, −8.4, −10.5; long-take segment clock means −0.07 to +0.08 ms).
- **After scrubbing:** the segment after the 20-position scrub is just as exact.
- **Scrub:** 4.4–9.8 ms per position on the short take (3 cameras, show + decode); 1.4–3.7 ms on the long take (1 camera). No missed ticks.
- **Opus pre-skip, measured in this player:**
  - Placing `AudioDecoder` output by its timestamps, with input timestamps on the untrimmed (`tfdt`) timeline, is exact (content 0). Chromium drops 312 samples after each configure without shifting the timestamps, which this placement cancels [M, agrees with P: mcap_electron/FINDINGS.md Task 3 and audio_skellycam §4.4].
  - For ps0, the player must add `file_sample_offset`. Without it the audio is +312 samples (+6.5 ms) late [D from the content check].

### 3.2 Clock source mistakes [M: naive.json]

| Clock | E35 av_ms / clock_ms mean | E45 av_ms / clock_ms mean |
|---|---|---|
| `getOutputTimestamp` (plan) | −7 to −11 / 0.0 | −5 to −11 / 0.0 |
| `ctx.currentTime` (naive), buf and wc, WAV | +48.5 to +50.5 / +57.3 | +39.9 to +40.5 / +48.5 |
| `<audio>.currentTime` (el) | +46 to +51 / +57 | +38 to +40 / +48 |
| `<audio>.currentTime − ctx.outputLatency` (ellat), all formats | −3.2 to −5.0 / +4.4 to +5.3 | −1.2 to −6.1 / +5.0 to +5.7 |

- **Naive and el both come out late by about `outputLatency` + 5–6 ms.** That exceeds a 33 ms frame.
- **ellat is within a frame** but carries a +5 ms bias and more spread (sd 2.8–7.3 ms).
- **Direct `<audio>` (no WebAudio)** cannot be tapped. An indirect probe [M: elprobe.json] looked at when `currentTime` starts moving after `play()`:

| | Direct to device | Through `MediaElementSource` |
|---|---|---|
| Median start (E35 / E45) | 62.0 / 62.8 ms | 1.0 / 1.2 ms |

  - This suggests a directly played element holds `currentTime` back by about the device latency, so a direct-`<audio>` leader may be close to sync. **Not verified;** it needs an output loopback or photodiode test.

### 3.3 Long take and drift [M: long.json, nofit.json, cont.json]
**With the fit:** clock_ms ≤ 0.24 ms at 0.2, 300, 1800, 2400 and 3540 s, for every format and API (Opus buf ≤ 0.98).

**Without the fit** (start anchor + nominal 48 kHz), clock_ms per segment, the same in E35 and E45:

| Segment (s) | wc clock_ms | el clock_ms |
|---|---|---|
| 0.2 | +0.2 | latency only, about +48 / +57 |
| 300 | +3.2 | |
| 1800 | +18.2 | +18 on top of latency |
| 2400 | +24.2 | |
| 3540 | **+35.6** | +35 on top of latency (+82 to +93 total) |

- The growth is exactly +10 ppm × t (36 ms/h) [D]. So **the CSV fit is what keeps a long take in sync.**
- **Continuous 10 min play** (WAV): the per-minute clock_ms mean stays flat.

| | wc, E35 and E45 | el, E35 | el, E45 |
|---|---|---|---|
| Per-minute clock_ms mean | −0.14 to +0.14 ms | 56.8–57.6 ms | 47.3–48.1 ms |
| sd | 0.6 ms (4 runs in parallel) | | |

  - No drift between the audio output clock and the video clock: the audio-master design takes up E35's −10 ppm output clock [P: audio_skellycam §4.4].
  - 0 late chunks; 1 missed tick in 17,9xx draws per run.

### 3.4 Load time, memory, decode cost for one hour of audio [M: long.json]
Working set (WS) is all Electron processes after load; the renderer ("Tab") is in brackets. Short-take runs with 3 cameras peak at 790–940 MB in total.

| Format | wc: load ms | wc: WS MB | buf: load ms (of which decode) | buf: WS MB | el: load ms | el: WS MB |
|---|---|---|---|---|---|---|
| WAV (346 MB) | **2** | 425–446 (118) | 1,380–1,417 (802–925) | 1,143–1,459 (781–1,107) | 4.5–5.9 | 547–570 (123) |
| FLAC (193 MB) | 594–648 (frame scan of the whole file) | 626–659 (305) | 2,124–2,493 | 1,139–1,293 | 3–4 | 545–572 |
| Opus fMP4 (74 MB) | 130–153 (moof walk of the whole file) | 510–551 (197) | **10,058–10,555** | 1,131–1,170 (777–853) | 133–186 | 583–631 (165) |

- **Decode per 1 s chunk (wc):** WAV 1.4–2.1 ms (fetch + convert); FLAC 4.6–4.8 ms; Opus 4.5–6.1 ms [M: short.json].
- **JPEG decode (320×240):** 1.2–2.2 ms per frame.
- **Seek preparation (wc):** WAV 0.8–4.4 ms; FLAC 2.3–10.3 ms; Opus 3.0–12.3 ms. buf about 0; el 0.3–13 ms (wait for `seeked`).
- **CPU while playing** (3 cameras at 320×240 + audio): 0.27–0.37 cores; the format makes no visible difference [M].

## 4. Recommendation (proposed; Dom decides)

**Formats.**
- In skellycam playback, **WAV, FLAC and Opus fMP4 all sync exactly** with the planned player. The format choice can stay with recording robustness and size, as in the earlier findings.
- **WAV is easiest for the player:**
  - no decoder, no index (byte = data offset + 2n), 2 ms load per hour;
  - sample-exact seeks, the smallest decode cost, and the same path for killed files.
- **Opus fMP4** needs a `moof` walk (130–150 ms/h, and the whole 74 MB fetched at load) or a per-packet byte-offset CSV, plus the 80 ms pre-roll.
- **FLAC** needs a frame scan (about 0.6 s/h) or `byte_offset` columns in the CSV.

**What the player must do:**
1. **Master clock from the audio output while playing:** n = n0 + (contextTimeAt(rAF timestamp) − when)·SR, with contextTimeAt from `getOutputTimestamp`. Never `ctx.currentTime`, and never a WebAudio-routed `<audio>.currentTime` (both +40 to +57 ms late). Paused or scrubbing: the clock = the target. Scrubbing stays muted.
2. **Map samples to host time with the CSV fit footer,** never start anchor + nominal rate (+36 ms/h at 10 ppm). Apply `file_sample_offset` (pre-skip-0 files: +6.5 ms otherwise).
3. **Windowed decode** with WebCodecs `AudioDecoder` (FLAC with the `fLaC` header as description; Opus with `OpusHead` built from `dOps`) or raw PCM for WAV. Schedule `AudioBufferSourceNode`s back to back at exact sample times.
   - Opus: start 80 ms (4 packets) early. Give input timestamps on the untrimmed timeline and place output by output timestamp. Never subtract the pre-skip a second time.
   - Don't use `decodeAudioData` for whole long files (10 s and about 1.1 GB for 1 h of Opus).
4. **Draw the PREV frame by sidecar time,** never by index/fps: the camera MKVs use index pts.
5. **Optional:** evaluate the clock at the expected display time (rAF timestamp + measured display latency) to centre the remaining 0–16.7 ms draw quantisation and the compositor delay. It is a single constant for every format.

**Remaining risks and desk tests:**
1. **True photon/sound latency:** the compositor delay and the device's real output latency are not in these numbers. Do TP4 B1 with an output loopback or a photodiode.
2. **The real skellycam-ui component** was not tested; it has no audio yet. This harness is the reference. Repeat inside the app, with 4–16 cameras at real resolutions and real camera JPEGs.
3. **Direct `<audio>` (not WebAudio)** as a fallback or leader: only an indirect probe (§3.2).
4. **Killed and repaired files** in this player (WAV with 0xFFFFFFFF sizes, unpatched FLAC, fMP4 without a final fragment); CSV rows past the end of the audio (Opus); multi-segment fits and gap rows.
5. **Other output devices and rates** (44.1 kHz devices, Bluetooth with 100+ ms latency, device changes mid-play), Linux and macOS, a low-end laptop; also playback rates ≠ 1 (muted by design today).
6. **Opus memory:** the wc engine fetched the whole 74 MB fMP4 to index it. A packet-offset CSV or `mfra` would avoid that. Hour-scale FLAC indexing: same.

Main-session check (2026-11-15): `long.csv` clock_absmax with the fit is 0.11-0.24 ms for wc on every format and 0.15-0.98 ms for buf, content error 0 in all 16 runs; `nofit.csv` shows 35.6 ms at 59 min. Matches §3.1 and §3.3. The sub-agent could not write this file (harness rule); the main session saved its text.
