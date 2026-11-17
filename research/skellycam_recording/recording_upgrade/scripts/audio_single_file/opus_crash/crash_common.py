"""Shared helpers for the crashed-Opus seek + repair desk test (2026-11-16).

Reuses ../opus/opus_common.py (timing signal: seeded noise + click every 1 s at 24000 + k*48000; seek_landing,
find_lag, click_offsets) and ../asf_common.py (CSV writer/parser, VLC afile, ffprobe). Files here are MONO
(left channel of the opus_common signal), D9N1 mono settings (128 kbit/s VBR, 20 ms, application audio,
complexity 10), because the skellycam playback harness (../skellycam_playback/electron/player.js, WcEngine) reads
WAV as mono 16-bit and the playback study used mono.
"""
import fractions
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "opus"))
import opus_common as O  # noqa: E402

C = O.C
SCRATCH = os.path.join(C.SCRATCH, "opus_crash")
RESULTS = os.path.normpath(os.path.join(C.RESULTS, "opus_crash"))
RATE, BLOCK, PRESKIP = 48000, 1024, 312
COPTS = {"b": "128000", "frame_duration": "20", "application": "audio", "vbr": "on", "compression_level": "10"}
WRITERS = {  # name: (format, ext, codec, codec options, muxer options)
    "wav": ("wav", ".wav", "pcm_s16le", {}, {"flush_packets": "1", "rf64": "auto"}),
    "fragpkt": ("mp4", ".m4a", "libopus", COPTS, {"flush_packets": "1", "movflags": "empty_moov+default_base_moof+frag_every_frame"}),
    "frag100": ("mp4", ".m4a", "libopus", COPTS, {"flush_packets": "1", "movflags": "empty_moov+default_base_moof", "frag_duration": "100000"}),
    "mka": ("matroska", ".mka", "libopus", COPTS, {"flush_packets": "1", "cluster_time_limit": "1"}),
}


class MonoWriter:
    """asf_common.PyAVWriter, mono."""

    def __init__(self, name, path):
        import av
        fmt, _, codec, copts, mopts = WRITERS[name]
        self.out = av.open(path, "w", format=fmt, options=dict(mopts))
        self.st = self.out.add_stream(codec, rate=RATE, layout="mono")
        self.st.codec_context.options = dict(copts)
        self.st.time_base = fractions.Fraction(1, RATE)
        self.n = 0

    def write(self, block):
        import av
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(block.reshape(1, -1)), format="s16", layout="mono")
        fr.sample_rate, fr.pts, fr.time_base = RATE, self.n, fractions.Fraction(1, RATE)
        self.n += len(block)
        for p in self.st.encode(fr):
            self.out.mux(p)

    def close(self):
        for p in self.st.encode(None):
            self.out.mux(p)
        self.out.close()


def sig1(n0, n):
    return np.ascontiguousarray(O.sig(n0, n)[:, 0])


_SRC = {}


def src(n):
    """Left-channel source as float64, cached and grown (long files: ~100 M samples)."""
    s = _SRC.get("x")
    if s is None or len(s) < n:
        parts, n0 = [], 0
        while n0 < n:  # chunked: sig() builds int64 index arrays
            k = min(1 << 24, n - n0)
            parts.append(sig1(n0, k).astype(np.float64) / 32768)
            n0 += k
        s = np.concatenate(parts)
        _SRC["x"] = s
    return s


def land(y, target, total):
    """Seek landing of output y that should start at (or jump to) source sample `target`; trailing zeros trimmed.
    Returns seek_landing fields plus nonzero_len (output samples up to the last non-silent one) and clicks
    (click positions found - expected, from y)."""
    y = O.to_f(y)
    nz = np.flatnonzero(np.abs(y) > 1e-4)
    if len(nz) == 0:
        return dict(nonzero_len=0, landed=None)
    y = y[: nz[-1] + 1]
    r = dict(nonzero_len=int(len(y)))
    if len(y) < 2400:
        return r
    E, B = target + 12 * RATE, target - 20 * RATE
    if B <= 4 * RATE:
        r.update(O.seek_landing(y, src(E), target))
        return r
    # The noise repeats every 2^22 samples (87.4 s), so on long files the "content before the jump" search would find
    # false matches. Search a virtual source instead: [target - 20 s, target + 12 s) + 1 s of zeros + file start [0, 3 s).
    # The target window comes first so that, when the content at the target equals the file start (target mod 2^22
    # < 3 s), the tie goes to "no jump" (the lag search takes the first maximum).
    A, Z, W = 3 * RATE, RATE, E - B
    v = np.concatenate([sig1(B, W).astype(np.float64) / 32768, np.zeros(Z), sig1(0, A).astype(np.float64) / 32768])
    q = O.seek_landing(y, v, target - B)
    m = lambda i: i + B if i < W else i - (W + Z)  # noqa: E731  virtual -> source index
    if q.get("landed") is not None:
        q["landed"] = m(q["landed"])
        q["error_samples"] = q["landed"] - target
        q["timeline_error_samples"] = m(q["jump_at_output_sample"] + q["lag_post"]) - target
        q["lag_post"] += B
        q["virtual_source"] = True
    r.update(q)
    return r


# ---------------------------------------------------------------- EBML (Matroska)
def ebml_id(b, p):
    v = b[p]
    n = 1 if v & 0x80 else 2 if v & 0x40 else 3 if v & 0x20 else 4
    return int.from_bytes(b[p:p + n], "big"), n


def ebml_size(b, p):
    v, n = b[p], 1
    while n <= 8 and not v & (0x80 >> (n - 1)):
        n += 1
    val = v & (0xFF >> n)
    for k in range(1, n):
        val = (val << 8) | b[p + k]
    unknown = val == (1 << (7 * n)) - 1
    return val, n, unknown


def ebml_children(b, p, end):
    """[(id_hex, elem_offset, header_len, data_size, unknown)] for elements in b[p:end].
    Stops at a zero byte where an ID should start (zero-filled tail) and at an element that runs past `end`
    (reported with data_size = what is there and unknown=None)."""
    out = []
    while p + 2 <= end and b[p] != 0:
        i, ni = ebml_id(b, p)
        if p + ni >= end or b[p + ni] == 0:
            break
        s, ns, unk = ebml_size(b, p + ni)
        if not unk and p + ni + ns + s > end:
            out.append((f"{i:X}", p, ni + ns, end - p - ni - ns, None))
            break
        out.append((f"{i:X}", p, ni + ns, s, unk))
        if unk:
            break
        p += ni + ns + s
    return out


def complete_end_mka(b):
    """End of the last complete Segment child (after stripping a zero-filled tail): where a torn tail is cut."""
    n = len(b.rstrip(bytes(1)))
    top = ebml_children(b, 0, n)
    seg = top[1]
    kids = ebml_children(b, seg[1] + seg[2], n)
    while kids and kids[-1][4] is None:
        kids.pop()
    return kids[-1][1] + kids[-1][2] + kids[-1][3]


# ---------------------------------------------------------------- ISO BMFF
def boxes(b, start=0, end=None):
    """Top-level boxes of bytes b: [(type, offset, size, complete)]. A torn last box is reported incomplete."""
    end = len(b) if end is None else end
    out, p = [], start
    while p + 8 <= end:
        sz = struct.unpack(">I", b[p:p + 4])[0]
        t = bytes(b[p + 4:p + 8]).decode("latin1")
        if sz == 1 and p + 16 <= end:
            sz = struct.unpack(">Q", b[p + 8:p + 16])[0]
        if sz < 8:
            out.append((t, p, sz, False))
            break
        out.append((t, p, sz, p + sz <= end))
        p += sz
    if p < end and (not out or out[-1][3]):
        out.append(("<tail>", p, end - p, False))
    return out


def child_box(b, p, end, want):
    while p + 8 <= end:
        sz = struct.unpack(">I", b[p:p + 4])[0]
        if bytes(b[p + 4:p + 8]) == want:
            return p, sz
        if sz < 8:
            break
        p += sz
    return None, None


def fmp4_complete_end(b):
    """Byte offset after the last complete moof+mdat pair (plus everything before it), after stripping a
    zero-filled tail (power loss can leave one; a real last packet ending in zero bytes then just loses that
    packet). Also the fragment list [(moof_offset, base_media_decode_time)] of complete pairs."""
    bx = boxes(b, 0, len(bytes(b).rstrip(bytes(1))))
    good, frags, i = 0, [], 0
    while i < len(bx):
        t, off, sz, ok = bx[i]
        if t in ("ftyp", "moov", "free", "skip", "styp", "sidx") and ok:
            good = off + sz
        elif t == "moof" and ok and i + 1 < len(bx) and bx[i + 1][0] == "mdat" and bx[i + 1][3]:
            traf, tsz = child_box(b, off + 8, off + sz, b"traf")
            tfdt, _ = child_box(b, traf + 8, traf + tsz, b"tfdt")
            v = b[tfdt + 8]
            bmdt = struct.unpack(">Q", b[tfdt + 12:tfdt + 20])[0] if v == 1 else struct.unpack(">I", b[tfdt + 12:tfdt + 16])[0]
            frags.append((off, bmdt))
            good = bx[i + 1][1] + bx[i + 1][2]
            i += 1
        else:
            break
        i += 1
    return good, frags


def mfra_bytes(frags, track_id=1):
    """mfra = tfra (v1: 64-bit time and moof offset, 1-byte traf/trun/sample numbers) + mfro."""
    ent = b"".join(struct.pack(">QQBBB", t, o, 1, 1, 1) for o, t in frags)
    tfra_body = struct.pack(">B3xII", 1, track_id, 0) + struct.pack(">I", len(frags)) + ent
    tfra = struct.pack(">I4s", 8 + len(tfra_body), b"tfra") + tfra_body
    size = 8 + len(tfra) + 16
    return struct.pack(">I4s", size, b"mfra") + tfra + struct.pack(">I4sII", 16, b"mfro", 0, size)
