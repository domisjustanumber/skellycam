"""Shared helpers for the Opus leg of the audio_single_file desk test (2026-11-15).

Reuses ../asf_common.py (PyAVWriter, CSV writer/parser, ffprobe, ffmpeg, VLC afile, Opus writers are added to its
PYAV table). Opus is lossy, so the index signal of asf_common cannot be checked sample by sample. This module uses a
timing signal instead:
  per channel: uniform hash noise (about -17 dBFS rms, independent per channel) + a click of 29,000 (s16) on both
  channels at sample 24000 + k*48000 (the click train of scripts/audio_skellycam/electron/page.html clicks()).
Timing is measured two ways: click offsets (argmax |x| per 1 s window - expected, as audio_skellycam/align.py) and
a cross-correlation lag of the noise against the source (find_lag / seek_landing). Both are in samples at 48 kHz.
Convention (as audio_skellycam): offset < 0 = the audio comes out early.
"""
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import asf_common as C  # noqa: E402

SCRATCH = os.path.join(C.SCRATCH, "opus")
RESULTS = os.path.normpath(os.path.join(C.RESULTS, "opus"))
RATE, BLOCK, PRESKIP = 48000, 1024, 312
CLICK = 29000

# Opus writers (stereo, D9N1 stereo settings: 256 kbit/s VBR, 20 ms, application audio, complexity 10).
COPTS = {"b": "256000", "frame_duration": "20", "application": "audio", "vbr": "on", "compression_level": "10"}
WRITERS = {
    "ogg_pd20": ("ogg", ".opus", {"flush_packets": "1", "page_duration": "20000"}),
    "ogg_pd1": ("ogg", ".opus", {"flush_packets": "1", "page_duration": "1"}),
    "mka_ct1": ("matroska", ".mka", {"flush_packets": "1", "cluster_time_limit": "1"}),
    "webm_ct1": ("webm", ".webm", {"flush_packets": "1", "cluster_time_limit": "1"}),
    "mp4_fragpkt": ("mp4", ".m4a", {"flush_packets": "1", "movflags": "empty_moov+default_base_moof+frag_every_frame"}),
    "mp4_frag100": ("mp4", ".m4a", {"flush_packets": "1", "movflags": "empty_moov+default_base_moof", "frag_duration": "100000"}),
    "mp4_plain": ("mp4", ".m4a", {"flush_packets": "1"}),
}
for _k, (_fmt, _ext, _mo) in WRITERS.items():
    C.PYAV[_k] = (_fmt, _ext, "libopus", dict(COPTS), dict(_mo))
    C.EXT[_k] = _ext


_NOISE = []
NOISE_LEN = 1 << 22  # 87 s; longer than any test file


def sig(n0, n):
    """Timing signal for samples [n0, n0+n), shape (n, 2) int16.
    Noise from a seeded PRNG table (a multiplicative hash of the index is quasi-periodic at Fibonacci lags,
    measured: lag 17,711 correlates 0.999, which breaks the seek locator)."""
    if not _NOISE:
        _NOISE.append(np.random.default_rng(20261115).integers(-8192, 8192, (NOISE_LEN, 2), dtype=np.int16))
    idx = np.arange(n0, n0 + n, dtype=np.int64)
    x = _NOISE[0][idx % NOISE_LEN].copy()
    x[idx % RATE == RATE // 2] = CLICK
    return x


def src_f(n):
    """Left channel of the source as float (-1..1), samples [0, n)."""
    return sig(0, n)[:, 0].astype(np.float64) / 32768


def to_f(x):
    """(n,) or (n, ch) int16/float -> left channel float."""
    x = np.asarray(x)
    if x.ndim == 2:
        x = x[:, 0]
    return x.astype(np.float64) / 32768 if x.dtype == np.int16 else x.astype(np.float64)


def click_offsets(x, origin=0, n=None):
    """Found - expected click position per 1 s window of x (x[0] = source sample `origin`)."""
    a = np.abs(to_f(x))
    out = []
    k0 = max(0, -(-(origin - RATE // 2) // RATE))
    k = k0
    while n is None or k - k0 < n:
        e = RATE // 2 + k * RATE - origin
        lo, hi = e - RATE // 2, e + RATE // 2
        if lo < 0 or hi > len(a):
            if hi > len(a):
                break
            k += 1
            continue
        out.append(int(lo + np.argmax(a[lo:hi]) - e))
        k += 1
    return out


def find_lag(y, src, lo, hi):
    """d in [lo, hi] maximising correlation of y[i] with src[i + d] (FFT). Returns (d, normalised peak)."""
    y = to_f(y)
    lo = max(lo, 0)
    seg = src[lo:hi + len(y)]
    if len(seg) < len(y):
        return None, 0.0
    m = 1 << int(np.ceil(np.log2(len(seg) + len(y))))
    c = np.fft.irfft(np.fft.rfft(seg, m) * np.conj(np.fft.rfft(y, m)), m)[: len(seg) - len(y) + 1]
    i = int(np.argmax(c))
    den = np.sqrt(np.sum(y * y) * np.sum(seg[i:i + len(y)] ** 2)) or 1.0
    return lo + i, float(c[i] / den)


def corr_profile(y, src, d, blk=240):
    """Per-block correlation of y with src shifted by d."""
    out = []
    for b in range(0, len(y) - blk + 1, blk):
        s0 = b + d
        if s0 < 0 or s0 + blk > len(src):
            out.append(0.0)
            continue
        a, s = y[b:b + blk], src[s0:s0 + blk]
        den = np.sqrt(np.sum(a * a) * np.sum(s * s))
        out.append(float(np.sum(a * s) / den) if den > 0 else 0.0)
    return np.array(out)


def seek_landing(y, src, target, blk=240):
    """y = a player's output that contains a jump to source sample `target`, or starts there.
    lag_post = lag of the content after the jump (from the tail of y: output index o plays source o + lag_post).
    The jump j is where the content before it ends (an earlier lag that stops fitting, change point at 0.6 x the
    signal power, new content or anything else after it), or the first non-silent output sample when y starts at the seek. Opus decoded from a mid-stream
    packet without pre-roll does not match the source for its first ~10 ms (decoder convergence), so j is NOT taken
    from where the new content starts to fit.
      error_samples          = source index of the first non-silent sample after j - target
                               (the ../libvlc_seek.py metric: silence a player inserts after the jump is ignored)
      timeline_error_samples = j + lag_post - target (inserted silence counts: > 0 audio early, < 0 late)
      convergence_samples    = output samples after j (and its silence) before the new content fits the source."""
    y = to_f(y)
    tail = min(12000, len(y) // 3)
    d_post, peak = find_lag(y[-tail:], src, target - 10 * RATE, target + 10 * RATE)
    if d_post is None or peak < 0.3:
        return dict(landed=None, peak=round(peak, 3))
    d_post -= len(y) - tail
    s_t = src[len(y) - tail + d_post:len(y) + d_post]
    g = np.dot(y[-tail:], s_t) / max(1e-12, np.dot(s_t, s_t))
    nz = np.flatnonzero(np.abs(y) > 1e-4)
    first = int(nz[0]) if len(nz) else 0
    h0 = first + 600  # 25 ms window, 12.5 ms in: allows a negative lag, and short content before a jump
    head = y[h0:h0 + 1200]
    d_pre, pk = find_lag(head, src, 0, len(src) - len(head)) if len(head) == 1200 else (None, 0.0)
    d_pre = d_pre - h0 if d_pre is not None and pk > 0.3 else None
    if d_pre is not None and abs(d_pre - d_post) > 48:  # content before the jump
        prof = corr_profile(y[h0:], src, d_pre + h0, 96) > 0.5
        e = 0  # end of the old content: first of 4 blocks in a row that no longer fit (lossy blocks dip alone)
        while e < len(prof) and (prof[e] or not (~prof[e:e + 4]).all()):
            e += 1
        e = h0 + e * 96
        idx = np.arange(max(first, e - 288), min(len(y), e + 384))
        idx = idx[(idx + d_pre >= 0) & (idx + d_pre < len(src))]
        good = y[h0:e - 96]
        thr = 0.6 * (np.mean(good ** 2) if len(good) else np.mean(y[idx] ** 2))
        r_pre = (y[idx] - g * src[idx + d_pre]) ** 2
        ok = (idx + d_post >= 0) & (idx + d_post < len(src))
        r_aft = np.where(ok, np.minimum((y[idx] - g * src[np.clip(idx + d_post, 0, len(src) - 1)]) ** 2, thr), thr)
        cost = np.r_[0, np.cumsum(r_pre)][:-1] + (np.sum(r_aft) - np.r_[0, np.cumsum(r_aft)][:-1])
        j = int(idx[int(np.argmin(cost))])
        while j > first and abs(y[j - 1]) < 1e-4:  # a split inside inserted silence belongs at its start
            j -= 1
    else:
        d_pre, j = None, first
    sil = 0
    while j + sil < len(y) and abs(y[j + sil]) < 1e-4:
        sil += 1
    prof = corr_profile(y, src, d_post, blk) > 0.5
    jb = len(prof)
    while jb > 0 and prof[jb - 1]:
        jb -= 1
    return dict(landed=int(j + sil + d_post), error_samples=int(j + sil + d_post - target),
                timeline_error_samples=int(j + d_post - target), jump_at_output_sample=j, silence_after_jump=sil,
                convergence_samples=max(0, jb * blk - j - sil), lag_post=int(d_post), lag_pre=d_pre,
                peak=round(peak, 3), gain=round(float(g), 3))


def snr_db(y, src, d):
    """Waveform SNR of y against the source at lag d (least-squares gain)."""
    y = to_f(y)
    n = min(len(y), len(src) - d)
    a, s = y[:n], src[d:d + n]
    g = np.dot(a, s) / np.dot(s, s)
    return round(float(10 * np.log10(np.sum((g * s) ** 2) / max(1e-20, np.sum((a - g * s) ** 2)))), 2)


def decode_all(path):
    """PyAV decode (left channel float), header durations, packet count. FFmpeg applies pre-skip/edit lists."""
    import av
    res = dict(error=None)
    chunks = []
    try:
        with av.open(path) as c:
            st = c.streams.audio[0]
            res["duration_s"] = float(c.duration / 1e6) if c.duration else None
            res["stream_duration_s"] = float(st.duration * st.time_base) if st.duration else None
            res["start_time"] = float(st.start_time * st.time_base) if st.start_time is not None else None
            res["initial_padding"] = st.codec_context.initial_padding if hasattr(st.codec_context, "initial_padding") else None
            for fr in c.decode(st):
                a = fr.to_ndarray()
                chunks.append(a[0] if fr.format.is_planar else a.reshape(-1, fr.layout.nb_channels)[:, 0])
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"[:300]
    x = np.concatenate(chunks).astype(np.float64) if chunks else np.zeros(0)
    if x.size and np.abs(x).max() > 2:
        x = x / 32768
    res["samples"] = int(len(x))
    return res, x


def ffmpeg_f(path, extra=()):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, *extra, "-f", "s16le", "-ac", "1", "-ar", "48000", "-"], capture_output=True)
    return np.frombuffer(p.stdout[: len(p.stdout) // 2 * 2], np.int16).astype(np.float64) / 32768, p.returncode


def timing(x, n_src, origin=0):
    """Start offset of a decode that should begin at source sample `origin`: click offsets + correlation lag."""
    if len(x) < RATE:
        return dict(samples=int(len(x)), clicks=None)
    src = src_f(n_src)
    offs = click_offsets(x, origin)
    lag, pk = find_lag(x[RATE // 4: RATE // 4 + RATE // 2], src, max(0, origin - RATE), origin + RATE)
    lag = None if lag is None else lag - RATE // 4 - origin
    return dict(samples=int(len(x)), click_offsets=sorted(set(offs)), click_n=len(offs),
                corr_lag=None if lag is None else -lag, corr_peak=round(pk, 3),
                snr_db=None if lag is None else snr_db(x[RATE // 4:], src, RATE // 4 + origin + lag))
