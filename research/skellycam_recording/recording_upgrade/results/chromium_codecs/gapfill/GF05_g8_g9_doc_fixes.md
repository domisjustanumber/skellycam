# GF05: G8/G9 doc fixes (stale bench text, HEVC 4:2:2 / libx265 pointers, BENCH and NOTES corrections)

2026-11-10, gap-fill step 3. No test and no timing was run. One ffprobe inspection (allowed: inspect only).
Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). Shorthands: `CC` = `results/chromium_codecs/`, `CSS` = `results/chromium_sync_scrub/`, `IP` = `results/intra_playback/`.

Labels: **measured** (result file + key), **source**, **code** (file:line), **inferred**. Unverifiable = NOT VERIFIED.

## 0. Evidence made in this step

| file | what |
|---|---|
| `scripts/chromium_codecs/gf05_extract_intra_playback.py` | re-reads every `IP/bench/<e35\|e45>/bench_intra_{seek,sync,scrub}/c1080p30_*.json` and `IP/clips_summary.json`; reads only |
| `CC/gapfill/GF05_intra_playback_extract.json` | its output: 24 seek, 68 sync, 48 scrub rows; `clip_checks` |
| `CC/gapfill/GF05_ffprobe_hevc_intra_420.txt` | ffprobe 9.0.2 on the libx265 sample: `profile=Rext`, `codec_tag_string=hvc1`, 1920x1080, yuv420p, `nb_frames=8`, 8/8 `pict_type=I` |
| `scripts/intra_playback/gf05_bench_private_kb_edit.py` | rewrites the 48 GPU-memory cells and 2 headers in `IP/BENCH.md` §5 from the JSON; asserts each old cell = round(`private_kb` / 2^20, 1) |
| `IP/gapfill/GF05_private_kb_cells.json` | old → new for those 50 lines, with the raw peak and GPU pid count |

Values re-read for this file (all **measured**, `CC/gapfill/GF05_intra_playback_extract.json`):
- Seek: `exact` = 200/200 in all 24 configs; `errors` 0 on every WebCodecs/JPEG config.
- Seek p50 (`result.summary.lat_ms.p50`): WebCodecs E35 3.1–3.4 ms, E45 2.7–2.9 ms; JPEG ImageDecoder E35 4.4, E45 4.6; JPEG createImageBitmap E35 7.0–7.1, E45 6.0–6.1. `<video>` `mid` to rVFC (`lat_rvfc_ms.p50`): E35 11.8–14.1, E45 8.5–14.1; `seeked` 1.3–1.6.
- Sync N = 8 (`result.spread`, `metrics_summary.cpu_cores_total_from_cumulative`): every master-clock config spread p50/p95/max 0/0/0 and `spread_exact0_pct` 100. Electron CPU: WebCodecs E35 0.58–0.63, E45 0.51–0.57 (QSV files included: E35 0.63 / 0.59, E45 0.57 / 0.52); ImageDecoder E35 1.45, E45 1.44; bitmap E35 2.55–2.56, E45 2.14.
- Sync N = 8 `<video>` (20 configs): max spread 100–245 frames; slowest stream / upper-median stream rVFC callbacks 0.42–0.58 in 19 configs, 0.78 in E35 `hevc_qsv` `video-rvfc` (IP F21 states 42–60% against the median).
- Scrub: WebCodecs per-stream errors E35 914 (5 of 8 configs), E45 0. ImageDecoder 58.0–58.75 shown/s per stream at N = 4 and 8, lag p50/p95 2/2.
- Clip checks: 48/48 NVENC/QSV H.264/HEVC clips are all-IDR, `has_b_frames = 0`, and `decode_order_equals_pts_order` true (`IP/clips_summary.json`).
- Queue: IP-SEEK-E35/E45, IP-SYNC-E35/E45, IP-SUM are `order` 12–16; IP-SCRUB-E35/E45, IP-SUM-2 are 25–27; IP-SYNC-QSV-E35/E45, IP-SUM-3 are 46–48 (`results/bench_queue_2300.json`, 68 items). All 11 have `status` ok (`results/BENCH_RUN_2300_LOG.jsonl` lines 13–17, 26–28, 48–50).
- `results/bench_queue_2300.json` has no item with topic `chromium_sync_scrub` (topic counts: intra_compare 27, intra_playback 11, write_throughput 10, overlays 5, jpeg_passthrough 4, crash_resilience 4, uncompressed_intra 4, python_integration 3).

## 1. chromium_codecs FINDINGS (proposed text)

**1a. Replace §5 (lines 331–344, heading "## 5. Pending tonight's bench" through "P2 and P3 stay open until these benches report.") with:**

```
## 5. Timed results (owned by intra_playback; this topic ran no timed bench)

The quiet run `20261109T230007` timed the G8/G9 playback paths as intra_playback items IP-SEEK-E35/E45, IP-SYNC-E35/E45, IP-SCRUB-E35/E45 and IP-SYNC-QSV-E35/E45 (`results/bench_queue_2300.json` order 12–15, 25–26, 46–47; all ok in `results/BENCH_RUN_2300_LOG.jsonl`). Clips: 1080p30 CFR MP4, 600 frames, about 55 dB Y-PSNR, **not target A or B** (`IP/FINDINGS.md` §1). Values re-read from `IP/bench/<e35|e45>/**.json` (`CC/gapfill/GF05_intra_playback_extract.json`).

| path | seek exact | seek p50 ms, E35 / E45 | N = 8 sync spread | N = 8 sync Electron CPU cores, E35 / E45 | N = 8 scrub | IP finding |
|---|---|---|---|---|---|---|
| JPEG Range + `ImageDecoder` | 200/200 per file | 4.4 / 4.6 | 0 on 100% of ticks | 1.45 / 1.44 | 58.0–58.625 shown/s, the harness input ceiling | F17–F20, F23 |
| JPEG Range + `createImageBitmap` | 200/200 | 7.0–7.1 / 6.0–6.1 | 0 | 2.55–2.56 / 2.14 | 41.75–50.75 shown/s | F18–F20, F23 |
| WebCodecs H.264/HEVC intra (`wcflush`), master clock | 200/200 | 3.1–3.4 / 2.7–2.9 | 0 | 0.58–0.63 / 0.51–0.57 (GPU decode not counted) | not usable (F22) | F17–F20, F22 |
| `<video>` H.264/HEVC intra, `mid` seek | 200/200 | 11.8–14.1 / 8.5–14.1 to rVFC | tiles stall: max spread 100–245 frames | 0.45–0.56 / 0.44–0.55 | gated 17.25–45.5 shown/s | F18, F21, F23 |

- measured (IP F17): every timed seek landed on the requested frame, 200/200 in all 24 seek configs.
- measured (IP F19, IP-SYNC + IP-SYNC-QSV): master-clock sync spread was 0/0/0 frames on 100% of ticks in all 28 configs (N = 4 and 8, WebCodecs and JPEG, both Electrons), QSV-encoded files included. Spread is index-based; pixels were checked only in the functional runs (IP F8).
- measured (IP F21): in 19 of 20 N = 8 `<video>` configs the slowest tile got 42–60% of the median stream's rVFC callbacks, giving max spread 100–245 frames; leader and rVFC correction did not fix it.
- measured (IP F22): WebCodecs scrub is not usable as a capacity figure. E35 logged 914 hidden per-stream errors, and the GPU process's peak `private_kb` reached 9,586,248–39,695,312 in 8 s (unit NOT VERIFIED).
- code: CPU is Electron process CPU only (`scripts/chromium_sync_scrub/harness/main.cjs:93-101`); hardware decode on the GPU is not counted.
- NOT VERIFIED: timing on the cameras' own JPEG bytes. The timed JPEG files are `mjpeg_qsv` re-encodes (IP P3).
- Full tables: `IP/BENCH.md` §3–§6; per-finding labels: `IP/FINDINGS.md` F17–F25.
```

**1b. P2, line 296.** Old: `  - Whether the path is fast enough for N cameras is tonight's bench (§5).`
New:
```
  - measured (§5; IP F17–F20, F23): at N ≤ 8, 1080p30, on this machine the JPEG path stays frame-exact (200/200 seeks), seeks at p50 4.4–4.6 ms with `ImageDecoder`, syncs N = 8 with spread 0 at 1.44–1.45 Electron cores, and scrubs N = 8 at the harness input ceiling (58.0–58.625 shown/s).
  - inferred (IP P3): prefer `ImageDecoder`; `createImageBitmap` costs 2.14–2.56 cores at N = 8 sync and drops to 41.75–50.75 shown/s in N = 8 scrub.
  - NOT VERIFIED: the same timing on camera JPEG bytes (the bench used `mjpeg_qsv` re-encodes at about 55 dB, not target A or B), and over `file://` or `protocol.handle`.
```

**1c. P3, after line 300, add:**
```
  - measured (§5; IP F19–F21): WebCodecs H.264/HEVC intra under a master clock synced N = 8 with spread 0 at 0.51–0.63 Electron cores (GPU decode not counted). One `<video>` per camera stalled at N = 8 (max spread 100–245 frames).
  - inferred (IP P1): if H.264/HEVC intra is used, play it through WebCodecs and a master clock drawing to canvas, not N `<video>` elements.
```

**1d. P4, line 303.** Old: `...so neither meets the RTX 3000+ target (requirement 9).` New: `...so neither meets the RTX 3000+ target (HANDOFF §1 requirement 3).`
- source: `HANDOFF.md` §1 item 3 is the hardware target; item 9 is now the matched-quality comparison.

**1e. §8, line 429.** Old row: `| §5 bench queue | weak | `bench_queue_2300.json`: 23 items, IP-SEEK/SYNC ×2 and IP-SUM present, IP-SCRUB absent | table updated |`
New row: `| §5 bench queue | weak; superseded | 2026-11-09 queue had 23 items with IP-SCRUB absent. The final queue has 68 items; IP-SCRUB-E35/E45 are order 25–26 and ran ok (`results/bench_queue_2300.json`, `results/BENCH_RUN_2300_LOG.jsonl` lines 26–27) | §5 replaced by pointers to intra_playback (GF05, 2026-11-10) |`

**1f. §8, add at the end:**
```
GF05 (2026-11-10): §5, P2, P3, P4 and the §8 queue row were revised from `IP/BENCH.md` and `IP/bench/**.json`, re-read by `scripts/chromium_codecs/gf05_extract_intra_playback.py` (output `CC/gapfill/GF05_intra_playback_extract.json`). No test or timing was run.
```

## 2. chromium_sync_scrub FINDINGS (proposed text)

**2a. Header, line 6.** Old: `**No timing numbers appear here.** Every latency, sync-spread, scrub-rate and CPU question is in section 5.`
New: `**This topic ran no timed bench of its own** (its `bench_*` suites ran only as smoke, section 5). The timed latency, sync-spread, scrub-rate and CPU results for these questions are intra_playback's (section 5).`

**2b. Header line 8 and I6 line 234: requirement numbers.** `HANDOFF §1 requirement 10` / `HANDOFF §1 req 10` → `HANDOFF §1 requirement 8` (intra-only is now item 8). Line 354 (§8 history) can stay, with "(numbering of 2026-11-09)" appended.

**2c. §3.3 heading, line 208.** Old: `### 3.3 Storage cost of all-intra (measured, background PyAV 18, `clips_summary.json`)`
New: `### 3.3 Storage cost of all-intra (measured, background PyAV 18, `clips_summary.json`; not at target A or B)`
- Add under it: `Sizes for recording decisions are in `results/intra_compare/` at target A or B; these encoder settings (AV1 crf 35, VP9 crf 33, H.264 crf 23, MJPEG q90) were not matched to either.`

**2d. I3, line 227.** Old ends: `Their cost is unmeasured (section 5), so the plan must not pick between I2 and I3 until tonight's bench has run.`
New I3:
```
- **I3** (F15, F16, F16a, F7; intra_playback F17–F21, P1): only the index-driven paths (WebCodecs, JPEG) were exact in every run, including the near-duplicate pair (WebCodecs; JPEG not targeted).
  - measured (intra_playback F19): a single master clock driving WebCodecs or JPEG kept spread 0/0/0 frames on 100% of ticks at N = 4 and N = 8 (28 configs, 1080p30, both Electrons).
  - measured (intra_playback F21): N = 8 `<video>` elements (free, leader-corrected or rVFC-steered) stalled in 19 of 20 configs, max spread 100–245 frames.
  - inferred (intra_playback P1): for N ≥ 8, use a master clock and draw to canvas; I2's per-camera `<video>` fix is only a candidate for small N (at N = 4 spread max was 2–4 frames with 6–8% dropped, intra_playback F21).
  - Limits: intra_playback clips, not this topic's; about 55 dB, not target A or B; spread is index-based.
```

**2e. I8, line 236.** Add at the end: `measured (intra_playback F24): in the timed run, seek exactness, master-clock spread 0 and the N = 8 `<video>` stall were the same in E35 and E45.`

**2f. Replace §5 (lines 238–261) with:**
```
## 5. Timed results (owned by intra_playback)

- measured: this topic's own `bench_seek`, `bench_step`, `bench_sync` and `bench_scrub` suites ran only as smoke, 2026-11-09: `bench/e{35,45}/bench_{seek,step,sync,scrub}_smoke/_index.json`, 6 / 4 / 10 / 10 runs per Electron, `smoke: true`, 0 errors. No other folder exists under `bench/`.
- measured: the final queue `results/bench_queue_2300.json` (68 items) has no `chromium_sync_scrub` item. The timed G9 items ran under intra_playback with this topic's runner (`scripts/chromium_sync_scrub/run_suite.py --suite bench_intra_*`): IP-SEEK, IP-SYNC, IP-SCRUB, IP-SYNC-QSV for E35 and E45, all ok (`results/BENCH_RUN_2300_LOG.jsonl` lines 13–16, 26–27, 48–49).
- Results: `results/intra_playback/FINDINGS.md` F17–F25 and P1; tables in `results/intra_playback/BENCH.md` §3–§6. In short (all measured there):
  - every timed seek exact, 200/200 in 24 configs, seed 11 (F17); this is a second seed for the intra and JPEG paths, on intra_playback's clips;
  - seek p50: WebCodecs 2.7–3.4 ms, JPEG `ImageDecoder` 4.4–4.6 ms, `<video>` `mid` to rVFC 8.5–14.1 ms (F18);
  - master-clock spread 0 at N = 4 and 8 (F19); N = 8 `<video>` tiles stall (F21);
  - WebCodecs scrub not usable as a capacity figure (F22); JPEG `ImageDecoder` scrub at the harness ceiling (F23).
- Not run, still NOT VERIFIED: the exhaustive every-frame sweep (`scripts/chromium_sync_scrub/verify_method/exhaustive_mid_sweep.py`; no `functional/e*/exhaustive/` exists), single-step latency, and every timed test on this topic's own PyAV 18 clips.
```

**2g. F25, line 179.** Old: `  - Chromium playback of NVENC/QSV-encoded files was not tested. Intra-only (`g=1`) hardware encodes were not checked for ordering. inferred: a stream where every frame is a keyframe has no B-frames.`
New:
```
  - measured (intra_playback F1–F3): 48 intra-only NVENC/QSV H.264/HEVC files (PyAV 19.0.2) open, play and seek frame-exactly in E35, E45 and Chrome 156 (`mid` 4800/4800 seeks and 5856/5856 steps per browser; WebCodecs `wcflush=1` 4800/4800).
  - measured: all 48 are all-IDR with `has_b_frames = 0` and decode order = pts order (`results/intra_playback/clips_summary.json`, `nal_check`, `ffprobe.stream.has_b_frames`, `decode_order_equals_pts_order`).
```

**2h. §6, line 273.** Old: `- Chromium playback of NVENC/QSV-encoded files (the encode target, HANDOFF §1 req 3) was not tested (F25).`
New: `- Chromium playback of NVENC/QSV-encoded intra files (the encode target, HANDOFF §1 req 3) is measured in intra_playback F1–F3 (frame-exact in E35, E45, Chrome 156; decoded by `D3D11VideoDecoder` on the NVIDIA GPU, F9). This topic did not play them. Intel, AMD and Apple decode remain NOT VERIFIED.`

**2i. §6, lines 265 and 284.** Line 265 add: `intra_playback played PyAV 19.0.2 files in both Electrons (F1–F4).` Line 284 old `There are no timing numbers in this topic.` → `This topic took no timing; timed results are intra_playback's (section 5).`

**2j. §7 '# tonight' block, lines 314–317.** Replace with:
```
# timed bench: DONE 2026-11-10 as intra_playback items (run 20261109T230007; commands in results/intra_playback/FINDINGS.md §7)
# this topic's own bench suites were run only with --smoke (bench/e{35,45}/*_smoke/); not run timed:
#   run_suite.py --electron <35|45> --suite bench_sync --only mjpeg
#   run_suite.py --electron <35|45> --suite bench_seek --only c1080p30/mjpeg
```

**2k. §8 "Remains NOT VERIFIED", line 360.** Old: `- NVDEC use by Chromium; Chromium playback of NVENC/QSV files; PyAV 19 files in Electron.`
New: `- NVDEC use by Chromium (intra_playback F9 shows `D3D11VideoDecoder` on the active NVIDIA adapter, not NVDEC itself). Chromium playback of NVENC/QSV files and PyAV 19 files in Electron: now measured in intra_playback F1–F4.`
Line 362 old `- Every timing question (section 5).` → `- Timing on this topic's own clips; timing of single steps (section 5).`

## 3. intra_playback §6 line 258 and gpu_encode §6.2 line 481 (HEVC 4:2:2)

Basis (all from `CC/FINDINGS.md` C17, C17a, re-checked in `CC/raw/verify_method_rechecks.json` `play_file_url`):
- measured: one 720p 8-bit 4:2:2 `hevc_qsv` MKV (from YUYV), played from `file://`: E35 MediaError 4 `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`; E45 opens, then MediaError 3 `PipelineStatus::PIPELINE_ERROR_DECODE`. A 4:2:0 `hevc_qsv` control plays in both. The active GPU is the RTX 3070 (C12).
- measured (C17a): E45 and Chrome 156 still answer "probably" / supported for HEVC RExt codec strings; E35 answers `""` / false.
- NOT VERIFIED: Chrome 156 playback of the file (C17 says so), and index-pattern readback.

**3a. intra_playback FINDINGS lines 258–260.** Old:
```
- NOT VERIFIED: HEVC 4:2:2 (`hevc_qsv` from YUY2, Rext) playback.
  - chromium_codecs NOTES §3 probes show E35 unsupported and E45/C156 supported.
  - hw_accel_target NOTES_functional §4 shows NVIDIA cannot decode it. No clip was played.
```
New:
```
- measured (chromium_codecs C17): HEVC 4:2:2 (`hevc_qsv` from YUY2, Rext) does not play on this RTX 3070. One 720p MKV: E35 does not open it (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`); E45 opens it, then fails with `PIPELINE_ERROR_DECODE`. A 4:2:0 control plays in both (`results/chromium_codecs/raw/verify_method_rechecks.json`).
  - measured (C17a): E45 and C156 probes still say "probably"/supported for RExt strings, so probes cannot be trusted for 4:2:2.
  - NOT VERIFIED: Chrome 156 playback of the file; frame-exact seek (no index readback).
  - Supporting only: FFmpeg's NVIDIA decoders also fail on the file (`results/hw_accel_target/NOTES_functional.md:126`).
```
- Also §8 "Still NOT VERIFIED", line 339: `Frame-exact libx265 (Rext) intra playback in Electron, and HEVC 4:2:2 playback.` → `Frame-exact libx265 (Rext) intra playback in Electron. (HEVC 4:2:2: measured to fail in E35/E45, chromium_codecs C17; C156 NOT VERIFIED.)`

**3b. gpu_encode FINDINGS line 481.** Old: `- Chromium playback of hevc_qsv 4:2:2 (Rext): not played in intra_playback ("Not played: HEVC 4:2:2", `results/intra_playback/FINDINGS.md` line 64).`
New: `- Chromium playback of hevc_qsv 4:2:2 (Rext): measured to fail on this RTX 3070 (chromium_codecs C17): E35 does not open the one 720p MKV tested; E45 gives `PIPELINE_ERROR_DECODE`; a 4:2:0 control plays. Chrome 156 playback: NOT VERIFIED. The old pointer ("intra_playback FINDINGS line 64") is stale.`

## 4. intra_compare FINDINGS §6 (libx265 in Electron)

**4a. Line 525.** Old: `- NOT VERIFIED: Electron/Chromium playback of libx265's Rext all-intra 4:2:0 (chromium_codecs tested only HEVC Rext 4:2:2).`
New:
```
- measured (intra_playback F16): one CLI-made libx265 all-intra 4:2:0 sample (8 frames, 1080p, Rext, `hvc1`) fails in E35 (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) and loads, draws and seeks in E45 (`results/uncompressed_intra/chromium_check_electron{35,45}.json`; profile from `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`).
- NOT VERIFIED: playback of PyAV-made libx265 streams, and frame-exact seek of any libx265 all-intra stream in Electron.
```

**4b. Line 476.** Old: `- **Avoid libx265 output for the UI.** It is Rext even at 4:2:0 (§2.1), and its Electron playback is NOT VERIFIED.`
New: `- **Avoid libx265 output for the UI.** It is Rext even at 4:2:0 (§2.1). One CLI libx265 Rext 4:2:0 sample fails in E35 (the skellycam-ui pin) and plays in E45 (intra_playback F16); PyAV-made streams and frame-exact seek are NOT VERIFIED.`

**4c. Line 620 (§8 "still NOT VERIFIED").** Old: `- Electron playback of libx265 Rext 4:2:0.` New: `- Electron playback of PyAV-made libx265 Rext 4:2:0 and frame-exact seek (one CLI sample: E35 fails, E45 plays, intra_playback F16).`

**4d. Lines 40–43 (stale NOTES cells).** After GF05 the cells are annotated in `R/NOTES.md`; two more stale rows were found (section 7, item 10). Proposed: replace the list with `- `R/NOTES.md` §1 line 54 and §6 lines 179, 181, 185, 186, 208 had stale cells; they are annotated in place with the `R/matched_summary.md` values (GF05, 2026-11-10). This text uses `R/matched_summary.md`.`

## 5. uncompressed_intra FINDINGS §2.11 line 378 (and the "Main" source line)

**5a. Line 378.** Old: `  - HEVC intra 4:2:0 (Main) fails in E35 and plays in E45.`
New: `  - libx265 all-intra 4:2:0 (Rext; the generator declares `hvc1.1.6.L120.90`, a Main string, `scripts/uncompressed_intra/make_chromium_samples.py:46`) fails in E35 and plays in E45 (intra_playback F16; ffprobe: `profile=Rext`, 8/8 frames I, `results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`).`

**5b. Pointer fix.** The "Main" claim is in `results/uncompressed_intra/VERIFY_method.prev.md:28` (row R1: "the original sample was x265 crf20 4:2:0 Main"), not in `VERIFY_method.md:28`.
- measured: current `VERIFY_method.md:28` is about NVENC lossless exactness at 720p and does not mention the libx265 sample. It was left unchanged.
- `VERIFY_method.prev.md:28` was annotated in place (section 7).
- intra_playback FINDINGS line 85: change `uncompressed_intra `VERIFY_method.md:28` calls the sample "Main"` → `uncompressed_intra `VERIFY_method.prev.md:28` (row R1) calls the sample "Main"`.
- Not edited (outside this step's allowed files): `results/uncompressed_intra/NOTES.md:209` row "HEVC intra 4:2:0" (no profile given; it is the same Rext sample).

## 6. Follow-on FINDINGS wording now out of date (because of the direct edits)

| topic | line | old | new |
|---|---|---|---|
| intra_playback | 12 | `...agree with the JSON, except for two points: the GPU memory unit (see F22) and BENCH.md's "about one 60 Hz vsync" remark, which is wrong (see F18).` | `...agree with the JSON. Two BENCH.md points (the GPU memory "GB" label and the "one 60 Hz frame" remark) were corrected in place by GF05 (2026-11-10).` |
| intra_playback | 124 | `BENCH.md labels the same values "GB".` | `BENCH.md now shows the raw `private_kb` (corrected by GF05).` |
| intra_playback | 320 | `BENCH.md carries the same wrong remark.` | `BENCH.md was corrected by GF05 (2026-11-10).` |
| python_integration | 328 | `(`R/BENCH.md` §2 says "about 18,000 … from PyTurboJPEG"; that is wrong in the same way.)` | `(`R/BENCH.md` §2 was corrected to these counts by GF05, 2026-11-10.)` |
| python_integration | 614 | `- `R/BENCH.md` §2 still carries the wrong PyTurboJPEG / about-18,000 wording. It was not edited in this step.` | `- `R/BENCH.md` §2 was corrected by GF05 (2026-11-10).` |

## 7. Direct edits made (non-FINDINGS files)

Each edit carries an inline `(corrected 2026-11-10, GF05: <reason>)` mark.

| # | file | line | old → new |
|---|---|---|---|
| 6 | `IP/BENCH.md` | 355 | "The ~14 ms rVFC p50 is consistent with one 60 Hz frame (*inferred*)." → "The `<video>` seek-to-rVFC p50s (8.5-14.1 ms, section 3) are under one 60 Hz frame period (16.7 ms); the cause of the rVFC delay is not determined" + mark (aligned with F18) |
| 7 | `IP/BENCH.md` | 233, 262 | header "GPU proc private peak GB; GPU pids" → "GPU proc peak `private_kb` (raw; unit NOT VERIFIED, FINDINGS F22); GPU pids" + mark |
| 7 | `IP/BENCH.md` | 235–258, 264–287 | 48 cells "X.X; n" (= `private_kb` / 2^20) → raw peak, e.g. E35 H.264 NVENC WebCodecs N = 4 "13.0; 1" → "13,610,276; 1"; E45 H.264 NVENC WebCodecs N = 8 "37.9; 1" → "39,695,312; 1". All 48 in `IP/gapfill/GF05_private_kb_cells.json` |
| 7 | `IP/BENCH.md` | 293 | "(peaks 9.1-37.9 GB …) … exceeds 0.9 GB … falling to ~0.1 GB … private GB at 1 s steps" → "peaks 9,586,248-39,695,312 `private_kb` … exceeds 901,812 `private_kb` … new process's first sample is 82,404-99,088 `private_kb` … `private_kb` / 1,048,576 at 1 s steps" + mark |
| 7 | `IP/BENCH.md` | 295 | "series (s: GB)" → "series (s: `private_kb` / 1,048,576; unit NOT VERIFIED, FINDINGS F22)" |
| 7 | `IP/BENCH.md` | 334 | "GPU-process private bytes reach 9-38 GB within 8 s" → "GPU-process peak `private_kb` reaches 9,586,248-39,695,312 within 8 s" + mark |
| 7 | `IP/BENCH.md` | 40 | field definition: added "(stored as `private_kb`) … shown raw in section 5" + mark |
| 8 | `results/python_integration/BENCH.md` | 46 | "about 18,000 libjpeg-turbo `UserWarning` … lines (PyTurboJPEG on generic_1080p …)" → "stderr (20,043 lines): 20,021 bare libjpeg `Corrupt JPEG data` lines plus 11 PyTurboJPEG `UserWarning` lines … per FINDINGS F14 the bare lines come from `cv2.imdecode` (inferred)" + mark. Recount: `grep -c "^Corrupt JPEG data"` = 20,021, `grep -c UserWarning` = 11, `wc -l` = 20,043 on `results/bench_runner/logs/20261109T230007/39_PI-JPEG-DECODE-PYAV19.err.txt` |
| 9 | `results/intra_compare/BENCH.md` | 606 | "and its QC carries the swscale RGB bias (`NOTES.md` §9.3)" → "Its QC from NV12 / YUY2 hits target A (1080p PSNR-Y 52.344 / 52.365 dB, SSIM-Y 0.99707 / 0.99708; 720p 51.474 / 51.485 dB) … only the `mjpeg_cpu` feed misses (45.211 dB) … `nvjpeg_rgb_diag.json` 46.73 dB RGB step does not show in the bench QC; why is NOT VERIFIED" + mark. Values from `bench/matched_stream_A_{1080p,720p}_*.json` `summary[*].quality_check` |
| 10 | `results/intra_compare/NOTES.md` | 54 | "1.41-1.52x passthrough" → "1.42-1.53x passthrough" + mark |
| 10 | `results/intra_compare/NOTES.md` | 179 | h264_nvenc yuy2_720p "83,921" → "83,913" + mark |
| 10 | `results/intra_compare/NOTES.md` | 181 | hevc_nvenc "55,112 (0.91; 0.83)" → "53,975 (0.89; 0.81)"; "144,376 (0.99; 0.88)" → "141,655 (0.97; 0.87)" + marks |
| 10 | `results/intra_compare/NOTES.md` | 185 | (extra, found by a full table compare) libx264_ultrafast "93,764 (1.55; 1.41)" → "94,459 (1.57; 1.42)"; "248,857 (1.71; 1.52)" → "249,785 (1.71; 1.53)" + marks |
| 10 | `results/intra_compare/NOTES.md` | 186 | (extra) libx265_ultrafast "67,557 (1.12; 1.01)" → "67,662 (1.12; 1.02)"; "160,931 (1.10; 0.98)" → "161,155 (1.11; 0.99)" + marks |
| 10 | `results/intra_compare/NOTES.md` | 208 | "55,112 vs 46,217 … 144,376 vs 123,426" → "53,975 vs 46,217 … 141,655 vs 123,426" + mark |
| 5 | `results/uncompressed_intra/VERIFY_method.prev.md` | 28 | appended to "the original sample was x265 crf20 4:2:0 Main": "(corrected 2026-11-10, GF05: "Main" is wrong. ffprobe … `profile=Rext` …)". `VERIFY_method.md:28` was not changed (it does not carry the claim) |

- The full NOTES §6 compare (target A and B tables against `R/matched_summary.md`) found stale cells only on lines 179, 181, 185 and 186; the target B table matched.
- Line endings (CRLF) were kept on `IP/BENCH.md`, `results/intra_compare/BENCH.md` and `results/intra_compare/NOTES.md`.
