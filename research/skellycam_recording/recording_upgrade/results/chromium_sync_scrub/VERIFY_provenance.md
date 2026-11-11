# chromium_sync_scrub: provenance check of the draft FINDINGS

Verifier: adversarial provenance check, 2026-11-09, machine Gerald. No timed runs. Paths are relative to `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/` unless written out in full.

Method:
- Recomputed every exact/n total from the raw `functional/e{35,45}/{seek,step}_batch.json` (138 seek and 52 step configs per Electron) and `targeted.json` (30 configs each).
- Opened `caps.json`, `jpegcompat.json`, `jpeg_decode_compare.json`, `mp4box.json`, `sync_scrub_smoke.json`, `clips_summary.json`, `pyav19_*.json` and `bench/e*/*/_index.json`.
- Downloaded the spec pages again (curl) and string-matched every quote against the HTML with tags removed.
- Downloaded the Chromium files at both tags (`?format=TEXT`) and grepped the cited lines.
- Opened every cited skellycam-ui, skellycam and script line.
- Scratch copies: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/chromium_sync_scrub_verify/`.

## Verdict

The draft holds up well. Every spec quote, every Chromium file:line at both tags, every UI code citation, and almost every number matches its evidence. Four statements are false as written: the F11 all-intra row, the word "always" in F13, the mp4box/`run_suite.py` limit in section 6, and the size ratio in I6. About a dozen more need a label, a scope or a citation fixed. No PyAV 18 result is presented as primary. The clip encode, the libavcodec check and the PyAV columns of `jpeg_decode_compare.json` are all labelled background. There are no timing numbers in the draft.

## Confirmed (spot list)

| Claim | Evidence checked | Result |
|---|---|---|
| Versions: Electron 35.7.5 / Chromium 134.0.6998.205, Electron 45.2.3 / Chromium 156.0.8078.80 | `functional/e*/caps.json` `versions` | match |
| Clips made with PyAV 18.0.0, libavcodec 62.28.102 | `clips_summary.json` `generator` | match |
| F1-F4 code lines | `SyncedVideoPlayer.tsx:101,103,332-335,377-378,424-425,456,506-507,523-526,541-544,568` (End key); `playback_router.py:230`; `requestVideoFrameCallback` has 0 hits in `skellycam-ui/src` | match |
| F6 quotes; no "frame-accurate" | html.spec.whatwg.org media.html: all 3 quotes found; "frame-accurate" and "frame accurate" both 0 hits | match |
| F7 quotes, "Draft Community Group Report, 2 August 2024" | wicg.github.io/video-rvfc | match |
| F8 quotes, "W3C Working Draft, 8 November 2026"; AV1 "description is not used for this codec" | TR/2026/WD-webcodecs-20261108; av1_codec_registration | match. "Set [[key chunk required]] to true" appears in `flush()` and in `configure()` |
| F9 lines | `web_media_player_impl.cc:1079`@134, `:1115`@156; `time.h:902-904`@134; `ffmpeg_common.cc:112`@134, `:124`@156; `video_renderer_impl.cc:626`@134, `:660`@156 | all match |
| F11/F12 totals (c720p30 GOP MP4 360/600; GOP WebM `ui` 240/400; c720p60 GOP MP4 116 and 268 of 400; vfr GOP MP4 `ui` 68/400 with the error histogram; hdr329 10/400, +1..+52; `ptsexact` vfr GOP WebM 42 and 392 of 400; `cfrmid` 38/400 and 19/200) | raw seek_batch | match |
| F14 step totals (82/122 with 27/40 and 54/80; vfr 0/122 with +1:61, +2:61; c720p60 GOP MP4 41 and 81 of 122) | raw step_batch | match |
| F15: 30 WebCodecs seek and 16 step configs per Electron, `flushes` 0, `decoder_error` null; 5/5 targeted | raw JSON | match |
| F16a table | `targeted.json` rows (e45 GOP MP4: k=82 shows 81, twice) | match |
| F17: 30 video plus 5 MJPEG entries, all `all_samples_byte_exact`; `gen_clips.py:179-185` fallback | `clips_summary.json`; script | match (NOTES "35" is wrong, as the draft says) |
| F18 numbers | `pyav19_recorder_index_check.json`, `pyav19_webm_pos_delta.json` | match |
| F19: 20/20 MP4 files match on every field; 2 fragmented | `mp4box.json` | match |
| F20, F21: frame counts, `I422`, bitmap max diff 0, ImageDecoder max 5-24 and 81.799-96.981 % | `jpegcompat.json`, `jpeg_decode_compare.json`; frame 0 per `compare_jpeg_decode.py:1,36` | match |
| F22: codec lists identical in e35 and e45; HEVC prefer-software false; VP8 prefer-hardware false; jxl differs; GPUs 0x10de/0x2484 and 0x1414 | `caps.json` (`codecs` lists compare equal) | match |
| F23: stuck case 3/10 with rVFC 2/10 | `e35/targeted.json` | match (this corrects NOTES §6.4 "no rVFC fired") |
| F24: smoke modes, pattern mismatch 0; bench smoke runs 6/4/10/10, all `error: null` | `sync_scrub_smoke.json`, `bench/e*/*/_index.json` | match |
| §5 bench ids; `run_suite.py:20-29` and `summarize.py:8-12` import only the standard library | `bench_queue_from_wf_2e122ed0.json`; scripts | match |

## Refuted

| # | Draft claim | Evidence | Correction |
|---|---|---|---|
| R1 | F11 row "all-intra CFR files: 400/400 (MP4), 200/200 (WebM), same in e45" | `e35/seek_batch.json`: `c720p60/av1_intra.mp4` `ui` 198/200, off `13:1, 591:1`. The c720p60 all-intra family is 398/400 in e35 | Scope the row to c720p30 and c1080p30. Add c720p60 all-intra `ui`: 398/400 (e35, stuck case F23) and 400/400 (e45) |
| R2 | F13 "misses on CFR GOP files are always -1" | `e35/seek_batch.json`: `c720p30/av1_gop.webm` and `vp9_gop.webm` `ptsexact` off_by_hist `{'13':1,'591':1,'-1':3}` | "Always -1, except 2 misses per file in e35 `ptsexact` on the c720p30 GOP WebM files, which come from the stuck case (F23)" |
| R3 | §6: "run_suite.py hard-codes the old scratchpad for Electron 45.2.3 and mp4box.js (`run_suite.py:34-38`) ... e45 and mp4box runs fail with 'missing ...' (`:238-239`)"; "mp4box.js was not checked" | `run_suite.py:34-38` holds only `SCRATCH` and the Electron paths. mp4box appears only in the docstring (`:5-6`). The served path is `harness/server.cjs:20` (`process.env.CSS_MP4BOX_DIST` or the old scratchpad). `:238-239` checks only the Electron exe. Both `.../106dc0c8-.../scratchpad/shared/electron-latest/.../electron.exe` and `.../chromium_sync_scrub/npm_mp4box/node_modules/mp4box/package.json` exist (checked 2026-11-09) | "Electron 45 path: `run_suite.py:34-38`, exits 'missing ...' at `:238-239`. mp4box.js path: `harness/server.cjs:20`, can be overridden with `CSS_MP4BOX_DIST`. If it is missing, the mp4box test fails in the page; the runner does not catch it up front. Both were present on 2026-11-09" |
| R4 | I6 "costs 6.5x (AV1) to 7.4x (VP9) the GOP file size" | Table 3.3 (`clips_summary.json`): H.264 9,634,168 / 3,331,315 = 2.9x. AV1 6.5x, VP9 7.4x | "2.9x (H.264) to 7.4x (VP9) on c720p30 at these settings" |

## Weak (needs label, scope or citation)

| # | Claim | Problem | Fix |
|---|---|---|---|
| W1 | F10 "the same frames are unreadable ... through libavcodec (NOTES §6.2, PyAV 18 one-off check)" | No result file exists. NOTES §8 gives prose only. Only `c1080p30/av1_gop.mp4` was checked, and it listed 66, 306 **and 322**. The WebM and fragmented files were not checked | Label it NOT VERIFIED (no result file). Or re-run with PyAV 19.0.2 (decode only, under 1 min) and save a JSON. Stronger evidence already in the data (measured): the `wrong_rows` for k=66 and 306 have `mt_idx` = k, so rVFC `mediaTime` maps to the requested frame (`functional/e*/seek_batch.json`) |
| W2 | F10 parenthetical "c1080p30 AV1 files (598/600 MP4, 398/400 WebM-family total, 198/200 fragmented)" | These are family totals that include the VP9 and H.264 files. Each AV1 file is 198/200 | "Each c1080p30 AV1 file (`av1_gop.mp4`, `av1_gop.webm`, `av1_gop_frag.mp4`): 198/200, frames 66 and 306 unreadable" |
| W3 | F10 "exact for every readable frame ... every ... clip ... both Electrons" | True for the 200 random seeks only. F16a shows `mid` missing on the 0.011 ms pair (5/9 and 7/9) | Add "in 200 random seeks per file; see F16a for the exception" |
| W4 | F5 labelled "source (background ...)", "about 32.9 fps" | It is a measured result of the prior study, not a primary source. `REPORT.md:28` gives headers of **32.8-33.25 fps** across 15 videos | Relabel "measured (prior study, background)" and give the range. hdr329 uses 32.9 as one point in that range |
| W5 | F15 "with `optimizeForLatency: true`" | Not recorded in any result JSON | Label "code: `scripts/chromium_sync_scrub/harness/harness.mjs:105`" |
| W6 | F16 "122/122 for steps" (next to 4 JPEG paths) | Only `jpeg-range-imagedecoder` was stepped (`run_suite.py:115`; 4 configs per Electron) | "Steps: `jpeg-range-imagedecoder` only, 122/122 per content" |
| W7 | F14 "20 forward then 40 back from random starts, 122 steps per clip" | It is 2 starts × (1 seek + 20 forward + 40 back) = 122 rows, so 120 steps plus 2 seeks. The seed is 2, not 1 (`harness.mjs:235-239`, `run_suite.py:113-115`) | State "2 random starts (seed 2), 40 forward and 80 back steps" |
| W8 | F16a "measured (`targeted.json`): frames 81 and 82 ... captured 0.011 ms apart" | `targeted.json` has seek targets only. The gap comes from the capture JSONL | Cite `pyav19_recorder_index_check.json` `gap_81_82_ms: 0.011` (from `research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl`) |
| W9 | F18, §6: SimpleBlock explanation "NOT VERIFIED against the Matroska spec" | It can be upgraded. source: RFC 9559 §10.2, https://www.rfc-editor.org/rfc/rfc9559.txt (accessed 2026-11-09): "Track Number: 8, 16, 24, 32, 40, 48, or 56 bits. An EBML VINT-coded track number." and "Timestamp: 16 bits." followed by one flags octet (Figure 13). A 1-octet track number gives a 4-byte header | Cite RFC 9559 for the 4-byte header layout. That `packet.pos` points at the SimpleBlock payload start (after element ID and size) stays inferred |
| W10 | F18 "two PyAV 18 clips (600/600 each)" | `pyav19_webm_pos_delta.json` stores bare names (`av1_gop.webm`, `vp9_intra.webm`) with no paths. Only the §7 command ties them to `clips/c720p30/` | Store full paths in the JSON, or say the identity rests on the command line |
| W11 | §7 F18 reproduction; scripts in "this session's scratchpad" | `pyav19_recorder_index_check.py` and `webm_pos_delta.py` exist only in `.../93366190-.../scratchpad/chromium_sync_scrub/`, which is not durable. The evidence would lose its generator | Copy both into `scripts/chromium_sync_scrub/` (local, not committed) and update §7 |
| W12 | 3.3 "c720p30 has 600 distinct real frames" | `clips_summary.json` `distinct_source_frames` is **891** for c720p30, which is the corpus set size. The clip has `frames` 600 | Cite `frames: 600` from a set of 891 distinct corpus frames |
| W13 | I5 "HEVC has no software decode path in these Electrons (F22)" | Measured only for WebCodecs `isConfigSupported` prefer-software = false. For `<video>`, `canPlayType` is "probably" and mediaCapabilities says supported/smooth/powerEfficient | "WebCodecs reports no software HEVC decoder. `<video>` HEVC without hardware was not tested" |
| W14 | I8 "slightly worse for `mid` on a 1-tick VFR pair" | Mixed result: GOP MP4 went from 9/9 to 7/9 (worse) and GOP WebM from 5/9 to 7/9 (better) (`targeted.json`) | "Worse on GOP MP4 and better on GOP WebM. Neither Electron is exact on that pair; only WebCodecs is" |
| W15 | I1 "badly off on today's 32.9 fps-header files" | Measured only on the synthetic `hdr329` clip, not on a real recording | Add "(measured on a synthetic clip built that way)" |
| W16 | §6 "Regenerating the 30 clips with PyAV 19 ... decide before 23:00" | `gen_clips.py` writes to fixed paths (`MEDIA` at `:41`; `clips_summary.json` at `:252`). A PyAV 19 rerun would overwrite the PyAV 18 clips and their evidence | Add an output-dir option first, or move the old clips and summary aside. Note this in the bench decision |

## Notes outside the draft

- `results/bench_queue_from_wf_2e122ed0.json` → `chromium_sync_scrub.summary` says "37 test clips". `clips_summary.json` has 35 entries (30 video + 5 MJPEG). Fix the queue summary.
- `functional/e*/sync_scrub_smoke.json` still holds `spread_hist` / `spread_exact0_pct` from a shared machine. The draft correctly uses none of them. They must not be quoted.
