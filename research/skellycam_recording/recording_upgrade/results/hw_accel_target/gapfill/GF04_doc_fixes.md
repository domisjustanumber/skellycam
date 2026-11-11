# GF04: hw_accel_target doc fixes (proposed text; FINDINGS.md not edited)

Date 2026-11-10. Gap-fill GF04 (doc_fix). No tests and no timing were run. Every number below was re-read from the JSON files named, through `S/hw_accel_target/gf04_capacity_extract.py` (parse only, no device opened), and its output `R/hw_accel_target/gapfill/GF04_capacity.json`.

Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `S` = `research/skellycam_recording/recording_upgrade/scripts/`, `IB` = `R/intra_compare/bench/`. Line numbers refer to `R/hw_accel_target/FINDINGS.md` as of 2026-11-10 (639 lines).

Labels: **measured** = result file + key; **source** = URL + exact quote + access date; **code** = file:line; **inferred** = reasoning, marked.

---

## Item 1. Header line 7

Old (line 7):

> `- **No timing numbers**, because other agents were running. Only size, PSNR/SSIM, correctness and seek exactness are reported.`

New:

> `- **Timing:** this topic ran no timed test. The capacity column in §3.3 and the table in §3.3.1 come from the quiet bench run \`20261109T230007\` (23:00:07–05:36:29; 67 of 68 items ok, the one timeout was OV-COST, not an encode item; no item flagged \`load_over_15pct\`) [measured: \`R/BENCH_RUN_2300_SUMMARY.md\` §1–§2]. Full tables, flags and caveats: \`R/intra_compare/FINDINGS.md\` §2.4–§2.6 and §3.5. Size, PSNR/SSIM, correctness and seek exactness are from the functional runs, as before.`

Also line 13 (labels):

- Old: `- **[source]**: a primary source, accessed 2026-11-09.`
- New: `- **[source]**: a primary source, accessed 2026-11-09 (2026-11-10 for R6 and the NVIDIA session column re-fetched by intra_compare).`

---

## Item 2. §3.3: new capacity column, plus a new §3.3.1 table

### 2a. Column to add to the §3.3 table (lines 366–374)

New column header, after "bytes at target A": **measured 1080p30 capacity on Gerald at target A (streams kept up, cores)**. Cells (detail and citations in §3.3.1):

| §3.3 row | new cell text |
|---|---|
| H.264 intra 4:2:0 | h264_nvenc 12 (session cap) at 0.611 cores; h264_qsv 16 at 1.246 cores (NV12 best case); libx264 not scaled (§3.3.1) |
| HEVC intra 4:2:0 | hevc_nvenc 12 (session cap) at 0.652 cores; **hevc_qsv 1** at 0.155 cores (default mode; low_power NOT VERIFIED); libx265 not scaled (§3.3.1) |
| JPEG re-encode | mjpeg_qsv 4:2:2 from YUY2: 16 at 0.915; mjpeg_qsv 4:2:0 from NV12: 16 at 1.050; nvJPEG from NV12: 8 at 2.558; nvJPEG 4:2:2 from YUY2: 16 at 4.684 (with late frames); nvJPEG fed decoded MJPEG **misses A** (not scaled); libjpeg-turbo 4:2:0: 16 at ≥1.685, 4:2:2: 16 at ≥2.809 (process workers, lower bound) (§3.3.1) |
| JPEG passthrough | n/a: no encoder (write cost: `R/write_throughput/BENCH.md`, `R/jpeg_passthrough/BENCH.md`) |
| AV1 intra | not benched: no RTX 3000 encode in the wheel (`R/BENCH_QUEUE_2300.md:217`) |
| VP9 intra | not benched: no NVIDIA encoder (`R/BENCH_QUEUE_2300.md:220`) |
| FFV1 (Vulkan) | not benched here (CPU `ffv1` is a G4 fallback in uncompressed_intra; `R/BENCH_QUEUE_2300.md:217`) |

HEVC row, "meets target?" cell. Old: `**yes**; playback needs HEVC decode hardware`. New: `**yes**; playback needs HEVC decode hardware. hevc_qsv: capability yes; 1 stream at 1080p30 in default mode (measured); low_power NOT VERIFIED`.

### 2b. New §3.3.1 (insert after line 387, before §3.4)

> ### 3.3.1 Measured capacity at target A on Gerald (quiet run 20261109T230007)
>
> - measured: every scaling item ran pinned to CPUs 0–15 (8 P-cores with HT) of the i7-14700K; `system_before.process_cpu_affinity` and `system_after.process_cpu_affinity` list CPUs 0–15 in every file (`GF04_capacity.json` keys `affinity_before`, `affinity_after`).
> - code: "keeps up" = per-stream fps ≥ 0.98 × 30 and end lag < 1/30 s; paced = 450 frames per stream at 30 fps, unpaced = 300 frames per stream; one thread or process and one encoder per stream (`S/intra_compare/bench_matched_concurrent.py:14-16, 127-131`).
> - code: packets are discarded, so these are encode-only numbers with no writer (`S/intra_compare/bench_matched_concurrent.py:60-62, 73-75`).
> - Column "streams kept up" = the largest requested N whose every paced rep has `streams_keeping_up` == `opened` (JSON `runs[]`, `mode` = "paced"). Cores = `runs[].cpu_cores` at that N, median (min–max) over reps. Unpaced = `runs[].aggregate_fps`, `mode` = "unpaced", same N.
> - measured: **NVENC opens at most 12 sessions.** Every requested N=16 NVENC cell has `opened` = 12, and the limit probes read `limit_probe.opened` = 12 of `max_tried` = 32 (IB `…h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json`, `…hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json`). Read every N=16 NVENC row as 12 streams.
>
> | candidate · feed (item) | streams kept up, 1080p30 | CPU cores at that N | unpaced aggregate fps at that N | 720p30 streams kept up | file in IB |
> |---|---|---|---|---|---|
> | h264_nvenc · NV12 (4) | **12** (N=16 requested, 12 opened) | 0.611 (0.601–0.635), 3 reps | 541.79 | 12 (item 49) | `matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` |
> | h264_nvenc · YUY2 → swscale NV12 (45) | 12 | 2.526 (2.409–2.644), 2 reps | 540.44 | – | `…h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json` |
> | h264_nvenc · MJPEG CPU decode (41) | 12 | 4.057 (4.013–4.101) | 596.21 | – | `…h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` |
> | hevc_nvenc · NV12 (5) | **12** (N=16 requested, 12 opened) | 0.652 (0.586–0.656), 3 reps | 390.01 | 12 (item 50) | `…hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json` |
> | hevc_nvenc · MJPEG CPU decode (42) | 12 | 3.901 (3.769–4.033) | 377.97 | – | `…hevc_nvenc_420_1080p_mjpeg_cpu_thread_20261110T082302Z.json` |
> | h264_qsv · NV12 (6) | **16** (probe 32/32 opened) | 1.246 (1.233–1.276), 3 reps | 679.40 | 16 (item 51) | `…h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json` |
> | h264_qsv · mjpeg_qsv decode (43) | 16 | 4.326 (4.303–4.350) | 485.54 | – | `…h264_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z.json` |
> | hevc_qsv · NV12, default mode (7) | **1** (N=4: `streams_keeping_up` 0 in all 3 reps) | 0.155 (0.154–0.183) | 66.40 | 4 (item 52) | `…hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json` |
> | hevc_qsv · mjpeg_qsv decode (44) | 1 (late 6, 7) | 0.431 (0.407–0.455) | 63.58 | – | `…hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` |
> | hevc_qsv 4:2:2 · YUY2 (34) | 1 | 0.153 (0.146–0.160) | 64.07 | – | `…hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json` |
> | mjpeg_qsv 4:2:2 · native YUY2 (33) | **16** (probe 32/32) | 0.915 (0.857–0.974) | 933.92 | – | `…mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` |
> | mjpeg_qsv 4:2:0 · NV12 (8) | **16** (probe 32/32) | 1.050 (1.029–1.055), 3 reps | 700.43 | 16 (item 53) | `…mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json` |
> | nvJPEG 4:2:0 · NV12 via swscale RGB (9) | **8** (late 0, 73, 66). N=16: 1, 2, 3 of 16 keep up | 2.558 (2.466–2.566), 3 reps | 455.51 at N=8; 475.37 at N=16 | 16 (item 54; late 136, 0) | `…nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` |
> | nvJPEG 4:2:2 · YUY2 via swscale RGB (32) | 16, with 383 and 955 late of 7,200 frames | 4.684 (4.630–4.739) | 567.47 | – | `…nvjpeg_422_1080p_yuy2_thread_20261110T063635Z.json` |
> | nvJPEG · decoded camera MJPEG | **not scaled; misses target A** (below) | – | – | – | – |
> | libjpeg-turbo 4:2:0 · NV12, process (10) | 16 | ≥1.685 (1.594–1.778), lower bound | 3,571.86 | 16 (item 55) | `…jpeg_turbo_420_1080p_nv12_process_20261110T053417Z.json` |
> | libjpeg-turbo 4:2:2 · YUY2, process (31) | 16 | ≥2.809 (2.482–3.137), lower bound | 1,742.22 | – | `…jpeg_turbo_422_1080p_yuy2_process_20261110T063244Z.json` |
> | libx264 / libx265 | **not scaled** (no `matched_concurrent_libx26*` file in IB) | single stream only, below | – | – | – |
>
> - measured: **nvJPEG fed decoded camera MJPEG misses target A.** In the single-stream item 1, the `nvjpeg_420` and `nvjpeg_422` rows with source `mjpeg_cpu` read `quality_check.ssim_y` 0.9954 (< 0.9961) and `quality_check.psnr_y` 45.211 dB against `matched_psnr_y` 49.995 (IB `matched_stream_A_1080p_20261110T042204Z.json`, `summary[]`). No scaling item fed nvJPEG decoded MJPEG.
> - measured: single-stream CPU encoders at A, 1080p from NV12 (same file, `summary[]` `fps_median`, `cpu_cores_median`): libx264 ultrafast 372.47 fps at 5.476 cores; libx264 veryfast 229.19 fps at 7.116 cores; libx265 ultrafast 106.22 fps at 26.935 cores. libx265 widened the process affinity to CPUs 0–27, so its row is not a P-core figure (`R/intra_compare/FINDINGS.md` §5 flag 1).
> - measured: process-worker CPU is a lower bound; three unpaced N=8 process runs recorded negative CPU (`R/intra_compare/FINDINGS.md` §5 flag 6).
> - measured (functional, no timing): `hevc_qsv` with the target-A options opens and writes 8/8 keyframes with `low_power=1`, with `preset=veryfast` and with both (`R/gpu_encode/verify_method_lowpower.json`, `cases[]`). Its speed in those modes is NOT VERIFIED.
> - inferred: on this machine, the hardware paths that carry 16 × 1080p30 at A are h264_qsv, mjpeg_qsv (4:2:0 and 4:2:2) and, at its limit, nvJPEG from YUY2. NVENC carries 12. hevc_qsv in default mode carries 1.
> - Scope: one run, one machine (RTX 3070 driver 610.88, UHD 770 driver 32.0.101.7088, 16 logical CPUs). Lower-end CPUs, other GPUs, NVENC + QSV together, target B and file writing were not timed (`R/intra_compare/FINDINGS.md` §6).

---

## Item 3. §5: replace "Pending tonight's bench"

Old (lines 465–494): the whole section from `## 5. Pending tonight's bench (23:00, timed, one item at a time)` to `- The NVENC limit under PyAV 19.0.2 is already measured (N10). The limit probe only needs to re-confirm it under load.`

New:

> ## 5. What happened to the old bench items (quiet run 20261109T230007)
>
> - measured: none of the 68 queued items is a `B-*` item, and no queued command runs a script under `S/hw_accel_target/`. `R/bench_queue_2300.json` has 68 `id` fields and 0 matches for `scripts/hw_accel_target`; `R/BENCH_RUN_2300_LOG.jsonl` has 0 matches for `"B-`.
> - measured: the queue replaced the old items with the matched-quality intra_compare benches (`S/intra_compare/bench_matched_stream.py`, `S/intra_compare/bench_matched_concurrent.py`) and listed the rest as dropped (`R/BENCH_QUEUE_2300.md:216-222`). `R/gpu_encode/FINDINGS.md` §6.1 records the same outcome for the gpu_encode items.
> - code: the replacement benches feed JPEG paths full range and H.264/HEVC limited range (`S/intra_compare/benchpaths.py:16-19`), so they do not have the K5 bug.
> - Bracket reasons in `BENCH_QUEUE_2300.md` use the old numbering: `[9]` is now requirement 3 (recording-format sub-bullet) and `[10]` is now requirement 8.
>
> | old item (`R/hw_accel_target/NOTES_functional.md` line) | what it asked | answered by (queue order, id) | JSON in `R/intra_compare/bench/` (or other) |
> |---|---|---|---|
> | B-QSV-1 (:195) | per-stream fps and CPU per frame, QSV, 720p/1080p, sources nv12/yuy2/yuy2native/mjpeg_cpu/mjpeg_qsv | 1 IC-STREAM-1080p-A, 2 IC-STREAM-720p-A, 3 IC-STREAM-1080p-B ("replaced by items 1-3", `BENCH_QUEUE_2300.md:216`) | `matched_stream_A_1080p_20261110T042204Z.json`, `matched_stream_A_720p_20261110T043459Z.json`, `matched_stream_B_1080p_20261110T044204Z.json` |
> | B-NV-1 (:196) | same, NVENC | 1–3 (same line) | same three files |
> | B-DEC-1 (:198) | source pipeline cost | "replaced": mjpeg_cpu / mjpeg_qsv rows minus nv12 rows of items 1–3, and pipeline items 41–44 (`BENCH_QUEUE_2300.md:218`) | items 1–3 files; `matched_concurrent_{h264,hevc}_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z / T082302Z.json`, `matched_concurrent_{h264,hevc}_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z / T083946Z.json` |
> | B-CPU-1 (:197) | CPU baselines: libsvtav1, libvpx-vp9, mjpeg, ffv1 | FFmpeg mjpeg kept as the `ff_mjpeg_*` rows of items 1–3. libsvtav1 and libvpx-vp9 **dropped, not queued**: no RTX 3000 encode path. ffv1 covered for G4 by UI-CORE-AV19 / UI-BAYER-AV19 (items 57, 56) (`BENCH_QUEUE_2300.md:217`) | items 1–3 files; `R/uncompressed_intra/BENCH.md` |
> | B-QSV-C1 (:199) | h264_qsv 1/4/8/16 + limit probe, 1080p | 6 IC-SCALE-h264_qsv_420 (+ 51 at 720p) (`BENCH_QUEUE_2300.md:219`) | `matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json`; `…720p_nv12_thread_20261110T090121Z.json` |
> | B-QSV-C2 (:200) | same, hevc_qsv | 7 IC-SCALE-hevc_qsv_420 (+ 52 at 720p; also 34 and 44) | `…hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json`; `…hevc_qsv_420_720p_nv12_thread_20261110T090841Z.json` |
> | B-QSV-C3 (:201) | same, vp9_qsv | **dropped, not queued**: "VP9 has no NVENC encoder" (`BENCH_QUEUE_2300.md:220`); gpu_encode §6.1: "vp9_qsv timing dropped (outside the hardware target)" | – |
> | B-QSV-C4 (:202) | same, mjpeg_qsv | 8 IC-SCALE-mjpeg_qsv_420 (+ 53 at 720p); 4:2:2 from YUY2 in 33 | `…mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json`; `…mjpeg_qsv_420_720p_nv12_thread_20261110T091225Z.json`; `…mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` |
> | B-QSV-C5 (:206) | h264_qsv 720p | 51 (`BENCH_QUEUE_2300.md:222`: "intra parts added") | `…h264_qsv_420_720p_nv12_thread_20261110T090121Z.json` |
> | B-QSV-C6 (:208) | MJPEG CPU decode + hevc_qsv **gop30** | gop30 part **dropped** (intra only); intra pipelines added as items 41–45 (`BENCH_QUEUE_2300.md:222`). inferred: the nearest hevc_qsv pipeline is item 44 (mjpeg_qsv decode, not CPU decode) | `…hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` |
> | B-QSV-C7 (:209) | mjpeg_qsv decode + vp9_qsv gop30 | **dropped, not queued** (VP9, gop30; `BENCH_QUEUE_2300.md:220`) | – |
> | B-NV-C1 (:203) | h264_nvenc 1/4/8/16 + limit probe | 4 IC-SCALE-h264_nvenc_420 (+ 49 at 720p) (`BENCH_QUEUE_2300.md:219`) | `…h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json`; `…h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` |
> | B-NV-C2 (:204) | same, hevc_nvenc | 5 IC-SCALE-hevc_nvenc_420 (+ 50 at 720p) | `…hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json`; `…hevc_nvenc_420_720p_nv12_thread_20261110T085747Z.json` |
> | B-NV-C3 (:207) | h264_nvenc 720p | 49 | `…h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` |
> | B-NV-C4 (:210) | MJPEG CPU decode + h264_nvenc gop30 | intra part = 41 IC-SCALE-h264_nvenc_420-mjpeg_cpu; gop30 dropped (`BENCH_QUEUE_2300.md:222`) | `…h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` |
> | B-MF-1 (:205) | per-stream MF + D3D12VA | **dropped, not queued**: MF and d3d12va land on the same RTX 3070 NVENC; d3d12va does not mux to MKV (`BENCH_QUEUE_2300.md:221`) | – |
> | IP-SYNC/SEEK/SCRUB-E35/E45 | Electron decode cost, H.264/HEVC intra vs JPEG path | 12–15, 25–26, 46–47 (intra_playback) | `R/intra_playback/BENCH.md` |
>
> - code: **the K5 range bug is still in `S/hw_accel_target/bench_encode_stream.py`.** `mjpeg_qsv` defaults to `nv12` (`:54`). YUY2 sources are reformatted to `nv12` with no range argument (`:112`). Decoded MJPEG sources are reformatted with `dst_color_range=1` for every non-`yuvj` format (`:119-124`).
> - measured: **no reported result uses that script.** It was not queued (first bullet), and `R/hw_accel_target/bench/` is empty (listing 2026-11-10).
> - code: the script also uses default rate control: its `ENC` table has empty QSV options and no `i_qfactor` (`:49-66`). Any future use needs both fixes, or the script should be retired in favour of the intra_compare benches.

---

## Item 4. §6 line 536

Old (line 536):

> `- No timing, CPU-cost or stream-scaling numbers yet (§5).`

New (replace, do not just delete):

> `- Timing limits: the capacity numbers (§3.3.1) are from one quiet run on Gerald only, encode only (packets discarded), at target A, on CPUs 0–15 [measured: \`R/BENCH_RUN_2300_SUMMARY.md\` §2; \`R/intra_compare/FINDINGS.md\` §2.5]. Not timed: scaling at target B; NVENC and QSV together; hevc_qsv \`low_power\` or other presets; libx264/libx265 with more than one stream; nvJPEG with process workers; any file writer in the loop [measured by absence: \`R/intra_compare/FINDINGS.md\` §6; \`R/gpu_encode/FINDINGS.md\` §6.2].`

---

## Item 5. §8.4 follow-ups

Old (lines 637–639):

> ```
> - intra_compare: `R/intra_compare/NOTES.md` §6 is out of sync with `matched_summary.md`.
> - hw_accel_target bench: fix or bypass the K5 range bug before 23:00.
> - FN §4: the "bit-identical" wording needs the F9 correction.
> ```

New:

> ```
> - intra_compare: `R/intra_compare/NOTES.md` §6 is still out of sync with `matched_summary.md` (checked 2026-11-10: lines 179, 181, 208 still read 83,921 / 55,112 / 144,376). `R/intra_compare/FINDINGS.md` uses `matched_summary.md` and lists the stale cells.
> - hw_accel_target bench: the K5 range bug was bypassed, not fixed. No `S/hw_accel_target/` script was queued, so no result uses it (§5). The bug is still at `bench_encode_stream.py:112` and `:119-124`; fix it or retire the script before any future use.
> - FN §4: the "bit-identical" wording still needs the F9 correction (checked 2026-11-10: `NOTES_functional.md:118, 120`).
> ```

Other "before 23:00" or "tonight" text: lines 465 and 484 go with §5 (item 3). Line 592 (§8.1 X9) and line 621 (§8.2) are revision history. Keep them as history; only the requirement number on line 621 changes (item 7).

---

## Item 6. Line 387: licence vs royalty wording

Old (lines 386–387):

> ```
> - every candidate has a software encoder;
> - JPEG's is royalty-free (libjpeg-turbo), while the wheel's H.264/HEVC encoders are GPL (R4).
> ```

Checking the proposed wording against R1 and R4:
- R1 (line 286) does **not** say "no patents listed in T.81 Annex L". It says that Annex L lists patents "only for the arithmetic-coding and hierarchical-lossless processes" (LIC Q17, Q18). So the accurate wording is "no patent listed for the baseline process".
- R4 (line 291) is labelled **[measured]**, not [source]. It covers only libx264/libx265 (shipped as DLLs, GPL, cannot be removed). It says nothing about libjpeg-turbo's licence. So a new source item, R6, is needed for libjpeg-turbo.

New (lines 386–387):

> ```
> - every candidate has a software encoder;
> - patents and licences are separate questions:
>   - JPEG baseline: T.81 Annex L lists patents only for the arithmetic-coding and hierarchical-lossless processes, none for baseline (R1) [source];
>   - libjpeg-turbo's code licence is permissive, BSD-style (R6) [source];
>   - the wheel's libx264/libx265 are GPL and cannot be removed (R4) [measured; licence text per LIC §2.5].
> ```

New R6, to add after R5 (line 292):

> `- **R6 [source]** libjpeg-turbo licence: "libjpeg-turbo is covered by two compatible BSD-style open source licenses" (the IJG License and the Modified (3-clause) BSD License). https://raw.githubusercontent.com/libjpeg-turbo/libjpeg-turbo/main/LICENSE.md, accessed 2026-11-10, sha256 \`ba6bceeb…d4433579\`. The binding used, simplejpeg, is under the "MIT License" (https://raw.githubusercontent.com/jfolz/simplejpeg/master/LICENSE, accessed 2026-11-10, sha256 \`dcb18a8a…cd7fe6d4\`). Both were read from the default branch, not from the version bundled in simplejpeg 1.9.0. Neither text is a patent grant.`

Optional, same issue on line 419. Old: `2. **JPEG is the only royalty-free format accelerated on both RTX 3000 and Intel TGL–RPL iGPUs.**` New: `2. **JPEG baseline is the only format with no listed patents (R1) that is accelerated on both RTX 3000 and Intel TGL–RPL iGPUs.**` Reason: R1 supports "no patents listed (1992)", not a royalty-free licence. `R/licensing/FINDINGS.md:140` calls the "de facto ... RF" quote secondary (Q19).

---

## Item 7. Requirement numbers remapped to the current HANDOFF §1

Current numbering (HANDOFF.md §1): 3 = hardware target (with sub-bullets: applies to the recording format; nvJPEG counts as hardware); 4 = jellyfin-ffmpeg sources only; 5 = PyAV 19.0.2 only; 8 = intra-only; 9 = H.264/HEVC intra vs JPEG at matched quality; 10 = timed tests from 23:00; 11 = no camera access. Old numbering: `HANDOFF_20261109_1300.md:30-48` (9 = 17:20 recording-format + 17:35 nvJPEG + 17:35 head-to-head; 10 = intra-only; 11 = queue).

| line | old | new |
|---|---|---|
| 3 | `HANDOFF §1 req 3, 9 and 10, plus the 17:20 and 17:35 decisions` | `HANDOFF §1 requirements 3 (hardware target, including the 17:20 recording-format and 17:35 nvJPEG sub-bullets), 8 (intra-only) and 9 (H.264/HEVC intra vs JPEG at matched quality)` |
| 315 | `Per Dom (17:35), it counts as hardware-accelerated.` | `Per Dom (17:35; HANDOFF §1 requirement 3), it counts as hardware-accelerated.` |
| 376 | `(req 3)` | unchanged (`requirement 3`) |
| 467 | `Req 11 / 17:35 JPEG-vs-H.264/HEVC bench` | requirement 9 (the line is removed by item 3) |
| 478 | `--gops intra only (req 10)` | requirement 8 (the line is removed by item 3) |
| 482 | `keep (req 9 playback side)` | requirement 9 plus G8/G9 (the line is removed by item 3) |
| 621 | `§5 cites … as the req-11 bench.` | `§5 cites … as the requirement-9 bench (then numbered 11).` |

The task's item list does not name line 592 (§8.1 X9). It has no requirement number.

---

## Evidence used

- measured: `R/hw_accel_target/gapfill/GF04_capacity.json` (from `S/hw_accel_target/gf04_capacity_extract.py`, parse only).
- measured: `R/intra_compare/bench/*.json` (24 scaling files, 3 single-stream files), `R/BENCH_RUN_2300_SUMMARY.md`, `R/BENCH_RUN_2300_LOG.jsonl`, `R/bench_queue_2300.json`, `R/gpu_encode/verify_method_lowpower.json`.
- code: `S/hw_accel_target/bench_encode_stream.py:49-66, 54, 112, 119-124`; `S/intra_compare/benchpaths.py:16-19`; `S/intra_compare/bench_matched_concurrent.py:14-16, 127-131, 60-62, 73-75`.
- source: libjpeg-turbo LICENSE.md and simplejpeg LICENSE (URLs above, accessed 2026-11-10). Copies are in the step3 scratchpad, `GF04_src/`.
- Cross-topic text: `R/BENCH_QUEUE_2300.md:206-222`, `R/gpu_encode/FINDINGS.md` §6.1–§6.2, I3–I5; `R/intra_compare/FINDINGS.md` §2.5, §3.5, §5, §6.
