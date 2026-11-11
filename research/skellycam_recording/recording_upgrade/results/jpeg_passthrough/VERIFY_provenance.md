# jpeg_passthrough: provenance verification of the 2026-11-10 FINDINGS draft

2026-11-10. Adversarial verifier, provenance lens. The draft under review is the "timed results added" revision (§2.9, §3.2-§3.4, §5 new). The previous provenance report (2026-11-09) is now `VERIFY_provenance.prev.md`.

No timed measurement was run. Everything here comes from reading the result files and code and re-downloading sources. Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU).

## 1. What was checked and how

| Check | Method | Result |
|---|---|---|
| Every MUX-D / MUX-F number (§2.9.1, §2.9.2, §3.1 mux row, §3.2, §3.3) | Recomputed median and min-max per (container, res) from `runs` in `bench/bench_mux_default_pyav19_20261110T055215Z.json` and `bench/bench_mux_fsync_pyav19_20261110T093308Z.json` | All match to 2 decimals. 130 runs per file, 0 `error` keys, `frames` 3000 everywhere. CPU µs/frame values are all multiples of 15625/3000 µs, and close CPU ms all multiples of 15.625 ms (260 of 260 runs) |
| Container B/frame and payload per frame | `(bytes_on_disk - payload_bytes)/3000`; `payload_bytes/3000` | 45.7/45.8, 11.8/12.1, 12.4, 131.3, 11.8/12.0, 26.4/26.6, 28.9/33.8, 20.0; 55,341 and 192,382 B/frame: all match |
| OPEN numbers (§2.9.3, §3.1, §3.2) | `bench/open_long.json` `files.*` | All match: open ms arrays, medians, counts (54,000 ×3, 53,819), `pyav_stream_frames`, demux counts and ms, bytes (about 2.99 GB) |
| ROT numbers (§2.9.4, §3.4) | Recomputed from `bench/bench_rotate_20261110T093546Z.json` `runs` | All 6 medians and ranges match. CPU steps are 15.625 µs/frame. `meta.lib_sha256` = 3dd7a8a9…; the DLL at that path and the one used for `rotation.json` (106dc0c8 scratchpad) have the same sha256 (re-hashed) |
| Run conditions (§2.9, §5) | `results/BENCH_RUN_2300_LOG.jsonl` lines 18, 30, 61, 62 (orders 17, 29, 59, 60) | status ok, exit 0, `affinity` "pcores", `defender_scan_events_during_item` "", `load_over_15pct` false; MsMpEng 32.44 / 1.23 / 34.78 / 4.75 CPU-s; durations 47 s and 59 s: all match |
| Arithmetic (§2.9.1, §2.9.4, §3.2) | Recomputed | 22% (19.97/16.32), 11.4×/4.2×/10.5×/3.9×, 0.62/1.81/6.5/7.0 ms/s, 58/223 ms/s, 26×/27×, 0.02%/0.24%, 266/532/67 ms/s: correct |
| Functional numbers carried over (§2.1-§2.8, §3.1) | `pyav19_recheck.json` (A_matrix 210 rows, 194 written, 194 byte-exact; c930e sizes; ts maxima per container; C_killed; D_setup; E_decode), `version_bump.json` (26 rows), `verify_method_*.json`, `pyav19_seek_ts_check.json`, `pyav19_lavf_tag.json`, `pyav19_fmp4_tb_us_readers.json`, `rotation.json` (228/228, 195, 33, max diff 5), `truncation.json` (409, large_avi), `edge_cases.json` (438 B, 5 DHT out) | All spot-checked values match |
| Quality-target header | `results/intra_compare/camera_jpeg_quality.md` lines 7-10; HANDOFF.md §1.1 lines 49-56 | Match: q94 luma and chroma, not exact (err 124 / 60), 4 sets. Correctly labelled inferred / NOT VERIFIED |
| Code citations | Opened every cited line in `bench_mux.py`, `bench_open_long.py`, `bench_rotate.py`, `rotate_check.py:74-92`, `jp_common.py`, `jp_io.py`, `pyav19_recheck.py`, `version_bump_check.py:58`, `python_integration/recwriter.py:52`, FreeMoCap 5632778a `video_group_helper.py`, skellycam `parse_video_filename.py:18`, `git show upstream/sfn26:` Rust files | Mostly correct. Errors in §2 below (R1, R2) |
| FFmpeg / OpenCV sources | Re-downloaded n9.0.2 `mux.c`, `matroskaenc.c`, `avienc.c` and OpenCV 4.12.0 `cap_ffmpeg_impl.hpp` from raw.githubusercontent.com on 2026-11-10 into the step2 scratchpad; `cmp` against the author's copies | Byte-identical. Cited lines (mux.c:820-821, matroskaenc.c:3602-3603, 3744-3747, matroska.c:86, 110-124, isom.c:55, mjpegdec.c:62,148, avienc.c:745-762, movenc.c:177-179,204-208, cap_ffmpeg_impl.hpp:1980-1996) say what the draft says |
| PyAV source | uv-cache wheel `av-19.0.2` `av/container/output.py:265-269,306-310` | Quote and ValueError text match |
| Web sources (accessed 2026-11-10) | curl | webmproject.org: "Video codec SHOULD be VP8 *or* VP9" present. matroska.org codec_specs: V_MJPEG text with "[@!JPEG]" and "Initialization: none" present. mp4ra.org object types: 6C "Visual ISO/IEC 10918-1" present. All primary |

## 2. Refuted

**R1. The Rust "~1-2ms per frame" comment is on line 4, not line 3.**
- Draft (§2.9.4, §8): cited at `jpeg_transform.rs:3`, and §8 says the previous revision's `:4` was corrected to `:3`.
- code: `git show upstream/sfn26:skellycam-rust/src/camera_group/jpeg_transform.rs | grep -n "1-2ms"` gives `4://! no quality loss, ~1-2ms per frame.` Line 3 holds only the start of the sentence ("Operates entirely in the DCT (compressed) domain — no decode to pixels,"). The previous provenance report also had line 4.
- Correction: cite `jpeg_transform.rs:4` (or `:3-4` for the whole sentence). Delete the §8 line that claims `:4` was wrong.

**R2. Three `jp_io.py` line citations are stale.** Three entries were added at `jp_io.py:46-48` for the fMP4 1/1e6 variants, which shifted the later lines by 3.
- `jp_io.py:332` (OpenCV seek targets, §2.4): the targets list is now at line 335; the match logic is at 336-343.
- `jp_io.py:154-160` (folder `timestamps.csv`, §2.3): the jpg_folder branch is now at 157-166, and `timestamps.csv` is opened at 161.
- `jp_io.py:236-250` (`pyav_seek`, §2.4): `def pyav_seek` is now at 239, and the pts-only `exact` test is at 253.
- Correction: cite `jp_io.py:335-343`, `:157-166` and `:239-253`.

**R3. "Container differences of a few µs/frame at 720p are within run-to-run variation" is contradicted by the two runs.**
- Draft: §2.9.1 (inferred), §4.3 ("the run-to-run spread of the raw baseline (22%) is as large as most container differences"), §5 ("Treat 720p container differences of a few µs/frame as noise").
- measured (MUX-D vs MUX-F medians, computed from `runs`): every libav container moved by at most 2.7% between the two runs at 720p: mkv +0.1%, mp4 +0.2%, mov -0.1%, fmp4_1s_tb_us +0.3%, fmp4_perframe_tb_us -2.7%, nut -1.7%, avi -1.0%, raw mux -1.9%. At 1080p the largest change is -2.3%. Only the Python writers moved more: raw_sidecar 720p -18.3% (19.97 → 16.32) and jpg_folder 720p -12.6%.
- The container ordering is reproducible. For example, MP4 vs fMP4 1 s at 1/1e6 at 720p is 17.87 vs 20.78 in MUX-D and 17.91 vs 20.86 in MUX-F.
- Correction: the libav container medians are reproducible to within about 3%, and their differences are real. The 22% swing is specific to the Python `raw_sidecar` loop. The conclusion "the wrapper does not matter for single-stream throughput" still holds, but on magnitude: the largest 720p spread between libav containers is about 4.6 µs/frame, about 0.14 ms/s at 30 fps (computed). The differences are not noise.

## 3. Weak (true but imprecise, or missing a label or scope)

| # | Claim | Why | Fix |
|---|---|---|---|
| W1 | §2.9.2 "about 3.9-4.1 GB/s, computed from bytes / median close time" | That holds only for fMP4 1 s at 1/1e6 (166,061,056 B / 42.91 ms = 3.87 GB/s; 577,182,423 B / 140.50 ms = 4.11 GB/s). Across all medians the range is 2.0 GB/s (720p mjpeg_raw_mux, 81.92 ms) to 4.15 GB/s (1080p mov) | Say "for fMP4 1 s at 1/1e6", or give 2.0-4.1 GB/s across writers |
| W2 | §3.1 "OpenCV count exact with gaps … MKV: no (888/888)" | Reads as "888 of 888", which would be exact. The data is 888 for 831 (gap60) and 888 for 874 (drop50) | Write "no (888 for 831 / 888 for 874)" |
| W3 | §4.6 "After a kill, OpenCV over-counts by 1-3 frames (582 vs 579, 597 vs 596)" | True for fMP4 only. On killed NUT, OpenCV under-counts (595 vs 598 read), and on killed MKV the count is negative (`verify_method_killed_readers.json`) | "OpenCV miscounts killed files: fMP4 +1 to +3, NUT -3, MKV negative" |
| W4 | §2.3 "OpenCV differs by up to 586 µs … (`mux_matrix.md` lines 38-39, 49-50)" | Line 50 is jpg_folder, where all three readers agree (6031976 ×3). The differing rows are 38, 39 and 49 | Cite lines 38-39, 49 |
| W5 | §2.9 run conditions: "Items ran … 01:18-01:19 (OPEN) … 04:33-04:36 (ROT)" | OPEN ran 01:18:31-01:18:57 and ROT ran 04:33:19-04:35:46 (log). It also omits the flag "leftover processes after item (listed, not killed)" that all four items carry. BENCH_RUN_2300_SUMMARY.md line 38 explains it as harmless monitoring shells. Before ROT, SearchIndexer used 9.36 CPU-s in the 10 s window (mean CPU 6.03%, under the 15% flag) | Give exact times. Mention the leftover-process flag and the summary's explanation, and SearchIndexer before ROT |
| W6 | §2.9.3 "matches the bench's own rationale that the mov demuxer walks every moof at open (docstring :8-10)" | The docstring is the bench author's hypothesis, not a source. Citing it does not support the mechanism | Keep it as inferred without the docstring as support, or cite FFmpeg `libavformat/mov.c` (fragment index / moof reading) at file:line |
| W7 | §2.9.3 "Every open was from the page cache" (bold, presented as fact) | The script docstring (`:15`) states it and no cache drop is done, but residency was not measured. A 2.99 GB file written just before the open is very likely cached, but this is not shown | Label it "inferred (no cache drop; docstring :15)". "No cold-open number" is correct as written |
| W8 | §2.9.1 / §4.4 Defender share of jpg_folder cost: "MsMpEng used 32.44 CPU-s during MUX-D" | That CPU-s figure covers the whole 47 s item (all 13 writers × 2 sizes), not jpg_folder alone. A direct per-writer measurement exists in write_throughput: Defender CPU per 30 s cell, files 26.8 s vs 1.2-1.5 s for the other writers (BENCH_RUN_2300_SUMMARY.md line 102) | Say the item-level CPU-s is not attributed per writer, and cite the write_throughput per-writer figure as the measured support |
| W9 | §4.3 "about 0.2% of one CPU per 1080p30 camera (computed, §2.9.1)" | §2.9.1 computes wall time (1.81 ms/s), not CPU. CPU medians agree here (62.5 µs/frame at 1080p → 1.9 ms/s), but CPU resolution is 5.2 µs/frame | Say "wall time ≈ CPU here (MUX-D `cpu_us_per_frame_mux` median 62.5)", or say "0.2% of wall time" |
| W10 | §2.9.4 "The script raises on any failed transform (`:53-55`)" | It raises only on hard errors. A `TJERR_WARNING` result is kept (`rotate_check.py:82-89`). ROT used c930e and c922 only, which had 0 warnings in `rotation.json` | "raises on a hard error; warnings are accepted (none expected for these two sets, `rotation.json` `tj3_warnings` 0)" |

## 4. Items confirmed that the lens asks about

- **PyAV 18 results:** every PyAV 18 item is marked "[18]" or "measured, PyAV 18 - background". None is presented as primary.
- **Contaminated daytime numbers:** this topic has none. The draft says so (§5 write-latency flag).
- **Target A/B:** the draft states that nothing in the topic is at A or B (camera quality, about q94), with the inference labelled. There are no quality-dependent numbers without a target.
- **BENCH.md vs JSON:** BENCH.md rounds to 1 decimal. The draft's 2-decimal figures come from the JSON and are consistent with BENCH.md.
- **Version strings:** PyAV 19.0.2 and libavformat/libavcodec 63.1.102 are in both mux JSON metas. `ffmpeg_version_info` "9.0.2" is in `pyav19_seek_ts_check.json` and `pyav19_lavf_tag.json` metas. `open_long.json` records `pyav` and `opencv` but no lib versions; the draft does not claim it does.
- **Flags:** the libx265 affinity, NVENC 12-session, nvJPEG, WebCodecs, N=8 `<video>` and uncompressed_intra flags are correctly marked as not applicable. The 15.625 ms timer, Defender ON and P-core pinning are reflected.

## 5. Verdict

Provenance is good. Every timed number in §2.9 and §3.2-§3.4 matches the quiet-run JSON exactly, and the functional numbers match their result files. The sources re-verify as primary and byte-identical.

Three findings were refuted. Two are citation errors: the Rust line is 4, not 3, and three `jp_io.py` line numbers are stale. The third is an inference ("container differences are noise") that the two runs contradict. It should be reworded around magnitude. Ten weak points need wording or label fixes. None changes a §4 recommendation.
