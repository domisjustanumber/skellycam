# Times N runs of `uv run --script camera_identity.py` (wall clock incl. uv start-up) and saves keys + times.
import json, subprocess, sys, time
out = sys.argv[1]; runs = []
for i in range(5):
    t = time.perf_counter()
    p = subprocess.run(["uv", "run", "--script", "research/usb_cameras/naming/camera_identity.py"], capture_output=True, text=True)
    dt = time.perf_counter() - t
    keys = [c["key"] for c in json.loads(p.stdout)] if p.returncode == 0 else p.stderr[-500:]
    runs.append(dict(i=i, seconds=round(dt, 3), rc=p.returncode, keys=keys))
json.dump(dict(command="uv run --script research/usb_cameras/naming/camera_identity.py (x5, wall clock incl uv)", runs=runs), open(out, "w"), indent=1)
print(json.dumps([(r["seconds"], r["rc"]) for r in runs])); print(runs[-1]["keys"])
