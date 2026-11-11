# GF07: Intel Windows encode coverage from verbatim primary sources (2026-11-10)

Gap-fill for hw_accel_target (and gpu_encode). Question: which Intel claims rest on WebFetch transcriptions or on the Linux media-driver tables, and can each be replaced with Intel's own text?

Method:
- Every page was downloaded raw on 2026-11-10 with curl (Chrome user agent and browser headers; intel.com no longer returns 403 with these headers) into the scratchpad `step3/GF07/dl/`. They were treated as data.
- Each quote below was checked against the raw file, not against a model transcript:
  - script `step3/GF07/tools/verify.py` (HTML: tags stripped, entities unescaped, whitespace collapsed) found 87 of 88 sentence and field quotes (lists `quotes.tsv`, `q2.tsv`–`q5.tsv`). The one miss was a probe string that is not used here: a ™ sits between the words on the page;
  - table rows were extracted with `tools/rows.py`, which joins cells with ` | `, and 33/33 row quotes matched both the parsed rows and the raw text.
- Excerpts (verbatim, with sha256 of every raw file) are in `GF07_sources/`. The manifest is `GF07_sources/GF07_manifest.json`.
- No tests and no timing were run. No camera was accessed.

Labels:
- **source**: Intel primary text, URL in §1, accessed 2026-11-10.
- **source (Win)**: the source is Windows-specific. That means one of three things:
  - the document states a Windows OS scope (S8);
  - the encode section names Windows APIs as the exposure path ("Direct3D12 Video API", "MFT (Media Foundation Transform) filters"; S4–S7). The ARL-S datasheet lists Direct3D 12 under "API Support (Windows*)" (S6). That MFT is Windows-only is **inferred** (it is not stated on the pages);
  - a per-cell "(Windows Only)" note (S2).
- **source (OS-agnostic)**: Intel text that names no OS for that cell. These documents mark OS exceptions per cell ("(Windows Only)" in S2; "3 Encode supported only on Linux" in S3), so applying an unmarked cell to Windows is **inferred**.
- **source (Linux)**: the media-driver (VA-API) or vpl-gpu-rt, background only.
- **measured**: Gerald (RPL-S UHD 770), existing result files cited in hw_accel_target FINDINGS (F1–F5, F9).
- **NOT VERIFIED**: no verbatim Intel source found.

## 1. Sources

| id | document (version / date) | URL | OS scope | excerpt |
|---|---|---|---|---|
| S1 | oneVPL "Media Capabilities Supported by Intel Hardware", ID 772607, "1.1 (latest)", "Date 3/07/2024": overview | https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/overview.html (`/current/` redirects here) | OS-agnostic | `GF07_sources/01_*.md` |
| S2 | same document: "Features and Formats" | https://www.intel.com/content/www/us/en/docs/onevpl/developer-reference-media-intel-hardware/1-1/details.html | OS-agnostic, with "(Windows Only)" cells | `02_*.md` |
| S3 | "Encode and Decode Capabilities for 7th Generation Intel® Core™ Processors and Newer", "Updated 6/8/2021" | https://www.intel.com/content/www/us/en/developer/articles/technical/encode-and-decode-capabilities-for-7th-generation-intel-core-processors-and-newer.html (support KB 000055741 links to it) | OS-agnostic, with a Linux-only footnote | `03_*.md` |
| S4 | 13th/14th Gen Core datasheet Vol 1 (Raptor Lake), ID 743844, 05/30/2025, rev 015, Public | https://edc.intel.com/content/www/us/en/design/products/platforms/details/raptor-lake-s/13th-generation-core-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/ | Win (APIs: "Intel® Media SDK", "MFT (Media Foundation Transform) filters") | `04_*.md` |
| S5 | Core Ultra (Series 1) datasheet Vol 1 (Meteor Lake U/H/U-Type4), ID 792044, 05/09/2025, rev 008, Public | https://edc.intel.com/content/www/us/en/design/products/platforms/details/meteor-lake-u-p/core-ultra-processor-datasheet-volume-1-of-2/hardware-accelerated-video-encode/ | Win (APIs) | `05_*.md` |
| S6 | Core Ultra 200S/200HX datasheet Vol 1 (Arrow Lake-S), ID 832586, 03/17/2026, rev 007, Public | https://edc.intel.com/content/www/us/en/design/products/platforms/details/arrow-lake-s/core-ultra-200s-series-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/ and `.../api-support-windows/` | Win (APIs) | `06_*.md` |
| S7 | Core Ultra 200V datasheet Vol 1 (Lunar Lake), ID 829568, 05/27/2025, rev 004. **Classification on the page: "Confidential"**, yet served to an anonymous request | https://edc.intel.com/content/www/us/en/secure/design/confidential/products/platforms/details/lunar-lake-mx/core-ultra-200v-series-processors-datasheet-volume-1-of-2/hardware-accelerated-video-encode/ | Win (APIs) | `07_*.md` (short excerpt only) |
| S8 | Intel Support KB 000098345 "Video Codecs Supported by Intel® Arc™ GPUs", "Last Reviewed: 04/07/2026" | https://www.intel.com/content/www/us/en/support/articles/000098345/graphics.html | **Win**: "Operating System Windows® 10*, Windows 11*" | `08_*.md` |
| S9 | ark "Intel® Arc™ B580 Graphics"; Intel Newsroom "Intel Launches Arc B-Series Graphics Cards" | https://www.intel.com/content/www/us/en/products/sku/241598/intel-arc-b580-graphics/specifications.html ; https://www.intel.com/content/www/us/en/newsroom/news/intel-launches-arc-b-series-graphics-cards.html | OS-agnostic | `09_*.md` |
| S10 | ark F/KF SKUs, i7-14700K; "processor numbers" suffix table | https://www.intel.com/content/www/us/en/products/sku/{199278,212321,134587,236789,241062,236783}/…/specifications.html ; https://www.intel.com/content/www/us/en/processors/processor-numbers.html | hardware | `10_*.md` |
| S11 | intel/libvpl README @ `v2.17.0`; intel/vpl-gpu-rt README @ `intel-onevpl-26.4.1` (raw markdown) | https://raw.githubusercontent.com/intel/libvpl/v2.17.0/README.md ; https://raw.githubusercontent.com/intel/vpl-gpu-rt/intel-onevpl-26.4.1/README.md | libvpl: Windows DirectX dispatch table; vpl-gpu-rt: **Linux** | `11_*.md` |
| S12 | intel/media-driver README @ `intel-media-26.3.5` (latest release on 2026-11-10; sha256 matches the 2026-11-09 copy) | https://raw.githubusercontent.com/intel/media-driver/intel-media-26.3.5/README.md | **Linux** (VA-API), background | `12_*.md` |
| S13 | Windows graphics driver 32.0.101.9175 WHQL release notes, "Date: November 04, 2026" | https://downloadmirror.intel.com/932449/ReleaseNotes_101.9175_WHQL.pdf (linked from https://www.intel.com/content/www/us/en/download/785597/intel-arc-graphics-windows.html) | Win | `13_*.md` |

Context facts from these sources:
- source (S11, Linux): vpl-gpu-rt README L72-73: "**Operating System:**" / "* Linux x86-64 fully supported". This repo has no per-platform codec table. It lists platforms (L38-43, incl. "- MTL/ARL …", "- LNL (Lunar Lake)", "- BMG (Battlemage)") and "**Supported video encoders**: HEVC, AVC, MPEG-2, JPEG, VP9, AV1" for the runtime as a whole.
- source (S11, Win): the libvpl README table "Runtime loaded by Intel® VPL Dispatcher and their Microsoft* DirectX* support" has rows "| MTL (Meteor Lake) | | :heavy_check_mark: | DX11 |", "ARL-S", "ARL-H" and "LNL (Lunar Lake)" with the same cells. BMG is not named; it falls under "| Future platforms... | | :heavy_check_mark: | DX11 |".
- source (S13, Win): the Windows driver package lists "Intel® oneVPL GPU Runtime (21.0.2.17)" and "Intel® Media SDK Runtime (21.0.1.35)". Its "Operating System Support:" table names "Intel ® Arc™ B580, B570 … (Codename … Battlemage)" and "Intel® Core™ Ultra with built-in Intel® Arc™ GPUs and Intel® Graphics (Codename Meteor Lake, Lunar Lake, Arrow Lake-S, Arrow Lake-H, Arrow Lake-U)". The release notes have **no codec table**.
- source (S12, Linux): media-driver README L1 "# Intel(R) Media Driver for VAAPI"; L6 "The Intel(R) Media Driver for VAAPI is a new VA-API (Video Acceleration API)". It is Linux background only.

## 2. Cell table (encode only)

Old labels are from FINDINGS (F:line) and NOTES_sources_nvidia_intel.md (NI:line).

| platform / cell | old label | new verbatim evidence (source) | new label | Windows-specific source? |
|---|---|---|---|---|
| **TGLx** JPEG | F:326 measured RPL-S + I3 (Linux); NI:111 "[source (transcribed)] oneVPL ENCODE-11-12 MJPEG 4:2:2 (YUY2) ✔16k" | S1 (11th / 12th-13th Gen table): "MJPEG 8-bit, 4:2:2 \| ✔ \| ✔". S2: "MJPEG Encode \| 4:2:0 (NV12) \| ✔16k", " \| 4:2:2 (YUY2) \| ✔16k". S3: "Intel® UHD Graphics 750 \| Yes \| Yes \| …" under the "JPEG \| MJPEG" columns. S4 (RPL): "JPEG \| Baseline \| — \| 16Kx16K"; "Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG." | measured (RPL-S) + source (Win, RPL) + source (OS-agnostic, TGL/RKL/ADL) | yes for RPL (S4); TGL/RKL/ADL OS-agnostic only |
| TGLx H.264 | F:326 measured + source (Linux) | S1: "AVC 8-bit, 4:2:0 \| ✔ \| ✔". S4: "AVC/H264 \| High Main \| L5.1 \| 2160p(4K)" | measured + source (Win, RPL) | yes (RPL) |
| TGLx HEVC 4:2:0 | F:326 measured + source (Linux) | S1: "HEVC 8-bit, 4:2:0 \| ✔ \| ✔". S4: "HEVC/H265 \| Main Main10 Main 4:2:2 10 Main 4:4:4 Main 4:4:4 10 \| L5.1 \| 4320p(8K) 16Kx4K @higher freq" | measured + source (Win, RPL) | yes (RPL) |
| TGLx HEVC 4:2:2 | F:326 "shader-assisted; measured Rext 4:2:2 on RPL-S"; NI:108 transcribed | S1: "HEVC 4:2:2 \| \| " (fixed-function: blank) and "HEVC (fixed-function hardware + shader-based) 8-bit, 4:2:2 \| ✔ \| ✔". S2: " \| 8-bit, 4:2:2 (YUY2) \| ✔4k". S4 profile list contains "Main 4:2:2 10" | measured + source (Win, RPL) | yes (RPL) |
| **MTL** JPEG | F:327 "Windows read from Linux tables, I6" | S5: "JPEG \| \| \| 16Kx16K"; "Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG/AV1."; "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]" | source (Win); not tested | **yes** |
| MTL H.264 | F:327 Y (Linux tables) | S5: "AVC/H264 \| High Main Constrained Baseline \| L5.2 \| 4K@60". S8, column "Intel® Core™ Ultra Series 1 with Intel® Arc™ GPU": "AVC / H.264 \| 8-bit 4:2:0 …" | source (Win) | **yes** |
| MTL HEVC 4:2:0 | F:327 Y (Linux tables) | S5: "Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b \| L6.1 \| 4320p(8K) @60 16Kx12K". S8 Series 1: "8-bit 4:2:0 … 10-bit 4:2:0 …" | source (Win) | **yes** |
| MTL HEVC 4:2:2 | F:327 "4:2:2 enc N" (I4, Linux README MTLx "D") | S5: "HEVC/H265 \| Main10 422 - 8b/10b \| L5.2 \| 4K@60". S8 Series 1 HEVC encode: "8-bit 4:2:2 … 10-bit 4:2:2". S12 L118 MTLx: "\<u\>D\</u\>\<br\>\<i\>D\<i\>" | **source (Win): Y; source (Linux): N**. Vendor vs vendor / OS split (J5). Not tested | yes |
| **ARL-S/HX** JPEG | F:327 "Windows read from Linux tables, I6" | S6 (title "Intel® Core™ Ultra 200S, Intel® Core™ Ultra 200S Plus ,Intel® Core™ Ultra 200HX and 200HX Plus Series Processors"): "JPEG \| \| \| 16Kx16K"; "Xe supports full HW accelerated video encoding for AVC/HEVC/VP9/JPEG/AV1."; MFT line as S5 | source (Win); not tested | **yes** |
| ARL-S/HX H.264 / HEVC 4:2:0 | F:327 Y (Linux) | S6: "AVC/H264 \| High Main Constrained Baseline \| L5.2 \| 4K@60"; HEVC row as S5 | source (Win) | **yes** |
| ARL-S/HX HEVC 4:2:2 | F:327 N (Linux) | S6: "HEVC/H265 \| Main10 422 - 8b/10b \| L5.2 \| 4K@60" | source (Win): Y; source (Linux): N (J5) | yes |
| ARL-H / ARL-U, all codecs | F:327 (row "MTL / ARL") | No ARL-H/U datasheet was fetched. S8's "Core Ultra Series 2 with Intel® Arc™ GPU" column does not say which Series 2 parts it covers. S11/S13 only show that a Windows VPL runtime and driver exist for "ARL-H" / "Arrow Lake-H, Arrow Lake-U" | **NOT VERIFIED** (Windows codec list) | no |
| **LNL** JPEG | F:328 "Windows inferred, I6" | S7: "JPEG \| \| \| 16Kx16K"; "Xe2 supports full HW accelerated video encoding for AVC/HEVC/JPEG/AV1."; MFT line as S5 | source (Win), **but S7 is labelled "Confidential"**. If Dom does not allow citing it: NOT VERIFIED on Windows (Linux S12 L115 "D/E") | yes (S7 only) |
| LNL H.264 / HEVC 4:2:0 | F:328 Y (Linux) | S7: "AVC/H264 \| High Main Constrained Baseline \| L5.2 \| 4K @ 60"; "HEVC/H265 \| Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b \| L6.1 \| 4320p(8K) @60 16Kx12K". S8 Series 2 column (mapping to LNL not stated) | source (Win, S7); S8 supporting only | yes (S7) |
| LNL HEVC 4:2:2 | F:328 Y (I4: LNL "E", Linux) | S7 HEVC row has no 4:2:2 profile. S12 L118 LNL "D/E". S8 Series 2 lists "8-bit 4:2:2" (parts not stated) | **NOT VERIFIED** (vendor vs vendor, J5) | conflicting |
| **Arc A** JPEG | F:329 "Y / Y" (Linux); NI:111 transcribed | S1 (Iris Xe MAX \| Arc A): "MJPEG 8-bit, 4:2:2 \| ✔ \| ✔". S2: " \| 4:2:2 (YUY2) \| ✔ 16K \| ✔16k" | source (OS-agnostic); Windows inferred. S8 (Win) lists no JPEG for any column, so it is silent | no |
| Arc A H.264 / HEVC 4:2:0 | F:329 Y; NI:106 transcribed | S1: "AVC 8-bit, 4:2:0 \| ✔ \| ✔"; "HEVC 8-bit, 4:2:0 \| ✔ \| ✔". S8 Arc A-Series: "8-bit 4:2:0" (AVC), "8-bit 4:2:0 …" (HEVC) | source (Win) | **yes** (S8) |
| Arc A HEVC 4:2:2 | F:329 "vendor vs vendor, J5"; F:164 J5 transcribed | S1: "HEVC 8-bit, 4:2:2 \| \| ✔". S2: " \| 8-bit, 4:2:2 (YUY2) \| \| ✔16k (Windows Only)". S8 Arc A-Series HEVC encode: "8-bit 4:2:2 … 10-bit 4:2:2". S12 L118 DG2: "\<u\>D/E\</u\>\<br\>\<i\>D/E\<i\>" | source (Win): Y. Linux vendor vs vendor kept (J5) | **yes** |
| **Arc B** JPEG | F:330 "Windows inferred, I6" | **No Intel Windows text found.** S8 has no JPEG row (0 case-insensitive matches for "jpeg"). S9 ark B580 has no JPEG field (0 "jpeg"/"vp9" matches). Linux only: S12 L115 BMG "\<u\>D/E\</u\>" | **NOT VERIFIED (Windows)**; source (Linux) | no |
| Arc B H.264 | F:330 Y (Linux) | S8 B-Series: "8-bit 4:2:0". S9: "H.264 Hardware Encode/Decode Yes" | source (Win) | **yes** (S8) |
| Arc B HEVC 4:2:0 / 4:2:2 | F:330 Y (Linux) | S8 B-Series HEVC encode: "8-bit 4:2:0 8-bit 4:2:2 8-bit 4:4:4 10-bit 4:2:0 10-bit 4:2:2 10-bit 4:4:4 Screen Content Coding". S9: "H.265 (HEVC) Hardware Encode/Decode Yes"; newsroom: "…hardware encode and decode codec support, such as AV1, H.265 including 4:2:2 10-bit, H.264 and VP9." | source (Win) | **yes** (S8) |
| **F/KF** no iGPU | F:95-98 I5 [source (transcribed)] | S1: "NOTE: Intel® Core™ Processors without processor graphics do not have media support." S10 suffix table: "\| F \| Requires discrete graphics". S10 ark 265KF: "Intel® Quick Sync Video \| No", "Xe-cores \| 0", "Graphics Output \| n/a". 10400F (Q2'20), 11900KF (Q1'21), 12400F (Q1'22) and 14700KF (Q4'23) pages have 0 "GPU Specifications" and 0 "Quick Sync" matches; the 14700K page has "Intel® Quick Sync Video \| Yes" | source + measured (absence on the downloaded pages) | n/a (hardware) |

Cells with a Windows-specific Intel source:
- H.264 and HEVC 4:2:0 on RPL, MTL, ARL-S/HX, LNL (S7, Confidential label), Arc A and Arc B.
- HEVC 4:2:2 on RPL (shader-assisted), MTL, ARL-S/HX, Arc A and Arc B.
- JPEG on RPL, MTL, ARL-S/HX and LNL (S7 only).

No Windows-specific source:
- JPEG on TGL/RKL/ADL and Arc A: OS-agnostic Intel doc only.
- Arc B JPEG: NOT VERIFIED on Windows.
- ARL-H/U: NOT VERIFIED.
- LNL HEVC 4:2:2: NOT VERIFIED.

## 3. Labelled findings

- source (Win, S5/S6): on Meteor Lake and Arrow Lake-S/HX the encode section says "The HW encode is exposed by the graphics driver using the following APIs:" "Direct3D12 Video API", "Intel®one VPL", "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]".
- inferred: FFmpeg's `mjpeg_qsv` goes through oneVPL (`qsvenc_jpeg.c`, already cited in FINDINGS), so the documented hardware path exists on MTL and ARL-S. **NOT TESTED** there.
- source (Win, S4): the Raptor Lake datasheet lists "Intel® Media SDK" and "MFT (Media Foundation Transform) filters" as the exposure APIs, and "JPEG | Baseline | — | 16Kx16K". This matches the measured `mjpeg_qsv` on Gerald.
- source (Win) vs source (Linux), **DISAGREE**:
  - MTL/ARL-S HEVC 4:2:2 encode: datasheets say "Main10 422 - 8b/10b … 4K@60", and S8 lists "8-bit 4:2:2" for Core Ultra Series 1;
  - media-driver README L118 gives MTLx "D" only.
  - So the FINDINGS cell "4:2:2 enc N" is a Linux statement.
- source, **DISAGREE** (LNL HEVC 4:2:2):
  - S7's HEVC row lists only "Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b";
  - the media-driver gives LNL "D/E".
  - NOT VERIFIED.
- source (Win, S8), ambiguity: S8's "Core Ultra Series 2 with Intel® Arc™ GPU" column lists VP9 encode ("8-bit 4:2:0 8-bit 4:4:4 10-bit 4:2:0 10-bit 4:4:4"), while S7 says "Xe2 implements a low-power low-latency fixed function encoder which supports AVC, HEVC, and AV1" (no VP9) and S12 gives LNL VP9 "D".
  - inferred: the Series 2 column does not describe LNL alone. Do not use S8 alone for LNL cells.
- source (Win, S8): Arc B-Series VP9 encode is "Not Supported", which agrees with FINDINGS §3.1 (BMG VP9 **N**).
- source (Win, S5/S6, S8): AV1 encode on MTL/ARL-S ("AV1 | Main (4:2:0 8b, 10b) | L6 | 8K@30") and on Arc A, Series 1 and Arc B ("8-bit 4:2:0 10-bit 4:2:0"). This agrees with I2.
- source (OS-agnostic, S1/S4): no TGLx AV1 encode. S1's 11th/12th–13th table row is "AV1 | | ", and S4 has no AV1 row. This agrees with I1.
- source (S3), new for J6: "For all processor graphics listed here, there is no limitation on the number of concurrent sessions to transcode."
  - S3 lists only Iris Xe MAX and 7th–11th Gen.
  - So Jellyfin's "no concurrent encoding sessions limit" now has an Intel source for TGL/RKL (11th Gen) and older. It stays Jellyfin-only for ADL/RPL, MTL and later, and Arc.
- source (S10), new: the i7-14700K ark field is "Multi-Format Codec Engines | 2", so NI:135 (Jellyfin L89 "second MFX video engine") no longer depends on a transcription.
- Errors found in the 2026-11-09 WebFetch transcription (`sources_nv_intel/intel_com_webfetch_transcripts.md`):
  1. The encode summary showed only "MJPEG 8-bit, 4:2:0". The raw S1 tables also have "MJPEG 8-bit, 4:2:2 | ✔ | ✔" and "MJPEG 8-bit, 4:4:4 | ✔ | ✔" for Xe MAX/Arc A and for 11th, 12th/13th Gen.
  2. The summary dropped the "(fixed-function hardware + shader-based)" rows, including HEVC 8/10/12-bit 4:2:2 ✔ for 11th–13th Gen.
  3. The transcript merged per-family tables into one. In raw S1 each family has its own table.
  4. The i7-14700KF code name, given there as "(not asked)", is "Products formerly Raptor Lake".
  - The other transcribed values checked here (Arc A HEVC 4:2:2 "✔16k (Windows Only)", MJPEG YUY2 ✔16k, 265KF "Quick Sync Video: No") match the raw pages.
- **Caution (S7):** the Lunar Lake datasheet page shows the classification "Confidential". It was served to an anonymous request (no sign-in) on 2026-11-10. Only a short excerpt is stored in the repo; the raw page stays in the scratchpad. **Dom should decide whether PLAN.md may cite S7.** Without S7, LNL Windows JPEG/H.264/HEVC falls back to NOT VERIFIED (H.264/HEVC: S8 Series 2, mapping not stated).
- NOT VERIFIED (market): share of 2020+ Intel SKUs or shipments that are F/KF. No source.

## 4. Proposed replacement text for hw_accel_target FINDINGS

Line numbers are in the current `results/hw_accel_target/FINDINGS.md`.

### 4.1 Header, line 12
Old (L12): `- **[source (transcribed)]**: intel.com returned 403, so the page was read through WebFetch's small model (NI header). Weaker than [source].`

Proposed: delete the line. After GF07, no FINDINGS claim uses the label. Add instead:
`- **[source (Win)]**: a primary source that is Windows-specific (Windows OS scope, Windows exposure APIs, or a "(Windows Only)" cell). Intel Windows sources: R/hw_accel_target/gapfill/GF07_intel_windows_sources.md (GF07).`

### 4.2 I5 (L95-98)
Old:
```
- **I5 [source (transcribed)]** Intel desktop F/KF SKUs have no iGPU, so they have no Quick Sync.
  - ark examples span 2020–2024: i5-10400F, i9-11900KF, i5-12400F, i7-14700KF, Core Ultra 7 265KF.
  - Only the 265KF page says "Intel® Quick Sync Video": "No". The other pages have no GPU section (NI §5).
  - **NOT VERIFIED:** what share of 2020+ SKUs or shipments they are.
```
Proposed:
```
- **I5 [source + measured]** Intel desktop F/KF SKUs have no processor graphics, so they have no Quick Sync media engine (GF07 §2).
  - source: Intel oneVPL media-capabilities doc (ID 772607 v1.1): "Intel® Core™ Processors without processor graphics do not have media support."
  - source: Intel processor-numbers page, desktop suffix table: "F | Requires discrete graphics".
  - source: ark Core Ultra 7 265KF (Q4'24, Arrow Lake): "Intel® Quick Sync Video | No", "Xe-cores | 0", "Graphics Output | n/a".
  - measured (downloaded ark pages, 2026-11-10): i5-10400F (Q2'20), i9-11900KF (Q1'21), i5-12400F (Q1'22) and i7-14700KF (Q4'23) have no "GPU Specifications" section and 0 "Quick Sync" matches; i7-14700K has "Intel® Quick Sync Video | Yes".
  - **NOT VERIFIED:** what share of 2020+ SKUs or shipments they are.
```

### 4.3 I6 (L99)
Old: `- **I6 [source (transcribed)]** The media-driver tables are for Linux VA-API. The Windows oneVPL capability doc covers only 11th–13th Gen and Arc A. Windows support for MTL/ARL/LNL/BMG is therefore read from the Linux tables (NI §4).`

Proposed:
```
- **I6 [source (Win)]** Intel Windows encode sources per generation (GF07 §2). The media-driver tables are Linux VA-API background.
  - RPL, MTL, ARL-S/HX: the datasheet encode sections name the Windows exposure APIs ("Direct3D12 Video API", "Intel®one VPL", "MFT (Media Foundation Transform) filters [Only for AVC/HEVC/JPEG/AV1 Encoder]"; RPL: "Intel® Media SDK", "MFT …") and list "JPEG" (RPL "Baseline", MTL/ARL "16Kx16K"), AVC and HEVC encode.
  - Arc A, Core Ultra Series 1, Arc B: Intel KB 000098345 ("Operating System Windows® 10*, Windows 11*") lists H.264 "8-bit 4:2:0" and HEVC incl. "8-bit 4:2:2" encode. It has no JPEG row.
  - Arc A JPEG: oneVPL doc "MJPEG 8-bit, 4:2:2 | ✔ | ✔" (OS-agnostic; Windows inferred).
  - LNL: only a datasheet whose page is labelled "Confidential" ("Xe2 supports full HW accelerated video encoding for AVC/HEVC/JPEG/AV1."); citing it is Dom's call.
  - **NOT VERIFIED on Windows:** Arc B JPEG encode; ARL-H/ARL-U codec list; LNL HEVC 4:2:2. No `*_qsv` encode was tested outside RPL-S.
```

### 4.4 J5 (L164)
Old: `- **J5 [source (transcribed)] Vendor vs vendor (Intel).** oneVPL marks Arc A HEVC 4:2:2 encode "✔16k (Windows Only)". Media-driver README L118 gives DG2 "D/E" on Linux (NI §4.3).`

Proposed:
```
- **J5 [source] Vendor vs vendor (Intel), HEVC 4:2:2 encode, Windows vs Linux (GF07 §3).**
  - Arc A: oneVPL details "8-bit, 4:2:2 (YUY2) |  | ✔16k (Windows Only)", and KB 000098345 (Windows) lists "8-bit 4:2:2". Media-driver README L118 gives DG2 "D/E" on Linux. Windows Y; the Linux statement disagrees with "Windows Only".
  - MTL and ARL-S/HX: datasheets "HEVC/H265 | Main10 422 - 8b/10b | L5.2 | 4K@60", and the KB lists "8-bit 4:2:2" for Core Ultra Series 1. Media-driver L118 gives MTLx "D" (no encode). Windows Y, Linux N.
  - LNL: the datasheet HEVC row lists only "Main Main10 420, 444 - 8b/10b SCC 420 444 - 8b/10b"; media-driver L118 gives LNL "D/E". NOT VERIFIED.
  - None tested. This matters only for keeping 4:2:2 in HEVC.
```

### 4.5 §3.1 Intel rows (L326-331)
Old (L326-331):
```
| Intel TGL / RKL / ADL / RPL iGPU | Y / Y | Y / Y (4:2:2 enc shader-assisted; **measured Rext 4:2:2 on RPL-S**) | **N** / Y (measured on RPL-S; other TGLx source) | **Y (measured on RPL-S)** / Y | **Y fixed-function (measured on RPL-S, 4:2:2 from yuyv422; needs full-range input, K5)** / Y (measured, output nv12) | NV (Vulkan 1.4 device, not run) | AGREE; scope DISAGREE on "QSV only on Windows" (J10) | I1, I3, I4, F1-F5, F9 |
| Intel MTL / ARL | Y / Y | Y / Y (4:2:2 enc N) | Y / Y | Y / Y | Y / Y (Windows read from Linux tables, I6) | NV | AGREE | I2, I4, I6 |
| Intel LNL | Y / Y | Y / Y | Y / Y | **N** / Y | Y / Y (Windows inferred, I6) | NV | AGREE | I2, I6 |
| Intel Arc A (DG2) | Y / Y | Y / Y (4:2:2: vendor vs vendor, J5) | Y / Y | Y / Y | Y / Y | NV | AGREE | I2, J5 |
| Intel Arc B (BMG) | Y / Y | Y / Y | Y / Y | **N** / Y | Y / Y (Windows inferred, I6) | NV | AGREE | I2, I6 |
| Intel F/KF desktop (no iGPU) | none | none | none | none | none | none | AGREE ("ending with F") | I5 |
```
Proposed:
```
| Intel TGL / RKL / ADL / RPL iGPU | Y (measured RPL-S; Win source RPL) / Y | Y / Y (4:2:2 enc fixed-function + shader only, ≤4k; Win source RPL "Main 4:2:2 10"; **measured Rext 4:2:2 on RPL-S**) | **N** / Y (measured on RPL-S; other TGLx source) | **Y (measured on RPL-S)** / Y | **Y fixed-function (measured on RPL-S, 4:2:2 from yuyv422; needs full-range input, K5); Win source RPL "JPEG \| Baseline"; TGL/RKL/ADL OS-agnostic source** / Y (measured, output nv12) | NV (Vulkan 1.4 device, not run) | AGREE; scope DISAGREE on "QSV only on Windows" (J10) | I1, I3, I4, I6, F1-F5, F9 |
| Intel MTL / ARL-S/HX | Y / Y (Win source) | Y / Y (Win source); 4:2:2 enc: Win Y, Linux N (J5) | Y / Y | Y / Y | **Y (Win source, datasheets; not tested)** / Y | NV | AGREE | I2, I4, I6, J5 |
| Intel ARL-H / ARL-U | NV (Windows codec list not sourced) | NV | NV | NV | NV | NV | n/a | I6 |
| Intel LNL | Y / Y (datasheet labelled "Confidential", I6) | Y / Y; 4:2:2 enc NV (J5) | Y / Y | **N** / Y | Y on Windows only per the "Confidential" datasheet; else Windows NV (Linux source) / Y | NV | AGREE | I2, I6, J5 |
| Intel Arc A (DG2) | Y / Y (Win source, KB) | Y / Y (Win source); 4:2:2 enc Win Y ("Windows Only"), Linux vendor vs vendor (J5) | Y / Y | Y / Y | Y (oneVPL doc, OS-agnostic; Windows inferred) / Y | NV | AGREE | I2, I6, J5 |
| Intel Arc B (BMG) | Y / Y (Win source, KB + ark B580) | Y / Y incl. 4:2:2 enc (Win source, KB) | Y / Y | **N** / Y (KB "Not Supported") | **Windows NV** (no Intel Windows source; Linux media-driver "D/E") / Y | NV | AGREE | I2, I6 |
| Intel F/KF desktop (no iGPU) | none | none | none | none | none | none | AGREE ("ending with F") | I5 |
```
Also add a legend line under §3.1: "Win source = Windows-specific Intel source (GF07); decode cells unchanged."

### 4.6 §3.3 JPEG row (L370) and §4 (L421)
- L370, Intel cell. Old: `Y (`mjpeg_qsv`, in the wheel; measured on RPL-S; MTL+ on Windows inferred, I6; needs full-range input, K5)`. Proposed: `Y (`mjpeg_qsv`, in the wheel; measured on RPL-S; Windows source for MTL and ARL-S/HX, not tested; LNL only per a "Confidential" datasheet; Arc B Windows NV; needs full-range input, K5)`.
- L370, last cell. Old: `**partly**: Ampere and Intel TGL–RPL measured or source; RTX 40/50 and Windows MTL+ inferred; AMD and Apple software only`. Proposed: `**partly**: Ampere and Intel TGL–RPL measured or source; Intel MTL/ARL-S Windows source (not tested); RTX 40/50 inferred; Arc B Windows NV; AMD and Apple software only`.
- L421. Old: `- Intel support is fixed-function `mjpeg_qsv` (F2). It is measured on RPL-S; Windows MTL+ is inferred from the Linux tables (I6).` Proposed: `- Intel support is fixed-function `mjpeg_qsv` (F2). It is measured on RPL-S. Intel datasheets list JPEG hardware encode exposed through oneVPL/MFT on MTL and ARL-S/HX (Windows source, not tested through FFmpeg). LNL rests on a datasheet labelled "Confidential", and Arc B on Windows is NOT VERIFIED (I6).`

### 4.7 §6 (L498, L505-507)
- L498. Old: `- Hardware physically tested: only NVIDIA Ampere (RTX 3070) and Intel Xe-LP (RPL-S UHD 770). Every Turing, Ada, Blackwell, other TGLx, MTL/ARL/LNL, Arc, AMD and Apple cell is from primary sources only.` Proposed: append ` Intel Windows-specific sources per cell: GF07.`
- L505-507. Old:
```
- Intel NOT VERIFIED:
  - Windows codec support for MTL/ARL/LNL/BMG. It is read from the Linux media-driver tables (I6).
  - Intel/Linux QSV through the PyPI wheel; likely unusable per code (§3.2).
```
Proposed:
```
- Intel NOT VERIFIED:
  - Windows JPEG encode on Arc B (BMG); the Windows codec list for ARL-H/ARL-U. No Intel Windows source found (I6).
  - LNL on Windows, if the "Confidential"-labelled datasheet is not cited (I6).
  - HEVC 4:2:2 encode on LNL; Linux HEVC 4:2:2 on MTL/ARL/Arc A (J5).
  - Any `*_qsv` encode through FFmpeg/PyAV on MTL, ARL, LNL, Arc A or Arc B: sources only, no hardware tested (I6).
  - Intel/Linux QSV through the PyPI wheel; likely unusable per code (§3.2).
```
(L508, Windows-on-ARM64, unchanged.)

### 4.8 J6 (L165-168) and §4 L450, optional
- Add under J6: `- source (Intel, "Encode and Decode Capabilities for 7th Generation … and Newer", Updated 6/8/2021): "For all processor graphics listed here, there is no limitation on the number of concurrent sessions to transcode." It covers Iris Xe MAX and 7th–11th Gen only. So the Intel "no limit" claim has an Intel source for TGL/RKL and older, and stays Jellyfin-only for ADL and later and Arc (GF07 §3).`
- L450. Old: `- The Intel "no limit" claim is Jellyfin-only (J6).` Proposed: `- The Intel "no limit" claim has an Intel source only up to 11th Gen (TGL/RKL); for ADL+ and Arc it is Jellyfin-only (J6).`

### 4.9 §8 note
Add to §8.2: `- GF07 (2026-11-10): I5, I6, J5 and the §3.1 Intel rows re-sourced from raw intel.com / edc.intel.com / GitHub downloads (quotes checked against the raw files); the [source (transcribed)] label is retired; transcription errors listed in GF07 §3.`

## 5. Files

- `results/hw_accel_target/gapfill/GF07_intel_windows_sources.md` (this file)
- `results/hw_accel_target/gapfill/GF07_NOTES.md`
- `results/hw_accel_target/gapfill/GF07_sources/01-13_*.md`: verbatim excerpts, with sha256 values
- `results/hw_accel_target/gapfill/GF07_sources/GF07_manifest.json`: sha256 of every raw download
- `results/gpu_encode/gapfill/GF07_NOTES.md`: pointer for gpu_encode §2.12 / §3.4
- Correction note appended to `results/hw_accel_target/NOTES_sources_nvidia_intel.md`
- Scratchpad (not in repo): `step3/GF07/dl/` (raw downloads), `step3/GF07/tools/` (`fetch.sh`, `html2txt.py`, `rows.py`, `verify.py`, `excerpts.py`, quote lists `quotes.tsv`, `rowquotes.tsv`, `q2-q4.tsv`)
