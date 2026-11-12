"""Which VLC 3 capture methods show orientation? Runs the scene filter, rc `snapshot` (dummy and Direct3D11 vouts)
and the window screen grab on H90.mp4 (the one file VLC rotates on screen) and on B90.mkv.

Usage: python -I vlc_methods_check.py <media_dir> <result_json>
"""
import glob, json, os, subprocess, sys
import cv2

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import vlc_snap, vlc_window                 # noqa: E402
from probe_all import orient                # noqa: E402


def scene(video, out, timeout=60):
    video, out = os.path.normpath(video), os.path.normpath(out)
    os.makedirs(out, exist_ok=True)
    args = [vlc_snap.VLC, "-I", "dummy", "--vout=dummy", "--play-and-exit", "--no-loop", "--no-audio", "--avcodec-hw=none",
            "--video-filter=scene", "--scene-format=png", "--scene-ratio=10", f"--scene-path={out}", "--scene-prefix=f", video]
    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill(); rc = "timeout"
    pngs = sorted(glob.glob(os.path.join(out, "f*.png")))
    return dict(rc=rc, frame=orient(cv2.imread(pngs[0])) if pngs else None)


def main(media, out_json):
    d = os.path.join(media, "1280x720"); work = os.path.join(d, "methods")
    res = {}
    for f in ("H90.mp4", "B90.mkv", "D90.mp4"):
        v = os.path.join(d, f); w = os.path.join(work, f)
        r = res[f] = {"scene_filter": scene(v, os.path.join(w, "scene"))}
        for vout in ("dummy", "direct3d11"):
            s = vlc_snap.snap(v, os.path.join(w, "snap_" + vout), vout)
            r["rc_snapshot_" + vout] = dict(rc=s["rc"], frame=orient(cv2.imread(os.path.join(w, "snap_" + vout, s["pngs"][0]))) if s["pngs"] else None)
        g = vlc_window.run(v, os.path.join(w, "window"))
        r["window_grab"] = dict(client_w=g.get("client_w"), client_h=g.get("client_h"),
                                frame=orient(cv2.imread(os.path.join(w, "window", "window.png"))))
        print(f, json.dumps({k: (x.get("frame") or {}).get("label") for k, x in r.items()}), flush=True)
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
