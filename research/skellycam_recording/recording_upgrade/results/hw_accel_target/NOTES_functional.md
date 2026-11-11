# hw_accel_target: functional tests on Gerald through PyAV 19.0.2 (Intel UHD 770 now present)

Stage: functional only. **No timing, throughput or CPU numbers here** (other agents were running). The PSNR values are
quality numbers. Timed benchmarks are written and smoke-tested (smoke outputs deleted); they are listed in the bench
manifest at the end, for the 23:00 run.

Labels: **measured** (result file), **source** (primary source, accessed 2026-11-09), **code** (file:line),
**inferred** (kept short and marked). Paths are relative to the repo root unless absolute. `R` =
`research/skellycam_recording/recording_upgrade/results/hw_accel_target/`, `S` =
`research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/`. Media (shows the room):
`C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/hw_accel_target/functional/`.

## 1. Bottom line

- measured: with the iGPU present, **QSV encode works through PyAV 19.0.2** for `h264_qsv`, `hevc_qsv`, `vp9_qsv` and `mjpeg_qsv`. Each one does all-intra (60/60 key frames) and gop30 (2 key frames in 60), decodes back with the software decoder (60/60 frames), and writes MKV and MP4 (`R/functional_pyav19.md`).
- measured: **`vp9_qsv` is the one royalty-free, inter-frame hardware encoder that works on Gerald.** All-intra, gop30, MKV, WebM and MP4 all work (`R/functional_pyav19.md`, rows `vp9_qsv`).
- measured: `mjpeg_qsv` is a royalty-free all-intra hardware encoder. It takes `yuyv422` natively and writes **4:2:2 JPEG** (`yuvj422p`, Baseline). From `nv12` it writes 4:2:0.
- measured: `hevc_qsv` takes `yuyv422` natively and writes **HEVC Rext 4:2:2 8-bit** (`yuv422p`). It is the only 4:2:2 hardware video encode found on Gerald.
- measured: `av1_qsv` fails on the UHD 770: `Current codec type is unsupported`, then `avcodec_open2` returns `Function not implemented`.
- measured: `av1_nvenc` (`Codec not supported`, `No capable devices found`), `av1_d3d12va` (on NVIDIA: `Driver does not support requested features`; on Intel: `Driver does not support any RC mode compatible with selected options`) and `av1_mf` (Intel AV1 MFT; header write fails with `Invalid data found when processing input`) all fail.
  - So **no AV1 hardware encode exists on Gerald through any API**, which agrees with `results/gpu_encode/NOTES.md` §1.
- measured: the AMF encoders fail as expected: `DLL amfrt64.dll failed to open`, then `Failed to create hardware device context (AMF)`.
- measured: **QSV hardware decode of the cameras' 4:2:2 MJPEG works.**
  - `mjpeg_qsv` decodes all 10 frames for each of the three camera sets.
  - The output is `nv12`, so the 4:2:2 chroma comes back as 4:2:0. PSNR against the CPU decode is Y 66.9–69.5 dB and all-planes 57.6–61.5 dB.
  - With `HWAccel('qsv', is_hw_owned=True)` it outputs `qsv` GPU frames.
  - NVDEC still fails on the same frames (`mjpeg_cuvid`, `mjpeg`+cuda: `cuvidCreateDecoder ... CUDA_ERROR_NO_DEVICE`).
- measured: two **pipeline pitfalls** that affect any skellycam implementation (§6):
  - decoded MJPEG frames carry `pict_type=I`, which forces key frames in GOP encoders;
  - `VideoFrame.reformat()` keeps full-range JPEG samples when it converts to `nv12`.

## 2. Machine state (read-only)

- measured (`R/system_probe_1700.txt`, 2026-11-09 16:39 local):
  - `Get-PnpDevice -Class Display`: `OK True Intel(R) UHD Graphics 770` (PCI\VEN_8086&DEV_A780&SUBSYS_88821043), `OK True NVIDIA GeForce RTX 3070` and `OK True Parsec Virtual Display Adapter`.
  - The Intel driver is 32.0.101.7088, dated 2026-06-16 (Win32_VideoController).
  - NVIDIA: 610.88; `nvidia-smi -q -d ENCODER_STATS`: Active Sessions 0.
  - The processes `parsecd` (2), `sunshine` and `sunshinesvc` were running.
- measured: the PyAV 19.0.2 wheel reports libavcodec 63.1.102 and `hwdevices_available` = cuda, dxva2, qsv, d3d11va, d3d12va, amf (`R/functional_pyav19.json` keys `libavcodec`, `hwdevices_available`).
- measured: QSV device selection, from the FFmpeg log in `R/functional_pyav19.md` §log excerpts:
  - `Selecting d3d11va adapter 1`;
  - `Using device 8086:a780 (Intel(R) UHD Graphics 770)`;
  - `Use Intel(R) oneVPL ... API version is 2.16`, `implementation version is 2.15`.
  - The encoders log `Initialized an internal MFX session using hardware accelerated implementation`.
- measured: nvidia-smi `sessionCount` read while each encoder was open (after frame 5), from the JSON field `nvenc_sessions_while_open`:
  - QSV encoders 0. One h264_qsv row read 1, which is a session from another process;
  - NVENC 1 (2 in one row);
  - `*_d3d12va` (default adapter) 1;
  - `*_mf` 1.
  - The per-encoder before/after readings are in `nvidia_smi_per_encoder`. Every before/after count was 0.

## 3. Encoder matrix (PyAV 19.0.2, 60 frames, real-camera-derived input)

Script: `S/pyav19_functional.py`. Results: `R/functional_pyav19.{json,md}`. Inputs:

- `yuy2_1080p`: the corpus `c930e_1080p_yuy2` (8 real YUY2 frames, looped);
- `mjpeg_720p`: `c930e_720p_flash`, 60 JPEGs;
- `mjpeg_1080p`: `c930e_1080p`, 19 JPEGs, looped.

All conversions were done with PyAV `reformat()`, and outputs were checked with ffprobe `-show_frames key_frame,pict_type`.

| encoder | opens | all-intra (keys/60) | gop30 from YUY2 (keys/60, types) | pix_fmt accepted (probe) | output | MKV | MP4 | WebM | NVENC session while open |
|---|---|---|---|---|---|---|---|---|---|
| h264_qsv | yes | 60 | 2, I+P | nv12 only | H.264 High 4:2:0 | yes | yes | n/a | 0 |
| hevc_qsv | yes | 60 | 2, I+B (low-delay B: has_b_frames=0, pts=dts) | nv12, **yuyv422** | Main 4:2:0 / **Rext 4:2:2** | yes | yes | n/a | 0 |
| vp9_qsv | yes | 60 | 2, I+P | nv12 only | VP9 Profile 0 4:2:0 | yes | yes | **yes** | 0 |
| mjpeg_qsv | yes | 60 (intra codec) | n/a | nv12, **yuyv422** | Baseline yuvj420p / **yuvj422p** | yes | yes | n/a | 0 |
| av1_qsv | **no** | – | – | none | `Current codec type is unsupported` | – | – | – | – |
| h264_nvenc | yes | 60 (`gop_size=0`) | 2, I+P | nv12, yuv420p (4:2:2 inputs rejected) | High 4:2:0 | yes | yes | n/a | 1 |
| hevc_nvenc | yes | 60 (`gop_size=0`) | 2, I+P | nv12, yuv420p | Main 4:2:0 | yes | yes | n/a | 1 |
| av1_nvenc | **no** | – | – | – | `Codec not supported` | – | – | – | – |
| h264_d3d12va | yes (hwctx only) | 60 | 2, I+P | nv12 only | Main 4:2:0 | **no** (`Invalid data found when processing input`) | yes | n/a | 1 (default adapter = NVIDIA) |
| hevc_d3d12va | yes (hwctx only) | 60 | 2, I+P | nv12 only | Main 4:2:0 | **no** (same) | yes | n/a | 1 |
| av1_d3d12va | **no** | – | – | – | see §1 | – | – | – | – |
| h264_mf (`hw_encoding=1`) | yes | 60 | 2, I+P | nv12 only | Constrained Baseline 4:2:0 | yes | yes | n/a | 1 |
| hevc_mf | yes | 60 | 2, I+P | nv12 only | Main 4:2:0 | yes | yes | n/a | 1 |
| av1_mf | **no** | – | – | – | Intel AV1 MFT; header write `Invalid data` | – | – | – | – |
| h264/hevc/av1_amf | **no** | – | – | – | `DLL amfrt64.dll failed to open` | – | – | – | – |
| libsvtav1 (CPU, preset 10) | yes | 60 | 2, I+P | yuv420p | AV1 Main 4:2:0 | yes | yes | yes | – |
| libvpx-vp9 (CPU, realtime, cpu-used 8) | yes | 60 | 2, I+P | yuv420p, **yuv422p** | Profile 0 / **Profile 1 4:2:2** | yes | yes | yes | – |
| mjpeg (CPU) | yes | 60 | n/a | yuvj420p, yuvj422p (and yuv4xxp per codec list) | Baseline | yes | yes | n/a | – |
| ffv1 (CPU, level 3, 16 slices) | yes | 60 | key 2/60, pict_type I on all 60 (FFV1 context-reset semantics) | yuv420p, yuv422p | lossless (PSNR 99 = identical) | yes | yes | n/a | – |

Details (all measured, `R/functional_pyav19.md` unless noted):

- Format probe (4 frames per pix_fmt):
  - QSV encoders reject `yuv420p`, `yuv422p` and `nv16` with `Specified pixel format ... is not supported` and list their formats (h264_qsv: `nv12, qsv`; mjpeg_qsv: `nv12, yuyv422, bgra, qsv`).
  - The advertised lists come from `av.Codec(name,'w').video_formats`, JSON key `encoder_advertised_formats`: hevc_qsv lists `yuyv422`/`y210le`, and NVENC lists `nv16`/`p210le`. NVENC still rejects every 4:2:2 input on Ampere, which matches the NVIDIA support matrix (`results/gpu_encode/NOTES.md` §7.1, RTX 3070 row "H.264 4:2:2 NO", "HEVC 4:2:2 NO").
- The `HWAccel(type)` frames-context mode ("hwctx"):
  - It works for NVENC (`cuda`) and is required for D3D12VA.
  - For every QSV encoder it fails: `AVHWFramesContext: Could not create the texture (80070057)`, then `Error initializing a child frames context` and `Error creating an internal frame pool`.
  - Feeding software NV12/YUY2 frames to the QSV encoders works (they upload internally).
  - inferred: PyAV's auto-built QSV frames pool is not configured the way the D3D11 child expects. NOT VERIFIED against the PyAV source.
- MF adapter choice: the FFmpeg log enumerates `NVIDIA H.264 Encoder MFT`, then `Intel® Quick Sync Video H.264 Encoder MFT`, and picks `MFT name: 'NVIDIA H.264 Encoder MFT'`. HEVC does the same with `NVIDIA HEVC Encoder MFT` over `Intel® Hardware H265 Encoder MFT`. `av1_mf` picks `Intel® Hardware Accelerated AV1 Encoder MFT` (the only AV1 MFT) and fails.
  - NOT TESTED: forcing MF onto the Intel MFT. The FFmpeg mf wrapper option for that was not checked.
- D3D12VA adapter probe (`HWAccel('d3d12va', device=i)`, JSON `d3d12_adapter`):
  - devices 0 and 2: `Using device 10de:2484 (NVIDIA GeForce RTX 3070)`, NVENC session 1;
  - device 1: `Using device 8086:a780 (Intel(R) UHD Graphics 770)`. **h264/hevc_d3d12va work on the Intel iGPU too**, with NVENC sessions 0. hevc on Intel logs `Driver does not support P-frames, replacing them with B-frames`;
  - device 3: `Microsoft Basic Render Driver`, fails.
- D3D12VA MKV: the header write fails with `Invalid data found when processing input`, as it did in `results/gpu_encode/ff_functional.md`. MP4 works. The first full run used MKV for d3d12va and was replaced by the MP4 re-run `R/functional_pyav19_d3d12.json`; the replaced records are kept in the JSON key `superseded_records`.
- NVENC all-intra needs `gop_size=0` (`code: FFmpeg n9.0.2 libavcodec/nvenc.c:1761-1767`, cited in `results/gpu_encode/NOTES.md` §3).
- Decode-back PSNR, from software-decoding each file and comparing it with the frames actually fed. This is method v2, recomputed by `S/recompute_psnr.py`; the v1 values are kept as `decode_back_v1`:
  - all-intra, real YUY2 1080p: h264_qsv Y 50.2 dB; hevc_qsv 50.8; vp9_qsv 53.1; mjpeg_qsv 48.9; h264_nvenc 50.5; hevc_nvenc 50.1; h264_d3d12va 47.7; hevc_d3d12va 48.2; h264_mf 47.9; hevc_mf 51.5; libsvtav1 47.2; libvpx-vp9 50.6; mjpeg (CPU, PyAV defaults) 38.6; ffv1 identical.
  - These are default rate-control settings (QSV: CQP default, per its own warning; d3d12va: `No quality level set; using default (25)`). The file sizes differ, so these are **not** a quality-per-bit comparison.

## 4. Decode matrix (PyAV 19.0.2; one child process per test, 60 s timeout, `allow_software_fallback=False`)

Results: `R/functional_pyav19.md` §Decode tests and §Extra; JSON keys `decode` and `decode_extra`. The 4:2:0 JPEG control was made by the PyAV `mjpeg` encoder (yuvj420p) from decoded 1080p camera frames.

| input | mjpeg (CPU) | mjpeg_qsv (sw out) | mjpeg_qsv (qsv frames) | mjpeg_cuvid | mjpeg + HWAccel cuda | mjpeg + HWAccel qsv / d3d11va / d3d12va / dxva2 |
|---|---|---|---|---|---|---|
| camera 4:2:2 720p / 1080p / c922 1080p | yuvj422p | **ok, nv12** (Y 66.9–69.5 dB vs CPU) | **ok** (`qsv`) | **fail** (`avcodec_send_packet()` generic error) | **fail** (`CUDA_ERROR_NO_DEVICE`, `Failed setup for format cuda`) | decoded **in software**: the mjpeg decoder has no hw config for these devices, and PyAV did not raise |
| control 4:2:0 1080p | yuvj420p | ok, nv12 (Y 74.7) | ok | **ok**, nv12 (Y 74.5) | **ok**, nv12 (Y 74.5) | software (same reason) |

- measured: `av.Codec('mjpeg','r').hardware_configs` lists only cuda (JSON `mjpeg_decoder_hw_configs` = [2] = cuda), and every `mjpeg + HWAccel(qsv/d3d11va/d3d12va/dxva2)` row has `decoder_has_hw_config_for_device` False with output `yuvj422p`. **FFmpeg has no D3D11VA/D3D12VA/DXVA2 MJPEG hwaccel.** The QSV path is the separate `mjpeg_qsv` decoder.
- measured: in this PyAV harness `mjpeg_cuvid` failed quickly instead of hanging. The ffmpeg CLI hung for over 120 s on the same frames (`results/gpu_encode/NOTES.md` §5). The 60 s child timeout was never hit.
- Encoded-stream decode. The files are this run's h264_qsv / hevc_qsv / vp9_qsv / libsvtav1 outputs, intra and gop30. The PSNR is against the default software decoder.
  - measured: `h264_qsv`, `hevc_qsv`, `vp9_qsv`, `av1_qsv`, `h264_cuvid`, `hevc_cuvid`, `vp9_cuvid` and `av1_cuvid` all decode 60/60 frames, bit-identical to software (PSNR 99 = identical).
    - inferred: the UHD 770 decodes AV1 even though it cannot encode it.
  - measured: native `h264`/`hevc`/`vp9` + `HWAccel(d3d11va | d3d12va | cuda | dxva2)` all work, bit-identical. d3d12va logs `Using device 10de:2484 (NVIDIA ...)`, so the default adapter is NVIDIA.
  - measured: native decoders + `HWAccel('qsv')` fail with `Hardware accelerated decode requested but no stream is compatible`. QSV decode goes through the `*_qsv` decoders.
  - measured: AV1 + HWAccel through `av.open` fails, because PyAV opens AV1 with `libdav1d` (which has no hw configs).
    - FFmpeg's native `av1` decoder without hwaccel fails with `Your platform doesn't support hardware accelerated AV1 decoding`.
    - With hwaccel attached to a standalone CodecContext it fails with `get_buffer() failed` (`S/decode_av1_native.py`).
    - NOT VERIFIED: native-av1 hwaccel decode via PyAV. This is a harness limitation, not a hardware result.
  - measured: the **HEVC 4:2:2** file from `hevc_qsv` decodes with `hevc_qsv` (`yuyv422`, identical) and in software. It fails on NVIDIA: `hevc_cuvid` errors, and `hevc`+cuda gives `Hardware is lacking required capabilities`. d3d11va, d3d12va (NVIDIA adapter) and dxva2 give `Operation not permitted` at `avcodec_send_packet()`.

## 5. What fits the hardware target on Gerald (functional view only)

| candidate | encode on Gerald's RTX 3070 | encode on Gerald's UHD 770 (RPL-S) | royalty-free (G7) | 4:2:2 kept | notes |
|---|---|---|---|---|---|
| H.264 | yes (nvenc, d3d12va, mf) | yes (qsv, d3d12va dev 1) | no | no | measured |
| HEVC | yes | yes; 4:2:2 Rext only on Intel | no | Intel only | measured |
| VP9 | **no** (no `vp9_nvenc` in FFmpeg) | **yes (vp9_qsv)** | yes | no (Profile 0) | measured; inferred: no NVENC VP9 encoder, consistent with the NVENC matrix having no VP9 column (`results/gpu_encode/NOTES.md` §7.6) |
| AV1 | no (Ampere) | no (RPL Xe-LP) | yes | – | measured; vendor tables in `results/gpu_encode/NOTES.md` §7 |
| MJPEG/JPEG | no NVENC JPEG (nvJPEG CUDA path, `results/gpu_encode/NOTES.md` §6) | **yes (mjpeg_qsv), 4:2:2 from YUY2** | yes | yes (Intel) | measured |

- inferred (minimal): on Gerald no single royalty-free codec is hardware-encoded on **both** GPUs. VP9 and JPEG are hardware-encoded only on the Intel iGPU; H.264 and HEVC on both. The per-generation picture for other machines is in the source notes (`R/NOTES_sources_*.md`, other agents) and is not repeated here.

## 6. Pipeline pitfalls found (affect a skellycam implementation)

1. measured: **decoded MJPEG frames force key frames.**
   - The PyAV mjpeg decoder sets `pict_type=I`, and `reformat()` copies it. Checked in the scratchpad: `after reformat: 1`.
   - Fed to a GOP encoder, every frame then becomes a key frame:
     - h264_qsv, hevc_qsv, h264/hevc_d3d12va, h264/hevc_mf, libsvtav1 and libvpx-vp9 gop30 from MJPEG gave **60/60 key frames**;
     - h264/hevc_nvenc gave 2 key frames but pict_type I on all 60 (non-IDR I frames);
     - only vp9_qsv ignored it (2/60). ffv1 gave 2/60 key frames, as it does from YUY2.
   - Setting `frame.pict_type = PictureType.NONE` gives 2 key frames in 60 for every encoder (stage `gop_pictreset`, `R/functional_pyav19_pictreset.json`).
2. measured: **colour range.**
   - A decoded camera JPEG frame is `yuvj422p` with `color_range=2` (JPEG) and Y samples 2..246.
   - `reformat(format='nv12')` keeps Y 2..246 and the JPEG tag. `reformat(format='nv12', dst_color_range=1)` gives Y 18..227, tagged MPEG (scratchpad `rng2.py`; JSON field `fed_frame0` per record).
   - The encoders still tag their streams `tv` or leave the range unspecified (ffprobe `color_range`, `R/functional_pyav19.json`). So the MJPEG-sourced files in this run hold full-range samples in streams labelled limited range.
   - `mjpeg_qsv` fed limited-range NV12 (from YUY2) writes JPEGs tagged `pc`.
   - inferred: a real pipeline must convert range explicitly, or signal it. The 23:00 bench scripts pass `dst_color_range=1`.
3. measured: the PSNR method matters. PyAV 19 `reformat()` converts range only when the source is an untagged `yuvj*` frame, and keeps it when the frame is tagged. v1 PSNR therefore under-read `mjpeg` from YUY2 (27.5 dB v1, 38.6 dB v2). Every other row is unchanged (difference 0.0 dB).

## 7. Limits

- Functional only. Short clips: 60 frames from 8 or 19 real frames looped, plus 60 real 720p frames.
- One machine. Only NVIDIA Ampere and Intel Xe-LP (RPL-S) are physically tested.
- Default encoder settings, so PSNR is not comparable at equal bitrate.
- The Parsec/Sunshine processes were running. nvidia-smi showed 0 sessions before and after each encoder group. One reading of 1 or 2 during open came from another process.
- Not tested: Chromium playback of these files (chromium_codecs topic); crash truncation (crash_resilience); forcing h264_mf/hevc_mf onto the Intel MFT; QSV `hwctx` with a manually sized frames pool.

## 8. Scripts and commands (repo root)

| script | purpose | command |
|---|---|---|
| `S/common.py` | paths, corpus readers, ffprobe frame probe (inspection only) | imported |
| `S/pyav19_functional.py` | full functional matrix + decode matrix | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/pyav19_functional.py` |
| same, d3d12va re-run (MP4) | replaces the d3d12va MKV records | `uv run --script .../pyav19_functional.py --only h264_d3d12va,hevc_d3d12va,av1_d3d12va --skip-decode --tag d3d12`, then `uv run --script .../merge_functional.py d3d12` |
| same, pict_type reset stage | gop30 from MJPEG with `pict_type` reset | `uv run --script .../pyav19_functional.py --only h264_qsv,hevc_qsv,vp9_qsv,mjpeg_qsv,h264_nvenc,hevc_nvenc,h264_d3d12va,hevc_d3d12va,h264_mf,hevc_mf,libsvtav1,libvpx-vp9,mjpeg,ffv1 --stage pictreset --tag pictreset`, then `.../merge_functional.py pictreset --append` |
| same, decode stage | decode matrix with PSNR v2 + hw-config check | `uv run --script .../pyav19_functional.py --stage decode --tag decode`, then `.../merge_functional.py decode --append` |
| `S/recompute_psnr.py` | PSNR v2 for all encode records | `uv run --script .../recompute_psnr.py` |
| `S/decode_av1_native.py` | native `av1` + HWAccel check | `uv run --script .../decode_av1_native.py` |
| `S/merge_functional.py` | merges subset runs into the main JSON/MD | see above |
| `S/benchlib.py` | background-load record, nvidia-smi sampler, PyAV input builders | imported |
| `S/bench_encode_stream.py` | **timing** (23:00): single-stream fps + CPU ms/frame | manifest below |
| `S/bench_concurrent.py` | **timing** (23:00): 1/4/8/16 streams + session limit probe | manifest below |

- `S/` was copied from `scripts/gpu_encode/` (common.py, benchlib.py, pyav_functional.py, bench_pyav_concurrent.py) and adapted. `gpu_encode` files were not edited.
- `ff_functional.py` was not carried over, because the ffmpeg CLI is for inspection only now.
- The system probe was PowerShell, read-only, saved to `R/system_probe_1700.txt`.

## 9. Bench manifest (23:00; one item at a time, quiet machine)

- Every bench records `background_load_before` (10 s typeperf `\Processor(_Total)\% Processor Time`, the top processes by CPU seconds over the same window, and nvidia-smi sessions), plus the flag `load_over_15pct`.
- Every bench writes JSON to `R/bench/`.
- Smoke-tested at 10 frames into the scratchpad; outputs deleted, numbers discarded.
- `cpu_ms_per_frame` is the whole process (psutil user+system, all threads, including driver threads). It includes building the input frame, and decode/convert for the MJPEG sources. Subtract the `none` rows (B-DEC) for encode-only cost.
- MJPEG sources reset `pict_type` and convert to limited range (§6).

| id | prio | est min | what | command |
|---|---|---|---|---|
| B-QSV-1 | 1 | 20 | per-stream fps + CPU/frame, QSV encoders, 720p/1080p, sources nv12 / yuy2 / yuy2native / mjpeg_cpu / mjpeg_qsv, intra + gop30 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py --encoders h264_qsv,hevc_qsv,vp9_qsv,mjpeg_qsv --sizes 720p,1080p --sources nv12,yuy2,yuy2native,mjpeg_cpu,mjpeg_qsv --gops intra,gop30 --frames 600 --reps 3 --label qsv` |
| B-NV-1 | 1 | 12 | same, NVENC (mjpeg_qsv = Intel decode feeding NVIDIA encode) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py --encoders h264_nvenc,hevc_nvenc --sizes 720p,1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv --gops intra,gop30 --frames 600 --reps 3 --label nvenc` |
| B-CPU-1 | 1 | 30 | CPU software baselines, same inputs, plus native 4:2:2 runs | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py --encoders libsvtav1,libvpx-vp9,mjpeg,ffv1 --sizes 720p,1080p --sources nv12,yuy2,mjpeg_cpu --gops intra,gop30 --native422 --frames 300 --reps 3 --label cpu` |
| B-DEC-1 | 1 | 5 | source pipeline only (frame build / YUY2 convert / MJPEG CPU vs QSV decode) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py --encoders none --sizes 720p,1080p --sources nv12,yuy2,mjpeg_cpu,mjpeg_qsv --native422 --frames 600 --reps 3 --label decode_only` |
| B-QSV-C1 | 1 | 7 | concurrent h264_qsv 1080p, 1/4/8/16, unpaced + paced, intra + gop30, limit probe 32 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec h264_qsv --size 1080p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-QSV-C2 | 1 | 7 | same, hevc_qsv | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec hevc_qsv --size 1080p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-QSV-C3 | 1 | 7 | same, vp9_qsv (royalty-free) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec vp9_qsv --size 1080p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-QSV-C4 | 1 | 4 | same, mjpeg_qsv (intra only) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec mjpeg_qsv --size 1080p --source nv12 --gop intra --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-NV-C1 | 1 | 7 | concurrent h264_nvenc 1080p (expect the open error at 13 sessions) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec h264_nvenc --size 1080p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-NV-C2 | 1 | 7 | same, hevc_nvenc | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec hevc_nvenc --size 1080p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced --limit-probe 32` |
| B-MF-1 | 2 | 10 | per-stream MF + D3D12VA (default adapter = NVIDIA) | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_encode_stream.py --encoders h264_mf,hevc_mf,h264_d3d12va,hevc_d3d12va --sizes 720p,1080p --sources nv12,mjpeg_cpu --gops intra,gop30 --frames 600 --reps 3 --label mf_d3d12` |
| B-QSV-C5 | 2 | 6 | concurrent h264_qsv 720p | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec h264_qsv --size 720p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced` |
| B-NV-C3 | 2 | 6 | concurrent h264_nvenc 720p | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec h264_nvenc --size 720p --source nv12 --gop intra,gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced` |
| B-QSV-C6 | 2 | 6 | full pipeline: per-stream CPU MJPEG decode + hevc_qsv gop30, 1/4/8/16 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec hevc_qsv --size 1080p --source mjpeg_cpu --gop gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced` |
| B-QSV-C7 | 2 | 6 | full pipeline: mjpeg_qsv decode + vp9_qsv gop30, 1/4/8/16 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec vp9_qsv --size 1080p --source mjpeg_qsv --gop gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced` |
| B-NV-C4 | 2 | 6 | full pipeline: CPU MJPEG decode + h264_nvenc gop30 | `uv run --script research/skellycam_recording/recording_upgrade/scripts/hw_accel_target/bench_concurrent.py --codec h264_nvenc --size 1080p --source mjpeg_cpu --gop gop30 --streams 1,4,8,16 --frames 600 --mode unpaced,paced` |

Totals: priority 1 is about 106 min; priority 2 about 40 min.
