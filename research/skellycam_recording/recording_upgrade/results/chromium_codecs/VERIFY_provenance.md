# chromium_codecs: provenance verification of the draft FINDINGS (2026-11-09)

Lens: does each cited file, line or key exist and say exactly what the draft says? No timing numbers were taken.
No earlier `VERIFY_provenance.md` existed, so nothing was renamed.

My recount scripts (read-only, they parse the raw JSON directly and do not use `summarize.py` or the drafter's scripts):
`C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_codecs/verify_prov/`
(`ipagg.py`, `ipenc.py`, `ipplay.py`, `cc.py`, `tags.py`).

Paths: `CC` = `results/chromium_codecs/`, `IP` = `results/intra_playback/`, `IPF` = `IP/functional/<e35|e45|c156>/`.

The draft cites no web sources, so there were no URLs or quotes to re-fetch. No PyAV 18 results are presented as primary.

## 1. Refuted (the evidence says something else)

| claim | what the evidence says | correction |
|---|---|---|
| C23: `decoded_hist = {"1": n}` in "all 184 WebCodecs seek configurations per browser" | `IPF/seek_*.json` holds 192 WebCodecs seek configs per browser. 168 have `decoded_hist` with key `"1"` only. The other 24 (HEVC, path `webcodecs-sw`) failed with `config not supported` and have no `decoded_hist`. This is identical in E35, E45 and C156. | "168 of 192 WebCodecs seek configurations per browser. The other 24 are HEVC `prefer-software`, which is unsupported (C14)." |
| C24: "The same E35 decodes `h264_nvenc` and `h264_qsv` intra exactly through WebCodecs: 1440/1440 without forced flush, 4800/4800 with it" | 1440 and 4800 are totals for **all four encoders** (path `webcodecs`). For H.264 only, E35 gives: path `webcodecs` 720/720; `webcodecs` + `-hw` + `-sw` 2160/2160; `wcflush=1` 2400/2400. | Use the H.264-only numbers, or say "all four encoders". |
| C27: master-clock playback "0 pattern mismatches in 600 frames per content per browser" | `IPF/play_*.json`, path `jpeg-master-range-bitmap`: 2 clips (`jpeg_seq`, `jpeg_in_mkv`) × 150 draws = **300 draws per content per browser**, 1200 per browser. Only the `createImageBitmap` path was played. No ImageDecoder master-clock run exists. | "0 mismatches in 300 draws per content per browser (1200 in total), `createImageBitmap` path only." |
| C12 for C156: the UHD 770 is `active: false`, cited to `chrome156_main.json` `systemInfoBefore.gpu.devices` | That array has no `active` field (0 occurrences of `"active"` in the file). It lists the RTX 3070, the UHD 770, the RTX 3070 again and the Basic Render Driver. `active` exists only in the E35/E45 `gpuInfoComplete.gpuDevice` and in the IPF `gpu_info`. | For C156, say "both GPUs listed; active adapter not recorded". NOT VERIFIED for C156. |
| P11: Electron 45 gives "correct colour on untagged AV1" | E45/C156 `play\|av1_high8_444__mp4` (DevTools matrix `UNSPECIFIED`) has MAD 2.61/2.73, against 0.5 for the `__webm` copy (`BT709`). So E45/C156 also render untagged AV1 differently, at least for 4:4:4 (dav1d). | Drop that benefit, or limit it to "AV1 Main 4:2:0 untagged mp4: MAD 0.9 in E45/C156 vs 3.12 in E35". |
| §7: "each script ... logs nvidia-smi to `raw/nvidia_smi.log`" | `scripts/chromium_codecs/run_pyav19_check.sh` has no `gpu()` and no nvidia-smi call. The other run scripts do log it. | "except `run_pyav19_check.sh`". Also see the nvidia-smi gap in section 2. |

## 2. Weak (true in part, mislabelled, or the scope is wider than the evidence)

| claim | why | fix |
|---|---|---|
| C18 (and P8): E35 renders AV1 "with an unspecified colour matrix" differently | The data does not support the tag as the cause. **E35** `play\|av1_main8_intra__webm` reports `BT709` in DevTools and still has MAD 3.12. E35 `mse\|av1_main8_intra__fmp4` (BT709) has 0.9. The PyAV 19 clip also differs in encoder build, not only in its tags (`CC/raw/electron35_main.json`; `tags.py`). | Keep the numbers. Label the tag explanation **inferred**, and note the counter-example. P8 (write BT.709 tags) is still sensible, but as inferred. |
| C21 / P7: WebCodecs "needs a `flush()` after each chunk for `h264_nvenc`" | Only the **hardware** paths needed it. `webcodecs` and `webcodecs-hw` each had 360 flushes per browser. `webcodecs-sw` (FFmpegVideoDecoder) had 0 flushes for `h264_nvenc` and was 360/360 exact. The "needed" count comes from a 200 ms timer (`scripts/chromium_sync_scrub/harness/harness.mjs:150-151`, `flushAfterMs` default 200) on a shared machine. | Say "with the D3D11 hardware decoder, no output within the harness's 200 ms window unless flushed". P7 applies to hardware decode only. |
| C14: "HEVC has no software decoder in any of the three browsers" | Measured only through WebCodecs `prefer-software` (and the probe). `<video>` software fallback was never run: `run_swdecode.sh` exists but there is no `*_swdecode.json`. | Say "WebCodecs reports no software HEVC decoder". The `<video>` fallback is NOT VERIFIED. |
| C5, C6, C13, C15, C19, C20, C35; table 3.1 MSE/WebCodecs cells for "AV1/VP9 intra (CLI and PyAV 19)" | These cells rest on **ffmpeg-CLI fixtures** whose source frames were decoded with OpenCV from the skellycam venv. The study rule allows the CLI for inspection only. The PyAV 19 clips were run only as `play\|pyav19_*` (`<video src>`). No MSE or WebCodecs task uses them (12 `pyav19` keys, all `play\|`). | Label these as CLI-fixture results (background). In table 3.1, say PyAV 19 covers `<video>` only. |
| C9: "the errors ... do not occur with all-intra, no-B files in the same containers" | Not a controlled A/B. The GOP clips (CC: 720p, 60 frames, 10 fixed targets, `(k+0.5)/fps`) and the intra clips (IP: other encoders and content, 100 random `mid` seeks) differ in several ways. The HEVC GOP error was in mp4/mov, and no intra mov was tested. | Keep both measurements. Label the causal link **inferred**. |
| C24 context "libx264 Annex B with an SEI-first access unit" | `h264_nvenc` access units also start with SEI (`IP/clips_summary.json`, `nal_check.first_frame_nal = [6, 6, 5]`), and E35 decodes those. The visible difference is Annex B elementary stream (CC) vs MP4/avcC chunks (IP), which the E35 error text hints at. | Keep "root cause NOT VERIFIED". Do not suggest SEI-first as the cause. |
| §5: "`results/BENCH_QUEUE_2300.md` did not exist" | `results/bench_queue_2300.json` (19:06) exists and contains IP-SEEK-E35/E45, IP-SYNC-E35/E45 and IP-SUM. IP-SCRUB is **not** in it. | Cite the JSON and mark IP-SCRUB as not queued. |
| Table 3.3, mjpeg_qsv bytes/frame 51,075 / 206,938 | These come from `jpeg_seq` (concatenated JPEG, no container). The H.264/HEVC rows come from non-fragmented MP4. `mjpeg_qsv422.mkv` gives 51,121 / 206,983. PSNR/SSIM match. | Footnote the basis (row source `c*/jpeg_seq`). |
| Versions: C156 "recorded in the C156 user agent" | The `ua` string says `Chrome/156.0.0.0` (reduced UA). `156.0.8078.80` is in `uaData.fullVersionList` and in the result keys (`chrome156.0.8078.80\|...`). | Cite `uaData.fullVersionList`. |
| §7: "Without them the first attempt timed out" | `CC/raw/first_attempt/electron45_main.json`: 0 rVFC callbacks in all 113 play tasks (`electron_main.js:35-36` comment says the same). E35's first attempt had callbacks in 71 of 113. The "timeout" lines in the E35/E45 stdout are the expected MSE-mkv failures. The C156 first attempt did time out, but C156 does not use `electron_main.js`. | "Without them E45's first run got 0 rVFC callbacks (`first_attempt/electron45_main.json`)." |
| §6: "nvidia-smi encoder sessions were 0–1 around the CC runs" | `CC/raw/nvidia_smi.log` ends at 22:14Z (E35 rerun). The E45/C156 `--only pyav19` runs (file times 17:15 local) are not logged. | Add "not logged for the pyav19 check runs". |
| C34: list of E35 differences | Not complete. E35 also differs on `application/vnd.apple.mpegurl` (`""` vs `"maybe"`), on Matroska audio probes, and on flac/vorbis `AudioDecoder` configs (needs a description in E35). | Add "not exhaustive", or list them. |
| C28: "decoded with both APIs" | The harness checks only the decoded width/height (`harness.mjs:590-591`), not pixel content. Byte-identity (300/300, 150/150) is the strong check. | Add "(decoded size checked)". |
| Table 3.1, JPEG "software image decode" | Inferred from `jpegDecodeAcceleratorSupported: false`. The decoder in use was not observed. | Mark it inferred. |
| Header machine facts (i7-14700K, driver 610.88) | No citation. The driver is in `CC/NOTES.md:105`, and Chromium reports `32.0.16.1088`. | Cite the source. |

## 3. Verified (recomputed, matches the draft)

| claim | evidence checked |
|---|---|
| C1, C4 | Every MJPEG (422 and camera), FFV1 and rawvideo `play\|` cell is error 4 (`NO_SUPPORTED_STREAMS`) in mp4/fmp4/mkv/mov, and `COULD_NOT_OPEN` in AVI, in all 3 browsers. |
| C2 | `mjpeg_qsv422.mkv` fails with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` in 4 contents × 3 browsers. |
| C3 | No MJPEG string is accepted by `canPlayType`, MSE or MediaCapabilities. WebCodecs is false for all 3 preferences. `video/x-motion-jpeg` returns `""`. |
| C5, C6, C7 | Play 35–37 of 35–37 per clip, seeks 10/10, decoder `D3D11VideoDecoder`, AVI fails. PyAV19 MAD 0.89 (AV1) and 0.9 (VP9). E35 has 217 tasks (205 + 12 `pyav19`). `pyav19_clips_log.json` records `av` 19.0.2 and `g` 1. |
| C8, C10 | Video `mid` seeks 2400 + 2400 = 4800/4800, steps 5856/5856, `cfrmid` VFR 228/2400, CFR 2400/2400, in all 3 browsers. 48 video clips, all-IDR, `has_b_frames` 0, no non-IRAP VCL. |
| C9 numbers | h264 fmp4: 0/34–35 frames index-correct, 2 frames behind, seeks 2/10. HEVC mp4/mov: seeks 7/10, with targets 29/30/31 all landing on frame 33. |
| C11 | rVFC VFR mismatches: E35 25/3549, E45 62/3426, C156 55/3294. CFR 0. `wc-master` and JPEG master 0. |
| C13, C15, C16, C35 | Decoder names, NV12/I420 outputs, `inOrderCorrect` 60, `jpegDecodeAcceleratorSupported` false (also false in C156 `auxAttributes`). "probably" + `powerEfficient` false for AV1 4:4:4/4:2:2 and VP9 p1. |
| C14 numbers | HEVC `prefer-software`: `isConfigSupported` false. `hev1.1.6.L120.90` `config not supported`. H.264 sw 720/720 per browser. |
| C17 | RExt 4:2:2 is "probably" / `powerEfficient` / WC hw supported in E45/C156, and unsupported in E35. `hw_accel_target/NOTES_functional.md:126` says what the draft says. |
| C19, C20 | MSE mkv gives `addSourceBuffer` NotSupportedError. AV1/VP9 intra MSE webm/fmp4: 10/10. |
| C22 | `IP/sps_vui_trace.txt` lines 7, 16, 17 match. |
| C25, C26 | 88 camera JPEGs (group counts match), all OK with 3 APIs, max MAD 0.04, all `I422`. The warnings file has 11 frames. |
| C28 | 300/300 sequential and 150/150 random, byte-identical, SOI/EOI. Status 206 is enforced in code (`harness.mjs:585`). |
| C29–C32 | Serving cells match in all 3 files. The `protocolLog` has no 206 for the `appnf`/`appnfh` schemes. C156 `file://` gives `pixelError` canvas tainted, `seekCompleted` 10, `seekExact` 0. |
| C33 sub-claim | E35 rerun vs the 12:19 run: exactly 1 differing cell, `mse\|av1_pro8_422__fmp4` play flag. |
| C34 core | E45 and C156 probe records are identical in all 6 sections. E35 mkv `""`, no JXL. |
| Table 3.2 citations | `NOTES_functional.md:15, 16, 17, 19-21, 69, 134` and `NOTES_sources_nvidia_intel.md:31` say what the draft says. |
| Table 3.3 (H.264/HEVC rows) | Bytes/frame, PSNR and SSIM match `IP/clips_summary.json` (non-fragmented mp4). |
| Code refs | `harness/electron_main.js:35-40` (switches). `make_pyav19_clips.py` pins `av==19.0.2` and leaves `numpy` unpinned. |

## 4. Verdict

The draft's measurements are sound and nearly all of its numbers recompute exactly. Six statements must be corrected before it is final:
- the C23 count (168 of 192, not 184);
- the C24 H.264 numbers, which are really totals for all four encoders;
- the C27 master-clock frame count (300 per content, bitmap path only);
- the C156 "active" GPU claim in C12;
- the P11 colour benefit;
- the §7 nvidia-smi logging statement.

Several causal readings need an **inferred** label, mainly C18/P8 (colour tags), C9 and C21/P7 (hardware path only). The CLI-fixture results in the MSE and WebCodecs rows should be labelled background, because PyAV 19 clips were only run through `<video src>`.
