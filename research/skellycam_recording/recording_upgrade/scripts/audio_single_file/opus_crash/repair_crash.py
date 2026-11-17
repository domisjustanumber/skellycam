# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Repair options for crashed files, applied to copies (sets/repaired/), each measured for bytes changed, time,
losslessness (decoded samples identical to the killed file's, or to its intact prefix for torn tails) and what a
crash part-way through the repair leaves behind (partial states, checked by PyAV + ffprobe).

fMP4 (fragpkt, frag100, fragpkt_ps0):
  trunc  : truncate the torn tail at the end of the last complete moof+mdat (no-op after a process kill)
  mfra   : trunc + append an mfra (tfra v1, one entry per fragment) + mfro = what FFmpeg appends at a clean close
           (minus the held packet, which is lost)
  remux  : ffmpeg -c copy -f mp4 (plain MP4, moov at the end; .m4a alone picks the ipod muxer, which refuses Opus)
  refrag : ffmpeg -c copy -f mp4 -movflags empty_moov+default_base_moof -frag_duration 1000000 (1 s fragments + mfra)
MKA (in place, the bytes a clean FFmpeg close writes, minus CRC-32 and the DURATION tag):
  dur    : Info Duration into its 11-byte Void placeholder
  dur_seg: dur + Segment size (8 bytes)
  full   : dur_seg + Cues appended (one CuePoint per cluster) + SeekHead written into the leading Void
  remux  : ffmpeg -c copy (Matroska)
WAV: asf_common.repair_in_place (RIFF/data sizes) as the reference.

Usage: uv run --script .../opus_crash/repair_crash.py
Output: results/audio_single_file/opus_crash/repair.json; sets/repaired/ + sets/repaired.files.json for seek_crash.py
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

C, O = K.C, K.O
SETS = os.path.join(K.SCRATCH, "sets")
RDIR = os.path.join(SETS, "repaired")


def ebml_el(eid, data):
    n = 1
    while len(data) >= (1 << (7 * n)) - 1:
        n += 1
    size = ((1 << (7 * n)) | len(data)).to_bytes(n, "big") if n < 8 else b"\x01" + len(data).to_bytes(7, "big")
    return eid.to_bytes((eid.bit_length() + 7) // 8, "big") + size + data


def uint(v):
    return v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big")


def void(total):
    if total >= 9:
        return b"\xec\x01" + (total - 9).to_bytes(7, "big") + bytes(total - 9)
    return bytes([0xEC, 0x80 | (total - 2)]) + bytes(total - 2)


def mka_layout(b):
    top = K.ebml_children(b, 0, len(b))
    seg = top[1]
    data0 = seg[1] + seg[2]
    kids = K.ebml_children(b, data0, len(b))
    return seg, data0, kids


def mka_duration_ms(path):
    import av
    end = 0.0
    with av.open(path) as c:
        st = c.streams.audio[0]
        for p in c.demux(st):
            if p.pts is not None:
                end = max(end, float((p.pts + (p.duration or 0)) * st.time_base))
    return end * 1000


def mka_repair(path, level):
    """In place. Order chosen so every intermediate state is a valid file: Cues are appended while the Segment
    size is still 'unknown' (so they are inside the Segment), then SeekHead, then Duration, Segment size last."""
    b = bytearray(open(path, "rb").read())
    cut = K.complete_end_mka(b)
    if cut < len(b):  # torn tail first (a process kill leaves none)
        with open(path, "r+b") as f:
            f.truncate(cut)
        b = b[:cut]
    seg, data0, kids = mka_layout(b)
    writes = []  # (offset, bytes) in order; offset None = append
    if level == "full":
        cues = b""
        for t, off, h, s, _ in kids:
            if t == "1F43B675":
                ts_id, ts_off, ts_h, ts_s, _ = next(c for c in K.ebml_children(b, off + h, off + h + min(s, 64)) if c[0] == "E7")
                ct = int.from_bytes(b[ts_off + ts_h:ts_off + ts_h + ts_s], "big")
                cues += ebml_el(0xBB, ebml_el(0xB3, uint(ct)) + ebml_el(0xB7, ebml_el(0xF7, b"\x01") + ebml_el(0xF1, uint(off - data0))))
        cues_el = ebml_el(0x1C53BB6B, cues)
        cues_pos = len(b) - data0
        writes.append((None, cues_el))
        pos = {t: off - data0 for t, off, *_ in kids}
        seeks = b"".join(ebml_el(0x4DBB, ebml_el(0x53AB, bytes.fromhex(i)) + ebml_el(0x53AC, uint(pos[i] if i != "1C53BB6B" else cues_pos)))
                         for i in ("1549A966", "1654AE6B", "1254C367", "1C53BB6B") if i in pos or i == "1C53BB6B")
        sh = ebml_el(0x114D9B74, seeks)
        v = kids[0]
        assert v[0] == "EC", kids[0]
        room = v[2] + v[3]
        writes.append((v[1], sh + void(room - len(sh))))
    info = next(k for k in kids if k[0] == "1549A966")
    iv = [c for c in K.ebml_children(b, info[1] + info[2], info[1] + info[2] + info[3]) if c[0] == "EC" and c[2] + c[3] == 11]
    writes.append((iv[-1][1], b"\x44\x89\x88" + struct.pack(">d", mka_duration_ms(path))))
    if level in ("dur_seg", "full"):
        total = len(b) + (len(writes[0][1]) if level == "full" else 0)
        writes.append((seg[1] + 4, b"\x01" + (total - data0).to_bytes(7, "big")))
    return writes


def apply(path, writes, upto=None, partial_last=None):
    """Apply writes in order (upto = how many); partial_last = bytes of the next write that land (crash mid-write)."""
    with open(path, "r+b") as f:
        for k, (off, data) in enumerate(writes):
            if upto is not None and k >= upto:
                if partial_last is not None and k == upto:
                    data = data[:partial_last]
                else:
                    break
            if off is None:
                f.seek(0, 2)
            else:
                f.seek(off)
            f.write(data)
            if upto is not None and k == upto:
                break


def decode(path):
    info, x = O.decode_all(path)
    return info, x


def lossless(x, ref):
    n = min(len(x), len(ref))
    return dict(samples=int(len(x)), ref_samples=int(len(ref)), identical=bool(len(x) == len(ref) and np.array_equal(x, ref)),
                identical_common=bool(np.array_equal(x[:n], ref[:n])))


def quick(path):
    info, x = decode(path)
    pr = C.ffprobe(path)
    return dict(pyav_samples=info["samples"], pyav_error=info["error"], ffprobe_duration=pr["duration"], ffprobe_rc=pr["rc"]), x


def main():
    shutil.rmtree(RDIR, ignore_errors=True); os.makedirs(RDIR)
    crash = json.load(open(os.path.join(SETS, "crash.json")))
    torn = json.load(open(os.path.join(SETS, "torn.json")))
    jobs = [(crash["dir"], f) for f in crash["files"] if f["length"] != "clean"] + [(torn["dir"], f) for f in torn["files"] if f["writer"] != "wav"]
    out, files = dict(results=[]), []
    for sdir, f in jobs:
        src = os.path.join(sdir, f["name"])
        stem, ext = os.path.splitext(f["name"])
        _, x_src = decode(src)
        gb = os.path.getsize(src) / 1e9
        ref = x_src
        if f.get("torn"):  # the reference for a torn tail is the intact prefix
            ref = x_src[: f["vs_intact"]["identical_prefix"]]
        methods = ["trunc", "mfra", "remux", "refrag"] if ext == ".m4a" else ["dur", "dur_seg", "full", "remux"] if ext == ".mka" else ["riff"]
        if f.get("torn"):
            methods = ["trunc", "mfra"] if ext == ".m4a" else ["full"] if ext == ".mka" else []
        for m in methods:
            dst = os.path.join(RDIR, f"{stem}__{m}{ext}")
            r = dict(source=f["name"], method=m, writer=f["writer"], length=f["length"], torn=f.get("torn"), src_bytes=os.path.getsize(src))
            t0 = time.perf_counter()
            if m in ("remux", "refrag"):
                extra = ["-f", "mp4"] if ext == ".m4a" else []
                if m == "refrag":
                    extra += ["-movflags", "empty_moov+default_base_moof", "-frag_duration", "1000000"]
                p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy", *extra, dst], capture_output=True, text=True)
                r.update(rc=p.returncode, stderr=p.stderr[-200:], in_place=False)
            else:
                shutil.copy(src, dst)
                t0 = time.perf_counter()
                if m in ("trunc", "mfra"):
                    b = open(dst, "rb").read()
                    end, frags = K.fmp4_complete_end(b)
                    with open(dst, "r+b") as fh:
                        fh.truncate(end)
                    r.update(truncated_bytes=len(b) - end, fragments=len(frags))
                    if m == "mfra":
                        mf = K.mfra_bytes(frags)
                        with open(dst, "ab") as fh:
                            fh.write(mf)
                        r.update(appended_bytes=len(mf))
                elif m == "riff":
                    r.update(C.repair_in_place(dst))
                else:
                    n0 = os.path.getsize(dst)
                    w = mka_repair(dst, m)
                    apply(dst, w)
                    r.update(truncated_bytes=n0 - os.path.getsize(dst) + sum(len(d) for o, d in w if o is None),
                             writes=[[o, len(d)] for o, d in w], appended_bytes=sum(len(d) for o, d in w if o is None),
                             overwritten_bytes=sum(len(d) for o, d in w if o is not None))
                r["in_place"] = True
            r["s"] = round(time.perf_counter() - t0, 3)
            r["s_per_gb"] = round(r["s"] / gb, 2) if gb else None
            r["dst_bytes"] = os.path.getsize(dst)
            q, x = quick(dst)
            r.update(q)
            r["lossless"] = lossless(x, ref)
            r["lossless_vs_killed"] = lossless(x, x_src)
            out["results"].append(r)
            files.append(dict(name=os.path.basename(dst), writer=f["writer"], length=f["length"], acked=f["acked"], full=False, repair=m, torn=f.get("torn"), source=f["name"]))
            shutil.copy(src + ".csv", dst + ".csv")
            print(f["name"], m, r["s"], r.get("truncated_bytes"), r.get("appended_bytes"), r.get("overwritten_bytes"), r["pyav_samples"], r["ffprobe_duration"], r["lossless"]["identical"], r["lossless_vs_killed"]["identical_common"], flush=True)
    # crash part-way through an in-place repair (short killed files)
    sim = []
    for f in crash["files"]:
        if f["length"] != "short" or f["writer"] not in ("fragpkt", "mka"):
            continue
        src = os.path.join(crash["dir"], f["name"])
        _, x_src = decode(src)
        b = open(src, "rb").read()
        if f["writer"] == "fragpkt":
            end, frags = K.fmp4_complete_end(b)
            writes = [(None, K.mfra_bytes(frags))]
        else:
            tmp = os.path.join(RDIR, "_tmp.mka"); shutil.copy(src, tmp)
            writes = mka_repair(tmp, "full"); os.remove(tmp)
        states = []
        for k in range(len(writes)):
            n = len(writes[k][1])
            for part in sorted({1, 3, 8, n // 2, n - 1}):
                if 0 < part < n:
                    states.append((k, part))
            states.append((k + 1, None))
        for upto, part in states:
            dst = os.path.join(RDIR, "_sim" + os.path.splitext(src)[1])
            shutil.copy(src, dst)
            apply(dst, writes, upto=upto, partial_last=part)
            q, x = quick(dst)
            sim.append(dict(source=f["name"], writes_done=upto, partial_bytes_of_next=part, write_sizes=[len(d) for _, d in writes], **q,
                            lossless_vs_killed=lossless(x, x_src)))
            os.remove(dst)
            print("sim", f["name"], upto, part, q, sim[-1]["lossless_vs_killed"]["identical"], flush=True)
    out["crash_during_repair"] = sim
    import av
    out.update(av=av.__version__, ffmpeg=os.popen("ffmpeg -version").readline().strip())
    json.dump(out, open(os.path.join(K.RESULTS, "repair.json"), "w"), indent=1)
    json.dump(files, open(os.path.join(SETS, "repaired.files.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
