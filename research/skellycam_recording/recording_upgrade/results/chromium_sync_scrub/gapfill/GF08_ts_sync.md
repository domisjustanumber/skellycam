# GF08: multi-camera sync by capture timestamp in a master-clock player (G9), exactness only

Date 2026-11-10, machine Gerald (Windows 11, RTX 3070 driver 610.88, UHD 770 present). Functional test; **no timing numbers** (no latency, fps or CPU). The nanosecond values below are capture timestamps and rule thresholds, not measurements of the machine.

Labels: **measured** (result file + key), **code** (file:line), **inferred**. Paths are relative to `research/skellycam_recording/recording_upgrade/`. `R` = `results/chromium_sync_scrub/gapfill/`, `S` = `scripts/chromium_sync_scrub/gapfill/GF08/`.

Files:
- `R/GF08_ts_sync.json`: raw rows from both Electrons, conventions, offsets, mismatch table, offline checks.
- `R/GF08_generation.json`: streams, offsets, gaps, file checks. `R/GF08_sidecars.json`: per-camera k → ts_ns. `R/GF08_ticks.json`: the 456 ticks.
- Scripts: `S/gen_gf08.py` (PyAV 19.0.2), `S/run_gf08.py` (runner + offline check), `S/harness/` (a copy of `scripts/chromium_sync_scrub/harness/` that adds `test=tssync`; the original harness was not edited).
- Media: `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/gapfill/GF08/`.

## 1. Setup

### 1.1 Streams on one shared clock

Rule: `ts_ns = os_timestamp_ns[orig] - os_timestamp_ns[0 of that set] + offset_ns` (code: `S/gen_gf08.py` `main`). Timestamps come from `jp_common.real_timestamps_ns`, which checks every frame's `payload_bytes` against the corpus file size (code: `scripts/jpeg_passthrough/jp_common.py:48-56`).

| cam | source set | offset_ns | frames kept | first / last ts_ns | gaps |
|---|---|---|---|---|---|
| cam0 | c930e_720p_flash | 0 | 891 (all) | 0 / 29,568,024,200 | none |
| cam1 | c922_720p_flash | +7,654,321 | 893 (all) | 7,654,321 / 29,751,641,021 | none |
| cam2 | c930e_720p_flash | −3,000,000 | 776 | 1,325,039,000 / 29,565,024,200 | late start (orig 0–39 dropped), orig 400–459 (60 frames), every orig index divisible by 50: 16 gaps |
| cam3 | c922_720p_flash | +19,876,543 | 697 | 19,876,543 / 23,331,848,143 | early end (orig 700–892 dropped), orig 300–302 (3 frames) |

- measured: offsets, first/last ts and gaps are in `R/GF08_generation.json` → `cameras.<cam>` and `offset_ns`.
- measured: in the raw capture, c930e started 164,995,500 ns after c922 (`R/GF08_generation.json` → `raw_start_difference_ns_c930e_minus_c922`). The test removes this offset on purpose (own t0 per set, then the known offsets above).
- measured: both sets are strictly increasing (`sets.<name>.strictly_increasing`). The c930e set contains the 0.011 ms pair (orig 81/82, 11,000 ns apart; `R/GF08_ts_sync.json` → `offline.intervals.cam0.min_ns`).

### 1.2 Files per camera (PyAV 19.0.2, libavcodec/libavformat 63.1.102)

| path | content | identity read back in the page | file checks (measured, `R/GF08_generation.json` → `cameras.<cam>.files`) |
|---|---|---|---|
| `jpeg` | camera's own JPEG bytes in MKV (`add_mux_stream('mjpeg')`, time base 1/1000) + byte-range index | SHA-256 of the Range-fetched bytes, looked up in that camera's own hash table; `ImageDecoder` decode complete at 1280×720 | `byte_identical_to_corpus` = frames (891/893/776/697); `pos_delta_hist {"4": n}` |
| `jpegbc` | same frames, barcode `cam*4096 + k` burned in, FFmpeg `mjpeg` 4:2:2, `qmin=qmax=2` (target A, `matched_settings.json` `ff_mjpeg_422/mjpeg_720p`), MKV + index | 16-bit pattern from the `ImageDecoder` output | software decode-back: barcode correct on every frame (`decode_back.barcode_ok` = frames) |
| `h264` | same barcoded frames, **h264_nvenc** all-intra at target A (`h264_nvenc_420/mjpeg_720p`: preset p4, tune ll, constqp qp 14, i_qfactor 1, i_qoffset 0, gop_size 0, max_b_frames 0), MP4 +faststart, 1/90000 + index | 16-bit pattern from the WebCodecs `VideoFrame`, `flush()` after each chunk | NVENC opened (no fallback; `nvenc_error` null); `all_key` true; decode order = pts order; ffprobe 9.0.2: key_frame 1 and pict_type I on every frame; barcode correct on every frame |

- The barcode layout and reader are the ones from `scripts/intra_playback/gen_intra_clips.py` (`burn_index`, `read_index_y`) and the harness `readIndex` (code: `scripts/chromium_sync_scrub/harness/harness.mjs:42-56`).
- Limit: cam0 and cam2 hold the same c930e bytes, so the `jpeg` path cannot detect a cam0/cam2 mix-up. The barcode paths can, because they check `cam`.

### 1.3 Rules and conventions (sidecar only, integer ns)

P = 33,333,333 ns, the nominal period from `nominal_fps` 30 in `corpus/index.json` for both sets.

| case | PREV (largest ts ≤ T) | NEAREST (min \|ts − T\|, ties → earlier) |
|---|---|---|
| T before the first frame | **none** (`before_start`) | frame 0 if 2·\|ts₀ − T\| ≤ P, else **none** |
| inside the stream | frame k | frame k |
| inside a gap | **hold** the frame before the gap; flag `hold_stale` if T − ts_k > P | nearest frame; flag `hold_stale` if 2·\|ts_k − T\| > P |
| after the last frame | hold the last frame while T − ts_last ≤ P, then **none** (`after_end`) | last frame if 2·\|ts_last − T\| ≤ P, else **none** |

- code: page `gfPrev` / `gfNearest` (`S/harness/harness.mjs:646-663`); independent Python `exp_prev` / `exp_nearest` (`bisect`; `S/run_gf08.py:54-74`).
- "none" means the tile shows no frame, and nothing is decoded.

### 1.4 Ticks

456 fixed master-clock ticks (`R/GF08_ticks.json`), visited in a fixed shuffled order (seed 80), so the mapping is used statelessly, as in a scrub. Tags (one tick can carry several): exact 62, mid 58, mid+1 ns 58, −1 ms 62, +1 ms 62, gap 27, gap edge (±1 ns) 10, gap + P 5, gap + P + 1 ns 5, before start 28, after end 32, random 60 (measured: `R/GF08_ts_sync.json` → `tick_why_hist`).
- The ticks include exact frame timestamps, exact ties (midpoints; all timestamps are multiples of 100 ns plus a per-camera constant, so midpoints are exact), the 0.011 ms pair (cam0 k 81/82 and the same frames in cam2), each convention boundary, and the inside of every gap.

## 2. Results (N = 4 cameras, E35.7.5 / Chromium 134.0.6998.205 and E45.2.3 / Chromium 156.0.8078.80)

### 2.1 Mismatch table

Identity mismatch = expected none but something was decoded, or the read id ≠ the expected k, or (barcode paths) the read cam ≠ cam, or the decode failed. Selection mismatch = the page's chosen (k, status) ≠ Python's.

| path | rule | Electron | cam0 | cam1 | cam2 | cam3 |
|---|---|---|---|---|---|---|
| jpeg (camera bytes, ImageDecoder) | PREV | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpeg | PREV | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpeg | NEAREST | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpeg | NEAREST | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpegbc (barcode JPEG, ImageDecoder) | PREV | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpegbc | PREV | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpegbc | NEAREST | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| jpegbc | NEAREST | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| h264 (h264_nvenc intra, WebCodecs + flush) | PREV | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| h264 | PREV | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| h264 | NEAREST | E35 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |
| h264 | NEAREST | E45 | 0 / 456 | 0 / 456 | 0 / 456 | 0 / 456 |

- measured: 0 identity mismatches, 0 selection mismatches and 0 decode failures in all 48 cells (`R/GF08_ts_sync.json` → `mismatch_table`).
- measured: per path and Electron, 3,157 (camera, rule, tick) cases decoded a frame and 491 were "none" (count of `electron.<ver>.rows` with `chosen_k` ≥ 0 / < 0).
- measured: page errors 0, WebCodecs decoder errors 0 and decoder re-creations 0 per camera in both Electrons (`electron.<ver>.per_path`). `isSecureContext` was true, so `crypto.subtle` was available.
- measured: the 174 rows that chose cam0 k 81 or 82 (the 0.011 ms pair) were all correct, across all paths, rules and both Electrons (count from `electron.*.rows`).
- measured: the active Chromium GPU was the NVIDIA device (`electron.<ver>.gpu_device`, `active: true` on vendor 4318). The UHD 770 was listed but inactive.

### 2.2 Before start, after end and gaps

Expected status counts over the 456 ticks (measured: `R/GF08_ts_sync.json` → `status_counts`; the page agreed on every row, 2.1):

| rule | cam | ok | hold_stale | before_start (none) | after_end (none) |
|---|---|---|---|---|---|
| PREV | cam0 | 417 | 3 | 15 | 21 |
| PREV | cam1 | 410 | 20 | 21 | 5 |
| PREV | cam2 | 330 | 35 | 68 | 23 |
| PREV | cam3 | 328 | 28 | 27 | 73 |
| NEAREST | cam0 | 412 | 10 | 9 | 25 |
| NEAREST | cam1 | 413 | 24 | 12 | 7 |
| NEAREST | cam2 | 312 | 52 | 65 | 27 |
| NEAREST | cam3 | 339 | 24 | 18 | 75 |

- measured: `hold_stale` also fires on cameras with no synthetic drops (cam0, cam1). With threshold P, 71 (cam0) and 75 (cam1) real consecutive intervals exceed P; none exceed 1.5·P. Consecutive-interval median is 32,002,000 ns (cam0) and 32,002,400 ns (cam1); max is 48,097,600 and 48,060,100 ns (`offline.intervals`).
- inferred: a staleness / end-hold threshold of P flags normal capture jitter. A threshold of 1.5·P would flag only the synthetic drops in this data. Only P was run in the browser.
- measured: chosen-frame distance from the tick (a property of the rule, not a runtime measurement): PREV `ok` ≤ 33,333,333 ns; NEAREST `ok` ≤ 16,666,666 ns (`offline.chosen_frame_distance`).

### 2.3 The existing harness helpers on the same ticks (seconds, float)

`floorIdx` and `nearestIdx` (code: `scripts/chromium_sync_scrub/harness/harness.mjs:57-67`) were evaluated in the page on `ts_ns / 1e9` (measured: `R/GF08_ts_sync.json` → `harness_helpers`; identical in E35 and E45):
- measured: neither helper has a "none" result. Before the first frame both return 0; after the last frame both return the last index (`helper_value_before_start_0`, `helper_value_after_end_<last>`). code: `floorIdx` starts at `r = 0` (`harness.mjs:64`).
- measured: `floorIdx` ≠ PREV on 5 defined ticks (cam2 4, cam3 1). All 5 are `gap_edge` ticks 1 ns before a frame. code: the `+ 1e-9` s tolerance (`harness.mjs:65`) picks the next frame.
- measured: `nearestIdx` ≠ NEAREST on 18 defined ticks (cam0 4, cam1 2, cam2 9, cam3 3). Every one is an exact tie (`mid` or a gap midpoint); float seconds made the later frame look nearer. This includes the 0.011 ms pair midpoint on cam2 (`mismatch_examples_where_defined`).
- inferred: the existing bench never hit these cases, because its master clock starts at the first pts (`harness.mjs:430`). A player built on the helpers as written would show frame 0 before a late camera starts and the last frame forever after an early end.

### 2.4 Offline checks (Python only, no browser)

**Rule on container pts instead of the sidecar** (measured: `offline.container_pts_instead_of_sidecar`):

| container | max \|pts − ts\| (ns) | ticks where the rule gives a different answer than the sidecar (per cam × rule, of 456) |
|---|---|---|
| MKV (1/1000) | 386,479 to 1,010,000 | 14 to 31 |
| MP4 (1/90000) | 5,534 to 5,545 | 5 to 28 |

- measured: every differing tick lies within the container's rounding error of a rule boundary (timestamp, midpoint, ts + P, ts ± P/2): at most 327,433 ns (MKV) and 1 ns (MP4) (`max_distance_of_differing_tick_from_a_rule_boundary_ns`). The differences are ±1 frame or a status flip at an edge (`k_container_minus_k_sidecar_hist`).
- measured: the 1,010,000 ns MKV maximum for c930e comes from the 0.011 ms pair: one pts was bumped to stay increasing (`R/GF08_generation.json` → `files.jpeg.pts_bumped_for_monotonic` = 1 on cam0 and cam2).
- inferred: container pts are good enough to display a frame, but they are not the same rule. Exact, reproducible selection needs the recorder's own integer timestamps (the sidecar).

**Frame-index sync** (every camera shows the index k₀ that cam0 shows under PREV) vs timestamp PREV (measured: `offline.frame_index_sync_vs_timestamp`):

| cam | ticks where both rules show a frame | index rule = timestamp PREV | index rule: frame captured > P from cam0's frame | timestamp PREV: same check (of which `hold_stale`) |
|---|---|---|---|---|
| cam1 (no drops) | 414 | 58 | 321 | 0 (0) |
| cam2 (late start + drops) | 328 | 0 | 328 | 27 (27) |
| cam3 (early end + gap) | 338 | 27 | 296 | 9 (6) |

- measured: index sync is wrong even for cam1, which has no drops. The two cameras' real intervals differ (c930e median 32,002,000 ns, c922 32,002,400 ns, min 11,000 vs 31,316,400 ns), so frame k drifts apart in capture time (`offline.intervals`).

## 3. Recommendation for the G9 mapping rule

- **inferred (from measured 2.1, 2.3, 2.4): map master-clock time to frames by capture timestamp, rule PREV, in integer nanoseconds, from a per-camera sidecar on one shared clock.**
  - measured: PREV and NEAREST were both exact on every tick, path, camera and Electron (2.1). Either rule is implementable.
  - Why PREV over NEAREST:
    - inferred: PREV never shows a frame captured after T.
    - measured (2.3): PREV has no ties to break; NEAREST's tie rule broke in float seconds on 18 exact-tie ticks.
    - measured (2.2): NEAREST keeps the shown frame closer to T (≤ P/2 vs ≤ P). Choose NEAREST only if that matters more than the two points above. If so, it must use integer ns with an explicit tie rule.
  - Conventions to adopt (tested at threshold P, 2.2):
    - none before a camera's first frame;
    - hold inside gaps, with a stale flag;
    - hold after the last frame up to a limit, then none.
    - inferred: set the stale/end limit to about 1.5·P, because P flags normal jitter (2.2). Not run in the browser.
  - measured (2.4): do not sync by frame index. Do not select by container pts when exactness matters; the MKV 1 ms time base moves boundaries by up to about 1 ms.
  - code (2.3): if the harness helpers are reused, `floorIdx` / `nearestIdx` need a "none" result, no `+1e-9` tolerance, and integer timestamps.
- Scope limits:
  - Functional only; no timing.
  - One machine, NVIDIA D3D11 decode.
  - 720p only; N = 4.
  - Ticks come from a fixed list, not from rAF playback.
  - Synthetic drops on real timestamps; the camera clocks were aligned by construction (own t0 + known offsets), so cross-camera clock alignment in a real recording is NOT VERIFIED here.
  - HEVC and `<video>` were not tested in this gap-fill.

## 4. Proposed replacement text

### 4.1 chromium_sync_scrub FINDINGS §6, line 275

Old (line 275):
> - No multi-camera clips with different capture times: all N streams in `bench_sync` are the same clip. Sync by capture timestamp vs by frame index is an open design question.

Proposed:
> - `bench_sync` uses the same clip for all N streams. Multi-camera sync by capture timestamp was tested separately and functionally in gap-fill GF08 (`gapfill/GF08_ts_sync.md`). N = 4 cameras from the real c930e/c922 720p timestamps on one shared clock, with late start, a 60-frame gap, every-50th drops, early end and a 3-frame gap; 456 fixed ticks. Rules PREV and NEAREST (integer ns, sidecar only) gave 0 identity mismatches for camera JPEG bytes, barcoded JPEG (ImageDecoder) and h264_nvenc intra at target A (WebCodecs + flush), in E35 and E45 (measured: `gapfill/GF08_ts_sync.json` `mismatch_table`). Frame-index sync matched timestamp PREV on only 58/414, 0/328 and 27/338 ticks for cam1-3 (measured, offline: `offline.frame_index_sync_vs_timestamp`). Not tested: `<video>` paths, HEVC, rAF-driven playback, and real cross-camera clock alignment.

### 4.2 chromium_sync_scrub FINDINGS §4 I3, line 227

Old (line 227):
> - **I3** (F15, F16, F16a, F7): only the index-driven paths (WebCodecs, JPEG) were exact in every run, including the near-duplicate pair (WebCodecs; JPEG not targeted). A single master clock can then choose frame k for every camera. Their cost is unmeasured (section 5), so the plan must not pick between I2 and I3 until tonight's bench has run.

Proposed:
> - **I3** (F15, F16, F16a, F7; GF08): only the index-driven paths (WebCodecs, JPEG) were exact in every run, including the near-duplicate pair (WebCodecs in F16a; camera JPEG and h264_nvenc intra in GF08). A single master clock chooses, **per camera**, the frame whose capture timestamp is the largest one ≤ T (rule PREV). It uses integer-ns timestamps from a per-camera sidecar on one shared clock, shows nothing before a camera's first frame, holds inside gaps with a stale flag, and shows nothing after a hold limit past the last frame. measured (GF08): 0 mismatches over 456 ticks × 4 cameras for JPEG and H.264 intra in E35 and E45; frame-index sync and float-seconds helpers do not give this rule (GF08 §2.3, §2.4). Their cost: intra_playback F17-F20 (timed run 20261109T230007).

## 5. Reproduce

```
# repo root C:/Users/Dom/GitHub/freemocap/skellycam
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gapfill/GF08/gen_gf08.py
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gapfill/GF08/run_gf08.py            # E35 + E45, then analysis
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gapfill/GF08/run_gf08.py --analyze-only
```
- The runner removes `ELECTRON_RUN_AS_NODE`, sets `CSS_MEDIA_ROOT` to the GF08 media dir and `CSS_USER_DATA` to the step3 temp dir, and passes `--noocclusion=1`. Raw page output goes to `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF08/raw_e{35,45}.json` and is copied into `R/GF08_ts_sync.json` → `electron.<ver>.rows`.
