# crash_resilience: VERIFY_method (methodology check of the draft FINDINGS)

Adversarial method check, 2026-11-09, machine "Gerald". Scope: confounders, wrong conclusions, and counts that the result files don't support. The source and URL provenance check is in `VERIFY_provenance.md`, not here.

Paths are relative to `research/skellycam_recording/recording_upgrade/results/crash_resilience/` unless they start with `research/` or `scripts/`. New checks were functional only, using PyAV 19.0.2 (`uv run --script`, PEP 723 `av==19.0.2`, `numpy`). **No timing numbers were produced or used.** OpenCV 4.12.0 came from the skellycam venv, read-only, as in the draft. Electron was 35.7.5 (Chromium 134.0.6998.205).

New evidence files:

| file | what it is | script |
|---|---|---|
| `verify_method_pyav19_checks.json` | segment muxer with and without `flush_packets`; `rt` (live 30 fps) kills for MJPEG mkv+fp, NVENC mkv_cl0+fp and AV1 mkv_cl0+fp | `scripts/crash_resilience/pyav19_checks/verify_method/verify_method_checks.py` |
| `verify_method_cv2_on_pyav_remux.json` | OpenCV frame count and frame-identity seek on the PyAV 19 `opaque=True` remuxes | `.../verify_method/cv2_on_pyav_remux.py` |
| `verify_method_electron_seek_identity_e35.json` | Electron 35: does a seek in an unfinalized file show the same frame as the finalized remux? Checked by canvas readback | `.../verify_method/seekprobe/` |

## 1. Refuted

| draft claim | evidence | correction |
|---|---|---|
| §2.3 "`ffmpeg -c copy` ... kept the frame count of every readable kill image (**21/21**)" | `pyav19_recheck.json`: 19 `kill[]` rows have `ffmpeg_copy_mkv`, and 19/19 counts match. The readable images are 9 MJPEG, 6 NVENC and 4 AV1. `seg_mkv+fp` was not repaired. | 19/19 |
| §2.3 "`add_stream_from_template(ist)` with default arguments fails for every AV1 file (**5/5**)" | `pyav19_recheck.json`: only 4 AV1 rows were remuxed (mkv+fp, mkv_cl0+fp, webm_cl0+fp, fmp4_every+fp). All 4 give `UnknownCodecError: libdav1d`. The 0-frame AV1 mkv and mp4+fp were not remuxed. | 4/4 |
| §2.2 "the PyAV mid-file seek check passed" (repeated in §4 item 6 and §3A) | `common_cr.py:238-252`: `ok` only means "a frame at or before the target and no exception", so a seek that falls back to the start of the file still counts as `ok`. `pyav19_recheck.json` → `pyav.seek`: **MJPEG avi+fp target pts 75 → got pts 0** (back to the start, like OpenCV). MJPEG nut / nut+fp landed about 1 frame early (2028 ticks at about 2048 ticks/frame) although every frame is intra. `exact` is True only for MJPEG mkv, mkv+fp, mkv_cl0+fp, fmp4_every, fmp4_every+fp and fmp4_kf+fp. The inter-codec rows landed on the previous key frame, as `backward=True` should. | "PyAV 19 seeks exactly on unfinalized MJPEG MKV and fMP4. On unfinalized AVI it returns frame 0 (pts 0), and on NUT it returns a frame before the target. A reader must decode forward to the target pts and must not trust the seek." The difference from OpenCV is that PyAV reports the pts it actually landed on, so the reader can detect the miss. |

## 2. Weak: needs rewording, a label change or more evidence

1. **Table A "MKV/WebM + fp + cl0: ... 1 frame for inter codecs".** This is true only after the encoder was drained (the `drained:150` kill). A live kill under PyAV 19 (`rt`: fed at 30 fps, killed after 75 frames fed; measured, `verify_method_pyav19_checks.json` → `rt`) gave:
   - NVENC mkv_cl0+fp: 72 readable of 75 fed;
   - AV1 mkv_cl0+fp: **35 readable of 75 fed** (36 muxed);
   - MJPEG mkv+fp: 74/75 (all 74 byte-exact).

   Fix: label the column "after encoder drain". Add the `rt` row: loss = 1 frame + encoder hold-back (§2.5).

2. **Table A "segment muxer ... ignores fp (P19, bg)".** When the draft was written, PyAV 19 had only `seg_mkv+fp`, so nothing was compared. Now measured (`verify_method_pyav19_checks.json` → `segment`): seg_mkv and seg_mkv+fp give identical results, 148 frames, segments 30/30/30/30/28, 8238820 B each. So the claim now holds on PyAV 19.

   Also flag: the loss is 2 frames. That is less than the 256 KiB buffer plus the open cluster (4–6 frames) would give. The mechanism for the inner muxer's buffering is NOT VERIFIED, so don't explain it with M1–M4.

3. **§4 item 6, "ffmpeg -c copy or a PyAV remux ... both fix count and seek".** The draft's OpenCV evidence covers only the ffmpeg-CLI repairs (`*.repaired.mkv` in `cv2_on_pyav19.py` and `cv2_seek_identity.py`). Under the version rule, the ffmpeg CLI may only inspect files; it is not the implementation under test.
   - Now measured (`verify_method_cv2_on_pyav_remux.json`): the PyAV 19 `opaque=True` remuxes of MJPEG mkv+fp, avi+fp, nut+fp, NVENC mkv_cl0+fp and AV1 mkv_cl0+fp give OpenCV a correct `CAP_PROP_FRAME_COUNT` (149/150) and a frame-exact `POS_FRAMES=74` seek (returned frame == sequential 74) in 5/5.
   - Also measured: PyAV `opaque=True` kept the count in 19/19 (`pyav19_recheck.json` → `pyav_remux_template_opaque`).

   Fix: make the PyAV 19 opaque remux the repair finding, cite these files, and mark the ffmpeg-CLI rows as reference only.

4. **§2.7 "seek ok", and §4 item 8 / §3A "Chromium plays unfinalized ... (seek ok)".** In `electron_probe/probe.html:30-32`, "seek ok" only means that `seeked` fired; which frame was shown was never checked. Given that OpenCV lands silently on frame 0 for the same files, this needed a frame check. Now measured (`verify_method_electron_seek_identity_e35.json`, Electron 35.7.5):
   - Method: unfinalized vs finalized (PyAV 19 opaque remux), targets 1.5, 2.5, 3.5 and 4.5 s, 2 passes each, matched against every finalized frame.
   - AV1 mkv_cl0+fp: 8/8 exact.
   - H.264 mkv_cl0+fp and fmp4_every+fp: 16/16 exact when the canvas was read 250 ms after `seeked`.
   - Without that wait, H.264 returned the *previously shown* frame in 6/16 reads, in MKV and in fMP4 alike. So that is a property of readback at `seeked` with H.264, not of the unfinalized container.

   Fix: cite this file for seek correctness. Pass the stale-at-`seeked` effect to chromium_sync_scrub (G9). It is a functional observation, not a timing one.

5. **§2.7 "ended ... every frame shown" type wording.** The probe ran in a hidden window. `rvfc_callbacks` is 0–1 and `droppedVideoFrames` is large (e.g. 48 of 90 for AV1 mkv_cl0+fp cut 60 %, `electron_pyav19_e35.json`), so presentation was never verified. Fix: write "reached `ended` with no MediaError and `final_currentTime` = last frame time; presentation and pixels not verified". The draft already does this for the −4 offset; apply the same caution to "plays to the end".

6. **§2.1 "readable" includes torn frames.** Without fp, fmp4_every and nut read 147 frames but only 146 are byte-exact (`pyav19_recheck.json`). The 147th is the JPEG torn at the 256 KiB buffer boundary, and ffprobe and PyAV count it as a frame. So a plain process kill (not only a power cut) hands out torn frames when fp is off. Fix: note it under the table and in the §3A torn-frame column.

7. **§2.4 torn-frame column is "n/a" for AV1.** In AV1 fmp4_every+fp the torn sample **is** handed to the decoder: PyAV raised `InvalidDataError` at `avcodec_send_packet()` in 12/12 cuts (`truncation_pyav19.json`), and Chromium gave `PIPELINE_ERROR_DECODE` (§2.7). AV1 mkv_cl0+fp had no decoder error in 12/12 (the demuxer drops the torn block). Fix: rename the column "torn last sample handed to the decoder (any codec)" and fill in AV1 fMP4 = yes 12/12, AV1 MKV = no.

8. **§2.5 low-delay settings: a confounder that isn't mentioned.** The SVT-AV1 log for `pred-struct=1` reports `BRC mode / CQP Assignment : CQP / 35.00` and `Number of PPCS 1`. The default run reports `BRC mode / rate factor : CRF / 35.00` and `Number of PPCS 161` (`encoder_hold_check_pyav19.log` lines 9, 18, 33, 42). So turning on low delay also changed the rate control (CRF → CQP) and the picture-level parallelism. "0 held" therefore compares two different rate-control modes. In addition, inferred: with 0 frames held at a 30 fps feed, `encode()` returns each frame's packet during the same call, so the encode cost moves onto the calling thread. Fix: state both log lines. The cost needs a bench (bench request 1).

9. **Table B and §4 item 12, "ffmpeg-CLI probing holds the first ~5 MB".** What was observed: 75 frames (4.3 MB) left no output file, and 300 frames did (`sfn26_pipe_n150.md`, `sfn26_pipe.md`). The boundary between those two was never bisected. `probesize` 5000000 is one candidate; the analyze-duration limit is another and was not checked. Fix: write "the output did not exist after 75 frames (4.3 MB) and did after 300; mechanism inferred (probing), bound NOT VERIFIED".

10. **§2.1 "a second identical run gave the same counts".** That's correct: only `nvidia_smi_before` differs (diff of `pyav19_recheck.json` vs `pyav19_recheck_repeat.json`). But in `drained` mode the kill happens while the writer is blocked in `stdin.readline()` after `IDLE` (`writer_child.py:29-32`, `:184-187`), so the result is deterministic by construction. The repeat does not show robustness to kill timing or load. Fix: say so. Cite the new `rt` kills (item 1) as the only PyAV 19 kills made mid-recording.

11. **Pending bench `cr_fsync`: a confounder in the script.** The `mkv_fp_fsync_K` policy writes Matroska through a **Python file object** (`bench_fsync.py:50-73`). That is PyAV's Python I/O path plus Python's `BufferedWriter`, and `f.flush()` runs only every K frames. It is not the `av.open(path)` file-protocol path that the recorder and every kill test use. Its numbers will not transfer to `av.open(path, options={"flush_packets": "1"})`. Fix: flag this in §5 and add a policy that writes by path. How to fsync a path-opened file on Windows through a second handle: NOT VERIFIED.

## 3. Checked and holding (no change needed)

| claim | evidence checked |
|---|---|
| §2.1 table, all 25 counts, byte-exact counts, sizes, `bytes_mod_262144`, AV1 0-byte file | `pyav19_recheck.json` → `kill[]` |
| PyAV 19 count == ffprobe count in every readable row | same |
| OpenCV −2.767e17 / 0 / 149 counts and silent seek to frame 0 on unfinalized MKV and AVI | `cv2_on_pyav19_files.json`, `cv2_seek_identity_pyav19_files.json`. The identity test matches against every sequential frame, so it is not a static-scene artifact: only index 0 matched. |
| §2.4 counts (12/12, 0/12, 10/12, 12/12, up to 6 short) | `truncation_pyav19.json` |
| §2.5 counts 36/75, 75/75, 73/75, 75/75; SVT v4.2.0 | `encoder_hold_check_pyav19.json`, `.log` |
| §2.5 hold count is consistent with a live kill | `rt` AV1 mkv_cl0+fp muxed 36 of 75 (`verify_method_pyav19_checks.json`) |
| §2.6 pict_type 60/60 vs 2/60 | `pyav19_recheck.json` → `pict_type` |
| §2.8 resumable PyAV 19: children ran on the uv PyAV 19 interpreter; all 5 rows as stated | `resumable_demo_pyav19.json` → `env.child_interpreter`, `scenarios[].verify` |
| §2.9 sfn26 writes the CSV per frame during recording, not only at finish | code: `git show 765bf82d:skellycam-rust/src/recording/recording_thread.rs` line 301 (`writer.write_row`), `timestamps/csv_writer.rs:72` |
| §2.10 sfn26 `finish()` closes stdin and waits; `Drop` kills only if `finish` didn't run (it sets `frame_count = 0`) | code: `recorder.rs` (765bf82d) `finish` and `impl Drop`. "Drop = kill" is right for the crash or unwinding path only, so state that. |

## 4. Bench requests (tonight, quiet machine, PyAV 19.0.2 only)

1. **Low-delay encoder cost (no manifest id existed).** New script `scripts/crash_resilience/pyav19_checks/bench_lowdelay_pyav19.py`, smoke-tested for function only (the smoke output was not kept or cited). Configs: SVT preset 10 crf 35 with and without `pred-struct=1`, NVENC p4 bf 0 vbr cq 23 with and without `delay=0`. It measures:
   - per-`encode()` call latency p50/p99/max at a 30 fps feed, and frames held;
   - unpaced fps and CPU;
   - bytes;
   - mean and min Y-PSNR of the decoded output.

   Caveat for the analysis: the corpus has flash frames (in the smoke run, a decoded frame matched a different frame of the input better than its own), so read min PSNR with care.
2. **`cr_fsync` under PyAV 19.** The manifest command uses the PyAV 18 venv. This form runs the unchanged script under PyAV 19 and satisfies the `cv2` import in `common_cr.env_versions()`. `--no-project` is required: without it `uv run` would sync the skellycam `.venv`. Measured: `opencv-python-headless==4.12.0.88` resolves and reports 4.12.0, and the script ran functionally under PyAV 19.0.2 / libavformat 63.1.102 (the smoke output was deleted). Item 11's confounder still applies to the `mkv_fp_fsync_*` rows.

## 5. Verdict

The frame-count evidence is solid and reproducible: every §2.1–§2.6 and §2.8 count matches the result files. These need fixing before FINDINGS is saved:

- Two counts are wrong (21/21 → 19/19, 5/5 → 4/4).
- The claim "PyAV seek passed" is refuted for AVI and NUT.
- The inter-codec "1 frame" loss and the "seek ok" / "plays to the end" claims for Chromium leave out how they were tested (drained kill; `seeked` event only; hidden window).
- The repair finding leans on the ffmpeg CLI, which the version rule does not allow as the implementation under test.

The new PyAV 19 checks support the recommendations (MKV + fp, a PyAV remux for finalizing, MKV/WebM for the UI), so the plan's direction holds. The low-delay recommendation needs the CQP/CRF confounder stated and a bench.
