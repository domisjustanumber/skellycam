# Licensing: methodology verification

Verifier: adversarial methodology pass, 2026-11-09, machine Gerald. No timed work was run.

Target: `results/licensing/FINDINGS.md`. **That file did not exist when this check ran.** `BENCH.md` and `bench/` don't exist either, which is consistent with NOTES section 6 ("No timing measurements"). So this pass checks `NOTES.md`, `browser_codec_table.md`, the probe JSONs and `scripts/licensing/*`. If FINDINGS.md is later merged from NOTES.md, the corrections below apply to it as well.

## New evidence written by this pass

| File | What it is |
|---|---|
| `scripts/licensing/verify_msmf_fourcc_check.py` | Functional check of cv2.VideoWriter(CAP_MSMF) with FOURCCs that OpenCV maps explicitly, plus unmapped ones. Writes 10 synthetic frames per clip and checks each clip with ffprobe. |
| `results/licensing/verify_method_msmf_fourcc_4.12.0.json` | Result: skellycam venv, opencv-contrib-python 4.12.0.88 |
| `results/licensing/verify_method_msmf_fourcc_5.0.0.93.json` | Result: opencv-python 5.0.0.93 (uv, offline from the topic's uv cache) |
| `results/licensing/verify_method_nvsmi.txt` | nvidia-smi before/after: `0, 8 %` / `0, 7 %`. An earlier ad-hoc run of the same check saw `1, 23 %` before start, which is background NVENC use. That doesn't matter here because the check is untimed. |

Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/licensing/verify_method*/` (synthetic gray clips only).

## Refuted

### R1. "CAP_MSMF ignores the FOURCC and always writes **H.264**" (NOTES section 2, OpenCV wheels)

- code: OpenCV 4.12.0 `modules/videoio/src/cap_msmf.cpp:2496-2553` (`CvVideoWriter_MSMF::FourCC2GUID`; fetched with `gh api repos/opencv/opencv/contents/modules/videoio/src/cap_msmf.cpp?ref=4.12.0`). It maps `'H','E','V','C'` to `MFVideoFormat_HEVC` (lines 2523-2524), `'H','2','6','5'` to `MFVideoFormat_H265` (2521-2522), and also MJPG, MP4V, WMV1/2/3, WVC1, DV and others. Only the `default:` branch returns `MFVideoFormat_H264` (lines 2550-2551).
- measured: `verify_method_msmf_fourcc_4.12.0.json` and `verify_method_msmf_fourcc_5.0.0.93.json`:

| FOURCC / ext | 4.12.0 | 5.0.0.93 |
|---|---|---|
| `HEVC` .mp4 | opens, **hevc** | opens, **hevc** |
| `WMV3` .wmv | opens, **wmv3** | opens, **wmv3** |
| `H265` .mp4 | opens, file unreadable (no moov) | same |
| `MP4V` .mp4, `MJPG` .mp4 | does not open | does not open |
| `hev1`, `avc1`, `av01`, `mp4v` .mp4 | opens, h264 | opens, h264 |

- Why the original probe got it wrong: `probe_opencv_build.py` tried MSMF only with FOURCCs that OpenCV doesn't map (`hev1`, `av01`, lowercase `mp4v`, `avc1`). It tried `HEVC` only with `.mkv`, which MSMF doesn't open. So every FOURCC that "worked" fell through to the H.264 default.
- Correction: "CAP_MSMF maps a fixed FOURCC list (cap_msmf.cpp:2496-2553). Any FOURCC not on the list, including `avc1`, `hev1`, `av01` and lowercase `mp4v`, falls back to H.264. `HEVC` writes HEVC and `WMV3` writes VC-1/WMV3 (measured). None of the codecs that open through MSMF here is royalty-free. skellycam's default `X264` (code: `skellycam/core/camera/config/camera_config.py:29`) is unmapped and so ends up as H.264." The downstream conclusion, that the current cv2→MSMF path produces a patent-pool codec, still holds. The "ignores the FOURCC" mechanism does not.

## Weak (keep, but fix the wording or scope)

| # | Claim | Problem | Fix |
|---|---|---|---|
| W1 | Table, SVT-AV1: "libsvtav1 (AV1 encode, BSD-3-Clause-Clear + AOM patent licence, Q42)" | Q42 is only the BSD-3-Clause-Clear header. The same fetched file (svtav1_license, gitlab master LICENSE.md) says "NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE." The cited source doesn't support the AOM-patent part. It was also read from `master`, not the SVT-AV1 version in the wheel. | Cite the AOM grant via Q01 + Q58 ("Implementation means any implementation"), or fetch SVT-AV1 PATENTS.md at the tag the wheel bundles. Add the quoted BSD-Clear patent disclaimer. Apply the same pinning caveat to libvpx (read from `main`). |
| W2 | "H.264, HEVC and AAC play in Electron. That matches the `proprietary_codecs = true` build flag" | Alternative explanation for HEVC: Chromium has no software HEVC decoder here. In all three runtimes WebCodecs `hevc/prefer-software` returns false while `prefer-hardware` returns true (measured: the three probe JSONs). So HEVC playback relies on the RTX 3070's hardware decoder (and possibly the installed HEVCVideoExtension), not just the build flag. This is a one-machine result. | Say HEVC playback is hardware-dependent (inferred from the WebCodecs result) and NOT VERIFIED on machines without HEVC hardware decode. Attribute only H.264/AAC to `proprietary_codecs`. |
| W3 | Section 4 table: "WebCodecs encode avc1 / hvc1 / av01 / vp09 ... true" | `probe.html` calls only `VideoEncoder.isConfigSupported`. No frame was encoded. | Rename the row "WebCodecs VideoEncoder.isConfigSupported (1280x720)". Don't read it as working encode. |
| W4 | "plays + decodes" (section 4, browser_codec_table.md) | The decode proof is `canvas_nonblack_fraction > 0.5` after a seek, not a comparison with reference pixels. Mitigating: the canvas mean RGB sums agree across runtimes (for example h264 373.49 in Electron 35, Electron 45 and Chrome), which is good cross-check evidence. Images (`<img>` JPEG/JXL/AVIF) were checked only by `onload` + `naturalWidth`, with no pixel check. | Describe the criterion exactly ("non-black canvas after seek; mean RGB matches across runtimes"). Say image decode was not pixel-verified. |
| W5 | Browser support is stated per codec (AV1, VP9 "plays + decodes") and feeds G4/G8 conclusions in section 3 | The samples are 320x240, 2 s, yuv420p 8-bit, default GOP from the ffmpeg 9.0.2 CLI, not PyAV. Nothing tested all-intra streams, 4:2:2 (the cameras' native sampling; AV1 Professional / VP9 profile 1), 1080p, or bitstreams from PyAV's own encoder builds. | Scope the claim to "4:2:0 8-bit, small GOP clips from ffmpeg CLI". Point to the chromium_codecs / chromium_sync_scrub topics for all-intra, 4:2:2 and PyAV-produced files. |
| W6 | Table, JPEG: "So G1 passthrough stores only the Annex-L-free process" | Measured only for the 7 corpus sets from 3 camera models (C922, C930e, one generic). This is not a property of G1 in general. Also, T.81 Annex L reflects 1992 knowledge (Q18 "at the time of publication"). | Write "for the cameras in the corpus". Suggest that the recorder checks each stream's SOF marker (SOF0/SOF1, no DAC) at runtime if this matters. |
| W7 | OpenCV 4.12 vs 5.0 comparison | The two sides are different packages: opencv-contrib-python 4.12.0.88 (venv) vs opencv-python 5.0.0.93. The videoio FFmpeg DLL is probably identical between contrib and main builds, but nothing checked that. | State the package names in the comparison, or repeat with opencv-contrib-python 5.0.0.93. |
| W8 | "H.264 through CAP_FFMPEG does not work out of the box ... This matches Cisco's 'separately downloaded' condition (Q36)" | The DLL-load failure is measured. The link to Cisco's licence condition is an interpretation labelled [measured]. In 4.12 the log also shows "[libopenh264] Incorrect library version loaded", so something was loaded. The cause isn't fully pinned down. | Relabel the Cisco link [inferred]. Quote both stderr lines. |
| W9 | Q25 shown as a quote: "licensed under ... GNU GPL version 2 or later" | Not verbatim. The source reads "is licensed under [GNU General Public License (GNU GPL) version 2](gplv2.txt) or later." NOTES drops ")" and the link inside its quotation marks. The other "..." splices (Q12, Q28, Q29, Q31, Q33, Q39, Q47) check out, apart from markdown or comment-asterisk noise. | Quote the exact text, or paraphrase without quotation marks. |
| W10 | "Sisvel ... rates EUR 0.32 / 0.24 per display device" | The source (quote_verification_supplement S1) gives a "Standard Rate" of EUR 0.32 and a "Compliant Rate" of EUR 0.24, which are two tiers. Written as "0.32 / 0.24", a reader could take them as two device classes. The same applies to VP9 (0.24 / 0.18, Q08). | Write "standard EUR 0.32, compliant EUR 0.24 per consumer display device". |
| W11 | JPEG XL in the "royalty-free statements" group (section 3), Q21 | Q21 ("royalty-free JPEG XL reference implementation") describes the Part 4 software, not a patent licence for the format. The patent evidence is only Google's libjxl grant (Q22), which is limited to Google's implementation. | Say so. Don't present JPEG XL as having a format-level royalty-free statement. |

## Checked and holding

- measured: 59/59 quotes found verbatim (`quote_verification.json`). All 36 cited sources returned HTTP 200 (`source_fetch_log.json`). Spot checks (Q01-Q05, Q16-Q20, Q35-Q38, Q44-Q49, Q55, Q59) match the cached page text. The T.81 Annex L reading, arithmetic-coding patents plus one hierarchical-lossless patent (US 4,665,436), is accurate (cached itu_t81_pdf.txt).
- measured: the JPEG audit counts 1,862 frames (891+893+19+19+19+10+11), all SOF0, with DHT and with no DAC (`jpeg_process_audit.json`). It agrees with corpus `index.json`. The marker walker stops at SOS, which is correct for SOF/DAC/DHT detection.
- measured: the IETF IPR query has a working positive control. Opus RFC 6716 returns 5 disclosures and the draft returns 11, so the zero counts for FFV1, Matroska and FLAC are not an API-name mismatch (`ietf_ipr_disclosures.json`).
- measured: PyAV 18.0.0 and 19.0.2 report all 7 libraries as "LGPL version 3 or later" and bundle libx264-165 and libx265 DLLs. The only licence files are PyAV's own. Removing the x264/x265 DLLs breaks `import av` (`probe_pyav_*.json`, `pyav_strip_gpl_*.json`). The pyav-ffmpeg patch excerpt moves libx264/libx265 into `EXTERNAL_LIBRARY_VERSION3_LIST`. The hunk header in `pyav_build_evidence.json` names NONFREE_LIST because git uses the preceding line as the hunk label, but the excerpt shows VERSION3, and NOTES reads it correctly. The unpatched configure would `die_license_disabled gpl`, so the shipped binary (libx264 enabled, no `--enable-gpl`) is itself evidence that the patch was applied.
- measured: Electron 35.7.5 vs 45.2.3 differences. A full diff of the two probe JSONs, excluding timing and pixel-mean fields, finds only: JXL `<img>`/ImageDecoder, `canPlayType` for `video/x-matroska` (both av01 and avc1), the error-message prefix `PipelineStatus::`, and mp3 duration 2.04 vs 2. So the "only differences" claim holds.
- measured: none of MJPEG (mkv/mp4/avi), FFV1, ProRes or UT Video plays in any of the three runtimes. These are demuxer errors, so the result doesn't depend on the clip encoder.
- No timed numbers exist in this topic, so no repro requests are needed.

## Verdict

The licensing notes are mostly sound. Quotes are verified mechanically and the functional probes are reproducible. There is one refuted mechanism claim (R1, MSMF "always H.264"). Its codec-pool conclusion survives, but the stated mechanism is wrong and the probe design hid it. Eleven wording or scope fixes are listed above (W1-W11). The most important are W1 (SVT-AV1 patent claim not supported by its citation), W2 (HEVC playback depends on hardware, not just the build flag) and W5 (browser results only cover 4:2:0 8-bit small-GOP CLI clips). FINDINGS.md did not exist at verification time.
