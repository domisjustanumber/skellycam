# GF02: container functional matrix under PyAV 19.0.2 (2026-11-10)

Functional only. No durations, rates or CPU were recorded (timing rule). The writer child paced itself at 30 fps with `sleep`; that pacing only shapes the feed and nothing from it is reported.

- Writers: PyAV 19.0.2 (FFmpeg 9.0.2, libavformat 63.1.102), Python 3.12.13, `uv run --script` with exact PEP 723 pins (`av==19.0.2`, `numpy==2.2.6`).
- Readers: OpenCV 4.12.0 CAP_FFMPEG and FreeMoCap's real `VideoHelper`, both used read-only from the skellycam `.venv`, following the pattern in `scripts/jpeg_passthrough/verify_method_reader.py`. ffprobe was used for inspection only.
- Raw data: `GF02_container_matrix.json` (merged rows), `GF02_partA_write.json`, `GF02_partA_long_write.json`, `GF02_partA_read.json`, `GF02_partA_long_read.json`, `GF02_partB_kills.json`, `GF02_partB_read.json`, `GF02_recovered_rates.txt`.
- Scripts: `scripts/crash_resilience/gapfill/GF02/` (`gf02_common.py`, `gf02_partA_write.py`, `gf02_child.py`, `gf02_partB_kills.py`, `gf02_cv2_reader.py`, `gf02_report.py`).
- Media: `C:/Users/Dom/Documents/skellycam-raw/.../crash_resilience/gapfill/GF02/` (partA 1.6 GB, partB 1.9 GB). The four 54,000-frame files (about 2.99 GB each) were deleted after reading (`GF02_partA_long_read.json` → `deleted_after_read` true ×4).
- Free disk before writing: 808,459,767,808 B (Part A) and 806,222,315,520 B (long set). Both are above the 30 GB floor, so the long set ran.

## Method

**Writer.** `GF02Writer` (code: `gf02_common.py`) is a copy of `recwriter.RecordingWriter` (code: `scripts/python_integration/recwriter.py:67-157`) with three changes:
- `add_mux_stream("mjpeg", rate=30, width, height)` replaces the encoder stream, as `verify_method_writer.py:43` does;
- `flush_packets=1` is added to the muxer options;
- an optional empty packet follows each frame.

It writes the same 48-byte CRC sidecar and the same manifest. `recwriter.recover()` and `find_unfinished()` were used unchanged. Our container names were added to `rw.CONTAINERS` in-process only; the file was not touched (code: `recwriter.py:253`).

**Containers** (code: `gf02_common.py` `CONTAINERS`):

| name | format | muxer options | extra |
|---|---|---|---|
| MKV + fp | matroska | `flush_packets=1` | none |
| MKV + fp + empty pkt | matroska | `flush_packets=1` | after every frame, `av.Packet()` with time_base 1/1e6, pts = dts = frame time in µs + 1, sent with `mux_one`. This is the WT verifier's construction (93366190 scratchpad `verify_emptypkt_av19.py`, `write_mkv`). |
| fMP4 per-frame + fp | mp4 | `movflags=frag_keyframe+empty_moov+default_base_moof`, `flush_packets=1` | movflags as `verify_method_writer.py:33` (FRAGPF) and `jp_io.py:48` |
| fMP4 1 s + fp | mp4 | same plus `min_frag_duration=1000000` | as `verify_method_writer.py:32` (FRAG1S) and `jp_io.py:47` |

**PTS modes.**
- `real`: stream time base 1/1e6 requested; pts = (t − t0) rounded half up (code: `recwriter.py:111-115`).
- `index`: 1/30 requested; pts = i/30 (code: `recwriter.py:117-121`).
- Time bases after the header (measured, `GF02_partA_write.json` → `time_base`): MKV 1/1000 in both modes; fMP4 real 1/1000000; fMP4 index 1/15360.

**Part A inputs.**
- c930e full (891) and c922 full (893), with real capture timestamps (`jp_common.real_timestamps_ns`).
- gap60 (831) and drop50 (874), built with the keep lists of `verify_method_writer.py:88-89`, real timestamps kept.
- Long: c930e looped to 54,000 frames with real intervals looped and no gap, the shape of `bench_open_long.py:49-54`.
- Rounding differs from `verify_method_writer.py:92`, which floors to µs; the recwriter rounding used here rounds half up.

**Part A checks per file.**
- PyAV demux byte-exact for every JPEG.
- PyAV pts-seek identity at 11 targets.
- ffprobe `-count_packets` and ffprobe per-packet size list.
- EBML scan of MKV files (a non-FFmpeg parser, copied from the WT verifier).
- cv2 `CAP_PROP_FRAME_COUNT`, `CAP_PROP_FPS` and `grab()` count.
- cv2 sequential `read()` hashes against reference hashes.
- 11 `CAP_PROP_POS_FRAMES` seeks at k = 0, ⌊n·p/10⌋ for p = 1..9, and n − 1, checked by frame identity.
- `jp_io.freemocap_read` reads at 0, 1, count//2 and count − 1, matched to the reference.
- Reference hashes: cv2 CAP_FFMPEG reading the corpus folder through `frame_%06d.jpg` (the same mjpeg decoder). The sequential decode matched the reference for every frame of every non-long file (`seq_matches_input` = n in 32/32).
- Long files: count with `grab()`, and seeks checked against the reference of input k mod 891. There was no sequential `read()` pass.

**Part B.**
- 4 containers × {real, index} × 6 kill points (50, 137, 300, 451, 611, 700 frames acknowledged) = 48 kills.
- The kill method alternates between `os._exit(1)` in the child right after "M k" and TerminateProcess from the parent. The parent's TerminateProcess is `os.kill(inner_pid, SIGTERM)` plus `Popen.kill()`, as in `run_kill_matrix.py`, after a seeded 0–33 ms random delay.
- Each combination got 3 + 3 kills, and every kill point was hit by both methods across the two PTS modes.
- Feed: c930e looped, paced at 30 fps; timestamps from real c930e intervals looped.
- "Acknowledged" means `write()` returned: mux, plus the empty packet where used, plus the sidecar record flushed.
- After each kill:
  - sidecar records;
  - PyAV byte-exact prefix and torn-tail inspection (`packet.is_corrupt`, prefix-of-expected, decode outcome);
  - ffprobe count;
  - PyAV seek to frame k = exact//2 by its sidecar pts, checked by identity;
  - cv2 FRAME_COUNT, `grab()` count, and a POS_FRAMES = k seek checked by identity;
  - then `recover()`, followed by the same checks on `rec.recovered.*`.

## Part A table

Cell = cv2 FRAME_COUNT / frames written; cv2 POS_FRAMES seeks exact (identity vs input) of 11; FreeMoCap ok, meaning count = written and all 4 reads match the reference.

measured: `GF02_container_matrix.json` → `partA[]` (`cv2_frame_count`, `cv2_seek_exact_input`, `freemocap_ok`, `pyav_seek_exact`).

| container | PTS | c930e full (891) | gap60 (831) | drop50 (874) | c922 full (893) | long 54,000 | PyAV seek n/11 (per input) |
|---|---|---|---|---|---|---|---|
| MKV + fp | real | 888 / 891; 2/11; FAIL | 888 / 831; 2/11; FAIL | 888 / 874; 1/11; FAIL | 893 / 893; 11/11; ok | 53820 / 54000; 1/11; FAIL | 11, 11, 11, 11, 11 |
| MKV + fp | index | 891 / 891; 11/11; ok | 831 / 831; 11/11; ok | 874 / 874; 11/11; ok | 893 / 893; 11/11; ok | 54000 / 54000; 11/11; ok | 11, 11, 11, 11, 11 |
| MKV + fp + empty pkt | real | 888 / 891; 2/11; FAIL | 888 / 831; 2/11; FAIL | 888 / 874; 1/11; FAIL | 893 / 893; 11/11; ok | not run | 10, 10, 10, 10 |
| MKV + fp + empty pkt | index | 891 / 891; 11/11; ok | 831 / 831; 11/11; ok | 874 / 874; 11/11; ok | 893 / 893; 11/11; ok | not run | 10, 10, 10, 10 |
| fMP4 per-frame + fp | real | 891 / 891; 9/11; ok | 831 / 831; 1/11; ok | 874 / 874; 8/11; ok | 893 / 893; 11/11; ok | not run | 11, 11, 11, 11 |
| fMP4 per-frame + fp | index | 891 / 891; 11/11; ok | 831 / 831; 11/11; ok | 874 / 874; 11/11; ok | 893 / 893; 11/11; ok | not run | 11, 11, 11, 11 |
| fMP4 1 s + fp | real | 891 / 891; 9/11; ok | 831 / 831; 1/11; ok | 874 / 874; 8/11; ok | 893 / 893; 11/11; ok | 54000 / 54000; 11/11; ok | 11, 11, 11, 11, 11 |
| fMP4 1 s + fp | index | 891 / 891; 11/11; ok | 831 / 831; 11/11; ok | 874 / 874; 11/11; ok | 893 / 893; 11/11; ok | 54000 / 54000; 11/11; ok | 11, 11, 11, 11, 11 |

**Every file**

- measured: all 36 files round-trip byte-exact through PyAV, and the ffprobe packet count equals the frames written (`partA[].pyav_all_exact`, `ffprobe_packets`).
- measured: in every one of the 36 files, `grab()` returned exactly the frames written (`cv2_grab`).

**FreeMoCap failures**

- measured: where FreeMoCap failed, the cause was the count:
  - c930e full real MKV: count 888, all 4 reads matched;
  - gap60 and drop50 real MKV: count 888, and the read at 887 raised "Failed to grab frame";
  - long real MKV: count 53,820, all 4 reads matched (`partA[].freemocap`).

**Real-PTS seek misses** (measured, `GF02_partA_read.json` → `seek[].got_seq_index`; long: `GF02_partA_long_read.json` → `got_input_index_near`)

- fMP4 c930e full: k 178 → 179 and 267 → 268.
- fMP4 gap60: every target after 0, landing 1–21 frames off.
- fMP4 drop50: 174 → 175, 349 → 350, 437 → 438.
- MKV c930e full: 1–3 frames late from k = 178 on; 890 not found.
- Long MKV real: 5400 → 5418, 10800 → 10836, 16200 → 16254, then more than 70 frames off.

**MKV empty-packet variant, clean close**

- measured: the 8 files are byte-exact.
- measured: ffprobe lists only the real packets (`ffprobe_zero_size_listed` 0, `ffprobe_packets` = n).
- measured: the EBML scan finds n size-0 SimpleBlocks and n + 1 Clusters per file, e.g. c930e: 892 clusters, 1782 SimpleBlocks, 891 of size 0 (`partA[].ebml`).
- measured: PyAV demux hides the size-0 blocks (`pyav_empty_packets_seen` 0).
- measured: overhead is +5,360 B over MKV+fp for 891 frames (49,360,153 vs 49,354,793 B), computed as **+6.0 B/frame**.
- measured: a PyAV seek to the **last frame's pts returns no packet** in all 8 finalized empty-packet files. The other 10 targets are exact (`pyav_seek_miss` k = n − 1, no `got_pts`).
  - measured: a probe seek to pts 29667 on `A_c930e_full_mkv_fp_empty_index.mkv` returned only the EOF flush packet (scratch probe; the files are in the media folder).
  - measured: the Cues hold 891 CuePoints, and the last points to the Cluster that holds frame 890 (scratch EBML Cues scan).
  - The demuxer mechanism is NOT VERIFIED.

**Other**

- measured: c930e real MKV has 1 sidecar record with `FLAG_PTS_ADJUSTED`. Two frames under 1 ms apart were bumped +1 ms, so all 11 PyAV seeks are exact. Index mode needed no bump (`partA[].pts_adjusted`, `GF02_partA_write.json`).

## Part B table

Kills per combination: 6 (3 `os._exit`, 3 TerminateProcess). Frames lost = acknowledged − complete byte-exact frames on disk.

measured: `GF02_container_matrix.json` → `partB[]`.

| container | PTS | lost per kill min / median / max | torn tail seen (flagged `is_corrupt`) | ffprobe = PyAV packets | cv2 FRAME_COUNT, killed | cv2 grab = packets, killed | PyAV / cv2 seek on killed file | recover matched = on-disk exact | recovered byte-exact | cv2 count recovered = frames | cv2 seek recovered |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MKV + fp | real | 1 / 1 / 1 | 0 (0) | 6/6 | −2.767e17 (6/6) | 6/6 | 6/6 / **0/6** | 6/6 | 6/6 | **0/6** (fps 62.5) | **0/6** |
| MKV + fp | index | 1 / 1 / 1 | 0 (0) | 6/6 | −2.767e17 (6/6) | 6/6 | 6/6 / **0/6** | 6/6 | 6/6 | 6/6 | 6/6 |
| MKV + fp + empty pkt | real | **0 / 0 / 0** | 0 (0) | 6/6 | −2.767e17 (6/6) | 6/6 | **0/6 (1 late)** / **0/6** | 6/6 | 6/6 | **0/6** (fps 62.5) | **0/6** |
| MKV + fp + empty pkt | index | **0 / 0 / 0** | 0 (0) | 6/6 | −2.767e17 (6/6) | 6/6 | **0/6 (1 late)** / **0/6** | 6/6 | 6/6 | 6/6 | 6/6 |
| fMP4 per-frame + fp | real | 1 / 1 / 1 | 0 (0) | 6/6 | = frames (6/6) | 6/6 | 6/6 / 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| fMP4 per-frame + fp | index | 1 / 1 / 1 | 0 (0) | 6/6 | = frames (6/6) | 6/6 | 6/6 / 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| fMP4 1 s + fp | real | **14 / 23 / 29** | 0 (0) | 6/6 | = frames (6/6) | 6/6 | 6/6 / 5/6 | 6/6 | 6/6 | 6/6 | 5/6 |
| fMP4 1 s + fp | index | **1 / 14 / 30** | 0 (0) | 6/6 | = frames (6/6) | 6/6 | 6/6 / 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |

**Acknowledgement and recovery bookkeeping**

- measured: in all 48 kills, the child's last "M" line = sidecar valid records = the kill point. Sidecar torn tail and bad-CRC records were 0 (`partB[].last_M_line`, `sidecar_records`, `sidecar_torn_tail_bytes`, `sidecar_bad_crc_records`).
  - inferred: the TerminateProcess kills landed between frames, while the child slept in its pacing wait.
- measured: `find_unfinished()` listed 48/48 stems, every manifest was still `recording`, and no PyAV demux error was raised on any killed file (`find_unfinished_lists_it`, `manifest_state`, `killed_pyav.demux_error`).
- measured: `recover()`'s matched prefix equals the byte-exact frames on disk in 48/48 kills, with `first_mismatch` and `reader_error` null.

**Frames lost per kill**

- measured: fMP4 1 s, frames lost per kill:
  - real: 20, 14, 24, 22, 29, 26;
  - index: 20, 17, 30, 1, 11, 10.

  The kill points are 50 / 137 / 300 / 451 / 611 / 700 in that order (`lost_vs_sidecar`).
  - inferred: with index PTS, loss = ((kill point − 1) mod 30) + 1, i.e. everything since the last 1 s fragment boundary. This is consistent with the rule "a fragment is flushed when the *next* packet meets the condition" (n9.0.2 `movenc.c:7449-7455`, as cited in CR §2.1).

**Torn tails**

- measured: no torn tail packet in any of the 48 kills (`killed_pyav.first_non_exact` null).
  - So the question "does PyAV flag a torn tail or decode it silently" is **not answered by this run**. These paced kills never interrupted a write in progress.

**Seeks on killed files**

- measured: on a killed MKV + empty-packet file, a PyAV seek to frame k's pts lands **one frame late** in 12/12 kills: `got_pts` = pts of frame k + 1, e.g. target 4976 → 5008 (`killed_pyav_seek`). On a killed plain MKV + fp file it is exact in 12/12.
  - inferred (mechanism NOT VERIFIED): every Cluster except the first starts with the empty block, and that block carries frame k's time but sits just before frame k + 1. The index the demuxer builds from Cluster starts therefore maps t_k to frame k + 1.
- measured: a cv2 POS_FRAMES seek on a killed MKV (both variants, both PTS modes) returned the wrong frame in 24/24 kills.
  - Where frame 0 was inside the ±70-frame search window (kill points 50 and 137), it returned **frame 0** (`killed_cv2.seek[0].got_input_index_near` [0]). This matches CR §2.2.
- measured: the single fMP4 1 s real-PTS cv2 seek miss is kill 137: k 61 → frame 60, on both the killed and the recovered file.

**`recover()` on real-PTS MKV**

- measured: `recover()` of a **real-PTS MKV** gives a file whose ffprobe `r_frame_rate` is 125/2 and `avg_frame_rate` 0/0. The killed source has 30/1, 30/1 (`GF02_recovered_rates.txt`).
- measured: cv2 then reports fps 62.5 and a count of about 2.1× the frames, e.g. 102 for 49 and 1451 for 699, in 12/12 kills (both MKV variants). POS_FRAMES seeks land at about k·30/62.5, e.g. 149 → 80 (`recovered_cv2`).
- measured: recovered index-PTS MKV files and every recovered fMP4 file keep the right count.
- code: `recover()` remuxes with `add_stream_from_template(s_in)` (`recwriter.py:259`).
  - inferred: the template does not carry the writer's 30 fps. The real-PTS MKV's 1 ms timestamps then make FFmpeg guess 62.5 fps. Python_integration's PyAV 19 kill (F4/F6) recovered real-PTS MKV with count 297.0; its timestamps came from `perf_counter_ns` pacing, not from the c930e intervals. The exact trigger is NOT VERIFIED.

## Combinations not run or not answered

- Torn tail packets: none occurred, so PyAV `is_corrupt` behaviour and silent decode on a torn tail are **not tested here**. Earlier evidence: PI F4/F5 and CR §2.4.
- Long set: the MKV + empty-packet and fMP4 per-frame containers were not written; the task limited it to 4 files. The long set also has no gap; it is the `bench_open_long.py` shape.
- Part B cv2 checks: one seek per file. FreeMoCap was not run on killed or recovered files.
- Chromium playback, timed write cost of the empty packet, power loss and multi-camera kills were not run. The timing rule excludes timed cells.

## What this changes (labelled; FINDINGS not edited)

### jpeg_passthrough §4

- **JP §4 item 2:** the "leading candidate fMP4 1 s" now has a measured crash cost under PyAV 19.
  - measured: 14–30 frames lost per live kill (median 23 real, 14 index; 12 kills), against 1 for per-frame fMP4 + fp and MKV + fp, and 0 for MKV + fp + empty packet (Part B).
  - measured: the claim "exact OpenCV frame count with dropped frames and at 54,000" still holds for fMP4 1 s + fp in both PTS modes (Part A).
  - measured: with **real** PTS, POS_FRAMES seeks miss even on fMP4: gap60 1/11, drop50 8/11, c930e full 9/11.
- **JP §4 item 8:** the MKV count reason applies to **real-PTS MKV only**.
  - measured: index-PTS MKV + fp gives the exact count, 11/11 seeks and FreeMoCap ok on c930e full, gap60, drop50, c922 full and 54,000 frames.
  - measured: the 1 ms-grid collision is handled by the recwriter +1 tick bump (1 bump in the c930e set, PyAV seeks 11/11).

### crash_resilience §3A and §4.1

- **CR §3A:** the fMP4 1 s + fp row is now P19 measured (proposed text below), and a new MKV + empty-packet row is proposed.
- **CR §3A, MKV + fp row:** add "live paced kill: 1 frame in 12/12 kills, real and index PTS (GF02)".
- **CR §3A, fMP4 per-frame row:** add "live paced kill with `frag_keyframe` (not `frag_every_frame`) + fp: 1 frame in 12/12; cv2 count exact on the killed file 12/12 (GF02)".
- **CR §4.1:** MKV + fp stays coherent, with three conditions:
  - measured: index PTS make clean and recovered MKV files exact for cv2 and FreeMoCap.
  - measured: `recover()` (template remux) breaks the cv2 count of real-PTS MKV (62.5 fps, 12/12).
  - measured: the empty-packet variant cut the loss to 0 in 12/12 more kills. It brings two seek defects: on unfinalized files PyAV seeks land 1 frame late (12/12), and on finalized files a seek to the last frame returns nothing (8/8).

### python_integration §3, §4.2 and §4.3

- **PI §3:** fill the "cv2 count, index (CFR) PTS" fMP4 cell (proposed text below), and extend the MKV cell with gap60, drop50 and 54,000.
- **PI §4.2:** now measured across every container.
  - measured: index PTS gave the exact cv2 count, 11/11 POS_FRAMES seeks and FreeMoCap ok in 18/18 index files (4 containers × 4 inputs + 2 long).
  - measured: real PTS failed seeks on drops in every container.
- **PI §4.3:** "kill behaviour with 1 s fragments was not tested here" is now measured: 14–30 frames lost (Part B). Add the `recover()` real-PTS MKV fps defect.

### write_throughput §4.4

- **WT §4.4:** three of the four adoption conditions are now met. Clean-close byte-exact: 8/8 files. More kills: 12 more, 0 lost, so 15/15 in total with WT's 3. Non-FFmpeg parser check: the EBML scan sees n size-0 SimpleBlocks.
- **WT §4.4:** the timed cell is still missing.
- **WT §4.4:** add two new caveats: the PyAV seek on an unfinalized file lands 1 frame late, and the last-frame seek fails on a finalized file.

## Proposed replacement text

**CR FINDINGS §3A, line 409 (old):**

> `| fMP4 1 s fragments + fp | bg only (1 s lost) | yes (bg) | not tested (P19) | not tested | not tested | 19.7 / 20.4 / 15.8 | 12.5 | not run |`

**Proposed:**

> `| fMP4 1 s fragments + fp | 14–30 frames (median 23 real / 14 index PTS; = frames since the last 1 s boundary), 12 live paced kills (P19, GF02) | none seen in 12 paced kills; torn-tail handling not exercised (GF02) | = byte-exact frames 12/12 / exact 11/12 (1 real-PTS drift miss) (GF02) | exact 12/12 (GF02) | not tested | 19.7 / 20.4 / 15.8 | 12.5 | not run (recwriter remux: count and bytes exact 12/12, GF02) |`

**New row after line 407 (proposed):**

> `| MKV + fp + empty timestamped packet per frame | **0** in 12/12 live paced kills (GF02) + 3/3 (WT) | no (GF02) | -2.767e17 / wrong frame (frame 0 where determinable) (GF02) | **1 frame late** 12/12 (GF02); finalized file: last-frame seek returns nothing 8/8 | not tested | not measured | 45.8 + 6.0 (computed from GF02 bytes) | not run (recwriter remux exact 12/12; real-PTS remux fps 62.5) |`

**PI FINDINGS §3, line 359 (old):**

> `| cv2 count, index (CFR) PTS | right on 7 of 7 | not tested | right on 7 of 7 | n/a | F3 |`

**Proposed:**

> `| cv2 count, index (CFR) PTS | right on 7 of 7; also gap60, drop50 and 54,000 (GF02) | right on c930e, gap60, drop50, c922 (per-frame and 1 s fragments) and at 54,000 (1 s); POS_FRAMES seeks 11/11 (GF02) | right on 7 of 7 | n/a | F3; GF02 |`
