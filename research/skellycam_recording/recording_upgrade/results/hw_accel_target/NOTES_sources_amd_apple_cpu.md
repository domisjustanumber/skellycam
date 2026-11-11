# hw_accel_target: sources for AMD, Apple, Rockchip and CPUs without an iGPU

Part of the `hw_accel_target` topic (Jellyfin-guided hardware-acceleration target). Scope of this file: AMD APUs and
GPUs (2020+), Apple M1-M4, Rockchip (brief), and CPUs with no iGPU. NVIDIA and Intel are covered in other files of
this topic and in `results/gpu_encode/NOTES.md` (cited, not redone).

Stage rule: functional facts and primary sources only. **No timing, throughput or CPU numbers** in this file.

Labels: **measured** (result file), **source** (primary source, URL, exact quote, accessed 2026-11-09),
**code** (file:line at a pinned tag/commit), **inferred** (kept short, marked). Paths are relative to the repo root.

## 0. Pinned sources used

| id | what | pin |
|---|---|---|
| JF-* | Jellyfin docs, markdown source of the pages under `docs/general/post-install/transcoding/hardware-acceleration/` (`index.md`, `amd.md`, `apple.md`, `rockchip.md`, `known-issues.md`). Rendered at https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/ (+ `/amd`, `/apple`, `/rockchip`, `/known-issues`) | jellyfin/jellyfin.org commit `e9d556985b97cb900951b1790576cab4771528b7` (2026-11-06, last commit touching the folder) |
| K-APU, K-DGPU | Linux kernel `Documentation/gpu/amdgpu/apu-asic-info-table.csv`, `dgpu-asic-info-table.csv` (AMD-maintained product to IP-version map) | torvalds/linux tag `v7.3` |
| K-NV, K-SOC15, K-SOC21, K-SOC24 | amdgpu per-ASIC video-capability tables (`drivers/gpu/drm/amd/amdgpu/{nv,soc15,soc21,soc24}.c`), reported to user space via `AMDGPU_INFO_VIDEO_CAPS` | torvalds/linux tag `v7.3` |
| AMFW | AMF GitHub wiki, "GPU and APU HW Features and Support" (linked from the AMF README as "Find hardware features and support") https://github.com/GPUOpen-LibrariesAndSDKs/AMF/wiki/GPU%20and%20APU%20HW%20Features%20and%20Support | wiki commit `57d4312967855ff63ea80bc2da0cc9e6f6c7fb03` (2026-10-28) |
| AMF-DOC | AMF SDK docs `amf/doc/AMF_Video_Decode_API.md`, `README.md` | GPUOpen-LibrariesAndSDKs/AMF tag `v1.5.3` |
| MESA | Mesa `src/amd/common/ac_video.c`, `ac_video.h` (RadeonSI/RADV video caps) | mesa tag `mesa-26.2.6` |
| AMD-<cpu> | amd.com product/support spec pages (HTML fetched with curl, fields extracted) | accessed 2026-11-09 |
| APL-<id> | Apple tech-spec pages `https://support.apple.com/en-us/<id>` and Apple Newsroom releases | accessed 2026-11-09 |
| FF | FFmpeg `libavcodec/{allcodecs.c,hwaccels.h,videotoolboxenc.c,videotoolbox.c,ffv1enc_vulkan.c,libsvtav1.c,libvpxenc.c,mjpegenc.c}` | FFmpeg tag `n9.0.2` (the FFmpeg that PyAV 19.0.2 bundles: measured libavcodec 63.1.102 in `results/hw_accel_target/sw_encoders_pyav19_win_amd64.json`, same as `results/gpu_encode/NOTES.md` §4) |
| PAF | pyav-ffmpeg `scripts/build-ffmpeg.py`, `scripts/pkg.py` (the build behind the PyAV 19.0.2 wheels) | PyAV-Org/pyav-ffmpeg tag `9.0.2-1` |
| SVT | SVT-AV1 `Docs/Parameters.md` | AOMediaCodec/SVT-AV1 tag `v4.2.0` (the version PAF pins) |
| MPP | rockchip-linux/mpp source tree `mpp/codec/{enc,dec}` | tag `1.1.0` (commit `075030f9`) |

Local copies (temp, not committed): `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/hw_accel_target/src_amd_apple/`.

## 1. Bottom line (this part)

- source + code: **no AMD GPU or APU has hardware VP9 or JPEG encode**, and every AMD hardware codec is **4:2:0 only**.
  - AMFW: "All codecs are 4:2:0". Its encode columns are AVC, HEVC and AV1 only.
  - MESA `ac_video.h:29`: `AC_VIDEO_CODEC_ENC_MAX = AC_VIDEO_CODEC_AV1 + 1`, so the driver only has encode slots for AVC, HEVC and AV1. `ac_video.c:424,468-469,516-517` give encode input formats `nv12` and `p010` only.
- source + code: **AMD AV1 encode needs VCN 4.0 or newer**: RDNA3 and RDNA4 dGPUs, Phoenix/Hawk Point (Ryzen 7x40/8x40, 8000G) and Strix Point APUs.
  - MESA `ac_video.c:478`: `cap->supported = info->vcn_ip_version >= VCN_4_0_0;` (AV1 encode).
  - AMFW table: AV1 encode "N/A" for VCN 2.0 and 3.0/3.1, "8,10b: 8K" for VCN 4.0 and 5.0.
- source: **the RDNA2 iGPU in desktop Ryzen 7000/9000 (Raphael, Granite Ridge) encodes H.264/HEVC only, not AV1**. K-APU lists both at VCN 3.1.2. AMFW lists Raphael as VCN 3.1 and Granite Ridge as VCN 3.0. Either way it has no AV1 encode (rows above).
- source + code: **no Apple silicon M1-M4 has AV1 or VP9 hardware encode**, and FFmpeg has no AV1/VP9 VideoToolbox encoder.
  - APL: M3 and M4 list "AV1 decode" only.
  - FF `allcodecs.c:875,890,907`: the only VideoToolbox encoders are h264, hevc and prores.
- inferred: so **no royalty-free lossy hardware encode covers "most 2020+ CPUs"**. AV1 hardware encode exists only on AMD VCN 4+ (2023+ APUs), NVIDIA Ada/Blackwell and Intel Arc/MTL+ (`results/gpu_encode/NOTES.md` §7). It is absent on Zen 2/Zen 3 APUs, Rembrandt, Raphael and Granite Ridge, every Apple M-series, and every CPU without an iGPU.
- source + code: **H.264 and HEVC 8-bit 4:2:0 encode is the only hardware encode common to every AMD part with an encoder (2020+) and every Apple M-series.**
  - AMFW: AVC "8b: 4K" and HEVC on every VCN row.
  - APL: "Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW" on M1 Pro/Max, M2, M3 and M4.
  - Base M1: see §3.1 (partial).
- measured + code: **on CPUs with no iGPU and no usable GPU encoder, every candidate falls back to CPU software**. In the PyAV 19.0.2 wheel the candidates are libsvtav1 (v4.2.0, **4:2:0 only**), libvpx-vp9 (v1.17.0, 4:2:2 via profile 1), native mjpeg (4:2:2), FFV1 (4:2:2, lossless), and libx264/libx265.
  - libaom-av1 and libopenh264 are **not in the wheel** (`results/hw_accel_target/sw_encoders_pyav19_win_amd64.json`).
- measured: MJPEG passthrough (G1) needs no encoder at all, so CPU class does not matter for it. Evidence: `research/frame_ring_buffer/prototypes/results/p4_mjpeg_passthrough.md` and `results/jpeg_passthrough/NOTES.md`. The p4 numbers are timing evidence from the prior study and are not repeated here.

## 2. AMD

### 2.1 Product to VCN map (2020+)

| product (generation) | VCN, K-APU/K-DGPU (v7.3) | VCN, AMFW | AMD spec page (accessed 2026-11-09) |
|---|---|---|---|
| Ryzen 4000 APU, Renoir (Zen 2) | "Ryzen 4000 series, RENOIR, ... VCN 2.2" (apu csv line 4) | not listed | AMD-4800U: "Graphics Model AMD Radeon Graphics", "Former Codename Renoir", "Launch Date 1/6/2020". No codec rows on the page |
| Ryzen 5000 U, Lucienne (Zen 2) | not listed by name | not listed | AMD-5700U: "Former Codename Lucienne", "Graphics Model AMD Radeon Graphics". NOT VERIFIED: its VCN version (inferred: Renoir silicon, VCN 2.2) |
| Ryzen 5000 APU, Cezanne / Barcelo (Zen 3) | "Ryzen 5000 series / Ryzen 7x30 series, GREEN SARDINE / Cezanne / Barcelo / Barcelo-R, DCN 2.1, 9.3, VCN 2.2" (line 7) | "Ryzen 5xxx, Cezanne, VCN 2.0" | AMD-5700G: "Graphics Model Radeon Graphics", "Former Codename Cezanne". No codec rows |
| Ryzen 6000 APU, Rembrandt (Zen 3+) | "Ryzen 6000 series / Ryzen 7x35 series / Ryzen 7x36 series, YELLOW CARP / Rembrandt / Rembrandt-R, ..., VCN 3.1.1" (line 8) | "Ryzen 6xxx, Rembrandt, VCN 3.1" | AMD-6800U: encode "1080p205 8bpc H.264, ... 2160p51 8bpc H.265"; decode "... 1080p240 10bpc H.265, 1080p240 JPEG 8bpc". Lists **no AV1** decode (see 2.3) |
| Ryzen 7000/9000 desktop, Raphael / Granite Ridge (Zen 4/5, 2-CU RDNA2 iGPU) | "Ryzen 7000 series (AM5), Raphael, 3.1.5, 10.3.6, 3.1.2, ..." and "Ryzen 9000 series (AM5), Granite Ridge, 3.1.5, 10.3.6, 3.1.2, ..." (lines 9-10; the 3rd value is the VCN column) | "Ryzen 7xxx, Raphael, VCN 3.1"; "Ryzen 9xxx, Granite Ridge, VCN 3.0" | AMD-7700X / AMD-9700X: "Graphics Model AMD Radeon Graphics", "Graphics Core Count 2". No codec rows |
| Ryzen 7x40 / 8x40 / 8000G, Phoenix / Hawk Point (Zen 4) | "Ryzen 7x40 series, Phoenix, ..., 4.0.2" and "Ryzen 8x40 series, Hawk Point, ..., 4.0.2" (lines 13-14) | "Ryzen 8xxx, Phoenix, VCN 4.0" | AMD-7840U, AMD-8840U, AMD-8700G: "Max Video Encode Bandwidth (SDR) 1080p630 8bpc H.264, ... 4320p43 8bpc H.265, 1080p864 8/10bpc AV1, ... 4320p60 8/10bpc AV1" |
| Ryzen AI 300, Strix Point (Zen 5) | "Ryzen AI 300 series, Strix Point, 3.5.0, 11.5.0, 4.0.5, ..." (line 15) | not listed | AMD-HX370: same encode row as Phoenix, including "8/10bpc AV1" |
| RX 5000, Navi 1x (RDNA1) | "RX 5600/5700 ... NAVI10 ... VCN 2.0.0"; "5300/5500 ... NAVI14 ... VCN 2.0.2" (dgpu lines 20-21) | RX 53xx-57xx: VCN 2.0 | (not fetched) |
| RX 6000, Navi 2x (RDNA2) | Navi21/22 "VCN 3.0.0", Navi23 "VCN 3.0.16", "RX 6500M /6300M ... BEIGE_GOBY ... VCN 3.0.33" (lines 22-25) | RX 66xx-69xx: VCN 3.0; RX 63xx/64xx/65xx Navi24: VCN 3.0 "Decode only" | gpu_encode §7.3: RX 6600 page has H.264/HEVC encode and AV1 decode, with no AV1 encode row |
| RX 7000, Navi 3x (RDNA3) | "RX 7900 XT/XTX ... VCN 4.0.0", "RX 7800 XT ... VCN 4.0.0", "RX 7600M ... VCN 4.0.4" (lines 26-28) | RX 75xx-79xx: VCN 4.0 | gpu_encode §7.3: RX 7600 page "AV1 Encode Yes" |
| RX 9000, Navi 4x (RDNA4) | "RX 9070 (XT) ... VCN 5.0.0", "RX 9060 XT ... VCN 5.0.0" (lines 29-30) | RX 906x/907x: VCN 5.0 | NOT VERIFIED (page is JS-rendered, gpu_encode §7.3) |

- source: AMFW and K-APU disagree on version numbers for Cezanne (2.0 vs 2.2) and Granite Ridge (3.0 vs 3.1.2). Both sides of each pair fall in the same capability band (no AV1 decode for VCN 2.x; AV1 decode but no AV1 encode for VCN 3.x), so the matrix below does not change. inferred: the wiki gives major versions only.

### 2.2 Codec capability per VCN (vendor sources)

AMFW codec table, verbatim ("All codecs are 4:2:0"; "AV1 encoder supported in one VCN instance only, except Strix Halo where it is supported on both."):

| VCN | dec AVC | dec HEVC | dec VP9 | dec AV1 | enc AVC | enc HEVC | enc AV1 |
|---|---|---|---|---|---|---|---|
| 2.0 | 8b: 4K | 8,10b: 8K | 8,10b: 8K | N/A | 8b: 4K | 8,10b: 4K | N/A |
| 3.0, 3.1 | 8b: 4K | 8,10b: 8K | 8,10b: 8K | 8,10b: 8K | 8b: 4K | 8,10b: 8K | N/A |
| 4.0 | 8b: 4K | 8,10b: 8K | 8,10b: 8K | 8,10,12b: 8K | 8b: 4K | 8,10b: 8K | 8,10b: 8K |
| 5.0 | 8b: 4K | 8,10b: 8K | 8,10b: 8K | 8,10,12b: 8K | 8b: 4K | 8,10b: 8K | 8,10b: 8K |

Cross-checks:
- code K-SOC15 `soc15.c:215-221`: VCN 2.2 (Renoir/Cezanne) uses `vega_video_codecs_encode` (AVC and HEVC, `soc15.c:93-94`) and `rn_video_codecs_decode` (`soc15.c:140-146`: MPEG2, MPEG4, AVC, VC1, HEVC, JPEG, VP9; **no AV1**).
- code K-NV `nv.c:254-259`: VCN 3.1.1 and 3.1.2 (Rembrandt, Raphael, Granite Ridge) use `sc_video_codecs_encode` (AVC, HEVC; `nv.c:98-99`) and `yc_video_codecs_decode` (`nv.c:199-203`: AVC, HEVC, VP9, JPEG, **AV1**).
- code K-NV `nv.c:261-265` with `nv.c:192-195`: VCN 3.0.33 (BEIGE_GOBY) has `bg_video_codecs_encode` with `.codec_count = 0` (no encoder). Its decode list (`nv.c:182-184`) is AVC, HEVC, VP9, with **no AV1**.
- code K-SOC21 `soc21.c:52-55,177-212`: VCN 4.0.0/4.0.2/4.0.4/4.0.5/4.0.6 encode AVC, HEVC and **AV1** on instance 0. Instance 1 (`soc21.c:58-60`) has AVC and HEVC only, matching AMFW's "one VCN instance only". Decode (`soc21.c:73-78`): AVC, HEVC, JPEG, VP9, AV1.
- code K-SOC24 `soc24.c:50-53,61-66`: VCN 5.0.0 (RX 9060/9070) encodes AVC, HEVC and AV1, and decodes AVC, HEVC, JPEG, VP9 and AV1.
- code MESA `ac_video.c:398-399,434-435`: the Linux RadeonSI/RADV encoder caps AVC and HEVC at `max_width = 4096`, `max_height = 2304`. AV1 is 8192x4352 (`ac_video.c:481-482`). That is lower than AMFW's "8K" for HEVC encode on VCN 3+. NOT VERIFIED which limit applies on Windows/AMF.
- code MESA `ac_video.c:459,468-469`: HEVC Main10 encode when `vcn_ip_version >= VCN_2_0_0`, input `nv12`/`p010`.
- code MESA `ac_video.c:490-491`: AV1 encode alignment is `width_alignment = ... >= VCN_5_0_0 ? 8 : 64` and `height_alignment = ... ? 2 : 16`, so VCN 4 needs 64-wide and 16-high alignment.
- code MESA `ac_video.c:540-545`: the VCN JPEG **decoder** outputs `nv12`, `y8u8y8v8_422` (YUYV) and `y8_400`, plus `y8_u8_v8_444/440` on VCN >= 2.0. So **4:2:2 JPEG decode to YUYV exists on Linux**. AMD has no JPEG encoder (see §1).
- source AMF-DOC `AMF_Video_Decode_API.md` (v1.5.3) lines 94 and 106: "AMFVideoDecoderUVD_MJPEG | Motion JPEG" and "The Motion JPEG codec supports the `AMF_SURFACE_YUY2` format in addition to `AMF_SURFACE_NV12`." Lines 95-98: HEVC and VP9 decoders are "(8-bit 4:2:0 sampling)" / "(10-bit 4:2:0 sampling)".
- source AMF-DOC README v1.5.3 line 49: "Version 1.5.0: ... Added 4:4:4/4:2:2 chroma subsampling support for VideoConverter color space conversion and scaling." That is the converter, not the encoder.

### 2.3 Jellyfin AMD claims vs vendor sources

| Jellyfin claim (JF-amd unless noted; line) | vendor primary source | verdict |
|---|---|---|
| "On Windows **AMF** is the only available method." (14) | FF `allcodecs.c:851,867,880` also declares `av1/h264/hevc_d3d12va` encoders, and `*_mf` encoders (859,868,883); they are in the PyAV win_amd64 wheel (measured `results/gpu_encode/wheel_hw_codecs.md`). Whether AMD's Windows driver serves them: NOT VERIFIED (no AMD hardware here) | Jellyfin-only for its own build; FFmpeg has other paths, unverified on AMD |
| "**VA-API** - Preferred on all GPUs, ... **AMF** - Not recommended, limited support, hardware encoder only, closed source." (18-20) | measured: the PyAV 19.0.2 manylinux x86_64 wheel has `h264/hevc/av1_amf` but **no `*_vaapi`** codec names, even though the scan searched for them (`scripts/gpu_encode/wheel_hw_codecs.py:27`, `results/gpu_encode/wheel_hw_codecs.md`). code PAF `build-ffmpeg.py`: 0 matches for "vaapi" or "vulkan" | AGREE on VA-API being the open path; **it is not reachable from the PyPI PyAV wheel on Linux** |
| "Unlike NVIDIA NVENC, there is no concurrent encoding sessions limit on AMD GPU." (28) | no session limit stated in AMF-DOC or AMFW. AMFW only says "AV1 encoder supported in one VCN instance only" | Jellyfin-only (NOT VERIFIED) |
| "RX 6400/6500 series don't have video encoders." (56) | AMFW: RX 63xx/64xx/65xx Navi24 "Decode only". K-NV: VCN 3.0.33 encode `.codec_count = 0` | AGREE |
| "AMD Ryzen APU (G/GE/H/HS/HX suffixed models) and Zen 4 based processors have integrated graphics." (60) | AMD-8700F and AMD-8400F: "Graphics Model Discrete Graphics Card Required", "Former Codename Phoenix" (both Zen 4 Phoenix parts with no iGPU) | **DISAGREE** (not all Zen 4 parts have an iGPU) |
| "Decoding & Encoding H.264 8-bit - Any AMD GPU supporting AMF or VA-API" (68) | AMFW: AVC enc "8b: 4K" on every VCN row; K-* encode tables include AVC for every encoding VCN | AGREE (except decode-only Navi24, which Jellyfin flags separately) |
| "Encoding HEVC 10-bit - Ryzen 4000 series APU (Renoir), Radeon RX 5000 series (Navi 1x) and newer" (82) | AMFW VCN 2.0: HEVC enc "8,10b: 4K". MESA `ac_video.c:459`: `main10 = vcn_ip_version >= VCN_2_0_0` | AGREE |
| "Decoding AV1 8/10-bit - Radeon RX 6000 series (Navi 2x), Ryzen 6000 mobile APU and newer (except RX 6400/6500)" (90) | AMFW VCN 3.0/3.1: AV1 dec "8,10b: 8K". K-NV yc table (VCN 3.1.x) includes AV1, bg table (VCN 3.0.33) does not. But K-APU line 7 maps "Ryzen 7x30" (Barcelo-R, newer branding) to VCN 2.2, whose decode table (`soc15.c:140-146`) has no AV1. AMD-6800U lists no AV1 decode at all, against K-NV and AMFW | AGREE for Navi 2x and Rembrandt. "and newer" is **overbroad** for Ryzen 7x30 |
| "Encoding AV1 8/10-bit - Radeon RX 7000 series (Navi 3x), Ryzen 7000/8000, AI 7/9 HX mobile APU, Ryzen 8000G desktop APU and newer" (92) | AV1 encode needs VCN >= 4.0 (MESA `ac_video.c:478`; AMFW). K-APU: Ryzen 7x40 and 8x40 = VCN 4.0.2; Strix Point = 4.0.5; 8700G page lists AV1 encode. But K-APU also maps other "Ryzen 7000" mobile lines to VCN < 4: 7x20 Mendocino 3.1.1 (line 12), 7x35 Rembrandt-R 3.1.1 (line 8), 7x30 Barcelo-R 2.2 (line 7), 7x45 Dragon Range 3.1.2 (line 11). "and newer" would also take in Ryzen 9000 desktop (Granite Ridge, VCN 3.1.2/3.0: no AV1 enc) | AGREE for RX 7000, 7x40/8x40/8000G and AI 300. **DISAGREE** for "Ryzen 7000 mobile" in general and for desktop Ryzen 7000/9000 |
| "VCN4.0 where the AV1 encoder required a height of 64 (1080p wrongly encoded as 1082p with black pixels)" fixed in VCN5.0 (106) | MESA `ac_video.c:490-491`: the VCN 4 AV1 alignment is width 64 / height 16, and VCN 5 is width 8 / height 2 | partial AGREE (VCN 4 has an alignment constraint that VCN 5 relaxes). The exact 64-height figure is Jellyfin-only |
| "VCN5(RX 9000) >> VCN4(RX 7000) > VCN3/VCN2(RX 6000/RX 5000/Renoir) ..." (110) | quality/speed ranking: no vendor source checked | Jellyfin-only (not used) |
| known-issues: "AMD Radeon RX 5000 and newer RDNA series ... Windows graphics driver issue ranging from **Adrenalin 24.1.1 to 24.4.1** ... error code of `-60` ... **Adrenalin 24.5.1** and newer drivers fix this issue." (JF-known-issues 12) | not checked against AMD release notes | Jellyfin-only. Note as a minimum-driver hint |
| known-issues: "Some Linux distros intentionally disabled the H.264 and HEVC codecs from the Mesa VA-API driver." Fix: "`-D video-codecs=all`" (JF-known-issues 16-33) | not checked against distro sources | Jellyfin-only. Relevant: H.264/HEVC VA-API may be missing on Fedora/openSUSE stock Mesa |

### 2.4 AMD: FFmpeg API per OS (n9.0.2) and what PyAV 19.0.2 ships

| OS | encode API (FFmpeg encoders) | decode API | in PyAV 19.0.2 wheel? |
|---|---|---|---|
| Windows | `h264/hevc/av1_amf` (code FF `allcodecs.c:864,877,857`); `*_d3d12va` and `*_mf` (vendor-neutral, AMD support NOT VERIFIED) | `av1/h264/hevc/vp9_amf` decoders (`allcodecs.c:858,865,878,915`); d3d11va/d3d12va/dxva2 hwaccels for h264/hevc/vp9/av1 (`hwaccels.h:23-92`). **No MJPEG hwaccel** for d3d11va/d3d12va/dxva2 and no `mjpeg_amf` decoder (only `mjpeg_nvdec`/`mjpeg_vaapi` hwaccels: `hwaccels.h:54-55`) | yes: amf, d3d12va, mf, d3d11va, dxva2 (measured `results/gpu_encode/wheel_hw_codecs.md`, NOTES §4 `hwdevices_available`) |
| Linux | `*_vaapi` (`allcodecs.c:860,874,889,896,920`), of which Mesa radeonsi serves AVC/HEVC/AV1 only (MESA `ac_video.h:29`); `*_amf` (needs AMD's closed AMF runtime, per JF-amd 20-22); `*_vulkan` (RADV; `results/gpu_encode/NOTES.md` §7.5) | vaapi hwaccels including **`mjpeg_vaapi`** (`hwaccels.h:55`) → VCN JPEG with YUYV 4:2:2 output (MESA `ac_video.c:543`); vulkan hwaccels | amf only. **No vaapi, no vulkan** (measured wheel scan; code PAF) |
| macOS (Intel Macs with AMD GPU) | VideoToolbox (§3) | VideoToolbox | yes (videotoolbox) |

- inferred: on AMD, **4:2:2 camera MJPEG cannot be HW-decoded through PyAV wheels on any OS** (Windows has no FFmpeg path; the Linux path needs VA-API, which the wheel lacks). This needs a functional test on AMD hardware before it is relied on. NOT VERIFIED.

## 3. Apple (VideoToolbox)

### 3.1 Vendor statements per chip

| chip | Apple primary source (exact) | page |
|---|---|---|
| M1 | Newsroom 2020-11-10: "Low-power, highly efficient media encode and decode engines for great performance and extended battery life." The base-M1 spec pages (MacBook Air M1 111883, Mac mini M1 111894, iMac M1 111895) have **no media-engine row**. MacBook Pro 13 M1 (111893) lists only "Video Playback Supported formats include HEVC, H.264, and ProRes" | https://www.apple.com/newsroom/2020/11/apple-unleashes-m1/ ; APL-111883, APL-111893 |
| M1 Pro / Max / Ultra | "Media engine Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW / Video decode engine / Video encode engine / ProRes encode and decode engine". M1 Max: "Two video encode engines / Two ProRes encode and decode engines". M1 Ultra: "Two video decode engines / Four video encode engines / Four ProRes encode and decode engines" | APL-111902 (MBP 14 2021), APL-111901 (MBP 16 2021), APL-111900 (Mac Studio 2022) |
| M2 | "Media engine Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW / Video decode engine / Video encode engine / ProRes encode and decode engine". Newsroom: "The media engine includes a higher-bandwidth video decoder, supporting 8K H.264 and HEVC video." | APL-111867 (MacBook Air M2); https://www.apple.com/newsroom/2022/06/apple-unveils-m2-with-breakthrough-performance-and-capabilities/ |
| M3 | "Media Engine Hardware-accelerated H.264, HEVC, ProRes, and ProRes RAW / Video decode engine / Video encode engine / ProRes encode and decode engine / AV1 decode". Newsroom: "for the first time, the media engine supports AV1 decoding" | APL-118551 (MacBook Air 13 M3), APL-117735 (MBP 14 M3); https://www.apple.com/newsroom/2023/10/apple-unveils-m3-m3-pro-and-m3-max-the-most-advanced-chips-for-a-personal-computer/ |
| M4 / M4 Pro / M4 Max | same list ending "AV1 decode". M4 Max: "Two video encode engines / Two ProRes encode and decode engines / AV1 decode" | APL-122209 (MacBook Air 13 M4), APL-121552, APL-121553 |

- source: no Apple page fetched lists VP9 or JPEG in the media engine, or any AV1 **encode**.
- code FF `videotoolboxenc.c:2852,2893` (`h264_videotoolbox`, `hevc_videotoolbox`) and `allcodecs.c:875,890,907`: three VideoToolbox encoders, h264, hevc and prores. **No av1/vp9/mjpeg VideoToolbox encoder.**
- code FF `videotoolbox.c:921-961` and `hwaccels.h:30,43,52,71,73,91`: VideoToolbox **decode** hwaccels for h263, h264, hevc, mpeg1/2/4, prores, prores_raw, vp9 and av1. No mjpeg.
- code FF `videotoolboxenc.c:2731-2738` (HEVC input formats include `AV_PIX_FMT_P210`), `:2874` (`"main42210","Main 4:2:2 10 Profile"`) and `:987-989` (maps to `kVTProfileLevel_HEVC_Main42210_AutoLevel`). So FFmpeg can *request* HEVC 4:2:2 10-bit from VideoToolbox. NOT VERIFIED whether any M-series encodes it in hardware (Apple's spec pages do not say).
- code FF `videotoolboxenc.c:2748-2753`: the ProRes encoder takes `AV_PIX_FMT_UYVY422` and, when the SDK has it, `AV_PIX_FMT_NV16` (8-bit 4:2:2). It is the only VideoToolbox path that takes 8-bit 4:2:2 input. ProRes licensing belongs to the licensing topic.
- measured: the PyAV 19.0.2 macOS wheels (arm64 and x86_64) contain the "VideoToolbox H.264 Encoder", "VideoToolbox H.265 Encoder" and "VideoToolbox ProRes Encoder" (`results/gpu_encode/wheel_hw_codecs.md`).

### 3.2 Jellyfin Apple claims vs Apple sources

| Jellyfin claim (JF-apple; line) | Apple source | verdict |
|---|---|---|
| "[VideoToolbox] is the only available method on macOS." (12) | FF: the only Apple hardware codec API in FFmpeg is VideoToolbox (`allcodecs.c`, `hwaccels.h`) | AGREE (code) |
| "Any VideoToolbox-supported Mac supports decoding and encoding H.264 8-bit." (54) | M1 Pro and later: "Hardware-accelerated H.264 ... Video encode engine". Base M1: encode engine stated, codecs not named | AGREE for M1 Pro+ and M2-M4; partial for base M1 (codec not named by Apple) |
| "Macs from 2017 and later, excluding the MacBook Air (13-inch, 2017), support decoding and encoding HEVC." (60) | as above (HEVC listed for M1 Pro+ and M2-M4) | AGREE for M-series except base M1 (vendor does not name HEVC encode); Intel Macs not checked |
| "Starting with the M3 series, Apple Silicon-based Mac supports hardware-accelerated decoding of AV1 video." (64) | M3 newsroom "for the first time, the media engine supports AV1 decoding"; M3/M4 spec "AV1 decode" | AGREE |
| AV1 / VP9 encode | Jellyfin is silent. Apple lists none. FFmpeg has no encoder | vendor + code: **N** |
| "The "Max" variant chips come with an additional video encoding engine." (70) | M1 Max / M4 Max: "Two video encode engines" | AGREE |
| "The "Ultra" variant chips feature 2 video decoding engines and 4 video encoding engines" (72) | M1 Ultra: "Two video decode engines / Four video encode engines" | AGREE |
| "The simultaneous session count is a soft limit." (78) | no Apple statement found | Jellyfin-only |

## 4. Rockchip (brief)

- source JF-rockchip 18-20: "Hardware accelerated transcoding is supported and verified with the Rockchip VPU of RK3588/3588S SoC. Linux is the only supported platform and **RKMPP** is the only available method."
- source JF-rockchip 74-76: "**Decoding AV1 8/10-bit** - Rockchip RK3588/3588S and RK3576 SoC." / "**Encoding AV1 8/10-bit** - As of the RK3588 series, there is no Rockchip SoC that supports AV1 encoder."
- code MPP @1.1.0: `mpp/codec/enc/` contains `h264`, `h265`, `jpeg` and `vp8`, with no `av1` or `vp9`. `mpp/codec/dec/` contains `av1`, `h264`, `h265`, `jpeg`, `vp8`, `vp9` and others. → AGREE with Jellyfin on "no AV1 encoder" at the library level. MPP also has a JPEG encoder, which is vendor-only (Jellyfin is silent). Per-SoC hardware: NOT VERIFIED (MPP is one library for many SoCs).
- code FF `allcodecs.c:156-163,377,380`: upstream FFmpeg n9.0.2 has `h264_rkmpp` and `hevc_rkmpp` encoders and h264/hevc/vp8/vp9 rkmpp decoders, with no av1 or mjpeg rkmpp codec.
- code PAF `build-ffmpeg.py`: 0 matches for "rkmpp". measured: the PyAV 19.0.2 manylinux aarch64 wheel has only `h264/hevc/vp8/vp9_v4l2m2m` hardware names (`results/gpu_encode/wheel_hw_codecs.md`). So RKMPP is **not reachable from PyAV wheels**.
- source JF-rockchip 32: "Unlike NVIDIA NVENC, there is no concurrent encoding sessions limit on Rockchip VPU." Jellyfin-only.

## 5. Per-generation matrix: hardware ENCODE / DECODE (AMD, Apple, Rockchip, no-iGPU)

Cell = enc / dec. Y = yes, N = no, P = partial (constraint given). All AMD codecs are 4:2:0 (AMFW). Source ids refer to §2-§4. "JF" = what Jellyfin says, then the verdict.

| generation | H.264 | HEVC | AV1 | VP9 | MJPEG/JPEG | FFV1 (Vulkan compute) |
|---|---|---|---|---|---|---|
| AMD Zen 2/3 APU: Renoir, Lucienne*, Cezanne, Barcelo (VCN 2.2) | Y 8b 4K / Y | Y 8/10b 4K / Y 8/10b | N / N (`soc15.c:140-146`; AMFW "N/A"). JF: AV1 decode starts at "Ryzen 6000 mobile" → AGREE | N / Y 8/10b (AMFW, K-SOC15) | N / Y (K-SOC15 JPEG 16384²; 4:2:2 out on Linux, MESA). Windows/PyAV path: none | NOT VERIFIED (not in PyAV) |
| AMD Rembrandt (VCN 3.1.1), Mendocino (3.1.1) | Y / Y | Y 8/10b 8K / Y | N / Y 8/10b (K-NV yc; AMFW). AMD-6800U page omits AV1 (vendor-internal gap). JF AGREE | N / Y | N / Y (AMD-6800U "1080p240 JPEG 8bpc") | NOT VERIFIED |
| AMD Raphael / Granite Ridge desktop iGPU (VCN 3.1.2; AMFW 3.1 / 3.0) | Y / Y | Y / Y | **N** / Y (K-NV `nv.c:254-259`). JF: "and newer" wording takes in Granite Ridge → DISAGREE | N / Y | N / Y | NOT VERIFIED |
| AMD Phoenix / Hawk Point / 8000G (VCN 4.0.2), Strix Point (4.0.5) | Y / Y | Y / Y | **Y 8/10b, 1 instance; VCN4 alignment 64w/16h** / Y 8/10/12b. AMD-7840U/8840U/8700G/HX370 list "8/10bpc AV1" encode. JF AGREE (for 7x40/8x40/8000G/AI 300) | N / Y | N / Y | NOT VERIFIED |
| AMD RDNA1 RX 5000 (VCN 2.0) | Y / Y | Y 8/10b 4K / Y | N / N (AMFW; K-NV `nv.c:81-88` has no AV1) | N / Y | N / Y (K-NV JPEG 8192²) | NOT VERIFIED |
| AMD RDNA2 RX 6600-6900 (VCN 3.0) | Y / Y | Y / Y | N / Y (JF AGREE) | N / Y | N / Y | NOT VERIFIED |
| AMD RDNA2 RX 6400/6500 (Navi24, VCN 3.0.33) | **N** / Y | **N** / Y | N / **N** (K-NV bg table has no AV1, against AMFW's VCN 3.0 row). JF AGREE | N / Y | N / N (bg table has no JPEG) | NOT VERIFIED |
| AMD RDNA3 RX 7000 (VCN 4.0.x) | Y / Y | Y / Y | Y 8/10b (1 of 2 VCNs) / Y (JF AGREE; RX 7600 page) | N / Y | N / Y | NOT VERIFIED |
| AMD RDNA4 RX 9060/9070 (VCN 5.0.0) | Y / Y | Y / Y | Y / Y (K-SOC24; AMFW). JF AGREE | N / Y | N / Y | NOT VERIFIED |
| Apple M1 (base) | P (encode engine exists, codecs not named by Apple) / Y (playback list) | P / Y | N / N | N / NOT VERIFIED (FFmpeg has `vp9_videotoolbox` hwaccel; Apple silent) | N (no FFmpeg VT JPEG path) / N via FFmpeg | NOT VERIFIED (MoltenVK) |
| Apple M1 Pro/Max/Ultra, M2 | Y / Y | Y (4:2:2 10-bit: NOT VERIFIED) / Y | N / N | N / NOT VERIFIED | N / N via FFmpeg | NOT VERIFIED |
| Apple M3, M4 | Y / Y | Y / Y | **N / Y** (JF AGREE) | N / NOT VERIFIED | N / N via FFmpeg | NOT VERIFIED |
| Rockchip RK3588 (Linux, RKMPP) | Y / Y (JF) | Y / Y (JF) | N / Y (JF; MPP tree AGREE) | N / Y (MPP dec tree) | Y enc in MPP (vendor-only) / Y dec | n/a |
| CPU with no iGPU (Ryzen 3000/5000 non-G, Ryzen 8400F/8700F, Intel F/KF) and no GPU encoder | software only (see §6) | software | software | software | software | software FFV1 (CPU) |

\* Lucienne VCN version is inferred (see §2.1).

Sessions / stream limits:
- measured: NVIDIA 12 sessions on driver 610.88 (`results/gpu_encode/nvenc_sessions.json`). JF-known-issues line 94: "590 and newer | Up to 12 encoding sessions" → AGREE.
- AMD: no vendor limit statement; JF says none (Jellyfin-only). AMFW: AV1 encode runs on only one VCN instance (except Strix Halo).
- Apple: Max/Ultra have 2/4 encode engines (AGREE). Session count: Jellyfin-only "soft limit".
- Rockchip: Jellyfin-only "no ... limit".

4:2:2 summary:
- **No AMD or Apple hardware path encodes 8-bit 4:2:2 H.264/HEVC/AV1/VP9.**
  - AMD: AMFW "All codecs are 4:2:0"; MESA inputs nv12/p010.
  - Apple: HEVC 4:2:2 is 10-bit (P210/main42210), and hardware support is NOT VERIFIED.
  - Apple ProRes accepts 8-bit 4:2:2 input (FF code).
- So cameras' YUY2 / 4:2:2 MJPEG must be converted to NV12 before any AMD/Apple/NVIDIA-Ampere hardware encode. inferred, consistent with `results/gpu_encode/NOTES.md` §8.

## 6. CPUs without an iGPU: software encode options

### 6.1 Which CPUs (primary sources)

- source AMD support pages (accessed 2026-11-09), field "Graphics Model":
  - Ryzen 7 3700X and Ryzen 5 3600 (Matisse): "Discrete Graphics Card Required" (launch 7/7/2019);
  - Ryzen 7 5800X ("11/5/2020") and Ryzen 5 5600 (Vermeer): "Discrete Graphics Card Required";
  - Ryzen 7 5700 (Cezanne die): "Discrete Graphics Card Required";
  - Ryzen 7 8700F and Ryzen 5 8400F (Phoenix): "Discrete Graphics Card Required".
- source AMD-7700X / AMD-9700X: desktop Zen 4/5 non-F parts *do* have an iGPU ("AMD Radeon Graphics", "Graphics Core Count 2"). See §2 for its codecs.
- source Intel processor-numbers page (https://www.intel.com/content/www/us/en/processors/processor-numbers.html, via WebFetch): suffix F means "Requires discrete graphics". The page does not define KF; it only says "Intel Core Ultra desktop processors have suffixes K, F, KF, or T."
- inferred: a no-iGPU CPU *with* a GPU that has an encoder (e.g. a Gerald-like RTX 3000+) uses that GPU's path. Software encode decides only when the dGPU has no usable encoder (e.g. RX 6400/6500, §2.3) or there is no dGPU encode path at all.

### 6.2 Software encoders available through PyAV 19.0.2

Script: `scripts/hw_accel_target/sw_encoders_pyav19.py` (functional inventory, no timing). Result: `results/hw_accel_target/sw_encoders_pyav19_win_amd64.json` (av 19.0.2, libavcodec 63.1.102).

| candidate | in PyAV 19.0.2 wheel | library version (PAF `pkg.py`) | 4:2:2 input | all-intra | notes / evidence |
|---|---|---|---|---|---|
| MJPEG passthrough (camera JPEG, G1) | n/a (no encode) | n/a | camera 4:2:2 kept | yes | measured `research/frame_ring_buffer/prototypes/results/p4_mjpeg_passthrough.md`; `results/jpeg_passthrough/NOTES.md` |
| `mjpeg` (FFmpeg native) | yes (measured) | FFmpeg built-in | yes: `yuvj422p`, `yuv422p` (measured json; code FF `mjpegenc.c:699`) | inherently intra | needs `strict=unofficial` for limited-range yuv422p (`results/uncompressed_intra/NOTES.md`, citing `mjpegenc_common.c` n9.0.2:499) |
| libjpeg-turbo (Python: simplejpeg / PyTurboJPEG / imagecodecs) | not via PyAV; separate wheels | simplejpeg 1.9.0, turbojpeg 2.6.1, imagecodecs libjpeg_turbo 3.2.0 (measured `results/uncompressed_intra/python_jpeg_libs_uv.json`) | yes: `simplejpeg.yuv_planes_422_from_yuy2` test present in that file | intra | FFmpeg's mjpeg encoder does not use libjpeg (code: native `mjpegenc.c`; PAF has no libjpeg flag) |
| `ffv1` | yes | FFmpeg built-in | yes: yuv422p and 9-16-bit 4:2:2 (measured json) | only with `gop_size=1` (measured `results/uncompressed_intra/NOTES.md` §"FFV1 with the default GOP is not intra-only") | lossless; slice threading |
| `libsvtav1` | yes | **SVT-AV1 v4.2.0** | **no**: pix_fmts `yuv420p`, `yuv420p10le` (measured json; code FF `libsvtav1.c:866`) | yes: `--pred-struct` "0: all intra" (SVT Parameters.md v4.2.0 line 261) | source SVT v4.2.0 line 65: "Color format, only yuv420 is supported at this time". Line 74 SIMD: "[c, mmx, sse, ..., avx2, avx512, avx512icl, max] for x86 platforms, [c, neon, ...] for Arm" |
| `libaom-av1` | **no** (measured json; `results/uncompressed_intra/NOTES.md` line 33) | not built (PAF: 0 matches) | - | - | CLI-only reference results exist in `results/uncompressed_intra/ffmpeg_cli_reference.json` (not the implementation under test) |
| `libvpx-vp9` | yes | **libvpx v1.17.0** | yes: `yuv422p` → VP9 profile 1 (code FF `libvpxenc.c:848-851`; measured json) | yes (keyint 1) | Chromium playback of VP9 profile 1: chromium topics, not checked here |
| `libopenh264` | **no** (measured json) | not built | - | - | the only software H.264 in the wheel is libx264 (licence: licensing topic) |
| `libx264` / `libx265` | yes | x264 commit b35605ac, x265 4.3 | yes: yuv422p / yuv422p10le (measured json) | yes | not royalty-free (G7); licensing topic |
| `prores_ks`, `jpeg2000`, `jpegls` | yes | built-in | prores_ks yuv422p10le; jpeg2000 yes; jpegls no (measured json) | intra | see `results/uncompressed_intra/` |

- measured: functional round-trips for these encoders on real YUY2 frames are already in `results/uncompressed_intra/functional_tables.md` and `functional_matrix_pyav19.0.2.json`. Not redone here.
- measured (background only, contaminated, PyAV 18): `results/uncompressed_intra/bench/*.json` and `bench_summary.md` have CPU-encode timings for `libsvtav1_intra_*`, `libvpx-vp9_intra_*`, `ffv1_*`, `mjpeg_q2` and `libx264_intra_*`. Those numbers are not quoted (stage rule; contaminated per HANDOFF §4).

### 6.3 What tonight's benches should measure (CPU software path)

All runs use PyAV 19.0.2 (`uv run --script`), one at a time, with background load recorded (HANDOFF §5). Input: the corpus YUY2 1080p sets and the C930e/C922 720p MJPEG sets (decoded to YUY2/NV12 first, decode cost recorded separately).

| id | measure | configs | why |
|---|---|---|---|
| SW1 | single-stream encode fps and CPU-seconds per frame, threads=1 and threads=auto | `mjpeg` (yuvj422p, q≈2-5), `ffv1` (g=1, slices 4/16/24, range coder), `libsvtav1` (pred-struct 0 / keyint 1, presets 8/10/12, yuv420p from YUY2), `libvpx-vp9` (keyint 1, profile 0 yuv420p and profile 1 yuv422p, `deadline=realtime`, cpu-used 8), at 720p and 1080p | decides per-camera CPU cost on no-iGPU CPUs |
| SW2 | the same including the YUY2→yuv420p / yuv422p conversion (swscale) inside the timed loop | as SW1 | svtav1 needs 4:2:0, so conversion is part of its real cost |
| SW3 | stream scaling: N concurrent encoders (N = 1, 2, 4, 6, 8) at 30 fps paced; record late frames and total CPU | `mjpeg`, `ffv1`, `libsvtav1` best preset, `libvpx-vp9` rt | gives the camera count a CPU sustains |
| SW4 | core-limited proxy: SW3 with process affinity pinned to 6 and 8 logical cores (P-cores only), as a stand-in for a Ryzen 5 3600/5600-class part | as SW3 | inferred proxy only. Flag in results that a 14700K P-core is not a Zen 2/3 core |
| SW5 | output size per frame (bytes) and PSNR/SSIM against the source for the lossy ones; bit-exact check for ffv1 | as SW1 | storage cost, needed alongside CPU cost |
| SW6 | libjpeg-turbo (simplejpeg) YUY2→JPEG 4:2:2 encode per frame vs FFmpeg `mjpeg` | 720p, 1080p | cheapest CPU path for G4 YUY2 cameras if MJPEG is the store format |

Output: `results/hw_accel_target/bench/*.json` plus `BENCH.md` (per HANDOFF §6B).

## 7. Open questions / NOT VERIFIED

- AMD Windows: whether `*_d3d12va` and `*_mf` encoders work on AMD drivers, and the real max encode resolution under AMF vs Mesa's 4096x2304. Needs AMD hardware.
- AMD: whether any FFmpeg path on Windows can HW-decode 4:2:2 MJPEG (the AMF SDK can; FFmpeg n9.0.2 has no `mjpeg_amf` and no d3d11va mjpeg hwaccel).
- Apple: HEVC Main 4:2:2 10 hardware encode per chip. VP9 hardware decode per chip. Base-M1 per-codec encode list. `ffv1_vulkan` via MoltenVK.
- Lucienne VCN version (inferred VCN 2.2).
- Jellyfin-only claims kept out of the plan: AMD "no session limit", Apple "soft limit", the Rockchip limits, and the VCN quality ranking.
