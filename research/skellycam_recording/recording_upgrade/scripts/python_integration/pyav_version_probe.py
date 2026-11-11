# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Compare PyAV versions for what the recorder needs (functional only, no timing).

Reports: bundled FFmpeg library versions; which encoders/decoders exist for the codecs this study considers;
whether recwriter.py (written against PyAV 18) still round-trips byte-exact with real PTS; whether every compat
clip decodes; and the type of Stream.time_base (PyAV 19 changed Fraction -> av.AVRational, CHANGELOG v19.0.0).

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/python_integration/pyav_version_probe.py --tag pyav_18.0.0_venv
  uv run --script research/skellycam_recording/recording_upgrade/scripts/python_integration/pyav_version_probe.py --tag pyav_19.0.2_uv
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path

import av

sys.path.insert(0, str(Path(__file__).parent))
CORPUS = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/corpus")
COMPAT = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/compat")
TMP = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/pyav_probe")
RESULTS = Path(__file__).resolve().parents[2] / "results/python_integration"
CODECS = ["mjpeg", "ffv1", "libsvtav1", "libaom-av1", "librav1e", "libdav1d", "av1", "av1_nvenc", "av1_qsv",
          "av1_amf", "av1_mf", "av1_vaapi", "av1_videotoolbox", "libvpx-vp9", "vp9", "vp9_qsv", "vp9_vaapi",
          "libx264", "h264_nvenc", "h264_qsv", "h264_amf", "h264_mf", "hevc_nvenc", "hevc_qsv", "libopenh264",
          "prores_ks", "dnxhd", "utvideo", "ffvhuff", "huffyuv", "libjxl", "libopenjpeg", "jpeg2000", "libwebp",
          "png", "h264", "hevc", "vp8", "libvpx", "opus", "libopus", "flac", "aac", "pcm_s16le"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()
    out = {"tag": args.tag, "av": av.__version__, "python": sys.version.split()[0],
           "library_versions": {k: list(v) for k, v in av.library_versions.items()}, "codecs": {}}
    try:
        out["ffmpeg_version_info"] = av.ffmpeg_version_info
    except AttributeError:
        out["ffmpeg_version_info"] = None
    for n in CODECS:
        modes = []
        for m in ("w", "r"):
            try:
                av.Codec(n, m)
                modes.append("enc" if m == "w" else "dec")
            except Exception:  # noqa: BLE001
                pass
        out["codecs"][n] = modes
    # recwriter round trip with this PyAV
    import zlib
    try:
        import recwriter as rw
        if TMP.exists():
            shutil.rmtree(TMP)
        frames = [p.read_bytes() for p in sorted((CORPUS / "c930e_720p_flash").glob("frame_*.jpg"))[:60]]
        rt = {}
        for cont in ("mkv", "mp4f", "avi"):
            for mode in ("real", "index"):
                if cont == "avi" and mode == "real":
                    continue
                stem = TMP / f"rt.{cont}.{mode}"
                try:
                    w = rw.RecordingWriter(stem, 1280, 720, container=cont, pts_mode=mode)
                    for i, f in enumerate(frames):
                        w.write(f, i, 5_000_000_000 + i * 33_366_667)
                    w.close()
                    pk = list(rw.RecordingReader(w.video_path).packets())
                    rt[f"{cont}.{mode}"] = {"time_base_type": type(w.tb).__name__, "time_base": str(w.tb),
                                            "packets": len(pk), "bytes_exact": all(b == f for (_, b, _, _), f in zip(pk, frames)) and len(pk) == 60}
                except Exception as e:  # noqa: BLE001
                    rt[f"{cont}.{mode}"] = {"error": repr(e)[:300], "trace": traceback.format_exc()[-600:]}
        out["recwriter_roundtrip"] = rt
    except Exception as e:  # noqa: BLE001
        out["recwriter_roundtrip"] = {"error": repr(e)[:300]}
    # decode every compat clip
    dec = {}
    if (COMPAT / "manifest.json").exists():
        man = json.loads((COMPAT / "manifest.json").read_text())
        for name, e in man["clips"].items():
            if not e.get("ok"):
                continue
            try:
                with av.open(e["path"]) as c:
                    s = c.streams.video[0]
                    n = sum(1 for _ in c.decode(s))
                    dec[name] = {"decoded": n, "decoder": s.codec_context.name, "stream_frames": s.frames,
                                 "average_rate": str(s.average_rate), "time_base_type": type(s.time_base).__name__}
            except Exception as ex:  # noqa: BLE001
                dec[name] = {"error": repr(ex)[:200]}
    out["compat_decode"] = dec
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"pyav_version_probe_{args.tag}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in ("av", "library_versions", "recwriter_roundtrip")}, indent=1, default=str))


if __name__ == "__main__":
    main()
