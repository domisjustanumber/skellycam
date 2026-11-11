# GF07 notes for gpu_encode (2026-11-10)

Evidence: `results/hw_accel_target/gapfill/GF07_intel_windows_sources.md`, with verbatim excerpts in `results/hw_accel_target/gapfill/GF07_sources/`. Sources only; no tests, no timing.

Effect on gpu_encode FINDINGS:
- §2.12 (Intel media-driver bullets, "These are Linux docs. On Windows only RPL-S was measured.") gets Windows-specific Intel sources:
  - RPL, MTL and ARL-S/HX datasheets: "JPEG" encode rows; exposure APIs "Direct3D12 Video API", "Intel®one VPL", "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]";
  - Intel KB 000098345 (Windows 10/11): H.264/HEVC/AV1 encode for Arc A, Core Ultra Series 1 and Arc B; Arc B VP9 encode "Not Supported".
- §3.4 row "Intel Arc / MTL / ARL / LNL / BMG", JPEG cell "yes (source)": that source is the Linux media-driver. Windows:
  - MTL and ARL-S/HX: source (datasheets);
  - Arc A: OS-agnostic oneVPL doc;
  - LNL: only a datasheet labelled "Confidential";
  - Arc B: NOT VERIFIED;
  - none tested.
- §3.4 VP9 cell "yes, except LNL/BMG": unchanged. Windows confirmations: Arc B "Not Supported" (KB); LNL datasheet "supports AVC, HEVC, and AV1".
