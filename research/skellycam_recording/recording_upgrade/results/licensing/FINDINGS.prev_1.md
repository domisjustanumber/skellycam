# Licensing findings (G7): royalty-free codecs, containers and libraries

Study: skellycam recording upgrade, topic `licensing`. Machine Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Date 2026-11-09.
Merged from `NOTES.md` and the raw result files in this folder. All raw files were re-read for this merge. There is no `BENCH.md` or `bench/`: this topic did no timing work.
This is not legal advice. It reports what licence texts and licensors say, plus functional tests on this machine.

Labels: **[measured]** = result file in this folder; **[source]** = primary source, verbatim quote, accessed 2026-11-09; **[code]** = source file:line at a pinned tag; **[inferred]** = reasoning, kept short; **NOT VERIFIED** = no primary source found.

Quote ids (Qnn) are entries in `quote_verification.json`. 59 of 59 quotes have `found_verbatim: true` against the downloaded page text. URL, HTTP status, sha256 and fetch time per page are in `source_fetch_log.json`. Quotes S1-S3 were checked during this merge (`quote_verification_supplement.txt`).

## 1. Questions answered

1. Which candidate codecs and containers have a primary-source royalty-free statement, which are royalty-bearing, and which are unknown?
2. What do the Python libraries skellycam would use (PyAV 18.0.0 pinned / 19.0.2 newest; OpenCV 4.12.0 pinned / 5.0.0.93 newest) actually ship, licence-wise? Which encoders work on this machine?
3. Which of these formats play natively in Electron 35.7.5 (pinned), Electron 45.2.3 (newest) and Chrome 156?
4. Does the G1 JPEG passthrough store only the patent-free JPEG process?

## 2. Findings

### 2.1 Video codecs: licensor statements

- [source] AV1: AOM Patent License 1.0 grants a "no-charge, royalty-free, irrevocable (except as expressly stated in this License) patent license to its Necessary Claims to make, use, sell, offer for sale, import or distribute any Implementation." (Q01, https://aomedia.org/license/patent-license/)
- [source] AV1: the licence is "immediately terminated" for a licensee that starts patent action (Q03). A licensee "must reproduce this License with any Implementation" (Q02).
- [source] AV1: Sisvel "offers royalty-bearing ... licences ... to patents related to the AV1 specification" (Q04), covering "any consumer product making use of the AV1 specification" (Q05). Listed rates: "Consumer Display Device* EUR 0.32 EUR 0.24 Consumer Non-Display Device** EUR 0.11 EUR 0.08" (S1, Sisvel AV1 page).
- [source] AV1 and VP9 are also in streaming-provider pools: Avanci Video (Q10) and the Access Advance VDP pool, "which covers four codecs including HEVC, VVC, VP9, and AV1" (Q11).
- [source] AOM press release (May 23, 2023): "European Commission has today closed its preliminary review of AOMedia's royalty-free licensing policy without further action" (S3). The Commission's own notice: NOT VERIFIED.
- [source] VP9: Google grants a "no-charge, royalty-free, irrevocable (except as stated in this section) patent license ... of these implementations of WebM" (Q12). It "does not include claims that would be infringed only as a consequence of further modification of these implementations" (Q13).
- [source] VP9: Sisvel offers "royalty-bearing" VP9 licences (Q07). Rates: "Consumer Display Device* EUR 0.24 EUR 0.18 Consumer Non-Display Device** EUR 0.08 EUR 0.06" (Q08).
- [source] VP8: "The VP8 Cross-License Agreement helps create a royalty-free ecosystem for VP8" (Q14). Sisvel's VP9 page refers to "the Google-MPEG LA agreement ... Covering VP8 Video Format" (S2). That agreement was not fetched: NOT VERIFIED.
- [source] FFV1 (RFC 9043): CABAC was replaced by a range coder "due to the uncertain patent/royalty situation" (Q16).
- [measured] FFV1: IETF Datatracker lists 0 IPR disclosures for rfc9043, draft-ietf-cellar-ffv1 and draft-ietf-cellar-ffv1-v4 (`ietf_ipr_disclosures.json`, queried 2026-11-09T16:09:37Z). No positive royalty-free declaration was found.
- [source] JPEG baseline: T.81 Annex L lists patents for processes "which uses arithmetic coding" (Q17). "No other patents required for implementation of any of the other processes ... had been identified at the time of publication of this Specification." (Q18, W3C copy of T.81)
- [source] JPEG baseline: ITU Journal 2020 says "de facto the baseline mode of JPEG remained RF" (Q19) and "Author's note - All JPEG-1 patents have now expired." (Q20; an author's note, not a standards-body statement).
- [source] JPEG baseline: Joan Mitchell (T.81 co-editor), on her page at w3.org: "So far no one has pressed any claims on the JPEG baseline (sequential Huffman) system that I know of." (Q56; undated personal statement, weak evidence.)
- NOT VERIFIED: ISO and ITU-T patent declaration databases for JPEG (HTTP 403 / search form only). jpeg.org/jpeg has no royalty statement (searched, 0 hits).
- NOT VERIFIED: "Motion JPEG" as a whole. There is no single MJPEG spec; each container defines its own carriage.
- [source] JPEG XL: Part 4 "Provides a free and open source, royalty-free JPEG XL reference implementation" (Q21, jpeg.org). libjxl v0.11.1 PATENTS: Google's "no-charge, royalty-free" grant for "this implementation of JPEG XL" (Q22). ISO/IEC 18181 declarations: NOT VERIFIED.
- [source] JPEG 2000: "has a royalty-free objective" (Q23); Part 15 (HTJ2K) "is intended to be royalty-free" (Q24). An objective is not a licence. Declarations: NOT VERIFIED.
- [source] UT Video original codec: "licensed under ... GNU GPL version 2 ... or later" (Q25). Patent status: NOT VERIFIED.
- [source] MagicYUV is a commercial product: "We offer MagicYUV at a low price" (Q26). Format/patent licence: NOT VERIFIED.
- HuffYUV / FFVHuff: the original licence page is dead. Licence and patent status NOT VERIFIED.
- [source] ProRes: "Apple also licenses and certifies ProRes and ProRes RAW for specific third-party products and workflows." (Q27). "Using any unauthorized implementation (such as the FFmpeg and derivative implementations) might lead to decoding errors, performance degradation, incompatibility, and instability." (Q28). Royalty terms: NOT VERIFIED.
- DNxHD / DNxHR (SMPTE VC-3): NOT VERIFIED (avid.com and smpte.org pages returned HTTP 404, `source_fetch_log.json`).
- [source] H.264: Via LA AVC fees: "For the first 1 to 100,000 units $0.00* For units 100,001 to 5,000,000 $ 0.20 ea. For units 5,000,001 and more $ 0.10 ea." (Q29). "The actual License agreement provides the only definitive and reliable statement of license terms." (Q30)
- [source] H.264 via Cisco OpenH264: Cisco covers the fees only if "the team can use the binary module distributed by Cisco" (Q35), and only when "The Cisco-provided binary is separately downloaded to an end user's device, and not integrated into or combined with third party software" (Q36). Covered use: "PERSONAL USE OF A CONSUMER OR OTHER USES IN WHICH IT DOES NOT RECEIVE REMUNERATION" (Q37). "Cisco is providing no such guarantee" for other patent holders (Q38).
- [source] HEVC: Via LA HEVC/VVC fees: "For the first 1 to 100,000 units $0.00* For units 100,001 and more $ 0.30 ea. for sales in R1** $0.20 ea. for sales in R2**" (Q31). "as of December 15, 2025, Access Advance has acquired this HEVC/VVC program" (Q32).
- [source] HEVC: Access Advance licenses "HEVC Decoders and HEVC Encoders in Consumer HEVC Products, whether made available in devices, software, or through Cloud Based Services" (Q33) and seeks "one royalty per device/software copy on First Sale" (Q34). A below-threshold or free-software term on the Access Advance pages: NOT VERIFIED.
- [source] FFmpeg legal page: "Q: Does FFmpeg use patented algorithms? A: We do not know, we are not lawyers" (Q46).

### 2.2 Containers

- [measured] Matroska (RFC 9559): 0 IETF IPR disclosures for rfc9559 and draft-ietf-cellar-matroska (`ietf_ipr_disclosures.json`).
- [source] WebM: "Google, Matroska and the Xiph.Org Foundation make the various components of WebM openly available on royalty- free terms." (Q59)
- [source] ISO BMFF: ISO's former Publicly Available Standards "are now available at no charge on the ISO and IEC webstores" (Q55). Whether 14496-12 is among them, and its patent declarations: NOT VERIFIED (iso.org HTTP 403).
- AVI (RIFF): Microsoft's reference page has no licence or royalty statement. Royalty status NOT VERIFIED.
- NUT: NOT VERIFIED (ffmpeg.org/~michael/nut.txt returned a stub).

### 2.3 Audio (if audio is recorded)

- [source] Opus: "protective, royalty-free licenses for the required patents" (Q53).
- [measured] Opus: 5 IETF disclosures on RFC 6716 (2 of them in state "rejected") and 11 on draft-ietf-codec-opus. France Telecom and Ericsson (RFC 6716) and Qualcomm and Huawei (draft) declared "c) Reasonable and Non-Discriminatory License to All Implementers with Possible Royalty/Fee" (`ietf_ipr_disclosures.json`).
- [source] FLAC: "is non-proprietary, is unencumbered by patents" (Q54). [measured] 0 IETF disclosures for rfc9639 / draft-ietf-cellar-flac.
- [source] AAC: Via LA "For the first 1 to 500,000 units $0.98 For units 500,001 to 1,000,000 $0.78" (Q57).
- PCM / WAV: NOT VERIFIED.

### 2.4 Platform encoders and SDKs

- [source] NVIDIA Video Codec SDK 13.0 licence: "NVIDIA does not grant to you under this license any necessary patent or other rights with respect to any audio and/or video encoders and decoders." (Q49). The CUDA EULA has the same sentence (Q48).
- [source] nvjpeg.dll is a CUDA redistributable component (Q50).
- [source] nvImageCodec: binary redistribution is allowed only "as incorporated into a software application" with "material additional functionality" (Q51). "You may not use the Software in any manner that would cause it to become subject to an open source software license" (Q52).
- Windows Media Foundation H.264 encoder: Microsoft's page has no royalty statement. Who bears codec royalties: NOT VERIFIED.
- [measured] This machine has Microsoft.HEVCVideoExtension 2.5.48.0, AV1VideoExtension 2.0.35.0 and VP9VideoExtensions 1.2.20.0 installed, plus the MPEG2, HEIF, WebP and Raw image extensions (`appx_codec_extensions.txt`, read-only `Get-AppxPackage`). Media Foundation and Chromium HEVC results may differ on a clean Windows install.
- Apple VideoToolbox licence: NOT VERIFIED (the page is JavaScript-rendered).
- [source] Electron builds Chromium with `ffmpeg_branding = "Chrome"` and `proprietary_codecs = true`: all.gn lines 17-18 at v35.7.5, lines 40-41 at v45.2.3 (`electron_gn_args_excerpt.txt`).
- [source] Electron release.gn lines 5-8 (both tags): "By default, Electron builds ffmpeg with proprietary codecs enabled. In order to facilitate users who don't want to ship proprietary codecs in ffmpeg, or who have an LGPL requirement to ship ffmpeg as a dynamically linked library, we build ffmpeg as a shared library." The releases ship `ffmpeg-v35.7.5-win32-x64.zip` and `ffmpeg-v45.2.3-win32-x64.zip` (`electron_gn_args_excerpt.txt`).
- Who bears H.264/HEVC/AAC royalties for Electron apps: NOT VERIFIED (no statement in Electron v45.2.3 faq.md, application-distribution.md or mac-app-store-submission-guide.md).

### 2.5 PyAV wheels (pinned 18.0.0 and newest 19.0.2)

- [measured] PyAV 18.0.0 bundles FFmpeg 8.1.2 (libavcodec 62.28.102). PyAV 19.0.2 bundles FFmpeg 9.0.2 (libavcodec 63.1.102). All 7 FFmpeg libraries report `"LGPL version 3 or later"` in both (`probe_pyav_18.0.0.json`, `probe_pyav_19.0.2.json`).
- [measured] Both configure lines contain `--enable-libx264 --enable-libx265 --enable-version3`, with `has_enable_gpl: false` and `has_enable_nonfree: false`. 19.0.2 adds `--enable-libvmaf` and drops `--enable-libopencore-amrnb/-amrwb`.
- [measured] Both wheels ship `libx264-165-*.dll` and `libx265-*.dll`. The only licence files in the wheel are `LICENSE.txt`, `AUTHORS.py` and `AUTHORS.rst` (`wheel_license_files`). No x264, x265 or FFmpeg licence text is included.
- [code] Upstream FFmpeg LICENSE.md n8.1.2 lines 84-98: "The following libraries are under GPL version 2: ... libx264 libx265 ... When combining them with FFmpeg, FFmpeg needs to be licensed as GPL as well by passing `--enable-gpl` to configure." Unpatched configure n8.1.2:1988-1998 puts libx264/libx265 in `EXTERNAL_LIBRARY_GPL_LIST`, and configure:4767 is `map "die_license_disabled gpl" $EXTERNAL_LIBRARY_GPL_LIST ...` (`ffmpeg_source_excerpts.txt`). The n9.0.2 LICENSE.md section is identical (`pyav_build_evidence.json`).
- [code] pyav-ffmpeg `patches/ffmpeg.patch` at tag 9.0.2-1 removes `libx264`/`libx265` from `EXTERNAL_LIBRARY_GPL_LIST` and inserts them at the top of `EXTERNAL_LIBRARY_VERSION3_LIST` (`pyav_ffmpeg_patch_9.0.2-1_excerpt.txt`). Tag 8.1.1-2 has the same hunks (`pyav_build_evidence.json`). The patch was introduced in commit dc9ee64dff (2025-06-27), message `GPLv3 OR "LGPLv3 + Exceptions"`.
- [code] PyAV v18.0.0 fetches pyav-ffmpeg release 8.1.2-1 and v19.0.2 fetches 9.0.2-1 (`scripts/ffmpeg-latest.json`, `pyav_build_evidence.json`). Release 8.1.2-1 was "NOT FOUND via API", so its patch was not read. The 18.0.0 binary shows the same licence string and flags.
- [source] x264.h: GPL "version 2 of the License, or ... (at your option) any later version" (Q39); "also available under a commercial proprietary license" (Q40). x265 COPYING: "also available under a commercial proprietary license" (Q41). Both were read from `master`, not the exact commits PyAV builds.
- [source] FFmpeg legal page: "If those parts get used the GPL applies to all of FFmpeg." (Q44). LGPL checklist: "Make sure your program is not using any GPL libraries (notably libx264)." (Q45)
- [measured] Deleting the GPL DLLs breaks PyAV. With `libx264-*.dll` and `libx265-*.dll` removed from a copy, `import av` fails with `ImportError: DLL load failed while importing _core` in both 18.0.0 and 19.0.2 (`pyav_strip_gpl_18.0.0.json`, `pyav_strip_gpl_19.0.2.json`).
- [code] PyAV can build against a chosen FFmpeg: `if arg.startswith("--ffmpeg-dir="):` (PyAV v19.0.2 setup.py:126). A build without x264/x265 was not attempted.
- [measured] These encoders open and write packets in an 8-frame smoke test in both versions: libsvtav1, libvpx (VP8), libvpx-vp9, ffv1, mjpeg, jpeg2000 (FFmpeg native), utvideo, magicyuv, huffyuv, ffvhuff, prores_ks, rawvideo, png, libx264, libx265, h264_nvenc and hevc_nvenc (`video_encoders` in both probe JSONs).
- [measured] Absent in both: libaom-av1, librav1e, libjxl, libopenjpeg and libopenh264 (`UnknownCodecError`). Among decoders, jpegxl/libjxl are absent; libdav1d, ffv1, utvideo, magicyuv, prores and dnxhd are present.
- [measured] Failed to open with default options in both: av1_nvenc (`ExternalError ... avcodec_open2("av1_nvenc", {})`), all `*_qsv` and `*_amf` (`UnknownError`), h264_mf / hevc_mf (`ExternalError`), av1_mf (`Function not implemented`), dnxhd (`Invalid argument`) and libwebp (no container accepted it). This was a default-option smoke test only; the causes were not investigated here (the GPU-encode topic owns this).
- [source] SVT-AV1 licence: "BSD 3-Clause Clear License" (Q42). dav1d: BSD-style redistribution clause (Q43).
- [code] FFmpeg's encoders for FFV1, UT Video, MagicYUV, HuffYUV/FFVHuff and DNxHD are LGPL-2.1-or-later: ffv1enc.c:9-11, utvideoenc.c:8-10, magicyuvenc.c:8-10, huffyuvenc.c:10-12, dnxhdenc.c:12-14 at FFmpeg n8.1.2 (`ffmpeg_source_excerpts.txt`).

### 2.6 OpenCV wheels (pinned opencv-contrib-python 4.12.0.88 and newest opencv-python 5.0.0.93)

- [source] opencv-python README: "All wheels ship with [FFmpeg](http://ffmpeg.org) licensed under the [LGPLv2.1]" (Q47). [code] cv2/LICENSE-3RD-PARTY.txt:243 (4.12.0.88 in the venv): "FFmpeg is redistributed within all opencv-python packages." The LGPL 2.1 text follows at line 250.
- [measured] 4.12.0 ships `opencv_videoio_ffmpeg4120_64.dll` (avcodec 58.134.100). 5.0.0.93 ships `opencv_videoio_ffmpeg500_64.dll` (avcodec 61.19.100). Both configure strings contain `--enable-libopenh264 --enable-libvpx --enable-libaom --disable-nvenc` and no `--enable-gpl` (`probe_opencv_4.12.0.json`, `probe_opencv_5.0.0.93.json`).
- [measured] H.264 through CAP_FFMPEG fails to open in both. OpenCV prints "Failed to load OpenH264 library: openh264-1.8.0-win64.dll" (4.12.0) or "openh264-2.5.0-win64.dll" (5.0.0), then "Please check environment and/or download library: https://github.com/cisco/openh264/releases" (`opencv_openh264_check_4.12.0.json`, `opencv_openh264_check_5.0.0.93.json`; functional check added in this merge).
- [measured] CAP_FFMPEG writes and reads back 10 of 10 frames for AV1 (mkv, mp4), VP8, VP9, FFV1, MJPEG (avi, mkv), HuffYUV and MPEG-4 Part 2 in both versions. `hev1.mp4` opens but reads back 0 frames (258 / 257 bytes).
- [measured] CAP_MSMF writes H.264 whatever FOURCC is requested. `avc1`, `H264`, `hev1`, `av01` and `mp4v` into .mp4 all give `ffprobe_codec: h264` (110194 bytes each). All .mkv, .webm and .avi requests fail to open. Same in 4.12.0 and 5.0.0.93.

### 2.7 Corpus JPEG process (G1)

- [measured] All 1,862 corpus frames (891 + 893 + 19 + 19 + 19 + 10 + 11 across the 7 MJPEG sets) start with SOI, are `SOF0 baseline Huffman`, contain DHT and have no DAC marker (`jpeg_process_audit.json`).

### 2.8 Browser playback (as it bears on licensing / G8)

Test: synthetic `testsrc2` 320x240 clips (no camera content), played in a hidden Electron window and in headless Chrome. A clip counts as "plays + decodes" when it reaches `loadeddata`, `currentTime` advances after `play()`, and a seek to 1.0 s draws a non-black frame to a canvas. `gpu_basic` in the Electron JSONs is basic GPU info only; whether decoding ran on hardware or software was not determined.

- [measured] H.264 mp4, HEVC mp4, AV1 (mp4, webm, mkv), VP9 (webm, mp4) and VP8 webm play + decode in Electron 35.7.5 (Chromium 134.0.6998.205), Electron 45.2.3 (Chromium 156.0.8078.80) and Chrome 156 (`browser_codec_table.md` and the three probe JSONs).
- [measured] MJPEG in mkv/mp4, FFV1 mkv and ProRes mov fail with error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`. MJPEG avi and UT Video avi fail with `DEMUXER_ERROR_COULD_NOT_OPEN`. Same in all three browsers.
- [measured] `<img>` and ImageDecoder accept JPEG, AVIF, WebP and PNG in all three. JPEG XL gives error / `false` in Electron 35.7.5 and load / `true` in Electron 45.2.3 and Chrome 156. JPEG 2000 fails in all three.
- [measured] `canPlayType('video/x-matroska; codecs="av01.0.04M.08"')` returns '' in 35.7.5 and 'probably' in 45.2.3. `MediaSource.isTypeSupported` is false for x-matroska in all three.
- [measured] Opus (webm, mp4), FLAC (flac, mp4), AAC m4a, PCM wav and MP3 play in all three.
- [measured] WebCodecs: HEVC prefer-software decode and encode are false in all three. For AV1 and VP9, prefer-hardware encode is false and software encode is true.

## 3. Comparison tables

### 3.1 Video codecs for recording (G4/G7) against the tested stack

| Codec | Royalty statement (primary source) | Royalty-bearing pool claims | Python encoder (PyAV 18/19 wheel, this machine) | GPU encode opened here | Electron 35 / 45 playback |
|---|---|---|---|---|---|
| JPEG baseline (passthrough) | No patents listed for non-arithmetic processes (Q17, Q18); "de facto ... RF" (Q19) | none found | none needed (bytes stored as received) | n/a | as images only (`<img>`, ImageDecoder); MJPEG in mkv/mp4/avi: no |
| AV1 | AOM royalty-free licence (Q01) | Sisvel (Q04, S1); Avanci, VDP for streaming (Q10, Q11) | libsvtav1 opens (BSD-3-Clause-Clear, Q42) | av1_nvenc fails | yes / yes |
| VP9 | Google grant for its implementations (Q12, Q13) | Sisvel (Q07, Q08); Avanci, VDP (Q10, Q11) | libvpx-vp9 opens | none of the probed GPU encoders | yes / yes |
| VP8 | VP8 cross-licence (Q14) | NOT VERIFIED | libvpx opens | none | yes / yes |
| FFV1 (lossless) | none; 0 IETF disclosures (measured) | none found | ffv1 opens (LGPL-2.1+) | none | no / no |
| JPEG XL | Google grant for libjxl (Q22); "royalty-free reference implementation" (Q21) | NOT VERIFIED | not in wheels | none | no / `<img>` + ImageDecoder only |
| JPEG 2000 | "royalty-free objective" (Q23) | NOT VERIFIED | jpeg2000 (native) opens | none | no / no |
| UT Video / MagicYUV / HuffYUV | NOT VERIFIED | NOT VERIFIED | opens (LGPL-2.1+ FFmpeg implementations) | none | UT Video avi: no / no |
| ProRes | Apple licenses specific products (Q27); FFmpeg is "unauthorized" (Q28) | terms NOT VERIFIED | prores_ks opens | none | no / no |
| DNxHD | NOT VERIFIED | NOT VERIFIED | dnxhd fails with default options | none | not tested |
| H.264 | none | Via LA (Q29) | libx264 (GPL-2.0+, Q39) opens | h264_nvenc opens | yes / yes |
| HEVC | none | Access Advance / Via LA (Q31-Q34) | libx265 (GPL-2.0+, Q41) opens | hevc_nvenc opens | yes / yes (HEVC extension installed here) |

### 3.2 Library version bumps: what changes for licensing and format support

| Item | Pinned | Newest | Difference found |
|---|---|---|---|
| PyAV | 18.0.0, FFmpeg 8.1.2 | 19.0.2, FFmpeg 9.0.2 | Same licence string, same GPL x264/x265 DLLs, same encoder open/fail results; 19.0.2 adds libvmaf and drops opencore-amr |
| OpenCV | contrib 4.12.0.88, avcodec 58.134.100 | 5.0.0.93, avcodec 61.19.100 | Same codec write results; H.264 needs Cisco DLL 1.8.0 vs 2.5.0; MSMF still always writes H.264 |
| Electron | 35.7.5 (Chromium 134) | 45.2.3 (Chromium 156) | 45.2.3 adds JPEG XL `<img>`/ImageDecoder and 'probably' for `video/x-matroska`; no other difference in this probe |

### 3.3 Audio

| Codec | Statement | IETF disclosures | Plays in Electron 35 / 45 |
|---|---|---|---|
| Opus | royalty-free licences (Q53) | 5 (RFC 6716) + 11 (draft); 4 holders declared RAND "with Possible Royalty/Fee" | yes / yes |
| FLAC | "unencumbered by patents" (Q54) | 0 | yes / yes |
| AAC | Via LA fee from unit 1 (Q57) | n/a | yes / yes |
| PCM WAV | NOT VERIFIED | n/a | yes / yes |

## 4. Implications for the plan

- G1: store the cameras' JPEG bytes unchanged. Only the JPEG process with no listed patents gets stored: the corpus is 100% SOF0 baseline Huffman with no DAC (2.7, Q17, Q18). No encoder library is involved for these frames.
- G1/G8: do not rely on an MJPEG video container for UI playback. MJPEG in mkv, mp4 and avi fails in both Electron versions, while JPEG frames do decode as images (2.8). [inferred] UI playback of passthrough recordings needs per-frame JPEG decode (`<img>`, ImageDecoder or WebCodecs) fed from a folder or an indexed container, or a playable proxy.
- Container: Matroska has 0 IETF IPR disclosures (2.2). ISO BMFF status is NOT VERIFIED. [inferred] For licensing, Matroska/WebM is the better-documented choice; MP4 is not ruled out, only unverified.
- Do not record through cv2 + CAP_MSMF for any royalty-free goal. It writes H.264 whatever FOURCC is passed, in both OpenCV 4.12.0 and 5.0.0.93 (2.6). This is today's skellycam path.
- G4/G7 compressed I-frame: AV1 (libsvtav1) and VP9 (libvpx-vp9) are the only tested codecs that have a primary-source royalty-free licence, encode in the stock PyAV wheel and play in Electron (3.1). Both also face royalty-bearing pool claims (Q04, Q07, S1). The plan should describe them as "royalty-free licence from the developers, contested by Sisvel", not as patent-free.
- G4 lossless: FFV1 is the best-documented lossless option (an RFC, 0 disclosures, LGPL encoder), but it does not play in Chromium (2.8). [inferred] A lossless archive needs a separate playable proxy or a decode path in Python. Avoid ProRes (Apple calls FFmpeg's implementation unauthorized, Q28). Treat UT Video, MagicYUV, HuffYUV and DNxHD as unknown status.
- G6 vs G7 conflict on this machine: the only GPU encoders that opened are h264_nvenc and hevc_nvenc (2.5), and both codecs are in patent pools (Q29, Q31). av1_nvenc did not open on the RTX 3070. NVIDIA leaves codec patent responsibility with the developer (Q49). [inferred] On Gerald, royalty-free compressed encode means CPU (libsvtav1 / libvpx), and GPU encode means accepting H.264/HEVC. Cross-check with the GPU-encode topic.
- Distribution: the stock PyAV wheels (both 18.0.0 and 19.0.2) ship GPL-2.0+ x264/x265 DLLs that cannot be deleted without breaking `import av` (2.5). [inferred] If skellycam ships PyAV inside an installer, it either meets the GPL/x264 terms or uses a custom FFmpeg/PyAV build without libx264/libx265 (`--ffmpeg-dir=`). Bumping PyAV does not change this.
- Version bumps: bumping PyAV to 19.0.2 or OpenCV to 5.0.0.93 gives no new codec relevant to G7 in these probes (3.2). Bumping Electron to 45.2.3 adds JPEG XL image decode (2.8). [inferred] JPEG XL storage would still need a Python encoder (libjxl is missing from the PyAV wheels and was not tested separately), so the Electron bump alone does not enable a JXL recording path.
- Audio: Opus and FLAC both play in Electron and have royalty-free / patent-unencumbered statements (Q53, Q54). FLAC has no IETF disclosures; Opus has RAND-with-possible-royalty disclosures. Avoid AAC (fee from the first unit, Q57).
- Electron already ships H.264/HEVC/AAC decoding (`proprietary_codecs = true`) and publishes a separate ffmpeg DLL with each release (2.4). Who bears those royalties is NOT VERIFIED. [inferred] That question exists today whatever recording format is chosen.

## 5. Not tested / limits / NOT VERIFIED

- Not legal advice. Only the licensors' public summaries were read, not any full pool agreement (Via LA, Access Advance, Sisvel, Avanci). Via LA says only the agreement itself is definitive (Q30).
- NOT VERIFIED: ISO/ITU-T patent declarations for JPEG, JPEG XL, JPEG 2000, ISO BMFF and VC-3 (the databases returned 403 or need a form); the EC notice on AOM; the Google-MPEG LA VP8 agreement; MJPEG as a whole; AVI, NUT and PCM/WAV status; UT Video, MagicYUV and HuffYUV patent status; ProRes terms; anything about DNxHD; the royalty position of MF, VideoToolbox and Electron.
- Zero IETF disclosures (FFV1, Matroska, FLAC) is evidence only about IETF disclosures, not about patents in general.
- The x264/x265 licence texts came from `master`, not the exact commits PyAV builds. The pyav-ffmpeg release 8.1.2-1 patch was not read (not found via API).
- Encoder results come from default-option, 8-frame open tests. They say nothing about speed or quality. A QSV failure does not show that QSV hardware is absent (not investigated). DNxHD failed only with default options.
- Browser tests used tiny synthetic clips. They establish support, not performance or frame accuracy. HEVC/AV1/VP9 results may depend on the Windows codec extensions installed here (2.4). Hardware vs software decode was not determined.
- Windows only: macOS/Linux wheels and VideoToolbox were not tested. A custom PyAV build without x264/x265 was not attempted. The libjxl encoder was not tested.

## 6. How to reproduce

Run from the repo root in Git Bash.

```
S=research/skellycam_recording/recording_upgrade/scripts/licensing
R=research/skellycam_recording/recording_upgrade/results/licensing
M=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/licensing
TMP=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/licensing
export UV_CACHE_DIR=$TMP/uv-cache
# PyAV build/licence probes
.venv/Scripts/python.exe $S/probe_pyav_build.py --out $R/probe_pyav_18.0.0.json
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.3.4 python -I $S/probe_pyav_build.py --out $R/probe_pyav_19.0.2.json
.venv/Scripts/python.exe $S/pyav_strip_gpl_test.py --tmp $TMP/strip_test --out $R/pyav_strip_gpl_18.0.0.json
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.3.4 python -I $S/pyav_strip_gpl_test.py --tmp $TMP/strip_test --out $R/pyav_strip_gpl_19.0.2.json
python $S/pyav_build_evidence.py --out $R/pyav_build_evidence.json          # needs gh CLI
gh api "repos/PyAV-Org/pyav-ffmpeg/contents/patches/ffmpeg.patch?ref=9.0.2-1" -H "Accept: application/vnd.github.raw" | head -30
# OpenCV probes
.venv/Scripts/python.exe $S/probe_opencv_build.py --out $R/probe_opencv_4.12.0.json --tmp $M
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/probe_opencv_build.py --out $R/probe_opencv_5.0.0.93.json --tmp $M
.venv/Scripts/python.exe -I $S/opencv_openh264_check.py --tmp $M/openh264_check_4120 --out $R/opencv_openh264_check_4.12.0.json
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/opencv_openh264_check.py --tmp $M/openh264_check_500 --out $R/opencv_openh264_check_5.0.0.93.json
# Browser probes (unset ELECTRON_RUN_AS_NODE first: VS Code sets it and electron.exe then runs as node)
bash $S/make_codec_samples.sh $M/samples
unset ELECTRON_RUN_AS_NODE
skellycam-ui/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_35.7.5.json
$TMP/../shared/electron-latest/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_45.2.3.json
python $S/run_chrome_probe.py --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --samples $M/samples --profile $TMP/chrome-profile3 --out $R/chrome_codec_probe.json
python $S/summarize_browser_probe.py $R/electron_codec_probe_35.7.5.json $R/electron_codec_probe_45.2.3.json $R/chrome_codec_probe.json > $R/browser_codec_table.md
# Electron GN args and release assets
for t in v35.7.5 v45.2.3; do gh api "repos/electron/electron/contents/build/args/all.gn?ref=$t" -H "Accept: application/vnd.github.raw" | grep -n -E "proprietary_codecs|ffmpeg_branding"; gh api "repos/electron/electron/releases/tags/$t" --jq '.assets[].name' | grep -E "^ffmpeg-.*win32-x64"; done
# FFmpeg source licence headers (full list in ffmpeg_source_excerpts.txt)
gh api "repos/FFmpeg/FFmpeg/contents/libavcodec/ffv1enc.c?ref=n8.1.2" -H "Accept: application/vnd.github.raw" | sed -n '9,11p'
# Corpus JPEG process audit (read-only)
python $S/jpeg_process_audit.py --corpus C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus --out $R/jpeg_process_audit.json
# IETF IPR disclosures (JSON API; the HTML search page returns 403)
python $S/ietf_ipr_query.py --out $R/ietf_ipr_disclosures.json rfc9043 draft-ietf-cellar-ffv1 draft-ietf-cellar-ffv1-v4 rfc9559 draft-ietf-cellar-matroska rfc9639 draft-ietf-cellar-flac rfc6716 draft-ietf-codec-opus rfc8251 rfc7845
# Primary sources: download + verbatim quote check (pypdf 5.4.0 via PEP 723)
(cd $S && uv run --script fetch_sources.py fetch --sources sources.json --cache $TMP/sources_cache)
(cd $S && uv run --script fetch_sources.py verify --quotes quotes.json --cache $TMP/sources_cache --out ../../results/licensing/quote_verification.json)
```

PowerShell, read-only: `Get-AppxPackage | Where-Object Name -match 'HEVC|AV1|VP9|MPEG2|RawImage|WebpImage|HEIF' | Select-Object Name, Version`.

nvidia-smi `encoder.stats.sessionCount, utilization.gpu` before and after the GPU-touching probes: sessionCount 0 in every sample, utilization 0-11 % (`nvsmi_pyav18.txt`, `nvsmi_pyav19.txt`, `nvsmi_opencv.txt`, `nvsmi_browser_probes.txt`).

Third-party downloads (temp only, via uv into `$TMP/uv-cache`): PyPI av 19.0.2, opencv-python 5.0.0.93, numpy 2.3.4, pypdf 5.4.0. Primary-source pages are cached in `$TMP/sources_cache` (URLs and sha256 in `source_fetch_log.json`).