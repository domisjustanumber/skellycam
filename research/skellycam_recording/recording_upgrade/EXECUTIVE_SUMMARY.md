# Recording upgrade: executive summary (2026-11-10)

> **Superseded (2026-11-11).** Dom's decisions in [`CAPTURE_AND_RECORDING_PLAN.md`](../../CAPTURE_AND_RECORDING_PLAN.md) (rev 3.1, 2026-11-11) replace the recommendations below. JPEG only, everywhere: no H.264 or HEVC anywhere, I-frames only. MJPEG cameras use passthrough. Raw cameras are encoded to JPEG with `mjpeg_qsv` first, then libjpeg-turbo. Playback uses a canvas player with Range fetch + `ImageDecoder`. The findings are unchanged, except the §4.3 size comparison, which is corrected there.

**What this is.** A short summary of the recording upgrade study's findings, with proposed recommendations. It summarises `results/EVIDENCE_INDEX.md` (the checked evidence index) and adds no evidence of its own. It is **not** `PLAN.md`: the plan workflow (HANDOFF §6 step 5) has not started. The recommendations below are proposals for Dom's review, and they are all **inferred**, built from the measured and sourced findings they cite.

**Labels**, as in the index: **[M]** measured (result file), **[S]** primary source, **[C]** code, **[I]** inferred, **[NV]** not verified. `EI §x` means `results/EVIDENCE_INDEX.md` §x; topic citations follow the index's notation (for example `CR §2.1`).

**Scope.** All timing comes from one machine (Gerald: i7-14700K, RTX 3070, UHD 770) with PyAV 19.0.2 / FFmpeg 9.0.2, in the quiet run of 2026-11-09/10. Quality numbers are at **target A** (SSIM-Y 0.9961, about 52 dB PSNR-Y, the cameras' own JPEG quality) unless stated. Only intra-only formats are in scope.

---

## 1. Bottom line

1. **Store the cameras' JPEGs as they arrive, in Matroska (MKV) with `flush_packets=1`, beside a small per-frame binary sidecar.** The sidecar holds the capture timestamp (integer ns), a CRC and the byte offset of each frame. This one change covers most of the goals: no transcoding (G1), at most 1 frame lost per crash (G2), royalty-free (G7), frame-exact playback in Electron (G8, G9) and low write cost (G5). [I] from the findings in §3.
2. **No custom container is needed for speed.** Standard containers dropped 0 frames at 16 × 1080p60, and the saving from going custom is small. [M]/[I] `EI §2.5`.
3. **The Electron player has to change whatever format is chosen.** Today's `k/fps` seek rule fails on real camera timing. Use one master clock that draws every camera to a canvas, and pick frames by capture timestamp. [M] `EI §2.9`.
4. **For cameras that send raw frames (YUY2, NV12), there is one real trade-off.** Royalty-free JPEG costs about 1.7–2.5× the bytes of hardware H.264/HEVC intra at target A. H.264 and HEVC are the only codecs with hardware encode on every target platform, and both carry patent royalties. I recommend JPEG as the default and H.264 intra as an opt-in compact mode (§4.4). This is Dom's call. [S]/[M] `EI §2.7, §2.10, §2.12`.
5. **Draw overlays from a sidecar file in the UI. Don't burn them in.** Burn-in costs about half of each frame's time budget, and with passthrough it would force a decode and re-encode. [M] `EI §2.3`.
6. **Don't adopt jellyfin-ffmpeg, AV1, VP9, FFV1-on-GPU or HEVC as the default.** Each one is ruled out or penalised by measured or sourced evidence (§5).

## 2. What today's recorder does, and why it needs to change

- [M] `cv2.VideoWriter` picks Media Foundation and **re-encodes every camera JPEG to H.264**, inside the camera loop. `LIC §2.6`, `PI F1`.
- [M] It writes **plain MP4, which keeps 0 frames after a crash** and cannot be remuxed at 1 GB. `CR §2.10, §4.4`.
- [C] **Overlays are burned in** with `cv2.putText`, and no clean copy is kept. `OV §2.1`.
- [M] **The UI's seek rule `k/fps` is wrong on real (variable) timing**: 34/200 seeks and 0/122 frame steps were correct on a VFR file. `CSS F10a, F14`.

## 3. Key findings by goal

| goal | finding | evidence |
|---|---|---|
| G1 passthrough | Camera JPEGs round-trip **byte-exact**: 1,862 JPEGs × 5 container variants. Width and height must be passed to `add_mux_stream`. | [M] `EI §2.1` (`PI F2`, `JP §2.1`) |
| G1 cost | Re-encoding camera MJPEG instead costs about 4 host cores for 12–16 × 1080p30 cameras and adds a generation of loss. | [M] `EI §2.1` (`IC §2.5`) |
| G2 crash | **MKV + `flush_packets=1` lost 1 frame per kill** (48 paced kills over all containers; 1 in 12/12 for MKV). It never handed out a torn frame on prefix cuts (0/12). Repair runs at 0.907 s/GB. Plain MP4 keeps 0 frames. | [M] `EI §2.2` (GF02, `CR §2.4, §2.13`) |
| G2 container | Fragmented MP4 per frame also loses 1, but tore a frame on 12/12 cuts and takes 1.1 s to open at 54,000 frames. 1 s fragments lose 1–30 frames. | [M] `EI §2.2, §3.2` |
| G2 timestamps | With **frame-index container timestamps** (capture times in the sidecar), OpenCV counts, seeks and FreeMoCap reads are exact in 18/18 files, including files with drops. With real capture times as container timestamps, MKV miscounts, and `recover()` writes a wrong 62.5 fps rate. | [M] `EI §2.1, §2.2` (GF02) |
| G2 integrity | A torn last JPEG decoded silently in 5 of 6 cases, so a per-frame CRC is needed. A CSV sidecar read with pandas gave wrong integers in 6/24 cuts. | [M] `EI §2.2` (`WT §2.2`, `CR §2.9`) |
| G3 overlays | Binary `.skov` sidecar: 29.3 µs/frame, 354.55 MB/h, and the only format tested that rejected a corrupted byte. Burn-in: 16.5 ms/frame. Canvas draw in Electron: about 1 ms. | [M] `EI §2.3` |
| G4 raw/lossless | `h264_nvenc` lossless NV12 1080p: 516 fps, 0.045 cores, bit-exact, plays in Electron. **Quick Sync cannot encode lossless** (0/300 exact frames). CPU FFV1 cannot hold Bayer12 at 30 fps. | [M]/[S] `EI §2.4` (GF09) |
| G5 throughput | **0 drops in 77/77 write cells** up to 16 × 1080p60. A folder of JPEG files costs 26.8 Defender CPU-seconds per 30 s (about 1.2–1.5 for the others), a 78 s first read and a 53 s delete. A custom format would save 0.25–0.52 ms per write at p50. | [M] `EI §2.5`; saving [I] `WT §4.2` |
| G6 GPU encode | Hardware encode works through PyAV 19 for NVENC, QSV, Media Foundation and D3D12. NVENC is capped at **12 sessions** on GeForce. At A, 1080p30: `h264_nvenc` 12 streams at 0.61 cores, `h264_qsv` 16 at 1.25, `mjpeg_qsv` 4:2:2 16 at 0.92, libjpeg-turbo 16 (≥2.81 cores), `hevc_qsv` only 1. | [M] `EI §2.6` |
| G6 pitfall | FFmpeg's default `i_qfactor` codes NVENC/QSV intra frames at a lower QP than requested. Set `i_qfactor=1, i_qoffset=0`. Use `bf=0`. | [M]/[C] `EI §2.6, §2.9` |
| G7 royalties | Baseline JPEG has no listed patents. H.264 and HEVC are pool-licensed. The PyAV wheel ships GPL libx264/libx265, and deleting them breaks `import av`. | [S]/[M] `EI §2.7` |
| G8 playback | MJPEG never plays in `<video>`, MSE or WebCodecs. Camera JPEGs fetched from MKV by byte range decode exactly (450/450 fetches). H.264/HEVC intra seek exactly in E35, E45 and Chrome 156. **HEVC has no software decode in Chromium**, and HEVC 4:2:2 fails in E35/E45. | [M] `EI §2.8` |
| G9 sync | **One master clock drawing to canvas: spread 0 in 28/28 configs.** Eight `<video>` elements: tiles stall in 19/20 configs. Picking frames by previous capture timestamp: 0 mismatches in 48/48 cells. Picking by frame index matched only 0–58 of 328–414 ticks. | [M] `EI §2.9` (GF08) |
| Hardware target | Only H.264/HEVC intra are hardware-encoded on RTX 3000+ **and** on Intel/AMD/Apple 2020+ parts. JPEG has hardware encode on NVIDIA (nvJPEG on CUDA) and Intel (`mjpeg_qsv`), but not on AMD or Apple. AV1 and VP9 fail the target. | [S]/[M] `EI §2.10` |
| jellyfin-ffmpeg | One FFmpeg major version behind, no PyAV binding (subprocess only), and no new encoder relevant on Windows/NVIDIA. | [S]/[M] `EI §2.11` |

## 4. Recommendations (proposed, all [I])

### 4.1 Recording file and writer (G1, G2, G5)
- **Container: MKV with `flush_packets=1`.** It has the best measured mix: 1 frame lost per kill, no torn frames on cuts, 0.19 ms warm open of a 30-minute file, and 0.907 s/GB repair. `EI §2.2, §3.2`.
  - Keep fragmented MP4 (per-frame fragments) as the fallback if MSE playback is ever needed. Its weaknesses are torn frames on cuts and slow opens.
  - Don't use the empty-packet trick by default. It reached 0 lost frames, but it has two seek defects and relies on undocumented muxer behaviour. `EI §3.2`.
- **Container timestamps: frame index at the nominal rate.** The real capture times go in the sidecar. This keeps OpenCV and FreeMoCap exact and avoids the `recover()` 62.5 fps defect. The cost is that the container timeline hides drops: every reader that needs real time must use the sidecar. `EI §2.1, §2.2`.
- **Sidecar: binary, one fixed-size record per frame,** written and flushed with each frame. Each record holds the frame number, capture time in integer ns, payload CRC, payload offset (PyAV `packet.pos` + 4 in MKV, measured) and size. `EI §2.2, §2.9`; `IP F14`.
  - Not yet tested: whether PyAV reports the offset at write time. The fallback is to build the offset index when the file is finalized or repaired.
- **Crash recovery:** on the next start, remux any unfinalized file before an OpenCV reader touches it (about 0.9 s/GB). For a resumed session, continue in a new segment listed in a journal; the prototype for this works. `EI §2.2` (`CR §2.2, §2.8, §2.13`).
- **Writer:** one writer thread per camera, off the capture loop, with a bounded queue that counts drops. The tested depth absorbed stalls up to 329 ms. A shared writer process raised tail latency. `EI §2.5` (`WT §2.11, §4.7`).
- **No folder of JPEGs, no custom raw format, no plain MP4, no FFmpeg segment muxer.** `EI §2.2, §2.5`.
- **Rotation:** store frames unrotated and record the rotation in the sidecar (untested). Lossless rotation costs 6.8–8.9 ms/frame at 1080p if it is ever needed. `EI §2.1`.

### 4.2 Dependencies (G6, G7)
- **Move skellycam to PyAV 19.0.2.** All study evidence uses it. It releases the GIL around header, trailer and close as well as mux (mux was already released in 18), and it needs `requires-python >= 3.12`. `EI §2.5` (`PI F7, F8`).
- **Don't adopt jellyfin-ffmpeg.** If Linux hardware encode is needed later, build PyAV against upstream FFmpeg with VAAPI and Vulkan enabled. `EI §2.11` (`JF §4`).
- **Licence review before shipping an installer.** The stock PyAV wheel carries GPL libx264/libx265 (`EI §2.7`). nvJPEG/nvImageCodec, if used at all, should be an optional pinned extra; its licence terms are split, and one of them bars publishing benchmarks (`EI §2.7`, GF03).

### 4.3 MJPEG cameras (the common case): passthrough only
- Write the camera's JPEG bytes unchanged (§4.1). No encoder means no GPU dependency, no hardware matrix and no royalties. Passthrough is 17.7 GB/h per 1080p30 camera, which is about H.264-intra size [arith] `EI §2.12`.
  - **Correction (2026-11-11):** the "about H.264-intra size" comparison is wrong. The 17.7 GB/h (163,478 B/frame) comes from the MJPEG captures. The H.264 rows in `EI §2.12` (for example `h264_nvenc` 157,840 B, 17.0 GB/h) were encoded from separate YUY2 captures, and `results/intra_compare/FINDINGS.md` §3.1 says not to compare bytes across the two.
  - Same-source numbers (camera JPEGs decoded and re-encoded; target A measured against the decoded camera frame) are in `IC §3.1`: `h264_nvenc` intra is 0.69× (720p) to 0.76× (1080p) of passthrough bytes, `h264_qsv` 0.84–0.91×, and `hevc_qsv` 0.64–0.68× but sustains only 1 stream at 1080p30 [M] `IC §3.1, §2.5`. At 1080p30 that is about 13.3 GB/h for `h264_nvenc` against 17.7 for passthrough [arith] `IC §4`.
  - All of these re-encodes are at lower fidelity than passthrough, because they add a second generation of loss [I] `IC §2.3`. The MJPEG CPU decode + `h264_nvenc` path costs 4.06 cores for 12 × 1080p30 [M] `IC §2.5`. Passthrough stays the recommendation.
  - Separately, at equal SSIM-Y the decoded camera JPEGs need about half the bytes of the YUY2 frames (jt422 145,774 vs 297,359 B at 1080p) [M] `IC §2.3`. The cause is [NV] (NG09, `IC §6`).
- Caveat: the camera JPEGs use q94-like quantisation, but their fidelity against target A is **[NV]** (NG21). Checking it needs back-to-back raw and MJPEG captures by Dom.

### 4.4 Raw cameras (YUY2, NV12): encode intra at target A
**Default: JPEG.**
- One file format and one UI decode path for all cameras (Range fetch + `ImageDecoder`).
- Royalty-free (G7), and no GPL encoder is needed.
- It is hardware-encoded on Intel and NVIDIA, and a CPU fallback works everywhere. `EI §2.10, §2.12`.

Encoder ladder:
1. `mjpeg_qsv` from YUY2: 4:2:2 output, 16 streams at 0.92 cores.
2. libjpeg-turbo in process workers: 16 streams, ≥2.81 cores (lower bound), every CPU.
3. nvJPEG only as an optional extra.
   - It keeps JPEG inside the hardware target on NVIDIA-only machines.
   - On Gerald it has not shown a capacity advantage over libjpeg-turbo: 8 NV12 streams at 2.56 cores.
   - It misses A when fed CPU-decoded MJPEG.
   - Its licence terms are unclear (§4.2).

`EI §2.6, §2.12`.

**Opt-in compact mode: H.264 intra 4:2:0**, using `h264_nvenc`, `h264_qsv`, AMF or VideoToolbox with `gop_size=1`.
- 0.53–0.59× JPEG bytes at A (17–19 GB/h per camera [arith]).
- 0.51–0.57 UI cores at N=8 with WebCodecs, against 1.44 cores for JPEG. The WebCodecs figure leaves out GPU decode.
- Requirements: `flush()` after each chunk for `h264_nvenc`, and `bf=0`.
- More than 12 cameras on NVIDIA needs a second encoder (QSV or CPU JPEG) because of the session cap.
- AMF and VideoToolbox settings come from source code only (not run on hardware).
- `EI §2.6, §2.8, §2.9, §2.12`.

**Not HEVC by default**, despite the smallest files (0.39–0.47×):
- no software decode in Chromium;
- 4:2:2 doesn't play in E35/E45;
- `hevc_qsv` keeps up with only 1 stream at 1080p30.

`EI §2.8, §2.6`.

**The cost of the JPEG default, stated plainly:** at A it is 1.7–1.9× the bytes of H.264 intra and 2.3–2.5× those of HEVC intra (libjpeg-turbo 4:2:2 basis), and at target B the ratios grow to 2.8–5.4×. `EI §2.7, §2.12`.

### 4.5 Lossless and Bayer (G4): defer, NVIDIA-only when needed
- `h264_nvenc` lossless (and the 8-bit Bayer quad split) is exact and plays in Electron.
- It **fails the hardware target**: QSV cannot do lossless, and on other platforms it is NV.
- 12/16-bit input is truncated to 10 bits by FFmpeg's NVENC path.
- Use FFV1 on the CPU only where playback in the UI is not needed.
- Whether the target cameras deliver 1080p30 YUY2 or Bayer at all is NV. Build this only when a camera needs it.
- `EI §2.4`.

### 4.6 Overlays (G3)
- Record overlays to a `.skov` binary sidecar keyed by frame number (CRC'd, 29.3 µs/frame).
- In the UI, draw them on the same canvas as the frame. Don't layer a separate canvas over `<video>`: that matched only 51/275 captures.
- Burn in only on export (works on PyAV 19.0.2).
- `EI §2.3`. Overlay pairing on the master-clock player is not yet tested (NG03).

### 4.7 Electron player (G8, G9)
- **Master clock + canvas** for all N, replacing one `<video>` per camera. `EI §2.9`.
- **Pick frames by capture timestamp:** the latest frame at or before the clock (PREV), in integer ns from each camera's sidecar, on one shared clock.
  - Show nothing before a camera's first frame.
  - Inside a gap, hold the last frame with a stale flag.
  - Stop holding at a limit; about 1.5 frame periods is suggested, and only 1 period was run in the browser.
  - `EI §2.9` (GF08).
- **JPEG:** Range fetch by sidecar offset, then `ImageDecoder` (cheaper than `createImageBitmap`).
  - Accept HTTP 200 without `Content-Range` under `file://`.
  - `EI §2.8, §2.9`.
- **H.264 intra (if used):** one WebCodecs decoder per stream, configured once, with `flush()` per target and every frame closed.
  - **GPU readback is required**: without it the GPU process crashed in 21/24 configs.
  - `EI §2.9` (GF10).
- **Electron 45:** not required for intra-only playback by the current evidence. Until NG02 settles it, clamp seeks away from the exact last frame. `EI §3.2`.

## 5. Ruled out (with evidence)
- **Plain MP4/MOV:** 0 frames after a kill. [M] `EI §2.2`
- **Folder of JPEGs:** Defender cost, tail latency, 78 s first read, 53 s delete; no measured benefit. [M] `EI §2.5`
- **MJPEG in `<video>`/MSE/WebCodecs:** never plays. [M] `EI §2.8`
- **AV1, VP9 intra:** no RTX 3000 encode (and VP9 none on NVIDIA, AMD or Apple); AV1 fails on Gerald. [S]/[M] `EI §2.10`
- **FFV1 on Vulkan:** no wheel has it, and it doesn't play in Chromium. [S]/[M] `EI §2.10`
- **QSV lossless:** impossible (QP floor 1). [M]/[S]/[C] `EI §2.4`
- **HEVC 4:2:2 and libx265 output for the UI:** fail in E35. [M] `EI §2.8`
- **Burn-in at record time:** 16.5 ms/frame. [M] `EI §2.3`
- **Frame-index sync, `k/fps` seeks:** fail on real timing. [M] `EI §2.9`
- **jellyfin-ffmpeg for recording:** [I] `EI §2.11`

## 6. Before building: tests worth running first

These come from the 22 open gaps (`EI §4`), ordered by how much they could change the recommendations. Timed items need a quiet machine and the bench runner.

| priority | gap | why it matters |
|---|---|---|
| 1 | **NG11** end-to-end recorder (encode + MKV+fp + CRC sidecar + overlay sidecar, 12–16 × 1080p30), timed | No test has yet run the whole recommended writer at once. |
| 2 | **NG07** killed MKV+fp and JPEG-index files played in Electron, functional | Confirms that a crashed recording still plays in the UI (G2 + G8). |
| 3 | **NG03** overlay pairing on the master-clock canvas player, functional | §4.6 depends on it. |
| 4 | **NG02** E35 last-frame seek workaround, functional | Decides whether Electron 45 is needed. |
| 5 | **NG06** QSV encoder hold-back under a kill, functional | Only for the raw-camera path (§4.4): frames lost per crash on Intel. |
| 6 | **NG10** more than 12 cameras on NVIDIA, timed | Only if the H.264 compact mode is adopted. |

**Accept as NV, and state in PLAN.md** (NG18–NG21):
- AMD, Apple, Linux and other GPU/CPU generations (source-only or code-only);
- how common CPUs with no iGPU are, so "most CPUs" cannot be quantified;
- H.264/HEVC royalties for free software using GPU or OS encoders (not legal advice);
- ISO BMFF patent status;
- camera JPEG fidelity against target A.

## 7. Where to read more
- `results/EVIDENCE_INDEX.md`: per-goal findings, rule-outs, NV items, contradictions (§3), the trade-off table (§2.12) and the 22 open gaps (§4).
- `results/BENCH_RUN_2300_SUMMARY.md`: the timed run, its flags and headline numbers with file paths.
- `results/<topic>/FINDINGS.md`: the labelled evidence behind each line above.
- `HANDOFF.md`: requirements, Dom's decisions (§1, §1.1) and the remaining steps (§6).
