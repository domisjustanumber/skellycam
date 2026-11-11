"""ffmpeg CLI reference runs (no timing) for intra codecs/containers that PyAV 18/19 cannot reach:
libjxl, libaom-av1 (all-intra, lossless), libopenjpeg, libsvtjpegxs, librav1e, plus muxings PyAV refuses
(utvideo/ffvhuff/magicyuv/jpegls in Matroska) and rawvideo Bayer in NUT/MKV as a cross-check.

Inputs: real YUY2 1080p frames (corpus c930e_1080p_yuy2) and formats derived from them by
uintra_frames.derive (see that module). Raw inputs are written under the media folder.
Each run: encode with ffmpeg 9.0.2 -> ffprobe packet flags (all keyframes?) -> decode back to the fed
pix_fmt as rawvideo -> sha256 vs fed bytes. Also cuts a copy at 50 % and counts decodable frames.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/ffmpeg_cli_reference.py [--frames 4] [--only substr] [--keep]
Writes results/uncompressed_intra/ffmpeg_cli_reference.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uintra_frames as uf  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/cli")

# (id, source key, ffmpeg input pix_fmt, encoder args, ext, lossless intended)
RUNS = [
    ("rawvideo_bayer8.nut", "bayer_rggb8", "bayer_rggb8", ["-c:v", "rawvideo"], "nut", True),
    ("rawvideo_bayer16.nut", "bayer_rggb16le", "bayer_rggb16le", ["-c:v", "rawvideo"], "nut", True),
    ("rawvideo_bayer8.mkv", "bayer_rggb8", "bayer_rggb8", ["-c:v", "rawvideo"], "mkv", True),
    ("rawvideo_bayer16.mkv", "bayer_rggb16le", "bayer_rggb16le", ["-c:v", "rawvideo"], "mkv", True),
    ("rawvideo_gray16.mkv", "gray16le", "gray16le", ["-c:v", "rawvideo"], "mkv", True),
    ("rawvideo_bayer16_allow_raw_vfw.mkv", "bayer_rggb16le", "bayer_rggb16le", ["-c:v", "rawvideo", "-allow_raw_vfw", "1"], "mkv", True),
    ("rawvideo_gray16_allow_raw_vfw.mkv", "gray16le", "gray16le", ["-c:v", "rawvideo", "-allow_raw_vfw", "1"], "mkv", True),
    ("rawvideo_yuyv.mkv", "yuyv422", "yuyv422", ["-c:v", "rawvideo"], "mkv", True),
    ("rawvideo_nv12.mkv", "nv12", "nv12", ["-c:v", "rawvideo"], "mkv", True),
    ("ffv1_l4_bayer16.mkv", "bayer_rggb16le", "bayer_rggb16le",
     ["-c:v", "ffv1", "-level", "4", "-strict", "experimental", "-g", "1", "-slices", "4", "-slicecrc", "1"], "mkv", True),
    ("ffv1_l3_bayer16_as_gray16.mkv", "bayer_rggb16le", "gray16le",
     ["-c:v", "ffv1", "-level", "3", "-g", "1", "-slices", "4", "-slicecrc", "1"], "mkv", True),
    ("utvideo_yuv422p.mkv", "yuyv422", "yuyv422", ["-c:v", "utvideo", "-pix_fmt", "yuv422p", "-pred", "median"], "mkv", True),
    ("ffvhuff_yuv422p.mkv", "yuyv422", "yuyv422", ["-c:v", "ffvhuff", "-pix_fmt", "yuv422p", "-pred", "median"], "mkv", True),
    ("magicyuv_yuv422p.mkv", "yuyv422", "yuyv422", ["-c:v", "magicyuv", "-pix_fmt", "yuv422p", "-pred", "median"], "mkv", True),
    ("jpegls_gray16.mkv", "gray16le", "gray16le", ["-c:v", "jpegls"], "mkv", True),
    ("libjxl_lossless_e1_bayer16.jxlseq", "bayer_rggb16le", "gray16le", ["-c:v", "libjxl", "-distance", "0", "-effort", "1"], "jxlseq", True),
    ("libjxl_lossless_e1_gray8.jxlseq", "gray", "gray", ["-c:v", "libjxl", "-distance", "0", "-effort", "1"], "jxlseq", True),
    ("libjxl_lossless_e1_yuyv_via_rgb24.jxlseq", "yuyv422", "yuyv422", ["-c:v", "libjxl", "-distance", "0", "-effort", "1", "-pix_fmt", "rgb24"], "jxlseq", False),
    ("libjxl_lossy_d1_e1_yuyv_via_rgb24.jxlseq", "yuyv422", "yuyv422", ["-c:v", "libjxl", "-distance", "1", "-effort", "1", "-pix_fmt", "rgb24"], "jxlseq", False),
    ("libaom_allintra_lossless_yuv422p.mkv", "yuyv422", "yuyv422",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "0", "-aom-params", "lossless=1", "-pix_fmt", "yuv422p"], "mkv", True),
    ("libaom_allintra_lossless_gray12_bayer16.mkv", "bayer_rggb16le", "gray12le",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "0", "-aom-params", "lossless=1"], "mkv", True),
    ("libaom_allintra_crf30_yuv420p.mkv", "nv12", "nv12",
     ["-c:v", "libaom-av1", "-usage", "allintra", "-cpu-used", "8", "-crf", "30", "-pix_fmt", "yuv420p"], "mkv", False),
    ("libopenjpeg_gray16.mkv", "gray16le", "gray16le", ["-c:v", "libopenjpeg"], "mkv", True),
    ("libopenjpeg_bayer16_as_gray16.mkv", "bayer_rggb16le", "gray16le", ["-c:v", "libopenjpeg"], "mkv", True),
    ("libsvtjpegxs_yuv422p_bpp3.mkv", "yuyv422", "yuyv422", ["-c:v", "libsvtjpegxs", "-pix_fmt", "yuv422p", "-b:v", "186624000"], "mkv", False),
    ("librav1e_yuv422p_qp0.mkv", "yuyv422", "yuyv422",
     ["-c:v", "librav1e", "-pix_fmt", "yuv422p", "-qp", "0", "-speed", "10", "-g", "1"], "mkv", False),
    ("libsvtav1_lossless_yuv420p.mkv", "nv12", "nv12",
     ["-c:v", "libsvtav1", "-pix_fmt", "yuv420p", "-preset", "10", "-svtav1-params", "keyint=1:lossless=1"], "mkv", True),
    ("libx264_intra_lossless_yuv422p.mkv", "yuyv422", "yuyv422",
     ["-c:v", "libx264", "-pix_fmt", "yuv422p", "-qp", "0", "-preset", "ultrafast", "-g", "1"], "mkv", True),
    ("libx265_intra_lossless_gray12_bayer16.mkv", "bayer_rggb16le", "gray12le",
     ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1:keyint=1:log-level=error"], "mkv", True),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    MEDIA.mkdir(parents=True, exist_ok=True)
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", a.frames)
    ver = run(["ffmpeg", "-hide_banner", "-version"], text=True).stdout.splitlines()[0]
    inputs = {}
    results = []
    for rid, src, in_fmt, args, ext, lossless in RUNS:
        if a.only and a.only not in rid:
            continue
        if src not in inputs:
            frames = [uf.derive(src, f, w, h, idx=i) for i, f in enumerate(yuy)]
            raw = b"".join(b"".join(p.tobytes() for p in fr[0]) for fr in frames)
            p = MEDIA / f"in_{src}.raw"
            p.write_bytes(raw)
            inputs[src] = (p, raw, frames[0][2], frames[0][3])
        p, raw, fw, fh = inputs[src]
        seq = ext == "jxlseq"  # ffmpeg 9.0.2 cannot mux JPEG XL into mkv/nut/mov: one .jxl per frame (image2)
        out = MEDIA / (f"{rid}_%06d.jxl" if seq else f"{rid}")
        r = dict(id=rid, source=src, input_pix_fmt=in_fmt, args=" ".join(args), lossless_intended=lossless)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", in_fmt,
               "-s", f"{fw}x{fh}", "-r", "30", "-i", str(p), *args, str(out)]
        r["cmd"] = " ".join(cmd)
        e = run(cmd, text=True)
        outs = sorted(MEDIA.glob(f"{rid}_*.jxl")) if seq else ([out] if out.exists() else [])
        if e.returncode != 0 or not outs:
            r.update(ok=False, error=e.stderr.strip()[-400:])
            results.append(r)
            print(f"{rid:44s} ENCODE FAIL {r['error'][:150]}")
            continue
        size = sum(o.stat().st_size for o in outs)
        pk, st = [], {}
        for o in outs:
            pr = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                      "stream=codec_name,codec_tag_string,pix_fmt,profile:packet=flags,size", "-of", "json", str(o)], text=True)
            pj = json.loads(pr.stdout or "{}")
            pk += pj.get("packets", [])
            st = st or (pj.get("streams") or [{}])[0]
        dec = run(["ffmpeg", "-v", "error", *(["-f", "image2", "-c:v", "libjxl"] if seq else []), "-i", str(out),
                   "-f", "rawvideo", "-pix_fmt", in_fmt, "-"])
        r.update(ok=True, file_bytes=size, packets=len(pk), all_keyframes=bool(pk) and all("K" in x["flags"] for x in pk),
                 packet_bytes_mean=(sum(int(x["size"]) for x in pk) / len(pk)) if pk else None,
                 stored_codec=st.get("codec_name"), stored_tag=st.get("codec_tag_string"), stored_pix_fmt=st.get("pix_fmt"),
                 profile=st.get("profile"), decode_stderr=dec.stderr.decode(errors="replace").strip()[-300:],
                 decoded_bytes=len(dec.stdout), bit_exact_vs_fed=dec.stdout == raw)
        if not seq:  # a per-frame file sequence has no single file to truncate
            tr = out.with_name(out.stem + ".trunc50" + out.suffix)
            tr.write_bytes(out.read_bytes()[: size // 2])
            td = run(["ffmpeg", "-v", "error", "-i", str(tr), "-f", "rawvideo", "-pix_fmt", in_fmt, "-"])
            fb = len(raw) // a.frames
            r["trunc50_frames_decoded"] = len(td.stdout) // fb
            r["trunc50_frames_exact"] = sum(td.stdout[i * fb:(i + 1) * fb] == raw[i * fb:(i + 1) * fb] for i in range(len(td.stdout) // fb))
            r["trunc50_stderr"] = td.stderr.decode(errors="replace").strip()[-200:]
            tr.unlink()
        if not a.keep:
            for o in outs:
                o.unlink()
        results.append(r)
        print(f"{rid:44s} keys={r['all_keyframes']} exact={r['bit_exact_vs_fed']} B/f={r['packet_bytes_mean']} "
              f"pix={r['stored_pix_fmt']} trunc={r.get('trunc50_frames_decoded')}/{a.frames}")
    for p, *_ in inputs.values():
        if not a.keep:
            p.unlink()
    RESULTS.mkdir(parents=True, exist_ok=True)
    o = RESULTS / "ffmpeg_cli_reference.json"
    o.write_text(json.dumps(dict(ffmpeg=ver, frames=a.frames, width=w, height=h, results=results), indent=1))
    print("wrote", o)


if __name__ == "__main__":
    main()
