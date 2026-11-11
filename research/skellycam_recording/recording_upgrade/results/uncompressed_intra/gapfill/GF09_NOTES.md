# GF09 notes (2026-11-10)

Report: `GF09_qsv_lossless.md`. Merged data: `GF09_qsv_lossless.json`.

**Results**
- Quick Sync (UHD 770, driver 32.0.101.7088) has no lossless H.264/HEVC mode: 0/300 exact frames in all 32 configurations that opened.
  - A requested QP 0 runs at QPI 1; VDENC (and every 4:4:4 input) runs at QPI 10.
  - FFmpeg n9.0.2 has no QSV lossless option.
  - oneVPL: "Zero QP is not valid" for these codecs.
- Pitfall: hevc_qsv with `low_power=1` on YUY2 silently writes 4:2:0 Main.
- NVENC lossless with the timed items' exact settings: bit-exact over 300 frames, all 10 timed configs plus Bayer8 quad. Checked with software decode, h264/hevc_cuvid and the cuda hwaccel.
  - d3d11va rejects H.264 High 4:4:4 Predictive.
- Chromium E35/E45: NVENC lossless H.264 (software, FFmpegVideoDecoder) and HEVC (hardware, D3D11VideoDecoder) play to the end in MKV and MP4, with exact YUV readback of 3 frames via `<video>` and via WebCodecs.

**Reproduce** (from the repo root; S = `research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09`)
```
uv run --script $S/probe_opts.py
uv run --script $S/gf09_lossless_check.py --part qsv
uv run --script $S/gf09_lossless_check.py --part nvenc
uv run --script $S/prep_chromium.py
uv run --script $S/verify_chromium_media.py
cd $S/chromium && env -u ELECTRON_RUN_AS_NODE <electron.exe> main.js --out <results>/GF09_chromium_electron{35,45}.json
uv run --script $S/summarize_gf09.py
```

**Media and files**
- Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/gapfill/GF09/`. Only the two NV12 1080p NVENC 300-frame MKVs and the `chromium/` cuts are kept; every other output was deleted after its check.
- The FFmpeg / oneVPL source copies quoted in the report are in the session scratchpad (`step3/GF09/src/`). SHA-256: qsvenc.c 4feac182…, nvenc.c 72bb256a…, mfxstructures.h (v2.15.0) d0d31b20….
