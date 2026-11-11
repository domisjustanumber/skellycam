# gpu_encode: provenance verification of the draft FINDINGS (2026-11-09)

Verifier: adversarial provenance pass. No timed runs. Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they start with `C:/`.
Method: opened every cited result file and script. Re-fetched 4 primary sources on 2026-11-09 (NVIDIA matrix, pyav-ffmpeg build script, Intel media_features.md, NVDEC guide). Checked the other quoted sources against the copies the investigator saved in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/gpu_encode/src/` (an old session's scratchpad, which may be deleted). Ran two inspection-only commands (ffprobe/ffmpeg `-c copy -f null`) on existing media.

## 1. New evidence produced by this verification

### 1.1 hevc_qsv `gpb=0` had no effect on the bitstream

- measured (verifier): the per-packet SHA256 list (`ffprobe -show_data_hash SHA256 -show_entries packet=data_hash`) is identical for `hevc_qsv_gop15_sw.mkv`, `hevc_qsv_gop15_gpb1.mkv` and `hevc_qsv_gop15_gpb0.mkv`. The hash of each list is `32365eea...d9f747`. All three files are 222,813 bytes. Their file hashes differ, so the difference is container-only. Media dir: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/gpu_encode/qsv_recheck_19.0.2/`.
- So "B pictures also with gpb=0" holds only in the sense that the option was passed. The encoder output did not change. Whether `gpb` ever reached the QSV runtime is NOT VERIFIED.

### 1.2 hevc_qsv gop15 slice headers (the earlier "NOT VERIFIED at slice level" is now measured)

Command (inspection only): `ffmpeg -loglevel trace -i hevc_qsv_gop15_gpb0.mkv -c copy -bsf:v trace_headers -f null -`. Counts over all 32 pictures:

| syntax element | values (count) |
|---|---|
| NAL type | IDR_W_RADL (3), TRAIL_R (29) |
| slice_type | 2 = I (3), 0 = B (29) |
| num_positive_pics, every explicit RPS (SPS set 0 and 9 slice-coded sets) | 0 (all) |
| inter-RPS-predicted sets | 12, all with delta_rps_sign = 1 (negative shift) |
| num_ref_idx_l1_default_active_minus1 (PPS) | 2 |

- measured (verifier): the 29 non-IDR pictures are B slices. Every short-term RPS signals only negative-POC (past) references, and pts == dts (`qsv_recheck2_ffprobe.txt`). So they are low-delay / generalized-P-B pictures with no future reference and no reordering.
- not checked: whether list 1 entries are the same pictures as list 0, i.e. strict GPB.

## 2. Claim-by-claim check

OK means the cited file says exactly that.

| draft § | claim | verdict | evidence checked |
|---|---|---|---|
| 2.1 | UHD 770 `Unknown / False / CM_PROB_PHANTOM` at 11:36 | OK | `system_probe.txt` |
| 2.1 | every QSV row in ff_functional **and pyav_functional** failed with "Failed to find d3d11va adapter by vendor id 0x8086" | **WEAK** | the string appears 10 times in `ff_functional.md` and **0 times** in `pyav_functional_19.0.2.{md,json}`. The PyAV rows record only `UnknownError ... 1313558101`. For PyAV the cause is inferred (same AVERROR code; works with the iGPU present) |
| 2.1 | iGPU present at 16:42 | OK | `qsv_recheck_19.0.2.md` header |
| 2.1 | RTX 3070, 610.88, cc 8.6 | OK | `system_probe.txt` |
| 2.1 | no `VK_KHR_video_encode_av1` | OK, with a scope note | the list is "device extensions used by ffmpeg", not a full device enumeration |
| 2.2 | NVENC h264 High / hevc Main, intra + gop15, sw + cuda | OK | `pyav_functional_19.0.2.md` |
| 2.2 | av1_nvenc errors | OK | same |
| 2.2 | d3d12va sw fails 22; hwctx works to MP4 | OK | md + `pyav_functional.py` (`"mp4"`) |
| 2.2 | default D3D12 device is NVIDIA with the iGPU present | OK **for h264_d3d12va only** | `adapter_check_19.0.2.json` has no hevc_d3d12va run. Table 3.1 extends it to hevc |
| 2.2 | h264_mf + hevc_mf work; cites `qsv_recheck` | **WEAK** | `qsv_recheck_19.0.2.md` re-ran only h264_mf. hevc_mf is from the iGPU-absent run only |
| 2.2 | h264_mf activates MFT 0 = NVIDIA | OK (h264 only) | `adapter_check_19.0.2.json`. Table 3.1 "h264_mf / hevc_mf: NVIDIA MFT" goes beyond the evidence for hevc_mf |
| 2.2 | av1_mf picks the Intel AV1 MFT **before the iGPU was present** (cites `pyav_functional_19.0.2.md`) | **WEAK** | `pyav_functional_19.0.2.json` records no MFT name. Before the iGPU was present the Intel MFT pick is shown only by the **CLI** (`system_probe.txt` last section). The after-state is OK (`qsv_recheck_19.0.2.md` MFT column) |
| 2.2 | QSV table (h264/hevc/vp9/mjpeg) | OK | `qsv_recheck_19.0.2.md` |
| 2.2 | av1_qsv message | OK | same |
| 2.2 | all QSV fail with HWAccel('qsv') | OK | same |
| 2.2 | hevc_qsv B "also with gpb=0" | **WEAK** | see 1.1: byte-identical packets, so the option had no effect |
| 2.2 | inferred low-delay B, NOT VERIFIED at slice level | **superseded** | now measured, see 1.2 |
| 2.2 | vulkan encoders not in wheel; AMF fail; hwdevices list | OK | `pyav_functional_19.0.2.md` |
| 2.3 | same pass/fail 18 vs 19 except h264_nvenc Main → High | OK | `diff` of the two md files shows only the header, libavcodec, nvidia-smi and the 4 h264_nvenc profile lines. Same script for both (`pyav_functional.py` docstring) |
| 2.3 | libavcodec 62.28.102 / 63.1.102 | OK | md headers |
| 2.3 | 19.0.2 = 18.0.0 in 6 wheels, sha256 checked | OK | `wheel_hw_codecs.md`; sha256 is in `.json`, asserted at `scripts/gpu_encode/wheel_hw_codecs.py:59-60` |
| 2.4 | 12 opened, 13th failed, smi 12 / 0 before | OK | `nvenc_sessions_19.0.2.json`. Sessions were 1280×720 (script docstring), which the draft does not say |
| 2.4 | four APIs failed while 12 were held, "so the four APIs share one pool" | measured failure OK; **conclusion is inferred** | the diagnoses for vulkan/d3d12va/mf are generic ("Error while opening encoder", "Failed to create encoder"). There is no same-arguments control without the held sessions in that run. The `ff_functional` controls used other arguments (e.g. `-bf 0` for h264_vulkan) and another iGPU state |
| 2.4 | PyAV 18 same; prior study "12 (20)" at p5_nvenc.md:7 | OK | `nvenc_sessions.json`; `research/frame_ring_buffer/prototypes/results/p5_nvenc.md:7` |
| 2.4 | NVIDIA matrix, "every GeForce row" 12 sessions | **WEAK (wording)** | re-fetched: 82 of the 90 GeForce rows give 12. MX570 A, MX150>MX330, MX350 and GT 1030 give `0`; four older mobile rows give `n/a`. Correct to "every GeForce row with NVENC" |
| 2.5 | `-g 1 -bf 0` message; `-g 0` gives 32 I | OK | `ff_functional.md`; `ff_functional.py:37-38,74-76` |
| 2.5 | `nvenc.c:1761-1767` | OK | cached n9.0.2 copy, lines 1761-1767: `gop_size > 0` → gopLength; `== 0` → frameIntervalP=0, gopLength=1. The script comment cites 1764-1767 (cosmetic) |
| 2.5 | vulkan h264 High / hevc Main; av1_vulkan message | OK | `ff_functional.md` |
| 2.5 | d3d12va `-bf 0`, default-B gop15 failure, MKV header failure | OK | `ff_functional.md`; `ff_functional.py:51-57` |
| 2.5 | ffv1_vulkan inputs, levels, byte-exact x3, level-3 messages, 3 key / 32 I | OK | `ff_functional.md`, `ff_functional.json` `roundtrip`, `ff_functional.py:62-66,116` |
| 2.5 | inferred coder-state carry-over from `ffv1enc_vulkan.c:279,289` | OK as inferred; thin | those lines show only `has_inter = gop_size > 1` and the key-frame decision, not the state carry-over itself. Keep the label |
| 2.5 | Bayer file sizes; CPU byte-exactness NOT VERIFIED | OK | `ls -l .../gpu_encode/diag/` matches 8,087,879 / 17,047,238 |
| 2.6 | PyAV 19 mjpeg_cuvid / cuda errors | OK | `pyav_functional_19.0.2.md` |
| 2.6 | CLI hang / fallback NOT VERIFIED | OK (correctly downgraded from NOTES §5) | no saved output; `diag/j420.mjpeg` exists (253,184 B) |
| 2.6 | NVDEC guide "Hybrid (CUDA + CPU) JPEG" | OK | re-fetched; the guide says nothing about JPEG 4:2:2 |
| 2.6 | mjpeg_qsv 5/5, nv12; Y max 21, means 7.705 / 8.297 | OK | `qsv_recheck_19.0.2.md`, `qsv_recheck2_19.0.2.json` |
| 2.6 | nvjpeg_cuda_decoder decodes to `STRIDED_DEVICE`; "decode on the GPU" | numbers OK; **framing WEAK** | `nvimgcodec_jpeg.json`: `libjpeg_turbo_decoder` (CPU) also reports `STRIDED_DEVICE`, so buffer kind does not show where decoding ran. `backend:HYBRID_CPU_GPU` gives results identical to `nvjpeg_cuda_decoder` (8/0.245/53.14 and 25/0.179/54.18), and `GPU_ONLY` fails. inferred: nvjpeg_cuda_decoder is the hybrid CPU+CUDA path. The 720p set is **c922**_720p_flash, not c930e |
| 2.6 | nvImageCodec version "0.10.0.9" | OK | pin in `nvimgcodec_jpeg.py:3`; the module reports "0.10.0" |
| 2.7 | mjpeg_qsv NV12 → Baseline yuvj420p | OK | `qsv_recheck_19.0.2.md` |
| 2.7 | nvJPEG / OpenCV encode table, GPU-resident 144,363 B / 43.5 dB, YUV rejected, gray 109,135 | OK | `nvimgcodec_jpeg.json`. The 43.5 dB is against ffmpeg's decode of the source JPEG (script line 125), not against source RGB |
| 2.7 | CUDA #700 counts per run | OK | `nvimgcodec_lifetime.json` |
| 2.8 | wheel lists per OS | OK | `wheel_hw_codecs.md` |
| 2.8 | build-ffmpeg.py flags; no vulkan/vaapi | OK | re-fetched raw file at 9.0.2-1: nvenc+nvdec, amf, libvpl and videotoolbox (Darwin) lines present; "vulkan" and "vaapi" absent |
| 2.8 | allcodecs.c:875,890,907 | OK | cached n9.0.2 copy |
| 2.9 | NVIDIA 3070/4070/5070 values | OK | re-fetched. RTX 2080 (Turing) also has AV1 NO, which table 3.4 uses but 2.9 does not cite |
| 2.9 | Intel media_features TGLx/BMG/LNL | OK | re-fetched raw: TGLx VP9 8bit `NV12/AYUV`, AV1 blank; BMG/LNL VP9 blank |
| 2.9 | AMD 7600 "AV1 Encode Yes"; 6600 none | OK | cached HTML: 7600 has `AV1 Decode Yes`, `AV1 Encode Yes`; 6600 has only `AV1 Decode Yes` |
| 2.9 | Apple M5 / M2 quotes | OK | cached HTML: both MacBook Air/Pro M5 pages contain the quoted phrase and "AV1 decode"; the M2 page has the phrase without AV1 decode |
| 3.4 | Intel TGL-RPL "mjpeg_qsv (Win, Linux x64)" in wheel | **WEAK** | Linux x86_64 has `mjpeg_qsv` only as a short name, which is shared with the decoder (`wheel_hw_codecs.md` column 3). No MJPEG-QSV encoder long name was found on any wheel. Encoder presence is proven only on win_amd64 (`av.codecs_available` + functional run) |
| 3.4 | CPU row "libsvtav1, libvpx-vp9 names present" | WEAK | `libvpx-vp9` is also a decoder name. Only `libsvtav1` is encoder-only. No functional test |
| 3.4 | NVIDIA Ada/Blackwell VP9 "no" | inferred | it rests on the matrix having no VP9 column (absence). Label it inferred |
| 4 I1 | "vp9_qsv is the **only** working hardware encoder for a lossy codec other than H.264/HEVC" | **REFUTED as worded** | `mjpeg_qsv` (JPEG, lossy) also works through PyAV 19.0.2 (`qsv_recheck_19.0.2.md`) |
| 4 I2 | no lossy non-H.264/HEVC codec is accelerated on RTX 3000 | inconsistent | the same bullet then names nvJPEG (CUDA) GPU JPEG, which is measured working on Ampere (`nvimgcodec_jpeg.json`). Reword to "no fixed-function video encoder for a non-H.264/HEVC codec" |
| 4 I5 | one pool across 4 APIs | inferred (see 2.4) | |
| 4 I6 | NVENC `gop_size=1` rejected | CLI reference only | PyAV never tried gop_size=1 (`pyav_functional.py` INTRA_GOP=0) |
| 4 I8 | "nvJPEG decodes it at full 4:2:2" | WEAK | output is an RGB device buffer; nothing measured the chroma resolution |
| 5 | B5 "optional" | add a flag | the manifest B5 command uses `.venv` (PyAV 18), the same problem as B2a |
| 6 | foreign NVENC session before the PyAV 19 run | OK | `pyav_functional_19.0.2.md` "1, 3 %". `nvenc_sessions_19.0.2.json` also shows `1` after close (not mentioned) |
| 7 | reproduce commands | WEAK | the CLI `mjpeg_cuvid` command reportedly does not exit (NOTES §5), so it needs a timeout. The `nvenc_sessions_versioned.py` docstring still names `nvenc_sessions.py` and the PyAV 18 venv |

## 3. Sources: re-fetch status (accessed 2026-11-09)

| source | status |
|---|---|
| https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new | re-fetched; values match; "every GeForce row" wording wrong (see 2.4) |
| https://github.com/PyAV-Org/pyav-ffmpeg/blob/9.0.2-1/scripts/build-ffmpeg.py | re-fetched (raw); matches |
| https://github.com/intel/media-driver/blob/intel-media-26.3.5/docs/media_features.md | re-fetched (raw); matches |
| https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/nvdec-video-decoder-api-prog-guide/index.html | re-fetched; quote matches |
| FFmpeg n9.0.2 nvenc.c, ffv1enc_vulkan.c, allcodecs.c | checked against the investigator's saved copies, not re-fetched |
| AMD RX 7600 / 6600, Apple M5 / M2 spec pages | checked against the saved HTML, not re-fetched |

## 4. Verdict

The draft is mostly faithful to its evidence, and it correctly downgrades several overclaims from NOTES.md ("identical", the CLI NVDEC hang, CPU FFV1 byte-exactness). Fix before publishing:

1. Refuted: I1 "only" (mjpeg_qsv).
2. Weak attributions: 2.1 PyAV QSV cause, 2.2 av1_mf pre-iGPU MFT, hevc_mf / hevc_d3d12va device, gpb=0.
3. Inference presented as measurement: the shared NVENC pool.
4. Wording errors: "every GeForce row"; nvJPEG "GPU decode" / "full 4:2:2"; Linux mjpeg_qsv in the wheel.
5. Replace the inferred low-delay-B bullet with the measured slice-header result in 1.2.
