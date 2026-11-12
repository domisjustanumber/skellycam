# T-S4: Loading the per-frame sidecars in the Electron canvas player

Date: 2026-11-12. Machine: Gerald (i7-14700K, 28 threads, 64 GB, WD_BLACK SN850X). Electron 35.7.5 and 45.2.3.
Labels: [M] measured (files below), [C] code read, [I] inferred, [NV] not verified.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked these against `summary.json`: the time to first frame and full-load medians for A_dvl, A_hyb and C, and retained memory for A_dvl, A_hyb, C and D, at 30 and 60 fps in both versions.*

## 0. Answer

- **Keep S1 (64 B row-major records) unchanged.** Don't add a columnar or compact section before freezing `skellyformat`. [M]
- **Loading the whole sidecar is fast enough.** 16 cameras × 1 h load and parse in 95–107 ms at 30 fps and 166–195 ms at 60 fps, in E35 and E45. The renderer keeps +37–48 MB and +69–83 MB afterwards. [M]
- **The first frame needs no format change.** A hybrid player draws frame 0 of all 16 cameras in 3–5 ms, at every size up to 16 × 4 h × 120 fps. It reads the header plus the first 256 records, draws, then streams the rest. [M]
- **Very long files need no format change either.** Lazy block reads by Range work on S1 as it is. [M]
- **The spec needs five rules, none of which changes the layout (§6).**

## 1. Method

- **Synthetic data** (`scripts/sidecar_load/gen.py`). 16 cameras per set:
  - 1 h at 30 fps: about 107,800 records per camera (6.9 MB);
  - 1 h at 60 fps: about 215,500 records per camera (13.8 MB);
  - stress set, 4 h at 120 fps: about 1.72M records per camera (110 MB).
- **Realistic values:**
  - QPC-like times around 3e14 ns;
  - arrival = capture time + 30 ms + exponential jitter, kept strictly increasing;
  - about 0.2 % drops, shown as gaps in `source_frame_number` with the gap flag set;
  - fitted time on a smooth lattice;
  - offsets climb past 4 GiB (up to 41 GB at 60 fps);
  - JPEG sizes N(192 kB, 15 kB);
  - real record CRCs.
- **Fit-valid flag:** set on cameras 0–14, so the player uses fitted time. Camera 15 has no valid fit, so it uses arrival.
- **Files and layouts:**
  - (a) `camNN.skfr`: a 512 B synthetic header, then the S1 records. The synthetic header is not the spec header.
  - (c, inside) the same file also holds a compact index after the records: time i64[N], offset u64[N], size u32[N], 20 B/frame, columnar.
  - (b) `camNN.skfc`: fully columnar. The player's five columns come first (arrival, fitted, offset, flags, size; 32 B/frame), so one read gets them.
  - (c, separate) `camNN.skix`: the index on its own.
  - `camNN.mkv`: a tiny FFmpeg MJPEG MKV. One Attachments element holds two AttachedFiles, `.skfr` and `.skix`, appended at the end like SE's appender. The JPEG offsets don't point into this dummy MKV. Only the sidecar load path is tested.
- **Harness** (`scripts/sidecar_load/electron/`):
  - one Electron process per run;
  - the page is loaded from `file://`;
  - all reads are `fetch` with a Range header;
  - memory comes from `app.getAppMetrics()` in the main process (renderer private bytes, polled every 20 ms for the peak) and `performance.memory` (`--enable-precise-memory-info`), after `gc()`.
- **What the timings cover:**
  - "First frame" = the reads and parsing needed to find frame 0 for all 16 cameras. It excludes the JPEG fetch and decode, which is the same for every layout (seek p50 4.6 ms, §2.6 of the plan).
  - Steady state = 10 starting points × 3,600 draws at 60 Hz × 16 cameras. Seeks = 5,000 random clock positions × 16 cameras.
- **Correctness:** every lookup method returned identical PREV indices in every run and both versions. This covers Float64, hinted, BigInt zero-copy over records, BigInt columnar, BigInt index and lazy. [M]
- **Runs:** 5 per cell, interleaved: 220 runs for the 1 h sets and 60 for the stress set. The machine was shared with two other agents running Electron and PyAV tests. CPU load sampled before each run: median 18 %, p90 51 %, max 74 % (stress set: 22.5 / 47 / 65 %). 6–17 other electron/python/chrome processes were running.
- **Limits:**
  - warm OS cache only [NV cold: ~110 MB at about 7 GB/s NVMe is under 20 ms more; on an HDD at about 150 MB/s it is about 0.7 s for 16 × 1 h × 30 fps (arithmetic)];
  - `file://` only (HTTP and `protocol.handle` are tested in `results/range_transport/`);
  - no real JPEG fetch or decode;
  - synthetic data.

Arm names: A_dv / A_dvl = (a) whole, parsed with DataView (A_dv also times extra parsers and the CRC check; A_dvl doesn't). A_seq = (a) streamed, 4 cameras at a time. A_hyb = hybrid. A_zc = (a) zero-copy with BigInt. B = columnar. C = compact index. D = lazy. E_a / E_cin / E_catt = embedded in the MKV.

## 2. Results, 16 cameras × 1 h

Medians with [min–max] of 5 runs. "Kept" and "peak" are the renderer's private memory after load and GC, and the highest value seen while loading, each minus its baseline.

| Arm | What is read | 30 fps E35: first frame ms · kept/peak MB | 30 fps E45 | 60 fps E35 | 60 fps E45 |
|---|---|---|---|---|---|
| A_dvl | all records, 110 / 221 MB | 103 [98–113] · 37/125 | 96 [92–105] · 39/115 | 185 [179–195] · 69/272 | 175 [165–183] · 83/262 |
| A_seq | same, 4 cameras at a time | 118 [112–124] · 38/89 | 103 [99–110] · 47/120 | 208 [203–277] · 71/133 | 193 [177–212] · 78/249 |
| A_hyb | header + 256 records, then as A_seq | **3.6** (full 116) · 39/88 | **4.6** (full 107) · 48/113 | **3.1** (full 207) · 71/129 | **4.4** (full 189) · 85/224 |
| A_zc | all records, kept raw | 89 [87–94] · 107/116 | 83 [80–84] · 108/112 | 155 [152–158] · 212/226 | 142 [139–147] · 213/212 |
| B | 5 columns, 55 / 110 MB | 69 [67–70] · 84/68 | 64 [62–66] · 86/84 | 112 [109–113] · 161/141 | 101 [97–107] · 164/118 |
| C | index, 34.5 / 69 MB | 48 [46–48] · 68/78 | 47 [45–50] · 73/74 | 76 [75–77] · 122/139 | 75 [72–79] · 124/137 |
| D | 271 kB | 3.5 [3.4–4.4] · 1/– | 4.4 [4.3–4.8] · 1/– | 3.2 [3.1–3.9] · 1/– | 4.6 [4.1–10.7] · 1/– |
| E_a | locator + all records | 107 [101–112] · 38/134 | 100 [99–103] · 40/136 | 185 [178–189] · 70/278 | 176 [171–183] · 87/257 |
| E_cin | locator + index inside the sidecar | 56 [54–56] · 38/38 | 52 [51–52] · 42/37 | 84 [82–86] · 70/135 | 82 [80–86] · 72/125 |
| E_catt | locator + index as a second attachment | 53 [51–60] · 38/37 | 52 [50–54] · 45/38 | 85 [83–87] · 71/127 | 84 [82–88] · 72/130 |

[M] `summary.json`. B and C keep the raw columns next to the Float64 copies, so their "kept" is higher. E_cin and E_catt drop them and match A at 20 B/frame.

**Fetch against parse in (a):**
- Fetch is 80–92 ms (30 fps) and 138–167 ms (60 fps). That is about 1.3–1.6 GB/s from the warm cache.
- Parsing to Float64 time, Float64 offset and Uint32 size is 13–16 ms and 24–28 ms (about 8 ns per record). [M]
- Parser choice:
  - DataView with two u32 reads, and an Int32Array/Uint32Array view: the same speed;
  - `getBigInt64` → Number: 3.9–4.2× slower (53–56 ms and 100–111 ms);
  - in C, converting the index time with BigInt was 3× slower than with u32 halves (26–27 against 8–9 ms at 30 fps). [M]

**Record CRC check in JS** (table CRC-32 over bytes 0–59 of every record): 210–375 ms at 30 fps and 425–767 ms at 60 fps, about 8× the parse time at 30 fps. E45 is about 1.8× faster than E35 here. [M]

**Peak memory during load:**
- It comes from holding all 16 raw buffers at once: A_dvl +115–125 MB (30 fps), +262–272 MB (60 fps).
- Streaming 4 at a time (A_seq / A_hyb) lowered it in E35 (+88 and +129–133 MB).
- E45 peaked higher and with more spread (+113–120 and +224–249 MB). GC timing is the likely cause. [M]/[I]

## 3. Lookup cost

Steady state = PREV for 16 cameras at each 60 Hz draw. Seek = a random jump. Both Electron versions.

| Method | Steady µs/draw, 1 h | Steady, 4 h × 120 | Seek µs/draw, 1 h | Seek, 4 h × 120 |
|---|---|---|---|---|
| Float64 binary search | 1.26–1.39 | 1.69–1.71 | 2.1–2.7 | 4.3–4.5 |
| Float64, last-index hint | 0.07–0.09 | 0.11 | 2.2–3.2 | 4.7–5.2 |
| BigInt zero-copy over 64 B records (flag picks the time per probe) | 1.77–2.01 | 2.5 | 5.2–6.1 | 9.2–9.5 |
| BigInt columnar (B) | 1.64–1.84 | – | 3.6–4.8 | – |
| BigInt single column (C) | 1.26–1.40 | 1.67–1.71 | 2.2–2.8 | 4.5 |
| Lazy D, sync path | 2.3–3.9 | 6.0–7.4 | async: p50 2.1–3.9 ms, p95 3.9–5.3 ms, about 1.2 reads per camera | p50 2.7–3.9 ms |

[M] `summary.json`, `summary_stress_4h120.json`.
- Every method is below 0.06 % of the 16.7 ms frame budget.
- D's steady test ran about 100× faster than real time, so its prefetch (64 frames ahead) often lagged and misses were awaited (366–3,373 draws out of 36,000). At real speed the prefetch has about 1 s of lead for a read of about 3 ms. [I]

## 4. Stress set: 16 × 4 h × 120 fps (27.6M frames; S1 = 1.77 GB)

| Arm | E35 first frame / full ms · kept/peak MB | E45 |
|---|---|---|
| A_dvl | 1306 [1282–1327] · 531/2219 | 1237 [1149–1295] · 533/2242 |
| A_seq | 1414 [1395–1502] · 536/967 | 1351 [1283–1398] · 534/1621 |
| A_hyb | **3.3** / 1405 · 537/994 | **4.4** / 1305 · 534/1347 |
| A_zc | 1117 · 1692/1819 | 996 · 1690/2068 |
| C (552 MB index) | 481 · 954/1020 | 435 · 964/1071 |
| D | 3.2 · 1/– | 4.4 · 1/– |

[M] Load time and memory scale linearly. Loading all 16 buffers at once (A_dvl) peaks at more than 2.2 GB, so a player must stream per camera. Above roughly this size, lazy (D) is the sane mode, and it needs no format change.

## 5. Scaling by arithmetic

Base for the arithmetic, from the measurements above:
- 64 B per record; about 8 ns per record to parse;
- warm `file://` fetch at about 1.4 GB/s;
- the in-memory form kept is 20 B per frame;
- streamed peak = kept + 4 cameras' raw buffers.

| 16 cameras | Frames | S1 bytes | Full load (warm) | Kept | Compact index |
|---|---|---|---|---|---|
| 1 h × 30 | 1.73 M | 110 MB | 0.10 s [M] | 35 MB | 35 MB |
| 1 h × 60 | 3.45 M | 221 MB | 0.17–0.19 s [M] | 69 MB | 69 MB |
| 4 h × 30 or 1 h × 120 | 6.9 M | 442 MB | about 0.35–0.4 s | 138 MB | 138 MB |
| 4 h × 60 | 13.8 M | 885 MB | about 0.7 s | 276 MB | 276 MB |
| 4 h × 120 | 27.6 M | 1.77 GB | 1.24–1.41 s [M] | 552 MB (526 MB JS heap [M]) | 552 MB |

The in-scope cameras top out at 60 fps (plan §3.3), so 4 h × 120 fps is beyond the current scope.

## 6. What to put in the `skellyformat` spec (no layout change)

1. `header_size` must be a multiple of 8 (64 suggested), so records start 8-aligned and typed views need no copy. [I]
2. Finalisation writes `n_records` into the header. Readers fall back to the FileData size. A separate sidecar under `file://` has no Content-Length (SE §4). [I]
3. The player time (fitted when fit-valid is set, else arrival) must never decrease within a file. Either set fit-valid for every frame or none, or have finalisation guarantee the order. A mid-file switch can step back by about the arrival jitter, and PREV binary search then fails. [I]
4. Readers in JS: i64 ns → Number from the two u32 halves minus a recording base. This is exact within 2^53 ns (104 days); offsets are exact below 2^53. Don't parse with BigInt (3.9–4.2× slower). [M]
5. The player should not check every record CRC while loading (210–770 ms per 16 × 1 h in JS). Rely on the embed SHA for finalised files; check per block, or only for unfinalised and recovered files. [M]/[I]

## 7. Player guidance for package 1.9

- **Hybrid start:**
  1. Read the header plus the first 256 records for each camera (16.9 kB) and draw.
  2. Stream each camera's records, at most 4 cameras at a time.
  3. Parse into Float64 time, Float64 offset and Uint32 size (20 B/frame).
  4. Drop each raw buffer after parsing it.
  5. Search PREV from the last index (the hint).
- **Above a size threshold, switch to lazy blocks** (D: 256-record blocks, interpolation guess, bounded cache, prefetch the next block). A suggested threshold is about 500 MB of sidecar, or about 8M frames in total. [I]
- **Avoid zero-copy BigInt.** It keeps 64 B per frame resident (3.2× the memory) and is 1.4–2.3× slower per lookup. [M]

## 8. Why not a compact or columnar section

- **Benefit [M]:**
  - the full load is about 2× faster (C: 47–48 ms against 95–107 ms at 30 fps; 75–76 against 166–185 at 60 fps);
  - it reads a third of the bytes.
  - That is invisible once the first frame takes 3–5 ms through the hybrid path. Retained memory is the same, because the player's in-memory form decides it.
- **Cost [I]:**
  - a second copy of time, offset and size that must match the records;
  - finalisation and crash recovery must rebuild and verify it;
  - both writers (skellycam, skellysync) must implement it;
  - the Python and JS readers, the spec, the test vectors and the golden files grow;
  - the "chosen time" column bakes a player policy into the file.
- **If one is ever added:** put it inside the sidecar after the records, declared in the header. It measured the same speed as a second attachment (E_cin 52–84 ms, E_catt 52–85 ms) [M], and it keeps one attachment, one SHA and one recovery step. [I]

## 9. Files

- `scripts/sidecar_load/`:
  - `gen.py` (synthetic sets; env `SL_ONLY_SKFR=1` writes only the `.skfr`, used for the stress set);
  - `run.ps1` (runner: one Electron process per run, interleaved, CPU load logged; call it with `&`, because `pwsh -File` passes `-Arms a,b` as one string);
  - `summarize.py`;
  - `electron/main.cjs`, `electron/page.html`, `electron/package.json` (the app directory needs its own `package.json`).
  - It reuses `scripts/sidecar_embedding/locator.js` and the helpers in `append_attachment.py`, read-only.
- `results/sidecar_load/`:
  - `summary.json` (1 h sets, all arms, both versions);
  - `runs.jsonl` (raw runs, 1 h);
  - `summary_stress_4h120.json`, `runs_stress_4h120.jsonl`.
- Synthetic data (rebuildable, 3.5 GB) was kept only in the session scratchpad.
