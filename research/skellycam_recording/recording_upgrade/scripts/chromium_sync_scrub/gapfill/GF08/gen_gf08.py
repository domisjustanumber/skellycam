# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF08 generator (FUNCTIONAL, no timing): 4 camera streams on one shared clock from real capture timestamps.

cam0 = c930e_720p_flash, all frames
cam1 = c922_720p_flash, all frames
cam2 = c930e_720p_flash, late start (first 40 frames dropped), a 60-frame gap (orig 400..459), every 50th orig frame dropped
cam3 = c922_720p_flash, early end (orig 0..699 kept), a 3-frame gap (orig 300..302)
Shared clock (ns): ts = (os_timestamp_ns[orig] - os_timestamp_ns[0 of that set]) + OFFSET_NS[cam].
Timestamps come from jp_common.real_timestamps_ns (MF sample time, QPC, 100 ns units * 100).

Per camera, three files (media dir only) + a sidecar (frame index k -> ts_ns):
  jpeg   : the camera's own JPEG bytes muxed into MKV (add_mux_stream mjpeg) + byte-range index (payload offsets)
  jpegbc : the same frames decoded, identity barcode burned (value cam*4096+k, 16-bit pattern of gen_intra_clips.py),
           re-encoded with FFmpeg mjpeg 4:2:2 at target A (matched_settings.json ff_mjpeg_422 / mjpeg_720p) in MKV + index
  h264   : same barcoded frames, h264_nvenc all-intra at target A (matched_settings.json h264_nvenc_420 / mjpeg_720p),
           MP4 (+faststart, 1/90000) + index; falls back to libx264 all-intra (libx264_veryfast_420) only if NVENC fails
Also writes the fixed tick list (ticks.json). The expected answers are computed separately (analyze_gf08.py).

Run (repo root): uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gapfill/GF08/gen_gf08.py
"""
from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from av.video.frame import PictureType

REPO = Path("C:/Users/Dom/GitHub/freemocap/skellycam")
RU = REPO / "research/skellycam_recording/recording_upgrade"
sys.path.insert(0, str(RU / "scripts/jpeg_passthrough"))
import jp_common  # noqa: E402  (no third-party deps)

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/gapfill/GF08")
RESULTS = RU / "results/chromium_sync_scrub/gapfill"
SETTINGS = json.loads((RU / "results/intra_compare/matched_settings.json").read_text())
BITS, CELLS = 16, 32
P_NS = 33_333_333  # nominal frame period of both sets (corpus index nominal_fps = 30); used only by the tick list and conventions

OFFSET_NS = {0: 0, 1: 7_654_321, 2: -3_000_000, 3: 19_876_543}
SETS = {0: "c930e_720p_flash", 1: "c922_720p_flash", 2: "c930e_720p_flash", 3: "c922_720p_flash"}


def keep_orig(cam: int, n: int) -> list[int]:
    if cam in (0, 1):
        return list(range(n))
    if cam == 2:
        return [o for o in range(n) if o >= 40 and not (400 <= o <= 459) and o % 50 != 0]
    return [o for o in range(0, 700) if not (300 <= o <= 302)]


def decode_rgb(b: bytes) -> np.ndarray:
    cc = av.CodecContext.create("mjpeg", "r")
    fr = list(cc.decode(av.Packet(b))) + list(cc.decode(None))
    return fr[0].to_ndarray(format="rgb24")


def burn(img: np.ndarray, v: int) -> np.ndarray:  # same layout as scripts/intra_playback/gen_intra_clips.py burn_index
    h, w = img.shape[:2]
    cw = w // CELLS
    out = img.copy()
    for b in range(BITS):
        bit = (v >> (BITS - 1 - b)) & 1
        for j, x in enumerate((bit, 1 - bit)):
            x0 = (2 * b + j) * cw
            out[0:cw, x0:x0 + cw] = 255 if x else 0
    return out


def read_y(y: np.ndarray) -> int | None:  # same rule as the browser (gen_intra_clips.py read_index_y)
    w = y.shape[1]
    cw = w // CELLS
    row = y[cw // 2, :].astype(np.int32)
    v = 0
    for b in range(BITS):
        a, c = row[(2 * b) * cw + cw // 2], row[(2 * b + 1) * cw + cw // 2]
        if abs(a - c) <= 64:
            return None
        v = (v << 1) | (1 if a > c else 0)
    return v


def luma(fr: av.VideoFrame) -> np.ndarray:
    p = fr.planes[0]
    return np.frombuffer(p, np.uint8).reshape(p.height, p.line_size)[:, :fr.width].copy()


def demux_index(path: Path) -> dict:
    data = path.read_bytes()
    rows = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        tb = s.time_base
        ed = bytes(s.codec_context.extradata) if s.codec_context.extradata else b""
        for p in c.demux(s):
            if p.size == 0:
                continue
            pb = bytes(p)
            pos = p.pos
            off = pos if (pos is not None and pos >= 0 and data[pos:pos + p.size] == pb) else None
            if off is None:
                lo = max(0, (pos or 0) - 256)
                f = data.find(pb, lo, lo + p.size + 4096)
                off = f if f >= 0 else None
            rows.append({"pts": p.pts, "dts": p.dts, "key": bool(p.is_keyframe), "offset": off, "size": p.size,
                         "pos_delta": (off - pos) if (off is not None and pos is not None) else None})
    order_ok = all((a["dts"] if a["dts"] is not None else a["pts"]) <= (b["dts"] if b["dts"] is not None else b["pts"])
                   for a, b in zip(rows, rows[1:]))
    rows.sort(key=lambda r: r["pts"])
    return {"tb_num": tb.numerator, "tb_den": tb.denominator, "extradata": ed, "rows": rows,
            "decode_order_equals_pts_order": order_ok, "all_offsets_found": all(r["offset"] is not None for r in rows),
            "all_key": all(r["key"] for r in rows),
            "pos_delta_hist": {str(k): sum(1 for r in rows if r["pos_delta"] == k) for k in sorted({r["pos_delta"] for r in rows}, key=str)}}


def avc_codec_string(ed: bytes) -> str:
    if len(ed) >= 4 and ed[0] == 1:
        return f"avc1.{ed[1]:02X}{ed[2]:02X}{ed[3]:02X}"
    raise ValueError("no avcC")


def to_tb(ts_ns: int, tb: Fraction, prev: int) -> tuple[int, bool]:
    t = int(round(Fraction(ts_ns, 10**9) / tb))
    if t <= prev:
        return prev + 1, True
    return t, False


def write_mkv(path: Path, pkts: list[bytes], ts: list[int], w: int, h: int) -> int:
    tb = Fraction(1, 1000)
    adj = 0
    prev = -10**18
    with av.open(str(path), "w", format="matroska") as out:
        st = out.add_mux_stream("mjpeg", rate=30, width=w, height=h)
        for b, t_ns in zip(pkts, ts):
            t, bumped = to_tb(t_ns, tb, prev)
            adj += bumped
            prev = t
            p = av.Packet(b)
            p.stream, p.time_base = st, tb
            p.pts = p.dts = t
            p.is_keyframe = True
            out.mux(p)
    return adj


def encode_h264(path: Path, enc: str, opts: dict, gop: int, rgbs, ts: list[int], w: int, h: int) -> int:
    tb = Fraction(1, 90000)
    adj = 0
    prev = -10**18
    with av.open(str(path), "w", format="mp4", options={"movflags": "+faststart"}) as out:
        st = out.add_stream(enc, rate=30)
        st.width, st.height, st.pix_fmt = w, h, "nv12" if enc.endswith("nvenc") else "yuv420p"
        st.time_base = tb
        cc = st.codec_context
        cc.time_base = tb
        cc.max_b_frames, cc.gop_size = 0, gop
        cc.options = dict(opts)
        for rgb, t_ns in zip(rgbs, ts):
            t, bumped = to_tb(t_ns, tb, prev)
            adj += bumped
            prev = t
            f = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format=st.pix_fmt, dst_color_range=1)
            f.pict_type = PictureType.NONE
            f.pts = t
            f.time_base = tb
            for p in st.encode(f):
                out.mux(p)
        for p in st.encode(None):
            out.mux(p)
    return adj


def encode_jpegbc(rgbs, w: int, h: int) -> list[bytes]:
    s = SETTINGS["ff_mjpeg_422"]["mjpeg_720p"]
    cc = av.CodecContext.create("mjpeg", "w")
    cc.width, cc.height, cc.pix_fmt = w, h, s["pix_fmt_fed"]
    cc.time_base, cc.framerate = Fraction(1, 30), Fraction(30, 1)
    cc.gop_size = 1
    cc.options = dict(s["options"])
    cc.open()
    out = []
    for i, rgb in enumerate(rgbs):
        f = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format=s["pix_fmt_fed"], dst_color_range=2)
        f.pts = i
        out += [bytes(p) for p in cc.encode(f)]
    out += [bytes(p) for p in cc.encode(None)]
    return out


def decode_back(path: Path, expect: list[int]) -> dict:
    got = []
    with av.open(str(path)) as c:
        for fr in c.decode(video=0):
            got.append(read_y(luma(fr)))
    return {"decoded": len(got), "expected": len(expect), "barcode_ok": sum(1 for a, b in zip(got, expect) if a == b),
            "unreadable": sum(1 for a in got if a is None)}


def ffprobe_keys(path: Path) -> dict:
    try:
        fr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=key_frame,pict_type",
                             "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=300).stdout.split()
        ver = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        return {"ffprobe": ver, "frames": len(fr), "key_frames": sum(1 for l in fr if l.startswith("1")),
                "pict_I": sum(1 for l in fr if l.endswith("I"))}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def make_ticks(side: dict) -> list[dict]:
    """Fixed master-clock ticks (ns) with a reason tag. Deterministic (seed 8)."""
    rnd = random.Random(8)
    T: dict[int, set] = {}

    def add(t, why):
        T.setdefault(int(t), set()).add(why)

    for cam, s in side.items():
        ts = s["ts_ns"]
        n = len(ts)
        # exact timestamps, midpoints, +-1 ms on a deterministic sample (+ first/last/neighbours of gaps)
        ks = set(rnd.sample(range(1, n - 2), 8)) | {0, 1, n - 2, n - 1}
        # full gap treatment for every multi-frame gap and the first 3 single-frame gaps; midpoint only for the rest
        full = [g for g in s["gaps"] if g["missing"] > 1] + [g for g in s["gaps"] if g["missing"] == 1][:3]
        for g in full:
            ks |= {g["k_before"], g["k_after"]}
        if s["source_set"] == "c930e_720p_flash":  # the 0.011 ms pair (orig 81/82)
            ks |= {s["orig_index"].index(o) for o in (81, 82) if o in s["orig_index"]}
        for k in sorted(ks):
            add(ts[k], f"exact:c{cam}")
            add(ts[k] - 1_000_000, f"minus1ms:c{cam}")
            add(ts[k] + 1_000_000, f"plus1ms:c{cam}")
            if k + 1 < n:
                add((ts[k] + ts[k + 1]) // 2, f"mid:c{cam}")
                add((ts[k] + ts[k + 1]) // 2 + 1, f"mid+1ns:c{cam}")
        # inside each gap: quarter points + 1 ns after the frame before the gap + 1 ns before the frame after it
        for g in s["gaps"]:
            a, b = ts[g["k_before"]], ts[g["k_after"]]
            if g not in full:
                add((a + b) // 2, f"gap:c{cam}")
                continue
            for q in (1, 2, 3):
                add(a + (b - a) * q // 4, f"gap:c{cam}")
            add(a + 1, f"gap_edge:c{cam}")
            add(b - 1, f"gap_edge:c{cam}")
            add(a + P_NS, f"gap_P:c{cam}")
            add(a + P_NS + 1, f"gap_P+1:c{cam}")
        # before the first frame and after the last frame, around the convention boundaries
        f0, fl = ts[0], ts[-1]
        for d in (1, 1_000_000, P_NS // 2, P_NS // 2 + 1, P_NS, 100_000_000, 1_000_000_000):
            add(f0 - d, f"before_start:c{cam}")
        for d in (1, 1_000_000, P_NS // 2, P_NS // 2 + 1, P_NS, P_NS + 1, 100_000_000, 1_000_000_000):
            add(fl + d, f"after_end:c{cam}")
    lo = min(s["ts_ns"][0] for s in side.values())
    hi = max(s["ts_ns"][-1] for s in side.values())
    for _ in range(60):  # uniform random ticks over the whole span
        add(rnd.randint(lo, hi), "random")
    ticks = [{"t_ns": t, "why": sorted(w)} for t, w in sorted(T.items())]
    order = list(range(len(ticks)))
    random.Random(80).shuffle(order)  # visit in a shuffled order: the mapping must be stateless (scrub-like access)
    return [dict(ticks[i], order=j) for j, i in enumerate(order)]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    meta = {"generator": {"pyav": av.__version__, "libavcodec": str(av.library_versions.get("libavcodec")),
                          "libavformat": str(av.library_versions.get("libavformat")), "python": sys.version.split()[0]},
            "offset_ns": OFFSET_NS, "P_ns": P_NS, "cameras": {}}
    raw = {}
    for name in ("c930e_720p_flash", "c922_720p_flash"):
        frames = jp_common.load_set(name)
        ts = jp_common.real_timestamps_ns(name, frames)  # checks payload_bytes == corpus size for every frame
        raw[name] = (frames, ts)
        meta.setdefault("sets", {})[name] = {"frames": len(frames), "t0_raw_ns": ts[0], "last_raw_ns": ts[-1],
                                              "ts_source": str(jp_common.TS_SOURCE[name].relative_to(REPO)).replace("\\", "/"),
                                              "strictly_increasing": all(b > a for a, b in zip(ts, ts[1:]))}
    meta["raw_start_difference_ns_c930e_minus_c922"] = raw["c930e_720p_flash"][1][0] - raw["c922_720p_flash"][1][0]
    side = {}
    for cam, name in SETS.items():
        frames, ts_raw = raw[name]
        orig = keep_orig(cam, len(frames))
        ts = [ts_raw[o] - ts_raw[0] + OFFSET_NS[cam] for o in orig]
        gaps = [{"k_before": k, "k_after": k + 1, "orig_before": orig[k], "orig_after": orig[k + 1],
                 "missing": orig[k + 1] - orig[k] - 1} for k in range(len(orig) - 1) if orig[k + 1] - orig[k] > 1]
        side[cam] = {"camera": f"cam{cam}", "source_set": name, "clock": "shared study clock, ns",
                     "offset_ns": OFFSET_NS[cam], "t0_raw_ns_of_set": ts_raw[0],
                     "rule": "ts_ns = os_timestamp_ns[orig] - os_timestamp_ns[0] + offset_ns",
                     "frames": len(orig), "orig_index": orig, "ts_ns": ts, "gaps": gaps,
                     "sha256": [hashlib.sha256(frames[o]).hexdigest() for o in orig]}
        (MEDIA / f"cam{cam}.ts.json").write_text(json.dumps(side[cam]))
    (RESULTS / "GF08_sidecars.json").write_text(json.dumps({f"cam{c}": {k: v for k, v in s.items() if k != "sha256"} for c, s in side.items()}))

    # H.264 encoder choice
    s_nv = SETTINGS["h264_nvenc_420"]["mjpeg_720p"]
    s_x = SETTINGS["libx264_veryfast_420"]["mjpeg_720p"]
    manifest = {"P_ns": P_NS, "cams": {}}
    for cam, name in SETS.items():
        frames, _ = raw[name]
        s = side[cam]
        jb = [frames[o] for o in s["orig_index"]]
        w, h = 1280, 720
        cam_m = {"frames": s["frames"], "width": w, "height": h, "ts_ns": s["ts_ns"], "sha256": s["sha256"]}
        # (a) camera bytes in MKV
        p_jpeg = MEDIA / f"cam{cam}_jpeg.mkv"
        adj = write_mkv(p_jpeg, jb, s["ts_ns"], w, h)
        ix = demux_index(p_jpeg)
        data = p_jpeg.read_bytes()
        same = sum(1 for r, b in zip(ix["rows"], jb) if r["offset"] is not None and data[r["offset"]:r["offset"] + r["size"]] == b)
        cam_m["jpeg"] = {"url": f"/media/cam{cam}_jpeg.mkv", "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]],
                         "container_pts_ns": [r["pts"] * 10**9 * ix["tb_num"] // ix["tb_den"] for r in ix["rows"]]}
        chk = {"jpeg": {"bytes": p_jpeg.stat().st_size, "packets": len(ix["rows"]), "byte_identical_to_corpus": same,
                        "time_base": f"{ix['tb_num']}/{ix['tb_den']}", "pts_bumped_for_monotonic": adj,
                        "pos_delta_hist": ix["pos_delta_hist"], "all_offsets_found": ix["all_offsets_found"]}}
        # barcoded frames
        rgbs = [burn(decode_rgb(b), cam * 4096 + k) for k, b in enumerate(jb)]
        expect = [cam * 4096 + k for k in range(len(jb))]
        # (a2) barcoded JPEG in MKV
        pk = encode_jpegbc(rgbs, w, h)
        p_bc = MEDIA / f"cam{cam}_jpegbc.mkv"
        adj = write_mkv(p_bc, pk, s["ts_ns"], w, h)
        ix = demux_index(p_bc)
        cam_m["jpegbc"] = {"url": f"/media/cam{cam}_jpegbc.mkv", "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]]}
        chk["jpegbc"] = {"bytes": p_bc.stat().st_size, "packets": len(ix["rows"]), "pts_bumped_for_monotonic": adj,
                         "encoder": "mjpeg", "options": SETTINGS["ff_mjpeg_422"]["mjpeg_720p"]["options"],
                         "pix_fmt_fed": SETTINGS["ff_mjpeg_422"]["mjpeg_720p"]["pix_fmt_fed"],
                         "decode_back": decode_back(p_bc, expect), "all_offsets_found": ix["all_offsets_found"]}
        # (b) H.264 all-intra
        p_h = MEDIA / f"cam{cam}_h264.mp4"
        enc_used, err = "h264_nvenc", None
        try:
            adj = encode_h264(p_h, "h264_nvenc", s_nv["options"], s_nv["gop_size"], rgbs, s["ts_ns"], w, h)
            opts = s_nv["options"]
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            enc_used = "libx264"
            adj = encode_h264(p_h, "libx264", s_x["options"], s_x["gop_size"], rgbs, s["ts_ns"], w, h)
            opts = s_x["options"]
        ix = demux_index(p_h)
        cam_m["h264"] = {"url": f"/media/cam{cam}_h264.mp4", "offsets": [r["offset"] for r in ix["rows"]], "sizes": [r["size"] for r in ix["rows"]],
                         "codec_string": avc_codec_string(ix["extradata"]), "description_hex": ix["extradata"].hex(),
                         "container_pts_ns": [r["pts"] * 10**9 * ix["tb_num"] // ix["tb_den"] for r in ix["rows"]]}
        chk["h264"] = {"bytes": p_h.stat().st_size, "packets": len(ix["rows"]), "encoder": enc_used, "nvenc_error": err,
                       "options": opts, "gop_size": s_nv["gop_size"] if enc_used == "h264_nvenc" else s_x["gop_size"], "max_b_frames": 0,
                       "settings_source": "results/intra_compare/matched_settings.json " + ("h264_nvenc_420" if enc_used == "h264_nvenc" else "libx264_veryfast_420") + " / mjpeg_720p (target A)",
                       "time_base": f"{ix['tb_num']}/{ix['tb_den']}", "pts_bumped_for_monotonic": adj,
                       "all_key": ix["all_key"], "decode_order_equals_pts_order": ix["decode_order_equals_pts_order"],
                       "all_offsets_found": ix["all_offsets_found"], "codec_string": cam_m["h264"]["codec_string"],
                       "decode_back": decode_back(p_h, expect), "ffprobe": ffprobe_keys(p_h)}
        manifest["cams"][f"cam{cam}"] = cam_m
        meta["cameras"][f"cam{cam}"] = {"source_set": name, "offset_ns": OFFSET_NS[cam], "frames": s["frames"],
                                        "first_ts_ns": s["ts_ns"][0], "last_ts_ns": s["ts_ns"][-1], "orig_first": s["orig_index"][0],
                                        "orig_last": s["orig_index"][-1], "gaps": s["gaps"], "files": chk}
        print(f"cam{cam}", json.dumps({k: {kk: v for kk, v in d.items() if kk in ('packets', 'byte_identical_to_corpus', 'decode_back', 'encoder', 'all_key')} for k, d in chk.items()}), flush=True)
    ticks = make_ticks(side)
    manifest["ticks"] = ticks
    (MEDIA / "manifest.json").write_text(json.dumps(manifest))
    meta["ticks"] = {"count": len(ticks), "why_hist": {}}
    for t in ticks:
        for w_ in t["why"]:
            key = w_.split(":")[0]
            meta["ticks"]["why_hist"][key] = meta["ticks"]["why_hist"].get(key, 0) + 1
    (RESULTS / "GF08_generation.json").write_text(json.dumps(meta, indent=1))
    (RESULTS / "GF08_ticks.json").write_text(json.dumps(ticks))
    print("ticks", len(ticks), meta["ticks"]["why_hist"])


if __name__ == "__main__":
    main()
