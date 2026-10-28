"""Rewrites study_state/recommend_result.json from the corrected evidence (REVISION stage, 2026-10-28) and writes
study_state/revision_result.json. Reads the revision benchmark outputs so the quoted numbers come from the files.
The pre-revision recommendation is kept as study_state/recommend_result_pre_revision.json.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\update_recommendation.py
"""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import numpy as np

FP = Path(__file__).resolve().parents[1]
SS = FP / "study_state"
BR = FP / "baseline" / "results"
PR = FP / "prototypes" / "results"
SK = "https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/"
FM = "https://github.com/freemocap/freemocap/blob/5632778af10e22befd4ec0a719ba844f14a84e93/"


def ref(repo, path, a, b=None):
    b = b or a
    base = SK if repo == "skellycam" else FM
    return dict(repo=repo, path=path, lines=f"{a}-{b}" if b != a else f"{a}", permalink=f"{base}{path}#L{a}" + (f"-L{b}" if b != a else ""))


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- numbers from the revision outputs
p12 = load(PR / "p12_disk_sustained.json")
rows12 = {r["phase"]: r for r in p12["rows"]}
A, B1, B2, C = rows12["A"], rows12.get("B1"), rows12.get("B2"), rows12.get("C")
cliff = next((i for i, v in enumerate(A["mb_per_s_per_gib"]) if v < 2000), None)
p12_txt = (f"P12 (prototypes/results/p12_disk_sustained.md; script prototypes/p12_disk_sustained.py; idle): C: had "
           f"{p12['free_bytes_at_start'] / 1e9:.1f} GB free ({p12['used_pct_at_start']}% used). 64 GiB unbuffered write-through ran at "
           f"about 5 GB/s for the first {cliff} GiB, then {min(A['mb_per_s_per_gib'][cliff:]):.0f}-{max(A['mb_per_s_per_gib'][cliff:]):.0f} MB/s "
           f"(SLC cache exhausted). With the cache exhausted, 5 paced write-through streams at 162 MB/s for 300 s achieved "
           f"{B1['achieved_mb_per_s']:.1f} MB/s, write() max {B1['worst_write_call']['max_ms']:.0f} ms, worst stream "
           f"{B1['worst_lag_behind_schedule_ms']:.0f} ms behind schedule")
if B2:
    p12_txt += (f"; at 69 MB/s for 600 s: {B2['achieved_mb_per_s']:.1f} MB/s, write() max {B2['worst_write_call']['max_ms']:.0f} ms, worst lag "
                f"{B2['worst_lag_behind_schedule_ms']:.0f} ms")
if C:
    p12_txt += (f"; buffered writes at 162 MB/s for 60 s then FlushFileBuffers: flush took up to {C['max_flush_s']:.2f} s, worst lag "
                f"{C['worst_lag_behind_schedule_ms']:.0f} ms")
p12_txt += (f". Time to fill the free space: {p12['time_to_full_at_rate_min']['69']} min at 69 MB/s (HEAD MSMF 5x1080p), "
            f"{p12['time_to_full_at_rate_min']['162']} min at 162 MB/s (MJPEG passthrough).")
worst_disk_stall_ms = max(r["worst_write_call"]["max_ms"] for r in (B1, B2, C) if r)
worst_lag_ms = max(r["worst_lag_behind_schedule_ms"] for r in (B1, B2, C) if r)

hd = load(BR / "h_deflate.json")
hd1080 = next(r for r in hd["rows"] if r["size"] == "1080p")
hd720 = next(r for r in hd["rows"] if r["size"] == "720p")
deflate_txt = (f"baseline/results/h_deflate.md (script baseline/bench_h_deflate.py, idle 2026-10-28): websockets "
               f"{hd['websockets_version']} PerMessageDeflate with uvicorn's defaults on a real create_frontend_payload payload: 1080p "
               f"{hd1080['payload_bytes_median'] / 1e3:.0f} KB -> {hd1080['deflated_bytes_median'] / 1e3:.0f} KB in "
               f"{hd1080['deflate']['median_ms']:.2f} ms median ({hd1080['deflate']['p99_ms']:.2f} p99); 720p "
               f"{hd720['payload_bytes_median'] / 1e3:.0f} KB in {hd720['deflate']['median_ms']:.2f} ms. The synthetic content deflates far more than camera JPEGs would, so the ratio is not representative; the time is. Whether a browser negotiates it was not checked.")

p6 = {}
for tag, f in (("orig", PR / "p6_ui_skellycamvenv.json"), ("repro", FP / "reproducibility/rerun/prototypes/results/p6_ui_skellycamvenv.json"),
               ("rev2", PR / "p6_ui_skellycamvenv_rev_rep2.json"), ("rev3", PR / "p6_ui_skellycamvenv_rev_rep3.json")):
    if f.exists():
        for r in load(f)["rows"]:
            p6.setdefault((r["size"], r["variant"]), []).append(r["payloads_per_s"])


def p6r(size, v):
    a = p6.get((size, v), [])
    return f"{min(a):.1f}-{max(a):.1f}/s over {len(a)} runs" if a else "n/a"


dsv = BR / "e2ev_dshowlike_1080p_mjpeg_ui_v2.json"
gap = load(BR / "e2ev_gap_detector.json")
ds_txt = ""
if dsv.exists():
    d = load(dsv)
    g = gap.get("e2ev_dshowlike_1080p_mjpeg_ui_v2", {})
    ds_txt = (f" A stand-in with the P9 timing (grab returns at once, retrieve waits for the frame; e2ev_dshowlike_1080p_mjpeg_ui_v2) gave "
              f"{min(c['achieved_fps'] for c in d['per_camera'].values()):.2f} fps and "
              f"{sum(c['sensor_frames_never_grabbed'] for c in d['per_camera'].values())} never grabbed; there the grab stamps spread "
              f"{g.get('grab_spread_p99_ms', float('nan')):.2f} ms p99 across cameras while the frames' capture times spread "
              f"{g.get('tick_spread', {}).get('median_ms', float('nan')):.1f} ms median / {g.get('tick_spread', {}).get('max_ms', float('nan')):.1f} ms max.")

e2ev = {f.stem: load(f) for f in BR.glob("e2ev_*_1080p_*.json")}


def fps(n):
    return min(c["achieved_fps"] for c in e2ev[n]["per_camera"].values())


def ng(n):
    return sum(c["sensor_frames_never_grabbed"] for c in e2ev[n]["per_camera"].values())


def cpu(n):
    return e2ev[n]["cpu_pct_mean_during_recording"]["sum_child_processes"]


H, N1, N2, T1, NT, X3, NU = ("e2ev_head_1080p_mjpeg_ui", "e2ev_nocopycopy_1080p_mjpeg_ui", "e2ev_nocopycopy_1080p_mjpeg_ui_rep2",
                             "e2ev_cvthreads1_1080p_mjpeg_ui", "e2ev_nocopycopy+cvthreads1_1080p_mjpeg_ui", "e2ev_extracpu3_1080p_mjpeg_ui",
                             "e2ev_head_1080p_mjpeg_noui_rep2")
E2EV = "baseline/results/e2ev_summary.md and e2ev_*.json (script baseline/bench_e2e_variants.py <variant> 1080p mjpeg ui 30, driver revision/run_revision.py e2ev; idle 2026-10-28)"
G = gap
det_txt = (f"Offline check against the true count (baseline/results/e2ev_gap_detector.md, script baseline/analyze_gap_detector.py): the per-interval "
           f"round(dt/T)-1 formula finds {G[H]['detectors']['per_interval_round|pre_frame_grab_ns']} of {G[H]['true_never_grabbed']} at HEAD, "
           f"{G[N1]['detectors']['per_interval_round|pre_frame_grab_ns']} of {G[N1]['true_never_grabbed']} and "
           f"{G[X3]['detectors']['per_interval_round|pre_frame_grab_ns']} of {G[X3]['true_never_grabbed']} in other runs; the accumulated clock finds "
           f"{G[H]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[H]['true_never_grabbed']}, "
           f"{G[N1]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[N1]['true_never_grabbed']}, "
           f"{G[N2]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[N2]['true_never_grabbed']}, "
           f"{G[T1]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[T1]['true_never_grabbed']}, "
           f"{G[X3]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[X3]['true_never_grabbed']} and "
           f"{G[NU]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {G[NU]['true_never_grabbed']} (sums over 5 cameras).")

p8v = {f.stem: load(f) for f in PR.glob("p8v_e2e_*.json")}
LM1, LM2, LRT, LX3, SPR = ("p8v_e2e_1080p_imdecode_msmf_lockstep_meta", "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_rep2",
                           "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_recthread", "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_extracpu3",
                           "p8v_e2e_1080p_imdecode_msmf_spread")
P8V = "prototypes/results/p8v_e2e_summary.md and p8v_e2e_*.json (script prototypes/p8_e2e_proto.py 1080p imdecode msmf 30 with P8_LOCKSTEP=1 P8_META=1 [P8_RECTHREAD=1 | P8_EXTRA_CPU_MS=3], driver revision/run_revision.py p8v; idle 2026-10-28)"


def p8f(n):
    return f"{p8v[n]['min_cam_fps']:.2f}"


def p8n(n):
    return p8v[n]["sensor_never_grabbed_total"]


def tw99(n):
    return max(r["tick_to_written"]["p99_ms"] for r in p8v[n]["recorders"])


p10v = load(PR / "p10v_msmf_threads.json")
r10 = {(r["threads"], r["mode"]): r for r in p10v["rows"]}
p11 = load(PR / "p11_crash_container.json")
r11 = {(r["size"], r["kind"], r["mode"]): r for r in p11["rows"]}
p3v = load(PR / "p3v_asymmetric_stall.json")

# ---------------------------------------------------------------- start from the pre-revision recommendation
src = SS / "recommend_result.json"
pre = SS / "recommend_result_pre_revision.json"
if not pre.exists():
    shutil.copy(src, pre)
old = load(pre)
recs = {r["rank"]: copy.deepcopy(r) for r in old["recommendations"]}

# ---- rank 1 (contain failures)
r = recs[1]
r["change"] = (
    "(a) skellycam/api/websocket/websocket_server.py WebsocketServer._frontend_image_relay L271-274 (and the other ws tasks): on an unexpected "
    "Exception, log it, close this connection and end the task. Do not set global_kill_flag. (b) CameraGroupSharedMemory.get_latest_multiframe "
    "(camera_group_shared_memory.py L138-140): on a cross-camera frame_number mismatch, return None (skip this payload) instead of raising ValueError. "
    "(c) FreeMoCap realtime nodes call ipc.kill_everything() on any exception (camera_node.py L349-352, realtime_aggregator_node.py L833-839, "
    "realtime_skeleton_inference_node.py L152, L260, L270, L319): call PipelineIPC.shutdown_pipeline() (pipeline_ipc.py L63-65) instead of "
    "kill_everything() (L67-70), so an analysis fault stops the pipeline, not capture. (d) Split the abort signal from a drain-then-stop state. "
    "Today rank 1(d)'s original form (finalize after the kill flag) cannot work: once global_kill_flag is set, CameraGroupIPC.should_continue is "
    "False (camera_group_ipc.py L47-53), so the camera loops have already exited (opencv_camera_loop.py L43); stop_recording's pause waits on "
    "all_cameras_paused with no timeout (camera_group.py L218, camera_orchestrator.py L58-67); finalize_recording's loop is guarded by "
    "should_continue and then raises 'Not all cameras finished' (camera_group.py L317-379); the timestamps exist only in the "
    "RecordingFinishedMessage (handle_recording_updates.py L50-59). Define ONE graceful-stop path that every camera-side error and every "
    "non-camera fault goes through: set a 'stop_recording_requested' flag (not the kill flag), let every camera record up to the same "
    "last_recording_frame_number, drain and release the recorders, then set the kill flag. Give pause and finalize timeouts, write per-frame "
    "timestamps incrementally to CSV (moved forward from rank 7) so finalize can run from the files on disk, and make "
    "WorkerRegistry.shutdown_all (worker_registry.py L161-207, 3 s join then TerminateProcess) wait for a 'recorders released' signal before "
    "terminate. Rank 3's CameraDisconnected, rank 4's guards and rank 11's slot-mismatch check must use this path, not raise into "
    "kill_everything (opencv_camera_loop.py L119-123). (e) Add a fault-injection test: raise inside the relay, inside a FreeMoCap node and inside "
    "one camera loop mid-recording; assert every camera's file holds the same frame-number range, the CSVs exist and the finalizer ran.")
r["code_refs"] = [
    ref("skellycam", "skellycam/api/websocket/websocket_server.py", 262, 276),
    ref("skellycam", "skellycam/core/ipc/shared_memory/camera_group_shared_memory.py", 129, 141),
    ref("skellycam", "skellycam/core/camera_group/camera_group_ipc.py", 47, 53),
    ref("skellycam", "skellycam/core/camera_group/camera_group.py", 215, 238),
    ref("skellycam", "skellycam/core/camera_group/camera_group.py", 317, 379),
    ref("skellycam", "skellycam/core/camera_group/camera_orchestrator.py", 58, 67),
    ref("skellycam", "skellycam/core/camera/opencv/opencv_helpers/handle_recording_updates.py", 50, 59),
    ref("skellycam", "skellycam/core/ipc/process_management/worker_registry.py", 83, 109),
    ref("skellycam", "skellycam/core/ipc/process_management/worker_registry.py", 161, 207),
    ref("skellycam", "skellycam/core/camera/opencv/opencv_camera_loop.py", 119, 130),
    ref("freemocap", "freemocap/core/pipeline/abcs/pipeline_ipc.py", 63, 70),
    ref("freemocap", "freemocap/core/pipeline/realtime/camera_node.py", 349, 352),
    ref("freemocap", "freemocap/core/pipeline/realtime/realtime_aggregator_node.py", 833, 839),
    ref("freemocap", "freemocap/core/pipeline/realtime/realtime_skeleton_inference_node.py", 152),
    ref("freemocap", "freemocap/core/pipeline/realtime/realtime_skeleton_inference_node.py", 260, 270),
    ref("freemocap", "freemocap/core/pipeline/realtime/realtime_skeleton_inference_node.py", 319),
]
r["expected_impact"] = ("ESTIMATE (not benchmarked): removes every code path by which a display or analysis exception truncates an in-progress "
                        "recording, and gives camera faults a stop that ends all cameras on the same frame number with timestamps on disk. No "
                        "benchmark exercised these faults: the baseline e2e UI stand-in catches every exception instead of setting the kill flag "
                        "(baseline/bench_e_e2e.py ui_task), so fault behaviour was excluded by construction, not observed as absent.")
r["evidence"] = ("Code: websocket_server.py L271-274 sets global_kill_flag; worker_registry.py L102-107 SIGTERMs its own PID when the flag is set "
                 "(TerminateProcess on Windows); pipeline_ipc.py L67-70 sets global_kill_flag; kill_everything call sites at freemocap 5632778a "
                 "(git grep): camera_node.py L351, realtime_aggregator_node.py L838, realtime_skeleton_inference_node.py L152/260/270/319. Why the "
                 "original (d) cannot work: camera_group_ipc.py L47-53, camera_group.py L218 and L328-368, camera_orchestrator.py L58-67 (critic "
                 "priorities issue 3, verified against the code in this stage). Crash consequence for the file: see rank 2 (P11).")
r["effort"] = "M-L"

# ---- NEW rank 2: crash-tolerant files, drain-aware shutdown, free-space guard
msmf_k = r11[("1080p", "msmf_mp4", "killed_idle")]
mkv_k = r11[("1080p", "mjpeg_mkv", "killed_idle")]
mkv_m = r11[("1080p", "mjpeg_mkv", "killed_mid")]
nv_k = r11[("1080p", "nvenc_mkv", "killed_idle")]
new2 = dict(
    rank=2, previous_rank=None,
    title="Make a crash or forced stop cost seconds, not the whole file: crash-tolerant containers, drain-aware shutdown, free-space guard",
    priorities_served=["P1"],
    change=("(a) Stop writing non-fragmented MP4. SkellyCam's default writer is cv2 'X264' -> .mp4 (camera_config.py L29, "
            "fourcc_codec_helpers.py L54-58), whose index (moov) is written only at release(). Record into MKV (PyAV) or fragmented MP4 "
            "(movflags=frag_keyframe+empty_moov), or roll segments every N seconds. (b) Drain-aware shutdown: WorkerRegistry.shutdown_all joins each "
            "worker for 3 s after setting the kill flag, then calls terminate() (worker_registry.py L161-207). With a decoupled recorder (rank 7) "
            "holding up to 2.87 s of 1080p backlog, release must happen before that deadline: wait for a per-camera 'recorder released' flag, and "
            "only then terminate. (c) Free-space guard: refuse to start (or stop gracefully via rank 1's path) when the free space is below "
            "the expected recording size plus a margin; show the remaining minutes in the UI. (d) For NVENC (rank 14), flush the encoder on stop "
            "and accept that a hard kill loses the frames inside the encoder."),
    code_refs=[ref("skellycam", "skellycam/core/camera/config/camera_config.py", 29),
               ref("skellycam", "skellycam/core/recorders/videos/fourcc_codec_helpers.py", 52, 58),
               ref("skellycam", "skellycam/core/recorders/videos/video_recorder.py", 116, 130),
               ref("skellycam", "skellycam/core/ipc/process_management/worker_registry.py", 161, 207),
               ref("skellycam", "skellycam/core/camera/opencv/opencv_camera_loop.py", 124, 127)],
    expected_impact=(f"Measured (P11): after TerminateProcess the default MSMF .mp4 had {msmf_k['cv2_frames_decoded']} of 300 frames readable "
                     f"at both sizes, killed idle or mid-write; MJPEG-in-MKV had {mkv_k['cv2_frames_decoded']} of 300 (idle) and "
                     f"{mkv_m['cv2_frames_decoded']} (killed mid-write, more frames written); NVENC in MKV {nv_k['cv2_frames_decoded']} of 300 "
                     "(the frames still inside the encoder are lost). Disk: a recording fills the 224.9 GB free in about 54 min at the HEAD "
                     "5x1080p MSMF rate and 23 min with MJPEG passthrough (P12)."),
    evidence=("prototypes/results/p11_crash_container.md (script prototypes/p11_crash_container.py, driver revision/run_revision.py p11; idle "
              "2026-10-28; reproduces the priorities critic's one-off test, critic_p1/out/crash_container_test.json, inside the benchmark tree and "
              "adds fragmented MP4 and NVENC). " + p12_txt),
    risks_tradeoffs=("MKV / fragmented MP4 must be checked against FreeMoCap's posthoc reader (cv2.VideoCapture in video_node.py) - not tested. "
                     "Fragmented MP4 written by PyAV NVENC was readable by cv2 up to the last fragment, but PyAV raised on the truncated tail "
                     "(P11 rows nvenc_fmp4): readers must tolerate a truncated last fragment. Segmenting adds files to manage."),
    effort="S-M")

# ---- old rank 2 (stale frame) -> 3
r = recs[2]
r["change"] += (" Bound the skip: if no grab succeeds for about 1 s while recording, take rank 1's graceful stop (all cameras end on the same "
                "frame number) instead of holding every camera at the lockstep gate indefinitely; expose failed_grabs live in the UI.")
r["code_refs"].append(ref("skellycam", "skellycam/core/camera_group/camera_orchestrator.py", 96, 109))
r["risks_tradeoffs"] += (" While one camera skips, lockstep holds the others at the gate (camera_orchestrator.py L96-109), so all cameras pause "
                         "together; that keeps frame numbers aligned (P3 ASYM) but must be bounded, hence the 1 s limit.")

# ---- old rank 3 (guard recording state) -> 4
r = recs[3]
r["title"] = "Guard recording state: no config apply, no inline reopen, no 3-frame start race, no pause at stop while recording"
r["change"] += (" (d) stop_recording also pauses every camera while recording is active (camera_group.py L215-232; paused loops never grab, "
                "opencv_camera_loop.py L60-65). Publish last_recording_frame_number = max(frame_count) + margin while the cameras run, and check "
                "on arrival (the mirror of (c)).")
r["code_refs"].append(ref("skellycam", "skellycam/core/camera/opencv/opencv_camera_loop.py", 60, 65))
r["expected_impact"] = ("ESTIMATE for (a)-(c) (not benchmarked). (d) measured small: in 8 real-stack runs at 5x1080p the last 10 recorded frames "
                        "of every camera showed at most 1 skipped sensor tick between consecutive frames (sum 0-14 over 50 camera-frames, vs "
                        "0.02-0.24 per camera-frame elsewhere in the same runs), so today's stop pause costs about one sensor frame per camera, "
                        "silently.")
r["evidence"] += " Stop gap: baseline/results/e2ev_gap_detector.md columns 'skipped ticks in last 10 recorded frames' (script baseline/analyze_gap_detector.py on the e2ev_*_perframe.npz dumps)."

# ---- old rank 4 (count drops) -> 5
r = recs[4]
r["change"] = ("In run_opencv_camera_loop, keep the first post_frame_retrieve_ns of the recording and the frame count, and compute "
               "missed = round((t_now - t_first) / T) + 1 - frames_recorded, with T from config.framerate (an accumulated clock; the per-interval "
               "max(0, round(dt/T) - 1) formula proposed before cannot see a loop that is uniformly slow, because round(18.7/16.7) = 1). Publish it "
               "in CameraStatus (camera_status.py L8-31) and the UI framerate message, store it in the recording metadata, and make "
               "RecordingFinalizer.validate_recording (recording_finalizer.py L126-203) warn or fail when it is non-zero. With rank 6, also export the "
               "ring's explicit drop and block counters. Prefer device timestamps (PyAV dshow pts, rank 8) where available.")
r["expected_impact"] = (f"Detection only; it prevents no loss (it is not a P1 fix by itself). At HEAD the loss is not counted or validated: the "
                        f"finalizer passes and only shows 'Mean Framerate 53.93 Hz' for a 60 fps configuration. {det_txt}")
r["evidence"] = (det_txt + " Baseline loss: baseline/results/e_e2e_summary.md rows e_e2e_1080p_mjpeg_ui.json and _rep2 (964 / 964); finalizer_stats "
                 "in those JSON files. DSHOW timing (why retrieve stamps): prototypes/results/p9_real_camera.md (grab 0.00-0.01 ms, retrieve about 32 ms).")
r["risks_tradeoffs"] = ("A camera that delivers below its nominal rate shows as constant loss; on real DSHOW cameras the retrieve stamp is the "
                        "only host stamp near frame arrival, and the detector's accuracy on real cameras is untested (open question).")

# ---- old rank 5 (ring v2) -> 6
r = recs[5]
r["change"] = r["change"].replace("(3) register_cursor(lossless: bool): before reusing a slot the writer checks gated cursors (SeqRing.can_write L140-147) and applies an explicit, counted policy: block or drop.",
                                  "(3) register_cursor(lossless: bool): before reusing a slot the writer checks gated cursors (SeqRing.can_write L140-147). For the RECORDING cursor the only policy is block, together with lockstep (or a group commit: a multiframe is recorded only once every camera has published that frame number), so that any loss falls on the same frame numbers on every camera and is counted; drop is allowed only for non-recording readers (UI, analysis).")
r["expected_impact"] = ("Removes silent torn reads for lagging by-index readers: in the adversarial test (an emulation on SeqRing with a 4,300 fps "
                        "writer) the current pattern accepted 39,854-41,834 torn and 1,068-1,846 wrong frames when reading the oldest slot, and 15 "
                        "at L=2; at SkellyCam's real L=388 with latest reads it had 0 (p2_seqlock_read.md row '388 | latest | copy_fncheck'), so the "
                        "realistic exposure is FreeMoCap readers that lag by about a ring length (6.4 s at 720p, 2.87 s at 1080p at 60 fps). The "
                        "seqlock had 0 in every row of part A. 5-camera 1080p reads cost 0.0333 ms as validated views vs 1.8365 ms copies "
                        "(2.3533 ms for get_latest_multiframe at HEAD). The lossless 5x1080p SPSC rate rises to 527-537 fps per camera vs 243-250. "
                        "The block-only rule keeps cameras in sync when one recorder stalls past the ring (P3 ASYM).")
r["evidence"] = ("prototypes/results/p2_seqlock_read.md part A (tear counts; rows at L=2/8 oldest/latest and L=388) and part B; script p2_seqlock_read.py. "
                 "cpp/results/cpp_comparison.md section 1b (SPSC rates; those gated runs cannot exercise a torn read, so they are throughput "
                 "evidence only). Asymmetric stall: prototypes/results/p3v_asymmetric_stall.md (script prototypes/p3_lossless_record.py ASYM; idle "
                 "2026-10-28): with a 3500 ms stall on 1 of 5 recorders at L=172, block without lockstep recorded 445 vs 481 frames and camera 0's "
                 "frame k was captured up to 606 ms after the others' (92 frames >= 1 period apart; every frame-count check would pass); drop gave "
                 "443 vs 481 and 639 ms; block + lockstep recorded 445 on all 5 cameras, each skipping the same 36 sensor ticks, spread 6.3 ms. "
                 "1000 ms stalls were lossless under every policy. First-lap cost: baseline/results/a_write.md. Spawn crash: "
                 "baseline/results/repro_type_overloads_spawn.txt.")
r["risks_tradeoffs"] += (" Block + lockstep turns a long single-camera stall into the same counted sensor skip on every camera; P1 then depends on "
                         "the overflow budget (rank 7 risks).")

# ---- old rank 6 (decouple recorder) -> 7
r = recs[6]
r["change"] = r["change"].replace("A thread in the camera process is enough (MSMF write releases the GIL: P7 x1.64 threads vs x1.53 processes); a process also works.",
                                  "A non-daemon thread in the camera process (measured end to end in P8 with lockstep: 59.93 fps, 1 frame never grabbed) or a separate process both work; a thread dies with its camera process, so it must drain and release on the rank-1 stop path.")
r["change"] += (" Keep lockstep (or a group commit) for recording; rank 13 makes the gate cheap. Overflow tier: the ring is the recorder's only "
                "buffer, so size it from measured stalls (P12: worst write-through stall " + f"{worst_disk_stall_ms:.0f} ms, worst stream lag {worst_lag_ms:.0f} ms" +
                "; antivirus and long-run stalls are open) and, where RAM allows, add a compressed overflow (rank 8's JPEG ring) before blocking.")
r["expected_impact"] = (f"Measured with lockstep kept and SkellyCam's per-frame metadata writes added (P8 variant): 5x1080p with in-loop imdecode "
                        f"{p8f(LM1)} / {p8f(LM2)} fps, {p8n(LM1)} / {p8n(LM2)} sensor frames never grabbed, files == produced and consecutive; "
                        f"recorder as a thread {p8f(LRT)} fps, {p8n(LRT)} never grabbed; tick to written p99 {tw99(LM1):.1f} / {tw99(LM2):.1f} ms. "
                        f"HEAD in the same session: {fps(H):.2f} fps, {ng(H)} never grabbed ({E2EV}). Still not modelled: "
                        "camera_loop_update_checks/pubsub polling, the deepcopy in should_grab_by_id, the start/stop handshake and the finalizer. "
                        f"Sensitivity: with 3 ms more CPU per frame on the capture thread (decode 14.5 ms, the low end of P9's real 11-15 ms) the "
                        f"same design gives {p8f(LX3)} fps and {p8n(LX3)} never grabbed. A 1500 ms recorder stall recorded 6005 / 6005 frames with 0 "
                        "of 605 content mismatches (P3 part B).")
r["evidence"] = (P8V + ". Original no-gate P8 rows: prototypes/results/p8_e2e_summary.md (59.95 / 59.95 fps), reproduced in "
                 "reproducibility/comparison.md. prototypes/results/p3_lossless_record.md part B. Finalization stall: 387 ms "
                 "RecordingFinishedMessage.__post_init__ plus 127 ms pickling for 36,000 frames (verified_digest.json control area; PROVISIONAL "
                 "2026-10-25 map-stage measurement).")
r["risks_tradeoffs"] = ("Synthetic cameras only: real 60 fps capture CPU on the calling thread is unmeasured, and the 3 ms sensitivity run shows "
                        "the decode-in-loop headroom is about 2-3 ms. The ring length is the recorder's stall budget (2.87 s at 1080p with the 1 GiB "
                        "default); a longer stall becomes counted loss on every camera (block + lockstep), not silent loss. Releasing a slot after "
                        "write() returns relies on the encoder copying its input (verified for MSMF and PyAV, P3 0/605). Lockstep raises tick to "
                        f"written p99 from {tw99(SPR):.1f} ms (no gate) to {tw99(LM1):.1f}-{tw99(LM2):.1f} ms.")

# ---- old rank 7 (passthrough) -> 8
r = recs[7]
r["expected_impact"] = ("5x1080p: 59.97 / 59.97 fps, 0 never grabbed, 60.00 fps decoded with 0 skipped, tick to written 0.8 / 1.5 / 2.9 ms. "
                        "Recorder CPU 19-20% vs 924-954% for decode + MSMF. P4 record path at 1080p: 35 / 28% CPU (cameras / recorders) vs 302 / "
                        "939%. Stall budget of the design that was built: 1,024 fixed 1 MiB JPEG slots per camera = 17 s at 60 fps (p8_e2e_proto.py "
                        "JSLOT = 1 << 20, SeqRing.create(1024, JSLOT)); a packed variable-size ring holding about 9,250 frames of 116 KB (about 154 s) "
                        "per GiB is an untested ESTIMATE (arithmetic).")
r["evidence"] = ("prototypes/results/p8_e2e_summary.md rows p8_e2e_1080p_imdecode_off_passthrough.json and _rep2 (reproduced, reproducibility/comparison.md); "
                 "prototypes/results/p4_mjpeg_passthrough.md; prototypes/results/p9b_pyav_dshow_probe.md: with an explicit 30 fps option, 3 of 4 "
                 "real cameras delivered 100% FF D8 packets (57-116 KB per frame at 1080p, at most 0.6 ms CPU per packet); with no framerate option "
                 "the c922 and C930e negotiated 10 fps raw (0 / 31 FF D8, 1,843,200 B); a 60 fps open failed (OSError 5) on 7 of 8 device/size "
                 "combinations and the one that opened (c922 1280x720) delivered 30.1 fps. A 60 fps passthrough capture is shown on no device. "
                 "Crash safety of MJPEG-in-MKV: prototypes/results/p11_crash_container.md. All idle.")
r["risks_tradeoffs"] += (" Copies (P3): the camera loop copies each JPEG into the byte ring and the recorder muxes from it (1 compressed copy each), and "
                         "the consumer decode keeps one full-frame copy (np.copyto(slot, cv2.imdecode(...))) unless a dst-capable decoder such as "
                         "simplejpeg buffer= (bench venv only) is used.")

# ---- old rank 8 (copy.copy) -> 9
r = recs[8]
r["expected_impact"] = (f"Measured alone in the real SkellyCam stack: 5x1080p mjpeg + UI {fps(N1):.2f} / {fps(N2):.2f} fps with {ng(N1)} / {ng(N2)} "
                        f"sensor frames never grabbed, vs {fps(H):.2f} fps and {ng(H)} for HEAD in the same session (and 53.56-53.97 fps, 902-964 in "
                        "the earlier idle runs); put_frame median 3.61 -> 1.29-1.38 ms; files == recorded in every run. It does not reach 60 fps on "
                        "its own: the finalizer still shows 2.5-3.2 ms per frame of camera idle at the lockstep gate (rank 13). Isolated: publish "
                        "3.085 / 4.046 ms -> 1.166 / 1.854 ms at 1080p with 5 writers, byte-identical slots; removes 6,221,432 B of copy per 1080p frame "
                        "(1.87 GB/s at 5x1080p60).")
r["evidence"] = (E2EV + " rows e2ev_head_1080p_mjpeg_ui vs e2ev_nocopycopy_1080p_mjpeg_ui(_rep2). prototypes/results/p1_write.md rows "
                 "cur_memcpy_putframe vs cur_memcpy_putdata_nocopycopy. baseline/results/f_copies.md (byte counts).")
r["effort"] = "S"

# ---- old rank 9 (setNumThreads) -> 10
r = recs[9]
r["title"] = "Call cv2.setNumThreads(1) in recorder processes, and in camera processes once the encode is decoupled"
r["change"] = ("Call cv2.setNumThreads(1) at the start of any recorder process or thread owner (rank 7), and at the start of "
               "opencv_camera_worker_method (opencv_camera_worker_method.py L28) once the encode no longer runs in the capture loop. While the "
               "encode stays inline, the cap halves camera-process CPU but slows record_frame and costs about 0.5 fps at 1080p (below), so apply it "
               "then only if CPU, not fps, is the constraint. Do not apply it blindly in the main process. SkellyCam never calls setNumThreads today.")
u1, ud, u2 = r10[("1", "unthrottled")], r10[("default", "unthrottled")], r10[("2", "unthrottled")]
l1, ld, l2 = r10[("1", "paced60_load")], r10[("default", "paced60_load")], r10[("2", "paced60_load")]
r["expected_impact"] = (f"Real VideoRecorder, 5x1080p, idle (P10 revision rows): unthrottled encode rate (slowest camera) {u1['encode_fps_slowest']:.1f} fps "
                        f"at threads=1 vs {ud['encode_fps_slowest']:.1f} default and {u2['encode_fps_slowest']:.1f} at 2, with {u1['cpu_pct_sum']:.0f}% vs "
                        f"{ud['cpu_pct_sum']:.0f}% vs {u2['cpu_pct_sum']:.0f}% CPU; paced 60 fps while 5 other processes decode 1080p JPEGs at 60 fps: "
                        f"{l1['cpu_pct_sum']:.0f}% vs {ld['cpu_pct_sum']:.0f}% (default) and {l2['cpu_pct_sum']:.0f}% (2), all 60.0 fps with "
                        f"{l1['late_over_16_7ms_total'] + ld['late_over_16_7ms_total'] + l2['late_over_16_7ms_total']} late writes; record_frame median "
                        f"{l1['record_frame_median_ms']:.2f} vs {ld['record_frame_median_ms']:.2f} ms. Real stack with the encode inline: children CPU "
                        f"{cpu(H):.0f}% -> {cpu(T1):.0f}% and {fps(H):.2f} -> {fps(T1):.2f} fps alone; combined with rank 9 {cpu(NT):.0f}% and "
                        f"{fps(NT):.2f} fps vs {fps(N1):.2f} / {fps(N2):.2f} for rank 9 alone (record_frame 1.0 -> 2.7 ms).")
r["evidence"] = ("prototypes/results/p10v_msmf_threads.md (script prototypes/p10_msmf_threads.py with P10_PLAN=revision, driver "
                 "revision/run_revision.py p10v; idle 2026-10-28) - replaces the provisional P10 rows for this claim; " + E2EV +
                 " rows e2ev_cvthreads1_* and e2ev_nocopycopy+cvthreads1_*. C++ reproduction: cpp/results/codec/vw_1080p_n5_paced60_th1_* 382 / 397 / 443% vs "
                 "thdefault 1127 / 1257 / 1279%.")
r["risks_tradeoffs"] = ("The cause (OpenCV Concurrency pool busy-waiting) is inferred, not profiled. With the encode inline, threads=1 raises "
                        "record_frame and costs fps (above).")

# ---- old rank 10 (retrieve into slot) -> 11
r = recs[10]
r["change"] = r["change"].replace("Check np.shares_memory(returned, slot_view) after retrieve and raise if it is False.",
                                  "Check np.shares_memory(returned, slot_view) after retrieve; if it is False, fall back to one counted copy into the slot (never raise into kill_everything).")

# ---- old rank 11 (UI) -> 12
r = recs[11]
r["title"] = "UI tap: (a) wake on new frames instead of a 10 ms sleep; (b) build off the event loop from views; plus if_newer_than and no deflate"
r["expected_impact"] = (f"(a) gives the rate: polling every 2 ms with the thread-pool build reached view_proto_threads_poll2ms {p6r('1080p', 'view_proto_threads_poll2ms')} "
                        f"at 1080p ({p6r('720p', 'view_proto_threads_poll2ms')} at 720p). (b) alone, at the same 10 ms poll, does NOT raise the rate "
                        f"(view_proto_threads {p6r('1080p', 'view_proto_threads')} vs cur_copy_real {p6r('1080p', 'cur_copy_real')} at 1080p) but removes the "
                        "event-loop blocking: 0.05 / 0.08 ms vs 8.28 / 10.11 ms median / p99 per payload (the loop also serves the start/stop recording "
                        f"HTTP handlers). 720p 10 ms-poll rows are bimodal across runs (e.g. view_proto {p6r('720p', 'view_proto')}). Removes 31.1 MB of "
                        "shm copies per 1080p multiframe. Deflate: " + deflate_txt)
r["evidence"] = ("prototypes/results/p6_ui_path.md plus repeats prototypes/results/p6_ui_skellycamvenv_rev_rep2.json / _rev_rep3.json (P6_OUT, driver "
                 "revision/run_revision.py p6v; idle 2026-10-28) and reproducibility/rerun/prototypes/results/p6_ui_skellycamvenv.json; script "
                 "prototypes/p6_ui_path.py (no browser). baseline/results/d_ui.md (46.0/s with the 10 ms sleep, 60.0 distinct/s without). " + deflate_txt)

# ---- old rank 12 (control plane) -> 13
r = recs[12]
r["expected_impact"] = ("Measured: with copy.copy removed, the real stack still idles 2.5-3.2 ms per frame at the lockstep gate (finalizer "
                        "'TOTAL CAMERA IDLE TIME', e2ev_nocopycopy_*), the largest remaining gap to 60 fps; HEAD idles 2.48 ms. The P8 lockstep variant, "
                        "whose gate reads one shared int64 array and polls with time.sleep(1e-5), waited 0.03-0.18 ms median and held 59.82-59.95 fps. "
                        "Micro: SharedMemoryNumber write / read 4,423 / 5,738 ns -> numpy view 52.85 / 60.36 ns; nested timestamp write 13,502 ns -> "
                        "53.85 ns cached; time.sleep(1e-5) 525.4 us median. Event-wake latency itself was not measured.")
r["evidence"] = (E2EV + "; " + P8V + "; cpp/results/micro_py.json (script cpp/py_micro.py, idle).")
r["risks_tradeoffs"] = ("Keep lockstep (or a group commit) for recording: removing it lets a single stalled camera desynchronise frame numbers "
                        "from capture time silently (P3 ASYM, 606 ms). Lockstep aligns frame numbers and grab calls, not exposure instants: with "
                        "free-running cameras the capture-time spread of a multiframe was 7.0-13.3 ms median and up to 20.2 ms in the e2ev runs, "
                        "while the finalizer's grab-stamp sync shows 0.5-1.3 ms.")

# ---- old rank 13 (nvenc) -> 14
r = recs[13]
r["priorities_served"] = ["P2", "P1"]
r["change"] += (" Failure handling (required before use): probe and reserve sessions before recording starts (the machine-wide cap is 12, "
                "shared with other apps); if NVENC is unavailable, fall back on all cameras together; on a mid-recording encoder failure keep the "
                "ring cursor, reopen the fallback into a new segment at the same frame number and count the event; write MKV, not MP4 (rank 2); "
                "flush the encoder on stop. Add an injection test.")
r["risks_tradeoffs"] += (f" A hard kill loses the frames inside the encoder: {r11[('1080p', 'nvenc_mkv', 'killed_idle')]['cv2_frames_decoded']} of 300 "
                         "readable (P11). Copies (P3): BGR -> I420 conversion and the from_ndarray copy add 2 passes of 1.5 B/px per frame "
                         "(p8_e2e_proto.py recorder); writing cvtColor output straight into a preallocated av.VideoFrame plane is untested.")

# ---- old rank 14 (FreeMoCap readers) -> 15 (unchanged content)

new_recs = [recs[1], new2]
for old_rank in range(2, 15):
    rr = recs[old_rank]
    rr["previous_rank"] = old_rank
    rr["rank"] = old_rank + 1
    new_recs.append(rr)
recs[1]["previous_rank"] = 1
for rr in new_recs:
    rr.setdefault("previous_rank", None)

out = copy.deepcopy(old)
out["recommendations"] = new_recs
out["revision"] = ("Revised 2026-10-28 by the REVISION stage after the evidence, priorities and reproducibility critiques; issue -> action -> "
                   "evidence in study_state/revision_result.json; new benchmarks in research/frame_ring_buffer/revision/README.md. Ranks were "
                   "renumbered: a new rank 2 (crash-tolerant files) was inserted, so previous ranks 2-14 are now 3-15 (field previous_rank).")
out["headline"] = (
    f"A C++ port is not needed. For P1 the plan is: contain failures, make a crash cost seconds not the file (today a killed MSMF .mp4 has 0 of 300 "
    f"frames readable, MJPEG-in-MKV 298), record with a block-only cursor under lockstep, and count every loss. For P2 the single biggest measured "
    f"step is removing copy.copy from put_data: alone, in the real SkellyCam stack, it raises 5x1080p mjpeg + UI from {fps(H):.2f} to "
    f"{fps(N1):.2f} / {fps(N2):.2f} fps (sensor frames never grabbed {ng(H)} -> {ng(N1)} / {ng(N2)}). Decoupling the recorder through a gated seqlock "
    f"ring with lockstep KEPT and SkellyCam's per-frame metadata writes reaches {p8f(LM1)} / {p8f(LM2)} fps with {p8n(LM1)} / {p8n(LM2)} never "
    "grabbed (prototype; synthetic 60 fps cameras; idle machine; 1920x1080 BGR). The headroom is small: 3 ms more capture-thread CPU per frame, "
    f"within P9's real-camera range, drops that design to {p8f(LX3)} fps. Suggested build order: ranks 9 (copy.copy), 3, 4, 5 and 2 (S effort) "
    "first, then rank 1, then ranks 6 + 11 + 7 together with 13 and 10, then 12, 14, 15, with rank 8 (passthrough) as a separate project.")
v = old["current_state_verdict"]
v = v.replace("No grabbed frame was lost on the way to disk in 8 e2e runs and 6 recorder configurations: files decode to exactly the recorded count, frames are consecutive, and the finalizer passed (baseline/results/e_e2e_summary.md, c_record.md).",
              "In 8 e2e runs and 6 recorder configurations the writer accepted every grabbed frame: files decode to exactly the recorded count, frames are consecutive, and the finalizer passed (baseline/results/e_e2e_summary.md, c_record.md). Those files sat in the OS page cache (no fsync, re-read from cache, then deleted), so they show the writer API kept up, not that the disk did; P12 below covers the disk.")
v = v.replace("with 964 sensor frames (10.7%) never grabbed, and SkellyCam cannot see that loss.",
              "with 964 sensor frames (10.7%) never grabbed. The loss is not counted or validated; it shows only as 'Mean Framerate 53.93 Hz' in the finalizer stats.")
v = v.replace("The limit is the serial loop body under lockstep: retrieve 10.1-10.3 ms + put_frame 3.6-3.7 ms + record_frame 1.1-1.2 ms against a 16.7 ms budget (camera_orchestrator.py L96-109, opencv_camera_loop.py L67-117). It is not the ring: put_frame sustains 353 fps per camera at 1080p (a_write.md).",
              "The limit is the loop body plus the lockstep gate: per camera the finalizer shows 15.77 ms median processing (retrieve 10.04, put_frame 3.56, record 1.14 ms and small idles) plus 2.49 ms median camera idle per frame, and the group runs at the pace of the slowest of 5 cameras each frame, polled with wait_10us (time.sleep(1e-5) = 0.53 ms median), giving an 18.7 ms frame duration (e_e2e_1080p_mjpeg_ui.json finalizer_stats; camera_orchestrator.py L96-109, opencv_camera_loop.py L67-117). The in-loop ring copy matters: removing copy.copy alone gives "
              f"{fps(N1):.2f} / {fps(N2):.2f} fps, and the remaining 2.5-3.2 ms gate idle is the next limit ({E2EV}). The isolated put_frame rate (353 fps per camera, a_write.md) does not represent its in-loop cost.")
v = v.replace("No real camera reached 60 fps on this machine (max 30.1 fps, p9_real_camera.md), so every 5x60 number is synthetic.",
              "No real camera reached 60 fps on this machine (max 30.1 fps, p9_real_camera.md), so every 5x60 number is synthetic, and the synthetic model "
              "differs from real DSHOW: FakeCapture.grab() blocks for the frame and retrieve() only decodes, while real grab() returns in 0.00-0.01 ms and "
              "retrieve() takes about 32 ms with 11.0-14.7 ms CPU per 1080p frame (at 30 fps, process total). With 3 ms more retrieve CPU the real stack "
              f"drops to {fps(X3):.2f} fps ({ng(X3)} never grabbed).{ds_txt} Per-frame capture-thread CPU of real cameras at 60 fps is unmeasured. "
              "Lockstep aligns grab calls, not exposure: the finalizer's 'Inter-Camera Sync' (0.5-1.3 ms) uses grab stamps, while the capture times of "
              "the same frame number differ by 7.0-13.3 ms median and up to 20.2 ms (more than one 16.7 ms period) across the free-running synthetic cameras "
              "(e2ev_gap_detector.md tick spread).")
v = v.replace("This stage ran no new benchmarks, so it has no machine load of its own to record.",
              "Disk: " + p12_txt + " The UI cost on capture is about 1.5-2.4 fps at 1080p (no-UI runs 55.94 and " + f"{fps(NU):.2f}" +
              " fps vs 53.56-54.14 with UI); the e2e UI consumer is a stand-in that catches every exception instead of setting the kill flag, so it "
              "cannot show fault behaviour. The revision stage's runs were all idle (revision/README.md, load_*.json).")
v = v.replace("(code refs in ranks 1-3)", "(code refs in ranks 1, 3 and 4)")
v = v.replace("5x1080p with a decode-free retrieve holds 59.99 fps.", "5x1080p with a decode-free retrieve holds 59.97-59.99 fps (0-3 sensor frames never grabbed in 3 idle runs, incl. the reproducibility re-run).")
out["current_state_verdict"] = v
out["cpp_verdict"] = old["cpp_verdict"].replace(
    "Codec speed is set by the OpenCV / libjpeg-turbo build: Python cv2 4.12 decodes 1.57x and encodes q90 4.9x faster than the C++ OpenCV 4.8 SDK.",
    "Codec speed is set mostly by the OpenCV / libjpeg-turbo build: Python cv2 4.12 decodes 1.57x and encodes q90 4.9x faster than the C++ OpenCV 4.8 SDK. "
    "At the same OpenCV version (4.8.0) C++ does decode 1080p faster: 11.32 ms (copy) or 10.36 ms (in place) vs 12.78 ms in Python, 11-19% on the "
    "largest per-frame cost (cpp/results/cpp_comparison.md section 4). C++ in-place decode with a current libjpeg-turbo 3.x was not measured, so "
    "'no meaningful gain' is not proven for decode; it is listed as untested.")
out["not_recommended"] = old["not_recommended"] + [
    dict(idea="A 'drop' policy (or no lockstep / group commit) on the recording cursor",
         why_not="One recorder stalling past the ring desynchronises that camera silently: frame numbers still match, but capture times differ by up to 606 ms (block, no lockstep) or 639 ms (drop) over 91-92 frames (prototypes/results/p3v_asymmetric_stall.md)."),
    dict(idea="Non-fragmented MP4 as the recording container",
         why_not=f"A killed writer leaves {msmf_k['cv2_frames_decoded']} of 300 frames readable (no index); MJPEG-in-MKV keeps {mkv_k['cv2_frames_decoded']} (prototypes/results/p11_crash_container.md)."),
    dict(idea="Per-interval round(dt/T) - 1 as the drop counter",
         why_not=f"Finds {G[H]['detectors']['per_interval_round|pre_frame_grab_ns']} of {G[H]['true_never_grabbed']} at HEAD because a uniformly slow loop rounds to 1 frame per interval; use the accumulated clock (baseline/results/e2ev_gap_detector.md)."),
    dict(idea="Using the finalizer's 'Inter-Camera Frame Grab Sync' as the sync-quality metric",
         why_not="It measures grab-call stamps (0.5-1.3 ms), not capture times, which differed by 7-13 ms median across the synthetic free-running cameras (e2ev_gap_detector.md); on DSHOW the grab call returns before the frame arrives (p9_real_camera.md)."),
]
oq = [q for q in old["open_questions"] if not q.startswith("End-to-end effect of each single change")]
oq = [q.replace("the SN850X is 91% full per research.json", "C: was 94.4% full on 2026-10-28, environment_system.json / P12") for q in oq]
FIX = {
    "Spill-to-disk as a full-ring policy": "Spill-to-disk as a full-ring policy was not tested. Raw write-through with the SLC cache exhausted was (P12: 481-1508 MB/s, 5 paced streams kept 162 MB/s, worst write 138 ms); recorder behaviour through the real encoders on a slow or nearly full disk was not.",
    "Whether lockstep should be kept": "Lockstep (or a group commit) is kept for recording (P3 ASYM). Open: whether non-recording consumers could group free-running frames by timestamp instead, and what sync quality that gives on real cameras.",
    "Whether FreeMoCap's posthoc pipeline accepts MJPEG-in-MKV": "Whether FreeMoCap's posthoc pipeline accepts MJPEG-in-MKV recordings (rank 8). FreeMoCap realtime-pipeline contention at 5x60 fps was not measured.",
    "Accuracy of the host-timing gap detector": "Accuracy of the accumulated-clock drop detector (rank 5) on real DSHOW cameras; on the synthetic stack it matched the true count within +5 (e2ev_gap_detector.md).",
}
oq = [next((v for k, v in FIX.items() if q.startswith(k)), q) for q in oq]
out["open_questions"] = oq + [
    "Per-frame capture-thread CPU of real cameras at 60 fps (P9 measured 11.0-14.7 ms per 1080p frame at 30 fps as a process total; the P8 lockstep design loses about 2 fps with 3 ms more CPU).",
    "Antivirus (Defender real-time scan) and GC pauses as recorder stalls during a 10-minute 5x1080p60 recording through the real encoders; P12 measured raw write-through stalls only (no encoder, Defender in its default state).",
    "NVENC session-exhaustion and mid-recording driver-reset handling (rank 14) and the rank-1 fault-injection test were specified but not built.",
    "Whether FreeMoCap's posthoc reader accepts MKV / fragmented MP4 recordings (rank 2) and tolerates a truncated last fragment.",
    "A packed variable-size compressed ring (rank 8's ~154 s per GiB estimate) was not built; the built prototype holds 17 s.",
    "Hybrid CPU (8 P-cores + 12 E-cores): no run pinned affinity or recorded core-type placement; the idle rule is a share of all 28 logical CPUs. Part of the run-to-run variance may come from placement.",
    "Real-camera hardware sync: with free-running cameras the capture-time spread of a multiframe is set by the sensors' phases (7-13 ms median, up to 20 ms on the synthetic stack) whatever the software does; whether the target cameras support a sync input was not examined.",
]
(SS / "recommend_result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("recommend_result.json written:", len(new_recs), "recommendations")
