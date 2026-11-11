# write_throughput: VERIFY_method (adversarial methodology check of the draft FINDINGS)

Verifier run 2026-11-09, machine Gerald. Scope: the draft FINDINGS text (given inline to the verifier, not on disk), checked against `RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput` and `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`.

Labels: **measured** (result file), **source** (primary source), **code** (file:line), **inferred** (marked). No timing numbers were produced by the verifier.

## 0. Verdict

The numbers in the draft match the result files. I spot-checked T1, T2/T3, T4 (all kills, both PyAV versions), T5, T6, the focus16/models16/core tables, the 45-cell count, first_read_check and meta_seek.

Several conclusions go further than the evidence, though:

- The draft blames PyAV 19 for the unreadable newest segment. The real cause is when the kill landed.
- The draft recommends FFmpeg's segment muxer on crash grounds, but that muxer was never kill-tested.
- MKV is called the "best" container, but on the measured crash metrics it ties with per-frame fMP4.
- The draft implies that a standard container helps Chromium playback (G8). Chromium plays MJPEG in no container.
- A cut JPEG at the tail usually decodes **silently**. The draft only reports the one case that raised an error.
- Every "standard reader" that was tested is built on FFmpeg.

New verifier evidence (functional, PyAV 19.0.2): the empty-packet MKV workaround lost 0 acknowledged frames in 3 of 3 hard kills. It does write size-0 SimpleBlocks to disk, one per frame, and FFmpeg-based readers hide them.

## 1. New functional re-check (PyAV 19.0.2, no timing)

Script: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/write_throughput/verify_emptypkt_av19.py` (PEP 723, `av==19.0.2`). Result: `RES/functional/verify_method_emptypkt_av19.0.2.json`. The media was deleted afterwards.

| Check | Result |
|---|---|
| A. Full FFmpeg log at WARNING with no line cap, 10 MJPEG frames, flush_packets=1, control vs empty packet with explicit ts | Both runs logged 14 lines, all `extract_extradata`. There were 0 other lines in each run. |
| B. EBML scan of the closed file (what is on disk, independent of demuxer filtering) | Control: 10 clusters, 10 SimpleBlocks, 0 of size 0. Empty-packet: 11 clusters, 20 SimpleBlocks, **10 of size 0**. Each size-0 block opens a new cluster (rel. timecode 0), and the next real frame follows in that cluster (rel. timecode 33/34). |
| B. ffprobe on the same files | 10 packets each, 0 of size 0. |
| C. Hard kill (TerminateProcess), mkv flush_packets=1 + explicit-ts empty packet, 60 fps paced, 720p c930e, kill after >= 300 acks + U(0, 1.2) s | acked 332/340/367, **acked lost 0/0/0**, 0 partial units, ffprobe counts = acked. |

## 2. Refuted or misattributed

| # | Draft claim | Why it fails | Correction |
|---|---|---|---|
| R1 | 2.2: the PyAV 18 statement "every killed file was still readable" "does not hold for segmented MKV under PyAV 19" | It is a kill-timing window, not a version effect. In T4, rotation happens when `tick - seg_start >= 2e9` (code `SCR/wt_common.py:295`), with ticks every `int(1e9/60)` ns (code `SCR/functional_tests.py:316`). New segments therefore start at frames 121, 242 and 363 (inferred, arithmetic). The PyAV 19 kill at 368 left 5 frames in `seg0003`, and 363 = exactly the frames of seg0000-0002 (measured, `functional_results_av19.0.2.json` T4 mkvseg10 rep 1). The nearest PyAV 18 kill was at 370, 7 frames into seg0003. That segment was readable, with 4 of its 7 frames (367 byte-exact, 4 files) (measured, `functional_results.json` T4 mkvseg10 rep 0). Default MKV holds 2-6 frames in the muxer (measured, mkv rows, both versions). | "A newest segment is unreadable when the kill lands within the first few frames after a rotation (seen once, 5 frames after rotation). No PyAV 18 kill landed that early, so this is not a version difference (inferred)." |
| R2 | 4.6: "FFmpeg's segment muxer works through PyAV, so manual rotation is not needed" | The segment muxer was tested only with a clean close (T6). The unreadable segment came from **manual** rotation (`AVWriter` kind `mkvseg`). Kill behaviour, whether `flush_packets` reaches the inner muxer, and the rotation window of the segment muxer are all untested. T6 also used `add_stream("mjpeg")` and exact 30 fps timestamps, not `add_mux_stream` with jittered ticks (code `SCR/functional_tests.py`, `t6_segment_muxer`). | "The segment muxer round-trips 300/300 packets after a clean close. Its crash behaviour is NOT VERIFIED, so it cannot replace manual rotation on crash-tolerance grounds yet." |
| R3 | 4.2/4.3 imply that a standard container gives G8 playback ("not a standard container, so playback (G8) needs a remux"; "adopt only after ... a Chromium playback test") | Chromium plays camera MJPEG in no container. Electron 35 and 45 both return `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` for mjpeg in mp4, fmp4, mkv and mov, and `DEMUXER_ERROR_COULD_NOT_OPEN` for avi (measured, `results/chromium_codecs/tables.md` lines 87-96, 127-131). | "For MJPEG, no wrapper gives native Chromium playback. Every layout needs a remux, a transcode or a JS JPEG path. The compatibility that G5 trades is only with FFmpeg/OpenCV tools." |

## 3. Weak (true but overreaching, or missing a confounder)

| # | Claim | Problem | Fix |
|---|---|---|---|
| W1 | Q1 / 2.1: "standard readers can open them"; FFV1-in-MP4 "decoded by every reader" | PyAV, cv2 `CAP_FFMPEG` and ffprobe all use libavformat. They are not independent readers. FFV1-in-MP4 is a format only FFmpeg uses. | Say "FFmpeg-based readers". Mark non-FFmpeg parsers (Media Foundation, MediaInfo, mkvalidator, Chromium's own parsers) NOT VERIFIED. |
| W2 | 2.2 / table 3.1: partial units described via "decode error once" | Under PyAV 19 there were 6 partial units (fmp4_frame x2, fmp4_1s x2, fmp4_hybrid x2). In 5 of them, PyAV decoded the cut packet with no error and cv2 returned it as a frame (`av_decoded` = `units`, `cv2_frames` = `units`). Under PyAV 18, all 15 fmp4 partials decoded silently (measured, `functional_results*.json` T4). | "A cut tail JPEG is usually returned as a valid image. Readers must check each packet's size against the sidecar index (or look for an EOI marker), not rely on decode errors." |
| W3 | 4.3: "MKV with flush_packets=1 is the best measured container" | On the crash metrics it ties with fmp4_frame_flush: kill loss 1,1 vs 1,1 (PyAV 19), and 1 x5 vs 0-1 (PyAV 18). Both had 0 partial units, and both kept 149 exact frames after truncation. fMP4 keeps 1/90000 timestamps, while MKV has less overhead (45.6 vs 133.7 B/frame) and a faster frame table (PyAV 18, background). | State the tie and the tie-breakers. Add the new verifier result: MKV with the empty packet lost 0 frames in 3 of 3 kills (section 1). An fMP4 fragment flush (`av_write_frame(NULL)`) has no PyAV API, and an equivalent trick for fMP4 is untested. |
| W4 | 2.3: "Its kill behaviour (T4) has not been tested"; size-0 blocks only described for the no-timestamp case | It is now measured: 0/0/0 acked frames lost (section 1C). With an explicit timestamp, the file holds one size-0 SimpleBlock per frame, each starting a new cluster (section 1B). FFmpeg-based readers hide them, and other parsers are untested. | Update 2.3, 3.1 and 6. Keep the Chromium/MSE and non-FFmpeg parser check NOT VERIFIED. |
| W5 | 2.3: explicit-ts empty packet "logged no warning"; `extract_extradata` "not attributed" | The source script kept only 6 log lines per step (code `SCR/av19_checks/mkv_emptypkt_ts_av19.py:41`), and step 0 was filled with `extract_extradata` lines. A one-time warning in step 0 would have been hidden. My uncapped re-run shows no other lines. `extract_extradata` appears identically (14 lines) **without** empty packets (section 1A). | Cite `functional/verify_method_emptypkt_av19.0.2.json`. Attribute `extract_extradata` to PyAV 19 / FFmpeg 9.0.2 MJPEG muxing in general, not to the workaround. |
| W6 | T4 as the crash answer | It covers only kills at frames 300-372 (code `SCR/functional_tests.py:340-342`), at 60 fps, 720p (about 55-66 KB frames), one camera, no backlog, and 2 kills per variant under PyAV 19. For buffered variants, frames lost depends on frame size and fps. Untested failure points: during header and first frames, at close, during rotation (hit only by chance, R1), and with a queued backlog (queued frames are not counted as acked). | Describe it as a "steady-state kill at 720p60". Add kill-at-start, kill-at-rotation and kill-at-close cases to `functional_rerun_quiet`. |
| W7 | 2.6 / 4.2 / 4.5: truncation results as G2 evidence | T5 makes one 50 % cut of a **cleanly closed** file. That state (Cues and known element sizes present) differs from a crash (T4). | Label T5 "damaged closed file", not crash evidence. The 4.5 hybrid argument still holds for that case. |
| W8 | 2.8 / 4.1: Defender cost attributed to the files layout | There is no idle-baseline cell. MsMpEng was a top process before the start (`RES/BENCH.md` section 1). Append cells ranged from 3.3 to 15.2 s of MsMpEng CPU, which shows a variable background, probably from other agents' file activity. SearchIndexer CPU was not recorded although the folder is indexed. Payloads are looped (19-frame 1080p sets), and Defender's handling of repeated content is NOT VERIFIED. | Keep the ratio as background. Add an idle baseline and SearchIndexer CPU (bench request 1). |
| W9 | 2.8 / 4.9: process_shared "looked cheaper" | p50 per call is the wrong metric for a writer that serializes 16 streams. tick->written max: process_shared files 26.1 (18.8-33.4) ms in the reruns but 269.9 ms in the first run, against thread 75.3 (32.6-118.0) and 274.6 ms (measured, `RES/BENCH.md` models16 tables). The results are mixed, and the runs are single and contaminated. | Compare tick->written p99/max and queue occupancy over 3 quiet reps (bench request 2). |
| W10 | 2.8: "written = produced, 0 dropped, in all 45 timed cells" | True (45 cells counted). But the thread/process queue holds 2.87 s (code `SCR/bench_write.py` `--ring-s` default 2.87), so even the 1278.5 ms stall fit in the queue. | Add: "No drops with a 2.87 s queue. Drop-free does not mean stall-free." |
| W11 | 4.7: "A process crash does not need fsync" | This holds only because every writer issues an unbuffered `WriteFile` per frame (code `SCR/wt_common.py:146,177,195` `buffering=0`). With Python's default buffered I/O, the tail would sit in user space. | Make the condition explicit: "provided each frame and index record is written unbuffered (or flushed) before it is acknowledged". |
| W12 | 4.4: "This matters for G9 frame-accurate sync" | inferred: rounding to ±0.5 ms is far below a 16.7 ms frame interval, so frame identity and seeking stay exact at 30/60 fps. What is lost is sub-millisecond cross-camera timing. | Reword to "limits timestamp precision to ±0.5 ms. Frame-exact seeking is unaffected at these frame rates (inferred)." |
| W13 | 2.1: pts error 6.434 us for fMP4 | Part of it is the writer's own floor from ns to µs (code `SCR/wt_common.py:304`). The container part is at most 5.56 us (inferred: half of 1/90000 s). | Add one line. |
| W14 | 2.4 | It misses that, with the gap, cv2 `CAP_FFMPEG`/`CAP_ANY` report `CAP_PROP_FRAME_COUNT` 30 while reading only 10 frames (measured, `functional_results_av19.0.2_t2t6.md`). | Add: "the frame count is misleading as well". |
| W15 | Section 5: "inferred: summarize_bench.py globs all bench JSONs" | This is code, not an inference: `SCR/summarize_bench.py:56` (`d.glob("*.json")` per set folder) and `SCR/aggregate_bench.py:32`. | Relabel it as code. Write tonight's runs to new folders (`run_matrix.py --outdir-name ..._av19`) rather than moving today's files. |

## 4. Checked and holding

- T1 byte-exact counts, time bases, overhead bytes, and keyframe flags. The flag is set by the writer (code `SCR/wt_common.py:305`), so it is not muxer inference.
- T4 loss lists for all variants under both versions, and index = acked in every kill.
- T5 rows, T2/T3 rows, T6 row.
- meta_seek: 100/100 seeks exact, `stream.frames` = 0.
- Windows Search scope rows (`RES/wsearch_scope_check_20261109.json`). The returned paths display as `C:\Users\Pictures\...` rather than `C:\Users\Dom\...`, a display-name quirk that does not change the result.
- Source line numbers in `RES/source/ffmpeg_n9.0.2_mux_flush_excerpts.txt` (matroskaenc.c 2613, 3231-3236, 3273, 3602-3603; mux.c 820-827, 1182, 1232).
- focus16, models16 and core tables against `RES/BENCH.md`. All 45 timed cells were counted in `RES/bench/*/`.

## 5. Bench requests for tonight (PyAV 19.0.2 env, quiet machine)

1. Idle baseline for Defender and Search CPU, taken just before and after the focus/repeat cells. Run from the repo root:

```sh
uv run --no-project --python 3.12 --with psutil==7.2.2 python -c "
import psutil,time,json
N=('msmpeng.exe','searchindexer.exe','searchprotocolhost.exe','searchfilterhost.exe')
def g():
    o={}
    for p in psutil.process_iter(['name']):
        n=(p.info['name'] or '').lower()
        if n in N:
            try: c=p.cpu_times(); o[n]=o.get(n,0)+c.user+c.system
            except Exception as e: o[n+'_err']=type(e).__name__
    return o
a=g(); time.sleep(30); b=g()
print(json.dumps(dict(when=time.strftime('%Y-%m-%dT%H:%M:%S'), idle_30s_cpu_s={k:(b[k]-a.get(k,0)) if isinstance(b[k],float) else b[k] for k in b})))
" >> research/skellycam_recording/recording_upgrade/results/write_throughput/bench/idle_baseline_av19.jsonl
```

2. process_shared vs thread, compared on tick->written p99/max (not per-call p50), 3 reps:

```sh
uv run --no-project --python 3.12 --with av==19.0.2 --with numpy==2.2.6 --with psutil==7.2.2 --with opencv-python==4.12.0.88 python research/skellycam_recording/recording_upgrade/scripts/write_throughput/run_matrix.py --set models --writers files,append,mkv_flush --cams 16 --profiles 1080p60 --models thread,process_shared --duration 30 --reps 3 --outdir-name models16_av19_shared_vs_thread
```
