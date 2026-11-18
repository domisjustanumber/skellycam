# /// script
# requires-python = "==3.12.13"
# dependencies = ["comtypes==1.5.0", "numpy==2.5.5", "opencv-contrib-python==5.1.0.95"]
# ///
"""One camera: native types + attributes, then YUY2/NV12 and MJPG captures held in memory only. Numbers out only.

    uv run --script probe.py --match vid_046d&pid_0843 --label C930e --out results_C930e.json
Reuses research/usb_cameras/suite/windows/pymf (Media Foundation, async reader, converters disabled).
Reads exposure/gain (read only). Sets no control. Never writes a frame.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from ctypes import byref, c_void_p
from pathlib import Path

import cv2
import numpy as np

SUITE = Path(__file__).resolve().parents[2] / "usb_cameras" / "suite" / "windows"
sys.path.insert(0, str(SUITE))
from pymf import bounded, mf, parse as P, com as C  # noqa: E402

ATTRS = ("MF_MT_VIDEO_NOMINAL_RANGE", "MF_MT_YUV_MATRIX", "MF_MT_VIDEO_PRIMARIES", "MF_MT_TRANSFER_FUNCTION",
         "MF_MT_VIDEO_CHROMA_SITING")
DISCARD, KEEP, TO = 30, 60, 5000
PCT = (0.1, 1, 50, 99, 99.9)
PCT7 = (1, 5, 25, 50, 75, 95, 99)


def native(src):
    """All native types of the first video stream, short form + the colour attributes."""
    hr, rd = mf.make_reader(src)
    out = []
    try:
        i = 0
        while True:
            raw = c_void_p()
            if rd.GetNativeMediaType(C.MF_SOURCE_READER_FIRST_VIDEO_STREAM, i, byref(raw)) & 0x80000000:
                break
            t = C.own(raw, C.IMFMediaType)
            f = mf.type_fields(t)
            a = mf.attrs_json(t)
            out.append({"subtype": f["subtype"], "w": f["width"], "h": f["height"],
                        "fps": round(P.fps_of(f["fps_num"], f["fps_den"]), 2),
                        **{k.replace("MF_MT_", ""): a.get(k, "not set") for k in ATTRS}})
            C.release(t)
            i += 1
    finally:
        C.release(rd)
    return out


def jpeg_header(b: bytes) -> dict:
    h = {"jfif": False, "adobe": None, "comps": None, "sof": None}
    i = 2
    while i + 4 < len(b) and b[i] == 0xFF:
        m, ln = b[i + 1], (b[i + 2] << 8) | b[i + 3]
        seg = b[i + 4:i + 2 + ln]
        if m == 0xE0 and seg[:4] == b"JFIF":
            h["jfif"] = True
        if m == 0xEE and seg[:5] == b"Adobe":
            h["adobe"] = {"transform": seg[11]}
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h["sof"] = hex(m)
            n = seg[5]
            h["comps"] = [{"id": seg[6 + 3 * k], "h": seg[7 + 3 * k] >> 4, "v": seg[7 + 3 * k] & 15} for k in range(n)]
            break
        i += 2 + ln
    if h["comps"]:
        c = h["comps"][0]
        h["subsampling"] = {(1, 1): "4:4:4", (2, 1): "4:2:2", (2, 2): "4:2:0", (1, 2): "4:4:0"}.get((c["h"], c["v"]), "other")
    return h


def capture(label: str, mode: dict, st_out: dict):
    """Stream one mode, return (frames as bytes list, info). Frames stay in memory."""
    st = mf.StreamState(mode["w"], mode["h"], 0)
    frames: list[bytes] = []

    def fn(st, arr, flags, ts, s):
        st.frames += 1
        braw = c_void_p()
        if not s.ConvertToContiguousBuffer(byref(braw)) & 0x80000000:
            b = C.own(braw, C.IMFMediaBuffer)
            _h, d = C.lock_bytes(b)
            C.release(b)
            if st.frames > DISCARD and len(frames) < KEEP:
                frames.append(d)
        st.last_ns = arr
        if not st.first_ns:
            st.first_ns = arr

    st.sample_fn = fn
    s = mf.Session()
    info = {"mode": mode}
    ok = mf.open_session(s, st_out["symlink"], mode, st, TO) and mf.wait_first(s, TO)
    if ok:
        info["negotiated"] = {k: s.negotiated.get(k) for k in ("subtype", "width", "height", "fps")}
        info["controls"] = {}
        for d in ((0, 4, "exposure"), (1, 9, "gain")):
            r = bounded.call(TO, lambda ctl, d=d: mf.read_ctl(s.ctl, d, False))
            v = r.value
            info["controls"][d[2]] = ({"val": v.get("val"), "flags": v.get("flags")} if v and v.get("has_value")
                                      else "not readable")
        t0 = time.time()
        while len(frames) < KEEP and time.time() - t0 < 20:
            with st.mu:
                err, eos = st.err, st.eos
            if err is not None or eos:
                s.fail("streaming", err or P.MF_E_END_OF_STREAM, False)
                break
            st.ev_sample.wait(0.05)
            st.ev_sample.clear()
        if len(frames) < KEEP and not s.stage_failed:
            s.fail("streaming", P.E_FAIL, True)
    mf.close_session(s, TO)
    info["error"] = s.error()
    info["frames_kept"] = len(frames)
    info["unreleasable"] = s.unreleasable
    return frames, info


def yuy2_stats(frames, w, h, sub):
    ys, us, vs = [], [], []
    for d in frames:
        a = np.frombuffer(d, np.uint8)
        if sub == "YUY2":
            a = a[: w * h * 2].reshape(h, w // 2, 4)
            ys.append(a[:, :, [0, 2]].reshape(-1)); us.append(a[:, :, 1].reshape(-1)); vs.append(a[:, :, 3].reshape(-1))
        else:  # NV12
            ys.append(a[: w * h]); uv = a[w * h: w * h * 3 // 2].reshape(-1, 2)
            us.append(uv[:, 0]); vs.append(uv[:, 1])
    pf = [dict(min=int(y.min()), max=int(y.max()), **{f"p{p}": float(np.percentile(y, p)) for p in PCT}) for y in ys]
    Y, U, V = np.concatenate(ys), np.concatenate(us), np.concatenate(vs)
    C_ = np.concatenate([U, V])
    return {"Y_min": int(Y.min()), "Y_max": int(Y.max()), **{f"Y_p{p}": float(np.percentile(Y, p)) for p in PCT},
            "U_min": int(U.min()), "U_max": int(U.max()), "V_min": int(V.min()), "V_max": int(V.max()),
            "frac_Y_below16": float((Y < 16).mean()), "frac_Y_above235": float((Y > 235).mean()),
            "frac_chroma_outside_16_240": float(((C_ < 16) | (C_ > 240)).mean()),
            "Y_hist256_counts": np.bincount(Y, minlength=256).tolist(),
            "per_frame_Y_range_min_of_mins": min(p["min"] for p in pf), "per_frame_Y_range_max_of_maxs": max(p["max"] for p in pf),
            "per_frame_first3": pf[:3]}, ys


def jpeg_y_profile(frames):
    prof, hdr = [], None
    for d in frames:
        if hdr is None:
            hdr = jpeg_header(d)
        im = cv2.imdecode(np.frombuffer(d, np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            continue
        b, g, r = (im[:, :, k].astype(np.float32) for k in range(3))
        prof.append(np.percentile(0.299 * r + 0.587 * g + 0.114 * b, PCT7))
    return (np.mean(prof, 0) if prof else None), hdr, len(prof)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res: dict = {"label": a.label, "modes": []}
    out = Path(a.out)

    def dump():
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")

    def watchdog():
        time.sleep(240)
        res["watchdog_fired"] = True
        dump()
        os._exit(5)
    threading.Thread(target=watchdog, daemon=True).start()
    C.MFStartup(C.MF_VERSION, C.MFSTARTUP_FULL)
    j: dict = {}
    rc, dev = mf.resolve_mf(a.match, TO, j)
    res["resolve"] = j.get("device") or j.get("error")
    if rc:
        dump(); os._exit(rc)
    res["name"] = dev["name"]
    dd = {"symlink": dev["symlink"]}
    steps: list = []
    r = mf.activate(dev["act"], TO)
    hr, src = r.value if r.value else (P.E_FAIL, None)
    if r.timed_out or P.failed(hr) or src is None:
        res["open_error"] = {"hr": None if r.timed_out else P.hr_hex(hr), "timed_out": r.timed_out, "name": P.hr_name(hr) if hr else None}
        res["dead"] = True; dump(); os._exit(4)
    nt = bounded.call(TO, lambda ctl: native(src))
    res["native_types"] = nt.value
    holder = {"src": src, "act": dev["act"]}
    mf.shutdown_mf(holder, TO)
    types = nt.value or []
    short = sorted({f"{t['subtype']} {t['w']}x{t['h']}@{t['fps']}" for t in types})
    res["native_short"] = short

    def has(sub, w, h):
        c = [t for t in types if t["subtype"] == sub and t["w"] == w and t["h"] == h]
        return max(c, key=lambda t: (abs(t["fps"] - 30) < 1, -abs(t["fps"] - 30))) if c else None
    plan = []
    for (w, h) in ((640, 480), (1280, 720)):
        unc = has("YUY2", w, h) or has("NV12", w, h)
        mj = has("MJPG", w, h)
        if unc:
            plan.append((unc, mj))
    for unc, mj in plan:
        w, h = unc["w"], unc["h"]
        entry: dict = {"res": f"{w}x{h}"}
        res["modes"].append(entry)
        for t in (unc, mj):
            if t is None:
                entry["MJPG"] = "not offered at this size"
                continue
            mode = {"subtype": t["subtype"], "w": w, "h": h, "fps": t["fps"]}
            fr, info = capture(a.label, mode, dd)
            entry[t["subtype"]] = info
            if info["error"] or len(fr) < KEEP:
                res["dead"] = True
                dump()
                if a.label.startswith("KiyoPro"):
                    os._exit(5)
                continue
            if t["subtype"] == "MJPG":
                prof, hdr, n = jpeg_y_profile(fr)
                info.update(jpeg_header=hdr, decoded=n, Y_profile_1_5_25_50_75_95_99=None if prof is None else prof.tolist(),
                            attrs={k: t[k] for k in ATTRS_SHORT})
            else:
                info["bytes_per_frame"] = len(fr[0])
                stats, ys = yuy2_stats(fr, w, h, t["subtype"])
                info["stats"] = stats
                info["Y_profile_1_5_25_50_75_95_99"] = np.mean([np.percentile(y, PCT7) for y in ys], 0).tolist()
                info["attrs"] = {k: t[k] for k in ATTRS_SHORT}
        u, m = entry.get(unc["subtype"]), entry.get("MJPG")
        if isinstance(u, dict) and isinstance(m, dict) and u.get("Y_profile_1_5_25_50_75_95_99") and m.get("Y_profile_1_5_25_50_75_95_99"):
            up, mp = np.array(u["Y_profile_1_5_25_50_75_95_99"]), np.array(m["Y_profile_1_5_25_50_75_95_99"])
            ea = float(np.abs(up - mp).mean())
            eb = float(np.abs(np.clip((up - 16) * 255 / 219, 0, 255) - mp).mean())
            entry["fit"] = {"MAE_a_full": ea, "MAE_b_limited": eb, "better": "a_full" if ea < eb else "b_limited"}
        dump()
    dump()
    os._exit(0)


ATTRS_SHORT = tuple(k.replace("MF_MT_", "") for k in ATTRS)

if __name__ == "__main__":
    main()
