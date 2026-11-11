# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "opencv-python==4.12.0.88"]
# ///
"""Lean PyAV 19.0.2 re-make of the MJPEG / FFV1 / SVT-AV1 compat clips + cv2 4.12 CAP_FFMPEG read/seek probe.

Functional only, no timing. Reuses make_compat_clips.py (barcode, VFR PTS pattern, codec settings) and
cv2_read_probe.probe_clip (FreeMoCap-style FRAME_COUNT / sequential read / POS_FRAMES seeks) unchanged, but:
  - encodes with PyAV 19.0.2 (bundled FFmpeg 9.0.2) instead of the venv's PyAV 18.0.0,
  - only the clips that matter for the CFR-vs-VFR recommendation: mjpeg_mkv, mjpeg_mkv_vfr, mjpeg_avi,
    mjpeg_mp4frag_vfr, ffv1_mkv, ffv1_avi, av1svt_mp4, av1svt_mp4_vfr,
  - CAP_FFMPEG only, in-process (CAP_ANY picked FFMPEG for every file in the earlier probe; MSMF is not
    used by FreeMoCap and hung on FFV1-MKV),
  - also decodes each clip with PyAV 19 and counts frames.
Media -> raw folder python_integration/compat_pyav19; JSON -> argv[1].

  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/compat_recheck_pyav19.py \
      research/skellycam_recording/recording_upgrade/results/python_integration/compat_recheck_pyav19.json
"""
from __future__ import annotations

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import av
import cv2

sys.path.insert(0, str(Path(__file__).parent))
import cv2_read_probe as cp  # noqa: E402
import make_compat_clips as mc  # noqa: E402

OUT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/compat_pyav19")
CLIPS = ["mjpeg_mkv", "mjpeg_mkv_vfr", "mjpeg_avi", "mjpeg_mp4frag_vfr", "ffv1_mkv", "ffv1_avi",
         "av1svt_mp4", "av1svt_mp4_vfr"]


def main():
    dst = Path(sys.argv[1])
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    files = sorted((mc.CORPUS / "c930e_720p_flash").glob("frame_*.jpg"))[:mc.N]
    src = []
    for i, f in enumerate(files):
        with av.open(str(f)) as c:
            fr = next(c.decode(video=0))
        rgb = fr.to_ndarray(format="rgb24")
        mc.barcode(rgb, i)
        src.append(rgb)
    out = {"what": "PyAV 19.0.2 compat clips (subset) + cv2 CAP_FFMPEG probe; functional, no timing",
           "pyav": av.__version__, "ffmpeg": av.ffmpeg_version_info, "opencv": cv2.__version__,
           "date": "2026-11-09", "seek_targets": cp.SEEK_TARGETS, "clips": {}}
    for name in CLIPS:
        fmt, ext, codec, pix, opts, gop, mux_opts, mode = mc.VARIANTS[name]
        path = OUT / f"{name}.{ext}"
        e = {"container": fmt, "codec": codec, "pts": mode}
        try:
            with av.open(str(path), "w", format=fmt, options=mux_opts) as c:
                s = c.add_stream(codec, rate=30)
                s.width, s.height, s.pix_fmt = 1280, 720, pix
                s.codec_context.gop_size = gop
                if gop == 1:
                    s.codec_context.max_b_frames = 0
                s.options = opts
                tb = Fraction(1, 1000) if mode == "vfr" else Fraction(1, 30)
                s.codec_context.time_base = tb
                for i, rgb in enumerate(src):
                    vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(format=pix)
                    vf.pts = mc.vfr_pts_ms(i) if mode == "vfr" else i
                    vf.time_base = tb
                    for p in s.encode(vf):
                        c.mux(p)
                for p in s.encode():
                    c.mux(p)
            e["encode_ok"] = True
        except Exception as ex:  # noqa: BLE001
            e["encode_ok"] = False
            e["encode_error"] = repr(ex)[:300]
            out["clips"][name] = e
            continue
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            e["pyav_decoded"] = sum(1 for _ in c.decode(st))
            e["pyav_stream_frames"] = st.frames
            e["pyav_average_rate"] = str(st.average_rate)
        e["cv2_CAP_FFMPEG"] = cp.probe_clip(path, cv2.CAP_FFMPEG, mc.N, True)
        out["clips"][name] = e
        f = e["cv2_CAP_FFMPEG"]
        print(name, e["pyav_decoded"], f.get("frame_count_prop"), f.get("frames_read"), f.get("sequence_exact"),
              f.get("seek_all_exact"), flush=True)
    dst.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", dst)


if __name__ == "__main__":
    main()
