# Licensing: provenance verification

Verifier: adversarial provenance pass, 2026-11-09, machine Gerald. No timed benchmarks were run.

## Scope and what was found

- `results/licensing/FINDINGS.md`, `BENCH.md` and `bench/*.json` did **not exist** when this check ran (checked 11:30 to 11:46 EST). NOTES.md section 6 says there is no `bench/` because the topic has no timing work. `quote_verification_supplement.txt` says it was written "during FINDINGS merge", so FINDINGS.md was probably still being written. **This report checks NOTES.md and every result file and script it cites.** Any FINDINGS.md written later needs its own check.
- Method: re-ran the quote check on the cached page text, re-fetched 6 live pages, re-read the cited code lines with `gh api` at the cited tags, opened every cited JSON/TXT result and compared the numbers, and re-ran one functional test with a control added (GPL DLL strip test). Verifier scratch files are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/licensing_verify/`.

## 1. Checks that passed

| Claim area | Check | Result |
|---|---|---|
| 59 quotes "found verbatim" | Re-ran the `norm()` + substring check from `fetch_sources.py` on `$TMP/licensing/sources_cache/*.txt` | 59/59 found again |
| Live pages still say it | Re-fetched with curl on 2026-11-09: Sisvel AV1, Via LA AVC, Via LA AAC, OpenH264 BINARY_LICENSE, AOM patent licence, Apple 118584 | All key strings present (EUR 0.32/0.24, $0.20 tier, $0.98, "separately downloaded...", "no-charge, royalty-free, irrevocable", "such as the FFmpeg and derivative implementations") |
| T.81 Annex L (Q17, Q18, "one hierarchical-lossless patent") | Read the context in `itu_t81_pdf.txt` | Correct: 10 arithmetic-coding patents, then US 4,665,436 for "hierarchical processes ... with a lossless final frame", then the "No other patents" sentence |
| AOM press release / EC review | `aom_ec_press.txt` | "European Commission has today closed its preliminary review of AOMedia's royalty-free licensing policy without further action" is present |
| SVT-AV1 patent licence, libvpx BSD + PATENTS, dav1d BSD-2 | Read the cached text | svtav1 PATENTS = AOM Patent License 1.0; libvpx LICENSE = BSD and PATENTS = same text as Q12; dav1d COPYING has exactly 2 conditions |
| NVIDIA codec patent disclaimer | Context of Q49 | Correct. The same page also says "it is your sole responsibility to obtain any additional third-party licenses ... relating to audio and/or video encoders and decoders" (supports section 3, but is not cited) |
| FFmpeg code citations | `gh api` raw at n8.1.2 | ffv1enc.c:9-11, utvideoenc.c:8-10, magicyuvenc.c:8-10, huffyuvenc.c:10-12, dnxhdenc.c:12-14 are all LGPL-2.1+. configure:1988 `EXTERNAL_LIBRARY_GPL_LIST=`, 1997/1998 libx264/libx265, 4767 `die_license_disabled gpl`. LICENSE.md lines 84-98 match at n8.1.2 **and** n9.0.2 |
| PyAV `--ffmpeg-dir=` | setup.py@v19.0.2 line 126 | Matches |
| Electron GN args | all.gn@v35.7.5 lines 17-18, @v45.2.3 lines 40-41; release.gn lines 5-8 | Match |
| Electron docs silent on codec royalties | Grepped docs/faq.md, tutorial/application-distribution.md, tutorial/mac-app-store-submission-guide.md @v45.2.3 for royalt/proprietary/h.264/codec/patent | 0 hits (files exist: 7,364 / 4,359 / 13,923 bytes). Confirmed, but the topic saved no evidence file for it |
| pyav-ffmpeg 8.1.2-1 not visible | `gh api .../releases/tags/8.1.2-1` and tag refs | 404; tags stop at 8.1.1-2. PyAV v18.0.0 `scripts/ffmpeg-latest.json` points to 8.1.2-1. Matches |
| opencv `LICENSE-3RD-PARTY.txt:243` | Read the venv file | "FFmpeg is redistributed within all opencv-python packages." LGPL text follows from line 250 |
| PyAV probes | `probe_pyav_18.0.0.json`, `probe_pyav_19.0.2.json` | 7/7 libraries report "LGPL version 3 or later". `has_enable_gpl` false, `has_enable_nonfree` false, x264/x265 enabled. libx264 + libx265 DLLs present. Licence files: only AUTHORS.py, AUTHORS.rst, LICENSE.txt. Encoder open/fail list matches section 2 exactly (incl. av1_nvenc ExternalError, *_qsv/*_amf fail, h264_mf/hevc_mf ExternalError, av1_mf ENOSYS) |
| GPL DLLs cannot be deleted | `pyav_strip_gpl_*.json` + verifier control run (PyAV 18.0.0) | Survives. The original script had **no control**, so I added one: an unmodified copy imports OK; removing only x264 or only x265 gives the same `DLL load failed` |
| OpenCV probes | `probe_opencv_*.json`, `opencv_openh264_check_*.json` | Configure flags, avcodec versions, OpenH264 DLL names, CAP_FFMPEG AV1/VP8/VP9/FFV1/MJPEG/HuffYUV read-back of 10 frames, HEVC 0 frames, and MSMF avc1/H264/hev1/av01/mp4v giving `h264` all match |
| Corpus JPEG audit | `jpeg_process_audit.json` + script | 891+893+19+19+19+10+11 = 1,862 frames, all SOF0, DHT 1,862, DAC 0. Script walks markers up to SOS. Sound |
| IETF IPR counts | `ietf_ipr_disclosures.json` + script | 0 for every FFV1 / Matroska / FLAC name. The query method works (finds 5 for rfc6716 and 11 for the Opus draft). RAND-with-royalty holders are France Telecom, Ericsson, Qualcomm and Huawei, as stated |
| Browser table | Raw JSON vs `browser_codec_table.md` | Chromium 134.0.6998.205 / 156.0.8078.80 from `process.versions`. JXL `<img>` error in 35.7.5, load in 45.2.3. HEVC mp4 `decoded_frame_ok: true` in all three |
| Appx extensions, nvidia-smi | `appx_codec_extensions.txt`, `nvsmi_*.txt` | Versions match. All sessionCount 0, utilization 0-11 % |

## 2. Refuted (wording contradicts its own evidence)

| Claim (NOTES.md) | Evidence | Correction |
|---|---|---|
| HuffYUV: "The original HuffYUV licence page could not be fetched (dead URL)" | `source_fetch_log.json` huffyuv_home: HTTP **200**, 346,182 bytes, only 14 characters of text extracted. `huffyuv_home.txt/.raw` are missing from the cache (73 of the 74 sources are cached) | "The page returned HTTP 200, but no licence text could be extracted (14 characters). The cached copy was not kept. NOT VERIFIED." |
| "All 59 quoted passages below were re-checked" | Q06, Q46, Q56 and Q58 are verified in `quote_verification.json` but do not appear in NOTES.md | "55 quotes are cited below. All 59 in quotes.json were checked." Alternatively, cite the other 4 |

## 3. Weak (true but imprecise, mislabelled or citing the wrong thing)

- **Sisvel AV1 rates.** "EUR 0.32 / 0.24 per display device" hides what the two numbers are. The page has a "Standard Rate" column (0.32) and a "Compliant Rate" column (0.24), and non-display devices are 0.11 / 0.08 (supplement S1). Fix: name both columns.
- **Via LA AVC fees (Q29).** The quoted tier is "Section 1 - Codec Manufacture and Sales: Products sold to End Users and OEMs for PCs (except for products that are part of a personal computer's operating system)". The $0.00 tier is "*Available to one legal entity in an affiliated group", and there is an enterprise cap ($9.75M per year from 2017). NOTES gives none of this context. Fix: name the product category and add the cap and the footnote.
- **Opus "5 disclosures on RFC 6716".** 2 of the 5 (Microsoft ids 2486 and 2487) have state `rejected`. Fix: "5 (3 posted, 2 rejected)".
- **Wrong quote ids.** VP8 "Google-MPEG LA agreement covering VP8 (Q15)": Q15 does not mention VP8; supplement S2 does. EC review "(Q09)": Q09 stops at "has today"; S3 holds the claim. libsvtav1 "+ AOM patent licence, Q42": Q42 is the BSD text only, and the patent licence is the uncited `svtav1_patent` source. libvpx "BSD + Google patent grant" has no citation. Fix: cite S2/S3 and add quote ids for svtav1_patent, libvpx_license and libvpx_patents.
- **NVENC "explicitly passes codec-patent responsibility to the developer (Q48, Q49)".** Q48/Q49 only say NVIDIA grants no codec patent rights. The sentence that supports "passes responsibility" ("it is your sole responsibility to obtain any additional third-party licenses ...") is on the same page but not quoted. Fix: add it as a quote.
- **Inference labelled as measured.** In section 2, "[measured] CAP_MSMF ... skellycam's current cv2→MSMF path therefore always produces a patent-pool codec, whatever FOURCC is requested" adds an inference to a measurement. Only 5 FOURCCs were tested, all in .mp4, and the mkv/avi/webm MSMF writers failed to open. "[measured] ... This matches Cisco's 'separately downloaded' condition (Q36)" has the same problem. Fix: split into a [measured] bullet and an [inferred] bullet, and say "for the 5 FOURCCs tested in .mp4".
- **Unlabelled inference.** In the Windows MF row, "MF results here may therefore differ from a clean Windows install" has no label. Fix: label it [inferred].
- **Licence texts not at pinned versions.** Fetched from branches, not tags: x264 `master`, x265 `master` (both acknowledged in section 6), SVT-AV1 LICENSE `master`, dav1d COPYING `master`, utvideo README `master`, and opencv-python README `4.x` (also used to describe the 5.0.0.93 wheel). The evidence rule asks for a pinned version or tag. Fix: re-fetch at the tags the wheels build, or list all of them in section 6.
- **Q19/Q20 (ITU Journal 2020) are secondary.** This is a historical journal article, and Q20 is explicitly an "Author's note". It is not a standards-body patent statement. NOTES labels Q20 as an author's note but still marks both as [source]. Fix: mark them as a secondary account, and rely on T.81 Annex L (Q17/Q18) as the primary source.
- **T.81 is a W3C copy.** It is hosted at w3.org, not itu.int (sha256 is recorded). The text matches the Rec, but it is a mirror. Fix: say so.
- **Chrome version.** "Chrome 156": the probe records only a reduced UA (`156.0.0.0`), so the exact build is not recorded. Fix: record `chrome.exe` file version.
- **Missing evidence files.** The Electron-docs "searched, no statement" result and the jpeg.org "0 hits" result have no saved grep output (the verifier reproduced both). Fix: save the grep output under results/licensing/.
- **Strip test had no control.** The conclusion survives (verifier control above), but `pyav_strip_gpl_test.py` should import an unmodified copy first so the result can stand on its own.

## 4. Verdict

NOTES.md holds up well on provenance. Every number and quote I sampled matches its result file or source. All code line citations are exact. The two key functional claims hold up: the GPL x264/x265 DLLs are required for `import av`, and MSMF writes H.264 for every FOURCC tested. There are 2 small factual misstatements (HuffYUV "dead URL", the "59 quotes below" count) and about 12 precision or labelling fixes. Nothing changes the conclusions. **FINDINGS.md was absent and has not been verified.**
