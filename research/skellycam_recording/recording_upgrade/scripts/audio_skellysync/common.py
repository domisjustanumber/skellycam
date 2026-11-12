"""Shared helpers for the skellysync audio study (PyAV 19.0.2 / numpy, skellycam-phase1 venv, run with python -I).

Synthetic content, so sync can be checked without a microphone:
  * video frame n carries n as 16 black/white blocks along the top row, and a bright lower half on "flash" frames;
  * audio carries a 4 ms tone burst starting exactly at n/fps for every flash frame n:
    left = 3 kHz burst, right = 1.5 kHz burst with inverted polarity (so channel swap or downmix is visible);
  * flash frames are irregular (gaps 9..25 frames), so a whole-frame A/V error is unambiguous.
"""
import fractions, os, struct, zlib

import numpy as np

W, H = 640, 360
NBITS, BLOCK = 16, 40
BURST_MS = 4.0
F_L, F_R = 3000.0, 1500.0


def flash_frames(n_frames, seed=7):
    rng = np.random.default_rng(seed)
    out, n = [], 5
    while n < n_frames:
        out.append(n)
        n += int(rng.integers(9, 26))
    return out


def make_frame_bgr(n, flash):
    img = np.full((H, W, 3), 40, np.uint8)
    for b in range(NBITS):
        if (n >> b) & 1:
            img[0:BLOCK, b * BLOCK:(b + 1) * BLOCK] = 255
    # light texture so the JPEGs are not trivially small
    yy, xx = np.mgrid[BLOCK:H, 0:W]
    img[BLOCK:H, :, 1] = ((xx + yy + 3 * n) % 64 + 60).astype(np.uint8)
    if flash:
        img[H // 2:H, :, :] = 235
    return img


def read_frame_number(bgr):
    """Inverse of make_frame_bgr for a decoded frame (any size; scaled by width)."""
    h, w = bgr.shape[:2]
    bw = w / NBITS
    bh = BLOCK * h / H
    gray = bgr.mean(axis=2) if bgr.ndim == 3 else bgr
    n = 0
    for b in range(NBITS):
        x0, x1 = int(b * bw + bw * 0.25), int(b * bw + bw * 0.75)
        y0, y1 = int(bh * 0.25), int(bh * 0.75)
        if gray[y0:y1, x0:x1].mean() > 150:
            n |= 1 << b
    return n


def is_flash(bgr):
    h = bgr.shape[0]
    return bgr[int(h * 0.75):, :].mean() > 180


def burst(sr, freq, sign=1.0):
    n = int(round(sr * BURST_MS / 1000))
    t = np.arange(n) / sr
    env = np.sin(np.pi * np.arange(n) / n) ** 0.5  # fast attack, so the onset is sharp
    return (sign * 0.5 * env * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def make_audio(n_samples, sr, flashes, fps, noise_dbfs=-50.0, seed=11):
    """Float32 stereo (2, n): bursts at flash-frame times, plus faint noise."""
    rng = np.random.default_rng(seed)
    a = (rng.standard_normal((2, n_samples)) * 10 ** (noise_dbfs / 20)).astype(np.float32)
    bl, br = burst(sr, F_L, 1.0), burst(sr, F_R, -1.0)
    for f in flashes:
        s = int(round(f * sr / fps))  # exact for 48000/30, 44100/30, 48000/60
        if s + len(bl) <= n_samples:
            a[0, s:s + len(bl)] += bl
            a[1, s:s + len(br)] += br
    return a


def find_bursts(x, sr, expected, window_s=0.15, freq=F_L):
    """Matched-filter search around each expected onset (samples). Returns list of (found, peak_ratio)."""
    tpl = burst(sr, freq)
    out = []
    win = int(window_s * sr)
    for e in expected:
        lo, hi = max(0, int(e) - win), min(len(x), int(e) + win + len(tpl))
        seg = x[lo:hi]
        if len(seg) < len(tpl):
            out.append((None, 0.0)); continue
        c = np.correlate(seg, tpl, mode="valid")
        k = int(np.argmax(np.abs(c)))
        ratio = float(np.abs(c[k]) / (np.median(np.abs(c)) + 1e-9))
        out.append((lo + k, ratio))
    return out


def sync_errors(x, sr, flash_out_frames, fps, freq=F_L):
    """Error (samples, found - expected) for every burst whose expected onset lies inside x."""
    exp = [int(round(f * sr / fps)) for f in flash_out_frames]
    exp = [e for e in exp if 0 <= e < len(x) - int(sr * BURST_MS / 1000)]
    res = find_bursts(x, sr, exp, freq=freq)
    errs = [(r[0] - e) if r[0] is not None else None for r, e in zip(res, exp)]
    strong = [r[1] for r in res]
    ok = [e for e, s in zip(errs, strong) if e is not None and s > 8]
    return dict(n_expected=len(exp), n_found=len(ok),
                err_samples_min=min(ok) if ok else None, err_samples_max=max(ok) if ok else None,
                err_samples_median=float(np.median(ok)) if ok else None,
                err_ms_median=round(float(np.median(ok)) / sr * 1000, 3) if ok else None)


# ---------- Matroska scan of every track (video and audio) ----------
ID_EBML, ID_SEGMENT, ID_CLUSTER, ID_TIMESTAMP = 0x1A45DFA3, 0x18538067, 0x1F43B675, 0xE7
ID_SIMPLEBLOCK, ID_BLOCKGROUP, ID_BLOCK = 0xA3, 0xA0, 0xA1
ID_INFO, ID_SEGMENTUID, ID_TRACKS, ID_TRACKENTRY = 0x1549A966, 0x73A4, 0x1654AE6B, 0xAE
ID_TRACKNUMBER, ID_CODECID, ID_CODECPRIVATE, ID_CODECDELAY, ID_SEEKPREROLL = 0xD7, 0x86, 0x63A2, 0x56AA, 0x56BB
ID_TIMESTAMPSCALE = 0x2AD7B1


def read_vint(b, p, keep_marker=False):
    first = b[p]; n = 1; m = 0x80
    while n <= 8 and not (first & m):
        n += 1; m >>= 1
    v = first if keep_marker else first & (m - 1)
    for i in range(1, n):
        v = (v << 8) | b[p + i]
    unknown = (not keep_marker) and v == (1 << (7 * n)) - 1
    return v, n, unknown


def read_elem(b, p):
    eid, n1, _ = read_vint(b, p, True)
    size, n2, unk = read_vint(b, p + n1)
    return eid, p + n1 + n2, (None if unk else size)


def _uint(b):
    return int.from_bytes(b, "big") if b else 0


def scan_mkv(path):
    """Walk the file reading element headers only (plus Info/Tracks bodies and each block's 4-byte header).

    Returns dict(segment_uid, timestamp_scale, tracks={num: {codec_id, codec_private, codec_delay_ns, seek_preroll_ns}},
                 blocks=[(track, payload_offset, payload_size, abs_ts_ticks, keyframe, laced)]).
    """
    res = dict(segment_uid=None, timestamp_scale=1_000_000, tracks={}, blocks=[])
    size_total = os.path.getsize(path)
    with open(path, "rb") as f:
        def hdr(pos):
            f.seek(pos); h = f.read(16)
            return read_elem(h, 0) if len(h) >= 2 else (None, 0, 0)

        eid, d, s = hdr(0)
        pos = d + s
        eid, d, s = hdr(pos)
        assert eid == ID_SEGMENT
        seg_start = pos + d
        seg_end = seg_start + s if s is not None else size_total
        pos = seg_start
        while pos < seg_end:
            eid, d, s = hdr(pos)
            if eid is None:
                break
            body = pos + d
            if eid == ID_INFO:
                f.seek(body); b = f.read(s); q = 0
                while q < s:
                    e2, d2, s2 = read_elem(b, q)
                    if e2 == ID_SEGMENTUID: res["segment_uid"] = b[d2:d2 + s2].hex()
                    if e2 == ID_TIMESTAMPSCALE: res["timestamp_scale"] = _uint(b[d2:d2 + s2])
                    q = d2 + s2
            elif eid == ID_TRACKS:
                f.seek(body); b = f.read(s); q = 0
                while q < s:
                    e2, d2, s2 = read_elem(b, q)
                    if e2 == ID_TRACKENTRY:
                        t = {}; r = d2
                        while r < d2 + s2:
                            e3, d3, s3 = read_elem(b, r)
                            v = b[d3:d3 + s3]
                            if e3 == ID_TRACKNUMBER: t["num"] = _uint(v)
                            elif e3 == ID_CODECID: t["codec_id"] = v.decode()
                            elif e3 == ID_CODECPRIVATE: t["codec_private"] = v.hex()
                            elif e3 == ID_CODECDELAY: t["codec_delay_ns"] = _uint(v)
                            elif e3 == ID_SEEKPREROLL: t["seek_preroll_ns"] = _uint(v)
                            r = d3 + s3
                        res["tracks"][t["num"]] = t
                    q = d2 + s2
            elif eid == ID_CLUSTER:
                cpos = body
                cend = body + s if s is not None else seg_end
                cts = 0
                while cpos < cend:
                    e2, d2, s2 = hdr(cpos)
                    if e2 is None or e2 == ID_CLUSTER:
                        break
                    if e2 == ID_TIMESTAMP:
                        f.seek(cpos + d2); cts = _uint(f.read(s2))
                    elif e2 == ID_SIMPLEBLOCK:
                        f.seek(cpos + d2); h = f.read(12)
                        tn, n, _ = read_vint(h, 0)
                        rel = struct.unpack(">h", h[n:n + 2])[0]
                        flags = h[n + 2]
                        res["blocks"].append((tn, cpos + d2 + n + 3, s2 - n - 3, cts + rel, bool(flags & 0x80), bool(flags & 0x06)))
                    elif e2 == ID_BLOCKGROUP:
                        g = cpos + d2
                        while g < cpos + d2 + s2:
                            e3, d3, s3 = hdr(g)
                            if e3 == ID_BLOCK:
                                f.seek(g + d3); h = f.read(12)
                                tn, n, _ = read_vint(h, 0)
                                rel = struct.unpack(">h", h[n:n + 2])[0]
                                flags = h[n + 2]
                                res["blocks"].append((tn, g + d3 + n + 3, s3 - n - 3, cts + rel, False, bool(flags & 0x06)))
                            g += d3 + s3
                    cpos += d2 + s2
                pos = cend
                continue
            if s is None:
                break
            pos = body + s
    return res


def crc32(b):
    return zlib.crc32(b) & 0xFFFFFFFF


def F(n, d=1):
    return fractions.Fraction(n, d)


def sync_errors_t(x, sr, times_s, freq=F_L, sign=1.0, window_s=0.15):
    """Like sync_errors, but expected burst onsets are given in seconds. Also reports the burst polarity seen."""
    exp = [int(round(t * sr)) for t in times_s]
    exp = [e for e in exp if 0 <= e < len(x) - int(sr * BURST_MS / 1000)]
    tpl = burst(sr, freq, sign)
    win = int(window_s * sr)
    errs, pol = [], []
    for e in exp:
        lo, hi = max(0, e - win), min(len(x), e + win + len(tpl))
        seg = x[lo:hi]
        c = np.correlate(seg, tpl, mode="valid")
        k = int(np.argmax(np.abs(c)))
        if np.abs(c[k]) / (np.median(np.abs(c)) + 1e-9) > 8:
            errs.append(lo + k - e); pol.append(1 if c[k] > 0 else -1)
    return dict(n_expected=len(exp), n_found=len(errs),
                err_samples_min=min(errs) if errs else None, err_samples_max=max(errs) if errs else None,
                err_samples_median=float(np.median(errs)) if errs else None,
                err_ms_median=round(float(np.median(errs)) / sr * 1000, 3) if errs else None,
                polarity_ok=f"{sum(1 for p in pol if p > 0)}/{len(pol)}")
