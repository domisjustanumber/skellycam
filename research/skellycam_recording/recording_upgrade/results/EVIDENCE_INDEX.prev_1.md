# Recording upgrade: evidence index (2026-11-10)

**Purpose.** This is the input to the PLAN.md workflow (HANDOFF.md §6 step 5: three draft plans, judge panel, synthesis, evidence audit). For each goal it lists the verified findings, the options ruled out with their evidence, and what is still NOT VERIFIED. It adds no evidence of its own. Every bullet points to a topic FINDINGS section, and through that to the result file. Where two FINDINGS files disagree, this index says so and does not pick one.

## 1. How to read this index

**Sources.**
- The 14 topic FINDINGS, all updated 2026-11-10 with the quiet-run numbers (step 2) and the gap-fill (step 3).
- `BENCH_RUN_2300_SUMMARY.md`.
- The step 3 output (`step3_result.json` in the session scratchpad): critics, triage, gap-fill GF01–GF10, and verify3/revise3.
- Gap-fill evidence is in `results/<topic>/gapfill/`.

**Labels** (as the FINDINGS give them; nothing has been upgraded):

| tag | meaning |
|---|---|
| **[M]** | measured: a result file |
| **[S]** | source: primary source, quoted |
| **[C]** | code: file:line |
| **[I]** | inferred: kept inferred wherever the FINDINGS say inferred |
| **[NV]** | NOT VERIFIED |
| **[arith]** | arithmetic done in this index from cited numbers (only in §2.12) |

**Citation shorthand.** `CR §2.1` means `results/crash_resilience/FINDINGS.md` §2.1. Result-file paths are relative to `results/`. Gap ids GF01–GF10 are the gaps filled in step 3. NG01–NG22 are the 22 gaps not filled, numbered in the order of `triage.not_filled` (table in §4).

| abbr | topic | abbr | topic |
|---|---|---|---|
| JP | jpeg_passthrough | CC | chromium_codecs |
| WT | write_throughput | CSS | chromium_sync_scrub |
| CR | crash_resilience | LIC | licensing |
| OV | overlays | PI | python_integration |
| UNC | uncompressed_intra | IC | intra_compare |
| GE | gpu_encode | IP | intra_playback |
| HW | hw_accel_target | JF | jellyfin_ffmpeg |

**Scope reminders (HANDOFF §1, §1.1).**
- Only intra-only formats are in scope; GOP results are background.
- The hardware target applies to the recording format itself, not an export copy. nvJPEG on CUDA counts as hardware.
- **Target A (SSIM-Y 0.9961, about 52 dB PSNR-Y) is fixed** as the primary operating point. Target B (PSNR-Y 45 dB) is the compact alternative. Dom ruled out the machine-vision test.
- All timing comes from one machine, Gerald (i7-14700K, RTX 3070, UHD 770). Benches were pinned to the P-cores (CPUs 0–15) and ran once in the quiet run `20261109T230007` (plus the OV-COST re-run `20261110T053653`). Tests use PyAV 19.0.2 (FFmpeg 9.0.2). PyAV 18 rows are background.

---

## 2. Per goal

### 2.1 G1: store camera JPEGs without transcoding

**Verified findings**
- [M] Passthrough is byte-exact with `add_mux_stream("mjpeg",rate,w,h)` + `av.Packet` + `mux()`: 194/194 outputs SHA-256-identical per packet, and 891/891 JPEGs found verbatim in the file bytes. Width and height are mandatory. PyAV 19.0.2. `JP §2.1`; `jpeg_passthrough/pyav19_recheck.json`, `verify_method_writer.json`.
- [M] Byte-exact round trip across 7 sets (1,862 JPEGs) × 5 variants (MKV real/index, fMP4 real, AVI real/index); container pts equal the sidecar. `PI F2`; `python_integration/pyav19_recheck_roundtrip_crash.json`.
- [M] No muxer changed any JPEG header. DHT-stripped frames stay byte-exact and decode to the same pixels. `JP §2.2`.
- [M] The time base sets timestamp error: MP4/MOV/NUT/fMP4 at 1/1e6 give 0 µs. MKV is fixed at 1/1000 (max error 470–499 µs), and frames under 1 ms apart share a pts. `JP §2.3`; `WT §2.5`.
- [M] With index (CFR) PTS, OpenCV count, 11/11 POS_FRAMES seeks and FreeMoCap reads are exact in all 18 index files: MKV+fp, MKV+fp+empty packet, fMP4 per-frame, fMP4 1 s; with drops and at 54,000 frames. **GF02: PyAV 19.0.2 writers; OpenCV 4.12 and FreeMoCap readers used read-only from the skellycam .venv.** `PI F3`, `JP §2.4`; `crash_resilience/gapfill/GF02_container_matrix.json` partA[].
- [M] With real VFR PTS: MKV miscounts (888 for 891; 53,819–53,820 for 54,000), and POS_FRAMES seeks miss in every container when frames drop (fMP4 9/11 even on gap-free c930e). PyAV pts seeks driven by the sidecar are exact (36/36, 34/34, 35/35). `JP §2.4`, `PI F3`; GF02 (same reader caveat).
- [M] OpenCV 4.12 has no configuration that returns JPEG bytes; today's recorder encodes inside the camera loop. `PI F1` (prior study + code).
- [M] The UI can fetch camera JPEGs from an MKV by byte range with an index: 450/450 byte-identical fetches per browser. Decoded by ImageDecoder and createImageBitmap. `IP F14`, `CC C28`.
- [M] All 88 real camera JPEGs (4:2:2 baseline) decode in E35/E45/C156 via ImageDecoder, createImageBitmap and `<img>`. `CC C25`.
- [M] The camera DQT is nearest IJG q94 in all 4 sets (not exact). `IC §2.2`; `intra_compare/camera_jpeg_quality.md`.
- [M] Lossless rotation (tj3Transform) costs 2.0–2.2 ms/frame at 720p and 6.8–8.9 ms at 1080p (quiet run). `JP §2.9.4`; `jpeg_passthrough/bench/bench_rotate_20261110T093546Z.json`.
- [M] Re-encoding camera MJPEG costs about 4 host cores for 12–16 × 1080p30 at A: CPU decode → h264_nvenc 4.06 cores (12 streams); mjpeg_qsv decode → h264_qsv 4.33 (16). `IC §2.5`, `GE §4 I8`.
- [M]/[I] On decoded camera MJPEG at A, H.264/HEVC re-encodes are 0.64–0.91× passthrough bytes, with one more generation of loss, so not at matched quality. [I] Passthrough is cheaper and more faithful. `IC §2.3/§4`, `HW Q4`.

**Ruled out / penalised**
- [M] MJPEG in `<video>`/MSE/WebCodecs in any container: fails in E35, E45 and C156 (C1–C3). JPEGs must be shown as images. `CC C1–C3, P1`.
- `add_stream_from_template` for passthrough: do not use. [M] It lost frames in MP4/MOV VFR and gave EINVAL in AVI. `JP §2.1, §4.1`.
- `add_stream(codec)` + extradata: never use. `WT §4.12`.
- `mjpeg2jpeg` bsf: not byte-exact. `JP §2.2`.
- MKV for FreeMoCap-compatible files **with real VFR PTS**: JP rules it out. JP now scopes that ruling to real PTS and records that index PTS gave exact counts (GF02). `JP §4.8`. See §3.
- NUT, AVI, raw .mjpeg, WebM (refuses MJPEG): ruled out. `JP §4.8`, `CR §4.1`.
- Re-encoding MJPEG cameras: passthrough stays the baseline at A. `IC §4`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Camera JPEG SSIM-Y/PSNR-Y against raw, i.e. passthrough's position on the A/B scale | `JP` header, §6; `PI §6` | NG21 accept_not_verified: state "q94-equivalent quantisation; fidelity vs A NOT VERIFIED"; back-to-back capture is a task for Dom |
| Why camera 1080p JPEGs (134,574 / 192,382 B) are much smaller than q94 on YUY2 (260,827 / 312,812 B) | `IC §6` | NG09 functional: re-encode with the camera's own DQT; compare high-frequency energy; final cause stays NV without captures |
| Passthrough timing on the cameras' own bytes in the UI (benches used mjpeg_qsv proxies) | `IP P3, §6`; `CC §5` | NG15 timed (IP-SEEK/IP-SYNC on camera JPEG bytes) |
| MP4/MOV/NUT mux cost at 1/1e6; cold opens; 1080p or 60+ min files; >4 GiB | `JP §6` | no gap raised |
| Rust rotation parity, multi-threaded rotation | `JP §6` | no gap raised |

### 2.2 G2: resumable, crash-tolerant files

**Verified findings**
- [M] Live paced kills under GF02 (48 kills at 30 fps, `os._exit` and TerminateProcess), frames lost per kill:
  - MKV+fp: 1;
  - fMP4 per-frame+fp: 1;
  - fMP4 1 s+fp: 1–30 (real PTS 14–29, index 1–30);
  - MKV+fp+empty timestamped packet: 0 in 12/12.
  - Sidecar records equal acked frames in 48/48, and `recover()` matched the byte-exact prefix in 48/48. No torn tail occurred.
  - GF02 used PyAV 19.0.2 writers with OpenCV 4.12/FreeMoCap readers read-only from the skellycam .venv.
  - `CR §2.1`, `WT §2.2`, `JP §2.5`; `crash_resilience/gapfill/GF02_container_matrix.json` partB[].
- [M] WT's kills (PyAV 19, 720p60, 2 per variant), frames lost: files 0,0; append 0,0; mkv 3,4; mkv_flush 1,1; fmp4_frame_flush 1,1; fmp4_1s 33,62; fmp4_1s_flush 46,5; hybrid 1,4; mkvseg10 4,5. The empty-packet MKV lost 0 in 3/3 kills at 60 fps. `WT §2.2, §2.3`.
- [M] Drained MJPEG kill of 150 frames: mkv+fp 149; fmp4_every+fp 149; nut/avi+fp 150; plain mp4 0. Without fp, files are multiples of 262,144 B, and fMP4/NUT hand out a torn frame. `CR §2.1`; `crash_resilience/pyav19_recheck.json`.
- [M] Prefix cuts (power-loss emulation): MKV+fp never handed out a torn sample (0/12); fmp4_every+fp did 12/12, nut+fp 12/12. `CR §2.4`; `truncation_pyav19.json`.
- [M] Intra NVENC H.264/HEVC live kill into MKV+fp: 3 of 75 lost (2 held by the encoder, 1 in the open Cluster). One kill per codec. `delay=0` makes hold-back 0 (hold count only). `CR §2.5`.
- [M] Encoder hold-back: NVENC returns a packet 2 encode() calls late, h264/hevc_qsv 4, mjpeg_qsv 3; JPEG returns in the same call. [I] That is about 67 ms (NVENC) and 100–133 ms (QSV) lost on a crash at 30 fps. `IC §2.5 F2`.
- [M] A torn tail JPEG decoded silently in 5 of 6 PyAV 19 cases. `WT §2.2`. A CRC sidecar (binary record or CSV flushed per row) survives a kill; pandas read_csv gave wrong integers in 6/24 cuts. `CR §2.9`.
- [M] Repair of a killed 1 GB recording (quiet run, warm cache): MKV+fp 0.907 s/GB; fmp4_every+fp 1.345 s/GB; MKV/fMP4 return 17,617/17,618 frames; plain MP4 returns 0. `CR §2.13`; `crash_resilience/bench/repair_pyav19.json`.
- [M] A resumable prototype (journal + per-segment MKV+fp + CRC sidecar) works on PyAV 19 across kill, double crash and cut. `CR §2.8`; `resumable_demo_pyav19.json`.
- [M] Costs (quiet run):
  - flush_packets=1 on MKV adds +4.9 µs/frame (MJPEG), 2.7 (H.264 intra), 3.0 (HEVC intra).
  - Overhead is 45.8 B/frame for MKV, 131.3 for per-frame fMP4 and 12.5 for 1 s fMP4.
  - fsync per frame: p50 409 µs, max 8.7 ms; K=30 p50 16.1 µs.
  - The intra payloads are "not target A results".
  - `CR §2.11, §2.12`; `crash_resilience/bench/fsync_pyav19.json`, `fragment_overhead_*_pyav19.json`.
- [M] Unfinalized MKV/AVI in OpenCV 4.12: FRAME_COUNT is −2.767e17 (MKV) or 0 (AVI), and POS_FRAMES seek silently returns frame 0. fMP4+fp counts correctly. PyAV seek on unfinalized MKV/fMP4 is exact. `CR §2.2`.
- [M] New defect: `recover()` on a real-PTS MKV writes r_frame_rate 125/2, so cv2 reports 62.5 fps and about 2.1× the count, in 12/12. Index-PTS MKV and all fMP4 recover correctly. GF02 (reader caveat as above). `CR §4.1`, `PI F6`; `GF02_recovered_rates.txt`.
- [M] The empty-packet MKV has two seek defects: killed files seek 1 frame late (12/12), and on finalized files the last-frame seek returns nothing (8/8). It adds +6.0 B/frame. `CR §2.2`, `WT §4.4`.

**Ruled out / penalised**
- Plain MP4/MOV as the recording format: **ruled out** ("Never record to plain MP4"). 0 frames after a kill, and it cannot be remuxed at 1 GB. This covers today's MSMF path and sfn26. `CR §4.4, §2.10`; `JP §4.7`; `UNC §4.8`.
- FFmpeg segment muxer: **ruled out**; use application-level segments. It ignores flush_packets. `CR §4.5`.
- NUT/AVI/raw+index: rejected for torn frames and bad seeks. `CR §4.1, §3A`; `UNC §4.8` (18/275 silently corrupted cut frames, all NUT/AVI).
- fMP4 per-frame: **penalised, not ruled out** ("Prefer MKV over per-frame fMP4"): torn samples after cuts, slow open, +48% repair. `CR §4.11`; `WT §4.4`.
- fMP4 1 s: **penalised** by 1–30 lost frames per kill (`CR §3A`). WT says "Avoid … 1 s fragments" (`WT §4.8`). JP keeps it as "a container candidate" (`JP §4.2`). See §3.
- hybrid_fragmented: avoid (0 frames after a 50% cut). `WT §4.8`.
- OpenCV on unfinalized MKV/AVI: unusable. "Finalize before any OpenCV reader." `CR §4.7`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| QSV encoder hold-back under a live kill; NVENC delay=0 kill and its cost | `CR §6`; `IC §2.5` | NG06 functional: 3 live kills each, h264/hevc/mjpeg_qsv (default and async_depth=1) and h264_nvenc delay=0, MKV+fp, PyAV 19 |
| Killed intra NVENC and JPEG-index files played in Electron | `CR §6`, `§2.7` | NG07 functional: reuse GF02's killed files; E35/E45 `<video>` mid seek, WebCodecs, Range+CRC ImageDecoder |
| Torn tail under live kills (GF02 had none) | `CR §6`, `PI §6`, `JP §6` | no gap raised (CR §2.4 stays the torn-tail evidence) |
| Real NTFS power loss / OS crash | `CR §6`, `WT §6` | none (critic gap "real power loss" was priority 3 and not carried into triage) |
| Mechanism of the empty-packet seek defects; its write cost; third-party parsers; more than 3 kills at 60 fps; kills that cut a write | `CR §2.2, §8`; `WT §6` | no gap raised |
| Cause of the recover() 125/2 rate (fix needed before MKV with real PTS can rely on it [I]) | `PI §6`, `PI §4.3`; `JP §6` | no gap raised |
| FreeMoCap on killed/recovered files; multi-camera durability cost; cold-cache repair | `CR §6`, `PI §6` | no gap raised; multi-camera cost is part of NG11 timed |

### 2.3 G3: overlays as a separate layer

**Verified findings**
- [C] Today skellycam burns the overlay into every frame with cv2.putText and keeps no clean copy. The UI draws HTML labels over `<video>` with frame = floor(currentTime·fps). `OV §2.1`; `opencv_get_frame.py:79-90`, `SyncedVideoPlayer.tsx:377-403`.
- [M] Sidecar write cost for the full "all" overlay at 720p (quiet re-run): .skov (CRC) 29.3 µs/frame, MessagePack 23.7, JSONL 125.4, WebVTT 128.3. All are at most 0.4% of a 33.3 ms frame. `OV §2.2`; `overlays/bench/bench_overlay_cost_20261110T103707Z.json`.
- [M] Size: .skov 3,282.9 B/frame (354.55 MB/h), JSONL 5,697.7, MessagePack 6,890.3. `OV §2.2`.
- [M] Crash modes: all four sidecars recovered every complete record at 28/28 clean cuts. Only .skov rejected a corrupted byte. MessagePack stopped at a 4 KiB zero hole. `OV §2.2`; `overlays/verify_method_crash_modes.json`.
- [M] Burn-in of charuco/all costs 16.5–16.7 ms/frame (about 50% of a frame). With G1 passthrough, even a text stamp needs decode + draw + re-encode: 3.43 ms (720p) / 7.68 ms (1080p). `OV §2.6`.
- [M] rVFC mediaTime looked up in the pts table matched the drawn frame in 255/269 to 299/299 callbacks at 1×. `OV §2.3.1`.
- [M] Canvas over `<video>` matched only 51/275 captures (overlay 1–3 frames behind). Drawing the video into the overlay canvas matched 111/112. `OV §2.3.2`.
- [M] Canvas draw with placed labels: median 1.1 ms (E35) / 0.9 ms (E45); SVG DOM 18 ms. The label placer gave 0 overlaps. `OV §2.8`; `overlays/bench/electron_drawbench_*.json`, `label_layout.json`.
- [M] Export burn-in works on PyAV 19.0.2 (60/60 aligned). The wheel has no ass/subtitles/drawtext filter. `OV §2.7`.

**Ruled out / penalised** (OV §4 recommendations are labelled [I])
- Burn-in at record time: ruled out ("Never burn them in at record time"). `OV §4, §2.6`.
- MessagePack without a resync marker: "Do not use". SVG/ASS as the recorded format: "Do not use" (5–11× size, 11–32× cost; SVG fails strict parse at 25/25 cuts). `OV §4`.
- JSONL: penalised; .skov preferred. `OV §4`.
- Alpha video layer (VP9 alpha): dropped at record time (rasterising alone takes 34.7–113.1 ms/frame); kept only for export. PNG-MOV and QTRLE-MOV fail in Chromium. `OV §2.5, §4`.
- Canvas layered over `<video>` where pairing matters: "Do not layer". floor(currentTime·fps): replace with rVFC mediaTime. track.activeCues and in-band text tracks: ruled out. presentedFrames or droppedVideoFrames alone for drop detection: ruled out. `OV §4`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Overlay pairing on the master-clock canvas player (WebCodecs/ImageDecoder) and on intra-only files (OV clips were PyAV 18 GOP 30) | `OV §5, §6` | NG03 functional: draw .skov for frame k in the canvas for JPEG ImageDecoder and WebCodecs intra at N=4/8, barcode readback, untimed; draw cost later on a quiet machine |
| E35 last-frame lock-up workarounds | `OV §6` | NG02 functional (see §3) |
| Real (non-synthetic) overlay sizes and costs; sidecar flush/fsync cost; 16 writers; writer killed mid-record | `OV §6` | no gap raised (end-to-end cost is in NG11 timed) |
| Many-tile draw cost; display refresh not recorded | `OV §6` | no gap raised |

### 2.4 G4: other uncompressed formats (Bayer, NV12 and others), intra-only

**Verified findings**
- [M] h264_nvenc lossless NV12 1080p (quiet run): 516 fps, 0.045 cores, 593.6 KB/frame, single-thread software decode 103 fps (High 4:4:4 Predictive). `UNC §2.7, §3.1`; `uncompressed_intra/bench/h264_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json`.
- [M] hevc_nvenc lossless NV12 1080p: 302 fps, 0.048 cores, 517.7 KB/frame, but single-thread software decode is only 29 fps. `UNC §2.7, §3.1`.
- [M] All ten timed NVENC lossless configs re-encode bit-exact over 300 frames with software, cuvid and cuda decode. d3d11va rejects H.264 High 4:4:4 Predictive. GF09. `UNC §5, §4.1`; `uncompressed_intra/gapfill/GF09_rows_nvenc_pyav19.0.2.json`.
- [M] E35 and E45 play both NVENC lossless formats from MKV and MP4. Seeked frames read back bit-exact YUV. H.264 lossless decodes in software, HEVC in hardware. GF09. `UNC §2.11`; `GF09_chromium_electron{35,45}.json`.
- [M]/[C]/[S] **Quick Sync cannot encode lossless** (GF09):
  - [M] 0/300 exact frames in all 32 h264_qsv/hevc_qsv configs that opened (UHD 770, driver 32.0.101.7088).
  - [M] A requested QP 0 runs at QPI 1; low_power or 4:4:4 runs at QPI 10.
  - [C] FFmpeg n9.0.2 qsvenc has no lossless option.
  - [S] oneVPL: "Zero QP is not valid".
  - `UNC` header, §2.5; `GF09_qsv_lossless.md`.
- [M] Pitfall: hevc_qsv low_power=1 on YUY2 silently writes 4:2:0 Main. `UNC §2.5`.
- [S] FFmpeg truncates every 12/16-bit NVENC input to 10 bits, so there is no exact 12-bit NVENC path. `UNC §2.5`; `nvenc.c:58-68`.
- [M] 8-bit Bayer quad split through NVENC lossless is exact over 300 frames (h264 772.6 KB, hevc 685.1 KB; synthetic Bayer). `UNC §2.5`.
- [M] CPU fallback (outside the target): FFV1 v3 on YUY2 1080p reaches 44–45 fps single-thread at about 0.67 cores. FFV1 Bayer12 manages 11–12 fps at 2.6 cores and cannot hold 30 fps. Rawvideo needs 62–124 MB/s per stream. `UNC §2.7, §3.2`.
- [M] Truncation: 18/275 lossless MKV/NUT/AVI cases returned a silently corrupted cut frame, all NUT/AVI, none MKV. Every MOV/MP4 decoded 0 frames. `UNC §2.4`.
- [M]/[S] PyAV refuses Matroska for ffvhuff, utvideo, magicyuv, jpegls, png and dnxhd (PyAV's compliance gate). `UNC §2.2`.

**Ruled out / penalised**
- QSV lossless: ruled out on the UHD 770 ("answered, not available"). [I] So the G4 lossless formats are NVIDIA-only and **do not meet the hardware target**. `UNC` header, §2.5, §4.1.
- FFV1, rawvideo and all CPU codecs: outside the hardware target; G4 CPU fallback only. FFV1 does not play in Chromium. `UNC §3.2`, `CC C4`, `LIC §4`.
- HEVC lossless: penalised on decode (29 fps single-thread software). `UNC §4.1`.
- YUY2 4:2:2 has no exact hardware recorder on RTX 3000 (NVENC 4:2:2 starts at Blackwell). Bayer12/gray16 have no exact NVENC path. `UNC §4.3, §4.4`; `HW N2`.
- FFV1 v4: experimental, not in RFC 9043. AV1 lossless: outside the RTX 3000 + Intel intersection [I]. `UNC §2.6, §6`.
- A 16-camera NVENC plan does not fit one RTX 3070 (12-session cap, measured lossy; NV for lossless). `UNC §4.9`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Lossless on AMF, VideoToolbox, other Intel generations, other RTX 3000 SKUs | `UNC §6` | NG18 accept_not_verified |
| Hardware/threaded decode speed of NVENC lossless | `UNC §6` | no gap raised |
| FFV1/rawvideo timed streams checked for exactness over 300 frames (only 1–8 frame checks); no lossless check inside the timed bench | `UNC §5, §6`; summary §3 flag 9 | no gap raised |
| NVENC timing on Bayer8 quad, packed 10/12-bit, RGB | `UNC §6` | no gap raised |
| Real Bayer and real 10/12-bit sensor data; whether the cameras deliver 1080p30 YUY2 | `UNC §2.1, §6` | no gap raised (needs camera access, requirement 11) |

### 2.5 G5: throughput wrapper, or proof that it doesn't matter

**Verified findings**
- [M] No wrapper dropped a frame: 77/77 cells had 0 drops up to 16 × 1080p60, including three 10-minute cells at 156.94 MB/s (quiet run, PyAV 19.0.2). `WT §2.8`; `write_throughput/bench/long_av19/*.json`.
- [M] Defender CPU per 30 s cell: folder of files 26.8 s; append 1.19; mkv_flush 1.52; fmp4_frame_flush 1.16 (idle 1.23–1.53). Over 10 min: files 558.7 CPU-s vs mkv_flush 25.7. `WT §2.9`; `write_throughput/bench/focus16_av19/`.
- [M] Write latency at 16 × 1080p60 (p50 / p99.9): files 2.111 / 20.3 ms; append 0.553 / 1.72; mkv_flush 0.808 / 2.85; fmp4_frame_flush 0.853 / 3.18. `WT §2.10`.
- [I] Giving up a standard container saves 0.25–0.52 ms per write at p50 and 0.23–0.39 logical CPUs (append vs mkv_flush), which is "not enough on its own". `WT §4.2`.
- [M] Mux cost at 720p: containers 16.1–20.8 µs/frame vs folder of JPEGs 217.9 (1080p: 46.4–60.2 vs 232.5). `JP §2.9.1`; `jpeg_passthrough/bench/bench_mux_default_pyav19_20261110T055215Z.json`.
- [M] Warm open+count of a 30-min file: MKV 0.19 ms; finalized MP4 2.4; fMP4 1 s 42.6; fMP4 per-frame 1107 (cv2) / 1224 (PyAV). `JP §2.9.3`; `jpeg_passthrough/bench/open_long.json`.
- [M] RecordingWriter `write()` median: MKV 0.033 ms (720p) / 0.10–0.11 (1080p). The folder is 2.5–6.8× that, and its worst call was 10.41 ms. A 10-min file opens in 3.68 ms (MKV) vs 371.96 ms (per-frame fMP4). `PI F11, F13`; `python_integration/bench/recwriter_quiet1_pyav19.json`.
- [M] After recording 18,000 frames: the first sequential read takes 78.36 s for files vs 0.18–0.20 s for append/MKV. Deleting a 10-min 16-camera recording takes 53.0 s vs 4.4 s. `WT §2.12`; `write_throughput/bench/usability/`.
- [M] A shared writer process vs a thread per camera: both had 0 drops. The shared process raised tick→written p99 1.25–2.1×. `WT §2.11`.
- [M] PyAV 19 releases the GIL around mux, header, trailer and close. A bump needs requires-python ≥ 3.12. `PI F7, F8`.

**Ruled out / penalised**
- Folder of JPEGs:
  - [M] Its costs: Defender CPU, the worst tail latency, a 4 ms first read per file, a 53 s delete, readers that stop at gaps, and no crash advantage. `WT §4.1`.
  - WT: "Do not make a folder of JPEGs the default layout" (strongly penalised).
  - CR: "Don't record to a folder of JPEGs" (ruled out). `CR §4.12`.
  - JP: "the expensive and incompatible option" (penalised, not formally ruled out). `JP §4.4`.
  - PI: "slow outlier". `PI §4.4`.
  - The topics differ in strength only. None measured a benefit.
- AVI: "not a candidate". `PI §4.4`.
- A custom raw+index format solely for speed: [I] not justified by the 0.25–0.52 ms saving. `WT §4.2`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| End-to-end recorder (encode + MKV+fp + CRC sidecar + overlay sidecar at 12–16 × 1080p30) | `IC §6` (writing not tested), `WT §6` | NG11 timed: N=12 NVENC, N=16 QSV and mjpeg_qsv_422; drops, p99.9, cores, MsMpEng; 3 × 60 s + one 10-min cell |
| Cause of tonight's higher latencies (P-core pinning [I]) | `WT §2.10`; summary §3 flag 7 | no gap raised |
| Variants not in the paced cost matrix, FFV1 wrapper cost, Defender exclusions, other disks/OSes | `WT §6` | no gap raised; other OSes are under NG18 |

### 2.6 G6: GPU-accelerated encode on as many platforms as possible

**Verified findings**
- [M] On Gerald through PyAV 19.0.2, these encoders work: h264/hevc_nvenc, h264/hevc_d3d12va (MP4 only), h264/hevc_mf, and h264/hevc/vp9/mjpeg_qsv. All 26 working outputs decode 32/32. AV1 fails everywhere (av1_nvenc/qsv/mf/d3d12va). `GE §2.2, §3.1`.
- [M]/[S] NVENC opens at most 12 sessions; the 13th fails with ExternalError. [S] The NVIDIA matrix gives 12 for the RTX 3070. NVENC, D3D12 and MF share the pool; QSV is outside it. `GE §2.4`, `IC §2.6`, `HW N10`; `verify_method_pool.json`.
- [M] Capacity at target A, paced 1080p30 (largest tested N in 1/4/8/16; encode only; no QC in the scaling runs):
  - h264_nvenc 12 at 0.61 cores; hevc_nvenc 12 at 0.65;
  - h264_qsv 16 at 1.25; mjpeg_qsv 4:2:2 (YUY2) 16 at 0.92; mjpeg_qsv 4:2:0 16 at 1.05;
  - nvJPEG NV12 8 at 2.56; nvJPEG 4:2:2 YUY2 16 at 4.68 (5.3–13.3% late);
  - hevc_qsv 1;
  - libjpeg-turbo 4:2:0 / 4:2:2 16 at ≥1.69 / ≥2.81 cores (process workers, lower bound).
  - `IC §3.5`, `HW §3.3.1`; `hw_accel_target/gapfill/GF04_capacity.json`, `intra_compare/bench/matched_concurrent_*.json`.
- [M] hevc_qsv tops out at 66–67 fps aggregate at 1080p (4 streams keep up at 720p) and loads the iGPU 3D engine to 89–91%. `IC §2.5, §2.4`.
- [M] Single stream at A from NV12: h264_nvenc 540 fps; h264_qsv 585; hevc_nvenc 390; hevc_qsv 65; mjpeg_qsv_420 602; libjpeg-turbo 4:2:0 360. `IC §2.4`; `matched_stream_A_1080p_20261110T042204Z.json`.
- [M] mjpeg_qsv chroma follows its input: yuyv422 in gives yuvj422p, nv12 in gives yuvj420p. hevc_qsv fed YUY2 gives Rext 4:2:2. `GE §2.7`, `IC §2.1`.
- [M] nvJPEG per feed at A 1080p: NV12 or YUY2 via swscale hits A (52.34 / 52.37 dB); after mjpeg_qsv decode it hits A (56.46 dB). CPU-decoded MJPEG through swscale rgb24 **misses** (SSIM-Y 0.9954, 45.21 dB; at B 43.14 dB). `IC §2.7`, `HW §3.3.1`, `GE §2.7`.
- [S]/[M] nvJPEG on GeForce runs on the CUDA backend; fixed-function JPEG encode exists only on Jetson Thor. [M, static parse] The wheel DLL has SASS for sm_75/86/89/120. RTX 30 is measured; RTX 20/40/50 have the code present but were not run. GF03. `HW N6, N13`; `licensing/gapfill/GF03_nvjpeg_licence_arch.md`.
- [M]/[C] Pitfall: FFmpeg's default i_qfactor lowers the intra QP (requesting 25 gives 20 on NVENC/QSV). Fix: i_qfactor=1, i_qoffset=0 (NVENC/QSV only). `IC §2.8`, `GE §2.10`, `HW K3`.
- [C]/[S] AMF all-intra needs gop_size=1 (gop_size=0 is **not** intra on AMF) and rc=cqp/qp_i. VideoToolbox needs an explicit gop_size=1 (default 12); quality is global_quality only, with no constant QP in n9.0.2. GF06; not run on hardware. `HW A8, P5, K6`; `hw_accel_target/gapfill/GF06_amf_vt_intra.md`.
- [M] YUY2→NV12 swscale for NVENC raised CPU from 0.60–0.64 to 2.41–2.64 cores at 12 × 1080p30. NVENC does not take yuyv422. `GE §2.8`.
- [M]/[S] PyPI wheels: win_amd64 has NVENC, QSV, D3D12VA, MF and h264/hevc_amf. manylinux has NVENC, QSV av1/vp9, AMF av1 and V4L2 m2m, with no VAAPI/Vulkan. macOS has VideoToolbox H.264/H.265/ProRes. `GE §3.5`, `JF F22`.

**Ruled out / penalised**
- AV1 and VP9 hardware encode on the target: no RTX 3000 AV1 or VP9 encode (`HW N1–N3`), and AV1 fails on Gerald (`GE §2.2`). See §2.10.
- hevc_qsv default mode for multi-camera at 1080p: "not a multi-camera path as configured" (1 stream). GE: do not rule it out until low_power is timed. `IC §4`, `GE I5`.
- nvJPEG fed swscale-RGB from CPU-decoded MJPEG: misses A and B, so it is not a camera-MJPEG re-encode route. `IC §4`, `GE I8`.
- NVENC alone for 16 cameras: the cap is 12. `IC §4`, `HW §4.6`.
- libx264/libx265 as a many-camera CPU fallback: [I] "JPEG is the only practical CPU fallback for many cameras on this CPU". libx265 must not open in a pinned capture process (it widens affinity). `IC §4`.
- NVDEC decode of the cameras' 4:2:2 MJPEG: fails (mjpeg_cuvid, cuda). `GE §2.6`, `HW N5`.
- D3D12 into MKV fails (291-byte file). `GE §2.2`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| More than 12 NVIDIA cameras (NVENC + QSV / nvJPEG / CPU mix); cap across processes | `IC §4, §6`; `GE §6.2` | NG10 timed: 12 nvenc + 4 qsv, + 4 nvjpeg_422, + 4 jt422 process workers; optional functional 6+6 sessions across 2 processes |
| hevc_qsv low_power/VDEnc at A | `IC §6`, `GE §6.2`, `JF §5` | NG13 timed: functional QC sweep, then IC-SCALE at N=1/4/8/16 |
| nvJPEG with GPU-side YUV→RGB (or a planar-YUV binding) | `IC §4, §6`; `GE §2.7`; `HW N9` | NG14 timed: CuPy into an nvImageCodec device image keeps A, then timing at N=8/16 |
| Scaling at target B; h264_qsv/mjpeg_qsv 4:2:0 × 16 from YUY2 | `IC §6` | NG15 timed |
| CPU fallback capacity on lower-end or no-iGPU CPUs | `IC §6`; `HW §6` | NG12 timed proxy / effectively accept_not_verified: state NV; optional proxy pinned to 4 E-cores |
| nvJPEG on RTX 20/40/50; AMF/VT intra and quality on real hardware; any *_qsv outside RPL-S | `HW §6`, `GE §6.2` | NG18 accept_not_verified |
| Whether the post-libx265 single-stream cells stayed on P-cores | `IC §5 flag 1`; summary §3 flag 2 | no gap raised |

### 2.7 G7: royalty-free codecs where possible

**Verified findings**
- [S] Baseline JPEG: T.81 Annex L lists patents only for arithmetic coding and hierarchical lossless. [M] All 1,862 corpus frames are SOF0 baseline Huffman. `LIC §2.1, §2.7`; `HW R1`.
- [S] H.264 and HEVC are royalty-bearing:
  - Via LA AVC: $0.00 for the first 100,000 units, then $0.20/$0.10.
  - HEVC: $0.00 for 100,000, then $0.30/$0.20.
  - Access Advance took over the HEVC program on 2025-12-15.
  - `LIC §2.1` (Q29–Q34); `HW R2`.
- [S] AV1 (AOM licence) and VP9 (Google grant) are royalty-free from the developers. Sisvel offers royalty-bearing pools for both. `LIC §2.1`, `HW R3`.
- [S]/[M] FFV1 has 0 IETF IPR disclosures, but no positive royalty-free declaration. Matroska has 0 IETF disclosures; ISO BMFF is NV. `LIC §2.1, §2.2`.
- [S] The NVIDIA Video Codec SDK and the CUDA EULA grant no codec patent rights. `LIC` Q48/Q49.
- [M]/[C] The PyAV 19.0.2 wheel ships GPL-2.0+ libx264/libx265 DLLs; deleting them breaks `import av`. `LIC §2.5`, `HW R4`.
- [S] libjpeg-turbo is BSD-style and simplejpeg MIT; neither is a patent grant. `HW R6` (GF04).
- [S] nvImageCodec/nvJPEG licences (GF03):
  - Redistribution is allowed only inside an application with material added function, and the software may not be made subject to an open-source licence.
  - The nvImageCodec wheel carries the NVIDIA SLA, while PyPI/GitHub say Apache-2.0.
  - SLA §2.11 bars publishing benchmarks without permission.
  - [I, not legal advice] An optional pinned pip extra is low-risk. Bundling in an installer needs legal review.
  - `LIC §2.4`, `HW R5`; `licensing/gapfill/GF03_nvjpeg_licence_arch.md`.
- [M] skellycam today: cv2.VideoWriter picks MSMF and writes H.264. `LIC §2.6`.
- [I]/[M] The cost of choosing JPEG at A (sweep basis, YUY2 1080p), JPEG bytes as a multiple of hardware intra:
  - vs H.264: 1.7–1.9× (jt422) or 1.5–1.7× (jt420);
  - vs HEVC: 2.3–2.5× (jt422) or 2.1–2.3× (jt420);
  - at B: 2.8–3.5× (H.264) and 5.4× (HEVC) vs jt422.
  - `IC §4`. HW gives a wider range with nvJPEG and mjpeg_qsv included (about 1.3–2.5× at A); see §2.12 and §3.
- [S]/[I] "JPEG is the only format with no listed patents (R1) that is accelerated on both RTX 3000 and Intel TGL-RPL iGPUs." `HW §4.2`. The target and G7 conflict for re-encoded formats, and the plan must say so. `HW §4.1`.

**Ruled out / penalised**
- No royalty-free *video* codec meets the hardware target. `HW §4.1` (kept after verification, §8.3).
- VP9 via QSV is royalty-free-licensed but fails the target (no NVIDIA/AMD/Apple VP9 encode). `LIC §4`, `HW §3.3`.
- ProRes (Apple calls FFmpeg's implementation "unauthorized") and AAC: avoid. `LIC §4`.
- Bundling the nvJPEG/nvImageCodec wheels in an installer without legal review: avoid [I]. Bundling stock PyAV must meet GPL/x264 terms or use a custom build [I]. `LIC §4`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| H.264/HEVC royalties for free AGPL software using GPU/OS encoders; who bears royalties for MF, VT and Electron decode | `LIC §2.4, §5`, Q29–Q34 | NG19 accept_not_verified: state NV (not legal advice), quoting Q29–Q34; optional Via LA licensor FAQ |
| ISO BMFF patent status (iso.org 403) | `LIC §2.2` | NG20 accept_not_verified: Matroska 0 IETF disclosures, ISO BMFF NV; keep both |
| Which licence governs the nvImageCodec wheel (SLA vs Apache-2.0) and the nvjpeg wheel (2018 vs live EULA); whether an installer is an AGPL "aggregate" | `LIC §2.4, §7.2`; `HW R5`; `GE §6.2` | no gap raised (GF03 left it for legal review) |
| A custom PyAV build without x264/x265 | `LIC §2.5, §5` | no gap raised |

### 2.8 G8: native playback in the Chromium (Electron) UI

**Verified findings**
- [M] All 48 PyAV 19 NVENC/QSV H.264/HEVC intra clips (mp4/fMP4/mkv, 720p/1080p, CFR/VFR) play and seek exactly: `<video>` mid 4800/4800, WebCodecs 4800/4800 and steps 5856/5856 per browser in E35, E45 and C156. Clips are at about 55 dB, not A or B. `IP F1–F3`, `CC C8`; `intra_playback/F/seek_*.json`.
- [M] Every timed seek was exact (200/200 in 24 configs, N=1). `IP F17`; `intra_playback/bench/*/bench_intra_seek/*.json`.
- [M] Seek p50, E45 (about 55 dB clips): WebCodecs 2.7–2.9 ms; JPEG ImageDecoder 4.6; createImageBitmap 6.0–6.1; `<video>` to rVFC 8.5–14.1. `IP F18`.
- [M] HEVC has no software decode in E35/E45/C156 (WebCodecs prefer-software "config not supported"). H.264 has FFmpegVideoDecoder. `IP F10`, `CC C14`.
- [M] h264_nvenc intra needs flush() after each chunk in WebCodecs (360/360 fallback flushes; others 0). The SPS has bitstream_restriction_flag=0 [M]; the decoder-holding cause is [I]. `IP F11, F12`, `CC C21, C22`.
- [M] HEVC 4:2:2 (hevc_qsv from YUY2, one 720p MKV): E35 gives MediaError 4 (demuxer); E45 gives PIPELINE_ERROR_DECODE. The 4:2:0 control plays. Probes still say "probably". `CC C17, C17a`; `chromium_codecs/raw/verify_method_rechecks.json` → `hevc422_probe_and_play.play_file_url`.
- [M] libx265 all-intra 4:2:0 is Rext (ffprobe, GF05). One CLI sample fails in E35 and plays in E45. `UNC §2.11`, `IC §2.1`; `chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`.
- [M] PyAV 19 AV1 and VP9 all-intra play via `<video src>` in all three browsers (10/10 seeks). `CC C7`.
- [M] Only 4:2:0 streams got D3D11VideoDecoder; 4:4:4/4:2:2 went to software decoders (background). `CC C13`.
- [M] Serving: HTTP with Range, file:// and a Range-parsing protocol.handle all seek exactly. Without Range, or through a net.fetch(file://) passthrough, seeking breaks. `CC C29–C31`.
- [M] JPEG path: `.mjpeg`+index or JPEG-in-MKV+index by Range seeks 800/800 and steps 976/976 per decode path per browser. `IP F4`, `CC C27`.
- [M] E35, E45 and C156 give the same intra-only play/seek/MSE/WebCodecs results, except partially tagged AV1 MAD, libx264 WebCodecs and HEVC 4:2:2. `CC C33`.

**Ruled out / penalised**
- MJPEG in `<video>`/MSE/WebCodecs: no. `CC C1–C3`, `IP F13`.
- FFV1 and rawvideo: do not open. `CC C4`.
- HEVC 4:2:2 for the UI: [I] "not a safe recording format"; P5: record 4:2:0. `IC §4`, `CC P5`.
- libx265 output for the UI: "Avoid" (Rext; fails in E35). `IC §4`.
- HEVC-only recordings: penalised (no software fallback; HEVC fails after the GPU falls back to disabled_software). `IP P5, P7`.
- canPlayType/probes as a gate: unreliable (E35 says "" for MKV it plays; Rext probes say "probably" for a file that fails). `CC P9`, `IP F15`.
- MSE with Matroska: not supported (background). `CC C19`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| `<video>` software-decode fallback; Intel-adapter decode (all QSV files were decoded on NVIDIA) | `CC §6, C14`; `IP F9, §6` | NG04 functional: intra_functional in E35/E45 with --disable-accelerated-video-decode; adapter switch only if a Chromium flag exists |
| A primary source for Chromium HEVC decode requirements (hardware-only?) per OS | `CC §6` (no source cited) | NG05 source: Chromium 134/156 `supported_types.cc` and enable_platform_hevc, quoted file:line |
| PyAV-made libx265 all-intra clips in Electron (beyond one 8-frame CLI sample) | `IP F16, §6`; `IC §6` | NG08 functional: PyAV 19 libx265 clips at A (mp4/fMP4/mkv, CFR/VFR, 720p/1080p), intra_functional E35/E45 |
| Playback exactness and cost on clips at target A or B | `IP P9, §6` | NG16 functional (exactness at A); NG15 timed (cost) |
| HEVC 4:2:2 in C156; AMD/Apple/Linux/macOS decode; machines without HEVC hardware | `CC §6`, `IP §6` | NG18 accept_not_verified |
| vp9_qsv, *_mf and *_d3d12va output playback | `CC §6` | no gap raised |

### 2.9 G9: synchronized, frame-accurate playback and scrubbing

**Verified findings**
- [C] Today's UI uses one `<video>` per camera. It seeks with k/fps, reads frame = currentTime·fps, and gets fps from the CSV. `CSS F1–F4`; `SyncedVideoPlayer.tsx:332-335`.
- [M] Today's k/fps rule on the one intra VFR file: 34/200 seeks, 0/122 steps. (k+0.5)/fps: CFR 2400/2400 but VFR 228/2400. The real-pts midpoint and the file's pts are exact. `CSS F10a`, `IP F5, F6`, `CC C10`.
- [M] Master-clock sync (WebCodecs and JPEG paths) at N=4 and N=8: spread 0 on 100% of ticks in all 28 configs, both Electrons. The spread is index-based, on identical clips. `IP F19`; `intra_playback/bench/*/bench_intra_sync/*.json`.
- [M] Master clock at N=8, E45 (about 55 dB clips):
  - WebCodecs 0.51–0.57 cores (GPU decode not counted), 872–1104 MB;
  - ImageDecoder 1.44 cores;
  - createImageBitmap 2.14 cores.
  - `IP F20`.
- [M] N=8 `<video>` stalls: in 19/20 configs the slowest tile got 42–60% of the median's rVFC callbacks, and max spread was 100–245 frames. At N=4, 5.9–8.4% of frames dropped. `IP F21`.
- [M] Sync by capture timestamp (GF08: 4 cameras built from real c930e/c922 timestamps, offsets, gaps, drops, early end; 456 ticks):
  - Rules PREV and NEAREST in integer ns from the sidecar gave 0 mismatches in 48/48 cells.
  - Paths: camera JPEG in MKV via Range+ImageDecoder; barcoded JPEG at A; h264_nvenc at A via WebCodecs; E35/E45.
  - `CSS F26`; `chromium_sync_scrub/gapfill/GF08_ts_sync.json`.
- [M] Frame-index sync matched the timestamp rule on only 58/414 (cam1, no drops), 0/328 and 27/338 ticks. Container pts change 14–31 (MKV) or 5–28 (MP4) of 456 ticks, all at rule boundaries. `CSS F28`.
- [M] The existing harness helpers floorIdx/nearestIdx do not implement PREV/NEAREST (5 and 18 ticks wrong; no "no frame" result). `CSS F27`.
- [I] Pick frames by PREV, in integer ns, from a per-camera sidecar on one shared clock. Show nothing before the first frame, hold with a stale flag inside gaps, and stop at a hold limit (about 1.5P suggested; only P was run in the browser). `CSS I3`; GF08 §4.
- [M] Bounded WebCodecs scrub (GF10, functional, shared machine):
  - One decoder per stream, configured once; decode + flush per target; close every frame; GPU readback every target or every 20th.
  - Result over 64 configs: 0 errors, 240/240 exact frames per stream, 0 GPU replacements; peak private_kb 324k–967k (unit NV).
  - The decoder pool brought no benefit.
  - `IP F22, P7`; `intra_playback/gapfill/GF10_wc_scrub_memory.json`.
- [M] Without readback, the GPU process crashed (exit code 34) in 21/24 configs. After 3 crashes, Chromium switched to disabled_software and HEVC failed. The original scrub loop crashed in 12/12. `IP F22`.
- [M] Scrub rate: JPEG ImageDecoder sits at the harness ceiling of about 58 shown/s at N=4/8 (capacity above that not measured). `IP F23`.
- [M] JPEG-in-MKV and WebM/MP4 recorder indexes: packet.pos gives the sample offset (MP4 96/96) or the payload 4 bytes after pos (WebM/MKV). mp4box.js 2.4.1 reproduced the index for all 20 MP4s. `CSS F18, F19`, `IP F14`.
- [M] The 48 intra NVENC/QSV files are all-IDR with decode order = pts order. With default options the hardware encoders reorder; bf=0 fixes it. `CSS F25`.

**Ruled out / penalised**
- Today's k/fps rule and (k+0.5)/fps on VFR. G9 needs a player change whatever the format. `CSS I1`, `IP P2`.
- One `<video>` per camera for N ≥ 8: penalised [I]; use a master clock + canvas. `IP P1`, `CSS I3`.
- Sync by frame index; MKV ms timestamps for sync "when exactness matters". `CSS I3, F28`.
- The original WebCodecs scrub loop, and any loop without GPU readback. Its 23:00 rates are excluded from the tables. `IP F22, F23`.
- Decoder pool: no benefit. `IP P7`.
- createImageBitmap is penalised against ImageDecoder (2.14 vs 1.44 cores at N=8). `IP P3`.
- ptsexact seeking: less safe than mid because of the E35 last-frame stuck case (3/10 in E35). `CSS I2, F23`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Scrub rate, latency and CPU of the bounded WebCodecs pattern | `IP P7, §6`; `CSS I3` | NG15 timed (IP-SCRUB-type item on a quiet machine) |
| N=16 playback; playback at A or B; fMP4/MKV/VFR/720p/long files timed | `IP §6` | NG15 timed; NG16 functional |
| Real cross-camera clock alignment (GF08 aligned the clocks by construction) | `CSS §6`, `IP §6` | no gap raised (needs a real multi-camera recording) |
| 1.5P hold limit in the browser; GF08 on `<video>`, HEVC, running clock, N=8 | `CSS F28, §6` | no gap raised |
| Exhaustive every-frame seek sweep | `CSS §5, §6` | none (critic gap, priority 3, not in triage) |
| Overlay pairing on the master-clock player | `OV §5, §6` | NG03 functional |
| E35 last-frame lock-up root cause and workaround | `CSS F23`, `OV §6` | NG02 functional |
| Meaning of GPU exit code 34; the cause of the 23:00 memory growth (not reproduced by GF10) | `IP §6, F22` | no gap raised |
| Real React component, backend streaming, a real 5-camera recording | `CSS §6` | NG18 accept_not_verified (skellycam-ui may not be modified) |

### 2.10 Hardware target (requirement 3)

**Verified findings**
- [S] Only H.264 and HEVC intra are hardware-encoded on both RTX 3000+ and the iGPU/APU of Intel, AMD and Apple 2020+ parts. Both are royalty-bearing. `HW §4.1`, N1, I1, A1, P1, R2.
- [S] RTX 3000 NVENC: H.264 8-bit 4:2:0/4:4:4 and HEVC 8/10-bit 4:2:0/4:4:4. No AV1, no VP9, no 4:2:2. AV1 starts at Ada; 4:2:2 at Blackwell; no NVIDIA generation encodes VP9. `HW N1–N3`.
- [S] Intel TGL/RKL/ADL/RPL encode H.264, HEVC, VP9 and JPEG, but not AV1; JPEG encode is available from Skylake on. AV1 encode exists on MTL/ARL/LNL/Arc. `HW I1–I3`.
- [S] Intel on Windows (GF07, verbatim):
  - RPL, MTL and ARL-S/HX datasheets list JPEG/AVC/HEVC encode via D3D12, oneVPL and MFT.
  - KB 000098345 lists H.264/HEVC (incl. 8-bit 4:2:2) for Arc A, Core Ultra S1 and Arc B, but has no JPEG row.
  - Arc A JPEG rests on an OS-agnostic doc (Windows [I]).
  - LNL rests on a datasheet labelled "Confidential"; whether PLAN.md may cite it is Dom's decision.
  - `HW I6`; `hw_accel_target/gapfill/GF07_intel_windows_sources.md`.
- [S]/[M] Intel F/KF SKUs have no Quick Sync. AMD 8700F/8400F and non-G Ryzen 3000/5000 need a discrete card. A CPU with no iGPU has only software encoders: mjpeg, ffv1, libvpx-vp9, libsvtav1, GPL libx264/x265, and libjpeg-turbo via simplejpeg. `HW I5, A5, C1/C2`.
- [S]/[C] AMD: no GPU or APU encodes JPEG or VP9, and all AMD encode is 4:2:0. h264/hevc_amf are in the Windows wheel; all-intra via gop_size=1 [C] (GF06, not run). `HW A1, A8`.
- [C]/[S] Apple: VideoToolbox all-intra needs gop_size=1 and quality is set through global_quality; there is no CQP in n9.0.2. Upstream has no VT JPEG encoder. M1–M4 have no AV1/VP9 encode. `HW P2, P3, P5`.
- [M] Measured on Gerald: h264/hevc/vp9/mjpeg_qsv encode all-intra (60/60 keyframes). mjpeg_qsv and hevc_qsv accept yuyv422 natively. JPEG targets must be fed full range. `HW F1/F2, K5`.
- [S]/[M] §3.3 verdicts against the target:
  - H.264 intra 4:2:0: yes.
  - HEVC intra 4:2:0: yes, but playback needs HEVC hardware and hevc_qsv kept up at N=1.
  - JPEG re-encode: partly. Ampere and Intel TGL–RPL are measured or sourced; MTL/ARL-S/HX have a Windows source but were not tested; RTX 20/40/50 have code present but were not run; Arc B on Windows is NV; AMD and Apple are software only.
  - JPEG passthrough: n/a (no encoder).
  - AV1, VP9, FFV1 (Vulkan): no.
  - `HW §3.3`.
- [M] Capacity at A on Gerald: see §2.6. NVENC 12 (session cap, shared by nvenc/d3d12va/mf), h264_qsv 16, hevc_qsv 1, mjpeg_qsv 16, nvJPEG NV12 8 / YUY2 16 (late frames), libjpeg-turbo 16 (lower bound). `HW §3.3.1`, `HW §4.6`.
- [M] Matched-quality bytes at A: see §2.12. `HW §3.4`.

**Ruled out (with evidence)**
- **AV1 intra.** No RTX 3000 encode (N2); none on TGL–RPL (I1). [M] av1_qsv/nvenc/d3d12va/mf all fail on Gerald (F4). No M1–M4 encode (P2). `HW §3.3`.
- **VP9 intra.** No NVIDIA generation (N3), no AMD (A1), no Apple (P2); absent on LNL and Arc B (I2).
- **FFV1 Vulkan.** No PyAV wheel has a Vulkan encoder (N12), and FFV1 does not play in Chromium.
- **AMD and Apple JPEG hardware encode:** none in upstream FFmpeg or the wheels. jellyfin-ffmpeg's mjpeg_videotoolbox is 4:2:0 only and CLI only. `HW A1, P3`.
- **QSV lossless**, so G4 lossless is NVIDIA-only (GF09). `UNC §2.5`.
- **hevc_qsv default mode** as a 1080p multi-camera path ([I] from the measured 1 stream). `IC §4`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Every generation except Ampere RTX 3070 and RPL-S UHD 770 (source only); share of F/KF and no-iGPU CPUs, so "most CPUs" cannot be quantified | `HW §6, I5, A5` | NG18 accept_not_verified: list per goal and next to the matrix; do not present "most CPUs" as quantified |
| AMF/VT: every-frame IDR honoured, which qp_i/global_quality reaches A, VT Min/MaxQP, hevc_videotoolbox IDR vs CRA | `HW §6` (GF06) | NG18 accept_not_verified |
| Intel: Arc B Windows JPEG; ARL-H/ARL-U list; LNL if the "Confidential" sheet is not cited; any *_qsv outside RPL-S | `HW I6, §6` | NG18; LNL citation is Dom's decision |
| nvJPEG on Turing/Ada/Blackwell (code present, not run); hardware-decode list on GeForce | `HW N7, N13` | NG18 |
| Linux QSV through the PyPI wheel (likely unusable [I]); Windows on ARM64 | `HW §3.2`, `JF F23` | NG18 |
| CPU fallback capacity on 2020-era low-end / no-iGPU CPUs | `HW §6`, `IC §6` | NG12 (see §2.6) |
| hevc_qsv low_power; NVENC+QSV together; hevc_qsv N=2–3 and nvJPEG N=9–15 never run | `HW §6, §8.4` | NG13, NG10; N=2–3 / 9–15 no gap raised |
| K5 range bug in `bench_encode_stream.py` (bypassed, not fixed; no reported result uses it) | `HW §8.4` | no gap raised |

### 2.11 Requirement 4: standard FFmpeg vs jellyfin-ffmpeg

**Verified findings** (sources only, by rule; no jellyfin binary was run)
- [S] The latest release is v8.1.3-2 (2026-11-03), on FFmpeg 8.1.3 with 106 patches. [M] PyAV 19.0.2 bundles FFmpeg 9.0.2. [I] jellyfin is one major version behind. `JF F1–F5, F10`.
- [M] It registers 29 names, 28 absent from n9.0.2, of which only 2 are encoders: mjpeg_videotoolbox and mjpeg_rkmpp. It adds no NVIDIA encoder and no nvJPEG. `JF F12, F13`.
- [C]/[S] mjpeg_videotoolbox (patch 0047) takes NV12/YUV420P only (no 4:2:2) and requires a hardware encoder by default. Apple fixed-function JPEG is NV. `JF F15, F19`.
- [S] VAAPI/Vulkan encoders exist upstream; jellyfin enables them but does not add them. [M] The PyAV manylinux wheel has no VAAPI or Vulkan. `JF F21–F23`.
- [S] Behaviour patches absent upstream: 0096 (mjpeg_vaapi full range), 0097 (MF adapter by LUID), 0071 (QSV low-power retry), 0033 (Intel d3d11va HEVC 4:2:2 decode; effect NV). [I] Gerald needs none of them. `JF F24–F34`.
- [M]/[I] There is no PyAV binding or wheel, so it is usable only as a subprocess. `JF F44, F45`.
- [S]/background pipe costs:
  - rawvideo/image2 default to 25 fps.
  - Killing the child or the whole tree after 300 frames: MP4 0/300; MKV/fMP4 x264 246; MKV copy 293. Killing only the feeder: 300/300.
  - At least 75 frames lost at startup (bound NV).
  - In-process PyAV mkv+fp kept 74/75.
  - `JF F46–F50`.
- [I] Binaries are GPLv3. [S] FDK-AAC is moved out of nonfree. `JF F37, F38`.
- **Pros/cons table** (`JF §3.1`, 18 rows) and **options table** (`JF §3.2`, 7 rows): present and complete. GF04 replaced the stale §5. The rows, with favours/label:
  1. base version: Standard [I];
  2. Python use: Standard [I];
  3. added encoders: Jellyfin, macOS only [I];
  4. Windows x64 hardware encode: Tie for target codecs on Gerald [I];
  5. Linux x64: Jellyfin [S+C];
  6. macOS: Jellyfin if hardware JPEG is confirmed [I];
  7. nvJPEG: Tie [M];
  8. AV1 on RTX 3070/UHD 770: Tie [I];
  9. QSV/NVENC/VAAPI/MF fixes: Jellyfin in principle [S], none needed on Gerald [I];
  10. crash: Mixed [I];
  11. timestamps: Tie [I];
  12. startup loss: Standard [I];
  13. distribution: Standard [I];
  14. licence: Standard, neither clean [I];
  15. GPL boundary: Standard not blocked [I];
  16. cadence: Standard [I];
  17. platform floor: Tie [I];
  18. tested in study: Standard [I].
- [I] Verdict: do not adopt jellyfin-ffmpeg for the recording path. macOS mjpeg_videotoolbox is the one unique option. Close the Linux gaps with a PyAV build against upstream with --enable-vaapi --enable-vulkan. `JF §4.1–§4.5`.
- [M] Bench caveat on the standard side: hevc_qsv default mode keeps up with 1 stream at 1080p30 and 4 (not 8) at 720p30. "Not a 1080p multi-camera path" is [I]. The Windows "Tie" stays [I] because only the standard side was benched. `JF §5` (GF04, verify3 correction).

**Ruled out / penalised**
- In-process use via PyAV: no binding. Adopting it for recording: rejected [I]. Plain MP4 for a subprocess writer: 0/300. Killing the child on shutdown: close stdin instead. `JF F44, §4.1, §4.6`.

**Still NOT VERIFIED / open**

| open item | where stated | gap: type, proposed action |
|---|---|---|
| Whether the backport patches (0017, 0018, 0078, …) are already in n9.0.2 (only 5 spot-checked) | `JF F35` | no gap raised |
| Whether QSV patches 0011/0020 fix PyAV's QSV frames-context failure; 0033 effect | `JF F32, F34` | no gap raised |
| Apple fixed-function JPEG; wheel QSV on Linux hardware; FDK-AAC licence | `JF F19, F23, F38` | NG18 (hardware); no gap for FDK |
| hevc_qsv low_power=1 speed | `JF §5` | NG13 timed |

### 2.12 JPEG vs H.264/HEVC intra trade-off (NG01; requirement 9)

Built from the cited numbers as NG01 proposed. It adds no new measurement. Bytes are at **target A**, YUY2 1080p, **sweep basis** (interpolated to the exact target, `intra_compare/matched_summary.md`, `IC §3.1`; `HW §3.4` gives the same values). The bench-basis ratio (integer setting, against the bench jt422 of 286,974 B) is from `IC §3.3`. The B ratio is the sweep ratio vs jt422 (`IC §3.2`). Keep-up is paced 1080p30 at A (`IC §3.5`, `HW §3.3.1`).

GB/h is **[arith]**: bytes × 30 × 3600 / 1e9 for one 1080p30 camera, done here and not measured.

| path | B/frame at A (sweep) | ratio vs jt422 at A, sweep / bench | ratio at B | GB/h at A [arith] | 1080p30 keep-up (cores) | vendor coverage (`HW §3.3`, GF06/GF07) | G7 |
|---|---|---|---|---|---|---|---|
| libjpeg-turbo 4:2:2 (jt422) | 297,359 | 1.00 / 1.00 | 1.00 | 32.1 | 16 YUY2, process (≥2.81) | CPU everywhere | no listed patents (R1) |
| libjpeg-turbo 4:2:0 (jt420) | 265,001 | 0.89 / 0.89 | 0.89 | 28.6 | 16, process (≥1.69) | CPU everywhere | same |
| mjpeg_qsv 4:2:2 | 331,349 | 1.11 / 1.07 | 0.99 | 35.8 | 16 YUY2 (0.92) | Intel: M on RPL-S; S Win for RPL/MTL/ARL-S/HX | same |
| mjpeg_qsv 4:2:0 | 296,502 | 1.00 / 0.96 | 0.88 | 32.0 | 16 NV12 (1.05) | same | same |
| nvJPEG 4:2:0 | 221,461 (exact RGB) | 0.74 / 0.79 (swscale) | 0.92 | 23.9 | 8 NV12 (2.56) | RTX 30 M; RTX 20/40/50 code present, not run; AMD/Apple none | same; NVIDIA licence terms (R5) |
| nvJPEG 4:2:2 | 248,629 (exact RGB) | 0.84 / – | 1.04 | 26.9 | 16 YUY2 (4.68, 5.3–13.3% late) | same | same |
| h264_nvenc | 157,840 | 0.53 / 0.55 | 0.29 | 17.0 | 12, session cap (0.61) | RTX 3000+ (S+M) | royalty-bearing (R2) |
| hevc_nvenc | 129,131 | 0.43 / 0.47 | 0.18 | 13.9 | 12, session cap (0.65) | RTX 3000+ (S+M) | royalty-bearing |
| h264_qsv | 175,094 | 0.59 / 0.59 | 0.35 | 18.9 | 16 (1.25) | Intel (S; M RPL-S); AMD/Apple via AMF/VT, intra code-only | royalty-bearing |
| hevc_qsv 4:2:0 | 116,646 | 0.39 / 0.41 | 0.18 | 12.6 | 1 | same | royalty-bearing |
| hevc_qsv 4:2:2 (Rext) | 155,171 | 0.52 / 0.54 | 0.22 | 16.8 | 1 | Intel; does not play in E35/E45 (C17) | royalty-bearing |
| camera passthrough (1080p mean) | 163,478 (camera q94-like, **not at A**) | n/a | n/a | 17.7 | no encode | any | no listed patents for these SOF0 baseline frames (`LIC §2.7`) |

Notes:
- nvJPEG at A has PSNR-Y 50.80 dB vs 52.24 for libjpeg-turbo, and at B it is no smaller at matched PSNR. `HW Q2a`.
- At A, H.264/HEVC PSNR-Y is 53.12–53.36 dB vs JPEG 52.24–52.56 at equal SSIM-Y. `IC §2.2`.
- At B (bench NV12 bytes), jt420 is 69,092 B against h264_nvenc 21,825 and hevc_nvenc 14,506. There is no bench jt422 row at B. `IC §3.4`.
- The passthrough bytes come from `IC §2.3`. Its fidelity vs A is NV (NG21).

---

## 3. Cross-topic contradictions

### 3.1 Resolved in step 3

| topic of conflict | what disagreed | resolution and evidence |
|---|---|---|
| Real vs index PTS, and the MKV rule-out | JP ruled MKV out on the cv2 count; PI F3 measured correct MKV counts with index PTS | GF02 Part A [M]: index PTS give exact count, 11/11 seeks and FreeMoCap in all containers, incl. drops and 54,000 frames (OpenCV 4.12/FreeMoCap read-only from the skellycam .venv; PyAV 19.0.2 writers). JP §4.8 now scopes the rule-out to real VFR PTS; CR §4.1 says the ruling "depends on the PTS policy". |
| fMP4 1 s kill loss | JP: one unpaced kill lost 22 (578/600, no fp) and called it "leading"; WT: 33/62 (no fp), 46/5 (fp), "avoid"; CR: PyAV 18 only | GF02 [M]: 1–30 lost per paced fp kill. GF01: the kill tests are not comparable. JP demoted it to "a container candidate" (`JP §4.2`, §9). |
| Index PTS with drops (GF01 "not yet tested") | open cell | Superseded by GF02 (exact). `JP §9` |
| HEVC 4:2:2 playback in Chromium | IP and LIC listed it NV ("no clip played"); CC C17 had played one | GF05: measured failure in E35 (demuxer) and E45 (decode); C156 NV. `CC C17`, `IP §6` (line 282). LIC's end note (line 361) still flags IP line 258 as conflicting; IP's current text agrees with C17, so that flag is outdated. |
| libx265 Rext vs "Main" | uncompressed_intra sample labelled Main | GF05 ffprobe: Rext, 8/8 I-frames; the Main label came from `VERIFY_method.prev.md:28` (annotated). Fails E35, plays E45. `UNC §2.11`. The generator's codec string hvc1.1.6.L120.90 still says Main (`IP` conflicts note). |
| mjpeg_qsv 4:2:0 vs 4:2:2 | GE said 4:2:0 out | Chroma follows the input (YUY2 → 4:2:2). `GE §2.7, §2.11` |
| nvJPEG "misses target A" | HW §3.3/§4.4 generalised the miss | Narrowed to CPU-decoded MJPEG → swscale rgb24. NV12/YUY2 and mjpeg_qsv feeds hit A. `HW §3.3.1, §8.6`, `IC §2.7`; GF05 corrected `intra_compare/BENCH.md` caveat 3. Cause still NV, as is the conflict with `nvjpeg_rgb_diag.json`. |
| WebCodecs scrub memory (F22) and "E45 more stable" | 23:00 run: 914 hidden errors, 9–38 GB growth, E45 0 errors | GF10 [M]: a bounded pattern with readback is error-free in both versions; without readback the GPU crashes in both. "E45 is not more stable for this loop" (`IP F24`). The reset() inference was withdrawn. The growth itself was not reproduced; its cause is open. |
| Stale "pending tonight's bench" text | HW §5/§6, CC §5/P2, CSS §5/I3/§6, JF §5 | GF04/GF05 replacement text; current FINDINGS carry the timed results or pointers to IP. |
| Multi-camera sync rule (G9) | CSS I3 deferred the choice to a bench | GF08 [M] plus IP F19/F21: PREV by sidecar ns on a master clock. `CSS I3` rewritten. |

### 3.2 Still unresolved (evidence on each side)

| conflict | side A | side B | gap |
|---|---|---|---|
| **Container choice for recording** (facts reconciled, choice open) | MKV+fp (`CR §4.1` preference; `WT §4.4`; `PI §4.3`): 1 lost per kill; 0 torn samples on prefix cuts; warm 30-min open 0.19 ms; repair 0.907 s/GB; 1 ms time base. recover() on real PTS gives 62.5 fps (needs a fix [I]). | fMP4: per-frame+fp also loses 1, but tears 12/12 on cuts, opens in 1107 ms at 54k frames, repair +48%. 1 s fragments: 1–30 lost, open 42.6 ms. JP keeps 1 s as "a candidate" (`JP §4.2`); WT says avoid (`WT §4.8`). MSE needs fMP4/WebM (`CC P9`, background). | GF01 is the table; no gap raised for the decision itself |
| MKV+empty packet (0 loss) vs its defects | 0 lost in 15/15 kills (`WT §2.2`, `CR §2.1`) | Seek 1 frame late on killed files (12/12); last-frame seek empty on finalized files (8/8); relies on undocumented muxer behaviour [I]; write cost not measured (`CR §4.1` Condition 3, `WT §4.4`) | no gap raised |
| HANDOFF §4 headline | "fMP4 with a 1/1e6 time base is the leading container"; the UI seek rule is "(k+0.5)/fps"; mjpeg_qsv/nvJPEG ratios 1.00/0.74 | GF01 §4: fMP4 contested. IP F6: the UI uses k/fps. IC: sweep 1.00/0.74 vs bench 0.96/0.79 | NG22 doc_fix (main session); this index cites FINDINGS only |
| **Is Electron 45 needed?** | `OV §4`: "Upgrade Electron 35.7.5 → 45.x, or never seek to a video's last frame" (E35 lock-up 5/5 files, functional, GOP clips). `IP P8`: E45 is needed for the libx265 Rext sample. | `CC P11`: "not required" for intra-only playback. `CSS I8`: not required for G9 with mid or index seeking. `UNC §4.11`: no bump needed for G4. `IP P8`: not needed for NVENC/QSV H.264/HEVC Main [I]. `CSS F23`: ptsexact triggers the stuck case 3/10 in E35. | NG02 functional: E35 last-frame seek by exact pts / mid / clamp on intra files, then harmonise OV §4, CC P11, IP P8, CSS I8 |
| Overlays assume `<video>` vs recommended master-clock canvas | `OV §2.3` tested rVFC on one `<video>` (GOP 30) | `IP P1`, `CSS I3` recommend master clock + canvas; OV §5 says the method "rides on whichever multi-video path G9 picks … not tested" | NG03 functional |
| JPEG vs video byte ratio ranges | `IC §4`: 1.7–1.9× (H.264) and 2.3–2.5× (HEVC) vs jt422 at A | `HW Q7`: JPEG 1.3–2.5× H.264/HEVC 4:2:0 at A, including nvJPEG (1.26–1.90×) and mjpeg_qsv (1.69–2.54×); at B 2.5–5.0× (4:2:0) and 2.8–5.4× (jt422). Different JPEG rows and chroma bases, so the two are not contradictory, only differently scoped. | NG01 (table in §2.12) |
| CSS I2 wording | `CSS I2` (line 271): mid "measured only on single elements, on software encodes without reordering" | `IP F1/F3`: mid measured on NVENC/QSV intra files, 4800/4800 per browser. Neither file flags this. | no gap raised (doc fix) |
| Intel HEVC 4:2:2 encode, Windows vs Linux (J5) | MTL/ARL-S/HX datasheets and KB 000098345: Windows yes (GF07) | Linux media-driver gives MTLx "D" (decode only) | NG18; matters only if 4:2:2 HEVC is kept (it does not play in E35/E45) |
| AMD vendor vs vendor (J9) | AMF wiki: Navi24 AV1 decode Y | kernel: N (cell follows the kernel) | NG18; not decision-relevant for intra encode |
| nvImageCodec licence | PyPI and GitHub v0.10.0: Apache-2.0 | the wheel's licence file: NVIDIA SLA (`LIC §2.4`, GF03) | none; legal review |
| MKV kill buffer size | `JP §2.5` infers a 32 KiB buffer | GF01 side finding: the killed sizes fit 126 × 262,144 B, and `CR §2.1` cites FFmpeg's 262,144 B buffer | no gap raised |

---

## 4. The 22 gaps left for Dom (not filled in step 3)

**Nothing in this list has been planned or started. Dom reviews it first.** Timed gaps need a quiet machine: one item at a time through the bench runner (`scripts/bench_runner/run_queue.py`), nothing else running. Functional gaps can run in parallel. Gaps are numbered in `triage.not_filled` order.

**Timed**

| id | title | topics | why not filled | proposed action |
|---|---|---|---|---|
| NG10 | More than 12 cameras on NVIDIA: NVENC plus a second encoder | GE, IC | timed; concurrent agents ruled it out | Quiet queue: paced 1080p30, 12 h264_nvenc + 4 h264_qsv; + 4 nvjpeg_422 (YUY2); + 4 jt422 process workers. Optional functional pre-check: 6+6 NVENC sessions across 2 processes |
| NG11 | End-to-end recorder bench (encode + MKV+fp + CRC sidecar + overlay sidecar, 12–16 × 1080p30) | IC, GE, WT, PI, OV | timed | Quiet queue: N=12 NVENC, N=16 QSV and mjpeg_qsv_422 from YUY2, recwriter MKV+fp + binary sidecar + .skov; drops, write p99.9, cores, MsMpEng; 3 × 60 s + one 10-min cell |
| NG12 | CPU fallback capacity on lower-end / no-iGPU CPUs | IC, WT, PI, UNC, HW | timed proxy; no such hardware, so really accept_not_verified | PLAN.md states NV with at most an inferred per-core figure. Optional proxy: IC-SCALE jt420/jt422 + simplejpeg decode pinned to 4 E-cores and 4 P-core CPUs, labelled proxy |
| NG13 | hevc_qsv low_power / VDEnc at target A | GE, IC, HW | needs timing; QC alone decides nothing | Functional sweep low_power=1 (and preset veryfast) to hit A/B on yuy2_1080p and nv12; then one quiet item IC-SCALE hevc_qsv_420 low_power N=1/4/8/16 |
| NG14 | nvJPEG with GPU-side YUV→RGB | IC, GE | priority 3, mostly timed | Functional check that pinned CuPy conversion into an nvImageCodec device image keeps A; then quiet timing at N=8/16, threads vs processes |
| NG15 | Scaling at target B; h264_qsv/mjpeg_qsv_420 × 16 from YUY2; playback at A/B and N=16 | IC, IP | priority 3, timed | Quiet queue: IC-SCALE at B for h264_nvenc, h264_qsv, mjpeg_qsv, jt420; h264_qsv from YUY2 N=16; IP-SEEK/IP-SYNC on A/B clips and camera JPEG bytes; N=16 playback |

**Functional**

| id | title | topics | why not filled | proposed action |
|---|---|---|---|---|
| NG02 | Is Electron 45 needed? E35 last-frame lock-up workaround on intra files | OV, CC, IP, CSS | priority 2, beyond the 10-slot limit | E35 on intra H.264/HEVC: last-frame seek by exact pts, by mid, by clamp (last pts − 1 ms), 10 trials each; then harmonise OV §4, CC P11, IP P8, CSS I8 |
| NG03 | Overlay pairing on the master-clock canvas player and on intra files | OV, IP | priority 2; GF08/GF10 harness copies first | Harness copy draws .skov frame k into the canvas for JPEG ImageDecoder and WebCodecs intra at N=4/8; barcode readback, untimed |
| NG04 | Chromium software-decode fallback and Intel-adapter decode | CC, IP | priority 2 | intra_functional in E35/E45 with --disable-accelerated-video-decode; Chromium command-line adapter choice only if it exists (no system change); record decoder name and exactness |
| NG06 | QSV encoder hold-back under a kill; NVENC delay=0 kill | CR, IC | priority 2; G2 loss for Intel paths unknown until it runs | PyAV 19, untimed: 3 live kills each of 75-frame MKV+fp for h264/hevc/mjpeg_qsv (default and async_depth=1) and h264_nvenc delay=0 |
| NG07 | Killed intra NVENC and JPEG-index recordings played in Electron | CR, IP | priority 2; reuse GF02 killed files | Play killed/recovered intra MKV+fp and fMP4 in E35/E45 (`<video>` mid, WebCodecs); killed JPEG MKV/fMP4 via Range + CRC sidecar ImageDecoder; count exact seeks |
| NG08 | PyAV-made libx265 all-intra clips in Electron | IP, CC, UNC | priority 2 (doc part done in GF05) | PyAV 19 libx265 all-intra 4:2:0 at A (mp4/fMP4/mkv; CFR/VFR; 720p/1080p); intra_functional in E35/E45; ffprobe profile |
| NG09 | Camera 1080p JPEG size vs libjpeg-turbo q94 gap | IC, JP | priority 2 (HANDOFF §4 loose end) | Re-encode decoded camera JPEGs with the camera's own DQT/subsampling; compare high-frequency energy of the MJPEG and YUY2 sets and whether they show the same scene; the final cause stays NV without captures |
| NG16 | intra_playback exactness on clips at target A | IP | priority 3 | Generate NVENC/QSV intra and mjpeg_qsv clips at A from matched_settings.json; intra_functional seek/step in E35/E45 |
| NG17 | Quality checks on C922 frames (all bench QC is C930e) | IC | priority 3 | Untimed quality_check for every path and feed at A and B on 8 C922 YUY2 + 19 C922 MJPEG frames; hit/miss per path |

**Source**

| id | title | topics | why not filled | proposed action |
|---|---|---|---|---|
| NG05 | Primary source for Chromium HEVC decode requirements (hardware-only?) on Windows, macOS, Linux | IP, CC, HW | priority 2 | Cite Chromium source at the 134 and 156 tags (`media/base/supported_types.cc`, enable_platform_hevc) file:line with exact quotes |

**Doc fix**

| id | title | topics | why not filled | proposed action |
|---|---|---|---|---|
| NG01 | One JPEG vs H.264/HEVC intra trade-off table | IC, HW, GE | the core job of this index | Done here as §2.12 (sweep + bench bases, B ratios, keep-up, coverage, G7; GB/h is arithmetic, not measured) |
| NG22 | HANDOFF §4 headline and status table carry corrected or stale claims | IP, IC, JP | gap-fill agents may not edit HANDOFF | Main session updates HANDOFF §4: seek rule is k/fps per IP F6; mjpeg_qsv/nvJPEG sweep vs bench 1.00/0.74 vs 0.96/0.79; fMP4 contested (GF01); IC and IP now verified. This index cites FINDINGS only |

**Accept as NOT VERIFIED** (PLAN.md states them as such)

| id | title | topics | why not filled | proposed action |
|---|---|---|---|---|
| NG18 | Coverage that cannot be measured here (AMD, Apple, Linux, Windows on ARM, other NVIDIA/Intel generations, Chromium on non-NVIDIA, no-iGPU share, real UI) | HW, GE, UNC, JF, CC, CSS, IP | no such hardware/OS; skellycam-ui may not be modified | List per goal (done in §2) and next to the PLAN.md hardware matrix, each with its source-only basis; do not present "most CPUs" as quantified |
| NG19 | H.264/HEVC royalties for free AGPL software using GPU or OS encoders | LIC | pool agreements not available as primary text; legal interpretation | PLAN.md: NV (not legal advice), quoting LIC Q29–Q34; optional Via LA licensor FAQ quoted from a licensor page |
| NG20 | ISO BMFF patent status | LIC, JP | iso.org 403 | PLAN.md and the GF01 table: Matroska 0 IETF disclosures, ISO BMFF NV; keep both containers |
| NG21 | Camera JPEG fidelity vs target A (passthrough on the A/B scale) | JP, IC, PI | needs simultaneous raw + MJPEG captures; requirement 11 forbids camera access | PLAN.md: "q94-equivalent quantisation; fidelity vs A NOT VERIFIED"; a back-to-back capture is a task for Dom |

---

## 5. The 10 gaps filled in step 3

All were functional, source or doc work, with no timing. None wrote a FINDINGS.md; the topic FINDINGS were then updated from them. Status is from `gapfill.*.status` (all "filled").

| id | what it established | status | evidence |
|---|---|---|---|
| GF01 | Cross-topic container table (7 rows × 13 columns, labelled cells with file:line) and the listed conflicts; no container chosen | filled | `crash_resilience/gapfill/GF01_container_decision_table.md`, `GF01_NOTES.md` |
| GF02 | Container matrix under PyAV 19.0.2, functional. Index PTS exact in all containers. Kill loss: MKV+fp 1, fMP4 per-frame 1, fMP4 1 s 1–30, empty packet 0. Real-PTS recover() 62.5 fps defect. **Readers were OpenCV 4.12 and FreeMoCap, used read-only from the skellycam .venv; writers were PyAV 19.0.2.** | filled | `crash_resilience/gapfill/GF02_container_matrix.{md,json}`, `GF02_partA_*.json`, `GF02_partB_*.json`, `GF02_recovered_rates.txt`; scripts in `scripts/crash_resilience/gapfill/GF02/` |
| GF03 | nvjpeg wheel 12.4.0.76 is CUDA 12.9.1 libnvjpeg; nvImageCodec licence split (Apache metadata vs SLA file); SLA benchmark clause; CUDA-backend encode on GeForce; sm_75/86/89/120 present; 13 superseded licensing caveats | filled | `licensing/gapfill/GF03_nvjpeg_licence_arch.md`, `GF03_quote_verification.json`, `GF03_wheel_arch_facts.json`, `GF03_sources/` |
| GF04 | Measured capacity column at A (NVENC 12, h264_qsv 16, hevc_qsv 1, mjpeg_qsv 16, nvJPEG 8/16, libjpeg-turbo 16); old B-* items mapped; R6 libjpeg-turbo licence; jellyfin §5 replaced | filled | `hw_accel_target/gapfill/GF04_doc_fixes.md`, `GF04_capacity.json`; `jellyfin_ffmpeg/gapfill/GF04_jellyfin_doc_fixes.md` |
| GF05 | Stale G8/G9 text replaced; HEVC 4:2:2 now cites C17 (measured fail E35/E45); libx265 sample is Rext; BENCH.md and NOTES corrections (private_kb unit NV) | filled | `chromium_codecs/gapfill/GF05_g8_g9_doc_fixes.md`, `GF05_ffprobe_hevc_intra_420.txt`, `intra_playback/gapfill/GF05_private_kb_cells.json` |
| GF06 | AMF and VideoToolbox all-intra and quality knobs from FFmpeg n9.0.2 code and vendor docs (AMF gop_size=1 + cqp; VT gop_size=1 + global_quality, no CQP); not run on hardware | filled | `hw_accel_target/gapfill/GF06_amf_vt_intra.md`, `GF06_pyav_options.json`, `GF06_sources/` |
| GF07 | Intel Windows coverage from verbatim sources (RPL/MTL/ARL datasheets, KB 000098345); F/KF no Quick Sync sourced; LNL rests on a "Confidential" datasheet; HEVC 4:2:2 Windows-vs-Linux disagreement | filled | `hw_accel_target/gapfill/GF07_intel_windows_sources.md`, `GF07_sources/` |
| GF08 | Multi-camera sync by capture timestamp: PREV/NEAREST 0 mismatches in 48 cells (E35/E45, 3 paths); frame-index sync fails; harness helpers wrong at edges | filled | `chromium_sync_scrub/gapfill/GF08_ts_sync.{md,json}`, `GF08_ticks.json` |
| GF09 | QSV lossless impossible (0/300 exact, QP floor 1); NVENC lossless bit-exact; E35/E45 play both NVENC lossless formats exactly | filled | `uncompressed_intra/gapfill/GF09_qsv_lossless.{md,json}`, `GF09_rows_*.json`, `GF09_chromium_electron{35,45}.json` |
| GF10 | Bounded WebCodecs scrub (configure once, flush per target, readback) error-free in 64 configs; no readback crashes the GPU; decoder pool no benefit | filled | `intra_playback/gapfill/GF10_wc_scrub_memory.{md,json}` |

---

## 6. Which target each number is at, and run-wide caveats

**Which target each number is at**
- **Target A** (SSIM-Y 0.9961): the intra_compare single-stream and scaling numbers (scaling at A settings, no QC in the scaling runs); the hw_accel_target §3.3.1 capacity and §3.4 bytes; the gpu_encode quiet-run throughput; GF08's barcoded JPEG and h264_nvenc paths (A settings, quality not measured on those frames).
- **Target B** (45 dB): `IC §3.2` sweep ratios, `IC §3.4` bench bytes, the B single-stream fps (`IC §2.4`), item 3 of the queue. At B, five rows sit under 45 dB by one knob step (44.61–44.85). `IC §2.7`.
- **Sweep vs bench basis.** For example, hevc_qsv 0.39 vs 0.41, hevc_nvenc 0.43 vs 0.47, mjpeg_qsv_420 1.00 vs 0.96, nvJPEG 0.74 vs 0.79. Always name the basis. `IC §2.3 vs §3.3`.
- **Neither A nor B:**
  - all intra_playback clips (54.49–55.72 dB Y-PSNR), and so every G8/G9 timing;
  - CSS functional clips (PyAV 18 crf/q90);
  - CR intra fragment payloads (A QPs, quality not measured);
  - uncompressed_intra lossless rows (exact) and its lossy rows;
  - the overlay burn-in re-encode (q90);
  - camera passthrough (q94-like quantisation; fidelity vs A NV).
- **No quality dependence:** write_throughput, jpeg_passthrough mux/open/rotate, python_integration writer and decode benches, overlays sidecar costs.
- **QC scope:** the first 4 C930e frames only; the C922 is never QC'd (NG17). At A, NV12 QC reads 0.6–0.9 dB above the sweep, nvJPEG +1.5 dB. `IC §2.7, §5 flag 5`.

**Run-wide caveats PLAN.md must carry** (`BENCH_RUN_2300_SUMMARY.md` §3, with the topic sections that apply them)
1. OV-COST timed out at 1800 s and was re-run alone (60 min timeout, 36.4 min, ok). To do: raise its estimate and timeout in `make_queue.py`.
2. Items 1–3 are not all P-core-only. libx265 widened the affinity from CPUs 0–15 to 0–27 ([M] in IC F1; summary calls it inferred). Which later cells ran on 28 CPUs cannot be told. Scaling items kept 0–15. (`IC §5 flag 1`; † cells in GE.)
3. NVENC opens at most 12 sessions; read N=16 NVENC rows as 12 streams. QSV h264 opened 32/32.
4. nvJPEG fed CPU-decoded camera MJPEG misses the matched target (SSIM-Y 0.9954; 43.14 dB at B). Other feeds hit A (§3.1).
5. WebCodecs scrub in the 23:00 run is not a capacity number: 914 hidden E35 errors, GPU private_kb 9–38 M (unit NV), 3 GPU replacements. GF10 gives the bounded pattern but no rate (NG15).
6. N=8 `<video>` sync has stalled tiles in 19/20 configs (max spread 100–245 frames). Master clock spread was 0 in 28/28.
7. Write latencies in the quiet run are higher than the contaminated daytime run for files and append (2.11 vs 1.30 ms; 0.55 vs 0.18 ms). The old file is not a lower bound in every column. P-core pinning is a possible cause [I].
8. Fast items were checked complete. CR-FRAG-INTRA loops 300 encoded frames to 3000, and its all-intra payload rests on the smoke check.
9. uncompressed_intra has no lossless check inside the timed bench. Exactness comes from functional files (GF09 for NVENC). FFV1 s24 on NV12/Bayer8 and the 720p NVENC rows have no PyAV 19 exactness file. Encoder open is 3.6–22.7% of NVENC wall time.
10. Overlays: canvas-over-video shows the overlay 1–3 frames behind (earlier run: 1). The E45 drop counter says 19–20/300 dropped on CFR while presentedFrames shows 0 gaps.
11. Coarse CPU timers: mux/fragment CPU comes in 15.625 ms steps, so those documents compare on wall time. Process-worker CPU in items 10 and 55 is a lower bound.
12. Single runs: the core write matrix, long cells, each intra_playback config, recwriter A/B and decode benches ran once. Their medians and ranges are within one run.

Also carried:
- Defender real-time scanning was on and is part of the measured cost. Folder-of-files triggers it (summary §2, `WT §2.9`).
- The GF gap-fills ran on a shared machine and are functional only. Their timings, if any, are not evidence (GF10 limits).
- Requirement 5: only PyAV 19.0.2 results are evidence; PyAV 18 rows are background.
- Deviation to carry: GF02's readers were OpenCV 4.12 / FreeMoCap run read-only from the skellycam .venv, not PyAV 19.0.2 (its writers were PyAV 19.0.2). The venv was not modified (requirement 6).
