# crash_resilience: VERIFY_method (post-bench revision, 2026-11-10)

This is an adversarial check of the methods in the updated draft FINDINGS (the one with §2.11–2.13 built from run `20261109T230007`). It was run on machine "Gerald" on 2026-11-10. The previous report is `VERIFY_method.prev.md`.

- Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless they start with `research/` or `scripts/`. `scripts/` = `research/skellycam_recording/recording_upgrade/scripts/`.
- **No timing was produced or used here.** Every bench number was recomputed from the `repeats[]` arrays in `bench/*_pyav19.json`. They all match the draft, including medians, min–max, B/frame, the s/GB figures and the 3.9 % spread.
- New checks were functional only: PyAV 19.0.2 via `uv run --script`, counts only. Each needed a few seconds of CPU. NVENC was used for about 10 s in total.

**New evidence files (2026-11-10)**

| file | what it shows | script |
|---|---|---|
| `verify_method2_intra_kill.json` | intra NVENC H.264/HEVC (bench settings, `gop 0`): encoder hold-back at a 30 fps feed, and a live `rt` kill into mkv+fp after 75 frames fed | `scripts/crash_resilience/pyav19_checks/verify_method/step2/intra_check.py` (+ `child_wrap.py`, which registers the payloads from `bench_fragment_overhead.py:45-48`, then runs `writer_child.py`) |
| `verify_method2_intra_hold.json` | intra NVENC hold-back with and without `delay=0`, run twice | `.../step2/intra_delay0.py` |
| `verify_method2_template_keyframes.txt` | keyframe flags of tonight's CR-FRAG-INTRA templates (mtimes 04:35:58 and 04:36:02, inside item 61) | `.../step2/template_keyframes.py` |

## 1. Refuted

| draft claim | evidence | correction |
|---|---|---|
| §4 item 1: MKV+fp "has the lowest overhead of the crash-safe options, 45.8 B/frame (§2.12)" | measured, `bench/fragment_overhead_mjpeg_pyav19.json`: nut+fp 28.67, avi+fp 26.40 and rawidx 32.0 B/frame. All three lost 0 frames in the drained kill (§2.1, bg for rawidx). fmp4_frag_500/1000/2000+fp are 16.7/12.5/10.4 B/frame. | "45.8 B/frame. NUT (28.7), AVI (26.4) and raw+index (32.0) are lower but are rejected for torn frames, bad seeks and no Chromium support. All of these are ≤ 0.24 % of the payload, so overhead is not a deciding factor." |
| §2.5, §3B, §4 item 3 and §6: the intra NVENC hold-back and kill behaviour are "not measured" / "not tested", and inferred as "1 frame plus whatever the encoder holds" | measured, `verify_method2_intra_kill.json`: bench settings (`preset p4`, `tune ll`, `constqp`, QP 14 / 11, `bf 0`, `gop 0`), 75 frames paced at 30 fps. **h264_nvenc and hevc_nvenc each held 2 packets** (73 before the drain), and all 75 packets were key frames. Live `rt` kill into mkv+fp: **73 muxed, 72 readable of 75 fed** for both codecs (ffprobe = PyAV = 72; 72/72 demuxed packets are key; the PyAV seek is exact). `verify_method2_intra_hold.json` gives 2 held without `delay=0` and 0 held with `delay=0`, for both codecs, in 2/2 runs. | "Intra NVENC under a live kill loses 3 frames at 30 fps: 2 held by the encoder plus 1 in the open Cluster (measured, P19, one 75-frame kill per codec). With `delay=0` the hold-back is 0 (measured, hold count only). A kill test with `delay=0` and the cost of `delay=0` were not measured." |

## 2. Weak: reword, relabel or qualify

1. **Cross-payload wall-time comparisons in §2.12, §3A and the "HEVC is fastest" sentence.**
   - Why the comparison is confounded:
     - The intra rows open the template file *inside* the timed region; the MJPEG rows don't (code, `bench_fragment_overhead.py:124` timer start, `:147-148` `av.open(template)` + `add_stream_from_template`).
     - MJPEG uses `add_stream("mjpeg")` instead (`:143`).
     - The MJPEG item ran at 00:52 and the intra item at 04:35 (log orders 19 and 61). H.264 always ran before HEVC (`:181`).
   - Within-payload deltas (fp vs no fp) are fine. Differences between payloads are not.
   - Fix: say "the wall columns are comparable within a payload only", and drop or label the HEVC vs H.264 vs MJPEG ranking.
2. **The "target A" label on the intra payloads.**
   - The bench feeds `yuv420p` (`bench_fragment_overhead.py:45-48`, `:70`), but matched_settings uses `pix_fmt_fed` = `nv12` and limited-range input (`research/skellycam_recording/recording_upgrade/results/intra_compare/matched_settings.json` → `_meta.apply`, `h264_nvenc_420.mjpeg_720p`).
   - The QP was calibrated on a different camera-MJPEG corpus: `_meta.camera_passthrough_bytes_per_frame.mjpeg_720p` = 66,594.1 B/frame, against 55,341 B/frame here.
   - So these packets use target A *QPs*, but they are not verified to be at target A on this content.
   - Fix: "target A QPs from matched_settings (calibrated on another corpus, fed nv12); this payload's quality is not measured; it is not a target A result." That size is what drives the µs/frame differences between payloads.
3. **All-intra rests on inference (§2.12, §5).** Now measured: tonight's templates have **300/300 key frames** for both codecs (`verify_method2_template_keyframes.txt`; the files were written during item 61). Fix: change "inferred" to measured and cite this file.
4. **"container bytes do not depend on the payload codec" (§2.12).** This is true for MKV, fMP4, NUT and plain MP4. It is false for the segment muxer: seg_mkv_1+fp is 61.42 / 63.82 / 66.42 B/frame for MJPEG / H.264 / HEVC (measured, both fragment JSONs). Fix: exclude segments. A likely cause is codec private data repeated in each segment's header (inferred, not checked).
5. **fsync figures generalised to "this disk" (§2.11, §3B, §4 item 10).**
   - The drive is not recorded in the CR JSONs (`drive` "C:" only). `results/write_throughput/BENCH.md:4` names it: WD_BLACK SN850X NVMe, the OS disk.
   - fsync cost is a property of the drive and its cache (inferred). Here it is one SKU, one run of 3 back-to-back repeats.
   - Fix: name the drive with that citation, and say the numbers don't transfer to SATA SSDs or HDDs.
6. **§4 item 10, "every 30 frames or less often, never every frame".** The data do not support "or less often" or "never every frame":
   - K=300 has the largest median stall, 12.4 ms (6.7–12.6). K=30: max 3.6–9.1 ms. K=1: max 8.7 ms, p99 0.67 ms (`bench/fsync_pyav19.json`).
   - K=1 still has throughput headroom for one camera: 127 MB/s against 1.66 MB/s (computed). BENCH.md §3.1 says the same.
   - Less frequent fsyncs also widen the power-loss window, and the power-loss benefit itself is NOT VERIFIED (§6).
   - Also, "max 4.2–9.1 ms" mixes a median with a maximum. The repeat maxima are 3.6–9.1 ms.
   - Fix: present K as a trade-off (stall size and power-loss window against per-frame cost). Say that multi-camera cost is unmeasured, and that only the sidecar and journal can be fsynced in the current design. Sidecar-only fsync was benched only at K=1.
7. **The Defender cost lies outside the measured per-frame numbers (§2.12, §4 item 12, §5).**
   - MsMpEng CPU is another process, so it is not in the bench's `wall_s`/`cpu_s`, except where a scan blocks the writer.
   - In item 19, MsMpEng used 5.38 CPU-s. Its `folder` variant created 9000 files (3 × 3000). If all of that CPU went to the folder variant, it would be about 600 µs/file (computed upper bound, inferred attribution).
   - That is more than the 207.3 µs/frame measured for the writer.
   - Also, §5 says "the higher value for item 19", but item 28 (repair, 10.25 CPU-s) is the highest of the four.
   - Fix: say that 207.3 µs/frame is the writer's cost only and excludes Defender's CPU, and correct the item reference.
8. **Cross-topic open times in §4 item 11 are warm, repeated opens.**
   - In `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/open_long.json`, the first open is slower than the median: MKV 4.93 ms vs 0.19; fMP4 per-frame 1111.88 vs 1107.28; fMP4 1 s 55.1 vs 42.57.
   - The files had just been written: 3 GB each, 54,000 frames, `fmp4_*_tb_us` time base.
   - Fix: write "median of 5 back-to-back opens of a just-written file (page cache); the first open was 4.93 ms (MKV) and 1111.88 ms (fMP4 per-frame); cold open not measured".
9. **Raw .mjpeg repair "gives back all" (§2.13, §3A).**
   - The input was a drained, quiescent kill (`writer_child.py` `drained:N`), so no frame was torn.
   - The repair demuxes with `-f mjpeg` and does not use the CRC index (`bench_repair.py`, `common_cr.remux_pyav`).
   - After a mid-write kill or cut, raw MJPEG counts the torn frame (bg, §2.4).
   - Fix: "all 17,618 in a quiescent kill; after a mid-write kill the plain demux hands out the torn frame unless the CRC index is used".
10. **Balance in §4 item 11.** fMP4 per-frame muxes *faster* than MKV+fp for every payload, with non-overlapping ranges:
    - MJPEG 23.5 (23.4–23.7) vs 24.9 (24.8–25.0);
    - H.264 21.5 vs 22.4;
    - HEVC 17.0 vs 17.9 µs/frame.

    The 2.9× container bytes is 0.24 % vs 0.08 % of the payload. Fix: say that MKV's advantages are no torn samples, the open time and the repair time, not mux cost or bytes.
11. **Repeats (§2.11–2.13).** The 3 repeats ran back-to-back in one process, within one run (`bench_fragment_overhead.py:181-190`; the same in `bench_fsync.py`). Variants ran in a fixed order, not interleaved. The min–max is within-run noise, not run-to-run variation (summary flag 12 applies). Fix: one sentence in §5.
12. **§4 item 6, segment length vs repair time.** The repair after a power loss runs after a reboot, so the cache is cold by definition (inferred). The 0.907 s/GB figure is the in-cache case only, a process crash without a reboot. It is already labelled "cold-cache not measured". Fix: tie that caveat to the power-loss case explicitly.

## 3. Checked and holding

| item | check |
|---|---|
| §2.11–2.13 numbers | recomputed from `repeats[]`. All match, including the 3.9 % spread and "first repeat slowest only for the mkv+fp methods". |
| P-core claim, no libx265 exception | `BENCH_RUN_2300_LOG.jsonl` orders 18, 19, 28 and 61: `affinity` "pcores". The runner sets affinity before `Popen`, so children inherit it (code, `scripts/bench_runner/run_queue.py:21-22`, `:441-443`, `:461`). The CR scripts don't use libx265. |
| Quiet machine | CPU before the items averaged 5.40 / 3.59 / 3.59 / 3.89 %, with no `load_over_15pct` and no Defender scan event. MsMpEng CPU was 1.05 / 5.38 / 10.25 / 1.36 s (log). |
| NVENC 12-session flag | Not applicable. CR-FRAG-INTRA opens one encoder, untimed (`bench_fragment_overhead.py:63-77`). |
| Page cache | Stated correctly for the fragment and repair results. `free_ram_mb_start` 49,399 (`bench/repair_pyav19.json`). |
| 15.625 ms CPU tick | Every `cpu_s` in the fragment JSONs is a multiple of 0.015625. The latencies use `perf_counter_ns` (`bench_fsync.py`). |
| p99 = fsync frame at K ≤ 30 | `pct()` uses index `int(0.99 × 3000)` = 2970. At K=30 there are 100 fsync frames (indices 2900–2999), at K=300 only 10 (code, `bench_fsync.py` `pct`). |
| Clip quality vs targets | No quality-dependent claim in this topic is tied to target A/B, except the intra payload label (weak item 2). |
| `mkv_fp_fsync` confounder | Disclosed correctly: a file-object writer (`bench_fsync.py:56-79`). |

## 4. Verdict

**Needs revision before it is saved.** Two claims are refuted:
- the "lowest overhead" wording;
- intra NVENC kill/hold-back "not tested". It is now measured: 2 held, 72/75 readable on a live kill, 0 held with `delay=0`. §2.5, §3B row "encoder hold-back", §4 item 3 and §6 must change.

The main method fixes:
- cross-payload wall comparisons are confounded (template open inside the timer, a different stream setup, run 3.7 h apart);
- the intra payloads are not verified to be at target A (nv12 vs yuv420p, another corpus);
- the fsync recommendation overreaches the data, and the results are from one drive;
- Defender CPU lies outside the measured per-frame numbers;
- the cross-topic open times are warm.

The bench numbers themselves are reproduced exactly from the JSON.
