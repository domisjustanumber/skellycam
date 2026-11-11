# uncompressed_intra: provenance check of the revised draft FINDINGS (after the quiet bench)

Verifier: adversarial provenance pass, 2026-11-10, machine Gerald. No timed measurements were run. The draft checked is the post-run revision (built on run `20261109T230007`, items 35/56/57). The previous pass is now `VERIFY_provenance.prev.md`.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/` unless they start with `results/` (= `research/skellycam_recording/recording_upgrade/results/`) or `scripts/`.

## What was checked

- **All 36 `bench/*_q2300.json` files**, read by script: median, min and max for encode fps, cores/stream, bytes/frame, p99, `latency_max` and decode fps; `prep_ms_per_frame`; packets and decode frames per rep; `env` fields; `nvidia_smi_before/after`; `encode_cpu_s` / 15.625 ms per rep; `latency_max` / `encode_wall_s` per rep.
- **The old rows**: `bench/*__pyav18.0.0.json` and the untagged `*__pyav19.0.2.json`, compared with tonight's rows for every §2.7 correction.
- **The run record**: `results/BENCH_RUN_2300_LOG.jsonl` items 35, 56, 57 and 58, and `results/BENCH_RUN_2300_SUMMARY.md` §3 and §4.
- **Functional evidence**:
  - `functional_matrix_pyav19.0.2.json`: all 555 rows, including `trunc50_*` for every source;
  - `functional_tables.md`;
  - `qsv_recheck_pyav19.0.2.json`, `ffv1_recheck_pyav19.0.2.json`, `loose_ends_check.json`;
  - `pyav_caps_{18.0.0,19.0.2}.json`, `pyav_mux_acceptance_19.0.2.json`, `ffv1_v4_cross_version_pyav{18.0.0,19.0.2}.json`;
  - `bayer_debayer_check_pyav19.0.2.json`, `python_jpeg_libs_{uv,venv}.json`;
  - `chromium_check_electron{35,45}.json`, `verify_method/chromium_benched_configs_electron{35,45}.json`;
  - the corpus `index.json` in the media folder.
- **Code**:
  - `scripts/uncompressed_intra/bench_intra.py:95-200`;
  - `functional_matrix.py:80-90` and `:400-412`;
  - `uintra_frames.py` docstring;
  - `bench_suite.py` and `bench_runner/run_queue.py` argument lists;
  - PyAV 19.0.2 wheel in the uv cache: `av/container/output.py:160-173`, `av/codec/context.py:680-712`, `output.py:592-612`.
- **Sources fetched again on 2026-11-10** (into the step2 scratchpad):
  - `https://www.rfc-editor.org/rfc/rfc9043.txt`;
  - from `https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/`: `libavformat/matroskaenc.c`, `libavcodec/nvenc.c`, `libavcodec/nvenc.h`, `libavcodec/nvenc_hevc.c`, `libavcodec/ffv1enc.c`, `libavcodec/mjpegenc_common.c` and `libavcodec/options_table.h`.

## Summary

- **Numbers.** About 260 numeric claims in §2.7, §3.1, §3.2, §3.3, §4 and §5 match the JSON after rounding. No number was found that was taken from BENCH.md or from memory against the JSON. Every source quote matches its primary text.
- **Refuted: 2.**
  - The truncation bullet names 2 silent-corruption cases. The JSON it cites has 18.
  - The draft lists `yuv444p12msble` into NVENC as NOT VERIFIED, but the FFmpeg source already answers it.
- **Weak: 12.** Mostly secondary citations, labels that overstate the evidence, and a version confound in the "not lower bounds" correction.

## Refuted

| # | draft claim | what the evidence says | correction |
|---|---|---|---|
| R1 | §2.4: "MKV, NUT and AVI kept 1-2 frames for nearly all configs, and every complete frame was exact ... `ffvhuff_median.nut` and `jpegls.nut` on bayer_rggb16le returned 2 frames, of which only 1 was exact. The cut frame came back silently corrupted." Also "`rawvideo.avi` with bayer_rggb16le kept 0." | measured, `functional_matrix_pyav19.0.2.json` `trunc50_*`, all 15 sources. The draft's examples come from the `functional_tables.md` truncation table, which covers only the yuyv422 and bayer_rggb16le sources. Across all sources:<br>- **18 of 275** exact lossless MKV/NUT/AVI cases returned more frames than were exact.<br>- `jpegls.nut` returned **3** frames with 2 exact on gray, gray16le, rgb24, bgr24, bayer_rggb8, bayer8_quad and bayer16_quad.<br>- `ffvhuff_median.nut` returned 2 with 1 exact on bayer_rggb8, bayer_rggb16le, raw12_packed and raw10_packed.<br>- `magicyuv_median.avi` returned 2 with 1 exact on bayer_rggb8, raw12_packed and raw10_packed.<br>- **`ffv1_l3_s4_crc_g1.avi` on raw12_packed** returned 2 with 1 exact.<br>- `rawvideo.avi` also kept 0 on bayer_rggb8.<br>- **No MKV case** returned a corrupted frame. | "After a 50% cut, MKV/NUT/AVI returned 1-3 frames. In 18 of 275 exact lossless cases, all in NUT or AVI and including FFV1 in AVI, the cut frame came back silently corrupted (jpegls, ffvhuff, magicyuv, FFV1-in-AVI). No MKV case did this. `rawvideo.avi` kept 0 frames on both Bayer sources." This strengthens §4.8: use MKV, and validate the last frame. |
| R2 | §2.5 "A `yuv444p12msble` request was not tested (NOT VERIFIED)"; §3.4 "NVENC 12-bit pix_fmts listed but untested"; §6 "`yuv444p12msble` into hevc_nvenc ... NOT VERIFIED" | source, FFmpeg n9.0.2 `libavcodec/nvenc.c:52-82` (fetched 2026-11-10), the NVENC input format list:<br>- line 57: `AV_PIX_FMT_P012,      // Truncated to 10bits`;<br>- line 62: `AV_PIX_FMT_P212,      // Truncated to 10bits`;<br>- line 66: `AV_PIX_FMT_YUV444P12MSB, // Truncated to 10bits`;<br>- line 67: `AV_PIX_FMT_YUV444P16, // Truncated to 10bits`.<br>Line 67 explains the measured yuv444p16le -> yuv444p10le result. | "source (nvenc.c:57,62,66, n9.0.2): FFmpeg truncates every 12-bit NVENC input to 10 bits, so no exact 12-bit NVENC path exists in this build. Not run." Change §3.4 to "12-bit pix_fmts listed, but truncated to 10 bits (source)". Drop the item from §6, or move it to "answered by source". |

## Weak

| # | claim | why it is weak | fix |
|---|---|---|---|
| W1 | §2.7 correction: "the contaminated all-threads FFV1 s24 rows were not lower bounds" (YUY2 241 vs 266) | measured: the 266 row is PyAV 18 (`bench/ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t0__pyav18.0.0.json`, 266.39). The loaded **PyAV 19** row for the same config (`...__t0__pyav19.0.2.json`) is 226.42 (217.98-234.65), and tonight's 241.4 beats it. The comparison mixes three things: the PyAV version, the affinity (16 vs 28 CPUs) and the load. The withdrawn rule may still hold within one version. The earlier pass (prev R2) had already shown that PyAV 18 vs 19 differ beyond the spread on this config. | Give both comparisons: "vs PyAV 18 loaded: slower (241 vs 266); vs PyAV 19 loaded: faster (241 vs 226)". Say that version and affinity are confounded, and keep "not reliably lower bounds". |
| W2 | §2.7 "every other config re-run tonight is faster than its loaded PyAV 18 row" | measured: `rawvideo.nut__nv12_1080p` and `ffv1_l3_s4_crc_g1.mkv__nv12_1080p` have no PyAV 18 1080p file. Only 720p NV12 exists for those. | "every other config **with a PyAV 18 row** is faster (2 of the 36 have none)". |
| W3 | "What this revision changes": "Three earlier statements were wrong ... the NVENC decode and 720p figures" | measured: the earlier 12-24 fps and 327-876 fps match the PyAV 18 loaded files exactly (hevc decode 12.45 / 17.11 / 23.87; 720p 326.8 to 876.15). They were correct for those files and have been superseded, not shown wrong. | Call them "superseded by quiet numbers", not "wrong". |
| W4 | §2.5 "source (via `results/hw_accel_target/FINDINGS.md` N2 / N1, NVIDIA ...)" quotes "4:2:2 encoding \| N \| N \| Y" and "YES NO YES YES"; also "Together, these confirm ..." | This is a secondary citation through another topic's draft FINDINGS. The URL, the exact source quote and the access date are not in this file. "Together, these confirm that the refusal is the RTX 3070 hardware" has no label. The code chain that supports it is not cited: nv16 sits in `ff_nvenc_pix_fmts` only under `NVENC_HAVE_422_SUPPORT` (nvenc.c:60-61, defined at nvenc.h:69), and under that macro the 4:2:2 check is a GPU capability query (nvenc.c:445-447). The previous pass asked for this (prev W1). | Copy the NVIDIA URLs, quotes and access dates from hw_accel_target, or mark the bullets as cross-references. Cite nvenc.h:69, nvenc.c:60-61 and nvenc.c:445-447 (re-checked 2026-11-10). Label the conclusion **inferred**. |
| W5 | §2.7 CQ row: "code/measured (`results/intra_compare/FINDINGS.md` line 62): FFmpeg's default `i_qfactor` codes NVENC constqp intra frames at 0.8x" | This cites another topic's draft FINDINGS, not the primary code. The primary code was checked here (n9.0.2, 2026-11-10) and agrees:<br>- `nvenc.c:832-836`: with `cqp >= 0`, `qpIntra = av_clip(ctx->cqp * fabs(avctx->i_quant_factor) + avctx->i_quant_offset + 0.5, ...)`;<br>- `options_table.h:151`: `i_qfactor` default `-0.8`;<br>- `nvenc_hevc.c` defaults (line 197 on) do not override `i_qfactor`. | Cite nvenc.c:832-836, options_table.h:151 and nvenc_hevc.c directly. inferred (arithmetic): with qp 24, the intra QP is about 19. |
| W6 | §2.7 "nvidia-smi read `0, 0 %` before and after every GPU case, so no other NVENC session ran" | measured: the JSON has snapshots at case start and end only (`nvidia_smi_before/after`). They cannot rule out a session during the case. | "...so no other NVENC session was open at the start or end of any GPU case". |
| W7 | §2.7 Method: "**code** (`bench_intra.py:150-164`): ... The codec opens on the first `encode()`, so the open is inside the window"; §5 cites `bench_intra.py:150-153` | The lazy open is PyAV behaviour, not bench_intra code:<br>- PyAV 19.0.2 `av/codec/context.py:686` calls `self.open(strict=False)` inside the encode path;<br>- the header is written on the first mux (`av/container/output.py:592-612`, `start_encoding`), which is also inside the window;<br>- line 153 is `make_frame`, while the first `encode()` is line 155. | Cite context.py:686 and output.py:592-612. Correct the line range to 150-164, with encode at 155. Add that the header write is also timed. |
| W8 | §2.5 "The raw12-packed rawvideo frame is 3,110,400 B (`bench/rawvideo.nut__raw12_packed_1080p__t1__pyav18.0.0.json`)", labelled measured | The cited file is a PyAV 18 background file. The value is deterministic. | Cite `bayer_debayer_check_pyav19.0.2.json` `raw_bytes.bayer12_packed_raw12` = 3110400, or label it arithmetic (1920 x 1080 x 1.5). |
| W9 | §4.4 "only P010 has an exact in-target path (hevc_nvenc lossless, 1,423.4 KB ...)"; §2.1 and §5 say only the "12-bit sizes" are noise-dominated | code, `uintra_frames.py` docstring: "p010le : ... 10-bit value = (8-bit << 2) \| 2 noise bits", and raw10_packed also carries 2 noise bits. The hevc_nvenc P010 size (1,423.4 KB) is 2.75x the NV12 size (517.7 KB), so it is probably noise-inflated too (inferred). | Extend the noise caveat to P010 and RAW10 wherever their sizes are quoted (§2.5, §3.1, §4.4). |
| W10 | §5 "The libx265 affinity widening (flag 2) does not apply ... the per-item affinity record reads `pcores`" | `affinity: "pcores"` in the log is the setting the runner requested, not a measurement. This topic's JSON records no process affinity. The conclusion holds for a different reason: no libx265 case ran in items 35, 56 or 57, and each case runs as its own `uv run --script` process. | Give that reason. Say that affinity was not measured per case. |
| W11 | §5 Defender: "the large Defender cost seen in `results/write_throughput/` does not apply" | This is unlabelled inference. MsMpEng used 9.22-17.92 CPU-s per item (log). Each rawvideo rep writes and deletes a file of about 1.24 GB (file_bytes in the JSON, about 300 x 4.15 MB). Any scan-on-close or delete cost falls outside the timed window, and its effect is not measured. | Label it **inferred**. Keep "Defender's share is not separated". |
| W12 | §4.5 "Use 24 slices with threads ... and 4 slices if single-threaded" | measured, t1 s4 vs s24: YUY2 45 vs 44, NV12 59 vs 57, Bayer8 55 vs 56 fps. Cores differ by at most 0.017. s24 is 9% smaller on Bayer8 (990.4 vs 1,087.3 KB). The data do not favour s4 at t1. | "At t1, s4 and s24 run within 4% of each other. s24 is smaller on Bayer8. Use s24." Alternatively, call the s4 choice a preference, not a finding. |

## Minor (no change of meaning)

- **Header**: the machine line is unlabelled. The driver 610.88 is in `bench/precheck_nvsmi.txt`, and the CPU is in `results/BENCH_RUN_2300_SUMMARY.md` row "Machine". Cite them.
- **§2.8 table**: "PyAV 18, 3 reps" hides frame counts. vp9, x265, jpeg2000, jpegls and svtav1 used 3 x 24 frames; the others used 3 x 90 (the `frames` field).
- **§2.7**: the slowest-call share "largest at 720p" holds for the NV12 rows only. At 720p, the P010 (6.9-8.7%) and Bayer8 (7.9-8.8%) shares are smaller than the 1080p h264 NV12 (10.7-11.9%) and gray (11.8-13.1%) shares. The draft does qualify "for NV12".
- **§2.9**: the mjpegenc quote spans lines 499-500, not just 499.
- **`prep_ms_per_frame`**: the NV12 native path (no re-layout) also reports 0.55 ms (h264_nvenc and rawvideo NV12 JSON). The prep loop also times `make_frame` + `reformat` + `read_planes` (`bench_intra.py:116-120`). The YUY2 de-interleave figure (1.415-1.490 ms) is right for the FFV1 files. "Prep = re-layout only" is true only for paths that have a `fwd` function.

## Checks that passed

- **measured, every row in §3.1 and §3.2** matches the JSON. This covers median (min-max) fps, cores, KB/f, p99, decode fps and MB/s@30 (arithmetic). For example: h264 NV12 515.52 (514.75-520.62) / 0.045 (0.045-0.055) / 593.57 KB / p99 1.979 / dec 103.05; FFV1 s24 Bayer12 t1 11.55 (11.47-11.56) / 2.587 / 2348.99 KB / dec 9.31.
- **measured, §2.7 aggregates**:
  - NVENC 720p range 332.05-1027.16 fps at 0.017-0.047 cores;
  - p99 0.958-7.059 ms;
  - `latency_max` medians 60.576-83.719 ms;
  - per-rep open share 3.6-22.7%; CPU rows at most 1.7%;
  - ticks: all 108 `encode_cpu_s` values are integer multiples of 15.625 ms, and the NVENC reps span 6-60 ticks;
  - 36/36 files, with every rep at 300 packets and 300 decoded frames;
  - env 19.0.2 / 9.0.2 / [63,1,102] / numpy 2.2.6 / Python 3.12.13; `unique_frames` 8, `looped` true.
- **measured, §2.7 run record**: items 35, 56 and 57 ran 02:30:22-02:35:07, 04:19:15-04:28:08 and 04:28:19-04:31:46, all with exit code 0. Load means were 3.87 / 4.27 / 5.33%, `load_over_15pct` was false, and no Defender scan events were recorded. MsMpEng used 13.14 / 17.92 / 9.22 CPU-s. Item 35 waited for the 02:00 Defender window, and each item has a "leftover processes" flag (not mentioned in the draft; harmless).
- **measured, §2.7 corrections**: 266.39/326.37/310.16 vs 241.4/323.34/308.45; Bayer8 cores 0.505 vs 0.719; 427.73 -> 515.52; 27.22 -> 41.05; 286.98 -> 390.56; old hevc decode 12.45-23.87; old 720p 326.8-876.15; mjpeg 149.41 (PyAV 18) vs 168.21 (PyAV 19). The on-disk FINDINGS.md:230-235 did list "149 vs 168" under "PyAV 19 vs 18", so "versions reversed" is a fair description.
- **measured, NVENC sizes**: identical across all reps, and equal to the PyAV 18 files.
- **measured, functional**:
  - Bayer8 NVENC sizes 1,803,645 / 1,368,828 / 767,200 / 681,534 B; raw12/raw10 hevc 3,141,306 / 2,326,082 B;
  - 12-bit -> yuv444p10le; CQ PSNR 51.02 dB; QSV table (Rext/Main/High, 50.64/50.65/50.12 dB, av1_qsv "Function not implemented");
  - FFV1 coder/noise bytes (1,617,493 / 504,260 / 2,347,875 / 1,219,858 / 1,629,144 / 1,612,245); C930e 470.3 vs C922 740.7 KB;
  - YUY2 ranges; mux acceptance (dnxhd MOV only); caps (unavailable encoders and decoders, and the pix_fmt diffs);
  - container pix_fmt losses; NVENC error strings; debayer (BG 43.6-44.25, RG 20.33-20.35, RGB 3,735,615 B; mosaic 2,414,539, quad 1,596,055);
  - JPEG-lib sizes; Chromium E35/E45 results, including JXL stills decoding in E45 only.
- **source, matches the text fetched on 2026-11-10**:
  - matroskaenc.c:2042-2043, nvenc.c:445-453, ffv1enc.c:921-927 and 652-653, mjpegenc_common.c:499-500;
  - RFC 9043 line 162 (§1), lines 1307-1308 (§3.8.2.5) and line 1757 (§4.2.17);
  - PyAV 19.0.2 `av/container/output.py:166-171`, from the uv cache entry with `av-19.0.2.dist-info`.
- **code**:
  - `bench_intra.py:111-121` (untimed prep), `:150-164` (timed window), `:173-187` (decode with the same `thread_count`, line 179), `:188` (unlink);
  - `functional_matrix.py:85` (CQ config, no `i_qfactor`) and `:403-411` (50% cut of a finalized file);
  - `bench_intra.py:99` (720p from `c930e_720p_flash`); corpus `index.json` (both YUY2 sets from `pyav_ds_1920x1080_5`).

## Verdict

The numbers are clean. Every timed figure traces to the quiet-run JSON, and the background rows are labelled. Two statements must change before the FINDINGS are saved:
- **R1**: silent corruption after truncation is broader than stated. It includes FFV1 in AVI, and no MKV case shows it.
- **R2**: FFmpeg's source already says that 12-bit NVENC inputs are truncated to 10 bits.

The main weak point is W1: the "not lower bounds" correction compares across PyAV versions. The others are secondary citations (W4, W5) and labels or citations that need tightening.
