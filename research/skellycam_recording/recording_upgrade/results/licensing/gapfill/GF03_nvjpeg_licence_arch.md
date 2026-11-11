# GF03: nvJPEG / nvImageCodec licence vs AGPL skellycam, supported GPU architectures, superseded licensing caveats

Gap-fill GF03, 2026-11-10, machine Gerald. Topics: licensing, hw_accel_target, gpu_encode. **Source work only: no timing, no installs, no downloaded code executed.**

- Labels: **measured** = result file; **source** = primary source, verbatim quote, accessed 2026-11-10; **code** = file:line; **inferred** = reasoning, kept short; **NOT VERIFIED**.
- Quote ids below are checked by `scripts/licensing/gapfill/GF03_verify_quotes.py`: **72/72 `found_verbatim: true`** (whitespace-normalised, otherwise exact) in `GF03_quote_verification.json`. That file also holds the sha256 of each source.
- Short verbatim excerpts are in `GF03_sources/`. URLs, HTTP status and sha256 of every download are in `GF03_fetch_log.json`.
- Wheel contents, PyPI fields, CUDA redistrib versions, SPDX flags and the fatbinary architecture lists are in `GF03_wheel_arch_facts.json`.
- Downloads (untrusted, read only as zip/text with `python -I`): `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF03/dl/`.
- **Not legal advice.**

## 1. What the study pins

- code: every nvJPEG script pins `nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9` (e.g. `scripts/gpu_encode/nvimgcodec_jpeg.py:3`, `scripts/intra_compare/sweep.py:4`).
- measured: that resolved to `nvidia-nvjpeg-cu12==12.4.0.76` (`results/gpu_encode/NOTES.md:148`). The intra_compare raw JSONs record only `"nvidia-nvimgcodec-cu12": "0.10.0.9"` (e.g. `results/intra_compare/raw/ff_mjpeg_420__mjpeg_1080p.json:4167`), not the nvjpeg wheel.
- source: the nvjpeg extra is **unpinned**: `Requires-Dist: nvidia-nvjpeg-cu12; extra == "nvjpeg"` (G04). On 2026-11-10 the newest nvidia-nvjpeg-cu12 on PyPI is 12.4.0.76 (`GF03_wheel_arch_facts.json` → `pypi`). A future nvjpeg release would be picked up silently (inferred).
- source: **nvJPEG library 12.4.0.76 is the libnvjpeg of CUDA 12.9 Update 1, not of CUDA 12.4.** `redistrib_12.9.1.json` gives libnvjpeg `"version": "12.4.0.76"` (R04); `redistrib_12.4.0.json` gives `"12.3.1.89"` (R05). The wheel header agrees: `NVJPEG_VER_MAJOR 12 … MINOR 4 … PATCH 0 … BUILD 76` (R22; code: wheel `nvidia/nvjpeg/include/nvjpeg.h:70-73`).
  - So the CUDA 12.9.1 nvJPEG docs (R06-R08) describe the measured library. The CUDA 12.4.0 docs (R01-R03) are quoted only because the task asked for them.

## 2. Quotes table (all accessed 2026-11-10)

### 2.1 Licence: NVIDIA packages

| id | URL | exact quote | supports |
|---|---|---|---|
| G01 | https://pypi.org/pypi/nvidia-nvimgcodec-cu12/0.10.0.9/json | `"license":"Apache License 2.0"` | PyPI metadata says Apache-2.0 for nvImageCodec |
| G02 | https://pypi.org/pypi/nvidia-nvjpeg-cu12/12.4.0.76/json | `"license":"LicenseRef-NVIDIA-Proprietary"` | nvJPEG wheel is proprietary |
| G03 | (same as G02) | `"License :: Other/Proprietary License"` | classifier agrees |
| W01 | nvimgcodec 0.10.0.9 win_amd64 wheel, `dist-info/licenses/LICENSE.txt` (URL in `GF03_fetch_log.json`) | "NVIDIA Software License Agreement" | **the wheel's only licence file is NVIDIA's SLA, not Apache-2.0** (conflicts with G01) |
| W02 | (W01 file) | "(v. November 28, 2023)" | SLA version in the wheel |
| W03 | (W01 file, §1.3) | "distribute the Software in binary format as incorporated into a software application subject to the following distribution requirements:" | redistribution only inside an application |
| W04 | (W01 file, §1.3(a)) | "Your application must have material additional functionality, beyond the included portions of the Software." | condition |
| W05 | (W01 file, §1.3(b)) | "The distributable portions of the Software shall only be accessed by your application." | condition |
| W06 | (W01 file, §1.3(e)) | "The terms under which you distribute your application must be consistent with the terms of this Agreement, including (without limitation) terms relating to the license grant and license restrictions and protection of NVIDIA’s intellectual property rights." | downstream terms must match NVIDIA's |
| W07 | (W01 file, §2.6) | "You may not use the Software in any manner that would cause it to become subject to an open source software license; subject to the terms in the “Components Under Other Licenses” section below" | open-source restriction |
| W08 | (W01 file, §6) | "except that this Agreement will prevail regarding the use of third-party open source software, unless a third-party open source software license requires its license terms to prevail." | conflict rule with OSS components |
| W09 | (W01 file, §2.1) | "The Software is licensed for you to develop applications only for use in systems with NVIDIA GPUs and NVIDIA CPUs (if and when available)." | NVIDIA-only use |
| W10 | (W01 file, §2.11) | "You may not distribute or disclose to third parties the output of the Software where the output reveals functionality or performance data pertinent to NVIDIA hardware or software products, results of benchmarking, competitive analysis, or regression or performance data relating to the Software or NVIDIA GPUs without the prior written permission from NVIDIA." | **benchmark-disclosure restriction** |
| W11 | (W01 file, §2.4) | "Except as expressly granted in this Agreement, you may not copy, sell, rent, sublicense, transfer, distribute, modify or create derivative works of the Software, or make its functionality available to others." | everything else reserved |
| D01-D04 | https://docs.nvidia.com/cuda/nvimagecodec/license.html | D01 = W03 text; D02 = W07 text; D03 = end of W10 ("results of benchmarking, … without the prior written permission from NVIDIA."); D04 "(v. November 28, 2023)" | the docs page carries the same SLA as the wheel |
| H01 | https://github.com/NVIDIA/nvImageCodec/blob/v0.10.0/LICENSE.txt (tag commit 77a7d15b) | "Apache License Version 2.0, January 2004" | the **source repo** at the matching tag is Apache-2.0 |
| H02 | https://github.com/NVIDIA/nvImageCodec/blob/v0.10.0/README.md | "[![License](https://img.shields.io/badge/License-Apache_2.0-yellogreen.svg)](https://opensource.org/licenses/Apache-2.0)" | same |
| E01 | nvjpeg 12.4.0.76 win_amd64 wheel, `dist-info/licenses/License.txt` | "Release Date: July 26, 2018" | the wheel ships a **2018** CUDA EULA text |
| E02 | (E01 file, §1.1.1) | "Distribute those portions of the SDK that are identified in this Agreement as distributable, as incorporated in object code format into a software application that meets the distribution requirements indicated in this Agreement." | distribution grant |
| E03 | (E01 file, §1.2.5) | "You may not use the SDK in any manner that would cause it to become subject to an open source software license. As examples, licenses that require as a condition of use, modification, and/or distribution that the SDK be: a. Disclosed or distributed in source code form; b. Licensed for the purpose of making derivative works; or c. Redistributable at no charge." | open-source restriction |
| E04 | (E01 file, Attachment A) | "Component NVIDIA JPEG Library Linux libnvjpeg.so, libnvjpeg_static.a" | **the wheel's own EULA lists nvJPEG as distributable on Linux only** |
| E05 | (E01 file, §1.2.2) | "For clarity, you may not distribute or sublicense the SDK as a stand-alone product." | no stand-alone redistribution |
| C01 | https://docs.nvidia.com/cuda/eula/index.html | "Last updated: January 26, 2026" | live EULA version |
| C02 | (C01 page, §1.1.1) | E02 text, same wording | distribution grant |
| C03 | (C01 page, §1.1.2) | "Your application must have material additional functionality, beyond the included portions of the SDK." | condition |
| C11 | (C01 page, §1.1.2) | "The distributable portions of the SDK shall only be accessed by your application." | condition |
| C13 | (C01 page, §1.1.2) | W06 text with "this Agreement" (same wording) | downstream terms must match |
| C04 | (C01 page, §1.1.6) | "Subject to the other terms of this Agreement, you may use the SDK to develop and test applications released under Open Source Initiative (OSI) approved open source software licenses." | **explicit permission for OSI-licensed applications (not in the 2018 text, E01)** |
| C05 | (C01 page, §1.1.6) | "If and to the extent there is a conflict between the terms in this Agreement and the license terms associated with the component, the license terms associated with the components control only to the extent necessary to resolve the conflict." | component licences prevail on conflict |
| C06 | (C01 page, §1.2) | E03 text (list markers dropped in HTML) | open-source restriction still present |
| C07 | (C01 page, §1.2) | "For clarity, you may not distribute or sublicense the SDK as a stand-alone product." | no stand-alone redistribution |
| C08 | (C01 page, §2.6 Attachment A) | "The following CUDA Toolkit files may be distributed with applications developed by you, including certain variations of these files that have version number or architecture specific information embedded in the file name" | versioned DLL names are covered |
| C09 | (C01 page, Attachment A) | "Component NVIDIA JPEG Library Windows nvjpeg.lib, nvjpeg.dll Linux libnvjpeg.so, libnvjpeg_static.a" | **live EULA lists Windows nvjpeg as distributable** (the wheel ships `nvjpeg64_12.dll`, measured) |
| C10 | (C01 page, §2.1) | "The SDK is licensed for you to develop applications only for use in systems with NVIDIA GPUs." | NVIDIA-only use |
| C12 | (C01 page, §2.4) | "NVIDIA does not grant to you under this Agreement any necessary patent or other rights with respect to any audio and/or video encoders and decoders." | = existing LIC Q48 |

### 2.2 Licence: AGPL and OSI

| id | URL | exact quote | supports |
|---|---|---|---|
| A01 | https://www.gnu.org/licenses/agpl-3.0.txt returned **HTTP 403**; text from https://raw.githubusercontent.com/spdx/license-list-data/main/text/AGPL-3.0-only.txt, identical to `C:/Users/Dom/GitHub/freemocap/skellycam/LICENSE:111-119` | "The "System Libraries" of an executable work include anything, other than the work as a whole, that (a) is included in the normal form of packaging a Major Component, but which is not part of that Major Component, and (b) serves only to enable use of the work with that Major Component, or to implement a Standard Interface for which an implementation is available to the public in source code form. A "Major Component", in this context, means a major essential component (kernel, window system, and so on) of the specific operating system (if any) on which the executable work runs, or a compiler used to produce the work, or an object code interpreter used to run it." | System Libraries definition |
| A02 | (as A01; LICENSE:122-133) | "The "Corresponding Source" for a work in object code form means all the source code needed to generate, install, and (for an executable work) run the object code and to modify the work, including scripts to control those activities. However, it does not include the work's System Libraries, or general-purpose tools or generally available free programs which are used unmodified in performing those activities but which are not part of the work. For example, Corresponding Source includes interface definition files associated with source files for the work, and the source code for shared libraries and dynamically linked subprograms that the work is specifically designed to require, such as by intimate data communication or control flow between those subprograms and other parts of the work." | Corresponding Source definition |
| A03 | (as A01; LICENSE:281-283) | "A separable portion of the object code, whose source code is excluded from the Corresponding Source as a System Library, need not be included in conveying the object code work." | System Library exclusion when conveying |
| A06 | (as A01; LICENSE:223-231) | "A compilation of a covered work with other separate and independent works, … is called an "aggregate" … Inclusion of a covered work in an aggregate does not cause this License to apply to the other parts of the aggregate." (full sentence in `GF03_quotes.json`) | aggregate rule |
| A07 | (as A01; LICENSE:333-336) | ""Additional permissions" are terms that supplement the terms of this License by making exceptions from one or more of its conditions." | the licensor can add an exception |
| A04 | https://opensource.org/license/agpl-v3 | "Approved: March 3, 2008" | AGPL-3.0 is OSI-approved |
| A05 | https://raw.githubusercontent.com/spdx/license-list-data/main/json/licenses.json | `"licenseId": "AGPL-3.0-or-later"` with `isOsiApproved` true (`GF03_wheel_arch_facts.json` → `spdx`) | same, SPDX list 8791eda |
| code | `pyproject.toml:13`, `:15` (skellycam 55f851e4) | `license = { file = "LICENSE" }`; `"License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)"` | skellycam is AGPL-3.0-or-later; it declares no NVIDIA dependency today |

### 2.3 Architectures

| id | URL | exact quote | supports |
|---|---|---|---|
| R01 | https://docs.nvidia.com/cuda/archive/12.4.0/nvjpeg/index.html | "Hardware accelerated JPEG decode is available on the following GPUs - A100, A30, H100." | CUDA 12.4: hardware decode on data-centre parts only |
| R02 | (R01 page) | "The encoding functions of the nvJPEG library perform GPU-accelerated compression of user’s image data to the JPEG bitstream." | CUDA 12.4 encode is GPU (CUDA); no hardware encoder mentioned |
| R03 | (R01 page) | "Uses Hardware Acceleration for decode. Supports baseline JPEG images with single scan with 1 or 3 channels. 410 and 411 chroma subsamplings are not supported." | hardware decode limits |
| R04 | https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.9.1.json | `"version": "12.4.0.76"` (key `libnvjpeg`) | measured library = CUDA 12.9.1 |
| R05 | https://developer.download.nvidia.com/compute/cuda/redist/redistrib_12.4.0.json | `"version": "12.3.1.89"` (key `libnvjpeg`) | CUDA 12.4's nvJPEG is a different version |
| R06 | https://docs.nvidia.com/cuda/archive/12.9.1/nvjpeg/index.html | "Hardware accelerated JPEG decode is available on the following GPUs architectures - Ampere (A100, A30) Hopper Ada Blackwell Platforms which support hardware accelerated JPEG decode: Windows Linux (x86_64, PowerPC, ARM64) Hardware accelerated JPEG encode is available on Jetson Thor (Blackwell), running Linux ARM64." | **docs matching the measured library**: hardware decode by architecture; hardware encode on Jetson Thor only |
| R07 | (R06 page) | "NVJPEG_ENC_BACKEND_DEFAULT Use hardware engine if possible. If not, fallback to CUDA encoder. NVJPEG_ENC_BACKEND_GPU Always use CUDA encoder. NVJPEG_ENC_BACKEND_HARDWARE Always use hardware engine. Do not fallback to CUDA." | **docs separate CUDA (SM) encode from the hardware engine** |
| R08 | (R06 page) | = R02 text | encode is GPU-accelerated |
| R09 | https://docs.nvidia.com/cuda/archive/12.9.1/cuda-toolkit-release-notes/index.html | "Added hardware-accelerated JPEG encoding support for NVIDIA Jetson Thor hardware (Blackwell SM 10.1 architecture)." | hardware JPEG encode = SM 10.1 Thor only |
| R10 | (R09 page, nvJPEG 12.8) | "Added hardware-accelerated JPEG decoding support in nvJPEG for NVIDIA Blackwell architecture GPUs." | Blackwell hardware decode |
| R11 | (R09 page, nvJPEG 12.9) | "nvjpegEncode: Replaces nvjpegEncodeYUV and nvjpegEncodeImage. nvjpegEncode is required for hardware encoding" | encode API in the measured library |
| R21 | (R09 page, nvJPEG 12.9) | "Added JPEG decoding support for two new formats: NV12 and YUY2, for both hardware engine and CUDA. For NV12, the chroma subsampling must be 420, and for YUY2, it must be 422." | lead for gpu_encode (decode to YUY2) |
| R12 | (R09 page) | "Maxwell, Pascal, and Volta architectures are now feature-complete with no further enhancements planned." | older archs on the way out |
| R13 | https://docs.nvidia.com/cuda/nvjpeg/index.html (nvJPEG 13.5) | "Hardware accelerated JPEG decode is available on the following GPUs architectures - Ampere (A100, A30) Hopper Ada Blackwell Jetson Thor Platforms which support hardware accelerated JPEG decode: Windows Linux (x86_64, ARM64) Hardware accelerated JPEG encode is available on Jetson Thor, running Linux ARM64." | hw_accel_target N6/N7 quotes still current |
| R14 | https://docs.nvidia.com/cuda/archive/12.9.1/cuda-c-programming-guide/index.html | "Binary compatibility is guaranteed from one minor revision to the next one, but not from one minor revision to the previous one or across major revisions. In other words, a cubin object generated for compute capability X.y will only execute on devices of compute capability X.z where z≥y." | SASS for sm_80 runs on 8.6/8.9; sm_70 on 7.5 |
| K01-K04 | https://developer.nvidia.com/cuda-gpus | rows listed under CC headings: "GeForce RTX 5090" under "12.0"; "GeForce RTX 4090" under "8.9"; "GeForce RTX 3070" under "8.6"; "GeForce RTX 2080" under "7.5" (order checked in the page text) | GeForce generation → compute capability |
| R15 | https://github.com/NVIDIA/nvImageCodec/blob/v0.10.0/README.md | "- nvjpeg_ext - Hardware jpeg decoder - Hardware jpeg encoder (on Jetson Thor) - CUDA jpeg decoder - CUDA lossless jpeg decoder - CUDA jpeg encoder" | nvImageCodec separates hardware and CUDA codecs |
| R16 | (R15 file) | "- NVIDIA driver >= 531.14 - CUDA Toolkit >= 12.1" | Windows requirements; **no compute-capability list** |
| R17, R18 | https://docs.nvidia.com/cuda/nvimagecodec/release_notes_v0.10.0.html | "v0.10.0-beta.11"; "This software is in beta version, which means it is still undergoing testing and development before its official release." | the 0.10.0 notes are labelled beta. Whether that applies to wheel 0.10.0.9: NOT VERIFIED |
| R19 | (R17 page) | "Planar YUV (P_YUV) is not converted, and CPU-only encoders are unaffected." | consistent with the measured YUV-input rejection (N8) |
| R20 | (R17 page) | "Encoding a chroma-subsampled Image is not supported yet and raises ValueError." | binding limit in 0.10 |
| R22 | nvjpeg wheel `nvidia/nvjpeg/include/nvjpeg.h:70-73` | "#define NVJPEG_VER_MAJOR 12 … #define NVJPEG_VER_BUILD 76" | header version |

- source/measured: nvImageCodec docs (index, installation, getting_started, 0.10.0 release notes) and the v0.10.0 README contain **no** match for "compute capab", "Turing", "Ampere", "Ada", "Blackwell", "Hopper" or "sm_" (grep of the saved text, 2026-11-10). An nvImageCodec statement of supported GPU architectures is **NOT VERIFIED**.

## 3. Licence analysis (source + inferred, not legal advice)

### 3.1 Facts that apply to both cases

- measured: each wheel has exactly one licence-like file. nvimgcodec: `dist-info/licenses/LICENSE.txt` (NVIDIA SLA, W01). nvjpeg: `dist-info/licenses/License.txt` (CUDA EULA dated 2018, E01). No NOTICE or EULA file besides these (`GF03_wheel_arch_facts.json` → `licence_like_members`).
- source: **nvImageCodec's licence is inconsistent across NVIDIA's own channels.** PyPI metadata and the GitHub source at v0.10.0 say Apache-2.0 (G01, H01, H02). The wheel and the docs page carry the proprietary NVIDIA SLA (W01, D01-D04). Which one governs the PyPI binary: NOT VERIFIED.
  - inferred: treat the wheel as SLA-licensed until NVIDIA says otherwise; building nvImageCodec from the Apache-2.0 source could remove the SLA for nvImageCodec, but not for nvJPEG.
- source: **nvJPEG is proprietary in every channel** (G02, G03, E01, C01).
- source: **the nvjpeg wheel carries an older EULA than the web page.**
  - The wheel's 2018 text lists the NVIDIA JPEG Library as distributable on **Linux only** (E04). The live 2026 EULA lists Windows `nvjpeg.lib, nvjpeg.dll` (C09), plus file names with version information embedded (C08), which covers `nvjpeg64_12.dll` (inferred).
  - The live EULA adds permission to "develop and test applications released under" OSI-approved licences (C04). The 2018 text has no such sentence.
  - Which text governs a given wheel: NOT VERIFIED.
- source: AGPL-3.0 is OSI-approved (A04, A05). skellycam is AGPL-3.0-or-later (code: `pyproject.toml:15`).
- source: both NVIDIA licences forbid any use that would make the NVIDIA software "subject to an open source software license" (W07, E03, C06). The CUDA EULA's examples include licences requiring that the SDK be "Disclosed or distributed in source code form" (C06).
- source: **benchmark clause.** The nvImageCodec SLA bars disclosing "results of benchmarking … relating to the Software or NVIDIA GPUs" without NVIDIA's written permission (W10, D03). The CUDA EULA text has 0 matches for "benchmark" (grep of both copies).
  - inferred: this study's nvJPEG-via-nvImageCodec timings (gpu_encode §2.8, intra_compare §2.4–2.5) are local research. Publishing them, for example by pushing `research/` to a public repo, may need NVIDIA's permission under W10. Dom to decide; not a legal opinion.

### 3.2 Case (a): skellycam lists the NVIDIA wheel as an optional dependency the user installs with pip

- inferred: skellycam conveys only its own source. The user downloads `nvidia-nvimgcodec-cu12` and `nvidia-nvjpeg-cu12` from PyPI and takes them under NVIDIA's terms (W01, E01/C01). NVIDIA's redistribution conditions (W03-W06, C02, C03, C11, C13) bind the party that distributes, which here is NVIDIA/PyPI, not skellycam.
- inferred: AGPL side. The AGPL obligations attach to what skellycam conveys. Corresponding Source covers libraries "the work is specifically designed to require" (A02). If skellycam runs without nvJPEG (libjpeg-turbo or `mjpeg_qsv` fallback, both measured in intra_compare), the optional extra is arguably not "required". Whether nvJPEG counts as a System Library (A01) is doubtful: it is neither part of the OS nor of a compiler or interpreter.
- inferred: NVIDIA side. Nothing in case (a) makes the NVIDIA binaries subject to the AGPL, because skellycam neither distributes nor relicenses them (W07, C06). The live CUDA EULA expressly allows developing and testing OSI-licensed applications (C04). "Develop and test" does not clearly cover end-user deployment, and the 2018 text in the wheel lacks C04 (NOT VERIFIED which governs).
- inferred: to remove doubt, the skellycam licensors can add an AGPL "additional permission" (A07) for linking the NVIDIA libraries. That is a licensor decision; contributors' consent was not checked.
- inferred, practical: the lowest-risk form is an extra in `pyproject.toml` (for example `skellycam[nvjpeg]`) that names `nvidia-nvimgcodec-cu12[nvjpeg]` with a pinned nvjpeg version, with a runtime fallback when the import fails. Naming a package is not distributing it. The pin also fixes the unpinned-extra problem in §1.

### 3.3 Case (b): skellycam bundles the wheel in an installer

- source: skellycam would then be the distributor. It may distribute only "as incorporated into a software application" with "material additional functionality", with the NVIDIA parts "only … accessed by your application", and not as a stand-alone product (W03-W05, C02, C03, C07, C11, E05).
- source: skellycam's own distribution terms "must be consistent with the terms of this Agreement" (W06, C13).
- inferred: that creates tension with the AGPL. The AGPL gives recipients rights to copy, modify and redistribute the conveyed work. NVIDIA requires downstream terms consistent with its restrictions, and forbids anything that would subject its software to an open-source licence (W07, C06).
  - A route exists if the NVIDIA DLLs are a separate work in an "aggregate" (A06), so the AGPL does not apply to them, and if they are excluded from Corresponding Source because skellycam does not "require" them (A02).
  - Whether a Python installer that loads them in-process is an aggregate or "a larger program": NOT VERIFIED, and a legal question.
- source: for Windows, only the live EULA lists nvjpeg as distributable (C09). The licence file inside the wheel does not (E04). An installer copying the wheel's DLL would rely on the web EULA (NOT VERIFIED which governs).
- source: both NVIDIA licences limit use to systems with NVIDIA GPUs (W09, C10). An installer for all users should install the NVIDIA parts only where an NVIDIA GPU is present (inferred).
- inferred: case (b) needs legal review before shipping. Case (a) avoids most of the open questions.

### 3.4 Summary

| question | case (a) optional pip extra | case (b) bundled in installer |
|---|---|---|
| who distributes NVIDIA binaries | NVIDIA via PyPI (inferred) | skellycam (inferred) |
| NVIDIA redistribution conditions apply to skellycam | no (inferred) | yes: W03-W06, C02, C03, C07, C11, C13 |
| Windows nvjpeg listed as distributable | n/a | live EULA yes (C09); wheel's own EULA no (E04) |
| conflict with AGPL | low, if nvJPEG stays optional (A02; inferred) | open: W06/W07/C06 vs AGPL recipients' rights; aggregate test (A06) NOT VERIFIED |
| NVIDIA permission for OSI-licensed apps | "develop and test" (C04), live EULA only | same; deployment scope NOT VERIFIED |
| benchmark disclosure (W10) | applies to anyone publishing nvImageCodec benchmarks | same |
| label | source + inferred, not legal advice | source + inferred, not legal advice |

## 4. Architecture coverage (nvJPEG encode)

- measured (static): CUDA fatbinary headers parsed from the wheel DLLs with `scripts/licensing/gapfill/GF03_fatbin_archs.py` (no execution; my own parser; `cuobjdump` is not installed, so it is not cross-checked). Result in `GF03_wheel_arch_facts.json` → `fatbin`:
  - `nvjpeg64_12.dll` (11 fatbins): SASS for sm_50, 52, 60, 61, 70, **75, 80, 86, 89**, 90, **100, 101, 103, 120, 121**, plus PTX 121.
  - nvImageCodec `nvjpeg_ext_0.dll`, `nvimgcodec_0.dll`, `nvimgcodec_impl.cp312-win_amd64.pyd`: SASS for sm_50, 60, 70, 80, 90, 100, **120**, plus PTX 120.
- source: sm_80 SASS runs on 8.6 and 8.9, and sm_70 SASS on 7.5 (R14). So every nvImageCodec kernel has a runnable binary on 7.5, 8.6, 8.9 and 12.0 (inferred from R14 + the parse).
- source: the docs **do distinguish** CUDA (SM) encode from the fixed-function JPEG engine. The engine is selected by `NVJPEG_ENC_BACKEND_HARDWARE`, the CUDA path by `NVJPEG_ENC_BACKEND_GPU` "Always use CUDA encoder" (R07). nvImageCodec lists "Hardware jpeg encoder (on Jetson Thor)" apart from "CUDA jpeg encoder" (R15).
  - Hardware encode: Jetson Thor (Blackwell SM 10.1), Linux ARM64, only (R06, R09, R13).
  - Hardware decode: "Ampere (A100, A30) Hopper Ada Blackwell" in the measured library's docs (R06). CUDA 12.4 named "A100, A30, H100" only (R01).
  - inferred: on any GeForce RTX, nvJPEG **encode** is the CUDA backend.

| GeForce | compute capability (K01-K04) | nvJPEG 12.4.0.76 SASS (measured static) | nvImageCodec 0.10.0.9 kernels (measured static + R14) | nvJPEG CUDA encode works | hardware JPEG decode engine | hardware JPEG encode engine |
|---|---|---|---|---|---|---|
| RTX 20 (Turing) | 7.5 | sm_75 present | sm_70 SASS, runs on 7.5 (inferred) | **NOT VERIFIED** (no device) | not listed (R06) → no | no (R06) |
| RTX 30 (Ampere GA10x) | 8.6 | sm_86 present | sm_80 SASS, runs on 8.6 (inferred) | **measured** on Gerald RTX 3070 (`results/gpu_encode/nvimgcodec_jpeg.md`; hw_accel_target N8) | not listed; only "Ampere (A100, A30)" (R06) → no. Matches measured `HW_GPU_ONLY` failure (N8) | no |
| RTX 40 (Ada) | 8.9 | sm_89 present | sm_80 SASS, runs on 8.9 (inferred) | **NOT VERIFIED** | "Ada" listed (R06); whether that includes GeForce RTX 40: NOT VERIFIED | no |
| RTX 50 (Blackwell) | 12.0 | sm_120 present | sm_120 SASS | **NOT VERIFIED** | "Blackwell" listed (R06, R10); GeForce RTX 50 applicability NOT VERIFIED | no (Thor SM 10.1 only, R09) |

- inferred: binaries for all four generations exist in the pinned wheels, so RTX 20/40/50 are **"code present, not run"**, not "inferred from N6 docs" alone. Functional encode on 7.5, 8.9 and 12.0 stays NOT VERIFIED.
- NOT VERIFIED: driver minimum for sm_120 with this wheel. The README gives only "NVIDIA driver >= 531.14" for Windows (R16).
- code: the measured library has YUV and NV12 encode inputs and `nvjpegEncodeYUV` / `nvjpegEncode` (wheel `nvjpeg.h:154`, `:159`, `:540`, `:560`; excerpt `GF03_sources/nvjpeg_h_12.4.0.76_lines.txt`). So "planar-YUV encode in nvJPEG 12.4" (hw_accel_target N9, §6) exists in the API of the measured library. Reaching it from Python through a binding is still NOT TESTED. nvImageCodec 0.10 states it does not convert P_YUV (R19).

## 5. Superseded caveats in licensing FINDINGS (`results/licensing/FINDINGS.md`)

| line | old text (verbatim) | superseded by | status |
|---|---|---|---|
| 97 | "Decoding of the emitted packets and whether they ran on the iGPU were not checked." | gpu_encode FINDINGS line 55: "each of the 26 working outputs decodes to 32 frames. This covers NVENC, D3D12, MF and QSV, including vp9_qsv and mjpeg_qsv." intra_compare FINDINGS §2.1 lines 56-58: every sweep point "decoded back in PyAV 19.0.2 software decode with frames out = frames in", 0 failed (h264_qsv, hevc_qsv, mjpeg_qsv included). gpu_encode FINDINGS line 217: QSV encodes load the iGPU engines (GPU Engine counters) | decode: superseded. iGPU use: superseded for h264/hevc/mjpeg_qsv (engine counters); vp9_qsv engine use not recorded |
| 98 | "The GPU-encode / hw_accel_target topics own the QSV analysis." | same | keep as pointer, but drop the implied "not done" |
| 124 | "All-intra streams, 4:2:2, 1080p and PyAV-produced files were not tested here (chromium_codecs / chromium_sync_scrub topics)." | intra_playback F1 (line 30): 48 PyAV 19.0.2 NVENC/QSV intra clips, 720p30/1080p30, CFR and VFR, open, play and seek in E35, E45, C156. chromium_codecs C2, C5-C7 (lines 48, 56-66): mjpeg_qsv 4:2:2 MKV fails; AV1/VP9 all-intra and PyAV 19 AV1/VP9 intra clips play | still true "here"; add the pointer with results |
| 132 | "[inferred] HEVC playback here relies on a hardware decoder (RTX 3070 and/or the installed HEVC extension), not only on `proprietary_codecs = true`. HEVC playback on machines without HEVC hardware decode: NOT VERIFIED." | intra_playback F10 (line 59): "HEVC has no software decode in E35, E45 or C156 on this Windows machine." `prefer-software` fails with `config not supported` for every HEVC clip. F9 (line 56): `D3D11VideoDecoder` for H.264 and HEVC | **inferred → measured** on this machine; "machines without HEVC hardware" stays NOT VERIFIED |
| 142 | "vp9_qsv opens (Intel iGPU; decode not checked)" | gpu_encode FINDINGS line 55 (vp9_qsv decodes to 32 frames) | superseded |
| 151 | "yes / yes (HEVC extension installed; hardware decode inferred)" | intra_playback F9, F10 | "hardware decode only, measured (F10)" |
| 176 | "Playback of all-intra, 4:2:2 or PyAV-produced streams is for the chromium topics." | chromium_codecs C5-C7; intra_playback F1 | superseded: AV1/VP9 all-intra and PyAV 19 AV1/VP9 intra clips play |
| 178 | "Whether vp9_qsv output decodes correctly, and coverage on the hardware target (RTX 3000+, 2020+ CPUs), belongs to the GPU-encode / hw_accel_target topics." | gpu_encode line 55 (decodes); hw_accel_target §3.3 VP9 row (line 373): "**N** (all NVIDIA) … **no**" | superseded: decodes, and VP9 fails the target |
| 182 | "HEVC playback also appears to depend on hardware (2.8)." | intra_playback F10 | superseded: measured, no software decode |
| 190 | "QSV output was not decoded." | gpu_encode line 55; intra_compare §2.1 | superseded |
| 191 | "Browser tests used tiny synthetic 4:2:0 clips from the ffmpeg CLI. … Hardware vs software decode was not determined." | intra_playback F1, F9, F10 | the 2.8 rows are still tiny CLI clips; decoder type is now determined elsewhere |
| 301 | "Whether vp9_qsv output decodes correctly and whether QSV ran on the iGPU; the cause of the 10:55 QSV failures." | gpu_encode lines 55, 217 | only "the cause of the 10:55 QSV failures" remains |
| 302 | "HEVC playback on machines without HEVC hardware decode; browser playback of all-intra, 4:2:2, 1080p or PyAV-produced streams." | intra_playback F1, F10, F16; chromium_codecs C2, C5-C7 | only "machines without HEVC hardware decode" and "HEVC 4:2:2 playback" remain |

## 6. Proposed replacement text

### 6.1 licensing FINDINGS

**§2.4, line 71.** Old: "- [source] nvjpeg.dll is a CUDA redistributable component (Q50)."
New:
- [source] The live CUDA EULA (last updated January 26, 2026) lists "NVIDIA JPEG Library Windows nvjpeg.lib, nvjpeg.dll" as distributable (Q50; GF03 C09), including file names with version information embedded (GF03 C08). The `nvidia-nvjpeg-cu12==12.4.0.76` wheel ships `nvjpeg64_12.dll` [measured, GF03].
- [source] The licence file inside that wheel is an older EULA ("Release Date: July 26, 2018"), which lists the NVIDIA JPEG Library as distributable for Linux only (GF03 E01, E04). Which text governs: NOT VERIFIED.
- [source] The live EULA adds: "you may use the SDK to develop and test applications released under Open Source Initiative (OSI) approved open source software licenses" (GF03 C04). AGPL-3.0 is OSI-approved (GF03 A04). It keeps the ban on use that would make the SDK "subject to an open source software license" (GF03 C06).

**§2.4, line 72.** Old: "- [source] nvImageCodec: binary redistribution is allowed only "as incorporated into a software application" with "material additional functionality" (Q51). "You may not use the Software in any manner that would cause it to become subject to an open source software license" (Q52)."
New: keep the line, then add:
- [source] The nvimgcodec 0.10.0.9 wheel's only licence file is the same NVIDIA Software License Agreement (v. November 28, 2023) (GF03 W01, W02). PyPI metadata and the GitHub source at tag v0.10.0 say Apache-2.0 (GF03 G01, H01). NVIDIA's channels disagree; treat the binary wheel as SLA-licensed (inferred).
- [source] The SLA forbids disclosing "results of benchmarking … relating to the Software or NVIDIA GPUs" without NVIDIA's written permission (GF03 W10).

**§2.5, line 97.** Replace the last sentence ("Decoding of the emitted packets and whether they ran on the iGPU were not checked.") with: "Decoding was later checked: every QSV output, vp9_qsv and mjpeg_qsv included, decodes to all frames (gpu_encode FINDINGS §2.2), and every intra_compare sweep point decodes with frames out = frames in (intra_compare FINDINGS §2.1). h264/hevc/mjpeg_qsv load the iGPU engines (gpu_encode FINDINGS §2.8, GPU Engine counters)."

**§2.8, line 132.** Old: "- [inferred] HEVC playback here relies on a hardware decoder (RTX 3070 and/or the installed HEVC extension), not only on `proprietary_codecs = true`. HEVC playback on machines without HEVC hardware decode: NOT VERIFIED."
New: "- [measured, intra_playback F10] HEVC has no software decode in E35, E45 or C156 on this machine: WebCodecs `prefer-software` fails for every HEVC clip, and `<video>` uses `D3D11VideoDecoder` (F9). HEVC playback on machines without HEVC hardware decode: NOT VERIFIED (expected to fail, inferred)."

**§3.1 table, lines 142 and 151.** VP9 GPU cell: "vp9_qsv opens and decodes (Intel iGPU; gpu_encode §2.2)". HEVC playback cell: "yes / yes, hardware decode only (intra_playback F10)".

**§4, line 176.** Old sentence: "Playback of all-intra, 4:2:2 or PyAV-produced streams is for the chromium topics."
New: "PyAV 19.0.2 AV1 and VP9 all-intra clips play via `<video src>` in E35, E45 and C156 (chromium_codecs C7)."

**§4, line 178.** Old sentence: "Whether vp9_qsv output decodes correctly, and coverage on the hardware target (RTX 3000+, 2020+ CPUs), belongs to the GPU-encode / hw_accel_target topics."
New: "vp9_qsv output decodes (gpu_encode §2.2), but VP9 fails the hardware target: no NVIDIA, AMD or Apple VP9 encode (hw_accel_target §3.3)."

**§4, line 182.** Old: "HEVC playback also appears to depend on hardware (2.8)."
New: "HEVC has no software decode in these Chromium builds (intra_playback F10)."

**§4, new bullet after line 178** (nvJPEG; source + inferred, not legal advice):
- "nvJPEG (G1 re-encode on NVIDIA) needs two proprietary NVIDIA wheels (GF03 G02, W01). Ship them as an optional pip extra that the user installs, with a pinned nvjpeg version and a CPU/QSV fallback. Do not bundle them in an installer without legal review: bundling makes skellycam the distributor under conditions that require consistent downstream terms and forbid open-source licensing of the NVIDIA parts (GF03 W03-W07, C02, C06, C13). Whether the AGPL aggregate rule (GF03 A06) avoids the conflict is NOT VERIFIED (GF03 §3)."

**§5, line 190.** Old: "Encoder results come from default-option, 8-frame open tests. They say nothing about speed or quality. QSV output was not decoded. DNxHD failed only with default options."
New: "Encoder results here come from default-option, 8-frame open tests. They say nothing about speed or quality; decode, quality and speed are in gpu_encode and intra_compare. DNxHD failed only with default options."

**§5, line 191.** Old: "Browser tests used tiny synthetic 4:2:0 clips from the ffmpeg CLI. They establish support, not performance or frame accuracy. HEVC/AV1/VP9 results may depend on the Windows codec extensions and GPU here. Hardware vs software decode was not determined. WebCodecs results are capability queries only."
New: "The §2.8 browser rows used tiny synthetic 4:2:0 clips from the ffmpeg CLI and capability queries. Frame accuracy, all-intra, 1080p and PyAV-produced clips, and decoder type were measured later (intra_playback F1, F9, F10; chromium_codecs C5-C7). HEVC/AV1/VP9 results may depend on the Windows codec extensions and the GPU here."

**§7.2, lines 301-302.**
New 301: "The cause of the 10:55 QSV failures."
New 302: "HEVC playback on machines without HEVC hardware decode; HEVC 4:2:2 playback."
Add: "Which licence governs the nvImageCodec wheel (SLA in the wheel vs Apache-2.0 on PyPI/GitHub) and which CUDA EULA version governs the nvjpeg wheel (2018 file vs 2026 web page); whether a bundled installer is an AGPL "aggregate" (GF03)."

### 6.2 hw_accel_target FINDINGS

**N6, line 58.** Old: "  - Version gap: the measured stack is `nvidia-nvjpeg-cu12==12.4.0.76` (GE §6, `R/gpu_encode/NOTES.md:148`). The 13.5 docs are used for capability statements only."
New:
- "  - [source] `nvidia-nvjpeg-cu12==12.4.0.76` is the libnvjpeg of CUDA 12.9 Update 1 (`redistrib_12.9.1.json`), not of CUDA 12.4, whose libnvjpeg is 12.3.1.89 (GF03 R04, R05)."
- "  - [source] The CUDA 12.9.1 nvJPEG docs, which match the measured library, carry the same statements: `NVJPEG_ENC_BACKEND_GPU` "Always use CUDA encoder", and "Hardware accelerated JPEG encode is available on Jetson Thor (Blackwell), running Linux ARM64" (GF03 R06, R07). The version gap is closed."

**N9, line 71.** Old: "  - NOT VERIFIED: planar-YUV encode in nvJPEG 12.4, and any YUV path through another binding."
New: "  - [code] The measured library's header has `NVJPEG_INPUT_YUV`, `NVJPEG_INPUT_NV12`, `nvjpegEncodeYUV` and `nvjpegEncode` (wheel `nvjpeg.h:154, 159, 540, 560`; GF03). A Python binding that reaches them: NOT TESTED. nvImageCodec 0.10 states "Planar YUV (P_YUV) is not converted" (GF03 R19)."

**R5, line 292.** Old: "- **R5 [source]** nvImageCodec may be redistributed only "as incorporated into a software application", and not under an open-source licence (LIC Q51, Q52)."
New:
- "- **R5 [source]** nvImageCodec (wheel SLA) and nvJPEG (CUDA EULA) may be redistributed only inside an application with material additional functionality. Downstream terms must be consistent with NVIDIA's, and neither may be made subject to an open-source licence (LIC Q51, Q52; GF03 W03-W07, C02-C06)."
- "  - The nvImageCodec SLA also bars publishing nvImageCodec benchmark results without NVIDIA's permission (GF03 W10)."
- "  - [inferred, GF03 §3, not legal advice] An optional pip extra is the low-risk route for AGPL skellycam. Bundling the wheels in an installer needs legal review."

**§3.1, lines 322, 324, 325 (JPEG column).**
- Turing: "enc CUDA: NV (not run; sm_75 SASS in the nvjpeg wheel, GF03) / dec hybrid CUDA+CPU; no hardware engine (not listed, GF03 R06)".
- Ada: "enc CUDA: NV (not run; sm_89 SASS in the nvjpeg wheel, GF03) / dec: "Ada" in the hardware-decode list (N7); GeForce applicability and 4:2:2 NV".
- Blackwell: "enc CUDA: NV (not run; sm_120 SASS in nvjpeg and nvImageCodec, GF03) / dec: "Blackwell" in the hardware-decode list (N7; CUDA 12.8 notes, GF03 R10); GeForce applicability NV. Hardware JPEG encode is Jetson Thor (SM 10.1) only, not RTX 50 (GF03 R09)".
- Legend line 315: add "Hardware JPEG encode exists only on Jetson Thor (GF03 R06, R09), so every GeForce JPEG encode cell is the CUDA backend."

**§3.3, line 370, RTX column.** Old: "Y via **nvJPEG CUDA** (measured on Ampere, outside FFmpeg/PyAV; RTX 40/50 inferred, N6)".
New: "Y via **nvJPEG CUDA** (measured on Ampere, outside FFmpeg/PyAV; RTX 20/40/50: binaries present for sm_75/89/120, not run, GF03)". Same change in the last column ("RTX 40/50 … inferred" → "RTX 40/50 code present, not run").

**§4 item 2, line 420.** Old: "It is measured on Ampere; RTX 40/50 is inferred." New: "It is measured on Ampere; RTX 40/50 have SASS in the pinned wheels but were not run (GF03)."

**§4.4, line 434.** Old: "     - It is a separate dependency with licence limits (R5)." New: "     - It needs two proprietary NVIDIA wheels; ship them as an optional, pinned pip extra, not inside an installer (R5; GF03 §3)."

**§6, lines 500, 503, 504.**
- 500 → "nvJPEG encode on Turing/Ada/Blackwell (binaries present, not run; GF03)".
- 503 → "a Python binding for nvJPEG planar-YUV encode (the API exists in the measured library, GF03)".
- 504 → delete (version gap closed by GF03 R04, R06).

**Out of scope, observed:** hw_accel_target §5 ("Pending tonight's bench", lines 465-494) is stale; the bench ran on 2026-11-10 (`results/BENCH_RUN_2300_SUMMARY.md`). Another gap-fill may own it.

## 7. Not done / NOT VERIFIED

- gnu.org `agpl-3.0.txt` returned HTTP 403. The AGPL text is quoted from the SPDX copy and the skellycam `LICENSE`, both whitespace-identical for the quoted passages.
- Which licence governs the nvImageCodec PyPI wheel (SLA file vs Apache-2.0 metadata).
- Which CUDA EULA version governs the nvjpeg wheel (2018 text in the wheel vs 2026 web page).
- Whether "Ada" and "Blackwell" in the hardware-decode list include GeForce parts.
- Functional nvJPEG encode on RTX 20/40/50.
- The fatbinary parse is not cross-checked with `cuobjdump`.
- Whether a bundled installer is an AGPL "aggregate". A legal question.
- nvImageCodec 0.9.0.20, used by the python_integration decode bench, was not inspected.
