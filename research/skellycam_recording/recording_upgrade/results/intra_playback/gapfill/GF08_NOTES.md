# GF08 pointer (intra_playback)

GF08 ran under chromium_sync_scrub. Results: `results/chromium_sync_scrub/gapfill/GF08_ts_sync.md` and `GF08_ts_sync.json`.

What it adds to this topic (functional only, no timing):
- measured: h264_nvenc all-intra at **target A** (720p, `matched_settings.json` `h264_nvenc_420/mjpeg_720p`: constqp qp 14, i_qfactor 1, i_qoffset 0) decoded frame-exactly in E35 and E45. Path: WebCodecs with `flush()` after each chunk; 3,157 decodes per Electron; barcode identity correct on every one (`GF08_ts_sync.json` → `mismatch_table`, path `h264`).
- measured: the 0.011 ms VFR pair (c930e frames 81/82) was targeted. All 174 rows that chose frame 81 or 82 were correct, for the h264_nvenc, camera-JPEG and barcode-JPEG paths in both Electrons.
- measured: with 4 cameras with different capture times (late start, gaps, early end), a sidecar-timestamp master clock (rule PREV or NEAREST, integer ns) had 0 mismatches. F19's spread is index-based on identical clips; GF08 is the timestamp-based check.
