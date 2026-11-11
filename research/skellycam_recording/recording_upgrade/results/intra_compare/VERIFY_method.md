# intra_compare: method verification of the 2026-11-10 draft FINDINGS

Verifier: adversarial method check (confounders, wrong conclusions), 2026-11-10. Draft checked: the 2026-11-10 intra_compare FINDINGS text (it was handed to the verifier and is not on disk).

Paths:
- `R` = `research/skellycam_recording/recording_upgrade/results/intra_compare/`
- `B` = `R/bench/`
- `S` = `research/skellycam_recording/recording_upgrade/scripts/intra_compare/`

The bench JSON aliases (S-A1080, C-nvj, and so on) are the draft's own.

**Verdict: REVISE.** Every timed number I re-read from the JSON matches the draft. The problems are in interpretation: three claims are wrong (§2) and fifteen need qualifying (§3). None changes the draft's main conclusions:
- G7 cost ordering;
- the 12-session NVENC limit;
- hevc_qsv at 1 stream;
- mjpeg_qsv and h264_qsv at 16 streams from NV12;
- the nvJPEG miss on decoded MJPEG.

## 1. What was checked

- measured: every number in draft §2.4, §2.5, §2.6, §3.3, §3.4 and §3.5 was recomputed from the 27 JSON files in `B` (`summary[]`, `runs[]`, `limit_probe`). Medians and min–max were taken over reps by a scratch script (`scratchpad/step2/icv/conc.py`, `dump.py`; temp files, not kept).
  - All the values I checked agree to the draft's rounding. Examples:
    - h264_nvenc N=12 paced: 0.61 (0.60–0.64) cores, paced p99 12.4–16.0 ms;
    - nvJPEG N=16 NV12: 1/2/3 keep up, late 72.8 / 83.6 / 87.2 %;
    - h264_qsv after mjpeg_qsv at N=8: 153 and 113 late frames;
    - limit probes: NVENC 12/32, QSV 32/32.
- measured: the draft's §3.1 ratios against camera passthrough, its 4:2:2-against-4:2:0 ratios (1.075–1.166 for JPEG, 1.129–1.330 for hevc_qsv) and its storage arithmetic (§4) were recomputed from the §3.1 bytes. All are correct.
- code: I read the source preparation, the QC and the paced loop (`S/benchpaths.py:7-19, 86-102, 196-245, 266-288`; `S/bench_matched_concurrent.py:44-131, 193-210`; `S/iclib.py:44-47, 125-150`).
- Two functional checks: PyAV 19.0.2 via `uv run --script` with PEP 723 pins, no timing, each under 1 min CPU. The outputs are copied verbatim below. The scripts are temp files in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/icv/`.

### 1.1 Functional check F1: does libx265 change the process CPU affinity? (`x265_aff.py`)

The script pins the process to CPUs 0–15 with psutil. It then opens libx264 (veryfast, qp 12, gop 1) and libx265 (ultrafast, qp 12, gop 1) at 1080p `yuv420p`, encodes 3 frames with each, flushes and deletes the encoder, and reads `psutil.Process().cpu_affinity()` after each step. Output, 2026-11-10:
```
after pin: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
libx264 after open: 16 CPUs
libx264 after encode+flush: 16 CPUs [0, 1, 2] ... [13, 14, 15]
libx265 after open: 28 CPUs
libx265 after encode+flush: 28 CPUs [0, 1, 2] ... [25, 26, 27]
end: 28 CPUs
```
- measured: opening libx265 in PyAV 19.0.2 widens the process affinity from 16 to 28 CPUs. The wider mask stays after the encoder is deleted. libx264 does not change it.

### 1.2 Functional check F2: encoder output delay (`delay_check.py`, `nv_min.py`)

The script opens each path at 1080p NV12 with its `matched_settings.json` yuy2_1080p target-A options, encodes 12 frames (8 for h264_nvenc) and counts the packets returned by each `encode()` call. Output, 2026-11-10:
```
h264_nvenc packets per encode() call: [0, 0, 1, 1, 1, 1, 1, 1] flushed 2
hevc_nvenc_420 packets per encode() call: [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] first packet after frame index 2 flushed 2
h264_qsv_420 packets per encode() call: [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1] first packet after frame index 4 flushed 4
hevc_qsv_420 packets per encode() call: [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1] first packet after frame index 4 flushed 4
mjpeg_qsv_420 packets per encode() call: [0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1] first packet after frame index 3 flushed 3
```
- measured:
  - NVENC (H.264 and HEVC) returns each packet 2 `encode()` calls after its frame;
  - h264_qsv and hevc_qsv return it 4 calls later;
  - mjpeg_qsv returns it 3 calls later.
  - simplejpeg and nvJPEG return the JPEG from the same call (code: `S/benchpaths.py` `Encoder.encode`).
- The first variant of the script segfaulted on h264_nvenc (random-noise input, options loaded from JSON). The cause was not investigated. A minimal script (`nv_min.py`, flat input, the same options typed in) ran cleanly and gave the h264_nvenc line above.

## 2. Refuted claims

### R1. Draft §2.4: "bench bytes/frame at the chosen settings are within 0.1% of the sweep for JPEG; for H.264/HEVC fed decoded MJPEG they are 1.8–3.5% smaller"

- measured: S-A1080, `summary[].bytes_per_frame_median` ÷ `quality_check.matched_bytes_per_frame`.
- **JPEG rows outside 0.1%:**

  | path · source | ratio |
  |---|---|
  | nvjpeg_420 · mjpeg_qsv | 0.9731 |
  | nvjpeg_422 · mjpeg_cpu | 0.9816 |
  | nvjpeg_420 · mjpeg_cpu | 0.9849 |
  | ff_mjpeg_420 · mjpeg_cpu | 0.9879 |
  | nvjpeg_420 · nv12 | 0.9954 |
  | mjpeg_qsv_420 · mjpeg_cpu | 0.9964 |
  | ff_mjpeg_420 · yuy2 | 0.9968 |
  | nvjpeg_420 · yuy2 | 0.9968 |
  | jpeg_turbo_420 · mjpeg_cpu | 0.9973 |

  - Within 0.1% are only the libjpeg-turbo, FFmpeg `mjpeg` and mjpeg_qsv rows from NV12, and the native 4:2:2 YUY2 rows.
- **H.264/HEVC from mjpeg_cpu:** 0.9647–0.9822 for h264/hevc nvenc/qsv 4:2:0. hevc_qsv_422 is the exception at 0.9953 (0.5% smaller).
- **Not mentioned in the draft:**
  - the H.264/HEVC rows fed YUY2 through swscale are also 1.4–1.6% smaller (0.9837–0.9858);
  - libx264/libx265 from MJPEG are 1.1–2.8% smaller.
- Correction:
  - "Bench bytes are within 0.1% of the sweep for the NV12 and native-YUY2 rows of libjpeg-turbo, FFmpeg mjpeg and mjpeg_qsv.
  - Rows with a swscale or decode step in the feed are 0.2–3.5% smaller: JPEG up to 2.7% (nvJPEG after mjpeg_qsv decode), H.264/HEVC from YUY2 1.4–1.6%, H.264/HEVC 4:2:0 from decoded MJPEG 1.8–3.5% (hevc_qsv_422 0.5%).
  - inferred: the swscale/decoder feed differs from the sweep's numpy feed. NOT VERIFIED."

### R2. Draft §5 flag 1: "Whether those cells ran on the wider mask cannot be told from the files … inferred: x265's thread pool set its own affinity; NOT VERIFIED"

- measured (F1): opening libx265 in PyAV 19.0.2 widens process affinity 16 → 28 CPUs, and the mask stays after the encoder is deleted.
- code/measured: in items 1–3 the libx265 NV12 cell is the 11th cell; the 10 NV12 cells before it ran on CPUs 0–15. Cell order is the order of `runs[]`:
  - S-A1080: 45 cells after it, starting with jpeg_turbo_422·yuy2;
  - S-A720: 32 cells after it;
  - S-B1080: 16 cells after it.
- inferred (from F1 plus `system_after` = 0–27): **every cell after the first libx265 cell in items 1–3 ran with the 0–27 mask.** That covers:
  - every YUY2, MJPEG-CPU, mjpeg_qsv and exact-RGB row;
  - the native-YUY2 4:2:2 rows: jt422 225 fps, mjpeg_qsv_422 481 fps, hevc_qsv_422 64 fps;
  - nvJPEG encode-alone 1,126 fps.
  - Only the first 10 NV12 rows of each item are P-core-only.
  - The scheduler may still have kept these single-threaded cells on P-cores; that is NOT VERIFIED.
- Correction:
  - Replace "cannot be told" with the F1 result: the libx265 open widens the process mask and it does not revert.
  - Mark table §3.3 columns 3–5 ("from YUY2", "after MJPEG CPU decode", "after mjpeg_qsv decode"), the native-YUY2 4:2:2 rows and the exact-RGB row as "0–27 mask (flag 1)".
  - In §3.4, only the NV12 rows before libx265 are P-core-only. In S-B1080 those are all NV12 rows except libx265.

### R3. Draft §5 flag 12: "inferred: the effect here is under about 0.5% for reps of 3 s or more, but can reach about 5% for the shortest unpaced scaling runs (0.29 s)"

- The error from a 15.625 ms CPU-time quantum is relative to the CPU-seconds read, not to wall time.
- measured: the readings are quantised in these files. Single-stream hevc_qsv_420·nv12 reps read `cpu_s` 0.7656, 0.7344, 0.8438, 1.5312 and 1.1719 s (49, 47, 54, 98 and 75 × 15.625 ms) (S-A1080 `runs[]`).
- measured: h264_nvenc 720p unpaced N=1 read 0.203 and 0.156 CPU-s over 0.288 and 0.303 s of wall (`B/matched_concurrent_h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json`). One quantum there is 7.7–10% of the reading.
- inferred: low-CPU paths (QSV, NVENC) in short runs carry several percent of quantisation error per reading. Single-stream hevc_qsv reps at about 0.8 CPU-s carry about 2%.
- Correction:
  - "One 15.625 ms quantum is 15.625 ms ÷ the run's CPU-seconds: under 0.5% for CPU-bound reps of 3 s or more, about 2% for single-stream hevc_qsv (about 0.8 CPU-s), and 8–10% for the unpaced N=1 NVENC 720p runs (0.16–0.20 CPU-s)."
  - Keep summary flag 11 as the source of the granularity.

## 3. Weak claims (true as far as they go, but they need a qualifier)

| # | draft claim | why it is weak | fix |
|---|---|---|---|
| W1 | §2.7 "every NV12, YUY2 and exact-RGB row hits its target at A … the sweep's settings transfer to the bench feeds" | code: the QC encodes the first 4 sources (`S/benchpaths.py:266-288`, `srcs[j]` for j < 4). The sources load C930e first (`S/iclib.py:44-47`, sorted per set at `:133, :143`), so **all 4 QC frames are C930e frames**; the C922 is never QC'd. measured: QC PSNR-Y reads 0.6–0.9 dB above the 16-frame sweep value on every NV12 row (for example jpeg_turbo_420 52.82 vs 52.24, h264_nvenc 54.07 vs 53.22, S-A1080), consistent with the C930e scoring higher (52.65 vs 51.83 dB, `R/camera_jpeg_quality.md`). | Say the QC covers 4 C930e frames and reads about 0.6–0.9 dB above the two-camera sweep mean. A "hit" shows the setting is not grossly off; the byte match with the sweep is the stronger evidence for NV12/YUY2. The misses (nvJPEG from MJPEG) are robust, because the bias runs the other way. |
| W2 | §2.5 / §3.5 / §4 "paced encode-call p99 …" (for example libjpeg-turbo 5.6–6.7 ms vs h264_qsv 18.6–23.1 ms), read as a latency comparison | measured (F2): NVENC returns a packet 2 calls after its frame, h264_qsv/hevc_qsv 4 calls, mjpeg_qsv 3. simplejpeg and nvJPEG return it from the same call. So for NVENC/QSV the call time is not frame-to-packet latency: at 30 fps paced, a frame's packet appears about 2 frame intervals later (NVENC, about 67 ms) or 3–4 (QSV, about 100–133 ms). inferred: those frames are still inside the encoder if the process dies (relevant to G2). | Keep the column but label it "encode call, not frame-to-packet". Add the F2 delays. Do not rank latency across JPEG and NVENC/QSV from this column. |
| W3 | §4 "G7 cost … JPEG needs about 1.7–1.9x the bytes of hardware H.264 intra and about 2.3–2.6x those of HEVC intra" (ratios against jt422) | The baseline is 4:2:2 JPEG and the codecs are 4:2:0, while matching is on SSIM-Y only, so chroma is not matched. measured: at like-for-like 4:2:0, against jpeg_turbo_420 (265,001 B, yuy2_1080p, A), H.264 is 0.60–0.66 and HEVC 0.44–0.49, i.e. JPEG is 1.5–1.7x and 2.0–2.3x (`R/matched_summary.md` bytes as in draft §3.1). measured: the comparison against jt422 survives a full-colour metric. At A the 4:2:0 H.264/HEVC points have `psnr_yuv_422` 53.06–53.25 dB, against jt422's 52.41 (`R/matched_settings.json`, yuy2_1080p), so jt422 is not ahead on chroma-inclusive PSNR. | State the chroma basis. Give both: 1.7–1.9x / 2.3–2.6x against jt422 (keeps the cameras' chroma) and 1.5–1.7x / 2.0–2.3x against jt420 (same subsampling). Cite `psnr_yuv_422`. At B against jt420: H.264 0.33–0.40, HEVC 0.21. |
| W4 | §4 "Storage at A, 1080p30 per camera: jt422 8.9 MB/s; mjpeg_qsv_422 9.9; camera passthrough 4.9; h264_nvenc 4.7; hevc_qsv 3.5" | The list mixes content: passthrough is the MJPEG captures, while the encoder rows are the yuy2_1080p column, which is different and noisier captures (`R/NOTES.md` §2; draft §6). Read side by side, it suggests h264_nvenc ≈ passthrough. On the same MJPEG content at A, h264_nvenc is 123,426 B = 3.7 MB/s (0.76x passthrough), with generation loss. | Label each row with its input class. Split into "YUY2 camera" rows and "MJPEG camera" rows (passthrough 4.9 MB/s against h264_nvenc 3.7 / jt422 4.4 MB/s, both re-encodes with generation loss). |
| W5 | §2.3 / §3.1 MJPEG columns "× camera passthrough", and §4 "best practical hardware re-encode at A saves 24–31%" | For the MJPEG classes, target A is measured against the decoded camera frame (`R/matched_settings.json` `_meta.metric_note`). A re-encode "at A" therefore has the camera's loss plus SSIM-Y 0.9961 of generation loss, so it is less faithful to the scene than the passthrough it is compared with. The draft says this once in §4, but the table header and the 24–31% figure read as matched quality. | Add to the §3.1 header: "MJPEG columns: quality relative to the decoded camera JPEG; ratios to passthrough are not at equal fidelity to the scene." Attach "at lower fidelity than passthrough" to the 24–31%. |
| W6 | §4 "nvJPEG sustains 8 × 1080p30 from host NV12, and 16 from YUY2 with 5–13% late frames" | Both are at the threshold, and the 8-vs-16 split is fragile. measured (C-nvj, N=16 paced): aggregate 471.0–473.2 fps of the 480 needed (98.2%); dropped-equivalent only 56–79 of 7,200 frames; per-stream fps sits just under the 0.98 × 30 cut. measured (C-nvj422, N=16): 479.9 fps, 5.3/13.3% late, p99 39–44 ms. The YUY2 path is the heavier feed yet "passes", while NV12 "fails", over 3 and 2 reps. Item 32 had the run's highest pre-item load sample (14.7% max, BENCH.md §1). | Say "nvJPEG is at its limit near 16 × 1080p30 from either feed (NV12: 98% of the needed rate, 1–3 of 16 streams keep up; YUY2: all keep up with 5–13% late)". Do not present 8 as a firm ceiling. |
| W7 | §4 "h264_qsv sustains 16 × 1080p30 alone"; "mjpeg_qsv sustains 16 × 1080p30 from NV12 (1.05 cores)"; §2.5 "the decisive set" | NV12 is synthetic here: made untimed in numpy from YUY2 (`S/benchpaths.py:8-9, 96-97`). measured: the study cameras deliver YUY2 or 4:2:2 JPEG (`R/NOTES.md` §7, line 226). NV12 is therefore the best case for 4:2:0 hardware paths. From YUY2, h264_qsv needs swscale at 8.44 ms CPU/frame in one stream (S-A1080), and h264_qsv × 16 from YUY2 was not tested at scale. | Qualify: "from NV12 (best case; no conversion; these cameras do not deliver NV12)". List "h264_qsv/mjpeg_qsv 4:2:0 × 16 from YUY2" under not tested. The tested YUY2 pipelines are YUY2 → h264_nvenc (2.53 cores for 12) and mjpeg_qsv 4:2:2 native. |
| W8 | §2.5 / §3.5 / §4 CPU fallback: "libjpeg-turbo 4:2:0 runs 16 × 1080p30 at about 2 cores"; 3,511 / 3,572 fps; "JPEG is the only practical CPU fallback" | The draft never states that the scaling items were pinned to CPUs 0–15 (8 P-cores with HT) of an i7-14700K (`R/BENCH.md` header; summary §2). measured: the unpaced N=16 libjpeg-turbo runs use 14.55 (threads) and 15.32 (processes) cores, i.e. they saturate the 16-CPU pin, so 3,511 / 3,572 fps is a 16-CPU ceiling, not a machine ceiling. The hardware target covers "most CPUs from 2020 on" (HANDOFF §1, req. 3), and this is one high-end desktop. | Add "on 16 logical CPUs (8 P-cores) of an i7-14700K" to every CPU-fallback number and to §3.5. Add to §6: CPU-fallback capacity on lower-end or no-iGPU CPUs is not tested. |
| W9 | §4 "libjpeg-turbo … about 2 cores (inferred: 4.14 ms/frame at N=16 threads × 480 fps)"; "libx264 veryfast about 0.93 cores per stream, libx265 ultrafast about 7.6" | These mix modes. Unpaced per-frame CPU is not the paced per-frame CPU. measured: paced N=1 costs 2.5x unpaced for libjpeg-turbo (process, 7.05 vs 2.81 ms/frame, C-jt-proc) and h264_nvenc (3.82 vs 1.46, C-h264nv). libx265's 252.95 ms/frame was read at 26.9 cores on the widened 0–27 mask (R2). libx264 veryfast ran at 7.1 cores (threaded) in one unpaced stream. | Label them as unpaced-saturation estimates. Keep the measured paced figure (libjpeg-turbo ≥ 1.69 cores, process floor) as the primary number. Mark libx265's 7.6 as "0–27 mask, x265 thread pool; not a P-core figure". |
| W10 | §2.3 / §4 "4:2:2 costs 7–17% more bytes for JPEG and 13–33% for HEVC Rext, with luma unchanged"; "PSNR-Y is identical in every pair" | True in the sweep. The timed bench contradicts it for hevc_qsv fed decoded MJPEG. measured: QC PSNR-Y hevc_qsv_422 49.97 vs hevc_qsv_420 52.53 dB (1080p A, mjpeg_cpu), and 49.53 vs 52.00 (720p) (S-A1080, S-A720). From YUY2 they are equal (54.069 vs 54.071). | Write "luma unchanged in the sweep and from YUY2; from decoded MJPEG, hevc_qsv_422 came out 2.5 dB lower in the bench (§2.7)". |
| W11 | §2.5 "inferred: 390 fps caps hevc_nvenc at 13 × 1080p30 per GPU even without the session limit" | It generalises one SKU and one preset (RTX 3070, p4/ll, CQP at A). | Write "on this RTX 3070 at p4/ll, target A". The 12-session limit for GeForce rests on the cited NVIDIA matrix, not on this run. |
| W12 | §2.5 "inferred: threads scale like processes, so simplejpeg does not serialise on the GIL" | Thread mode is 1 unpaced rep (item 11), short runs (wall 0.83–1.37 s), against 3 process reps. The inference is sound (14.55 cores used by threads), but the evidence is one run. | Add "(1 thread rep)". |
| W13 | §3.1 / §3.2 nvJPEG rows | The sweep fed nvJPEG exact float BT.601 RGB (`R/matched_settings.json` nvjpeg_420 `options.input`), which is not what a recorder would feed. The bench's swscale feed gave a different quality on the same frames (QC 52.34 vs 51.36 dB from exact RGB, S-A1080). | Mark the nvJPEG rows "exact-RGB input (sweep)". Point to §2.4 for the swscale feed. |
| W14 | §4 implications and §5 flag 11 (Defender), with no write cost in §4 | Packets were discarded (`S/bench_matched_stream.py:12`; concurrent loop `S/bench_matched_concurrent.py:60-62, 73-75`), so these items exclude the write path. They also exclude Defender's real-time scanning cost, which is large for folder-of-files writing (summary §2; `results/write_throughput/BENCH.md`). Flag 11 lists MsMpEng CPU-s during items that wrote no files, which a reader could take for a write cost. | Add to §4: "encode only; the JPEG recording cost also depends on the writer (folder-of-files triggers Defender scanning; containers do not, per write_throughput)". In flag 11: "MsMpEng CPU during these items is not a write cost (no files were written); its cause is NOT VERIFIED". |
| W15 | §2.4 "decoding camera MJPEG on the CPU first limits one stream to 152–243 fps for most paths, at 6.4–14.4 ms CPU/frame (libx264/x265 excepted)" | measured (S-A1080 mjpeg_cpu): nvJPEG 140–145 fps and hevc_qsv 66–68 fps are also outside 152–243; 9 of the 13 non-x264/x265 paths are inside. | Name the exceptions: "nvJPEG 140–145, hevc_qsv 66–68". |

## 4. Lenses checked with no problem found

- **N=16 NVENC rows read as 12:** done throughout (§2.5, §2.6, §3.5 header "12 for NVENC"; summary flag 3).
- **Matched quality:**
  - §3.1 and §3.2 are interpolated at the target;
  - the bench rows are at the chosen integer step, and knob-step shortfalls are flagged (§2.7, §3.4);
  - the nvJPEG MJPEG-feed rows are marked as not at matched quality (flag 3).
- **Clip quality kept apart from A/B:** the intra_playback 54.5–55.0 dB clips are kept separate (§6).
- **Intra vs GOP:** IDR-only is verified in the sweep (`R/verification.md`). The bench reuses the same `gop_size` and options (`entry` block; `S/benchpaths.py` `Encoder.__init__`). No GOP result is used.
- **Single runs:** stated (flag 9). Min–max over 2 reps is noted as just the two values.
- **Page-cache vs cold opens:** not applicable (no file opens).
- **Functional pass vs compatibility:** PyAV decode is not presented as browser support. Electron playback of libx265 Rext 4:2:0 is NOT VERIFIED (§6), and HEVC 4:2:2 playback is cited from chromium_codecs.
- **One SKU generalised:** stated in §6 ("RTX 3070 and UHD 770 only"), apart from W8 and W11.
- **Process CPU as a lower bound, and the negative readings:** stated (flag 6) and matches the JSON (−2.22 / −2.44 in item 10, −1.15 in item 55).

## 5. Status of the run flags (BENCH_RUN_2300_SUMMARY §3) in this draft

| flag | in the draft | status |
|---|---|---|
| 2 libx265 affinity | flag 1 | needs R2 |
| 3 NVENC 12 sessions | §2.6, flag 2 | ok |
| 4 nvJPEG MJPEG miss | §2.7, flag 3 | ok |
| 7 write latencies | flag 14 (not this topic) | ok |
| 9 uncompressed_intra lossless | flag 14 (not this topic) | ok |
| Defender (summary §2) | flag 11 | needs W14 |
| 11 timer granularity | flag 12 | needs R3 |
| 12 single runs | flag 9 | ok |
