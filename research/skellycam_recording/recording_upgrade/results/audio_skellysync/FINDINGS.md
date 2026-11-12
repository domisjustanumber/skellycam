# skellysync: audio in the synchronised output files

2026-11-12, Gerald (Windows 11, i7-14700K). For `research/skellysync_jpeg/SCOPE.md` §2.6 (D-AUDIO) and the sidecar spec (`research/CAPTURE_AND_RECORDING_PLAN.md` rev 3.5 §2.7, S3). Nothing in skellysync, skellycam or freemocap was changed. Scripts are in `scripts/audio_skellysync/`. Test media were synthetic and stayed in the session scratchpad; they are rebuildable and were not kept.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked these against the result files: the OpenCV frame-count table (`frame_count_vs_audio.json`), every compatibility row's OpenCV, PyAV, VLC and CRC numbers (`compat_summary.json`), and the R1 result (`r1_resync.json`). Note: `compat_summary.json` shows ±7,200 samples for `opus_r1_60to30`. That is the generic checker matching a neighbouring burst 150 ms away; `r1_resync.json` reran it with a ±60 ms window and got 0 on 51/51.*

**Labels:** **[M]** measured (result file named) · **[S]** primary source · **[C]** code read (skellysync paths relative to `skelly_synchronize/` at `0231c41`) · **[I]** inferred · **[NV]** not verified · **[arith]**.

**Versions:** PyAV 19.0.2 (libavformat 63.1.102, FFmpeg 9.0.2) and OpenCV 5.0.0 from the `skellycam-phase1` venv, used read-only; FFmpeg/ffprobe/ffplay CLI 9.0.2; VLC 3.0.24; Electron 35.7.5 (Chrome 134) and 45.2.3 (Chrome 156). mpv is not installed [NV]. Nothing was installed.

**Short names:** `CS` = `compat_summary.json` (raw data in `compat_raw.json`); `E35`/`E45` = `electron_e35.json`/`electron_e45.json`; `FC` = `frame_count_vs_audio.json`; `SZ` = `sizes.json`; `SE` = `results/sidecar_embedding/FINDINGS.md`.

## 0. Recommendation
1. **Design A: one MKV per camera** with the JPEG track plus one audio track, written in the same PyAV pass. No remux, no separate WAV for players, no AAC.
2. **Codec: FLAC 16-bit at the source rate, keeping the source channels (up to 2).** Opus 48 kHz (libopus, 128 kb/s stereo / 64 kb/s mono, VBR) is the size option. Both are royalty-free [S], both are in the PyAV 19.0.2 wheel [M], and both passed every test.
   - Why FLAC: no second lossy generation on top of the camera's AAC; no resampling; no decoder delay (VLC plays it sample-exact, Opus 6.5 ms late); no special handling for the OpenCV frame count.
   - Cost: 0.84–1.24 Mb/s on realistic proxies, against 0.10–0.12 Mb/s for Opus [M, SZ]. That is under 5 % of a 1080p30 JPEG track (about 31 Mb/s) [arith].
3. **With Opus, drop the last 312 samples** (the pre-skip) so the audio track ends where the video ends. Otherwise OpenCV's `CAP_PROP_FRAME_COUNT` is one high at 120 fps in 20/20 files [M, FC].
4. **Player: WebCodecs `AudioDecoder` on audio packets fetched by byte range at offsets indexed in the sidecar,** with `description` = the track's CodecPrivate. Sample-exact for Opus, FLAC and Vorbis in E35 and E45 [M]. Fallback: `<audio src=camera.mkv>`, which plays the audio of an MJPEG+audio MKV and seeks [M].
5. **Sidecar:** an audio header block plus a 32-byte audio packet table, both rebuilt by scanning the final file (SE §7).
6. **Design B:** nothing is written. The sync record states each camera's audio-to-video start offset, the lag in both domains, and the sample window.
7. **Fix the latent lag bug either way:** the lag is measured on audio that starts at the audio stream's start but applied from the video's start (§5.2).

## 1. Codec and container
### 1.1 Royalty status
| Codec | Statement | Other evidence | PyAV 19.0.2 wheel |
|---|---|---|---|
| Opus (A_OPUS) | "These patents are available under open-source-compatible, royalty-free licenses."; "automatically granted to everyone" [S] https://opus-codec.org/license/ (2026-11-12) | 5 IETF disclosures on RFC 6716, 11 on the draft. 4 holders declared RAND "with Possible Royalty/Fee" [M] (`results/licensing/FINDINGS.md` §2.3) | `libopus` encoder and decoder [M]. Asking for `opus` resolves to libopus [M] |
| FLAC (A_FLAC) | "is non-proprietary, is unencumbered by patents" [S] https://xiph.org/flac/ (licensing NOTES Q54) | 0 IETF disclosures (RFC 9639) [M] | native `flac`, s16 and s32/24-bit [M] |
| Vorbis | "fully open, non-proprietary, patent-and-royalty-free" [S] https://xiph.org/vorbis/ | — | only the experimental native `vorbis` encoder, no libvorbis [M]. It ignored the 128k target: 298–459 kb/s [M, SZ] |
| AAC, MP3 | excluded | AAC: fee from the first unit (licensing Q57) | encoders present; must not be used |

Matroska has 0 IETF disclosures. Not legal advice.

### 1.2 Size and CPU (60 s of 48 kHz stereo, synthetic proxies, SZ)
| Encoding | Quiet room | Speech-like | Loud ambient | White noise | CPU, ms per audio second |
|---|---|---|---|---|---|
| FLAC 16 stereo | 841 kb/s | 877 | 1,237 | 1,455 | 1.0–1.3 |
| FLAC 24 stereo | 1,609 | 1,645 | 2,005 | 2,227 | 1.0–1.3 |
| FLAC 16 mono | 423 | 451 | 621 | 706 | 0.5–0.8 |
| Opus 128k stereo | 112 | 101 | 112 | 116 | 4.7–6.8 |
| Opus 96k stereo | 83 | 72 | 82 | 86 | 4.4–6.3 |
| Opus 64k mono | 56 | 52 | 56 | 56 | 2.9–3.4 |
| Vorbis "128k" | 341 | 298 | 341 | 459 | 11.7–13.5 |
| PCM s16 stereo | 1,536 | 1,536 | 1,536 | 1,536 | 0.3 |

- These are proxies; real decoded camera AAC is [NV]. On the sync clips: FLAC 794 kb/s, Opus 115 kb/s, against a 7.0 Mb/s 640×360 JPEG track [M, CS].
- Against SCOPE §5: FLAC is 2.7–4.7 % of 1080p30 (about 31 Mb/s) and under 0.6 % of 4K60 (250–1,070 Mb/s); Opus is about 0.4 % and 0.05 % [arith].
- 24-bit roughly doubles the size [M] and adds nothing for decoded AAC [I].

### 1.3 Rate and channels
- **Opus is fixed at 48 kHz** (the libopus encoder offers 48/24/16/12/8 kHz) [M]. 44.1→48 kHz by `scipy.signal.resample_poly` or by PyAV `AudioResampler` (swr) was sample-exact at the median: L 0..0, R −16..0. The spread is already present when the 44.1 kHz AAC source is decoded [M].
- **FLAC keeps 44.1 kHz** [M].
- **Keep the source channels.** librosa's mono is only for correlation (`stages.py:216`) [C]. Every stereo variant passed the L/R identity and polarity check [M].
- More than 2 channels [NV]: downmix or refuse (decision).

## 2. Compatibility, measured
**Source:** MJPEG + AAC stereo 192k in MP4, 30 or 60 fps, 48 or 44.1 kHz. Each frame shows its index in pixels. Flash frames are irregular (9–25 apart), each with a 4 ms burst starting on its own sample (`gen_source.py`).

**Output:** `sync_writer.py` cut frames 47–496 (450 frames, 15 s). Errors are found minus expected burst onset, in samples.

| Variant | ffprobe / ffmpeg decode | PyAV frames; A/V | OpenCV count; seeks; vs twin | VLC play (decoder; frames; A/V) | VLC start-time 7 s (slot; A/V) | ffplay |
|---|---|---|---|---|---|---|
| none (twin) | ok/0 | 450/450 | 450; 11/11 | avcodec; 449–450 | 210 | rc 0 |
| Opus 128k st (+embedded sidecar) | ok/0 | 450/450; 0..0 both channels | 450; 11/11; pixels 450/450, seeks 11/11 identical | opus; 450; +312 | 210; +312 | rc 0 |
| Opus 64k mono | ok/0 | 0..0 | identical | opus; +312 | 210; +312 | rc 0 |
| FLAC 16 st (+embedded) | ok/0 | 0..0 | identical | flac; 450; 0..0 | 210; −384 | rc 0 |
| FLAC 24 st | ok/0 | 0..0 | identical | flac; 0..0 | 210; −384 | rc 0 |
| Vorbis | ok/0 | 0..0 (R −1..0) | **451**; 450 read; identical | vorbis; 0..0 | 210; +1152 | rc 0 |
| PCM s24 (control) | ok/0 | 0..0 | identical | araw; 0..0 | 210; 0 | rc 0 |
| Opus from 44.1 kHz (poly/swr) | ok/0 | L 0..0, R −16..0 | 450; 11/11 | opus; +312 | 210; +312 | rc 0 |
| FLAC 44.1 kHz | ok/0 | L −7..0 | 450; 11/11 | flac; L −7..0 | 210; −36 | rc 0 |
| Opus / FLAC, video starts 0.1 s after audio | ok/0 | 0..0 | 450; 11/11 | +312 / 0..0 | 210 | rc 0 |
| R1 60→30 fps, Opus | ok/0 | 450/450 PREV slots; 51/51 bursts 0..0 (`r1_resync.json`) | 450; 11/11 | +312 (`r1_vlc.json`) | 210; +312 | rc 0 |

Notes:
1. **FFmpeg applies the Opus CodecDelay and the trailing DiscardPadding:** 720,000 samples decoded of 720,000 written [M].
2. **VLC plays video and audio and seeks to the exact slot** [M].
   - Opus is 312 samples (exactly the pre-skip) late before and after a seek. VLC appears not to subtract CodecDelay [M; cause I]. RFC 9559: CodecDelay "MUST be subtracted from each frame timestamp" [S]; ffprobe shows the first Opus packet at −7 ms.
   - Post-seek offsets are codec-dependent and all under ⅓ of a frame at 30 fps.
   - Method: VLC `afile` output aligned to the first `scene` frame. This is decode-timeline alignment, not wall-clock playback [I]. The scene filter writes one stale slot-0 frame before a seek on video-only, FLAC and PCM files; the checker skips it.
3. **OpenCV is unchanged by Opus, FLAC and PCM.** Vorbis made the count 451, because the container duration was 15.021 s (§2.3).
4. **ffplay** played every file to the end, with dummy SDL drivers. mpv [NV].
5. **Embedded sidecar plus audio:** 1,201/1,201 (Opus) and 607/607 (FLAC) blocks unchanged, Segment UID kept [M].

### 2.1 Offsets with audio interleaved
- An element-header scan of the final MKV (`common.scan_mkv`) matched the CRCs of video 450/450 in every variant, and audio 751/751 (Opus), 157/157 (FLAC), 705/705 (Vorbis). Scan time 8–17 ms per file [M].
- 0 laced blocks in 13 variants [M]: one SimpleBlock is one packet.
- Live offsets are not used (they fail with FLAC, SE §6.5).

### 2.2 Timing
- Video packets with a fixed 1/fps time base: first pts 0, 33, 67 ms [M] (no SE §1 pitfall). Audio packets keep the encoder's 1/rate; Opus spacing is 20 ms.
- FFmpeg writes Opus CodecPrivate = OpusHead (19 B), CodecDelay 6,500,000 ns and SeekPreRoll 80,000,000 ns [M], as the Matroska codec mapping requires [S] (matroska.org codec_specs).
- Opus block timestamps start at 0 with the pre-skip included; FFmpeg's demuxer subtracts the delay [M].

### 2.3 OpenCV frame count versus the audio end (FC)
OpenCV derives `CAP_PROP_FRAME_COUNT` from the container duration × fps, and the container duration is that of the longest track [I from the data]. freemocap and skellysync both use this count [C].

| 20 consecutive frame counts | 30 fps | 60 fps | 120 fps | Audio past the video end |
|---|---|---|---|---|
| Opus, all N samples | 20/20 | 20/20 (0.33 ms margin) | **0/20** | 7.3–8.0 ms |
| Opus trimmed to whole packets | 20/20 | 20/20 | 17/20 | −0.7–6.0 ms |
| **Opus, N − 312** | 20/20 | 20/20 | **20/20** | 0.7–1.3 ms |
| FLAC | 20/20 | 20/20 | 20/20 | −0.3–0.7 ms |

- Frames read were always correct; only the reported count was wrong [M].
- Rule: the audio must not overhang the video. For Opus, set `opus_end_align=True`. Checked at 60 fps: 900/900 frames exact, 51/51 bursts 0..0, count 900 [M, `endalign_check.json`].

## 3. Canvas player (Electron, file://, muted; E35/E45)
| Path | E35 | E45 |
|---|---|---|
| WebCodecs, Opus, `description` = CodecPrivate | 0..0, 720,648 frames | 0..0 |
| WebCodecs, Opus, no `description` | +312, 720,960 frames | +312. Chunks shifted by −CodecDelay come out at −6,500 µs; placing by timestamp gives 0 |
| WebCodecs, FLAC 16/24, `description` (fLaC + STREAMINFO) | 0..0, 720,000 | 0..0 |
| WebCodecs, FLAC, no `description` | throws "description is required" | configure fails |
| WebCodecs, Vorbis, `description` = CodecPrivate | 0..0 | 0..0 |
| Fetch cost, 15 s of audio | Opus 751 reads in 411–500 ms; FLAC 157 reads in 106–142 ms | 647–729 ms; 137–141 ms |
| `<audio src=mkv>` | loads, plays (peak 0.44), seeks to 7.000; Opus, FLAC, PCM, Vorbis | same |
| `<video src=mkv>` | plays the audio only, `videoWidth` 0 | same |
| `<video>` on the video-only MJPEG MKV | `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` | same |
| `decodeAudioData` on the whole MKV | all 0..0 | FLAC/PCM 0..0; Opus −24, Vorbis −1024 |
| Separate `.opus` / `.webm` / `.mka` / `.flac` / `.wav` | all play; 0..0 | all play; Opus `.webm`/`.mka` −24 |

- W3C Opus registration: with a `description` "the bitstream is assumed to be in ogg format", and the header's pre-skip initialises the samples to discard (default 0) [S]. FLAC's `description` is required [S].
- WebCodecs ignores DiscardPadding (720,648 against FFmpeg's 720,000), so the player stops at the sidecar's `total_samples`.
- E35 clamps negative chunk timestamps to 0, so place audio by sample index, not by `AudioData.timestamp`.
- Range reads cost 0.55–0.97 ms each under `file://`; over HTTP [NV].

**Choice: (a) WebCodecs on indexed packets.**
- It reuses the Range-plus-offset machinery, needs no second file, decodes only what is played, and is scheduled on the master clock through an AudioContext [I].
- Seek: decode from `t − SeekPreRoll` (80 ms for Opus, 0 for FLAC) and drop output before `t`. Mute while scrubbing.

**(b) `<audio src=mkv>`** is the quick fallback. It reads the whole MKV including the JPEG bytes [I], and its `currentTime` precision is [NV].

**(b') `decodeAudioData`:** not advised. One hour of stereo float is 1.38 GB [arith], and E45 is off by 24 samples on Opus.

**(c) A separate file** is not needed for skellysync.

**Reconciliation with `results/audio_skellycam/` (not read):** the WebCodecs path needs only a URL, a packet table, a codec string and `description`. If skellycam's separate file is `.mka` (FLAC or Opus), the same scanner indexes it, giving one player audio path for both producers. FLAC suits re-encoding lossy camera AAC; Opus may suit raw-microphone capture.

## 4. Sidecar audio fields (proposal) [I]
**Header, JSON `audio` block:**
- `track_number`, `codec_id`, `webcodecs_codec`, `sample_rate`, `channels`, `channel_layout`;
- `codec_private` (base64; the WebCodecs `description`);
- `codec_delay_samples` (312 / 0), `seek_preroll_samples` (3,840 / 0);
- `total_samples`, after the delay;
- `first_sample_offset_ns`, relative to video frame 0: 0 by construction;
- `encoder` and its settings;
- `source` `{stream_index, codec, sample_rate, channels, start_minus_video_start_ns, window_first_sample, pad_front_samples, pad_back_samples, resampled_from, resampler}`.

**Audio packet table, 32-byte little-endian record, after the per-frame records:**

| Bytes | Field | Notes |
|---|---|---|
| 0–7 | `offset` u64 | |
| 8–11 | `size` u32 | |
| 12–15 | `n_samples` u32 | |
| 16–23 | `first_sample` i64 | after the delay; Opus starts at −312 |
| 24–27 | `crc32` u32 | |
| 28–31 | `flags` u32 | keyframe, discard padding, last |

The header gives `audio_table_offset` and `audio_record_count`. Size: FLAC 1.2 MB per camera-hour, Opus 5.8 MB per camera-hour [arith].

## 5. Writing it in skellysync (Design A)
### 5.1 One pass per camera (prototype `sync_writer.py`)
1. **PyAV probe:** video `start_time`, `average_rate`, demuxed frame count; audio codec, rate, channels and `start_time`. MP4 edit lists are applied, so AAC priming is gone (first pts 0, 0-sample error [M]).
2. **Lag stage:** decode with PyAV (drops the CLI WAV step, `ffmpeg.py:217-230`). Downmix and resample in memory for the correlation only (replaces the `-ar` re-encode, `ffmpeg.py:233-261`). Then apply §5.2.
3. **Window:** `t0 = video_start + start_frame / src_fps`, `N = round(frame_count × rate / out_fps)`. First source sample = `round((t0 − audio_start) × rate)`. Pad with silence where the source has none, and record the padding.
   - This replaces `videos[0].duration_seconds` (`stages.py:410-412`) and `int(lag × sr)` (`audio.py:108`).
   - In-file A/V equals the source's. The sub-frame residual goes in the sidecar.
4. **Mux:** exactly one mjpeg stream and one audio stream.
   - Per frame k: encode the samples `[round(k·rate/fps), round((k+1)·rate/fps))` with pts = sample index and time base 1/rate, and mux them; then mux JPEG k with pts = k and the fixed 1/out_fps time base.
   - Flush the encoder. For Opus, write N − 312 samples.
5. **Finalise:** close → scan → check all CRCs → tables → Segment UID → sidecar → optional append. Measured: all CRCs matched, scan 8–17 ms, embed 5.5–7.5 ms [M].
6. **Verify:** sidecar counts; one cv2 count equals `frame_count`; decoded audio equals `total_samples`.

**`-map` bug class:** there is no remux and no second input, so no default stream selection. Delete `attach_audio` (`ffmpeg.py:264-290`), `ReattachAudioStage` (`stages.py:405-439`) and the trim's implicit AAC passthrough (`ffmpeg.py:153-185`) [C].

**R1:** audio depends only on `t0` and `frame_count / out_fps`. 60→30: 51/51 bursts 0..0, including dropped flash frames [M].

### 5.2 Latent bug: audio start versus video start
- `ffmpeg -i video out.wav` (`ffmpeg.py:224`) starts at the audio stream's start. In the test file whose video starts 0.1 s after its audio, frame n's burst sat at n/30 + 0.1 s [M].
- The lag between WAVs (`audio.py:51-86`) is applied as `start_frame = round(lag × fps)` (`stages.py:273`). skellysync never probes start times (`ffmpeg.py:90-151`) [C].
- Error: (audio_start − video_start) per camera, minus the reference camera's value [I]; size on real files [NV].
- Fix: video lag = audio lag + (audio_start − video_start), then renormalise.

### 5.3 Design B
- The audio stays inside each original (usually AAC). skellysync writes none; B-convert would write FLAC.
- The sync record, per camera: `audio_stream_index`, codec, rate, channels; `audio_start_minus_video_start_s`; `lag_audio_s` and `lag_video_s`; `start_frame`; `residual_s`; `audio_window_first_sample` and `audio_window_samples` (own samples); `reference_camera`, `shared_frame_count`, `confidence`; the sign convention.
- The `<video>` import player plays each original with its own audio and should unmute only one camera [I].

## 6. Tests to add
1. A burst fixture (frame index in pixels, irregular flashes, distinct L/R): 0-sample A/V, channels kept, frames exact.
2. A source whose video starts after its audio; a 44.1 kHz source.
3. R1 60→30 with bursts on dropped frames.
4. cv2 count = `frame_count` at 30, 60 and 120 fps.
5. Scan: all CRCs match; `total_samples` equals the decoded count; embedding changes nothing.
6. A stereo source plus a mono analysis signal stays stereo with the source audio (the old `-map` bug).
7. Optional local VLC check via `check_compat.vlc_run`: native Windows paths, no `CREATE_NO_WINDOW`, run from PowerShell. VLC hung otherwise.

## 7. Effort [I]
| Item | Where | Size |
|---|---|---|
| Audio decode, window, resample (Opus only), encode, interleave | skellysync | 2–3 days |
| PyAV probe, video-domain lag fix, removals | skellysync | 1–2 days |
| Audio header and table in the shared sidecar module | D-PKG | 1–2 days |
| Tests | skellysync | 2–3 days |
| **Total, skellysync** | | **about 1.5–2 weeks** on top of the Design A writer |
| Design B audio fields | skellysync | 0.5–1 day |
| Player (a) | skellycam-ui | 1–2 weeks |
| Player (b) fallback | skellycam-ui | 2–4 days |

## 8. Open risks and decisions
1. FLAC vs Opus (D-AUDIO). Opus brings a second lossy generation, a resample, VLC's +6.5 ms and the end-align rule.
2. 3+ channel sources: downmix or refuse [NV].
3. VLC numbers are `afile` alignment, not live playback [I].
4. Range-fetch cost over HTTP; audio scheduling under load [NV].
5. Synthetic clips only: real camera sizes, VFR, edit lists and start offsets [NV].
6. The PyAV 19 Python floor (SCOPE §0.4) is unchanged by the audio work.

## 9. Files
- Scripts in `scripts/audio_skellysync/`: `common.py`, `gen_source.py`, `sync_writer.py`, `check_compat.py`, `run_matrix.py`, `rerun_vlc.py`, `summarize.py`, `duration_test.py`, `size_test.py`, `make_electron_cfg.py`, `electron_test/`.
- Results in `results/audio_skellysync/`: the JSONs listed above.
- Reproduce:
  - `gen_source.py <scratch>/src`;
  - from PowerShell with `$env:VLC_TMP` set: `run_matrix.py`, then `rerun_vlc.py`;
  - `make_electron_cfg.py`, then Electron with `ELECTRON_RUN_AS_NODE` unset and `AUDIO_CFG`/`AUDIO_OUT` set;
  - Python from the `skellycam-phase1` venv, run with `-I`.
