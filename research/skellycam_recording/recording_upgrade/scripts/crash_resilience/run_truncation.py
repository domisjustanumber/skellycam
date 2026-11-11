"""(b) power-loss emulation: truncate the in-progress image of each recording at >= 24 byte offsets.

Source image = the `drained:N` recording from run_kill_matrix.py (all N frames fed and the encoder drained, writer
killed before close, so no trailer/index/final sizes). A power cut leaves some prefix of that image on disk; we emulate
it by keeping the first `offset` bytes (multi-file kinds: the files are taken in write order, the file containing the
offset is cut, later files are dropped; raw .mjpeg+.idx: data cut at offset, index keeps only records whose data had
been completely written, because the writer writes+flushes data before its index record).

Offsets per variant: 20 uniform random (seeded by crc32(variant id)) + 4 targeted: byte 64 (inside the header), the
middle of the first packet, the middle of the median packet, and size-1.
ideal = packets of the clean file that lie completely before the offset (ffprobe packet pos+size; approximate to
+-1 frame because pos is the block/sample start).
Limits: a real power cut can also leave zero-filled or stale blocks and lose data out of order (not emulated here).

usage: python run_truncation.py [--n 150] [--payloads ...] [--containers ...] [--workers 3]
writes results/crash_resilience/truncation.json and truncation.md
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def layout(img: Path, clean: Path, c: str):
    """-> (files [(name, size)], packets [(global_pos, size)])"""
    fmt, ext, opts, kind = cc.spec(c)
    if kind == "file":
        pk = cc.ffprobe_packets(str(clean))
        return [(img.name, img.stat().st_size)], [(int(p["pos"]), int(p["size"])) for p in pk if p.get("pos") not in (None, "N/A")]
    if kind == "segment":
        files = [(f.name, f.stat().st_size) for f in cc.segment_files(img, ext)]
        pk = []
        base = 0
        for name, size in files:
            cf = clean / name
            src = cf if cf.exists() else img / name
            for p in cc.ffprobe_packets(str(src)):
                if p.get("pos") not in (None, "N/A") and int(p["pos"]) + int(p["size"]) <= size:
                    pk.append((base + int(p["pos"]), int(p["size"])))
            base += size
        return files, pk
    if kind == "rawidx":
        idxb = (img / "frames.idx").read_bytes()
        pk = [cc.IDX_REC.unpack_from(idxb, k * 32)[1:3] for k in range(len(idxb) // 32)]
        return [("frames.mjpeg", (img / "frames.mjpeg").stat().st_size)], [(int(o), int(s)) for o, s in pk]
    if kind == "folder":
        files = [(f.name, f.stat().st_size) for f in cc.folder_files(img)]
        pk = []
        base = 0
        for name, size in files:
            pk.append((base, size))
            base += size
        return files, pk
    raise ValueError(kind)


def make_trunc(img: Path, dst: Path, c: str, files, offset: int):
    fmt, ext, opts, kind = cc.spec(c)
    cc.rm(dst)
    if kind == "file":
        with open(img, "rb") as fi, open(dst, "wb") as fo:
            left = offset
            while left > 0:
                b = fi.read(min(left, 1 << 22))
                if not b:
                    break
                fo.write(b)
                left -= len(b)
        return
    dst.mkdir(parents=True)
    if kind == "rawidx":
        data = (img / "frames.mjpeg").read_bytes()[:offset]
        (dst / "frames.mjpeg").write_bytes(data)
        idxb = (img / "frames.idx").read_bytes()
        keep = 0
        for k in range(len(idxb) // 32):
            _, o, s, _, _ = cc.IDX_REC.unpack_from(idxb, k * 32)
            if o + s <= offset:
                keep = k + 1
        (dst / "frames.idx").write_bytes(idxb[:keep * 32])
        return
    pos = 0
    for name, size in files:
        if pos >= offset:
            break
        n = min(size, offset - pos)
        if n == size:
            shutil.copyfile(img / name, dst / name)
        else:
            (dst / name).write_bytes((img / name).read_bytes()[:n])
        pos += size
    if (img / "list.csv").exists():
        shutil.copyfile(img / "list.csv", dst / "list.csv")


def do_variant(args):
    p, c, n = args
    media = cc.MEDIA / "kill"
    img = cc.out_path(media, p, c, f"drained{n}")
    clean = cc.out_path(media, p, c, "clean")
    vid = cc.variant_id(p, c)
    if not img.exists() or not clean.exists():
        return {"payload": p, "container": c, "skipped": "no drained/clean recording"}
    files, pk = layout(img, clean, c)
    total = sum(s for _, s in files)
    if total < 2:
        return {"payload": p, "container": c, "skipped": f"image is {total} bytes"}
    rng = random.Random(zlib.crc32(vid.encode()))
    offs = set(rng.randrange(1, total) for _ in range(20))
    while len(offs) < 20:
        offs.add(rng.randrange(1, total))
    tgt = {"header64": min(64, total - 1), "end-1": total - 1}
    if pk:
        tgt["mid_first_pkt"] = pk[0][0] + pk[0][1] // 2
        mp = pk[len(pk) // 2]
        tgt["mid_median_pkt"] = mp[0] + mp[1] // 2
    offsets = [(o, "random") for o in sorted(offs)] + [(o, k) for k, o in tgt.items() if 0 < o < total]
    ref = [cc.sha(b) for b in cc.load_jpegs(cc.DEFAULT_SET, n)] if p == "mjpeg" else None
    work = cc.TEMP / "trunc" / vid.replace("+", "_")
    work.mkdir(parents=True, exist_ok=True)
    fmt, ext, opts, kind = cc.spec(c)
    rows = []
    for off, why in offsets:
        dst = work / (f"t.{ext}" if kind == "file" else "t")
        make_trunc(img, dst, c, files, off)
        ideal = sum(1 for (ps, sz) in pk if ps + sz <= off)
        mid = any(ps < off < ps + sz for (ps, sz) in pk)
        rd = cc.read_any(dst, c, ref)
        s = cc.summarize_read(rd)
        rep = None
        if kind == "file" and dst.stat().st_size > 0:
            rdst = work / "r.mkv"
            cc.rm(rdst)
            r = cc.remux_ffmpeg(str(dst), str(rdst))
            rep = cc.ffprobe_count(str(rdst))["frames"] if rdst.exists() and rdst.stat().st_size else 0
            cc.rm(rdst)
        elif kind == "rawidx" and (dst / "frames.mjpeg").stat().st_size > 0:
            rdst = work / "r.mkv"
            cc.rm(rdst)
            cc.remux_ffmpeg(str(dst / "frames.mjpeg"), str(rdst), "mjpeg")
            rep = cc.ffprobe_count(str(rdst))["frames"] if rdst.exists() and rdst.stat().st_size else 0
            cc.rm(rdst)
        rows.append({"offset": off, "why": why, "frac": round(off / total, 4), "mid_packet": mid, "ideal": ideal,
                     **s, "repaired_ffprobe": rep})
        cc.rm(dst)
    shutil.rmtree(work, ignore_errors=True)
    return {"payload": p, "container": c, "image_bytes": total, "n_packets_clean": len(pk), "rows": rows}


def agg(v):
    rows = v["rows"]
    out = {"offsets": len(rows), "mid_packet_offsets": sum(r["mid_packet"] for r in rows),
           "ideal_sum": sum(r["ideal"] for r in rows)}
    for k in ("ffprobe", "pyav", "cv2"):
        out[f"{k}_sum"] = sum(min(r[k], r["ideal"] + 1) for r in rows)
        out[f"{k}_total_loss"] = sum(1 for r in rows if r[k] == 0 and r["ideal"] > 0)
        out[f"{k}_max_short"] = max((r["ideal"] - r[k]) for r in rows)
    out["seek_ok_when_ge4"] = f"{sum(1 for r in rows if r['pyav_seek'])}/{sum(1 for r in rows if r['pyav_seek'] is not None)}"
    reps = [r["repaired_ffprobe"] for r in rows if r["repaired_ffprobe"] is not None]
    out["repaired_sum"] = sum(min(x, r["ideal"] + 1) for x, r in zip(reps, [r for r in rows if r["repaired_ffprobe"] is not None])) if reps else None
    if "rawidx" in rows[0]:
        out["rawidx_parser_sum"] = sum(r["rawidx"] for r in rows)
    if "folder_complete" in rows[0]:
        out["folder_complete_sum"] = sum(r["folder_complete"] for r in rows)
    if rows[0].get("byte_exact") is not None or any(r.get("byte_exact") for r in rows):
        out["byte_exact_sum"] = sum((r.get("byte_exact") or 0) for r in rows)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--payloads", default=",".join(cc.PAYLOADS))
    ap.add_argument("--containers", default=None, help="comma list of container ids incl. +fp; default all")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--tag", default="truncation")
    a = ap.parse_args()
    pl = a.payloads.split(",")
    cl = a.containers.split(",") if a.containers else None
    jobs = [(p, c, a.n) for p, c in cc.combos() if p in pl and (cl is None or c in cl)]
    res = {"env": cc.env_versions(), "n": a.n, "variants": []}
    with ProcessPoolExecutor(a.workers) as ex:
        for v in ex.map(do_variant, jobs):
            if "rows" in v:
                v["agg"] = agg(v)
                print(v["payload"], v["container"], json.dumps(v["agg"]), flush=True)
            else:
                print(v["payload"], v["container"], v.get("skipped"), flush=True)
            res["variants"].append(v)
            (cc.RES / f"{a.tag}.json").write_text(json.dumps(res, indent=1, default=str))
    write_md(res, cc.RES / f"{a.tag}.md")


def write_md(res, path):
    L = ["# Truncation (power-loss emulation) results (generated by run_truncation.py)", "",
         f"N={res['n']} frames per recording; source image = `drained:{res['n']}` kill image. Env: {json.dumps(res['env'])}", "",
         "Per variant, summed over all offsets: ideal = frames completely before the cut; ffprobe/PyAV/cv2 = frames each "
         "reader recovered (capped at ideal+1 per offset); total-loss = offsets where a reader got 0 frames although "
         "ideal > 0; max short = worst (ideal - recovered); seek = PyAV mid-file seek ok / attempted; repaired = ffprobe "
         "frames after `ffmpeg -c copy` to .mkv.", "",
         "| payload | container | offsets (mid-pkt) | ideal | ffprobe | PyAV | cv2 | total-loss ffp/PyAV/cv2 | max short ffp/PyAV/cv2 | seek | repaired | notes |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in res["variants"]:
        if "agg" not in v:
            L.append(f"| {v['payload']} | {v['container']} | - | - | - | - | - | - | - | - | - | {v.get('skipped')} |")
            continue
        g = v["agg"]
        notes = []
        if "rawidx_parser_sum" in g:
            notes.append(f"idx+scan parser {g['rawidx_parser_sum']}")
        if "folder_complete_sum" in g:
            notes.append(f"files ending EOI {g['folder_complete_sum']}")
        if "byte_exact_sum" in g:
            notes.append(f"byte-exact {g['byte_exact_sum']}")
        L.append(f"| {v['payload']} | {v['container']} | {g['offsets']} ({g['mid_packet_offsets']}) | {g['ideal_sum']} | "
                 f"{g['ffprobe_sum']} | {g['pyav_sum']} | {g['cv2_sum']} | {g['ffprobe_total_loss']}/{g['pyav_total_loss']}/{g['cv2_total_loss']} | "
                 f"{g['ffprobe_max_short']}/{g['pyav_max_short']}/{g['cv2_max_short']} | {g['seek_ok_when_ge4']} | "
                 f"{'' if g['repaired_sum'] is None else g['repaired_sum']} | {'; '.join(notes)} |")
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
