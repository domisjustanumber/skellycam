"""Writes results/bench_queue_2300.json (the machine-readable 23:00 queue read by run_queue.py). Standard library only.
  python research/skellycam_recording/recording_upgrade/scripts/bench_runner/make_queue.py
Order = priority order from the queue-building task (HANDOFF section 6A.5 as amended by section 1 items 9-11).
Items 1-23 are the decisive set (built 19:30, unchanged). Items 24+ were appended on 2026-11-09 evening after Dom
removed the 3 h cap (HANDOFF section 1 item 11): every dropped bench still in the intra-only scope, in priority
order, so that the runner's 05:00 deadline skips only the least important ones.
"""
from __future__ import annotations

import json
from pathlib import Path

STUDY = Path(__file__).resolve().parents[2]
S = "research/skellycam_recording/recording_upgrade/scripts"
UV = ["uv", "run", "--script"]
IC = f"{S}/intra_compare"


def stream(label, sizes, sources, reps, target="A"):
    base = UV + [f"{IC}/bench_matched_stream.py", "--paths", "all", "--sizes", sizes, "--sources", sources,
                 "--target", target]
    return (base + ["--frames", "300", "--min-seconds", "3", "--reps", str(reps), "--label", label],
            base + ["--smoke", "--label", label, "--outdir", "{SMOKE_OUT}"])


def scale(path, workers="thread", modes="paced,unpaced", reps=3, probe=0, size="1080p", source="nv12"):
    base = UV + [f"{IC}/bench_matched_concurrent.py", "--path", path, "--size", size, "--source", source,
                 "--workers", workers, "--modes", modes]
    pr = ["--limit-probe", str(probe)] if probe else []
    return (base + ["--streams", "1,4,8,16", "--reps", str(reps)] + pr,
            base + ["--smoke", "--outdir", "{SMOKE_OUT}"] + pr)


def suite(ver, name, skip=""):
    base = UV + [f"{S}/chromium_sync_scrub/run_suite.py", "--electron", ver, "--suite", name]
    sk = ["--skip", skip] if skip else []
    return base + sk, base + ["--smoke"] + sk


items = []


def add(id_, topic, prio, purpose, cmds, est, timeout, tags=(), watch=(), affinity="pcores", outputs="", **kw):
    items.append({"order": len(items) + 1, "id": id_, "topic": topic, "priority_group": prio, "purpose": purpose,
                  "command": cmds[0], "smoke_command": cmds[1], "est_minutes": est, "timeout_minutes": timeout,
                  "tags": list(tags), "watch": list(watch), "affinity": affinity, "outputs": outputs, **kw})


SRC_ALL = "nv12,yuy2,mjpeg_cpu,mjpeg_qsv,rgb"
ICB = "research/skellycam_recording/recording_upgrade/results/intra_compare/bench"
# ---- 1. head-to-head intra encode at matched quality (single stream)
add("IC-STREAM-1080p-A", "intra_compare", 1,
    "Single-stream encode at matched quality (target A, SSIM-Y 0.9961), all 16 paths (libjpeg-turbo, FFmpeg mjpeg, "
    "mjpeg_qsv, nvJPEG; h264/hevc NVENC + QSV, hevc_qsv 4:2:2; libx264/libx265), 1080p, sources NV12 / YUY2 (native "
    "yuyv422 where taken) / MJPEG CPU decode / MJPEG mjpeg_qsv decode / exact RGB (nvJPEG encode-only). fps, process "
    "CPU ms/frame, nvidia-smi + per-adapter GPU Engine utilisation, in-pipeline PSNR/SSIM check. 1 warm-up + 5 reps.",
    stream("A_1080p", "1080p", SRC_ALL, 5), 30, 60, tags=["nvidia", "qsv_optional"],
    qsv_absent_extra_args=["--skip-qsv"], outputs=f"{ICB}/matched_stream_A_1080p_<UTC>.json")
add("IC-STREAM-720p-A", "intra_compare", 1,
    "Same at 720p (YUY2 720p derived by swscale), sources NV12 / YUY2 / MJPEG CPU decode. 1 warm-up + 4 reps.",
    stream("A_720p", "720p", "nv12,yuy2,mjpeg_cpu", 4), 18, 40, tags=["nvidia", "qsv_optional"],
    qsv_absent_extra_args=["--skip-qsv"], outputs=f"{ICB}/matched_stream_A_720p_<UTC>.json")
add("IC-STREAM-1080p-B", "intra_compare", 1,
    "Same at target B (PSNR-Y 45 dB), 1080p, sources NV12 / MJPEG CPU decode, 1 warm-up + 3 reps: shows whether the "
    "ranking holds at lower quality.",
    stream("B_1080p", "1080p", "nv12,mjpeg_cpu", 3, "B"), 9, 20, tags=["nvidia", "qsv_optional"],
    qsv_absent_extra_args=["--skip-qsv"], outputs=f"{ICB}/matched_stream_B_1080p_<UTC>.json")
# ---- 2. stream scaling 1080p30 intra, paced + unpaced, 1/4/8/16
for pid, tags, est, probe in [("h264_nvenc_420", ["nvidia"], 6, 32), ("hevc_nvenc_420", ["nvidia"], 6, 32),
                              ("h264_qsv_420", ["qsv"], 6, 32), ("hevc_qsv_420", ["qsv"], 9, 0),
                              ("mjpeg_qsv_420", ["qsv"], 6, 32), ("nvjpeg_420", ["nvidia"], 6, 0)]:
    add(f"IC-SCALE-{pid}", "intra_compare", 2,
        f"Stream scaling at matched quality (A), {pid}, 1080p30 from NV12, 1/4/8/16 streams (one thread + encoder per "
        f"stream), paced 30 fps (keeps up, late, dropped-equivalent, CPU) and unpaced, 3 reps"
        + (f"; session-limit probe to {probe}" if probe else ""),
        scale(pid, probe=probe), est, 2 * est + 5, tags=tags,
        outputs=f"{ICB}/matched_concurrent_{pid}_1080p_nv12_thread_<UTC>.json")
add("IC-SCALE-jpeg_turbo_420-proc", "intra_compare", 2,
    "Stream scaling, CPU JPEG (libjpeg-turbo 4:2:0 via simplejpeg) with one spawned process per stream, 1/4/8/16, "
    "paced + unpaced, 3 reps (process CPU summed over the workers).",
    scale("jpeg_turbo_420", workers="process"), 8, 20,
    outputs=f"{ICB}/matched_concurrent_jpeg_turbo_420_1080p_nv12_process_<UTC>.json")
add("IC-SCALE-jpeg_turbo_420-thread", "intra_compare", 2,
    "CPU JPEG with one thread per stream in one process, unpaced only, 1 rep: shows whether simplejpeg releases the GIL "
    "(flat aggregate fps = it does not).",
    scale("jpeg_turbo_420", modes="unpaced", reps=1), 2, 8,
    outputs=f"{ICB}/matched_concurrent_jpeg_turbo_420_1080p_nv12_thread_<UTC>.json")
# ---- 3. Chromium intra playback / seek / sync timing (JPEG sequence vs H.264/HEVC intra), E35 and E45
IPB = "research/skellycam_recording/recording_upgrade/results/intra_playback/bench"
add("IP-SEEK-E35", "intra_playback", 3,
    "Electron 35.7.5, N=1 1080p, 200 random seeks: <video> mid (to rVFC and to seeked), WebCodecs (wcflush=1), JPEG "
    "Range + createImageBitmap / ImageDecoder (.mjpeg and JPEG-in-MKV): per-frame decode/seek latency for scrubbing.",
    suite("35", "bench_intra_seek"), 4, 15, tags=["electron", "nvidia"], watch=[IPB],
    outputs=f"{IPB}/e35/bench_intra_seek/")
add("IP-SEEK-E45", "intra_playback", 3, "Same in Electron 45.2.3.", suite("45", "bench_intra_seek"), 4, 15,
    tags=["electron", "nvidia"], watch=[IPB], outputs=f"{IPB}/e45/bench_intra_seek/")
add("IP-SYNC-E35", "intra_playback", 3,
    "Electron 35.7.5, N=4 and 8 at 1080p, 15 s: <video> free / rVFC-steered / leader and WebCodecs master clock "
    "(H.264 + HEVC intra, NVENC files) vs JPEG master clock (.mjpeg bitmap and ImageDecoder, JPEG-in-MKV): frame-index "
    "spread, drops, CPU, working set. QSV-encoded files skipped (--skip _qsv_) to fit the 3 h cap.",
    suite("35", "bench_intra_sync", "_qsv_"), 9, 25, tags=["electron", "nvidia"], watch=[IPB],
    outputs=f"{IPB}/e35/bench_intra_sync/")
add("IP-SYNC-E45", "intra_playback", 3, "Same in Electron 45.2.3.", suite("45", "bench_intra_sync", "_qsv_"), 9, 25,
    tags=["electron", "nvidia"], watch=[IPB], outputs=f"{IPB}/e45/bench_intra_sync/")
sumc = UV + [f"{S}/chromium_sync_scrub/summarize.py", "bench", "intra"]
add("IP-SUM", "intra_playback", 3, "Tables from the intra bench JSONs.", (sumc, sumc), 1, 5, watch=[IPB],
    outputs=f"{IPB}/bench_tables.md")
# ---- 4. passthrough recording costs (MJPEG payload only)
CONT = "pkt_only,mkv,mp4,fmp4_1s,fmp4_perframe,fmp4_1s_tb_us,fmp4_perframe_tb_us,mov,avi_tb_rate,nut,mjpeg_raw_mux,raw_sidecar,jpg_folder"
mux = UV + [f"{S}/jpeg_passthrough/bench_mux.py", "--containers", CONT]
add("JP-MUX-PYAV19", "jpeg_passthrough", 4,
    "jp_mux_cost under PyAV 19.0.2: passthrough mux CPU/wall us per frame + close ms per container (incl. fMP4 at "
    "1/1e6, added per jpeg_passthrough FINDINGS section 5), 720p + 1080p, 3000 frames, 5 reps, 1 camera per process.",
    (mux + ["--tag", "default_pyav19"], mux + ["--frames", "30", "--reps", "1", "--tag", "smoke"]), 10, 25,
    watch=["research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench"],
    outputs="research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_mux_default_pyav19_<UTC>.json")
CRB = "research/skellycam_recording/recording_upgrade/results/crash_resilience/bench"
fs = UV + [f"{S}/crash_resilience/bench_fsync.py"]
add("CR-FSYNC-PYAV19", "crash_resilience", 4,
    "cr_fsync under PyAV 19.0.2: none / flush / fsync every 1,10,30,300 / sidecar-only / MKV+fp via a Python file "
    "object (confounder noted in crash_resilience FINDINGS section 5), per-frame latency, throughput, CPU.",
    (fs + ["--frames", "3000", "--repeats", "3", "--out-name", "pyav19"],
     fs + ["--frames", "30", "--repeats", "1", "--out-name", "smoke"]), 5, 15, watch=[CRB],
    outputs=f"{CRB}/fsync_pyav19.json")
fo = UV + [f"{S}/crash_resilience/bench_fragment_overhead.py", "--payloads", "mjpeg"]
add("CR-FRAG-MJPEG-PYAV19", "crash_resilience", 4,
    "cr_fragment_overhead under PyAV 19.0.2, MJPEG payload only: mkv / +flush_packets / cluster 0, fMP4 per frame / "
    "per keyframe / 100-2000 ms fragments, mp4, nut, avi, segments, raw+index, folder; CPU, wall, size.",
    (fo + ["--frames", "3000", "--repeats", "3", "--out-name", "mjpeg_pyav19"],
     fo + ["--frames", "60", "--repeats", "1", "--out-name", "smoke"]), 6, 20, watch=[CRB],
    outputs=f"{CRB}/fragment_overhead_mjpeg_pyav19.json")
# ---- 5. reduced write_throughput confirmation + reduced usability check
WTB = "research/skellycam_recording/recording_upgrade/results/write_throughput/bench"
idle = UV + [f"{S}/bench_runner/idle_baseline.py"]
add("WT-IDLE-BEFORE", "write_throughput", 5, "30 s idle CPU of MsMpEng / SearchIndexer / SearchProtocolHost / "
    "SearchFilterHost before the focus cells (VERIFY_method request 1).",
    (idle + ["--tag", "before_focus16_av19"], idle + ["--seconds", "2", "--out", "{SMOKE_OUT}/idle.jsonl"]), 0.6, 3,
    outputs=f"{WTB}/idle_baseline_av19.jsonl")
rm = UV + [f"{S}/write_throughput/run_matrix.py", "--set", "core", "--profiles", "1080p60",
           "--writers", "files,append,mkv_flush,fmp4_frame_flush"]
add("WT-FOCUS16-AV19", "write_throughput", 5,
    "16 cameras x 1080p60 camera-MJPEG passthrough, thread model, 30 s, 3 reps: folder of JPEGs vs raw append+index vs "
    "MKV flush vs fMP4 per-frame flush (write latency p50-max, drops, CPU, MsMpEng CPU); replaces background focus16.",
    (rm + ["--cams", "16", "--reps", "3", "--outdir-name", "focus16_av19"],
     rm + ["--cams", "1", "--reps", "1", "--duration", "2", "--outdir-name", "smoke_av19"]), 10, 25, watch=[WTB],
    outputs=f"{WTB}/focus16_av19/")
fr = UV + [f"{S}/write_throughput/first_read_check.py"]
add("WT-FIRST-READ", "write_throughput", 5,
    "Reduced usability check: first read of 5000 freshly written frame files vs one append file, two passes, wall time "
    "and MsMpEng CPU per pass (Defender cost of folder-of-files read-back).",
    (fr + ["--frames", "5000"], fr + ["--frames", "60"]), 4, 15, watch=[WTB],
    outputs=f"{WTB}/usability/first_read_check_5000.json")
add("WT-IDLE-AFTER", "write_throughput", 5, "Idle baseline again after the write cells.",
    (idle + ["--tag", "after_first_read_av19"], idle + ["--seconds", "2", "--out", "{SMOKE_OUT}/idle.jsonl"]), 0.6, 3,
    outputs=f"{WTB}/idle_baseline_av19.jsonl")

# =====================================================================================================================
# Appended 2026-11-09 19:45-20:30 (3 h cap removed, HANDOFF section 1 item 11). Priority groups 6-14, most important
# first. New stream-scaling items use 2 reps (the decisive 1080p NV12 items 4-11 have 3).
SP = "C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad"
E35 = "{REPO}/skellycam-ui/node_modules/electron/dist/electron.exe"  # runner substitutes {REPO}; a relative exe path fails in CreateProcess
E45 = ("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/"
       "shared/electron-latest/node_modules/electron/dist/electron.exe")  # the binary run_suite.py uses for --electron 45
PIB = "research/skellycam_recording/recording_upgrade/results/python_integration/bench"
JPB = "research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench"
OVB = "research/skellycam_recording/recording_upgrade/results/overlays/bench"
UIB = "research/skellycam_recording/recording_upgrade/results/uncompressed_intra/bench"


def scale_item(id_, prio, pid, size, source, est, tags, workers="thread", probe=0, reps=2, why=""):
    add(id_, "intra_compare", prio,
        f"Stream scaling at matched quality (A), {pid}, {size}30 from {source}, 1/4/8/16 streams "
        f"({'one spawned process' if workers == 'process' else 'one thread + encoder'} per stream, per-frame input work "
        f"in the loop), paced 30 fps + unpaced, {reps} reps" + (f"; session-limit probe to {probe}" if probe else "")
        + (f". {why}" if why else ""),
        scale(pid, workers=workers, reps=reps, probe=probe, size=size, source=source), est, round(2.2 * est + 3), tags=tags,
        outputs=f"{ICB}/matched_concurrent_{pid}_{size}_{source}_{workers}_<UTC>.json")


# ---- 6. decisive pending questions for G2 (container choice), G9 (scrub), G5 (threading model)
rw = UV + [f"{S}/python_integration/bench_recwriter.py"]
add("PI-RECWRITER-AV19", "python_integration", 6,
    "pi_recwriter_cost under PyAV 19.0.2 (python_integration FINDINGS section 5; the G2 container choice waits on it): "
    "(A) RecordingWriter.write() per-call median/p99/p99.9/max, mkv / fMP4 / avi vs folder of JPEGs, fsync off and every "
    "30, 720p + 1080p, 3000 frames; (B) RecorderThread.submit() cost, queue depth, drops, 5 cameras paced 30 and 60 fps "
    "for 60 s + byte-exact check; (C) cv2/PyAV open, frame count, mid-seek on a 10-min 720p MKV vs fMP4. ~3 GB temp "
    "under the media root, deleted.",
    (rw + ["--tag", "quiet1_pyav19"], rw + ["--tag", "smoke", "--quick"]), 12, 30, watch=[PIB],
    outputs=f"{PIB}/recwriter_quiet1_pyav19.json")
add("IP-SCRUB-E35", "intra_playback", 6,
    "Electron 35.7.5, N=4 and 8 at 1080p, 8 s simulated drag at 90 frames/s: <video> gated, WebCodecs (wcflush=1), "
    "JPEG Range + bitmap / ImageDecoder (.mjpeg and JPEG-in-MKV): frames shown and distinct per second, lag to the "
    "slider, CPU (G9 scrubbing; intra_playback NOTES section 8).",
    suite("35", "bench_intra_scrub"), 6, 20, tags=["electron", "nvidia"], watch=[IPB],
    outputs=f"{IPB}/e35/bench_intra_scrub/")
add("IP-SCRUB-E45", "intra_playback", 6, "Same in Electron 45.2.3.", suite("45", "bench_intra_scrub"), 6, 20,
    tags=["electron", "nvidia"], watch=[IPB], outputs=f"{IPB}/e45/bench_intra_scrub/")
add("IP-SUM-2", "intra_playback", 6, "Tables again, now including the scrub runs.", (sumc, sumc), 1, 5, watch=[IPB],
    outputs=f"{IPB}/bench_tables.md")
rp = UV + [f"{S}/crash_resilience/bench_repair.py", "--methods", "pyav_copy_mkv,resumable_repair"]
add("CR-REPAIR-PYAV19", "crash_resilience", 6,
    "cr_repair under PyAV 19.0.2 (bench_repair.py:38 interpreter fix applied): ~1 GB unfinalized recordings made by "
    "killing the writer before close (mkv+fp, fmp4 per-frame+fp, plain mp4, raw .mjpeg+index), then PyAV remux to MKV "
    "and the resumable prototype's segment repair, 3 repeats (first = cold, repeats = OS cache): seconds per GB, frames "
    "recovered (ffprobe count, inspection only). ffmpeg CLI repair rows left out (the CLI is not under test).",
    (rp + ["--gb", "1", "--repeats", "3", "--out-name", "pyav19"],
     rp + ["--gb", "0.02", "--repeats", "1", "--out-name", "smoke"]), 8, 25, watch=[CRB],
    outputs=f"{CRB}/repair_pyav19.json")
ol = UV + [f"{S}/jpeg_passthrough/bench_open_long.py"]
add("JP-OPEN-LONG-PYAV19", "jpeg_passthrough", 6,
    "VERIFY_method request bench_open_long: open time + frame count of a 30-min (54,000-frame) camera-JPEG recording in "
    "fMP4 1 s / per-frame / MP4 at 1/1e6 and MKV, for cv2 CAP_FFMPEG + CAP_PROP_FRAME_COUNT and PyAV open, plus a full "
    "PyAV demux count, 5 reps (FreeMoCap opens every file this way). About 12 GB written, then deleted.",
    (ol + ["--frames", "54000", "--reps", "5"], ol + ["--frames", "300", "--reps", "1"]), 10, 25, watch=[JPB],
    outputs=f"{JPB}/open_long.json")
rmm = UV + [f"{S}/write_throughput/run_matrix.py", "--set", "models", "--profiles", "1080p60",
            "--models", "thread,process_shared"]
add("WT-MODELS16-AV19", "write_throughput", 6,
    "Threading model for the plan (verifier request models16_av19_shared_vs_thread): {files, append, mkv_flush} x "
    "{thread, one shared writer process} at 16 x 1080p60 camera-MJPEG passthrough, 30 s, 3 reps: tick->written p99/max, "
    "queue occupancy, drops, CPU, MsMpEng CPU.",
    (rmm + ["--writers", "files,append,mkv_flush", "--cams", "16", "--duration", "30", "--reps", "3",
            "--outdir-name", "models16_av19_shared_vs_thread"],
     rmm + ["--writers", "files", "--cams", "4", "--duration", "2", "--reps", "1", "--outdir-name", "smoke_models_av19"]),
    14, 35, watch=[WTB], outputs=f"{WTB}/models16_av19_shared_vs_thread/")
# ---- 7. 4:2:2 stream scaling (the cameras deliver 4:2:2) + in-target G4 (NVENC lossless intra incl. Bayer8)
scale_item("IC-SCALE-jpeg_turbo_422-proc-yuy2", 7, "jpeg_turbo_422", "1080p", "yuy2", 6, [], workers="process",
           why="CPU JPEG 4:2:2 from the packed YUY2 frame, one process per stream")
scale_item("IC-SCALE-nvjpeg_422-yuy2", 7, "nvjpeg_422", "1080p", "yuy2", 4.5, ["nvidia"])
scale_item("IC-SCALE-mjpeg_qsv_422-yuy2", 7, "mjpeg_qsv_422", "1080p", "yuy2", 4.5, ["qsv"], probe=32,
           why="mjpeg_qsv takes yuyv422 natively")
scale_item("IC-SCALE-hevc_qsv_422-yuy2", 7, "hevc_qsv_422", "1080p", "yuy2", 6.5, ["qsv"],
           why="HEVC 4:2:2 intra on QSV, native yuyv422 input")
uis = UV + [f"{S}/uncompressed_intra/bench_suite.py", "--interp", "uv", "--tag", "_q2300"]  # tag: earlier contaminated
# PyAV 19 files (group pyav19) share names with some of these cases; untagged, the suite would skip them as existing
add("UI-GPU-AV19", "uncompressed_intra", 7,
    "G4, inside the hardware target: NVENC intra-only lossless (h264/hevc on NV12, hevc on P010, h264 on gray, hevc on "
    "Bayer8 as gray) and HEVC intra constant-QP, 1080p + 720p, single stream, under PyAV 19.0.2 (uncompressed_intra "
    "group 'gpu'; replaces the contaminated PyAV 18 rows): fps, CPU per frame, bytes/frame, decode fps.",
    (uis + ["--group", "gpu"], uis + ["--group", "gpu", "--frames", "10", "--reps", "1", "--warmup-frames", "2"]),
    6, 15, tags=["nvidia"], watch=[UIB], outputs=f"{UIB}/*nvenc*__pyav19.0.2_q2300.json")
# ---- 8. G3 overlay costs + G1 live-view decode cost of passthrough
OV_METHODS = ("sidecar_jsonl,sidecar_msgpack,sidecar_bin,sidecar_vtt,svg_per_frame,svg_single,ass,burnin_cv2,"
              "burnin_cv2_jpeg_roundtrip,jpeg_roundtrip_only,alpha_render")
ov = UV + [f"{S}/overlays/bench_overlay_cost.py", "--only", OV_METHODS]
add("OV-COST", "overlays", 8,
    "overlay_cost (uv env: numpy, opencv 4.12.0.88, msgspec 0.21.1; this script imports no PyAV): per-frame cost of "
    "vector sidecars (.skov binary, JSONL, MessagePack, WebVTT), SVG per frame / single SVG, ASS vs cv2 burn-in, burn-in "
    "with JPEG decode + re-encode, plain JPEG round trip and alpha rasterisation; cases text (today's stamp), "
    "skeleton(33), charuco(100), all (FreeMoCap-like); 720p + 1080p; bytes/hour. alpha_vp9_pipeline left out (CLI).",
    (ov + ["--frames", "900", "--repeats", "3"], ov + ["--frames", "20", "--repeats", "1", "--smoke"]), 12, 30,
    watch=[OVB], outputs=f"{OVB}/bench_overlay_cost_<UTC>.json")
HAR = f"{S}/overlays/electron_harness"
for ver, exe in (("35.7.5", E35), ("45.2.3", E45)):
    add(f"OV-DRAW-E{ver[:2]}", "overlays", 8,
        f"electron_draw: UI render cost per frame in Electron {ver} for the full overlay (33-point skeleton + 100 ChArUco "
        "corners): canvas with deterministic label layout, naive labels, no labels, SVG DOM replacement; 5 reps.",
        ([exe, HAR, "--tests=drawbench", "--mode=bench", "--query=reps=5", f"--out={OVB}/electron_drawbench_{ver}.json"],
         [exe, HAR, "--tests=drawbench", "--mode=bench", "--query=reps=1", f"--out={{SMOKE_OUT}}/drawbench_{ver}.json"]),
        3, 10, tags=["electron"], watch=[OVB], outputs=f"{OVB}/electron_drawbench_{ver}.json")
DLL = f"{SP}/jpeg_passthrough/ljt321/bin/turbojpeg.dll"
jd = UV + [f"{S}/python_integration/bench_jpeg_decode.py", "--turbojpeg-dll", DLL]
add("PI-JPEG-DECODE-PYAV19", "python_integration", 8,
    "pi_jpeg_decode_cpu under PyAV 19.0.2 (header pin changed from 18.0.0): live-view decode cost of passthrough on the "
    "real camera JPEGs (720p x2, 1080p x3): cv2.imdecode full and reduced/2, simplejpeg default / fast / min_h360 / "
    "into-buffer, PyTurboJPEG full and 1/2 (libjpeg-turbo 3.2.1 official DLL, already extracted: no download at run "
    "time), PyAV mjpeg bgr24 and native YUV; 1 vs 5 threads aggregate (GIL).",
    (jd + ["--tag", "quiet1_pyav19"], jd + ["--tag", "smoke", "--quick"]), 12, 30, watch=[PIB],
    outputs=f"{PIB}/jpeg_decode_quiet1_pyav19.json")
nd = UV + [f"{S}/python_integration/bench_nvjpeg_decode.py"]
add("PI-NVJPEG-DECODE", "python_integration", 8,
    "pi_nvjpeg_decode: nvJPEG (nvImageCodec 0.9.0.20) decode of the same camera JPEGs: single frame to GPU, to host "
    "numpy, batch of 5 (5 cameras); nvidia-smi before/after. This script imports no PyAV.",
    (nd + ["--tag", "quiet1_2300"], nd + ["--tag", "smoke", "--quick"]), 5, 15, tags=["nvidia"], watch=[PIB],
    outputs=f"{PIB}/nvjpeg_decode_quiet1_2300.json")
# ---- 9. realistic recorder pipelines: camera MJPEG decoded (CPU or mjpeg_qsv) and re-encoded; YUY2 source
scale_item("IC-SCALE-h264_nvenc_420-mjpeg_cpu", 9, "h264_nvenc_420", "1080p", "mjpeg_cpu", 5.5, ["nvidia"],
           why="Camera MJPEG decoded on the CPU in each stream's loop, then NVENC H.264 intra")
scale_item("IC-SCALE-hevc_nvenc_420-mjpeg_cpu", 9, "hevc_nvenc_420", "1080p", "mjpeg_cpu", 5.5, ["nvidia"],
           why="Camera MJPEG CPU decode, then NVENC HEVC intra")
scale_item("IC-SCALE-h264_qsv_420-mjpeg_qsv", 9, "h264_qsv_420", "1080p", "mjpeg_qsv", 5.5, ["qsv"],
           why="Camera MJPEG decoded by mjpeg_qsv, then QSV H.264 intra (all on the iGPU)")
scale_item("IC-SCALE-hevc_qsv_420-mjpeg_qsv", 9, "hevc_qsv_420", "1080p", "mjpeg_qsv", 7, ["qsv"],
           why="Camera MJPEG decoded by mjpeg_qsv, then QSV HEVC intra")
scale_item("IC-SCALE-h264_nvenc_420-yuy2", 9, "h264_nvenc_420", "1080p", "yuy2", 4.5, ["nvidia"],
           why="YUY2 camera source: swscale yuyv422 -> NV12 limited range in each stream's loop, then NVENC")
# ---- 10. the QSV-encoded files left out of IP-SYNC (decoder side of the QSV encode paths)
for ver in ("35", "45"):
    add(f"IP-SYNC-QSV-E{ver}", "intra_playback", 10,
        f"The QSV-encoded H.264/HEVC intra files trimmed from IP-SYNC-E{ver} (--only _qsv_): N=4/8 1080p sync spread, "
        "drops, CPU, working set for <video> free / rVFC and WebCodecs master clock. Same output folder; own index file.",
        (UV + [f"{S}/chromium_sync_scrub/run_suite.py", "--electron", ver, "--suite", "bench_intra_sync", "--only", "_qsv_"],
         UV + [f"{S}/chromium_sync_scrub/run_suite.py", "--electron", ver, "--suite", "bench_intra_sync", "--smoke",
               "--only", "_qsv_"]), 6, 20, tags=["electron", "nvidia"], watch=[IPB],
        outputs=f"{IPB}/e{ver}/bench_intra_sync/")
add("IP-SUM-3", "intra_playback", 10, "Tables again, including the QSV-file sync runs.", (sumc, sumc), 1, 5,
    watch=[IPB], outputs=f"{IPB}/bench_tables.md")
# ---- 11. 720p stream scaling (NV12 source)
for pid, tags, est, workers in [("h264_nvenc_420", ["nvidia"], 3.5, "thread"), ("hevc_nvenc_420", ["nvidia"], 3.5, "thread"),
                                ("h264_qsv_420", ["qsv"], 3.5, "thread"), ("hevc_qsv_420", ["qsv"], 4.5, "thread"),
                                ("mjpeg_qsv_420", ["qsv"], 3.5, "thread"), ("nvjpeg_420", ["nvidia"], 3.5, "thread"),
                                ("jpeg_turbo_420", [], 5, "process")]:
    scale_item(f"IC-SCALE720-{pid}" + ("-proc" if workers == "process" else ""), 11, pid, "720p", "nv12", est, tags,
               workers=workers)
# ---- 12. G4 outside the hardware target (CPU lossless fallback), PyAV 19.0.2
LOSSLESS = "rawvideo.nut,ffv1_l3_s4_crc_g1.mkv,ffv1_l3_s24_crc_g1.mkv"
add("UI-BAYER-AV19", "uncompressed_intra", 12,
    "G4, OUTSIDE the hardware target (no RTX 3000 / QSV encoder takes Bayer, apart from NVENC lossless on Bayer8-as-gray "
    "in UI-GPU-AV19): Bayer 1080p storage cost under PyAV 19.0.2: 12-bit mosaic packed as gray16le and 8-bit mosaic, "
    "rawvideo vs FFV1 v3 4 / 24 slices, 1 thread and all threads.",
    (uis + ["--group", "bayer", "--sources", "bayer12,bayer8", "--configs", LOSSLESS],
     uis + ["--group", "bayer", "--sources", "bayer12,bayer8", "--configs", LOSSLESS, "--frames", "10", "--reps", "1",
            "--warmup-frames", "2"]), 8, 20, watch=[UIB], outputs=f"{UIB}/*bayer*__pyav19.0.2_q2300.json")
add("UI-CORE-AV19", "uncompressed_intra", 12,
    "G4, OUTSIDE the hardware target: lossless NV12 / YUY2 1080p storage cost under PyAV 19.0.2: rawvideo vs FFV1 v3 "
    "4 / 24 slices, 1 thread and all threads (the JPEG / H.264 / HEVC intra points for NV12/YUY2 are items 1-3).",
    (uis + ["--group", "core_1080p", "--sources", "yuyv422,nv12", "--configs", LOSSLESS],
     uis + ["--group", "core_1080p", "--sources", "yuyv422,nv12", "--configs", LOSSLESS, "--frames", "10", "--reps",
            "1", "--warmup-frames", "2"]), 8, 20, watch=[UIB], outputs=f"{UIB}/*__pyav19.0.2_q2300.json")
uisum = UV + [f"{S}/uncompressed_intra/bench_summary.py"]
add("UI-SUM", "uncompressed_intra", 12, "Aggregate the uncompressed_intra bench JSONs (PyAV 18 and 19 rows) into "
    "bench_summary.md.", (uisum, uisum), 0.5, 3, watch=[UIB], outputs=f"{UIB}/bench_summary.md")
# ---- 13. remaining passthrough / durability / write-matrix items
add("JP-MUX-FSYNC-PYAV19", "jpeg_passthrough", 13,
    "jp_mux_cost_fsync under PyAV 19.0.2: as item 17 but with FlushFileBuffers after close (close cost includes getting "
    "the data to disk), 13 containers incl. fMP4 1/1e6, 720p + 1080p, 3000 frames, 5 reps.",
    (mux + ["--fsync", "--tag", "fsync_pyav19"], mux + ["--fsync", "--frames", "30", "--reps", "1", "--tag", "smoke"]),
    10, 25, watch=[JPB], outputs=f"{JPB}/bench_mux_fsync_pyav19_<UTC>.json")
rot = UV + [f"{S}/jpeg_passthrough/bench_rotate.py", "--lib", DLL]
add("JP-ROTATE", "jpeg_passthrough", 13,
    "jp_rotate_cost: lossless JPEG rotation (libjpeg-turbo 3.2.1 tj3Transform via ctypes, as skellycam-rust "
    "jpeg_transform.rs) rot90/180/270 on real 720p and 1080p camera JPEGs, 1000 frames x 5 reps, single thread. DLL "
    "copied to the study scratchpad (sha256 recorded in the JSON). No PyAV.",
    (rot, rot + ["--frames", "20", "--reps", "1"]), 3, 10, watch=[JPB], outputs=f"{JPB}/bench_rotate_<UTC>.json")
foi = UV + [f"{S}/crash_resilience/bench_fragment_overhead.py", "--payloads", "h264nv_intra,hevcnv_intra"]
add("CR-FRAG-INTRA-PYAV19", "crash_resilience", 13,
    "cr_fragment_overhead for intra-only H.264 / HEVC NVENC packets (new payloads: matched-settings target A options, "
    "gop 0) to compare with item 19's MJPEG: mkv / +fp / cluster 0, fMP4 per frame / per keyframe / 100-2000 ms, mp4, "
    "nut, segments; CPU, wall, size. Packets encoded once, untimed.",
    (foi + ["--frames", "3000", "--repeats", "3", "--out-name", "intra_pyav19"],
     foi + ["--frames", "60", "--repeats", "1", "--out-name", "smoke"]), 9, 22, tags=["nvidia"], watch=[CRB],
    outputs=f"{CRB}/fragment_overhead_intra_pyav19.json")
rmc = UV + [f"{S}/write_throughput/run_matrix.py", "--set", "core", "--writers", "files,append,mkv_flush,fmp4_frame_flush"]
add("WT-CORE-AV19", "write_throughput", 13,
    "Broader core matrix for the passthrough writers (folder / append+index / MKV flush / fMP4 per-frame flush) x "
    "1/4/8/16 cams x 720p30 + 1080p30, thread model, 20 s cells, 1 rep (scaling below the 16 x 1080p60 worst case).",
    (rmc + ["--cams", "1,4,8,16", "--profiles", "720p30,1080p30", "--duration", "20", "--outdir-name", "core_av19"],
     rmc + ["--cams", "1", "--profiles", "720p30", "--duration", "2", "--outdir-name", "smoke_core_av19"]), 18, 40,
    watch=[WTB], outputs=f"{WTB}/core_av19/")
add("WT-CORE60-AV19", "write_throughput", 13,
    "Same writers at 1/4/8 cams x 1080p60 (16 x 1080p60 is item 21), 20 s cells, 1 rep.",
    (rmc + ["--cams", "1,4,8", "--profiles", "1080p60", "--duration", "20", "--outdir-name", "core_av19"],
     rmc + ["--cams", "1", "--profiles", "1080p60", "--duration", "2", "--outdir-name", "smoke_core_av19"]), 7, 18,
    watch=[WTB], outputs=f"{WTB}/core_av19/")
add("WT-IDLE-AFTER2", "write_throughput", 13, "Idle baseline after the extra write cells.",
    (idle + ["--tag", "after_core_av19"], idle + ["--seconds", "2", "--out", "{SMOKE_OUT}/idle.jsonl"]), 0.6, 3,
    outputs=f"{WTB}/idle_baseline_av19.jsonl")
# ---- 14. lowest priority
for ver, exe in (("35.7.5", E35), ("45.2.3", E45)):
    add(f"OV-PLAY-E{ver[:2]}", "overlays", 14,
        f"electron_play_quiet: quiet-machine rerun of the load-sensitive overlay alignment tests in Electron {ver} "
        "(canvas-over-video vs canvas-composite captures, today's rAF rule, paused-seek convergence, WebVTT cue lag, "
        "dual-video alpha sync). Same readback-heavy harness (the overlays FINDINGS 2.3 confounder remains).",
        ([exe, HAR, "--tests=play,seek,vtt,alpha", f"--out={OVB}/electron_play_quiet_{ver}.json"],
         [exe, HAR, "--tests=play", f"--out={{SMOKE_OUT}}/play_{ver}.json"]), 6, 15, tags=["electron"], watch=[OVB],
        outputs=f"{OVB}/electron_play_quiet_{ver}.json")
us = UV + [f"{S}/write_throughput/bench_usability.py", "--formats", "files,files_subdirs,append,mkv_flush,fmp4_frame_flush"]
add("WT-USABILITY-18K", "write_throughput", 14,
    "Reduced usability_1h: after-recording cost of an 18,000-frame (10 min) single-camera 720p30 recording per format: "
    "build, frame table, sequential read, 1000 random frame-accurate reads, first image, copy (shutil + robocopy /MT:8), "
    "delete (warm cache). WT-FIRST-READ covers the Defender first-read part.",
    (us + ["--frames", "18000", "--robocopy"],
     us + ["--frames", "200", "--random-reads", "20", "--json-out", "{SMOKE_OUT}/usability_smoke.json"]), 10, 25,
    watch=[WTB], outputs=f"{WTB}/usability/usability_18000.json")
add("WT-LONG-AV19", "write_throughput", 14,
    "Sustained 10-minute cells at 16 x 1080p60 for files / append / mkv_flush (about 94 GB each, deleted after each "
    "cell; built-in >240 GB free guard): SSD cache, lazy writer, Defender steady state.",
    (UV + [f"{S}/write_throughput/run_matrix.py", "--set", "long", "--outdir-name", "long_av19"],
     UV + [f"{S}/write_throughput/run_matrix.py", "--set", "long", "--writers", "files", "--duration", "2",
           "--outdir-name", "smoke_long_av19"]), 35, 60, watch=[WTB], outputs=f"{WTB}/long_av19/")

q = {
    "name": "recording upgrade study, 23:00 timed queue (2026-11-09)",
    "generated_by": f"{S}/bench_runner/make_queue.py",
    "runner": f"uv run --script {S}/bench_runner/run_queue.py",
    "deadline": "05:00",
    "avoid_windows": [{"start": "01:55", "end": "02:30",
                       "why": "Defender daily scheduled quick scan at 02:00 (Get-MpPreference ScanScheduleDay 0, "
                              "ScanScheduleTime 02:00:00, ScanParameters 1; read 2026-11-09 18:54)"}],
    "rules": ["items 1-23 = decisive set (unchanged); items 24+ appended after the 3 h cap was removed, in priority order",
              "one item at a time", "PyAV 19.0.2 via uv run --script PEP 723 pins only", "no timing from smoke runs",
              "background load recorded before each item; flag mean CPU > 15 %"],
    "total_est_minutes": round(sum(i["est_minutes"] for i in items), 1),
    "items": items,
}
out = STUDY / "results/bench_queue_2300.json"
out.write_text(json.dumps(q, indent=1), encoding="utf-8")
print("wrote", out, "items", len(items), "total est", q["total_est_minutes"])
