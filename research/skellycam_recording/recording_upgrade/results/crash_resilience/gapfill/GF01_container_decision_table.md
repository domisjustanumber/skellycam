# GF01: cross-topic container evidence table (no choice made)

2026-11-10, gap-fill GF01 (doc fix). No tests and no timing were run; this file only collects evidence that already exists. It does **not** choose a container.

## 0. How to read this

**Citation shorthand.** `XX:n` = line n of that file (line numbers as of 2026-11-10, ~10:00):

| Code | File (relative to `research/skellycam_recording/recording_upgrade/`) |
|---|---|
| JP | `results/jpeg_passthrough/FINDINGS.md` |
| CR | `results/crash_resilience/FINDINGS.md` |
| CRs | `results/crash_resilience/summary.md` (PyAV 18 background tables) |
| WT | `results/write_throughput/FINDINGS.md` |
| WTg | `results/write_throughput/functional/functional_results_av19.0.2_gapfill.md` |
| WTe | `results/write_throughput/functional/verify_method_emptypkt_av19.0.2.json` |
| PI | `results/python_integration/FINDINGS.md` |
| PIb | `results/python_integration/bench/recwriter_quiet1_pyav19.json` |
| LIC | `results/licensing/FINDINGS.md` |
| IP | `results/intra_playback/FINDINGS.md` |
| CC | `results/chromium_codecs/FINDINGS.md` |
| HO | `HANDOFF.md` |

**Labels.** M = measured (the FINDINGS line cites the result file); S = source (primary source quoted in the cited FINDINGS line); C = code (file:line); I = inferred (minimal); bg = PyAV 18.0.0 background, not the implementation under test. `fp` = `flush_packets=1`.

**Empty cells.** GF02 is a concurrent functional gap-fill writing `results/crash_resilience/gapfill/GF02_*`. GF01 did not see GF02's task text, only its first output and scripts (09:49-09:50):
- C: GF02 Part A writes clean-closed `mkv_fp`, `mkv_fp_empty`, `fmp4pf_fp` and `fmp4_1s_fp` files, each with real and index PTS, on c930e, c922, gap60 and drop50. It checks PyAV byte-exactness and PyAV seek identity (`scripts/crash_resilience/gapfill/GF02/gf02_partA_write.py:5-17`; `gf02_common.py:40-45`).
- C: its reader runs OpenCV 4.12 count, POS_FRAMES seeks and FreeMoCap's VideoHelper on those files (`gf02_cv2_reader.py:1-13`).
- `gap: GF02` = no evidence yet; the cell is inside that confirmed scope.
- `gap: GF02?` = no evidence yet; a functional test could fill it, but GF01 could not confirm it is in GF02's scope. If GF02 does not report it, read it as NOT VERIFIED.
- Cells that need a timed run are marked NOT VERIFIED (timed).

**Kill tests differ between topics, so loss counts are not directly comparable:**
- CR: 150 frames, killed after the encoder drained (`drained`), plus a live 30 fps kill after 75 frames (`rt`) (CR:48-52, CR:74).
- WT: one camera, 720p60 paced, TerminateProcess at about frames 300-372, 2 kills per variant (PyAV 19) (WT:87-89, WT:93).
- JP: 600 frames, `os._exit(1)` with no close, 1 kill, no fp on any container (JP:284).
- PI: recwriter (no fp), killed once at ≥300 sidecar records (PI:131, PI:146).

## 1. The table

Same rows in both parts. Row R4 has two variants: R4a without fp, R4b with fp.

### 1a. Crash behaviour, OpenCV counting/seeking, timestamps

| Row | Kill loss, PyAV 19 | Kill loss, PyAV 18 (bg) | Torn sample handed to readers | cv2 4.12 FRAME_COUNT, real VFR PTS | cv2 count, index (CFR) PTS | cv2 POS_FRAMES seek with drops | Timestamp resolution |
|---|---|---|---|---|---|---|---|
| **R1 MKV + fp** | M: 1 frame: 149/150 drained (CR:57); 74/75 live (CR:78); WT mkv_flush 1, 1 (WT:95). M: intra NVENC H.264/HEVC live kill loses 3 = 2 encoder + 1 Cluster (CR:79-80, CR:167). Without fp: WT 3, 4 (WT:95); JP 597/600 (JP:288) | M bg: 149/150 drained, 74/75 rt (CRs:10); WT mkv_flush 1 in each of 5 kills (WT:112) | M: no. Prefix cuts 0/12 (CR:140); 0 cut packets after kills (WT:401); killed recwriter MKV returns only whole packets (PI:135, PI:143) | M, finalized: wrong with drops or off-nominal mean rate: gap60 888 for 831, drop50 888 for 874, c930e 888 for 891, 30-min 53,819 for 54,000; exact on c922 893/893 (JP:223, JP:225, JP:233-234, JP:412; PI:113). These files had no fp; I: fp does not change pts. M, killed: −2.767e17 (CR:117; PI:135) | M: right on 7/7 sets, which have no drops (PI:110); 18,000/18,000 with ideal 33.333 ms PTS (PI:274, PI:283; PIb `c_open_cost.mkv.cv2_frame_count_prop`). Both recwriter, no fp. With drops: gap: GF02 (I: an index timeline has no gaps by construction). M, killed: still −2.767e17 until `recover()` (PI:136, PI:169) | M, real PTS: 5/10 gap60, 5/10 drop50 (JP:223); 67 ms gap moved seek 119 → 117 (PI:121). M, CFR without drops: all 11 seeks exact (PI:120). Index PTS with drops: gap: GF02. M, unfinalized: silently returns frame 0 (CR:118-119). M, PyAV seek by sidecar pts: 35/36, 33/34, 34/35 (JP:259) | S: fixed 1/1000 (matroskaenc.c:3602-3603, JP:180; WT:152-153). M: error ≤470 µs (JP:175), ≤498.9 µs (WT:63); frames <1 ms apart share a pts (JP:176-177). I: under index PTS, real time is in the int64 ns sidecar (PI:405-408), so the grid no longer carries timing |
| **R2 MKV + fp + empty timestamped packet** | M: 0, 0, 0 in 3 kills (acked 332, 340, 367; byte-exact = acked) (WT:98-99; WTe `C_kills_mkv_flush_emptypkt_ts`) | not run (PyAV 18 is background only) | M: 0 partial units in the 3 kills (WT:99). Prefix cut: gap: GF02? | gap: GF02. M: ffprobe hides the size-0 blocks (WT:134-135); their effect on cv2 duration × fps is untested | gap: GF02 | gap: GF02 | M: 1/1000, same muxer (WT:402); C: empty packet pts = frame pts + 1 µs (WT:133). I: stored on the same 1 ms grid |
| **R3 fMP4 per-frame fragments + fp** | M: 1 frame: 149/150 drained (CR:61); WT fmp4_frame_flush 1, 1 (WT:96). Without fp: WT 5, 5 (WT:96); JP 596/600 (JP:293); CR 147 counted, 146 exact (CR:60). Intra NVENC: not tested (CR:501) | M bg: 149/150 drained, 74/75 rt (CRs:20); WT 1, 1, 1, 1, 0 (WT:112) | M: after a kill with fp, 0 cut packets (WT:403). M: **yes** after a prefix cut, 12/12 (CR:141). M: yes after a kill without fp (CR:70; JP:293; PI:137) | M, finalized: exact on 7/7 (PI:112), gap60 831, drop50 874 (JP:221-222), 54,000 (JP:412). M, killed: 149 correct with fp (CR:117); without fp 597 for 596 (JP:293) and 298 including the torn frame (PI:137) | M: 18,000/18,000 with ideal PTS (PI:283-284; PIb `c_open_cost.mp4f.cv2_frame_count_prop`; recwriter, no fp). Index test on the camera sets not run (PI:359): gap: GF02. With drops: gap: GF02 | M, real PTS: 5/10 gap60, 7/10 drop50 (JP:221-222); 4 seeks off by one after a 67 ms gap (PI:122). M, unfinalized: lands on the right frame (CR:120). Index PTS with drops: gap: GF02. M, PyAV seek by sidecar pts: 36/36, 34/34, 35/35 (JP:258) | M: 1/1e6 keeps µs inputs exactly (0 µs) (JP:170). M: at 1/90000, 6.434 µs (WT:64) |
| **R4a fMP4 1 s fragments, no fp** | M: WT fmp4_1s 33, 62 (WT:96); JP 578 complete of 600 at 1/1e6 (JP:292), i.e. 22 lost (computed) | M bg: 119/150 drained (118 byte-exact), 57/75 rt (CRs:21); WT 19-59 over 5 kills (WT:112) | M: **yes**. WT 1 cut packet per kill, decoded silently (WT:100-101, WT:404); JP 579 packets, 578 complete, OpenCV returns 579 (JP:292, JP:303) | M, finalized at 1/1e6: c930e 891, c922 893 exact (JP:226); gap60 831, drop50 874 (JP:221-222); 54,000 (JP:412). M, killed: 582 for 579 (JP:292) | gap: GF02 (GF02 writes this with fp; I: fp does not change pts) | M, real PTS: 5/10 gap60, 7/10 drop50 (JP:221-222). Unfinalized: not tested on PyAV 19 (CR:409): gap: GF02?. Index PTS with drops: gap: GF02 (with fp, as before) | M: 0 µs at 1/1e6 (JP:170); 6.434 µs at 1/90000 (WT:64) |
| **R4b fMP4 1 s fragments + fp** | M: WT fmp4_1s_flush 46, 5 (WT:96; WTg:26). CR: no PyAV 19 kill (CR:409) | M bg: 120/150 drained (120 byte-exact), 60/75 rt (CRs:22) | M: 0 partial units in 2 kills (WTg:26). CR §3A says yes (bg) (CR:409). Prefix cut on PyAV 19: gap: GF02? | Finalized: gap: GF02 (I: = R4a, since fp does not change pts). Killed: gap: GF02? | gap: GF02 | Finalized: gap: GF02. Unfinalized: gap: GF02? | M: 6.434 µs at 1/90000 (WTg:10). I: 0 µs at 1/1e6, as R4a |
| **R5 append / raw file + CRC index sidecar** | M: WT append 0, 0 (WT:94). C: Python file I/O with `buffering=0`, no PyAV, so PyAV-version independent (WT:77, WT:117) | M bg: WT append 0 ×5, append_fsync1s 0 (WT:112); CR rawidx 0 (CR:414). M bg: a buffered Python raw+sidecar writer kept only 409/600 (JP:309) | M: 0 cut packets in WT kills (WT:399). bg: own CRC parser no, ffprobe yes (CR:414). I: a plain MJPEG demux hands out the torn frame unless the index is used (CR:393) | M: raw `.mjpeg` gives a garbage count, −192,153,584,101,141 in OpenCV 5 (JP:248), −1.92e14 bg (CR:414); FreeMoCap rejects raw `.mjpeg` (JP:280). M: the index held a record for every acked frame (WT:113) | n/a (no container PTS); count comes from the index | M: cv2 0/10 on raw `.mjpeg` (JP:248; bg JP:278). M: index lookup, 1000 random reads, 0 wrong (WT:350) | M bg: int64 ns in the index, exact 7/7 (JP:196); M: sidecar int64 ns (WT:399) |
| **R6 plain MP4 (ruled out; reference)** | M: all frames: 0/150 (CR:63); "moov atom not found" (JP:289); 0/17,618 at 1 GB (CR:386) | M bg: 0/150 (CRs:23-24) | n/a (file unreadable) | M, finalized: exact, count stored in the file (JP:231; JP:221-222; JP:412) | I: exact (count is stored, not estimated; JP:229-231) | M, real PTS: 5/10 gap60, 7/10 drop50 (JP:221-222) | M: 0 µs at 1/1e6 (JP:170) |

### 1b. Open, repair, Chromium, write cost, licence

| Row | Warm open + count, 30-min file (OPEN, quiet run 20261109T230007) | Repair s/GB (CR-REPAIR, quiet run) | Chromium `<video>`, intra H.264/HEVC | Chromium JPEG path (ImageDecoder / createImageBitmap + byte-range index) | Write overhead (existing measured values only) | Patent / licence (container) |
|---|---|---|---|---|---|---|
| **R1 MKV + fp** | M: cv2 0.19 ms, PyAV 0.17 ms; cv2 count wrong, 53,819 (JP:411-412). Written without fp. M: 10-min, cv2 open + count + first read 3.68 ms (PI:283) | M: 0.907 (PyAV remux), 0.965 (prototype); 17,617/17,618 frames (CR:383-384) | M: MKV clips play and seek exactly, 4800/4800 per browser across mp4/fMP4/mkv (IP:30-31; CC:68-73). M: E35 `canPlayType` "" but plays (IP:76-79). M bg: MSE rejects Matroska (CC:152). M: HEVC decodes only in hardware (CC:299). M bg: killed GOP H.264 mkv+fp plays to `ended`, duration Infinity (CR:200) | M: JPEG-in-MKV + offset index exact on seeks and steps (IP:35-37; CC:191). M: camera bytes fetched from MKV byte-identical, 450 per browser, one 720p clip (IP:72-73). M: index must store `packet.pos` + 4 (IP:74) | M (CR-FRAG, quiet run, 1 unpaced writer, 3000 frames 720p): 24.9 µs/frame MJPEG, 22.4 H.264 intra, 17.9 HEVC intra; 45.75 B/frame (CR:334); fp adds 4.9 / 2.7 / 3.0 µs (CR:353). M (WT focus16, quiet run): 16 × 1080p60 write p50 0.808 ms, p99.9 2.85 ms (WT:416) | M: 0 IETF IPR disclosures for RFC 9559 and its draft (LIC:53); evidence only about IETF disclosures (LIC:188) |
| **R2 MKV + fp + empty timestamped packet** | NOT VERIFIED (timed) | NOT VERIFIED (timed) | gap: GF02?. M: the file holds size-0 SimpleBlocks (WT:134); non-FFmpeg parsers untested (WT:21) | gap: GF02? | NOT MEASURED (WT:451-454); NOT VERIFIED (timed). I: relies on undocumented muxer behaviour (WT:138) | as R1 (LIC:53) |
| **R3 fMP4 per-frame fragments + fp** | M: cv2 1107.28 ms, PyAV 1224.24 ms; count 54,000 exact (JP:408, JP:412). Written without fp. M: 10-min, 371.96 ms (PI:284) | M: 1.345; 17,617/17,618 (CR:385) | M: fMP4 clips play and seek exactly (IP:30-31; CC:68-73). C: those clips used `frag_keyframe` = one fragment per intra frame, 1/90000 (`scripts/intra_playback/gen_intra_clips.py:17`, `:74`). M bg: MSE accepts fMP4 (CC:319). M bg: killed GOP H.264 fmp4_every+fp plays to `ended`, finite duration (CR:202); a torn cut gives MediaError in E35, plays in E45 (CR:204) | NOT VERIFIED (only `.mjpeg` and MKV tested: IP:35; CC:191) | M (CR-FRAG): 23.5 / 21.5 / 17.0 µs/frame; 131.27 B/frame (CR:339). M (WT focus16): p50 0.853 ms, p99.9 3.18 ms (WT:417). M (JP MUX-D, no fp, 1/1e6): 20.41 µs/frame 720p, 56.26 1080p (JP:505) | NOT VERIFIED: ISO BMFF patent declarations (LIC:55) |
| **R4a fMP4 1 s fragments, no fp** | M: cv2 42.57 ms, PyAV 45.69 ms; count 54,000 exact (JP:409, JP:412) | not run (CR:409); NOT VERIFIED (timed) | NOT VERIFIED: no 1 s-fragment intra clip was made (C: `gen_intra_clips.py:74` sets only `frag_keyframe`) | NOT VERIFIED | M (JP MUX-D, quiet run, single stream, 1/1e6): 20.78 µs/frame 720p, 60.24 1080p; 12.4 B/frame (JP:504). M: close 1.54 ms at 1080p (JP:392) | NOT VERIFIED (LIC:55) |
| **R4b fMP4 1 s fragments + fp** | I: as R4a (fp does not change the file layout); not measured | not run (CR:409); NOT VERIFIED (timed) | NOT VERIFIED (as R4a) | NOT VERIFIED | M (CR-FRAG `fmp4_frag_1000+fp`): 19.7 / 20.4 / 15.8 µs/frame; 12.50 B/frame (CR:345) | NOT VERIFIED (LIC:55) |
| **R5 append / raw file + CRC index sidecar** | Not measured at 30 min. M: 10-min (18,000 frames) frame table from the index 0.016 s, against demux 0.233 s (mkv_flush) and 0.638 s (fmp4_frame_flush) (WT:357-359, WT:365) | M: 1.441, all 17,618 frames of a quiescent kill (CR:387). C: this demuxes with PyAV `format='mjpeg'` and does not use the CRC index (CR:389) | n/a: no container; intra H.264/HEVC in this layout not tested (NOT VERIFIED) | M: `.mjpeg` + index exact: 800/800 seeks, 976/976 steps per decode path per browser (IP:35-37) | M (CR-FRAG `rawidx`, 2 flushes/frame): 34.9 µs/frame; 32.0 B/frame index (CR:350). M (JP MUX-D `raw_sidecar`): 19.97 µs/frame 720p, 42.98 1080p (JP:510). M (WT focus16): append p50 0.553 ms, p99.9 1.72 ms (WT:415) | no container spec. S: the JPEG baseline process has no listed patents (LIC:33); M: corpus is SOF0 baseline Huffman (LIC:120). I: the sidecar is skellycam's own format |
| **R6 plain MP4 (ruled out; reference)** | M: cv2 2.38 ms, PyAV 2.95 ms; the only container with PyAV `stream.frames` set (JP:411, JP:413) | M: unrepairable, 0 frames, `InvalidDataError` (CR:386) | M: mp4 +faststart clips play and seek exactly (IP:30-31). M bg: killed plain MP4 cannot open (CR:210) | NOT VERIFIED | M (CR-FRAG): 17.6 / 18.1 / 14.0 µs/frame; 9.84-10.17 B/frame (CR:340). M (JP MUX-D): 17.87 µs/frame 720p, 51.22 1080p (JP:501) | NOT VERIFIED (LIC:55) |

**Run notes for the write-overhead column.**
- CR-FRAG = items CR-FRAG-MJPEG-PYAV19 (00:52) and CR-FRAG-INTRA-PYAV19 (04:35) of run `20261109T230007`. Wall times compare within a payload only. The intra timer includes a template open (CR:318, CR:329).
- JP MUX-D = item JP-MUX-PYAV19 (order 17), same run, single stream, no fp (JP:44, JP:367).
- WT focus16 = `results/write_throughput/bench/focus16_av19/`, same run, 16 × 1080p60, 3 reps (WT:410, WT:420).
- All of these are single machine (Gerald, P-cores only, one NVMe, Defender on) (CR:476-482; WT:23).

## 2. Conflicts

### 2.1 What each topic recommends (exact quotes)

| Topic | Line | Exact text | Evidence it relies on |
|---|---|---|---|
| JP §4 item 2 | JP:531 | "**The leading container candidate is fMP4 with `st.time_base = Fraction(1, 1_000_000)` and 1 s fragments**" | byte-exact; 0 µs timestamps (JP:170); exact cv2 count with drops and at 54,000 frames (JP:221-222, JP:412); 43-46 ms warm open (JP:409); readable after **one** kill without fp, 578/600 (JP:292) |
| JP §4 item 2 | JP:540 | "**fMP4 with per-frame fragments meets every point except warm open time.**" | open 1107.28 ms vs 42.57 ms (JP:408-409) |
| JP §4 item 8 | JP:565-569 | "**Rule out these containers for FreeMoCap-compatible recordings:**" / "MKV, for three reasons" / "its 1 ms grid merges frames less than 1 ms apart;" / "its OpenCV count is wrong whenever frames are dropped (gap60, drop50) or the mean rate is off nominal" / "it opens fastest, but the count it gives FreeMoCap cannot be trusted." | cv2 count with **real VFR PTS** (JP:223, JP:233, JP:412); 1 ms grid (JP:175-177) |
| CR §4.1 | CR:432 | "**Recording container for G1 (MJPEG passthrough): Matroska with `flush_packets=1`.**" | 1-frame kill loss (CR:57); no torn frame after cuts (CR:140); exact PyAV seek unfinalized (CR:109); fastest repair 0.907 s/GB (CR:383) |
| CR §4.3 | CR:440 | "**For intra-only H.264/HEVC (G6/G7 hardware path), use MKV+fp with no cluster options.**" | intra NVENC live kill: 3 lost (CR:167); cl0 byte-identical (CR:356) |
| CR §4.7 | CR:449 | "**Finalize before any OpenCV reader, and check PyAV seeks on unfinalized files.**" | unfinalized MKV count −2.767e17 and seek to frame 0 (CR:117-119) |
| CR §4.11 | CR:466 | "**Prefer MKV over per-frame fMP4 for crash safety.**" | fMP4 torn sample after cut (CR:141); slow long open (CR:468); +48 % repair (CR:391) |
| CR §3A | CR:409 | fMP4 1 s row: "bg only (1 s lost)" and "not tested (P19)" | no PyAV 19 data in CR for 1 s fragments |
| WT §4.4 | WT:480 | "**For a standard single file, prefer mkv_flush over fmp4_frame_flush on after-recording cost; they tie on crash loss.**" | open 0.006 vs 0.412 s; 1000 random reads 0.027 vs 0.425 s (WT:482); 1, 1 lost each (WT:481) |
| WT §4.4 | WT:484 | "MKV plus an explicit-ts empty packet per frame was the only variant with 0 loss in every kill" | 3 kills (WT:98) |
| WT §4.8 | WT:496 | "**Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid gives 0 frames after truncating a closed file (2.6), and 1 s fragments lost up to 62 frames per kill (2.2)." | fmp4_1s 33, 62; fmp4_1s_flush 46, 5 (WT:96) |
| WT §4.3 | WT:477 | "**The append + sidecar index layout remains the reference for crash tolerance (G2) and indexing.**" | 0 lost (WT:94); index read 0.016 s (WT:478) |
| PI §4.2 | PI:405 | "**Write CFR (index) PTS to the file and keep the exact ns timestamps in the sidecar.**" | MKV index count 7/7 (PI:110); real-PTS failures (PI:113-114, PI:121-122) |
| PI §4.3 | PI:409 | "**Container for G2: against per-frame-fragment fMP4, MKV wins on open cost; against 1 s-fragment fMP4 the choice rests on crash behaviour.**" | open cost (PI:283-284); notes HO:173 (PI:412) |
| LIC §4 | LIC:174 | "Container: Matroska has 0 IETF IPR disclosures (2.2). ISO BMFF status is NOT VERIFIED. [inferred] For licensing, Matroska/WebM is the better-documented choice; MP4 is not ruled out, only unverified." | LIC:53, LIC:55 |

### 2.2 Where the evidence disagrees

1. **fMP4 1 s fragments: kill loss.**
   - JP measured 22 frames lost at one kill without fp (JP:292, computed) and calls it the leading candidate (JP:531).
   - WT measured 33 and 62 frames lost without fp, and 46 and 5 with fp, over 2 kills each (WT:96; WTg:26), and says avoid (WT:496).
   - CR has only PyAV 18 data for this row (CR:409; CRs:21-22: 30-31 of 150 lost drained).
   - I: the loss scales with the open fragment (up to about 1 s of frames), so WT's 60 fps test loses more frames per kill than a 30 fps recording would.
2. **The PTS policy changes the MKV argument.**
   - JP excludes MKV because cv2's count is wrong with **real VFR PTS** (JP:568: gap60 888 for 831, drop50 888 for 874, c930e 888 for 891, 53,819 for 54,000).
   - PI F3 measured a correct MKV count with **index (CFR) PTS** on 7/7 sets (PI:110). Those sets have no dropped frames: 891 frames grabbed on c930e (PI:116), and the corpus is the camera's own captures (JP:56).
   - M: PI also counted 18,000/18,000 on a 10-minute MKV with ideal 33.333 ms PTS (PI:274, PI:283).
   - PI recommends index PTS plus ns timestamps in the sidecar (PI:405-408). WT recommends exact timestamps in the sidecar too (WT:485-487).
   - I: under index PTS the 1 ms grid reason (JP:567) also stops mattering, because the container pts no longer carry capture time.
   - Still open under index PTS: no test has dropped frames (gap: GF02); a killed MKV still reports −2.767e17 until `recover()` (PI:136, PI:169; CR:117); fMP4 1 s with index PTS is untested (gap: GF02).
   - I: index PTS also makes a `<video>` file's clock CFR, so the CFR seek rule would apply to it (IP:39-40, CFR 2400/2400), while real time comes from the sidecar. Not tested with index-PTS files.
3. **Torn samples.**
   - CR rejects fMP4 because a prefix cut hands the decoder a torn sample (12/12, CR:141).
   - WT and JP accept a container that can hand out a torn frame, provided the reader checks the sidecar CRC or EOI (WT:497; JP:562).
   - M: after a kill with fp, fMP4 per-frame and 1 s fragments gave 0 cut packets in WT (WT:403; WTg:26). The torn case is the power-cut (prefix) case and the no-fp case.
4. **Open cost.** Per-frame fMP4 opens 26× slower than 1 s fMP4 (JP:410) and about 5,800× slower than MKV (PI:294) at 30 minutes, warm. Nobody disputes the numbers; they weigh against per-frame fragments only.
5. **Repair.** MKV+fp 0.907 s/GB, per-frame fMP4 1.345 s/GB (CR:383-385). 1 s fragments were not repaired (CR:409).
6. **Chromium.** Intra H.264/HEVC plays and seeks exactly in MKV, per-frame fMP4 and MP4 (IP:30-31). MSE needs fMP4 or WebM (CC:319, bg). 1 s-fragment fMP4 and the JPEG path out of fMP4 are untested. Chromium does not separate MKV from per-frame fMP4 for `<video src>`.
7. **Licence.** Matroska has 0 IETF disclosures (LIC:53); ISO BMFF is NOT VERIFIED (LIC:55).
8. **Write cost does not separate them.** Single-writer wall time differs by at most a few µs/frame (CR:334-345; JP:500-510), and 16 × 1080p60 p50 is 0.808 vs 0.853 ms (WT:416-417). The empty-packet variant's cost is unmeasured (WT:451-454).

### 2.3 What PLAN.md still needs (no choice made here)

- A PTS policy decision (real VFR vs index CFR + sidecar), because it decides whether JP's MKV exclusion holds (2.2 item 2).
- For fMP4 1 s: a PyAV 19 kill and prefix-cut result in CR's harness (gap: GF02?), a repair time (timed) and a Chromium intra check (NOT VERIFIED).
- For MKV + empty packet (WT:484 lists what is needed):
  - clean-close byte-exactness and cv2 counting: gap: GF02 (Part A);
  - more kills, a prefix cut and Chromium: gap: GF02?;
  - a write cost: NOT VERIFIED (timed).
- For index PTS: cv2 count and POS_FRAMES seek on files with dropped frames, MKV and fMP4 (gap: GF02).

## 3. Proposed cross-reference text (for the main session to paste; GF01 edits no FINDINGS)

- **JP §4 item 2 (JP:531).**
  - Old: "2. **The leading container candidate is fMP4 with `st.time_base = Fraction(1, 1_000_000)` and 1 s fragments** (`movflags frag_keyframe+empty_moov+default_base_moof`, `min_frag_duration 1000000`). In the tests it is all of the following (§2.3-§2.5, §2.9, table 3.2):"
  - New: "2. **fMP4 with `st.time_base = Fraction(1, 1_000_000)` and 1 s fragments is a container candidate** (`movflags frag_keyframe+empty_moov+default_base_moof`, `min_frag_duration 1000000`). Other topics disagree: write_throughput lost 33 and 62 acked frames per kill with 1 s fragments (46 and 5 with `flush_packets=1`; `results/write_throughput/FINDINGS.md:96`), against 22 at this topic's one kill (§2.5). The cross-topic evidence is in `results/crash_resilience/gapfill/GF01_container_decision_table.md`. In the tests it is all of the following (§2.3-§2.5, §2.9, table 3.2):"
- **JP §4 item 8 (JP:565-571).**
  - Old: "8. **Rule out these containers for FreeMoCap-compatible recordings:**" … "- MKV, for three reasons (§2.3, §2.4, §2.9.3):"
  - New: "8. **Rule out these containers for FreeMoCap-compatible recordings written with real VFR PTS:**" … "- MKV, for three reasons, all under real VFR PTS (§2.3, §2.4, §2.9.3). With index (CFR) PTS and exact times in a sidecar, as python_integration recommends (`results/python_integration/FINDINGS.md:405`), cv2 counted MKV correctly on 7/7 sets without drops and on an 18,000-frame file (`results/python_integration/FINDINGS.md:110`, `:283`), and the 1 ms grid no longer carries timing (inferred). Index PTS with dropped frames is untested. See GF01 §2.2."
- **CR §4.1 (CR:432).**
  - Old: "1. **Recording container for G1 (MJPEG passthrough): Matroska with `flush_packets=1`.**"
  - New: "1. **For crash safety, Matroska with `flush_packets=1` is this topic's preference for G1 (MJPEG passthrough).** jpeg_passthrough rules MKV out for FreeMoCap under real VFR PTS (`results/jpeg_passthrough/FINDINGS.md:565-569`); that depends on the PTS policy. The cross-topic choice is open: `results/crash_resilience/gapfill/GF01_container_decision_table.md`."
- **WT §4.4 (WT:480).**
  - Old: "4. **For a standard single file, prefer mkv_flush over fmp4_frame_flush on after-recording cost; they tie on crash loss.**"
  - New: "4. **For a standard single file, prefer mkv_flush over fmp4_frame_flush on after-recording cost; they tie on crash loss.** This compares two layouts only; the cross-topic table, including fMP4 1 s fragments and the PTS policy, is `results/crash_resilience/gapfill/GF01_container_decision_table.md`."
- **WT §4.8 (WT:496).**
  - Old: "8. **Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid gives 0 frames after truncating a closed file (2.6), and 1 s fragments lost up to 62 frames per kill (2.2)."
  - New: "8. **Avoid `hybrid_fragmented` and 1 s fragments for recording.** hybrid gives 0 frames after truncating a closed file (2.6), and 1 s fragments lost 33 and 62 frames per kill without `flush_packets=1` and 46 and 5 with it (2.2; 720p60). This conflicts with jpeg_passthrough §4 item 2 (`results/jpeg_passthrough/FINDINGS.md:531`), which names 1 s fMP4 the leading candidate; see GF01."
- **PI §4.2 (PI:405).**
  - Old: "2. **Write CFR (index) PTS to the file and keep the exact ns timestamps in the sidecar.**"
  - New: "2. **Write CFR (index) PTS to the file and keep the exact ns timestamps in the sidecar.** This policy removes jpeg_passthrough's MKV-count reason for ruling out MKV (`results/jpeg_passthrough/FINDINGS.md:568`), which was measured with real VFR PTS. Not yet tested: index PTS with dropped frames, and fMP4 1 s fragments with index PTS. See `results/crash_resilience/gapfill/GF01_container_decision_table.md`."

## 4. HANDOFF note (HANDOFF not edited)

- HO:173 says: "fMP4 with a 1/1e6 time base is the leading container."
- That headline is **contested**:
  - CR:432 recommends MKV + fp;
  - WT:496 says avoid 1 s fragments (33, 62 lost per kill, WT:96);
  - WT:480 prefers MKV over per-frame fMP4;
  - PI:412 already flags HO:173;
  - PI:405 plus PI:110 remove JP's MKV-count reason under index PTS.
- I: the headline should read as "contested; see GF01" until PLAN.md decides. GF01 does not edit HANDOFF.md.
