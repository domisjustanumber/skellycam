# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""Readers on the files left by kill_opus.py (killed + clean), before and after a lossless remux repair.
Same checks as ../readers.py, with timing (click offsets, correlation lag) instead of bit-exactness:
PyAV (count, start offset, every click in the file), ffprobe duration, ffmpeg CLI count and offset, CSV sidecar
(rows vs decoded audio), VLC 3.0.24 afile playback (count, start offset), VLC --start-time at 50 % + 1 s run (landing
error via opus_common.seek_landing), libvlc length/seekable (../libvlc_check.py).
Repair = `ffmpeg -c copy` into <scratch>/opus/repaired (Ogg, Matroska/WebM: same container; fragmented MP4: plain
MP4 with +faststart). lost = acked samples - samples PyAV decodes (FFmpeg applies pre-skip / edit list).

Usage: uv run --script .../opus/readers_opus.py     Output: results/audio_single_file/opus/readers_opus.json
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

C = O.C
HERE = os.path.dirname(os.path.abspath(__file__))


def vlc_checks(path, expected, n_src):
    tag = os.path.basename(path)
    vdir = os.path.join(O.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    rc, wall, x = C.vlc_afile(path, os.path.join(vdir, tag + ".play.wav"))
    play = dict(rc=rc, wall_s=wall, samples=None if x is None else int(len(x)))
    if x is not None and len(x):
        play.update(O.timing(x, n_src))
    target = int(round(expected * 0.5 / O.RATE, 3) * O.RATE)
    rc, wall, y = C.vlc_afile(path, os.path.join(vdir, tag + ".seek.wav"), start_s=target / O.RATE, run_s=1.0)
    seek = dict(rc=rc, target=target, samples=None if y is None else int(len(y)))
    if y is not None and len(y) > 4800:
        seek.update(O.seek_landing(y, O.src_f(n_src), target))
    return play, seek


def check(path, acked, csv_path=None, do_vlc=True):
    n_src = acked + 10 * O.RATE
    r = dict(bytes=os.path.getsize(path), ffprobe=C.ffprobe(path))
    info, x = O.decode_all(path)
    r["pyav"] = dict(info, **O.timing(x, n_src))
    r["lost_samples_pyav"] = acked - info["samples"]
    xf, rc = O.ffmpeg_f(path)
    r["ffmpeg"] = dict(rc=rc, samples=int(len(xf)), click_offsets=sorted(set(O.click_offsets(xf))) if len(xf) > O.RATE else None)
    if csv_path and os.path.exists(csv_path):
        cs = C.parse_csv(csv_path)
        last = cs["rows"][-1] if cs["rows"] else None
        r["csv"] = dict(rows_ok=len(cs["rows"]), bad_rows=cs["bad_rows"], torn_bytes=cs["torn_bytes"], bytes=os.path.getsize(csv_path),
                        rows_cover_samples=(last[1] + last[2]) if last else 0)
        r["csv_minus_audio_samples"] = r["csv"]["rows_cover_samples"] - info["samples"]
    if do_vlc:
        r["vlc_play"], r["vlc_start_time"] = vlc_checks(path, max(acked, 2 * O.RATE), n_src)
    return r


def repair(path, rdir):
    ext = os.path.splitext(path)[1]
    out = os.path.join(rdir, os.path.basename(path))
    if os.path.exists(out):
        os.remove(out)
    extra = ["-f", "mp4", "-movflags", "+faststart"] if ext == ".m4a" else []  # .m4a alone picks the ipod muxer (no Opus)
    t0 = time.perf_counter()
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy", *extra, out], capture_output=True)
    return out, dict(rc=p.returncode, ms=round((time.perf_counter() - t0) * 1e3, 1), stderr=p.stderr.decode(errors="replace")[-200:],
                     ok=p.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0)


def main():
    km = json.load(open(os.path.join(O.RESULTS, "kill_opus.json")))
    kdir, cdir = os.path.join(O.SCRATCH, "killed"), os.path.join(O.SCRATCH, "clean")
    rdir = os.path.join(O.SCRATCH, "repaired"); os.makedirs(rdir, exist_ok=True)
    jobs = [("killed", os.path.join(kdir, k["file"]), k) for k in km["kills"]]
    jobs += [("clean", os.path.join(cdir, c["file"]), dict(c, acked_samples=c["samples"])) for c in km["clean"]]

    def run(job):
        kind, path, meta = job
        r = dict(kind=kind, file=meta["file"], format=meta["format"], method=meta.get("method"), acked_samples=meta["acked_samples"])
        r.update(check(path, meta["acked_samples"], path + ".csv"))
        if kind == "killed":
            rp, r["repair"] = repair(path, rdir)
            if r["repair"]["ok"]:
                r["repaired"] = check(rp, meta["acked_samples"], None, do_vlc=meta.get("method") == "term")
        return r

    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(run, jobs))
    lst = os.path.join(O.SCRATCH, "libvlc_list.json")
    paths = [os.path.join(kdir if r["kind"] == "killed" else cdir, r["file"]) for r in res]
    paths += [os.path.join(rdir, r["file"]) for r in res if "repaired" in r]
    json.dump(paths, open(lst, "w"))
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "libvlc_check.py"), lst], check=True)
    lv = json.load(open(lst + ".out.json"))
    for r in res:
        r["libvlc"] = lv["files"][os.path.join(kdir if r["kind"] == "killed" else cdir, r["file"])]
        if "repaired" in r:
            r["repaired"]["libvlc"] = lv["files"][os.path.join(rdir, r["file"])]
    out = dict(vlc=lv["vlc"], python_vlc=lv["python_vlc"], av=C.av.__version__,
               ffmpeg=os.popen("ffmpeg -version").readline().strip(), wall_s=round(time.time() - t0, 1), results=res)
    json.dump(out, open(os.path.join(O.RESULTS, "readers_opus.json"), "w"), indent=1, default=str)
    print("files", len(res), "wall", out["wall_s"])


if __name__ == "__main__":
    main()
