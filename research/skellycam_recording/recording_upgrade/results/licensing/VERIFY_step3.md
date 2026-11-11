# VERIFY step 3: licensing (provenance + method)

Verifier: adversarial, 2026-11-10, machine Gerald. Scope: only the new or changed claims in the step 3 draft (GF01, GF03). No tests and no timing were run. Downloaded sources were read as text or zip only (`python -I`).

## 1. Verdict

No claim refuted. 6 weak points: 2 labels, 2 scopes, 2 internal or cross-topic inconsistencies. All are wording fixes.

## 2. What was checked, independently

| Claim (draft section) | Check | Result |
|---|---|---|
| 72/72 GF03 quotes verbatim, accessed 2026-11-10 | `gapfill/GF03_quote_verification.json`: `access_date` 2026-11-10, `n` 72, `n_found` 72; all cited ids (C01, C02, C04, C06, C08, C09, C13, E01, E04, W01-W03, W06, W07, W10, D03, G01, G02, G04, H01, H02, A01-A04, A06) are `found_verbatim: true` | confirmed |
| Live CUDA EULA date, Windows nvjpeg row, C08 file-name clause, C04 OSI clause, C06 ban, C13 consistency (§2.4) | Own grep of `step3/GF03/dl/cuda_eula.html` (tags stripped): each string found once | confirmed |
| Wheel ships `nvjpeg64_12.dll` (§2.4, measured) | Own zip listing of `nvidia_nvjpeg_cu12-12.4.0.76-py3-none-win_amd64.whl`: `nvidia/nvjpeg/bin/nvjpeg64_12.dll`; also in `GF03_wheel_arch_facts.json` | confirmed |
| Wheel's EULA is the 2018 text and lists nvJPEG for Linux only (§2.4) | Own read of the wheel `License.txt`: "Release Date: July 26, 2018" 1 hit; Linux nvjpeg row 1 hit; `nvjpeg.dll` 0 hits, "Windows nvjpeg" 0 hits | confirmed |
| nvimgcodec wheel's only licence file is the SLA (v. November 28, 2023) (§2.4) | Own zip listing: the only licence-like member is `dist-info/licenses/LICENSE.txt`; it contains both strings, 0 "Apache" | confirmed |
| PyPI Apache-2.0, GitHub v0.10.0 Apache-2.0 (§2.4) | `pypi_nvimgcodec_0.10.0.9.json` `info.license` = "Apache License 2.0"; wheel METADATA `License: Apache License 2.0`; `gh_LICENSE_v0.10.0.txt` starts "Apache License / Version 2.0, January 2004" | confirmed |
| SLA §2.11 benchmark clause (§2.4) | `nvimagecodec_license.html` text: the sentence is numbered "2.11" | confirmed |
| Unpinned nvjpeg extra (§2.4) | Wheel METADATA: `Requires-Dist: nvidia-nvjpeg-cu12; extra == "nvjpeg"` (no version) | confirmed |
| AGPL-3.0 OSI-approved (§2.4) | `osi_agpl.html`: "Approved: March 3, 2008" 1 hit | confirmed |
| gnu.org 403; AGPL quotes from SPDX + skellycam LICENSE line ranges (§7.3) | `GF03_fetch_log.json` entry `http: 403`; `LICENSE` lines 111/119, 122/133, 223/231, 281/283, 333/336 start and end the quoted passages | confirmed |
| QSV outputs decode, 32 frames (§2.5, §3.1, §4) | `results/gpu_encode/FINDINGS.md:55` (in §2.2, which starts at line 51): "each of the 26 working outputs decodes to 32 frames ... including vp9_qsv and mjpeg_qsv" | confirmed (scope: see W4) |
| intra_compare 0 failed, frames out = frames in (§2.5) | `results/intra_compare/FINDINGS.md:56-58` | confirmed |
| h264/hevc/mjpeg_qsv load iGPU engines (§2.5) | `results/gpu_encode/FINDINGS.md:217`, item-1 GPU Engine counters from the quiet bench run (not a concurrent run) | confirmed; no timing number copied |
| HEVC no software decode; `<video>` uses D3D11VideoDecoder (§2.8, §3.1, §4) | `results/intra_playback/FINDINGS.md:56` (F9), `:59` (F10) | confirmed (scope: see W3) |
| PyAV 19.0.2 AV1/VP9 all-intra clips play via `<video src>` in E35, E45, C156 (§4) | `results/chromium_codecs/FINDINGS.md:62-66` (C7): SVT-AV1 all-intra mp4/webm/mkv, libvpx-vp9 all-intra webm, build log `g: "1"` | confirmed |
| VP9 fails the hardware target: no NVIDIA, AMD or Apple VP9 encode (§4) | `results/hw_accel_target/FINDINGS.md:373` (§3.3 VP9 row: N NVIDIA, Y Intel except LNL/BMG, N AMD, N Apple, "no") | confirmed |
| §5 browser bullet: frame accuracy, all-intra, 1080p, PyAV clips, decoder type measured later | intra_playback F1 (`:30-32`, 4800/4800 exact `mid` seeks, 720p/1080p), F9, F10; chromium_codecs C5-C7 (C5/C6 labelled background there) | confirmed |
| GF01 pointer; LIC:53 Matroska, LIC:55 ISO BMFF | `GF01_container_decision_table.md:60, 63, 93, 117` cite LIC:53/LIC:55/LIC:174; current FINDINGS lines 53, 55, 174 are those bullets; lines 1-55 keep the same count in the draft | confirmed |
| "now 109", "now 135" (§7.3) | Pre-fold 98 + 3 (§2.4 Q50 split) + 5 (§2.4 adds) + 3 (§2.5 split) = 109; 124 + 11 = 135 | confirmed |
| No "pending tonight's bench" references (§7.3) | grep of current FINDINGS for pending/tonight/bench: only line 4 | confirmed |
| Cited evidence files exist | All listed GF01/GF03 result, NOTES and script files present | confirmed |

## 3. Weak points

| # | Claim | Why weak | Fix |
|---|---|---|---|
| W1 | §4: "[source] nvJPEG needs two proprietary NVIDIA wheels (GF03 G02, W01)" | Only the nvjpeg wheel is proprietary in every channel (G02). For nvimgcodec the draft itself says the licence is disputed (W01 SLA vs G01/H01 Apache-2.0, NOT VERIFIED). "Needs two" holds for the study's nvImageCodec binding, not for nvJPEG as such | "The study's nvJPEG path (nvImageCodec 0.10.0.9 + nvidia-nvjpeg-cu12) uses two NVIDIA wheels: nvjpeg is proprietary (G02); the nvimgcodec wheel carries the NVIDIA SLA (W01) although PyPI says Apache-2.0 (G01)." |
| W2 | §4: "[source] Bundling makes skellycam the distributor ..." | GF03 §3.4 labels "who distributes: skellycam" as inferred. Only the conditions (W03-W07, C02, C06, C13) are source | Label "Bundling makes skellycam the distributor" [inferred]; keep [source] on the quoted conditions |
| W3 | §4: "HEVC has no software decode in these Chromium builds (intra_playback F10)" | F10 says "on this Windows machine"; intra_playback line 327 scopes F10 to "these Windows builds on this NVIDIA machine" | "HEVC has no software decode in these Windows Chromium builds on this machine (intra_playback F10)." |
| W4 | §2.5: "[measured, other topics] Every QSV output, vp9_qsv and mjpeg_qsv included, decodes to all 32 frames" | Placed under this topic's 8-frame 640x480 probe, it can read as if those packets were decoded. The 32 frames are gpu_encode's own 1080p NV12 test | "In gpu_encode's own 32-frame 1080p NV12 test, every working QSV output ... decodes to all 32 frames (gpu_encode §2.2 line 55). This topic's 8-frame packets were not decoded." |
| W5 | §2.8 intro (kept): "hardware vs software decode was not determined. All-intra streams, 4:2:2, 1080p and PyAV-produced files were not tested here (chromium_codecs / chromium_sync_scrub topics)" | It sits directly above the new F10 bullet, which states the decoder type from intra_playback. The pointer names chromium_sync_scrub, but the results are in intra_playback and chromium_codecs | "... was not determined by this probe (see the intra_playback F9/F10 bullet below). All-intra, 4:2:2, 1080p and PyAV-produced files were not tested here (intra_playback, chromium_codecs)." |
| W6 | §7.2: "HEVC 4:2:2 playback" NOT VERIFIED | chromium_codecs C17 (`FINDINGS.md:116-117`) measured that a 720p hevc_qsv 4:2:2 MKV does not play on this RTX 3070 (E35 does not open it, E45 fails to decode it, line 225). intra_playback line 258 still says NOT VERIFIED, so the two topics disagree | "HEVC 4:2:2: fails on this machine (chromium_codecs C17); on other hardware NOT VERIFIED." Flag the C17 vs intra_playback:258 conflict to the owners |

## 4. Not refuted, noted

- Timing rule: the only cross-topic run data cited (gpu_encode:217 engine counters) comes from the quiet bench run, and no numbers are copied. The fold ran no timing.
- The draft makes no claim that C08 covers `nvjpeg64_12.dll`; it places C08 next to the wheel listing. GF03 §3.1 labels that coverage inferred. Correct as written.
- W10 is attributed only to the nvImageCodec SLA. GF03 reports 0 "benchmark" hits in the CUDA EULA, and own grep of `cuda_eula.html` and the nvjpeg wheel `License.txt` also gives 0. Correct.
