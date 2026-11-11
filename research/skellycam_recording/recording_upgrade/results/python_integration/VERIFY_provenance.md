# python_integration: provenance check of the 2026-11-10 draft FINDINGS

2026-11-10, Gerald. This is an adversarial provenance check of the draft FINDINGS that the step-2 workflow passed in. The draft adds F11-F15 from bench run `20261109T230007`. No timed runs were made. No functional script was run either: every check below reads files, code or a DLL version resource.

The previous report (2026-11-09, functional F1-F10) is now `VERIFY_provenance.prev.md`.

Paths: `R/` = `results/python_integration/`, `B/` = `R/bench/`, `S/` = `scripts/python_integration/`, `RES/` = `results/`, `L/` = `RES/bench_runner/logs/20261109T230007/`.

## Method

- **Timed JSON.** I dumped all three timed JSONs and compared every number in the draft with them:
  - `B/recwriter_quiet1_pyav19.json`: all 16 phase-A cases, both phase-B cases, and the phase-C lists of 3 reps each.
  - `B/jpeg_decode_quiet1_pyav19.json`: 5 sets × 10 methods, with medians, n, min-max, `max_abs_diff_vs_cv2` and both thread counts.
  - `B/nvjpeg_decode_quiet1_2300.json`: 5 sets × 3 modes, plus `env`.
- **Arithmetic.** I recomputed every arithmetic claim: ratios, percentages, batch/5 and durations.
- **Runner records.** I read the runner log lines for items 24, 39 and 40 in `RES/BENCH_RUN_2300_LOG.jsonl`. They give the times, affinity, load, MsMpEng CPU-s and leftover processes. I also read their stdout/stderr in `L/` and the queue entries in `RES/bench_queue_2300.json`.
- **Code citations.** I opened every new citation: `S/bench_recwriter.py`, `S/bench_jpeg_decode.py`, `S/bench_nvjpeg_decode.py` and `S/recwriter.py`.
- **Cross-topic files.** I opened `RES/jpeg_passthrough/bench/open_long.json` with its script `scripts/jpeg_passthrough/bench_open_long.py`. I also opened:
  - `RES/intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json` → `summary`;
  - `RES/crash_resilience/FINDINGS.md:305-325`;
  - `RES/chromium_codecs/tables.md`;
  - `RES/gpu_encode/NOTES.md:58-61,100-103`;
  - `RES/BENCH_QUEUE_2300.md:170-201`;
  - `HANDOFF.md:47-62`.
- **libjpeg-turbo DLL.** I hashed the DLL the bench used (sha256 `3dd7a8a99dd744b4…681f975fd`, which matches `BENCH_QUEUE_2300.md:174`). I read its Windows version resource: `ProductName libjpeg-turbo`, `ProductVersion 3.2.1`. The folder holds `uninstall_3.2.1.exe.nsis`.
- **Primary sources.** These claims are unchanged since the 2026-11-09 check, so I did not fetch them again. I re-checked the quotes against the copies that verifier fetched on 2026-11-09 (`…/93366190-…/scratchpad/python_integration_verify/src/`):
  - `matroskaenc.c` (sha256 `087df6ac…3e1c`, matches the draft): `:3231-3241`;
  - `cap_ffmpeg_impl.hpp`: `:1982-1986`;
  - `CHANGELOG.rst`: `:58`, `:60`, `:64`, `:90`.
  All match.

## Refuted

| # | Draft claim | Evidence | Correction |
|---|---|---|---|
| X1 | F14 (and `R/BENCH.md` §2): stderr holds "about 18,000 libjpeg-turbo `Corrupt JPEG data` warnings **from PyTurboJPEG** on generic_1080p" | measured: `L/39_PI-JPEG-DECODE-PYAV19.err.txt` holds 20,021 bare `Corrupt JPEG data: N extraneous bytes before marker 0xd9` lines. It also holds only 11 PyTurboJPEG `turbojpeg.py:2493: UserWarning` lines, because Python shows each distinct warning once. arithmetic from the JSON: the cv2 calls on generic_1080p add up to exactly 20,021. That is 5,998 for `cv2_imdecode_bgr` and 14,022 for `cv2_imdecode_reduced2_bgr` (1 frame-0 call + 11 warm-up + `single_call.n` + both `threaded.decodes`), plus the 1 reference decode at `S/bench_jpeg_decode.py:171`. PyTurboJPEG made 27,435 calls on that set. | About 20,000 lines (20,021) come from **cv2.imdecode**, once per call on generic_1080p. That cv2 writes to stderr is inferred from the exact count match. PyTurboJPEG adds only 11 UserWarning lines. Add a method note: the cv2 rows on generic_1080p include one stderr write per timed call (redirected to a file). A skellycam using cv2 would also print one line per frame for that camera. Fix `R/BENCH.md` §2 the same way. |
| X2 | F13: "Even that [MKV 77.83 ms] is **4.9×** faster than the fastest fMP4 open (arithmetic: 370.83 / 77.83)" | arithmetic: 370.83 / 77.83 = 4.76 | **4.8×**. |
| X3 | Implication 10: "A decode → nvJPEG re-encode path is therefore **not a target-A path** as tested" | measured, same JSON → `summary`: `nvjpeg_420`, source `mjpeg_qsv` (camera MJPEG decoded on QSV) gives `ssim_y` **0.99788**, `psnr_y` 56.462. Only source `mjpeg_cpu` (CPU decode, then swscale to RGB, `BENCH_QUEUE_2300.md:192`) gives 0.9954. | "nvJPEG fed **CPU-decoded** camera MJPEG (`mjpeg_cpu`, swscale RGB) misses target A (SSIM-Y 0.9954 < 0.9961). The QSV-decoded row (`mjpeg_qsv`, `nvjpeg_420`) reaches SSIM-Y 0.99788." The claim holds only for the CPU-decode path. |

## Weak

| # | Draft claim | Problem | Fix |
|---|---|---|---|
| W1 | F13 / §5: the MKV first rep (77.83 ms) is the "cold-open cost" | Phase C reads each file straight after writing it (`S/bench_recwriter.py:169-188`), so the OS cache is warm. MKV is the first `cv2.VideoCapture` in the process: phases A and B never call cv2. The fMP4 first rep (378.58) is close to its later reps (371.96, 370.83). inferred: 77.83 ms is mostly one-time cv2/FFmpeg backend start-up, not a cold disk read. | Label it "first cv2 open in the process (inferred: includes backend start-up); not a cold-cache measurement". Drop the "even that is N× faster" comparison, or keep it labelled as start-up. |
| W2 | F13 inferred: fMP4 open time grows with fragment count (372 ms at 18k, 1107 ms at 54k). Implication 3 compares "3.7 ms / 0.19 ms for MKV" | The two scripts time different things. Phase C times cv2 open + count + **first read** and PyAV open + **first packet** (`S/bench_recwriter.py:177-190`). `open_long` times cv2 open + count only and PyAV open + `streams.frames` only (`scripts/jpeg_passthrough/bench_open_long.py:73-85`). The corpus (c922 vs c930e) and the writer (recwriter vs a direct `add_mux_stream`) also differ. So MKV 3.68 ms includes a 720p decode while 0.19 ms does not, and that wrongly suggests MKV opens faster at 30 min. | Say the scopes differ. Compare like with like: open_long MKV 0.19 vs per-frame fMP4 1107.28 (cv2, 54k), and phase C 3.68 vs 371.96 (18k). Keep the growth inference labelled and note that its scope is mixed. |
| W3 | F12 inferred: "a maximum queue depth of 1 means each writer thread **finished** a frame before the next one arrived" | `max_depth` is `q.qsize()` read right after `put` (`S/recwriter.py:317-319`). Depth 1 shows the previous item had been **taken off the queue** (`get`, :324), not that `write()` had returned (:328). | "...each writer thread had taken the previous frame off the queue before the next submit". The writer may still have been writing it. |
| W4 | F11: MsMpEng 12.31 CPU-s during item 24, given with "That item writes 3000 new .jpg files per folder case", which implies a link | measured (runner log): Defender's idle rate from WT-IDLE-BEFORE / WT-IDLE-AFTER / WT-IDLE-AFTER2 is 3.40 / 3.12 / 2.60 CPU-s per min. Item 24 ran at 5.50 CPU-s/min over 2.24 min. arithmetic: about 5-6 CPU-s above idle. The decode-only item 39 drew 16.62 CPU-s (1.80/min), which is below idle. | Give the idle rate and the excess (about 5-6 CPU-s over the whole item). Phase B and phase C (2 × 1.4 GB files) also wrote. Keep "not separated per case". |
| W5 | F14 heading: "simplejpeg into a preallocated buffer is **fastest at full size**" | measured: PyAV native YUV is faster at full size on c922 720p (1.3823 vs 1.4027 ms) and c922 1080p (3.3099 vs 3.3434). Its output is planes, not BGR. Implication 9 already says "full-size BGR". | Change the heading to "fastest full-size **BGR** decode". |
| W6 | F9: "PyTurboJPEG on libjpeg-turbo 3.2.1, **simplejpeg default** and simplejpeg into-buffer all differ by 0" | The quiet run's `simplejpeg_bgr` uses `strict=False` (`S/bench_jpeg_decode.py:60`). "Default" reads as strict=True, which rejects generic_1080p. | Call it "simplejpeg (default DCT, `strict=False`)". |
| W7 | §5 caveat: "3.2.1 rests on `BENCH_QUEUE_2300.md:174,200`" | It can now be shown directly. Measured (this check): the DLL at `env.turbojpeg_dll` has sha256 `3dd7a8a9…f975fd` and Windows `ProductVersion 3.2.1`, with `uninstall_3.2.1.exe.nsis` beside it. | Cite the version resource as well (measured, read 2026-11-10). It is still not recorded in the JSON. |
| W8 | Header + §5: each item was "pinned to the 8 P-cores" | The runner log records `affinity: pcores`. The runner set this mask on itself before starting the child (`scripts/bench_runner/run_queue.py:21-22,441-443`), so the child inherited it. No PI JSON records the affinity during or after the run. Flag 2 shows that a library can widen it. | "Started with P-core affinity (runner log). The affinity during the run is not recorded." |
| W9 | Quality paragraph: "HANDOFF 1.1 says the camera JPEGs sit at about target A (nearest IJG quality q94)" | `HANDOFF.md:55` covers "the C930e and C922 JPEGs … all four sets". The generic_1080p camera is not covered. | Say "the C930e and C922 JPEGs". The generic camera's quality is not stated. |
| W10 | Implication 3 / F13: "16 cameras … about 6 s" | inferred, arithmetic 16 × 372 ms, assumes files open serially and the cache is warm. This is labelled. | Add "serial, warm cache". |
| W11 | Comparison table: nvJPEG "Accepts generic_1080p: yes"; F9/F15 "decodes all 5 sets" | The script only checks for no exception, plus shape and `buffer_kind` (`S/bench_nvjpeg_decode.py:71-74`). The pixels were never compared, and the JSON does not record which nvImageCodec backend ran. "nvJPEG" comes from the script docstring (`:10`). | Say "decoded without error (output not validated; backend not recorded)". |
| W12 | Implication 11: `RES/chromium_codecs/tables.md:37,42-45,105-118` | The mjpeg_422 error rows run to line **119** (`mjpeg_422__avi`, C156). | Cite `:105-119`. |
| W13 | F4: `flush_packets` absent, "muxer options at `S/recwriter.py:48-53`" | `CONTAINERS` is lines 49-54. Line 48 is blank. | Cite `:49-54`. |
| W14 | F4: killed MKV/AVI = 23,068,672 B = 704 × 32 KiB | Correct, but this is also exactly 88 × 262,144 B. That matches the FFmpeg file-protocol buffer of 262144 B that crash_resilience cites (`RES/crash_resilience/FINDINGS.md:61,78,310`). | Add "= 88 × 262144 B". This supports the inferred unflushed-buffer cause, which stays NOT VERIFIED for recwriter. |
| W15 | Intro: "The timed findings F11-F14 are new" | F15 (nvJPEG) is new as well, and the revision log maps it. | "F11-F15". |
| W16 | F12 method: "submits frame i to all 5 cameras, **then sleeps** to the next tick" | The loop sleeps to the tick first and then submits (`S/bench_recwriter.py:137-145`). | Swap the order. It does not change any result. |

## Verified (the evidence says exactly what the draft says)

- **F11 (phase A):** every median, p99, p99.9, max and close() value in the 16-row table matches `a_write_cost`. The other claims check out:
  - ratios 6.8× (0.2233/0.0330 = 6.77) and 2.5× (0.2737/0.1117 = 2.45);
  - MKV/fMP4 max ≤ 0.68 ms (0.6799), worst folder 10.4082, worst AVI 7.1538 and 2.8203;
  - 30 × 0.1117 = 3.35 ms/s.
  The method citations are correct: `bench_recwriter.py:87-117`, folder with no CSV `:68-76`, fsync on the sidecar only (`recwriter.py:154-155`, `bench_recwriter.py:75-76`), and the write body `recwriter.py:139-152`. The item time is 134.2 s (JSON), i.e. 2.24 min (log).
- **F12 (phase B):** multiframes 1801 / 3601 and submit n 9005 / 18005 match. So do the submit stats (0.0142 / 0.0586 / 0.1154 / 0.54 and 0.0143 / 0.0642 / 0.2 / 0.4122), dropped 0×5, max depth 1×5, frames 1801 / 3601, `all_bytes_exact` True, thread errors `'None'`×5, and lateness median 0.5289 / 0.5421 with max 1.4394 / 1.4917. The code is `bench_recwriter.py:120-158` with `maxsize=256, policy="drop"`, MKV with real PTS by default (`recwriter.py:69`).
- **F13 (phase C):** bytes 1,398,584,150 / 1,400,100,613 match. So do the reps: cv2 [77.83, 3.66, 3.68] / [378.58, 371.96, 370.83], seek [29.42, 29.02, 29.29] / [25.57, 25.67, 25.71], PyAV [0.4, 0.39, 0.34] / [407.89, 409.05, 407.89], and count 18000.0 for both. The ratios are 101× and ≈1,046×. The method is `:161-195`, the seek is not checked (`:182-185`), and the movflags are at `recwriter.py:52`.
- **open_long (F3, F13, implication 3):** MKV `cv2_frame_count` 53,819 with `count_exact` false, and the three MP4 variants at 54,000. The medians are 1107.28 (cv2) / 1224.24 (PyAV) for per-frame fMP4, 42.57 for 1 s fMP4, 2.38 for MP4 and 0.19 for MKV. `min_frag_duration` is 1000000 (`bench_open_long.py:35`). The intervals are real c930e intervals looped (`:50-54`). arithmetic: 181/54000 = 0.335%, against 3/891 = 0.337% on the short set. The relative error is constant, which fits the drift inference.
- **F14:** all 50 medians, n (1500/1500/95/95/55), the c922 1080p min-max values and the median JPEG sizes match. So do the thread ratios 3.92-5.03 and the c922 1080p rates (297.3→1486.1, 186.9→807.5, 244.4→1161.2, 249.4→1056.8, 242.6→1150.0, 302.0→1504.2, 2262.1 / 1845.9 / 1587.7). The arithmetic holds: 159 / 100 ms/s, 32% / 59%, 37%. The method lines are correct: `:51-140`, `:155`, `:58-63`, `:80-86`. `cv2_num_threads` is 1 and `cpu_count` is 28.
- **F9 (quiet run):** the PyAV diffs are 6/24/8/11/11 and simplejpeg fast 8/26/11/13/12. PyTurboJPEG, simplejpeg (strict=False) and into-buffer are 0. The comparison is at frame 0 only (`:171-181`).
- **F15:** every gpu_single, gpu_to_host and batch5 median and p99 matches. batch/5 = 0.240 / 0.246 / 0.623 / 0.639 / 0.531. The run took 10.28 s, with nvImageCodec 0.9.0.20 and the nvidia-smi before/after strings. The 5 `cuDevicePrimaryCtxRelease failed: 4` lines come after `wrote …json`. The citations `:15`, `:48-51`, `:65-96`, `:82`, `:84-86` and `:89-95` are correct. The comparisons with simplejpeg into-buffer hold set by set.
- **Implication 10 version note:** intra_compare pins nvImageCodec 0.10.0.9 (`scripts/intra_compare/bench_matched_stream.py:4`), and the JSON records `0.10.0`.
- **§5 load record:** load means were 3.37 / 3.75 / 3.21% (max 9.44), with `load_over_15pct` false. Every item had the "leftover processes" flag, which lists the monitoring shells. MsMpEng was 12.31 / 16.62 / 0.78, with no Defender scan events. The flag numbers 2, 3, 4, 5, 6, 7, 9, 11 and 12 match `BENCH_RUN_2300_SUMMARY.md` §3.
- **Cross-topic citations:** `crash_resilience/FINDINGS.md:310` (262144 B, 4–5 frames), `:312` (1 s fragments, bg) and `:325` (`flush_packets=1`) say what the draft says. `gpu_encode/NOTES.md:60,102` say av1_nvenc fails. `BENCH_QUEUE_2300.md:174` gives the sha256 and `:200` says 3.2.1. The queue command for PI-NVJPEG is plain `uv run --script`. `scripts/bench_runner/` has no `UV_CACHE_DIR`.
- **No PyAV 18 or daytime number is presented as current.** The smoke JSONs are no longer cited. Every number in F11-F15 is from the quiet run, and each topic's quality target is stated: none here, as the draft says.
