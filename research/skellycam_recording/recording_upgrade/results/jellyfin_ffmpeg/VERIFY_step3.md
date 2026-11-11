# jellyfin_ffmpeg: step 3 verification (GF04), provenance + method

Date 2026-11-10. Scope: only the new or changed claims of GF04 in the step 3 draft (new §5, F9 requirement pointer, §8 F9 row, §8 "Step 3 gap-fill" table). No test was run and no timing was measured. Every check below is a read of a result file or source file.

Paths: `R/` = `research/skellycam_recording/recording_upgrade/results/`, `IB/` = `R/intra_compare/bench/`.

## 1. Verdict

**Pass with one correction.** Every cited file exists and says what the draft says, with one exception: the hevc_qsv caveat in §5 (and its §8 row) is wider than the cited section. No timing number was added, and no claim depends on a concurrent run (all evidence is from the quiet run `20261109T230007`).

## 2. Claims checked

| Draft claim (§5 / §8 GF04) | Check | Result |
|---|---|---|
| No jellyfin-ffmpeg item queued, by rule (HANDOFF §1 requirement 4) | `HANDOFF.md` §1 item 4: "jellyfin-ffmpeg: sources only, no tests" | OK |
| None of the 68 ids in `R/bench_queue_2300.json` starts with `B-`; 0 matches for `hw_accel_target` | Parsed the JSON: 68 items, ids `IC-*`, `IP-*`, `JP-*`, `CR-*`, `WT-*`, `PI-*`, `UI-*`, `OV-*`; `grep '"id": *"B-'` 0; `grep -c hw_accel_target` 0 | OK |
| Queue replaced B items with matched-quality intra_compare items (`R/BENCH_QUEUE_2300.md:216-222`) | Line 216: B-QSV-1, B-NV-1 "replaced by items 1-3"; line 219: B-QSV-C1, C2, C4, B-NV-C1, C2 "replaced by items 4-8 (+ 720p items 49-53)"; line 222: gop30 pipelines "intra parts added (items 41-45, 49-55)" | OK |
| Items 1-8, 33, 34, 41-45, 49-53 status ok, exit 0 (`R/BENCH_RUN_2300_LOG.jsonl`) | Every one of these ids has `"status": "ok"`, `exit_code` 0 in run `20261109T230007` | OK |
| Item mapping (4-5/49-50 NVENC 1080p/720p; 6-7/51-52 QSV; 8, 33, 53 mjpeg_qsv 4:2:0/4:2:2; 34 hevc_qsv 4:2:2; 41-45 MJPEG/YUY2 pipelines) | Queue ids: 4 `IC-SCALE-h264_nvenc_420`, 5 hevc_nvenc, 6-7 h264/hevc_qsv, 8 mjpeg_qsv_420, 33 `mjpeg_qsv_422-yuy2`, 34 `hevc_qsv_422-yuy2`, 41-42 `*_nvenc_420-mjpeg_cpu`, 43-44 `*_qsv_420-mjpeg_qsv`, 45 `h264_nvenc_420-yuy2`, 49-53 `IC-SCALE720-*` | OK |
| PyAV 19.0.2 wheel's own encoders | `scripts/intra_compare/bench_matched_stream.py:3` and `bench_matched_concurrent.py:3` pin `av==19.0.2`; log `command` runs them with `uv run --script` | OK |
| Item 3 at target B, the rest at target A | `IB/matched_stream_B_1080p_20261110T044204Z.json` `target` = "B"; A_1080p and A_720p `target` = "A"; `R/intra_compare/FINDINGS.md` §2.5 heading "all at target A" | OK |
| Items 1-3: every NVENC/QSV row `reps_ok` ≥ 3, `skipped` empty | `reps_ok` 5 / 4 / 3 on every NVENC/QSV row, equal to `args.reps` (5/4/3), so no rep failed; `skipped` = [] in all three | OK |
| Quality misses: hevc_qsv_422 from MJPEG just under A; at B 1080p h264_nvenc, h264_qsv, hevc_qsv_422 under 45 dB by a knob step, as in the sweep | `quality_check` in the JSONs: hevc_qsv_422/mjpeg_cpu SSIM-Y 0.99608 (1080p), 0.996 (720p) < 0.9961; B 1080p PSNR-Y h264_nvenc/nv12 44.614, h264_qsv/nv12 44.74, hevc_qsv_422/mjpeg_cpu 44.849, with `matched_psnr_y` 44.848 / 44.898 / 44.782. Every other NVENC/QSV/mjpeg_qsv row hits. Matches `R/intra_compare/FINDINGS.md` §2.7 | OK |
| "at matched quality" for the whole set | The QC exists only in items 1-3. `R/intra_compare/FINDINGS.md` §2.5: "Scaling items have no in-pipeline QC; they use the same `matched_settings.json` entries" | Weak (see §4) |
| hevc_qsv "was not a multi-camera path in those items" (measured, §2.5) | `R/intra_compare/FINDINGS.md:217-218`: 1 stream keeps up at 1080p (items 7, 34, 44). `:244`: at 720p (item 52) "4 keep up, but 8 do not" | **Refuted as written** (see §3) |
| hevc_qsv `low_power=1` speed NOT VERIFIED (`R/gpu_encode/FINDINGS.md` I5) | `gpu_encode/FINDINGS.md:409`: "`low_power=1` and `preset=veryfast` open and produce intra output (functional), but their speed is NOT TESTED" | OK |
| inferred (F31): no §3.2 patch shown to change that speed; 0071 is about opening | §3.2 row 0071: "Could help ... QSV open on parts without low-power support (inferred)"; F31 patch lines 9-15 reset `LowPower` on an open failure. Scope "in §3.2" is correct (F35 QSV patches 0017/0018/0020 were not examined) | OK, inferred |
| Timing numbers not repeated; they stay in intra_compare §3.3-§3.5 | New §5 has no fps, CPU or latency number; `R/intra_compare/FINDINGS.md:360,383,399` are §3.3-§3.5 | OK |
| §3.1 Windows-row "Tie (inferred)" unchanged | Current `FINDINGS.md:278` and the draft row are the same | OK |
| F9 / §8 F9 row: requirement 9 + 17:35 text at `HANDOFF_20261109_1300.md:46` | `HANDOFF.md` §1 item 9: H.264/HEVC intra vs JPEG at matched quality (no inputs listed). Old file line 46, under item 9, "(Added 17:35) ... Same inputs (YUY2/NV12 from the real 1080p frames, decoded camera MJPEG at 720p/1080p)" | OK |
| Requirement remap: 4 jellyfin, 8 intra-only, 9 head-to-head, 10 timed tests; old 10 intra-only (line 47), 11 queue (line 48) | `HANDOFF.md` §1 items 4, 8, 9, 10; `HANDOFF_20261109_1300.md:47-48` | OK |
| Old §5 lines 335-344; "req. 11" at 339 and "requirement 10" at 341 removed with it | Current `FINDINGS.md` (463 lines): `## 5. Pending tonight's bench (23:00)` at 335, `req. 11` at 339, `requirement 10` at 341; none in the draft | OK |
| Requirement-4 references kept (lines 1, 3, 292, 333, 337) | Present in the draft header, §3.1 last row, §4.7, §5 | OK |
| No stale "pending"/"tonight" text left | Draft has no "Pending tonight's bench"; §8 history row "§5 bench items" kept as history | OK |

## 3. Refuted

- **Claim:** §5 "measured (caveat for the Tie): in its default mode, hevc_qsv was not a multi-camera path in those items (`R/intra_compare/FINDINGS.md` §2.5)"; also the §8 GF04 row "§2.5 (1 stream keeps up)".
  - **Why:** "those items" includes item 52 (720p). §2.5 line 244 says hevc_qsv at 720p: "4 keep up, but 8 do not". "1 stream keeps up" is the 1080p result only (lines 217-218: items 7, 34, 44). "Not a multi-camera path" is a judgement, not a measurement. `gpu_encode` I5 uses the same judgement, but it gives both numbers.
  - **Correction:** "measured: in its default mode, hevc_qsv kept up with 1 stream at 1080p30 (items 7, 34, 44) and 4 but not 8 streams at 720p30 (item 52) (`R/intra_compare/FINDINGS.md:217-218,244`). inferred: it is not a 1080p multi-camera path." In the §8 row write "(1 stream at 1080p, 4 at 720p)".

## 4. Weak

- **Claim:** §5 "measured: the wheel's NVENC and QSV H.264/HEVC and `mjpeg_qsv` encoders open and run at matched quality on Gerald".
  - **Why:** quality is checked only in items 1-3. The scaling items (4-8, 33, 34, 41-45, 49-53) have no in-pipeline QC and only reuse the settings (`R/intra_compare/FINDINGS.md` §2.5, first bullet).
  - **Fix:** add "(quality checked in items 1-3 only; the scaling items reuse the same `matched_settings.json` entries with no QC)".

## 5. Method notes

- No timing claim from a concurrent run: every number cited is from the quiet run files or from quality/size fields.
- Labels in the new §5 are correct, except the hevc_qsv caveat (§3), which mixes a measurement with a judgement.
