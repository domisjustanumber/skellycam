# chromium_sync_scrub: methodology verification of the draft FINDINGS

Verifier: adversarial method check. Date 2026-11-09, Gerald. No timing numbers were produced; every check below is functional (each under 1 min CPU).
Paths are relative to `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/` unless written out in full.
Scripts are in the scratchpad: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_sync_scrub/verify_method/` (`model_seek.py`, `hw_reorder_check.py`, `hw_reorder_check_bf0.py`, `exhaustive_mid_sweep.py`).

## Checks run

| # | Check | Output | Result |
|---|---|---|---|
| V1 | Recomputed every `<video>`, WebCodecs, JPEG and step total from `functional/e{35,45}/{seek,step}_batch.json` and `targeted.json` | console (scripts above) | All draft totals in F10-F16a, F14 and 3.1 match the raw JSON |
| V2 | Rebuilt the harness's seek sequence (mulberry32, seed 1, `harness.mjs:19,231-233`) and checked which frames were sampled | console | 200 random seeks hit **169 distinct of 600** frames and **185 distinct of 891** (VFR). Frames 80, 81, 82 were **never** sampled. Step runs (seed 2) start at 416/195 (600 frames) and 630/290 (891 frames), so steps also never touched 81/82 |
| V3 | Model of the F9 mechanism: target truncated to whole µs, container pts rounded to nearest µs, show the last frame with ts <= target; applied to the exact seed-1 sequence, compared to the measured exact count of each `<video>` config | `verify_method_seek_model.txt` | GOP files in **e45**: model equals measured in every config, or is off by 1-2 (c1080p30 AV1 unreadable frames; VFR MP4 `ptsexact` 38 vs 36). **e35** has two large mismatches the model does not explain: c720p60 GOP MP4 `ui` measured 58/200 per file vs model 136; VFR GOP WebM `ptsexact` measured 21/200 vs model 197. All-intra files are exact where the GOP model predicts misses, as F13 says. The model predicts `mid` correct for **every** frame of every clip, so the measured `mid` failures (F16a) come from a mechanism outside F9 |
| V4 | Unreadable c1080p30 AV1 frames: rVFC index vs requested frame | `functional/e35/seek_batch.json`, `wrong_rows` of `c1080p30/av1_gop.mp4` | For k = 66 and 306 (pattern unreadable) `mt_idx` equals k. rVFC says the right frame was shown, which supports "unreadable, not wrong" with a Chromium-side measurement (the draft relies on a PyAV 18 one-off) |
| V5 | hdr329 `ui`: which seeks were "exact", and why rVFC fired 195/200 | `functional/e35/seek_batch.json`; model | Exact k = 1, 2, 8, 8, **599**. 599 is exact only because the target (19.97 s) is past the end of the 18.24 s file and the element clamps to the last frame. 21/200 targets lie past the file end. The rows without rVFC (e.g. k = 581, 553) all show 599: no new frame was presented. Max error among targets inside the file is still +52 |
| V6 | Do PyAV 19.0.2 hardware encoders reorder frames with default options? (HANDOFF §1 requirement 3 makes NVENC/QSV the encode target; every study clip is a software encode, H.264 forced to bf=0) | `verify_method_hw_reorder_default.json`, `verify_method_hw_reorder_bf0.json` | Default options: `h264_nvenc`, `hevc_nvenc`, `h264_qsv`, `hevc_qsv` and `libx264` all give decode order != pts order (e.g. h264_nvenc pts/3000 in decode order `0,4,2,1,3,8,...`). `libsvtav1` does not reorder. `av1_nvenc` fails to open (RTX 3070) and `av1_qsv` is not implemented (UHD 770). With `bf=0` all four hardware encoders give decode order = pts order |
| V7 | WebM `packet.pos` + 4 bytes = payload (F18) against the Matroska spec | source | RFC 9559 §10.2 "SimpleBlock Structure" (https://www.rfc-editor.org/rfc/rfc9559.html, accessed 2026-11-09): Track Number "8, 16, 24, 32, 40, 48, or 56 bits. An EBML VINT-coded track number."; Timestamp "16 bits. Signed timestamp in Track Ticks."; then one flags octet (KEY, Rsvrd, INV, LACING, DIS). For track 1 (1-byte VINT) with no lacing that is 1 + 2 + 1 = 4 bytes, matching the measured delta. That `pos` points at the start of the SimpleBlock body is inferred from the match |
| V8 | MP4 box layout of PyAV 18 clips vs PyAV 19.0.2 clips | console (crude byte scan for box names, plus ffprobe `start_time`) | Same box set: `elst` 1, no `ctts`, `stss` present, `moov` before `mdat` at offset 36 (faststart); fragmented: `moof` + `mfra`, no `elst`. `start_time=0.000000` in both H.264 files. Supports, but does not prove, that Chromium would behave the same on PyAV 19 files |

## Verdict per claim

### Refuted (wording must change)

1. **F10 and table 3.1, "`mid` was exact for every readable frame ... every VFR clip ... both Electrons" / "Real VFR: 100 %".**
   The random runs sampled only 185 of 891 VFR frames and never frames 80-82 (V2). The targeted run on exactly those frames fails: e35 WebM 5/9, e45 GOP MP4 and WebM 7/9 (`functional/e*/targeted.json`). The 100 % is a property of the sample.
   Correction: "`mid` was exact on all 200 sampled seeks per file (169-185 distinct frames, same sequence for every file of a given length); it was not run on every frame; it fails on the one near-duplicate VFR pair (F16a)."
2. **I6, "all-intra costs 6.5x (AV1) to 7.4x (VP9) the GOP size".**
   H.264 is 9,634,168 / 3,331,315 = 2.9x (`clips_summary.json`, same table 3.3). Correction: "2.9x (H.264) to 7.4x (VP9) on c720p30 at these settings."

### Weak (keep, but fix as listed)

- **I8, "slightly worse for `mid` on a 1-tick pair".** In e45 both visits to frame 82 showed 81 in every GOP file, MP4 and WebM, and rVFC also reported 81 (`functional/e45/targeted.json`, rows `(82, 81, mt_idx 81)` at target 2.719978 s, 16 ms inside frame 82). So with the `mid` rule, frame 82 was never shown in e45. Fix: say "frame 82 was not reachable with `mid` in e45 GOP files (other targets inside frame 82 were not tried)".
- **F9 / F13 mechanism.** The model reproduces e45 GOP results and the CFR30 results in both versions (V3), which makes the mechanism stronger than "inferred". But e35 c720p60 MP4 `ui` and e35 VFR WebM `ptsexact` need a second, unidentified e35 mechanism, and the e45 frame-82 loss is outside the model. Fix: state that F9 explains the e45 GOP counts (cite `verify_method_seek_model.txt`) and that the e35 extra misses and the near-duplicate failure are NOT VERIFIED.
- **I2 "No codec change is needed", I5 "AV1, VP9 and H.264 behaved the same", F15 WebCodecs path.** All clips were software encodes without container-level reordering (H.264 forced to bf=0). The hardware encoders the plan targets reorder by default under PyAV 19.0.2 (V6). The WebCodecs harness feeds index entries start..k and waits for frame k (`harness.mjs:132-140`, decode loop at :139), which assumes decode order = pts order. Fix: limit these claims to non-reordering streams, and add "recorder must set `bf=0` (or the index must store decode order and the player must feed past k)" as a requirement. `bf=0` works for h264/hevc NVENC and QSV (V6). Chromium playback of NVENC/QSV-encoded files was not tested.
- **"200 random seeks per clip" as evidence weight.** One seed, so every file with the same frame count used the identical sequence. Family totals like 600/600 are the same 169 frames on three files, not 600 independent samples. Fix: say so next to F10/F11.
- **F10 "unreadable, not wrong".** Add the stronger evidence: rVFC `mt_idx` equals k for k = 66 and 306 (V4).
- **F18 WebM 4-byte offset "NOT VERIFIED against the Matroska spec".** Now consistent with RFC 9559 §10.2 for track numbers below 128 without lacing (V7). Keep the limit: 5 bytes for track numbers 128 or more; laced blocks differ.
- **Section 6, hdr329 rVFC 195/200 "not checked".** Checked (V5): the 5 rows are past-end targets that show the last frame. Also: 1 of the 5 exact hdr329 seeks per file (k = 599) is a coincidence of clamping, and 21/200 targets are frames today's UI cannot request (its slider stops at `floor(duration * fps) - 1`). Fix the F11 row text.
- **F23 / I8, "today's End key can trigger" the stuck case.** It was reproduced with `ui` only in `c720p60/av1_intra.mp4`. In `c720p30/av1_gop.webm` and `vp9_intra.webm`, `ui` (599/30) did not trigger it. On a today-style file (hdr329), End gives 546/30 = 18.2 s while the last pts is 18.2067 s (model inputs from `clips/manifest.json`), so the trigger condition is not met there. Fix: "can trigger when the End target equals the last pts exactly (seen once, with `ui` on 60 fps all-intra); not shown for today's files".
- **F15 "flushes: 0 ... with optimizeForLatency: true".** Only `hardwareAcceleration: 'no-preference'` (`harness.mjs:105-106`) on the NVIDIA machine, and no run without `optimizeForLatency`. Fix: state it as a condition, not a cause, and limit it to the decoder Chromium chose here.
- **F23 and the e35/e45 differences are single runs.** Same counts across AV1 and H.264 files (e.g. 58/58, 134/134) argue for determinism, but no repeat was run. Keep as measured, single run.
- **I7 / F16 JPEG paths.** The seek and step tests used OpenCV q90 re-encodes. The camera bytes were only decode-tested (30 or fewer frames per set) and pixel-compared on frame 0 only. Fix: I7 should cite F20 for "decodes" and F21 frame 0 only for "matches OpenCV".
- **Version note, "Chromium results do not depend on the encoder version apart from bitstream and container layout".** V8 shows the same MP4 box set in PyAV 18 and 19 files, but no Electron run used a PyAV 19 file. Keep the claim as inferred, add V8, and list "load the `pyav19_check` files in both Electrons" as not done.

### Confirmed (spot checks)

- F11, F12, F14, F16, F16a totals and offsets, F15 counts (30 WebCodecs seek configs, 5994/6000 with 6 unreadable, `flushes` 0, `decoder_error` null), F17 count correction (manifest has 35 entries, 5 of them MJPEG), F18 values, F21 frame-0 numbers, 3.3 byte counts.
- The draft correctly corrects NOTES §6.4 (e45 is not identical to e35 for `mid`).
- No timing numbers in the draft.

## Requests for tonight

1. Exhaustive `mid` and WebCodecs sweep over every frame of all `vfr720p` and `c720p30` video clips (28 configs per Electron). It is functional, but too long for the 1-minute budget. It decides whether F10 can say "every frame":
   `.venv/Scripts/python.exe C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_sync_scrub/verify_method/exhaustive_mid_sweep.py --electron 45` (then `--electron 35`). Output goes to `functional/e<ver>/exhaustive/`. Dry run checked: 28 configs.
2. The bench_seek suite already records exactness on a second seed (seed 11, `run_suite.py:151`): FINDINGS should report its `exact` counts as an independent sample when it runs.
