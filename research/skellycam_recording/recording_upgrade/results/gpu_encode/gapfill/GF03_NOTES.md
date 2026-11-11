# GF03 pointer (2026-11-10)

See `results/licensing/gapfill/GF03_nvjpeg_licence_arch.md`.

- source: nvJPEG 12.9 (= the measured 12.4.0.76 library) adds decode to NV12 and YUY2 for "both hardware engine and CUDA"; YUY2 output must be 4:2:2 (GF03 R21). This is a lead for a GPU MJPEG → YUY2 decode path; NOT TESTED.
- code: the measured library's header has `NVJPEG_INPUT_YUV` / `NVJPEG_INPUT_NV12` and `nvjpegEncodeYUV` / `nvjpegEncode` (wheel `nvjpeg.h:154, 159, 540, 560`). nvImageCodec 0.10 does not convert P_YUV (GF03 R19), which matches the measured "encode returned None" for YUV input.
- measured (static): SASS for sm_75/86/89/120 in `nvjpeg64_12.dll`. Table 3.4 row "NVIDIA Ada/Blackwell | JPEG HW enc NOT VERIFIED" can say "CUDA nvJPEG: binaries present (sm_89/sm_120), not run; no fixed-function JPEG encoder on GeForce (Jetson Thor only)".
