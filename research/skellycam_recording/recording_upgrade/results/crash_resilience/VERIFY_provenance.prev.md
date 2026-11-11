# crash_resilience: provenance check of the draft FINDINGS

Verifier: adversarial provenance pass, 2026-11-09. No timed runs were made. Checks were: re-opening every cited result file and recomputing the numbers from the raw JSON; re-fetching the cited FFmpeg n9.0.2 and SVT-AV1 v4.2.0 sources (raw.githubusercontent.com / gitlab.com raw, accessed 2026-11-09) and comparing line numbers and quotes; and `git show upstream/sfn26` (765bf82d) for the Rust citations. The fetched sources are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/crash_resilience/verify_src/`.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless stated otherwise.

## Verdict

Most of the draft holds up. Every source citation (file:line and quote) matches n9.0.2 / v4.2.0 / 765bf82d exactly. Most numbers match their JSON. Two counts are wrong, one claim about PyAV seeking is contradicted by the draft's own data, and several statements are unlabelled or inferred but presented as measured. The fixes are listed below.

## Refuted (the evidence says something different)

| # | draft claim | evidence | correction |
|---|---|---|---|
| R1 | §2.3 "`ffmpeg -c copy` ... kept the frame count of every readable kill image (21/21)" | `pyav19_recheck.json` → `kill[]`: 19 entries have `ffmpeg_copy_mkv`, and all 19 match. There are 20 readable images; `seg_mkv+fp` was not repaired. | Say **19/19** (seg_mkv+fp not repaired). |
| R2 | §2.3 "`add_stream_from_template(ist)` default **fails for every AV1 file (5/5)**" | `pyav19_recheck.json`: `pyav_remux_template_default` has the error on 4 AV1 entries (mkv+fp, mkv_cl0+fp, webm_cl0+fp, fmp4_every+fp). For AV1 mkv (0 B) and mp4+fp it is `null`, because those files are unreadable. | Say **4/4 readable AV1 files**. |
| R3 | §2.2 the PyAV mid-file seek "passed", and "cv2 seek worked ... true only for ffprobe and PyAV" | `pyav19_recheck.json` → `mjpeg avi+fp`: `seek {ok: true, target_pts: 75, got_pts: 0, exact: false}`. MJPEG is intra-only, so an exact landing is expected (code `scripts/crash_resilience/common_cr.py:239-249`: `ok` only means "at or before target"). PyAV therefore also lands silently on frame 0 for unfinalized AVI. MJPEG nut / nut+fp are also `exact: false` (target 153600, got 151572). ffprobe ran no seek test at all. NOTES §4.1 (line 225) also records PyAV seek failures on H.264 AVI (background). | Replace "passed" with: PyAV seek was exact on MJPEG MKV and fMP4, landed on the preceding keyframe for H.264/AV1, landed **2 frames early on NUT**, and returned **frame 0 on AVI**. Drop "ffprobe" from the seek sentence. Add "AVI unusable for seeking by PyAV *and* OpenCV when unfinalized" to §3A and implication 6. |
| R4 | §2.4 background "naive PyAV loop up to **5** frames short for AV1 in fMP4, NUT, AVI and IVF" | `truncation_b.json` → av1 `fmp4_kf+fp` `agg.pyav_max_short` = **6**. The other five variants are 5. | "up to 6 frames short" (bg). |

## Weak (needs a label, a citation fix or a narrower wording)

| # | draft claim | problem | fix |
|---|---|---|---|
| W1 | Versions: "The ffprobe 9.0.2 CLI was used only to read and inspect files" | True of ffprobe, but the **ffmpeg 9.0.2 CLI wrote files**: every `ffmpeg_copy_mkv` repair (`common_cr.py:280-290`), the repaired files that OpenCV read in `cv2_*_pyav19_files.json`, and every output in the sfn26 stand-in (`sfn26_pipe*.md`). The study rule allows the CLI only to inspect. | State this openly. Make the PyAV 19 `opaque=True` remux (same counts in all 19 cases, `pyav19_recheck.json`) the primary repair evidence, and label the ffmpeg-CLI repair and sfn26 results "ffmpeg 9.0.2 CLI, not the implementation under test". For OpenCV-after-repair, note that the repaired files were written by the CLI. |
| W2 | §2.3 "PyAV 18 showed the same failure (background, `pyav_remux_opaque_check.json`)" | That file shows only `opaque=True` successes. It contains no default-argument failure. The failure is recorded in `kill_matrix_b.json` → `repair.pyav_copy` (NOTES.md:260-262). | Change the citation to `kill_matrix_b.json` → `repair.pyav_copy`. |
| W3 | §2.10 / §3B / impl. 12: "probing holds the first ~5 MB"; table B "ffmpeg-CLI probing ... first ~5 MB, measured" | Only the 0-byte outcome is measured. The cause is inferred, and there is a second candidate. `analyzeduration` defaults to 0 (`options_table.h:56`), which becomes `5*AV_TIME_BASE` (`demux.c:2638-2641`, n9.0.2), i.e. 5 s. 75 frames at `-r 30` = 2.5 s, which is also inside that window. The probesize (5 MB) and analyzeduration (5 s) explanations both fit both runs. | Label it **inferred**. Write "probing (probesize 5 MB or analyzeduration 5 s, not separated)". In table B, change the evidence column to "measured 0 B; cause inferred". |
| W4 | Implication 3: "Only with both is the loss 1 frame, not up to a GOP plus 39 frames" | Low-delay encoding together with cl0/frag_every_frame was **never run in a kill test**. The kill matrix used drained encoders, and `encoder_hold_check` counted packets without muxing or killing anything. The "1 frame" figure combines two separate measurements. | Label it **inferred**. Add a functional PyAV 19 kill of SVT `pred-struct=1` / NVENC `delay=0` into mkv_cl0+fp, killed mid-stream without a drain. |
| W5 | Input "about 57 KB/frame" (§2.1, §6) | It has no citation. The measured mean of the 150 frames used is **55.4 KB**: the clean folder is 8317014 B / 150 (`kill_matrix_a.json`, mode `clean`, container `folder`; also NOTES.md:227). | Use "55.4 KB/frame (measured, 8317014 B / 150)". |
| W6 | §3B "unflushed CSV sidecar: everything since the last 8 KiB-ish block" | The "8 KiB" figure has no source. What was measured is the loss in the 500-row kill: CSV 72532 − 66152 = 6380 B, binary 36000 − 32544 = 3456 B (`sidecar_durability.md`). Neither on-disk size is a multiple of 8192. | Quote the measured loss, or cite the Python `io` docs for the buffer size. |
| W7 | §2.7 "in every ended file [final_currentTime] equals the last frame's time (e.g. 4.933 s = frame 148)" | That holds for MKV/WebM only. Ended fMP4 files end at the duration, i.e. at the end of the last frame: 4.966667 = 149/30, fmp4_kf 4.0 = 120/30, and H.264 fmp4 cut 60 % in E45 ends at 3.0 although ffprobe counted 89 frames (`electron_pyav19_e35/e45.json`). | Say "MKV/WebM: start time of the last frame; fMP4: end of the last frame (= duration)". |
| W8 | §2.7 "decoded_during_play = expected − 4 (132/132 PyAV-18 files, 14/14 PyAV-19 files)" | 132 and 14 are the Electron 35 counts. Electron 45 is 153/153 (PyAV 18) and 16/16 (PyAV 19). The "23 differences by id" figure comes from NOTES.md:295-297 (15 + 6 behavioural + 2 AV1 decode-count). Recomputed with (ended, error code), 21 ids differ. | Give both versions' counts and break down "23". |
| W9 | Impl. 8 "Electron 35, the version the UI pins" | It is unlabelled, and the UI does not pin a version. `skellycam-ui/package.json:52` has `"electron": "^35.0.3"`, and 35.7.5 is the installed version (`node_modules/electron/package.json:26`). | Say "code: `^35.0.3` range, 35.7.5 installed". |
| W10 | §2.1 / §3A "segment muxer ignores fp (P19, bg)" | PyAV 19 has only the `seg_mkv+fp` run and no no-fp twin, so it cannot show "ignores". The PyAV 18 rt rows can: seg_mkv and seg_mkv+fp are byte-identical (796847 B, `kill_matrix_b.json`). The source cited through NOTES M12 is **n8.1**. At n9.0.2, `segment.c:161-167` copies `s->flags` (so also `AVFMT_FLAG_FLUSH_PACKETS`) into the inner context, but not `flush_packets`, and muxes through `ff_write_chained` (`segment.c:996`). | Label it "measured bg, mechanism source n9.0.2 segment.c:161-167". Note (inferred, untested) that `-fflags flush_packets` might propagate. |
| W11 | §6 "The first PyAV 18 `kill_matrix_a` pass was ended externally" | `kill_matrix_b.json` also has `resumed_from_partial_run: true`, and both have `replaced_modes: [busy, rt]`. | Mention both. |
| W12 | §2.3 "after repair, OpenCV ... seeks to the right frame" | Pixel identity was checked only for repaired MJPEG mkv+fp and H.264 mkv_cl0+fp (`cv2_seek_identity_pyav19_files.json`). The repaired AVI has only `pos_after` 76 (`cv2_on_pyav19_files.json`). | Say "pixel-verified on 2 repaired files; position-only on the third". |
| W13 | Machine line "i7-14700K, RTX 3070 driver 610.88" | Unlabelled. | Cite `HANDOFF.md:60-61`. |

## Checked and confirmed (spot list)

- `pyav19_recheck.json`: all 25 kill rows match table §2.1 (counts, byte-exact counts, bytes, `bytes_mod_262144`, 0-byte AV1 mkv, segments 30/30/30/30/28). `pyav19_recheck_repeat.json` differs only in `nvidia_smi_before`.
- `pict_type` table matches `pyav19_recheck.json` and `pict_type_check.json` (PyAV 18).
- `cv2_on_pyav19_files.json` and `cv2_seek_identity_pyav19_files.json`: -2.767e17, 0, 149 values and frame-0 identity as stated. PyAV 18 background: every drained mkv/webm/avi/rawidx cv2 seek has `pos_after == 1.0`, and fmp4/nut/ivf/folder land on target+1 (recounted from `kill_matrix_a/b.json`).
- `truncation_pyav19.json`: all 5 rows of the §2.4 table match.
- `encoder_hold_check_pyav19.json/.log`: 36/39, 75/0, 73/2, 75/0. The log shows "random access" / mini-gop 16, "low delay" / mini-gop 4, "TPL is disabled in low delay applications.", and SVT-AV1 v4.2.0.
- Electron PyAV 19 table: every cell matches both JSONs, including the error codes, 0 and 73 decoded frames, and the end times. Chromium versions match.
- `resumable_demo_pyav19.json`: all 5 rows match (lost frames, counts, max gaps). `resumable_demo.md` (PyAV 18) has 9 scenarios.
- `sidecar_durability.md/json`: kill table; 48/48 per parser; pandas 23/24, 24/24 and 17/6, 18/6 (recounted from the raw rows).
- `sfn26_pipe.md` / `sfn26_pipe_n150.md`: all counts.
- Sources (all n9.0.2 unless noted). Line numbers and quotes match exactly:
  - libavformat: version_major.h:32, version.h:34, file.c:324-332, mux.c:425-433, options_table.h:39 and :84, aviobuf.c:466-469, matroskaenc.c:2744-2748, :3032-3048 and :3231-3236, movenc.c:7449-7455
  - libavcodec: nvenc_h264.c:100-101, libsvtav1.c:830
  - SVT-AV1 v4.2.0: Parameters.md:261
- sfn26 765bf82d: recorder.rs:40-45, :141-156, :233, :265-275, dispatcher.rs:373 (`.mp4`), csv_writer.rs:72 (flush), and no `sync_all`/`sync_data` in csv_writer.rs.
- Background REPORT.md:27, :210-213 and :226 say what is claimed.
- Bench section: `common_cr.py:423-426` (cv2 import at :425), `bench_repair.py:38` (`cc.VENV_PY`), `resumable_pyav19.py:14`. All 4 `cr_*` manifest commands use `.venv/Scripts/python.exe` (`results/bench_queue_from_wf_2e122ed0.json`). All 4 bench smoke files report `pyav: 18.0.0`.
