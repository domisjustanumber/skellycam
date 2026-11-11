"""Extra inputs for the Chromium tests (run after make_clips.py).

1. Camera-native MJPEG passthrough clips: the corpus JPEG bytes of c930e_720p_flash frames 0..59,
   UNMODIFIED, muxed with `ffmpeg -c copy` (image2 demuxer) into mkv / avi / mov / mp4.
   No index pattern (that would need a re-encode) - these only test "does Chromium open it at all".
2. Still images for ImageDecoder / createImageBitmap / <img>:
   - real camera JPEGs, unmodified: all frames of c922_1080p, c930e_1080p, c922_1600x896, c922_720p60,
     generic_1080p (some frames have extra bytes before EOI), first 10 of c930e_720p_flash.
   - stamped frame 0 (from make_clips master) re-encoded to PNG, WebP (libwebp), AVIF 4:2:0 and 4:4:4
     (libaom-av1 still picture), JPEG XL (libjxl).
   For every image the expected 16x9 cell-mean luma grid (OpenCV decode for JPEGs; the source pixels
   for the others) is stored so the browser can check decoded content.
Output: <media>/camera_mjpeg/*, <media>/images/*, manifest.json gains "camera_clips" and "images".

Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_extras.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs")
GW, GH = 16, 9


def grid16(img_bgr: np.ndarray) -> list[float]:
    h, w = img_bgr.shape[:2]
    b, g, r = (img_bgr[..., i].astype(np.float64) for i in range(3))
    y = 0.299 * r + 0.587 * g + 0.114 * b
    out = []
    for i in range(GH):
        for j in range(GW):
            y0, y1 = (i * h) // GH, ((i + 1) * h) // GH
            x0, x1 = (j * w) // GW, ((j + 1) * w) // GW
            out.append(round(float(y[y0:y1, x0:x1].mean()), 2))
    return out


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return p.returncode, p.stderr[-600:]


def main() -> None:
    man = json.loads((MEDIA / "manifest.json").read_text())

    # 1. camera-native MJPEG passthrough
    cam = MEDIA / "camera_mjpeg"
    cam.mkdir(exist_ok=True)
    seq = cam / "seq"
    seq.mkdir(exist_ok=True)
    for i in range(60):
        shutil.copyfile(CORPUS / "c930e_720p_flash" / f"frame_{i:06d}.jpg", seq / f"f_{i:06d}.jpg")
    camera_clips = []
    for kid, ext, fmt in [("mkv", "mkv", "matroska"), ("avi", "avi", "avi"), ("mov", "mov", "mov"), ("mp4", "mp4", "mp4")]:
        out = cam / f"mjpeg_camera__{kid}.{ext}"
        rc, err = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", "30", "-i", str(seq / "f_%06d.jpg"),
                       "-c", "copy", "-f", fmt, str(out)])
        # byte-exact check: first packet of the output equals the corpus file
        exact = None
        if rc == 0:
            p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(out), "-map", "0:v:0", "-c", "copy", "-frames:v", "1", "-f", "image2", "-y", str(cam / "first.jpg")], capture_output=True)
            exact = (cam / "first.jpg").read_bytes() == (seq / "f_000000.jpg").read_bytes()
        camera_clips.append({"id": f"mjpeg_camera__{kid}", "codec": "mjpeg_camera", "container": kid,
                             "file": f"camera_mjpeg/{out.name}" if rc == 0 else None, "mux_rc": rc,
                             "mux_err": err if rc else "", "first_packet_byte_exact": exact, "nopattern": True})
        print(kid, rc, exact)

    # 2. images
    imgdir = MEDIA / "images"
    imgdir.mkdir(exist_ok=True)
    images = []
    sets = {"c922_1080p": None, "c930e_1080p": None, "c922_1600x896": None, "c922_720p60": None, "generic_1080p": None, "c930e_720p_flash": 10}
    for s, lim in sets.items():
        files = sorted((CORPUS / s).glob("frame_*.jpg"))[: lim or None]
        for f in files:
            data = f.read_bytes()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            eoi = data.rfind(b"\xff\xd9")
            name = f"cam_{s}_{f.stem}.jpg"
            shutil.copyfile(f, imgdir / name)
            images.append({"id": name, "file": f"images/{name}", "mime": "image/jpeg", "w": img.shape[1], "h": img.shape[0],
                           "grid": grid16(img), "camera_bytes": True, "trailing_after_eoi": len(data) - eoi - 2, "bytes": len(data)})

    raw = np.fromfile(MEDIA / "master/stamped_bgr24.raw", dtype=np.uint8, count=1280 * 720 * 3).reshape(720, 1280, 3)
    png = imgdir / "stamped0.png"
    cv2.imwrite(str(png), raw)
    g = grid16(raw)
    images.append({"id": "stamped0.png", "file": "images/stamped0.png", "mime": "image/png", "w": 1280, "h": 720, "grid": g})
    for name, mime, args in [
        ("stamped0.webp", "image/webp", ["-c:v", "libwebp", "-quality", "85", "-f", "image2"]),
        ("stamped0_420.avif", "image/avif", ["-c:v", "libaom-av1", "-still-picture", "1", "-crf", "30", "-pix_fmt", "yuv420p", "-f", "avif"]),
        ("stamped0_444.avif", "image/avif", ["-c:v", "libaom-av1", "-still-picture", "1", "-crf", "30", "-pix_fmt", "yuv444p", "-f", "avif"]),
        ("stamped0.jxl", "image/jxl", ["-c:v", "libjxl", "-distance", "1.0", "-f", "image2"]),
        ("stamped0_ffmpeg.jpg", "image/jpeg", ["-c:v", "mjpeg", "-q:v", "3", "-pix_fmt", "yuvj422p", "-f", "image2"]),
    ]:
        out = imgdir / name
        rc, err = run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(png), "-frames:v", "1", *args, str(out)])
        images.append({"id": name, "file": f"images/{name}" if rc == 0 else None, "mime": mime, "w": 1280, "h": 720, "grid": g,
                       "enc_rc": rc, "enc_err": err if rc else ""})
        print(name, rc, err[-200:] if rc else "")

    man["camera_clips"] = camera_clips
    man["images"] = images
    (MEDIA / "manifest.json").write_text(json.dumps(man))
    print(len(images), "images")


if __name__ == "__main__":
    main()
