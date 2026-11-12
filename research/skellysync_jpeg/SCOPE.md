# skellysync: scope for a JPEG-only, I-frame-only output path

2026-11-11 · status: **scope only, nothing implemented.** No change was made to the skellysync repo, freemocap or skellycam. This file is the only file written.

**What this covers:** what it would take to make skellysync (Python package `skelly_synchronize`) write JPEG-in-MKV + sidecar instead of long-GOP MP4; an alternative that writes only a sync sidecar and never re-encodes; file sizes and CPU cost; effort per work item; and the decisions the owner needs to make.

**Code basis:** skellysync commit `0231c41a3bcb967e231163943a39dd40b50278f1` (branch `philip/rewrite`, dated 2026-08-12), the commit freemocap pins (`freemocap/uv.lock:2158-2160`). It was read from uv's read-only checkout `C:\Users\Dom\AppData\Local\uv\cache\git-v0\checkouts\fbf6d6a3b968a95a\0231c41\`. All skellysync paths below are relative to `skelly_synchronize/` in that checkout unless they start with a repo-root folder (`frontend/`, `src-tauri/`, `packaging/`, `pyproject.toml`, `.github/`). freemocap was read at `5632778a`.

**Labels:** **[C]** code (file:line at the commits above) · **[M]** measured (linked file, or this report's §8 for the new local check) · **[S]** primary source (URL, access date) · **[W]** user report or third-party page · **[I]** inferred · **[arith]** arithmetic from cited numbers · **[NV]** not verified.

Short names for evidence files:
- `IC` = `research/skellycam_recording/recording_upgrade/results/intra_compare/FINDINGS.md`
- `EI` = `research/skellycam_recording/recording_upgrade/results/EVIDENCE_INDEX.md`
- `PLAN` = `research/CAPTURE_AND_RECORDING_PLAN.md`
- `CC` = `research/skellycam_recording/recording_upgrade/results/chromium_codecs/FINDINGS.md`
- `IP` = `research/skellycam_recording/recording_upgrade/results/intra_playback/FINDINGS.md`

---

## Handoff (2026-11-11): start here in a new session

Dom will pick this up in a separate session. Nothing is decided yet: everything below is for that session to settle with Dom.

**Project rules this work must follow** (Dom, 2026-11-11, in `PLAN` §1):
- JPEG only, I-frames only, everywhere; long-GOP is forbidden. Container: JPEG in MKV with a binary per-frame sidecar.
- Raw frames are encoded with `mjpeg_qsv` first (needs full-range input), libjpeg-turbo as the fallback.
- Imported footage plays in a separate `<video>`-based import player (`PLAN` §4, item 2.8). `<video>` cannot play MJPEG.
- Phase 2 is freemocap-side work. freemocap stays on Python 3.11 and its current skellycam pin until its phase-2 move to 3.13 (`PLAN` §6, D3).

**Recommendation from the main session** (inferred from this report, not decided):
**Update 2026-11-12: Dom decided Design A** (see §7 D-DESIGN). The recommendation below is kept for the record.

1. **Design B first:** keep the originals untouched and write a sync sidecar (§3). It is days of work in skellysync, adds no disk and loses no quality. It has no Python/PyAV blocker, and it fits the `<video>` import player.
2. **Treat untouched imported originals as source data** that the JPEG-only rule does not cover. The rule applies to everything skellysync and freemocap *write*.
3. **Fix the two existing bugs either way** (§1): the 30 s ffmpeg trim timeout (`core/backends/ffmpeg.py:178`, `config.py:24`), and the audio reattach ignoring the synced WAV for stereo sources (no `-map`).
4. **Design A later, only if needed:** if imported footage must be shown in the canvas player, or processed as JPEG. When it is built, settle the quality basis first. Matching target A against an already-lossy source makes JPEG copy the source's noise: phone clips needed 1.4–5.4× the bytes of webcam frames (§8).

**The three decisions that drive the rest** (the full list of 11 is in §7):
1. **Design:** A (JPEG-in-MKV output), B (sidecar only), or B now and A later.
2. **Rule scope:** do untouched imported originals fall under "JPEG only, I-frames only"?
3. **Quality basis for lossy sources:** SSIM-Y 0.9961 against the decoded source, or a fixed quality (the cameras' q94-like quantisation).

**Headline numbers** (details in §5–§6):
- **Effort:** A is ~3–5 weeks in skellysync plus a few days to a week in freemocap. B is days to a week in skellysync plus 1–2+ weeks in freemocap if every reader applies the offsets.
- **Size, GB per camera-hour:** 4K60 is 27–54 from the source against ~112–480 as JPEG at A. A 4-camera, 10-minute 4K60 session goes from 30 GB to ~75–320 GB.
- **CPU:** 4K HEVC software decode dominates, at about 11 cores for 4 × 4K60, so conversion runs at about real time on an i7-14700K.
- **Playback:** GoPro HERO11/12 record HEVC only, and Chromium has no software HEVC decode.

**Not kept:** the size-measurement scripts and raw results (`sizecheck.py`, `sizecheck_hiq.py`, `result*.json`) were left in the original session's temporary scratchpad. They name the paths of personal phone clips, so they are not in the repo. §8 describes the method well enough to redo it on real GoPro clips, one per mode, which is the next step for firming up sizes.

**Related:** `PLAN` (rev 3.2) §4 item 2.8 and phase-2 exit tests; `research/usb_cameras/docs/` for the capture side.

---

## 0. Summary

1. **Your read of the code is right, with three corrections and two extra defects.** One offset per video, from audio cross-correlation or the first brightness flash. Normalize with `-r`, trim with `-ss … -frames:v N`, reattach audio with `-c:v copy`. No codec is named, so the output is ffmpeg's default MP4 encoder, which with the Gyan 9.0.2 build on this machine is libx264 High with B-frames (`has_b_frames=2`) [M, §8.4]. Corrections and additions:
   - **When frame rates differ, a video is encoded twice.** The trim reads the normalized MP4, not the original, so the output carries two generations of long-GOP loss [C] (`core/pipeline/stages.py:196-200` re-points `context.videos` at `normalized_videos/`, and `TrimStage` trims `context.videos`, `:291`).
   - **The ffmpeg trim has a 30 s timeout** (`core/backends/ffmpeg.py:178` uses the default from `core/config.py:24`). A full libx264 re-encode of real action-camera footage takes much longer than that, so the trim would time out on anything beyond short clips [C] + [I]. Normalize and audio use 1800 s (`config.py:25`).
   - **The WAV reattach can be a no-op.** The ffmpeg trim keeps the source's audio track, and `attach_audio` passes no `-map`. ffmpeg's default stream selection then picks the audio with the most channels. librosa's default `mono=True` makes the trimmed WAV mono, so with a stereo source (GoPro audio is stereo [I]) the output keeps the trim's own AAC track and ignores the WAV. Reproduced: `Stream #0:1 -> #0:1`, stereo output from a stereo source plus a mono WAV [M, §8.4]; code `core/backends/ffmpeg.py:264-290`, `core/pipeline/stages.py:216`.
   - Rotation: the deffcode path applies an explicit transpose (`core/backends/deffcode.py:63-76`). The ffmpeg CLI path relies on ffmpeg's default autorotate on transcode [I].
   - The deffcode path writes MPEG-4 Part 2 (`mp4v`) through `cv2.VideoWriter`, with no audio [C] (`deffcode.py:101-105`).
2. **Design A (JPEG-in-MKV output) is a rewrite of the output half of the pipeline, not a codec flag.** Normalize, both trim backends and the audio reattach collapse into one PyAV pass per video: decode, then frame-exact select, then range and rotation fix, then JPEG at target A, then MKV with index timestamps and a sidecar. The total is about **L (3–5 weeks)** in skellysync, plus **S–M** in freemocap (§6).
3. **Design B (sync sidecar only, no re-encode) is about S–M in skellysync.** It costs zero extra disk and no generation loss. It moves the work to freemocap: every reader must apply the offset and frame count. Or freemocap runs a deferred JPEG conversion, which is Design A's encoder run later (§4).
4. **Hard dependency: PyAV 19.0.2 needs Python ≥ 3.12, and skellysync declares `requires-python = ">=3.10,<3.13"`** [C] (`pyproject.toml:37`); CI runs on 3.10 [C] (`.github/workflows/python-testing.yml:18`). freemocap is on ≥ 3.11 until its phase-2 move to 3.13 (PLAN §2.4, D3). Design A on PyAV 19 therefore cannot reach freemocap before freemocap's phase-2 Python bump, unless it is built on PyAV 18.x [I].
5. **Sizes: JPEG at target A is several times larger than action-camera sources, and the ratio depends heavily on content.**
   - A new local check on five camera-originated 1080p30 H.264 phone clips (§8) needed **182–698 kB/frame at A (median 555 kB)** when A is measured against the decoded source [M]. That is 1.4–5.4× our webcam-based 130 kB figure.
   - So a 4K60 camera at 100 Mb/s (45 GB/h) becomes roughly **112–480 GB/h** of JPEG [I/arith] (§5.3).
   - The one 4K clip measured (tone-mapped from HDR) needed 1.32 MB/frame, which is **286 GB/h at 4K60** [M/arith].
6. **"Target A against the decoded source" makes the JPEG copy the source's noise and codec artefacts.** That drives the bytes up. A fixed knob (q94, the setting that hits A on raw YUY2) gives 394–436 kB/frame on the same phone clips (SSIM-Y 0.9920–0.9961) [M]. How A is defined for re-encodes of already-lossy sources is an owner decision (§7, D-Q).
7. **CPU: decode dominates for 4K HEVC.**
   - Software decode of a 4K60 10-bit HEVC clip in PyAV 19.0.2 took 45 ms CPU/frame and 35 fps wall per stream [M, §8.3]. So 4 × 4K60 needs about 11 cores for decode alone [arith], slower than real time on most machines.
   - JPEG encode is cheaper. libjpeg-turbo at 4K takes about 11–12 ms/frame single-threaded at q94–96 [M, §8.3], about 2.9 cores for 4 × 4K60 [arith].
   - `mjpeg_qsv` opens at 3840×2160 [M, §8.4]. Pixel-scaled from its measured 700 fps aggregate at 1080p (IC §2.5), it could not quite keep up with 4 × 4K60 in real time (about 960 1080p-equivalent frames/s needed) [I].
8. **Playback interaction (neutral).** JPEG-in-MKV cannot play in `<video>` (CC C1, C2). If skellysync writes JPEG-in-MKV, its results need the canvas player (PLAN 1.9 / 2.3). The owner picked a `<video>`-based import player for originals (PLAN 2.8); that player can play Design B's untouched originals with offsets from a sidecar, but not Design A's outputs. GoPro HERO11/12 record HEVC only [S], and Chromium has no software HEVC decode (IP F10). So a `<video>` player shows modern GoPro originals only where hardware HEVC decode exists (§3).

---

## 1. What skellysync does today (verified against 0231c41)

### 1.1 Pipeline

Stage order [C] (`core/pipeline/runner.py:33-56`): SetupOutputFolder, then DiscoverVideos, then Probe, then NormalizeFramerate, then AudioLag or BrightnessLag, then Trim, then VerifySynchronizedFramerate, then VerifySynchronizedFrameCount, then ReattachAudio (audio method only), then DebugArtifacts (if `create_debug_artifacts`).

| Stage | What it does | Writes video? | Code |
|---|---|---|---|
| Probe | ffprobe `format=duration` and `stream=r_frame_rate` (fps as a float); frame count from `cv2.CAP_PROP_FRAME_COUNT` | no | `core/backends/ffmpeg.py:90-151`; `core/pipeline/stages.py:118-148` |
| NormalizeFramerate | Runs only if fps (or, for audio, sample rate) differs. Target = **lowest** fps and lowest sample rate. `ffmpeg -i in -r FPS -ar RATE -y out.mp4`, no codec named. Writes into `<raw folder>/normalized_videos/`, then re-probes and **replaces `context.videos`** with the normalized files | **yes**: long-GOP MP4, generation 1 | `stages.py:151-201`; `ffmpeg.py:233-261` |
| AudioLag | `ffmpeg -i video out.wav` per video (into `<synced>/audio_files/`); `librosa.load(sr=None)` (mono by default); FFT cross-correlation against a reference video (longest duration, then name); confidence = peak / mean abs correlation; lags normalized so the minimum is 0 | no | `stages.py:204-226`; `core/audio.py:13-86`; `ffmpeg.py:217-230` |
| BrightnessLag | cv2 reads every frame, mean gray per frame; first frame where Δ·Δ² ≥ threshold, else argmax Δ²; lag = max − own | no | `stages.py:229-251`; `core/brightness.py:18-88` |
| Trim | `start_frame = round(lag_s × fps)`; shared `frame_count = min(frame_count − start_frame)`; `ProcessPoolExecutor` with one worker per video; re-probe of the output via ffmpeg + cv2 | **yes** | `stages.py:254-343` |
| — ffmpeg backend | `ffmpeg -i in -ss (start − 1e-4) -frames:v N -y synced_<name>.mp4`: output-side seek (decodes from the start), **default encoder**, audio copied through re-encoded to AAC by default, **30 s timeout** | **yes**: generation 1 or 2 | `ffmpeg.py:153-185`; `config.py:24` |
| — deffcode backend | deffcode `FFdecoder` → bgr24 frames; keeps `[start, start+N)`; `cv2.VideoWriter` fourcc `mp4v` at deffcode's `output_framerate`; explicit transpose for rotated sources (with `-noautorotate`); no audio | **yes**: MPEG-4 Part 2 | `core/backends/deffcode.py:36-132` |
| VerifySynchronizedFramerate | Hard-fails unless every output has the identical float fps | no | `stages.py:346-370` |
| VerifySynchronizedFrameCount | Hard-fails unless every output has the identical cv2 frame count | no | `stages.py:373-402` |
| ReattachAudio | Trims the in-memory signals (`int(lag × sr)`, length from `videos[0].duration_seconds`), writes PCM_24 WAVs to `audio_files/trimmed_audio/`, then `ffmpeg -i video -i wav -c:v copy -c:a aac` into a temp file and moves it over the synced MP4. No `-map` | **yes**: remux, video copied | `stages.py:405-439`; `core/audio.py:89-115`; `ffmpeg.py:264-290` |
| DebugArtifacts | `synchronization_debug.toml`, `debug_plot.png`; brightness method also writes `<name>_brightness.npy` **into the raw (or normalized) folder** | no (reads outputs via cv2) | `stages.py:442-514`; `core/debug.py:21-127` |

Naming and containers [C]: outputs are always `synced_<name>.mp4` (`config.py:43-46`); discovery globs mp4/mkv/avi/mpeg/mov (`config.py:35-40`, `core/discovery.py`); KI-16 records "always `.mp4`" as a deliberate v1 decision (`docs/architecture/00-known-issues.md:22`).

### 1.2 Defaults and callers

- `SyncRequest.video_handler` defaults to **DEFFCODE** [C] (`core/models.py:45`), as do the CLI (`cli/main.py:50-52`) and the frontend (`frontend/src/screens/SetupScreen.tsx:16`, options `:105-106`).
- freemocap overrides it to **FFMPEG** [C] (`freemocap/api/http/mocap/mocap_router.py:279`), copies raw files into a temp `raw/` (`:265-273`), and later copies each `videos_after[i].filepath` to `synchronized_videos/<original stem>.mp4`, always `.mp4` (`:344-362`).
- The frozen API (PyInstaller) does not bundle ffmpeg. `check_for_ffmpeg()` needs `ffmpeg`/`ffprobe` on PATH [C] (`ffmpeg.py:28-43`; `packaging/pyinstaller/skelly-sync-api.spec` collects librosa data and hidden imports, no ffmpeg binary).

### 1.3 Facts checked on this machine (§8.4)

- The trim command, run on a synthetic 30 fps stereo-audio source, wrote libx264 High with `has_b_frames=2` (long-GOP, B-frames) and an AAC stereo track [M].
- `attach_audio`'s command with a mono WAV mapped `Stream #0:1` (the trimmed MP4's own audio) and ignored the WAV [M].

---

## 2. Design A: JPEG-in-MKV + sidecar outputs

### 2.1 Target shape

One pass per video, in a worker process:

```
open source (PyAV 19.0.2) ─► seek to keyframe ≤ start ─► decode (threaded) ─► pick source frames for output slots 0..N-1
   ─► to 8-bit full-range 4:2:0 (swscale), bake rotation ─► JPEG encode at the agreed quality (mjpeg_qsv, else libjpeg-turbo/simplejpeg)
   ─► mux packet into MKV (pts = slot index, time_base = 1/nominal_rate, flush_packets=1)
   ─► append sidecar record (slot, source frame index, times in ns, CRC32, offset, size)
audio (optional) ─► trimmed to the same window ─► WAV beside the MKV, or a lossless track in the MKV
```

This replaces `NormalizeFramerateStage`, both `VideoBackend.trim` implementations and `ReattachAudioStage`. Lag detection (audio, brightness) is unchanged.

### 2.2 Every place that writes video, and what changes

| # | Writer today | Change for Design A | Effort |
|---|---|---|---|
| A1 | **Normalize** `ffmpeg -r` → `normalized_videos/*.mp4` (`stages.py:151-201`, `ffmpeg.py:233-261`) | **Delete** as a separate pass. Frame-rate handling moves into the single encode pass (§2.4). Lag detection then runs on the originals. Audio sample-rate normalization is only needed for cross-correlation, so resample in memory (librosa `sr=` or PyAV `AudioResampler`), not by re-encoding video | M (with A2) |
| A2 | **Trim, ffmpeg backend** (`ffmpeg.py:153-185`) | Replace with a PyAV decode → JPEG → MKV writer (§2.3). It removes the ffmpeg-on-PATH dependency for video, because the PyAV wheel bundles FFmpeg [I], and removes the 30 s timeout bug | L |
| A3 | **Trim, deffcode backend** (`deffcode.py:79-132`, `mp4v`) | Delete, or keep only as a decoder behind the same writer. deffcode decodes to bgr24 (`:94`), and converting 4:2:0 → BGR → 4:2:0 costs CPU and chroma precision [I]. Recommend removing `VideoBackendKind.DEFFCODE` and `deffcode==0.2.6` (`pyproject.toml:31`) | S |
| A4 | **Audio reattach** (`ffmpeg.py:264-290`, `stages.py:405-439`) | Either write the trimmed audio as a WAV next to each MKV (already produced at `audio_files/trimmed_audio/*.wav`, `audio.py:112`), or mux it into the MKV as PCM/FLAC by stream copy. Either way, fix the length: compute it from `frame_count / nominal_rate`, not `videos[0].duration_seconds` (`stages.py:410-412`). See §2.6 | S |
| A5 | **Debug artifacts** (`stages.py:442-514`) | Plots unchanged (cv2 reads MKV). Stop writing `.npy` into the raw folder (`:487-492`); write it under the output folder. Add the sync record (§2.8) to the TOML or replace the TOML with it | S |
| A6 | **Verify stages** (`stages.py:346-402`) | Check from the sidecar, not by re-probing with ffprobe + cv2: equal record counts, equal nominal rate (rational, not float), every packet a JPEG (SOI…EOI), CRCs match. Keep one cv2 open-and-count as a compatibility check (freemocap reads with cv2) | S |
| A7 | **`synced_video_filename`** (`config.py:43-46`) | `.mkv`, plus `<stem>.sidecar.bin` (name to match skellycam 1.5's convention) | S |

### 2.3 Frame-exact trimming of long-GOP inputs

- **Decode is unavoidable.** Long-GOP sources (all GoPro, phone and most action-camera files) cannot be cut at an arbitrary frame without decoding from the previous keyframe. The output is a fresh JPEG per frame, so there is no GOP to preserve. That is the point of I-frames only.
- **How to select frames exactly:**
  - Seek with `container.seek(ts, backward=True, any_frame=False, stream=v)` to the keyframe at or before the start, then decode and discard until the first frame whose index ≥ `start_frame`.
  - Compute the index from the frame's pts, not a running counter after a seek: `idx = round((pts − stream.start_time) × time_base × rate)` for CFR sources.
  - Today's ffmpeg path decodes from frame 0 every time, through output-side `-ss`. The seek saves decode time on long offsets [I].
- **Variable frame rate is a real risk.** The phone clips on this machine report `r_frame_rate` 119/4 or 30/1 against `avg_frame_rate` 29.90–29.97 [M, §8.1 probe]. Action cameras normally record CFR [I, NV per model]. The writer must detect VFR (pts deltas not constant), then either refuse it, resample it to the nominal grid (dup/drop with flags in the sidecar), or record true per-frame times. Today's code treats fps as a single float everywhere (`core/models.py:23`).
- **Frame count:** use the count of decoded frames (or demuxed video packets), not `cv2.CAP_PROP_FRAME_COUNT` (`stages.py:118-124`). OpenCV estimates the count from duration × fps for some containers [I]. Reuse the existing logic `frame_count = min(count_i − start_i)` (`stages.py:302-306`).
- **Quality of the pick:** offsets are whole frames (`round(lag × fps)`, `stages.py:273`). Sub-frame residuals (up to ±½ frame, ±8.3 ms at 60 fps) can be written to the sidecar for later 2D time interpolation (PLAN 2.7) [I].

### 2.4 Differing frame rates without `-r` resampling

What freemocap needs today [C]: equal frame counts, paired by index. `_check_video_sync` rejects unequal counts (`mocap_router.py:186-196`). Posthoc reading goes through `VideoHelper` / `video_node` with cv2 (`core/pipeline/posthoc/video_group_helper.py:151-159`, `core/pipeline/posthoc/video_node.py:297-301`). PLAN 2.2 lists about 11 equal-count sites.

| Option | Output | freemocap today | Notes |
|---|---|---|---|
| **R1. Resample to the lowest rate in the encode pass** | Equal counts and one nominal rate. Each output slot takes the source frame at or before the slot time (PREV, as the canvas player uses). The sidecar records the source frame index and source time per slot | **Works unchanged** (index pairing) | Same behaviour class as today's `-r`, but one generation instead of two, and traceable. 60 → 30 is exact decimation; 59.94 vs 60 drops one frame every ~16.7 s [arith: 1/(60−59.94)]; 50 vs 60 gives an uneven pattern [I]. Loses temporal resolution on the faster cameras |
| **R2. Keep native rates, map in the sidecar** | Each camera keeps all its frames and its own count. A group sidecar maps each camera's frames to one sync timeline (ns), and optionally a slot table (slot k → frame index per camera, with fresh/repeated/missing flags) | **Does not work**: unequal counts are rejected | Matches PLAN 1.13 / 2.2 (time-based slots). freemocap must learn to read slot tables, which is phase 2 work |
| **R3. Both** | R2 files plus a materialized R1 copy for freemocap | Works | Doubles the encode work and disk for the faster cameras [I] |

Neutral note: R1 fits today's freemocap and the lockstep contract (PLAN 3.1). R2 fits where PLAN 2.2 is heading. Moving from R1 to R2 later means re-encoding, unless the originals are kept (Design B).

### 2.5 Pixel format, range, bit depth and rotation

- **Range.** `mjpeg_qsv` needs full-range input, or the JPEGs come out washed out (PLAN 1.4; `hw_accel_target/FINDINGS.md` F2) [M]. Action-camera H.264/HEVC is usually limited range [I]; 3 of 5 phone clips here were full range (`yuvj420p`) and 2 limited [M, §8.1]. Use swscale (`frame.reformat(format="yuvj420p")` or `nv12` with full range) to do the expansion in C. The rounding costs little: SSIM-Y of the rounded expansion against the float one is 0.9990 [M, §8.2].
- **Chroma.** The sources are 4:2:0, so write 4:2:0 JPEG. Upsampling to 4:2:2 adds bytes without adding information [I]. IC's 4:2:0 numbers apply (jt420, mjpeg_qsv_420).
- **10-bit and HDR.** GoPro HERO11/12 offer 10-bit at 4K and above [S] (gopro.com product pages, below). Phones record HDR10/PQ: the 4K and 1080p60 phone clips here are `yuv420p10le`, `smpte2084` [M, §8.1 probe]. Baseline JPEG is 8-bit. 10-bit SDR needs a dither or round to 8-bit. HDR (PQ/HLG) needs tone mapping, or the frames look flat and grey [I]. GP-Log footage (HERO12+, [W]) loses its grading latitude in 8-bit [I]. This needs a decision: refuse, tone-map, or keep the original (D-HDR).
- **Rotation.**
  - PyAV does not apply the display matrix; one 4K phone clip here carries `rotation=-90` [M, §8.1 probe].
  - Bake the rotation into the pixels (rotate the Y/U/V planes) and record `rotation_applied` in the sidecar header. Neither cv2 nor the canvas player would reliably honour a container rotation tag in MKV [I/NV].
  - The current deffcode transpose table (`deffcode.py:16-23`) is the reference for the angle conventions; port its tests (`tests/core/backends/test_deffcode.py`).

### 2.6 Audio

| Option | Pros | Cons |
|---|---|---|
| **Au1. Separate WAV per camera** (already produced, PCM_24, `audio.py:112`) | Simplest. librosa, browsers (WebAudio `decodeAudioData`) and freemocap tools read WAV [I]. Keeps the MKV a pure JPEG file, the same layout as skellycam recordings | Two files per camera; must travel with the MKV on import |
| **Au2. Audio track inside the MKV** (PCM or FLAC by stream copy from the WAV; AAC if size matters) | One file. Matroska carries any of these [I] | The canvas player reads frames by byte range and would need a separate path for audio. Some readers don't handle PCM-in-MKV [NV]. skellycam's 1.5 writer muxes audio "by stream copy" (PLAN 1.5), so being consistent with skellycam may favour Au2 |
| Au3. No audio | Smallest | Loses the evidence that the audio sync worked |

Whatever the choice, fix the selection bug (always `-map 0:v -map 1:a`, or write the WAV and skip the remux) and the length (frames ÷ rate).

**Audio and the sidecar (added 2026-11-12, from `skellycam_recording/recording_upgrade/results/sidecar_embedding/FINDINGS.md` §6.5–6.7):**
- Today's reattach pattern (write the video, then remux it with the audio and move the result over the output) moves every JPEG and changes the MKV's Segment UID: 0/1,800 offsets kept in a PyAV test [M]. A sidecar written during the encode is then wrong.
- Muxing FLAC audio in the same pass also breaks offsets taken live from the file size (0/1,799); PCM in step kept them (1,799/1,799) [M].
- So with Au2, offsets and the UID must be rebuilt by scanning the final MKV after the audio step: exact, about 0.1 s per 18,000 frames on a warm cache [M].

**Decided 2026-11-12 (Dom; plan D15, §2.8): Au2 with FLAC.**
- FLAC at the source rate, keeping the source channels, as a second track of each camera MKV, interleaved with the JPEG frames in the same PyAV pass. No remux.
- Then rebuild offsets by scan, add an audio packet table to the sidecar, and write the Segment UID.
- Measured in `skellycam_recording/recording_upgrade/results/audio_skellysync/FINDINGS.md`:
  - VLC plays video and audio in sync and seeks to the exact frame;
  - OpenCV's count and seeks are unchanged;
  - every video and audio CRC matched;
  - skellycam's player decodes the FLAC packets by offset with WebCodecs.
- That doc also covers the audio-window rule and a latent lag bug (audio start vs video start, its §5.2) to fix in either design.

### 2.7 Encoder choice

| Route | JPEG encoders available | Sidecar (offset/size/CRC) | Fit with project | Verdict |
|---|---|---|---|---|
| **PyAV 19.0.2 in-process** | `mjpeg_qsv` (opens at 3840×2160 on this machine [M, §8.4]); FFmpeg `mjpeg`. **libjpeg-turbo via simplejpeg 1.9.0**, with packets muxed through PyAV | Natural: the writer sees every packet's bytes and size | Project standard (PLAN 1.0); same ladder as skellycam 1.4 | **Recommended** |
| ffmpeg CLI (`-c:v mjpeg_qsv -global_quality N` or `-c:v mjpeg -q:v N`) | `mjpeg_qsv`, FFmpeg `mjpeg`; **no libjpeg-turbo** | Needs a second parse of the MKV to find offsets | Smallest diff to today's code; keeps the PATH dependency | Possible stopgap, not the target |
| deffcode → numpy → simplejpeg | libjpeg-turbo only (from BGR) | Writer must mux itself (PyAV anyway) | Extra dependency; BGR round trip | Not recommended |

Notes:
- **Knob mapping.** On the phone clips, `mjpeg_qsv` `global_quality` N and simplejpeg `quality` N give nearly the same SSIM-Y and 1.00–1.06× the bytes [M, §8.2]. This agrees with IC's mjpeg_qsv / libjpeg-turbo 0.99–1.12× at A (IC §2.3).
- **FFmpeg `mjpeg` is not in the ladder.** It is the slowest JPEG path (11.1 ms CPU/frame at 1080p, IC §3.3), and its knob at A is qscale 1–2 (`matched_settings.json`).
- **The `mjpeg_qsv` 3-call delay** (IC §2.5, F2) only matters for crash recovery. Here the source is still on disk, so a crashed job is simply re-run [I].
- **Licensing** is unchanged from PLAN §2.1: the PyAV wheel bundles GPL x264/x265 even if unused.

### 2.8 Sidecar and sync record

- **Reuse skellycam package 1.5's per-frame format; don't invent a second one.** The fixed record holds the frame number, times in integer ns, CRC, offset and size; the header holds the format, encoder and camera key (PLAN 1.5).
- How the 1.5 writer obtains byte offsets is that package's design. The playback study used "a sidecar index of byte offsets" (CC C28). Update 2026-11-12: every producer rebuilds offsets by scanning the final MKV after any remux or audio step, then writes the Segment UID, and can embed the sidecar as an attachment appended at the end of the file (`sidecar_embedding/FINDINGS.md` §7; plan §2.7). The shared format package (D-PKG) should hold the record codec, that scanner and the appender.
- **Fields skellysync adds:**
  - per record: `source_frame_index` (u64) and `source_pts_ns` (i64), so every output frame can be traced to the original;
  - header: source file name, size and a content hash; source codec, profile, bit depth, range and transfer; `rotation_applied`; `range_converted`; encoder and knob (for example `mjpeg_qsv gq=94`); the quality definition used (D-Q); nominal rate as a rational; and the sync block below.
- **Group sync record** (JSON, one per set; also the whole of Design B's output, §4):
  - `method`; `reference_camera`;
  - per camera: `lag_seconds`, `start_frame`, `confidence` (already in `LagResult`, `core/models.py:35-38`), `fps_rational`, `vfr` flag;
  - `shared_frame_count`, `framerate_policy` (R1/R2), `skellysync_version`, input hashes.
  - Sub-frame residual per camera (§2.3) [I].
- **Packaging.** skellysync should not import skellycam (a heavy dependency) [I]. The options are a tiny shared package for the sidecar format, or a vendored module with a format version and a shared test vector (D-PKG).

### 2.9 API, CLI, schema and frontend

| Area | Change | Code today |
|---|---|---|
| `SyncRequest` | Add `output_mode` (`jpeg_mkv` / `sidecar_only` / legacy `mp4` if kept), `encoder` (`auto` / `mjpeg_qsv` / `libjpeg_turbo`), `framerate_policy` (R1/R2), `audio_output` (Au1/Au2/none), `hdr_policy`. Replace `video_handler` (or reduce it to `pyav`) | `core/models.py:41-47` |
| `VideoInfo` | `fps` → rational + float; add width, height, codec, bit depth, range, rotation, `sidecar_path`, `start_frame` | `core/models.py:19-24` |
| `SyncResult` | Add `sync_record_path`, the encoder actually used, per-video bytes written | `core/models.py:50-59` |
| Config | Output extension `.mkv`; sidecar names; remove `NORMALIZED_VIDEOS_FOLDER_NAME` if A1 goes | `core/config.py` |
| CLI | `--output-mode`, `--encoder`, `--framerate-policy`, `--audio-output`; remove `--video-handler deffcode` | `cli/main.py:50-52` |
| API | Schemas follow the models automatically (FastAPI). Progress messages say "trimmed" (`api/jobs.py:66`); per-frame progress from the encode loop would be more useful for hour-long files [I] | `api/jobs.py`, `api/routers/jobs.py` |
| Frontend (Tauri) | `types.ts` union `"ffmpeg" \| "deffcode"` (`frontend/src/api/types.ts:1`); backend dropdown and its default (`SetupScreen.tsx:16, 105-106`); new fields for output mode and frame-rate policy; ResultScreen shows output folder and lags only, so add encoder, sizes and frame count | `frontend/src/` |
| Packaging | PyInstaller spec: add `av` and `simplejpeg` (with their DLLs, including the oneVPL runtime that `mjpeg_qsv` needs [I]); drop deffcode. The ffmpeg-on-PATH requirement could go if audio extraction also moves to PyAV | `packaging/pyinstaller/skelly-sync-api.spec` |
| Python / deps | `requires-python` `>=3.10,<3.13` → `>=3.12` (PyAV 19) or `>=3.13` to match the project; `librosa==0.10.1` pin (and its numba chain) must resolve on 3.13 [NV]; CI on 3.10 and only for PRs to `main` (`python-testing.yml:6, 18`) | `pyproject.toml:27, 31, 37` |

### 2.10 Tests that would change

| Test | Why |
|---|---|
| `tests/core/test_config.py:4-9` | Expects `synced_cam_1.mp4` |
| `tests/core/pipeline/test_stages.py` (`FakeBackend`, `_trim_video_worker`, TrimStage, Verify*) | The backend protocol and the trim worker change shape; Verify reads sidecars |
| `tests/core/backends/test_ffmpeg.py`, `test_deffcode.py` | ffmpeg trim/normalize/attach go; deffcode goes; port the transpose test to the rotation code |
| `tests/integration/test_audio_sync_pipeline.py`, `test_brightness_sync_pipeline.py` | Parametrized over FFMPEG/DEFFCODE; add asserts: MKV, codec `mjpeg`, every packet a JPEG, sidecar count = shared count, CRCs, cv2 count = shared count |
| `tests/integration/slow/test_sample_dataset.py` | Same asserts on the Figshare set |
| `tests/api/test_jobs.py`, `tests/cli/test_main.py` | New request/result fields |
| **New** | (1) frame-exactness: a long-GOP fixture with the frame number drawn into pixel blocks, then decode the output and check the exact numbers at the start and end; (2) mixed 30/60 fps (R1 decimation, R2 mapping); (3) rotated source; (4) limited-range source; (5) VFR source rejected or flagged; (6) 10-bit source handled per D-HDR; (7) `mjpeg_qsv` unavailable → libjpeg-turbo fallback |

The fixtures are already libx264 long-GOP at 64×64 / 10 fps (`tests/fixtures/README.md`), which suits a trim-exactness test, but they are too small for `mjpeg_qsv` minimum sizes [NV].

### 2.11 freemocap side

| Item | Change | Code |
|---|---|---|
| Copy to `synchronized_videos/` | Stop forcing `.mp4`: use `synced_video.filepath.suffix`. Copy the sidecar(s), WAV and group sync record too. An MKV renamed to `.mp4` would probably still open in cv2 (ffmpeg probes the content) but would mislead people and any `<video>` element [I] | `mocap_router.py:344-362` (comment `:346-349`) |
| `video_handler=VideoBackendKind.FFMPEG` | Replace with the new request fields | `mocap_router.py:279` |
| Extensions | `.mkv` is already in `VIDEO_EXTENSIONS` in freemocap (`api/http/playback/playback_router.py:47`, `system/recording_status/recording_status.py:19`) and in the skellycam module freemocap imports (`skellycam/core/recorders/videos/parse_video_filename.py:18`, used by `video_group_helper.py:15, 474`). `utilities/get_video_paths.py:8-9` globs only `*.mp4` (used by `get_number_of_frames_of_videos_in_a_folder.py`) | as listed |
| Reading | cv2 reads index-timestamped JPEG MKV with exact counts (18/18 files, PLAN §2.2, EI §2.1–2.2) [M]. `video_node` opens with `CAP_FFMPEG` (`video_node.py:297`). The decode cost per frame is JPEG instead of H.264, not measured for freemocap (PLAN phase-2 exit test) | — |
| Playback in freemocap-ui | `<video>` cannot play the outputs (CC C1, C2) [M]. They play only once the canvas player (PLAN 2.3) lands | — |
| Python floor | PyAV 19 in skellysync forces freemocap ≥ 3.12 (§0 item 4) | `freemocap/pyproject.toml:6` (PLAN §2.4) |

---

## 3. Playback: how the two players and the two designs interact

| | Design A (JPEG-in-MKV outputs) | Design B (originals + sync sidecar) |
|---|---|---|
| **Canvas player** (Range fetch + `ImageDecoder`; PLAN 1.9 / 2.3) | Plays them directly; this is the player built for this format (CC C27, C28) | Cannot play H.264/HEVC originals (it decodes JPEG stills only). Needs a JPEG conversion first |
| **`<video>` import player** (owner's choice for imported originals, PLAN 2.8) | **Cannot play them**: `<video>`, MSE and WebCodecs reject MJPEG in every container (CC C1, C2) [M] | Plays the originals; each element starts at `offset_seconds` from the sidecar. Known risks (PLAN 2.8): long-GOP seeks off by up to 2 frames or failing 2/10 (CC C9); HEVC has no software decode in Chromium (IP F10), and GoPro HERO11/12 record HEVC only [S]; 8 `<video>` elements stalled (IP F21) |

Consequences, without a recommendation:
- **If skellysync writes JPEG-in-MKV,** a sync result has to be shown in the canvas player. The `<video>` import player would show only the unsynchronized originals.
- **If originals stay in `<video>`,** the sync result can live entirely in a sidecar (Design B), and the import player applies the offsets. Frame accuracy is then limited by `<video>` seeking on long-GOP files.
- **A mixed route is possible:** show the originals in `<video>` for preview and sync checking, then convert to JPEG-in-MKV at import or processing time for freemocap and the canvas player. That is Design B followed by Design A's encoder run later.

---

## 4. Design B: keep originals, write only a sync sidecar

**What skellysync does.** Discover, probe, detect the lag (unchanged), compute `start_frame` and `shared_frame_count` (or the R2 mapping), then write the group sync record from §2.8. Normalize, Trim and ReattachAudio are skipped. Optional: write trimmed WAVs for checking, and the debug plot.

**What freemocap must do,** either:
- **B-read:** every reader skips `start_frame` frames and stops after `shared_frame_count`. Those readers are `VideoHelper`, `video_node`, calibration, playback, and the frame-count checks (about 11 sites, PLAN 2.2). Sequential decode and discard is exact; random seek in cv2 on long-GOP is not reliable [I]. Or:
- **B-convert:** at import or processing time, run Design A's encoder (§2) on the originals with the stored offsets. The work is the same as Design A, but deferred and optional.

| | Design A (JPEG output now) | Design B (sidecar only) |
|---|---|---|
| skellysync effort | L (§6) | S–M |
| freemocap effort | S–M (copy, suffix, sidecar) + canvas player (already planned, 2.3) | B-read: M–L (offset-aware readers); B-convert: Design A's encoder moved into freemocap or called from it |
| Extra disk | JPEG copies: about 1–17× the source, depending on mode and content (§5.3) | ~0 (a few kB of JSON) |
| Quality | One generation of JPEG loss on top of the camera's own long-GOP loss | Original quality |
| Compatibility with "JPEG only, I-frames only, everywhere" | Complies | **The originals stay long-GOP H.264/HEVC.** Whether imported originals count as "outputs" is an owner call (D-RULE). B-convert complies at the point of use |
| freemocap processing today | Works (R1) | B-read: needs reader changes; B-convert: works after conversion |
| Playback | Canvas player only | `<video>` import player (with its HEVC and seek limits) |
| Frame-rate change later (R1 → R2) | Needs a re-encode | Free: originals kept |
| Drift correction later (second sync point, PLAN 2.8) | Needs a re-encode | Free: add a rate term to the sidecar |
| Python floor | PyAV 19 → ≥ 3.12 | No new deps; could ship on today's stack [I] |

---

## 5. File sizes

### 5.1 Inputs used

**JPEG bytes per frame at target A.**
- **[M] our webcams (IC §3.1):**
  - 1080p jt420: 130,185 B on decoded camera MJPEG (A against the decoded frame); 265,001 B on raw YUY2.
  - `mjpeg_qsv_420`: 129,364 / 296,502 B.
  - 720p jt420: 55,459 / 147,259 B.
- **[M] new local check (§8), jt420 at A against the decoded source, 1080p30 camera-originated H.264 (phone clips as a stand-in for action-camera footage):**
  - P1 555,162; P2 697,887; P3 182,426; P4 516,678; P5 618,782 B;
  - **median 555,162 B, range 182–698 kB.**
  - At the fixed knob q94 the clips need 181,639–436,283 B.
- **[M] new local check, 4K:** one HDR10 4K60 HEVC phone clip, tone-mapped to SDR, at A: **1,322,646 B/frame**. Same frames at q94: 4K 1,060,046 B against 1080p 274,891 B, which is 3.86× for 4× the pixels [arith]. At q83 it is 4.78× [arith]. So pixel scaling is roughly right on this content [I].

**Source bitrates.**
- **[S] GoPro HERO11 Black:** HEVC only, max 120 Mb/s, 10-bit at 5.3K and 4K. https://gopro.com/en/us/shop/cameras/hero11-black/CHDHX-111-master.html, accessed 2026-11-11.
- **[S] GoPro HERO12 Black:** H.265 (HEVC), max 120 Mb/s, 8-bit, and 10-bit at 4K and higher. https://gopro.com/en/us/shop/cameras/hero12-black/CHDHX-121-master.html, accessed 2026-11-11.
- **[S, via a search index] HERO11 per-mode table.** GoPro support article "HERO11 Black: Video Settings And Resolutions", https://community.gopro.com/s/article/HERO11-Black-Video-Settings-And-Resolutions?language=en_US, accessed 2026-11-11. The page needs JavaScript and did not render for a direct fetch; the figures are the article text as returned by the search engine:
  - 4K60: 60 (Standard) / 100 (High) / 120 (10-bit) Mb/s;
  - 4K30: 45 / 100 / 120;
  - 5.3K60: 60 / 120 / 120;
  - 1080p60: 45 / 60;
  - 2.7K at 120/240 fps: 60 / 100.
- **[S, via a search index] GoPro HERO (2024):** "All video modes record with Standard, 8-bit encoding at a 50Mbps bitrate (4:3 has 60Mbps)". https://community.gopro.com/s/article/HERO-2024-Capture-Modes?language=en_US, accessed 2026-11-11, same caveat.
- **[S, via a search index] HERO12/13:** "Bit Rate is highly variable depending on the complexity of the scene", so High/Standard are ceilings, not constants. https://community.gopro.com/s/article/HERO13-Black-SD-Card-Capacity-In-Various-Settings?language=en_US, accessed 2026-11-11.
- **[W] older H.264 GoPros:** HERO5 Black ≤ 60 Mb/s and HERO6 ≈ 78 Mb/s (havecamerawilltravel.com, via search); HERO8/9 up to 100 Mb/s (retailer-hosted spec sheet and reviews, via search). HERO11+ record H.264 only at 1080p60 and below in 8-bit, per havecamerawilltravel.com [W].
- **[M] local phone clips (§8.1):** H.264 1080p30 12.0–17.0 Mb/s; HEVC 10-bit 1080p60 34–57 Mb/s; HEVC 10-bit 4K60 144–146 Mb/s.

### 5.2 Method

- **Bytes:** GB/h = bytes/frame × fps × 3600 / 10⁹ [arith].
- **Source:** GB/h = Mb/s × 0.45 [arith].
- **Pixel scaling from 1080p (1920×1080):** 2.7K (2704×1520) × 1.982; 4K (3840×2160) × 4.000; 5.3K (5312×2988) × 7.654 [arith].
- **Three JPEG rows**, all labelled [I]: they are pixel-scaled from measured 1080p bytes and assume bytes scale with pixel count. The 4K check above found 3.9–4.8×.
  - **J-low** = webcam on decoded-MJPEG basis (130,185 B): clean, low-noise content.
  - **J-yuy2** = webcam raw YUY2 basis (265,001 B).
  - **J-phone** = median of the five camera H.264 clips (555,162 B; range 182–698 kB).

Bytes depend on content. Action-camera footage with motion, water, foliage, low light or sensor noise can sit at or above J-phone; a static indoor scene can sit near J-low [I].

### 5.3 Per-camera GB/hour

| Mode | Source, typical (GB/h) | JPEG J-low [I] | JPEG J-yuy2 [I] | JPEG J-phone [I] (range) | J-phone ÷ source at High |
|---|---|---|---|---|---|
| 1080p30 | H.264 phone 12–17 Mb/s → 5.4–7.7 [M]; GoPro 1080p ≤ 60 Mb/s → ≤ 27 [S] | 14.1 | 28.6 | 60.0 (19.7–75.4) | 2.2× vs 27 GB/h |
| 1080p60 | GoPro 45 / 60 Mb/s → 20.3 / 27.0 [S]; HERO (2024) 50 → 22.5 [S] | 28.1 | 57.2 | 119.9 (39.4–150.7) | 4.4× |
| 2.7K60 | GoPro ≈ 60 / 100 Mb/s → 27 / 45 [S, from the 2.7K high-frame-rate rows; 2.7K60 itself is not in the snippet] | 55.7 | 113.4 | 237.7 (78–299) | 5.3× |
| 4K30 | GoPro 45 / 100 / 120 Mb/s → 20.3 / 45 / 54 [S] | 56.2 | 114.5 | 239.8 (79–302) | 5.3× vs 45 |
| 4K60 | GoPro 60 / 100 / 120 Mb/s → 27 / 45 / 54 [S]; phone HEVC 144 Mb/s → 64.8 [M] | 112.5 | 229.0 | 479.6 (158–603) | 10.7× vs 45 |
| 4K60, measured clip | phone HEVC 10-bit HDR 144 Mb/s → 64.8 [M] | — | — | **285.7 measured** (1,322,646 B/frame, tone-mapped) [M/arith] | 4.4× vs that clip |
| 5.3K60 | GoPro 60 / 120 Mb/s → 27 / 54 [S] | 215.2 | 438.1 | 917.9 | 17× vs 54 |

Reading it:
- **Even on the cleanest basis (J-low), JPEG at A is 1.0–4.0× a GoPro on High** at the same mode [arith]: 1080p60 28.1 vs 27 (1.0×), 4K30 56.2 vs 45 (1.25×), 4K60 112.5 vs 45 (2.5×), 5.3K60 215 vs 54 (4.0×).
- **On camera-like content (J-phone), JPEG is 2.2–17× High** (4K60: 10.7× High, 17.8× Standard) [arith].
- **With the fixed knob q94 instead of A-against-source,** the 1080p phone clips need 182–436 kB/frame (§8.2): 1080p30 19.6–47.1 GB/h and 4K60 157–377 GB/h [arith, pixel-scaled].
- **A 4-camera, 10-minute 4K60 session:** source at 100 Mb/s is 30 GB; JPEG is about 75 GB (J-low), 153 GB (J-yuy2) or 320 GB (J-phone) [arith: GB/h × 4 × 10/60].

### 5.4 CPU cost per stream

| Step | 1080p30 per stream | 4K60 per stream (pixel-scaled, [I]) | 4 × 4K60 |
|---|---|---|---|
| **`mjpeg_qsv` encode** | 16 streams at 1.05 cores (NV12) → 0.066 cores/stream; 4:2:2 from YUY2 0.92/16 = 0.058 [M] (IC §2.5, §3.5) | 8 × the 1080p30 pixel rate → about 0.5 cores of host CPU | About 2 cores of host CPU, **but the engine ceiling binds first**: 700 fps aggregate at 1080p (IC §3.5) ≈ 175 fps at 4K [I], against 240 fps needed. So roughly 0.73× real time [arith] |
| **libjpeg-turbo (simplejpeg) encode** | 16 streams at ≥ 1.69 cores → ≥ 0.11 cores/stream (process lower bound); 2.77 ms CPU/frame single-stream at A (IC §2.5, §3.3) [M]. Local re-check: 3.0–3.8 ms at q94–97 on phone frames [M, §8.3] | 10.9–12.1 ms/frame at q94–96 [M, §8.3] × 60 → 0.65–0.73 cores | **2.6–2.9 cores** [arith]; scales across processes (IC §2.5) |
| **Decode of the source (software, PyAV 19.0.2, auto threads)** | H.264 1080p30 12 Mb/s: 4.7 ms CPU/frame → 0.14 cores [M, §8.3] | HEVC 10-bit 4K60 144 Mb/s: **45 ms CPU/frame, 35 fps wall** for one stream → 2.7 cores, below real time [M, §8.3] | **≈ 10.9 cores** [arith] |
| Range/rotation/bit-depth conversion | swscale, not measured [NV] | not measured | not measured |
| Today, for comparison: libx264 re-encode (default preset) | libx264 veryfast at A from NV12: 31 ms CPU/frame (IC §3.3); the default preset (medium) is slower [I] | — | The JPEG path costs less CPU than today's trim [I] |

So for 4 × 4K60 inputs on the i7-14700K, decode plus libjpeg-turbo is about 13.5 core-seconds per second of footage [arith]. Run offline on 20 cores / 28 threads, that is roughly real time at best: a 10-minute session takes about 10 minutes or more [I]. Hardware decode (`d3d11va`/QSV through PyAV `hwaccel`) would cut the decode share and was not measured [NV].

### 5.5 How to firm up the size estimate cheaply

**Done here (§8):** five 1080p30 H.264 phone clips and one 4K HDR clip, 24 / 12 evenly spaced frames each, PyAV 19.0.2 decode, simplejpeg 1.9.0 and `mjpeg_qsv`. No camera and no download were needed.

**Next steps, if the owner wants a firmer number:**
1. Run the same script on **real GoPro files**: one per mode (1080p60, 2.7K60, 4K60, Standard and High, HEVC, plus an older H.264 model), 60–120 frames each, spread across action and static scenes. The script takes a JSON list of paths. The output is bytes/frame at A (against the decoded source), at q94 and at gq94.
2. Add a scene label (motion, low light) per clip and report the range, not one number.
3. Write a real MKV + sidecar per clip, to include container overhead. The JPEG bytes dominate; MKV overhead is a few bytes per frame (EI §2.2 notes +6 B/frame for an empty-packet variant) [I].

---

## 6. Effort per work item

S ≈ ≤ 2 days, M ≈ 3–7 days, L ≈ 2+ weeks, for one engineer familiar with the code [I].

| # | Item | Design | Effort |
|---|---|---|---|
| W1 | Python ≥ 3.12/3.13 for skellysync: `requires-python`, librosa/numba on 3.13, CI matrix and triggers | A (B only if PyAV is added) | M |
| W2 | Probe with PyAV: rational fps, exact counts, VFR detection, codec, bit depth, range, rotation | A, B | S–M |
| W3 | Group sync record (JSON schema, versioning) + writing it | A, B | S |
| W4 | PyAV decode → frame-exact selection → JPEG → MKV writer, with seek-to-keyframe, R1 resampling, rotation, range | A | L |
| W5 | Encoder ladder: `mjpeg_qsv` probe-encode-check, simplejpeg fallback, knob per D-Q | A | S (reuse skellycam 1.4) |
| W6 | Per-frame sidecar writer/reader, shared with skellycam 1.5 (package or vendored module) | A | M |
| W7 | R2 native-rate mapping and slot table | A (if R2) | M |
| W8 | Audio: WAV or MKV track, length and selection fixes | A | S |
| W9 | 10-bit / HDR handling per D-HDR (refuse, or tone-map with zscale/swscale) | A | S (refuse) – M (tone-map) |
| W10 | Remove the deffcode backend, `ffmpeg -r`, `attach_audio`; config and naming | A | S |
| W11 | Verify stages from the sidecar | A | S |
| W12 | API/CLI/schema changes | A, B | S |
| W13 | Tauri frontend: types, setup options, result screen | A, B | S–M |
| W14 | PyInstaller: bundle PyAV + simplejpeg, drop deffcode, test the frozen build with `mjpeg_qsv` | A | M |
| W15 | Tests: update existing + new fixtures (exactness, mixed fps, rotation, range, VFR, 10-bit, fallback) | A (B: smaller set) | M |
| W16 | freemocap `mocap_router`: suffix, copy sidecars/WAV/sync record, new request fields | A, B | S |
| W17 | freemocap readers apply offset/count (B-read) | B | M–L |
| W18 | Real-footage size and speed check (§5.5) | A | S |
| | **Total, Design A** | | **L: about 3–5 weeks in skellysync + S–M in freemocap** |
| | **Total, Design B** | | **S–M in skellysync (W2, W3, W12, W13, a smaller W15) + M–L in freemocap (W16, W17), or Design A's encoder later (B-convert)** |

---

## 7. Decisions the owner needs to make

| # | Decision | Options (neutral) |
|---|---|---|
| **D-DESIGN** | Output design | **Decided 2026-11-12 (Dom): Design A,** JPEG-in-MKV + `skellyformat` sidecar + FLAC per camera. Built on the shared `skellyformat[write]` layer that skellycam's recorder and its old-recording converter also use (plan §2.9 S10c, D17), which cuts A's cost well below the original 3–5 week estimate. Was: A · B sidecar only · B then convert |
| **D-RULE** | Do imported originals fall under "JPEG only, I-frames only, everywhere"? | **Settled by Design A (2026-11-12):** originals are inputs only and are never modified; everything skellysync writes, and everything played or processed downstream, is JPEG I-frames |
| **D-PLAYER** | Which player shows sync results | Canvas player (needs Design A or conversion) · `<video>` import player (needs B; HEVC hardware-decode and seek caveats, §3) · both (preview in `<video>`, process from JPEG) |
| **D-Q** | What "target A" means for re-encoding an already-lossy source | SSIM-Y 0.9961 against the decoded source, per-clip knob search (182–698 kB/frame at 1080p on phone clips) · fixed knob q94 / gq94, the setting that hits A on raw YUY2 (182–436 kB) · the knob that hits A on decoded webcam MJPEG, q83 (94–250 kB, SSIM-Y 0.986–0.994) [M §8.2] |
| **D-FPS** | Differing frame rates | R1 resample to the lowest rate, with a source-index map (works with freemocap today) · R2 native rates + mapping (needs PLAN 2.2) · R3 both |
| **D-AUDIO** | Audio output | **Decided 2026-11-12: Au2 with FLAC** (plan D15; §2.6). Was: Au1 separate WAV · Au2 PCM/FLAC/AAC track in the MKV · Au3 none |
| **D-HDR** | 10-bit, HDR and Log sources | Refuse with a clear error · tone-map to 8-bit SDR (and record it) · keep the originals (Design B) |
| **D-PY** | Python floor and timing | Wait for freemocap's 3.13 move (PLAN D3) and use PyAV 19 · use PyAV 18.x now on 3.11 [I] · ship Design B first (no new deps) |
| **D-PKG** | Where the sidecar format code lives | **Decided 2026-11-12: the shared package `skellyformat`** (plan D17), with a detailed spec document; skellysync depends on it, not on skellycam |
| **D-BACKEND** | Keep any old paths? | **Decided 2026-11-12 (Dom; plan D19): new skellysync writes only the new format** (JPEG-in-MKV + `skellyformat` sidecar, FLAC audio). Remove deffcode and the MP4 outputs. freemocap must still read `synced_*.mp4` files made by today's skellysync |
| **D-DRIFT** | Clock drift (PLAN 2.8) | Out of scope here · add a second sync point and a rate term (cheap in B; needs a re-encode in A) |

Also worth fixing whatever is decided, because these are existing defects [C]/[M]:
- the 30 s trim timeout (`ffmpeg.py:178`);
- the no-`-map` audio reattach (`ffmpeg.py:264-290`);
- the double encode after normalize (`stages.py:196-200`);
- the `.npy` written into the raw folder (`stages.py:487-492`).

---

## 8. Local measurement (this report)

**Run:** 2026-11-11 on Gerald (i7-14700K, UHD 770, RTX 3070, Windows 11). PyAV 19.0.2 (libavcodec 63.1.102), simplejpeg 1.9.0, Python 3.12.13, ffmpeg 9.0.2 (Gyan full build). CPU load at start: 4 %. Not pinned, not repeated.

**Files:** the script and raw JSON are in the session scratchpad, not in the repo, because the script names local personal media paths:
- `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\6082a5eb-540a-4bae-b0a9-d862f257c329\scratchpad\sizecheck\` holds `sizecheck.py`, `sizecheck_hiq.py`, `result.json`, `result_hiq.json` and `result_hiq2.json`.

**Method:**
- **Inputs:** personal phone clips from the user's Downloads folder. File names are withheld here on purpose; they are camera-originated long-GOP H.264/HEVC, a stand-in for action-camera footage, not GoPro files.
- **Frames:** 24 frames evenly spaced over each 1080p clip; 12 frames (every 150th) for the 4K clip.
- **Conversion:** decoded with PyAV to 8-bit 4:2:0. Limited-range sources were expanded to full range in float, then rounded.
- **Encode:** simplejpeg `encode_jpeg_yuv_planes` (4:2:0, `fastdct=False`) and `mjpeg_qsv` (NV12, full range).
- **Decode back:** libjpeg-turbo gray (Y) decode.
- **Metric:** SSIM-Y with the same parameters as IC (`iclib.ssim`), against the decoded source Y.
- **Target A:** SSIM-Y 0.9961, linearly interpolated between the two bracketing knob values.

### 8.1 Clips (ffprobe)

| Label | Codec | Size, rate | Bit rate | Range / transfer |
|---|---|---|---|---|
| P1 | H.264 | 1920×1080, 30 (avg 30.0) | 12.0 Mb/s | limited, smpte170m |
| P2 | H.264 | 1920×1080, 30 (avg 29.99) | 13.1 Mb/s | limited, bt709 |
| P3 | H.264 | 1920×1080, 30 (avg 29.98) | 16.8 Mb/s | full (`yuvj420p`), bt709 |
| P4 | H.264 | 1920×1080, 30 (avg 30.0) | 17.0 Mb/s | full, bt709 |
| P5 | H.264 | 1920×1080, 30 (avg 30.0) | 17.0 Mb/s | full, bt709 |
| P6 | HEVC Main 10 | 3840×2160, 60 | 144.2 Mb/s | limited, `smpte2084` (HDR10), BT.2020 |
| (others seen) | HEVC Main 10 | 1920×1080, 59 (avg 59.27) | 34–57 Mb/s | HDR10 |
| (others seen) | HEVC Main 10 | 3840×2160, 60, one with `rotation=-90` | 144–146 Mb/s | HDR10 |
| (VFR example) | H.264 | 1920×1080, r 119/4 vs avg 29.90 | 17.0 Mb/s | full |

### 8.2 Bytes per frame (simplejpeg 4:2:0) and SSIM-Y against the decoded source

| Clip | q83 | q94 | q96 | q97 | q98 | **At A (0.9961)** | mjpeg_qsv gq83 / gq94 |
|---|---|---|---|---|---|---|---|
| P1 | 219,545 (0.98940) | 393,878 (0.99364) | 491,292 (0.99548) | 555,640 (0.99610) | 633,936 (0.99666) | **555,162** | 220,575 (0.98952) / 404,563 (0.99374) |
| P2 | 244,670 (0.98571) | 436,283 (0.99201) | 543,140 (0.99445) | 614,338 (0.99533) | 701,804 (0.99614) | **697,887** | 245,830 / 445,765 |
| P3 | 94,041 (0.99380) | 181,639 (0.99608) | 230,509 (0.99762) | — | — | **182,426** | 95,568 / 192,472 (0.99632) |
| P4 | 249,689 (0.98960) | 435,817 (0.99442) | 536,071 (0.99650) | 601,724 (0.99720) | 675,051 (0.99784) | **516,678** | 250,228 / 445,245 |
| P5 | 242,512 (0.98581) | 435,473 (0.99232) | 540,797 (0.99499) | 610,334 (0.99600) | 690,543 (0.99695) | **618,782** | 243,369 / 446,035 |
| P6 4K (tone-mapped) | 531,357 (0.98734) | 1,060,046 (0.99386) | 1,337,300 (0.99623) | — | — | **1,322,646** | 535,505 / 1,107,410 |
| P6 2.7K (lanczos from the tone-mapped 4K) | 251,102 | 575,359 | 760,036 (0.99250) | — | — | not reached by q96 | 254,503 / 604,416 |
| P6 1080p (same) | 111,083 | 274,891 | 373,878 (0.98985) | — | — | not reached by q96 | 113,466 / 289,639 |

Notes:
- **Rounding ceiling.** The limited-range expansion with rounding scores SSIM-Y 0.99906 (P1) and 0.99903 (P2) against the float reference, so it is not what limits A [M].
- **PSNR-Y at A** was about 50.8–52.2 dB on the 1080p clips (interpolated from the table rows), close to IC's 51.7–52.6 dB at A.
- **Why A sits so high on these clips** [I]: the decoded H.264 frames contain sensor noise and codec texture, and JPEG has to reproduce them to reach SSIM-Y 0.9961 against that frame.
- **Downscaled P6 frames are denser per pixel**, so A is not reached by q96 at 2.7K and 1080p. That is why pixel-count scaling from 1080p to 4K (J-rows) is an estimate, not a law [I].

### 8.3 Speed (single process, unpinned; indicative only)

- **simplejpeg encode, single thread:** 1080p 1.9–3.6 ms/frame (q70–q96), 3.8–5.4 ms (q97–q100); 2.7K 3.8–6.2 ms; 4K 7.8–12.1 ms (q70–q96; q94 10.9 ms, q96 12.1 ms).
- **PyAV software decode, `thread_type="AUTO"`, 300 frames:**
  - P1 H.264 1080p: 2,329 fps wall, 4.74 ms CPU/frame;
  - P6 HEVC 10-bit 4K60: **35.3 fps wall, 45.3 ms CPU/frame**.

### 8.4 Functional checks

- `mjpeg_qsv` via PyAV 19.0.2 opened at 3840×2160 (NV12, `global_quality=94`) and returned 5 packets for 5 frames after flush. FFmpeg `mjpeg` also opened at 4K.
- **Today's trim command.** A synthetic source (testsrc2 320×240 at 30 fps, stereo AAC, libx264) was trimmed with `ffmpeg -i src.mp4 -ss 0.9999 -frames:v 60 -y trimmed.mp4`. Output: H.264 High, `has_b_frames=2`, 60 frames, plus an AAC 2-channel track of 1.997 s.
- **Today's reattach command.** `ffmpeg -i trimmed.mp4 -i mono.wav -c:v copy -c:a aac` → stream mapping `#0:1 -> #0:1`: the output audio is the trimmed MP4's stereo track, and the WAV is not used.

---

## 9. Sources

- **skellysync** `0231c41`, files cited inline:
  - `core/pipeline/{runner,stages}.py`, `core/backends/{base,ffmpeg,deffcode}.py`, `core/{audio,brightness,debug,config,models,discovery}.py`;
  - `api/`, `cli/main.py`, `tests/`;
  - `frontend/src/{api/types.ts,screens/SetupScreen.tsx}`, `packaging/pyinstaller/skelly-sync-api.spec`, `pyproject.toml`, `.github/workflows/python-testing.yml`, `docs/architecture/00-known-issues.md`.
- **freemocap** `5632778a`: `freemocap/api/http/mocap/mocap_router.py`, `api/http/playback/playback_router.py`, `system/recording_status/recording_status.py`, `core/pipeline/posthoc/{video_group_helper,video_node}.py`, `utilities/get_video_paths.py`, `uv.lock`.
- **skellycam:** `skellycam/core/recorders/videos/parse_video_filename.py`.
- **Research:** PLAN §2.1, §2.2, §2.4, 1.4, 1.5, 1.13, §4 (2.2, 2.3, 2.8), D2, D3; IC §2.2–2.5, §3.1, §3.3, §3.5 and `matched_settings.json`; EI §2.1, §2.2, §2.12; CC C1, C2, C9, C27, C28; IP F10, F21; `hw_accel_target/FINDINGS.md` F2 (as cited in PLAN).
- **Web**, accessed 2026-11-11:
  - [S] https://gopro.com/en/us/shop/cameras/hero11-black/CHDHX-111-master.html
  - [S] https://gopro.com/en/us/shop/cameras/hero12-black/CHDHX-121-master.html
  - [S, search index only] https://community.gopro.com/s/article/HERO11-Black-Video-Settings-And-Resolutions?language=en_US
  - [S, search index only] https://community.gopro.com/s/article/HERO-2024-Capture-Modes?language=en_US
  - [S, search index only] https://community.gopro.com/s/article/HERO13-Black-SD-Card-Capacity-In-Various-Settings?language=en_US
  - [W] https://havecamerawilltravel.com/action/gopro-hevc-h264-video/ and its HERO6/HERO11 bitrate pages (403 on direct fetch; text via search)
  - [W] https://www.netram.fr/out/media/CHDHX-802-XX-spec-sheet.pdf (HERO8 "up to 100 Mbps", via search)
