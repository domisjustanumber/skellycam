"""Where a frame-pipeline stage writes its results (added 2026-10-28 by the REVISION stage, answering the reproducibility
critic: re-running a documented command used to overwrite the result files the reports cite).

Default (variable unset): <stage>/results, exactly as before.
With FRAME_PIPELINE_RESULTS_DIR=<dir>: <dir>/<stage folder name>/results (created on demand), e.g.
    $env:FRAME_PIPELINE_RESULTS_DIR = "C:\\temp\\fp_rerun"   ->   C:\\temp\\fp_rerun\\baseline\\results\\...
Used by bench_common.py, proto_common.py, the three run_with_load.py copies, run_all.py (prototypes, cpp), cpp/run_matrix.py,
the summarizers and env_snapshot.py. Inputs that are deliberately read from the original tree (cpp/summarize.py reading
baseline/results/a_write.json) are not redirected.
"""
from __future__ import annotations

import os
from pathlib import Path


def results_dir(stage_dir: Path) -> Path:
    root = os.environ.get("FRAME_PIPELINE_RESULTS_DIR")
    if not root:
        p = Path(stage_dir) / "results"
    else:
        p = Path(root) / Path(stage_dir).name / "results"
    p.mkdir(parents=True, exist_ok=True)
    return p
