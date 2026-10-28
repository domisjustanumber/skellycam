# Provisional results

## Status after the 20261027 overnight run

| folder / run | status | evidence |
|---|---|---|
| `baseline/results/`: all of bench_a .. bench_g, the 8 e2e runs, summarize_e2e, repro_type_overloads_spawn, the 3 diagnostics | **Measured idle on 20261027** (night of 2026-10-27/28, 00:59-01:27). Every run met the idle rule: background CPU mean 2.0-4.1% (corrected 2026-10-28; was 2.0-4.0%) and p95 2.9-7.2%, and system CPU 2.9-5.1% before and 3.3-5.1% after each run | `baseline/results/load_summary.md` (from `baseline/summarize_load.py`), `baseline/results/load_*.json` (from `baseline/run_with_load.py`); comparison table in `baseline/README.md`, section "20261027 idle re-run"; structured result `study_state/baseline_result.json` |
| `baseline/results_provisional_20261025/` and `study_state/baseline_result_provisional_20261025.json` | **Provisional** (2026-10-25, loaded machine). Kept only for comparison | this file, section below |
| `prototypes/results/`: P1-P8, P9/P9b (real cameras), P10 | **Measured idle on 2026-10-28** (01:44-03:20). Every measuring run met the same idle rule (background mean 1.6-3.9%, p95 2.5-6.1%), except `p10_msmf_threads`, which the rule labels provisional because Windows Defender scanned its last row's files at the end (max 22.7%, after-window 18.2%). Its paced rows ran before that and saw at most 6.1% background | `prototypes/results/load_summary.md`, `prototypes/results/load_*.json` (from `prototypes/run_with_load.py`); `prototypes/README.md`; `study_state/prototypes_result.json` |
| `prototypes/results_partial_20261025/` (the stopped agent's partial p1, p2, p4, p6, p8) | **Provisional** (loaded machine). Kept only for reference; superseded by `prototypes/results/` | `study_state/RESUME.md` |
| REVISION stage (2026-10-28 06:10-07:06): `baseline/results/e2ev_*`, `h_deflate.*`; `prototypes/results/p8v_e2e_*`, `p10v_*`, `p11_*`, `p3v_*`, `p12_*`, `p6_ui_skellycamvenv_rev_rep*` | **Measured idle**: every measuring step met the idle rule (background mean 1.9-4.6%, p95 3.0-8.0%). A blocked smoke-test process stayed alive 06:09-06:21 during the `e2ev_*` steps; it is included in their background load | `revision/README.md`, `revision/run_revision_log.txt`, `load_*.json` next to each result |
| `cpp/` (2026-10-28 03:44-04:44), `reproducibility/` (2026-10-28 05:13-06:02) | **Measured idle**: every measuring step met the idle rule (C++: background mean 1.6-3.7%, p95 2.2-5.2%; reproducibility re-run: background mean 2.0-3.6%, p95 3.1-5.9%). The sub-second `largepages_probe`, `p6_ui_summarize` and `p8_e2e_summarize` steps had no load sample and are labelled provisional for that reason only (corrected 2026-10-28; was "Not yet run when the baseline re-run finished. Later overnight stages must record their own load") | `cpp/results/load_summary.md`, `cpp/README.md` ("Machine load and environment"); `reproducibility/load_summary_rerun.md` |

Idle rule used for the baseline re-run: background CPU (every process outside the benchmark's process tree, as % of the whole
28-thread machine) mean < 10% and p95 < 10% during the run, and system CPU < 10% in 3 s windows before and after it.
`baseline/run_with_load.py` records and applies the rule; use it (or equivalent load records) for later stages, so that each run can be labelled the same way.

What the idle re-run changed: most numbers moved by 0-30%, and the conclusions held, except for three points that the
baseline README lists under "What changed in the conclusions":
- 5x1080p mjpeg e2e now reaches 53.6 fps instead of 44-47 fps, still short of 60.
- The UI has a small measurable cost on capture (1 run).
- The 1080p UI build is about 9 ms, so the relay's 10 ms sleep plus the build, not the build alone, limits the UI to about 46 payloads/s.

## 2026-10-25 first run (provisional)

All results from the first run on 2026-10-25 are **provisional**: `baseline/` (now `baseline/results_provisional_20261025/`),
and the stopped prototypes agent's partial results (now `prototypes/results_partial_20261025/`). `cpp/` and `reproducibility/` did not run on 2026-10-25; they first ran, idle, in the 20261027 run (corrected 2026-10-28; was "`prototypes/`, `cpp/` and `reproducibility/`").

The machine was not idle while they ran. Other workloads (browser, IDE, chat apps, other agents) were active.
A load snapshot at 2026-10-25T14:37 (during `baseline/`) showed 62% average CPU load and 61% memory in use.

What this means:

- Absolute numbers (fps, GB/s, ms per frame) may be lower and noisier than on a quiet machine. The 20261027 baseline re-run confirmed this.
  For example, 5x1080p mjpeg e2e reached 44-47 fps loaded and 53.6 fps idle.
- Relative comparisons measured back to back in the same script are more trustworthy than absolute values, but contention can still skew them.
- Reproducibility re-runs may differ from the originals because the background load changed, not only because of the code.

Re-run every benchmark on an idle machine before treating any number as final.
