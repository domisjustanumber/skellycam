# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
"""Which (container, codec) pairs does PyAV's OutputContainer.add_stream accept?

PyAV refuses a pair when libavformat's avformat_query_codec(oformat, codec_id, FF_COMPLIANCE_NORMAL)
returns 0 (see av/container/output.py in the installed wheel). The ffmpeg CLI does not apply that gate,
so a pair refused here may still mux fine from the CLI. No frames are encoded.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/pyav_mux_acceptance.py
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/pyav_mux_acceptance.py
Writes results/uncompressed_intra/pyav_mux_acceptance_<av version>.json
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import av

OUT = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra"
CODECS = ["rawvideo", "ffv1", "ffvhuff", "huffyuv", "utvideo", "magicyuv", "jpegls", "jpeg2000", "png", "mjpeg",
          "libsvtav1", "libvpx-vp9", "prores_ks", "dnxhd", "libx264", "libx265", "h264_nvenc", "hevc_nvenc"]
FORMATS = ["matroska", "webm", "nut", "avi", "mov", "mp4"]


def main() -> None:
    res = {"av_version": av.__version__, "ffmpeg_version": getattr(av, "ffmpeg_version_info", "?"), "accept": {}}
    for codec in CODECS:
        row = {}
        for fmt in FORMATS:
            buf = io.BytesIO()
            try:
                with av.open(buf, "w", format=fmt) as c:
                    c.add_stream(codec)
                    row[fmt] = "accepted"
            except ValueError as e:
                row[fmt] = "refused" if "does not support" in str(e) else f"ValueError: {e}"
            except Exception as e:  # noqa: BLE001 - closing an empty container may raise; acceptance already known
                row.setdefault(fmt, f"{type(e).__name__}")
        res["accept"][codec] = row
        print(f"{codec:12s}", " ".join(f"{f}={'Y' if v == 'accepted' else 'n'}" for f, v in row.items()))
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"pyav_mux_acceptance_{av.__version__}.json"
    p.write_text(json.dumps(res, indent=1))
    print("wrote", p)


if __name__ == "__main__":
    main()
