"""Functional repro: PyAV add_stream(codec) + codec_context.extradata=... vs add_stream_from_template for FFV1 passthrough.

Finding (functional): with av 18.0.0, add_stream('ffv1') opens an FFV1 *encoder* when the container starts, which
writes its own configuration record, so passthrough packets from another FFV1 encoder are stored with the wrong
extradata. add_stream_from_template keeps the source extradata. Result JSON: results/write_throughput/functional/
repro_pyav_add_stream_extradata.json. Media under MEDIA/functional_repro (deleted at the end).
Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/repro_pyav_add_stream_extradata.py
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import av  # noqa: E402
import wt_common as W  # noqa: E402


def planes0(path):
    with av.open(str(path)) as c:
        st = c.streams.video[0]
        ed = len(st.codec_context.extradata or b"")
        for fr in c.decode(st):
            return ed, [bytes(p) for p in fr.planes]


def main():
    pl = W.build_ffv1_payload("720p")
    d = W.MEDIA / "functional_repro"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    ref_ed, ref = planes0(pl["template"])
    out = dict(env=W.env_versions(), template_extradata_bytes=ref_ed)
    for mode in ("add_stream_set_extradata", "add_stream_from_template"):
        path = d / f"{mode}.mkv"
        c = av.open(str(path), "w", format="matroska")
        if mode == "add_stream_set_extradata":
            ic = av.open(pl["template"])
            st = c.add_stream("ffv1", rate=30)
            st.width, st.height, st.pix_fmt = pl["w"], pl["h"], "yuv422p"
            st.codec_context.extradata = ic.streams.video[0].codec_context.extradata
            ic.close()
        else:
            ic = av.open(pl["template"])
            st = c.add_stream_from_template(ic.streams.video[0])
            ic.close()
        for i, b in enumerate(pl["packets"][:4]):
            p = av.Packet(b)
            p.stream = st
            p.time_base = W.US
            p.pts = p.dts = i * 33333
            p.is_keyframe = True
            c.mux(p)
        c.close()
        try:
            ed, got = planes0(path)
            out[mode] = dict(stored_extradata_bytes=ed, frame0_equals_template_decode=(got == ref))
        except Exception as e:  # noqa: BLE001
            out[mode] = dict(error=f"{type(e).__name__}: {e}")
    shutil.rmtree(d, ignore_errors=True)
    W.RESULTS.joinpath("functional").mkdir(parents=True, exist_ok=True)
    (W.RESULTS / "functional" / "repro_pyav_add_stream_extradata.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
