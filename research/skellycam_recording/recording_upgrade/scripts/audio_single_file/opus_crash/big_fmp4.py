# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1", "python-vlc==3.0.21203"]
# ///
"""The 4 GiB question for fragmented MP4 Opus (fragment per packet, mono 128 kbit/s, the D9N1 settings).
  write : a child writes the timing signal UNPACED (1 s blocks; still one fragment per 20 ms packet) until the file
          passes LIMIT, then TerminateProcess. Run 2026-11-16: the muxer slowed as the file grew (3.2 MB/s at 0.2 GB,
          0.53 MB/s at 1.9 GB; per-fragment cost grows with the fragment count), so the process tree was killed at
          1,936,490,798 bytes (~25.8 h of audio, past tfdt = 2^32 at 24.86 h) instead.
  grow  : big_x3.m4a = ftyp+moov + the killed file's complete fragments 3 times, each moof's mfhd sequence number and
          tfdt rewritten so the timeline continues (what the writer would have produced, with repeated packets):
          ~5.8 GB, moofs past 4 GiB
  check : per file (killed, x3): box walk (sizes, moofs past 4 GiB, last tfdt), ffprobe duration, PyAV seek (200 ms
          pre-roll, cut by pts) and VLC --start-time near the end (landing by opus_common.seek_landing against the
          source at the same position in copy 1), mfra append (64-bit moof offsets) + PyAV seek again, remux
          `-c copy -f mp4` time per GB, co64 present, PyAV seek in the remux; packet identity killed vs remux.
          Stopped on 2026-11-16 before it wrote anything (too slow at 4.86 M fragments; see check_aborted in the JSON).
  check_x3 : a lighter check of the 5.8 GB file (not run: every open would parse ~14.6 M moofs; see check_aborted in the JSON)
  scale : open cost against fragment count (prefixes of the killed file, 15 min to 4 h), ffprobe and VLC
  frag1s / check_1s : a > 4 GiB file with 1 s fragments (6 h written, grown x14 to 84 h, 4.48 GB): 64-bit fields, seeks, mfra, remux
Usage: uv run --script .../opus_crash/big_fmp4.py write|grow|check|check_x3|scale|frag1s|check_1s   Output: results/.../opus_crash/big_fmp4.json
"""
import hashlib
import json
import multiprocessing as mp
import os
import struct
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

C, O = K.C, K.O
sys.path.insert(0, os.path.join(K.HERE, ".."))
from kill_matrix import terminate  # noqa: E402

BIG = os.path.join(K.SCRATCH, "big", "fragpkt__big.m4a")
X3 = os.path.join(K.SCRATCH, "big", "fragpkt__big_x3.m4a")
OUT = os.path.join(K.RESULTS, "big_fmp4.json")
LIMIT = 4_350_000_000
GROWTH = [  # (local time, bytes) read off the growing file during the 2026-11-16 run
    ("09:41:30", 167229657), ("09:42:00", 263332549), ("09:52:26", 1254536940), ("09:55:31", 1446741142),
    ("09:56:20", 1495755353), ("10:03:20", 1860848723), ("10:04:20", 1892665827), ("10:05:10", 1936490798)]


def child(acked, pid):
    pid.value = os.getpid()
    w = K.MonoWriter("fragpkt", BIG)
    n = 0
    while True:
        w.write(K.sig1(n, K.RATE))
        n += K.RATE
        acked.value = n


def write():
    os.makedirs(os.path.dirname(BIG), exist_ok=True)
    if os.path.exists(BIG):
        os.remove(BIG)
    acked, pid = mp.Value("q", 0, lock=False), mp.Value("q", 0, lock=False)
    p = mp.Process(target=child, args=(acked, pid)); p.start()
    t0 = time.time()
    while p.is_alive() and (not os.path.exists(BIG) or os.path.getsize(BIG) < LIMIT):
        time.sleep(0.5)
    ok = terminate(pid.value); p.join(30)
    json.dump(dict(write=dict(acked_samples=acked.value, bytes=os.path.getsize(BIG), wall_s=round(time.time() - t0, 1), term_ok=ok)), open(OUT, "w"), indent=1)


def walk(path, want_frags=False):
    """Top-level box walk by seeking. Returns summary, and [(moof_offset, tfdt)] if asked."""
    size = os.path.getsize(path)
    frags, n, past, last, p = [], 0, 0, [], 0
    with open(path, "rb") as f:
        while p + 8 <= size:
            f.seek(p); h = f.read(16)
            s = struct.unpack(">I", h[:4])[0]
            if s == 1:
                s = struct.unpack(">Q", h[8:16])[0]
            if s < 8 or p + s > size:
                last.append([h[4:8].decode("latin1"), p, s, "torn"]); break
            n += 1
            past += p > 0xFFFFFFFF
            if h[4:8] == b"moof":
                m = h + f.read(s - 16)
                i = m.find(b"tfdt")
                t = struct.unpack(">Q", m[i + 8:i + 16])[0] if m[i + 4] == 1 else struct.unpack(">I", m[i + 8:i + 12])[0]
                last_tfdt = (m[i + 4], t)
                if want_frags:
                    frags.append((p, t))
            if size - p < 2048:
                last.append([h[4:8].decode("latin1"), p, s])
            p += s
    return dict(boxes=n, boxes_past_4GiB=int(past), walk_end=p, file=size, last=last[-4:], last_tfdt_version=last_tfdt[0], last_tfdt=last_tfdt[1],
                last_tfdt_over_2_32=last_tfdt[1] > 0xFFFFFFFF), frags


def frag_dur(m):
    """Total sample duration of one moof (bytes m): trun per-sample durations or the tfhd default."""
    i, j = m.find(b"tfhd"), m.find(b"trun")
    hf = int.from_bytes(m[i + 5:i + 8], "big"); q = i + 12 + (8 if hf & 1 else 0) + (4 if hf & 2 else 0)
    ddur = struct.unpack(">I", m[q:q + 4])[0] if hf & 8 else 0
    rf, cnt = int.from_bytes(m[j + 5:j + 8], "big"), struct.unpack(">I", m[j + 8:j + 12])[0]
    if not rf & 0x100:
        return ddur * cnt
    r = j + 12 + (4 if rf & 1 else 0) + (4 if rf & 4 else 0)
    step = 4 * sum(1 for b in (0x100, 0x200, 0x400, 0x800) if rf & b)
    return sum(struct.unpack(">I", m[r + k * step:r + k * step + 4])[0] for k in range(cnt))


def grow(src=None, dst=None, copies=3, key="grow"):
    src, dst = src or BIG, dst or X3
    b = open(src, "rb").read()
    end, frags = K.fmp4_complete_end(b)
    head = frags[0][0]
    body = bytearray(b[head:end])
    lsz = struct.unpack(">I", b[frags[-1][0]:frags[-1][0] + 4])[0]
    last_dur = frag_dur(b[frags[-1][0]:frags[-1][0] + lsz])
    del b
    # per-moof patch positions (relative to body): mfhd sequence number, tfdt value (v1, 64-bit)
    pos = []
    for off, _ in frags:
        o = off - head
        sz = struct.unpack(">I", body[o:o + 4])[0]
        m = body[o:o + sz]
        i, j = m.find(b"mfhd"), m.find(b"tfdt")
        assert m[j + 4] == 1, "tfdt v0"
        pos.append((o + i + 8, o + j + 8))
    seq0 = struct.unpack(">I", body[pos[-1][0]:pos[-1][0] + 4])[0]
    dur = frags[-1][1] + last_dur  # untrimmed timeline length of one copy
    t0 = time.perf_counter()
    with open(dst, "wb") as f:
        f.write(open(src, "rb").read(head))
        for c in range(copies):
            if c:
                for (ps, pt), (_, t) in zip(pos, frags):
                    body[ps:ps + 4] = struct.pack(">I", struct.unpack(">I", body[ps:ps + 4])[0] + seq0)
                    body[pt:pt + 8] = struct.pack(">Q", t + c * dur)
            f.write(body)
    r = json.load(open(OUT)) if os.path.exists(OUT) else {}
    r[key] = dict(copies=copies, fragments_per_copy=len(frags), copy_untrimmed_samples=dur, bytes=os.path.getsize(dst), s=round(time.perf_counter() - t0, 1))
    json.dump(r, open(OUT, "w"), indent=1)
    print(r[key], flush=True)


def land_ref(y, tgt, ref):
    """seek_landing of output y (should start at file sample tgt) against the source window around source sample
    ref (= tgt in copy 1). Returns error_samples relative to ref."""
    base = ref - 12 * K.RATE
    srcw = K.sig1(base, 26 * K.RATE).astype(np.float64) / 32768
    r = O.seek_landing(O.to_f(y), srcw, ref - base)
    if r.get("landed") is not None:
        r["landed"] += base
    return r


def pyav_seek(path, tgt, ref):
    import av
    t0 = time.perf_counter()
    with av.open(path) as c:
        st = c.streams.audio[0]
        t_open = time.perf_counter() - t0
        c.seek(int((tgt - K.RATE // 5) / K.RATE / st.time_base), stream=st)
        chunks, first = [], None
        for fr in c.decode(st):
            if first is None:
                first = int(round(fr.pts * (fr.time_base or st.time_base) * K.RATE))
            chunks.append(fr.to_ndarray()[0])
            if first + sum(map(len, chunks)) > tgt + 2 * K.RATE:
                break
    if first is None or first > tgt:
        return dict(first_pts=first, error="no frames before target")
    x = np.concatenate(chunks).astype(np.float64)
    x = x / 32768 if np.abs(x).max() > 2 else x
    return dict(open_s=round(t_open, 3), seek_decode_s=round(time.perf_counter() - t0, 3), first_pts=first, **land_ref(x[tgt - first:tgt - first + K.RATE], tgt, ref))


def vlc_start(path, tgt, ref):
    vdir = os.path.join(K.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    rc, wall, y = C.vlc_afile(path, os.path.join(vdir, "big.wav"), start_s=tgt / K.RATE, run_s=1.0, timeout=900)
    res = dict(rc=rc, wall_s=wall, samples=0 if y is None else int(len(y)))
    if y is not None and len(y) > 4800:
        res.update(land_ref(y[:, 0].astype(np.float64) / 32768, tgt, ref))
    return res


def packets(path):
    import av
    h, n, t0 = hashlib.sha256(), 0, time.perf_counter()
    with av.open(path) as c:
        for pkt in c.demux(c.streams.audio[0]):
            if pkt.size:
                h.update(bytes(pkt)); n += 1
    return dict(packets=n, sha256=h.hexdigest(), s=round(time.perf_counter() - t0, 1))


def check_one(path, copy_samples, copies):
    r = {}
    gb = os.path.getsize(path) / 1e9
    r["struct"], frags = walk(path, want_frags=True)
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path], capture_output=True, text=True)
    r["ffprobe_duration"] = json.loads(p.stdout or "{}").get("format", {}).get("duration")
    total = frags[-1][1] + 960 - K.PRESKIP
    tg = [3600 * K.RATE + 17, int(24.9 * 3600 * K.RATE) + 5, total - 30 * K.RATE - 123]  # 1 h, just past tfdt 2^32, 30 s before the end
    ref = lambda t: t - (t // copy_samples) * copy_samples if copies > 1 else t  # noqa: E731  same sample in copy 1
    r["targets"] = tg
    r["pyav_seek"] = {str(t): pyav_seek(path, t, ref(t)) for t in tg}
    r["vlc_start_time"] = {str(t): vlc_start(path, t, ref(t)) for t in tg}
    print(path, r["struct"], r["ffprobe_duration"], {k: v.get("error_samples") for k, v in r["pyav_seek"].items()}, {k: v.get("error_samples") for k, v in r["vlc_start_time"].items()}, flush=True)
    # mfra (64-bit tfra) appended, seek again, then removed
    t0 = time.perf_counter()
    mf = K.mfra_bytes(frags)
    size = os.path.getsize(path)
    with open(path, "ab") as f:
        f.write(mf)
    r["mfra"] = dict(bytes=len(mf), s=round(time.perf_counter() - t0, 2), max_moof_offset=frags[-1][0], over_4GiB=frags[-1][0] > 0xFFFFFFFF,
                     pyav_seek={str(t): pyav_seek(path, t, ref(t)) for t in tg[-1:]})
    with open(path, "r+b") as f:
        f.truncate(size)
    rp = path.replace(".m4a", "__remux.m4a")
    t0 = time.perf_counter()
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy", "-f", "mp4", rp], capture_output=True, text=True)
    dt = time.perf_counter() - t0
    with open(rp, "rb") as f:
        f.seek(max(0, os.path.getsize(rp) - (64 << 20))); tail = f.read()
    r["remux"] = dict(rc=p.returncode, stderr=p.stderr[-300:], s=round(dt, 1), s_per_gb=round(dt / gb, 2), bytes=os.path.getsize(rp), co64=b"co64" in tail, stco=b"stco" in tail,
                      pyav_seek={str(t): pyav_seek(rp, t, ref(t)) for t in tg[-1:]})
    return r, rp


def check():
    r = json.load(open(OUT)) if os.path.exists(OUT) else {}
    r["write"] = dict(note="unpaced writer killed (process tree) at 10:05 local; see GROWTH", growth_bytes=GROWTH)
    r["killed"], rp = check_one(BIG, None, 1)
    r["killed"]["remux"]["packets_killed"] = packets(BIG)
    r["killed"]["remux"]["packets_remux"] = packets(rp)
    r["killed"]["remux"]["packets_identical"] = r["killed"]["remux"]["packets_killed"]["sha256"] == r["killed"]["remux"]["packets_remux"]["sha256"]
    os.remove(rp)
    json.dump(r, open(OUT, "w"), indent=1)
    if os.path.exists(X3):
        r["x3"], rp = check_one(X3, r["grow"]["copy_untrimmed_samples"], 3)
        os.remove(rp)
    json.dump(r, open(OUT, "w"), indent=1)
    print(json.dumps(r)[:4000])


def check_x3():
    """Lighter check of the 5.8 GB file (the full check_one would take hours: every open parses ~14.6 M moofs):
    box walk, ffprobe duration and wall time, PyAV seek 30 s before the end (copy 3, moofs past 4 GiB) without and
    with an appended mfra (64-bit moof offsets)."""
    r = json.load(open(OUT))
    copy = r["grow"]["copy_untrimmed_samples"]
    x = {}
    t0 = time.perf_counter(); x["struct"], frags = walk(X3, want_frags=True); x["walk_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", X3], capture_output=True, text=True)
    x["ffprobe_duration"] = json.loads(p.stdout or "{}").get("format", {}).get("duration"); x["ffprobe_s"] = round(time.perf_counter() - t0, 1)
    total = frags[-1][1] + 960 - K.PRESKIP
    t = total - 30 * K.RATE - 123
    ref = (t + K.PRESKIP) % copy - K.PRESKIP  # same sample in copy 1
    x.update(target=t, expected_duration_s=round(total / K.RATE, 3), moofs_past_4GiB=sum(1 for o, _ in frags if o > 0xFFFFFFFF))
    x["pyav_seek"] = pyav_seek(X3, t, ref)
    size = os.path.getsize(X3)
    mf = K.mfra_bytes(frags)
    with open(X3, "ab") as f:
        f.write(mf)
    x["mfra"] = dict(bytes=len(mf), max_moof_offset=frags[-1][0], pyav_seek=pyav_seek(X3, t, ref))
    with open(X3, "r+b") as f:
        f.truncate(size)
    r["x3"] = x
    json.dump(r, open(OUT, "w"), indent=1)
    print(json.dumps(x)[:2000])


def vlc_open_s(path, limit=300):
    """Seconds until libvlc reports Playing (dummy audio output), or None after `limit`."""
    import vlc
    inst = vlc.Instance("--aout=dummy", "--no-video", "--quiet")
    pl = inst.media_player_new(); pl.set_media(inst.media_new_path(os.path.normpath(path)))
    t0 = time.time(); pl.play()
    while pl.get_state() != vlc.State.Playing and time.time() - t0 < limit:
        time.sleep(0.01)
    s = time.time() - t0 if pl.get_state() == vlc.State.Playing else None
    pl.stop(); pl.release(); inst.release()
    return None if s is None else round(s, 2)


def scale():
    """Open cost against fragment count: prefixes of the killed 25.8 h per-packet file cut at a fragment boundary
    (= a file killed after that many packets). ffprobe wall time and VLC open time, one at a time."""
    want = [45_000, 90_000, 180_000, 360_000, 720_000]
    ends, n, p = {}, 0, 0
    with open(BIG, "rb") as f:
        while len(ends) < len(want):
            f.seek(p); h = f.read(8)
            s = struct.unpack(">I", h[:4])[0]
            if h[4:8] == b"mdat":
                n += 1
                if n in want:
                    ends[n] = p + s
            p += s
    r = json.load(open(OUT)) if os.path.exists(OUT) else {}
    r["scale"] = []
    tmp = os.path.join(K.SCRATCH, "big", "prefix.m4a")
    for n in want:
        with open(BIG, "rb") as f, open(tmp, "wb") as g:
            left = ends[n]
            while left:
                b = f.read(min(left, 64 << 20)); g.write(b); left -= len(b)
        t0 = time.perf_counter()
        try:
            subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", tmp], capture_output=True, timeout=900)
            fp = round(time.perf_counter() - t0, 2)
        except subprocess.TimeoutExpired:
            fp = "timeout 900 s"
        e = dict(fragments=n, hours=round(n * 0.02 / 3600, 2), bytes=ends[n], ffprobe_s=fp, vlc_open_s=vlc_open_s(tmp))
        r["scale"].append(e)
        json.dump(r, open(OUT, "w"), indent=1)
        print(e, flush=True)
        if isinstance(fp, str) or fp > 300:
            break
    os.remove(tmp)


BIG1S = os.path.join(K.SCRATCH, "big", "frag1s.m4a")
BIG1S_X = os.path.join(K.SCRATCH, "big", "frag1s_x14.m4a")


def frag1s():
    """A > 4 GiB fMP4 with 1 s fragments (how the 64-bit fields behave without the fragment-count cost): write 6 h
    unpaced with frag_duration = 1 s and close cleanly, then grow x14 (84 h, ~4.5 GB) with tfdt/mfhd rewritten."""
    K.WRITERS["frag1s"] = ("mp4", ".m4a", "libopus", K.COPTS, {"flush_packets": "1", "movflags": "empty_moov+default_base_moof", "frag_duration": "1000000"})
    t0 = time.perf_counter()
    w = K.MonoWriter("frag1s", BIG1S)
    for k in range(6 * 3600):
        w.write(K.sig1(k * K.RATE, K.RATE))
    w.close()
    r = json.load(open(OUT)) if os.path.exists(OUT) else {}
    r["frag1s_write"] = dict(hours=6, bytes=os.path.getsize(BIG1S), s=round(time.perf_counter() - t0, 1))
    json.dump(r, open(OUT, "w"), indent=1)
    grow(BIG1S, BIG1S_X, 14, "frag1s_grow")


def check_1s():
    r = json.load(open(OUT))
    copy = r["frag1s_grow"]["copy_untrimmed_samples"]
    x = {}
    x["struct"], frags = walk(BIG1S_X, want_frags=True)
    x["moofs_past_4GiB"] = sum(1 for o, _ in frags if o > 0xFFFFFFFF)
    t0 = time.perf_counter()
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", BIG1S_X], capture_output=True, text=True)
    x["ffprobe_duration"] = json.loads(p.stdout or "{}").get("format", {}).get("duration"); x["ffprobe_s"] = round(time.perf_counter() - t0, 2)
    t = int(float(x["ffprobe_duration"]) * K.RATE) - 30 * K.RATE - 123 - K.PRESKIP
    ref = (t + K.PRESKIP) % copy - K.PRESKIP
    x.update(target=t, target_h=round(t / K.RATE / 3600, 2), ref_in_copy1=ref)
    x["pyav_seek"] = pyav_seek(BIG1S_X, t, ref)
    x["vlc_start_time"] = vlc_start(BIG1S_X, t, ref)
    x["vlc_open_s"] = vlc_open_s(BIG1S_X)
    size = os.path.getsize(BIG1S_X)
    mf = K.mfra_bytes(frags)
    with open(BIG1S_X, "ab") as f:
        f.write(mf)
    x["mfra"] = dict(bytes=len(mf), max_moof_offset=frags[-1][0], pyav_seek=pyav_seek(BIG1S_X, t, ref))
    with open(BIG1S_X, "r+b") as f:
        f.truncate(size)
    rp = BIG1S_X.replace(".m4a", "__remux.m4a")
    t0 = time.perf_counter()
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", BIG1S_X, "-c", "copy", "-f", "mp4", rp], capture_output=True, text=True)
    dt = time.perf_counter() - t0
    with open(rp, "rb") as f:
        f.seek(max(0, os.path.getsize(rp) - (64 << 20))); tail = f.read()
    x["remux"] = dict(rc=p.returncode, stderr=p.stderr[-300:], s=round(dt, 1), s_per_gb=round(dt / (size / 1e9), 2), bytes=os.path.getsize(rp),
                      co64=b"co64" in tail, stco=b"stco" in tail, pyav_seek=pyav_seek(rp, t, ref))
    os.remove(rp)
    r["frag1s_x14"] = x
    json.dump(r, open(OUT, "w"), indent=1)
    print(json.dumps(x)[:3000])


if __name__ == "__main__":
    {"write": write, "grow": grow, "check": check, "check_x3": check_x3, "scale": scale, "frag1s": frag1s, "check_1s": check_1s}[sys.argv[1]]()
