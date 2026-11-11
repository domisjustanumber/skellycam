# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy"]
# ///
"""PyAV 19.0.2 cross-check clips for the Chromium play/seek test (topic chromium_codecs, G8).

The main clip set (make_clips.py) was encoded with the ffmpeg 9.0.2 CLI. The study rule is that the implementation under
test is PyAV 19.0.2, so this script re-encodes the SAME stamped master (master/stamped_bgr24.raw, 60 frames, 1280x720,
index pattern in the top band) with PyAV 19.0.2's bundled FFmpeg for the royalty-free candidates, muxes them with PyAV,
and appends them to manifest.json as clips with id prefix "pyav19_" (the harness then runs them with --only pyav19).

Run: uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_codecs/make_pyav19_clips.py
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_codecs")
REPO = Path(__file__).resolve().parents[5]
LOG = REPO / "research/skellycam_recording/recording_upgrade/results/chromium_codecs/pyav19_clips_log.json"
W, H, N, FPS = 1280, 720, 60, 30

# id -> (encoder, pix_fmt, options, containers)
CLIPS = {
    "av1_main8_420": ("libsvtav1", "yuv420p", {"preset": "8", "crf": "35", "g": "30"}, ["mp4", "webm", "mkv"]),
    "av1_main8_intra": ("libsvtav1", "yuv420p", {"preset": "8", "crf": "35", "g": "1"}, ["mp4", "webm", "mkv"]),
    "vp9_p0_420": ("libvpx-vp9", "yuv420p", {"deadline": "realtime", "cpu-used": "8", "crf": "32", "b": "0", "g": "30"}, ["mp4", "webm", "mkv"]),
    "vp9_p0_intra": ("libvpx-vp9", "yuv420p", {"deadline": "realtime", "cpu-used": "8", "crf": "32", "b": "0", "g": "1"}, ["webm"]),
    "vp9_lossless_444": ("libvpx-vp9", "yuv444p", {"deadline": "realtime", "cpu-used": "8", "lossless": "1", "g": "30"}, ["webm", "mp4"]),
}
FMT = {"mp4": ("mp4", "mp4", {"movflags": "+faststart"}), "webm": ("webm", "webm", {}), "mkv": ("matroska", "mkv", {})}


def main() -> None:
    raw = np.fromfile(MEDIA / "master/stamped_bgr24.raw", np.uint8).reshape(N, H, W, 3)
    out_dir = MEDIA / "pyav19"
    out_dir.mkdir(exist_ok=True)
    log = {"av": av.__version__, "ffmpeg": av.library_versions.get("libavcodec"), "clips": {}}
    man = json.loads((MEDIA / "manifest.json").read_text())
    man["clips"] = [c for c in man["clips"] if not c["id"].startswith("pyav19_")]
    for cid, (enc, pix, opts, conts) in CLIPS.items():
        for cont in conts:
            fmt, ext, mopts = FMT[cont]
            path = out_dir / f"pyav19_{cid}__{cont}.{ext}"
            entry = {"encoder": enc, "pix_fmt": pix, "options": opts, "container": fmt}
            try:
                with av.open(str(path), "w", format=fmt, options=mopts) as oc:
                    st = oc.add_stream(enc, rate=FPS, options=opts)
                    st.width, st.height, st.pix_fmt = W, H, pix
                    st.time_base = Fraction(1, FPS)
                    cc = st.codec_context
                    for k, v in (("color_range", 1), ("colorspace", 1), ("color_primaries", 1), ("color_trc", 1)):
                        try:
                            setattr(cc, k, v)  # 1 = MPEG/tv range, 1 = BT.709
                        except Exception as e:  # noqa: BLE001
                            entry.setdefault("tag_errors", []).append(f"{k}: {e}")
                    for i in range(N):
                        fr = av.VideoFrame.from_ndarray(raw[i], format="bgr24")
                        fr = fr.reformat(format=pix, dst_colorspace="ITU709", dst_color_range="MPEG")
                        fr.pts = i
                        fr.time_base = Fraction(1, FPS)
                        for p in st.encode(fr):
                            oc.mux(p)
                    for p in st.encode(None):
                        oc.mux(p)
                entry["ok"] = True
                entry["bytes"] = path.stat().st_size
                man["clips"].append({"id": f"pyav19_{cid}__{cont}", "codec": f"pyav19_{cid}", "container": cont,
                                     "file": f"pyav19/{path.name}", "bytes": entry["bytes"]})
            except Exception as e:  # noqa: BLE001
                entry["ok"] = False
                entry["error"] = f"{type(e).__name__}: {e}"
            log["clips"][path.name] = entry
            print(path.name, entry.get("ok"), entry.get("error", ""))
    (MEDIA / "manifest.json").write_text(json.dumps(man))
    LOG.write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
