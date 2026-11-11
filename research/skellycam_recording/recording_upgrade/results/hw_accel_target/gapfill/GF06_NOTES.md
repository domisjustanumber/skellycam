# GF06 notes (2026-11-10)

Task: all-intra and constant-QP/quality evidence for h264/hevc_amf and h264/hevc_videotoolbox (FFmpeg n9.0.2 code + vendor docs). Source-only: no AMD or Apple hardware on Gerald, no timing.

Files:
- `GF06_amf_vt_intra.md`: findings, verdict table, proposed replacement text for FINDINGS §3.2/§3.3.
- `GF06_pyav_options.json`: static PyAV 19.0.2 query (encoders present, private AVOptions, context defaults). Made by `scripts/hw_accel_target/gf06_pyav_amf_vt_options.py` (`uv run --script`, av==19.0.2). No encoder was opened.
- `GF06_sources/`: verbatim excerpts with line numbers (FFmpeg n9.0.2, AMF SDK v1.5.3, Apple docs JSON, macOS 15.5 SDK header via mirror) and `FETCH_MANIFEST.txt` (URLs, commits, sha256).
- Raw downloads (data only) are in the scratchpad `step3/GF06/{ff,amf,apple}`.

Headline (labels in the main file):
- AMF: all-intra via `gop_size=1`. **`gop_size=0` is NOT intra on AMF**: H.264 "turns IDR off", HEVC "only insert the first IDR/CRA". The NVENC K4 recipe must not be reused.
- AMF: constant QP via `rc=cqp, qp_i`. `i_qfactor` is not read, so K3 does not apply.
- VideoToolbox: all-intra via `gop_size=1` → MaxKeyFrameInterval 1. The default gop_size is 12.
- VideoToolbox: only a 0-1 Quality knob (`global_quality`). FFmpeg n9.0.2 does not reach constant QP (BaseFrameQP is unused). `qmin=qmax` is a best-effort clamp that may be ignored silently.
- Actual hardware behaviour, and the QP or quality value that reaches target A: NOT VERIFIED.

Source caveats:
- The Apple header-only text (BaseFrameQP, the Min/MaxAllowedFrameQP discussion) comes from a third-party SDK mirror, not from Apple. The Apple-hosted JSON confirms the symbols and their platforms, but for BaseFrameQP it has no discussion text.
- The AMF docs are SDK v1.5.3. The runtime shipped in a given driver is not pinned.
