# write_throughput: VERIFY_method (post-bench draft, 2026-11-10)

Adversarial methodology check of the updated draft FINDINGS (given inline, not on disk), after the quiet run `20261109T230007`. The previous pass (2026-11-09) is kept as `VERIFY_method.prev.md`.

Prefixes: `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`, `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`, `RU` = `research/skellycam_recording/recording_upgrade`. Labels: **measured**, **source**, **code**, **inferred**. The verifier ran no timed measurement.

## 0. Verdict

**Pass with corrections.** The spot-checked numbers match the JSON. The main conclusions hold: no drops in 77 cells, the Defender cost of a folder of JPEGs, append/MKV/fMP4 being close on throughput, and the crash results. Six statements are wrong or mis-cited (section 2). Several more need scoping (section 3):
- the Defender window;
- the whole-system cost of files;
- long-file behaviour of mkv_flush;
- the ordering in the usability bench;
- the hardware-target scope.

## 1. What was checked, and the verifier's own functional check

| Check | Result |
|---|---|
| focus16_av19 p50, bench CPU, MsMpEng and sys busy per rep, against the daytime `bench/focus16/` | Draft values match. Same config (ring_s 2.87, 30 s); env av 18.0.0 for the daytime run and 19.0.2 tonight (measured, cell JSONs). |
| models16_av19 bench CPU, tick->written p99 and write p50 per rep | Recomputed (section 2, items 1-2). |
| long_av19: p50, p99.9, max, tick->written, grab-late, bench CPU, MsMpEng, files, delete, PhysicalDrive0 delta | Match the draft. |
| core_av19 files MsMpEng and `files_written` | Match (e.g. 16 cam 1080p30: 14.266 CPU-s, 9616 files). |
| `first_read_check_5000.json` | The wall time (20.594033 s) and MsMpEng (20.59375 s) really are separate readings that happen to agree, not a copy bug (code `SCR/first_read_check.py:46-59`). |
| `crash_resilience/bench/fsync_pyav19.json` | flush p50 16.3 us, 2484 MB/s; fsync_every_1 p50 409.3, p99 669.0, max 8735.9 us, 127 MB/s. Match. |
| MsMpEng window | It starts before `go` and ends after every child has joined, so the writer closes are inside it (code `SCR/bench_write.py:333-347`). |
| process_shared CPU accounting | The writer-process CPU is split per camera (`cpu / len(cams)`, `SCR/bench_write.py:141-146`) and added once in `our_cpu_s` (`:387-389`). It is not double-counted. |
| **Affinity inheritance (new, functional, no timing)** | The parent python was set to CPUs 0-15. Then `uv run --script` child, then a multiprocessing `spawn` grandchild: **both reported 16 CPUs, 0-15.** Scripts: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wt_vm/aff_parent.py` and `aff_child.py` (psutil 7.2.2). This is the same chain as runner → uv → bench_write.py → camera processes (code `RU/scripts/bench_runner/run_queue.py:441-446`; `SCR/bench_write.py:315`). |

## 2. Refuted (wrong as written)

1. **"process_shared uses a third to a half of the bench CPU"** (2.11, implication 6).
   - measured, median bench CPU, process_shared vs thread:
     - files 0.339 vs 0.693 (0.49);
     - append 0.295 vs 0.697 (0.42);
     - mkv_flush 0.255 vs 0.926 (0.28).
   - Correction: "about a quarter to a half".
2. **"roughly doubles tick->written p99"** (2.11, implication 6).
   - measured: files 7.49 vs 5.98 ms (1.25x); append 4.49 vs 2.10 (2.1x); mkv_flush 5.44 vs 2.62 (2.1x).
   - Correction: "about doubles it for append and mkv_flush, +25 % for files".
3. **"files p50 grows with camera count; the containers barely do (1080p30)"** (2.10).
   - measured (1 to 16 cams, core_av19 1080p30):
     - files 1.324 → 3.368 ms (2.5x, +2.04 ms);
     - append 0.195 → 0.679 (3.5x);
     - mkv_flush 0.324 → 0.818 (2.5x);
     - fmp4_frame_flush 0.311 → 0.958 (3.1x).
   - The containers roughly double from 8 to 16 cams.
   - Correction: files grows most **in absolute ms**; in relative terms the containers grow as much. inferred: the 8 → 16 step coincides with 16 camera processes on 16 pinned logical CPUs. At 720p30 the containers do stay nearly flat.
4. **Chromium citation `tables.md lines 87-100, 127-131`** (2.14) is wrong. Those lines are VP9/H.264/FFV1 rows.
   - The MJPEG rows are `RU/results/chromium_codecs/tables.md` lines 105-119 (mjpeg_422) and 165-176 (mjpeg_camera).
   - The claim itself holds for the five containers tested.
5. **"grab-late max was 1.1-2.0 ms in focus16 (medians per writer)"** (2.8).
   - The per-writer medians are 1.3-2.0 ms (BENCH.md 3.1). 1.1 is a rep minimum.
6. **"the only container variant with 0 lost frames"** (implication 4).
   - PyAV 18 fmp4_frame_flush lost 0-1 in 5 kills (background, `functional_results_fmp4_flush.md`), so it also had 0-loss kills.
   - Correction: "the only variant with 0 loss in every kill (3 kills, against 2 per variant elsewhere)".

## 3. Weak (true but under-scoped or missing a confounder)

**A. The Defender window and the "Contradicted" row in section 8.**
- code: MsMpEng is read right after the children join (`SCR/bench_write.py:340-347`).
- Any asynchronous scan after a single large file is closed falls outside the window.
- measured: the item totals exceed the cell sums by 20.4 s (focus16), 35.6 s (models16), 28.7 s (core) and 45.6 s (long). That excess is unattributed.
- Fix:
  - say "no measurable Defender work **inside the timed window, which ends at writer close**";
  - say that the out-of-window excess could include close-time scans of the one-file layouts (NOT VERIFIED);
  - label "the old append range reflected background activity" as inferred.

**B. The cost totals for files are understated.**
- inferred (arithmetic from measured `system_busy_pct_all_cpus` x 28, `our_cpu_s` and `msmpeng_cpu_s`): the residual system busy beyond bench + MsMpEng is 2.0-2.2 logical CPUs for files, against 1.25-1.7 for append, mkv_flush and fmp4_frame_flush. This holds in focus16, models16, long and core.
- So files has about 0.5-0.7 of a logical CPU of other system work: kernel, file system, and possibly SearchIndexer, which indexes this folder (2.7) and is not recorded per cell.
- The whole-system busy is 3.5-4.2 logical CPUs for files and 2.1-2.5 for the one-file layouts (focus16 median 4.09 vs 2.13).
- files bench CPU itself is 0.69-1.09 across items (focus16, models16, long).
- Fix: give implication 1 as a range, "bench + Defender 1.6-2.0 logical CPUs; whole-system about 1.3-2 logical CPUs more than append". Note the residual.

**C. Per-file Defender cost is a lower bound and is not constant.**
- It excludes the out-of-window work (A).
- It varies with concurrency: 8 cams x 1080p60 is 11.06 s / 9608 files = 1.15 ms, against 1.5-1.7 ms for 16 cams x 30 fps at the same file count (measured, core_av19).
- Fix: present 0.9-1.7 ms per file as a lower-bound range.

**D. Implication 2 quotes only the 30 s cells.**
- measured: 10 min mkv_flush gives p50 1.003 ms, p99.9 6.75 ms and bench CPU 1.19, against 0.808 / 2.85 / 0.90 at 30 s. This is a single sample.
- fmp4_frame_flush has no long cell.
- Across focus16, models16 and long, the append vs mkv_flush difference is 0.26-0.52 ms at p50 and 0.23-0.38 logical CPUs, not "0.25-0.3 ms".
- Fix:
  - quote these ranges;
  - drop "p99.9 under 3.2 ms" or add the 6.75 ms long value;
  - mark the long-file fMP4 cost NOT MEASURED. This also qualifies implication 4's "write costs equal".

**E. Hardware-target scope.**
- G5's "throughput does not decide" is measured on one i7-14700K (16 P-core logical CPUs) and one WD_BLACK SN850X NVMe.
- The hardware target (HANDOFF section 1, item 3) includes 2020-era CPUs with far fewer logical CPUs, and slower disks.
- Fix: scope implications 1-2 to this machine. The relative CPU gap (files 1.6-2 logical CPUs plus residual) matters more on small CPUs (inferred). Other machines are NOT VERIFIED.

**F. The daytime comparison (2.10).**
- "append rose 3.1x" uses focus16 only. models16 tonight gives append p50 0.365 ms (2.0x the daytime 0.179).
- The daytime per-rep bench CPU was erratic (append 0.03, 0.35 and 0.62 logical CPUs; measured, `bench/focus16/append__*`), so the CPU %/cam comparison (3.84 vs 6.82) is not usable.
- measured: daytime system busy was 11-26 %, against 7-15 % tonight. The more loaded run was faster per call. inferred: this is consistent with oversubscription of the 16 pinned CPUs, which supports the pinning hypothesis but does not test it.
- Fix: give the factor as 2.0-3.2x and drop the CPU %/cam comparison.

**G. Usability: ordering effects (2.12, 3.4).**
- code: for the folder formats the order is frame table, then sequential read, then random reads, then first image (`SCR/bench_usability.py:90-108`).
- So the random-read (0.048 s) and first-image (0.0023 s) numbers come after the Defender first-open cost was paid in the sequential pass.
- Fix: mark these columns "after a full read". The first access to frames in a fresh folder recording costs about 4 ms per file (2.12).

**H. Implication 7 (queue depth).**
- Only the 2.87 s queue was tested. The 329 ms worst stall is one 10-minute sample per writer, with Defender on, on NVMe.
- Fix: recommend the tested depth (2.87 s); mark smaller queues NOT VERIFIED rather than "several hundred ms".

**I. Implication 11 (no fsync needed for a process crash).**
- It rests on the unsourced WriteFile premise (2.2) and on 2 + 5 steady-state kills per variant.
- Fix: label the implication **inferred**.

**J. Section 5, affinity.**
- Upgrade "inferred from Windows affinity inheritance" to measured: the verifier's functional check (section 1) gave 16 of 16 CPUs through uv and spawn.
- "No WT item uses libx265" can be labelled code: nothing is encoded (`SCR/bench_write.py:7-11`).

**K. Reader compatibility at length (3.1).**
- "PyAV, cv2, ffprobe" for MKV rests on 300-frame files.
- measured (other topic): cv2 counts a 54,000-frame MKV as 53,819 frames (`RU/results/jpeg_passthrough/BENCH.md:176-180`).
- Fix: add it as a long-file reader caveat.

**L. Extra disk writes for files (2.8).**
- The 12.8 % excess is one rep, and the PhysicalDrive delta is system-wide.
- Lazy-writer carry-over from WT-USABILITY-18K, which ended 12 s before WT-LONG-AV19 began (BENCH.md section 1), is not excluded.
- Fix: keep the hedge "plausibly"; name the carry-over as an alternative.

## 4. Lens items found sound

| Lens | Result |
|---|---|
| Quality targets | No target confusion. Payloads are camera bytes (about target A), and target B is not benched (stated). |
| NVENC 12-session flag | Correctly excluded: there is no encode in this topic. |
| Intra vs GOP | Only intra-only payloads. The Rust prototype (libx264 GOP) is labelled "not a passthrough reference". |
| Repetitions | Single runs are listed in section 5. focus16 and models16 are the only items with 3 reps. |
| Defender | ON and reported separately. The first-read equality is stated as not proof of cause. |
| Cache state | Warm cache is stated, and the 30 s cells are labelled as the OS-cache path. |
| Functional vs compatibility | Non-FFmpeg readers are NOT VERIFIED, and Chromium plays no MJPEG wrapper. |
| Timer granularity | The 15.625 ms quantum is stated, and the per-cell Defender comparisons are far above it. |
