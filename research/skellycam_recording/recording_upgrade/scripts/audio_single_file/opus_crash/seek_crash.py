# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""Seek accuracy on crashed (killed, NOT repaired) files, per reader, at many targets.

  prep <set>     : build <scratch>/opus_crash/sets/<set>/ and sets/<set>.json (files, decoded length L, CSV rows,
                   targets). Sets:
                     crash : one short kill per writer (the longest one) + the long (30-32 min) kill per writer,
                             plus fragpkt with dOps PreSkip patched to 0 (ps0) for both; 20 targets in [0, L) + 2 past
                             L (half-way into the samples the CSV has but the audio lost, and L + 0.5 s)
                     torn  : synthetic torn tails of the short kills (power loss / OS crash shapes a process kill
                             does not make): cut mid-mdat, mid-moof, inside a box header, zero-filled tail; 5 targets
                     repaired : built by repair_crash.py; 5 targets
  std <set>      : PyAV seek (pts-trusting app), ffmpeg -ss, VLC seek bar (libvlc set_time while playing) and
                   VLC --start-time, ffprobe duration, libvlc length
  electron <set> [--analyse-only] : the skellycam playback harness engine (../skellycam_playback/electron/player.js WcEngine,
                   unchanged) + Chromium decodeAudioData + <audio> currentTime seeks, in Electron 35.7.5 and 45.2.3
  blender <set>  : Blender 5.2.3 aud Sound.limit seeks + VSE strip length
Landing: opus_common.seek_landing (source index of the first non-silent output sample after the jump - target);
< 0 = early. Results: results/audio_single_file/opus_crash/seek_<reader>_<set>.json
"""
import base64
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

C, O = K.C, K.O
SR = K.RATE
HERE = K.HERE
REPO = os.path.normpath(os.path.join(HERE, *[".."] * 6))
ELECTRON = {
    "e35": os.path.join(REPO, "skellycam-ui", "node_modules", "electron", "dist", "electron.exe"),
    "e45": r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\106dc0c8-f977-4082-9d8d-367e9a9f721d\scratchpad\shared\electron-latest\node_modules\electron\dist\electron.exe",
}
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
SETS = os.path.join(K.SCRATCH, "sets")


def patch_ps0(path):
    d = bytearray(open(path, "rb").read(4096))
    j = d.find(b"dOps")
    with open(path, "r+b") as f:
        f.seek(j + 6); f.write(b"\0\0")


def decoded_len(path):
    info, x = O.decode_all(path)
    return info, x


def csv_cover(csv_path):
    if not os.path.exists(csv_path):
        return None
    cs = C.parse_csv(csv_path)
    last = cs["rows"][-1] if cs["rows"] else None
    return dict(rows=len(cs["rows"]), cover=(last[1] + last[2]) if last else 0, torn_bytes=cs["torn_bytes"], bad_rows=cs["bad_rows"],
                has_fit=any(l.startswith("# fit") for l in cs["footer"]), has_end=any(l.startswith("# end") for l in cs["footer"]))


def targets(L, cover, seed, full=True):
    rng = random.Random(seed)
    j = lambda: rng.randrange(48)  # noqa: E731
    lost = max(0, (cover or L) - L)
    if not full:
        return [int(0.5 * SR) + j(), L // 2 + j(), L - SR + j(), L - int(0.3 * SR) + j(), L + max(lost // 2, 100)]
    mid = sorted(rng.randrange(2 * SR, L - 3 * SR) for _ in range(11))
    t = [int(0.1 * SR) + j(), int(0.5 * SR) + j(), SR + j()] + mid + [L - int(s * SR) + j() for s in (2.0, 1.5, 1.0, 0.7, 0.4, 0.2)]
    return t + [L + max(lost // 2, 100), L + int(0.5 * SR)]


def prep(setname):
    d = os.path.join(SETS, setname)
    if setname != "repaired":  # repaired/ is written by repair_crash.py
        shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    files = []
    if setname == "crash":
        short = json.load(open(os.path.join(K.RESULTS, "make_crash_short.json")))["files"]
        lj = os.path.join(K.RESULTS, "make_crash_long.json")
        long_ = json.load(open(lj))["files"] if os.path.exists(lj) else []
        pick = {}
        for f in short:
            if f["writer"] not in pick or f["acked_samples"] > pick[f["writer"]]["acked_samples"]:
                pick[f["writer"]] = f
        clean = json.load(open(os.path.join(K.RESULTS, "make_crash_clean.json")))["files"]
        srcs = [("clean", f) for f in clean] + [("short", f) for f in pick.values()] + [("long", f) for f in long_]
        for sub, f in srcs:
            for ps0 in ([False, True] if f["writer"] == "fragpkt" else [False]):
                name = f["file"].replace("__", "_ps0__") if ps0 else f["file"]
                shutil.copy(os.path.join(K.SCRATCH, sub, f["file"]), os.path.join(d, name))
                shutil.copy(os.path.join(K.SCRATCH, sub, f["file"] + ".csv"), os.path.join(d, name + ".csv"))
                if ps0:
                    patch_ps0(os.path.join(d, name))
                files.append(dict(name=name, writer=f["writer"] + ("_ps0" if ps0 else ""), length=sub, acked=f["acked_samples"], full=True))
    elif setname == "torn":
        short = json.load(open(os.path.join(K.RESULTS, "make_crash_short.json")))["files"]
        for f in short:
            if not f["file"].endswith("term1" + K.WRITERS[f["writer"]][1]):
                continue
            b = open(os.path.join(K.SCRATCH, "short", f["file"]), "rb").read()
            stem, ext = os.path.splitext(f["file"])
            if ext == ".m4a":
                bx = K.boxes(b)
                last_mdat, last_moof = bx[-1], bx[-2]
                cuts = {"cut_mid_mdat": b[:last_mdat[1] + last_mdat[2] // 2], "cut_mid_moof": b[:last_moof[1] + 50],
                        "cut_in_box_header": b[:last_moof[1] + 3], "zero_tail_4k": b + bytes(4096),
                        "cut_mid_mdat_zero_tail": b[:last_mdat[1] + last_mdat[2] // 2] + bytes(4096)}
            elif ext == ".mka":
                cuts = {"cut_mid_block": b[:-150], "zero_tail_4k": b + bytes(4096)}
            else:
                cuts = {"cut_odd_byte": b[:-1], "zero_tail_4k": b + bytes(4096)}
            for k, v in cuts.items():
                name = f"{stem}_{k}{ext}"
                open(os.path.join(d, name), "wb").write(v)
                shutil.copy(os.path.join(K.SCRATCH, "short", f["file"] + ".csv"), os.path.join(d, name + ".csv"))
                files.append(dict(name=name, writer=f["writer"], length="short", acked=f["acked_samples"], full=False, torn=k))
    else:  # repaired: repair_crash.py wrote the files and sets/repaired.files.json
        files = json.load(open(os.path.join(SETS, "repaired.files.json")))
    for i, f in enumerate(files):
        p = os.path.join(d, f["name"])
        info, x = decoded_len(p)
        f["pyav"] = dict(samples=info["samples"], error=info["error"], duration_s=info.get("duration_s"))
        L = info["samples"]
        f["csv"] = csv_cover(p + ".csv")
        f["lost_vs_acked"] = f["acked"] - L
        f["targets"] = targets(L, f["csv"]["cover"] if f["csv"] else None, 20261116 + i, f.get("full", True))
        f["ffprobe"] = C.ffprobe(p)
        if f.get("torn"):  # decoded samples vs the intact killed file: same up to where, and what the tail holds
            _, x0 = decoded_len(os.path.join(K.SCRATCH, "short", f["name"].split("_cut")[0].split("_zero")[0] + os.path.splitext(f["name"])[1]))
            n = min(len(x), len(x0))
            dif = np.flatnonzero(x[:n] != x0[:n])
            f["vs_intact"] = dict(intact_samples=int(len(x0)), identical_prefix=int(dif[0]) if len(dif) else n, extra_samples=int(len(x) - len(x0)),
                                  extra_nonzero=int(np.count_nonzero(np.abs(x[len(x0):]) > 1e-4)) if len(x) > len(x0) else 0)
        print(f["name"], L, f["lost_vs_acked"], f["csv"] and f["csv"]["cover"] - L, f["pyav"]["error"], f["ffprobe"]["duration"], flush=True)
    json.dump(dict(set=setname, dir=d, files=files), open(os.path.join(SETS, setname + ".json"), "w"), indent=1)


def load_set(s):
    return json.load(open(os.path.join(SETS, s + ".json")))


def expect_shift(f):
    return K.PRESKIP if "ps0" in f["writer"] else 0  # ps0: file sample i holds device sample i - 312


def pyav_seek(path, tgt):
    """What a careful app trusting PyAV pts does: seek 200 ms before the target (backward; > the 80 ms Opus
    pre-roll), decode, cut at pts = target (frames are assumed contiguous from the first frame's pts)."""
    import av
    with av.open(path) as c:
        st = c.streams.audio[0]
        try:
            c.seek(int(max(0, tgt - SR // 5) * st.time_base.denominator / st.time_base.numerator / SR), stream=st)
        except Exception as e:  # noqa: BLE001
            return dict(error=f"seek {type(e).__name__}: {e}"[:200])
        chunks, first = [], None
        try:
            for fr in c.decode(st):
                if first is None:
                    first = int(round(fr.pts * (fr.time_base or st.time_base) * SR))
                chunks.append(fr.to_ndarray()[0])
                if first + sum(map(len, chunks)) > tgt + 2 * SR:
                    break
        except Exception as e:  # noqa: BLE001
            return dict(error=f"decode {type(e).__name__}: {e}"[:200], first_pts=first)
    if first is None:
        return dict(no_frames=True)
    x = np.concatenate(chunks).astype(np.float64)
    if np.abs(x).max() > 2:
        x /= 32768
    if tgt - first < 0:
        return dict(first_pts=first, first_after_target=first - tgt)
    return dict(first_pts=first, **K.land(x[tgt - first:], tgt, tgt + 3 * SR))


def ffmpeg_ss(path, tgt):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tgt / SR:.6f}", "-i", path, "-t", "1.5", "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], capture_output=True)
    y = np.frombuffer(p.stdout[: len(p.stdout) // 2 * 2], np.int16).astype(np.float64) / 32768
    return dict(rc=p.returncode, samples=int(len(y)), **K.land(y, tgt, tgt + 3 * SR))


def vlc_set_time(path, tgt, out):
    import vlc
    if os.path.exists(out):
        os.remove(out)
    inst = vlc.Instance("--aout=afile", f"--audiofile-file={out}", "--audiofile-wav", "--audiofile-format=s16",
                        "--audiofile-channels=1", "--no-video", "--quiet")
    pl = inst.media_player_new(); pl.set_media(inst.media_new_path(os.path.normpath(path))); pl.play()
    t0 = time.time()
    while pl.get_state() != vlc.State.Playing and time.time() - t0 < 6:
        time.sleep(0.01)
    time.sleep(0.6)
    t1 = time.time()
    rc = pl.set_time(int(round(tgt / SR * 1000)))
    time.sleep(1.2)
    res = dict(set_time_rc=rc, length_ms=pl.get_length(), time_ms=pl.get_time(), state=str(pl.get_state()), open_s=round(t1 - t0 - 0.6, 3))
    pl.stop(); pl.release(); inst.release()
    b = open(out, "rb").read() if os.path.exists(out) else b""
    i = b.find(b"data")
    y = np.frombuffer(b[i + 8:][: (len(b) - i - 8) // 2 * 2], np.int16) if i >= 0 else np.zeros(0, np.int16)
    if os.path.exists(out):
        os.remove(out)
    res["samples"] = int(len(y))
    # libvlc set_time takes ms: the request itself is up to 0.5 ms (24 samples) off the target
    req = int(round(tgt / SR * 1000)) * SR // 1000
    res["request_minus_target"] = req - tgt
    if len(y) > 4800:
        res.update(K.land(y, tgt, tgt + 3 * SR))
    return res


def vlc_start(path, tgt, out):
    rc, wall, y = C.vlc_afile(path, out, start_s=tgt / SR, run_s=1.0)
    res = dict(rc=rc, wall_s=wall, samples=0 if y is None else int(len(y)))
    if y is not None and len(y) > 4800:
        res.update(K.land(y[:, 0], tgt, tgt + 3 * SR))
    return res


def std(setname):
    S = load_set(setname)
    vdir = os.path.join(K.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    jobs = []
    for f in S["files"]:
        for i, t in enumerate(f["targets"]):
            jobs.append((f, i, t))

    def run(job):
        f, i, t = job
        p = os.path.join(S["dir"], f["name"])
        tag = f"{f['name']}_{i}"
        r = dict(file=f["name"], i=i, target=t, past_end=t >= f["pyav"]["samples"])
        t0 = time.perf_counter(); r["pyav"] = pyav_seek(p, t); r["pyav"]["s"] = round(time.perf_counter() - t0, 3)
        t0 = time.perf_counter(); r["ffmpeg_ss"] = ffmpeg_ss(p, t); r["ffmpeg_ss"]["s"] = round(time.perf_counter() - t0, 3)
        r["vlc_set_time"] = vlc_set_time(p, t, os.path.join(vdir, tag + ".st.wav"))
        r["vlc_start_time"] = vlc_start(p, t, os.path.join(vdir, tag + ".ss.wav"))
        print(tag, t, {k: (r[k].get("error_samples"), r[k].get("nonzero_len")) for k in ("pyav", "ffmpeg_ss", "vlc_set_time", "vlc_start_time")}, flush=True)
        return r

    t0 = time.time()
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(run, jobs))
    # libvlc length / seekable once per file (../libvlc_check.py, own interpreter)
    lst = os.path.join(K.SCRATCH, f"libvlc_{setname}.json")
    json.dump([os.path.join(S["dir"], f["name"]) for f in S["files"]], open(lst, "w"))
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "libvlc_check.py"), lst], check=True)
    lv = json.load(open(lst + ".out.json"))
    import av
    out = dict(set=setname, av=av.__version__, vlc=lv["vlc"], python_vlc=lv["python_vlc"], ffmpeg=os.popen("ffmpeg -version").readline().strip(),
               wall_s=round(time.time() - t0, 1), files={f["name"]: dict({k: v for k, v in f.items() if k != "targets"}, libvlc=lv["files"][os.path.join(S["dir"], f["name"])])
                                                          for f in S["files"]}, seeks=res)
    json.dump(out, open(os.path.join(K.RESULTS, f"seek_std_{setname}.json"), "w"), indent=1)


def b64f(s):
    return np.frombuffer(base64.b64decode(s), np.int16).astype(np.float64) / 32768


def electron(setname):
    S = load_set(setname)
    raw_dir = os.path.join(K.SCRATCH, "raw"); os.makedirs(raw_dir, exist_ok=True)
    cfg = dict(scratch=K.SCRATCH, files=[dict(name=f["name"], path=os.path.join(S["dir"], f["name"]), targets=f["targets"], L=f["pyav"]["samples"]) for f in S["files"]])
    cp = os.path.join(raw_dir, f"electron_{setname}.cfg.json"); json.dump(cfg, open(cp, "w"))
    for ev, exe in ELECTRON.items():
        raw = os.path.join(raw_dir, f"electron_{setname}_{ev}.json")
        env = dict(os.environ, CR_CFG=cp, CR_OUT=raw); env.pop("ELECTRON_RUN_AS_NODE", None)
        if "--analyse-only" not in sys.argv:  # else re-analyse the raw page output already in the scratchpad
            p = subprocess.run([exe, os.path.join(HERE, "electron", "main_crash.cjs")], env=env, capture_output=True, text=True, timeout=3600)
            print(ev, p.returncode, p.stdout[-200:], p.stderr[-400:] if p.returncode else "", flush=True)
        j = json.load(open(raw))
        files = {}
        for f, jf in zip(S["files"], j["files"]):
            L = f["pyav"]["samples"]
            a = {k: v for k, v in jf.items() if k not in ("wc",)}
            wc = jf.get("wc", {})
            a["wc"] = {k: v for k, v in wc.items() if k != "seeks"}
            a["wc"]["seeks"] = []
            for s in wc.get("seeks", []):
                e = {k: v for k, v in s.items() if k != "data"}
                if "data" in s:
                    y = b64f(s["data"])
                    e.update(K.land(y, s["n"], s["n"] + 3 * SR))
                    e["clicks"] = sorted(set(O.click_offsets(y[:e["nonzero_len"]], origin=s["n"])))
                    e["end_vs_decoded"] = s["n"] + e["nonzero_len"] - L  # where the returned audio stops vs PyAV's length
                a["wc"]["seeks"].append(e)
            if "decodeAudioData" in a and "length" in a["decodeAudioData"]:
                a["decodeAudioData"]["length_minus_pyav"] = a["decodeAudioData"]["length"] - L
            files[f["name"]] = a
        json.dump(dict(set=setname, electron=j["electron"], chrome=j["chrome"], files=files), open(os.path.join(K.RESULTS, f"seek_electron_{setname}_{ev}.json"), "w"), indent=1)


def blender(setname):
    S = load_set(setname)
    raw_dir = os.path.join(K.SCRATCH, "raw"); os.makedirs(raw_dir, exist_ok=True)
    npy = os.path.join(raw_dir, "blender_npy"); os.makedirs(npy, exist_ok=True)
    lst, out = os.path.join(raw_dir, f"blender_{setname}.in.json"), os.path.join(raw_dir, f"blender_{setname}.out.json")
    json.dump([[os.path.join(S["dir"], f["name"]), f["targets"]] for f in S["files"]], open(lst, "w"))
    p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", os.path.join(HERE, "blender_inner_crash.py"), "--", lst, out, npy],
                       capture_output=True, text=True, timeout=3600)
    raw = json.load(open(out))
    res = dict(set=setname, blender=raw["blender"], fps=raw["fps"], rc=p.returncode, stderr=p.stderr[-300:], files={})
    for f in S["files"]:
        r = raw["files"][os.path.join(S["dir"], f["name"])]
        L = f["pyav"]["samples"]
        a = {k: v for k, v in r.items() if k != "seeks"}
        a["vse_expected_frames"] = round(L / SR * raw["fps"], 3)
        a["seeks"] = []
        for s in r.get("seeks", []):
            e = {k: v for k, v in s.items() if k != "npy"}
            if "npy" in s:
                y = np.load(s["npy"]).astype(np.float64); os.remove(s["npy"])
                e.update(K.land(y, s["n"], s["n"] + 3 * SR))
            a["seeks"].append(e)
        res["files"][f["name"]] = a
        print(f["name"], a.get("aud_samples"), L, a.get("vse_frame_final_duration"), a["vse_expected_frames"], [s.get("error_samples") for s in a["seeks"]], flush=True)
    json.dump(res, open(os.path.join(K.RESULTS, f"seek_blender_{setname}.json"), "w"), indent=1)


if __name__ == "__main__":
    {"prep": prep, "std": std, "electron": electron, "blender": blender}[sys.argv[1]](sys.argv[2])
