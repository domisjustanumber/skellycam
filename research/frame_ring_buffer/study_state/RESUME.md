# Frame ring buffer study: state

Status as of 2026-10-28 (after the 20261027 overnight run and its report audit): **all stages done**. The report is complete.
What is still open is listed under "Open items" below; none of it blocks reading or acting on the report.

## Location (moved 2026-10-28) and how to resume

On 2026-10-28 this folder moved from `benchmarks/frame_pipeline/` to `research/frame_ring_buffer/`
(`C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer`). It is at the same depth, so the scripts' repo-root
math (`parents[2]`) is unchanged; `.venv-bench` was rebuilt in place with the same packages. Every script, README,
workflow script and `study_state/*.json` file now uses the new path.

Paths recorded before 2026-10-28 in results/ and journals refer to the old location `benchmarks/frame_pipeline`
(moved to `research/frame_ring_buffer`). That covers every `results/` and `results_*/` folder, `*.log`, the `*.jsonl`
journals and transcripts in this folder, `../reproducibility/*.json`, `../revision/run_revision_log.txt` and the built
binaries in `../cpp/build/`; they were left as recorded.

How to resume: nothing needs resuming (see "Open items"). To re-run stages, start the workflow with
scriptPath `C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\study_state\continue_workflow.js`
and args `{skip: [...]}` naming the finished stages to skip (`prototypes`, `cpp`, `recommend`), or the overnight wrapper
`C:\Users\Dom\GitHub\freemocap\skellycam\research\frame_ring_buffer\study_state\overnight_workflow.js` with args
`{stamp: 'YYYYMMDD'}` (it re-runs everything, then revises and re-audits the report doc). The original run's script is
`original_workflow.js` in this folder (identical copy: `../workflows/frame-ring-buffer-analysis-wf_c08d445c-b09.js`).
Set `FRAME_PIPELINE_RESULTS_DIR` before any re-run, or the scripts overwrite the cited results.

## What the study is

The task, as asked:

> Review skellycam and freemocap and create a report that shows how the frame buffer is used to move images between them.
> Record how images are loaded into the buffer, how they are read, and how control messages work.
> Show where each UI taps its outputs and where the SkellyCam > FreeMoCap flow happens.
> Make no assertion without a code reference or a link to test output with code that reproduces it.
> Then suggest how to optimise the process for higher throughput. Research best practices for high-throughput video pipelines,
> and whether porting code to C++ would raise throughput, with code and test results to prove the claims.
> Priorities: 1. disk writes must never drop; 2. highest throughput (goal: 5 cameras at 60+ fps); 3. no frame copies unless necessary.

Pinned commits: SkellyCam `23ccbf208e43879bfc74fc01049e5af2a623933d` (development). FreeMoCap `5632778af10e22befd4ec0a719ba844f14a84e93` (development).
FreeMoCap's venv runs SkellyCam `777b058ceafb578c55092179506cd8a925a38b50` (main).
Reference sizes: 1280x720 and 1920x1080 BGR (the user gave no resolution).

Which numbers are idle and which are provisional: `../PROVISIONAL.md`.

## Stage status

| Stage | Status | Output |
|---|---|---|
| Map (5 areas: write, read, control, ui, fmc) | Done (2026-10-25) | `verified_maps.json` (`map` per area) |
| Verify (adversarial, per area) | Done (2026-10-25): 167 claims (123 confirmed, 43 corrected, 1 refuted, 0 unverifiable) (corrected 2026-10-28; was "172 claims (123 confirmed, 43 corrected, 1 refuted, 5 unverifiable)"), 55 missed facts added | `verified_maps.json` (`verification`), compact form in `verified_digest.json` |
| Research: best practices, Python vs C++ | Done (2026-10-25) | `research.json` |
| Benchmark: baseline | Done, **re-run idle in the 20261027 run** (2026-10-28 00:59-01:27) | `baseline_result.json`, `../baseline/` (README.md, scripts, results/); loaded first run kept in `baseline_result_provisional_20261025.json` and `../baseline/results_provisional_20261025/` |
| Benchmark: prototypes P1-P10 | Done idle in the 20261027 run (01:44-03:20); `p10_msmf_threads` provisional (Defender scan), superseded by the idle `p10v_msmf_threads` | `prototypes_result.json`, `../prototypes/` |
| Benchmark: C++ comparison | Done idle in the 20261027 run | `cpp_result.json`, `../cpp/` (`results/cpp_comparison.md`) |
| Recommend | Done; rewritten by the revision stage | `recommend_result.json` (pre-revision copy: `recommend_result_pre_revision.json`) |
| Critique: evidence, priorities, reproducibility re-run | Done | `critic_evidence_result.json`, `critic_priorities_result.json`, `critic_reproduce_result.json`, `../reproducibility/` (`comparison.md`: 130 of 136 throughput rows within 15%, all pass/fail rows unchanged) |
| Revision (34 critic issues: 30 resolved, 4 partly) | Done idle (2026-10-28 06:10-07:06): e2ev single-change variants, P8 with lockstep + metadata, P3 ASYM, P10v, P11 crash containers, P12 physical disk, deflate, P6 repeats | `revision_result.json`, `../revision/` |
| Report (Claude Doc) | Done: every section filled; audited 2026-10-28 (see below) | https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it |

## The report

Claude Doc: https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it
(doc id `610a6b1c-1f2a-4bb4-95ef-02f4b8ca0a15`, tab file `cee6e77d-fec3`, body node `36d22330-cfd9`).
Sections: Summary, Architecture overview (diagram), Write path, Read paths, Control messages, UI taps and handoff,
Measured baseline (chart), Best practices, C++ port evaluation (chart), Recommendations (chart, 15 ranks), Reproducing the results.
No pending blocks remain.

Audit of 2026-10-28 (report auditor, 20261027 run). Every number in the doc was checked against the result files; code refs were spot-checked at the pinned commits. Corrections made in the doc:

- Write path: in-loop `put_frame` cost said 3.56-3.73 ms citing `e_e2e_summary.md`, which shows 3.64-3.73 ms (3.56 is the finalizer's figure). Now 3.64-3.73 ms at 5x1080p MJPEG + UI.
- Read paths: the 0-tear result at L=388 (the 720p ring) was paired with the 1080p ring time (2.87 s). Now "720p ring (388 slots) ... 6.5 s at 720p, 2.87 s at 1080p" (`../prototypes/results/p2_seqlock_read.md` part A).
- UI taps: "the UI got 36.6-40.8 payloads/s" now says "at 1080p" (720p runs gave 57.0-58.9/s).
- Rank 7 and the Recommendations chart: the 59.82 / 59.95 fps prototype was labelled "with 6, 11, 13". P8 copies the decoded frame into the slot (no retrieve-into-slot, rank 11) and polls the gate with `time.sleep(1e-5)` (no event wake, rank 13) (`../prototypes/p8_e2e_proto.py` L17, L175, L193-194). Relabelled "seqlock ring + decoupled recorder, lockstep (6, 7)".
- Rank 13: "a gate on one int64 array waited 0.03-0.18 ms" was the camera-0 median only. Per-camera medians are 0.03-6.4 ms (`lockstep_gate_wait` in `../prototypes/results/p8v_e2e_1080p_imdecode_msmf_lockstep_meta{,_rep2}.json`; corrected 2026-10-28; was `..._lockstep_meta*.json`, which also matches the `_recthread` and `_extracpu3` runs, and all four together span 0.01-6.70 ms). Corrected in the doc.
- Not recommended: hevc_nvenc / libx264 "56 fps and 46 fps" now says these are the slowest recorder's rates (`p5_nvenc.md`).
- Byline as-of date moved from 2026-10-25 to 2026-10-28.

`recommend_result.json` rank 13 `expected_impact` was fixed at the end of the run (07:32:48, `../../overnight_run_20261027/OVERNIGHT_LOG.md`) and now says "waited 0.03-6.4 ms median per camera", which matches the doc (corrected 2026-10-28; was "Not corrected (not a doc file): ... still says 'waited 0.03-0.18 ms median'; the doc is right, the JSON is not.").

## Open items

From `revision_result.json` (`open_questions`, unresolved actions) and the audit:

- Real 5x60 capture: no attached UVC camera delivered more than 30.1 fps (`../prototypes/results/p9_real_camera.md`); USB bandwidth with 5 real cameras, and real per-frame capture CPU at 60 fps, are unmeasured. All 5x60 numbers use synthetic cameras.
- Disk never-drop is not guaranteed: antivirus (Defender real-time scan) and GC stalls through the real encoders over a 10-minute 5x1080p60 recording were not measured (P12 measured raw write-through only).
- NVENC session exhaustion / driver-reset handling (rank 14) and the rank-1 fault-injection test were specified but not built.
- Whether FreeMoCap's posthoc reader accepts MKV / fragmented MP4 (ranks 2 and 8).
- Hybrid CPU placement (P-cores vs E-cores) was not controlled; no affinity-pinned repeat.
- Event-wake latency for the lockstep gate (rank 13) was not measured.
- No browser was attached in the UI benchmarks.

Nothing needs resuming. A follow-up would be a new task (for example, real 60 fps cameras, or implementing ranks 9, 3, 4, 5 and 2).
Any re-run must set `FRAME_PIPELINE_RESULTS_DIR` first, or the scripts overwrite the cited results (see each stage README).

## Runs

| Run | When | What |
|---|---|---|
| Original workflow `wf_c08d445c-b09` | 2026-10-25 | Map, verify, research, baseline (loaded, provisional), partial prototypes; paused by Dom at 18:50 |
| Overnight run 20261027 | night of 2026-10-27/28 (workflow `wf_8fd1ec97-b0e`, 00:57:41 to 07:32:48) (corrected 2026-10-28; was "00:59 to about 07:10") | Idle baseline re-run, prototypes P1-P10, C++ comparison, recommend, three critiques, reproducibility re-run, revision, report fill, report audit (`overnight_workflow.js`) |

## Files in this folder

| File | Contents |
|---|---|
| `RESUME.md` | This file |
| `overnight_workflow.js` | Workflow script of the 20261027 overnight run |
| `continue_workflow.js` | Earlier continuation script (superseded by `overnight_workflow.js`; kept for reference) |
| `original_workflow.js` | The original full workflow script (for reference) |
| `journal_wf_c08d445c-b09.jsonl` | Raw journal of the original run |
| `verified_maps.json` | Per area: the mapper's output and the verifier's verdicts |
| `verified_digest.json` | Compact verified map (non-refuted claims, missed facts, copies, flow, risks) |
| `research.json` | The two research results |
| `baseline_result.json` | Baseline structured result (idle 20261027) |
| `baseline_result_provisional_20261025.json` | Baseline structured result of the loaded 2026-10-25 run (comparison only) |
| `prototypes_result.json` | Prototypes P1-P10 structured result |
| `prototypes_partial_transcript.jsonl` | Transcript of the stopped 2026-10-25 prototypes agent |
| `cpp_result.json` | C++ comparison structured result |
| `critic_evidence_result.json`, `critic_priorities_result.json`, `critic_reproduce_result.json` | The three critiques |
| `recommend_result.json` | Final recommendations (after revision); `recommend_result_pre_revision.json` is the earlier version |
| `revision_result.json` | What the revision stage changed, its new evidence and the open questions |
