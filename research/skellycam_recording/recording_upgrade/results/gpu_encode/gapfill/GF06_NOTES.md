# GF06 notes for gpu_encode (2026-11-10)

Evidence lives in `../../hw_accel_target/gapfill/GF06_amf_vt_intra.md` (+ `GF06_pyav_options.json`, `GF06_sources/`). Relevance to gpu_encode FINDINGS I6 (per-encoder intra settings):
- AMF: `gop_size=1` (not 0) for all-intra; constant QP `rc=cqp, qp_i=N` [code amfenc_h264.c:574-576, 377-378; amfenc_hevc.c:298-301, 523-524; source AMF SDK v1.5.3].
- VideoToolbox: `gop_size=1`; quality via `global_quality` (Quality 0-1); no constant QP in FFmpeg n9.0.2 [code videotoolboxenc.c:1379-1395, 1250-1261].
- `i_qfactor=1, i_qoffset=0` matters for NVENC and QSV only; AMF and VideoToolbox never read it [code: 0 grep matches].
- None of this ran on AMD or Apple hardware (NOT VERIFIED).
