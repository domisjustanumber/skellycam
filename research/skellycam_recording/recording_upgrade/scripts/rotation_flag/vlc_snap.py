"""VLC 3 snapshot of a paused video via the rc interface (TCP), so the picture comes from VLC's video output
(after any orientation handling), not from the scene filter (which sits before it).

Usage: python -I vlc_snap.py <video> <out_dir> [vout]      (vout default: dummy)
Writes <out_dir>/snap*.png and <out_dir>/vlc.log; prints JSON.
"""
import glob, json, os, socket, subprocess, sys, time

VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"


def snap(video, out, vout="dummy", port=47123, timeout=40):
    video, out = os.path.normpath(os.path.abspath(video)), os.path.normpath(os.path.abspath(out))
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "snap*.png")):
        os.remove(f)
    log = os.path.join(out, "vlc.log")
    args = [VLC, "-I", "rc", f"--rc-host=127.0.0.1:{port}", "--rc-quiet", f"--vout={vout}", "--no-audio",
            "--start-paused", "--no-loop", "--snapshot-path=" + out, "--snapshot-format=png",
            "--snapshot-prefix=snap", "--no-snapshot-preview", "--no-osd", "--no-video-title-show",
            "--verbose=2", "--file-logging", f"--logfile={log}", video]
    p = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = dict(vout=vout)
    t0 = time.time()
    s = None
    try:
        while time.time() - t0 < 15:
            try:
                s = socket.create_connection(("127.0.0.1", port), timeout=2); break
            except OSError:
                time.sleep(0.3)
        if s is None:
            res["error"] = "no rc connection"
        else:
            def cmd(c, wait=1.0):
                s.sendall((c + "\n").encode()); time.sleep(wait)
                try:
                    s.settimeout(0.3); return s.recv(65536).decode(errors="replace")
                except OSError:
                    return ""
            time.sleep(2.0)                 # let the input open and the vout start
            cmd("frame", 1.0)               # step one frame so a picture reaches the vout
            res["rc_snapshot_reply"] = cmd("snapshot", 2.0).strip()[-200:]
            cmd("quit", 0.5)
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill(); rc = "timeout"
    finally:
        if s: s.close()
    res["rc"] = rc
    res["pngs"] = sorted(os.path.basename(f) for f in glob.glob(os.path.join(out, "snap*.png")))
    return res


if __name__ == "__main__":
    print(json.dumps(snap(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or [])), indent=1))
