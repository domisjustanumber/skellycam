# jellyfin_ffmpeg: FINDINGS (requirement 4: standard FFmpeg vs jellyfin-ffmpeg)

Machine "Gerald" (Windows 11, i7-14700K + UHD 770, RTX 3070 driver 610.88), 2026-11-09. **Sources only.** jellyfin-ffmpeg was not downloaded, installed or run (HANDOFF §1 requirement 4). The comparison baseline is the FFmpeg 9.0.2 bundled in the **PyAV 19.0.2** wheels. PyAV 18 and skellycam venv results are background only. This topic reports no timing numbers.

**Labels.**
- **measured**: a result file. Here that is usually a string search of fetched source files, or another topic's PyAV 19.0.2 test.
- **source**: a primary source, given as a URL at a pinned tag with an exact quote, accessed 2026-11-09.
- **code**: file:line, in this repo or in a fetched upstream file at a pinned tag.
- **cross-topic**: a fact taken from another topic's notes file, with its own label in that file.
- **background**: an ffmpeg 9.0.2 CLI or PyAV 18 result. These are not the implementation under test.
- **inferred**: reasoning, kept short and marked.
- **NOT VERIFIED**: not checked.

**Paths.**
- `R/` = `research/skellycam_recording/recording_upgrade/results/`
- `J/` = `R/jellyfin_ffmpeg/`
- `JF@tag` = `https://github.com/jellyfin/jellyfin-ffmpeg/blob/v8.1.3-2/`
- `FF@n9.0.2` = `https://github.com/FFmpeg/FFmpeg/blob/n9.0.2/`

---

## 1. Questions answered

1. What is jellyfin-ffmpeg today: version, upstream base and patches? Why does Jellyfin require it?
2. Which hardware encoders, hardware paths and QSV/NVENC/VAAPI/MF fixes does it add, compared with upstream FFmpeg and with the PyAV 19.0.2 wheels?
3. Which of those additions are **options for skellycam's recording path**? The path covers intra-only JPEG, H.264 intra and HEVC intra, on the hardware target (RTX 3000+ and most 2020+ CPUs).
4. What would it cost to use? It has no PyAV binding (so it needs a subprocess pipe), it is distributed separately, and it has licensing questions.
5. Pros and cons table: standard FFmpeg (PyAV 19.0.2 wheels) vs jellyfin-ffmpeg.

## 2. Findings

### 2.1 Version and upstream base

- **F1 source:** the latest release is `v8.1.3-2`.
  - Published 2026-11-03T17:49:24Z.
  - Tag commit `7250de8375a4959ac1c25c139ce9789fdac199fb`.
  - Sources: https://github.com/jellyfin/jellyfin-ffmpeg/releases/tag/v8.1.3-2; `J/releases.txt`.
- **F2 source:** `VERSION` and `RELEASE` at that tag both read `8.1.3` (`JF@tag/VERSION`; `J/build_config_excerpts.txt`).
- **F2 source:** the v8.1.3-1 notes say "New upstream version 8.1.3" (`J/releases.txt`).
- **F3 measured:** PyAV 19.0.2 bundles FFmpeg 9.0.2 with libavcodec 63.1.102.
  - `R/hw_accel_target/sw_encoders_pyav19_win_amd64.json`, keys `ffmpeg_version` and `libavcodec`.
  - `R/licensing/FINDINGS.md` §2.5 (`probe_pyav_19.0.2.json`).
- **F4 source:** upstream tag dates, from the FFmpeg GitHub tag objects (`J/sources_excerpts.txt`, last line):
  - n9.0: 2026-08-03
  - n9.0.2: 2026-09-18
  - n8.1.3: 2026-09-21
- **F5 inferred (F2-F4):** jellyfin-ffmpeg is **one FFmpeg major version behind** the FFmpeg in PyAV 19.0.2 (8.1.3 vs 9.0.2). It was still on 8.1.x three months after FFmpeg 9.0 shipped.
- **F6 source:** the repo `README.md` is upstream FFmpeg's README, unchanged ("FFmpeg is a collection of libraries and tools"; `JF@tag/README.md`).
- **F6 source:** the jellyfin-specific documentation is in `builder/README.md`, `debian/changelog` and the release notes.
- **F6 source:** the repo description is "FFmpeg for Jellyfin with custom extensions and enhancements" (`gh api repos/jellyfin/jellyfin-ffmpeg`; `J/NOTES.md` §1).

### 2.2 Why Jellyfin requires it (a transcoding rationale)

- **F7 source:** "The Jellyfin server uses a modified version of FFmpeg as its transcoder, namely jellyfin-ffmpeg. It enables the Jellyfin server to access the fixed-function video codecs, video processors and GPGPU computing interfaces ..."
  - Page: https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/
  - Source file: `index.md:12` at jellyfin/jellyfin.org@4acfc64a; copy in `J/sources_excerpts.txt`.
- **F8 source:** "Using FFmpeg binaries downloaded from somewhere else will result in partial acceleration." (`index.md:74`)
  - The page defines partial acceleration over these stages: "Video Decoding ... Deinterlacing ... Scaling & Format conversion ... HDR/DV Tone-mapping ... Subtitle burn-in ... Encoding ... Zero-copy in above stages" (`index.md:28-44`).
  - It adds: "Partial acceleration may result in higher CPU usage and lower transcoding speed." (`index.md:50`)
- **F9 inferred:** the JPEG passthrough path (G1) uses no decode, no filters and no encode, so none of the jellyfin-only filters (F12) applies to it.
- **F9 inferred:** the intra re-encode path is different. It covers H.264/HEVC intra from decoded camera MJPEG, and YUY2 to NV12 (requirement 9).
  - That path does use decode and format conversion (4:2:2 to NV12, plus a range change).
  - Jellyfin lists both as acceleration stages (F8).
  - Jellyfin's QSV and D3D11 decode, scale and zero-copy patches would apply there, but only through a CLI child. NOT VERIFIED.

### 2.3 Patch set

- **F10 source:** `JF@tag/debian/patches/series` lists **106 patches**. `J/patch_index.txt` records them with the files each patch touches.
- **F11 measured:** every patch has `hdr_lines=0`. They are quilt diffs with no description header, so the file name is the only description (`J/patch_index.txt`).
- **F12 measured:** the patches register 29 codec, filter and bsf names (`J/upstream_presence.txt`).
  - In upstream n9.0.2, 28 of them are absent. `transpose_cuda` is present.
  - Only **two of the 29 are encoders**: `mjpeg_videotoolbox_encoder` and `mjpeg_rkmpp_encoder`.
  - The rest are decoders (rkmpp, ac4), filters (d3d11, videotoolbox, cuda, opencl, rkrga, vaapi, tonemapx) and the `trim` bsf.
  - Limit: the n8.1.3 column did not search `bitstream_filters.c`, so the `trim_bsf n8.1.3=0` cell was **not checked**.
  - Limit: this count covers newly registered names only. It does not capture patches that change how existing encoders behave (F35).
- **F13 measured:** none of the 29 added names is an NVIDIA encoder. **jellyfin-ffmpeg adds no NVIDIA JPEG encoder** (no nvJPEG path) and nothing for AV1 on Ampere (`J/upstream_presence.txt`).
- **F13 measured:** FFmpeg has no nvJPEG encoder either. Upstream n9.0.2 `allcodecs.c` has 0 case-insensitive matches for `nvjpeg` (verifier grep, `J/VERIFY_provenance.md` §3). The PyAV 19.0.2 wheel scan lists no nvjpeg name (`R/gpu_encode/wheel_hw_codecs.md`).
- **F13 measured:** AV1 hardware encode is missing on Gerald through every API (`R/hw_accel_target/NOTES_functional.md:19-21`).

### 2.4 Additions that touch the recording path

**macOS: `mjpeg_videotoolbox` (patch 0047)**

- **F14 source:** patch 0047 maps `AV_CODEC_ID_MJPEG` to `kCMVideoCodecType_JPEG`. It registers `mjpeg_videotoolbox` ("VideoToolbox MJPEG Encoder") with `AV_CODEC_CAP_HARDWARE`.
  - Patch: `JF@tag/debian/patches/0047-add-mjpeg-videotoolbox-encoder.patch`, lines 46 and 109-126.
  - Copy: `J/upstream_spotcheck_mf_vt.txt`.
- **F15 source:** its input formats are `AV_PIX_FMT_VIDEOTOOLBOX`, `AV_PIX_FMT_NV12` and `AV_PIX_FMT_YUV420P` only (patch lines 81-85).
- **F15 inferred:** there is **no 4:2:2 input**, so camera YUY2 would be written as 4:2:0 JPEG.
- **F16 source:** option `allow_sw` ("Allow software encoding") defaults to 0 (patch line 98).
- **F16 source:** `color_ranges = AVCOL_RANGE_MPEG | AVCOL_RANGE_JPEG` (patch line 119).
- **F17 measured:** upstream n9.0.2 `videotoolboxenc.c` has 0 occurrences of `kCMVideoCodecType_JPEG` (`J/upstream_spotcheck.txt`; `J/upstream_spotcheck_mf_vt.txt`).
- **F18 measured:** the PyAV 19.0.2 macOS wheels (arm64 and x86_64) contain only three VideoToolbox encoders: "VideoToolbox H.264 Encoder", "H.265 Encoder" and "ProRes Encoder" (`R/gpu_encode/wheel_hw_codecs.md`).
- **F19 code:** with `allow_sw=0`, upstream n9.0.2 `videotoolboxenc.c:1702-1705` sets `kVTVideoEncoderSpecification_RequireHardwareAcceleratedVideoEncoder = true`. With default options, the encoder therefore *requires* a VideoToolbox hardware encoder.
- **F19 inferred:** if `mjpeg_videotoolbox` opens with `allow_sw=0`, VideoToolbox reported a hardware JPEG encoder.
- **F19 NOT VERIFIED:** whether Apple silicon M1-M4 encodes JPEG in fixed-function hardware. The encoder was not run.
  - No Apple page fetched lists JPEG in the media engine (cross-topic, `R/hw_accel_target/NOTES_sources_amd_apple_cpu.md:136`).
  - `AV_CODEC_CAP_HARDWARE` is FFmpeg's label, not a statement from Apple.

**Linux: VAAPI (including `mjpeg_vaapi`), Vulkan and QSV**

- **F20 source:** the Debian build configures `--enable-vaapi --enable-vulkan` (`JF@tag/debian/rules:54-56`; `J/build_config_excerpts.txt`).
- **F20 source:** the portable builder enables Vulkan and libplacebo on every target except `mac*` (`builder/scripts.d/47-vulkan/45-vulkan-loader.sh`, `50-libplacebo.sh`; `J/upstream_spotcheck_mf_vt.txt`).
- **F21 source:** these encoders already exist in **upstream** n8.1.3 and n9.0.2:
  - `h264/hevc/av1/vp9/mjpeg_vaapi`
  - `ffv1/h264/hevc/av1_vulkan`
  - Lines: `FF@n9.0.2/libavcodec/allcodecs.c:119,860,861,874,876,889,891,896,920`; copy in `J/upstream_spotcheck_mf_vt.txt`.
  - jellyfin-ffmpeg *enables* these encoders; it does not *add* them.
- **F22 cross-topic (measured):** the PyAV 19.0.2 manylinux x86_64 wheel has **no VAAPI and no Vulkan** encoders (`R/gpu_encode/NOTES.md:130`).
- **F22 measured:** no PyAV 19.0.2 wheel on any OS lists a Vulkan encoder (`R/gpu_encode/wheel_hw_codecs.md`, 0 matches for "vulkan").
- **F23 measured:** the QSV **encoders** are compiled into the PyAV 19.0.2 manylinux x86_64 wheel (`J/verify_method_linux_wheel_qsv.txt`).
  - The bundled `libavcodec` contains the encoder long names "H.264 / AVC / ... (Intel Quick Sync Video acceleration)", "HEVC (Intel Quick Sync Video acceleration)" and "MJPEG (Intel Quick Sync Video acceleration)".
  - Decoder long names take the form "`<X> video (...)`", so these strings are encoders.
  - The short names in `R/gpu_encode/wheel_hw_codecs.md` could not show this on their own, because short names are shared with the decoders.
- **F23 measured:** the same wheel has **no VAAPI** (`J/verify_method_linux_wheel_qsv.txt`).
  - libavutil and libavcodec contain 0 strings with "vaapi".
  - No libva is bundled. `libvpl` and `libdrm` are bundled.
- **F23 code (upstream n9.0.2):** Linux QSV needs a VA display (`J/verify_method_linux_wheel_qsv.txt`).
  - `qsv_internal.h:26-28` defines `AVCODEC_QSV_LINUX_SESSION_HANDLE` only `#if CONFIG_VAAPI && !defined(_WIN32)`.
  - `qsv.c:461` says "This code is only required for Linux since a display handle is required."
  - `hwcontext_qsv.c:2548-2552` returns "No supported child device type is enabled" when no D3D11, DXVA2 or VAAPI is configured.
- **F23 inferred:** the wheel's QSV encoders most likely cannot get a hardware session on Linux. NOT VERIFIED on Linux hardware.
- **F24 source:** patch 0096 changes `mjpeg_vaapi` `color_ranges` (patch 0096, lines 9-10):
  - from `AVCOL_RANGE_MPEG, /* FIXME: implement tagging */`
  - to `AVCOL_RANGE_MPEG | AVCOL_RANGE_JPEG, /* Depends on driver impl */`
- **F24 measured:** upstream n9.0.2 still has the FIXME line (`J/upstream_spotcheck.txt`, `vaapi_encode_mjpeg.c:586`).
- **F25 cross-topic (source):** AMD has no hardware JPEG encoder, and Mesa radeonsi serves AVC, HEVC and AV1 only (`R/hw_accel_target/NOTES_sources_amd_apple_cpu.md:33,92,119`).
- **F25 inferred:** `mjpeg_vaapi` is an Intel-only option.
- **F26 background:** `ffv1_vulkan` (lossless, byte-exact) and `h264/hevc_vulkan` worked on the RTX 3070 through the ffmpeg 9.0.2 CLI, which is not the implementation under test (`R/gpu_encode/NOTES.md:17,20,61,69`).
- **F26 cross-topic (measured):** the UHD 770's **Windows** Vulkan driver 101.7088 exposes no Vulkan Video encode extension (`R/hw_accel_target/NOTES_sources_nvidia_intel.md:38`).
- **F26 NOT VERIFIED:** Vulkan encode on Linux (ANV).

**Windows: Media Foundation adapter selection (patch 0097), QSV and D3D11 patches**

- **F27 source:** patch 0097 enumerates MF encoders with `MFTEnum2` and `MFT_ENUM_ADAPTER_LUID`, taking the LUID from the D3D11 device.
  - It does this only when `use_hw` is set and the input is `AV_PIX_FMT_D3D11` frames.
  - Patch 0097, lines 30-35, 441-442 and 458; copy in `J/upstream_spotcheck_mf_vt.txt`.
- **F28 measured:** upstream n9.0.2 `mfenc.c` and `mf_utils.c` have 0 matches for `ADAPTER_LUID|MFTEnum2|hw_luid`. They enumerate with `MFTEnumEx` (`mf_utils.c:575,580`; `J/upstream_spotcheck_mf_vt.txt`).
- **F29 cross-topic (measured):** through PyAV 19.0.2 on Gerald, `h264_mf` and `hevc_mf` pick the NVIDIA MFT over the Intel one (`R/hw_accel_target/NOTES_functional.md:94`).
- **F30 inferred (F27-F29):** patch 0097 could let `h264/hevc_mf` target the Intel MFT when fed Intel D3D11 frames.
- **F30 inferred:** the value of that is low on Gerald, because `h264/hevc/mjpeg_qsv` already reach the iGPU from PyAV 19.0.2 (measured, `R/hw_accel_target/NOTES_functional.md:15`).
- **F31 source:** patch 0071 retries QSV init when parameters are "not supported under Low power mode". It resets `LowPower` from `MFX_CODINGOPTION_ON` to `MFX_CODINGOPTION_UNKNOWN`, the driver default (patch 0071, lines 9-15; the `LowPower` reset is line 13). The log text says "disabled".
- **F31 measured:** the 0071 bail-out is absent from upstream n9.0.2 (0 matches, `J/upstream_spotcheck.txt`).
- **F31 measured:** on Gerald (UHD 770), the QSV encoders open with default options and encode (`R/hw_accel_target/NOTES_functional.md:15`).
- **F31 inferred:** 0071 is therefore not needed on Gerald.
- **F31 NOT VERIFIED:** other Intel generations.
- **F32 cross-topic (measured):** PyAV 19.0.2's QSV frames-context (`HWAccel`) mode fails with `Could not create the texture (80070057)`. Software NV12 and YUY2 input works (`R/hw_accel_target/NOTES_functional.md:91-92`).
- **F32 inferred, NOT VERIFIED:** the cause is PyAV's auto-built QSV frames pool. The source file marks this cause as inferred and not checked against the PyAV source (`NOTES_functional.md:93`).
- **F32 NOT VERIFIED:** whether jellyfin QSV patch 0011 or 0020 ("add-external-frame-support-for-qsv-enc") would change this failure.
  - Patch 0064 is not a candidate: it touches only `libavfilter/qsvvpp.c` and `vf_hwupload.c` (`J/patch_index.txt:65`).
  - The question is moot in practice, because jellyfin-ffmpeg cannot be used from PyAV (F45).
- **F33 source:** patch 0013 only adds `vendor` as an alias of `vendor_id` "for backward compatibility" (patch 0013, lines 9-10). It does not change adapter discovery.
- **F34 source:** patch 0033 is "add-d3d11va-dxva2-hevc-422-444-decoding-on-intel". It also touches `libavcodec/d3d12va_hevc.c` (`J/patch_index.txt:34`).
- **F34 cross-topic (measured):** PyAV 19.0.2 decoding of the `hevc_qsv` 4:2:2 file failed through d3d11va, d3d12va (NVIDIA adapter) and dxva2, but worked through `hevc_qsv` (`R/hw_accel_target/NOTES_functional.md:126`).
- **F34 NOT VERIFIED:** whether 0033 enables the Intel d3d11va or d3d12va path.
- **F35 source:** other QSV, NVENC, NVDEC, AMF and VAAPI patches are listed with quoted diff content in `J/NOTES.md` §3. Each entry gives the patch number and what it does:
  - 0017: QSV backports.
  - 0018: QSV fixes from cartwheel.
  - 0020: QSV external frames.
  - 0036: VPL runtime init.
  - 0059: VPL runtime init.
  - 0037: QSV default B-frames.
  - 0105: QSV H.264 A53 SEI.
  - 0005: AMF.
  - 0024: VAAPI async depth.
  - 0032: NVENC HEVC HDR metadata.
  - 0083: CUDA backports.
  - 0016: NVDEC (decode).
- **F35 NOT VERIFIED:** whether each of these is already in n9.0.2. The one exception is 0017's `has_b_frames` line, which is absent (`J/upstream_spotcheck.txt`).

### 2.5 Build, bundled libraries and licence

- **F36 source:** the Debian configure line contains `--enable-gpl --enable-version3 --enable-shared` and `--enable-libx264 --enable-libx265 --enable-libfdk-aac ... --enable-ffnvcodec --enable-cuda ... --enable-nvenc` (`JF@tag/debian/rules:9-72`; `J/build_config_excerpts.txt`).
  - x86 adds `--enable-libvpl --enable-amf`.
  - arm64 adds `--enable-rkmpp --enable-rkrga`.
  - This is the Linux `.deb` build.
- **F36b source:** the Windows portable build is set by `builder/scripts.d` (`J/build_config_excerpts.txt:142-171`; Vulkan in `J/upstream_spotcheck_mf_vt.txt`):
  - `50-dxva.sh`: `--enable-dxva2 --enable-d3d11va --enable-d3d12va --enable-mediafoundation` on `win*`
  - `50-ffnvcodec.sh`: NVENC, CUDA and NVDEC except on `mac*`
  - `50-libvpl.sh` and `50-amf.sh`: everywhere except `mac*` and `*arm64`
  - `45-vulkan-loader.sh`: Vulkan except on `mac*`
- **F37 source:** the portable builds use `LICENSE_FILE="COPYING.GPLv3"` (`builder/variants/defaults-gpl.sh:6`).
- **F37 source:** upstream `LICENSE.md` (n8.1.3, lines 61-64) says `COPYING.GPLv3` applies to a version3 build with GPL parts.
- **F37 inferred:** **the binaries are GPLv3**.
- **F38 source:** patch 0026 moves `libfdk_aac` out of `EXTERNAL_LIBRARY_NONFREE_LIST` (`J/build_config_excerpts.txt`).
- **F38 measured:** upstream configure n8.1.3:2004-2007 lists `libfdk_aac` as nonfree (`J/upstream_spotcheck.txt`).
- **F38 measured:** upstream LICENSE.md says "The Fraunhofer FDK AAC and OpenSSL libraries are under licenses which are incompatible with the GPLv2 and v3." It also says `--enable-nonfree` "will cause the resulting binary to be unredistributable" (`J/upstream_spotcheck.txt`).
- **F38 NOT VERIFIED:** whether the "fdk-aac-stripped" fork resolves this.
- **F39 cross-topic (measured):** the PyAV 19.0.2 FFmpeg libraries report "LGPL version 3 or later" (`R/licensing/FINDINGS.md` §2.5; `probe_pyav_19.0.2.json`; `revise_pyav_strip_gpl_control_19.0.2.json`).
- **F39 cross-topic (measured):** the same wheel ships GPL-2.0+ `libx264` and `libx265` DLLs, and deleting them breaks `import av` (same sources).
- **F39 cross-topic (code):** pyav-ffmpeg applies `patches/ffmpeg.patch`, which moves x264 and x265 into the version3 licence list (`R/licensing/FINDINGS.md` §2.5).

### 2.6 Distribution format

- **F40 source:** the v8.1.3-2 release assets (`J/releases.txt`):
  - `.deb` packages for bookworm, trixie, jammy, noble and resolute, amd64 and arm64, 25.5-53.4 MB each.
  - Portable `-gpl` archives: win64 68.5 MB, winarm64 55.8 MB, linux64 60.7 MB, linuxarm64 54.1 MB, mac64 38.1 MB, macarm64 32.9 MB.
  - There is **no `gpl-shared` release asset**.
- **F41 source:** the portable package copies only `bin/*` and `doc` (`builder/variants/default-install.sh:7-11`).
- **F41 source:** macOS builds use `--disable-shared --enable-static` (`defaults-mac.sh:9`).
- **F41 source:** the `.deb` installs `ffmpeg`, `ffprobe` and `libav*.so*`, with no headers (`debian/jellyfin-ffmpeg8.install`).
- **F41 inferred:** no released artifact contains the headers plus shared libraries that a PyAV build needs.

### 2.7 PyAV and jellyfin-ffmpeg

- **F42 source:** "PyAV can also be compiled against your own build of FFmpeg 8.x." (PyAV v19.0.2 `docs/overview/installation.rst:27`)
- **F42 source:** `setup.py:123-131` takes `--ffmpeg-dir=` and looks for `include/` and `lib/` under it, falling back to the directory itself (lines 56-76; `J/sources_excerpts.txt`).
- **F43 inferred:** the "8.x" text sits beside a wheel that bundles 9.0.2 (F3), so the doc may be stale.
- **F43 NOT VERIFIED:** whether PyAV 19.0.2 builds and passes its tests against 8.1.3 plus 106 patches.
- **F44 measured (search log):** **no public PyAV binding or wheel for jellyfin-ffmpeg was found** (`J/sources_excerpts.txt`):
  - `gh search repos` returned 0 hits for two queries.
  - `gh search code` in `setup.py` found 3 repos, all calling the CLI binary.
  - Five PyPI names and conda-forge returned 404.
- **F45 source:** the builder has `gpl-shared` variants for win64, linux64 and linuxarm64 at v8.1.3-2, but none for macOS (`gh api .../builder/variants?ref=v8.1.3-2`, `J/VERIFY_provenance.md` §3).
- **F45 source:** `windows-install-shared.sh` packages `include/`, `lib/` and `.pc` files, which matches the `--ffmpeg-dir` layout (F42).
- **F45 inferred (F41-F44):** a binding would need two self-built pieces on Windows and Linux: a `gpl-shared` jellyfin-ffmpeg and a PyAV source build. macOS has no shared variant and forces `--disable-shared` (F41), so it would need a different build.
- **F45 inferred:** otherwise jellyfin-ffmpeg is usable only as a **subprocess**.

### 2.8 What the subprocess pipe costs (and what it gains)

- **F46 source:** the rawvideo demuxer has no per-frame timestamps: "framerate Set input video frame rate. Default value is 25." (`FF@n9.0.2/doc/demuxers.texi:1040-1041`)
- **F46 source:** the image2 demuxer section says "framerate Set the frame rate for the video stream. It defaults to 25." (`demuxers.texi:622-623`)
- **F46 inferred:** image2pipe uses the same option.
- **F46 inferred:** camera timestamps therefore need a timestamped container on the pipe (NUT/MKV) or a sidecar.
- **F46 cross-topic (measured):** the plan's own recommendation for FreeMoCap is CFR video with the real timestamps in a sidecar (`R/python_integration/NOTES.md:17-20`).
- **F46 inferred:** a sidecar is therefore needed with either FFmpeg build, unless container PTS must carry the real timestamps.
- **F47 background (ffmpeg 9.0.2 CLI as a stand-in for any ffmpeg child; jellyfin-ffmpeg not run):** test conditions (`R/crash_resilience/sfn26_pipe.md`):
  - The sfn26 arguments with CLI defaults: no `flush_packets` (the killed MKV is 16 × 262144 B, `R/crash_resilience/NOTES.md`), image2pipe input, and an x264 transcode or MJPEG `-c copy`.
  - 300 of 600 frames fed, then the child killed.
- **F47 background:** readable frames after killing **the ffmpeg child**:
  - plain MP4: 0/300
  - MKV x264: 246
  - fMP4 x264: 246
  - MKV MJPEG copy: 293
- **F47b background (same test):** killing **the whole process tree** (`taskkill /F /T`) lost exactly the same frames: 0, 246, 246 and 293 (`R/crash_resilience/sfn26_pipe.md`, `tree_killed`).
- **F48 background (same test):** **killing only the feeder** (the parent) left ffmpeg to finalize, giving 300/300 readable frames in all four outputs (`R/crash_resilience/sfn26_pipe.md`, `feeder_killed`).
  - This advantage holds only when the child is outside the killed process tree or job.
  - NOT VERIFIED here: whether a packaged skellycam launcher would kill the child (`R/crash_resilience/FINDINGS.md` §6).
- **F49 background (ffmpeg 9.0.2 CLI stand-in):** 75 frames were fed (2.5 s at 30 fps; the MKV MJPEG copy of those frames is 4,174,837 B). Killing ffmpeg, or the whole tree, then left **no output file** in all four outputs. Killing only the feeder gave 75/75 (`R/crash_resilience/sfn26_pipe_n150.md`).
- **F49 inferred:** ffmpeg was still probing its input. Two source limits fit, and they were not separated (`R/crash_resilience/FINDINGS.md` §2.10):
  - `probesize` 5000000 (`options_table.h:39`)
  - `analyzeduration`, which becomes 5 s (`options_table.h:56`, `demux.c:2638-2641`)
- **F49 NOT VERIFIED:** the size of the startup window. The boundary between 75 and 300 frames was not bisected.
- **F50 cross-topic (measured, PyAV 19.0.2 in-process), live kill:** frames were fed at 30 fps, and the writer was killed with TerminateProcess after 75 frames, with no drain. MJPEG `mkv+fp` kept **74/75** (`R/crash_resilience/verify_method_pyav19_checks.json` → `rt`; `R/crash_resilience/FINDINGS.md` §2.1).
- **F50 cross-topic (measured, PyAV 19.0.2 in-process), `drained` mode:** the writer was killed after all 150 frames were muxed and the encoder drained, but before `close()`. This is deterministic by construction (`R/crash_resilience/FINDINGS.md` §2.1). Readable frames:
  - MJPEG `nut+fp`: 150/150
  - MJPEG `mkv+fp`: 149/150
  - MJPEG `mkv` without fp: 146/150
- **F50 cross-topic (measured):** in-process muxing of JPEG `av.Packet`s keeps container PTS equal to the sidecar PTS on every frame (7 sets, 1,862 frames; `R/python_integration/NOTES.md:16`).
- **F50b inferred (F47-F50):** compared like for like (MKV with no fp), the loss is similar: in-process drained 146/150 vs the child's MJPEG copy at 293/300. Most of the gap in the headline numbers comes from container and flush settings, not from the process model.
- **F50b inferred:** the cost specific to the subprocess is one extra failure mode (the child itself is killed) plus input probing at startup (F49).
- **F50b NOT VERIFIED:** whether `-flush_packets 1`, NUT, or a lower probesize removes the child's loss.

### 2.9 Update cadence

- **F51 source:** jellyfin-ffmpeg published 21 releases between 2025-11-10 and 2026-11-03 (`J/releases.txt`).
  - 7 were prereleases: all of 8.1.1-x, and 8.1.2-1 to 8.1.2-3.
  - 7.1.x stayed the stable line until 8.1.2-4.
- **F52 source:** PyAV published 9 releases from 2026-01-09 to 2026-10-21 (`J/releases.txt`).
- **F52 source:** v19.0.0 (2026-09-29) was released 57 days after FFmpeg n9.0 (F4).
- **F52 FFmpeg version per PyAV release:**
  - 19.0.2 bundles 9.0.2 (measured, F3).
  - 18.0.0 bundles 8.1.2 (background, `R/licensing/FINDINGS.md` §3.2).
  - 19.0.0: NOT VERIFIED; its changelog "Major" section does not mention FFmpeg 9.
  - 18.1.0 (2026-08-12, after n9.0): not checked.
- **F52 inferred:** 57 days is therefore only an upper bound on how long PyAV took to adopt FFmpeg 9.

## 3. Comparison tables

### 3.1 Pros/cons: standard FFmpeg (PyAV 19.0.2 wheels) vs jellyfin-ffmpeg v8.1.3-2

Every data cell carries its label. The last column says which side the row favours for **skellycam's recording path**.

| Aspect | Standard FFmpeg 9.0.2 in PyAV 19.0.2 wheels | jellyfin-ffmpeg v8.1.3-2 | Favours (recording path) |
|---|---|---|---|
| Base version | FFmpeg 9.0.2 (measured, F3) | FFmpeg 8.1.3 + 106 patches (source, F2, F10) | Standard: newer (inferred, F5) |
| How Python uses it | In-process `import av`. JPEG passthrough via `av.Packet`, with PTS exact (cross-topic, F50) | No binding, so a subprocess pipe only (search F44; inferred F45) | Standard (inferred, F45-F50) |
| Encoders added over upstream | None found by name (measured, `R/gpu_encode/wheel_hw_codecs.md`). The wheel scan cannot show the codecs are stock; pyav-ffmpeg patches only the licence lists in configure (code, F39). Stock code: inferred | 2 encoders: `mjpeg_videotoolbox`, `mjpeg_rkmpp` (measured, F12) | Jellyfin on macOS only (inferred, F14-F19) |
| Windows x64 hardware encode | Work on Gerald: NVENC h264/hevc; QSV h264/hevc/vp9/mjpeg; D3D12VA h264/hevc; MF h264/hevc. No AV1 hardware encode (cross-topic, `R/hw_accel_target/NOTES_functional.md:15-21,62-78`) | Same families, plus Vulkan (source, F36b). No extra Windows encoder name (measured, F12). Encoder-behaviour patches for QSV, AMF and MF exist; their upstream status is NOT VERIFIED (F35) | Tie for the target codecs **on Gerald** (inferred). Other Intel generations, AMD AMF and laptops: NOT VERIFIED. Jellyfin adds `h264/hevc/ffv1_vulkan` (source, F20-F21; background F26) |
| Linux x64 hardware encode | NVENC, AMF and V4L2 m2m. QSV encoders are compiled in, but there is no VAAPI, which Linux QSV needs, so QSV is likely non-functional (measured + code + inferred, F23). **No VAAPI, no Vulkan** (measured, F22-F23) | Adds VAAPI (incl. `mjpeg_vaapi` + the 0096 full-range fix) and Vulkan (source, F20, F24). inferred: its VAAPI build also makes QSV usable (F23) | Jellyfin (source + code, F20-F24). QSV on Linux on either side: NOT VERIFIED on hardware |
| macOS hardware encode | VideoToolbox H.264, H.265, ProRes (measured, F18) | Adds `mjpeg_videotoolbox`, 4:2:0 input only. Requires a VT hardware encoder by default (code, F19). Apple fixed-function JPEG NOT VERIFIED (source, F14-F16, F19) | Jellyfin, if hardware JPEG is confirmed (inferred) |
| NVIDIA JPEG (nvJPEG) | Not in FFmpeg or the wheel (measured, F13); separate nvImageCodec | Not added either (measured, F13) | Tie (measured, F13) |
| AV1 on RTX 3070 / UHD 770 | Fails through every API (cross-topic, F13) | No patch can add it; it is a chip limit (inferred, F13) | Tie (inferred) |
| QSV / NVENC / VAAPI / MF fixes | Upstream behaviour. On Gerald, QSV, NVENC and MF work from software frames; QSV `HWAccel` frames mode fails, cause inferred (cross-topic, F29-F32) | 0071 low-power retry, 0097 MF adapter-LUID choice, 0096 mjpeg_vaapi range, 0016/0083 NVDEC/CUDA, 0024 VAAPI async (source, F24, F27, F31, F35) | Jellyfin in principle (source). A fix for a failure skellycam hits on Gerald: none shown (inferred, F30-F32). NOT VERIFIED elsewhere |
| Crash behaviour, live kill | Writer killed after 75 frames fed: MJPEG `mkv+fp` 74/75 (cross-topic, F50) | Child or tree killed after 300 fed, no fp: plain MP4 0/300, MKV/fMP4 x264 246, MKV copy 293. Parent alone killed: 300/300 (background, ffmpeg 9.0.2 CLI stand-in, F47-F48) | Mixed (inferred, F50b). Like for like (MKV, no fp), both sides lose little. The child adds a failure mode, and survives a Python crash only if it is outside the killed tree or job |
| Per-frame timestamps | Packet PTS set per frame (cross-topic, F50) | rawvideo and image2 default to a fixed 25 fps (source, F46). Needs NUT/MKV on the pipe or a sidecar (inferred) | Tie (inferred): the plan keeps real timestamps in a sidecar with CFR video anyway (cross-topic, `R/python_integration/NOTES.md:17-20`). Standard only if container PTS must carry real timestamps |
| Startup data loss | Live kill at 75 frames kept 74/75 with `mkv+fp` (cross-topic, F50) | At least 75 frames (2.5 s) lost when the child is killed early, with CLI defaults (background, F49). Upper bound NOT VERIFIED (probesize or analyzeduration) | Standard (inferred, F49-F50). Whether fp or a lower probesize closes the gap: NOT VERIFIED |
| Distribution | One PyPI wheel per platform: win_amd64 28.2 MB, macOS arm64 18.6 MB, manylinux x86_64 35.0 MB (source, `J/pyav_19.0.2_pypi_files.txt`) | Separate binary per OS/arch, 32.9-68.5 MB, pinned outside pip (source, F40). PyAV still needed for decode and playback (inferred) | Standard (inferred, F40) |
| Licence | Libraries say LGPLv3+, but the wheel ships GPL-2.0+ x264/x265 that cannot be removed (cross-topic, F39) | GPLv3, plus FDK-AAC, which upstream calls GPL-incompatible and unredistributable when enabled (source, F37-F38) | Standard; neither is clean (inferred). FDK question NOT VERIFIED |
| GPL boundary for AGPL skellycam | skellycam is AGPL-3.0+ (code, `LICENSE:1`, `pyproject.toml:15`). AGPLv3 §13 allows combining with GPLv3 works (code, `LICENSE:553-559`) | GPL FAQ: "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs" (source, https://www.gnu.org/licenses/gpl-faq.en.html). Redistribution still needs a source offer and the licence text (inferred) | Standard: not blocked (inferred). Jellyfin release binary: redistribution unclear because of FDK-AAC (NOT VERIFIED, F38). A self-built jellyfin-ffmpeg without FDK would avoid that (inferred) |
| Update cadence | 9 releases in 2026. v19.0.0 came 57 days after n9.0; whether it already bundled 9.0.x is NOT VERIFIED; 19.0.2 does (source/measured, F3, F52) | 21 releases in 12 months, 7 prereleases; still on 8.1.x (source, F51) | Standard for FFmpeg currency (inferred) |
| Platform floor | macOS 11+ x86_64, macOS 14+ arm64, win_amd64/arm64, manylinux_2_28 (source, PyPI wheel tags) | macOS target 12.0 (source, `defaults-mac.sh:25`, not in `J/build_config_excerpts.txt`). Builder README: `win64` "windows>=7", `linux64` glibc>=2.28 (source). Floor of the released build NOT VERIFIED | Tie (inferred) |
| Tested in this study | Yes, all topics (measured) | No, by rule (source, HANDOFF §1 req. 4) | Standard: evidence exists (inferred) |

### 3.2 Options jellyfin-ffmpeg could provide for skellycam's recording path

| Option | Platform / hardware | In PyAV 19.0.2 wheel? | In upstream n9.0.2? | Meets the target / G7? | Caveat |
|---|---|---|---|---|---|
| `mjpeg_videotoolbox` (0047): JPEG encode on VideoToolbox | macOS 12+, Apple silicon and Intel Macs | no (measured, F18) | no (measured, F17) | Royalty-free JPEG (inferred). macOS is not in the RTX/2020-CPU target matrix | 4:2:0 input only (source, F15). Requires a VT hardware encoder by default (code, F19); fixed-function on Apple NOT VERIFIED. CLI only (F45) |
| `mjpeg_vaapi` + full-range tag fix (0096) | Linux, Intel iGPU (AMD has no JPEG encode) | no VAAPI (measured, F22-F23) | encoder yes, fix no (source F21; measured F24) | Royalty-free, Intel 2020+ (inferred, F25) | A self-built PyAV against upstream FFmpeg with `--enable-vaapi` would give the encoder without the patch (inferred). The wheel's `mjpeg_qsv` is likely non-functional on Linux (no VAAPI; F23) |
| `h264/hevc_vaapi` intra | Linux, Intel and AMD | no (measured, F22) | yes (source, F21) | Royalty-bearing; accelerated on Intel/AMD 2020+ (inferred) | Same: not jellyfin-specific |
| `ffv1_vulkan`, `h264/hevc_vulkan` | Windows and Linux. RTX 3070 via the CLI (background, F26). UHD 770 on Windows driver 101.7088: no Vulkan encode extension (cross-topic, F26). Linux ANV: NOT VERIFIED | no (measured, F22) | yes (source, F21) | FFV1 is royalty-free, lossless, intra, GPU compute (background, F26) | Not jellyfin-specific: any upstream build with Vulkan enabled has them. `h264_vulkan` shares the 12-session NVENC pool (cross-topic, `R/gpu_encode/NOTES.md:21`; `nvenc_sessions*.json`). `hevc_vulkan`: NOT VERIFIED. `ffv1_vulkan`: not tested; inferred to use compute, not NVENC |
| MF adapter choice by D3D11 LUID (0097) | Windows, dual-GPU machines | no (measured, F28) | no (measured, F28) | H.264/HEVC only, royalty-bearing (inferred) | Needs D3D11 frame input (source, F27). QSV already reaches Intel on Gerald (cross-topic, F30) |
| QSV low-power retry (0071) | Windows/Linux Intel | no (measured, F31) | no (measured, F31) | Could help H.264/HEVC/JPEG QSV open on parts without low-power support (inferred) | Not needed on Gerald (inferred from measured, F31). Other generations NOT VERIFIED |
| `mjpeg_rkmpp` encoder (0042) | RK3588 boards | no (measured, `R/gpu_encode/wheel_hw_codecs.md`) | no (measured, F12) | Outside the target (inferred) | ARM SBCs only |

## 4. Implications for the plan

1. **Do not adopt jellyfin-ffmpeg for the recording path.** inferred, tied to these findings:
   - It has no PyAV binding (F44), so it would need a subprocess pipe.
   - The pipe adds an extra kill failure mode and a startup probing window (F47-F49, F50b).
   - It is a separate 33-69 MB binary per platform (F40).
   - It is GPLv3 and has an open FDK-AAC question (F37-F38).
   - Its FFmpeg is one major version behind (F5).
   - Timestamps are not a deciding cost, because the plan already uses a sidecar (F46).
2. **On Gerald (UHD 770 + RTX 3070), the Windows hardware target needs nothing from jellyfin-ffmpeg.** inferred.
   - The target paths already work from PyAV 19.0.2: QSV JPEG/H.264/HEVC and NVENC H.264/HEVC intra (F29-F32, `R/hw_accel_target/NOTES_functional.md:15`).
   - jellyfin-ffmpeg's Windows additions are filters, a dual-GPU MF tweak (F12, F27-F30) and encoder-behaviour patches whose upstream status is NOT VERIFIED (F35).
   - Other Intel generations, AMD AMF and laptops: NOT VERIFIED.
3. **No jellyfin patch closes the NVIDIA JPEG gap** (F13). The nvJPEG path (nvImageCodec) stays a separate dependency, whichever FFmpeg build is chosen. inferred.
4. **macOS hardware JPEG is the one unique option** (`mjpeg_videotoolbox`, F14-F17, F19). inferred.
   - The plan may list it as a future option for macOS, run through a CLI child.
   - Mark it NOT VERIFIED: it takes 4:2:0 input only (F15), and Apple hardware JPEG is not confirmed (F19).
5. **Close the Linux gaps by building PyAV against an upstream FFmpeg** configured with `--enable-vaapi --enable-vulkan` (`--ffmpeg-dir`, F42). inferred.
   - On Linux, VAAPI is needed for both the VAAPI encoders and QSV (F22-F23).
   - This keeps the in-process API and needs no jellyfin patch, except 0096 if full-range `mjpeg_vaapi` tagging matters (F24).
   - A Linux Intel run of the wheel's `mjpeg_qsv` is still worth doing, but expect it to fail (F23).
6. **If a subprocess writer is ever used, with any FFmpeg:** inferred.
   - Use a timestamped pipe format (NUT/MKV) or a sidecar (F46).
   - Write NUT, MKV or fMP4, never plain MP4 (F47).
   - Set `-flush_packets 1` and consider a lower `probesize`/`analyzeduration`. Their effect on the child's loss is NOT VERIFIED (F49, F50b).
   - Do not kill the child on shutdown; close its stdin (F48; `R/crash_resilience/FINDINGS.md` §2.10).
   - Keep the child out of any job that is killed with the parent (F47b).
7. The PLAN's requirement-4 table can reuse §3.1 as it stands.

## 5. Pending tonight's bench (23:00)

- No jellyfin-ffmpeg item is queued. Testing it is out of scope by rule (HANDOFF §1 requirement 4).
- These queued PyAV 19.0.2 items decide whether the wheel alone covers the target, and so whether any jellyfin-only option is ever needed:
  - CPU JPEG vs nvJPEG vs `mjpeg_qsv` for YUY2/NV12 at 720p/1080p (HANDOFF §1 req. 11);
  - `B-QSV-1` and `B-QSV-C4` (mjpeg_qsv), `B-NV-1` and `B-NV-C1/C2` (NVENC), and `B-QSV-C1/C2` (QSV H.264/HEVC) (`R/hw_accel_target/NOTES_functional.md:195-204`).
  - Those commands also run `gop30` legs. Only the **intra** legs bear on this topic; GOP results are background (requirement 10).
- The results will not change §3.1. They can only confirm or weaken the Windows row's "Tie for the target codecs on Gerald" verdict.
- No timing numbers from the bench belong in this topic.

## 6. Not tested / limits / NOT VERIFIED

**Not tested**
- Any jellyfin-ffmpeg binary, by rule. Every jellyfin row is source-only.

**NOT VERIFIED**
- Whether Apple silicon encodes JPEG in fixed-function hardware through `mjpeg_videotoolbox` (F19).
- Whether the backport patches (0017, 0018, 0078, 0083, 0090, 0098, 0100, 0103, 0104) and the other encoder patches are already in n9.0.2 (F35). Only these were spot-checked: 0017 (one line), 0071, 0047, 0096 and 0097.
- Whether any jellyfin QSV patch would fix PyAV's QSV frames-context failure, and what causes that failure (F32).
- Whether 0033 enables Intel d3d11va or d3d12va decode of 4:2:2 HEVC (F34).
- Whether PyAV 19.0.2 compiles against FFmpeg 8.1.3 plus the patches (F43).
- Whether a `gpl-shared` jellyfin build works with PyAV; this was not attempted, and macOS has no such variant (F45).
- The FDK-AAC "stripped" licence position (F38).
- The Windows floor of the released `win64` build (§3.1).
- The wheel's QSV encoders on Linux hardware (F23). They are compiled in, but no VAAPI is present, so failure is expected (code, inferred).
- Vulkan encode on Linux Intel (ANV); `hevc_vulkan` and `ffv1_vulkan` against the NVENC session pool (§3.2).
- The probing bound for the ffmpeg child (probesize vs analyzeduration, 75-300 frames). Also whether fp, NUT or a lower probesize removes the child's kill and startup loss (F49, F50b).
- The FFmpeg version in PyAV 19.0.0 and 18.1.0 (F52).

**Limits**
- The subprocess crash-loss numbers come from the gyan ffmpeg 9.0.2 CLI with sfn26's x264/MJPEG-copy arguments and CLI defaults (F47-F49). They are background, not jellyfin-ffmpeg and not the implementation under test.
- The in-process crash numbers mix modes: live kill 74/75 (75 fed) and drained 146-150/150. The child figures are live kills after 300 or 75 frames fed. Treat the cross-side comparison as indicative only (F50b).
- The patch grouping in `J/NOTES.md` §2 is this study's own, made from file names (F11).
- Only one machine was examined (UHD 770, RTX 3070, no AMD).

## 7. How to reproduce

From the repo root, with `gh` authenticated (sources only; nothing is installed or run):

```bash
S=research/skellycam_recording/recording_upgrade/scripts/jellyfin_ffmpeg
OUT=<empty scratch dir>
bash $S/fetch_sources.sh "$OUT"   # releases, patches, build config, upstream files, PyAV docs/setup.py, PyPI JSON, Jellyfin docs; writes upstream_presence.txt
bash $S/spotcheck_mf_vt.sh "$OUT" research/skellycam_recording/recording_upgrade/results/jellyfin_ffmpeg/upstream_spotcheck_mf_vt.txt   # 0097 MF LUID, 0047 pix fmts, Vulkan enables, upstream encoder lines
```

**`J/upstream_spotcheck.txt`: commands not recorded.** No script writes this file, and `J/NOTES.md` contains no grep commands. It records string searches of the fetched upstream files for:
- the 0017 `has_b_frames`/`GopRefDist` line and the 0071 low-power string in n9.0.2 `qsvenc.c`;
- `kCMVideoCodecType_JPEG` in n9.0.2 `videotoolboxenc.c`;
- the `color_ranges` line in n9.0.2 `vaapi_encode_mjpeg.c`;
- `configure` n8.1.3 lines 2004-2008;
- `LICENSE.md` n8.1.3 lines 117-127.

Open item: put these greps in a script.

**Fetch gaps.** `fetch_sources.sh` does not fetch every cited input. Not fetched:
- builder `scripts.d` 25-openssl, 45-opencl, 50-dav1d, libvpx, mfx, schannel, svtav1, x264, x265 and `50-libplacebo`;
- the v8.1.3-1 release notes;
- the PyAV release list and the FFmpeg tag dates;
- the `gh search` and PyPI queries;
- the GPL FAQ and the PyAV changelog;
- the builder variants listing (F45).

These were fetched by hand into the scratchpad. Open item: add them to the script.

**Other limits**
- `upstream_presence.txt` does not search the n8.1.3 `bitstream_filters.c`, so the `trim_bsf n8.1.3` cell is not checked (F12).
- The header of `J/upstream_spotcheck_mf_vt.txt` does not match what `spotcheck_mf_vt.sh` writes. Open item: regenerate the file with the script.
- `defaults-mac.sh:25` (`MACOSX_DEPLOYMENT_TARGET="12.0"`) is not copied into `J/build_config_excerpts.txt`.

**Binding search (F44):**
- `gh search repos 'jellyfin-ffmpeg pyav'`
- `gh search repos 'jellyfin ffmpeg python'`
- `gh search code 'jellyfin-ffmpeg' --filename setup.py|pyproject.toml`
- `curl https://pypi.org/pypi/<name>/json` for the five names in `J/sources_excerpts.txt`

**Linux wheel QSV/VAAPI check (F23):** `J/verify_method_linux_wheel_qsv.txt`. Scripts `strs.py` and `qsv_names.py` are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jellyfin_ffmpeg/verify_method/`. They are not yet copied to `scripts/jellyfin_ffmpeg/`.

**Cross-topic evidence (PyAV 19.0.2 runs):**
- `R/hw_accel_target/NOTES_functional.md` §8
- `R/gpu_encode/NOTES.md`, with the wheel scan in `scripts/gpu_encode/wheel_hw_codecs.py`
- `R/crash_resilience/FINDINGS.md` §2.1 and §2.10 (`sfn26_pipe.md`, `sfn26_pipe_n150.md`, `verify_method_pyav19_checks.json`)
- `R/python_integration/NOTES.md:16-20`
- `R/licensing/FINDINGS.md` §2.5

## 8. Verification

Two verifier reports were applied: `J/VERIFY_provenance.md` and `J/VERIFY_method.md`, both dated 2026-11-09. I re-checked each refutation against the files before applying it.

**Refuted claims, corrected**

| Draft claim | My check | Change |
|---|---|---|
| F49 / §3.1: "Up to the 5 MB probe buffer lost", labelled measured, with probesize as the only cause | `R/crash_resilience/FINDINGS.md:284-287` names both probesize and analyzeduration and says "The bound is NOT VERIFIED". `sfn26_pipe_n150.md` is one point: 75 fed, 0 B, "missing" | F49 is now "≥75 frames lost (background); bound NOT VERIFIED; two candidate limits" |
| §7: upstream_spotcheck commands are "in `J/NOTES.md`" | `grep` of `J/NOTES.md` finds no grep commands. No script names `upstream_spotcheck.txt` | §7 now says "commands not recorded" and lists the checks |
| §3.2: ffv1_vulkan "Shares the 12-session NVENC pool (measured)" | `gpu_encode/NOTES.md:21` and both `nvenc_sessions*.json` contain only `h264_vulkan` | Caveat limited to h264_vulkan; hevc_vulkan NOT VERIFIED; ffv1_vulkan not tested |
| F23: the wheel's QSV "may already be reachable" on Linux | `verify_method_linux_wheel_qsv.txt`: encoder long names present, 0 "vaapi" strings, no libva; upstream `qsv_internal.h:26-28`, `qsv.c:461`, `hwcontext_qsv.c:2548-2552` quoted | F23, the Linux row and implication 5 reversed: likely non-functional; VAAPI needed for QSV too |

**Weak claims, relabelled or rescoped**

| Draft claim | My check | Change |
|---|---|---|
| F50 / Crash row: 150/150 "after kill" | §2.1: those figures are `drained` mode. `verify_method_pyav19_checks.json` → `rt`: MJPEG mkv+fp 74/75 | F50 names the mode; the row compares live kill with live kill |
| F47-F49 labelled measured | CLI stand-in results; F26 already used "background" | Relabelled background |
| Like-for-like comparison | In-process mkv without fp: 146/150. Child MKV copy without fp: 293/300 | Added F50b |
| Tree kill missing | `sfn26_pipe.md` `tree_killed` rows match `ffmpeg_killed` | Added F47b and the job/tree caveat |
| Timestamp row favoured Standard | `python_integration/NOTES.md:17-20`: CFR plus sidecar | Now Tie, with a condition |
| F52: "FFmpeg 9 adopted in 57 days" | The PyAV v19.0.0 changelog "Major" section has no FFmpeg 9 line. 18.1.0 (2026-08-12) was not checked | Rewritten as an upper bound; NOT VERIFIED |
| F13: nvJPEG absence cited to §6 | Scratch `up_allcodecs_n9.0.2.c`: 0 case-insensitive "nvjpeg". `wheel_hw_codecs.md`: 0 | Re-cited |
| F31 | Patch 0071 line 13 sets `MFX_CODINGOPTION_UNKNOWN` | "No need" relabelled inferred; wording fixed |
| F45: "on every OS" | Verifier `gh api` variants listing; `defaults-mac.sh:9` checked | No macOS gpl-shared variant |
| F19 lacked code evidence | Scratch `up_vtenc_n9.0.2.c:1702-1705` checked | Code + inferred lines added |
| F32 cause stated as fact | `NOTES_functional.md:93` marks it inferred. `patch_index.txt:65`: 0064 is filter-only | Cause relabelled; 0064 dropped |
| F9: recording path uses no filters | Requirement 9 includes a decode + convert leg | Rescoped |
| Windows row and implication 2 | Rest on one machine; F35 covers encoder-behaviour patches | Scoped to Gerald; F36b cites scripts.d (`build_config_excerpts.txt:142-171`) instead of debian/rules |
| GPL boundary: "Neither blocks" | F38 FDK question is open | Release binary marked unclear |
| F46 applied to image2pipe | Scratch `demuxers.texi:622-623` (image2): "It defaults to 25." | Quote added; image2pipe sharing marked inferred |
| §3.2 Vulkan row | `NOTES_sources_nvidia_intel.md:38` is the Windows driver | Windows driver scoped; Linux ANV NOT VERIFIED |
| §5 bench items | `NOTES_functional.md:195-204` commands include gop30 | Only the intra legs count |
| Citation and label fixes | Each checked against its file | F3/F39 cited by section and JSON (line numbers drift). F21 adds `:860`. F25 labelled cross-topic. F34 adds d3d12va (`patch_index.txt:34`). F35 reworded. F22 rescoped to `wheel_hw_codecs.md`. F42 "expects" softened. `defaults-mac.sh:25` cited. Encoders-added row relabelled inferred. trim_bsf n8.1.3 marked not checked (scratch has no n8.1.3 bsf file) |

**Open items (not fixed in this revision)**
- Script the `upstream_spotcheck.txt` greps.
- Add the missing fetches to `fetch_sources.sh`.
- Regenerate `upstream_spotcheck_mf_vt.txt` with its script.
- Add `defaults-mac.sh:25` to the excerpt file.
- Copy the verifier's `strs.py` and `qsv_names.py` into `scripts/jellyfin_ffmpeg/`.

**Outcome.** The recommendation stands: do not adopt jellyfin-ffmpeg for the recording path (§4.1). The Linux case for a self-built PyAV with VAAPI is now stronger (F23).
