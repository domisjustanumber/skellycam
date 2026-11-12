# Microphone audio in skellycam recordings: format, crash safety and synchronisation

2026-11-12, Gerald (Windows 11, i7-14700K). Written for `research/CAPTURE_AND_RECORDING_PLAN.md` rev 3.5 (§2.7 S3). Scripts: `scripts/audio_skellycam/`. Results: this folder. All test media were synthetic, in the scratchpad, not kept.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked these against the result files: the libopus 1.6.1 wheel entry (`codecs.json`), every crash row's loss and ffmpeg agreement (`summary.json`), and today's start offset (`device_timing/today_offset.json`).*

**Labels:** [M] measured (result file), [S] primary source, [C] code read, [I] inferred, [NV] not verified.

**Versions:** PyAV 19.0.2 (libavformat 63.1.102 / FFmpeg 9.0.2), sounddevice 0.5.6 (PortAudio V19.7.0-devel), from the `skellycam-phase1` venv, used read-only. libopus 1.6.1 is in the wheel [M] (`codecs.json`). Also: FFmpeg CLI 9.0.2, VLC 3.0.24, Electron 35.7.5 (Chrome 134.0.6998.205) and 45.2.3 (Chrome 156.0.8078.80), Python 3.13.13.

**Privacy.** Real mics were opened only for timing: 8 runs of 20–30 s plus 7 pipeline runs of 20 s, in shared mode.
- The callbacks never copied, measured or stored samples.
- Only callback times, PortAudio time-info values and frame counts were kept.
- The pipeline runs fed a synthetic tone to the encoder and deleted the file.
- No settings were changed.

## 0. Recommendation
| Item | Recommendation |
|---|---|
| Format | Opus in Ogg, `<rec>.audio.opus`, separate from the MKVs. The MKVs stay video-only: live offsets valid, no remux (S3) |
| Encoder | `libopus` (`av==19.0.2` wheel, libopus 1.6.1). 48 kHz; mono 64 kb/s (stereo 96 kb/s); VBR; `application=audio`; `frame_duration=20` |
| Muxer | `flush_packets=1`, `page_duration=20000` µs: 29–44 ms lost per hard kill, 12/12 files readable [M] |
| Device | 48 kHz on the mic's WASAPI entry. WASAPI shared refuses 44.1 kHz here [M]. MME bursts callbacks (p99 interval 51 ms) and gives zero time info [M] |
| Lossless option | Native FLAC with `frame_size=1024`: 0 ms lost in 12/12 kills, sample-exact in all decoders incl. VLC [M]. 172 MB/h mono on the synthetic signal (≈ 7× Opus) [M] |
| Writer | Callback → bounded deque → writer thread, in a **dedicated audio process** (§3) |
| Timing sidecar | `<rec>.audio.skau`: 48 B record per callback block, CRC per record, header with recording UUID, clock id and anchors. The UUID also goes in the Opus tags [M] |
| Sync | pts = device sample index. Segment fit host_ns = t0 + n/f_eff. Frame k at host time T → n = (T − t0)·f_eff. The player slaves its master clock to the audio output while playing |
| Player | WebCodecs `AudioDecoder` on JS-parsed Ogg packets, decoding a window around the playhead; sample-exact in E35/E45, including after a seek [M] |

## 1. Codec and container shortlist

### 1.1 Royalty status
- **Opus:** royalty-free patent licences, granted automatically, and BSD code. Some holders filed royalty-bearing IPR; counsel advised they aren't needed [S] https://opus-codec.org/license/ ; RFC 6716, RFC 7845.
- **FLAC:** "unencumbered by patents" [S] https://xiph.org/flac/ ; RFC 9639 (Standards Track, Dec 2024).
- **Vorbis:** "patent-and-royalty-free" [S] https://xiph.org/vorbis/
- **AAC: out.** Via LA charges per-unit fees on encoders and decoders ($0.98–$0.10 per unit, plus an initial fee) [S] https://www.via-la.com/licensing-programs/aac/
- **MP3: out, but not for royalties.** Technicolor's licensing programme ended on 2017-04-23 [S] https://www.iis.fraunhofer.de/en/ff/amm/consumer-electronics/mp3.html. It is out because Opus beats it, and because its encoder delay isn't signalled in the stream, so sample-exact alignment depends on LAME/Xing tags [I].

### 1.2 Wheel contents [M] (`codecs.json`)
- `libopus` 1.6.1. `av.Codec("opus","w")` resolves to `libopus`; FFmpeg's native Opus encoder is absent.
- FFmpeg's native `flac` encoder.
- `vorbis`: native only, experimental and stereo-only ("only supports 2 channels"). `libvorbis` is absent.
- Muxers: ogg, matroska, webm, flac, wav.

### 1.3 Cost and size (synthetic 60 s signal: −60 dBFS floor, bursts at −20 dBFS 30 % of the time, a click every second) [M] (`bench.json`)
| Config | MB/h | CPU, % of one core |
|---|---|---|
| Opus mono 24k voip / 32k / 48k | 9.6 / 12.7 / 19.0 | 0.47–0.50 |
| **Opus mono 64k** | **25.1** (≈ 30 with 20 ms pages: +13 % page overhead [M, smoke run]) | 0.34 |
| Opus mono 96k | 38.5 | 0.34 |
| Opus stereo 96k / 128k | 38.3 / 52.0 | 0.63 / 0.73 |
| FLAC mono, level 0 / 5 / 8 | 192.8 / 172.0 / 170.5 | 0.08–0.18 |
| FLAC stereo, level 5 | 334.6 | 0.23 |
| Vorbis stereo "96k" (native encoder) | 151.8 (bitrate ignored) | 1.43 |
| WAV mono | 345.6 | 0.05 |

- **Resampling** 44.1 → 48 kHz in PyAV costs 0.13 % of a core, and the output length is exact [M].
- **Click peaks** stayed at offset 0 at every mono bitrate [M]. Stereo rows show 0–7 sample offsets, an artifact of the test signal (channel 2 was shifted 7 samples).
- **Quality by listening:** not done (no real audio may be kept) [NV].
- Xiph's guidance puts fullband speech at about 28–40 kb/s and music at 64–96 kb/s (stereo) [S, https://wiki.xiph.org/Opus_Recommended_Settings; not fetched today, so NV].
- FLAC size on real room audio [NV].

## 2. Crash safety, measured

### 2.1 Method
- **Real kills** (`crash_kill.py` → `crash_kill.json`):
  - A child process writes paced real-time 1024-sample blocks (48 kHz mono, synthetic) through PyAV encode + mux, pts = sample count.
  - It publishes the acknowledged sample count in shared memory after each write.
  - 6 kill points (1.0–10.4 s) × {`os._exit(1)` right after a block; `TerminateProcess` 0–21 ms after a block} = 12 kills per format.
  - Lost = acknowledged − samples PyAV decodes from the killed file.
- **Virtual kills** (`growth.py` → `growth.json`): copy the on-disk file after every 4th block and decode the copy. About 140 points per format.
- **Readers** (`killed_readers.py` → `killed_readers.json`): ffprobe, ffmpeg, VLC (transcode, plus the `afile` playback path for the 10.4 s kills) and Chromium (`electron_killed_e3x/e4x.json`). Repair = `ffmpeg -c copy`. Summary: `summary.json`.

### 2.2 Results [M]
| Format (all `flush_packets=1`) | Lost per kill, ms (median) | Virtual-kill lag, max ms | PyAV / ffmpeg / Chromium read the killed file | ffprobe duration | Repair |
|---|---|---|---|---|---|
| Ogg Opus, default page (1 s) | 1003–1900 (1357) | 2004 | 10/12; 2 had no audio (killed before the first page) | 10/12 | `-c copy` 10/12, 28 ms |
| **Ogg Opus, page 20 ms** | **29–44 (37)** | 45 | 12/12 | yes | 12/12, 33 ms |
| Ogg Opus, page 60 ms | 77–109 (99) | – | 12/12 | yes | 12/12 |
| Ogg Opus, page 100 ms | 109–204 (197) | 205 | 12/12 | yes | 12/12 |
| MKA Opus, default | 317–3691 (1600) | 5011 | 6/12; 6 had no audio | N/A | 6/12 |
| MKA / WebM Opus, `cluster_time_limit=100` | 117–137 (122) | 145 | 12/12 | N/A (unknown-size Segment, no Cues) | 12/12, 26 ms |
| FLAC native, default (4608-sample frames) | 11–85 (43) | 85 | 12/12 | N/A (total samples = 0) | `-c copy` leaves 0; in-place patch works |
| **FLAC native, `frame_size=1024`** | **0** | 0 | 12/12 | N/A | patch: 19 ms count + 0.1 ms write for 10 s (`flac_patch.json`) |
| Ogg FLAC, page 100 ms | 213–299 (235) | 363 | 12/12 | yes | 12/12 |
| MKA FLAC, `cluster_time_limit=100` | 203–277 (235) | 277 | 12/12 | N/A | 12/12 |
| Ogg Vorbis (native), page 100 ms | not killed | 6059 | – | – | – |
| WAV PCM | 0 | 0 | 12/12 (RIFF size left at 0xFFFFFFFF) | yes | 12/12 |

- **Defaults are not crash-safe.** Ogg writes a page every 1 s; audio-only Matroska closes a cluster about every 5 s.
- **Where the loss comes from** [I from M]:
  - libopus holds up to one 20 ms frame plus 6.5 ms look-ahead;
  - Ogg holds the open page; Matroska holds the open cluster plus one packet;
  - FLAC holds one encoder frame, so `frame_size=1024` with 1024-sample blocks holds nothing.
- **Kill method:** `os._exit` and `TerminateProcess` lost the same amount in 71 of 72 pairs. The kills landed between blocks, as in GF02.
- **Ogg CRCs:** every page in every killed Ogg file had a valid CRC and there was no torn tail; only the EOS page was missing, which no reader minded. A torn last page would be skipped through its CRC [S, RFC 3533].
- **FLAC STREAMINFO:** every killed `.flac` has total samples = 0 ("unknown", RFC 9639 §8.2 [S]) and a zero MD5. All readers still decoded it.
- **PyAV creates the output file at the first mux.** A FLAC writer killed before its first frame leaves no file at all [M].

### 2.3 Readers [M]
- **ffmpeg CLI:** sample count = PyAV's on 144/144 killed files.
- **Chromium `decodeAudioData`:** sample count = PyAV's on every killed file with audio, in E35 and E45, except E45 on Matroska Opus (−0.5 ms).
- **Chromium `<audio>`, killed files:**
  - Ogg: finite duration, played 12/12 per Ogg format.
  - MKA, WebM and FLAC: duration unknown (NaN/Infinity), but they played when the seek target lay inside the content. On the 1 s kills, the 1 s seek target fell past the end.
  - Files with no audio: error 4 (`DEMUXER_ERROR_COULD_NOT_OPEN`).
- **VLC 3.0.24 on clean files** (`align.json`; click offset in samples at 48 kHz):

| File | Transcode | Playback (`afile`) |
|---|---|---|
| Ogg Opus, page 20 ms | −648 | −3528 |
| Ogg Opus, page 60 ms | −2568 | −5448 |
| MKA / WebM Opus | +312 (codec delay ignored) | +312 |
| FLAC native, MKA FLAC, WAV | 0 | 0 |
| Ogg FLAC | −9216 | −18432 |

  On Ogg, VLC's playback output was also sometimes cut short.
- **PyAV and ffmpeg:** offset 0 in every format, including 44.1 kHz input resampled to 48 kHz.

## 3. Capture → encode pipeline [M] (`pipeline.py`, `pipeline_*.json`)
WASAPI "USB Audio" mic, 48 kHz, 1024-sample blocks, 20 s:

| Load in the same process | Callbacks | Device samples lost | Writer queue drops | Writer time per block, median / p99 |
|---|---|---|---|---|
| none (dedicated process) | 937 | 0 | 0 (max depth 1) | 0.30 / 0.53 ms |
| 1 spinning Python thread | 937 | 0 | 572 | 0.08 / 116 ms |
| 2 threads | 921 | 16,384 (1.8 %) | 635 | 0.08 / 302 ms |
| 4 threads | 656 | 288,256 (30 %) | 381 | 0.10 / 573 ms |
| 1 thread, batched writer | 937 | 0 | 300 | 711 ms per batch |
| MME 44.1 kHz, 4 threads | 844 | 17,744 | 572 | 0.09 / 521 ms |

- **Output length is always right:** the decoded length equalled the expected length in every run, because dropped blocks are replaced by silence of the same length. Sidecar CRCs: 0 bad.
- **The GIL is the risk, not CPU.** Encoding a block costs about 0.1 ms. PyAV releases the GIL in encode/mux, and each release hands it to a CPU-bound thread for up to the 5 ms switch interval (convoy effect) [I].
- **PyAV doesn't starve other threads:** a Python thread ran as fast or faster while an encoder thread ran (ratio 1.09 libopus, 1.48 FLAC) [M] (`bench.json`).
- **WASAPI did not flag the loss** (`input_overflow` = 0); MME flagged 4 overflows [M].
- **So:** a dedicated audio process. Callback 11–17 µs median, ≤ 58 µs max.
- **Memory is bounded:** at most `queue_blocks` payloads (256 × 2 KB). Today's recorder keeps the whole recording in RAM until stop [C] (`skellycam/core/recorders/audio/audio_recorder.py:114`).
- **Block vs frame size:** 1024-sample blocks don't need to match 960-sample Opus frames; PyAV's encoder FIFO re-blocks them exactly [M]. WASAPI shared delivers on a 20 ms engine period (median interval 20.1 ms) [M]. A 960 block would align with both [I].
- **skellycam today uses MME at 44.1 kHz:** device detection keeps the first device per name, and MME is listed first [C] (`skellycam/core/device_detection/detect_microphone_devices.py:47-65`; `audio_recorder.py:16`).

## 4. Synchronisation

### 4.1 Clocks [M] (`device_timing/*.json`, `analysis.json`, `today_offset.json`)
- **PortAudio time = `perf_counter`** on Windows (0 ± 7 µs), so ADC and current times are QPC, the video sidecar's timebase.
- **WASAPI timing:** `currentTime` is taken 55–69 µs before the Python callback runs. `inputBufferAdcTime` is about 6 ms before `currentTime`.
- **The ADC time behaves like the end of the block,** not its first sample: fitted to the block end, it lands 1.9–2.6 ms before the earliest callback arrival [M; interpretation I].
- **MME:** `currentTime` = 0, and ADC time alternates 0 / 23.2 ms. Unusable.
- **Jitter after the fit** (WASAPI): ADC times 0.66–0.72 ms std (p99 2.4–2.6 ms); callback times about 3.0 ms; MME 12 ms.

| Mic (WASAPI 48 kHz) | Drift from ADC times, ppm | From callback times | Start-up |
|---|---|---|---|
| Revelator IO 24, 30 s | −2.5 ± 2.7 | −1.9 ± 12.1 | settled by 2 s |
| C922, 20 s | +1.4 ± 6.4 | +5.0 ± 26 | settled by 1 s |
| "USB Audio" (default), 30 s | +4.5 ± 4.1 (skip 10 s) | +5.8 ± 16.8 | **~9 ms step at 6–8 s** (also seen under MME) |

- **Drift must be fitted.** All three clocks are within about ±10 ppm of QPC, but at 10 ppm that is 36 ms/h, more than a 60 fps frame.
- **A fixed start-up exclusion isn't enough** because of the step; use change-point segments, as for video (row 1.6).
- **Today's anchor:** `start_perf_ns` is taken before `stream.start()` and treated as the time of sample 0 [C] (`audio_recorder.py:68`; `video_audio_remuxer.py:99-100`).
  - Measured: the first callback came 47–103 ms after it, and the fitted arrival of sample 0 came 9–74 ms after it.
  - So today's audio is early by about that much [I].

### 4.2 What to store
- **Container:** Ogg granule = device sample index. Decoded sample n = captured n in PyAV, ffmpeg, `decodeAudioData` and WebCodecs (E35/E45) [M]. The 312-sample Opus pre-skip is handled by all of them.
- **`.skau` header:**
  - magic `SKAU`, version, header_size, record_size, flags;
  - recording UUID (16 B), also the Opus tag `SKELLYCAM_RECORDING_ID` (stored in OpusTags, reads back as stream metadata [M]);
  - device and encoder rate, channels, nominal block;
  - clock id (1 = QPC) and frequency; a (host ns, UTC ns) anchor;
  - then length-prefixed JSON: device, host API, PortAudio version, `stream.latency`, codec settings, versions.
- **Record (48 B, little-endian):**

| Bytes | Field | Notes |
|---|---|---|
| 0–3 | `block_index` u32 | |
| 4–7 | `frames` u32 | |
| 8–15 | `sample_index` i64 | block's first sample |
| 16–23 | `host_ns` i64 | `perf_counter_ns` at callback entry |
| 24–31 | `pa_adc_ns` i64 | INT64_MIN when the host API gives 0 (MME) |
| 32–39 | `pa_current_ns` i64 | |
| 40–41 | `flags` u16 | overflow / underflow, queue drop (silence written), priming |
| 42–43 | reserved | |
| 44–47 | `crc32` u32 | over bytes 0–43 |

- **Size:** 8.1 MB/h. The prototype's 40 B record (no `pa_current_ns`) had 0 bad CRCs in 7 runs [M].
- **Write order:** each record is flushed before its block is encoded. After a kill, records may run ≤ 45 ms ahead of the audio; recovery trims them [I].

### 4.3 Mapping (finalisation and recovery)
1. Use x = sample_index + frames, y = `pa_adc_ns` where valid. Otherwise use a lower-envelope fit of `host_ns`.
2. Split segments at residual jumps of more than about 3 ms, and where block, sample and elapsed counts disagree. This catches silent WASAPI loss.
3. Exclude 1–2 s per segment, then fit t = t0 + (n − n0)·1e9/f_eff. Store n0, t0, ppm and residual p99 per segment, with `fit_unreliable` when p99 > 5 ms or the segment is shorter than 10 s.
4. **Latency:** the acoustic latency isn't observable from software (PortAudio reports 42.7–46.4 ms; unchecked). Apply a per-mic `audio_latency_ns` from the TP2 clap test, and record it.

- **Frame → sample:** n(c,k) = n0 + (T(c,k) − t0 − latency)·f_eff/1e9, where T is the frame's sidecar time (fitted when valid, else arrival). Both clocks are QPC.
- **Gaps:** a queue drop already has silence in the file. A device-side loss becomes a segment boundary; the file is left unchanged.

### 4.4 Canvas player
skellycam-ui has no audio playback today, only a mic selector [C] (`skellycam-ui/src/components/recording-info-panel/recording-subcomponents/MicrophoneSelector.tsx`).

**Chromium [M]** (`electron_aligned_e35/e45.json`):
- `<audio>` plays Ogg Opus/FLAC, native FLAC, WebM and MKA. A seek takes about 5 ms.
- MSE accepts only WebM Opus and MP4 variants, never Ogg or FLAC.
- `AudioDecoder` supports Opus in both versions. FLAC without a description: supported in E45, rejected in E35.
- `decodeAudioData`: offset 0 everywhere, except Matroska Opus in E45 (−24 samples, from Matroska's 1 ms timestamps).
- JS Ogg parser + `AudioDecoder`: offset 0 for the whole file and after a seek to 5 s with 80 ms pre-roll, in both versions. Decoding 10 s takes 21–25 ms.
  - Chromium trims the pre-skip itself when given OpusHead as `description`, and its output timestamps are already on the trimmed timeline.
  - Subtracting the pre-skip again puts audio 312 samples (6.5 ms) early.
- **Output clock vs `performance.now`** (25 s): −10.2 ppm in E35, −0.13 ppm in E45; `outputLatency` 42–52 ms (`electron_clock_e*.json`).

**Design [I]:**
- **Clock:** while audio plays, master clock = t(n_heard), from `getOutputTimestamp().contextTime` and the schedule. Video picks frames from it (PREV). Paused, scrubbing, or no audio: `performance.now()` drives.
- **Decode:** fetch the whole `.opus` (about 30 MB/h) and scan pages in JS. Decode a window of −2 s / +10 s with `AudioDecoder`. Schedule `AudioBufferSourceNode`s back to back.
  - Don't `decodeAudioData` long files: 691 MB per mono hour.
- **Seek:** page at the target − 80 ms (RFC 7845 pre-roll), reconfigure, discard output before the target.
- **Other speeds and scrubbing:** mute.
- **Killed files** need no index or duration.
- **Fallback:** `<audio>` + `currentTime` / `playbackRate` nudging, accurate only to tens of ms.

### 4.5 External players and freemocap
- **Camera MKVs use index pts at the nominal rate.** The generic camera delivers ~25.7 fps for 30 requested, so its MKV plays 14 % fast. Never pair audio with index-pts video.
- **Exports are new files,** so remux freely:
  - video: real timestamps from the sidecar;
  - audio: first sample offset by (t0 − T(c,0)), resampled by the fitted ppm (48000·(1 + ppm·1e-6));
  - audio codec: FLAC in MKA (VLC 0 offset) or Opus in MKA (VLC +6.5 ms).
- **freemocap** doesn't read skellycam's audio today. Its audio sync is skelly_synchronize cross-correlation on imported videos [C] (`freemocap/api/http/mocap/mocap_router.py:139,252`; `core/pipeline/posthoc/sync_job.py:3`).
  - Contract: `.opus` + `.skau` + the fit in the info JSON (S8), and a Python reader in the shared sidecar package (S5).

## 5. Finalisation
1. Drain the queue, `encode(None)`, close (writes the EOS page).
2. Write the last records, fit the segments, and write a footer plus the S8 info-JSON fields.
3. Derive `<rec>.audio_timestamps.json` (today's keys plus the fit).
4. The §2.7 remux rule doesn't apply: the MKVs are untouched.
5. **Crash recovery:** the killed `.opus` plays as is. Optionally run `-c copy` to add the EOS page (about 30 ms). For FLAC, patch STREAMINFO. Then run steps 2–3 on the surviving records.

## 6. Tests
**TP2:**
- A1: audio + 4 cameras on every set; samples vs elapsed QPC; callbacks lost; drops; writer p99; CRCs.
- A2: T-KILL, ≤ 50 ms lost; readable in PyAV, ffmpeg and the player; records ≥ decoded samples; torn record caught.
- A3: **clap/flash AV latency per mic model**, 10 claps (needs consent; delete the audio after measuring).
- A4: drift over 10 and 60 minutes per mic; ppm and change points; residual p99 < 3 ms.
- A5: the audio process under TP3 load: zero loss, zero drops.
- A6: hot-unplug the mic mid-recording.

**TP4:**
- B1: flash + click sync at start, after 30 minutes and after 20 seeks; target ≤ 1 frame (output loopback).
- B2: WebCodecs seek latency and correctness, E45 and the low-end laptop.
- B3: memory over 1 h.
- B4: killed files play; UUID mismatch rejected.
- B5: an export stays in sync in VLC and Chromium at start and end of 30 minutes.

**Release checks:** libopus is in the wheel; decoded count = input; click offset 0; virtual-kill lag ≤ 50 ms with `page_duration=20000`.

## 7. Effort
| Work | Days |
|---|---|
| Audio process, writer, `.skau`, WASAPI 48 kHz selection | 2 |
| Segment fit, recovery, S8 fields, Python reader | 1.5–2 |
| Player: Ogg scanner, `AudioDecoder` window, audio-driven clock, seek | 2–3 |
| Export with real timestamps and drift-corrected audio | 1 |

## 8. Open risks
- Absolute AV latency until A3.
- Silent WASAPI loss under GIL load (no flag).
- Drift precision of ±3–6 ppm, from runs of 30 s or less; one mic had a start-up step.
- VLC shifts Ogg audio earlier.
- Linux and macOS time info [NV].
- FLAC size on real audio and Opus quality by listening [NV].
- `getOutputTimestamp` drift differs between E35 and E45.

## 9. Files
- **Scripts** (`scripts/audio_skellycam/`): `ac_common.py`, `codecs_probe.py`, `growth.py`, `crash_kill.py`, `killed_readers.py`, `flac_patch.py`, `align.py`, `bench.py`, `device_timing.py`, `analyze_timing.py`, `today_offset.py`, `pipeline.py`, `summarize.py`, `electron/main.cjs`, `electron/page.html`.
- **Results** (this folder): `codecs.json`, `growth.json`, `crash_kill.json`, `killed_readers.json`, `summary.json`, `flac_patch.json`, `align.json`, `bench.json`, `pipeline_*.json`, `device_timing/*.json`, `electron_{aligned,killed,clock}_e35/e45.json`.
- **How to run:** with the `skellycam-phase1` venv, `python -I <script> …` (usage is in each docstring). Electron: `AUDIO_DIRS=<dir> AUDIO_OUT=<json> electron.exe electron/main.cjs`.
