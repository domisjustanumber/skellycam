# One standard audio file + one CSV timing sidecar (desk test, 2026-11-15)

For Dom's question (2026-11-15): "It would be nice to have a standard audio file with a single CSV sidecar with timing information. Then the audio file can be played in standard players (VLC). Is that possible?"

Provenance: a sub-agent ran this on 2026-11-15, 11:30–11:56 local, Windows 11, i7-14700K. Only synthetic signals were used: no microphone or camera was opened, and no device or driver settings were touched. Scripts are in `scripts/audio_single_file/`, results in this folder. Test media are in the session scratchpad; they can be rebuilt, and the >4 GiB WAVs were deleted.

**Labels:** [M] measured here (result file named) · [P: path] prior evidence · [K] knowledge, not verified.

**Versions:** Python 3.12.13 · PyAV 19.0.2 · FFmpeg/ffprobe CLI 9.0.2 (gyan.dev full build) · soundfile 0.13.1 / libsndfile 1.2.2 · numpy 2.2.6 · VLC 3.0.24 Vetinari, via the CLI and via python-vlc 3.0.21203 on the installed libvlc · Electron 35.7.5 (Chrome 134.0.6998.205) and 45.2.3 (Chrome 156.0.8078.80), driven by the existing harness `scripts/audio_skellycam/electron/` · Blender 5.2.3 LTS (headless, `aud` + VSE).

**Test signal.** Stereo s16 at 48 kHz. The left channel holds the low 16 bits of the absolute sample index; the right channel holds a hash of the index (noise). Every decoded sample therefore says which sample it is, and "exact" below means every output sample equals the source at that index.

## 0. Short answer

**Yes.** A live-written standard file plus one CSV works, and the native file can be the final file, with no finalisation copy.

**Best fit: WAV**, written live by FFmpeg's wav muxer through PyAV with `rf64=auto` and `flush_packets=1` (`<rec>.audio.wav`).
- **Hard kills:** 0 samples lost in 20/20 [M].
- **Killed file, no repair:** it plays, shows a duration and seeks sample-exactly in VLC, Chromium `<audio>`, Blender and FFmpeg [M].
- **Clean file:** sample-exact everywhere [M].
- **Cost:** 2× the size of FLAC (345.6 MB/h mono, 691 MB/h stereo [P: `audio_skellycam/FINDINGS.md` §1.3]).
- **Conflicts with D19.** The proposal swaps D19's FLAC for WAV for the mic file. This needs Dom's decision (**proposed**, not accepted).

**Native FLAC also works as the final file** (PyAV, `frame_size=1024`, `flush_packets=1`). Kills lose 0 samples [M, and P: `flac_skau`]. But a killed `.flac` has STREAMINFO total = 0, which causes four problems [M]:
- VLC shows no length, and a seek lands 0.6–2 s off target;
- Chromium reports the duration as NaN/Infinity;
- ffprobe reports no duration;
- Blender's VSE makes the strip **1 frame** long.

A lossless 5-byte STREAMINFO patch fixes all four [M]. So FLAC needs a recovery step; WAV under 4 GiB does not.

**Avoid** [M]:
- `rf64=always`: killed files read as **0 samples** in FFmpeg, PyAV and Chromium;
- libsndfile FLAC: 2,048–4,096 samples lost per kill, and VLC seeks land about 200 ms off;
- Matroska FLAC written live: 2,048 samples lost per kill, and a killed file shows no duration or a 1-frame strip;
- Ogg Opus and Ogg FLAC [P: `audio_skellycam` §2.3]: VLC shifts Ogg audio by 648–18,432 samples.

**Gaps:** write silence for samples the device lost, and flag them in the CSV. No player tested honours a timestamp gap in the container [M] (§4).

## 1. Live writing and hard kills (Q1)

### 1.1 Method (`kill_matrix.py` → `kill_matrix.json`)
- **Child writer.** It writes real-time-paced 1,024-sample blocks.
- **Order per block:** audio write, then one CSV row with a CRC, then flush. After that the child publishes its acknowledged sample and row counts.
- **Two kill methods:**
  - `exit`: `os._exit(1)` after a random block;
  - `term`: `TerminateProcess` on the **child's own PID** at a random time, so it can land mid-write. The uv `python.exe` launcher problem from `mcap_kill` is avoided.
- **Kill times** 0.51–7.94 s, seed 20261115.
- **Counts:** 8 writers × 10 kills × 2 methods = **160 kills, 160 landed** (exit code 1 or 15).
- **Clean files:** one cleanly closed 10.005 s file per writer.
- **Readers** (`readers.py` → `readers.json`, `libvlc_check.py`, `libvlc_seek.py` → `libvlc_seek.json`): PyAV, ffmpeg CLI, ffprobe, the VLC afile playback path, libvlc length and seek, and the CSV parser. All of them were run again after `repair_in_place` (header bytes only).

### 1.2 Results [M]
"Lost" = acknowledged samples − samples PyAV decodes. ffmpeg gave the same count as PyAV in 160/160 files.

| Writer | Lost per kill (20 kills) | Header after a kill | ffprobe duration (killed) | VLC afile playback (killed) | libvlc length (killed) | VLC seek, interactive (`set_time`), killed | Chromium `<audio>` (killed, E35 and E45) | Blender VSE strip (killed) |
|---|---|---|---|---|---|---|---|---|
| **WAV, PyAV `rf64=auto`** | **0** (−1,024 in 1 = a block written but not yet acknowledged) | RIFF and data sizes 0xFFFFFFFF | yes | all samples, exact 20/20 | correct 20/20 | **0 samples** (3/3) | finite duration, seek exact | correct length |
| WAV, PyAV default (`rf64=never`) | 0 | 0xFFFFFFFF | yes | exact 20/20 | correct | 0 | ok | ok |
| WAV, Python `wave` + flush per block | 0 | **valid sizes** (`writeframes` re-patches the header after each call) | yes | exact 20/20 | correct | 0 | ok | ok |
| WAV, libsndfile + `flush()` | 0 | RIFF size 8, data size 0 | yes | exact 20/20 | correct | 0 | ok | ok |
| WAV, PyAV `rf64=always` | **all** (FFmpeg/PyAV decode 0 samples) | RF64, ds64 sizes 0 | yes (estimate) | VLC plays all, exact | estimate only | 0 | `decodeAudioData` fails; `<audio>` does not play | length from file size, but `aud` decodes 0 |
| **FLAC, PyAV `frame_size=1024`** | **0** | STREAMINFO total = 0, MD5 = 0 | **no** | exact 20/20 | **0 ms** 20/20 | **lands 1.7–2.1 s early** (3/3) | duration NaN/Inf; plays | **1 frame** |
| FLAC, libsndfile | 2,048–4,096 | total = 0 | no | exact | 0 ms | 0.6–1.2 s early | NaN/Inf | 1 frame |
| MKA FLAC, `cluster_time_limit=1` | 2,048 (two packets, 42.7 ms) | unknown-size Segment, no Cues | no | exact | 21 ms short | 0–528 samples | NaN/Inf | 1 frame |

- **CSV under kills:** 160/160 parsed with 0 torn bytes and 0 CRC failures. CSV rows cover **exactly** the decoded audio, or one block less, in every zero-loss writer: CSV − audio ∈ {0, −1,024 samples} [M]. Writing the audio before the row means the CSV is never ahead of the audio. In the lossy writers the CSV leads by the lost samples.
- **Prior evidence agrees:**
  - PyAV FLAC `frame_size=1024`: 0 ms in 12/12 kills [P: `audio_skellycam` §2.2];
  - TerminateProcess mid-write: 40/40 kills with no torn record [P: `flac_skau` §7–8];
  - a CSV flushed per row keeps every reported row, and an unflushed one loses them [P: `crash_resilience/sidecar_durability.md`].

### 1.3 Repair: lossless, header bytes only (`asf_common.repair_in_place`) [M]

**FLAC:** write STREAMINFO total samples (5 bytes) and leave MD5 at 0 ("unknown", RFC 9639). Took 5–17 ms on these short files, mostly counting samples. The CSV's last row gives the same count, as long as it is checked against the frames.
- **After repair:** 20/20 exact; ffprobe duration and libvlc length correct.
- **VLC interactive seek error:** −1,024 to −496 samples (PyAV FLAC). libsndfile FLAC stays at +8,688 to +9,856.
- **Chromium:** finite duration and an exact seek. **Blender:** correct strip length.

**WAV under 4 GiB:** RIFF size and data size from the file length (8 bytes). It changes nothing a player showed, because they all already used the file length.

**WAV over 4 GiB, killed before FFmpeg's close-time RF64 conversion** (`big_wav.py` → `big_wav.json`):
- **Killed file:** RIFF with 0xFFFFFFFF sizes and a 28-byte JUNK placeholder. FFmpeg/PyAV read all of it: duration 23,960 s, and a seek to 23,500 s is sample-exact.
- **VLC caps the killed file at 4 GiB:** length 22,369,621 ms, and it plays nothing past that point.
- **Repair:** rebuild the header region as RF64 + ds64 + the other chunks, with the ds64 **first**, using the JUNK space. That is 114 bytes, in 0.23 ms. The result is byte-identical in layout to FFmpeg's own cleanly closed RF64.
- **After repair:** VLC length 23,960,000 ms, and VLC, PyAV, ffmpeg and Blender `aud` all seek **exactly** to sample 1,128,000,000 (23,500 s).
- **ds64 position matters:** a first repair attempt that put the ds64 after fmt was rejected by FFmpeg ("Invalid data") [M].

**Python `wave` past 4 GiB:** raises `struct.error` at 4,293,120,000 data bytes (6.2 h stereo, 12.4 h mono), and `close()` fails too [M]. skellycam's current recorder would also hit this [P: code read, `audio_recorder.py` keeps everything in RAM and writes with `wave` at stop].

## 2. Cleanly closed files (Q2) [M]
All 8 writers, 10.005 s each.

| Reader | WAV (all four writers, `rf64=auto`/`always`) | FLAC (PyAV) | FLAC (libsndfile) | MKA FLAC |
|---|---|---|---|---|
| PyAV, ffmpeg | exact, 480,256 samples | exact | exact | exact |
| VLC afile playback | exact, nothing dropped | exact, nothing dropped (469 whole 1,024-sample frames) | **last 5,120 samples dropped** | exact |
| VLC interactive seek to 5 s | **0 samples** | −384 | +9,856 | +640 |
| VLC CLI `--start-time` | **ignored: plays from sample 0** | −528 | +9,712 | +496 |
| Chromium E35/E45: `decodeAudioData`; `<audio>` duration, seek to 2 s | 480,256; 10.005 s; 2.000 | same | same | same (10.005) |
| Blender `aud` decode; seek to 2 s; VSE frames at 24 fps | exact; 0; 240 (240.128 expected) | exact; 0; 240 | exact; 0; 240 | exact; +256; 240 |

- **VLC drops a partial last frame.** It dropped the last 1,280 samples of a 30 s native FLAC whose last frame was partial [P: `flac_skau` §4]. Here PyAV's file ends on a whole frame and lost nothing. Treat "VLC drops a partial last FLAC frame" as likely [K]. WAV has no such effect.
- **`--start-time` on WAV** is a VLC command-line quirk. The seek bar (`set_time`) is sample-exact on WAV, including at 23,500 s in a 4.6 GB RF64 (`libvlc_seek.json`, `vlc_big_seek.json`).
- **The VLC afile output is not a real sound device** [K]. Real-window playback was not checked.
- **Blender `aud`** returns floats scaled by 1/32,767, not 1/32,768 [M]. Reading samples back exactly needs ×32,767.

## 3. The single CSV sidecar (Q3)

### 3.1 Proposed layout (tested in all 160 kills)
- **One file per audio file**, `<rec>.audio.csv`, UTF-8, LF line endings.
- **One row per capture callback**, written right after that block's audio write and flushed.
- **Example:** `csv_example.csv`. Its footer values are illustrative.

```
# skellycam_audio_timing=0
# take_uuid=…            # sample_rate=48000   # channels=2   # codec=pcm_s16le   # container=wav
# clock=QPC              # clock_hz=10000000   # host_ns_origin=take_start   # sample_index_origin=first_sample_in_file
# device=…  # host_api=WASAPI  # block=1024 (one '# key=value' per line)
block,first_sample,n_samples,host_ns,adc_ns,flags,crc32
0,0,1024,74369872,70817602,0,1b0d7f10
…
# fit segment=0 first_row=0 rows=… n0=0 t0_ns=… rate_hz=47999.520 ppm=-10.00 resid_p99_ns=…
# end rows=… samples=…
```

**Columns:**
- **`first_sample`:** index in the file. It equals the device index, because silence fills gaps (§4).
- **`host_ns`:** `perf_counter_ns` at callback entry minus the take start.
- **`adc_ns`:** PortAudio's `inputBufferAdcTime` on the same clock. It is −1 when the host API gives 0 (MME).
  - It is the better fit input: 0.66–0.72 ms std against about 3 ms for callback times [P: `audio_skellycam` §4.1].
- **`flags`:** bits for overflow, inserted silence and priming.
- **`crc32`:** of the row text before it.

**Mapping to the host clock:**
- Fit t = t0 + (n − n0)·1e9 / f_eff per segment, using the fit rules from [P: `audio_skellycam` §4.3]: segment breaks, a 1–2 s start exclusion, and `fit_unreliable` when the residual p99 exceeds 5 ms.
- The fit result goes into the footer. A video frame at host time T maps to sample n = n0 + (T − t0 − latency)·f_eff / 1e9.
- Drift of ±10 ppm (36 ms/h) is fitted, not corrected in the file. A plain player plays at the nominal 48 kHz [P: `audio_skellycam` §4.1; `docs/vlc_playback_rate_20261112.md`].

**Readers must be strict:** use only rows that end in a newline and pass the CRC, and stop at the first bad row. pandas silently NaN-pads or corrupts a truncated last row in 6/24 cases [P: `sidecar_durability.md`]. The CRC catches that.

### 3.2 Byte offsets for the browser?
- **`<audio>`:** no. Chromium seeks every clean and repaired file to exactly 2.000 s, and seeks killed files too [M]. VLC and Blender do the same with the container's own seeking.
- **A sample-exact WebCodecs/WebAudio player:**
  - **WAV needs no index:** byte = data_offset + n × block_align. A Range fetch of PCM can go straight into an `AudioBuffer`, without a decoder [K].
  - **FLAC needs each frame's offset:** either `byte_offset,byte_size` columns (one row = one 1,024-sample frame; offsets are exact live [P: `flac_skau` §1]) or a scan of the file at load.

### 3.3 Size and parse time (`csv_size.py` → `csv_size.json`) [M]
One hour = 168,750 rows, with realistic hour-scale values.

| Variant | MB/h | Bytes per row |
|---|---|---|
| proposed (7 columns) | **9.97** | 59.1 |
| + `byte_offset,byte_size` (FLAC) | 12.47 | 73.9 |
| minimal (`first_sample,host_ns`) | 3.89 | 23.1 |

- The strict CRC parser reads 1 h in 0.23 s.
- In the kill test the rows were 41–57 bytes, because `host_ns` values are short early in a take.

## 4. Gaps and discontinuities (Q4) (`gap_test.py` → `gap_test.json`) [M]
10 s file; 5,120 samples (106.7 ms) are "lost by the device" at sample 240,640. "Shift after the gap" = device index − output position. 0 = in sync; +5,120 = audio early by 106.7 ms.

| Written as | PyAV | ffmpeg (default) | ffmpeg `-af aresample=async=1` | VLC playback | Chromium `decodeAudioData` length | Blender `aud` length / VSE |
|---|---|---|---|---|---|---|
| **WAV or FLAC with silence inserted** | 0 | 0 | 0 | **0** | 480,256 | 480,256 / 240 |
| WAV, samples just skipped | +5,120 | +5,120 | +5,120 | +5,120 | 475,136 | 475,136 / 238 |
| Native FLAC with a pts jump | +5,120 (the FLAC muxer drops pts) | +5,120 | +5,120 | +5,120 | 475,136 | 475,136 / 238 |
| MKA FLAC with a timestamp jump | +5,120 | +5,120 | **0** (fills the gap) | **+5,120** | 475,136 | 475,136 / 240 |

**Rule (proposed).** When a gap is detected, write that many zero samples, so that file sample index = device time.
- **Detection:** block or sample count disagrees with elapsed `adc_ns`/`host_ns` time. WASAPI raised no flag under GIL load [P: `audio_skellycam` §3].
- **CSV:** write a row for the inserted block with `flags` = inserted_silence and its own `first_sample`/`n_samples`.
- **Fit:** start a new segment there. The fit absorbs the error in the estimated gap length, about the `adc_ns` jitter.
- **Why:** only this keeps VLC, Chromium, Blender and FFmpeg in sync after the gap.
- **The alternative** (keep real samples and mark the jump only in the CSV) leaves every standard player early by the gap length for the rest of the file. Only a CSV-aware player would be right.

## 5. Recommendation and comparison (Q5)

**Proposed:**
- `<rec>.audio.wav` (RIFF, becoming RF64 above 4 GiB through `rf64=auto`) plus `<rec>.audio.csv` as in §3.1.
- 48 kHz s16, written live from the dedicated audio process [P: `audio_skellycam` §3]: PyAV wav muxer, `flush_packets=1`, one write and one CSV row per callback.

**Finalisation:**
1. Close the muxer. FFmpeg writes the sizes, or converts to RF64.
2. Append the fit and `# end` lines to the CSV.

There is no copy and no second file. That replaces the earlier `.flac` → `.mka` + `.skat` stream copy and the deletion of the `.flac` [P: `flac_skau` §5].

**Recovery after a crash:**
- Optional `repair_in_place` under 4 GiB (players already cope).
- Required over 4 GiB, so that VLC sees past 4 GiB. It is lossless and touches header bytes only.
- Then fit from the surviving CSV rows. The audio may hold one block more than the CSV; extrapolate it with the fit.

**If size matters more than crash behaviour:** native `.flac` (PyAV, `frame_size=1024`) is also a valid final file. Then:
- recovery **must** patch STREAMINFO, or there is no duration or seek in VLC, Chromium or Blender;
- the CSV gains `byte_offset,byte_size` for a WebCodecs player.

| | WAV (`rf64=auto`) | Native FLAC | Earlier plan: FLAC → `.mka` + `.skat` |
|---|---|---|---|
| Lost per kill | 0 [M] | 0 [M] | 0 (live `.flac`) |
| Killed file in VLC, Chromium, Blender without repair | plays, length, exact seek (< 4 GiB) | plays; no length; seek off; 1-frame strip | n/a (recovered by copy) |
| Repair | optional (< 4 GiB); 8–114 header bytes | required; 5 bytes plus a sample count | stream copy + attachment |
| Finalisation copy | none | none | yes |
| Sidecar | 1 CSV | 1 CSV (+ offsets) | `.skat` embedded |
| Size, mono / stereo | 345.6 / 691 MB/h | about 172 / 335 MB/h on synthetic audio [P]; real audio [K] | same as FLAC |
| VLC seek (clean) | 0 samples | −384 | +640 (MKA) |

### Remaining risks and desk tests still needed
1. **D19 says FLAC.** Choosing WAV is Dom's decision. The FLAC route is fully workable if recovery always patches STREAMINFO.
2. **Real microphone through WASAPI** with the CSV writer in the audio process (gap detection, `adc_ns` validity, start-up step). Not run: no microphone, by instruction.
3. **Paced writing past 4 GiB:** only unpaced writes were tested. Also an hour-long drift fit from the CSV.
4. **VLC in a real window** (only afile/dummy output was tested), VLC 4, mpv. Also Linux and macOS.
5. **Power loss or OS crash** (process kills only), and fsync policy.
6. **libsndfile RF64 and other writers** were not tested. PyAV `rf64=auto` is the tested path.

## 6. Files
**Scripts** (`scripts/audio_single_file/`, each a uv script with exact pins, run as `uv run --script <script>` from the repo root):
- `asf_common.py`: signal, writers, CSV, readers, repair;
- `kill_matrix.py`, `readers.py`, `libvlc_check.py`, `libvlc_seek.py`;
- `big_wav.py` (`--repair-only` reruns the repair), `vlc_big_seek.py`;
- `gap_test.py`, `csv_size.py`;
- `blender_check.py` + `blender_inner.py`, run with `python -I`.

Electron: the harness in `scripts/audio_skellycam/electron/main.cjs` was reused unchanged, with `AUDIO_DIRS` set to the scratch `electron_set` subfolders.

**Results** (this folder): `kill_matrix.json`, `readers.json`, `libvlc_seek.json`, `big_wav.json`, `vlc_big_seek.json`, `gap_test.json`, `csv_size.json`, `csv_example.csv`, `electron_e35.json`, `electron_e45.json`, `blender.json`.

Main-session check (2026-11-15): `readers.json` lost_samples_pyav per writer over 20 kills: flac_pyav {0}, wav_pyav {0}, rf64auto_pyav {-1024, 0}, wav_stdlib {0}, wav_sf {0}, mka_flac_pyav {2048}, flac_sf {2048..4096}, rf64always_pyav all lost; matches §1.2. The sub-agent could not write this file (harness rule); the main session saved its text.


Correction (2026-11-15, from the Opus study `opus/FINDINGS.md`): VLC `--start-time` on WAV is **not** ignored. VLC plays 2,400 samples (50 ms) from sample 0, then jumps exactly to the target (error 0). The row in §2 looked only at the first 50 ms.
