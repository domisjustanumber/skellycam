# chromium_codecs: FINDINGS (G8: native playback in the Chromium/Electron UI)

Machine Gerald, 2026-11-09. **Functional results only. No timing numbers** (TIMING RULE: other agents were running).
- CPU i7-14700K (`HANDOFF.md:62`).
- RTX 3070, driver 610.88 (`CC/NOTES.md:105`); Chromium reports driverVersion `32.0.16.1088` (`IPF/*/caps.json`, `gpu_info`).
- UHD 770 listed by Chromium (`IPF/*/caps.json`).

Labels: **measured** (result file), **source** (primary source), **code** (file:line), **inferred** (kept minimal and marked), **background** (ffmpeg-CLI/OpenCV fixtures or GOP files; not the implementation under test). NOT VERIFIED where stated.

Paths are relative to `research/skellycam_recording/recording_upgrade/`. Shorthands:
- `CC` = `results/chromium_codecs/`
- `IP` = `results/intra_playback/`
- `IPF` = `IP/functional/<e35|e45|c156>/`

Browsers:
- E35 = Electron 35.7.5 (Chromium 134.0.6998.205): `CC/raw/electron35_main.json` `versions`.
- E45 = Electron 45.2.3 (Chromium 156.0.8078.80): `CC/raw/electron45_main.json` `versions`.
- C156 = Chrome 156.0.8078.80: `CC/raw/chrome156/chrome156_main.json`, `version.Browser` and `uaData.fullVersionList`. The UA string itself is reduced to `Chrome/156.0.0.0`.

Scope:
- Per Dom's 17:20 decision, only **intra-only** formats are in scope.
- GOP results (libx264/libx265 defaults, GOP-30 AV1/VP9, VP9-lossless serving clips) are **background**.
- **Fixture provenance.** Most `CC` clips are ffmpeg-CLI encodes of frames decoded with OpenCV from the skellycam venv (code: `scripts/chromium_codecs/make_clips.py:22`), so they are **background**.
- The implementation-under-test evidence (PyAV 19.0.2) is:
  - the `CC` PyAV 19 AV1/VP9 clips, tested **only via `<video src>`** (C7);
  - the `IP` NVENC/QSV H.264/HEVC/MJPEG clips (C2, C8, C10, C11, C21, C27, C28).

The counts below were recomputed from `CC/raw/*.json` and `IPF/*.json` with my own scripts, not with `summarize.py`. The scripts are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_codecs/` (`dump.py`, `wc2.py`, `cmp.py`, `ip.py`, `cs.py`, and for this revision `revise/recount.py`, `revise/play.py`).

## 1. Questions answered

| # | Question |
|---|---|
| Q1 | Which intra-only recording formats can E35, E45 and C156 play natively? Covers `<video src>`, MSE, WebCodecs, and still images for JPEG. |
| Q2 | Are those formats frame-exact for paused seeks, single steps and playback? |
| Q3 | Which decoder does Chromium pick on this machine (hardware or software), and is there a software fallback? |
| Q4 | How must Electron serve recordings so that seeking works? |
| Q5 | Do files encoded and muxed with **PyAV 19.0.2** behave the same as the ffmpeg-CLI fixtures? |

## 2. Findings

### 2.1 Which intra-only formats open in `<video>`

- **C1** measured: **MJPEG never opens in `<video>`** in any of the three browsers.
  - This holds for re-encoded MJPEG 4:2:2 in mp4, fmp4, mkv and mov, and for the cameras' unmodified JPEG bytes in mp4, mkv and mov.
  - The error is MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`. AVI fails earlier with `DEMUXER_ERROR_COULD_NOT_OPEN`.
  - Evidence: the three `*_main.json` files (`CC/raw/electron35_main.json`, `electron45_main.json`, `chrome156/chrome156_main.json`), keys `...|play|mjpeg_422__*` and `...|play|mjpeg_camera__*`.
- **C2** measured: **`mjpeg_qsv` 4:2:2 MJPEG in MKV (PyAV 19.0.2) fails the same way** in 3 browsers × 4 contents (`IPF/seek_*.json`, clip `*/mjpeg_qsv422.mkv`).
- **C3** measured: **no API accepts an MJPEG codec string** in any of the three browsers.
  - Strings tried: `mp4v.6C`, `mjpg`, `mjpeg`, `jpeg`.
  - `canPlayType` returns `""`; MSE `isTypeSupported` returns false; MediaCapabilities says unsupported in every container.
  - WebCodecs `isConfigSupported` is false for all three hardware preferences.
  - The bare `video/x-motion-jpeg` returns `""`.
  - Evidence: probe record in the three `*_main.json`, keys `video.mjpeg`, `webcodecs.mjpeg|*`, `containersBare`.
- **C4** measured, background fixtures: **FFV1 v3 4:2:2 and rawvideo (yuv420p, yuyv422) do not open** in any container they were muxed into, in all three browsers (keys `play|ffv1_*`, `play|raw*`).
- **C5** measured, background (CLI fixture): **AV1 Main 8-bit 4:2:0 all-intra (SVT-AV1 CLI, GOP 1) plays correctly in mp4, fmp4, webm and mkv** in all three browsers (keys `play|av1_main8_intra__*`).
  - Every presented frame carried the expected index (35–37 of 35–37 per clip).
  - 10/10 paused seeks were exact.
  - The decoder was `D3D11VideoDecoder`.
  - AVI fails to open.
- **C6** measured, background (CLI fixture): **VP9 profile 0 all-intra gives the same result** in mp4, fmp4, webm and mkv in all three browsers: OK, 10/10 seeks, `D3D11VideoDecoder` (keys `play|vp9_p0_intra__*`).
- **C7** measured: **PyAV 19.0.2 AV1 and VP9 intra clips play correctly via `<video src>`** in E35, E45 and C156.
  - Clips (from `scripts/chromium_codecs/make_pyav19_clips.py`, `av==19.0.2`): SVT-AV1 all-intra in mp4, webm and mkv; libvpx-vp9 profile 0 all-intra in webm.
  - Results: 10/10 seeks, playback index exact, `D3D11VideoDecoder`, grid MAD max 0.89 (AV1) and 0.9 (VP9).
  - Evidence: `CC/raw/electron35_main.json` (217 tasks = 205 + 12 PyAV 19), `CC/raw/pyav19/electron45_main_pyav19.json`, `CC/raw/chrome156/chrome156_main_pyav19.json`.
  - Build log: `CC/pyav19_clips_log.json` records `"av": "19.0.2"` and `g: "1"`.
  - These clips were **not** run through MSE or WebCodecs (all 12 `pyav19` keys are `play|`).
- **C8** measured: **H.264 and HEVC all-IDR, no-B files from the hardware encoders (PyAV 19.0.2) open and seek exactly in all three browsers.** All decoding ran on the RTX 3070, QSV-encoded files included.
  - Encoders: `h264_nvenc`, `hevc_nvenc`, `h264_qsv`, `hevc_qsv`.
  - 48 files: 4 encoders × mp4/fmp4/mkv × 4 contents (720p and 1080p; CFR and real-capture VFR).
  - Paused seeks to the midpoint of the real pts interval: **4800/4800 per browser** (`IPF/seek_*.json`, path `video`, mode `mid`).
  - Single steps: **5856/5856 per browser** (`IPF/step_*.json`, path `video`).
  - All-IDR and no-B checked: every frame is IDR in a NAL scan, and `has_b_frames = 0` (`IP/clips_summary.json`, `nal_check`, `ffprobe`).
- **C9** measured, background: **libx264/libx265 GOP files showed frame-index and seek errors** (`CC/raw/*_main.json`, keys `play|h264_high_420__fmp4`, `play|hevc_main_420__mp4`).
  - fmp4: every presented frame 2 frames behind; seeks 2/10.
  - HEVC in mp4/mov: seeks 7/10, with targets 29, 30 and 31 all landing on frame 33.
  - measured: **not observed in the IP intra clips**: `cfrmid` CFR fmp4 200/200 per encoder (`IPF/seek_*.json`).
  - inferred: the link to B-frames/GOP is not isolated. Encoder, content, resolution, harness, seek targets and seek mode all differ, and no intra mov was tested.
- **C10** measured: **`currentTime = (k + 0.5) / fps` is exact only on constant-frame-rate files** (`IPF/seek_*.json`, mode `cfrmid` vs `mid`).
  - CFR: 2400/2400 per browser.
  - Real-capture VFR: **228/2400 per browser**.
  - Seeking to `mid` computed from the real pts gives 2400/2400 on the same VFR files.
- **C11** measured: **`<video>` rVFC readback on VFR intra files shows a few off-by-one frames** (`IPF/play_*.json`, `per_stream.pattern_mismatch`).
  - VFR: E35 25/3549, E45 62/3426, C156 55/3294. CFR: 0 in every browser.
  - Master-clock paths had 0 mismatches. These paths read the pattern from the frame they drew themselves, so they cannot show a readback race. The two numbers measure different things.
  - inferred (`IP/NOTES.md` §4.3): a readback race, not a wrong frame on screen. NOT VERIFIED.
  - The three browsers ran concurrently.

### 2.2 Decoders on this machine (RTX 3070)

- **C12** measured: **E35 and E45 mark the RTX 3070 active and the UHD 770 inactive.**
  - RTX 3070 (0x10DE/0x2484): `active: true`. UHD 770 (0x8086/0xA780): `active: false`.
  - Evidence: `CC/raw/electron35_main.json` and `electron45_main.json`, `gpuInfoComplete.gpuDevice`; `IPF/e35/caps.json` and `IPF/e45/caps.json`, `gpu_info.gpuDevice`.
  - C156 lists both GPUs (`chrome156_main.json` `systemInfoBefore.gpu.devices`; `IPF/c156/caps.json`) but has no `active` field. Its active adapter is NOT VERIFIED.
  - inferred: the active adapter is the one `D3D11VideoDecoder` used.
- **C13** measured: **of the streams played, only the 4:2:0 ones got `D3D11VideoDecoder`** (`kIsPlatformVideoDecoder = true`) on this RTX 3070.
  - 4:2:0 on D3D11:
    - AV1 and VP9 4:2:0 (CLI and PyAV 19);
    - H.264 High 4:2:0 and HEVC Main/Main 10 (background);
    - H.264/HEVC intra from NVENC and QSV.
  - Background (CLI GOP fixtures) on software decoders: `Dav1dVideoDecoder` for AV1 4:4:4/4:2:2, `VpxVideoDecoder` for VP9 profile 1/3, `FFmpegVideoDecoder` for H.264 High 4:2:2.
  - The one HEVC 4:2:2 file played is in C17.
  - Not separated: whether the limit comes from the GPU or from Chromium.
  - Evidence: DevTools `kVideoDecoderName` in `CC/raw/*_main.json` `media`, and in `IPF/seek_*.json` `media_players_at_end`.
- **C14** measured: **WebCodecs `prefer-software` rejects HEVC in all three browsers.**
  - HEVC Main/Main 10 probes: `isConfigSupported` false (`CC/raw/*_main.json`, `wc|hevc_*|prefer-software`).
  - All 24 HEVC `webcodecs-sw` seek configs per browser fail with `config not supported` (`IPF/seek_*.json`).
  - H.264 `prefer-software` decodes with `FFmpegVideoDecoder`: 720/720 seeks per browser.
  - NOT VERIFIED: `<video>` software fallback for H.264 or HEVC. `scripts/chromium_codecs/run_swdecode.sh` exists but produced no output file.
- **C15** measured, background (CLI fixture): **AV1 and VP9 all-intra decode in WebCodecs with both preferences** (`CC/raw/*_main.json`, `wc|av1_main8_intra|*`, `wc|vp9_p0_intra|*`).
  - 60/60 key chunks output in order.
  - `prefer-hardware` uses `D3D11VideoDecoder` and outputs NV12.
  - `prefer-software` uses `Dav1dVideoDecoder`/`VpxVideoDecoder` and outputs I420.
- **C16** measured: **Chromium reports `jpegDecodeAcceleratorSupported: false`** (`CC/raw/electron35_main.json`, `electron45_main.json` and `chrome156_main.json`, `auxAttributes`).
  - inferred: JPEG images are decoded in software. The decoder actually used by `ImageDecoder`/`createImageBitmap` was not observed. NOT VERIFIED.
- **C17** measured: **HEVC 4:2:2 from `hevc_qsv` does not play in Chromium on this RTX 3070.**
  - Test: one 720p 8-bit 4:2:2 MKV (`hevc_qsv` from YUYV), played from `file://` (`CC/raw/verify_method_rechecks.json`).
  - E35: MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`.
  - E45: opens, then MediaError 3 `PIPELINE_ERROR_DECODE`.
  - A 4:2:0 `hevc_qsv` control MKV plays in both.
  - C156: NOT VERIFIED.
  - The test was functional only: no index-pattern readback.
- **C17a** measured: **E45/C156 accept HEVC RExt codec strings; E35 rejects them.**
  - E45/C156 return `canPlayType` "probably" and WebCodecs `prefer-hardware` supported for:
    - `hvc1.4.10.L93.B0` (`CC/raw/*_main.json`, `video.hevc_rext_422_10`);
    - E45 only: `hvc1.4.10.L120.9D` and `hvc1.4.10.L120.9D.08`, which carry the real file's constraint flags (`verify_method_rechecks.json`).
  - E35 returns `""` and false for all of them.
  - code: `hvc1.4.10.L93.B0` is defined with no explanation (`scripts/chromium_codecs/harness/probe.js:30`).
  - inferred, from the SPS bit order in the trace: byte `B0` carries no 4:2:2 or 10-bit constraint flags. So the earlier label "4:2:2 10-bit" for that string was wrong.
  - Supporting only, different decoders: FFmpeg also fails to decode the same file with `hevc_cuvid`, `hevc`+cuda, d3d11va and d3d12va (`results/hw_accel_target/NOTES_functional.md:126`).
- **C18** measured: **E35 renders partially tagged CLI AV1 intra clips with a higher grid MAD than E45/C156.** The frame index is exact in every case.
  - ffprobe on the CLI clip: `color_space=bt709`, `color_range=tv`, primaries and transfer `unknown`.
  - ffprobe on the PyAV 19 clip: bt709 for all three tags.

  | clip (DevTools matrix / primaries / transfer) | E35 MAD | E45 MAD | C156 MAD |
  |---|---|---|---|
  | CLI AV1 intra mp4, `play` (UNSPECIFIED / UNSPECIFIED / UNSPECIFIED) | 3.12 | 0.9 | 0.9 |
  | CLI AV1 intra webm, `play` (BT709 / UNSPECIFIED / UNSPECIFIED) | 3.12 | 0.9 | 0.9 |
  | CLI AV1 intra webm, `mse` (BT709 / INVALID / INVALID) | 3.12 | 0.9 | 0.9 |
  | CLI AV1 intra fmp4, `mse` (BT709 / BT709 / BT709) | 0.9 | 0.9 | 0.9 |
  | PyAV 19 AV1 intra mp4, `play` (BT709 / BT709 / BT709) | 0.89 | 0.89 | 0.89 |
  | background: CLI AV1 4:4:4 mp4, `play`, dav1d (UNSPECIFIED ×3) | 2.73 | 2.61 | 2.73 |
  | background: CLI AV1 4:4:4 webm, `play`, dav1d (BT709 / UNSPECIFIED / UNSPECIFIED) | 2.73 | 0.5 | 0.5 |

  - Evidence: `kVideoTracks` and `madMax` in the three `*_main.json`, plus the PyAV 19 result files for E45/C156.
  - The reported matrix alone does not explain the E35 difference: the webm reports BT709 and still gives 3.12.
  - inferred: in this data, E35 gives 0.9 only when all three tags are BT.709. Root cause not traced.
  - MAD is a luma block-mean grid statistic (code: `scripts/chromium_codecs/harness/common.js:22,39-41`). No image was inspected.

### 2.3 MSE and WebCodecs details

- **C19** measured, background (CLI fixture): **MSE rejects Matroska** for every codec in all three browsers (`CC/raw/*_main.json`, `mse|*__mkv`, `setupError`).
  - `video/x-matroska` gives `isTypeSupported` false.
  - `addSourceBuffer` throws NotSupportedError.
- **C20** measured, background (CLI fixture): **AV1 and VP9 all-intra work under MSE** in webm and fmp4 in all three browsers: 10/10 seeks, playback index exact (keys `mse|av1_main8_intra__{webm,fmp4}`, `mse|vp9_p0_intra__{webm,fmp4}`).
  - PyAV 19 clips under MSE: NOT VERIFIED.
- **C21** measured: **with the hardware decoder, `h264_nvenc` intra frames come out only after a `flush()`** (`IPF/seek_*.json`, `IPF/step_*.json`).
  - On paths `webcodecs` (no preference) and `webcodecs-hw`, no output arrived within the harness's 200 ms window (code: `scripts/chromium_sync_scrub/harness/harness.mjs:153,273`), so the fallback `flush()` ran: 360/360 per path per browser.
  - `webcodecs-sw` (FFmpegVideoDecoder): 0/360 flushes, and 360/360 exact.
  - `h264_qsv`, `hevc_nvenc` and `hevc_qsv` needed 0 fallback flushes on every path.
  - With `wcflush=1` (flush right after the target chunk), every encoder was exact: 4800/4800 seeks and 5856/5856 steps per browser.
  - inferred: the 360/360 vs 0/360 split makes machine load an unlikely cause.
  - Not tested: Intel and AMD decoders.
- **C22** measured: **the SPS differs between the two H.264 encoders** (`IP/sps_vui_trace.txt` lines 7, 16 and 17; the trace covers the `c720p30` clips only).
  - `h264_nvenc`: `bitstream_restriction_flag = 0`.
  - `h264_qsv`: `bitstream_restriction_flag = 1`, `max_num_reorder_frames = 0`.
  - inferred: without a reorder bound, the hardware decoder holds the frame until more data or a flush arrives. NOT VERIFIED in Chromium code.
- **C23** removed in this revision.
  - The `decoded_hist = {"1": n}` value is 1 by construction for all-keyframe clips (code: `harness.mjs:124,138,151,160`).
  - The correct count would be 168 of 192 WebCodecs seek configs per browser; the other 24 are HEVC `prefer-software`, unsupported (C14).
  - Single-frame independence is shown by exact output after `reset()` + `configure()` with only chunk k fed (C8, C21).
- **C24** measured, background (GOP, libx264 Annex B elementary stream): **E35 rejects the libx264 H.264 stream in WebCodecs, and E45/C156 accept it** (`CC/raw/*_main.json`, `wc|h264_high_420|*`).
  - E35: `DataError: A key frame is required after configure() or flush()` for both preferences.
  - E45 and C156 decode it 60/60.
  - The same E35 decodes `h264_nvenc` + `h264_qsv` intra (MP4/avcC-derived chunks) exactly (`IPF/e35/seek_*.json`, `step_*.json`):
    - seeks without forced flush: 720/720 on each of the three paths (2160/2160);
    - seeks with `wcflush=1`: 2400/2400;
    - steps with `wcflush=1`: 2928/2928.
  - `h264_nvenc` access units also start with SEI (`IP/clips_summary.json`, `nal_check.first_frame_nal = [6, 6, 5]`), so SEI-first is not the distinguishing factor.
  - Root cause NOT VERIFIED.

### 2.4 JPEG frames as images (the G1 passthrough path)

- **C25** measured: **all 88 real camera JPEGs decode with `ImageDecoder`, `createImageBitmap` and `<img>`** in all three browsers (`CC/raw/*_main.json`, key `...|img`, `images`).
  - Quality: grid luma MAD ≤ 0.04 against the OpenCV decode (code: `scripts/chromium_codecs/harness/img.js:2,11`; `common.js:22`). Chroma and fine detail were not checked.
  - The files are 4:2:2 baseline frames. `ImageDecoder` outputs `I422`.
  - Sets (my regrouping): c922_1080p 19, c930e_1080p 19, c922_1600x896 19, c922_720p60 10, generic_1080p 11, c930e_720p_flash 10.
- **C26** measured: **the `generic_1080p` frames decode in all three browsers although libjpeg warns.**
  - OpenCV/libjpeg reports "Corrupt JPEG data: 535 extraneous bytes before marker 0xd9" and similar (`CC/jpeg_warnings_generic_1080p.txt`).
  - All 11 decode with all three APIs.
- **C27** measured: **the JPEG-sequence path (frames fetched by HTTP Range) was exact on every check**, on both `.mjpeg` + index and JPEG-in-MKV + index (`IPF/seek_*.json`, `step_*.json`, `play_*.json`).
  - Seeks: 800/800 per decode path (`createImageBitmap`, `ImageDecoder`) per browser.
  - Steps: 976/976 per decode path per browser.
  - Master-clock playback: 0 pattern mismatches in **1200 draws per browser**: 4 contents × 2 containers × 150 draws, which is 300 per content.
  - Master-clock playback used the `createImageBitmap` path only (`jpeg-master-range-bitmap`). No `ImageDecoder` playback run exists.
- **C28** measured: **single camera frames can be fetched out of an MKV by byte range over HTTP** (`IPF/jpegmkv_seq.json`, `IPF/jpegmkv_random.json`).
  - Setup: an MKV of 300 unmodified c930e 720p JPEGs, plus a sidecar index of byte offsets.
  - Per browser, 300 sequential and 150 random fetches all returned HTTP 206. The harness enforces 206 (code: `harness.mjs:585`).
  - Every fetched frame was byte-identical to the corpus file, with SOI and EOI.
  - Every frame decoded with both APIs. Only the decoded size was checked (code: `harness.mjs:591-592`).

### 2.5 Serving in Electron (suite `serving`; 7 small + 3 big ~120 MB clips)

Background: 9 of the 10 serving clips are GOP (the big VP9-lossless clips use `-g 30`, code: `scripts/chromium_codecs/make_big_clips.py:45`). Only `av1_main8_intra__mp4` is intra. inferred: Range behaviour does not depend on the codec.

- **C29** measured: **three serving methods all seek exactly**: local HTTP with Range, `file://` (Electron), and `protocol.handle` with a handler that parses `Range` itself.
  - Small clips 10/10, big clips 15/15, including mp4 with the moov at the end.
  - This holds in E35 and E45, with and without the `stream` privilege (`CC/raw/electron35_serving.json`, `electron45_serving.json`).
- **C30** measured: **serving without Range breaks seeking** (same files, plus `CC/raw/chrome156_serving.json`).
  - HTTP that always returns 200 with the full body: every seek lands on frame 0 (1/10, 1/15) in E35, E45 and C156.
  - `protocol.handle` returning a full 200 body: small clips exact, big clips 2/15, and the big mp4 with the moov at the end fails to open.
- **C31** measured: **a protocol handler that passes `net.fetch(file://...)` through breaks seeking.**
  - Results: E35 1/10 and 1/15 everywhere; E45 mixed on small clips and 1/15 on big clips.
  - The handler answered 200 even when `Range` was forwarded: `protocolLog` has 0 status-206 responses (same JSONs).
- **C31a** measured (new): **in E35 and E45, `fetch(file://…)` with `Range: bytes=10-19` returns the correct 10 bytes, but with status 200 and no `Content-Range`** (`CC/raw/verify_method_rechecks.json`).
- **C32** NOT VERIFIED: **frame accuracy over `file://` in Chrome.**
  - Seeks complete (10/10), but the canvas is tainted, so frames cannot be read back: `seekExact` 0, `first` null (`CC/raw/chrome156_serving.json`).
  - This does not apply to Electron, which was exact (C29).

### 2.6 Electron 35 vs 45 vs Chrome 156

- **C33** measured: **the intra-only play, seek, MSE and WebCodecs results and the decoder choices are the same in E35, E45 and C156** (C5–C8, C13–C15, C19–C22). Exceptions:
  - MAD on partially tagged AV1 (C18);
  - the libx264 WebCodecs case (C24, background);
  - HEVC 4:2:2: E35 does not open the file, E45 fails to decode it (C17).
- **C33a** measured: **the E35 rerun matches the 12:19 E35 run (iGPU absent)** on every play, MSE and WebCodecs result except one flaky playback frame in `mse|av1_pro8_422__fmp4`.
  - That cell is GOP, 4:2:2 and background.
  - Evidence: my `cmp.py` on `CC/raw/electron35_main.json` vs `CC/raw/e35_main_1219_igpu_absent/electron35_main.json`.
- **C34** measured: **the E45 and C156 probe records are identical in all six sections; E35 differs** (`containersBare`, `video`, `audio`, `audioWebCodecs`, `webcodecs`, `imageDecoder`). E35 differences found (not exhaustive):
  - `""` for `video/x-matroska` (bare and with codecs) and MediaCapabilities `unsupported`, although E35 plays MKV (C5, C8);
  - `""` for `application/vnd.apple.mpegurl`, where E45/C156 say `"maybe"`;
  - no JPEG XL in `ImageDecoder`;
  - HEVC RExt strings unsupported (C17a);
  - Matroska audio probes and flac/vorbis `AudioDecoder` configs differ (`CC/VERIFY_provenance.md` §2).
- **C35** measured, background (CLI fixtures for the decoder side): **`canPlayType` returns "probably" for codecs that only decode in software.**
  - Affected: AV1 4:4:4 (`av01.1…`), AV1 4:2:2 (`av01.2…`) and VP9 profile 1.
  - MediaCapabilities `powerEfficient` false matched the software decoder in every case played (probe record vs C13).
  - Counter-case: the HEVC RExt probe says "probably" and `powerEfficient` true in E45/C156, yet the real 4:2:2 file fails to decode in E45 (C17, C17a).

## 3. Comparison tables

### 3.1 Intra-only recording formats in Chromium (E35 / E45 / C156 identical unless noted; all decoding on the RTX 3070)

| intra-only format (encoder) | `<video>` opens | frame-exact paused seek / step | MSE | WebCodecs | decoder on RTX 3070 | software fallback in Chromium | evidence |
|---|---|---|---|---|---|---|---|
| JPEG frames, camera bytes (passthrough) | **no** (C1) | yes, as images via HTTP Range + `createImageBitmap`/`ImageDecoder`: 800/800 seeks, 976/976 steps per path (C27) | no (C3) | no `VideoDecoder` config (C3); `ImageDecoder` yes | no JPEG accelerator reported (C16); software decode inferred | n/a (image decode) | C1, C3, C16, C25–C28 |
| MJPEG 4:2:2 from `mjpeg_qsv` (MKV) | **no** (C2) | as images: same as row 1 (C27) | no | no | – | – | C2, C27 |
| H.264 all-IDR, `h264_nvenc` / `h264_qsv` (mp4, fmp4, mkv) | yes | yes: `<video>` 4800/4800 seeks (mid from pts) and 5856/5856 steps per browser across the 4 H.264/HEVC encoders | not tested on these files | yes. With the hardware decoder, `h264_nvenc` needs `flush()` per chunk (C21) | D3D11 (QSV files also decoded on NVIDIA) | WebCodecs `prefer-software`: yes, FFmpegVideoDecoder (C14). `<video>` fallback NOT VERIFIED | C8, C13, C14, C21 |
| HEVC all-IDR 4:2:0, `hevc_nvenc` / `hevc_qsv` | yes | yes (as above) | not tested on these files | yes, hardware only | D3D11 (QSV files also decoded on NVIDIA) | WebCodecs: **no** (C14). `<video>` NOT VERIFIED | C8, C14 |
| HEVC RExt 4:2:2 8-bit (`hevc_qsv` from YUYV), one 720p MKV | **E35 no** (demuxer error); **E45 opens, then decode error**; C156 NOT VERIFIED | – | not tested | probes only: E45/C156 "supported", E35 no (C17a) | fails (E45 `PIPELINE_ERROR_DECODE`) | not tested | C17, C17a |
| AV1 Main 8-bit 4:2:0 all-intra (SVT-AV1) | yes: PyAV 19 (C7) and CLI (C5, background) | yes: 10/10 seeks, every presented frame correct (PyAV 19 and CLI) | CLI fixture only (C20, background); PyAV 19 NOT VERIFIED | CLI fixture only: both preferences (C15, background) | D3D11 | WebCodecs dav1d, CLI fixture (C15, background) | C5, C7, C15, C20 |
| VP9 profile 0 all-intra (libvpx) | yes: PyAV 19 webm (C7) and CLI (C6, background) | yes: 10/10 | CLI fixture only (C20, background) | CLI fixture only: both preferences (C15, background) | D3D11 | WebCodecs libvpx, CLI fixture (C15, background) | C6, C7, C15, C20 |
| VP9 profile 0 all-intra from `vp9_qsv` | **NOT VERIFIED** (not played) | – | – | – | – | – | §6 |
| FFV1 v3 4:2:2 / rawvideo (background fixtures) | **no** (C4) | – | no | no | – | – | C4 |

### 3.2 Hardware-target recording candidates (encode side from `hw_accel_target`) vs Chromium playback (this topic)

| recording format | hardware encode on RTX 3070 | hardware encode on UHD 770 | licensing (G7), from `results/licensing/FINDINGS.md` | Chromium playback route |
|---|---|---|---|---|
| JPEG / MJPEG 4:2:2 | nvJPEG (CUDA): `results/gpu_encode/NOTES.md` §6 | `mjpeg_qsv`, 4:2:2 from YUY2 (`results/hw_accel_target/NOTES_functional.md:17`) | baseline: no patents identified in T.81 Annex L (`:33`) | images only (C1–C3, C25–C28) |
| H.264 intra 4:2:0 | `h264_nvenc` (`NOTES_functional.md:69`) | `h264_qsv` (`:15`) | royalty-bearing pool, Via LA AVC (`:45`) | `<video>`/WebCodecs, hardware decode; software decode in WebCodecs (C8, C14) |
| HEVC intra 4:2:0 | `hevc_nvenc` | `hevc_qsv` | royalty-bearing pools (`:47-48`) | `<video>`/WebCodecs, hardware decode; no WebCodecs software decoder (C14) |
| VP9 intra | none: no NVENC VP9 (`results/hw_accel_target/NOTES_sources_nvidia_intel.md:31`, `NOTES_functional.md:134`) | `vp9_qsv` (`NOTES_functional.md:16`) | Google royalty-free grant (`:28`); Sisvel royalty-bearing pool also offered (`:29`) | libvpx VP9 intra plays (C6, C7); `vp9_qsv` output NOT VERIFIED |
| AV1 intra | none on RTX 3000; AV1 NVENC starts at Ada (`NOTES_sources_nvidia_intel.md:32`; `NOTES_functional.md:19-21`) | none | AOM royalty-free licence (`:22`); Sisvel royalty-bearing pool also offered (`:25`) | plays (C5, C7) |

### 3.3 Playback fixture sizes (PyAV 19.0.2, about Y-PSNR 55 dB; **not** the official matched-quality comparison, which is `results/intra_compare/`)

Source: measured, `IP/clips_summary.json` (bytes/frames, `decode_check*.y_psnr_db_mean` and `y_ssim_mean`). I recomputed these numbers.

| encoder (q) | 720p bytes/frame | 720p Y-PSNR / SSIM | 1080p bytes/frame | 1080p Y-PSNR / SSIM | basis |
|---|---|---|---|---|---|
| h264_nvenc (17 / 14) | 33,772 | 55.42 / 0.9979 | 181,957 | 54.49 / 0.9969 | MP4 file |
| hevc_nvenc (17 / 11) | 27,457 | 54.54 / 0.9973 | 213,013 | 54.92 / 0.9971 | MP4 file |
| h264_qsv (11 / 8) | 41,340 | 55.71 / 0.9980 | 223,571 | 54.93 / 0.9972 | MP4 file |
| hevc_qsv (20 / 17) | 31,732 | 55.35 / 0.9978 | 184,628 | 55.01 / 0.9972 | MP4 file |
| mjpeg_qsv 4:2:2 (85 / 90) | 51,075 | 55.72 / 0.9983 | 206,938 | 54.55 / 0.9975 | `jpeg_seq` (raw concatenated JPEG, no container); `mjpeg_qsv422.mkv` gives 51,121 / 206,983 |

Caveats:
- PSNR/SSIM are on Y only.
- `mjpeg_qsv` gets YUYV full range and writes 4:2:2. H.264/HEVC get NV12 limited range and write 4:2:0 (`IP/NOTES.md` §2). JPEG's extra chroma is not credited.
- The 1080p content is 19 real frames looped.
- The quality points differ by up to about 1.2 dB.
- Use `results/intra_compare/` for bytes at matched quality.

## 4. Implications for the plan (each tied to findings)

- **P1, from C1–C4.**
  - A recording that stores the camera JPEGs untouched **cannot be played with `<video>`** in any Chromium version tested. This is G1: royalty-free per `results/licensing/FINDINGS.md:33`, and hardware-encodable through nvJPEG or `mjpeg_qsv`.
  - The UI must show JPEG recordings as images: Range fetch, then `createImageBitmap` or `ImageDecoder`, driven by a frame index.
- **P2, from C27, C28 and C31a.**
  - The image path is **frame-exact** for seek, step and master-clock playback (`createImageBitmap`) over local HTTP with Range.
  - It works on a concatenated `.mjpeg` file and on JPEG-in-MKV with a byte-offset sidecar, so one MKV can serve both G1 (no transcode) and G9 (index access).
  - Every JPEG-path test was served over HTTP (code: `scripts/chromium_sync_scrub/harness/main.cjs:142`, `server.cjs:55`).
  - Under Electron `file://`, a Range fetch returns the right bytes but with status 200 and no `Content-Range` (C31a). Code must not require 206 there.
  - NOT VERIFIED: the full JPEG path over `file://` or `protocol.handle`.
  - Whether the path is fast enough for N cameras is tonight's bench (§5).
- **P3, from C8, C13 and C14.** If the plan also needs a `<video>`-playable intra format:
  - H.264 intra is the only hardware-target candidate with a measured Chromium software decoder (WebCodecs `prefer-software`). It is encodable on NVENC and QSV, but royalty-bearing.
  - HEVC intra decoded only in hardware here; WebCodecs offers no software HEVC decoder.
  - inferred: a machine without HEVC decode hardware would get no HEVC playback in these builds. NOT VERIFIED (no such machine; `<video>` fallback not run).
- **P4, from C5–C7 and table 3.2.**
  - AV1 and VP9 intra, the formats with royalty-free grants, play frame-exactly in `<video>`.
  - Neither has hardware encode on RTX 3000 (Ampere), so neither meets the RTX 3000+ target (requirement 9).
  - VP9 intra has hardware encode only on Intel QSV here.
  - AV1 NVENC exists from Ada; all-intra AV1 on Ada is NOT VERIFIED.
  - JPEG (P1) is the format that meets the hardware target on RTX 3000 and has a royalty-free basis, at the cost of the image-based player.
- **P5, from C13, C17 and C17a.**
  - Record 4:2:0 if Chromium must decode the file on NVIDIA.
  - The one HEVC 4:2:2 file measured fails: E35 does not open it, and E45 fails to decode it.
  - E45/C156 probes still say "probably"/supported for RExt strings, so the UI must not trust the probes for 4:2:2.
  - The FFmpeg result on the same GPU (`NOTES_functional.md:126`) is supporting evidence only.
- **P6, from C10.** The UI must seek by **real pts** (the midpoint of the frame interval, from the file or the index), not by `(k + 0.5) / fps`. Real captures are VFR, and the fps rule hit 228/2400.
- **P7, from C21 and C22.**
  - A WebCodecs player for `h264_nvenc` intra, using hardware decode on NVIDIA, must call `flush()` after each key chunk.
  - inferred, NOT VERIFIED: alternatively, the encoder could write a VUI reorder bound. Whether NVENC has such an option was not checked.
  - Intel/AMD decoders were not tested.
- **P8, from C18.** inferred: the recorder should write all three BT.709 colour tags (primaries, transfer, matrix). Partially tagged CLI AV1 gave a higher grid MAD in E35. Fully tagged PyAV 19 output gave 0.89 in all three browsers.
- **P9, from C19, C20 and C34.**
  - If MSE is needed, use MP4 (fmp4) or WebM; Matroska works only for `<video src>`.
  - Evidence is CLI fixtures (background).
  - Do not gate playback on `canPlayType`: E35 says `""` for MKV that it plays.
- **P10, from C29–C31a.**
  - For `<video>`, Electron must serve recordings from `file://`, or from a `protocol.handle` scheme that answers Range itself with 206 and `Content-Range`.
  - A `net.fetch(file://)` passthrough or a full-body 200 breaks seeking on files that are not fully buffered.
  - The evidence is mostly GOP clips; codec independence is inferred.
- **P11, from C17a, C18, C33 and C34.**
  - Upgrading Electron from 35 to 45 is **not required** for intra-only playback.
  - E45 adds: MKV and HLS MIME probes, JPEG XL in `ImageDecoder`, and lower grid MAD on partially tagged AV1 4:2:0 (0.9 vs 3.12).
  - E45 does not fix untagged AV1 4:4:4 mp4 (MAD 2.61), and does not make HEVC 4:2:2 decodable here.

## 5. Pending tonight's bench

`results/BENCH_QUEUE_2300.md` does not exist. The queue is `results/bench_queue_2300.json` (19:06). This topic has no bench items of its own. The queued items that bear on G8:

| id | in queue | question it answers for this topic | command |
|---|---|---|---|
| IP-SEEK-E35 / IP-SEEK-E45 | yes | decode cost per frame on the scrubbing path, N = 1, 1080p, 200 random seeks: `<video>` mid vs WebCodecs (`wcflush=1`) vs JPEG Range + `createImageBitmap`/`ImageDecoder` (C27 vs C8) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35\|45> --suite bench_intra_seek` |
| IP-SYNC-E35 / IP-SYNC-E45 | yes | N = 4/8, 1080p: frame-index spread, drops, CPU and working set. Compares the JPEG master clock (bitmap and ImageDecoder) with `<video>`/WebCodecs H.264/HEVC intra. NVENC files only (`--skip _qsv_`) | `... run_suite.py --electron <35\|45> --suite bench_intra_sync --skip _qsv_` |
| IP-SUM | yes | tables | `uv run --script .../chromium_sync_scrub/summarize.py bench intra` |
| IP-SCRUB-E35 / IP-SCRUB-E45 | **no, not queued** | N = 4/8 drag scrub | `... run_suite.py --electron <35\|45> --suite bench_intra_scrub` |

- inferred from the item purposes: IP-SEEK and IP-SYNC cover the "Chromium JPEG-sequence sync/seek" item of requirement 11. There is no separate chromium_sync_scrub item in the queue.
- measured: smoke runs of the three intra suites completed with 0 errors in E35 and E45. The smoke numbers were discarded (`IP/bench/e*/bench_intra_*_smoke/`, `IP/NOTES.md` §7).
- Nothing in this document depends on a timing number. P2 and P3 stay open until these benches report.

## 6. Not tested / limits / NOT VERIFIED

- NOT VERIFIED: playback of **`vp9_qsv`** output, the only intra hardware video encoder on Gerald with a royalty-free grant. Only libvpx VP9 intra was played.
- NOT VERIFIED: playback of `h264_mf`/`hevc_mf` and `*_d3d12va` output.
- NOT VERIFIED: HEVC 4:2:2 in C156, and HEVC 4:2:2 with index-pattern readback. One file was tested in E35/E45 (C17).
- NOT VERIFIED: `<video>` software-decode fallback. `run_swdecode.sh` produced no output.
- NOT VERIFIED: MSE or WebCodecs on the PyAV 19 AV1/VP9 clips. They were tested via `<video src>` only.
- NOT VERIFIED: hardware decode on Intel (UHD 770 inactive in E35/E45, C12), AMD or Apple GPUs; Linux (VA-API) and macOS; a machine with no HEVC or AV1 decode hardware. All QSV-encoded files were decoded on NVIDIA.
- NOT VERIFIED: the JPEG path over `file://` or `protocol.handle` (P2).
- Fixture deviation: most `CC` clips were encoded with the ffmpeg 9.0.2 CLI (gyan) from frames decoded with OpenCV from the skellycam venv, read-only (code: `scripts/chromium_codecs/make_clips.py:22`). These are background.
  - PyAV 19.0.2 coverage is SVT-AV1 and libvpx-vp9 via `<video>` (C7) in `CC`, plus the NVENC/QSV H.264/HEVC/MJPEG clips in `IP`.
  - `make_pyav19_clips.py` pins `av==19.0.2` but not `numpy`.
- `CC` clips are 1280×720 and 60 frames (600 for the big serving clips); playback is checked over about 1.2 s per clip.
- `IP` adds 1080p, but its 1080p content is 19 frames looped. `IP` playback covers 5 s per clip.
- The `CC` play/seek check uses 10 fixed seek targets per clip. `IP` uses 100 random seeks per clip (seed 1) plus steps.
- Quality checks are luma grid MAD (C18, C25) or Y-PSNR/SSIM (§3.3). No chroma check, and no visual inspection.
- Serving runs (12:01–12:19) predate the iGPU's return and were not rerun. Their decoder names match C13. 9 of the 10 serving clips are GOP.
- Root causes not traced in Chromium code:
  - the `h264_nvenc` hardware-decoder flush need (C21/C22);
  - the E35 libx264 WebCodecs DataError (C24);
  - the E35 MAD on partially tagged AV1 (C18);
  - the GOP fmp4 and HEVC mp4 seek errors (C9, background).
- The `<video>` VFR readback mismatches (C11) are not resolved to what was on screen.
- The `IP` functional runs had E35, E45 and C156 running in parallel on a shared machine. This affects no exactness result, but no timing may be taken from them.
- No crash-truncated files were played (that is `crash_resilience`). No audio was played (probes only).
- nvidia-smi encoder sessions were 0–1 around the logged `CC` runs (`CC/raw/nvidia_smi.log`, which ends at 22:14Z). The E45/C156 `--only pyav19` runs were not logged. These are decode-only tests.
- After the verifier's Electron rechecks: 0 encoder sessions (`CC/raw/verify_method_rechecks.json`).

## 7. How to reproduce

Repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Git Bash. `S` = `research/skellycam_recording/recording_upgrade/scripts`. Media goes under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/`.

```
# chromium_codecs fixtures (CLI/OpenCV, background) and the PyAV 19.0.2 cross-check clips
.venv/Scripts/python.exe $S/chromium_codecs/make_clips.py          # read-only venv use; see section 6
.venv/Scripts/python.exe $S/chromium_codecs/make_extras.py
.venv/Scripts/python.exe $S/chromium_codecs/make_big_clips.py
uv run --script $S/chromium_codecs/make_pyav19_clips.py            # av==19.0.2

# browser runs (each script unsets ELECTRON_RUN_AS_NODE; all except run_pyav19_check.sh log nvidia-smi to results/chromium_codecs/raw/nvidia_smi.log)
bash $S/chromium_codecs/run_rerun_e35.sh          # E35 main (217 tasks incl. pyav19)
bash $S/chromium_codecs/run_rerun_e45_chrome.sh   # E45 main + Chrome 156 main
bash $S/chromium_codecs/run_pyav19_check.sh       # E45 + C156, --only pyav19 (no nvidia-smi logging)
bash $S/chromium_codecs/run_functional.sh serving # serving suite (E35, E45, C156)
.venv/Scripts/python.exe $S/chromium_codecs/summarize.py           # regenerates results/chromium_codecs/tables.md
python $S/chromium_codecs/spotcheck.py <raw json> 'play|hevc_main_420__mp4'
python $S/chromium_codecs/probe_diff.py <e35_main.json> <e45_main.json> <c156_main.json>

# intra-only H.264/HEVC/MJPEG playback (PyAV 19.0.2 clips; see results/intra_playback/NOTES.md section 7)
uv run --script $S/intra_playback/gen_intra_clips.py
bash $S/intra_playback/trace_headers.sh > research/skellycam_recording/recording_upgrade/results/intra_playback/sps_vui_trace.txt
uv run --script $S/chromium_sync_scrub/run_suite.py --electron <35|45|chrome> --suite intra_functional
uv run --script $S/intra_playback/summarize_intra.py

# verifier rechecks (HEVC 4:2:2 probe/play, file:// Range fetch): scripts in $S/chromium_codecs/verify_method/, output CC/raw/verify_method_rechecks.json
```

- Electron binaries:
  - E35: `skellycam-ui/node_modules/electron/dist/electron.exe`.
  - E45: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe`. If it is missing, reinstall `electron@45.2.3` into a scratchpad.
- The harness needs the switches `disable-backgrounding-occluded-windows`, `disable-renderer-backgrounding` and `--disable-features=CalculateNativeWinOcclusion` (code: `scripts/chromium_codecs/harness/electron_main.js:35-40`).
  - Without them, E45's first run got 0 rVFC callbacks in all 113 play tasks (`CC/raw/first_attempt/electron45_main.json`).
  - E35's first run had callbacks in 71 of 113.

## 8. Verification

Inputs: `CC/VERIFY_provenance.md` and `CC/VERIFY_method.md` (both 2026-11-09). I re-checked every refutation against the raw files before applying it. My scripts are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_codecs/revise/`.

| draft claim | verdict | my re-check | change made |
|---|---|---|---|
| C23 "184 configs, decoded exactly one chunk" | refuted | `recount.py`: 192 WebCodecs seek configs per browser, 168 with `{"1": n}`, 24 HEVC `webcodecs-sw` with no histogram. `harness.mjs:138,151,160` gives decoded = 1 by construction for intra | finding removed; note kept under C23 |
| C24 "1440/1440 without, 4800/4800 with flush" for H.264 | refuted | E35 H.264: 720/720 per path (2160 over 3 paths), 2400/2400 with `wcflush=1`, steps 2928/2928. The draft figures mixed in HEVC | numbers replaced; SEI-first framing removed |
| C27 "600 frames per content, bitmap or ImageDecoder" | refuted | `play.py`: `jpeg-master-range-bitmap` only, 8 configs × 150 = 1200 draws per browser, 0 mismatches | corrected to 1200 per browser (300 per content), bitmap only |
| C12 "UHD 770 active: false" for C156 | refuted | 0 `"active"` in `chrome156_main.json`; `IPF/c156/caps.json` has no `active` field either. E35/E45 `caps.json` confirm active flags | C156 active adapter marked NOT VERIFIED; IPF caps cited |
| C17 / P5 / table 3.1 (HEVC 4:2:2 string, not played) | refuted | `verify_method_rechecks.json`: E35 error 4, E45 error 3 on the 4:2:2 file, 4:2:0 control plays; E45 accepts `…9D.08` too. `probe.js:30` gives no basis for "4:2:2 10-bit" | C17 rewritten as a measurement; C17a added for probes; table row and P5 updated |
| C18 / P8 / P11 "untagged", "visibly", "correct colour" | refuted / weak | ffprobe: CLI clips are bt709 matrix with unknown primaries and transfer; PyAV 19 is bt709 ×3. DevTools tuples and `madMax` per cell (table in C18): E35 webm reports BT709 and still gives 3.12; AV1 4:4:4 mp4 gives 2.61–2.73 in E45/C156 | C18 rewritten with the table; cause marked inferred; "visibly" dropped; P8 inferred; P11 narrowed |
| §7 "each script logs nvidia-smi" | refuted | `run_pyav19_check.sh` has no nvidia-smi call; `nvidia_smi.log` ends 22:14Z, pyav19 result files are 17:15 local | exception noted in §6 and §7 |
| C21 / P7 flush need | weak | `play.py`: `h264_nvenc` 360/360 fallback flushes on `webcodecs` and `webcodecs-hw`, 0/360 on `webcodecs-sw`; 200 ms criterion at `harness.mjs:153,273` | scoped to the hardware decoder; VUI remedy marked inferred |
| C14 / P3 HEVC software decoder | weak | no `*swdecode*` output exists | scoped to WebCodecs; `<video>` NOT VERIFIED |
| C5, C6, C13, C15, C19, C20, C35, table MSE/WebCodecs cells | weak | 12 `pyav19` keys, all `play\|` | labelled background (CLI fixture); PyAV 19 marked `<video>` only |
| C9, C11, C13, C16, C25, C28, C29–C31 | weak | code lines checked (`common.js:22,39-41`; `harness.mjs:585,591-592`; `make_big_clips.py:45`) | inferred / scope labels added |
| §3.2 G7 column, P4 | weak | `results/licensing/FINDINGS.md:22,25,28,29,33,45,47-48`; `NOTES_sources_nvidia_intel.md:32` | licensing cited per row; P4 limited to RTX 3000 |
| §3.3 mjpeg_qsv row | weak | `clips_summary.json`: `jpeg_seq` 30,645,221 B / 600 = 51,075; MKV 30,672,371 B / 600 = 51,121 (1080p: 206,938 / 206,983) | basis column and Y-only caveat added |
| §5 bench queue | weak | `bench_queue_2300.json`: 23 items, IP-SEEK/SYNC ×2 and IP-SUM present, IP-SCRUB absent | table updated |
| versions, header, first attempt, C34 | weak | `version.Browser` and `uaData.fullVersionList` hold 156.0.8078.80; `HANDOFF.md:62`; `CC/NOTES.md:105`; first-attempt E45 0/113 and E35 71/113 tasks with callbacks; HLS `""` (E35) vs `"maybe"` (E45) confirmed | citations fixed; C34 marked not exhaustive |

Recomputed and unchanged:
- C1–C4;
- C5–C7 counts;
- C8 (4800/4800, 5856/5856);
- C10 (228/2400; CFR 2400/2400);
- C11 counts;
- C22 lines;
- C25/C26;
- C28 counts;
- table 3.3 H.264/HEVC rows;
- table 3.2 line citations.

No web sources are cited, so no URLs were re-fetched. No PyAV 18 result is used.
