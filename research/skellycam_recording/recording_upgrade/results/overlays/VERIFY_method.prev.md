# Overlays (G3): methodology verification of the draft FINDINGS

Verifier pass, 2026-11-09, machine Gerald. Lens: confounders, wrong conclusions, functional passes mistaken for compatibility. No timing was measured. Paths are relative to `research/skellycam_recording/recording_upgrade/`.

Checks I re-ran (functional only, under 1 min CPU each):
- `electron_summary.md` regenerated from the raw `electron_35.7.5.json` / `electron_45.2.3.json` with `scripts/overlays/summarize_electron.py`. The output is identical to the committed file after the title line (`diff` empty). The draft's provenance claim holds.
- `scripts/overlays/verify_method_crash_modes.py` → `results/overlays/verify_method_crash_modes.json`: crash and corruption modes other than a clean tail cut, using the study's own writers and readers (`overlay_model.py`). 300 frames, 720p, "all". Pure Python + numpy + msgspec 0.21.1. No PyAV.
- `scripts/overlays/verify_method_precision.py` → `results/overlays/verify_method_precision.json`: sidecar sizes with unrounded float32 coordinates instead of the study's coordinates pre-rounded to 0.01 px.
- Read the harness code behind each Electron metric: `scripts/overlays/electron_harness/harness.js`, `main.js`.

## 1. Refuted or wrong as worded

| draft claim | evidence | correction |
|---|---|---|
| 2.3: today's `floor(currentTime*30)` rule "matched the presented frame" in 13/596 to 464/595 | **code** `harness.js:218-225`: the reference is `readVideoBarcode(v)`, i.e. `drawImage(video)` + `getImageData` inside rAF, not the frame on screen. **measured** `electron_summary.md`: at 2x, `drawImage` returned the frame *after* the rVFC `metadata` frame in 72/241 (E35) callbacks, and with two `<video>`s `drawImage` disagreed with the screen in 136/250 while capturePage matched 25/25. So `drawImage` can lead the screen. The rule was never compared with the screen ("not separately captured"). | "matched the frame `drawImage` returned in rAF". The magnitude of the CFR `-1` offsets is not a measure of what the user sees. The VFR `+1/+2` offsets remain evidence that `floor(currentTime*fps)` is wrong for VFR. |
| 2.3 / 3.2: the rAF rule range 13/596 to 464/595 as a rate | **measured** `electron_summary.md`: the same file in the same Electron version, measured twice with the identical rAF loop (plain run vs `@canvasComposite` run), gave CFR VP9 289/598 vs 522/597 (E35) and 58/599 vs 169/600 (E45). | Report it as unstable between runs (factor 1.8 to 2.9 on one file). The numbers can't rank codecs or versions. |
| 3.3: E45 seek after the last frame is "correct, 5/5 files" | **measured** `electron_summary.md`, E45 last-frame table: VFR VP9 `75->74`, VFR H.264 `duration->298` | "not stuck in 5/5 files; 2 of the 25 later seeks on the VFR files showed the neighbouring frame" (consistent with the exact-pts VFR seek errors in 2.3). |

## 2. Weak: true as measured, but the conclusion goes further than the evidence

### 2.1 Sidecar crash tolerance (2.2, 4)
- **Clean tail cuts only.** All 28 cuts cut a finished file at a byte offset (**code** `formats_functional.py:98-112`). Other crash modes give different results (**measured** `results/overlays/verify_method_crash_modes.json`):

  | mode | `.skov` | JSONL | MessagePack (study reader) | WebVTT |
  |---|---|---|---|---|
  | cut + 64 KiB zero tail | 149 returned, 0 wrong | 149, 0 wrong | 149, 0 wrong | 149, 0 wrong |
  | 4 KiB zero hole mid-file | 298, 0 wrong | 299, 0 wrong | **149** (no resync after the hole) | 298, 0 wrong |
  | one byte changed in record 150 | 299, 0 wrong (CRC rejects it) | 300, **1 wrong returned silently** | 300, **1 wrong** | 300, **1 wrong** |

  So "all four recovered 28/28" hides two differences that matter for the `.skov` vs JSONL choice. Only `.skov` detects corrupt records, and the length-prefixed MessagePack reader cannot resync.
- **Implication 4, bullet 1, "the only kind that recovered all complete records at every cut":** only the four data sidecars were cut at 28 points. SVG per frame and VP9-alpha were not tested that way: VP9-alpha got one 50% cut, and SVG per frame got no cut test. "Only" compares against alternatives that were not tested. Fix: "all four data sidecars recovered all complete records at 28 clean cuts; SVG per frame and VP9-alpha were not tested the same way".

### 2.2 Sidecar size ratios (2.2, 3.1, 4)
- **The 1.73x JSONL/`.skov` ratio depends on the writer's precision.** The synthetic coordinates are pre-rounded to 0.01 px (NOTES §2), so JSON holds short decimals. With the same frames as unrounded float32 values, JSONL is 13,795.3 B/frame against 3,287.6 for `.skov`, a ratio of **4.2x**. MessagePack and `.skov` sizes don't change (**measured** `results/overlays/verify_method_precision.json`). Fix: state the precision assumption next to every JSONL/WebVTT size. The real ratio is between 1.74x (2-decimal JSON) and 4.2x (repr of float32). Compression of either format was not tested.
- "1080p within 5.4% of 720p" holds only because the precision is fixed at 0.01 px at both resolutions (**inferred**, same cause).

### 2.3 Chromium alignment method (2.3, 3.2, 4)
- **Measurement load.** Every rVFC callback does a 1280x720 `drawImage` + `getImageData` readback of the video plus a `getImageData` self-check of the overlay canvas. A parallel rAF loop does another readback about 60 times a second, and every 10th callback triggers `capturePage` (**code** `harness.js:196-226`). These synchronous GPU readbacks delay the main-thread canvas commit. That is an alternative explanation for why the canvas-over-`<video>` lag was "the common case, not occasional". The quiet-machine bench (`electron_play_quiet_*`) uses the same instrumented harness, so it will not remove this confounder. `noRaf` exists in the code but cannot be set from the command line (**code** `harness.js:229`, `main.js:18-25`). Fix: call the 3/30 to 19/30 capture counts "with heavy readback instrumentation". The lag direction is supported, its frequency is not.
- **"Screen captures" are `webContents.capturePage` snapshots** requested asynchronously over HTTP (**code** `main.js:81-90`). They show the compositor output, not necessarily scan-out. Fix: name them capturePage captures.
- **The `@canvasComposite` 29/29 to 30/30 is close to built in.** Both barcodes are read from the same canvas, so a capture can only mismatch if `drawImage` and the lookup disagree. That is already counted by the 291/291 rVFC check (**code** `harness.js:61`). It shows that the canvas commits video and overlay together. It doesn't show anything new about timing.
- **Implication 4, bullet 5, "at 2x even the single-canvas path paired a frame one ahead in up to 72/241":** the canvas-composite path was run only at 1x (**code** `harness.js:522-523`). The 72/241 comes from the canvas-over-video run. Fix: label it **inferred** (same `drawImage`-in-rVFC mechanism).
- **Paused seeks:** 2.3 lists CFR H.264 80/80 but omits CFR VP9 79/80 and CFR AV1 78/79 at exact pts, both `f241->240`, in both versions; the midpoint seek gave 80/80 and 79/79 (**measured** `electron_summary.md`). Implication bullet 6 limits the midpoint seek to "VFR files", but CFR WebM also failed at exact pts. skellycam-ui seeks to exact `frame/fps` (**code** `SyncedVideoPlayer.tsx:334,506`). Fix: "seek to the midpoint for all files".
- **WebVTT (2.4, implication 8):** the test measured `track.activeCues` read inside rVFC against the `drawImage` frame (**code** `harness.js:319-330`). It did not test a WebVTT file used as data, with cues looked up by rVFC `mediaTime`. "Do not use WebVTT" conflates the file format with the `activeCues` mechanism. The E35 vs E45 gap (148/299 vs 8/299, single runs under load) is the same `drawImage`-reference and load issue as above. Fix: "do not drive overlays from `activeCues`"; WebVTT as a storage format is not ruled out.
- **Decoder path not recorded.** Neither Electron run recorded whether each file was decoded in hardware (RTX 3070 D3D11) or software. That is an uncontrolled factor in any per-codec difference (**code** `main.js:98-100` stores only `getGPUInfo('basic')`).

### 2.4 Alpha layer and export (2.5, 2.6, 4)
- **Alpha size depends on one encoder setting and on synthetic motion.** 80,251 B/frame (CLI, 300 frames) and 64,006 B/frame (PyAV 19, 60 frames) come from one setting (crf 32, realtime, cpu-used 8) and synthetic labels that move every frame (**code** `make_test_media.py:186-187`, `pyav19_functional_check.py:182`). "About 24x `.skov`, larger than the camera JPEG" is about 19.5x with the PyAV 19 number. Fix: give it as a range for this config and content only.
- **PyAV 19 decoded alpha is not exact.** Frame 0 has exact-zero alpha on 0.8463 of pixels against 0.873 in the matte (**measured** `pyav19_functional_check.json` → `alpha.libvpx_decoder`). The CLI figure of 87.5% used a `< 8` threshold (**code** `make_test_media.py:205`), so the two are not comparable. Mention it if alpha fidelity is used as an argument.
- **PyAV 19 P2 "reproduces P2" is pairing by construction.** The script sets `fb.pts = fl.pts = i` before pushing both frames (**code** `pyav19_functional_check.py:249`). It tests alpha compositing, not timestamp-based pairing of two files, which the CLI P2 did through demuxed pts. P1 is also aligned by construction (`by_f[i]`, `pyav19_functional_check.py:122,133`): it tests "no drop or reorder in encode/decode", not sidecar-to-video pairing when the camera drops frames. Fix: word both as "compositing/encode functional", not "alignment".
- **PNG/QTRLE-MOV "0 frames after truncation"** is a result for the default non-fragmented MOV muxer (moov at the end), not for the codecs. Fragmented MOV/MP4 was not tested (**code** `make_test_media.py` uses no `movflags`; **inferred**). The truncation of a *finished* WebM (Cues and segment size already written) is also not the same as a killed writer.
- **WebCodecs `isConfigSupported` is not an encode test.** "Would use software VP9/AV1" rests on a capability query only, made with the iGPU absent (the draft notes the iGPU).

### 2.5 Smaller points
- "Undetected list fits 35/53 lines" is **code** arithmetic (`label_layout.py:186`, `(h-40)//20+1`), not a measurement. It counts a baseline at y = H as fitting. The test data never got near it (`max_undetected_in_a_frame: 9`, `label_layout.json`).
- "libvpx-vp9 (royalty-free)" in implication 10 has no source in the draft. Add a source or link to the codec topic.
- The refresh rate is called "not measured". The rAF count (598/599 callbacks in a 300-frame, 10 s play, `electron_*.json` → `play.base_cfr_vp9.webm.raf`) suggests about 60 Hz (**inferred**).

## 3. Checked and holding
- Every number I spot-checked against `electron_summary.md`, `formats_functional.json`, `export_burnin.json`, `alpha_truncation.json`, `pyav19_functional_check.json`, `label_layout.json` and `real_recording_20261109/RESULTS.md:145` matches the draft.
- The test media use 300 distinct real C930e 720p frames, not a looped 19-frame set (**code** `pyav19_functional_check.py:131`, `make_test_media.py`). The tiny-corpus confounder does not apply. 1080p video was not tested in Chromium.
- PyAV 18 vs 19 labelling is correct throughout. The PyAV 19 re-check covers caps, P1, the alpha encode/decode/50% cut and the overlay filter graph.
- The Electron 35 last-frame lock-up is consistent across 5/5 files, with no rVFC and `ended` true. It is a strong functional finding. Workarounds (seek to the midpoint of the last frame, reload) were not tested.

## 4. Bench requests (tonight, quiet machine)
Repeat runs to measure run-to-run variance of the load-sensitive play metrics. The single `electron_play_quiet_*` run can't separate signal from noise (see section 1, row 2).
1. `for i in 1 2 3; do env -u ELECTRON_RUN_AS_NODE skellycam-ui/node_modules/electron/dist/electron.exe research/skellycam_recording/recording_upgrade/scripts/overlays/electron_harness --tests=play --out=research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_play_repeat_35.7.5_run$i.json; done`
2. Same with `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe` and `electron_play_repeat_45.2.3_run$i.json`.
