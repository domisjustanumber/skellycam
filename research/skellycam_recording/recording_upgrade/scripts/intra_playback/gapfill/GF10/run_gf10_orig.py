# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF10 control: the ORIGINAL bench scrub page logic (test 'scrub', path webcodecs, wcflush=1, dur 8, speed 90; unchanged
code in the GF10 harness copy, = harness.mjs:461-515 of the original) re-run functionally WITHOUT bench=1, so no rate or
latency fields are produced. Kept: per-stream error counts, GPU-process private_kb samples (500 ms sampler of main.cjs),
child-process-gone events, gpu_feature_status. presents / input_events / CPU fields are dropped (timing rule).

  uv run --script .../GF10/run_gf10_orig.py [--electron 35,45] [--ns 4,8] [--codecs h264_nvenc] [--medialog 0]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from run_gf10 import CLIPS, ELECTRON, HARNESS, MEDIA, TEMP  # same folder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--electron", default="35,45")
    ap.add_argument("--ns", default="4,8")
    ap.add_argument("--codecs", default="h264_nvenc")
    ap.add_argument("--medialog", default="0")
    ap.add_argument("--tag", default="orig")
    a = ap.parse_args()
    raw = TEMP / "raw" / a.tag
    raw.mkdir(parents=True, exist_ok=True)
    for ver in a.electron.split(","):
        for codec in a.codecs.split(","):
            for n in a.ns.split(","):
                out = raw / f"e{ver}__origscrub{'_ml' if a.medialog == '1' else ''}__{codec}__n{n}.json"
                params = f"clip={CLIPS[codec]}&path=webcodecs&n={n}&dur=8&speed=90&wcflush=1"
                env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}
                env["CSS_MEDIA_ROOT"] = str(MEDIA)
                cmd = [str(ELECTRON[ver]), str(HARNESS), "--test=scrub", f"--out={out}", "--timeout=300", "--noocclusion=1",
                       f"--medialog={a.medialog}", f"--params={params}"]
                if out.exists():
                    out.unlink()
                subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=400)
                if not out.exists():
                    print(f"e{ver} {codec} n{n}: no output", flush=True)
                    continue
                d = json.loads(out.read_text())
                d.pop("metrics_summary", None)
                d["bg_samples_gpu"] = [{"t": s["t"], "pid": s["pid"], "private_kb": s["private_kb"], "ws_kb": s["ws_kb"]}
                                       for s in (d.pop("metrics_samples", None) or []) if s["type"] == "GPU"]
                r = d.get("result") or {}
                r.pop("input_events", None)
                for s in r.get("per_stream", []):
                    s.pop("presents", None)
                    s.pop("distinct_frames", None)
                out.write_text(json.dumps(d, indent=1))
                g = d["bg_samples_gpu"]
                print(f"e{ver} {codec} n{n}: errors {[s.get('errors') for s in r.get('per_stream', [])]} "
                      f"gpu_peak {max((s['private_kb'] for s in g), default=None)} pids {len({s['pid'] for s in g})} "
                      f"gone {len(d.get('child_process_gone') or [])} video_decode {d['gpu_feature_status'].get('video_decode')} "
                      f"err {r.get('error')}", flush=True)
                time.sleep(2)


if __name__ == "__main__":
    main()
