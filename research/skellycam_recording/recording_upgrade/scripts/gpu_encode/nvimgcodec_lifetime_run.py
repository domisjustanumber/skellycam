"""Runs nvimg_life.py for several sequences (each in a fresh process) and records CUDA error
# (short file name on purpose: uv names the env after the script and a long name pushed the DLL path past Windows MAX_PATH)
counts. Run (repo root): python research/skellycam_recording/recording_upgrade/scripts/gpu_encode/nvimgcodec_lifetime_run.py
Writes results/gpu_encode/nvimgcodec_lifetime.json. Uses UV_CACHE_DIR from the environment if set."""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
res = {}
for seq in ("d1", "d8", "dl1", "eh1", "ed1", "ec1", "dl1,d8", "ed1,d8"):
    r = subprocess.run(["uv", "run", "--script", str(HERE / "nvimg_life.py"), seq], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300)
    txt = r.stdout + r.stderr
    res[seq] = {"returncode": r.returncode, "ok_steps": [ln for ln in r.stdout.splitlines() if ln.startswith("ok")],
                "cuda_700_lines": txt.count("#700")}
    print(seq, res[seq])
(HERE.parents[1] / "results/gpu_encode/nvimgcodec_lifetime.json").write_text(json.dumps(res, indent=1))
