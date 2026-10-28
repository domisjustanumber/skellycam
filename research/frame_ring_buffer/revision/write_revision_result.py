"""Writes study_state/revision_result.json: each critic issue -> action taken -> evidence (REVISION stage, 2026-10-28).
Run after update_recommendation.py. Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam):
  .venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\write_revision_result.py
"""
from __future__ import annotations

import json
from pathlib import Path

FP = Path(__file__).resolve().parents[1]
SS = FP / "study_state"
BR = FP / "baseline" / "results"
PR = FP / "prototypes" / "results"


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


g = load(BR / "e2ev_gap_detector.json")
e = {f.stem: load(f) for f in BR.glob("e2ev_*_1080p_*.json")}
p8 = {f.stem: load(f) for f in PR.glob("p8v_e2e_*.json")}
p12 = load(PR / "p12_disk_sustained.json")
r12 = {r["phase"]: r for r in p12["rows"]}
hd = {r["size"]: r for r in load(BR / "h_deflate.json")["rows"]}
p10 = {(r["threads"], r["mode"]): r for r in load(PR / "p10v_msmf_threads.json")["rows"]}
p11 = {(r["size"], r["kind"], r["mode"]): r for r in load(PR / "p11_crash_container.json")["rows"]}


def fps(n):
    return min(c["achieved_fps"] for c in e[n]["per_camera"].values())


def ng(n):
    return sum(c["sensor_frames_never_grabbed"] for c in e[n]["per_camera"].values())


H, N1, N2 = "e2ev_head_1080p_mjpeg_ui", "e2ev_nocopycopy_1080p_mjpeg_ui", "e2ev_nocopycopy_1080p_mjpeg_ui_rep2"
DS = "e2ev_dshowlike_1080p_mjpeg_ui_v2"
LM1, LM2, LRT, LX3 = ("p8v_e2e_1080p_imdecode_msmf_lockstep_meta", "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_rep2",
                      "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_recthread", "p8v_e2e_1080p_imdecode_msmf_lockstep_meta_extracpu3")
E2EV_CMD = ".venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\run_revision.py e2ev (runs baseline/bench_e2e_variants.py <variant> 1080p mjpeg ui 30 through baseline/run_with_load.py)"
P8V_CMD = ".venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\run_revision.py p8v"
A = []


def act(severity, issue, action, evidence, resolved=True):
    A.append(dict(severity=severity, issue=issue, action=action, evidence=evidence, resolved=resolved))


ds_part = ""
if DS in e:
    ds_part = (f" dshowlike stand-in (grab returns at once, retrieve waits then decodes): {fps(DS):.2f} fps, {ng(DS)} never grabbed; grab-stamp spread "
               f"p99 {g[DS]['grab_spread_p99_ms']:.2f} ms vs capture-time spread median {g[DS]['tick_spread']['median_ms']:.1f} / max {g[DS]['tick_spread']['max_ms']:.1f} ms.")

# ---------------- evidence critic
act("major", "[evidence] Root-cause arithmetic: quoted loop medians sum to 14.8-15.2 ms < 16.7 ms; 'it is not the ring' contradicts the e2e finalizer (put_frame 23.1% of processing, 2.49 ms gate idle).",
    "Re-ran the real stack with copy.copy removed alone (rank 8 -> new rank 9) and a same-session HEAD control; restated the verdict as loop body (15.77 ms) + lockstep gate idle (2.49 ms) under max-of-5 pacing; removed 'it is not the ring'; re-weighted ranks 9 and 13.",
    f"HEAD control {fps(H):.2f} fps / {ng(H)} never grabbed; nocopycopy {fps(N1):.2f} / {fps(N2):.2f} fps, {ng(N1)} / {ng(N2)} never grabbed, gate idle still 2.5-3.2 ms. "
    f"baseline/results/e2ev_summary.md, e2ev_*.json finalizer_stats; e_e2e_1080p_mjpeg_ui.json finalizer_stats. Command: {E2EV_CMD}. Idle (load_e2ev_*.json).")
act("major", "[evidence] 59.95 fps headline came from a prototype without lockstep or SkellyCam loop overheads; recommended configuration never measured.",
    "Added P8 options P8_LOCKSTEP (SkellyCam-style gate on a shared int64 count array, time.sleep(1e-5) poll), P8_META (31 nested timestamp writes + frame_number into a real SkellyCam frame recarray), P8_RECTHREAD and cross-camera spread; re-ran. Headline now quotes the lockstep+metadata result and lists what is still not modelled.",
    f"Lockstep+meta {p8[LM1]['min_cam_fps']:.2f} / {p8[LM2]['min_cam_fps']:.2f} fps, {p8[LM1]['sensor_never_grabbed_total']} / {p8[LM2]['sensor_never_grabbed_total']} never grabbed; recorder thread {p8[LRT]['min_cam_fps']:.2f} fps, {p8[LRT]['sensor_never_grabbed_total']}. prototypes/results/p8v_e2e_summary.md, p8v_e2e_*.json. Command: {P8V_CMD}. Idle.")
act("major", "[evidence] Synthetic camera model contradicted by P9 (real grab 0 ms, retrieve 32 ms, 11-15 ms CPU at 1080p).",
    "Added a caveat next to the 5x60 numbers in the verdict and rank 7; ran CPU-sensitivity stand-ins (+3 ms CPU in retrieve) in the real stack and in the P8 lockstep design, and a dshowlike timing stand-in (grab returns at once, retrieve waits, then decodes). Real-camera per-frame CPU at 60 fps stays an open question.",
    f"Real stack +3 ms: {fps('e2ev_extracpu3_1080p_mjpeg_ui'):.2f} fps, {ng('e2ev_extracpu3_1080p_mjpeg_ui')} never grabbed; P8 lockstep +3 ms: {p8[LX3]['min_cam_fps']:.2f} fps, {p8[LX3]['sensor_never_grabbed_total']}.{ds_part} "
    "baseline/results/e2ev_summary.md, e2ev_gap_detector.md; prototypes/results/p8v_e2e_summary.md. The first dshowlike run logged setup read() calls into its tick log (index shift) and is kept only in baseline/results/superseded_revision/.", resolved=True)
act("major", "[evidence] Rank-4 formula max(0, round(dt/T)-1) cannot see the dominant loss mode (18.7 ms intervals round to 1).",
    "Validated detectors offline against the true never-grabbed counts from per-frame dumps; replaced the formula with the accumulated clock round((t_last-t_first)/T)+1-n; relabelled rank 4 (now 5) as detection only.",
    f"Per-interval finds {g[H]['detectors']['per_interval_round|pre_frame_grab_ns']} of {g[H]['true_never_grabbed']} at HEAD; accumulated clock {g[H]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {g[H]['true_never_grabbed']}, "
    f"{g[N1]['detectors']['accumulated_clock|pre_frame_grab_ns']} of {g[N1]['true_never_grabbed']}, {g['e2ev_extracpu3_1080p_mjpeg_ui']['detectors']['accumulated_clock|pre_frame_grab_ns']} of {g['e2ev_extracpu3_1080p_mjpeg_ui']['true_never_grabbed']}. "
    "baseline/results/e2ev_gap_detector.md (script baseline/analyze_gap_detector.py on e2ev_*_perframe.npz).")
B1, B2, C = r12.get("B1"), r12.get("B2"), r12.get("C")
disk = (f"P12: 64 GiB write-through: about 5 GB/s, then {min(r12['A']['mb_per_s_per_gib']):.0f}+ MB/s after the SLC cache filled; 162 MB/s x 300 s write-through achieved {B1['achieved_mb_per_s']:.1f} MB/s, max write {B1['worst_write_call']['max_ms']:.0f} ms, "
        f"worst lag {B1['worst_lag_behind_schedule_ms']:.0f} ms")
if B2:
    disk += f"; 69 MB/s x 600 s: {B2['achieved_mb_per_s']:.1f} MB/s, max write {B2['worst_write_call']['max_ms']:.0f} ms, worst lag {B2['worst_lag_behind_schedule_ms']:.0f} ms"
if C:
    disk += f"; buffered 162 MB/s x 60 s then FlushFileBuffers: flush up to {C['max_flush_s']:.2f} s"
disk += f". Free {p12['free_bytes_at_start'] / 1e9:.1f} GB ({p12['used_pct_at_start']}% used): {p12['time_to_full_at_rate_min']['69']} min at 69 MB/s, {p12['time_to_full_at_rate_min']['162']} min at 162 MB/s."
act("major", "[evidence] No benchmark touched the physical disk; 'no frame lost on the way to disk' overstated; disk-fill figure stale (91%).",
    "Reworded to 'the writer accepted every grabbed frame (OS cache)'; added P12 (unbuffered write-through, SLC exhaustion past 48 GiB, paced 5-stream 300 s and 600 s runs, buffered + FlushFileBuffers), a free-space guard in new rank 2, and the 94.4% figure.",
    disk + " prototypes/results/p12_disk_sustained.md (script prototypes/p12_disk_sustained.py; command .venv\\Scripts\\python.exe research\\frame_ring_buffer\\revision\\run_revision.py p12). Not done: a 10-minute run through the real encoders with recording larger than RAM (raw writes only).",
    resolved=True)
act("major", "[evidence] Rank-11 rate gain comes from the 2 ms poll, not from views/threads; P6 noise large.",
    "Split rank 11 (now 12) into (a) wake/poll faster = rate and (b) thread pool from views = no event-loop blocking; quote 46.4/s for (b) alone; ran P6 two more times (4 runs incl. the reproducibility re-run) and quote ranges.",
    "prototypes/results/p6_ui_skellycamvenv_rev_rep2.json, _rev_rep3.json (P6_OUT; command run_revision.py p6v), prototypes/results/p6_ui_skellycamvenv.json, reproducibility/rerun/prototypes/results/p6_ui_skellycamvenv.json; ranges in recommend_result.json rank 12.")
u1 = p10[("1", "unthrottled")]
act("major", "[evidence] Rank 9 recommends setNumThreads(1) but the unthrottled comparison was only default vs 2; P10 provisional.",
    "Re-ran P10 idle with unthrottled threads=1/default/2 and paced rows under a concurrent 5x1080p60 decode load; measured setNumThreads(1) alone and with copy.copy removed in the real stack; rank 9 (now 10) recommends it for recorder processes, and for camera processes once the encode is decoupled.",
    f"Unthrottled threads=1 {u1['encode_fps_slowest']:.1f} fps at {u1['cpu_pct_sum']:.0f}% vs default {p10[('default', 'unthrottled')]['encode_fps_slowest']:.1f} at {p10[('default', 'unthrottled')]['cpu_pct_sum']:.0f}%; paced+load 1/default/2: "
    f"{p10[('1', 'paced60_load')]['cpu_pct_sum']:.0f}/{p10[('default', 'paced60_load')]['cpu_pct_sum']:.0f}/{p10[('2', 'paced60_load')]['cpu_pct_sum']:.0f}%, 0 late. Real stack: children CPU 1338% -> 713%, fps 54.14 -> 54.74; with nocopycopy 58.29 vs 58.84/58.98. "
    "prototypes/results/p10v_msmf_threads.md (P10_PLAN=revision; run_revision.py p10v); baseline/results/e2ev_summary.md. Idle.")
act("major", "[evidence] Rank 7 ring budget 154 s assumes an unbuilt ring (prototype 17 s); P9b 60 fps failed on 7 of 8 combos.",
    "Rank 7 (now 8) states the built budget (1024 x 1 MiB = 17 s) and labels 154 s an untested estimate; P9b qualified (30 fps only with an explicit option; 60 fps open failed on 7 of 8; framerate None -> 10 fps raw).",
    "prototypes/p8_e2e_proto.py JSLOT = 1 << 20, SeqRing.create(1024, JSLOT); prototypes/results/p9b_pyav_dshow_probe.md.")
act("minor", "[evidence] Thread recorder topology unmeasured (P7 compared writer threads vs processes, not a recorder thread beside the capture loop).",
    "Measured: P8 with P8_RECTHREAD=1 (recorder as a non-daemon thread in the camera process) + lockstep + metadata.",
    f"{p8[LRT]['min_cam_fps']:.2f} fps, {p8[LRT]['sensor_never_grabbed_total']} never grabbed, files == produced; prototypes/results/p8v_e2e_1080p_imdecode_msmf_lockstep_meta_recthread.json.")
act("minor", "[evidence] Tear framing ignores the 0-tear result at L=388 latest; '0 torn in 50 SPSC runs' cannot exercise the seqlock.",
    "Rank 5 (now 6) quotes the L=388 latest row (0 tears), names lagging by-index FreeMoCap readers as the realistic exposure, and cites P2 part A (not the gated SPSC runs) for the seqlock.",
    "prototypes/results/p2_seqlock_read.md rows 19-24.")
act("minor", "[evidence] Deflate evidence cited the wrong temp file; timings on 45-82 KB payloads.",
    "Added baseline/bench_h_deflate.py in the benchmark tree: real create_frontend_payload payload, websockets' own PerMessageDeflate with uvicorn's defaults.",
    f"1080p {hd['1080p']['payload_bytes_median'] / 1e3:.0f} KB -> {hd['1080p']['deflated_bytes_median'] / 1e3:.0f} KB in {hd['1080p']['deflate']['median_ms']:.2f} ms median; 720p {hd['720p']['deflate']['median_ms']:.2f} ms. baseline/results/h_deflate.md (command run_revision.py h_deflate). Browser negotiation not checked.")
act("minor", "[evidence] Rank 1 cited camera_node.py L256-280 for kill_everything.",
    "Cited the actual call sites with permalinks at freemocap 5632778a.",
    "git grep kill_everything: camera_node.py L351, realtime_aggregator_node.py L838, realtime_skeleton_inference_node.py L152/260/270/319.")
act("minor", "[evidence] cpp_verdict omits the same-version (OpenCV 4.8) decode comparison.",
    "Added: C++ 11.32 ms (copy) / 10.36 ms (in place) vs Python 12.78 ms at 4.8.0; C++ in-place decode with libjpeg-turbo 3.x listed as untested.",
    "cpp/results/cpp_comparison.md section 4.")
act("minor", "[evidence] 'SkellyCam cannot see that loss' overstated.",
    "Reworded: the loss is not counted or validated; it shows only as 'Mean Framerate 53.93 Hz' in the finalizer stats.",
    "baseline/results/e_e2e_1080p_mjpeg_ui.json finalizer_stats.")
act("minor", "[evidence] Hybrid CPU / per-thread background load not controlled.",
    "Recorded as an open question; the load records list the top background processes per 1 s sample (top_background in every load_*.json). No affinity-pinned repeat was run.",
    "revision/README.md; any load_*.json 'samples[].top_background'.", resolved=False)
act("minor", "[evidence] Baseline e2e UI is a stand-in; UI cost from 1 no-UI run.",
    "Verdict now states the stand-in catches every exception (fault behaviour excluded by construction); repeated the no-UI run.",
    f"No-UI repeat {fps('e2ev_head_1080p_mjpeg_noui_rep2'):.2f} fps ({ng('e2ev_head_1080p_mjpeg_noui_rep2')} never grabbed) vs original 55.94 (605); UI-on 53.56-54.14. baseline/results/e2ev_summary.md.")

# ---------------- priorities critic
a3 = load(PR / "p3v_asymmetric_stall.json")["rows"]
act("blocker", "[priorities] The plan converts silent loss into counted loss; no guarantee that disk writes never drop; ring cannot be sized from measured stalls.",
    "Recording cursor is now block-only under lockstep (rank 6/7), so any loss falls on the same frame numbers on every camera and is counted; measured physical-disk stalls (P12) against the 2.87 s ring; overflow tier (compressed JPEG ring) and free-space guard added to the plan. A true never-drop guarantee is not claimed: past the ring + overflow budget the plan stops loudly via rank 1's graceful path.",
    disk + " prototypes/results/p3v_asymmetric_stall.md. Antivirus and encoder-path stalls over 10 minutes remain open (open_questions).", resolved=False)
k = p11[("1080p", "msmf_mp4", "killed_idle")]
act("blocker", "[priorities] A crash or forced terminate loses the whole MP4; shutdown_all allows 3 s before terminate; thread recorder dies with its camera.",
    "Reproduced and extended the critic's test in the benchmark tree (P11: MSMF MP4, MJPEG MKV, NVENC fragmented MP4, NVENC MKV; killed idle and mid-write; 720p and 1080p). Added new rank 2: crash-tolerant containers, drain-aware shutdown (wait for 'recorders released' before terminate), free-space guard; rank 7 requires a non-daemon draining recorder thread on the rank-1 stop path.",
    f"Killed MSMF .mp4: {k['cv2_frames_decoded']} of 300 readable (both sizes, both kill modes); MJPEG .mkv {p11[('1080p', 'mjpeg_mkv', 'killed_idle')]['cv2_frames_decoded']} (idle) / {p11[('1080p', 'mjpeg_mkv', 'killed_mid')]['cv2_frames_decoded']} (mid); NVENC .mkv {p11[('1080p', 'nvenc_mkv', 'killed_idle')]['cv2_frames_decoded']}. "
    "prototypes/results/p11_crash_container.md (script prototypes/p11_crash_container.py; run_revision.py p11; idle). Code: worker_registry.py L161-207, camera_config.py L29, fourcc_codec_helpers.py L52-58.")
act("major", "[priorities] Rank 1(d) cannot work: after the kill flag the loops have exited, pause has no timeout, finalize is guarded by should_continue, timestamps live only in RecordingFinishedMessage.",
    "Verified each code claim at 23ccbf20 and rewrote rank 1(d): separate stop-requested state from the abort flag, one graceful-stop path, pause/finalize timeouts, incremental CSV timestamps moved forward, drain-aware shutdown.",
    "camera_group_ipc.py L47-53; camera_group.py L215-238, L317-379; camera_orchestrator.py L58-67; handle_recording_updates.py L50-59; worker_registry.py L83-109, L161-207 (permalinks in recommend_result.json rank 1).")
act("major", "[priorities] 59.95 fps measured without lockstep; frame-perfect sync requires lockstep or group commit.",
    "Measured P8 with lockstep kept (see evidence issue 2); made lockstep/group commit a P1 requirement for recording (ranks 6, 7, 13); added the measured capture-time spread and a not-recommended entry for free-running recording.",
    f"Lockstep+meta {p8[LM1]['min_cam_fps']:.2f}/{p8[LM2]['min_cam_fps']:.2f} fps. Capture-time vs grab-stamp spread: baseline/results/e2ev_gap_detector.md; P3 ASYM 606 ms desync without lockstep.")
act("major", "[priorities] 'Drop' policy on the recording cursor gives unequal per-camera counts under asymmetric stalls; P3 only tested simultaneous stalls.",
    "Added P3 ASYM (stall on 1 of 5 recorders; block / drop / block+lockstep; 1000 and 3500 ms) and changed rank 6: recording cursor block-only with lockstep; drop only for non-recording readers.",
    "; ".join(f"{r['stall_ms']} ms {r['policy']}{'+lockstep' if r['lockstep'] else ''}: recorded {r['sync']['recorded_per_cam']}, spread max {r['sync']['tick_spread']['max_ms']:.0f} ms" for r in a3) +
    ". prototypes/results/p3v_asymmetric_stall.md (command run_revision.py p3v; idle).")
act("major", "[priorities] stop_recording pauses capture during an active recording (silent sensor gap); no rank fixes it.",
    "Added rank 3(d) (now rank 4(d)): publish last_recording_frame_number while cameras run, no pause; measured the current gap from per-frame dumps.",
    "At most 1 skipped sensor tick between consecutive recorded frames in the last 10 frames of every camera, in every e2ev run (baseline/results/e2ev_gap_detector.md); code camera_group.py L215-232, opencv_camera_loop.py L60-65.")
act("major", "[priorities] NVENC session/mid-recording failure unhandled; rank 13 labelled P2-only.",
    "Rank 13 (now 14) now serves P2+P1 and lists required failure handling (probe/reserve sessions, all-camera fallback, segment reopen at the same frame number, MKV, flush on stop) and an injection test; crash loss of in-encoder frames measured.",
    f"NVENC .mkv killed: {p11[('1080p', 'nvenc_mkv', 'killed_idle')]['cv2_frames_decoded']} of 300 readable (P11). Injection test not built (open question).", resolved=False)
act("major", "[priorities] Remaining kill-flag paths: any camera-loop exception (incl. proposed raises in ranks 2, 3, 10) still kills everything.",
    "Rank 1 now defines one graceful-stop path for every camera-side error; rank 10 (now 11) falls back to one counted copy instead of raising; rank 2/3 (now 3/4) route through the graceful stop.",
    "opencv_camera_loop.py L119-130; worker_registry.py L83-109; recommend_result.json ranks 1, 3, 4, 11.")
act("minor", "[priorities] Rank 2 skip has no bound; a failing camera holds the group at the gate indefinitely.",
    "Added a ~1 s bound while recording, then graceful stop; failed_grabs exposed in the UI.", "recommend_result.json rank 3; camera_orchestrator.py L96-109.")
act("minor", "[priorities] Antivirus / GC stalls not measured.",
    "P12 measured raw storage stalls with Defender in its default state; encoder-path stalls with real-time scanning on/off and GC pauses remain open.",
    "prototypes/results/p12_disk_sustained.md; open_questions in recommend_result.json.", resolved=False)
act("minor", "[priorities] P3 accounting of ranks 7 and 13 (I420 + from_ndarray; decode copy; JPEG copies).",
    "Listed the copies in ranks 8 and 14.", "prototypes/p8_e2e_proto.py recorder (cvtColor dst=i420, VideoFrame.from_ndarray), camera loop jring copy and decoder np.copyto.")
act("minor", "[priorities] Ranks with no P1/P3 regression; rank 4 is detection only.",
    "Kept; rank 4 (now 5) explicitly says it prevents no loss; build order starts with copy.copy and the S-effort P1 fixes.", "recommend_result.json headline and rank 5.")

# ---------------- reproducibility critic
act("major", "[repro] Following the READMEs overwrites the cited results (fixed output names, appended logs, no output-dir option).",
    "Added research/frame_ring_buffer/fp_paths.py and the FRAME_PIPELINE_RESULTS_DIR option to bench_common.py, proto_common.py, the 3 run_with_load.py copies, prototypes/run_all.py, cpp/run_all.py, cpp/run_matrix.py, cpp/summarize.py, the summarizers and env snapshots; documented in each stage README. Verified that the default path is unchanged and that the variable redirects (scratch test). The revision stage's own runs use new file names.",
    "research/frame_ring_buffer/fp_paths.py; baseline/README.md, prototypes/README.md, cpp/README.md ('Keeping the cited results'). Pre-edit copies of the scripts: scratchpad backup_pre_paths/scripts.tar (session scratchpad).")
act("minor", "[repro] P6 720p 10 ms-poll rows not reproducible point values.",
    "prototypes/README.md now gives the range and the bimodality; rank 12 quotes ranges over 4 runs; only poll2ms is cited for 60/s.", "prototypes/README.md P6 section; p6_ui_skellycamvenv_rev_rep{2,3}.json.")
act("minor", "[repro] cpp_one_copy slowest-writer fps not reproducible (1488 -> 1207).",
    "cpp/README.md table 1a cell and a note now give ranges and the aggregate GB/s.", "cpp/README.md section 1 note; reproducibility/comparison.md.")
act("minor", "[repro] Baseline README '59.99-60.00 fps with 0 frames missed' for memcpy.",
    "Changed to '59.97-60.00 fps with 0-3 of about 9,000 never grabbed (3 idle runs)'.", "baseline/README.md 'What changed in the conclusions'.")
act("minor", "[repro] Summarizers merge every repeat into the summary.",
    "summarize_e2e.py takes an optional glob and output name; p8 --summarize honours P8_SUMMARY_GLOB / P8_SUMMARY_OUT; both behaviours documented in the READMEs.",
    "baseline/summarize_e2e.py; prototypes/p8_e2e_proto.py summarize(); baseline/results/e2ev_summary.md; prototypes/results/p8v_e2e_summary.md.")
act("minor", "[repro] cpp README prerequisites per step and the vswhere message.",
    "Documented which run_all.py steps need venv_cv48 and make_inputs.py, and that the vswhere message is expected.", "cpp/README.md 'Which prerequisite each run_all.py step needs'.")

oq = load(SS / "recommend_result.json")["open_questions"]
n_res = sum(a["resolved"] for a in A)
summary = (f"Addressed {len(A)} critic issues (2 blockers, {sum(a['severity'] == 'major' for a in A)} majors, {sum(a['severity'] == 'minor' for a in A)} minors); "
           f"{n_res} resolved with new or corrected evidence, {len(A) - n_res} partly resolved and carried as open questions. New idle benchmarks: real-stack "
           f"single-change variants (copy.copy removed alone: {fps(N1):.2f}/{fps(N2):.2f} fps vs {fps(H):.2f} HEAD), P8 with lockstep + metadata "
           f"({p8[LM1]['min_cam_fps']:.2f}/{p8[LM2]['min_cam_fps']:.2f} fps), P3 asymmetric stall (block+lockstep keeps sync; drop/no-lockstep desyncs by 606-639 ms), "
           f"P11 crash containers (killed MSMF .mp4 0/300 readable), P12 physical disk, P10 threads=1 unthrottled, deflate on real payloads, P6 repeats. "
           "recommend_result.json was rewritten (new rank 2; ranks renumbered with previous_rank) and the stage READMEs corrected.")
res = dict(summary=summary, actions=A, open_questions=oq)
(SS / "revision_result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(summary)
