# /// script
# requires-python = "==3.12.*"
# dependencies = []
# ///
"""Runs the playback harness (electron/main.cjs + player.js) in Electron 35.7.5 and 45.2.3, one process per run.

Usage: uv run --script run.py <set> [filter]      sets: smoke, short, long, nofit, naive, elprobe, cont
Raw results: <scratch>/audio_single_file/skellycam_playback/raw/<run id>.json (analyse.py reads them).
Needs gen_take.py short / long first. A window opens per run (real vsync); output is muted (gain 0).
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = (r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496"
           r"\scratchpad\audio_single_file\skellycam_playback")
ELECTRON = {
    "e35": os.path.normpath(os.path.join(HERE, *[".."] * 6, "skellycam-ui", "node_modules", "electron", "dist", "electron.exe")),
    "e45": r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\106dc0c8-f977-4082-9d8d-367e9a9f721d\scratchpad\shared\electron-latest\node_modules\electron\dist\electron.exe",
}
FORMATS = {"wav": ".audio.wav", "flac": ".audio.flac", "opus": ".audio.m4a", "opus_ps0": ".audio_ps0.m4a"}
rnd = random.Random(20261115)
PLANS = {
    "short": dict(cams=["cam0", "cam1", "cam2"], content=[1.5, 20.0, 45.0],
                  plan=[dict(op="play", t=0.2, dur=8), dict(op="play", t=40, dur=5), dict(op="play", t=12, dur=5),
                        dict(op="scrub", ts=[round(rnd.uniform(5, 55), 3) for _ in range(20)], dt=60), dict(op="play", t=50, dur=5)]),
    "long": dict(cams=["cam0"], content=[1.5, 1800.0, 3540.0],
                 plan=[dict(op="play", t=0.2, dur=4), dict(op="play", t=1800, dur=4), dict(op="play", t=3540, dur=5),
                       dict(op="play", t=300, dur=4), dict(op="scrub", ts=[round(rnd.uniform(10, 3590), 3) for _ in range(10)], dt=60),
                       dict(op="play", t=2400, dur=4)]),
    "cont": dict(cams=["cam0"], content=[], plan=[dict(op="play", t=60, dur=600)]),
}


def runs(which):
    out = []
    for ev in ELECTRON:
        if which in ("smoke", "short", "long"):
            take = "short" if which == "smoke" else which
            for fmt in FORMATS:
                for eng in ("buf", "wc", "el"):
                    out.append(dict(id=f"{which}_{ev}_{fmt}_{eng}", ev=ev, take=take, fmt=fmt, engine=eng, clock="out", map="fit", plan=take))
        elif which == "nofit":  # what the CSV fit buys on the long take
            for fmt in ("wav", "opus"):
                for eng in ("wc", "el"):
                    out.append(dict(id=f"nofit_{ev}_{fmt}_{eng}", ev=ev, take="long", fmt=fmt, engine=eng, clock="out", map="nofit", plan="long"))
        elif which == "naive":  # clock from ctx.currentTime instead of getOutputTimestamp; element clock corrected by outputLatency
            for eng in ("buf", "wc"):
                out.append(dict(id=f"naive_{ev}_wav_{eng}", ev=ev, take="short", fmt="wav", engine=eng, clock="naive", map="fit", plan="short"))
            for fmt in FORMATS:  # element clock minus ctx.outputLatency
                out.append(dict(id=f"naive_{ev}_{fmt}_ellat", ev=ev, take="short", fmt=fmt, engine="el", clock="ellat", map="fit", plan="short"))
        elif which == "elprobe":  # electron/elprobe.js: does currentTime include output latency when played direct?
            out.append(dict(id=f"elprobe_{ev}", ev=ev, take="short", fmt="wav", engine="el", clock="out", map="fit", plan="short", elprobe=True))
        elif which == "cont":  # 10 minutes of continuous play on the long take
            for eng in ("wc", "el"):
                out.append(dict(id=f"cont_{ev}_wav_{eng}", ev=ev, take="long", fmt="wav", engine=eng, clock="out", map="fit", plan="cont"))
    return out


def main():
    which = sys.argv[1]
    filt = sys.argv[2] if len(sys.argv) > 2 else ""
    rl = [r for r in runs(which) if filt in r["id"]]
    if which == "smoke":
        rl = rl[:1]
    os.makedirs(os.path.join(SCRATCH, "raw"), exist_ok=True)
    for r in rl:
        p = PLANS[r["plan"]]
        cfg = dict(scratch=SCRATCH, take_dir=os.path.join(SCRATCH, r["take"]), audio=r["take"] + FORMATS[r["fmt"]],
                   engine=r["engine"], clock=r["clock"], map=r["map"], run=r, elprobe=r.get("elprobe", False), **p)
        cp = os.path.join(SCRATCH, "raw", r["id"] + ".cfg.json")
        json.dump(cfg, open(cp, "w"))
        env = dict(os.environ, PB_CFG=cp, PB_OUT=os.path.join(SCRATCH, "raw", r["id"] + ".json"))
        env.pop("ELECTRON_RUN_AS_NODE", None)
        pr = subprocess.run([ELECTRON[r["ev"]], os.path.join(HERE, "electron", "main.cjs")], env=env,
                            capture_output=True, text=True, timeout=3600)
        print(r["id"], pr.returncode, pr.stdout.strip()[-200:], pr.stderr.strip()[-300:] if pr.returncode else "", flush=True)


if __name__ == "__main__":
    main()
