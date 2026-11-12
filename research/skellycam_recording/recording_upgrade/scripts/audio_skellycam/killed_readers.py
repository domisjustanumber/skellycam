"""Readers and repair on the files left by crash_kill.py.

Per killed file: ffprobe (errors, duration), ffmpeg CLI decode (samples, errors), VLC 3.0.24 transcode dump
(samples). For the kill at 10.4 s of each format/method: VLC's playback path (afile audio output, real time).
Repair = `ffmpeg -c copy` into the same container; reports time, the repaired file's decode and, for FLAC,
the STREAMINFO total-samples field before and after.

Usage: python -I killed_readers.py <crash_kill.json> <out_json>
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ac_common import FFMPEG, FORMATS, SCRATCH, VLC, decode_ffmpeg, decode_pyav, decode_vlc, ffprobe, flac_streaminfo  # noqa: E402


def vlc_play_samples(path):
    dst = path + ".afile.wav"
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run([VLC, "-I", "dummy", "--play-and-exit", "--no-video", "--aout=afile", f"--audiofile-file={dst}",
                    "--audiofile-wav", "--audiofile-format=s16", "--audiofile-channels=1", path, "vlc://quit"],
                   capture_output=True, timeout=120)
    if not os.path.exists(dst):
        return None
    b = open(dst, "rb").read(); os.remove(dst)
    rate = int.from_bytes(b[24:28], "little")
    i = b.find(b"data")
    return dict(samples=(len(b) - i - 8) // 2, rate=rate)


def main():
    ck = json.load(open(sys.argv[1]))
    work = os.path.join(SCRATCH, "killed")
    rep_dir = os.path.join(SCRATCH, "repaired"); os.makedirs(rep_dir, exist_ok=True)
    out = []
    for r in ck["results"]:
        path = os.path.join(work, r["file"])
        if not os.path.exists(path):
            out.append(dict(file=r["file"], missing=True)); continue
        name = r["format"]; f = FORMATS[name]
        row = dict(file=r["file"], format=name, method=r["method"], kill_s=r["kill_s"], acked=r["acked"], pyav_decoded=r["decoded"])
        row["ffprobe"] = ffprobe(path)
        row["ffmpeg"] = decode_ffmpeg(path)
        row["vlc"] = decode_vlc(path, work)
        if r["kill_s"] == 10.4:
            row["vlc_play"] = vlc_play_samples(path)
        # repair
        rp = os.path.join(rep_dir, r["file"])
        t0 = time.perf_counter()
        p = subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-c", "copy", "-f", f["fmt"], rp], capture_output=True)
        row["repair"] = dict(rc=p.returncode, wall_s=round(time.perf_counter() - t0, 3), stderr=p.stderr.decode(errors="replace")[-200:])
        if os.path.exists(rp):
            d = decode_pyav(rp)
            row["repair"].update(decoded=d["samples"], error=d["error"], ffprobe_duration=ffprobe(rp)["duration"])
            if f["fmt"] == "flac":
                row["repair"]["streaminfo_after"] = flac_streaminfo(rp)
                row["streaminfo_before"] = flac_streaminfo(path)
            os.remove(rp)
        print(r["file"], "pyav", r["decoded"], "ff", row["ffmpeg"]["samples"], "vlc", row["vlc"]["samples"],
              "probe_dur", row["ffprobe"]["duration"], "repair", row["repair"].get("decoded"), flush=True)
        out.append(row)
    json.dump(dict(results=out), open(sys.argv[2], "w"), indent=1)


if __name__ == "__main__":
    main()
