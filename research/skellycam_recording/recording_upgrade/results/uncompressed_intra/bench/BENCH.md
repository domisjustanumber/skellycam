# uncompressed_intra timing benches (G4) - BENCH

Machine Gerald (i7-14700K, 28 logical CPUs; RTX 3070, driver 610.88), 2026-11-09. Bench runtime 11:30-11:59, which is 29 min of the 35 min cap.

Every number here is **measured**. The raw per-case JSON is in this folder (`<config>__<source>_<res>__t<threads>__pyav<ver>.json`). The full flat table is `bench_summary.md` and the run logs are `run_*.log`. Paths are relative to `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/bench/`.

## Read this first: the machine was NOT quiet

- measured: total CPU averaged 50.4% over the 10 s before the runs (`precheck_typeperf.csv`). Re-checks over the next 5 min gave 52.3, 26.4, 30.1, 24.3 and 33.9% (`precheck_typeperf_recheck_avgs.txt`). The protocol limit is 15%. As instructed, I went ahead after 5 min and flag it here.
- measured: the load came from other agents' jobs: the jpeg_passthrough mux matrix, the crash_resilience kill and truncation matrices (3 workers), a USB camera suite, several Electron harnesses, the gpu_encode nvimgcodec bench and a cv2 read probe. They are listed in `precheck_other_jobs.txt` and `precheck_topcpu_now.txt`.
- measured: whole-machine CPU during individual reps was 13-99% (441 reps). The field is `system_cpu_percent_during_encode` (per rep) in each JSON, shown as the "sys CPU%" column in `bench_summary.md`. 10 s after the last case it still averaged about 29% (`postcheck_typeperf.csv`).
- measured: GPU utilisation was 5-43% before the NVENC cases. The NVENC session count was 3, not 0, before or after two of the 720p cases (`nvidia_smi_before/after` in each GPU JSON), so another agent was using NVENC.
- inferred: absolute fps are lower bounds, especially the all-threads (t0) rows and the multi-threaded codecs. Single-thread rows and the relative ordering are more trustworthy. Re-run on an idle machine before quoting absolute capacity.
- measured: Defender real-time protection was on (`precheck_defender.txt`). C: had 826 GB free (`precheck_disk.txt`).

## Method

- Input frames:
  - 1080p: the 8 real C930e 1080p YUY2 frames (corpus `c930e_1080p_yuy2`).
  - 720p: 8 real C930e 720p JPEGs decoded to YUY2 (`c930e_720p_flash`).
  - Frames are **looped** to the run length (`looped: true` in each JSON).
  - NV12, gray, P010, Bayer8/12, the quad split and RAW12-packed are **derived** from those frames by `scripts/uncompressed_intra/uintra_frames.py` (see `../NOTES.md` section 1).
  - The 10-bit and 12-bit sources carry seeded noise in the extra bits, so their compressed sizes are pessimistic (inferred).
- Each case:
  - one warm-up run, discarded: 10 frames, or 4 for slow codecs, or 20 for GPU;
  - then 3 timed reps: 90 frames, or 24 for the slow codecs (jpeg2000, x265, vp9, svtav1 p10/lossless, jpegls, prores), or 300 for GPU;
  - each rep encodes and muxes to a file on C:, then decodes that whole file.
  - Values are the median (min-max) of the 3 reps.
- Thread settings: t1 = `codec_context.thread_count=1`. t0 = libav auto (all cores) with `thread_type=AUTO`.
- cores/stream = process CPU seconds per second of 30 fps video. 1.0 means one core fully busy for one 30 fps stream. A value above 1 at t1 means either the codec cannot keep up on one core or the wrapper runs its own threads (see Headlines).
- p99 ms = the 99th percentile of one `make_frame + encode + mux` call. With frame threading (t0 for jpegls, prores, dnxhd, ...) encode() returns before the packet exists. So this is the call time, not frame-to-packet latency.
- Versions (recorded in every JSON):
  - skellycam venv: PyAV 18.0.0 with FFmpeg 8.1.2 libraries (libavcodec 62.28.102), Python 3.12.13, numpy 2.2.6.
  - PyAV 19.0.2 via `uv run --script`, with PEP 723 pins av==19.0.2, numpy==2.2.6, psutil==7.2.2.
  - `bench_py_still.py` pins simplejpeg 1.9.0, imagecodecs 2026.10.10 and opencv-python 5.0.0.93.
  - The debayer bench used the venv's OpenCV 4.12.0 (28 threads).
- Temporary media was written to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/bench_tmp/` and deleted after each rep. The folder was removed at the end.

## Script fixes made for this run

- `bench_intra.py`:
  - added `--reps` (default 3) and `--warmup-frames` (a discarded warm-up run);
  - per-rep results go in `rep_results` and median/min/max in `stats`; the flat fields (`encode_fps`, ...) now hold the medians;
  - it records whole-machine CPU during each encode, `library_versions` and the numpy version;
  - the 1 s idle samples before and after each case became 0.5 s.
- `bench_suite.py`: passes `--reps`, `--warmup-frames` and `--slow-warmup-frames` through, and has new `--sources`, `--configs` and `--skip-configs` filters (used to fit the time cap).
- `bench_py_still.py`, `bench_debayer.py`: a warm-up pass over the 8 unique frames, then `--reps` timed passes, with median/min/max recorded.
- `bench_summary.py`: reads the new fields and shows median (min-max) plus the sys-CPU columns.
- New `bench_tables.py`: prints the side-by-side t1/t0 tables below.

## What was run and what was dropped (time cap)

| manifest id | run as | dropped |
|---|---|---|
| uintra_gpu_nvenc | full (12 cases) | none |
| uintra_core_1080p | YUY2: all 23 configs x t1/t0 (46 cases). NV12: 5 configs x t1/t0 (ffv1 s24, ffv1 s24 range, utvideo, mjpeg, svtav1 lossless p12) | NV12 for the other 18 configs |
| uintra_bayer_1080p | bayer12, bayer12_quad, bayer8: all 8 configs x t1/t0 (48 cases). raw12_packed: rawvideo t1 only | bayer8_quad entirely; raw12_packed apart from rawvideo t1 (stopped at the cap) |
| uintra_core_720p | 4 configs (rawvideo.nut, ffv1 s24, utvideo, mjpeg) x YUY2/NV12 x t1/t0 | 6 configs (ffv1 s4, ffv1 s24 range, magicyuv, svtav1 p12, vp9 lossless, x264 qp0) |
| uintra_pyav19 | full (14 cases) | none |
| uintra_py_still | all 11 cases at 1 and 8 workers, 16 frames x 3 reps | the 4-worker runs; frames cut from 120 to 16 |
| uintra_debayer | full, 30 frames x 3 reps | frames cut from 120 to 30 |
| uintra_summary | run | none |

## Headlines

All measured. The file for each number is the JSON named by its config, source, resolution and thread setting.

- YUY2 1080p, configs that hold one 30 fps stream on **one core** (t1 encode fps of at least 30 and cores/stream of at most 1):
  - rawvideo: 366 fps, 4147 KB/f;
  - ffvhuff: 203 fps, 1162 KB/f;
  - utvideo: 99 fps, 786 KB/f;
  - magicyuv: 97 fps, 795 KB/f;
  - x264 qp0 (lossless): 75 fps, 581 KB/f;
  - dnxhr hq: 83 fps;
  - mjpeg q2 (lossy): 149 fps, 121 KB/f;
  - FFV1 v3 rice: 42-43 fps, 0.69-0.70 cores, 469-470 KB/f;
  - FFV1 level 1: 43 fps.
- FFV1 v3 with the range coder misses 30 fps at t1 on YUY2 1080p (27-29 fps, cores/stream 1.00-1.10). It makes files about 21% smaller (370-373 vs 469-470 KB/f).
- FFV1 encode threading is slice-based:
  - t0 encode reaches 138 fps with 4 slices and 266 fps with 16 or 24 slices;
  - FFV1 level 1 does not thread on encode (43 fps at t0);
  - decode scales for every FFV1 variant, from about 40 fps at t1 to 300-440 fps at t0.
- Smallest lossless YUY2 1080p, smallest first: FFV1 range (370 KB/f), FFV1 rice (469), x264 qp0 (581), jpeg2000 (633), vp9 lossless (668), x265 lossless (702), utvideo (786). rawvideo is 4147 KB/f.
- Slowest encoders:
  - jpeg2000: 7 fps t1, 19 fps t0, 8 cores/stream;
  - prores_ks: 7 fps t1;
  - vp9 lossless: 11 fps t1, 48 fps t0;
  - x265 lossless: 21-32 fps at about 12 cores/stream.
- libx265 and libsvtav1 ignore `thread_count=1`: at t1, cores/stream x fps/30 gives about 8.5 busy cores for x265 lossless and about 10.9 for svtav1 crf30 p12 (inferred from the measured cores/stream and fps).
- NV12 1080p (smaller input than 4:2:2):
  - FFV1 s24 rice: 54 fps t1, 326 fps t0, 383 KB/f;
  - utvideo: 159 fps t1, 896 fps t0, 627 KB/f;
  - svtav1 lossless p12: 41 fps at 7.3 cores/stream, 545 KB/f.
- Bayer 12-bit 1080p with FFV1 v3:
  - storing the 4-plane split instead of the mosaic (as gray16) cuts the size from 2349-2413 to 1625-1647 KB/f;
  - it raises t1 encode from 8-10 to 14-15 fps, but neither layout reaches 30 fps on one core;
  - FFV1 v3 s24 on the quad split reaches 107 fps at t0 (2.46 cores/stream).
- PyAV 19.0.2 FFV1 **v4 native Bayer** (bayer_rggb16le, `-strict experimental`):
  - 1633 KB/f, 30 fps at t1 (1.00 cores/stream), 94 fps at t0, decode 29 fps (t1) and 330 fps (t0);
  - that is about 2x the t1 speed of v3 on the quad split (16 fps in PyAV 19) at the same size;
  - `../NOTES.md` records that v4 is experimental and that FFmpeg 8.1.2 cannot read it.
- Bayer 8-bit 1080p:
  - FFV1 s24 rice: 50 fps t1 (0.60 cores), 990 KB/f;
  - jpegls: 31 fps t1, 1095 KB/f;
  - ffvhuff: 269 fps, 2238 KB/f, which is bigger than raw (2074 KB/f).
- PyAV 19.0.2 vs 18.0.0 on the same configs:
  - file sizes are identical;
  - fps differences are within run-to-run noise on this loaded machine (FFV1 s4 YUY2 t1: 43.1 vs 43.4 fps; mjpeg t1: 168 vs 149 fps);
  - the 19.0.2 svtav1 crf30 p12 NV12 run (396 fps t1) has no 18.0.0 NV12 run to compare with.
- NVENC, one session (t1 on the libav side), 1080p:
  - h264 lossless NV12: 428 fps at 0.07 cores/stream, 594 KB/f;
  - hevc lossless NV12: 292 fps, 518 KB/f;
  - hevc lossless P010: 155 fps;
  - hevc CQ24 (lossy): 431 fps, 59 KB/f;
  - h264 lossless gray: 472 fps;
  - 720p runs at roughly 2x these rates;
  - software decode of HEVC lossless is slow: 12-24 fps at 1080p, t1.
- 720p (real JPEGs decoded to YUY2), t1:
  - FFV1 s24: 117 fps, 0.25 cores/stream, 130 KB/f;
  - utvideo: 252 fps;
  - mjpeg: 407 fps, 46 KB/f.
- Python still-image encoders at 1080p (`py_still__uv.json`), 1 worker / 8 workers:
  - simplejpeg from YUV planes: 204 / 991 fps (4:2:2) and 423 / 1921 fps (4:2:0);
  - cv2 YUY2 to BGR to JPEG: 196 / 758 fps;
  - JXL lossless e1 on Bayer12: 84 / 430 fps on the mosaic (2766 KB) and 90 / 493 fps on the quad split (1777 KB);
  - at 1 worker only: lossless JPEG (libjpeg-turbo SOF3) 14 fps, ljpeg 42 fps, JPEG-LS 25 fps, J2K reversible 6 fps, PNG 20 fps;
  - every library ran 3.5-7.6x faster with 8 workers than with 1, so they all release the GIL (inferred from the measured scaling).
- Debayer at 1080p (`debayer__pyav18.0.0_cv4.12.0.json`), 8-bit / 12-bit:
  - OpenCV bilinear: 0.96 / 1.31 ms;
  - OpenCV EA: 0.99 / 1.31 ms;
  - OpenCV VNG: 8.4 ms at 8-bit; at 12-bit it raises an OpenCV assertion;
  - libswscale: 5.0 / 7.9 ms.

## Tables

Median (min-max) of 3 reps. All measured.


### yuyv422 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| ffvhuff_median.nut | yuv422p | 1162 | 203 (147-209) | 0.15 (0.15-0.20) | 10.7 | 515 (495-533) | 0.22 (0.22-0.23) | 9.0 | 66.24 / 757.4 | 3x90 |
| utvideo_median.avi | yuv422p | 786 | 99 (86-101) | 0.30 (0.29-0.33) | 15.8 | 456 (444-512) | 0.39 (0.36-0.40) | 4.0 | 114.74 / 1009.11 | 3x90 |
| magicyuv_median.avi | yuv422p | 795 | 97 (88-106) | 0.31 (0.28-0.33) | 13.1 | 441 (310-516) | 0.40 (0.33-0.40) | 4.0 | 103.23 / 851.01 | 3x90 |
| rawvideo.nut | yuyv422 | 4147 | 366 (344-367) | 0.08 (0.08-0.08) | 4.0 | 409 (398-429) | 0.10 (0.09-0.12) | 3.7 | 795.12 / 732.94 | 3x90 |
| rawvideo_yuv422p.nut | yuv422p | 4147 | 309 (291-321) | 0.10 (0.09-0.10) | 5.4 | 407 (388-436) | 0.10 (0.09-0.12) | 3.9 | 731.19 / 731.12 | 3x90 |
| libx264_intra_qp0.mkv | yuv422p | 581 | 75 (70-86) | 0.38 (0.35-0.42) | 17.2 | 385 (320-394) | 0.41 (0.37-0.46) | 5.5 | 70.75 / 475.02 | 3x90 |
| libx264_intra_crf18.mp4 | yuv422p | 97 | 126 (126-145) | 0.23 (0.20-0.24) | 11.2 | 384 (373-387) | 0.23 (0.22-0.27) | 6.6 | 309.71 / 1567.76 | 3x90 |
| rawvideo.mkv | yuyv422 | 4147 | 280 (278-286) | 0.10 (0.10-0.10) | 4.6 | 351 (343-357) | 0.10 (0.09-0.11) | 3.9 | 757.32 / 717.14 | 3x90 |
| ffv1_l3_s24_crc_g1.mkv | yuv422p | 470 | 42 (40-42) | 0.70 (0.70-0.75) | 39.5 | 266 (259-271) | 0.90 (0.67-0.96) | 20.4 | 39.32 / 427.91 | 3x90 |
| ffv1_l3_s16_crc_g1.mkv | yuv422p | 470 | 43 (43-43) | 0.69 (0.69-0.69) | 38.8 | 266 (264-272) | 0.80 (0.66-0.89) | 21.2 | 39.35 / 443.12 | 3x90 |
| libsvtav1_intra_crf30_p12.mkv | yuv420p | 25 | 266 (218-303) | 1.23 (1.20-1.30) | 91.8 | 259 (248-268) | 1.25 (1.21-1.33) | 94.4 | 188.75 / 1286.53 | 3x90 |
| ffv1_l3_s24_crc_range_g1.mkv | yuv422p | 370 | 27 (27-32) | 1.10 (0.90-1.10) | 54.6 | 207 (207-217) | 0.97 (0.96-1.17) | 24.8 | 23.79 / 305.92 | 3x90 |
| dnxhd_dnxhr_hq.mov | yuv422p | 918 | 83 (72-89) | 0.36 (0.34-0.40) | 24.5 | 159 (154-167) | 0.50 (0.49-0.52) | 404.5 | 177.43 / 1374.76 | 3x90 |
| mjpeg_q2.mkv | yuv422p | 121 | 149 (133-158) | 0.20 (0.18-0.22) | 11.0 | 158 (152-161) | 0.19 (0.19-0.20) | 9.7 | 274.39 / 306.2 | 3x90 |
| ffv1_l3_s4_crc_g1.mkv | yuv422p | 469 | 43 (40-44) | 0.69 (0.68-0.73) | 37.1 | 138 (131-138) | 0.70 (0.67-0.71) | 22.8 | 39.73 / 429.91 | 3x90 |
| libsvtav1_intra_crf30_p10.mkv | yuv420p | 25 | 132 (115-137) | 1.48 (1.39-1.52) | 97.3 | 135 (134-141) | 1.43 (1.33-1.47) | 98.9 | 183.68 / 894.89 | 3x24 |
| prores_ks_hq.mov | yuv422p10le | 944 | 7 (7-7) | 4.28 (4.08-4.41) | 158.7 | 104 (96-106) | 4.84 (4.77-4.96) | 2.8 | 58.24 / 425.02 | 3x24 |
| ffv1_l3_s4_crc_range_g1.mkv | yuv422p | 373 | 29 (27-30) | 1.00 (0.97-1.08) | 63.5 | 103 (85-106) | 0.94 (0.88-1.06) | 28.3 | 24.0 / 301.5 | 3x90 |
| libvpx-vp9_intra_crf30.webm | yuv422p | 111 | 30 (25-31) | 0.98 (0.98-1.17) | 61.6 | 83 (71-84) | 1.68 (1.31-2.17) | 62.8 | 69.29 / 365.75 | 3x24 |
| libvpx-vp9_intra_lossless.webm | yuv422p | 668 | 11 (10-12) | 2.71 (2.48-2.93) | 61.7 | 48 (47-52) | 3.57 (2.17-3.75) | 61.7 | 19.15 / 148.36 | 3x24 |
| ffv1_l1_g1.mkv | yuv422p | 469 | 43 (41-44) | 0.69 (0.68-0.72) | 39.4 | 43 (41-44) | 0.69 (0.69-0.72) | 46.7 | 39.15 / 417.42 | 3x90 |
| libx265_intra_lossless.mkv | yuv422p | 702 | 21 (20-22) | 11.99 (11.97-12.21) | 130.3 | 32 (25-34) | 12.42 (11.74-12.54) | 117.7 | 18.88 / 171.7 | 3x24 |
| jpeg2000_dwt53.mkv | yuv422p | 633 | 7 (7-7) | 4.14 (4.12-4.32) | 192.4 | 19 (19-33) | 8.01 (7.54-8.57) | 209.5 | 6.77 / 32.15 | 3x24 |

### nv12 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| utvideo_median.avi | yuv420p | 627 | 159 (155-159) | 0.19 (0.18-0.19) | 8.6 | 896 (870-903) | 0.26 (0.24-0.27) | 2.4 | 166.44 / 1568.96 | 3x90 |
| ffv1_l3_s24_crc_g1.mkv | yuv420p | 383 | 54 (51-54) | 0.56 (0.55-0.58) | 30.3 | 326 (321-329) | 0.73 (0.68-0.80) | 16.8 | 48.89 / 535.38 | 3x90 |
| ffv1_l3_s24_crc_range_g1.mkv | yuv420p | 306 | 45 (45-45) | 0.66 (0.66-0.67) | 34.2 | 296 (295-302) | 1.08 (0.79-1.16) | 17.0 | 37.55 / 401.88 | 3x90 |
| mjpeg_q2.mkv | yuv420p | 111 | 220 (214-224) | 0.13 (0.13-0.14) | 5.5 | 222 (219-227) | 0.14 (0.13-0.14) | 5.6 | 406.97 / 414.75 | 3x90 |
| libsvtav1_intra_lossless_p12.mkv | yuv420p | 545 | 41 (40-42) | 7.27 (6.99-7.52) | 85.3 | 41 (38-42) | 7.46 (7.30-7.93) | 85.2 | 30.56 / 145.33 | 3x24 |

### bayer12 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| ffvhuff_median.nut | gray16le | 3747 | 161 (155-162) | 0.19 (0.18-0.19) | 12.1 | 328 (322-341) | 0.28 (0.24-0.29) | 49.3 | 58.33 / 536.78 | 3x90 |
| rawvideo.nut | bayer_rggb16le | 4147 | 287 (271-332) | 0.10 (0.08-0.10) | 5.3 | 317 (314-416) | 0.10 (0.09-0.14) | 7.3 | 605.07 / 656.23 | 3x90 |
| jpegls.nut | gray16le | 2506 | 23 (22-28) | 1.25 (1.09-1.35) | 54.2 | 273 (264-275) | 1.56 (1.52-1.60) | 1.3 | 23.14 / 28.07 | 3x24 |
| ffv1_l3_s24_crc_g1.mkv | gray16le | 2349 | 10 (9-11) | 3.03 (2.78-3.22) | 132.8 | 76 (74-79) | 3.53 (3.50-3.55) | 30.0 | 8.34 / 99.55 | 3x90 |
| ffv1_l3_s24_crc_range_g1.mkv | gray16le | 2349 | 10 (9-10) | 2.96 (2.90-3.20) | 127.9 | 73 (72-81) | 3.59 (3.32-3.80) | 30.1 | 8.38 / 97.62 | 3x90 |
| jpeg2000_dwt53.mkv | gray16le | 1844 | 4 (4-4) | 7.29 (7.19-7.56) | 292.1 | 44 (43-46) | 10.66 (10.51-10.76) | 96.7 | 3.77 / 28.07 | 3x24 |
| ffv1_l3_s4_crc_g1.mkv | gray16le | 2413 | 8 (8-9) | 3.53 (3.38-3.60) | 150.4 | 27 (27-29) | 3.78 (3.47-3.79) | 55.8 | 6.78 / 93.87 | 3x90 |
| libx265_intra_lossless.mkv | gray12le | 2822 | 14 (13-15) | 22.07 (20.92-22.91) | 141.0 | 24 (24-24) | 23.59 (23.32-23.61) | 118.4 | 11.44 / 105.32 | 3x24 |

### bayer12_quad 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| ffvhuff_median.nut | gray16le | 1829 | 171 (146-173) | 0.18 (0.17-0.20) | 12.3 | 447 (431-458) | 0.26 (0.24-0.29) | 49.3 | 68.67 / 674.97 | 3x90 |
| rawvideo.nut | gray16le | 4147 | 328 (321-328) | 0.09 (0.09-0.09) | 4.8 | 412 (408-421) | 0.10 (0.10-0.10) | 3.9 | 687.02 / 719.29 | 3x90 |
| jpegls.nut | gray16le | 1605 | 20 (19-20) | 1.50 (1.48-1.54) | 58.6 | 242 (235-244) | 1.97 (1.93-1.99) | 1.3 | 20.73 / 20.68 | 3x24 |
| ffv1_l3_s24_crc_g1.mkv | gray16le | 1647 | 15 (15-15) | 2.00 (1.96-2.01) | 88.9 | 107 (107-116) | 2.46 (2.28-2.50) | 23.9 | 11.97 / 143.29 | 3x90 |
| ffv1_l3_s24_crc_range_g1.mkv | gray16le | 1647 | 15 (13-16) | 2.03 (1.88-2.27) | 83.5 | 104 (101-110) | 2.50 (2.30-2.51) | 25.6 | 11.61 / 141.35 | 3x90 |
| ffv1_l3_s4_crc_g1.mkv | gray16le | 1625 | 14 (14-15) | 2.07 (1.92-2.09) | 82.8 | 48 (41-54) | 2.13 (1.95-2.50) | 38.6 | 11.93 / 142.38 | 3x90 |
| jpeg2000_dwt53.mkv | gray16le | 1746 | 3 (3-4) | 8.46 (8.24-8.48) | 309.0 | 40 (39-42) | 11.84 (11.68-11.95) | 97.6 | 3.29 / 26.73 | 3x24 |
| libx265_intra_lossless.mkv | gray12le | 2072 | 15 (15-16) | 21.48 (21.11-21.74) | 142.3 | 26 (20-27) | 22.87 (22.71-23.16) | 82.7 | 14.21 / 120.92 | 3x24 |

### bayer8 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | bayer_rggb8 | 2074 | 672 (663-696) | 0.04 (0.04-0.05) | 2.3 | 825 (817-842) | 0.05 (0.05-0.06) | 1.9 | 1452.38 / 1421.19 | 3x90 |
| ffvhuff_median.nut | gray | 2238 | 269 (260-273) | 0.10 (0.10-0.12) | 9.4 | 593 (585-628) | 0.21 (0.20-0.22) | 7.0 | 91.12 / 883.47 | 3x90 |
| jpegls.nut | gray | 1095 | 31 (30-32) | 0.98 (0.94-1.00) | 36.9 | 372 (359-382) | 1.25 (1.23-1.37) | 0.9 | 34.44 / 34.42 | 3x24 |
| ffv1_l3_s24_crc_g1.mkv | gray | 990 | 50 (46-51) | 0.60 (0.58-0.64) | 28.2 | 310 (308-311) | 0.51 (0.31-0.54) | 13.0 | 39.27 / 444.63 | 3x90 |
| ffv1_l3_s24_crc_range_g1.mkv | gray | 916 | 23 (21-23) | 1.30 (1.28-1.40) | 54.6 | 170 (163-176) | 1.71 (1.68-1.79) | 15.8 | 18.29 / 209.21 | 3x90 |
| ffv1_l3_s4_crc_g1.mkv | gray | 1087 | 47 (46-53) | 0.62 (0.56-0.64) | 28.9 | 147 (115-150) | 0.64 (0.54-0.83) | 17.4 | 39.15 / 443.69 | 3x90 |
| libx265_intra_lossless.mkv | gray | 1377 | 34 (33-36) | 8.85 (8.61-9.38) | 90.6 | 61 (57-62) | 9.65 (9.43-9.84) | 57.2 | 19.77 / 180.47 | 3x24 |
| jpeg2000_dwt53.mkv | gray | 743 | 8 (8-9) | 3.54 (3.44-3.56) | 136.2 | 57 (57-71) | 6.02 (5.94-6.43) | 89.0 | 8.17 / 55.1 | 3x24 |

### raw12_packed 1080p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | gray | 3110 | 452 (424-453) | 0.07 (0.07-0.07) | 3.1 | - | - | - | 962.39 / - | 3x90 |

### yuyv422 720p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| utvideo_median.avi | yuv422p | 297 | 252 (250-253) | 0.12 (0.12-0.12) | 5.1 | 1534 (1467-1548) | 0.16 (0.15-0.17) | 1.3 | 303.76 / 2596.11 | 3x90 |
| rawvideo.nut | yuyv422 | 1843 | 688 (662-721) | 0.05 (0.04-0.05) | 2.2 | 895 (819-926) | 0.04 (0.03-0.05) | 1.9 | 1474.27 / 1466.48 | 3x90 |
| ffv1_l3_s24_crc_g1.mkv | yuv422p | 130 | 117 (116-119) | 0.24 (0.24-0.24) | 16.9 | 577 (574-600) | 0.29 (0.21-0.33) | 11.1 | 134.63 / 1194.25 | 3x90 |
| mjpeg_q2.mkv | yuv422p | 46 | 407 (404-407) | 0.07 (0.07-0.07) | 3.6 | 378 (368-397) | 0.08 (0.07-0.08) | 5.0 | 743.16 / 740.83 | 3x90 |

### nv12 720p PyAV 18.0.0

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| utvideo_median.avi | yuv420p | 239 | 338 (328-339) | 0.09 (0.08-0.09) | 3.9 | 2030 (1790-2041) | 0.09 (0.09-0.14) | 1.1 | 393.03 / 3089.49 | 3x90 |
| rawvideo.nut | nv12 | 1382 | 923 (875-964) | 0.03 (0.03-0.04) | 1.6 | 1236 (1159-1278) | 0.03 (0.03-0.05) | 1.6 | 1904.35 / 1881.81 | 3x90 |
| ffv1_l3_s24_crc_g1.mkv | yuv420p | 125 | 141 (140-142) | 0.21 (0.21-0.21) | 13.5 | 735 (700-766) | 0.17 (0.16-0.31) | 8.4 | 145.35 / 1276.74 | 3x90 |
| mjpeg_q2.mkv | yuv420p | 44 | 507 (490-511) | 0.06 (0.06-0.06) | 3.0 | 487 (466-495) | 0.06 (0.06-0.06) | 3.0 | 916.19 / 895.61 | 3x90 |

### yuyv422 1080p PyAV 19.0.2

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | yuyv422 | 4147 | 335 (325-351) | 0.09 (0.09-0.09) | 3.9 | 418 (416-420) | 0.09 (0.08-0.10) | 3.6 | 765.64 / 736.54 | 3x90 |
| ffv1_l3_s24_crc_g1.mkv | yuv422p | 470 | 42 (42-42) | 0.70 (0.70-0.72) | 40.6 | 226 (218-235) | 1.01 (0.80-1.05) | 22.4 | 38.92 / 399.24 | 3x90 |
| mjpeg_q2.mkv | yuv422p | 121 | 168 (162-169) | 0.18 (0.17-0.18) | 7.7 | 177 (176-179) | 0.17 (0.17-0.17) | 6.9 | 317.16 / 329.85 | 3x90 |
| ffv1_l3_s4_crc_g1.mkv | yuv422p | 469 | 43 (43-43) | 0.69 (0.69-0.69) | 38.1 | 134 (132-136) | 0.69 (0.65-0.70) | 23.8 | 40.14 / 438.58 | 3x90 |

### nv12 1080p PyAV 19.0.2

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| libsvtav1_intra_crf30_p12.mkv | yuv420p | 25 | 396 (381-403) | 0.97 (0.96-1.04) | 53.7 | 384 (374-385) | 1.01 (0.95-1.02) | 56.3 | 217.62 / 1399.83 | 3x90 |

### bayer12 1080p PyAV 19.0.2

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| ffv1_l4_experimental_s4_crc_g1.mkv | bayer_rggb16le | 1633 | 30 (29-30) | 1.00 (0.99-1.02) | 36.9 | 94 (91-95) | 0.93 (0.89-1.10) | 14.3 | 29.32 / 330.17 | 3x90 |

### bayer12_quad 1080p PyAV 19.0.2

| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |
|---|---|---|---|---|---|---|---|---|---|---|
| ffv1_l3_s4_crc_g1.mkv | gray16le | 1625 | 16 (15-16) | 1.91 (1.86-1.94) | 85.0 | 53 (52-55) | 1.98 (1.89-2.02) | 34.9 | 12.28 / 149.18 | 3x90 |

### NVENC (threads=1 on the libav side)

| config | source | res | enc fps | cores/stream | p99 ms | KB/frame | dec fps (software) | nvidia-smi before -> after (sessions, util) |
|---|---|---|---|---|---|---|---|---|
| h264_nvenc_intra_lossless.mkv | gray (yuv420p) | 1080p | 472 (321-534) | 0.06 (0.05-0.09) | 3.1 | 447 | 123 | 0, 12 % -> 0, 9 % |
| h264_nvenc_intra_lossless.mkv | nv12 (nv12) | 1080p | 428 (375-461) | 0.07 (0.06-0.08) | 3.4 | 594 | 87 | 0, 18 % -> 0, 14 % |
| hevc_nvenc_intra_cq.mp4 | nv12 (nv12) | 1080p | 431 (431-437) | 0.06 (0.04-0.06) | 2.6 | 59 | 95 | 0, 15 % -> 0, 18 % |
| hevc_nvenc_intra_lossless.mkv | bayer8 (yuv420p) | 1080p | 183 (175-187) | 0.10 (0.09-0.12) | 6.4 | 1370 | 17 | 0, 26 % -> 0, 14 % |
| hevc_nvenc_intra_lossless.mkv | nv12 (nv12) | 1080p | 292 (287-294) | 0.07 (0.06-0.07) | 3.8 | 518 | 24 | 0, 15 % -> 0, 11 % |
| hevc_nvenc_intra_lossless.mkv | p010le (p010le) | 1080p | 155 (154-155) | 0.13 (0.12-0.15) | 7.5 | 1423 | 12 | 0, 12 % -> 0, 16 % |
| h264_nvenc_intra_lossless.mkv | gray (yuv420p) | 720p | 876 (805-990) | 0.03 (0.03-0.04) | 1.4 | 173 | 335 | 3, 9 % -> 0, 8 % |
| h264_nvenc_intra_lossless.mkv | nv12 (nv12) | 720p | 857 (754-869) | 0.03 (0.03-0.03) | 1.6 | 202 | 255 | 0, 6 % -> 0, 8 % |
| hevc_nvenc_intra_cq.mp4 | nv12 (nv12) | 720p | 826 (747-892) | 0.03 (0.02-0.03) | 1.3 | 21 | 255 | 0, 43 % -> 3, 8 % |
| hevc_nvenc_intra_lossless.mkv | bayer8 (yuv420p) | 720p | 374 (367-377) | 0.04 (0.04-0.05) | 3.4 | 559 | 51 | 0, 27 % -> 0, 18 % |
| hevc_nvenc_intra_lossless.mkv | nv12 (nv12) | 720p | 634 (614-641) | 0.04 (0.03-0.04) | 1.8 | 213 | 69 | 0, 5 % -> 0, 11 % |
| hevc_nvenc_intra_lossless.mkv | p010le (p010le) | 720p | 327 (323-328) | 0.06 (0.06-0.06) | 3.6 | 622 | 31 | 0, 12 % -> 0, 29 % |

### Python still-image encoders and debayer

See `bench_summary.md` (sections "Python still-image encoders" and "Debayer cost"), from `py_still__uv.json` and `debayer__pyav18.0.0_cv4.12.0.json`.
