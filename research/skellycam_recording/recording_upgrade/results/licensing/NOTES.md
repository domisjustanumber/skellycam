# Licensing (G7): codec, container and library licence status

Study: skellycam recording upgrade, topic `licensing`. Machine Gerald (Windows 11, i7-14700K, RTX 3070). Date 2026-11-09.
No timing work in this topic. This is not legal advice. It reports what the licence texts and licensors say, plus functional tests.

Labels: **[measured]** = result file from this study, **[source]** = primary source quoted verbatim, **[code]** = repo or library source file:line, **[inferred]** = reasoning (kept short), **NOT VERIFIED** = no primary source found.

All 59 quoted passages below were re-checked by script against the downloaded page text: `results/licensing/quote_verification.json` reports 59/59 found verbatim. The URL, HTTP status, sha256 and fetch time of every page are in `results/licensing/source_fetch_log.json`. All pages were accessed on 2026-11-09.

## 1. Summary table

"Status (quoted)" is the licensor's or standard body's own wording. Qn is the quote id in `quote_verification.json`.

### Video codecs

| Format | Royalty / licence status (quoted) | Source | Caveats |
|---|---|---|---|
| AV1 | AOM Patent License 1.0: "no-charge, royalty-free, irrevocable (except as expressly stated in this License) patent license to its Necessary Claims to make, use, sell, offer for sale, import or distribute any Implementation." (Q01) | https://aomedia.org/license/patent-license/ | The grant covers only AOM licensors' claims. It ends for anyone who sues over AV1 patents ("immediately terminated", Q03). Distributing an Implementation means reproducing the licence (Q02). Sisvel runs a separate **royalty-bearing** AV1 pool for consumer products (Q04, Q05; rates EUR 0.32 / 0.24 per display device). Avanci Video (Q10) and Access Advance VDP (Q11) offer AV1 licences to streaming providers. These are those parties' claims, reported without judgement. AOM says the European Commission closed its preliminary review of the AOM policy (Q09). The Commission's own notice was NOT VERIFIED. |
| VP9 | Google (libvpx): "perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable (except as stated in this section) patent license ... of these implementations of WebM" (Q12) | https://www.webmproject.org/license/additional/ ; libvpx PATENTS (same text) | The grant covers Google's own implementations only. It "does not include claims that would be infringed only as a consequence of further modification" (Q13). Sisvel VP9 pool: "royalty-bearing" (Q07), with rates for display / non-display devices (Q08). Avanci Video and Access Advance VDP also list VP9 (Q10, Q11). |
| VP8 | WebM cross-licence: "helps create a royalty-free ecosystem for VP8" (Q14) | https://www.webmproject.org/cross-license/ | Sisvel's VP9 page mentions a Google-MPEG LA agreement covering VP8 (Q15). That agreement was not fetched: NOT VERIFIED. |
| FFV1 | RFC 9043. IETF Datatracker lists **0** IPR disclosures for rfc9043, draft-ietf-cellar-ffv1 and draft-ietf-cellar-ffv1-v4 [measured: `ietf_ipr_disclosures.json`]. The RFC says CABAC was dropped "due to the uncertain patent/royalty situation" (Q16). | https://www.rfc-editor.org/rfc/rfc9043.txt ; Datatracker API | Having no IETF disclosure does not mean no patents exist. No royalty-free declaration found. FFmpeg's ffv1enc.c is LGPL-2.1+ [code: FFmpeg n8.1.2 libavcodec/ffv1enc.c:9-11]. Chromium/Electron cannot play it (section 4). |
| JPEG baseline (SOF0 Huffman) | T.81 Annex L lists patents only for "processes ... which uses arithmetic coding" (Q17), plus one hierarchical-lossless patent. "No other patents required for implementation of any of the other processes ... had been identified at the time of publication" (Q18). ITU Journal 2020 history: "de facto the baseline mode of JPEG remained RF" (Q19) and "All JPEG-1 patents have now expired" (Q20, labelled an author's note). | T.81 text (W3C copy) https://www.w3.org/Graphics/JPEG/itu-t81.pdf ; https://itu.int/dms_pub/itu-s/opb/journal/S-JOURNAL-ICTS.V3I1-2020-13-PDF-E.pdf | jpeg.org/jpeg has no royalty statement (searched, 0 hits). The ISO and ITU patent databases could not be queried (HTTP 403 / search form only): NOT VERIFIED. All 1,862 corpus frames are SOF0 baseline Huffman with DHT and no DAC [measured: `jpeg_process_audit.json`]. So G1 passthrough stores only the Annex-L-free process. |
| Motion JPEG | There is no single MJPEG spec. Each container defines its own carriage (AVI, QuickTime/MP4, Matroska). | — | [inferred] The royalty status equals that of the JPEG process inside (baseline above) plus the container's status. No primary source covers "MJPEG" as a whole: NOT VERIFIED. |
| JPEG XL | jpeg.org: Part 4 "Provides a free and open source, royalty-free JPEG XL reference implementation" (Q21). libjxl PATENTS: Google's "no-charge, royalty-free" grant for "this implementation of JPEG XL" (Q22) | https://jpeg.org/jpegxl/index.html ; https://raw.githubusercontent.com/libjxl/libjxl/v0.11.1/PATENTS | No ISO/IEC 18181 patent declarations were obtained (ISO database: HTTP 403): NOT VERIFIED. The libjxl grant covers Google's implementation, with the same modification carve-out as WebM. libjxl is not in the PyAV 18/19 wheels [measured]. |
| JPEG 2000 Part 1 | "has a royalty-free objective" (Q23). HTJ2K Part 15: "intended to be royalty-free" (Q24) | https://jpeg.org/jpeg2000/index.html | An "objective" is not a licence. Patent declarations: NOT VERIFIED. No browser decodes .jp2 (section 4). |
| UT Video | Original codec: "licensed under ... GNU GPL version 2 or later" (Q25) | https://github.com/umezawatakeshi/utvideo README.md | Patent status: NOT VERIFIED (no statement found). FFmpeg's utvideoenc.c is its own LGPL-2.1+ implementation [code: FFmpeg n8.1.2 libavcodec/utvideoenc.c:8-10]. |
| MagicYUV | Commercial product: "We offer MagicYUV at a low price to be accessible to everyone" (Q26) | https://www.magicyuv.com/ | No format or patent licence statement found: NOT VERIFIED. FFmpeg magicyuvenc.c is LGPL-2.1+ [code: n8.1.2 libavcodec/magicyuvenc.c:8-10]. |
| HuffYUV / FFVHuff | FFmpeg huffyuvenc.c (also implements ffvhuff) is LGPL-2.1+ [code: n8.1.2 libavcodec/huffyuvenc.c:10-12] | FFmpeg source | The original HuffYUV licence page could not be fetched (dead URL): NOT VERIFIED. Patent status: NOT VERIFIED. |
| ProRes | Apple: "Apple also licenses and certifies ProRes ... for specific third-party products" (Q27). Unauthorized implementations "(such as the FFmpeg and derivative implementations) might lead to decoding errors ..." (Q28) | https://support.apple.com/en-us/118584 ; Apple ProRes white paper PDF | prores_ks in PyAV is an FFmpeg implementation, so not Apple-authorized under Apple's wording. Royalty terms are not public: NOT VERIFIED. |
| DNxHD / DNxHR (SMPTE VC-3) | NOT VERIFIED | avid.com product page returns 404; SMPTE ST 2019 page returns 404 | Only secondary sources were found (not used). FFmpeg dnxhdenc.c is LGPL-2.1+ [code: n8.1.2 libavcodec/dnxhdenc.c:12-14]. |
| H.264 / AVC | Via LA AVC fees: "For the first 1 to 100,000 units $0.00* For units 100,001 to 5,000,000 $ 0.20 ea. ..." (Q29). "The actual License agreement provides the only definitive and reliable statement of license terms." (Q30) | https://www.via-la.com/licensing-programs/avc-h-264/ | Royalty-bearing above the threshold. No free-software or open-source term found on the page: NOT VERIFIED. Cisco OpenH264: Cisco pays only for **its binary** when that binary is "separately downloaded to an end user's device, and not integrated into or combined with third party software" (Q35, Q36). The covered use is personal/non-remunerated (Q37). "Cisco is providing no such guarantee" for other patent holders (Q38). |
| HEVC / H.265 | Via LA (now Access Advance) HEVC/VVC: "For the first 1 to 100,000 units $0.00* For units 100,001 and more $ 0.30 ea. ..." (Q31). Programme acquired by Access Advance on 2025-12-15 (Q32). HEVC Advance licenses "HEVC Decoders and HEVC Encoders ... whether made available in devices, software, or through Cloud Based Services" (Q33) and seeks "one royalty per device/software copy on First Sale" (Q34). | https://www.via-la.com/licensing-programs/hevc-vvc/ ; https://accessadvance.com/topic-what-do-we-license/ ; HEVC Advance Program Overview PDF | At least two pools (plus Avanci Video and VDP for streaming). No free-software or below-threshold term found on the Access Advance pages: NOT VERIFIED. |

### Containers

| Format | Status | Source | Caveats |
|---|---|---|---|
| Matroska / WebM | RFC 9559. **0** IETF IPR disclosures for rfc9559 / draft-ietf-cellar-matroska [measured: `ietf_ipr_disclosures.json`]. The WebM cross-licence page names "Google, Matroska and the Xiph.Org Foundation" as making WebM components available "on royalty- free terms" (Q59) | https://www.rfc-editor.org/rfc/rfc9559.txt | Having no disclosure does not mean no patents exist. |
| ISO BMFF / MP4 (ISO/IEC 14496-12/14) | ISO now offers its former "Publicly Available Standards" "at no charge on the ISO and IEC webstores" (Q55) | https://standards.iso.org/ittf/PubliclyAvailableStandards/ | Whether 14496-12 is in that set, and its patent declarations, could not be checked (iso.org returned 403): NOT VERIFIED. |
| AVI (RIFF) | Microsoft documents it (learn.microsoft.com AVI RIFF reference). The page has no licence or royalty statement. | https://learn.microsoft.com/en-us/windows/win32/directshow/avi-riff-file-reference | Royalty status NOT VERIFIED. |
| NUT | NOT VERIFIED | ffmpeg.org/~michael/nut.txt returned a 100-byte stub | — |

### Audio (if audio is recorded)

| Format | Status | Source | Caveats |
|---|---|---|---|
| Opus (RFC 6716) | "protective, royalty-free licenses for the required patents" (Q53) | https://opus-codec.org/license/ | Datatracker lists 5 disclosures on RFC 6716 and 11 on the draft. France Telecom, Ericsson, Qualcomm and Huawei declared "Reasonable and Non-Discriminatory License to All Implementers with Possible Royalty/Fee" [measured: `ietf_ipr_disclosures.json`]. |
| FLAC (RFC 9639) | Xiph: "is non-proprietary, is unencumbered by patents" (Q54) | https://xiph.org/flac/ | 0 IETF IPR disclosures for rfc9639 / draft-ietf-cellar-flac [measured]. |
| PCM / WAV | NOT VERIFIED (no primary statement fetched) | — | — |
| AAC | Via LA AAC: "For the first 1 to 500,000 units $0.98 ..." (Q57) | https://www.via-la.com/licensing-programs/aac/ | Royalty-bearing from the first unit, by Via LA's table. |

### Platform encoders and SDKs

| Item | Status | Source |
|---|---|---|
| NVIDIA NVENC / Video Codec SDK | "NVIDIA does not grant to you under this license any necessary patent or other rights with respect to any audio and/or video encoders and decoders." (Q49) | https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/license/index.html |
| NVIDIA nvJPEG (CUDA Toolkit) | nvjpeg.dll is listed as a CUDA redistributable component (Q50). The EULA has the same codec-patent disclaimer (Q48). | https://docs.nvidia.com/cuda/eula/index.html |
| NVIDIA nvImageCodec | Binary redistribution is allowed "as incorporated into a software application" with "material additional functionality" (Q51). "You may not use the Software in any manner that would cause it to become subject to an open source software license" (Q52). | https://docs.nvidia.com/cuda/nvimagecodec/license.html |
| Windows Media Foundation H.264/HEVC encoders | Microsoft's encoder pages have no royalty statement. Who bears codec royalties: NOT VERIFIED. This machine has Microsoft.HEVCVideoExtension 2.5.48.0, AV1VideoExtension 2.0.35.0 and VP9VideoExtensions 1.2.20.0 installed [measured: `Get-AppxPackage`, read-only]. MF results here may therefore differ from a clean Windows install. | https://learn.microsoft.com/en-us/windows/win32/medfound/h-264-video-encoder |
| Apple VideoToolbox | NOT VERIFIED (developer.apple.com page is JavaScript-rendered; no licence text obtained) | — |
| Electron / Chromium | Electron builds with `ffmpeg_branding = "Chrome"` and `proprietary_codecs = true` at v35.7.5 and v45.2.3 [source: electron/electron build/args/all.gn lines 17-18 at v35.7.5, 40-41 at v45.2.3]. release.gn: "By default, Electron builds ffmpeg with proprietary codecs enabled. In order to facilitate users who don't want to ship proprietary codecs in ffmpeg, or who have an LGPL requirement to ship ffmpeg as a dynamically linked library, we build ffmpeg as a shared library." [source: build/args/release.gn at both tags]. Each release ships separate `ffmpeg-vX-<platform>.zip` assets (e.g. ffmpeg-v35.7.5-win32-x64.zip) [source: GitHub release v35.7.5 asset list]. | Who bears H.264/HEVC/AAC royalties for Electron apps: NOT VERIFIED (no statement in Electron docs at v45.2.3: faq.md, application-distribution.md, mac-app-store-submission-guide.md searched). |

## 2. Python distribution: what the PyAV and OpenCV wheels actually contain

### PyAV wheels bundle GPL x264/x265 while FFmpeg reports LGPL

- [measured] PyAV 18.0.0 (skellycam venv) bundles FFmpeg 8.1.2. All seven libraries report licence `"LGPL version 3 or later"`. The configure line has `--enable-libx264 --enable-libx265 --enable-version3` and **no** `--enable-gpl` or `--enable-nonfree`. Files: `probe_pyav_18.0.0.json`.
- [measured] PyAV 19.0.2 (isolated uv env) bundles FFmpeg 9.0.2 with the same licence string and flags. It adds `--enable-libvmaf` and drops opencore-amr. Files: `probe_pyav_19.0.2.json`.
- [measured] Both wheels ship `libx264-165-*.dll` and `libx265-*.dll` in `av.libs`. The only licence files in the wheel are PyAV's own `LICENSE.txt`, `AUTHORS.py` and `AUTHORS.rst`. No x264, x265 or FFmpeg licence text is included (`wheel_license_files` in both probe JSONs).
- [measured] libx264 and libx265 encode in both versions (8-frame smoke test, `video_encoders` in both probe JSONs).
- [source] Why the reported licence is LGPL: pyav-ffmpeg `patches/ffmpeg.patch` deletes `libx264` and `libx265` from `EXTERNAL_LIBRARY_GPL_LIST` and adds them to `EXTERNAL_LIBRARY_VERSION3_LIST`. Seen at pyav-ffmpeg tags 8.1.1-2 (commit b84838a0) and 9.0.2-1 (commit bac88941). The patch was introduced in commit dc9ee64dff (2025-06-27), message `GPLv3 OR "LGPLv3 + Exceptions"`. Evidence in `pyav_build_evidence.json`. PyAV v18.0.0 pulls pyav-ffmpeg release 8.1.2-1 and v19.0.2 pulls 9.0.2-1 (`scripts/ffmpeg-latest.json`, used by `CIBW_BEFORE_BUILD_WINDOWS` in `.github/workflows/tests.yml`). The 8.1.2-1 tag/release is not visible via the GitHub API, so its patch was not read directly. The local binary shows the same result.
- [source] Upstream FFmpeg (LICENSE.md at n8.1.2 and n9.0.2, lines 84-98): "The following libraries are under GPL version 2: ... libx264 libx265 ... When combining them with FFmpeg, FFmpeg needs to be licensed as GPL as well by passing `--enable-gpl` to configure." Unpatched configure puts libx264/libx265 in EXTERNAL_LIBRARY_GPL_LIST (configure n8.1.2:1988-1998) and enforces it with `die_license_disabled gpl` (configure:4767).
- [source] x264.h: GPL "version 2 of the License, or (at your option) any later version" (Q39), "also available under a commercial proprietary license" (Q40). x265 COPYING: GPLv2 text plus a commercial-licence note (Q41).
- [source] FFmpeg legal checklist for LGPL compliance: "Make sure your program is not using any GPL libraries (notably libx264)." (Q45). "If those parts get used the GPL applies to all of FFmpeg." (Q44)
- [measured] The GPL DLLs cannot simply be deleted. On a copy of the wheel with `libx264-*.dll` and `libx265-*.dll` removed, `import av` fails with `ImportError: DLL load failed while importing _core` in both 18.0.0 and 19.0.2 (`pyav_strip_gpl_18.0.0.json`, `pyav_strip_gpl_19.0.2.json`).
- [inferred] Shipping skellycam with stock PyAV wheels (for example inside an installer) ships GPL-licensed x264/x265 binaries. The "LGPL" string reported by FFmpeg does not change that. Avoiding it needs a custom FFmpeg/PyAV build without libx264/libx265 (PyAV can build against a given FFmpeg: `--ffmpeg-dir=` option [code: PyAV v19.0.2 setup.py:126]). That build was not attempted here.
- [measured] What else the stock wheels give: libsvtav1 (AV1 encode, BSD-3-Clause-Clear + AOM patent licence, Q42), libdav1d (AV1 decode, BSD-2, Q43), libvpx (VP8/VP9, BSD + Google patent grant), ffv1, mjpeg, utvideo, magicyuv, huffyuv/ffvhuff, prores_ks, rawvideo, png all encode. libaom, librav1e, libjxl and libopenjpeg are absent. FFmpeg's built-in jpeg2000 encoder works.
- [measured] Hardware encoders on this RTX 3070 in both versions: h264_nvenc and hevc_nvenc open. av1_nvenc fails (`ExternalError ... avcodec_open2("av1_nvenc")`). All *_qsv and *_amf encoders fail. h264_mf and hevc_mf fail with default options (`ExternalError`), and av1_mf gives `Function not implemented`. This was a default-option smoke test only. The GPU-encode topic owns the details.

### OpenCV wheels

- [source] opencv-python README: "All wheels ship with FFmpeg licensed under the LGPLv2.1" (Q47). cv2/LICENSE-3RD-PARTY.txt:243 says "FFmpeg is redistributed within all opencv-python packages." and includes the LGPL 2.1 text.
- [measured] opencv-contrib-python 4.12.0.88 has `opencv_videoio_ffmpeg4120_64.dll`, avcodec 58.134.100. opencv-python 5.0.0.93 has `opencv_videoio_ffmpeg500_64.dll`, avcodec 61.19.100. In both, the configure string embedded in the DLL has `--enable-libopenh264 --enable-libvpx --enable-libaom --disable-nvenc` and no `--enable-gpl` (`probe_opencv_4.12.0.json`, `probe_opencv_5.0.0.93.json`).
- [measured] H.264 through CAP_FFMPEG does not work out of the box. OpenCV tries to load a separate Cisco DLL: "Failed to load OpenH264 library: openh264-1.8.0-win64.dll" (4.12) / "openh264-2.5.0-win64.dll" (5.0). The writer then fails to open. This matches Cisco's "separately downloaded" condition (Q36).
- [measured] CAP_FFMPEG writes and reads back AV1 (libaom), VP8, VP9, FFV1, MJPEG and HuffYUV in both versions. HEVC writer "opens" but writes 0 frames.
- [measured] CAP_MSMF ignores the FOURCC and always writes **H.264**. `av01`, `hev1` and `mp4v` requests all produce `h264` (checked with ffprobe; `ffprobe_codec` field). skellycam's current cv2→MSMF path therefore always produces a patent-pool codec, whatever FOURCC is requested.

## 3. Royalty-free options vs goals (inferred, from the table)

- [inferred] G1 JPEG passthrough: baseline Huffman JPEG is the process for which T.81 Annex L lists no patents (Q17, Q18). The corpus is 100% SOF0 (measured). Writing these bytes needs no encoder at all.
- [inferred] G4/G7 I-frame-only royalty-free candidates with primary-source royalty-free statements are AV1 (AOM licence, but contested by Sisvel's pool), VP9 (Google grant, also in Sisvel's pool) and JPEG XL (Google grant for libjxl). FFV1 has no IETF disclosures but no positive royalty-free declaration either. UT Video, MagicYUV, HuffYUV, DNxHD and ProRes have no royalty statement (ProRes is controlled by Apple).
- [inferred] H.264/HEVC through NVENC or MF: NVIDIA explicitly passes codec-patent responsibility to the developer (Q48, Q49). Microsoft is silent (NOT VERIFIED).

## 4. Browser (Electron/Chromium) playback, as it bears on licensing (G8)

Test: the same synthetic `testsrc2` clips (no camera content) were opened in a hidden Electron window and in headless Chrome. A clip "plays + decodes" when it reaches `loadeddata`, `currentTime` advances after `play()`, and a seek to 1.0 s draws a non-black frame to canvas. Full table: `browser_codec_table.md`. Raw data: `electron_codec_probe_35.7.5.json`, `electron_codec_probe_45.2.3.json`, `chrome_codec_probe.json`.

| Item | Electron 35.7.5 (Chromium 134.0.6998.205) | Electron 45.2.3 (Chromium 156.0.8078.80) | Chrome 156 headless |
|---|---|---|---|
| H.264 mp4, HEVC mp4, AV1 mp4/webm/mkv, VP9 webm/mp4, VP8 webm | plays + decodes | plays + decodes | plays + decodes |
| MJPEG in mkv / mp4 | error 4 DEMUXER_ERROR_NO_SUPPORTED_STREAMS | same | same |
| MJPEG in avi, UT Video avi | error 4 DEMUXER_ERROR_COULD_NOT_OPEN | same | same |
| FFV1 mkv, ProRes mov | error 4 DEMUXER_ERROR_NO_SUPPORTED_STREAMS | same | same |
| `<img>` JPEG / AVIF / WebP / PNG | load | load | load |
| `<img>` JPEG XL | **error** | **load** | load |
| ImageDecoder image/jxl | false | **true** | true |
| JPEG 2000 (.jp2) | error | error | error |
| canPlayType `video/x-matroska; codecs="av01..."` | '' | 'probably' | 'probably' |
| WebCodecs decode HEVC prefer-software | false | false | false |
| WebCodecs encode avc1.42001f / hvc1 / av01 / vp09 (no-preference) | true / true / true / true | same | same |
| Audio: Opus (webm, mp4), FLAC, AAC, WAV, MP3 | play | play | play |

- [measured] H.264, HEVC and AAC play in Electron. That matches the `proprietary_codecs = true` build flag [source above].
- [measured] Version bump: Electron 45.2.3 adds JPEG XL decoding (`<img>` and ImageDecoder) compared with the pinned 35.7.5, and answers 'probably' to `canPlayType('video/x-matroska; ...')` (35.7.5 answers ''). These are the only differences between the two in this probe. Actual playback of the .mkv AV1 file worked in both.
- [measured] None of the lossless intra codecs (FFV1, UT Video, ProRes) and no MJPEG container play natively in Chromium. JPEG frames do decode as images (`<img>`, ImageDecoder).

## 5. Exact commands (run from repo root unless noted)

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
# OpenCV probes
.venv/Scripts/python.exe $S/probe_opencv_build.py --out $R/probe_opencv_4.12.0.json --tmp $M
uv run --no-project --python 3.12 --with opencv-python==5.0.0.93 python -I $S/probe_opencv_build.py --out $R/probe_opencv_5.0.0.93.json --tmp $M
# Browser probes (unset ELECTRON_RUN_AS_NODE first: it is set in the VS Code terminal and makes electron.exe run as node)
bash $S/make_codec_samples.sh $M/samples
unset ELECTRON_RUN_AS_NODE
skellycam-ui/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_35.7.5.json
$TMP/../shared/electron-latest/node_modules/electron/dist/electron.exe $S/electron_codec_probe --samples=$M/samples --out=$R/electron_codec_probe_45.2.3.json
python $S/run_chrome_probe.py --chrome "C:/Program Files/Google/Chrome/Application/chrome.exe" --samples $M/samples --profile $TMP/chrome-profile3 --out $R/chrome_codec_probe.json
python $S/summarize_browser_probe.py $R/electron_codec_probe_35.7.5.json $R/electron_codec_probe_45.2.3.json $R/chrome_codec_probe.json > $R/browser_codec_table.md
# Corpus JPEG process audit (read-only)
python $S/jpeg_process_audit.py --corpus C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus --out $R/jpeg_process_audit.json
# IETF IPR disclosures (JSON API; the HTML search page returns 403)
python $S/ietf_ipr_query.py --out $R/ietf_ipr_disclosures.json rfc9043 draft-ietf-cellar-ffv1 draft-ietf-cellar-ffv1-v4 rfc9559 draft-ietf-cellar-matroska rfc9639 draft-ietf-cellar-flac rfc6716 draft-ietf-codec-opus rfc8251 rfc7845
# Primary sources: download + verbatim quote check (pypdf 5.4.0 via PEP 723)
(cd $S && uv run --script fetch_sources.py fetch --sources sources.json --cache $TMP/sources_cache)
(cd $S && uv run --script fetch_sources.py verify --quotes quotes.json --cache $TMP/sources_cache --out ../../results/licensing/quote_verification.json)
```

Other read-only checks: `Get-AppxPackage | Where-Object Name -match 'HEVC|AV1|VP9|...'` (PowerShell). Electron GN args were read with `gh api repos/electron/electron/contents/build/args/{all,release}.gn?ref=v35.7.5|v45.2.3`. FFmpeg encoder headers were read with `gh api repos/FFmpeg/FFmpeg/contents/libavcodec/<file>?ref=n8.1.2`.

nvidia-smi `encoder.stats.sessionCount, utilization.gpu` before/after the GPU-touching probes: all sessionCount 0, utilization 0-11 % (`nvsmi_pyav18.txt`, `nvsmi_pyav19.txt`, `nvsmi_opencv.txt`, `nvsmi_browser_probes.txt`). One earlier aborted Electron attempt saw `1, 31 %` before start (Parsec/Sunshine or another agent). That run produced no data.

Third-party downloads (temp only): PyPI av 19.0.2, opencv-python 5.0.0.93, numpy 2.3.4, pypdf 5.4.0 (via uv into `$TMP/uv-cache`). Primary-source pages are cached in `$TMP/sources_cache` (URLs and sha256 in `source_fetch_log.json`).

## 6. Limits

- Quotes were extracted from the live pages on 2026-11-09. Licensor pages change. Via LA says only the agreement itself is definitive (Q30). None of the full licence agreements (Via LA, Access Advance, Sisvel, Avanci) were read. Only their public summaries were.
- Patent declaration databases (ISO, ITU-T) could not be queried (HTTP 403 / ASP.NET form). JPEG XL, JPEG 2000, ISO BMFF and VC-3 declarations are therefore NOT VERIFIED.
- Having no IETF disclosures (FFV1, Matroska, FLAC) is evidence only about IETF disclosures.
- x264 and x265 licence texts were read from their `master` branches (code.videolan.org API, bitbucket), not the exact commits PyAV builds (x264 b35605ac, x265 4.3 per the pyav-ffmpeg README at 9.0.2-1).
- Browser tests used tiny synthetic 320x240 clips in a hidden window. They establish codec/container support, not playback performance or frame accuracy (other topics).
- Windows-only machine: the macOS/Linux wheels and VideoToolbox were not tested.
- No timing measurements, so there is no `bench/` folder for this topic.
