"""What happens to an sfn26-style recording (ffmpeg child fed MJPEG on stdin, plain MP4 out) when something dies?

Mirrors skellycam-rust/src/recording/recorder.rs (upstream/sfn26): ffmpeg -y -f image2pipe -c:v mjpeg -s WxH -r 30
-i pipe:0 -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -an <out>.mp4 (no -movflags).
Here a Python 'feeder' process plays the Rust recorder's role. Cases (feed N/2 frames, then):
  clean            feeder closes stdin (what finish() does) and waits
  ffmpeg_killed    TerminateProcess on ffmpeg only (what VideoRecorder::drop does: ffmpeg_child.kill())
  feeder_killed    TerminateProcess on the feeder only; ffmpeg is NOT killed and sees EOF on its stdin
  tree_killed      taskkill /F /T on the feeder (kills feeder and ffmpeg together)
Also the same four cases with the ffmpeg CLI writing MKV and fragmented MP4, and the CLI's own flushing behaviour.

usage: python sfn26_pipe_test.py [--n 600] [--tag sfn26_pipe]   (--n 150 --tag sfn26_pipe_n150 shows the probe delay)
writes results/crash_resilience/sfn26_pipe.json/.md ; media under MEDIA/sfn26_pipe/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402

OUTS = {
    "mp4_sfn26": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-an"],
    "mkv_x264": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-an"],
    "fmp4_x264": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-an",
                  "-movflags", "frag_keyframe+empty_moov+default_base_moof"],
    "mkv_mjpeg_copy": ["-c:v", "copy", "-an"],
}
EXT = {"mp4_sfn26": "mp4", "mkv_x264": "mkv", "fmp4_x264": "mp4", "mkv_mjpeg_copy": "mkv"}


def feeder_main(out_kind, out_path, n_feed, n_total):
    """Child role: spawn ffmpeg, feed frames, print progress; for 'clean' close stdin after n_total."""
    w, h = cc.corpus_dims()
    jp = cc.load_jpegs(cc.DEFAULT_SET, n_total)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-s", f"{w}x{h}", "-r", str(cc.FPS),
           "-i", "pipe:0", *OUTS[out_kind], out_path]
    errf = open(out_path + ".ffmpeg_stderr.txt", "w")
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
    print(f"FFPID {ff.pid}", flush=True)
    for i in range(n_feed):
        ff.stdin.write(jp[i])
        ff.stdin.flush()
        print(f"F {i + 1}", flush=True)
    if n_feed >= n_total:
        ff.stdin.close()
        ff.wait()
        print(f"CLEAN {ff.returncode}", flush=True)
        return
    print("IDLE", flush=True)
    sys.stdin.readline()


def pid_alive(pid: int) -> bool:
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def run_case(out_kind, case, n, media: Path) -> dict:
    out = media / f"{out_kind}__{case}.{EXT[out_kind]}"
    cc.rm(out)
    n_feed = n if case == "clean" else n // 2
    pr = subprocess.Popen([str(cc.VENV_PY), __file__, "--feeder", out_kind, str(out), str(n_feed), str(n)],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    ffpid = None
    fed = 0
    res = {"out_kind": out_kind, "case": case}
    for line in pr.stdout:
        line = line.strip()
        if line.startswith("FFPID"):
            ffpid = int(line.split()[1])
        elif line.startswith("F "):
            fed = int(line.split()[1])
        elif line.startswith("CLEAN"):
            res["ffmpeg_exit"] = int(line.split()[1])
        elif line == "IDLE":
            time.sleep(1.0)  # let ffmpeg consume the pipe
            if case == "ffmpeg_killed":
                subprocess.run(["taskkill", "/F", "/PID", str(ffpid)], capture_output=True)
                time.sleep(0.5)
                pr.kill()
            elif case == "feeder_killed":
                pr.kill()
            elif case == "tree_killed":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pr.pid)], capture_output=True)
            break
    pr.wait(timeout=60)
    t0 = time.time()
    while ffpid and pid_alive(ffpid) and time.time() - t0 < 60:
        time.sleep(0.25)
    res["ffmpeg_alive_after_60s"] = bool(ffpid and pid_alive(ffpid))
    res["frames_fed"] = fed
    res["bytes"] = out.stat().st_size if out.exists() else 0
    rd = cc.read_any(out, "mkv" if EXT[out_kind] == "mkv" else "mp4", None)
    res["summary"] = cc.summarize_read(rd)
    res["read"] = rd
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--feeder", nargs=4, default=None)
    ap.add_argument("--tag", default="sfn26_pipe")
    a = ap.parse_args()
    if a.feeder:
        k, o, nf, nt = a.feeder
        feeder_main(k, o, int(nf), int(nt))
        return
    media = cc.MEDIA / a.tag
    media.mkdir(parents=True, exist_ok=True)
    ffv = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    res = {"ffmpeg": ffv, "n": a.n, "runs": []}
    for k in OUTS:
        for case in ("clean", "ffmpeg_killed", "feeder_killed", "tree_killed"):
            r = run_case(k, case, a.n, media)
            s = r["summary"]
            print(k, case, r["frames_fed"], r["bytes"], s["ffprobe"], s["pyav"], s["cv2"], s["pyav_err"][:60], flush=True)
            res["runs"].append(r)
    (cc.RES / f"{a.tag}.json").write_text(json.dumps(res, indent=1, default=str))
    L = ["# sfn26-style ffmpeg-child recording under kills (generated by sfn26_pipe_test.py)", "", f"{ffv}; N={a.n}; "
         "kill cases feed N/2 frames, wait 1 s, then kill. ffprobe/PyAV/cv2 = frames readable without repair.", "",
         "| output | case | fed | ffmpeg exit | ffmpeg alive 60 s later | bytes | ffprobe | PyAV | cv2 | dur (s) | PyAV error |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["runs"]:
        s = r["summary"]
        L.append(f"| {r['out_kind']} | {r['case']} | {r['frames_fed']} | {r.get('ffmpeg_exit', '')} | {r['ffmpeg_alive_after_60s']} | "
                 f"{r['bytes']} | {s['ffprobe']} | {s['pyav']} | {s['cv2']} | {s['dur']} | {s['pyav_err'][:60]} |")
    (cc.RES / f"{a.tag}.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
