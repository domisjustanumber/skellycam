"""Is setting av.Packet.is_keyframe required when muxing camera JPEGs with PyAV? Also: which stream setups work (question a).

Part 1 - keyframe flag: c930e_720p_flash (891 frames, real VFR timestamps) muxed with is_keyframe False vs True into
mkv / mp4 / mov / nut / avi_tb_rate; report ffprobe keyframe-flagged packets, cv2 seek accuracy, PyAV seek accuracy.
Part 2 - stream setup variants (first 30 frames): add_mux_stream with/without width+height, add_stream('mjpeg') (opens an
encoder context, yuvj422p and yuvj420p), add_stream_from_template(av.open(jpeg)); write ok / error, frames indexed, pix_fmt seen.

Run (repo root): .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/keyframe_check.py
Writes results/jpeg_passthrough/keyframe_setup.json
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402
import jp_io as io  # noqa: E402
from mux_matrix import compare  # noqa: E402


def main() -> None:
    name = "c930e_720p_flash"
    frames = C.load_set(name)
    ts = C.real_timestamps_ns(name, frames)
    us = [(t - ts[0]) // 1000 for t in ts]
    d = C.MEDIA / "keyframe_setup"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    res = {"meta": {"date": time.strftime("%Y-%m-%dT%H:%M:%S")}, "keyframe": {}, "setup": {}}
    for cont in ["mkv", "mp4", "mov", "nut", "avi_tb_rate"]:
        for kf in (False, True):
            p = d / f"kf{int(kf)}_{cont}{io.CONTAINERS[cont][1]}"
            vfr = cont != "avi_tb_rate"
            wr = io.pyav_write(p, cont, frames, 1280, 720, us if vfr else None, keyframe=kf)
            row = {"write_ok": wr.get("ok"), "error": wr.get("error")}
            if wr.get("ok"):
                exp = [u / 1e6 for u in us] if vfr else [k / 30 for k in range(len(frames))]
                fp = io.ffprobe(p)
                row["ffprobe_keyframe_flagged_packets"] = fp.get("keyframe_flags")
                row["ffprobe_packets"] = fp.get("packets_nonempty")
                cv = io.cv2_read(p, "FFMPEG", None, seek=True)
                row["cv2_seek"] = f"{cv.get('seek_exact')}/{cv.get('seek_total')}"
                row["cv2_seek_detail"] = cv.get("seek")
                ps = io.pyav_seek(p, [0, 1, 300, 445, 890, 2], exp)
                row["pyav_seek_exact"] = f"{sum(1 for s in ps if s.get('exact'))}/{len(ps)}"
                row["pyav_seek_detail"] = ps
            res["keyframe"][f"{cont}|kf={kf}"] = row
            print(cont, kf, {k: v for k, v in row.items() if not k.endswith("detail")}, flush=True)
    f30, us30 = frames[:30], us[:30]
    in_shas = [C.sha(f) for f in f30]
    for cont in ["mkv", "mp4", "mov", "avi", "nut", "mjpeg_raw_mux"]:
        for setup in ["mux_stream", "mux_stream_nodims", "encoder_ctx", "encoder_ctx_420", "template"]:
            p = d / f"setup_{setup}_{cont}{io.CONTAINERS[cont][1]}"
            wr = io.pyav_write(p, cont, f30, 1280, 720, us30, setup=setup)
            row = {"write_ok": wr.get("ok"), "error": (wr.get("error") or "")[-160:], "stream_tb": wr.get("stream_time_base_after_first_mux")}
            if wr.get("ok"):
                fp = io.ffprobe(p)
                pv = io.pyav_demux(p, decode=False)
                row.update({"ffprobe_pix_fmt": fp.get("pix_fmt"), "ffprobe_w": fp.get("width"), "ffprobe_packets": fp.get("packets_nonempty"),
                            "pyav_bytes": compare(pv.get("shas", []), in_shas)})
            res["setup"][f"{cont}|{setup}"] = row
            print(cont, setup, row.get("write_ok"), row.get("error", "")[-80:], row.get("ffprobe_packets"), row.get("ffprobe_pix_fmt"), flush=True)
    shutil.rmtree(d, ignore_errors=True)
    C.write_json(C.RESULTS / "keyframe_setup.json", res)
    print("wrote", C.RESULTS / "keyframe_setup.json")


if __name__ == "__main__":
    main()
