# Licensing findings (G7): royalty-free codecs, containers and libraries

Study: skellycam recording upgrade, topic `licensing`. Machine Gerald (Windows 11, i7-14700K, Intel UHD Graphics 770 iGPU, RTX 3070, driver 610.88). Date 2026-11-09.
Merged from `NOTES.md` and the raw result files in this folder, then revised against `VERIFY_provenance.md` and `VERIFY_method.md` (see section 7). This topic did no timing work, so there is no `BENCH.md` or `bench/`.
This is not legal advice. It reports what licence texts and licensors say, plus functional tests on this machine.

Labels: **[measured]** = result file in this folder; **[source]** = primary source, verbatim quote, accessed 2026-11-09; **[secondary]** = published account that is not the licensor or standards body; **[code]** = source file:line at a pinned tag or commit; **[inferred]** = reasoning, kept short; **[background]** = result from PyAV 18.0.0 or from the skellycam venv, kept for context only (the study's test rule is PyAV 19.0.2); **NOT VERIFIED** = no primary source or test.

Quote ids (Qnn) are entries in `quote_verification.json`: 59 of 59 have `found_verbatim: true` against the downloaded page text, and both verifiers re-ran the check (59/59). Quotes S1-S3 are in `quote_verification_supplement.txt`. Quotes N1-N3 were grep-checked against the same cache during the revise step (section 7). URL, HTTP status, sha256 and fetch time per page are in `source_fetch_log.json`.

## 1. Questions answered

1. Which candidate codecs and containers have a primary-source royalty-free statement, which are royalty-bearing, and which are unknown?
2. What do the Python libraries skellycam would use (PyAV 19.0.2 primary, 18.0.0 pinned as background; OpenCV 4.12.0.88 pinned / 5.0.0.93 newest) actually ship, licence-wise? Which encoders open on this machine?
3. Which of these formats play natively in Electron 35.7.5 (pinned), Electron 45.2.3 (newest) and Chrome 156?
4. Does the G1 JPEG passthrough store only the JPEG process with no listed patents?

## 2. Findings

### 2.1 Video codecs: licensor statements

- [source] AV1: AOM Patent License 1.0 grants a "no-charge, royalty-free, irrevocable (except as expressly stated in this License) patent license to its Necessary Claims to make, use, sell, offer for sale, import or distribute any Implementation." (Q01, https://aomedia.org/license/patent-license/)
- [source] AV1: "Implementation" means "any implementation, including the Reference Implementation, that is an Encoder and/or a Decoder." (Q58). So the grant is not limited to AOM's own code.
- [source] AV1: the licence is "immediately terminated" for a licensee that starts patent action (Q03). A licensee "must reproduce this License with any Implementation" (Q02).
- [source] AV1: Sisvel "offers royalty-bearing ... licences ... to patents related to the AV1 specification" (Q04), covering "any consumer product making use of the AV1 specification" (Q05). Rates table, two columns: "Standard Rate Compliant Rate Consumer Display Device* EUR 0.32 EUR 0.24 Consumer Non-Display Device** EUR 0.11 EUR 0.08" (S1). That is, per consumer display device EUR 0.32 standard or EUR 0.24 compliant; per non-display device EUR 0.11 or EUR 0.08.
- [source] AV1 and VP9 are also in streaming-provider pools: Avanci Video (Q10) and the Access Advance VDP pool, "which covers four codecs including HEVC, VVC, VP9, and AV1" (Q11).
- [source] AOM press release (May 23, 2023): "European Commission has today closed its preliminary review of AOMedia's royalty-free licensing policy without further action" (S3). The Commission's own notice: NOT VERIFIED.
- [source] VP9: Google grants a "no-charge, royalty-free, irrevocable (except as stated in this section) patent license ... of these implementations of WebM" (Q12). It "does not include claims that would be infringed only as a consequence of further modification of these implementations" (Q13).
- [source] VP9: Sisvel offers "royalty-bearing" VP9 licences (Q07). Rates table, same two columns ("Standard Rate Compliant Rate", N3): "Consumer Display Device* EUR 0.24 EUR 0.18 Consumer Non-Display Device** EUR 0.08 EUR 0.06" (Q08).
- [source] VP8: "The VP8 Cross-License Agreement helps create a royalty-free ecosystem for VP8" (Q14). Sisvel's VP9 page refers to "the Google-MPEG LA agreement ... Covering VP8 Video Format" (S2). That agreement was not fetched: NOT VERIFIED.
- [source] FFV1 (RFC 9043): CABAC was replaced by a range coder "due to the uncertain patent/royalty situation" (Q16).
- [measured] FFV1: IETF Datatracker lists 0 IPR disclosures for rfc9043, draft-ietf-cellar-ffv1 and draft-ietf-cellar-ffv1-v4 (`ietf_ipr_disclosures.json`, queried 2026-11-09T16:09:37Z). The same query finds 5 and 11 disclosures for the Opus names, so a zero is not an API-name mismatch. No positive royalty-free declaration was found.
- [source] JPEG baseline: T.81 Annex L lists patents for processes "which uses arithmetic coding" (Q17), plus one for hierarchical processes with a lossless final frame (US 4,665,436, read in context by both verifiers). "No other patents required for implementation of any of the other processes ... had been identified at the time of publication of this Specification." (Q18). The copy read is the W3C mirror https://www.w3.org/Graphics/JPEG/itu-t81.pdf, not itu.int (sha256 in `source_fetch_log.json`). It reflects 1992 knowledge ("at the time of publication").
- [secondary] JPEG baseline: an ITU Journal 2020 history article says "de facto the baseline mode of JPEG remained RF" (Q19) and "Author's note - All JPEG-1 patents have now expired." (Q20). Neither is a standards-body patent statement.
- [secondary] JPEG baseline: Joan Mitchell (T.81 co-editor), on her page at w3.org: "So far no one has pressed any claims on the JPEG baseline (sequential Huffman) system that I know of." (Q56; undated personal statement.)
- NOT VERIFIED: ISO and ITU-T patent declaration databases for JPEG (HTTP 403 / search form only). [measured] jpeg.org/jpeg has no royalty, patent or licence wording: 0 matching lines in the cached page text (`revise_no_statement_greps.txt`).
- NOT VERIFIED: "Motion JPEG" as a whole. There is no single MJPEG spec; each container defines its own carriage.
- [source] JPEG XL: Part 4 "Provides a free and open source, royalty-free JPEG XL reference implementation" (Q21, jpeg.org). This describes the reference software, not a patent licence for the format. The only patent grant found is Google's, limited to "this implementation of JPEG XL" (libjxl v0.11.1 PATENTS, Q22). A format-level royalty-free statement or ISO/IEC 18181 declarations: NOT VERIFIED.
- [source] JPEG 2000: "has a royalty-free objective" (Q23); Part 15 (HTJ2K) "is intended to be royalty-free" (Q24). An objective is not a licence. Declarations: NOT VERIFIED.
- [source] UT Video original codec: "is licensed under [GNU General Public License (GNU GPL) version 2](gplv2.txt) or later." (Q25, README on `master`). Patent status: NOT VERIFIED.
- [source] MagicYUV is a commercial product: "We offer MagicYUV at a low price" (Q26). Format/patent licence: NOT VERIFIED.
- HuffYUV / FFVHuff: the original HuffYUV page (neuron2.net mirror) returned HTTP 200 (346,182 bytes), but only 14 characters of text were extracted and the cached copy was not kept (`source_fetch_log.json`). Licence and patent status NOT VERIFIED.
- [source] ProRes: "Apple also licenses and certifies ProRes and ProRes RAW for specific third-party products and workflows." (Q27). "Using any unauthorized implementation (such as the FFmpeg and derivative implementations) might lead to decoding errors, performance degradation, incompatibility, and instability." (Q28). Royalty terms: NOT VERIFIED.
- DNxHD / DNxHR (SMPTE VC-3): NOT VERIFIED (avid.com and smpte.org pages returned HTTP 404, `source_fetch_log.json`).
- [source] H.264: Via LA AVC, "Section 1 - Codec Manufacture and Sales Products sold to End Users and OEMs for PCs (except for products that are part of a personal computer's operating system)" (N2): "For the first 1 to 100,000 units $0.00* For units 100,001 to 5,000,000 $ 0.20 ea. For units 5,000,001 and more $ 0.10 ea." (Q29). The footnote reads "*Available to one legal entity in an affiliated group", and the enterprise cap is "$9.75M per year in 2017 and after" (N2). "The actual License agreement provides the only definitive and reliable statement of license terms." (Q30)
- [source] H.264 via Cisco OpenH264: Cisco covers the fees only if "the team can use the binary module distributed by Cisco" (Q35), and only when "The Cisco-provided binary is separately downloaded to an end user's device, and not integrated into or combined with third party software" (Q36). Covered use: "PERSONAL USE OF A CONSUMER OR OTHER USES IN WHICH IT DOES NOT RECEIVE REMUNERATION" (Q37). "Cisco is providing no such guarantee" for other patent holders (Q38).
- [source] HEVC: Via LA HEVC/VVC fees: "For the first 1 to 100,000 units $0.00* For units 100,001 and more $ 0.30 ea. for sales in R1** $0.20 ea. for sales in R2**" (Q31). "as of December 15, 2025, Access Advance has acquired this HEVC/VVC program" (Q32).
- [source] HEVC: Access Advance licenses "HEVC Decoders and HEVC Encoders in Consumer HEVC Products, whether made available in devices, software, or through Cloud Based Services" (Q33) and seeks "one royalty per device/software copy on First Sale" (Q34). A below-threshold or free-software term on the Access Advance pages: NOT VERIFIED.
- [source] FFmpeg legal page: "Q: Does FFmpeg use patented algorithms? A: We do not know, we are not lawyers so we are not qualified to answer this." (Q46).

### 2.2 Containers

- [measured] Matroska (RFC 9559): 0 IETF IPR disclosures for rfc9559 and draft-ietf-cellar-matroska (`ietf_ipr_disclosures.json`).
- [source] WebM: "Google, Matroska and the Xiph.Org Foundation make the various components of WebM openly available on royalty- free terms." (Q59)
- [source] ISO BMFF: ISO's former Publicly Available Standards "are now available at no charge on the ISO and IEC webstores" (Q55). Whether 14496-12 is among them, and its patent declarations: NOT VERIFIED (iso.org HTTP 403).
- AVI (RIFF): Microsoft's reference page has no licence or royalty statement. Royalty status NOT VERIFIED.
- NUT: NOT VERIFIED (ffmpeg.org/~michael/nut.txt returned a stub).

### 2.3 Audio (if audio is recorded)

- [source] Opus: "protective, royalty-free licenses for the required patents" (Q53).
- [measured] Opus: 5 IETF disclosures on RFC 6716 (3 posted, 2 in state "rejected", Microsoft ids 2486 and 2487) and 11 on draft-ietf-codec-opus. France Telecom and Ericsson (RFC 6716) and Qualcomm and Huawei (draft) declared "c) Reasonable and Non-Discriminatory License to All Implementers with Possible Royalty/Fee" (`ietf_ipr_disclosures.json`).
- [source] FLAC: "is non-proprietary, is unencumbered by patents" (Q54). [measured] 0 IETF disclosures for rfc9639 / draft-ietf-cellar-flac.
- [source] AAC: Via LA "For the first 1 to 500,000 units $0.98 For units 500,001 to 1,000,000 $0.78" (Q57).
- PCM / WAV: NOT VERIFIED.

### 2.4 Platform encoders and SDKs

- [source] NVIDIA Video Codec SDK 13.0 licence: "NVIDIA does not grant to you under this license any necessary patent or other rights with respect to any audio and/or video encoders and decoders." (Q49). The CUDA EULA has the same sentence (Q48).
- [source] The same SDK licence page: "it is your sole responsibility to obtain any additional third-party licenses required to make, have made, use, have used, sell, import, and offer for sale your products or services that include or incorporate any third-party software and content relating to audio and/or video encoders and decoders" (N1). So NVENC users carry the codec patent licensing themselves.
- [source] nvjpeg.dll is a CUDA redistributable component (Q50).
- [source] nvImageCodec: binary redistribution is allowed only "as incorporated into a software application" with "material additional functionality" (Q51). "You may not use the Software in any manner that would cause it to become subject to an open source software license" (Q52).
- Windows Media Foundation H.264 encoder: Microsoft's page has no royalty statement. Who bears codec royalties: NOT VERIFIED.
- [measured] This machine has Microsoft.HEVCVideoExtension 2.5.48.0, AV1VideoExtension 2.0.35.0 and VP9VideoExtensions 1.2.20.0 installed, plus the MPEG2, HEIF, WebP and Raw image extensions (`appx_codec_extensions.txt`, read-only `Get-AppxPackage`).
- [inferred] Media Foundation and Chromium HEVC results may differ on a clean Windows install without these extensions. Not tested.
- Apple VideoToolbox licence: NOT VERIFIED (the page is JavaScript-rendered).
- [code] Electron builds Chromium with `ffmpeg_branding = "Chrome"` and `proprietary_codecs = true`: all.gn lines 17-18 at v35.7.5, lines 40-41 at v45.2.3 (`electron_gn_args_excerpt.txt`).
- [code] Electron release.gn lines 5-8 (both tags): "By default, Electron builds ffmpeg with proprietary codecs enabled. In order to facilitate users who don't want to ship proprietary codecs in ffmpeg, or who have an LGPL requirement to ship ffmpeg as a dynamically linked library, we build ffmpeg as a shared library." The releases ship `ffmpeg-v35.7.5-win32-x64.zip` and `ffmpeg-v45.2.3-win32-x64.zip` (`electron_gn_args_excerpt.txt`).
- [measured] Electron v45.2.3 docs/faq.md, tutorial/application-distribution.md and tutorial/mac-app-store-submission-guide.md have 0 lines matching royalt / proprietary / h.264 / h264 / patent / codec (`revise_no_statement_greps.txt`). Who bears H.264/HEVC/AAC royalties for Electron apps: NOT VERIFIED.

### 2.5 PyAV wheels (19.0.2 primary; 18.0.0 background)

- [measured] PyAV 19.0.2 bundles FFmpeg 9.0.2 (libavcodec 63.1.102). All 7 FFmpeg libraries report `"LGPL version 3 or later"` (`probe_pyav_19.0.2.json`, run in a uv env with `av==19.0.2`).
- [measured] The 19.0.2 configure line contains `--enable-libx264 --enable-libx265 --enable-version3 --enable-libvmaf`, with `has_enable_gpl: false` and `has_enable_nonfree: false` (`probe_pyav_19.0.2.json`).
- [measured] The 19.0.2 wheel ships `libx264-165-*.dll` and `libx265-*.dll`. The only licence files in the wheel are `LICENSE.txt`, `AUTHORS.py` and `AUTHORS.rst` (`wheel_license_files`). No x264, x265 or FFmpeg licence text is included.
- [background] PyAV 18.0.0 (skellycam venv) bundles FFmpeg 8.1.2 (libavcodec 62.28.102), reports the same licence string and flags, ships the same GPL DLLs, and additionally has `--enable-libopencore-amrnb/-amrwb` and no libvmaf (`probe_pyav_18.0.0.json`).
- [code] Upstream FFmpeg LICENSE.md n8.1.2 lines 84-98: "The following libraries are under GPL version 2: ... libx264 libx265 ... When combining them with FFmpeg, FFmpeg needs to be licensed as GPL as well by passing `--enable-gpl` to configure." The n9.0.2 LICENSE.md section is identical (`pyav_build_evidence.json`). Unpatched configure n8.1.2:1988-1998 puts libx264/libx265 in `EXTERNAL_LIBRARY_GPL_LIST`, and configure:4767 is `map "die_license_disabled gpl" $EXTERNAL_LIBRARY_GPL_LIST ...` (`ffmpeg_source_excerpts.txt`).
- [code] pyav-ffmpeg `patches/ffmpeg.patch` at tag 9.0.2-1 removes `libx264`/`libx265` from `EXTERNAL_LIBRARY_GPL_LIST` and inserts them at the top of `EXTERNAL_LIBRARY_VERSION3_LIST` (`pyav_ffmpeg_patch_9.0.2-1_excerpt.txt`). Tag 8.1.1-2 has the same hunks. The patch was introduced in commit dc9ee64dff (2025-06-27T02:08:25Z), message starting `GPLv3 OR` (`pyav_build_evidence.json`).
- [code] PyAV v19.0.2 fetches pyav-ffmpeg release 9.0.2-1; v18.0.0 fetches 8.1.2-1, which returns 404 via the API, so its patch was not read (`pyav_build_evidence.json`).
- [source] x264.h: GPL "version 2 of the License, or ... (at your option) any later version" (Q39); "also available under a commercial proprietary license" (Q40). x265 COPYING: "also available under a commercial proprietary license" (Q41). Both were read from `master`, not the exact commits PyAV builds.
- [source] FFmpeg legal page: "If those parts get used the GPL applies to all of FFmpeg." (Q44). LGPL checklist: "Make sure your program is not using any GPL libraries (notably libx264)." (Q45)
- [measured] The GPL DLLs cannot be deleted from PyAV 19.0.2. In copies of the package, the unmodified control imports from the copy; removing only libx264, only libx265, or both gives `ImportError: DLL load failed while importing _core` (`revise_pyav_strip_gpl_control_19.0.2.json`; first run without control: `pyav_strip_gpl_19.0.2.json`). [background] Same in 18.0.0 (`pyav_strip_gpl_18.0.0.json`, plus a verifier control run).
- [code] PyAV can build against a chosen FFmpeg: `if arg.startswith("--ffmpeg-dir="):` (PyAV v19.0.2 setup.py:126). A build without x264/x265 was not attempted.
- [measured] Encoders that open and write packets in an 8-frame default-option test, PyAV 19.0.2 (10:55 local run): libsvtav1, libvpx (VP8), libvpx-vp9, ffv1, mjpeg, jpeg2000 (FFmpeg native), utvideo, magicyuv, huffyuv, ffvhuff, prores_ks, rawvideo, png, libx264, libx265, h264_nvenc and hevc_nvenc (`video_encoders` in `probe_pyav_19.0.2.json`). [background] 18.0.0 gives identical present/opens flags for every encoder probed (`probe_pyav_18.0.0.json`).
- [measured] Absent in 19.0.2: libaom-av1, librav1e, libjxl, libopenjpeg and libopenh264 (`UnknownCodecError`). Among decoders, jpegxl/libjxl are absent; libdav1d, ffv1, utvideo, magicyuv, prores and dnxhd are present.
- [measured] Failed to open with default options in the 10:55 run: av1_nvenc (`ExternalError ... avcodec_open2("av1_nvenc", {})`), all `*_qsv` and `*_amf` (`UnknownError`), h264_mf / hevc_mf (`ExternalError`), av1_mf (`Function not implemented`), dnxhd (`Invalid argument`) and libwebp (no container accepted it) (`probe_pyav_19.0.2.json`).
- [measured] QSV re-check in the revise step, PyAV 19.0.2, 8 frames 640x480 nv12, default options (21:4x UTC): h264_qsv, hevc_qsv, vp9_qsv and mjpeg_qsv open and emit 8 packets; av1_qsv fails with `Function not implemented` (`revise_qsv_open_19.0.2.json`). At that time the Intel UHD Graphics 770 was listed `OK`, `Present True` (`revise_env_check.txt`). Decoding of the emitted packets and whether they ran on the iGPU were not checked.
- [inferred] The 10:55 `*_qsv` failures are superseded by the re-check. The study brief attributes them to the iGPU being absent at that time; this topic did not record the device state at 10:55, so that cause is NOT VERIFIED here. The GPU-encode / hw_accel_target topics own the QSV analysis.
- [source] SVT-AV1 LICENSE.md: "BSD 3-Clause Clear License" (Q42). The same file says "NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE" (grep-checked in the cached `svtav1_license.txt`). The AV1 patent grant for an SVT-AV1 user therefore comes from the AOM licence (Q01, Q58), not from this file. Read from `master`, not the SVT-AV1 version in the wheel.
- [source] dav1d COPYING: BSD-style redistribution clause (Q43, `master`).
- [code] FFmpeg's encoders for FFV1, UT Video, MagicYUV, HuffYUV/FFVHuff and DNxHD are LGPL-2.1-or-later: ffv1enc.c:9-11, utvideoenc.c:8-10, magicyuvenc.c:8-10, huffyuvenc.c:10-12, dnxhdenc.c:12-14 at FFmpeg n8.1.2 (`ffmpeg_source_excerpts.txt`). Not re-read at n9.0.2.

### 2.6 OpenCV wheels (opencv-contrib-python 4.12.0.88 pinned, opencv-python 5.0.0.93 newest)

The two sides are different packages (contrib vs main). Whether their videoio FFmpeg DLLs are identical: NOT VERIFIED. Results marked [background] came from the skellycam venv.

- [source] opencv-python README (`4.x` branch): "All wheels ship with [FFmpeg](http://ffmpeg.org) licensed under the [LGPLv2.1]" (Q47). [code] cv2/LICENSE-3RD-PARTY.txt:243 (4.12.0.88 in the venv): "FFmpeg is redistributed within all opencv-python packages." The LGPL 2.1 text follows at line 250.
- [measured] 5.0.0.93 ships `opencv_videoio_ffmpeg500_64.dll` (avcodec 61.19.100); configure contains `--enable-libopenh264 --enable-libvpx --enable-libaom --disable-nvenc` and no `--enable-gpl` (`probe_opencv_5.0.0.93.json`). [background] 4.12.0 ships `opencv_videoio_ffmpeg4120_64.dll` (avcodec 58.134.100) with the same flags (`probe_opencv_4.12.0.json`).
- [measured] H.264 through CAP_FFMPEG fails to open in 5.0.0.93. stderr: "Failed to load OpenH264 library: openh264-2.5.0-win64.dll", "Please check environment and/or download library: https://github.com/cisco/openh264/releases", then "[libopenh264 ...] Unable to create encoder" (`opencv_openh264_check_5.0.0.93.json`). [background] 4.12.0: "Failed to load OpenH264 library: openh264-1.8.0-win64.dll", then "[libopenh264 ...] Incorrect library version loaded" (`opencv_openh264_check_4.12.0.json`). The exact cause in 4.12.0 (something was loaded) is not pinned down.
- [measured] CAP_FFMPEG writes and reads back 10 of 10 frames for AV1 (mkv, mp4), VP8, VP9, FFV1, MJPEG (avi, mkv), HuffYUV and MPEG-4 Part 2 in 5.0.0.93; `hev1.mp4` opens but reads back 0 frames (257 bytes) (`probe_opencv_5.0.0.93.json`). [background] Same in 4.12.0 (258 bytes) (`probe_opencv_4.12.0.json`).
- [code] CAP_MSMF maps a fixed FOURCC list: `CvVideoWriter_MSMF::FourCC2GUID` (OpenCV 4.12.0 modules/videoio/src/cap_msmf.cpp:2496-2553) maps `HEVC` to `MFVideoFormat_HEVC` (2523-2524), `H265` to `MFVideoFormat_H265` (2521-2522), and also MJPG, MP4V, WMV1/2/3, WVC1, DV and others. Only `default:` returns `MFVideoFormat_H264` (2550-2551).
- [measured] CAP_MSMF in .mp4: `HEVC` writes hevc; `WMV3` (.wmv) writes wmv3; `H265` opens but the file has no readable stream; `MP4V` and `MJPG` do not open; the unmapped `hev1`, `avc1`, `av01` and lowercase `mp4v` all write h264. Identical in opencv-contrib-python 4.12.0.88 (uv env, `revise_msmf_fourcc_4.12.0.88_uv.json`) and opencv-python 5.0.0.93 (`verify_method_msmf_fourcc_5.0.0.93.json`). [background] Same in the venv 4.12.0 (`verify_method_msmf_fourcc_4.12.0.json`).
- [measured] MSMF .mkv, .webm and .avi requests failed to open for the FOURCCs tried in the original probe (`probe_opencv_*.json`).
- [code] skellycam writes with `cv2.VideoWriter(path, fourcc, fps, size)` and no apiPreference (skellycam/core/recorders/videos/video_recorder.py:125, commit 55f851e4). The default writer FOURCC is `X264` (skellycam/core/camera/config/camera_config.py:29), mapped to `.mp4` (fourcc_codec_helpers.py:58). A PyAV/libx264 writer is used only if the OpenCV H.264 probes fail (fourcc_codec_helpers.py:16, 22; video_recorder.py:117-118).
- [measured] That call pattern (no apiPreference, .mp4) with `X264`, `H264` or `avc1` selects the `MSMF` backend and writes h264, in both opencv-contrib-python 4.12.0.88 and opencv-python 5.0.0.93 (`revise_cv2_default_backend_4.12.0.88.json`, `revise_cv2_default_backend_5.0.0.93.json`).
- [inferred] So skellycam's current cv2 recording path on Windows produces H.264 from Media Foundation. None of the codecs that opened through MSMF here (H.264, HEVC, WMV3) has a royalty-free statement in this study.

### 2.7 Corpus JPEG process (G1)

- [measured] All 1,862 corpus frames (891 + 893 + 19 + 19 + 19 + 10 + 11 across the 7 MJPEG sets) start with SOI, are `SOF0 baseline Huffman`, contain DHT and have no DAC marker (`jpeg_process_audit.json`). The sets come from three cameras: Logitech C930e (046d:0843), C922 (046d:085c) and one generic camera (4c4a:4a55) (corpus `index.json`). This is a property of these cameras, not of G1 in general.

### 2.8 Browser playback (as it bears on licensing / G8)

Test: synthetic `testsrc2` clips, 320x240, 2 s, yuv420p 8-bit, default GOP, made with the ffmpeg 9.0.2 CLI (not PyAV) (`scripts/licensing/make_codec_samples.sh`), played in a hidden Electron window and in headless Chrome. A clip counts as "plays + decodes" when it reaches `loadeddata`, `currentTime` advances after `play()`, and after a seek to 1.0 s more than 50 % of canvas pixels are non-black (`probe.html:49`). Not a comparison with reference pixels; but the canvas mean RGB sums agree across runtimes (for example H.264 373.49 in all three). `gpu_basic` in the Electron JSONs is basic GPU info only; hardware vs software decode was not determined. All-intra streams, 4:2:2, 1080p and PyAV-produced files were not tested here (chromium_codecs / chromium_sync_scrub topics).

- [measured] H.264 mp4, HEVC mp4, AV1 (mp4, webm, mkv), VP9 (webm, mp4) and VP8 webm play + decode in Electron 35.7.5 (Chromium 134.0.6998.205), Electron 45.2.3 (Chromium 156.0.8078.80) and Chrome 156 (`browser_codec_table.md` and the three probe JSONs). The Chrome probe recorded only the reduced UA `156.0.0.0`; chrome.exe FileVersion read later the same day is 156.0.8078.80 (`revise_env_check.txt`).
- [measured] MJPEG in mkv/mp4, FFV1 mkv and ProRes mov fail with error 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`. MJPEG avi and UT Video avi fail with `DEMUXER_ERROR_COULD_NOT_OPEN`. Same in all three. These are demuxer errors, so they do not depend on the clip encoder.
- [measured] `<img>` and ImageDecoder accept JPEG, AVIF, WebP and PNG in all three. JPEG XL gives error / `false` in Electron 35.7.5 and load / `true` in Electron 45.2.3 and Chrome 156. JPEG 2000 fails in all three. Images were checked by `onload` + `naturalWidth` only, not pixel-verified.
- [measured] `canPlayType('video/x-matroska; codecs="av01.0.04M.08"')` returns '' in 35.7.5 and 'probably' in 45.2.3. `MediaSource.isTypeSupported` is false for x-matroska in all three.
- [measured] Opus (webm, mp4), FLAC (flac, mp4), AAC m4a, PCM wav and MP3 play in all three.
- [measured] WebCodecs `VideoDecoder/VideoEncoder.isConfigSupported` at 1280x720 (capability query only, no frames encoded): HEVC `prefer-software` is false and `prefer-hardware` is true for both decode and encode in all three runtimes. For AV1 and VP9, encode `prefer-hardware` is false and `prefer-software` is true; decode is true for both (the three probe JSONs).
- [inferred] HEVC playback here relies on a hardware decoder (RTX 3070 and/or the installed HEVC extension), not only on `proprietary_codecs = true`. HEVC playback on machines without HEVC hardware decode: NOT VERIFIED.

## 3. Comparison tables

### 3.1 Video codecs for recording (G4/G7) against the tested stack

| Codec | Royalty statement (primary source) | Royalty-bearing pool claims | Python encoder (PyAV 19.0.2 wheel) | GPU encoder opened here (PyAV 19.0.2) | Electron 35 / 45 playback (4:2:0 test clips) |
|---|---|---|---|---|---|
| JPEG baseline (passthrough) | No patents listed for non-arithmetic, non-hierarchical-lossless processes (Q17, Q18); "de facto ... RF" is secondary (Q19) | none found | none needed (bytes stored as received) | n/a (mjpeg_qsv opens) | as images only (`<img>`, ImageDecoder); MJPEG in mkv/mp4/avi: no |
| AV1 | AOM royalty-free licence covering any implementation (Q01, Q58) | Sisvel (Q04, S1); Avanci, VDP for streaming (Q10, Q11) | libsvtav1 opens (code BSD-3-Clause-Clear, Q42, no patent grant in that file) | none: av1_nvenc fails, av1_qsv ENOSYS | yes / yes |
| VP9 | Google grant for its implementations (Q12, Q13) | Sisvel (Q07, Q08); Avanci, VDP (Q10, Q11) | libvpx-vp9 opens | vp9_qsv opens (Intel iGPU; decode not checked) | yes / yes |
| VP8 | VP8 cross-licence (Q14) | NOT VERIFIED | libvpx opens | none probed | yes / yes |
| FFV1 (lossless) | none; 0 IETF disclosures (measured) | none found | ffv1 opens (LGPL-2.1+) | none | no / no |
| JPEG XL | software only: "royalty-free reference implementation" (Q21); Google grant limited to libjxl (Q22); format-level NOT VERIFIED | NOT VERIFIED | not in wheel | none | no / `<img>` + ImageDecoder only |
| JPEG 2000 | "royalty-free objective" (Q23) | NOT VERIFIED | jpeg2000 (native) opens | none | no / no |
| UT Video / MagicYUV / HuffYUV | NOT VERIFIED | NOT VERIFIED | open (LGPL-2.1+ FFmpeg implementations) | none | UT Video avi: no / no |
| ProRes | Apple licenses specific products (Q27); FFmpeg is "unauthorized" (Q28) | terms NOT VERIFIED | prores_ks opens | none | no / no |
| DNxHD | NOT VERIFIED | NOT VERIFIED | dnxhd fails with default options | none | not tested |
| H.264 | none | Via LA (Q29) | libx264 (GPL-2.0+, Q39) opens | h264_nvenc, h264_qsv open | yes / yes |
| HEVC | none | Access Advance / Via LA (Q31-Q34) | libx265 (GPL-2.0+, Q41) opens | hevc_nvenc, hevc_qsv open | yes / yes (HEVC extension installed; hardware decode inferred) |

### 3.2 Library version bumps: what changes for licensing and format support

| Item | Pinned | Newest | Difference found |
|---|---|---|---|
| PyAV | 18.0.0, FFmpeg 8.1.2 (background) | 19.0.2, FFmpeg 9.0.2 | Same licence string, same GPL x264/x265 DLLs, same encoder present/opens flags; 19.0.2 adds libvmaf and drops opencore-amr |
| OpenCV | opencv-contrib-python 4.12.0.88, avcodec 58.134.100 | opencv-python 5.0.0.93, avcodec 61.19.100 | Same codec write results; H.264 via CAP_FFMPEG needs Cisco DLL 1.8.0 vs 2.5.0; MSMF FOURCC mapping and default-backend result identical |
| Electron | 35.7.5 (Chromium 134) | 45.2.3 (Chromium 156) | 45.2.3 adds JPEG XL `<img>`/ImageDecoder and 'probably' for `video/x-matroska`; no other functional difference in this probe |

### 3.3 Audio

| Codec | Statement | IETF disclosures | Plays in Electron 35 / 45 |
|---|---|---|---|
| Opus | royalty-free licences (Q53) | RFC 6716: 5 (3 posted, 2 rejected); draft: 11; 4 holders declared RAND "with Possible Royalty/Fee" | yes / yes |
| FLAC | "unencumbered by patents" (Q54) | 0 | yes / yes |
| AAC | Via LA fee from unit 1 (Q57) | n/a | yes / yes |
| PCM WAV | NOT VERIFIED | n/a | yes / yes |

## 4. Implications for the plan

- G1: store the cameras' JPEG bytes unchanged. For the three corpus cameras this stores only SOF0 baseline Huffman with no DAC, a process with no patents listed in T.81 Annex L (2.7, Q17, Q18). No encoder library is involved. [inferred] If other cameras matter, the recorder can check each stream's SOF marker (SOF0/SOF1, no DAC) at runtime.
- G1/G8: do not rely on an MJPEG video container for UI playback. MJPEG in mkv, mp4 and avi fails in both Electron versions, while JPEG frames load as images (2.8). [inferred] UI playback of passthrough recordings needs per-frame JPEG decode (`<img>`, ImageDecoder or WebCodecs) fed from a folder or an indexed container, or a playable proxy.
- Container: Matroska has 0 IETF IPR disclosures (2.2). ISO BMFF status is NOT VERIFIED. [inferred] For licensing, Matroska/WebM is the better-documented choice; MP4 is not ruled out, only unverified.
- Today's skellycam path: cv2.VideoWriter with no backend chosen and the default `X264` .mp4 lands on Media Foundation and writes H.264 in both OpenCV versions (2.6). [inferred] No FOURCC change inside cv2 fixes G7 on Windows: the MSMF codecs that opened are H.264, HEVC and WMV3, and the royalty-free CAP_FFMPEG encoders (AV1, VP8, VP9, FFV1) do not play MJPEG-free in every case (FFV1 does not play in Chromium). A royalty-free path means choosing the backend/encoder explicitly.
- G4/G7 compressed I-frame: AV1 (libsvtav1) and VP9 (libvpx-vp9) are the only tested codecs that have a primary-source royalty-free licence, encode in the stock PyAV 19.0.2 wheel and play in Electron (3.1). Both also face royalty-bearing pool claims (Q04, Q07, S1). The plan should describe them as "royalty-free licence from the developers, contested by Sisvel", not as patent-free. Playback of all-intra, 4:2:2 or PyAV-produced streams is for the chromium topics.
- G4 lossless: FFV1 is the best-documented lossless option (an RFC, 0 disclosures, LGPL encoder), but it does not play in Chromium (2.8). [inferred] A lossless archive needs a separate playable proxy or a decode path in Python. Avoid ProRes (Apple calls FFmpeg's implementation unauthorized, Q28). Treat UT Video, MagicYUV, HuffYUV and DNxHD as unknown status.
- G6 vs G7 on this machine: the GPU encoders that opened are h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv and vp9_qsv (2.5). av1_nvenc did not open on the RTX 3070 and av1_qsv did not open on the UHD 770. NVIDIA leaves codec patent licensing with the developer (Q49, N1). [inferred] On Gerald the only royalty-free-licensed GPU encode found is VP9 via Intel QSV; on NVIDIA alone, royalty-free compressed encode means CPU (libsvtav1 / libvpx). Whether vp9_qsv output decodes correctly, and coverage on the hardware target (RTX 3000+, 2020+ CPUs), belongs to the GPU-encode / hw_accel_target topics.
- Distribution: the stock PyAV 19.0.2 wheel ships GPL-2.0+ x264/x265 DLLs that cannot be deleted without breaking `import av` (2.5). [inferred] If skellycam ships PyAV inside an installer, it either meets the GPL/x264 terms or uses a custom FFmpeg/PyAV build without libx264/libx265 (`--ffmpeg-dir=`). Moving from 18.0.0 to 19.0.2 does not change this.
- Version bumps: PyAV 19.0.2 and OpenCV 5.0.0.93 give no new codec relevant to G7 in these probes (3.2). Electron 45.2.3 adds JPEG XL image decode (2.8). [inferred] JPEG XL storage would still need a Python encoder (libjxl is missing from the PyAV wheel and was not tested separately), and JPEG XL has no format-level royalty-free statement here, so the Electron bump alone does not enable a JXL recording path.
- Audio: Opus and FLAC both play in Electron and have royalty-free / patent-unencumbered statements (Q53, Q54). FLAC has no IETF disclosures; Opus has RAND-with-possible-royalty disclosures. Avoid AAC (fee from the first unit, Q57).
- Electron ships H.264/AAC decoding (`proprietary_codecs = true`) and publishes a separate ffmpeg DLL with each release (2.4). HEVC playback also appears to depend on hardware (2.8). Who bears those royalties is NOT VERIFIED. [inferred] That question exists today whatever recording format is chosen.

## 5. Not tested / limits / NOT VERIFIED

- Not legal advice. Only the licensors' public summaries were read, not any full pool agreement (Via LA, Access Advance, Sisvel, Avanci). Via LA says only the agreement itself is definitive (Q30).
- NOT VERIFIED: ISO/ITU-T patent declarations for JPEG, JPEG XL, JPEG 2000, ISO BMFF and VC-3 (the databases returned 403 or need a form); the EC notice on AOM; the Google-MPEG LA VP8 agreement; MJPEG as a whole; AVI, NUT and PCM/WAV status; UT Video, MagicYUV and HuffYUV licence/patent status; ProRes terms; anything about DNxHD; the royalty position of MF, VideoToolbox and Electron; a format-level JPEG XL royalty-free statement.
- Zero IETF disclosures (FFV1, Matroska, FLAC) is evidence only about IETF disclosures, not about patents in general.
- Licence texts read from branches, not the tags the wheels build: x264 and x265 (`master`), SVT-AV1 LICENSE/PATENTS (`master`), dav1d COPYING (`master`), libvpx LICENSE/PATENTS (`main`), UT Video README (`master`), opencv-python README (`4.x`, also used for 5.0.0.93). The pyav-ffmpeg release 8.1.2-1 patch was not read (404).
- Encoder results come from default-option, 8-frame open tests. They say nothing about speed or quality. QSV output was not decoded. DNxHD failed only with default options.
- Browser tests used tiny synthetic 4:2:0 clips from the ffmpeg CLI. They establish support, not performance or frame accuracy. HEVC/AV1/VP9 results may depend on the Windows codec extensions and GPU here. Hardware vs software decode was not determined. WebCodecs results are capability queries only.
- OpenCV contrib vs main packages differ between the two versions compared; the CAP_FFMPEG and openh264 results for 4.12.0 are venv-only (background).
- Windows only: macOS/Linux wheels and VideoToolbox were not tested. A custom PyAV build without x264/x265 was not attempted. The libjxl encoder was not tested.

## 6. How to reproduce

Run from `research/skellycam_recording/recording_upgrade/` in Git Bash unless noted. Commands marked (background) use the skellycam venv and are kept only to reproduce background results.

```
S=scripts/licensing
R=results/licensing
M=C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/licensing
TMP=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/licensing
TMP2=C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/licensing
VENV=../../../.venv/Scripts/python.exe          # (background) skellycam venv
export UV_CACHE_DIR=$TMP/uv-cache
# PyAV 19.0.2 build/licence probes (primary)
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.3.4 python -I $S/probe_pyav_build.py --out $R/probe_pyav_19.0.2.json
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.3.4 python -I $S/pyav_strip_gpl_test.py --tmp $TMP/strip_test --out $R/pyav_strip_gpl_19.0.2.json
uv run --script $S/pyav_strip_gpl_control.py $TMP2/strip_control $R/revise_pyav_strip_gpl_control_19.0.2.json
uv run --script $S/qsv_open_recheck.py $R/revise_qsv_open_19.0.2.json
# PyAV 18.0.0 (background)
$VENV $S/probe_pyav_build.py --out $R/probe_pyav_18.0.0.json
$VENV $S/pyav_strip_gpl_test.py --tmp $TMP/strip_test --out $R/pyav_strip_gpl_18.0.0.json
python $S/pyav_build_evidence.py --out $R/pyav_build_evidence.json          # needs gh CLI
gh api "repos/PyAV-Org/pyav-ffmpeg/contents/patches/ffmpeg.patch?ref=9.0.2-1" -H "Accept: application/vnd.github.raw" | head -30
# OpenCV probes
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/probe_opencv_build.py --out $R/probe_opencv_5.0.0.93.json --tmp $M
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/opencv_openh264_check.py --tmp $M/openh264_check_500 --out $R/opencv_openh264_check_5.0.0.93.json
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/verify_msmf_fourcc_check.py $M/verify_method_500 $R/verify_method_msmf_fourcc_5.0.0.93.json
uv run --no-project --python 3.12 --with opencv-contrib-python==4.12.0.88 --with numpy==2.2.6 python -I $S/verify_msmf_fourcc_check.py $M/revise_msmf_4120_uv $R/revise_msmf_fourcc_4.12.0.88_uv.json
uv run --script $S/cv2_default_backend_check.py $M/revise_default_backend_500 $R/revise_cv2_default_backend_5.0.0.93.json
uv run --no-project --python 3.12 --with opencv-contrib-python==4.12.0.88 --with numpy==2.2.6 python -I $S/cv2_default_backend_check.py $M/revise_default_backend_4120 $R/revise_cv2_default_backend_4.12.0.88.json
$VENV $S/probe_opencv_build.py --out $R/probe_opencv_4.12.0.json --tmp $M                                   # (background)
$VENV -I $S/opencv_openh264_check.py --tmp $M/openh264_check_4120 --out $R/opencv_openh264_check_4.12.0.json  # (background)
gh api "repos/opencv/opencv/contents/modules/videoio/src/cap_msmf.cpp?ref=4.12.0" -H "Accept: application/vnd.github.raw" | sed -n '2496,2553p'
# Browser probes (unset ELECTRON_RUN_AS_NODE first: VS Code sets it and electron.exe then runs as node)
bash $S/make_codec_samples.sh $M/samples
unset ELECTRON_RUN_AS_NODE
../../../skellycam-ui/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_35.7.5.json
$TMP/../shared/electron-latest/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_45.2.3.json
python $S/run_chrome_probe.py --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --samples $M/samples --profile $TMP/chrome-profile3 --out $R/chrome_codec_probe.json
python $S/summarize_browser_probe.py $R/electron_codec_probe_35.7.5.json $R/electron_codec_probe_45.2.3.json $R/chrome_codec_probe.json > $R/browser_codec_table.md
# Electron GN args and release assets
for t in v35.7.5 v45.2.3; do gh api "repos/electron/electron/contents/build/args/all.gn?ref=$t" -H "Accept: application/vnd.github.raw" | grep -n -E "proprietary_codecs|ffmpeg_branding"; gh api "repos/electron/electron/releases/tags/$t" --jq '.assets[].name' | grep -E "^ffmpeg-.*win32-x64"; done
# Electron docs royalty grep (revise_no_statement_greps.txt)
for f in docs/faq.md docs/tutorial/application-distribution.md docs/tutorial/mac-app-store-submission-guide.md; do gh api "repos/electron/electron/contents/$f?ref=v45.2.3" -H "Accept: application/vnd.github.raw" | grep -ciE "royalt|proprietary|h\.264|h264|patent|codec"; done
# FFmpeg source licence headers (full list in ffmpeg_source_excerpts.txt)
gh api "repos/FFmpeg/FFmpeg/contents/libavcodec/ffv1enc.c?ref=n8.1.2" -H "Accept: application/vnd.github.raw" | sed -n '9,11p'
# Corpus JPEG process audit (read-only)
python $S/jpeg_process_audit.py --corpus C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus --out $R/jpeg_process_audit.json
# IETF IPR disclosures (JSON API; the HTML search page returns 403)
python $S/ietf_ipr_query.py --out $R/ietf_ipr_disclosures.json rfc9043 draft-ietf-cellar-ffv1 draft-ietf-cellar-ffv1-v4 rfc9559 draft-ietf-cellar-matroska rfc9639 draft-ietf-cellar-flac rfc6716 draft-ietf-codec-opus rfc8251 rfc7845
# Primary sources: download + verbatim quote check (pypdf 5.4.0 via PEP 723)
(cd $S && uv run --script fetch_sources.py fetch --sources sources.json --cache $TMP/sources_cache)
(cd $S && uv run --script fetch_sources.py verify --quotes quotes.json --cache $TMP/sources_cache --out ../../results/licensing/quote_verification.json)
# Revise-step quotes N1-N3 and the SVT-AV1 patent disclaimer (grep on the cache)
grep -o "it is your sole responsibility[^.]*" $TMP/sources_cache/nvidia_video_codec_sdk_license.txt
grep -o "Section 1 - Codec Manufacture and Sales.\{0,140\}" $TMP/sources_cache/via_la_avc.txt; grep -o "Available to one legal entity in an affiliated group\|\$9.75M per year in 2017 and after" $TMP/sources_cache/via_la_avc.txt
grep -o "Standard Rate Compliant Rate" $TMP/sources_cache/sisvel_vp9.txt
grep -o "NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY THIS LICENSE" $TMP/sources_cache/svtav1_license.txt
```

PowerShell, read-only: `Get-AppxPackage | Where-Object Name -match 'HEVC|AV1|VP9|MPEG2|RawImage|WebpImage|HEIF' | Select-Object Name, Version`; `(Get-Item "C:/Program Files/Google/Chrome/Application/chrome.exe").VersionInfo`; `Get-PnpDevice -Class Display`.

nvidia-smi `encoder.stats.sessionCount, utilization.gpu` before and after the GPU-touching probes: sessionCount 0 in every sample, utilization 0-11 % in the original runs (`nvsmi_pyav18.txt`, `nvsmi_pyav19.txt`, `nvsmi_opencv.txt`, `nvsmi_browser_probes.txt`), 7-8 % in the verifier run (`verify_method_nvsmi.txt`) and 2-18 % in the revise-step runs (`revise_nvsmi.txt`). Other agents were running; no timing was recorded.

Third-party downloads (temp only, via uv into `$TMP/uv-cache`): PyPI av 19.0.2, opencv-python 5.0.0.93, opencv-contrib-python 4.12.0.88, numpy 2.3.4 and 2.2.6, pypdf 5.4.0. Primary-source pages are cached in `$TMP/sources_cache` (URLs and sha256 in `source_fetch_log.json`). Revise-step media (synthetic gray clips only) are under `$M/revise_*`.

## 7. Verification

Both verifier reports (`VERIFY_provenance.md`, `VERIFY_method.md`) checked `NOTES.md` and the result files, because FINDINGS.md did not yet exist. Each refutation and weak point was re-checked in the revise step against the evidence before being applied.

### 7.1 What was challenged and what changed

| Challenge | Revise-step check | Outcome |
|---|---|---|
| R1: "CAP_MSMF ignores the FOURCC and always writes H.264" | Read cap_msmf.cpp@4.12.0:2496-2553 with `gh api`; re-ran the MSMF FOURCC check with opencv-contrib-python 4.12.0.88 in a uv env (`revise_msmf_fourcc_4.12.0.88_uv.json`) | **Refutation confirmed.** `HEVC` writes hevc, `WMV3` writes wmv3; only unmapped FOURCCs fall back to H.264. 2.6 rewritten |
| FINDINGS: "cv2 + CAP_MSMF ... is today's skellycam path" (not in NOTES, not checked by verifiers) | Read skellycam code at 55f851e4: no apiPreference is passed. New check `cv2_default_backend_check.py` | **Corrected.** skellycam does not request MSMF; OpenCV selects MSMF for `X264`/`H264`/`avc1` .mp4 and writes h264 in both versions (`revise_cv2_default_backend_*.json`). Conclusion (patent-pool codec) holds, mechanism changed |
| HuffYUV "dead URL" | `source_fetch_log.json`: HTTP 200, 346,182 bytes, 14 text chars | **Confirmed, corrected** |
| "All 59 quotes below" count | FINDINGS already says 59 of 59 checked; Q46, Q56 and Q58 are now cited, Q06 is not | No longer applies |
| Sisvel rate columns (AV1, VP9) | grep of cached pages: "Standard Rate Compliant Rate" precedes both tables | **Applied** |
| Via LA AVC context | grep of `via_la_avc.txt`: Section 1 PC category, "*Available to one legal entity...", "$9.75M per year in 2017 and after" | **Applied** (N2) |
| Opus 2 of 5 disclosures rejected | Already in FINDINGS | Kept, table 3.3 updated |
| Wrong quote ids (VP8 Q15, EC Q09) | FINDINGS already cites S2/S3 | No change needed |
| SVT-AV1 "+ AOM patent licence" from Q42 (W1) | grep: the SVT-AV1 LICENSE.md says no patent rights are granted by it | **Applied**: disclaimer added; AV1 patent grant cited via Q01 + Q58 |
| NVIDIA "passes responsibility" (Q48/Q49) | grep: "sole responsibility" sentence present in the SDK licence cache | **Applied** as N1 |
| Inference labelled measured (MSMF, Cisco link, clean-install remark) | Re-read FINDINGS | MSMF split into code/measured/inferred; clean-install remark labelled [inferred]; FINDINGS had no Cisco-link claim |
| Licence texts not at pinned tags | Confirmed from `source_fetch_log.json` URLs | Listed in full in section 5; not re-fetched |
| Q19/Q20 and Q56 treated as primary | Q19/Q20 are a journal history article; Q56 a personal page | Relabelled [secondary] |
| T.81 is a W3C mirror | `source_fetch_log.json` URL is w3.org | Stated |
| Chrome version not recorded | chrome.exe FileVersion 156.0.8078.80 (`revise_env_check.txt`) | Added, with the caveat that it was read after the probe |
| Missing evidence for "searched, no statement" (Electron docs, jpeg.org) | Saved `revise_no_statement_greps.txt` (0 matching lines each) | **Applied** |
| Strip test had no control | New 19.0.2 run with control and single-DLL variants (`revise_pyav_strip_gpl_control_19.0.2.json`) | Conclusion holds on PyAV 19.0.2 |
| W2: HEVC playback attributed to the build flag | Probe JSONs: HEVC `prefer-software` false, `prefer-hardware` true in all three | **Applied** as [inferred] hardware dependence |
| W3: WebCodecs "encode true" | `probe.html:78` calls `isConfigSupported` only | Relabelled as a capability query |
| W4/W5: decode criterion and clip scope | `probe.html:49`; `make_codec_samples.sh` (320x240, 2 s, yuv420p) | Criterion and scope stated in 2.8 |
| W6: G1 "only the patent-free process" in general | Corpus `index.json`: C930e, C922, one generic camera | Scoped to the corpus cameras |
| W7: OpenCV packages differ | Confirmed | Package names stated; DLL identity NOT VERIFIED |
| W8: OpenH264 failure cause | Result JSONs hold both stderr lines | Both quoted; cause in 4.12.0 left open |
| W9: Q25 not verbatim | `quote_verification.json` Q25 | Exact text now quoted |
| W11: JPEG XL format-level statement | Q21 describes software | Reworded; format-level NOT VERIFIED |
| PyAV 18.0.0 / venv evidence used as primary | Task rule: PyAV 19.0.2 only | 18.0.0 and venv OpenCV 4.12.0 results relabelled [background]; 19.0.2 / uv-env results made primary |
| QSV "failed" (10:55) vs iGPU now present | `revise_qsv_open_19.0.2.json` + `revise_env_check.txt` | h264/hevc/vp9/mjpeg_qsv now open; av1_qsv does not. G6/G7 implication revised: VP9 via QSV is the one royalty-free-licensed GPU encoder found |

### 7.2 What remains NOT VERIFIED

- Everything listed in section 5, in particular: ISO/ITU-T patent declarations; full pool agreements; the EC notice; the Google-MPEG LA VP8 agreement; MJPEG, AVI, NUT, PCM/WAV, UT Video, MagicYUV, HuffYUV, ProRes and DNxHD status; MF, VideoToolbox and Electron royalty positions.
- Licence texts at the exact tags the wheels build (x264, x265, SVT-AV1, dav1d, libvpx, UT Video, opencv-python README).
- The pyav-ffmpeg 8.1.2-1 patch (background version only).
- Whether vp9_qsv output decodes correctly and whether QSV ran on the iGPU; the cause of the 10:55 QSV failures.
- HEVC playback on machines without HEVC hardware decode; browser playback of all-intra, 4:2:2, 1080p or PyAV-produced streams.
- Whether opencv-contrib-python and opencv-python share the same videoio FFmpeg DLL.
- The exact Chrome build used by the 11:04 probe (FileVersion was read later).
