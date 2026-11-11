# jpeg_passthrough: provenance verification of the draft FINDINGS

2026-11-09, Gerald. Adversarial check (provenance lens) of the draft FINDINGS.md sent by the workflow (the draft is not on disk). No timed benchmark was run. Paths are relative to `research/skellycam_recording/recording_upgrade/` unless they are absolute.

## Method

- Opened every cited result file and recomputed the cited numbers with short Python one-liners: `pyav19_recheck.json` (A–E), `pyav19_fmp4_tb_us_readers.json`, `version_bump.json`, `mux_matrix.json`/`.md`, `keyframe_setup.json`, `truncation.json`, `edge_cases.json`, `electron_check.json` and `rotation.json`.
- Downloaded the FFmpeg n9.0.2 files (`mux.c`, `matroskaenc.c`, `matroska.c`, `isom.c`, `avienc.c`, `movenc.c`, `mjpegdec.c`) and OpenCV 4.12.0 `cap_ffmpeg_impl.hpp` again from raw.githubusercontent.com into `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jpeg_passthrough/verify_prov_src/`. All 8 are byte-identical (`cmp`) to the author's copies in `.../scratchpad/jpeg_passthrough/src/`. Then read the cited line ranges.
- Re-fetched the 3 web sources (matroska.org codec specs, mp4ra object types, webmproject container guidelines) with WebFetch.
- Read the PyAV 19.0.2 wheel's `av/container/output.py` (uv cache; 2 copies, same MD5), the `upstream/sfn26` Rust files (`git show`), freemocap at 5632778a, and skellycam `parse_video_filename.py`.
- Verifier functional checks (console output only, no result file):
  - `av.ffmpeg_version_info` is `8.1.2` for PyAV 18.0.0 (`.venv`, read-only) and `9.0.2` for PyAV 19.0.2 (`uv --with av==19.0.2`).
  - Recomputed the c930e frame 81→82 interval from the capture jsonl: 11,000 ns.

## Confirmed (evidence matches the draft)

| Draft claim | Evidence checked |
|---|---|
| 210 attempts, 194 written, 194/194 byte-exact; 16 not written = 14 WebM + c930e `avi\|vfr` + c930e `avi_tb_rate\|vfr` | `pyav19_recheck.json` `A_matrix` (recounted) |
| Frame counts per set (891/893/19/19/19/10/11 = 1,862) | `A_matrix` `bytes.n_in` |
| 1/1e6 VFR: max error 0 µs, strictly increasing, in MP4/MOV/NUT/fMP4 1 s/fMP4 per frame on all 7 sets | `A_matrix` `*_tb_us\|vfr` |
| 1/90000 VFR max error 5.556 µs; MKV 470 µs, c930e not strictly increasing; raw 6,031,976 µs; AVI 1/fps 14,671.667 µs | `A_matrix` |
| Overheads: MKV 40,253; MP4 11,232 / 11,936; fMP4 1 s 11,738; per frame 117,521; MOV 11,139; MOV 1/1e6 11,843; NUT 25,376; NUT 1/1e6 26,908; AVI 1/fps CFR 27,515 B | `A_matrix` `size_bytes` minus 49,314,521 |
| fMP4 1/1e6 ffprobe: 891 packets, `mp4v`, 0 µs | `B_fmp4_tb_us_ffprobe` |
| Kill table (597/597, moov not found ×2, 578/579 ×2, 596/597, 597/598 ×3) | `C_killed` |
| nodims EINVAL "dimensions not set" in all 6 formats; kf=False gives 30/30 flagged; template VFR file: MP4/MOV 29, AVI `2 >= 2`; template CFR in memory MP4/MOV 30/30 | `D_setup` |
| DHT-stripped decode 30/30, 30/30, 11/11 pixel-equal | `E_decode_dht_stripped` |
| OpenCV 4.12 on PyAV 19 fMP4 1/1e6: count 891, read 891, seek 10/10, POS_MSEC 0 µs, CAP_ANY→FFMPEG, MSMF 0 frames, FreeMoCap 891 | `pyav19_fmp4_tb_us_readers.json` |
| OpenCV 5.0.0 (FFMPEG) on c930e: MKV VFR 888 / 5 of 10; NUT VFR 887 / 6; NUT CFR 890 / 10; raw -192153584101141 / 0; AVI 1/600 CFR 17,820; AVI 1/fps CFR 891 / 10 | `version_bump.json` `rows[*].cv5_FFMPEG` |
| OpenCV 5.0.0 counts and seeks equal 4.12.0 on all 26 c930e rows | `version_bump.json` vs `mux_matrix.json` (recompared, all SAME) |
| PyAV 18 "Across all sets" rows (MP4/MOV/fMP4 7/7 + 70/70, MKV VFR 6/7 + 65/70, NUT 0/7, AVI default 0/7, raw 0/70, folder 7/7 + 70/70) | `mux_matrix.md` lines 14–50 |
| PyAV 18 kill / truncation / large-AVI numbers (MKV negative count, AVI 0, NUT 595, fMP4 582 vs 579, sidecar 409/600, 445 and 801–802 truncation survivors, 6000-frame OpenDML AVI) | `truncation.json` |
| Marker layouts, 4 standard DHTs, cv2/Pillow/djpeg stripped == original, djpeg "535 extraneous bytes" | `edge_cases.json` (djpeg `orig_ok` 0/11 and `eq` 11/11 on the generic camera) |
| mjpeg2jpeg +438 / +419 B | `edge_cases.json` `mjpeg2jpeg` |
| Electron versions, error codes, MIME results, image decodes (I422 / BGRX) | `electron_check.json` |
| Rotation: DCT equal 228/228, jpegtran 228/228, control 0/228, RGB diff ≤5, rot90/270 TJSAMP 4, legacy rc 0 on 195, generic -1 ×33, `tj3_warnings` 33 | `rotation.json` (recounted from `rows`) |
| FFmpeg n9.0.2 cites: `mux.c:820-821`, `matroskaenc.c:3602-3603` and `:3744-3747`, `matroska.c:86` and `:110-124`, `isom.c:55`, `avienc.c:745-762`, `movenc.c:177-179,204-208`, `mjpegdec.c:62,148` | Re-downloaded files; lines and quotes match |
| OpenCV 4.12.0 `cap_ffmpeg_impl.hpp:1980-1989` (`nb_frames`, else `floor(duration*fps+0.5)`), `:1991-1995` | Re-downloaded file |
| PyAV 19.0.2 `output.py:265-269,306-310` docstring and ValueError text | uv-cache wheel |
| mp4ra 0x6C "Visual ISO/IEC 10918-1"; webmproject "Video codec SHOULD be VP8 *or* VP9" | WebFetch 2026-11-09 |
| freemocap `video_group_helper.py:151,159,381-385`; skellycam `parse_video_filename.py:18` | `git show 5632778a:...`; working tree |
| Rust: recorder pipes MJPEG to ffmpeg libx264 (`recorder.rs:1-6,38-46,141-155`); `jpeg_transform.rs` `if ret == 0 && !dst_buf.is_null()` (line 108); "~1-2ms per frame" (line 4) | `git show upstream/sfn26:...` (re-read here; the draft said "not re-read") |
| Bench manifest ids and priorities; `bench/` and BENCH.md absent; the turbojpeg DLL is present | `results/bench_queue_from_wf_2e122ed0.json`; directory listings |

## Refuted

1. **"Add `fmp4_1s_tb_us` ... A one-line addition is needed" (§5).**
   - code: `scripts/jpeg_passthrough/bench_mux.py:82-87`. The bench worker reads the 4th `CONTAINERS` field but only acts on `"rate"` (`if stb == "rate": st.time_base = Fraction(1, 30)`). There is no `"us"` branch.
   - A `jp_io.CONTAINERS` entry `("mp4", ".mp4", FRAG1S, "us")` would therefore silently bench fMP4 at the muxer default 1/90000.
   - Fix: three changes are needed:
     - add the `jp_io.CONTAINERS` entry;
     - add `elif stb == "us": st.time_base = Fraction(1, 1_000_000)` after `bench_mux.py:86`;
     - add the name to `DEFAULT_CONTAINERS` (`bench_mux.py:36`) or pass `--containers`.
   - The same gap affects `mp4_tb_us`, `mov_tb_us` and `nut_tb_us` if someone benches them.
2. **"PyAV pts, ffprobe `pts_time` and OpenCV `CAP_PROP_POS_MSEC` give the same per-frame error in every container" (§2.3).**
   - measured, PyAV 18 - background: `mux_matrix.md` lines 38–39 and 49–50. Raw `.mjpeg` shows pyav/ffprobe 6,031,976 µs vs cv2 6,032,562 µs (VFR), and 5,946,667 vs 5,946,354 µs (CFR).
   - `version_bump.json` stores only the **maximum** error per reader (`max_abs_err_us`, `max_abs_err_vs_next_us`), not per-frame errors, and it has no ffprobe reader at all.
   - Correct wording: the maximum error agrees between PyAV and OpenCV 5 in every PyAV 19 container that was written (`version_bump.json`). In PyAV 18 files, PyAV, ffprobe and OpenCV 4.12 agree everywhere except raw `.mjpeg` and raw+sidecar (OpenCV off by ≤586 µs).
3. **"AVI cannot store VFR" / table 3.1 "VFR impossible", "n/a (VFR refused)".**
   - measured: `pyav19_recheck.json` `A_matrix`. `avi|vfr` (1/600) writes 6 of 7 sets with max error 830 µs, and `avi_tb_rate|vfr` writes 6 of 7 with 14,671.667 µs. Only c930e_720p_flash fails, because 2 frames fall into the same tick.
   - measured, PyAV 18 - background: `mux_matrix.md` lines 32 and 41 show the same (6/7 written).
   - Correct wording: AVI quantizes timestamps to its stream time base (gaps are filled with empty packets: `avienc.c:745-762`). It cannot keep real VFR times exactly, and it rejects the write when two frames land on the same tick (c930e: 11 µs apart).

## Weak (true in part, mis-cited, or overstated)

| Claim | Problem | Fix |
|---|---|---|
| "keep the real timestamps exactly ... on all 7 sets" (§2.3) | code: `jp_common.py:59-69` and `pyav19_recheck.py:152-160`. Only c930e_720p_flash and c922_720p_flash have real capture times. The 5 other sets reuse c930e's intervals (720p60 halves them). The timestamps are also cut to whole µs (`// 1000`) before muxing, so "exact" means exact to 1 µs | Say "real (2 sets) or borrowed real intervals (5 sets), exact to the µs the writer was given" |
| MKV "frames 81/82, which are 11 µs apart, get the same timestamp" cited to `pyav19_recheck.json` | That file records only `strictly_increasing: false`. The 11 µs comes from the capture jsonl (NOTES.md line 22, "printed during this study"). The verifier recomputed it: 11,000 ns at index 81. Which frames collide is from the PyAV 18 NOTES table (line 150) | Cite `research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_...frames.jsonl` via `jp_common.real_timestamps_ns`. Label the frame pair as PyAV 18 background or inferred |
| §2.4 table row "MP4, MOV, fMP4 (1/90000 and 1/1e6) — exact, 10/10" cited to `version_bump.json` (OpenCV 5) | `version_bump.json` has no fMP4 1/1e6 rows (`mp4_tb_us`, `mov_tb_us` and `nut_tb_us` only). fMP4 1/1e6 was read only by OpenCV 4.12 (`pyav19_fmp4_tb_us_readers.json`) | Split the row, or say "fMP4 1/90000 only; fMP4 1/1e6 see OpenCV 4.12 result" |
| FreeMoCap "4/4 reads ok" on PyAV 19 fMP4 1/1e6, used in Implication 2 as "exact ... seeks" | code: `fmp4_tb_us_cv2_check.py:45` calls `freemocap_read(p, None)`, so `match_cv2_sequential` is never checked (`jp_io.py:376`). "ok" means only "no exception". Frame identity was verified only for PyAV 18 fMP4 1/90000 (`mux_matrix.json`: 4/4 `match_cv2_sequential` true) | Say "4/4 reads without error (frame identity not checked)". Have Implication 2 cite OpenCV seek 10/10 for exact seeks |
| "1-3 B smaller than the PyAV 18 file writes" (§2.1, §6) | Recomputed over 166 matched rows: difference 0 B on 40 (all AVI and raw), 1 B on 112, 3 B on 14. Also, the PyAV 18 side is a file write and the PyAV 19 side is BytesIO, so writer version and target change together | "0–3 B; AVI and raw identical; cause NOT VERIFIED (version and file-vs-memory changed together)" |
| "PyAV 18.0.0 = FFmpeg 8.1.2 libs" (Labels) | No result file records it. `mux_matrix.json` meta gives only lib versions (libavformat 62.12.102). The verifier confirmed `av.ffmpeg_version_info == "8.1.2"` (console only) | Add `ffmpeg_version_info` to a result file's meta, or cite the lib versions only |
| Matroska quote "...compressed separately as a [@!JPEG] image." | The cited page (WebFetch 2026-11-09) reads "...compressed separately as a JPEG image." `[@!JPEG]` is RFC-markdown reference syntax from the spec source, not the cited URL | Quote the rendered text, or cite the source file the bracket syntax came from |
| "DHT-stripped frames stay byte-exact in MKV ... raw (30/30 each)" | code: `pyav19_recheck.py:320-331`. Only the first 30 c930e_720p_flash frames, CFR, in memory | Name the set and the mode |
| "`CAP_MSMF` ... reads MKV, MOV and AVI (1/fps)"; table 3.1 MKV "yes" | measured: `version_bump.json` `mkv\|vfr` `cv5_MSMF.frames_read` 888 of 891 (CFR 891) | "MKV: 888/891 on VFR" |
| `mjpeg2jpeg` "leaves Logitech frames with two sets of tables"; label "PyAV 18-era CLI run" | `edge_cases.json` `generic_1080p\|orig` `out_markers` also has 5 DHTs. The bsf ran through the ffmpeg CLI 9.0.2 (`edge_cases.py:125`, `jp_io.ffmpeg_extract`) on MKV written by PyAV 18 | "all cameras that carry DHT end up with two table sets". Label "measured, ffmpeg CLI 9.0.2 bsf on PyAV 18 MKV - background" |
| "Readable after hard kill" / "Complete byte-exact frames" table omits the PyAV 18 OpenCV/FreeMoCap row for fMP4 per frame | `truncation.json` `killed.fmp4_perframe`: OpenCV count 597, read 596, FreeMoCap 597 with 3/4 reads. That is relevant to table 3.2 (fragment choice) | Add the row to the §2.5 OpenCV/FreeMoCap table |
| "Folder .jpg + CSV — VFR timestamp error: exact in CSV (ns) [18]" (table 3.1) | code: `jp_io.py:154-160` writes `timestamps.csv`, but no script reads it back. No result file has a CSV timestamp check (only `sidecar_reader_ts_exact_ns` for raw+sidecar) | Mark "not tested (inferred: int64 written as text)" |
| PyAV seek results not reported | measured: `version_bump.json` `pyav19_seek_exact` is 5/10 for MP4/MOV/fMP4/MKV/AVI and 4/10 for NUT. The method is a keyframe seek to the frame pts plus a pts compare (`jp_io.py:236-248`). This is relevant to G9 scrubbing, yet the draft cites only OpenCV seeks | Report it with its method, or explicitly scope §2.4 to OpenCV seeks and list PyAV seek accuracy as open |

## Labels

- PyAV 18 results are labelled as background throughout. No PyAV 18 number is presented as the primary result, except where the citation mismatches listed above apply.
- The 3 inferred statements (Electron result carries to PyAV 19, MP4/MOV fine as a remux target, Rust's silent unrotated frames) are marked inferred.
- `mjpegadump` +44 B and the template-loss root cause are correctly marked NOT VERIFIED.
- No timing numbers appear. The Rust "~1-2 ms" is correctly marked NOT VERIFIED.

## Verdict

The draft is largely well sourced. Every number in the main tables traces to a result file and recomputes exactly, and every FFmpeg/OpenCV/PyAV/freemocap/Rust line citation and web quote checks out (one quote has stray reference syntax). Three statements must change before the draft becomes FINDINGS:

- the bench prep step ("one-line addition" is wrong: `bench_mux.py` ignores `"us"`);
- the "readers agree per-frame in every container" claim;
- the absolute "AVI cannot store VFR".

The rest needs scoping or citation fixes, mainly "real timestamps on all 7 sets", the fMP4 1/1e6 OpenCV 5 attribution, and unverified FreeMoCap frame identity on the leading candidate.
