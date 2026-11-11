# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""GF09 step 4 prep (functional, no timing): Chromium test media from the 300-frame NVENC lossless MKVs written by
gf09_lossless_check.py --part nvenc (same bitstream; no re-encode).

For each clip: the first 60 packets remuxed (stream copy) to MKV and to MP4 (+faststart); a WebCodecs sidecar
(<id>.wc.json: codec string built from the avcC/hvcC extradata, base64 extradata, base64 packets 0-7); and the exact
reference NV12 bytes of frames 0, 1 and 7 (<id>.ref_f<k>.nv12 = tight Y plane then tight interleaved UV plane),
rebuilt from the corpus exactly as the encoder was fed (uintra_frames.derive('nv12'), frame k = corpus frame k % 8).
Optional extra clips (--extra id=path.mkv:pix) for any exact QSV output.

Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09/prep_chromium.py
Writes <media>/chromium/manifest.json and results/uncompressed_intra/gapfill/GF09_chromium_media.json
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import av
import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]))
import uintra_frames as uf  # noqa: E402

MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/gapfill/GF09")
OUTDIR = MEDIA / "chromium"
RESULTS = HERE.parents[4] / "results" / "uncompressed_intra" / "gapfill"
CLIPS = {
    "h264_nvenc_lossless_nv12": MEDIA / "nvenc__h264_nvenc__nv12_1080p__t1.mkv",
    "hevc_nvenc_lossless_nv12": MEDIA / "nvenc__hevc_nvenc__nv12_1080p__t1.mkv",
}
NPKT = 60
REF_FRAMES = [0, 1, 7]


def avc_codec_string(ex: bytes) -> str:
    # avcC: configurationVersion, AVCProfileIndication, profile_compatibility, AVCLevelIndication (ISO/IEC 14496-15)
    return f"avc1.{ex[1]:02X}{ex[2]:02X}{ex[3]:02X}"


def hevc_codec_string(ex: bytes, tag: str = "hvc1") -> str:
    # hvcC byte 1: general_profile_space(2) tier(1) profile_idc(5); bytes 2-5 compatibility flags; 6-11 constraint
    # flags; 12 level_idc (ISO/IEC 14496-15 Annex E codec string rules).
    b1 = ex[1]
    space = "" if (b1 >> 6) == 0 else "ABC"[(b1 >> 6) - 1]
    tier = "H" if (b1 >> 5) & 1 else "L"
    prof = b1 & 0x1F
    compat = int.from_bytes(ex[2:6], "big")
    rev = int(f"{compat:032b}"[::-1], 2)
    cons = list(ex[6:12])
    while cons and cons[-1] == 0:
        cons.pop()
    s = f"{tag}.{space}{prof}.{rev:X}.{tier}{ex[12]}"
    if cons:
        s += "." + ".".join(f"{c:02X}" for c in cons)
    return s


def remux(src: Path, dst: Path, fmt_opts: dict | None = None) -> dict:
    with av.open(str(src)) as ic, av.open(str(dst), "w", options=fmt_opts or {}) as oc:
        ivs = ic.streams.video[0]
        ovs = oc.add_stream_from_template(ivs)
        n = 0
        for p in ic.demux(ivs):
            if not p.size:
                continue
            if n >= NPKT:
                break
            p.stream = ovs
            oc.mux(p)
            n += 1
    with av.open(str(dst)) as c:
        vs = c.streams.video[0]
        tag = vs.codec_context.codec_tag
        cnt = sum(1 for p in c.demux(vs) if p.size)
    return {"file": dst.name, "bytes": dst.stat().st_size, "packets": cnt, "codec_tag": tag}


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    yuy, w, h = uf.load_yuy2("c930e_1080p_yuy2", 8)
    manifest = {"w": w, "h": h, "fps": 30, "ref_frames": REF_FRAMES, "clips": []}
    for cid, src in CLIPS.items():
        if not src.exists():
            raise SystemExit(f"missing {src}; run gf09_lossless_check.py --part nvenc first")
        with av.open(str(src)) as ic:
            vs = ic.streams.video[0]
            ex = bytes(vs.codec_context.extradata)
            codec = vs.codec_context.name
            pk = []
            for p in ic.demux(vs):
                if p.size:
                    pk.append({"pts": int(p.pts), "key": bool(p.is_keyframe), "b64": base64.b64encode(bytes(p)).decode()})
                if len(pk) >= 8:
                    break
            tb = vs.time_base
        cs = avc_codec_string(ex) if codec == "h264" else hevc_codec_string(ex)
        mkv = remux(src, OUTDIR / f"{cid}.mkv")
        mp4 = remux(src, OUTDIR / f"{cid}.mp4", {"movflags": "+faststart"})
        wc = {"codec": cs, "description_b64": base64.b64encode(ex).decode(), "time_base": [tb.numerator, tb.denominator],
              "packets": pk, "w": w, "h": h}
        (OUTDIR / f"{cid}.wc.json").write_text(json.dumps(wc))
        refs = {}
        for k in REF_FRAMES:
            planes = uf.derive("nv12", yuy[k % 8], w, h, k % 8)[0]
            b = np.ascontiguousarray(planes[0]).tobytes() + np.ascontiguousarray(planes[1]).tobytes()
            (OUTDIR / f"{cid}.ref_f{k}.nv12").write_bytes(b)
            refs[k] = hashlib.sha256(b).hexdigest()
        manifest["clips"].append({"id": cid, "source_mkv": src.name, "codec_string": cs, "mkv": mkv, "mp4": mp4,
                                  "wc": f"{cid}.wc.json", "refs_sha256": refs, "extradata_hex_head": ex[:16].hex()})
        print(cid, cs, mkv, mp4)
    (OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (RESULTS / "GF09_chromium_media.json").write_text(json.dumps({"av_version": av.__version__, **manifest}, indent=1))
    print("wrote", OUTDIR / "manifest.json")


if __name__ == "__main__":
    main()
