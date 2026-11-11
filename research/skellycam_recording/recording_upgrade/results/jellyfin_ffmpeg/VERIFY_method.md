# jellyfin_ffmpeg: VERIFY_method (adversarial, methodology lens)

Verifier run 2026-11-09 on Gerald, against the draft FINDINGS (supplied in the task, not on disk). No VERIFY_method.md existed before, so nothing was renamed.

Lens: confounders and wrong conclusions. That means a functional pass mistaken for compatibility, Linux sources applied to Windows, generalising from one SKU, mixing up intra and GOP, and comparisons where the conditions do not match.

`R/` = `research/skellycam_recording/recording_upgrade/results/`, `J/` = `R/jellyfin_ffmpeg/`.

## New evidence made by this verifier

- `J/verify_method_linux_wheel_qsv.txt`:
  - Download: PyAV 19.0.2 `manylinux_2_28_x86_64` wheel from PyPI, sha256 checked. It was not run, because this is a Windows machine.
  - String scan of the bundled `.so` files.
  - Excerpts from upstream FFmpeg n9.0.2 `qsv_internal.h`, `qsv.c` and `hwcontext_qsv.c`, fetched with `gh api`.
  - A 2-second PyAV 19.0.2 `uv run --script` that prints the QSV encoder and decoder long names on win_amd64. It records no timing.
- Scratch files are in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad/jellyfin_ffmpeg/verify_method/`: the scripts `strs.py` and `qsv_names.py`, the extracted wheel, and the upstream files.
- No timed runs and no GPU encode sessions.

## Checked and confirmed

| Claim | Check | Result |
|---|---|---|
| F1, F51: release v8.1.3-2; 21 releases, 7 prereleases | `J/releases.txt`: counted the rows | confirmed (21 rows; 8.1.1-1..4 and 8.1.2-1..3 = 7 prereleases) |
| F10, F11: 106 patches, all `hdr_lines=0` | `J/patch_index.txt` | confirmed (106 of 106) |
| F12: 29 names, 28 absent upstream, 2 encoders | `J/upstream_presence.txt` | confirmed (only `transpose_cuda` has `n9.0.2=1`) |
| F17, F24, F28, F31: upstream spot checks | `J/upstream_spotcheck.txt`, `J/upstream_spotcheck_mf_vt.txt` | confirmed |
| F40: asset sizes | `J/releases.txt`: bytes converted to MB | confirmed |
| §3.1: wheel sizes | `J/pyav_19.0.2_pypi_files.txt` | confirmed (28.2 / 18.6 / 35.0 MB) |
| F52: 57 days | 2026-08-03 to 2026-09-29 | the arithmetic is right (but see W5) |
| F47, F48: 0 / 246 / 293 frames; 300/300 | `R/crash_resilience/sfn26_pipe.md` | numbers confirmed (but see W2 and W3) |
| F50: nut+fp 150/150, mkv+fp 149/150 | `R/crash_resilience/FINDINGS.md` §2.1 table | confirmed |
| F29, F30, F32, F34: functional facts | `R/hw_accel_target/NOTES_functional.md:15,91-94,126` | confirmed as cited |
| F26: UHD 770 has no Vulkan encode extension | `R/hw_accel_target/NOTES_sources_nvidia_intel.md:38` | confirmed for the **Windows** driver 101.7088 only (see W9) |
| F39: licence of the wheel | `R/licensing/FINDINGS.md:80-92` | confirmed |
| F3 | `R/hw_accel_target/sw_encoders_pyav19_win_amd64.json` | confirmed: `ffmpeg_version` 9.0.2, `libavcodec` [63,1,102] |

## Refuted

### R1. "Up to the 5 MB probe buffer lost" is labelled measured, but the bound was never measured

- Where: §3.1 row "Startup data loss" and F49.
- The measurement: 75 frames fed (4.3 MB, 2.5 s), then ffmpeg killed, gave no output file. Source: `R/crash_resilience/sfn26_pipe_n150.md`.
- The revised `R/crash_resilience/FINDINGS.md` §2.10 names **two** candidate limits that were never separated:
  - `probesize` 5,000,000 B;
  - `analyzeduration`, which defaults to 5 s.
- The same section says "The boundary between 75 and 300 frames was not bisected. The bound is **NOT VERIFIED**."
- Correction:
  - measured: the whole file was lost when ffmpeg was killed after 75 frames (4.3 MB, 2.5 s).
  - inferred: ffmpeg was still probing. The bound is `probesize` 5 MB or `analyzeduration` 5 s, whichever applies; NOT VERIFIED.
  - Cite `R/crash_resilience/FINDINGS.md` §2.10 instead of `NOTES.md:324-328`.

### R2. The NVENC session pool is applied to `ffv1_vulkan` without any test

- Where: §3.2 row "`ffv1_vulkan`, `h264/hevc_vulkan`". Its caveat says "Shares the 12-session NVENC pool (measured, `R/gpu_encode/NOTES.md:21`)".
- What was actually tested:
  - `R/gpu_encode/NOTES.md:21` tested `h264_vulkan` only.
  - `R/gpu_encode/nvenc_sessions.json` and `nvenc_sessions_19.0.2.json` contain only `h264_vulkan` among the Vulkan encoders.
- FFV1 on Vulkan is a compute-shader encoder, not Vulkan Video. inferred: there is no reason to expect it to hold an NVENC session.
- Correction: "measured: `h264_vulkan` shares the 12-session NVENC pool. `hevc_vulkan`: NOT VERIFIED. `ffv1_vulkan`: not tested; inferred: it uses compute, not NVENC."

### R3. F23: the evidence does not show encoders, and the inference that QSV "may be reachable" contradicts upstream code

- F23 rests on the wheel's codec **short names**. Short names are shared with the QSV decoders: `R/gpu_encode/wheel_hw_codecs.md` says in its header "codec short names (shared with hwaccel decoders)". So they do not show that encoders exist.
- New measured evidence (`J/verify_method_linux_wheel_qsv.txt`) shows the manylinux x86_64 `libavcodec` **does** contain the QSV encoder long names:
  - "H.264 / AVC / ... (Intel Quick Sync Video acceleration)";
  - "HEVC (Intel Quick Sync Video acceleration)";
  - "MJPEG (Intel Quick Sync Video acceleration)".
- These differ from the decoder names, which take the form "`<X> video (...)`". The upstream code that sets them is `qsvenc_jpeg.c:83`, `qsvenc_h264.c:194` and `qsvdec.c:1229`. The same difference shows on win_amd64 through `av.Codec(name,'w'/'r').long_name`.
- So the encoders are compiled in (measured). As a side effect, the manylinux row in `R/gpu_encode/wheel_hw_codecs.md` under-reports QSV encoders.
- But the same wheel has **no VAAPI**:
  - libavutil and libavcodec contain 0 strings with "vaapi";
  - no libva is bundled; `libvpl` and `libdrm` are.
- In upstream n9.0.2, Linux QSV depends on VAAPI:
  - `qsv_internal.h:26-28` defines `AVCODEC_QSV_LINUX_SESSION_HANDLE` only `#if CONFIG_VAAPI && !defined(_WIN32)`.
  - `qsv.c:461` has the comment "This code is only required for Linux since a display handle is required."
  - `qsv.c:710-714` sets the handle only under that macro.
  - `hwcontext_qsv.c:2548-2552` returns "No supported child device type is enabled" when there is no D3D11, DXVA2 or VAAPI.
- inferred: the wheel's QSV encoders on Linux most likely fail to get a hardware session. That is the opposite of F23's "may already be reachable". Still not run on Linux, so NOT VERIFIED functionally.
- Correction to F23: "measured: the encoders are compiled into the manylinux wheel. code: on Linux, upstream QSV needs a VAAPI display, and this build has no VAAPI. inferred: likely non-functional. NOT VERIFIED on Linux hardware."
- Knock-on edits:
  - §3.1 Linux row: Jellyfin's lead grows, because its VAAPI build also makes QSV usable on Linux.
  - Implication 5: a self-built PyAV with `--enable-vaapi` is needed for **both** VAAPI and QSV on Linux. Keep the Linux `mjpeg_qsv` test, but expect it to fail.

## Weak (needs rewording, scoping or relabelling)

### W1. F32 states as fact something the source marks as inferred

- F32 says "That failure is in a PyAV code path".
- Its source, `R/hw_accel_target/NOTES_functional.md:93`, says "inferred: PyAV's auto-built QSV frames pool is not configured the way the D3D11 child expects. NOT VERIFIED against the PyAV source."
- F32 also lists 0064 as a candidate fix. 0064 touches only `libavfilter/qsvvpp.c` and `vf_hwupload.c` (`J/patch_index.txt:65`), so it cannot touch an encoder frames-context path that PyAV builds.
- Fix: label the cause "inferred, NOT VERIFIED" and drop 0064 from the candidates (or say it is filter-only).

### W2. Kill and startup losses are blamed on the subprocess model, but container and flush settings confound them

- The ffmpeg-child runs used CLI defaults: no `flush_packets` (the killed MKV = 16 × 262144 B, `R/crash_resilience/NOTES.md`), x264 transcode or image2pipe probing, and plain MP4.
- The in-process baseline (F50) is `nut+fp` / `mkv+fp`.
- The fair pairs are similar:
  - in-process `mkv` without fp: 146/150 (`R/crash_resilience/FINDINGS.md` §2.1);
  - child MKV MJPEG copy without fp: 293/300.
- Most of the loss gap therefore comes from the container and flush choice, not from the process model.
- Child runs with `-flush_packets 1`, NUT, or a lower probesize were not tested.
- Fix:
  - §3.1 "Crash behaviour" row and implication 1: compare like with like.
  - State that the measured cost specific to the subprocess is one extra failure mode (the child itself gets killed) plus input probing.
  - Say how much of that loss remains with fp, NUT or a lower probesize: NOT VERIFIED.

### W3. "The child survives a Python crash" leaves out the tree-kill result

- `R/crash_resilience/sfn26_pipe.md` also measured `tree_killed` (taskkill /F /T). It lost exactly as much as killing the child: MP4 0, MKV x264 246, MKV copy 293.
- The draft reports only `ffmpeg_killed` and `feeder_killed`.
- Fix:
  - Add the tree-kill column.
  - State that 300/300 holds only when the parent dies alone and the child is not in the killed tree or job.
  - Whether skellycam's launcher kills the whole tree: NOT VERIFIED here.

### W4. Implication 2 and the Windows "Tie" verdict generalise from one machine, and they overlook encoder-behaviour patches

- "On Windows, the hardware target needs nothing from jellyfin-ffmpeg" rests on Gerald alone: one UHD 770 (Raptor Lake-S), one RTX 3070, no AMD.
- F31 itself says other Intel generations are NOT VERIFIED.
- "Its Windows additions are filters and a dual-GPU MF tweak" counts only newly registered names (F12). Several patches change encoder behaviour on Windows, and F35 marks each as NOT VERIFIED:
  - QSV: 0017, 0018, 0020, 0037, 0071, 0105;
  - AMF: 0005;
  - MF: 0097's async-frame binding.
- Fix:
  - Scope the claims: "on Gerald (UHD 770 + RTX 3070), nothing needed".
  - Mark other Intel generations, AMD AMF and laptops as NOT VERIFIED.
  - Drop "Its Windows additions are filters and ...", or add "plus encoder-behaviour patches, upstream status NOT VERIFIED".

### W5. F52 says "FFmpeg 9 adopted 57 days after release" but no source shows v19.0.0 was the first FFmpeg 9 release

- `J/releases.txt` has dates only.
- PyAV v18.1.0 (2026-08-12) was published after n9.0, and its FFmpeg version was not checked.
- `R/licensing/FINDINGS.md` shows only that 18.0.0 bundles 8.1.2.
- Fix: "PyAV 19.0.x bundles 9.0.2 (measured); 18.0.0 bundles 8.1.2 (background); 18.1.0 not checked". Keep 57 days only as an upper bound for the latest switch.

### W6. The GPL boundary row says "Neither blocks", which conflicts with F38's open FDK-AAC question

- Upstream FFmpeg calls an FDK-AAC build "unredistributable" (`J/upstream_spotcheck.txt`), and jellyfin's patch 0026 overrides that.
- Shipping the **released** jellyfin binary with skellycam is therefore blocked until the FDK question is answered. A self-built jellyfin-ffmpeg without FDK would avoid it.
- Fix: "Standard: not blocked. Jellyfin release binary: redistribution unclear (FDK-AAC, NOT VERIFIED). inferred."

### W7. F9 says the recording path uses no filters, which ignores the decode-then-encode leg the study is testing

- Requirement 9 compares H.264 and HEVC intra on **decoded camera MJPEG** and on YUY2→NV12 input. That path decodes and converts format: 4:2:2 to NV12, plus a range change.
- Jellyfin's own docs list both of those as acceleration stages (F8: "Video Decoding ... Scaling & Format conversion ... Zero-copy").
- Fix:
  - Say that the passthrough path (G1) uses no filters.
  - Say that the intra re-encode path does use decode and format conversion. Jellyfin's QSV and D3D11 decode, scale and zero-copy patches would apply there, but only via a CLI child (NOT VERIFIED).

### W8. §3.1 Windows row cites a Linux source

- F36 quotes `debian/rules`, which builds the Linux `.deb`.
- The Windows build is set by `builder/scripts.d`: `50-dxva.sh`, `50-amf.sh`, `50-libvpl.sh`, `50-ffnvcodec.sh` and `45-vulkan-loader.sh`. Their enable conditions are in `J/build_config_excerpts.txt:142-171` and `J/upstream_spotcheck_mf_vt.txt`.
- Fix: cite scripts.d for the Windows row, not F36.

### W9. A Windows driver result is applied to Linux

- §3.2 Vulkan row: "Windows and Linux; NVIDIA works, the UHD 770 has no Vulkan encode".
- The measurement is the **Windows** driver 101.7088 (`R/hw_accel_target/NOTES_sources_nvidia_intel.md:38`). NVIDIA "works" comes from one RTX 3070 through the gyan CLI, which is background.
- Fix: "UHD 770 on the Windows driver 101.7088: no Vulkan encode extension (measured). Linux ANV: NOT VERIFIED. NVIDIA: RTX 3070 via the CLI (background)."

### W10. The rawvideo quote is stretched to image2pipe

- §3.1 says "rawvideo/image2pipe has a fixed rate, default 25 (source, F46)".
- F46 quotes only the rawvideo demuxer (`demuxers.texi:1040-1041`). The image2pipe `framerate` default is not quoted.
- Fix: quote the image2/image2pipe `framerate` entry, or limit the claim to rawvideo.

### W11. §5 cites bench items that include GOP legs

- `B-QSV-1`, `B-NV-1`, `B-QSV-C1/C2` and `B-NV-C1/C2` run `--gops intra,gop30` / `--gop intra,gop30` (`R/hw_accel_target/NOTES_functional.md:195-204`).
- Requirement 10 makes GOP background only.
- Fix: say that only the intra legs bear on the verdict, or cite the trimmed 23:00 queue if it drops gop30.

### W12. Minor labelling and citation points

- F34: 0033 also touches `libavcodec/d3d12va_hevc.c` (`J/patch_index.txt:34`), not only d3d11va and dxva2. The open question should cover d3d12va on Intel too.
- F21: the `av1_vaapi` line (`allcodecs.c:860`) is missing from the line list.
- F22: "Neither PyPI wheel" in `R/gpu_encode/NOTES.md:27` means PyAV 18.0.0 vs 19.0.2, not two OS wheels. Say "no PyAV 19.0.2 wheel on any OS has a Vulkan encoder (`R/gpu_encode/wheel_hw_codecs.md`)".

## Methodology lens: other items checked and found clean

- Functional pass vs compatibility: the draft makes no playback or Chromium claim for either side. Playback is the same for both builds, so the rows hold. The "Tie for the target codecs" verdict is about encode only. Write "works" as "opens, encodes 60/60 intra, decodes back in software" (`NOTES_functional.md:15`), not as compatibility.
- Matched quality: the draft makes no quality-per-bit comparison. Nothing to check.
- Intra vs GOP: patches 0017 and 0037 (B-frame and GOP defaults) are correctly kept off the recording-path verdicts. W11 is the only slip.
- Jellyfin claims vs vendors: the draft does not rely on any Jellyfin per-generation claim. F7 and F8 are used only to explain why Jellyfin wants its own build.
- Sources only: the draft never ran jellyfin-ffmpeg, as requirement 4 says. The crash numbers are labelled as coming from a gyan 9.0.2 CLI stand-in.

## Verdict

The conclusion stands: don't adopt jellyfin-ffmpeg for the recording path, and the Windows target needs nothing from it on Gerald. Four corrections are needed:

1. **R1:** the "5 MB" startup-loss bound is inferred, not measured. The cause could be `probesize` or `analyzeduration`.
2. **R2:** the NVENC session-pool caveat was wrongly attached to `ffv1_vulkan`.
3. **R3:** the Linux wheel does have QSV encoders compiled in, but it has no VAAPI, which FFmpeg's Linux QSV needs. The "may already be reachable" inference is backwards, and that strengthens the case for Jellyfin or a self-built PyAV on Linux.
4. **W1-W4:** relabel or rescope:
   - F32's PyAV-cause claim;
   - the subprocess-cost attribution, which is confounded by flush and container settings;
   - the missing tree-kill result;
   - the Windows "needs nothing", generalised from one machine.
