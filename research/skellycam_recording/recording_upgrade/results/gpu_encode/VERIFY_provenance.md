# gpu_encode: provenance verification of the post-bench draft FINDINGS (2026-11-10)

- **Verifier:** adversarial provenance pass. No timed runs, no camera access, no system changes.
- **Paths:** relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
- **Previous report:** `results/gpu_encode/VERIFY_provenance.prev.md` (2026-11-09, first draft). The draft cites "`VERIFY_provenance.md` §2" for two counts (the 10 occurrences of the d3d11va string, and 82 of 90 GeForce rows) and "§3" for re-fetch status. Both are re-checked below (§2 and §3 here), so those references still resolve.

## 1. Method

- Every quiet-run number in draft §2.4, 2.6-2.10, 3.2, 3.3, 4 and 5 was recomputed from the JSON with read-only Python. It was not taken from BENCH.md. Files:
  - `results/intra_compare/bench/matched_stream_{A_1080p_20261110T042204Z,A_720p_20261110T043459Z,B_1080p_20261110T044204Z}.json` (`summary[]`, `runs[]` order, `system_before/after`);
  - all 24 `results/intra_compare/bench/matched_concurrent_*.json` (`runs[]` by mode and N, `limit_probe`, affinity);
  - `results/intra_compare/raw/{mjpeg_qsv,h264_nvenc,hevc_nvenc,h264_qsv,hevc_qsv}_*.json` (`points[]`);
  - `results/intra_compare/matched_settings.json`, `knob_check.json`, `ffmpeg_n9.0.2_knob_excerpts.txt`;
  - `results/python_integration/bench/nvjpeg_decode_quiet1_2300.json`;
  - `results/uncompressed_intra/bench/{h264,hevc}_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json`;
  - `results/BENCH_RUN_2300_SUMMARY.md`, `results/BENCH_RUN_2300_LOG.jsonl` (item 40), `results/BENCH_QUEUE_2300.md` lines 215-235.
- Functional files were spot-checked: `verify_method_{checks,opts,opts_mkv,pool,cuvid}.json`, `adapter_check{,_hevc}_19.0.2.json`, `revise_nvenc_packet_hashes.txt`, `nvimgcodec_{jpeg,lifetime}.json`, `ff_functional.md`, `qsv_recheck_19.0.2.md`. Media sizes came from `ls -l` of `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/{verify_method,diag}/`.
- Code checked at the cited lines: `scripts/intra_compare/benchpaths.py` (1-25, 174-244), `scripts/intra_compare/bench_matched_concurrent.py` (120-140, 210-240).
- Primary sources re-fetched on 2026-11-10 (§3). Raw copies are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/ge_src/`.

## 2. Claim-by-claim check

OK means the cited file says exactly that, with rounding to the precision shown.

### 2.1 Machine state

| draft claim | verdict | evidence |
|---|---|---|
| ff_functional d3d11va string occurs 10 times | OK | `grep -c` = 10 |
| iGPU present from 16:42 | OK | `qsv_recheck_19.0.2.md` header 16:42:40; `hw_accel_target/system_probe_1700.txt` exists |
| quiet run: UHD 770 and RTX 3070 `OK\|True` in `system_before.display_devices`; no QSV item skipped | OK | `matched_stream_A_1080p` `system_before`; `BENCH_RUN_2300_SUMMARY.md` lines 13, 26 |
| driver 610.88 at item 40, 03:16 | OK | `nvjpeg_decode_quiet1_2300.json` `env.nvidia_smi_before`; `started_unix` 1794298579 = 03:16:19 local; LOG order 40 `PI-NVJPEG-DECODE` 03:16:18 |
| intra_compare JSONs have no driver version | OK | `intra_compare/BENCH.md` line 7 |

### 2.2 Functional (spot checks)

| draft claim | verdict | evidence |
|---|---|---|
| 26 working outputs, 32 frames each, Y PSNR ≥ 45.18, \|mean Y offset\| ≤ 0.063 | OK | `verify_method_checks.json` `psnr_y`: 28 entries, 26 with frames=32 (h264_mf counted twice, once per iGPU state); min 45.18 (h264_qsv gop15), max \|offset\| 0.063 |
| sw-frame and HWAccel('cuda') payloads identical for 3 NVENC cases | OK | `revise_nvenc_packet_hashes.txt` |
| NVENC gop_size 1 fails with the "Gop Length" message in PyAV 19.0.2 | OK | `verify_method_opts.json` case `nvenc_gop1_bf0` |
| d3d12 default B-frames fail at `avcodec_send_frame` | OK | same file, `d3d12_gop15_default_bf` |
| D3D12 to `.mkv` gives `InvalidDataError` and a 291-byte file | OK | `verify_method_opts_mkv.json`; `ls -l` gives `d3d12_intra_mkv.mkv` 291 B |
| `887a0020` in the same process, success in a fresh one | OK | `verify_method_opts.json` case 3 vs `_mkv.json` (it opens, then fails at mux) |
| D3D12 default device NVIDIA for h264 and hevc; MF activates the NVIDIA MFT for both | OK | `adapter_check_19.0.2.json`, `adapter_check_hevc_19.0.2.json` ("Using device 10de:2484", "activate MFT 0" = NVIDIA) |
| pool test: hevc_nvenc "incompatible client key (21)", h264_d3d12va "Failed to create encoder.", h264_mf `MF_E_UNSUPPORTED_D3D_TYPE`; the control encoded 3 packets each; h264_qsv still encodes; MF stays on NVIDIA | OK | `verify_method_pool.json` |
| cuvid: 4:2:0 control 3/3 nv12 both routes; 4:2:2 fails | OK | `verify_method_cuvid.json` |
| mjpeg_qsv decoder: luma max \|diff\| 1, mean 0.007-0.009, slope 1.0; tagged limited, samples full | OK | `verify_method_checks.json` `mjpeg_qsv_raw` (`qsv_color_range` "1", Y 0-255) |
| nvImageCodec 53.14 / 54.18 dB; q90 2.4-2.8 dB below OpenCV | OK | `nvimgcodec_jpeg.json` (44.42 vs 47.25, 43.74 vs 46.16) |
| 392 CUDA #700 lines, exit 0 | OK | `nvimgcodec_lifetime.json` (d1, d8, dl1+d8) |
| Bayer 8,087,879 / 17,047,238 B | OK | `ls -l diag/` |
| sweeps: every NVENC/QSV H.264/HEVC point all-intra, all VCL IDR, has_b_frames 0, max_b_frames 0; gop 0 (NVENC) / 1 (QSV); profiles High/Main/High/Main/Rext | OK | all 28 raw files, every point |

### 2.3 mjpeg_qsv chroma (the HANDOFF §4 loose end)

| draft claim | verdict | evidence |
|---|---|---|
| fed nv12 → yuvj420p, 19-23 points per file, all intra | OK | 4 `mjpeg_qsv_420__*.json`: `pix_fmt_fed` {nv12}, `decoded_pix_fmts` {yuvj420p}, 19/19/19/23 points |
| fed yuyv422 → yuvj422p, sof 0xc0 | OK | 4 `mjpeg_qsv_422__*.json`: {yuyv422}, {yuvj422p}, sof {0xc0}. The 4:2:0 files are also 0xc0 |
| matched_settings pairing; gq 94 (A) / 44 (B) at yuy2_1080p | OK | `matched_settings.json` |
| item 1 `mjpeg_qsv` source rows feed nv12 | OK | `summary[]` `pix_fmt_fed` nv12 |
| Intel quote, `media_features.md` line 79 | OK | re-fetched; line 79 is the "\**Note: JPEG encoding supports input format NV12/YUY2/UYVY/ABGR/Y8 and output format YUV400/YUV420/YUV422H_2Y/YUV444/RGB24." |

### 2.4 Session limits

| draft claim | verdict | evidence |
|---|---|---|
| h264_nvenc 12/32, ExternalError 542398533; smi "0, 0 %, 0 %, 0 %" before → "12, 5 %, 0 %, 0 %" | OK | `limit_probe`, item 4 file |
| hevc_nvenc 12/32, same error, smi 12 at peak | OK | peak "12, 8 %, 6 %, 0 %" |
| every N=16 run in all 7 NVENC scaling files opened 12, same `open_error` | OK | 7 files (h264 nv12/yuy2/mjpeg_cpu/720p; hevc nv12/mjpeg_cpu/720p), every rep |
| QSV probes 32/32, smi 0 (h264_qsv, mjpeg_qsv_420, mjpeg_qsv_422) | OK | `limit_probe` in the 3 files |
| hevc_qsv no probe, N=16 opened 16 | OK | `limit_probe` null; `opened` 16 ×6 |
| probe method (`bench_matched_concurrent.py:217-234`) | OK | code read |
| scope | note | every probe ran in **one process**. A cross-process cap was not measured in the quiet run. The NVIDIA matrix value is the source for the cap in general |

### 2.5 Single-stream numbers (draft 2.7, 2.8, 3.2)

Every fps median/min/max, CPU ms/frame, bytes/frame, × jt422, QC PSNR-Y/SSIM-Y and matched value cited in 2.7-2.8 matches `summary[]` of the three `matched_stream_*` files. Checked: mjpeg_qsv 602/481/1,155/894/618; nvJPEG 1,126/323/343; NVENC/QSV 540/390/585/65, 1,115/842/1,151/128, 635/425/691/87; YUY2 6.67/8.44/3.18; nvJPEG-from-MJPEG 0.9954/45.21/49.995, 720p 45.512 vs 49.301 (3.79 dB), B 43.144; the 1.44 dB gap (52.24 − 50.797); NVENC encoder util 100 % (`runs[].gpu.nvidia_smi.utilization.encoder` mean 100 in 4/5 reps, 99 and 85.3 in one rep each). Two problems:

- **WEAK, affinity:** table 3.2 is headed "(P-cores; …)". But the YUY2, MJPEG and RGB cells of item 1 ran **after** the first libx265 cell. In the `runs[]` order, the nv12 block (with libx265 last) comes before every yuy2/mjpeg/rgb cell. `system_after.process_cpu_affinity` is 0-27 in all three files. So these single-stream values are not shown to be P-core-only: mjpeg_qsv_422 481, nvjpeg_422 343, hevc_qsv_422 64, MJPEG→h264_nvenc 228, MJPEG-QSV→h264_qsv 554, nvJPEG rgb 1,126, and the 720p mjpeg_qsv_422 894. Draft §5.3 says this, but 3.2, 2.7, I7 and I9 present those cells without it.
- **WEAK, matched settings summary:** 2.8 says "NVENC qp 12 at target A, qp 31 at target B" and "QSV QP 12-13 at target A, 30-31 at target B", under "All numbers are at the matched settings". `matched_settings.json` gives that only for `yuy2_1080p`. Other classes:
  - h264_nvenc A: 12 (yuy2_720p), 14 (mjpeg_*); B: 28/30.
  - hevc_nvenc A: 13 (yuy2_720p), 11 (mjpeg_*); B: 29/30.
  - h264_qsv A: 13 (mjpeg_720p); B: 28/29.
  - hevc_qsv A: **14** (mjpeg_*); B: 29/30.
  - 2.8 cites 720p and MJPEG-source items that ran at those values.

### 2.6 Scaling numbers (draft 2.8, 3.2)

All of these match the `runs[]` medians and ranges: h264_nvenc 0.61 (0.60-0.64) and unpaced 512/534/539/542 (537-542); hevc_nvenc 0.65 (0.59-0.66), 389-391; h264_qsv 1.25 (1.23-1.28), 679 (678-682), 542; hevc_qsv 66-67, 98.4 % late at N=4 (1772/1800), 4 fps per stream at N=16; hevc_qsv_422 64-65; 720p hevc_qsv 4 keep up / 8 not, 134-135; mjpeg_qsv_420 1.05, 700 (695-705); mjpeg_qsv_422 0.92 (0.86-0.97), 934 (932-936); nvJPEG 420 2.56 at N=8, 1/2/3 of 16, 83.6 % late (6020/7200), 475 (472-477) at 4.87; nvJPEG 422 4.68 (4.63-4.74), late 383/955 of 7200 = 5.3/13.3 %; pipelines 4.06 (4.01-4.10), 3.90, 4.33 (4.30-4.35); 720p 1,572-1,578; table 3.2 unpaced 542/390/679/66/64/700/934/456/567/596/486. Problems:

- **REFUTED (number):** "From mjpeg_qsv decode [hevc_qsv] gives 66-67 fps" (`…hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json`). The aggregates are 63.50/63.65 (unpaced N=1), 65.61-66.78 (N=4) and 66.26-66.64 (N=8, 16). Correct to "63.5-66.8 fps aggregate (66.3-66.6 at N ≥ 8)".
- **WEAK (minor rounding):** mjpeg_qsv_420 N=16 paced cores are 1.029/1.050/1.055, so the range is 1.03-1.06 under round-half-up, not 1.03-1.05.
- **WEAK, "keeps up" framing:** the script's definition (`bench_matched_concurrent.py:130-131`: every stream ≥ 0.98 × 30 fps and end lag < 1/30 s) counts nvJPEG 422 at N=16 as keeping up with 5.3 % and 13.3 % of frames late. 2.8 states the late %. I2 ("keeps up with 16 × 1080p30") does not. Also unstated: the mjpeg_qsv → h264_qsv pipeline had late frames at N=1/4/8 (5/5, 43/45, 153/113) even though N=16 had 0, and mjpeg_qsv_420 NV12 had 13-26 late frames at N=1.

### 2.7 Code citations

- **WEAK:** "the 4:2:0 NVENC/QSV paths get YUY2 → NV12 by swscale inside the timed loop … code `benchpaths.py:7-19`" (2.8, §5.6). Lines 7-19 are the module docstring. They state that MJPEG decode is in the loop and that range mapping for nv12/yuy2 is untimed. They do not state the yuyv422 → nv12 reformat. That is code at `benchpaths.py:217-229` (`Feed.next`: `return f if self.fmt == "yuyv422" else self._reformat(f, self.fmt, self.rng)`, line 229). The rgb24 conversions are at 214-215, 227-228 and 239-240. intra_compare/BENCH.md caveat 2 has the same imprecise cite. Cite `benchpaths.py:199-244`.
- OK: `bench_matched_concurrent.py:130-131` (keeps-up definition), `:217-234` (limit probe).
- OK: knob mechanism. `knob_check.json` `iqfactor`: h264_nvenc qp25 gives 19 / 50,990 B, and with i_qfactor 1 gives 24 / 33,081 B; hevc_nvenc 19 → 24; h264_qsv 20 → 25. `ffmpeg_n9.0.2_knob_excerpts.txt` holds `options_table.h:151` (`i_qfactor` default -0.8). `intra_compare/FINDINGS.md` line 62 is the pitfall bullet citing it.

### 2.8 python_integration and uncompressed_intra pointers

- **WEAK (attribution):** 2.6 and table 3.3 give "1.92-2.27 ms at 1080p" (decode on GPU) and "3.37-3.64 ms" (with copy) as decode of the **camera 4:2:2** JPEGs. In `nvjpeg_decode_quiet1_2300.json` the 1.92 and 3.37 minima come from `generic_1080p`. That is a non-camera set of 11 frames (`scripts/python_integration/bench_nvjpeg_decode.py:36`; `python_integration/BENCH.md` line 170), and its chroma format is not stated. The camera sets are c930e_1080p 2.08 / 3.45 and c922_1080p 2.27 / 3.64. Correct to "2.08-2.27 ms (camera sets; 1.92 for a generic JPEG set)". The 720p sets (0.72-0.93, 1.44-1.68) are camera sets: OK.
- OK: nvImageCodec 0.9.0.20 in `env`; no CPU-time fields in the JSON.
- **WEAK (missing run flag):** 2.9 states h264_nvenc 516 (515-521) fps, 0.045 cores, 593.6 KB/frame, and hevc_nvenc 302 / 29 fps. These match the JSON (`rep_results` 514.75/520.62/515.52; `encode_cpu_cores_per_30fps_stream` 0.045; `bytes_per_frame` 593,569.7; hevc decode 28.7). But 2.9 calls them "Lossless" with no qualifier. `BENCH_RUN_2300_SUMMARY.md` §3 flag 9 says there is no lossless check inside the timed uncompressed_intra bench, and that encoder open is inside the timed window (3.6-22.7 % of NVENC wall time). Carry that flag, or cite the functional exactness file for "lossless".
- OK: intra_playback draft lines 5, 15, 20 ("All 48 intra clips … frame-exactly"; 4 encoders × 3 containers × 4 contents; "about 55 dB Y-PSNR") and line 64 ("Not played: HEVC 4:2:2"). Correctly labelled as an unverified draft. Note: the quiet-run playback seek result (`BENCH_RUN_2300_SUMMARY.md` line 86, `intra_playback/bench/*`) is a measured alternative that the draft does not cite.

### 2.9 Run flags and queue (draft §5, 6.1)

| draft claim | verdict | evidence |
|---|---|---|
| every intra_compare JSON `system_before` affinity 0-15 | OK | all 27 files checked |
| libx265 widened affinity; NV12 GPU cells before first libx265 cell | OK | `runs[]` order in all 3 `matched_stream_*` files |
| scaling items 0-15 before and after | OK | all 24 files |
| MsMpEng 9.16 (item 4) / 48.86 (item 7); no load flag; no scan event | OK | `intra_compare/BENCH.md` §1 lines 26, 29, 52-54 |
| reps 5/4/3; 3 (items 4-10) / 2 | OK | `args.reps`; BENCH.md caveat 7 |
| source sets 16 / 38 / 240 frames | OK as cited | BENCH.md caveat 6 (not re-derived from `iclib.py`) |
| queue lines 225-230, 221, 227, 228 | OK | `BENCH_QUEUE_2300.md` |
| B4 items 1-3, 9, 32, 54, 40 | OK | queue line 229 |
| B-QSV items 6-8, 33-34, 43-44, 51-53 | OK | BENCH.md §4 headings |

### 2.10 Implications (draft §4)

- I1, I3, I4, I5, I6, I8, I11, I12: numbers and labels match the evidence above.
- **WEAK, I2:** "Its files are 0.79-0.88 × libjpeg-turbo, at 1.44 dB lower PSNR-Y" mixes two pipelines:
  - The byte ratios come from the timed swscale-RGB path (nv12/yuy2 sources).
  - The 1.44 dB gap comes from the exact-RGB sweep (`matched_settings.json` `input`: "host RGB24, exact float BT.601"). On the timed path the QC PSNR-Y of nvjpeg_420 · nv12 is 52.344 against jpeg_turbo 52.82, a gap of 0.48 dB on 4 frames.
  - I2 also omits the late frames at N=16 (see 2.6).
- **WEAK, I7 and I9:** they present YUY2-source single-stream numbers (0.66-1.58 ms; 1.07 ×) that ran after the libx265 affinity change, without that caveat.

### 2.11 Style and labels

- The Status bullet "This file background to hw_accel_target and intra_compare." is missing a verb.
- Section 2.12 sits after 3.5. Table 3.4 cites it, but the numbering is out of order.
- No unlabelled factual bullets were found in §2. Table 3.2's "host conversion (inferred)" is labelled.
- No PyAV 18 result is presented as primary. No contaminated daytime timing is presented as current: every timed number cites a `20261110T*` or `q2300` JSON. The 2.4 "earlier functional checks" are labelled as from the busier machine and have no timing.

## 3. Sources: re-fetch status (accessed 2026-11-10)

| source | status |
|---|---|
| https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new | re-fetched (WebFetch summary). RTX 3070/2080/4070/5070 concurrent sessions 12. AV1 4:2:0: NO/NO/YES/YES. H.264/HEVC 4:2:2: NO except 5070 YES. No VP9 encode column. About 8 GeForce rows ≠ 12: four give 0 (MX570 A, MX150 > MX330, MX350, GT 1030) and four give n/a. Consistent with "82 of 90". The row total was not recounted in this pass |
| https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/9.0.2-1/scripts/build-ffmpeg.py | re-fetched (curl). `--enable-nvenc --enable-nvdec` line 189, `--enable-amf` 192, `--enable-libvpl` 195, `--enable-videotoolbox` 200 (inside the cited 188-203). `grep -ci "vulkan\|vaapi"` = 0 |
| https://raw.githubusercontent.com/intel/media-driver/intel-media-26.3.5/docs/media_features.md | re-fetched (curl). The encode table starts at line 59. TGLx/ICL VP9 8-bit input NV12/AYUV; AV1 blank for TGLx/ICL/KBLx; BMG/LNL VP9 blank. Line 79 is the JPEG note |
| https://raw.githubusercontent.com/intel/media-driver/intel-media-26.3.5/README.md | re-fetched (curl). Lines 79-82 are KBLx (KBL, CFL, WHL, CML, AML), ICL, JSL/EHL, TGLx (TGL, RKL, ADL-S/P/N, RPL-S/P). The draft's list omits JSL/EHL (line 81), which is harmless |
| https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html | re-fetched (WebFetch). "Hybrid (CUDA + CPU) JPEG" is present. Nothing on JPEG 4:2:2 |
| FFmpeg n9.0.2 `nvenc.c`, `qsvenc.c`, `options_table.h`, `allcodecs.c`, `ffv1enc_vulkan.c` | not re-fetched. `options_table.h:151` is confirmed in `results/intra_compare/ffmpeg_n9.0.2_knob_excerpts.txt`. The rest rest on the saved copies listed in draft §6.2 |
| AMD RX 7600/6600 and Apple M5/M2 pages | not re-fetched (saved HTML, as the draft says) |

## 4. Verdict

The quiet-run rewrite is faithful to the JSON. Every headline number checked (about 150) matches `summary[]` or `runs[]`. The mjpeg_qsv chroma correction is fully supported by the 8 raw sweep files. The NVENC 12-session and QSV 32/32 results match the limit probes.

Fix before saving:
1. Refuted: hevc_qsv from mjpeg_qsv decode "66-67 fps". The data give 63.5-66.8.
2. Wrong scope: the NVENC/QSV QP summary in 2.8 holds only for `yuy2_1080p`. hevc_qsv uses QP 14 at target A on MJPEG classes, and B ranges 28-31.
3. Attribution: the nvJPEG decode 1080p lower bound (1.92 / 3.37 ms) is a non-camera set. The camera range is 2.08-2.27 / 3.45-3.64.
4. Missing caveats:
   - the libx265 affinity widening on YUY2/MJPEG/RGB single-stream cells in table 3.2, I7 and I9;
   - no lossless check in the timed NVENC-lossless pointer (2.9);
   - late frames behind "keeps up" in I2.
5. Citation: replace `benchpaths.py:7-19` with `benchpaths.py:199-244` (line 229) for the in-loop YUY2 → NV12 reformat.
6. I2 mixes the byte ratio of the swscale path with the PSNR gap of the exact-RGB sweep.
