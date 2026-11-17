# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""WAV past 4 GiB (stereo s16 48 kHz: 4 GiB = 6.2 h; mono 12.4 h). Unpaced writes of the index signal.
  rf64auto_clean  : PyAV wav muxer rf64=auto, closed cleanly at ~4.6 GB (FFmpeg turns it into RF64 at close)
  rf64auto_killed : same writer, os._exit at ~4.6 GB (header never converted), then repaired in place
  stdlib          : Python's wave module (skellycam today), writing until it fails or reaches 4.6 GB
Readers at 23,500 s (sample 1,128,000,000; byte offset ~4.51 GB, past 4 GiB): ffprobe duration, PyAV seek,
ffmpeg -ss, VLC --start-time (afile), libvlc length. Blender: blender_check.py picks up <scratch>/big/*.wav.

Usage: uv run --script .../big_wav.py      Output: results/audio_single_file/big_wav.json
"""
import fractions
import json
import os
import subprocess
import sys
import time
import wave

import av
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asf_common as C  # noqa: E402

TARGET_BYTES = 4_600_000_000
BLK = 480_000  # 10 s per write
SEEK_S = 23_500.0
BDIR = os.path.join(C.SCRATCH, "big")


def write_pyav(path, kill):
    out = av.open(path, "w", format="wav", options={"rf64": "auto", "flush_packets": "1"})
    st = out.add_stream("pcm_s16le", rate=C.RATE, layout="stereo")
    tb = fractions.Fraction(1, C.RATE)
    n = 0
    while n * 4 < TARGET_BYTES:
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(C.sig(n, BLK).reshape(1, -1)), format="s16", layout="stereo")
        fr.sample_rate, fr.pts, fr.time_base = C.RATE, n, tb
        for p in st.encode(fr):
            out.mux(p)
        n += BLK
    if kill:
        os._exit(1)
    out.close()


def write_stdlib(path):
    w = wave.open(path, "wb")
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(C.RATE)
    n, err = 0, None
    try:
        while n * 4 < TARGET_BYTES:
            w.writeframes(C.sig(n, BLK).tobytes())
            n += BLK
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"[:200]
    try:
        w.close()
    except Exception as e:  # noqa: BLE001
        err = (err or "") + f" | close: {type(e).__name__}: {e}"[:200]
    return dict(samples_written_before_error=n, error=err)


def pyav_seek(path):
    try:
        with av.open(path) as c:
            st = c.streams.audio[0]
            c.seek(int(SEEK_S / st.time_base), stream=st)
            for fr in c.decode(st):
                x = fr.to_ndarray().reshape(-1, 2)
                loc = C.locate(x, int(SEEK_S * C.RATE))
                return dict(loc, error_samples=None if loc["n0"] is None else loc["n0"] - int(SEEK_S * C.RATE))
    except Exception as e:  # noqa: BLE001
        return dict(error=f"{type(e).__name__}: {e}"[:200])
    return dict(error="no frame")


def ffmpeg_seek(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(SEEK_S), "-i", path, "-t", "0.5", "-f", "s16le", "-"], capture_output=True)
    x = np.frombuffer(r.stdout[: len(r.stdout) // 4 * 4], np.int16).reshape(-1, 2)
    loc = C.locate(x, int(SEEK_S * C.RATE))
    return dict(loc, samples=int(len(x)), rc=r.returncode, error_samples=None if loc["n0"] is None else loc["n0"] - int(SEEK_S * C.RATE))


def vlc_seek(path, name):
    rc, wall, y = C.vlc_afile(path, os.path.join(BDIR, name + ".vlcseek.wav"), start_s=SEEK_S, run_s=0.5, timeout=120)
    if y is None or not len(y):
        return dict(rc=rc, samples=None if y is None else 0)
    loc = C.locate(y, int(SEEK_S * C.RATE))
    return dict(loc, rc=rc, samples=int(len(y)), error_samples=None if loc["n0"] is None else loc["n0"] - int(SEEK_S * C.RATE))


def read_all(path, name):
    return dict(header=C.riff_info(path), ffprobe=C.ffprobe(path), pyav_seek=pyav_seek(path), ffmpeg_seek=ffmpeg_seek(path),
                vlc_seek=vlc_seek(path, name))


def libvlc(paths):
    lst = os.path.join(BDIR, "libvlc_list.json")
    json.dump(paths, open(lst, "w"))
    subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "libvlc_check.py"), lst], check=True)
    return json.load(open(lst + ".out.json"))["files"]


def main():
    os.makedirs(BDIR, exist_ok=True)
    res = dict(target_bytes=TARGET_BYTES, seek_s=SEEK_S, seek_sample=int(SEEK_S * C.RATE), files={})
    clean, killed, std = (os.path.join(BDIR, f) for f in ("rf64auto_clean.wav", "rf64auto_killed.wav", "stdlib.wav"))
    if not os.path.exists(clean):
        t0 = time.time(); write_pyav(clean, False); res["write_s_clean"] = round(time.time() - t0, 1)
    if not os.path.exists(killed):
        t0 = time.time()
        p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--write-killed", killed])
        res["write_s_killed"], res["killed_exit"] = round(time.time() - t0, 1), p.returncode
    res["files"]["rf64auto_clean"] = read_all(clean, "rf64auto_clean")
    res["files"]["rf64auto_killed"] = read_all(killed, "rf64auto_killed")
    lv = libvlc([clean, killed])
    res["files"]["rf64auto_clean"]["libvlc"], res["files"]["rf64auto_killed"]["libvlc"] = lv[clean], lv[killed]
    rep = os.path.join(BDIR, "rf64auto_killed_repaired.wav")
    os.replace(killed, rep)
    res["repair"] = C.repair_in_place(rep)
    res["files"]["rf64auto_killed_repaired"] = read_all(rep, "rf64auto_killed_repaired")
    res["files"]["rf64auto_killed_repaired"]["libvlc"] = libvlc([rep])[rep]
    t0 = time.time()
    res["stdlib"] = write_stdlib(std)
    res["stdlib"]["write_s"] = round(time.time() - t0, 1)
    res["stdlib"]["header"] = C.riff_info(std)
    res["stdlib"]["ffprobe"] = C.ffprobe(std)
    os.remove(std)
    json.dump(res, open(os.path.join(C.RESULTS, "big_wav.json"), "w"), indent=1, default=str)
    print(json.dumps(res, default=str)[:3000])


def repair_only():
    """Re-run the repair and its readers on the repaired file (after a repair fix); keeps the other results."""
    p = os.path.join(C.RESULTS, "big_wav.json")
    res = json.load(open(p))
    rep = os.path.join(BDIR, "rf64auto_killed_repaired.wav")
    res["repair"] = C.repair_in_place(rep)
    res["files"]["rf64auto_killed_repaired"] = read_all(rep, "rf64auto_killed_repaired")
    res["files"]["rf64auto_killed_repaired"]["libvlc"] = libvlc([rep])[rep]
    json.dump(res, open(p, "w"), indent=1, default=str)
    print(json.dumps(res["files"]["rf64auto_killed_repaired"], default=str))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--repair-only":
        repair_only()
    elif len(sys.argv) > 2 and sys.argv[1] == "--write-killed":
        write_pyav(sys.argv[2], True)
    else:
        main()
