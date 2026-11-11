"""Generate the test clips for the chromium_sync_scrub harness (goal G9).

Every frame = real camera content (corpus JPEG, decoded with OpenCV) with a per-frame binary index
pattern burned into the top strip: 16 bits, MSB first, each bit drawn as a pair of cells (bit, NOT bit),
32 cells across the full width, strip height = cell width. White = 255, black = 0 (BGR).
The browser reads the pattern back to learn which frame it is really showing.

Encodes with PyAV (explicit per-frame pts, so CFR and VFR are both exact), then demuxes every file
again and records, per frame in presentation order: container pts (s), keyframe flag, and the
"recorder index" (byte offset + size of the coded sample inside the container file, verified
byte-exact against the demuxed packet) used by the WebCodecs path.

Outputs (media - shows the room, never in the repo):
  C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips/
      <content>/<variant>.<ext>, <content>/mjpeg/clip.mjpeg, <content>/mjpeg/frames/frame_NNNNNN.jpg
      manifest.json (per-clip metadata + per-frame pts/key/offset/size)
Text summary: research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/clips_summary.json

Run (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py
  options: --only <content>[,<content>]  --frames N (override frame count, for smoke tests)
           --recompute-codec-strings (rewrite codec_string in manifest.json from the files, no re-encode)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips")
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub"
FLASH_JSONL = REPO / ("research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture/"
                      "vid_046d_pid_0843_mi_00_8_39dec205_0_0000.frames.jsonl")

BITS = 16
CELLS = 2 * BITS

# content name -> (corpus set, nominal fps, frame count, vfr?)
CONTENTS = {
    "c720p30": ("c930e_720p_flash", 30, 600, False),  # 600 distinct real frames
    "c1080p30": ("c922_1080p", 30, 600, False),       # 19 real frames looped (index pattern differs per frame)
    "c720p60": ("c922_720p60", 60, 600, False),       # 10 real frames looped
    "vfr720p": ("c930e_720p_flash", 30, 891, True),    # all 891 frames, pts = real MF sample times
    # today's Windows recordings: CFR header ~32.9 fps for a real 30.0 fps capture (research/skellycam_recording/REPORT.md R3);
    # pts = k / 32.9, nominal_fps = 30 (what the playback UI derives from the timestamp CSV)
    "hdr329": ("c930e_720p_flash", 30, 600, "hdr32.9"),
}

# variant name -> (codec, container ext, gop: "gop" (=fps) or 1, extra mux flags)
def variants_for(content: str) -> dict:
    base = {
        "av1_gop.mp4": ("libsvtav1", "mp4", "gop", {}),
        "av1_gop.webm": ("libsvtav1", "webm", "gop", {}),
        "av1_intra.mp4": ("libsvtav1", "mp4", 1, {}),
        "vp9_gop.webm": ("libvpx-vp9", "webm", "gop", {}),
        "vp9_gop.mp4": ("libvpx-vp9", "mp4", "gop", {}),
        "vp9_intra.webm": ("libvpx-vp9", "webm", 1, {}),
        "h264_gop.mp4": ("libx264", "mp4", "gop", {}),
        "h264_intra.mp4": ("libx264", "mp4", 1, {}),
        "av1_gop_frag.mp4": ("libsvtav1", "mp4", "gop", {"movflags": "frag_keyframe+empty_moov+default_base_moof"}),
    }
    if content == "hdr329":
        return {k: base[k] for k in ["h264_gop.mp4", "av1_gop.mp4"]}
    if content == "vfr720p":
        keep = ["av1_gop.mp4", "av1_gop.webm", "vp9_gop.webm", "h264_gop.mp4", "av1_intra.mp4"]
        return {k: base[k] for k in keep}
    if content == "c720p60":
        keep = ["av1_gop.mp4", "av1_intra.mp4", "vp9_gop.webm", "vp9_intra.webm", "h264_gop.mp4"]
        return {k: base[k] for k in keep}
    return base


def encoder_options(codec: str, g: int) -> dict:
    if codec == "libsvtav1":
        return {"preset": "10", "crf": "35", "g": str(g)}
    if codec == "libvpx-vp9":
        return {"deadline": "realtime", "cpu-used": "8", "crf": "33", "b": "0", "g": str(g), "row-mt": "1",
                "lag-in-frames": "0", "auto-alt-ref": "0"}
    if codec == "libx264":
        return {"preset": "veryfast", "crf": "23", "bf": "0", "g": str(g), "keyint_min": str(g),
                "sc_threshold": "0"}
    raise ValueError(codec)


def burn_index(img: np.ndarray, k: int) -> np.ndarray:
    h, w = img.shape[:2]
    cw = w // CELLS
    out = img.copy()
    for b in range(BITS):
        bit = (k >> (BITS - 1 - b)) & 1
        for j, v in enumerate((bit, 1 - bit)):
            x0 = (2 * b + j) * cw
            out[0:cw, x0:x0 + cw] = 255 if v else 0
    return out


def read_index(img: np.ndarray) -> int | None:
    """Same decoding rule as the browser: cell centres, pair must differ by >64."""
    h, w = img.shape[:2]
    cw = w // CELLS
    y = cw // 2
    gray = img[y, :, :].mean(axis=1) if img.ndim == 3 else img[y, :]
    v = 0
    for b in range(BITS):
        a = gray[(2 * b) * cw + cw // 2]
        c = gray[(2 * b + 1) * cw + cw // 2]
        if abs(a - c) <= 64:
            return None
        v = (v << 1) | (1 if a > c else 0)
    return v


def load_frames(corpus_set: str, n: int) -> list[np.ndarray]:
    files = sorted((CORPUS / corpus_set).glob("frame_*.jpg"))
    imgs = [cv2.imdecode(np.frombuffer(f.read_bytes(), np.uint8), cv2.IMREAD_COLOR) for f in files]
    return [imgs[k % len(imgs)] for k in range(n)], len(files)


def vfr_times_s(n: int) -> list[float]:
    rows = [json.loads(l) for l in FLASH_JSONL.open()]
    t = [r["mf_sample_time_100ns"] for r in rows[:n]]
    return [(x - t[0]) / 1e7 for x in t]


def encode(path: Path, codec: str, ext: str, g: int, flags: dict, frames, times_s, fps: int) -> dict:
    tb = Fraction(1, 90000) if ext == "mp4" else Fraction(1, 1000)
    opts = {}
    if ext == "mp4":
        opts["movflags"] = flags.get("movflags", "+faststart")
    fmt = "mp4" if ext == "mp4" else "webm"
    adjusted = 0
    with av.open(str(path), "w", format=fmt, options=opts) as out:
        st = out.add_stream(codec, rate=fps, options=encoder_options(codec, g))
        st.width, st.height = frames[0].shape[1], frames[0].shape[0]
        st.pix_fmt = "yuv420p"
        st.time_base = tb
        st.codec_context.time_base = tb
        prev = -1
        for k, img in enumerate(frames):
            pts = int(round(times_s[k] / tb))
            if pts <= prev:
                pts = prev + 1
                adjusted += 1
            prev = pts
            vf = av.VideoFrame.from_ndarray(img, format="bgr24").reformat(format="yuv420p")
            vf.pts = pts
            vf.time_base = tb
            for p in st.encode(vf):
                out.mux(p)
        for p in st.encode(None):
            out.mux(p)
    return {"pts_adjusted_for_monotonic": adjusted, "requested_time_base": str(tb)}


def demux_index(path: Path) -> dict:
    data = path.read_bytes()
    frames = []
    with av.open(str(path)) as c:
        s = c.streams.video[0]
        tb = s.time_base
        cc = s.codec_context
        extradata = bytes(cc.extradata) if cc.extradata else b""
        profile, level = cc.profile, getattr(cc, "level", None)
        for p in c.demux(s):
            if p.size == 0:
                continue
            pb = bytes(p)
            pos = p.pos
            exact = pos is not None and pos >= 0 and data[pos:pos + p.size] == pb
            if not exact:
                lo = max(0, (pos or 0) - 256)
                f = data.find(pb, lo, lo + p.size + 4096)
                if f >= 0:
                    pos, exact = f, True
            frames.append({"pts": p.pts, "dts": p.dts, "key": bool(p.is_keyframe), "offset": pos,
                           "size": p.size, "byte_exact": exact})
    frames.sort(key=lambda r: r["pts"])
    decode_order_equals_pts_order = all(a["dts"] <= b["dts"] for a, b in zip(frames, frames[1:]))
    return {"time_base": str(tb), "tb_num": tb.numerator, "tb_den": tb.denominator,
            "extradata_hex": extradata.hex(), "profile": profile, "level": level,
            "decode_order_equals_pts_order": decode_order_equals_pts_order, "frames": frames}


def verify_pattern(path: Path, sample: list[int]) -> dict:
    """Decode with libavcodec and read the index pattern on a sample of frames (sanity check)."""
    want = set(sample)
    ok = bad = 0
    with av.open(str(path)) as c:
        for k, fr in enumerate(c.decode(video=0)):
            if k in want:
                idx = read_index(fr.to_ndarray(format="bgr24"))
                ok += idx == k
                bad += idx != k
            if k > max(want):
                break
    return {"checked": ok + bad, "pattern_ok": ok}


VP9_LEVELS = [  # (level, max luma picture size, max luma sample rate) - VP9 level definitions, webmproject.org/vp9/levels
    (10, 36864, 829440), (11, 73728, 2764800), (20, 122880, 4608000), (21, 245760, 9216000),
    (30, 552960, 20736000), (31, 983040, 36864000), (40, 2228224, 83558400), (41, 2228224, 160432128),
    (50, 8912896, 311951360), (51, 8912896, 588251136)]


def codec_string(codec: str, ix: dict, w: int, h: int, fps: int) -> str:
    """WebCodecs codec string derived from the stream itself (avcC / av1C bytes; VP9 level from the level table)."""
    ed = bytes.fromhex(ix["extradata_hex"]) if ix.get("extradata_hex") else b""
    if codec == "libx264":
        if len(ed) >= 4 and ed[0] == 1:  # avcC: profile_idc, constraint flags, level_idc
            return f"avc1.{ed[1]:02X}{ed[2]:02X}{ed[3]:02X}"
        raise ValueError("no avcC")
    if codec == "libvpx-vp9":
        lvl = next(l for l, pic, rate in VP9_LEVELS if w * h <= pic and w * h * fps <= rate)
        return f"vp09.00.{lvl}.08"
    if codec == "libsvtav1":
        if len(ed) >= 3 and ed[0] == 0x81:  # av1C: marker|version, seq_profile(3)|seq_level_idx_0(5), tier|high_bitdepth|...
            prof, lvl = ed[1] >> 5, ed[1] & 0x1F
            tier = "H" if ed[2] & 0x80 else "M"
            bd = 10 if ed[2] & 0x40 else 8
            return f"av01.{prof}.{lvl:02d}{tier}.{bd:02d}"
        raise ValueError("no av1C")
    raise ValueError(codec)


def atomic_write(path: Path, text: str) -> None:
    """The harness may be reading manifest.json while clips are added: write a temp file and replace."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    for _ in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)
    raise RuntimeError(f"could not replace {path}")


def write_summary(manifest: dict) -> None:
    summary = {k: {kk: v for kk, v in c.items() if kk not in ("pts_s", "offsets", "sizes", "keyframes", "description_hex")}
               | {"keyframe_count": len(c["keyframes"])} for k, c in manifest["clips"].items()}
    (RESULTS / "clips_summary.json").write_text(json.dumps({"generator": manifest["generator"], "clips": summary}, indent=1))


def recompute_codec_strings() -> None:
    man_path = MEDIA / "manifest.json"
    m = json.loads(man_path.read_text())
    for key, c in m["clips"].items():
        if c["kind"] != "video":
            continue
        ix = demux_index(MEDIA / key)
        new = codec_string(c["codec"], ix, c["width"], c["height"], c["nominal_fps"])
        print(key, c["codec_string"], "->", new)
        c["codec_string"] = new
    atomic_write(man_path, json.dumps(m))
    write_summary(m)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--frames", type=int, default=0)
    ap.add_argument("--recompute-codec-strings", action="store_true")
    a = ap.parse_args()
    if a.recompute_codec_strings:
        recompute_codec_strings()
        return
    MEDIA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    man_path = MEDIA / "manifest.json"
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {"clips": {}}
    manifest["generator"] = {"python": sys.version.split()[0], "pyav": av.__version__,
                             "libav": {k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
                             "opencv": cv2.__version__, "platform": platform.platform(),
                             "pattern": f"{BITS} bits MSB first, (bit, NOT bit) cell pairs, {CELLS} cells across width, strip height = cell width"}
    only = [x for x in a.only.split(",") if x]
    for content, (cset, fps, n, vfr) in CONTENTS.items():
        if only and content not in only:
            continue
        if a.frames:
            n = min(n, a.frames)
        frames_src, n_distinct = load_frames(cset, n)
        frames = [burn_index(f, k) for k, f in enumerate(frames_src)]
        assert all(read_index(f) == k for k, f in enumerate(frames[:50]))
        if vfr == "hdr32.9":
            times, vfr = [k / 32.9 for k in range(n)], False
        else:
            times = vfr_times_s(n) if vfr else [k / fps for k in range(n)]
        h, w = frames[0].shape[:2]
        cdir = MEDIA / content
        cdir.mkdir(exist_ok=True)
        for vname, (codec, ext, gop, flags) in variants_for(content).items():
            g = fps if gop == "gop" else 1
            path = cdir / vname
            t0 = time.time()
            enc = encode(path, codec, ext, g, flags, frames, times, fps)
            ix = demux_index(path)
            sample = sorted(set([0, 1, g - 1, g, g + 1, n // 2, n - 2, n - 1]) - {-1})
            sample = [s for s in sample if 0 <= s < n]
            pv = verify_pattern(path, sample)
            pts_s = [fr["pts"] * ix["tb_num"] / ix["tb_den"] for fr in ix["frames"]]
            key = f"{content}/{vname}"
            manifest["clips"][key] = {
                "kind": "video", "content": content, "corpus_set": cset, "distinct_source_frames": n_distinct,
                "vfr": vfr, "nominal_fps": fps, "frames": len(ix["frames"]), "frames_encoded": n,
                "width": w, "height": h, "codec": codec, "container": ext, "gop": g,
                "encoder_options": encoder_options(codec, g), "mux_flags": flags or ({"movflags": "+faststart"} if ext == "mp4" else {}),
                "url": f"/media/clips/{content}/{vname}", "bytes": path.stat().st_size,
                "codec_string": codec_string(codec, ix, w, h, fps),
                "description_hex": ix["extradata_hex"] if codec == "libx264" else "",
                "time_base": ix["time_base"], "decode_order_equals_pts_order": ix["decode_order_equals_pts_order"],
                "all_samples_byte_exact": all(f["byte_exact"] for f in ix["frames"]),
                "keyframes": [i for i, f in enumerate(ix["frames"]) if f["key"]],
                "pts_s": pts_s, "offsets": [f["offset"] for f in ix["frames"]], "sizes": [f["size"] for f in ix["frames"]],
                "pyav_pattern_check": pv, **enc, "encode_wall_s_not_a_benchmark": round(time.time() - t0, 1),
            }
            print(key, len(ix["frames"]), "frames", path.stat().st_size, "B", "keys", len(manifest["clips"][key]["keyframes"]),
                  "byte_exact", manifest["clips"][key]["all_samples_byte_exact"], pv, enc)
        # JPEG sequence path: pattern-burned frames re-encoded by OpenCV (q90, 4:2:2 like the cameras)
        mdir = cdir / "mjpeg"
        (mdir / "frames").mkdir(parents=True, exist_ok=True)
        offs, sizes, blob = [], [], bytearray()
        params = [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_422]
        for k, f in enumerate(frames):
            ok, buf = cv2.imencode(".jpg", f, params)
            b = buf.tobytes()
            (mdir / "frames" / f"frame_{k:06d}.jpg").write_bytes(b)
            offs.append(len(blob)); sizes.append(len(b)); blob += b
        (mdir / "clip.mjpeg").write_bytes(bytes(blob))
        manifest["clips"][f"{content}/mjpeg"] = {
            "kind": "mjpeg", "content": content, "corpus_set": cset, "distinct_source_frames": n_distinct, "vfr": vfr,
            "nominal_fps": fps, "frames": n, "width": w, "height": h, "codec": "jpeg (OpenCV imencode q90 4:2:2)",
            "url": f"/media/clips/{content}/mjpeg/clip.mjpeg", "folder_url": f"/media/clips/{content}/mjpeg/frames/",
            "bytes": len(blob), "pts_s": times, "offsets": offs, "sizes": sizes, "keyframes": list(range(n)), "gop": 1,
        }
        print(f"{content}/mjpeg", n, len(blob))
        atomic_write(man_path, json.dumps(manifest))
    write_summary(manifest)


if __name__ == "__main__":
    main()
