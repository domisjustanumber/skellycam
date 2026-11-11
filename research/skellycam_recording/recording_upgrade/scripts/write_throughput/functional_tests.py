"""Functional (non-timing) tests for the recording wrappers of goal G5.

T1 round trip: every writer variant x payload (camera MJPEG 720p; FFV1 1080p from the YUY2 corpus).
   Byte-exact packet/file read-back, frame count, keyframe flags, timestamp round-trip error,
   whether PyAV / cv2 (FFMPEG backend) / ffprobe can open and decode it.
T2 cv2.VideoCapture on a JPEG folder as an image sequence (CAP_IMAGES, CAP_FFMPEG, CAP_ANY):
   contiguous numbering, numbering with a gap (one dropped frame), sub-folders.
T3 FFmpeg image2 demuxer through PyAV on the same folders (sequence + glob pattern types).
T4 hard kill (TerminateProcess via multiprocessing.Process.terminate) of a writer process in the middle
   of a paced 60 fps recording: how many acknowledged frames are readable, byte-exact, per reader.
T5 truncation of a cleanly closed file to 50 % of its size (stand-in for a partially flushed file).
T6 FFmpeg 'segment' muxer used through PyAV for packet passthrough (the alternative to manual rotation).

No timing numbers are produced. Media goes to MEDIA/functional (deleted at the end unless --keep).
Run from the repo root:
    .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/write_throughput/functional_tests.py
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wt_common as W  # noqa: E402

OUT = W.MEDIA / "functional"
RES = W.RESULTS / "functional"


def ticks_for(n: int, fps: int, seed=1) -> list[int]:
    """Producer clock with +-2 ms jitter (ns), like real camera arrival times."""
    rnd = random.Random(seed)
    t0 = 1_000_000_000_000
    return [t0 + int(i * 1e9 / fps) + rnd.randint(-2_000_000, 2_000_000) for i in range(n)]


def ffprobe_counts(path: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=flags",
           "-of", "csv=p=0", str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    flags = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    return dict(ffprobe_packets=len(flags), ffprobe_keyframes=sum(1 for f in flags if "K" in f),
                ffprobe_err=(p.stderr.strip().splitlines() or [None])[-1])


def cv2_count(path: str, api=None) -> tuple[int, bool]:
    import cv2
    cap = cv2.VideoCapture(path, api) if api is not None else cv2.VideoCapture(path)
    opened = cap.isOpened()
    n = 0
    while opened:
        ok, fr = cap.read()
        if not ok:
            break
        n += 1
    backend = cap.getBackendName() if opened else None
    cap.release()
    return n, opened, backend


def av_decode_count(path: Path) -> tuple[int, str | None]:
    import av
    n, err = 0, None
    try:
        with av.open(str(path)) as c:
            for _ in c.decode(video=0):
                n += 1
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    return n, err


def media_files(d: Path, cam=0):
    pre = f"cam{cam:02d}"
    return sorted(p for p in d.iterdir() if p.name.startswith(pre) and p.suffix not in (".idx",) and p.is_file())


def mp4_top_boxes(path: Path) -> dict:
    """Count top-level ISO-BMFF boxes (moov/moof/mdat/mfra...) and record the order of the first few."""
    import struct
    counts, order = {}, []
    with open(path, "rb") as f:
        while True:
            h = f.read(8)
            if len(h) < 8:
                break
            size, typ = struct.unpack(">I4s", h)
            typ = typ.decode("latin1")
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
                hdr = 16
            else:
                hdr = 8
            counts[typ] = counts.get(typ, 0) + 1
            if len(order) < 6:
                order.append(typ)
            if size == 0:
                break
            f.seek(size - hdr, 1)
    return dict(boxes=counts, first_boxes=order)


def first_frame_planes(path: Path):
    import av
    try:
        with av.open(str(path)) as c:
            for fr in c.decode(video=0):
                return fr.format.name, [bytes(pl) for pl in fr.planes]
    except Exception as e:  # noqa: BLE001
        return f"error {type(e).__name__}: {e}", []
    return None, []


def ref_planes(payload: dict):
    """Reference decode of payload frame 0: MJPEG via a bare decoder, FFV1 from its template MKV."""
    import av
    if payload.get("template"):
        return first_frame_planes(Path(payload["template"]))
    dec = av.CodecContext.create(payload["codec"], "r")
    fr = dec.decode(av.Packet(payload["packets"][0]))[0]
    return fr.format.name, [bytes(pl) for pl in fr.planes]


def read_back(variant: str, d: Path, src: list[bytes], ticks: list[int], ref=None) -> dict:
    """Read a recording back with every reader that applies; compare to the source payloads."""
    kind, _ = W.WRITER_VARIANTS[variant]
    r: dict = {}
    idx = d / "cam00.idx"
    recs = W.read_idx(idx) if idx.exists() else []
    r["idx_records"] = len(recs)
    if kind == "files":
        files = sorted((d / "cam00").rglob("frame_*"))
        exact = sum(1 for i, f in enumerate(files) if f.read_bytes() == src[i % len(src)])
        r.update(units=len(files), byte_exact=exact)
        return r
    if kind == "append":
        blob = next(d.glob("cam00.*raw"), None) or next(d.glob("cam00.mjpeg"))
        data = blob.read_bytes()
        frames = [data[o:o + n] for (_, _, o, n) in recs if o + n <= len(data)]
        exact = sum(1 for i, f in enumerate(frames) if f == src[i % len(src)])
        r.update(units=len(frames), byte_exact=exact, file_bytes=len(data))
        if blob.suffix == ".mjpeg":  # recovery without the index: split on SOI..EOI
            n_soi = 0
            i = data.find(b"\xff\xd8\xff")
            starts = []
            while i != -1:
                starts.append(i)
                i = data.find(b"\xff\xd8\xff", i + 3)
            parts = [data[s:e] for s, e in zip(starts, starts[1:] + [len(data)])]
            n_soi = sum(1 for i, p in enumerate(parts) if p == src[i % len(src)])
            r["byte_exact_without_index_soi_scan"] = n_soi
            # FFmpeg reads a raw .mjpeg elementary stream with the mjpeg demuxer
            r.update({f"ffprobe_{k}": v for k, v in ffprobe_counts(blob).items() if k != "ffprobe_err"})
            n, opened, be = cv2_count(str(blob))
            r.update(cv2_frames=n, cv2_opened=opened, cv2_backend=be)
        return r
    # containers (possibly several segment files)
    files = media_files(d)
    pk_all, pts_all, errs = [], [], []
    tb = None
    av_dec = 0
    cv = 0
    ffp = {"ffprobe_packets": 0, "ffprobe_keyframes": 0, "ffprobe_err": None}
    cv_open = []
    for f in files:
        pk, pts, err, tb = W.av_packets(f)
        pk_all += pk
        pts_all += pts
        if err:
            errs.append(err)
        n, e2 = av_decode_count(f)
        av_dec += n
        if e2 and not err:
            errs.append(e2)
        c, opened, be = cv2_count(str(f))
        cv += c
        cv_open.append(be)
        fp = ffprobe_counts(f)
        ffp["ffprobe_packets"] += fp["ffprobe_packets"]
        ffp["ffprobe_keyframes"] += fp["ffprobe_keyframes"]
        ffp["ffprobe_err"] = ffp["ffprobe_err"] or fp["ffprobe_err"]
    exact = sum(1 for i, p in enumerate(pk_all) if p == src[i % len(src)])
    r["file_bytes"] = sum(f.stat().st_size for f in files)
    r["container_overhead_bytes_per_frame"] = round((r["file_bytes"] - sum(len(p) for p in pk_all)) / max(len(pk_all), 1), 1)
    if files and files[0].suffix == ".mp4":
        r.update(mp4_top_boxes(files[0]))
    if ref is not None and files:
        got = first_frame_planes(files[0])
        r["frame0_decode_equals_reference"] = bool(got[1] and got == ref)
    r.update(units=len(pk_all), byte_exact=exact, files=len(files), av_decoded=av_dec, cv2_frames=cv,
             cv2_backends=sorted(set(map(str, cv_open))), av_errors=errs[:2], time_base=str(tb), **ffp)
    if tb is not None and pts_all and kind != "mkvseg":
        # timestamp round trip: stored pts (stream tb) vs producer tick relative to the first tick
        errs_ns = []
        for i, p in enumerate(pts_all[:len(ticks)]):
            if p is None:
                continue
            ns = p * tb.numerator * 1e9 / tb.denominator
            errs_ns.append(abs(ns - (ticks[i] - ticks[0])))
        r["pts_max_abs_err_us"] = round(max(errs_ns) / 1e3, 3) if errs_ns else None
    return r


# ------------------------------------------------------------------------------------------------ T1
def t1_round_trip(variants) -> list[dict]:
    rows = []
    cases = [("mjpeg", "720p30", 300), ("ffv1", "1080p30", 64)]
    for payload, prof, n in cases:
        pl = W.payload_for(prof, payload, 0)
        src = pl["packets"]
        fps = W.PROFILES[prof][2]
        tk = ticks_for(n, fps)
        ref = ref_planes(pl)
        for v in variants:
            d = OUT / "t1" / f"{payload}_{v}"
            shutil.rmtree(d, ignore_errors=True)
            row = dict(test="T1", payload=payload, profile=prof, variant=v, frames_written=n)
            try:
                wr = W.make_writer(v, d, 0, pl, fps)
                if W.WRITER_VARIANTS[v][0] == "mkvseg":
                    wr.segment_ns = int(2e9)  # 2 s segments so a 10 s clip gives several files
                for i in range(n):
                    wr.write(i, src[i % len(src)], tk[i])
                row["close"] = wr.close()
                row.update(read_back(v, d, src, tk, ref))
            except Exception as e:  # noqa: BLE001
                row["write_error"] = f"{type(e).__name__}: {e}"
            rows.append(row)
            print(json.dumps(row)[:400], flush=True)
    return rows


# ------------------------------------------------------------------------------------------------ T2/T3
def t2_t3_image_sequence() -> list[dict]:
    import av
    import cv2
    import numpy as np
    src = W.load_mjpeg_set("c930e_720p_flash", 30)
    rows = []
    layouts = {}
    base = OUT / "t2"
    shutil.rmtree(base, ignore_errors=True)
    # contiguous, start at 0
    d0 = base / "contiguous"
    d0.mkdir(parents=True)
    for i, b in enumerate(src):
        (d0 / f"frame_{i:06d}.jpg").write_bytes(b)
    layouts["contiguous_0..29"] = d0
    # gap: frame 10 missing (a dropped frame)
    dg = base / "gap_at_10"
    shutil.copytree(d0, dg)
    (dg / "frame_000010.jpg").unlink()
    layouts["gap_at_10"] = dg
    # subdirs of 10
    ds = base / "subdirs"
    for i, b in enumerate(src):
        (ds / f"{i // 10:04d}").mkdir(parents=True, exist_ok=True)
        (ds / f"{i // 10:04d}" / f"frame_{i:06d}.jpg").write_bytes(b)
    layouts["subdirs_of_10"] = ds
    ref0 = cv2.imdecode(np.frombuffer(src[0], np.uint8), cv2.IMREAD_COLOR)
    for name, d in layouts.items():
        pat = str(d / "frame_%06d.jpg")
        for api_name, api in (("CAP_IMAGES", cv2.CAP_IMAGES), ("CAP_FFMPEG", cv2.CAP_FFMPEG), ("CAP_ANY", None)):
            import cv2 as _c
            cap = _c.VideoCapture(pat, api) if api is not None else _c.VideoCapture(pat)
            opened = cap.isOpened()
            n, first_diff = 0, None
            fcount = cap.get(_c.CAP_PROP_FRAME_COUNT) if opened else None
            while opened:
                ok, fr = cap.read()
                if not ok:
                    break
                if n == 0:
                    first_diff = (int(np.abs(fr.astype(int) - ref0.astype(int)).max())
                                  if fr is not None and fr.shape == ref0.shape else f"shape {getattr(fr, 'shape', None)}")
                n += 1
            rows.append(dict(test="T2", layout=name, reader="cv2.VideoCapture", api=api_name, pattern="frame_%06d.jpg",
                             opened=opened, backend=cap.getBackendName() if opened else None,
                             frames_read=n, prop_frame_count=fcount, files_on_disk=len(list(d.rglob("*.jpg"))),
                             first_frame_max_abs_diff_vs_cv2_imdecode=first_diff))
            cap.release()
        # T3: FFmpeg image2 demuxer via PyAV
        for ptype, target in (("sequence", str(d / "frame_%06d.jpg")), ("glob", str(d / "frame_*.jpg")),
                              ("glob_recursive", str(d / "*" / "frame_*.jpg"))):
            n, err = 0, None
            try:
                opts = {"pattern_type": "glob" if ptype.startswith("glob") else "sequence"}
                with av.open(target, format="image2", options=opts) as c:
                    for pk in c.demux(c.streams.video[0]):
                        n += pk.size > 0
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"
            rows.append(dict(test="T3", layout=name, reader="PyAV image2", api=ptype, pattern=Path(target).name,
                             packets_read=max(n - 0, 0), error=err, files_on_disk=len(list(d.rglob("*.jpg")))))
    for r in rows:
        print(json.dumps(r), flush=True)
    return rows


# ------------------------------------------------------------------------------------------------ T4
def _kill_child(variant: str, d: str, acked, stop_after: int):
    pl = W.payload_for("720p30", "mjpeg", 0)
    src = pl["packets"]
    fps = 60
    wr = W.make_writer(variant, Path(d), 0, pl, fps)
    if W.WRITER_VARIANTS[variant][0] == "mkvseg":
        wr.segment_ns = int(2e9)
    t0 = time.perf_counter_ns()
    period = int(1e9 / fps)
    i = 0
    while i < stop_after:
        target = t0 + i * period
        now = time.perf_counter_ns()
        if target > now:
            time.sleep((target - now) / 1e9)
        wr.write(i, src[i % len(src)], 1_000_000_000_000 + i * period)
        i += 1
        acked.value = i
    wr.close()


def t4_kill(variants, seed=7, repeats=5) -> list[dict]:
    rnd = random.Random(seed)
    rows = []
    src = W.payload_for("720p30", "mjpeg", 0)["packets"]
    ctx = mp.get_context("spawn")
    for v, rep in [(v, r) for v in variants for r in range(repeats)]:
        d = OUT / "t4" / v
        shutil.rmtree(d, ignore_errors=True)
        acked = ctx.Value("q", 0, lock=False)  # a lock held at TerminateProcess would deadlock the parent
        p = ctx.Process(target=_kill_child, args=(v, str(d), acked, 10_000))
        p.start()
        while acked.value < 300 and p.is_alive():
            time.sleep(0.01)
        time.sleep(rnd.uniform(0.0, 1.2))  # kill point spread over more than one 1 s MP4 fragment
        p.terminate()  # TerminateProcess: no close(), no atexit, no Python-level flush
        p.join()
        n_ack = acked.value
        row = dict(test="T4", variant=v, repeat=rep, payload="mjpeg 720p (c930e_720p_flash)", acked_at_kill=n_ack,
                   exitcode=p.exitcode)
        row.update(read_back(v, d, src, ticks_for(n_ack + 2, 60)))
        row["acked_frames_all_readable"] = bool(row.get("byte_exact", 0) >= n_ack)
        row["acked_lost"] = max(n_ack - row.get("byte_exact", 0), 0)
        row["partial_or_corrupt_units"] = row.get("units", 0) - row.get("byte_exact", 0)
        rows.append(row)
        print(json.dumps(row)[:400], flush=True)
    return rows


# ------------------------------------------------------------------------------------------------ T5
def t5_truncate(variants) -> list[dict]:
    rows = []
    src = W.payload_for("720p30", "mjpeg", 0)["packets"]
    for v in variants:
        kind, _ = W.WRITER_VARIANTS[v]
        if kind in ("files", "mkvseg"):
            continue
        d0 = OUT / "t1" / f"mjpeg_{v}"
        if not d0.exists():
            continue
        d = OUT / "t5" / v
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(d0, d)
        target = next(f for f in d.iterdir() if f.name.startswith("cam00") and f.suffix != ".idx")
        size = target.stat().st_size
        with open(target, "r+b") as f:
            f.truncate(size // 2)
        row = dict(test="T5", variant=v, truncated_file=target.name, original_bytes=size, kept_bytes=size // 2,
                   frames_in_clean_file=300)
        row.update(read_back(v, d, src, ticks_for(300, 30)))
        rows.append(row)
        print(json.dumps(row)[:400], flush=True)
    return rows


# ------------------------------------------------------------------------------------------------ T6
def t6_segment_muxer() -> list[dict]:
    import av
    pl = W.payload_for("720p30", "mjpeg", 0)
    src = pl["packets"]
    d = OUT / "t6"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    row = dict(test="T6", what="PyAV format='segment', segment_format=matroska, segment_time=2, 300 frames @30")
    try:
        c = av.open(str(d / "cam00_seg%04d.mkv"), "w", format="segment",
                    options={"segment_time": "2", "segment_format": "matroska", "reset_timestamps": "1"})
        st = c.add_stream("mjpeg", rate=30)
        st.width, st.height, st.pix_fmt = 1280, 720, "yuvj422p"
        tb = W.US
        for i in range(300):
            pk = av.Packet(src[i % len(src)])
            pk.stream = st
            pk.time_base = tb
            pk.pts = pk.dts = int(i * 1_000_000 / 30)
            pk.is_keyframe = True
            c.mux(pk)
        c.close()
        files = sorted(d.glob("cam00_seg*.mkv"))
        tot, exact = 0, 0
        for f in files:
            pk, pts, err, _ = W.av_packets(f)
            for p in pk:
                exact += p == src[tot % len(src)]
                tot += 1
        row.update(files=len(files), packets=tot, byte_exact=exact, stream_time_base=str(_))
    except Exception as e:  # noqa: BLE001
        row["error"] = f"{type(e).__name__}: {e}"
    print(json.dumps(row), flush=True)
    return [row]


# ------------------------------------------------------------------------------------------------ report
def to_md(res: dict) -> str:
    L = [f"# write_throughput functional tests\n", f"Environment: `{json.dumps(res['env'])}`\n"]

    def table(rows, cols):
        out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for r in rows:
            out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/") for c in cols) + " |")
        return "\n".join(out)
    L.append("## T1 round trip (clean close)\n")
    L.append(table(res["T1"], ["payload", "variant", "frames_written", "units", "byte_exact", "idx_records", "files",
                               "av_decoded", "frame0_decode_equals_reference", "cv2_frames", "ffprobe_packets", "ffprobe_keyframes", "time_base",
                               "pts_max_abs_err_us", "container_overhead_bytes_per_frame", "first_boxes", "boxes", "write_error", "av_errors"]))
    L.append("\n## T2/T3 JPEG folder as an image sequence\n")
    L.append(table(res["T2T3"], ["test", "layout", "reader", "api", "pattern", "opened", "backend", "files_on_disk",
                                 "frames_read", "packets_read", "prop_frame_count", "first_frame_max_abs_diff_vs_cv2_imdecode",
                                 "error"]))
    L.append("\n## T4 hard kill of the writer process (TerminateProcess) at >= 300 acknowledged frames, 60 fps paced\n")
    L.append("Summary per variant over repeats (acked_lost = acknowledged frames not readable byte-exact):\n")
    agg = {}
    for r in res["T4"]:
        a = agg.setdefault(r["variant"], dict(variant=r["variant"], kills=0, lost=[], partial=[]))
        a["kills"] += 1
        a["lost"].append(r.get("acked_lost"))
        a["partial"].append(r.get("partial_or_corrupt_units"))
    L.append(table([dict(variant=a["variant"], kills=a["kills"], acked_lost_per_kill=a["lost"],
                         acked_lost_max=max(a["lost"]), partial_units_per_kill=a["partial"]) for a in agg.values()],
                   ["variant", "kills", "acked_lost_per_kill", "acked_lost_max", "partial_units_per_kill"]))
    L.append("\nAll kills:\n")
    L.append(table(res["T4"], ["variant", "repeat", "acked_at_kill", "acked_lost", "partial_or_corrupt_units", "units", "byte_exact", "acked_frames_all_readable",
                               "idx_records", "byte_exact_without_index_soi_scan", "files", "av_decoded", "cv2_frames",
                               "ffprobe_packets", "av_errors"]))
    L.append("\n## T5 clean file truncated to 50 %\n")
    L.append(table(res["T5"], ["variant", "original_bytes", "kept_bytes", "units", "byte_exact", "av_decoded",
                               "cv2_frames", "ffprobe_packets", "av_errors"]))
    L.append("\n## T6 FFmpeg segment muxer via PyAV\n")
    L.append(table(res["T6"], ["what", "files", "packets", "byte_exact", "stream_time_base", "error"]))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep media under MEDIA/functional")
    ap.add_argument("--only", default="T1,T2,T4,T5,T6")
    ap.add_argument("--repeats", type=int, default=5, help="T4 kills per variant")
    ap.add_argument("--tag", default="", help="suffix for the result files (e.g. _av19.0.2)")
    ap.add_argument("--variants", default="", help="comma list of writer variants (default: all)")
    a = ap.parse_args()
    RES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    variants = a.variants.split(",") if a.variants else list(W.WRITER_VARIANTS)
    res = dict(env=W.env_versions(), started=time.strftime("%Y-%m-%dT%H:%M:%S"), T1=[], T2T3=[], T4=[], T5=[], T6=[])
    only = a.only.split(",")
    if "T1" in only:
        res["T1"] = t1_round_trip(variants)
    if "T2" in only:
        res["T2T3"] = t2_t3_image_sequence()
    if "T4" in only:
        res["T4"] = t4_kill([v for v in variants if not v.endswith("fsync")], repeats=a.repeats)
    if "T5" in only:
        res["T5"] = t5_truncate(variants)
    if "T6" in only:
        res["T6"] = t6_segment_muxer()
    (RES / f"functional_results{a.tag}.json").write_text(json.dumps(res, indent=1, default=str))
    (RES / f"functional_results{a.tag}.md").write_text(to_md(res))
    if not a.keep:
        shutil.rmtree(OUT, ignore_errors=True)
    print("wrote", RES / f"functional_results{a.tag}.md")


if __name__ == "__main__":
    main()
