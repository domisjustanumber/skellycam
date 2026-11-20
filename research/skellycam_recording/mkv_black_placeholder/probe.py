"""Probe the placeholder files with ffprobe, ffmpeg, PyAV, OpenCV and skellycam's SequentialVideoReader.

Usage: python probe.py MEDIA_DIR   (writes MEDIA_DIR/probe_results.json)
Reference = the full file of the same camera config decoded by the same tool: every camera row must be
pixel-equal to it (hash compare), every placeholder row must be black (max pixel value reported).
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import av
import av.logging
import cv2
import numpy as np
from skellycam.core.recorders.videos.sequential_video_reader import SequentialVideoReader

d = Path(sys.argv[1])
meta = json.loads((d / "files.json").read_text())
av.logging.set_level(av.logging.VERBOSE)  # PyAV drops libav log lines unless a level is set
SEEK_N = [0, 5, 9, 10, 11, 20, 30, 50, 98, 99, 100, 101, 102, 110, 120, 150, 188, 189, 190, 191, 199, 200, 201, 205,
          206, 210, 250, 289, 290, 299]
N = 300


def h(a: np.ndarray) -> str:
    return hashlib.md5(a.tobytes() + str(a.shape).encode()).hexdigest()


def ident(bgr: np.ndarray, thumbs: np.ndarray) -> int:
    g = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
    return int(np.argmin(np.abs(thumbs - g).mean(axis=(1, 2))))


class Checker:
    """Compare frame i of a file with frame i of the full file (same tool)."""

    def __init__(self, ref_hashes, ph_rows, thumbs, keep):
        self.ref, self.ph, self.thumbs, self.keep = ref_hashes, set(ph_rows), thumbs, keep
        self.bad, self.ph_max, self.shapes = [], 0, set()

    def check(self, i, a):
        self.shapes.add(a.shape)
        if i in self.ph:
            self.ph_max = max(self.ph_max, int(a.max()))
            return a.max() <= 2
        if h(a) == self.ref[i]:
            return True
        r = self.keep.get(i)
        diff = int(np.abs(r.astype(int) - a.astype(int)).max()) if r is not None and r.shape == a.shape else None
        self.bad.append({"i": i, "drawn": ident(a, self.thumbs), "maxdiff_vs_full": diff, "shape": a.shape})
        return False

    def summary(self):
        return {"camera_rows_not_equal_full": self.bad[:10], "n_bad": len(self.bad), "placeholder_max_pixel": self.ph_max,
                "shapes": sorted(str(s) for s in self.shapes)}


def ffprobe(p):
    r = subprocess.run(["ffprobe", "-v", "warning", "-count_packets", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,pix_fmt,width,height,nb_read_packets,duration,avg_frame_rate:format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    return {"packets": int(s["nb_read_packets"]), "pix_fmt": s.get("pix_fmt"), "wh": f"{s['width']}x{s['height']}",
            "format_duration": j["format"]["duration"], "avg_frame_rate": s["avg_frame_rate"], "stderr": r.stderr.strip()}


def ffmpeg_null(p):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-v", "warning", "-i", str(p), "-f", "null", "-"],
                       capture_output=True, text=True)
    return {"rc": r.returncode, "stderr": r.stderr.strip()[:2000]}


def pyav_decode(p, chk):
    res = {"frames": 0, "corrupt": 0, "formats": [], "error": None}
    t = time.perf_counter()
    with av.logging.Capture() as logs:
        try:
            with av.open(str(p)) as c:
                for i, f in enumerate(c.decode(video=0)):
                    key = (f.format.name, f.width, f.height)
                    if not res["formats"] or res["formats"][-1][1:] != list(key):
                        res["formats"].append([i, *key])
                    res["corrupt"] += f.is_corrupt
                    chk.check(i, f.to_ndarray(format="bgr24"))
                    res["frames"] += 1
        except Exception as e:  # noqa: BLE001
            res["error"] = f"{type(e).__name__}: {e}"
    res["seconds"] = round(time.perf_counter() - t, 3)
    res["log"] = sorted({f"{lv}:{name}:{msg.strip()}" for lv, name, msg in logs if lv <= av.logging.WARNING})[:20]
    return res | chk.summary()


def opencv(p, chk, seek_ref):
    cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
    res = {"backend": cap.getBackendName(), "frame_count": cap.get(cv2.CAP_PROP_FRAME_COUNT)}
    t, n = time.perf_counter(), 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        chk.check(n, f)
        n += 1
    res["seconds"] = round(time.perf_counter() - t, 3)
    res["reads"] = n
    res |= chk.summary()
    seeks = []
    for s in SEEK_N:
        cap.set(cv2.CAP_PROP_POS_FRAMES, s)
        ok, f = cap.read()
        if not ok:
            seeks.append([s, "readF"])
        elif s in chk.ph:
            seeks.append([s, "black" if f.max() <= 2 else f"notblack(drawn {ident(f, chk.thumbs)})"])
        elif h(f) == seek_ref[s]:
            seeks.append([s, "ok"])
        else:
            seeks.append([s, f"drawn {ident(f, chk.thumbs)}"])
    res["seeks_bad"] = [x for x in seeks if x[1] not in ("ok", "black")]
    res["seeks_black"] = [x[0] for x in seeks if x[1] == "black"]
    cap.release()
    return res


def skelly(p, chk):
    r = SequentialVideoReader(path=p)
    res = {"frames": 0, "error": None, "end": None}
    try:
        for i in range(N + 1):
            try:
                a = r.read_bgr(frame_number=i)
            except IndexError as e:
                res["end"] = f"IndexError at {i}"
                break
            chk.check(i, a)
            res["frames"] += 1
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        r.close()
    return res | chk.summary()


KEEP = [10, 101, 190, 191, 0, 199, 200]  # rows right after a placeholder run, kept in full for a max-diff
out = {"opencv": cv2.__version__, "pyav": av.__version__}
refs = {}
for f in meta["files"]:
    p, cfg = d / f["file"], f["cfg"]
    thumbs = np.load(d / f"{cfg}_thumbs.npy")
    if f["pattern"] == "full":  # build the per-tool reference for this config
        ref = {"pyav": [], "cv": [], "keep_pyav": {}, "keep_cv": {}}
        with av.open(str(p)) as c:
            for i, fr in enumerate(c.decode(video=0)):
                a = fr.to_ndarray(format="bgr24")
                ref["pyav"].append(h(a))
                if i in KEEP:
                    ref["keep_pyav"][i] = a
        cap = cv2.VideoCapture(str(p), cv2.CAP_FFMPEG)
        while (r := cap.read())[0]:
            ref["cv"].append(h(r[1]))
            if len(ref["cv"]) - 1 in KEEP:
                ref["keep_cv"][len(ref["cv"]) - 1] = r[1]
                assert ident(r[1], thumbs) == len(ref["cv"]) - 1
        assert len(ref["pyav"]) == len(ref["cv"]) == N
        # the full file's own seeks must match its sequential reads
        ref["seek"] = {}
        for s in SEEK_N:
            cap.set(cv2.CAP_PROP_POS_FRAMES, s)
            ref["seek"][s] = h(cap.read()[1])
        ref["full_seeks_equal_sequential"] = all(ref["seek"][s] == ref["cv"][s] for s in SEEK_N)
        cap.release()
        refs[cfg] = ref
    ref = refs[cfg]
    r = {"ffprobe": ffprobe(p), "ffmpeg_null": ffmpeg_null(p),
         "pyav": pyav_decode(p, Checker(ref["pyav"], f["ph_rows"], thumbs, ref["keep_pyav"])),
         "opencv": opencv(p, Checker(ref["cv"], f["ph_rows"], thumbs, ref["keep_cv"]), ref["cv"]),
         "skelly": skelly(p, Checker(ref["pyav"], f["ph_rows"], thumbs, ref["keep_pyav"]))}
    if f["pattern"] == "full":
        r["full_seeks_equal_sequential"] = ref["full_seeks_equal_sequential"]
    out[f["file"]] = r
    print(f["file"], "ffprobe", r["ffprobe"]["packets"], r["ffprobe"]["pix_fmt"], "| pyav", r["pyav"]["frames"],
          r["pyav"]["n_bad"], r["pyav"]["formats"], r["pyav"]["error"], "| cv", r["opencv"]["frame_count"], r["opencv"]["reads"],
          r["opencv"]["n_bad"], r["opencv"]["placeholder_max_pixel"], r["opencv"]["seeks_bad"], "| sk", r["skelly"]["frames"],
          r["skelly"]["error"], flush=True)
(d / "probe_results.json").write_text(json.dumps(out, indent=1, default=str))
