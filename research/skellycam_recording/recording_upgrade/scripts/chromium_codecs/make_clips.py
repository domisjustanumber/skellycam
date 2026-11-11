"""Build the Chromium playback test clips (topic: chromium_codecs, goal G8).

Input : real camera JPEGs from the shared corpus (c930e_720p_flash, frames 0..N-1, 1280x720).
Each frame is decoded with OpenCV, a per-frame binary index pattern is stamped into the top band,
and the stamped frames become the master (raw bgr24). Every codec is encoded ONCE from the master
into Matroska, then remuxed with `-c copy` into each container, so all containers of one codec carry
the identical bitstream. Elementary streams (IVF / Annex B) are also written for the WebCodecs test.

Pattern (top-left band, 40x40 px blocks at y=0..39):
    block 0 = white reference, block 1 = black reference, blocks 2..11 = index bits b9..b0
    (white = 1). The browser samples the centre 20x20 of each block and thresholds at the
    midpoint of the two references.
Content check: 32x18 grid of 40x40 block means of luma (0.299R+0.587G+0.114B) per frame is
stored in the manifest; the browser computes the same grid and reports the mean abs difference.

Outputs (media - outside the repo, frames show the room):
    C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs/
        clips/<codec>__<container>.<ext>, es/<codec>.<ivf|h264|hevc>, images/*, manifest.json
Text log (repo): results/chromium_codecs/make_clips_log.json  (ffmpeg errors per codec x container)

Run (from repo root):
    .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_clips.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[5]
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs")
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/chromium_codecs"

SRC_SET = "c930e_720p_flash"
N_FRAMES = 60
FPS = 30
W, H = 1280, 720
BLOCK = 40
NBITS = 10
GOP = 30

YUV_TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def vf(pix_fmt: str, full_range: bool = False) -> list[str]:
    rng = "pc" if full_range else "tv"
    return ["-vf", f"scale=out_color_matrix=bt709:out_range={rng},format={pix_fmt}"]


# codec id -> (encoder args, elementary-stream format or None, note)
CODECS: dict[str, tuple[list[str], str | None, str]] = {
    "av1_main8_420": (["-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", str(GOP), *vf("yuv420p"), *YUV_TAGS], "ivf", "AV1 Main 8-bit 4:2:0 (SVT-AV1)"),
    "av1_main10_420": (["-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", str(GOP), *vf("yuv420p10le"), *YUV_TAGS], "ivf", "AV1 Main 10-bit 4:2:0 (SVT-AV1)"),
    "av1_high8_444": (["-c:v", "libaom-av1", "-cpu-used", "8", "-row-mt", "1", "-crf", "35", "-g", str(GOP), *vf("yuv444p"), *YUV_TAGS], "ivf", "AV1 High 8-bit 4:4:4 (libaom)"),
    "av1_pro8_422": (["-c:v", "libaom-av1", "-cpu-used", "8", "-row-mt", "1", "-crf", "35", "-g", str(GOP), *vf("yuv422p"), *YUV_TAGS], "ivf", "AV1 Professional 8-bit 4:2:2 (libaom)"),
    # libaom-av1 with -g 1 segfaults in ffmpeg 9.0.2 (gyan full) on this machine (rc 139, recorded in NOTES) -> SVT-AV1
    "av1_main8_intra": (["-c:v", "libsvtav1", "-preset", "8", "-crf", "35", "-g", "1", *vf("yuv420p"), *YUV_TAGS], "ivf", "AV1 Main 8-bit 4:2:0 all-intra (SVT-AV1 -g 1)"),
    "vp9_p0_420": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", str(GOP), *vf("yuv420p"), *YUV_TAGS], "ivf", "VP9 profile 0 (8-bit 4:2:0)"),
    "vp9_p1_444": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", str(GOP), *vf("yuv444p"), *YUV_TAGS], "ivf", "VP9 profile 1 (8-bit 4:4:4)"),
    "vp9_p1_422": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", str(GOP), *vf("yuv422p"), *YUV_TAGS], "ivf", "VP9 profile 1 (8-bit 4:2:2)"),
    "vp9_p2_420_10": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", str(GOP), *vf("yuv420p10le"), *YUV_TAGS], "ivf", "VP9 profile 2 (10-bit 4:2:0)"),
    "vp9_p3_444_10": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", str(GOP), *vf("yuv444p10le"), *YUV_TAGS], "ivf", "VP9 profile 3 (10-bit 4:4:4)"),
    "vp9_lossless_444": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-lossless", "1", "-g", str(GOP), *vf("yuv444p"), *YUV_TAGS], "ivf", "VP9 lossless (profile 1, 4:4:4)"),
    "vp9_lossless_420": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-lossless", "1", "-g", str(GOP), *vf("yuv420p"), *YUV_TAGS], "ivf", "VP9 lossless (profile 0, 4:2:0)"),
    "vp9_p0_intra": (["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "32", "-b:v", "0", "-g", "1", *vf("yuv420p"), *YUV_TAGS], "ivf", "VP9 profile 0 all-intra (-g 1)"),
    "vp8": (["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-crf", "10", "-b:v", "4M", "-g", str(GOP), *vf("yuv420p"), *YUV_TAGS], "ivf", "VP8"),
    "h264_high_420": (["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", str(GOP), "-x264-params", "aud=1", *vf("yuv420p"), *YUV_TAGS], "h264", "H.264 High 4:2:0 (reference; libx264, B-frames default)"),
    "h264_high422": (["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", str(GOP), "-x264-params", "aud=1", *vf("yuv422p"), *YUV_TAGS], "h264", "H.264 High 4:2:2 (reference)"),
    "hevc_main_420": (["-c:v", "libx265", "-preset", "veryfast", "-crf", "28", "-g", str(GOP), "-x265-params", "aud=1:log-level=error", *vf("yuv420p"), *YUV_TAGS], "hevc", "HEVC Main (reference; libx265)"),
    "hevc_main10_420": (["-c:v", "libx265", "-preset", "veryfast", "-crf", "28", "-g", str(GOP), "-x265-params", "aud=1:log-level=error", *vf("yuv420p10le"), *YUV_TAGS], "hevc", "HEVC Main 10 (reference)"),
    "mjpeg_422": (["-c:v", "mjpeg", "-q:v", "3", *vf("yuvj422p", full_range=True)], None, "MJPEG 4:2:2 (re-encoded from stamped frames)"),
    "ffv1_422": (["-c:v", "ffv1", "-level", "3", "-g", "1", "-slices", "4", *vf("yuv422p"), *YUV_TAGS], None, "FFV1 v3 4:2:2"),
    "rawvideo_420": (["-c:v", "rawvideo", *vf("yuv420p"), *YUV_TAGS], None, "rawvideo yuv420p"),
    "rawvideo_yuyv": (["-c:v", "rawvideo", *vf("yuyv422"), *YUV_TAGS], None, "rawvideo yuyv422 (camera YUY2 layout)"),
    "theora": (["-c:v", "libtheora", "-q:v", "7", "-g", str(GOP), *vf("yuv420p")], None, "Theora (Ogg native, extra)"),
}

# container id -> (extension, extra muxer args)
CONTAINERS: dict[str, tuple[str, list[str]]] = {
    "mp4": ("mp4", ["-f", "mp4", "-movflags", "+faststart"]),
    "fmp4": ("mp4", ["-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof"]),
    "webm": ("webm", ["-f", "webm"]),
    "mkv": ("mkv", ["-f", "matroska"]),
    "mov": ("mov", ["-f", "mov"]),
    "avi": ("avi", ["-f", "avi"]),
    "ogg": ("ogv", ["-f", "ogg"]),
}


def stamp(img: np.ndarray, idx: int) -> None:
    img[0:BLOCK, 0:BLOCK] = 255
    img[0:BLOCK, BLOCK:2 * BLOCK] = 0
    for b in range(NBITS):
        bit = (idx >> (NBITS - 1 - b)) & 1
        x0 = (2 + b) * BLOCK
        img[0:BLOCK, x0:x0 + BLOCK] = 255 if bit else 0


def grid(img_bgr: np.ndarray) -> list[float]:
    b, g, r = (img_bgr[..., i].astype(np.float64) for i in range(3))
    y = 0.299 * r + 0.587 * g + 0.114 * b
    gh, gw = H // BLOCK, W // BLOCK
    return [round(float(v), 2) for v in y.reshape(gh, BLOCK, gw, BLOCK).mean(axis=(1, 3)).ravel()]


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return p.returncode, (p.stderr or "")[-1500:]


def probe(path: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=codec_name,codec_tag_string,profile,level,pix_fmt,width,height,nb_read_packets,color_range",
                        "-of", "json", str(path)], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)["streams"][0]
    except Exception:
        return {"error": p.stderr[-500:]}


def relog() -> None:
    """Re-derive the per-container mux log from the master .mkv files (remux into a temp dir; clips/ untouched)."""
    import tempfile
    log = {"ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0],
           "source_set": SRC_SET, "frames": N_FRAMES, "fps": FPS, "gop": GOP, "relog": True, "codecs": {}}
    man = json.loads((MEDIA / "manifest.json").read_text())
    with tempfile.TemporaryDirectory(dir="C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_codecs") as td:
        for cid, (enc, es_fmt, note) in CODECS.items():
            inter = MEDIA / "master" / f"{cid}.mkv"
            entry = {"note": note, "encoder_args": enc, "encode_rc": 0 if inter.exists() else None, "encode_err": "", "containers": {},
                     "probe": man["codecs"].get(cid, {}).get("probe"), "es": man["codecs"].get(cid, {}).get("es")}
            log["codecs"][cid] = entry
            for kid, (ext, mux) in CONTAINERS.items():
                out = Path(td) / f"{cid}__{kid}.{ext}"
                extra = ["-tag:v", "hvc1"] if cid.startswith("hevc") and kid in ("mp4", "fmp4", "mov") else []
                if kid == "avi" and cid.startswith("h264"):
                    extra = ["-bsf:v", "h264_mp4toannexb"]
                if kid == "avi" and cid.startswith("hevc"):
                    extra = ["-bsf:v", "hevc_mp4toannexb"]
                rc2, err2 = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(inter), "-map", "0:v:0", "-c", "copy", *extra, *mux, str(out)])
                ok = rc2 == 0 and out.exists() and out.stat().st_size > 0
                entry["containers"][kid] = {"ok": ok, "rc": rc2, "err": err2.strip()[-400:] if not ok else "",
                                            "clip_present": (MEDIA / "clips" / f"{cid}__{kid}.{ext}").exists()}
    (RESULTS / "make_clips_log.json").write_text(json.dumps(log, indent=1))
    print("relogged")


def main() -> None:
    if "--relog" in sys.argv:
        return relog()
    only = set(sys.argv[1:])
    (MEDIA / "clips").mkdir(parents=True, exist_ok=True)
    (MEDIA / "es").mkdir(exist_ok=True)
    (MEDIA / "master").mkdir(exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)

    master = MEDIA / "master/stamped_bgr24.raw"
    grids = []
    with open(master, "wb") as f:
        for i in range(N_FRAMES):
            data = (CORPUS / SRC_SET / f"frame_{i:06d}.jpg").read_bytes()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            assert img.shape == (H, W, 3), img.shape
            stamp(img, i)
            grids.append(grid(img))
            f.write(img.tobytes())
    src_in = ["-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", str(master)]

    log: dict = {"ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0],
                 "source_set": SRC_SET, "frames": N_FRAMES, "fps": FPS, "gop": GOP, "codecs": {}}
    clips = []
    for cid, (enc, es_fmt, note) in CODECS.items():
        if only and cid not in only:
            continue
        inter = MEDIA / "master" / f"{cid}.mkv"
        rc, err = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *src_in, *enc, "-f", "matroska", str(inter)])
        entry = {"note": note, "encoder_args": enc, "encode_rc": rc, "encode_err": err if rc else "", "containers": {}}
        log["codecs"][cid] = entry
        if rc != 0:
            print(f"ENCODE FAIL {cid}: {err[-300:]}")
            continue
        entry["probe"] = probe(inter)
        for kid, (ext, mux) in CONTAINERS.items():
            out = MEDIA / "clips" / f"{cid}__{kid}.{ext}"
            extra = ["-tag:v", "hvc1"] if cid.startswith("hevc") and kid in ("mp4", "fmp4", "mov") else []
            if kid == "avi" and cid.startswith("h264"):
                extra = ["-bsf:v", "h264_mp4toannexb"]
            if kid == "avi" and cid.startswith("hevc"):
                extra = ["-bsf:v", "hevc_mp4toannexb"]
            rc2, err2 = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(inter), "-map", "0:v:0", "-c", "copy", *extra, *mux, str(out)])
            ok = rc2 == 0 and out.exists() and out.stat().st_size > 0
            entry["containers"][kid] = {"ok": ok, "rc": rc2, "err": err2.strip()[-400:] if not ok else ""}
            if not ok:
                out.unlink(missing_ok=True)
                continue
            pr = probe(out)
            clips.append({"id": f"{cid}__{kid}", "codec": cid, "container": kid, "file": f"clips/{out.name}",
                          "bytes": out.stat().st_size, "probe": pr})
        if es_fmt:
            es = MEDIA / "es" / f"{cid}.{es_fmt}"
            rc3, err3 = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(inter), "-map", "0:v:0", "-c", "copy", "-f", es_fmt, str(es)])
            entry["es"] = {"ok": rc3 == 0, "file": f"es/{es.name}", "err": err3[-300:] if rc3 else ""}
        print(f"{cid}: " + " ".join(f"{k}={'ok' if v['ok'] else 'X'}" for k, v in entry["containers"].items()))

    manifest_path = MEDIA / "manifest.json"
    old = json.loads(manifest_path.read_text()) if (only and manifest_path.exists()) else {"clips": [], "codecs": {}}
    if only:
        clips = [c for c in old["clips"] if c["codec"] not in only] + clips
        codecs = {**old["codecs"], **{k: v for k, v in log["codecs"].items()}}
    else:
        codecs = log["codecs"]
    manifest = {"w": W, "h": H, "fps": FPS, "frames": N_FRAMES, "block": BLOCK, "nbits": NBITS, "gop": GOP,
                "grids": grids, "clips": clips,
                "codecs": {k: {"note": v["note"], "probe": v.get("probe"), "es": v.get("es")} for k, v in codecs.items()}}
    manifest_path.write_text(json.dumps(manifest))
    if only and (RESULTS / "make_clips_log.json").exists():  # keep full per-container entries of codecs not rebuilt
        old_log = json.loads((RESULTS / "make_clips_log.json").read_text())
        codecs = {**{k: v for k, v in old_log["codecs"].items() if "containers" in v}, **log["codecs"]}
    log["codecs"] = codecs
    (RESULTS / "make_clips_log.json").write_text(json.dumps(log, indent=1))
    print(f"{len(clips)} clips; manifest {manifest_path}")


if __name__ == "__main__":
    main()
