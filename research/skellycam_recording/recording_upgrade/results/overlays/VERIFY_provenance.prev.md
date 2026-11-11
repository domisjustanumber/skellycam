# Overlays (G3): provenance check of the draft FINDINGS

Checked 2026-11-09 on Gerald. Lens: does each cited piece of evidence exist, and does it say exactly what the claim says? No timed runs were made. Functional re-checks:
- `electron_summary.md` was regenerated from copies of the raw JSON in the scratchpad (`.../scratchpad/overlays/verify_prov/`) with `summarize_electron.py`. The output is identical to the committed file (diff of lines 2 onward, and the title line is the same too). The committed file was not touched (mtime 11:59).
- PyAV 19.0.2 filter capabilities were re-checked with `uv run --script` (deps `av==19.0.2`): `ass` False, `subtitles` False, `drawtext` False, `overlay`/`alphamerge`/`drawbox` True, libvpx-vp9 decoder and encoder present. This matches `pyav19_functional_check.json` → `caps`.
- Primary sources were fetched raw with curl (rvfc.html, webvtt.html, assdec.c at n8.0), and the quotes were matched as text.

## Verified (evidence exists and matches)

| claim area | evidence checked | result |
|---|---|---|
| `.skov`/JSONL/msgpack/WebVTT/SVG/ASS B/frame and MB/h, 720p "all" | `formats_functional.json` / `.md` | all numbers match |
| 28/28 cuts, `trunc_errors: []`, every case and resolution; extra-record cut = 1 for jsonl and vtt only | `formats_functional.json` (all 32 data-level rows scanned) | match |
| single SVG strict parse fails 25/25; lenient 10-288 / 11-288; SVG per frame 300/300 | same | match |
| 1080p vs 720p max difference 5.4% (ASS skeleton) | same, computed over all rows | match (5.41%) |
| SVG per frame 10.7x `.skov`, 6.2x JSONL; alpha 24x `.skov` | arithmetic | 10.73, 6.19, 24.4 |
| Electron versions, Chromium versions, scaleFactor 1, GPU list (vendor 4318 x2, 5140 Basic Render) | `electron_*.json` → `env` | match |
| rVFC lookup, `round(mediaTime*30)`, rAF rule counts, captures, canvasComposite, 2x rows | `electron_*.json` → `results.play` | all counts match |
| every 1x canvas-over-video capture mismatch is `[N, N-1]` | all 10 1x runs, full lists (captureMismatch is not capped, `harness.js:212`) | match (0 exceptions) |
| dual `<video>`: layer one frame ahead in 136/250 and 195/271 | offset is `b - a` = layer - base (`harness.js:399`) | match |
| paused seeks, last-frame sequences, WebVTT table, in-band 0 tracks, canPlayType mkv | `electron_summary.md` (regenerated identical) | match |
| SVG/VTT cut "at 50%" | `make_test_media.py:221-223` (`d[: len(d) // 2]`) | match |
| VP9-alpha / PNG-MOV / QTRLE-MOV sizes, ffprobe `alpha_mode 1`, CLI alpha MAD 0.114 | `make_test_media.json` | match |
| alpha truncation 160/160, PNG/QTRLE 0 frames | `alpha_truncation.json` | match |
| PyAV 19 alpha 3,840,349 B, 64,006 B/frame, trunc50 30/30, decoders, MAD 0.4572, barcode 60/60; P1 60/60; P2 60/60 vs 1/60; caps | `pyav19_functional_check.json` | match |
| "same options" for the PyAV 19 alpha encode | `pyav19_functional_check.py:41,182` (crf 32, b 0, realtime, cpu-used 8, row-mt 1, auto-alt-ref 0, g 30) vs CLI command in `make_test_media.json` | match |
| P2 filter string `x=0:y=0:eof_action=pass:format=yuv420` | `pyav19_functional_check.py:239` | match |
| P1/P2/P2b/P3/P3b counts and sizes | `export_burnin.json` (pyav 18.0.0, correctly labelled background) | match |
| label layout table, 1,474 lanes, 0 hidden, deterministic, 0 HUD pairs, 35/53 lines | `label_layout.json` | match |
| layout PNG exists | `<raw>/overlays/layout/C_placed_720p_board20.png` | exists |
| camera JPEG median 56,759 (51,085-65,760) | `<raw>/corpus/index.json` → `c930e_720p_flash` | match |
| stamp code | `opencv_get_frame.py:79-90` (stamp at 80, putText outline at 90; colour pass is line 91) | match |
| stamp extent x 5-340, y 15-50 | `results/real_recording_20261109/RESULTS.md:145` | match |
| UI frame rule and seeks | `SyncedVideoPlayer.tsx:377-403` (floor at 401), `:334-335`, `:506-507` | match |
| FreeMoCap info panel `fillRect(5, 5, 500, 85)` | `charuco-overlay-renderer.ts:165` | match |
| `OVERLAY_STALE_MS = 500`, latest-only state | `offscreen-renderer.worker.ts:17,26-29,62-63,83` | match |
| rVFC quotes (Introduction) and `mediaTime` definition (§2.2) | https://wicg.github.io/video-rvfc/ | exact text, §1 Introduction and §2.2 Attributes |
| WebVTT quotes | https://www.w3.org/TR/webvtt1/ | "Three ASCII digits..." in §4.1; "only useful for scripted applications" in §4.2.1; "often provided as a JSON construct" in §1.7 (the correction in the draft is right) |
| ASS centiseconds | FFmpeg n8.0 `libavformat/assdec.c` lines 72 and 118 | exact text on those lines |
| bench manifest ids and priorities | `results/bench_queue_from_wf_2e122ed0.json` → `overlays.bench_manifest` | overlay_cost 1, play_quiet 2/2, draw 2/3 |
| `overlay_cost` uses the skellycam venv; `alpha_vp9_pipeline` pipes to the ffmpeg CLI | manifest command; `bench_overlay_cost.py:17,43-48,86,171-175` | match |
| msgspec 0.21.1 | `.venv/Lib/site-packages/msgspec-0.21.1.dist-info` (not recorded in the result JSON) | match |

## Refuted

| claim | why | correction |
|---|---|---|
| 2.3: today's rAF rule is "mostly offset -1, plus +1/+2 on VFR" | In all 4 VFR runs, positive offsets outnumber -1: E35 VFR VP9 302 vs 264; E35 VFR H.264 302 vs 147; E45 VFR VP9 304 vs 155; E45 VFR H.264 304 vs 200 (`electron_*.json` → `rafUiOffsets`) | "CFR: offset -1 (one +1 in E45 H.264). VFR: mostly +1/+2, with -1 in the rest." |
| 3.2: today's rule on VFR is "worse" | True in E35 only. In E45, VFR matched more often than CFR: 145/604 and 100/604 vs 35/600, 58/599, 13/596 | "Wrong on both. VFR adds +1/+2 offsets; the match rate is load-sensitive (E35 VFR worse, E45 VFR better)." |
| 3.3: E45 seek after the last frame is "correct, 5/5 files" | E45 VFR VP9 shows `75->74` and VFR H.264 shows `duration->298` (`electron_summary.md`, last-frame table). 2.3 of the draft states this correctly | "not stuck in 5/5 files; the CFR files are exact; each VFR file has one off-by-one seek (the VFR exact-pts issue)" |

## Weak (needs a label, a narrower wording or a better citation)

| claim | why | fix |
|---|---|---|
| 2.1: skellycam-ui "draws nothing on the video" | It draws HTML frame and time labels absolutely positioned over each `<video>` (`SyncedVideoPlayer.tsx:281-308` `updateOverlays`; `:658-700` `position: 'absolute'`, `showOverlays`) | "draws nothing into the video pixels; shows HTML frame/time labels positioned over each video" |
| 2.1: FreeMoCap sends "float32 point blocks" | The header allows `dtype_code = Dtype.FLOAT32 \| FLOAT64` (`binary_keypoints_protocol.py` docstring, BLOCK_HEADER) | "float32 or float64 point blocks keyed by `frame_number`" (now checked, code) |
| 2.1: post-hoc output `annotated_videos/<stem>_annotated.mp4` | Name is `f"{video_path.stem}_annotated{video_path.suffix}"`, so it uses the source suffix (`video_node.py:216-219`) | "`<stem>_annotated<source suffix>`"; cite `:211-219` |
| 6: `charuco-types.ts:21` requires `has_pose` | `has_pose: z.boolean()` is line 20 | cite `charuco-types.ts:20` |
| 2.2 / 4: JSONL "1.73x" `.skov` | 616.1/355.1 = 1.7350 and 5704.3/3287.6 = 1.7351, which round to 1.74 | write 1.74x (or about 1.7x) |
| 2.2: msgpack larger "because msgspec writes Python floats as float64" | Labelled inferred, but not tested. The data are float64 arrays rounded to 2 dp (`overlay_model.py:62`). For "text", msgpack is smaller than JSONL (31.4 vs 45.9 B/frame) | keep inferred and say "for the point-heavy cases", or test float32 arrays (already in section 6) |
| 2.3 / 4: at 2x "drawImage returned the next frame in 72/241" / "single-canvas path paired a frame one ahead in up to 72/241" | The harness keeps only 20 mismatch examples (`harness.js:201`). All 20 are `code = fi+1`, but the direction of the other 52 is not recorded. The 2x run was canvas-over-video, not `canvasComposite` | "72/241 mismatched; all 20 recorded examples were one ahead". Mark the single-canvas-at-2x statement inferred (composite at 2x not run) |
| 2.4: ASS-in-MKV packets "each 0.03 s long" | `make_test_media.json` → `ass_mkv_packets` keeps only `first6` | "the first 6 packets are 0.03 s long" |
| 2.5 / 3.1: "The VP9-alpha WebM loads in Chromium ... with alpha" | The file Chromium loaded was the CLI-encoded one (`make_test_media.json`, ffmpeg CLI - background). The PyAV-19-encoded file was not loaded in Chromium | label "(CLI-encoded file - background)"; add "PyAV 19 alpha file in Chromium: not tested" to section 6 |
| 2.6: P2b "because the layer came out opaque" | The JSON shows the barcodes (base read as 0, overlay correct), not opacity. Opacity is the explanation | mark "opaque" inferred from the barcode readout |
| 2.6: "PyAV 19.0.2 reproduces P2" | The base `base_cfr_vp9.webm` was encoded with PyAV 18 (`make_test_media.json`). PyAV 19 did the decode, filter and encode only | add "base input encoded by PyAV 18" |
| 4: "Seek to the midpoint between frames for VFR files" | Not uniformly better: E45 VFR H.264 exact 80/80 vs mid 79/80. E35 VFR H.264 mid is 76/80 | keep, but cite the E45 exception and say "midpoint plus rVFC `mediaTime` confirmation" |
| 6: AV1 wrong barcode at frames 14 and 254 as "investigator observation" | Measured evidence exists: `electron_*.json` → `play.base_cfr_av1.webm.decodeFailAt` lists fi 14 and 254 in both versions. The libdav1d cross-check in NOTES §11 has no result file | label measured with that path; keep libdav1d as NOT VERIFIED |
| Header: "RTX 3070, driver 610.88"; "i7-14700K" | Not labelled. The JSON has `driverVersion 32.0.16.1088` (610.88 is the usual NVIDIA mapping, inferred). The CPU is not in any overlay result file | cite `electron_*.json` → `env.gpuInfo.gpuDevice` and mark the mapping inferred, or cite the study's machine-info file |
| 2.3: GPU "absent" inference | All `gpuDevice` entries have `active: false` and `glImplementationParts "(gl=none,angle=none)"`, which suggests basic info collected before GPU init. The device list is still valid | fine as worded; optionally add that the list is Chromium's basic GPU info |
| 2.2: script "pure Python + numpy + msgspec" citing `formats_functional.py:15-25` | msgspec is imported in `overlay_model.py:231,248`, not in the cited lines. No PyAV import is in either file | cite `overlay_model.py:19,32,231` as well |

## Not re-checked here (draft already says so)

- `video_node.py` and `binary_keypoints_protocol.py` were spot-checked here (see Weak), but the skellytracker @6f78af48 citations were not opened.

## Verdict

The provenance is good. Every number in the draft was traced to an existing result file or primary source, and almost all match exactly. The summary regeneration and the PyAV 19 capability claims reproduce. Three wording claims are refuted by the raw data: the rAF offsets on VFR, "VFR worse" in 3.2, and "correct 5/5" in 3.3. About fifteen items need narrower wording, a corrected line number or an explicit label. None of them changes a recommendation.
