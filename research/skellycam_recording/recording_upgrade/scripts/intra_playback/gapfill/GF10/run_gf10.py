# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF10 (2026-11-10): WebCodecs scrub with bounded GPU memory (functional; NO timing recorded).

Runs the copied harness (./harness, test 'wcscrub') once per configuration, one Electron launch each, sequentially:
  modes reuse | pool | baseline  x  clips h264_nvenc / hevc_nvenc / h264_qsv 1080p30 intra mp4 (PyAV 19.0.2 clips of
  topic intra_playback)  x  N = 1, 4, 8 streams  x  Electron 35.7.5 / 45.2.3.
Every stream steps through the same fixed list of 240 targets (seeded; forward steps, backward steps, random jumps).
GPU-process memory is sampled by Electron main (app.getAppMetrics, memory.privateBytes kept in its raw unit) at fixed
target counts (every 20 targets), plus before decoders exist, after configure, after close and 3 s after close.
CPU fields that main.cjs records are dropped from the saved output (timing rule: no CPU / rate / latency).

Usage (repo root):
  uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/gapfill/GF10/run_gf10.py \
      [--electron 35,45] [--modes reuse,pool,baseline] [--ns 1,4,8] [--codecs h264_nvenc,hevc_nvenc,h264_qsv]
      [--targets 240] [--cap 25000000] [--tag main] [--baseline-ns 1,4] [--drive lockstep|free] [--readevery M]
Raw per-config JSON -> TEMP/raw/<tag>/ ; consolidated -> results/intra_playback/gapfill/GF10_wc_scrub_memory.json (--merge)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE / "harness"
REPO = Path(__file__).resolve().parents[7]
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/intra_playback/gapfill"
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF10")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback")
ELECTRON = {
    "35": REPO / "skellycam-ui/node_modules/electron/dist/electron.exe",
    "45": Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe"),
}
CLIPS = {"h264_nvenc": "c1080p30/h264_nvenc_intra.mp4", "hevc_nvenc": "c1080p30/hevc_nvenc_intra.mp4", "h264_qsv": "c1080p30/h264_qsv_intra.mp4"}
SEED = 20261110
FRAMES = 600


def target_list(n: int, seed: int = SEED, frames: int = FRAMES) -> tuple[list[int], dict]:
    """Fixed scrub sequence: runs of +1 steps (5-20), runs of -1 steps (5-20), single random jumps."""
    rng = random.Random(seed)
    k = rng.randrange(frames)
    seq = [k]
    comp = {"fwd_step": 0, "back_step": 0, "jump": 0}
    while len(seq) < n:
        r = rng.random()
        if r < 0.8:
            d = 1 if r < 0.4 else -1
            for _ in range(rng.randint(5, 20)):
                if len(seq) >= n:
                    break
                if not 0 <= k + d < frames:
                    d = -d
                k += d
                seq.append(k)
                comp["fwd_step" if d == 1 else "back_step"] += 1
        else:
            j = k
            while j == k:
                j = rng.randrange(frames)
            k = j
            seq.append(k)
            comp["jump"] += 1
    return seq, comp


def run_one(ver: str, cfg: dict, out: Path, timeout_s: int) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
    env["CSS_MEDIA_ROOT"] = str(MEDIA)
    params = "&".join(f"{k}={v}" for k, v in cfg.items())
    cmd = [str(ELECTRON[ver]), str(HARNESS), "--test=wcscrub", f"--out={out}", f"--timeout={timeout_s}",
           "--noocclusion=1", "--medialog=1", f"--params={params}"]
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout_s + 90)
    if not out.exists():
        return {"result": {"error": f"no output; rc {p.returncode}; {p.stdout[-1500:]} {p.stderr[-1500:]}"}}
    d = json.loads(out.read_text())
    # timing rule: drop CPU fields
    d.pop("metrics_summary", None)
    for s in d.get("metrics_samples") or []:
        s.pop("cpu", None)
        s.pop("cum_cpu_s", None)
    # keep only GPU-process background samples (raw unit) to keep the file small
    d["bg_samples_gpu"] = [{"t": s["t"], "pid": s["pid"], "private_kb": s["private_kb"], "ws_kb": s["ws_kb"]}
                           for s in (d.pop("metrics_samples", None) or []) if s["type"] == "GPU"]
    out.write_text(json.dumps(d, indent=1))
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--electron", default="35,45")
    ap.add_argument("--modes", default="reuse,pool,baseline")
    ap.add_argument("--ns", default="1,4,8")
    ap.add_argument("--baseline-ns", default="1,4")
    ap.add_argument("--codecs", default="h264_nvenc,hevc_nvenc,h264_qsv")
    ap.add_argument("--targets", type=int, default=240)
    ap.add_argument("--pool", type=int, default=3)
    ap.add_argument("--cap", type=int, default=25000000)
    ap.add_argument("--tag", default="main")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--drive", default="lockstep", choices=["lockstep", "free"], help="free: streams walk the list independently")
    ap.add_argument("--readevery", type=int, default=1, help="read the frame index on every M-th target (0 = never)")
    a = ap.parse_args()
    ks, comp = target_list(a.targets)
    raw = TEMP / "raw" / a.tag
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "_targets.json").write_text(json.dumps({"seed": SEED, "frames": FRAMES, "n": a.targets, "composition": comp, "targets": ks}))
    plan = []
    for ver in a.electron.split(","):
        for mode in a.modes.split(","):
            ns = a.baseline_ns if mode == "baseline" else a.ns
            for codec in a.codecs.split(","):
                for n in ns.split(","):
                    plan.append((ver, mode, codec, n))
    for i, (ver, mode, codec, n) in enumerate(plan):
        cfg = {"clip": CLIPS[codec], "n": n, "mode": mode, "pool": str(a.pool), "cap": str(a.cap), "ks": ",".join(map(str, ks)), "testtimeout": str(a.timeout), "drive": a.drive, "readevery": str(a.readevery)}
        out = raw / f"e{ver}__{mode}{'_free' if a.drive == 'free' else ''}{'' if a.readevery == 1 else f'_re{a.readevery}'}__{codec}__n{n}.json"
        try:
            d = run_one(ver, cfg, out, a.timeout)
            r = d.get("result") or {}
            if "error" in r:
                msg = f"ERROR {str(r['error'])[:200]}"
            else:
                ps = r.get("per_stream", [])
                msg = (f"errors {sum(s['errors'] for s in ps)} exact {sum(s['exact'] for s in ps)}/{a.targets * len(ps)} "
                       f"gpu_peak {max((g['private_kb'] for m in r['marks'] for g in m['gpu']), default=None)} "
                       f"gone {len(d.get('child_process_gone') or [])} aborted {r.get('aborted_at_count')}")
        except Exception as e:  # noqa: BLE001
            msg = f"EXC {e}"[:300]
        print(f"[{i + 1}/{len(plan)}] e{ver} {mode} {codec} n{n}: {msg}", flush=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
