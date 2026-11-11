# GF03 pointer (2026-11-10)

nvJPEG architecture coverage and licence results for this topic are in `results/licensing/gapfill/GF03_nvjpeg_licence_arch.md`: §4 has the architecture table, and §6.2 has the proposed replacement text for N6, N9, R5, §3.1, §3.3, §4 and §6.

- source: the measured `nvidia-nvjpeg-cu12==12.4.0.76` is CUDA 12.9.1's libnvjpeg. The CUDA 12.9.1 nvJPEG docs (decode engine on "Ampere (A100, A30) Hopper Ada Blackwell"; encode engine on Jetson Thor only; `NVJPEG_ENC_BACKEND_GPU` "Always use CUDA encoder") match it, so the N6 version gap is closed.
- measured (static): `nvjpeg64_12.dll` has SASS for sm_75, 86, 89 and 120. RTX 20/40/50 are "code present, not run".
