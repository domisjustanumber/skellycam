"""Build the shared real-camera frame corpus for the recording-upgrade study.

Splits camera captures that are already on disk (no camera is touched) into one file per frame,
and writes an index. Output goes OUTSIDE the repo (frames show the room):
    C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus/

    <set>/frame_000000.jpg ...        MJPEG sets: the camera's own JPEG bytes, unmodified
    <set>/frame_000000.yuy2 ...       raw YUY2 sets: the camera's own packed 4:2:2 bytes
    index.json                         per set: kind, width, height, frame count, sizes, DHT presence

Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/common/build_corpus.py
"""
from __future__ import annotations

import json
import statistics
import struct
from pathlib import Path

RAW = Path("C:/Users/Dom/Documents/skellycam-raw")
OUT = RAW / "skellycam_recording/recording_upgrade_20261109/corpus"
G = RAW / "results/windows/Gerald"
FLASH = RAW / "research/usb_cameras/results/windows/Gerald/timing/flash_run1_repositioned/capture"

MJPEG_SETS = {
    # name: (concatenated-JPEG file, nominal fps of the capture)
    "c930e_720p_flash": (FLASH / "vid_046d_pid_0843_mi_00_8_39dec205_0_0000.mjpeg", 30),
    "c922_720p_flash": (FLASH / "vid_046d_pid_085c_mi_00_8_268da596_0_0000.mjpeg", 30),
    "c922_1080p": (G / "suite_20261106T224912Z/W-MJPEG/c922prostreamw_046d-085c_C922SN01/pyav_ds_1920x1080_30/frames.mjpeg", 30),
    "c930e_1080p": (G / "suite_20261106T224912Z/W-MJPEG/logitechwebcam_046d-0843_7/pyav_ds_1920x1080_30/frames.mjpeg", 30),
    "c922_1600x896": (G / "suite_20261106T224912Z/W-MJPEG/c922prostreamw_046d-085c_C922SN01/pyav_ds_1600x896_30/frames.mjpeg", 30),
    "c922_720p60": (G / "suite_20261106T224912Z/W-MJPEG/c922prostreamw_046d-085c_C922SN01/pyav_ds_1280x720_60/frames.mjpeg", 60),
    "generic_1080p": (G / "suite_20261106T224912Z/W-MJPEG/usbcamera_4c4a-4a55_2/pyav_ds_1920x1080_30/frames.mjpeg", 30),
}
YUY2_SETS = {
    "c930e_1080p_yuy2": (G / "suite_20261106T181941Z/W-MJPEG/logitechwebcam_046d-0843_7/pyav_ds_1920x1080_5/frames.mjpeg", 1920, 1080),
    "c922_1080p_yuy2": (G / "suite_20261106T181941Z/W-MJPEG/c922prostreamw_046d-085c_C922SN01/pyav_ds_1920x1080_5/frames.mjpeg", 1920, 1080),
}


def split_jpegs(data: bytes) -> list[bytes]:
    """Split on SOI (FFD8FF) ... next SOI; trailing bytes after EOI stay with their frame (camera quirk kept)."""
    starts = []
    i = data.find(b"\xff\xd8\xff")
    while i != -1:
        starts.append(i)
        i = data.find(b"\xff\xd8\xff", i + 3)
    return [data[s:e] for s, e in zip(starts, starts[1:] + [len(data)])]


def jpeg_info(b: bytes) -> dict:
    """Walk markers up to SOS: SOF dims, presence of DHT/DQT."""
    pos, info = 2, {"dht": False, "dqt": False, "w": None, "h": None, "sof": None}
    while pos + 4 <= len(b) and b[pos] == 0xFF:
        m = b[pos + 1]
        if m == 0xDA:  # SOS
            break
        seglen = struct.unpack(">H", b[pos + 2 : pos + 4])[0]
        if m == 0xC4:
            info["dht"] = True
        elif m == 0xDB:
            info["dqt"] = True
        elif m in (0xC0, 0xC1, 0xC2):
            info["sof"] = hex(m)
            info["h"], info["w"] = struct.unpack(">HH", b[pos + 5 : pos + 9])
        pos += 2 + seglen
    info["ends_with_eoi"] = b.rstrip(b"\x00").endswith(b"\xff\xd9")
    return info


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    for name, (src, fps) in MJPEG_SETS.items():
        frames = split_jpegs(src.read_bytes())
        d = OUT / name
        d.mkdir(exist_ok=True)
        infos = []
        for k, fb in enumerate(frames):
            (d / f"frame_{k:06d}.jpg").write_bytes(fb)
            infos.append(jpeg_info(fb))
        sizes = [len(f) for f in frames]
        index[name] = {
            "kind": "mjpeg", "source": str(src), "nominal_fps": fps, "frames": len(frames),
            "width": infos[0]["w"], "height": infos[0]["h"], "sof": infos[0]["sof"],
            "bytes_median": statistics.median(sizes), "bytes_min": min(sizes), "bytes_max": max(sizes),
            "frames_with_dht": sum(i["dht"] for i in infos),
            "frames_ending_in_eoi": sum(i["ends_with_eoi"] for i in infos),
        }
    for name, (src, w, h) in YUY2_SETS.items():
        data = src.read_bytes()
        fsz = w * h * 2
        d = OUT / name
        d.mkdir(exist_ok=True)
        n = len(data) // fsz
        for k in range(n):
            (d / f"frame_{k:06d}.yuy2").write_bytes(data[k * fsz : (k + 1) * fsz])
        index[name] = {"kind": "yuy2", "source": str(src), "frames": n, "width": w, "height": h,
                       "bytes_per_frame": fsz, "layout": "packed YUYV 4:2:2 (ffmpeg pix_fmt yuyv422)"}
    (OUT / "index.json").write_text(json.dumps(index, indent=1))
    print(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()
