# chromium_codecs: methodology verification of the draft FINDINGS (G8)

Verifier: methodology lens (confounders, wrong conclusions). 2026-11-09, ~18:40-19:15 EST, machine Gerald. No timing numbers.
Paths are relative to `research/skellycam_recording/recording_upgrade/`. `CC` = `results/chromium_codecs/`, `IP` = `results/intra_playback/`, `IPF` = `IP/functional/<browser>/`.
No earlier `VERIFY_method.md` existed, so nothing was renamed.

## 0. What I re-checked

| check | how | result file |
|---|---|---|
| raw counts behind C5, C7, C10, C11, C18, C19, C21, C23, C24, C27, C34 | own scripts on `CC/raw/*.json`, `IPF/*.json` | scratchpad; `scripts/chromium_codecs/verify_method/wc_decoded_hist.py` |
| colour tags and key flags of the CLI vs PyAV 19 intra clips | ffprobe 9.0.2 (inspection only) | output quoted in §2 |
| GOP of the serving clips | ffprobe packet flags, `make_big_clips.py:45` | quoted in §3 |
| bit layout of the HEVC 4:2:2 SPS | `ffmpeg -bsf:v trace_headers` on the `hevc_qsv` YUYV file (inspection only) | `CC/raw/verify_method_rechecks.json` |
| HEVC 4:2:2 probes and playback in E35/E45 (new) | small Electron page, `file://`, 4:2:0 `hevc_qsv` control file | `CC/raw/verify_method_rechecks.json`, `scripts/chromium_codecs/verify_method/hevc422/` |
| `fetch(file://)` with `Range` in E35/E45 (new) | small Electron page | `CC/raw/verify_method_rechecks.json`, `scripts/chromium_codecs/verify_method/filefetch/` |

- measured: nvidia-smi after the Electron re-checks: encoder sessions 0, decoder utilisation 0 % (19:10:52 EST).
- The new Electron checks are functional only: one file each, no index-pattern readback, C156 not run.

## 1. Refuted

### R1. C17 / P5 / table 3.1: the probe string is not a 4:2:2 10-bit string, and the real 4:2:2 file does not play

- Draft: `hvc1.4.10.L93.B0` is "HEVC RExt 4:2:2 10-bit"; E45/C156 "claim support that FFmpeg could not get from the same GPU"; the table row says playback "NOT VERIFIED (not played)".
- code: the string is defined with no explanation (`scripts/chromium_codecs/harness/probe.js:30`). The key name `hevc_rext_422_10` is the only basis for "4:2:2 10-bit".
- measured: in the SPS of the real `hevc_qsv` 4:2:2 file, the constraint flags come in the order progressive, interlaced, non_packed, frame_only, max_12bit, max_10bit, max_8bit, max_422chroma, … (`trace_headers` bits 88-100; `CC/raw/verify_method_rechecks.json`).
- inferred (bit layout from that trace; hex encoding per ISO/IEC 14496-15, not re-sourced here): constraint byte `B0` = 1011 0000 sets only progressive, non_packed and frame_only. It sets **no** 10-bit or 4:2:2 constraint. So `hvc1.4.10.L93.B0` says "RExt profile, level 3.1", nothing more. The real file's flags give byte 1 = `9D`, byte 2 = `08`.
- measured (new): E45 returns `canPlayType` "probably" and WebCodecs `prefer-hardware` true for `hvc1.4.10.L93.B0`, `hvc1.4.10.L120.9D` and `hvc1.4.10.L120.9D.08`. E35 returns "" and false for all three.
- measured (new): the 8-bit 4:2:2 `hevc_qsv` MKV (`.../hw_accel_target/functional/hevc_qsv__mjpeg_720p_intra_native422_yuyv422.mkv`):
  - E35: MediaError 4, `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`;
  - E45: MediaError 3, `PIPELINE_ERROR_DECODE`;
  - control (4:2:0 `hevc_qsv` intra MKV, same method): plays in both, 10 rVFC frames, non-zero pixels.
- Correction:
  - C17: E45/C156 accept RExt codec strings, including one with the 4:2:2 10-bit constraint flags (`…9D.08`). The draft's string carries no chroma or bit-depth information.
  - Table 3.1, HEVC 4:2:2 row: measured on this RTX 3070, one 720p MKV: E35 does not open it, E45 opens it then fails to decode. C156 is NOT VERIFIED.
  - P5 then rests on a Chromium measurement, not on the FFmpeg cross-tool comparison.
  - Keep the FFmpeg result (`results/hw_accel_target/NOTES_functional.md:126`) as supporting evidence only. It used different decoders (cuvid, cuda, d3d11va, d3d12va), not Chromium's `D3D11VideoDecoder`.

### R2. C18 / P8 / P11: the CLI AV1 clip is not "untagged", and "visibly" has no evidence

- measured (ffprobe): the CLI clip `clips/av1_main8_intra__mp4.mp4` has `color_space=bt709`, `color_range=tv`, `color_primaries=unknown`, `color_transfer=unknown`. The PyAV 19 clip has bt709 for all three.
- measured: the CLI VP9 intra clip has the same partial tags. DevTools reports it as `BT709`, and E35 gives it MAD 0.9 (`CC/raw/electron35_main.json`, `play|vp9_p0_intra__mp4`).
- measured: DevTools reports `matrix UNSPECIFIED` for the CLI AV1 clip in **E45 as well** (`CC/raw/electron45_main.json`, `kVideoTracks`). Only E35 renders it with the larger MAD: 3.12 vs 0.9.
- measured: MAD is a luma-only grid statistic (`scripts/chromium_codecs/harness/common.js:22,39-56`). No image was looked at, so "visibly" is unsupported.
- Correction:
  - C18/P8: "an AV1 clip tagged only with the matrix (primaries and transfer unspecified), which Chromium reports as `matrix UNSPECIFIED`, gives grid MAD 3.12 in E35 and 0.9 in E45/C156. A fully BT.709-tagged PyAV 19 clip gives 0.89 in all three."
  - P8: write all three BT.709 tags (primaries, transfer, matrix). inferred.
  - P11: "lower content MAD on partially tagged AV1", not "correct colour on untagged AV1".

### R3. C24: the "with forced flush" count includes HEVC

- measured (`IPF/e35/seek_*.json`, my tally):
  - E35 H.264 only (`h264_nvenc` + `h264_qsv`), `wcflush=1`: **2400/2400**. The 4800 in the draft is all four encoders.
  - Without a forced flush: `no-preference` 720/720 and `prefer-hardware` 720/720, which gives the draft's 1440. `prefer-software` adds 720/720.
- Correction: "E35 decodes `h264_nvenc` and `h264_qsv` intra exactly through WebCodecs: 1440/1440 without forced flush (`no-preference` + `prefer-hardware`), 2400/2400 with `wcflush=1`."

### R4. C23: the count is wrong, and "decoded exactly one chunk" follows from how the harness is built

- measured: per browser there are **168** WebCodecs seek configurations with a `decoded_hist`, all `{"1": n}`. The draft's 184 adds the 16 JPEG configurations, which are not WebCodecs. The 24 HEVC `prefer-software` configurations have no histogram.
- code: `decoded = k - start + 1`, where `start = keyFor(k)` comes from the clip's keyframe list in the index (`scripts/chromium_sync_scrub/harness/harness.mjs:124,137-160`). When every index entry is a keyframe, `decoded` is 1 by construction.
- Correction:
  - Drop C23 as a finding.
  - The evidence that each intra frame decodes on its own is this: after `reset()` + `configure()`, the decoder was fed only chunk k, and the output carried pattern k, exact in every seek (C8, C21).

### R5. C27: the playback count is wrong

- measured: JPEG master-clock playback = **1200 draws per browser** over 8 clip configurations (4 contents × `.mjpeg` / JPEG-in-MKV, 150 draws each), with 0 mismatches. The path is `jpeg-master-range-bitmap` only (`IPF/play_*.json`, `per_stream.draws`).
- Correction: "0 pattern mismatches in 1200 draws per browser (createImageBitmap only; ImageDecoder was not used for playback)". Not "600 frames per content".

## 2. Weak (needs scoping or a label)

| # | claim | problem | fix |
|---|---|---|---|
| W1 | C9: the libx264/libx265 errors "do not occur" with all-intra no-B files | Confounded. The CC and IP fixtures differ in encoder, resolution, harness, time base (1/90000 vs CLI), playback check (`round(mediaTime*30)` vs nearest pts) and seek targets. B-frames and open GOP were never isolated (no libx264 `bf=0` / closed-GOP clip). The fair comparator is the IP `cfrmid` CFR seeks on fmp4: 200/200 per encoder. | "Not observed in the IP intra clips (`cfrmid` CFR fmp4 200/200 per encoder). Cause of the GOP errors not isolated (background)." |
| W2 | C11: master-clock paths "show none" vs rVFC | Not like for like. Master-clock paths read the pattern from the frame they themselves drew, so they cannot show a readback race. The browsers also ran at the same time (IP NOTES §4.3). | State that the two numbers measure different things. Keep the inferred label. |
| W3 | C13: "only 4:2:0 streams get a hardware decoder" | Too general. No HEVC 4:2:2 or 4:4:4 and no H.264 4:4:4 was played in CC. Whether the limit is the GPU or Chromium is not separated. | "Of the streams played, only the 4:2:0 ones got `D3D11VideoDecoder` on this RTX 3070." Add R1's HEVC 4:2:2 result (decode error, E45). |
| W4 | C14 / P3: "HEVC has no software decoder in any of the three browsers" | Evidence is WebCodecs `prefer-software` only. `<video>` with no HEVC hardware was not tested. P3's "plays here only because the RTX 3070 decodes it" is counterfactual and not marked. | "WebCodecs `prefer-software` rejects HEVC in all three." Mark the `<video>` consequence and P3's sentence as inferred, NOT VERIFIED. |
| W5 | C21 / P7: `h264_nvenc` "needs" `flush()` | The flush need was seen only with `D3D11VideoDecoder`; `prefer-software` (FFmpegVideoDecoder) needed 0/360 (`IPF/seek_*.json`). The criterion is "no output within 200 ms", then a fallback flush (`harness.mjs:153,273`). That is a timeout on a shared machine; inferred: the 360/360 vs 0/360 split makes load unlikely to explain it. P7's alternative remedy (a VUI reorder bound) is untested and not marked. | Scope C21 to "the hardware decoder on this NVIDIA GPU". Name the 200 ms criterion. Mark the VUI remedy in P7 inferred, NOT VERIFIED. Intel/AMD decoders were not tested. |
| W6 | C16 + table 3.1 "software image decode; no JPEG accelerator" | `jpegDecodeAcceleratorSupported` is a GPU-info flag. Its link to `ImageDecoder` / `createImageBitmap` is not shown by any source or measurement here. | Mark "software image decode" inferred, NOT VERIFIED. Cite C16 only for the flag's value. |
| W7 | C25: the JPEGs "decode correctly" | The check is a 16×9 grid of luma cell means against OpenCV (`img.js:2,11`; `common.js:22`). Chroma and fine detail are not checked. | "decode, with grid luma MAD ≤ 0.04 against OpenCV". |
| W8 | §3.3: "quality matched to about Y-PSNR 55 dB" | PSNR/SSIM are on Y only. `mjpeg_qsv` gets YUYV full range and writes 4:2:2, while H.264/HEVC get NV12 limited range and write 4:2:0 (IP NOTES §2). JPEG's extra chroma is not credited. | Add: "Y only; chroma format and input differ (4:2:2 vs 4:2:0)". The existing pointer to `results/intra_compare/` stays. |
| W9 | Table 3.2, column "royalty-free (G7)" | No citation. `results/hw_accel_target/NOTES_functional.md` §5 does not cite licensing either. | Cite `results/licensing/FINDINGS.md` (or its evidence files) for each yes/no. |
| W10 | P4: "no royalty-free `<video>` format meets the hardware target on NVIDIA" | Too broad. The source notes say AV1 NVENC starts at Ada (`results/hw_accel_target/NOTES_sources_nvidia_intel.md:32`). The target fails because RTX 3000 lacks it. Whether all-intra AV1 works on Ada NVENC is NOT VERIFIED. | "…on RTX 3000 (Ampere), so not across the RTX 3000+ target." |
| W11 | C29–C31 / P10: serving conclusions applied to intra recordings | 9 of the 10 serving clips are GOP. The big VP9-lossless clips are GOP 30 (`make_big_clips.py:45`; ffprobe: 55 key packets in 600). Only `av1_main8_intra__mp4` is intra. inferred: Range behaviour is codec-independent. | Label the serving evidence as mostly GOP, with codec independence inferred. |
| W12 | P1/P2 + P10: the JPEG image path is recommended alongside "serve from `file://`" | Every IP JPEG test was served over local HTTP with Range (`scripts/chromium_sync_scrub/harness/main.cjs:142`, `server.cjs:55`). measured (new): in E35 and E45, `fetch(file://…, {Range: bytes=10-19})` returns the correct 10 bytes but with **status 200 and no `Content-Range`** (`CC/raw/verify_method_rechecks.json`). | State that the JPEG path was tested only over HTTP. Under `file://` the bytes are right, but code must not require 206 / `Content-Range`. The full harness over `file://` / `protocol.handle` is NOT VERIFIED. |
| W13 | C12: "all hardware decode below ran on the RTX 3070" | The IP evidence for this is borrowed from CC. `IPF/*/caps.json` itself records the RTX 3070 `active: true` and the UHD 770 `active: false`. "Active GPU = decoder adapter" is inferred. | Cite `IPF/*/caps.json`. Mark the adapter link inferred. |
| W14 | C8 / table 3.1: QSV-encoded files "play" | They were decoded on NVIDIA only. Playback of the same files on Intel/AMD/Apple decoders is unknown (draft §6 says so). | Repeat "decoded on RTX 3070" in the table cells for the `*_qsv` rows. |

## 3. Checked and holding

- measured: C5, C6 and C7 rest on decoded-pixel checks: the index pattern in every rVFC frame plus 10 paused seeks. Counts 35–37 of 35–37 and 10/10; MAD 3.12 (E35 CLI AV1), 0.9 and 0.89 (my dump of the three main files plus the PyAV 19 files).
- measured: the CLI and PyAV 19 AV1/VP9 intra clips are all-key: ffprobe shows 60/60 `K` packets, and VP9 decodes 60 frames, all `I`.
- measured: C8, C10 and C21 counts agree with `IPF/seek_*.json` and `step_*.json`: `mid` 1200 per encoder per browser; `cfrmid` VFR 57/600 per encoder, giving 228/2400; `h264_nvenc` fallback flush 360/360, the other encoders 0.
- measured: C11 counts match `IP/NOTES.md` §4.3. The 25 + 62 + 55 = 142 mismatches equal the 142 recorded examples.
- measured: C19: every `mse|*__mkv` cell in all three files has `setupError` NotSupportedError (21 per browser). The intra mkv cells show `timeout` as `ready`, but the setup error is the same.
- measured: C34: E45 and C156 probe records are identical in all six sections (`containersBare`, `video`, `audio`, `audioWebCodecs`, `webcodecs`, `imageDecoder`).
- measured: C22: `IP/sps_vui_trace.txt` lines 7, 16 and 17 say what the draft says. The trace covers the `c720p30` clips only.
- measured: table 3.2 line citations `NOTES_functional.md:15,16,17,19-21,69,126` and `NOTES_sources_nvidia_intel.md:31` point at the stated content.
- Not found: no Jellyfin-derived or Linux-only claim is used for Windows behaviour in this draft. Per-generation statements are deferred to `hw_accel_target`, apart from W10.
