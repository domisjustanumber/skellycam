# FINDINGS: Opus as the single standard audio file + one CSV sidecar (desk test, 2026-11-15)

For Dom's 2026-11-15 request: assess Opus for the microphone role ("a standard audio file with a single CSV sidecar with timing information" that plays in VLC), against today's WAV/FLAC results (`results/audio_single_file/FINDINGS.md`).

**Provenance.** A sub-agent ran this on 2026-11-15, about 12:15–13:50 local, on Windows 11 with an i7-14700K.
- Only synthetic signals were used. No microphone or camera was opened, and no device or driver settings were changed.
- Scripts: `scripts/audio_single_file/opus/`. Results: `results/audio_single_file/opus/`.
- Media are in the scratchpad (rebuildable): `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file\opus\`.

**Labels:** [M] measured here (the result file is named) · [P: path] prior evidence · [K] knowledge, not verified.

**Versions** [M]:
- Python 3.12.13; PyAV 19.0.2 (libavformat/libavcodec 63.1.102), whose wheel contains libopus 1.6.1 [P: `audio_skellycam/codecs.json`]; numpy 2.2.6; soundfile 0.13.1.
- FFmpeg/ffprobe CLI 9.0.2 (gyan.dev full build).
- VLC 3.0.24 Vetinari, through the CLI and through python-vlc 3.0.21203. Its `libopus_plugin.dll` contains "libopus 1.6.1".
- Electron 35.7.5 (Chrome 134.0.6998.205) and 45.2.3 (Chrome 156.0.8078.80).
- Blender 5.2.3 LTS: bundled libavcodec 62.28.100, built with libopus (strings in `avcodec-62.dll`).
- uv pins are exact and the same as the existing scripts: `av==19.0.2`, `numpy==2.2.6`, `soundfile==0.13.1`, `python-vlc==3.0.21203`.

**Encoder settings (D9N1 item 5):** libopus, 48 kHz, 20 ms packets (960 samples), `application=audio`, VBR, complexity 10. The kill and player tests used stereo at 256 kbit/s; size and CPU were also measured mono at 128 kbit/s. Pre-skip is 312 samples [M, matches P: D9N1].

**Test signal.** Opus is lossy, so the WAV harness's index signal cannot be checked sample by sample.
- Per channel: seeded PRNG noise (uniform ±8,192 s16, about −17 dBFS rms, independent per channel), plus a click of 29,000 on both channels at sample 24,000 + k·48,000. This is the click train that the existing Electron page's `clicks()` uses.
- Timing is measured two ways, in samples at 48 kHz:
  - click offset: argmax of |x| in each 1 s window, minus the expected position, as in `audio_skellycam/align.py`;
  - cross-correlation lag of the noise against the source.
- Sign: **< 0 = audio comes out early**, > 0 = late.
- Seek landing (`opus_common.seek_landing`):
  - the content lag after the jump comes from the tail of the output;
  - the jump is placed where the pre-seek content stops fitting, or at the first output sample when the output starts at the seek;
  - error = source index of the first non-silent sample after the jump − target. This is the same metric as `libvlc_seek.py`.
- The method is self-checked (`selftest.py`, assert-based, synthetic jumps, silence, 312-sample shifts, decoder garbage) and calibrated: WAV gives 0 in every reader.
- A first signal (multiplicative hash noise, as in `asf_common`) was dropped. It is quasi-periodic at Fibonacci lags (lag 17,711 correlates 0.999), which broke seek location [M]. That kill run was discarded and redone.

## 0. Short answer

| Question | Answer |
|---|---|
| Can Opus be the one standard file + one CSV? | Yes, in fragmented MP4 or WebM/MKA [M]. Not in Ogg if VLC must be right [M] |
| Best container | **Fragmented MP4 `.m4a`, one fragment per packet** |
| Loss per hard kill | 26.5–45.2 ms (1,272–2,168 samples), 20/20 [M]. WAV and native FLAC: 0 [P: `audio_single_file/FINDINGS.md`] |
| Killed file without repair | Plays, has a duration and seeks in VLC, Chromium (E35/E45), FFmpeg/PyAV and Blender [M] |
| Start offset | 0 in FFmpeg/PyAV, Chromium `decodeAudioData` and Blender `aud`. **VLC: +312 (6.5 ms late)** [M] |
| Seek accuracy (clean) | VLC seek bar −271, VLC `--start-time` −451, Blender `aud` 0, Chromium `<audio>` `currentTime` exact (rendered content only coarsely measurable) [M] |
| Gaps | Encode silence: every player stays in sync, as with WAV [M] |
| Size | 75 / 130 MB/h (mono 128k / stereo 256k) with per-packet fragments, 58 / 112 with 100 ms fragments (but kills then lose up to 122.5 ms) [M]. WAV 345.6 / 691.2 |
| CPU | 0.34–0.68 % of one core for live encode + mux [M] |
| Lossy | Yes. Click and correlation timing are sample-exact on the test signal; waveform SNR on white noise is 5.8 dB [M] |
| Overall | WAV stays the better fit for the recording (proposed). Opus fMP4 is the choice if size must drop by 4.6–12.9× |

## 1. Live writing and hard kills (Q1)

### 1.1 Method (`kill_opus.py` → `kill_opus.json`, same as `kill_matrix.py`)
- **Child writer:** real-time-paced 1,024-sample stereo blocks through `asf_common.PyAVWriter`, with `flush_packets=1`.
- **Order per block:** audio write, then one CRC'd CSV row, then flush. The child then publishes its acked sample and row counts and its own PID.
- **Kills:** `exit` = `os._exit(1)` after a random block; `term` = `TerminateProcess` on the child's own PID at a random time.
- **Times and seed:** kill times 0.507–7.941 s, seed 20261115.
- **Counts: 6 writers × 10 × 2 = 120 kills, 120 landed** (exit code 1 for 60, 15 for 60) [M].
- **Clean files:** one cleanly closed 10.005 s file per writer, plus WAV (`wav_pyav`) and native FLAC (`flac_pyav`) references of the same signal.
- **Readers** (`readers_opus.py` → `readers_opus.json`): PyAV, ffmpeg CLI, ffprobe, CSV parser, VLC afile playback, VLC `--start-time` at 50 % for 1 s, and libvlc length/seekable via `../libvlc_check.py`.
- **Repair:** `ffmpeg -c copy` into `repaired/`. The `.m4a` repair needs `-f mp4`, because the `.m4a` extension alone picks the `ipod` muxer, which refuses Opus [M].
- **Seek bar:** `libvlc_seek_opus.py` → `libvlc_seek_opus.json`.
- **Growth probe:** `growth_probe.py` → `growth_probe.json` (decode a copy of the file after every block).

**Writers** (stereo, 256 kbit/s):

| Name | Container, options |
|---|---|
| `ogg_pd20` | Ogg `.opus`, `page_duration=20000` µs (`page_duration=1` gave the identical lag in the probe [M]) |
| `mka_ct1` / `webm_ct1` | Matroska `.mka` / WebM `.webm`, `cluster_time_limit=1` |
| `mp4_fragpkt` | MP4 `.m4a`, `movflags=empty_moov+default_base_moof+frag_every_frame` |
| `mp4_frag100` | MP4 `.m4a`, `empty_moov+default_base_moof`, `frag_duration=100000` |
| `mp4_plain` | MP4 `.m4a`, moov written at close |

**Not possible** [M, `probe0`]: CAF (FFmpeg: "Not yet implemented, patches welcome") and the `ipod` muxer ("does not support libopus").

### 1.2 Where the loss comes from
- **Encoder:** PyAV's libopus encoder returns floor(n/960) packets immediately after each write [M]. So it holds (n mod 960) samples plus the 312-sample look-ahead: 312–1,271 samples (6.5–26.5 ms). Opus cannot avoid this [M + K].
- **Muxer:**
  - Ogg and per-packet fMP4 hold one more packet (the open page or fragment is written when the next packet arrives).
  - Matroska holds two.
  - Growth-probe lag: Ogg and fMP4-per-packet 1,272–2,168; MKA/WebM 2,232–3,128; fMP4 100 ms 1,272–6,008 [M].
- **No muxer flush in PyAV 19.0.2:** there is no call to flush the muxer between packets [M: `OutputContainer` API]. FFmpeg's Ogg muxer does flush its pages on `av_write_frame(NULL)` [K]. A small custom Ogg or fMP4 writer would cut 20 ms [K, not tested].

### 1.3 Results [M] (20 kills per writer)

| Writer | Lost per kill, samples (ms) | Killed file in PyAV/ffmpeg | ffprobe duration | VLC afile playback | libvlc length vs decoded | VLC seek bar (3 term kills) | Chromium E35/E45 (1 exit + 1 term kill) | Blender (1 exit + 1 term kill) | Repair `-c copy` |
|---|---|---|---|---|---|---|---|---|---|
| **`mp4_fragpkt`** | **1,272–2,168 (26.5–45.2)** | plays; timing 0; ffmpeg = PyAV 20/20 | yes 20/20 | plays; +312 | +6 ms | −894 to −510 | duration finite, seek ok, `decodeAudioData` = PyAV count | strip length correct; `aud` timing 0 | not needed; lossless 20/20 (27–44 ms) |
| `mp4_frag100` | 1,528–5,880 (31.8–122.5) | same | yes | +312 | +6 ms | −1,086 to −414 | same | correct | lossless 20/20 |
| `ogg_pd20` | 1,272–2,168 (26.5–45.2) | same | yes | plays, **−3,528** | −74 ms | +5,832 to +6,168 | finite, seek ok | correct; `aud` timing 0 | not needed. **The remux harms VLC:** length 0 or short in 9/20 |
| `mka_ct1` | 2,232–3,128 (46.5–65.2) | same | **no** | +312 | −13 ms (length shown) | −311 to +312 | duration **NaN/Inf**; plays; seek to 1 s ok; E45 count −24 | **1-frame strip** | lossless 20/20 (22–35 ms); fixes ffprobe, Chromium, Blender |
| `webm_ct1` | 2,232–3,128 (46.5–65.2) | same | **no** | +312 | −13 ms | −325 to −72 | NaN/Inf | **1-frame strip** | lossless 20/20 |
| `mp4_plain` | **everything** (14,336–373,760) | `InvalidDataError` (no moov) | no | nothing | 0 | none | media error 4 | "couldn't be read" | **impossible** (moov missing) |

**Reference:** WAV and native FLAC lose 0 in 20/20 [P: `audio_single_file/FINDINGS.md` §1.2].

Notes:
- **exit vs term:** loss ranges overlap. For example, `mp4_fragpkt` exit lost 1,464–2,168 and term 1,272–2,040.
- **Short files:** "timing" is shown only for killed files longer than 1 s; 1–2 per writer were shorter.
- **Kills before the first packet:** none in this seed. The probe shows audio after block 1 (Ogg, fMP4) or block 2 (MKA) [M].
- **Lossless repair:** the decoded sample count after repair equals the killed file's count in 100/100 Ogg, MKA, WebM and fMP4 files [M].
- **In-place repairs, not tested** [K]:
  - Ogg: set EOS on the last page and recompute its CRC.
  - Matroska: write the Segment size and Duration.

### 1.4 CSV under kills [M]
- **Integrity:** 120/120 CSVs parse with 0 torn bytes and 0 CRC failures.
- **Unlike WAV, the CSV leads the audio:** in every killed file, CSV − audio equals the samples lost exactly (1,272–3,128; plain MP4 all).
- **Reader rule (proposed):** take the decoded length as the truth and drop or extrapolate CSV rows past it.

## 2. Cleanly closed files: timing, start offset, seeks (Q2) [M]
10.005 s files, 480,256 input samples.

### 2.1 Start offset and length

| Reader | Ogg | MKA / WebM | fMP4 (both) | plain MP4 | WAV / FLAC ref |
|---|---|---|---|---|---|
| PyAV, ffmpeg: click offset / correlation lag | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| PyAV decoded count | 480,256 | 480,256 | **480,648** (end padding not trimmed) | 480,648 | 480,256 |
| VLC afile playback: offset; samples | **−3,528**; 476,728 | +312; 480,960 | +312; 480,568 | +312; 480,568 | 0; exact |
| libvlc length (ms) | 9,932 | 10,013 | 10,012 | 10,005 | 10,005 |
| VLC seek bar (`set_time` 5 s), error | **+6,408** | −312 | −271 | −271 | WAV 0; FLAC +640 |
| VLC `--start-time` 5.003 s, error | +6,264 | +504 | −451 | −456 | WAV 0; FLAC +496 |
| Chromium `decodeAudioData` E35 / E45 | 0 / 0 | 0 / **−24** | 0 / 0 | 0 / **−312** | 0 / 0 |
| Chromium `<audio>` duration (s); seek `currentTime` | 10.012; 2.000 | 10.013; 2.000 | 10.012; 2.000 | 10.005; 2.000 | 10.005; 2.000 |
| Chromium `<audio>` rendered, from 0 (E35, coarse) | +312 | 0 | 0 | +312 | 0 |
| Blender `aud` decode offset | 0 | 0 | 0 | 0 | 0 |
| Blender `aud` seek (`limit` at 2 s) | +313 | **+960** | **0** | +312 | 0 |
| Blender VSE strip (24 fps) | 240 | 240 | 240 | 240 | 240 |

Notes:
- **VLC on Ogg:** VLC drops the first 3,840 samples (4 packets, 80 ms) of an Ogg Opus stream at `page_duration` 20 ms, whatever the pre-skip. It is −3,528 with pre-skip 312 and still −3,528 with pre-skip 0 (§2.2) [M].
  - Prior evidence: page 60 ms gives −5,448 [P: `audio_skellycam/FINDINGS.md` §2.3].
  - Its length is 73 ms short, and seeks land about 6,400 samples (133 ms) late [M].
- **VLC ignores the Opus pre-skip in Matroska and MP4:** it ignores CodecDelay/OpusHead, dOps PreSkip and the elst edit list, and plays the 312 priming samples first, so the audio is 6.5 ms late [M].
- **MP4 end padding:** FFmpeg does not trim it, so MP4 decodes 392 samples longer than the input. Clamp to the CSV `# end samples` [M].
- **E45 MKA/WebM −24:** from Matroska's 1 ms timestamps [M; same as P: `audio_skellycam` §4.4].
- **Chromium E45 on plain MP4 trims the pre-skip twice** (−312) in `decodeAudioData`. In E35, Ogg and plain MP4 `<audio>` start +312 early [M, coarse].
- **Blender seek** is exact only in fMP4. Ogg and plain MP4 come out 312 early after a seek, MKA/WebM 960 early (one packet) [M].
- **Decoder convergence:** after a seek with no pre-roll, the first ~480 samples (10 ms) do not match the source in Blender and VLC [M]. None of these players applies the RFC 7845 80 ms pre-roll [K].
- **Chromium `<audio>` rendered content can only be measured coarsely** [M]:
  - The MediaElementSource → ScriptProcessor capture steps by 128 samples during the first second, even for WAV.
  - E35 is resolvable: WAV is 0 at start, and drifts to +128…+512 after seeks for every format, WAV included.
  - E45 is not: WAV itself reads −1,024…−640.
  - Read those rows as ±~250 samples (E35) or unresolved (E45). The seek target was always reached exactly by `currentTime`.
  - Sample-accurate Chromium timing should come from `decodeAudioData` or WebCodecs, not from `<audio>` [M + P: `audio_skellycam` §4.4].

### 2.2 Variant: pre-skip = 0 (`preskip0.py` → `preskip0.json`) [M]
The patch is lossless, in place, and touches header bytes only:
- Ogg: OpusHead pre-skip (2 bytes) + that page's CRC (4 bytes).
- MKA/WebM: OpusHead pre-skip + the CodecDelay value.
- fMP4: dOps PreSkip.
- plain MP4: dOps PreSkip + elst `media_time` 312 → 0.

The priming samples are then played everywhere. File sample i plays at i/48000 s, and device sample 0 sits at file sample 312.

| Reader | MKA / WebM | fMP4 | plain MP4 | Ogg |
|---|---|---|---|---|
| PyAV, ffmpeg, Chromium `decodeAudioData` (E35 and E45), Blender `aud` | +312 | +312 | +312 | +312 |
| VLC playback | +312 | +312 | +312 | −3,528 |
| VLC seek bar / `--start-time` | −312 / −312 | −271 / −307 | −271 / −312 | +6,408 / +6,408 |
| Blender `aud` seek | −306 | −306 | −306 | −306 |

- **Result:** in Matroska/MP4 every reader agrees: the audio is 6.5 ms late at the start, and after VLC and Blender seeks.
- **Cost:** a non-default header. RFC 7845 allows a pre-skip of 0 [K]. Decoders then play 6.5 ms of near-silent priming.
- **This is an option for Dom (proposed), not a recommendation.** It trades exact FFmpeg/Chromium/Blender alignment for VLC agreement.

## 3. The CSV sidecar for Opus (Q3)
- **Rows stay one per capture callback (1,024 samples), identical to WAV** [M: 120 kills]. The decoders apply the pre-skip, so `first_sample` = index in the decoded (pre-skip-trimmed) stream = device sample index, exactly as with WAV.
- **Header additions:** `codec=opus`, `container`, `pre_skip=312`, `opus_frame=960`, `bitrate` (example: `results/audio_single_file/opus/csv_example_opus.csv`).
- **With the §2.2 variant,** the header would state `pre_skip=0` plus the 312-sample shift.
- **D9N1 item 6 needs no extra rows.** D9N1 item 6 sets a packet's timestamp as the host time of its first decoded sample, priming included. Packet k's first decoded sample is trimmed index 960k − 312, and its host time comes from the CSV fit (t = t0 + (n − n0)·1e9/f_eff). So per-packet timestamps are derived, not stored.
- **Differences from WAV:**
  - After a kill the CSV runs ahead of the audio by the lost samples (§1.4).
  - MP4 decodes 392 extra end-padding samples on clean files (clamp to `# end samples`).
  - Encoding is lossy.
- **Byte offsets.**
  - `<audio>`, VLC and Blender seek through the container, so they need none [M].
  - MSE accepts WebM Opus and MP4 Opus in E35 and E45, but not Ogg [M: `caps`].
  - A sample-exact WebCodecs player needs the packet bytes. It can scan `moof/trun` or Ogg pages in JS (a 10 s scan + decode took 21–25 ms [P: `audio_skellycam` §4.4]) or read an optional per-packet CSV (`packet,first_sample,byte_offset,byte_size,crc32`).
- **Size per hour** (`csv_size_opus.py` → `csv_size_opus.json`) [M]: callback rows 9.97 MB/h (unchanged); packet rows 6.80 MB/h (180,000 rows, 37.8 B each).

## 4. Gaps (Q4) (`gap_opus.py` → `gap_opus.json`; Chromium and Blender on the same files) [M]
4,800 samples (100 ms) are lost by the device at sample 239,688, on an Opus packet boundary. The table shows the offset of clicks after the gap (0 = in sync, −4,800 = 100 ms early).

| Written as | PyAV | ffmpeg | ffmpeg `aresample=async=1` | VLC playback | Chromium `decodeAudioData` E35/E45 | Blender `aud` |
|---|---|---|---|---|---|---|
| **Silence encoded** (Ogg, MKA, WebM, fMP4, plain MP4) | 0 | 0 | 0 | unchanged from its start offset (Ogg −3,528, others +312) | 0 (E45 MKA/WebM −24) | 0 |
| pts jump (Ogg granule, Matroska timestamps, MP4 timestamps) | −4,800 | −4,800 | Ogg/MP4 −4,800; **MKA/WebM +24** (fills the gap) | −4,800 relative | −4,800 (E45 MKA −4,824) | −4,800 |

- **Blender VSE with a pts jump:** the strip is 240 frames long (the container duration) while `aud` decodes only 237.6 frames of audio [M].
- **Conclusion: same rule as WAV.** Encode silence for samples the device lost and flag them in the CSV. No standard player honours a timestamp gap except ffmpeg `aresample=async` on Matroska.

## 5. Size and CPU (Q5) (`bench_opus.py` → `bench_opus.json`, 60 s per run, idle harness) [M]

| | Mono 128k: MB/h (timing / quiet signal) | Stereo 256k: MB/h | Overhead per packet |
|---|---|---|---|
| Opus payload only | 52.3 / 49.9 | 106.5 / 101.7 | – |
| Ogg, page 20 ms | 57.5 / 55.2 | 112.0 / 107.2 | 29–30 B |
| WebM / MKA, cluster 1 ms | 58.8 / 56.4 · 59.9 / 57.5 | 113.1 / 108.3 · 114.2 / 109.4 | 36 / 42 B |
| **fMP4, fragment per packet** | **75.2 / 72.9** | **129.5 / 124.7** | **127 B** |
| fMP4, 100 ms fragments | 57.6 / 55.3 | 111.9 / 107.1 | 30 B |
| plain MP4 | 53.1 / 50.7 | 107.4 / 102.6 | 4 B |
| WAV | 345.6 | 691.2 | – |
| Native FLAC (PyAV) | 316.8 (noise signal) / 201.4 (quiet) | 626.0 / 402.1 | – |

- "Timing" is the white-noise test signal. "Quiet" is −60 dBFS noise with −20 dBFS bursts 30 % of the time and a click every second.
- Prior FLAC on its own signal: 172 / 335 MB/h [P: `audio_skellycam` §1.3]. FLAC size on real room audio is not known [K].
- **libopus encode per 960-sample packet:** median 58 µs mono, 90 µs stereo; p99 96–183 µs; 0.31–0.52 % of one core [M].
- **Live write per 1,024-sample callback** (FIFO + encode + mux + flush): median 60–136 µs, p99 125–395 µs; 0.31–0.73 % of one core [M].
  - WAV: 4–5 µs, 0.03–0.05 %. FLAC: 16–25 µs, 0.08–0.16 %.
  - Prior evidence says the GIL convoy, not CPU, is the risk, so the writer belongs in a dedicated audio process [P: `audio_skellycam` §3].

**Lossy: what it means for later analysis:**
- Clicks peak on the exact source sample in PyAV, ffmpeg, Chromium `decodeAudioData` and Blender, at every container and through kills [M].
- The noise cross-correlation lag is exact (coefficient 0.89 per 50 ms window) [M]. So cross-correlation sync and click/onset timing work on this synthetic signal [M].
- Waveform SNR on white noise at 256 kbit/s stereo is only 5.8 dB [M]. Opus/CELT codes noise-like bands by energy, not waveform [K].
- Analysis that needs the waveform needs lossless audio: sample-level subtraction, phase, or noise-floor measurement [K].
- On real transients, pre-echo can smear an onset within one MDCT frame (2.5–20 ms) [K]. Not tested on real audio.

## 6. Licensing (Q6)
- **Opus:** royalty-free patent licences from Xiph.Org, Broadcom and Microsoft, BSD reference code [P: `audio_skellycam/FINDINGS.md` §1.1; skellyfileformat `HD8Z`/`D9N1`].
- **AAC:** per-unit fees through Via LA for encoders and decoders [P: same §1.1].
- **Containers:** Ogg, Matroska/WebM and ISO BMFF (MP4) carry no royalties [K].
- **FLAC and WAV/PCM:** unencumbered [P/K].

## 7. Recommendation (proposed; Dom decides)

| | WAV (`rf64=auto`) | Native FLAC (`frame_size=1024`) | **Opus, fragmented MP4 (per packet)** | Opus, WebM/MKA (cluster 1 ms) |
|---|---|---|---|---|
| Lost per kill | 0 [P] | 0 [P] | 26.5–45.2 ms [M] | 46.5–65.2 ms [M] |
| Killed file without repair: VLC / Chromium / Blender | plays, length, exact seek [P] | plays; no length; seek 0.6–2 s off; 1-frame strip [P] | plays, length, seek (VLC +312) [M] | plays; Chromium/ffprobe no duration; 1-frame strip [M] |
| Repair | optional (< 4 GiB) [P] | required: 5-byte STREAMINFO patch [P] | none needed; lossless remux optional [M] | lossless `-c copy` needed for Chromium/Blender [M] |
| Clean start offset: VLC / Chromium / Blender | 0 / 0 / 0 | 0 / 0 / 0 | **+312** / 0 / 0 [M] | **+312** / 0 (E45 −24) / 0 [M] |
| Clean seek: VLC seek bar / Blender `aud` | 0 / 0 | −384 or +640 (frame boundary) / 0 | −271 / 0 [M] | −312 / +960 [M] |
| Size, mono / stereo | 345.6 / 691.2 MB/h | 172–317 / 335–626 (signal-dependent) | 75 / 130 (58 / 112 with 100 ms fragments, loss ≤ 122.5 ms) | 59 / 114 |
| CPU (one core) | 0.03–0.05 % | 0.08–0.16 % | 0.34–0.68 % | 0.34–0.73 % |
| Lossy | no | no | yes | yes |

- **Keep `<rec>.audio.wav` + `<rec>.audio.csv` as proposed for the mic** if crash loss and VLC accuracy matter most. It is the only option with 0 loss and 0 offset in every player.
- **If size must come down, use Opus in fragmented MP4:**
  - `<rec>.audio.m4a`; PyAV `format="mp4"`, `movflags=empty_moov+default_base_moof+frag_every_frame`, `flush_packets=1`; D9N1 encoder settings.
  - The same CSV rows, plus `pre_skip` in the header.
  - Choose between standard pre-skip (VLC 6.5 ms late) and pre-skip 0 (everyone 6.5 ms late).
  - Use `-f mp4` for any remux.
- **WebM/MKA** is the fallback: it is smaller per packet but needs a repair after a crash, and Blender seeks 20 ms off.
- **Don't use** Ogg Opus (VLC), plain MP4 (unreadable after a crash) or CAF (FFmpeg can't write Opus to it).
- **Native FLAC** remains the lossless half-size alternative to WAV, with its required STREAMINFO patch [P].

## 8. Remaining risks and desk tests still needed
1. **Hour-long fragmented MP4:** 180,000 fragments per hour. VLC, Chromium and Blender seek time and memory, and VLC seek accuracy far into the file. Only 10 s files were tested. Also 100 ms fragments as a compromise.
2. **Real microphone, real audio:** Opus quality by listening, onset smearing, FLAC size on room audio. Not done, by instruction.
3. **A custom muxer flush:** a hand-written per-packet Ogg/fMP4 writer, or FFmpeg flush through another binding, to cut the 20 ms muxer hold (loss would become 6.5–26.5 ms).
4. **Pre-skip 0** in other players (mpv, VLC 4, Audacity, macOS/Linux players), and whether any tool rejects it.
5. **Chromium `<audio>` rendered timing** needs a better method (WebAudio loopback with a known clock, or an output device capture). Only `decodeAudioData` and `currentTime` are exact here.
6. **VLC in a real window,** VLC 4, Linux and macOS. Only the afile/dummy output was tested.
7. **Power loss and OS crash:** only process kills were tested.
8. **Decision record:** D9N1 is written for MCAP; its encoder settings were used here unchanged. Any container choice above is a `proposed` entry, not an accepted one.

## 9. Files
**Scripts** in `research/skellycam_recording/recording_upgrade/scripts/audio_single_file/opus/`. Each is a uv script with exact pins, run as `uv run --script <script>` from the repo root.

| Script | Purpose |
|---|---|
| `opus_common.py` | Signal, writers registered into `asf_common.PYAV`, timing locator |
| `selftest.py` | Assert-based check of the locator |
| `growth_probe.py` | Virtual-kill lag per writer |
| `kill_opus.py` | 120 hard kills + clean files + WAV/FLAC references; imports `kill_matrix.terminate` |
| `readers_opus.py` | All file readers; uses `../libvlc_check.py` |
| `libvlc_seek_opus.py` | VLC seek-bar seek |
| `gap_opus.py` | Gap test |
| `preskip0.py` | Pre-skip 0 patch and checks |
| `csv_size_opus.py` | CSV size; uses `../csv_size.py` |
| `bench_opus.py` | Size and CPU |
| `electron_opus.py` + `electron/main.cjs` + `electron/page_opus.html` | Chromium tests. `main.cjs` is a copy of `scripts/audio_skellycam/electron/main.cjs` with `.m4a` added; `--analyse-only` re-analyses the raw page output |
| `blender_opus.py` + `blender_inner_opus.py` | Blender tests |

**Results** in `research/skellycam_recording/recording_upgrade/results/audio_single_file/opus/`: `kill_opus.json`, `readers_opus.json`, `libvlc_seek_opus.json`, `growth_probe.json`, `gap_opus.json`, `preskip0.json`, `electron_opus_e35.json`, `electron_opus_e45.json`, `blender_opus.json`, `bench_opus.json`, `csv_size_opus.json`, `csv_example_opus.csv`.

**Media** (rebuildable): `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file\opus\` (`killed`, `clean`, `repaired`, `gap`, `preskip0`, `electron_set`, raw Electron output).

Main-session check (2026-11-15): `readers_opus.json` lost samples per writer over 20 kills: ogg_pd20 1272-2168, mka_ct1 2232-3128, webm_ct1 2232-3128, mp4_fragpkt 1272-2168, mp4_frag100 1528-5880, mp4_plain 14336-373760; matches §1.3. The sub-agent could not write this file (harness rule); the main session saved its text.
