# jellyfin-ffmpeg: what it could offer skellycam (sources only)

Topic for HANDOFF section 1, requirement 4. jellyfin-ffmpeg was **not** downloaded, installed or tested. Every source was fetched on 2026-11-09 through `gh api` or curl. Re-fetch script: `scripts/jellyfin_ffmpeg/fetch_sources.sh`.

Labels:
- **source**: primary source, with its URL at a pinned tag and an exact quote.
- **code**: a file:line in this repo.
- **measured**: a result file in this folder or another topic folder. Here that means a string search of fetched source files, not a test run.
- **inferred**: kept to a minimum.
- **NOT VERIFIED**: could not be checked.

Evidence files in this folder:
- `patch_index.txt`: all 106 patches, with the files each one touches.
- `upstream_presence.txt`: which added codecs and filters upstream FFmpeg has.
- `upstream_spotcheck.txt`: whether 4 patch changes are in upstream n9.0.2, plus the FFmpeg FDK-AAC licence text.
- `releases.txt`: release assets, release notes and the release list.
- `build_config_excerpts.txt`: build configuration excerpts.
- `sources_excerpts.txt`: PyAV docs, the PyAV binding search log, Jellyfin doc quotes and the FFmpeg rawvideo doc.
- `pyav_19.0.2_pypi_files.txt`: PyAV 19.0.2 wheel sizes.

## 1. Current release and upstream base

- source: latest release `v8.1.3-2`, published 2026-11-03T17:49:24Z, tag commit `7250de8375a4959ac1c25c139ce9789fdac199fb` (https://github.com/jellyfin/jellyfin-ffmpeg/releases/tag/v8.1.3-2; `releases.txt`).
- source: the `VERSION` and `RELEASE` files at that tag both contain `8.1.3` (https://github.com/jellyfin/jellyfin-ffmpeg/blob/v8.1.3-2/VERSION; `build_config_excerpts.txt`).
- source: the v8.1.3-1 release notes say "New upstream version 8.1.3" (https://github.com/jellyfin/jellyfin-ffmpeg/releases/tag/v8.1.3-1).
- source: upstream FFmpeg tag dates: `n9.0` 2026-08-03, `n9.0.2` 2026-09-18, `n8.1.3` 2026-09-21 (FFmpeg GitHub mirror, git tag objects; `sources_excerpts.txt`).
- measured: PyAV 19.0.2 bundles FFmpeg 9.0.2 (`results/licensing/FINDINGS.md:80`, `probe_pyav_19.0.2.json`).
- So jellyfin-ffmpeg's current release is **one major version behind** the FFmpeg inside PyAV 19.0.2 (8.1.3 against 9.0.2). This follows from the two facts above.
- source: the repo's `README.md` is upstream FFmpeg's README, unchanged ("FFmpeg README ... FFmpeg is a collection of libraries and tools"). There is no jellyfin-specific README (https://github.com/jellyfin/jellyfin-ffmpeg/blob/v8.1.3-2/README.md).
  - The jellyfin-specific documentation lives in `builder/README.md`, `builder/Buildmac.md`, `debian/changelog` and the release notes.
- source: the GitHub repo description is "FFmpeg for Jellyfin with custom extensions and enhancements". The licence field is `NOASSERTION` (`gh api repos/jellyfin/jellyfin-ffmpeg`).

### Why Jellyfin requires it

These quotes come from https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/ (source file `index.md`, repo jellyfin/jellyfin.org @ 4acfc64a; `sources_excerpts.txt`):
- source: "The Jellyfin server uses a modified version of FFmpeg as its transcoder, namely jellyfin-ffmpeg. It enables the Jellyfin server to access the fixed-function video codecs, video processors and GPGPU computing interfaces ..." (index.md:12).
- source: "Using FFmpeg binaries downloaded from somewhere else will result in partial acceleration." (index.md:74).
- source: the doc defines partial acceleration over the stages "Video Decoding ... Deinterlacing ... Scaling & Format conversion ... HDR/DV Tone-mapping ... Subtitle burn-in ... Encoding ... Zero-copy". It says "Partial acceleration may result in higher CPU usage and lower transcoding speed." (index.md:28-50).
- inferred: these reasons are about a *transcoding* pipeline (decode, filter, tone-map, burn subtitles, encode). skellycam records raw frames (G1: JPEG passthrough; G4: intra-only encode of NV12/YUY2/Bayer). Most of the jellyfin-only additions are filters (section 2), and the recording path does not use them.

## 2. Patch list, grouped by area (106 patches, tag v8.1.3-2)

- source: https://github.com/jellyfin/jellyfin-ffmpeg/blob/v8.1.3-2/debian/patches/series lists 106 patches. The files each one touches are in `patch_index.txt`.
- source: the patches are quilt diffs with **no description headers**. Each patch's file name is the only commit-message-like text, so the names below are quoted file names.
- source: the Debian build applies the patches. The portable builder uses the same branch (`builder/variants/defaults-gpl.sh`: `GIT_BRANCH="jellyfin"`).

| Area | # | Patch names (number-name, quoted) |
|---|---|---|
| QSV / Intel (oneVPL, D3D11 on Intel) | 16 | 0011 add-fixes-for-mapping-from-qsv-source-device; 0012 add-d3d11-opencl-interop-for-qsv; 0017 backport-fixes-for-qsv-from-upstream; 0018 backport-fixes-for-qsv-from-cartwheel; 0019 add-fixes-for-qsv-vpp-filters; 0020 add-external-frame-support-for-qsv-enc; 0030 tune-dxva-align-for-intel-to-avoid-copy-on-qsv; 0033 add-d3d11va-dxva2-hevc-422-444-decoding-on-intel; 0036 skip-loading-plugins-on-vpl-runtime; 0037 tune-the-default-bf-for-qsv-enc; 0040 sync-intel-d3d11va-textures-before-mapping-to-opencl; 0059 allow-vpl-qsv-to-init-with-the-legacy-msdk-path; 0064 use-dynamic-pool-for-vpl-qsv-hwupload; 0071 allow-qsvenc-to-bail-out-from-unsupported-low-power-mode; 0099 fix-qsv-av1-decoder-exporting-hdr-side-data; 0105 skip-oversized-a53-caption-sei-in-qsv-h264-encoder |
| VAAPI (Linux) | 11 | 0014 add-vaapi-hwupload-filter; 0015 check-alpha-mode-for-vaapi-overlay-filter; 0024 increase-the-default-async-depth-for-vaapi-encode; 0034 default-vaapi-scaler-algorithm-to-fast; 0035 dont-fail-on-vaapi-to-drm-export-vasync; 0038 allow-vaapi-import-drm-prime2-planar-formats; 0039 add-vui-info-to-the-seq-header-of-hevc-vaapi-encoder; 0070 allow-vpp-tonemap-without-hdr10-metadata; 0086 fix-amd-hevc-vaapi-encoder-extradata-with-overrides; 0096 fix-full-range-input-for-mjpeg-vaapi-encoder; 0103 backport-a-fix-for-pts-overflow-in-deint-vaapi-filter |
| NVENC / NVDEC / CUDA | 8 | 0002 update-cuda-func-header; 0003 add-enhanced-cuda-pixfmt-converter-impl; 0004 add-cuda-tonemap-impl; 0016 add-fixes-for-nvdec-exceed-32-surfaces-error; 0031 add-10bit-support-for-cuda-overlay; 0032 add-hdr-metadata-for-nvenc-hevc-encoder; 0050 add-cuda-transpose-filter-impl; 0083 backport-fixes-for-cuda-from-upstream |
| AMF / AMD | 3 | 0005 add-amf-fixes-from-upstream-and-custom-tunings; 0009 add-d3d11-opencl-interop-for-amd; 0076 fix-seeking-h264-open-gop-videos-with-d3d11va-on-amd |
| VideoToolbox (macOS) | 14 | 0043 add-format-option-to-vt-scale-filter; 0044 add-vf-overlay-videotoolbox-filter; 0045 add-coreimage-based-vf-transpose-vt-filter; 0046 add-vf-tonemap-videotoolbox-filter; **0047 add-mjpeg-videotoolbox-encoder**; 0048 add-vt-low-priority-keyframe-decoding; 0049 add-dummy-device-derive-to-videotoolbox-hwcontext; 0055 allow-vt-sw-decoder-for-every-codec; 0056 add-bwdif-videotoolbox-filter; 0057 add-12bit-decoding-on-videotoolbox; 0060 alway-set-videotoolboxenc-pixel-buffer-info; 0063 videotoolbox-remove-opengl-compatability; 0073 dont-return-ext-error-for-invalid-vt-frame; 0101 fix-videotoolbox-closed-caption-sei |
| Vulkan | 5 | 0078 backport-fixes-for-vulkan-from-upstream; 0079 add-fixes-for-vaapi-drm-prime-vulkan-interop; 0080 prefer-vulkan-device-with-higher-api-version; 0081 signal-vulkan-semaphores-in-drm-prime-reverse-mapping; 0082 add-fixes-and-enhancements-for-vulkan-filters |
| RKMPP / RGA (Rockchip) | 1 | 0042 add-full-hwa-pipeline-for-rockchip-rk3588-platform (8,394 lines) |
| Windows D3D11 / DXVA / Media Foundation | 9 | 0013 add-vendor-id-option-for-d3d11; 0072 add-array-of-textures-support-for-d3d11va-hwaccel; 0091 add-d3d11-deinterlace-filter; 0092 add-d3d11-video-processor-overlay-transpose-filters; 0093 fix-d3d11-scale-visible-source-rect; 0094 add-d3d11-tonemap-filter; 0095 add-scale-d3d11-p010-shader-fallback; **0097 add-misc-enhancements-to-mfenc-hw-encoder**; 0104 backport-a-fix-for-data-race-with-frame-threading-in-dxva |
| Tone-mapping, OpenCL and generic filters | 19 | 0006 add-opencl-scaler-and-pixfmt-converter-impl; 0007 add-bt2390-eetf-and-code-refactor-to-opencl-tonemap; 0008 add-pgs-support-to-opencl-overlay; 0010 add-a-hack-for-opencl-reverse-mapping; 0021 suppress-overlay-warning-logs; 0022 add-sub2video-option-to-subtitles-filter; 0023 add-alphasrc-source-video-filter; 0051 add-flip-feat-to-opencl-transpose-filter; 0053 add-simd-optimized-tonemapx-filter; 0058 fix-the-sub2video-perf-regressions; 0067 fix-auto-inserting-sw-color-conv-filters-between-hw-fmts; 0068 fix-dummy-hw-frame-missing-hw-frames-ctx; 0069 add-yadif-and-bwdif-opencl-filter-impl; 0074 fix-mapped-hwframe-to-swframe-swscale-conversion; 0075 fix-hwupload-filter-cannot-use-devices-created-by-hwaccel; 0085 fix-hdr10-sidedata-not-removed-in-libplacebo-outlink; 0098 backport-a-fix-to-not-stall-sub2video-on-stream-eof; 0102 fix-sse2-scene-sad-unaligned-input; 0106 unref-the-last-frame-on-filter-graph-cleanup |
| Other (muxers, audio, subtitles, CLI, licensing) | 20 | 0001 add-fixes-for-segment-muxer; 0025 add-multiple-values-tags-and-webp-support-for-id3v2; **0026 remove-fdk-aac-from-nonfree**; 0027 pass-dovi-sidedata-to-hlsenc-and-mpegtsenc; 0028 add-pause-support-for-ffmpeg-cli; 0029 enable-gcc-vectorization-and-fix-cpuflags; 0041 add-icon-for-windows-version-ffmpeg; 0052 opus-allow-5point1-side-inputs; 0054 add-ac4-decoder-for-atsc-3-0; 0061 add-remove-dovi-hdr10plus-bsf; 0062 fix-atenc-layout-samplerate; 0065 fix-ass-incorrect-null-copy; 0066 add-first-vframe-only-to-ffprobe; 0077 suppress-the-resumed-reading-at-pts-with-rate-warning; 0084 backport-fixes-for-detecting-ac4-streams-in-mpegts; 0087 add-dtsx-detect-for-dts-hd-hra; 0088 add-webp-to-matroskadec-image-mime-types; 0089 relax-to-allow-safe-filenames-in-mkv-attachments; 0090 backport-a-fix-to-use-sw-pix-fmt-in-codec-par-if-set; 0100 backport-trim-bitstream-filter |

The groups are my own, made from the patch names. The QSV, VAAPI, VideoToolbox and Windows groups overlap by nature; each patch is counted once. The counts sum to 106.

## 3. Hardware paths and fixes not in upstream FFmpeg

### New codecs and filters added by the patches

measured: `upstream_presence.txt` counts `extern const ... ff_<name>;` lines in upstream `allcodecs.c`, `allfilters.c` and `bitstream_filters.c` at n8.1.3 and n9.0.2.

| Added by | Name | In upstream n8.1.3 / n9.0.2? | Relevance to skellycam |
|---|---|---|---|
| 0047 | `mjpeg_videotoolbox` encoder ("VideoToolbox MJPEG Encoder", input pix fmts videotoolbox/nv12/yuv420p, `allow_sw` option) | no / no | **Hardware JPEG encode on macOS** (G4 intra-only, G6). Not in PyAV 19.0.2 wheels either: the macOS wheels have VideoToolbox H.264, H.265 and ProRes only (measured, `results/gpu_encode/wheel_hw_codecs.md`) |
| 0042 | `mjpeg_rkmpp` encoder; `mjpeg`, `av1`, `h263`, `mpeg1/2/4` rkmpp decoders; `scale/vpp/overlay_rkrga` filters | no / no (upstream already has `h264/hevc_rkmpp` encoders and `h264/hevc/vp8/vp9_rkmpp` decoders) | Rockchip RK3588 boards only. Outside the hardware target |
| 0091, 0092, 0094 | `bwdif/yadif_d3d11`, `overlay_d3d11`, `transpose_d3d11`, `tonemap_d3d11` | no / no | Windows GPU filters for transcoding. Not on the recording path (inferred) |
| 0044, 0046, 0056 | `overlay/tonemap/bwdif_videotoolbox` | no / no | macOS filters. Not on the recording path (inferred) |
| 0004, 0050 | `tonemap_cuda`, `transpose_cuda` | no / no (`transpose_cuda`: yes in n9.0.2) | Transcoding filters (inferred) |
| 0006, 0069 | `scale_opencl`, `yadif/bwdif_opencl` | no / no | Transcoding filters (inferred) |
| 0014, 0023, 0053 | `hwupload_vaapi`, `alphasrc`, `tonemapx` (SIMD CPU tone-map) | no / no | Transcoding filters (inferred) |
| 0054, 0100 | `ac4` decoder, `trim` bsf | no / no | Audio and bitstream. Not relevant |

### Encoder-side changes to codecs PyAV also ships

Each was read from the patch diff at v8.1.3-2. "Upstream" means a string spot-check in FFmpeg n9.0.2 (`upstream_spotcheck.txt`).

| Patch | What the diff does (quoted) | In upstream n9.0.2? |
|---|---|---|
| 0071 (QSV) | under `LowPower == MFX_CODINGOPTION_ON`, logs "Some encoding parameters are not supported under Low power mode, trying to recover with it set to disabled" and retries | no (measured: 0 matches) |
| 0017 (QSV) | "Update AVCodecContext with actual encoding parameters" sets `has_b_frames` from `GopRefDist`; adds HEVC to the per-frame encoded-info path that was H.264 only | `has_b_frames` line: no (measured: 0 matches) |
| 0018 (QSV) | cartwheel backports, including the HEVC option `main10sp` "This profile allow to encode 10 bit single still picture" | NOT VERIFIED |
| 0037 (QSV) | H.264/AV1 defaults `g` -1 to 250 and `bf` -1 to 3; HEVC `g` 248 to 250 and `bf` -1 to 4 | NOT VERIFIED. inferred: irrelevant for intra-only (`g=1`) |
| 0020 (QSV) | "add-external-frame-support-for-qsv-enc" (qsvenc.c, hwcontext_qsv.c) | NOT VERIFIED |
| 0059 / 0036 (QSV) | let oneVPL QSV start through the legacy MSDK path; "Plugins have been removed in VPL runtime, don't load them" | NOT VERIFIED |
| 0013 (D3D11) | accepts option `vendor` as an alias of `vendor_id` "for backward compatibility". It does not change adapter discovery. inferred: it would not fix the earlier `Failed to find d3d11va adapter by vendor id 0x8086` (`results/gpu_encode/ff_functional.md`), which HANDOFF §2 attributes to the absent iGPU | not checked |
| 0032 (NVENC) | adds HDR mastering metadata to `hevc_nvenc` | NOT VERIFIED |
| 0083 (CUDA) | "backport-fixes-for-cuda-from-upstream": NVDEC even-aligned targets for 4:2:0/4:2:2; NVENC B-frame reference mode warnings | NOT VERIFIED whether every hunk is already in n9.0.2 |
| 0016 (NVDEC) | "add-fixes-for-nvdec-exceed-32-surfaces-error" | NOT VERIFIED |
| 0005 (AMF) | AMF fixes plus "custom tunings": new `async_depth` option (default 8) and `forced_idr` (default 1) on the av1, h264 and hevc AMF encoders | NOT VERIFIED |
| 0097 (MF) | Media Foundation encoder: `MFTEnum2` loaded optionally ("missing in pre-Windows 10, version 1703's mfplat.dll"); binds the D3D11 frame to the sample "to prevent in-flight async frames from being prematurely released back to the frame pool" | NOT VERIFIED |
| 0024 (VAAPI) | default `async_depth` 2 to 4 for all `hw_base_encode` encoders | NOT VERIFIED |
| 0096 (VAAPI) | `mjpeg_vaapi` `color_ranges` from `AVCOL_RANGE_MPEG` to `AVCOL_RANGE_MPEG \| AVCOL_RANGE_JPEG` (full-range JPEG input) | no (measured: n9.0.2 still `AVCOL_RANGE_MPEG, /* FIXME: implement tagging */`) |
| 0033 (D3D11VA, Intel) | HEVC 4:2:2/4:4:4 hardware decode through D3D11VA/DXVA2 on Intel | NOT VERIFIED |

Notes:
- "backport" patches (0017, 0018, 0078, 0083, 0090, 0098, 0100, 0103, 0104) take changes from upstream or Intel cartwheel. Some may already be in FFmpeg 9.0.2. Each one was not checked (NOT VERIFIED), apart from the spot-checks marked above.
- measured: PyAV 19.0.2's manylinux x86_64 wheel has **no VAAPI and no Vulkan** encoders (`results/gpu_encode/NOTES.md:130`).
  - So the VAAPI fixes above only matter to skellycam on Linux if it uses an FFmpeg other than the PyAV wheel's.
  - That applies with jellyfin-ffmpeg or with a self-built PyAV.

## 4. Build configuration, bundled libraries and licence

- source: the Debian `configure` line (https://github.com/jellyfin/jellyfin-ffmpeg/blob/v8.1.3-2/debian/rules lines 9-72; `build_config_excerpts.txt`) contains:
  - `--enable-gpl --enable-version3 --enable-shared`;
  - `--enable-libx264 --enable-libx265 --enable-libfdk-aac --enable-libsvtav1 --enable-libdav1d --enable-libvpx --enable-libopus --enable-libwebp --enable-libplacebo --enable-vulkan --enable-vaapi --enable-opencl`;
  - `--enable-ffnvcodec --enable-cuda --enable-cuda-llvm --enable-cuvid --enable-nvdec --enable-nvenc`;
  - x86 only: `--enable-libvpl --enable-amf`; arm64 only: `--enable-rkmpp --enable-rkrga`.
- source: the portable builds (`builder/variants/defaults-gpl.sh`) use `FF_CONFIGURE="--enable-gpl --enable-version3 ..."` and `LICENSE_FILE="COPYING.GPLv3"`.
- source: per-platform enables in `builder/scripts.d/*.sh` at v8.1.3-2:
  - AMF and libvpl are off on `mac*` and `*arm64`;
  - ffnvcodec (NVENC/NVDEC/CUDA) is off on `mac*`;
  - `50-dxva.sh` adds `--enable-dxva2 --enable-d3d11va --enable-d3d12va --enable-mediafoundation` on `win*`;
  - Vulkan and libplacebo are off on `mac*`;
  - rkmpp and rkrga are on only on `linux*arm64`;
  - macOS adds `--enable-audiotoolbox --enable-videotoolbox` (`defaults-mac.sh`).
- **Resulting licence: GPL version 3.** source: upstream FFmpeg `LICENSE.md` says `--enable-version3` with GPL parts means `COPYING.GPLv3` applies ("Read the file `COPYING.LGPLv3` or, if you have enabled GPL parts, `COPYING.GPLv3`", n8.1.3 lines 61-64).
- **FDK-AAC.**
  - source: patch 0026 moves `libfdk_aac` out of `EXTERNAL_LIBRARY_NONFREE_LIST` and into `EXTERNAL_LIBRARY_LIST`. `builder/scripts.d/50-fdk-aac-stripped.sh` builds `https://gitlab.freedesktop.org/wtaymans/fdk-aac-stripped.git` and passes `--enable-libfdk-aac` (not on macOS).
  - source: upstream FFmpeg lists `libfdk_aac` as nonfree (configure n8.1.3:2004-2007). Its LICENSE.md says: "The Fraunhofer FDK AAC and OpenSSL libraries are under licenses which are incompatible with the GPLv2 and v3." and that `--enable-nonfree` "will cause the resulting binary to be unredistributable." (n8.1.3 lines 117-127; `upstream_spotcheck.txt`).
  - The jellyfin build overrides FFmpeg's own nonfree classification in a GPLv3 build. Whether the "stripped" FDK fork's licence resolves that is NOT VERIFIED; this is a legal question for anyone who redistributes the binary.
- source: the builder scripts are MIT ("Copyright 2020-2021 BtbN", `builder/LICENSE`). That covers the scripts only, not the binaries.
- source: the repo carries `COPYING.GPLv2`, `COPYING.GPLv3`, `COPYING.LGPLv2.1`, `COPYING.LGPLv3` and `LICENSE.md` at the root (tree at v8.1.3-2).

## 5. Platforms and distribution format

- source: v8.1.3-2 release assets (`releases.txt`, sizes in bytes):
  - `.deb` packages for Debian bookworm and trixie, and Ubuntu jammy, noble and resolute, each amd64 and arm64 (25.5-53.4 MB);
  - portable `linux64-gpl` and `linuxarm64-gpl` (.tar.xz, 60.7 MB and 54.1 MB);
  - portable `mac64-gpl` and `macarm64-gpl` (.tar.xz, 38.1 MB and 32.9 MB);
  - portable `win64-clang-gpl` and `winarm64-clang-gpl` (.zip, 68.5 MB and 55.8 MB).
- source: `builder/README.md`:
  - targets: "`win64` (x86_64 Windows, windows>=7)", "`linux64` (x86_64 Linux, glibc>=2.28, linux>=4.18)" and "`linuxarm64` ...";
  - variants: "`gpl` Includes all dependencies ..." and "`gpl-shared` Same as gpl, but comes with the `libav*` family of shared libs instead of pure static executables."
  - Whether the released `win64-clang` build keeps the windows>=7 floor is NOT VERIFIED.
- source: the release assets are the `-gpl` variant only, with no `gpl-shared` asset. `builder/variants/default-install.sh` copies only `bin/*` and `doc` into the package.
  - inferred: the Windows and macOS portable archives contain static executables (`ffmpeg`, `ffprobe`), with no `libav*` libraries and no headers.
- source: macOS builds use `--disable-shared --enable-static` and `MACOSX_DEPLOYMENT_TARGET="12.0"` (`defaults-mac.sh`). The Jellyfin docs list full acceleration for "Intel and Apple Silicon on macOS 12 and above" (index.md).
- source: the `.deb` installs `ffmpeg`, `ffprobe` and `libav*.so*` under `/usr/lib/jellyfin-ffmpeg` (`debian/jellyfin-ffmpeg8.install`). No headers are installed.
- source: Jellyfin docs:
  - "Jellyfin-ffmpeg usually ships with our deb package, official Docker images and Windows installers." (index.md:76);
  - "The `jellyfin-ffmpeg*` deb package comes with all necessary user mode Intel media drivers except OpenCL" (intel.md:270);
  - "... comes with all necessary user mode Mesa drivers." (amd.md:180).

## 6. PyAV and jellyfin-ffmpeg

- source: PyAV v19.0.2 `docs/overview/installation.rst:27`: "PyAV can also be compiled against your own build of FFmpeg 8.x. You can force installing PyAV from source by running: `pip install av --no-binary av`". Lines 33-41 list the 7 required libraries (libavcodec, libavdevice, libavfilter, libavformat, libavutil, libswresample, libswscale). https://github.com/PyAV-Org/PyAV/blob/v19.0.2/docs/overview/installation.rst
- source: PyAV v19.0.2 `setup.py:123-131` takes `--ffmpeg-dir=` and expects `include/` and `lib/` under it (lines 56-76). Otherwise it uses `pkg-config` on non-Windows.
- source: the Windows instructions build against "FFmpeg development files maintained by the PyAV project" via `fetch-vendor.py` (installation.rst:62-70).
- Can PyAV bind to jellyfin-ffmpeg?
  - inferred, from §5 and setup.py: **not to any released artifact**. The Windows and macOS releases have no shared libraries or headers, and the `.deb` has `.so` files but no headers.
  - A binding would need a self-built `gpl-shared` jellyfin-ffmpeg (builder README) plus a PyAV source build with `--ffmpeg-dir`, on each OS.
  - The PyAV docs' "FFmpeg 8.x" matches jellyfin's 8.1.3 base. Whether PyAV 19.0.2's source actually compiles and passes tests against 8.1.3 plus the jellyfin patches is **NOT VERIFIED** (testing was out of scope).
- **Public PyAV binding or wheel for jellyfin-ffmpeg: NOT FOUND** (`sources_excerpts.txt`). Searched on 2026-11-09:
  - `gh search repos "jellyfin-ffmpeg pyav"`: 0 results. `gh search repos "jellyfin ffmpeg python"`: 0 results.
  - `gh search code "jellyfin-ffmpeg"` in `setup.py`: 3 repos, all calling the CLI binary. In `pyproject.toml`: 0.
  - PyPI JSON for `jellyfin-ffmpeg`, `pyav-jellyfin`, `av-jellyfin`, `jellyfin-av` and `jellyfin_ffmpeg`: all 404. conda-forge `jellyfin-ffmpeg`: 404.
  - One web search found nothing relevant.

## 7. Draft pros/cons: standard FFmpeg (PyAV 19.0.2 wheel) vs jellyfin-ffmpeg

| Row | Standard FFmpeg 9.0.2 in PyAV 19.0.2 wheels | jellyfin-ffmpeg v8.1.3-2 |
|---|---|---|
| Base version | FFmpeg 9.0.2 (measured, `results/licensing/FINDINGS.md:80`) | FFmpeg 8.1.3 plus 106 patches (source, `VERSION`, `series`) |
| Hardware encoders, Windows x64 | NVENC h264/hevc/av1; QSV av1/vp9 (+ h264/hevc/mjpeg short names); AMF av1 (+ h264/hevc); D3D12VA h264/hevc/av1; MF av1 (+ h264/hevc) (measured, `results/gpu_encode/wheel_hw_codecs.md`, `gpu_encode/NOTES.md:128`) | Same families enabled: NVENC, libvpl (QSV), AMF, D3D11VA/D3D12VA/MF (source, `scripts.d` §4). No extra Windows *encoder*; the extras are filters (D3D11 deinterlace, overlay, transpose, tone-map) (measured, `upstream_presence.txt`) |
| Hardware encoders, Linux x64 | NVENC, QSV, AMF, V4L2 m2m. **No VAAPI, no Vulkan** (measured, `gpu_encode/NOTES.md:130`) | Adds **VAAPI** (incl. `mjpeg_vaapi` with the full-range fix 0096) and **Vulkan** (source, `debian/rules`) |
| Hardware encoders, macOS | VideoToolbox H.264, H.265, ProRes (measured, `wheel_hw_codecs.md`) | Adds **`mjpeg_videotoolbox`** (hardware JPEG encode), which is in neither upstream n9.0.2 nor the wheel (source 0047; measured, `upstream_presence.txt`) |
| Hardware encoders, ARM Linux | V4L2 m2m h264 (measured, `wheel_hw_codecs.md`) | RKMPP full pipeline, including `mjpeg_rkmpp` encode (RK3588 only) (source 0042) |
| QSV / NVENC / VAAPI fixes | Upstream behaviour (measured on Gerald: NVENC works including all-intra, `gpu_encode/NOTES.md` §1) | QSV low-power bail-out (0071), QSV defaults (0037), VPL/MSDK init (0036, 0059), NVDEC surface fix (0016), CUDA backports (0083), VAAPI async depth (0024) and others (source §3). Whether any of them fixes a failure skellycam would hit: NOT VERIFIED (untested by rule) |
| Python integration | In-process: JPEG bytes are muxed as `av.Packet` with per-frame `pts=dts`. Container PTS equal the sidecar PTS on every frame across 7 sets and 1,862 frames (measured, `results/python_integration/NOTES.md:16,72`). Errors come back as Python exceptions (inferred) | **Subprocess pipe only** (no binding, §6). Costs: (1) process management, kill and cleanup: measured, killing the ffmpeg child lost every frame of a plain MP4 and 54 of 300 frames of an MKV (`results/crash_resilience/NOTES.md:313-320`); (2) an extra copy of every frame through the OS pipe (inferred); (3) per-frame PTS: rawvideo/image2pipe input has no per-frame timestamps; the rate is fixed by an option, "framerate Set input video frame rate. Default value is 25." (source, FFmpeg n9.0.2 `doc/demuxers.texi:1040-1041`), so camera timestamps need a timestamped container on the pipe (e.g. NUT/MKV) or a sidecar (inferred); (4) startup probing buffers about 5 MB before output starts (measured, `crash_resilience/NOTES.md:324-328`); (5) errors arrive as stderr text and exit codes (inferred) |
| Distribution | One wheel per platform from PyPI, e.g. win_amd64 28.2 MB, macOS arm64 18.6 MB, manylinux x86_64 35.0 MB (source, PyPI JSON, `pyav_19.0.2_pypi_files.txt`) | A separate binary per OS and arch: win64 zip 68.5 MB, mac arm64 32.9 MB, linux64 60.7 MB (source, `releases.txt`), downloaded and version-pinned outside pip. Still needs PyAV or another reader for playback and decode (inferred) |
| Licensing | FFmpeg libs report "LGPL version 3 or later", but the wheel ships GPL-2.0+ `libx264`/`libx265` DLLs that cannot be removed without breaking `import av` (measured, `results/licensing/FINDINGS.md:80-88`) | Built `--enable-gpl --enable-version3` with `COPYING.GPLv3`, so GPLv3. It also enables FDK-AAC, which upstream calls GPL-incompatible (source §4) |
| GPL implications for skellycam | skellycam is AGPL-3.0+ (code: `LICENSE:1`, `pyproject.toml:15`). AGPLv3 §13 allows combining with GPLv3 works (code: `LICENSE:553-559`). Shipping x264/x265 inside an installer: see `licensing/FINDINGS.md:164` | As a separate executable: the GPL FAQ says "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs" (source, https://www.gnu.org/licenses/gpl-faq.en.html). GPLv3 still requires source offer and licence text when redistributing the binary (inferred). The FDK-AAC question: NOT VERIFIED |
| Update cadence | PyAV: 9 releases from 2026-01-09 to 2026-10-21 (source, GitHub releases); 19.0.0 moved to FFmpeg 9 within 2 months of FFmpeg 9.0 (2026-08-03 to 2026-09-29) | 21 releases between 2025-11-10 and 2026-11-03, 7 of them prereleases (all the 8.1.1-x and 8.1.2-1..3 releases, while 7.1.x stayed stable) (source, `releases.txt`). Still on 8.1.x three months after FFmpeg 9.0 (source, §1) |
| Windows support | win_amd64 and win_arm64 wheels (source, PyPI) | win64 and winarm64 portable zips (source). Builder README says "windows>=7" for `win64` |
| macOS support | macOS 11+ x86_64 and macOS 14+ arm64 wheels (source, PyPI wheel tags) | mac64 and macarm64 portable, `MACOSX_DEPLOYMENT_TARGET="12.0"`. No NVENC/AMF/QSV/Vulkan on mac (source, `scripts.d`) |
| Testability in this study | Tested (all topics) | Not tested, by rule (HANDOFF §1 req. 4) |

### Summary of options it could provide

These points are inferred from the table, and each depends on its cited row.
- The only jellyfin-ffmpeg additions on skellycam's recording path are:
  - `mjpeg_videotoolbox` (Apple hardware JPEG encode);
  - VAAPI and Vulkan encoders on Linux (missing from the PyAV Linux wheel);
  - the `mjpeg_vaapi` full-range fix;
  - QSV, AMF and MF robustness patches.
- None adds a royalty-free hardware *video* codec beyond what upstream has (G7).
- The VAAPI, Vulkan and VideoToolbox-MJPEG gaps could also be closed by building PyAV against a self-built upstream FFmpeg with those flags. That route keeps the in-process API and needs no jellyfin patches, except 0047 for `mjpeg_videotoolbox`.
- Using jellyfin-ffmpeg means:
  - a subprocess pipe, with measured crash-loss and probing costs and no native per-frame PTS;
  - a separate 33-69 MB binary per platform;
  - GPLv3 plus an unresolved FDK-AAC question;
  - being one FFmpeg major version behind PyAV 19.0.2.
