# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""Readers on the files left by kill_matrix.py (killed + clean), before and after an in-place header repair.

Per file: header fields (WAV/RF64 sizes, FLAC STREAMINFO total), PyAV decode (count, exact prefix of the
index signal), ffprobe duration, ffmpeg CLI count, CSV sidecar (rows that pass CRC, torn tail, rows vs audio),
VLC 3.0.24 playback path (afile, real time: count and exact prefix), VLC seek (--start-time at 50 %, 1 s run:
error in samples), libvlc length / is_seekable / position seek (python-vlc on the installed libvlc).
Repair: copy to <scratch>/repaired, asf_common.repair_in_place (header bytes only), re-check.

Usage: uv run --script .../readers.py      Output: results/audio_single_file/readers.json
"""
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402


def header(path):
    return C.flac_streaminfo(path) if path.endswith(".flac") else C.riff_info(path) if path.endswith(".wav") else None


def pyav_check(path):
    r, x = C.decode_pyav(path)
    r.update(C.locate(x, 0))
    return r


def vlc_checks(path, expected):
    tag = os.path.basename(path)
    vdir = os.path.join(C.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    rc, wall, x = C.vlc_afile(path, os.path.join(vdir, tag + ".play.wav"))
    play = dict(rc=rc, wall_s=wall, samples=None if x is None else int(len(x)))
    if x is not None:
        play.update(C.locate(x, 0))
    target_s = round(expected / C.RATE * 0.5, 3)
    rc, wall, y = C.vlc_afile(path, os.path.join(vdir, tag + ".seek.wav"), start_s=target_s, run_s=1.0)
    seek = dict(rc=rc, target_s=target_s, samples=None if y is None else int(len(y)))
    if y is not None and len(y):
        loc = C.locate(y, int(target_s * C.RATE))
        seek.update(loc)
        if loc["n0"] is not None:
            seek["error_samples"] = loc["n0"] - int(round(target_s * C.RATE))
        # VLC may emit leading silence before the first decoded sample after a seek
        nz = int((y != 0).any(axis=1).argmax())
        if loc["n0"] is None and nz:
            loc2 = C.locate(y[nz:], int(target_s * C.RATE))
            seek.update({"lead_zero_samples": nz, **loc2})
            if loc2["n0"] is not None:
                seek["error_samples"] = loc2["n0"] - int(round(target_s * C.RATE)) - nz
    return play, seek


def check(path, acked, csv_path=None, do_vlc=True):
    r = dict(header=header(path), ffprobe=C.ffprobe(path), ffmpeg=C.ffmpeg_samples(path))
    r["pyav"] = pyav_check(path)
    r["lost_samples_pyav"] = acked - r["pyav"]["samples"]
    if csv_path and os.path.exists(csv_path):
        cs = C.parse_csv(csv_path)
        last = cs["rows"][-1] if cs["rows"] else None
        r["csv"] = dict(rows_ok=len(cs["rows"]), bad_rows=cs["bad_rows"], torn_bytes=cs["torn_bytes"],
                        footer=cs["footer"], bytes=os.path.getsize(csv_path),
                        rows_cover_samples=(last[1] + last[2]) if last else 0,
                        contiguous=all(a[1] + a[2] == b[1] for a, b in zip(cs["rows"], cs["rows"][1:])))
        r["csv_minus_audio_samples"] = r["csv"]["rows_cover_samples"] - r["pyav"]["samples"]
    if do_vlc:
        r["vlc_play"], r["vlc_seek"] = vlc_checks(path, max(acked, 2 * C.RATE))
    return r


def main():
    km = json.load(open(os.path.join(C.RESULTS, "kill_matrix.json")))
    kdir, cdir = os.path.join(C.SCRATCH, "killed"), os.path.join(C.SCRATCH, "clean")
    rdir = os.path.join(C.SCRATCH, "repaired"); os.makedirs(rdir, exist_ok=True)
    jobs = [("killed", os.path.join(kdir, k["file"]), k) for k in km["kills"]]
    jobs += [("clean", os.path.join(cdir, c["file"]), dict(c, acked_samples=c["samples"])) for c in km["clean"]]

    def run(job):
        kind, path, meta = job
        r = dict(kind=kind, file=meta["file"], format=meta["format"], method=meta.get("method"),
                 acked_samples=meta["acked_samples"])
        r.update(check(path, meta["acked_samples"], path + ".csv"))
        if kind == "killed" and not path.endswith(".mka"):
            rp = os.path.join(rdir, meta["file"])
            shutil.copyfile(path, rp)
            r["repair"] = C.repair_in_place(rp)
            r["repaired"] = check(rp, meta["acked_samples"], None, do_vlc=meta.get("method") == "term")
        return r

    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(run, jobs))
    # libvlc in its own interpreter, sequentially (the afile runs above are parallel subprocesses)
    lst = os.path.join(C.SCRATCH, "libvlc_list.json")
    paths = [os.path.join(kdir if r["kind"] == "killed" else cdir, r["file"]) for r in res]
    paths += [os.path.join(rdir, r["file"]) for r in res if "repaired" in r]
    json.dump(paths, open(lst, "w"))
    subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "libvlc_check.py"), lst], check=True)
    lv = json.load(open(lst + ".out.json"))
    for r in res:
        r["libvlc"] = lv["files"][os.path.join(kdir if r["kind"] == "killed" else cdir, r["file"])]
        if "repaired" in r:
            r["repaired"]["libvlc"] = lv["files"][os.path.join(rdir, r["file"])]
    out = dict(vlc=lv["vlc"], python_vlc=lv["python_vlc"], av=C.av.__version__,
               ffmpeg=os.popen("ffmpeg -version").readline().strip(), wall_s=round(time.time() - t0, 1), results=res)
    with open(os.path.join(C.RESULTS, "readers.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print("files", len(res), "wall", out["wall_s"])


if __name__ == "__main__":
    main()
