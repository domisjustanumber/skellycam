"""Shared helpers for the skellycam audio study (PyAV 19.0.2, skellycam-phase1 venv, read-only use).

Formats under test, a writer that takes int16 blocks like a PortAudio callback delivers them,
and decoders that count how many samples a (possibly killed) file gives back.
No real audio is ever written by these helpers: callers pass synthetic signals.
"""
import fractions
import os
import subprocess
import json
import time

import av
import numpy as np

SCRATCH = os.environ.get(
    "AUDIO_SCRATCH",
    r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\f535e563-0d11-4407-af32-ec97af3fd139\scratchpad\audio_skellycam",
)
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"

# name -> writer settings. rate is the rate the encoder runs at (the device is assumed opened at it).
FORMATS = {
    # Opus (libopus 1.6.1 inside the PyAV wheel)
    "ogg_opus":        dict(fmt="ogg", ext=".opus", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1"}),
    "ogg_opus_pd20":   dict(fmt="ogg", ext=".opus", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1", "page_duration": "20000"}),
    "ogg_opus_pd100":  dict(fmt="ogg", ext=".opus", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1", "page_duration": "100000"}),
    "ogg_opus_pd60":   dict(fmt="ogg", ext=".opus", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1", "page_duration": "60000"}),
    "mka_opus":        dict(fmt="matroska", ext=".mka", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1"}),
    "mka_opus_ct100":  dict(fmt="matroska", ext=".mka", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1", "cluster_time_limit": "100"}),
    "webm_opus":       dict(fmt="webm", ext=".webm", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1"}),
    "webm_opus_ct100": dict(fmt="webm", ext=".webm", codec="libopus", rate=48000, copts={"b": "64000", "frame_duration": "20", "application": "audio"}, mopts={"flush_packets": "1", "cluster_time_limit": "100"}),
    # FLAC (FFmpeg's native encoder)
    "flac_native":     dict(fmt="flac", ext=".flac", codec="flac", rate=48000, copts={}, mopts={"flush_packets": "1"}),
    "flac_native_fs1024": dict(fmt="flac", ext=".flac", codec="flac", rate=48000, copts={"frame_size": "1024"}, mopts={"flush_packets": "1"}),
    "ogg_flac":        dict(fmt="ogg", ext=".oga", codec="flac", rate=48000, copts={}, mopts={"flush_packets": "1", "page_duration": "100000"}),
    "mka_flac":        dict(fmt="matroska", ext=".mka", codec="flac", rate=48000, copts={}, mopts={"flush_packets": "1"}),
    "mka_flac_ct100":  dict(fmt="matroska", ext=".mka", codec="flac", rate=48000, copts={}, mopts={"flush_packets": "1", "cluster_time_limit": "100"}),
    # Vorbis (FFmpeg's native, experimental encoder; libvorbis is not in the wheel)
    "ogg_vorbis":      dict(fmt="ogg", ext=".ogg", codec="vorbis", rate=48000, ch=2, copts={"strict": "experimental", "b": "96000"}, mopts={"flush_packets": "1", "page_duration": "100000"}),
    # Baseline: what a streamed WAV would do
    "wav_pcm":         dict(fmt="wav", ext=".wav", codec="pcm_s16le", rate=48000, copts={}, mopts={"flush_packets": "1"}),
}


def open_writer(name, path, channels=1, rate=None):
    f = FORMATS[name]
    rate = rate or f["rate"]
    out = av.open(path, "w", format=f["fmt"], options=dict(f["mopts"]))
    layout = "mono" if channels == 1 else "stereo"
    st = out.add_stream(f["codec"], rate=rate, layout=layout)
    copts = dict(f["copts"])
    if "b" in copts:
        st.codec_context.bit_rate = int(copts.pop("b"))
    st.codec_context.options = copts
    st.time_base = fractions.Fraction(1, rate)
    return out, st, rate


class BlockWriter:
    """Encode + mux int16 blocks (n, ch) as they arrive; pts = running sample count."""

    def __init__(self, name, path, channels=1, rate=None):
        self.name = name
        channels = FORMATS[name].get("ch", channels)  # FFmpeg's native Vorbis encoder is stereo-only
        self.out, self.st, self.rate = open_writer(name, path, channels, rate)
        self.channels = channels
        self.layout = "mono" if channels == 1 else "stereo"
        self.samples_in = 0
        self.packets = 0
        self.tb = fractions.Fraction(1, self.rate)

    def write(self, block):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(block.reshape(1, -1)), format="s16", layout=self.layout)
        fr.sample_rate = self.rate
        fr.pts = self.samples_in
        fr.time_base = self.tb
        self.samples_in += block.shape[0]
        for p in self.st.encode(fr):
            self.out.mux(p)
            self.packets += 1

    def close(self):
        for p in self.st.encode(None):
            self.out.mux(p)
            self.packets += 1
        self.out.close()


def synth(n0, n, rate, channels=1, click_every_s=1.0):
    """Deterministic test signal: quiet 440 Hz tone plus a full-scale 1-sample click every click_every_s."""
    t = np.arange(n0, n0 + n)
    x = 0.05 * np.sin(2 * np.pi * 440.0 * t / rate)
    period = int(round(click_every_s * rate))
    clicks = (t % period) == period // 2
    x[clicks] = 0.9
    y = (x * 32767).astype(np.int16)
    return np.repeat(y[:, None], channels, axis=1)


def decode_pyav(path, out_rate=None):
    """Decode every audio sample PyAV can get. Returns samples at the stream rate, errors, packets."""
    res = dict(samples=0, packets=0, error=None, rate=None, first_pts=None, duration_s_header=None, decode_errors=0)
    try:
        with av.open(path) as c:
            st = c.streams.audio[0]
            res["rate"] = st.rate
            res["duration_s_header"] = float(c.duration / 1e6) if c.duration else None
            for pk in c.demux(st):
                if pk.size == 0:
                    continue
                res["packets"] += 1
                if res["first_pts"] is None:
                    res["first_pts"] = pk.pts
                try:
                    for fr in pk.decode():
                        res["samples"] += fr.samples
                except av.error.FFmpegError:
                    res["decode_errors"] += 1
            try:
                for fr in st.codec_context.decode(None):
                    res["samples"] += fr.samples
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"[:300]
    return res


def decode_ffmpeg(path, rate=48000):
    """ffmpeg CLI decode to s16le mono at `rate`; returns sample count and stderr (errors only)."""
    t0 = time.perf_counter()
    p = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(rate), "-"],
                       capture_output=True)
    return dict(samples=len(p.stdout) // 2, rc=p.returncode, stderr=p.stderr.decode(errors="replace")[-400:],
                wall_s=round(time.perf_counter() - t0, 3))


def ffprobe(path):
    p = subprocess.run([FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", path], capture_output=True)
    try:
        j = json.loads(p.stdout or b"{}")
    except Exception:  # noqa: BLE001
        j = {}
    fmt = j.get("format", {})
    st = (j.get("streams") or [{}])[0]
    return dict(rc=p.returncode, stderr=p.stderr.decode(errors="replace")[-300:], format=fmt.get("format_name"),
                duration=fmt.get("duration"), stream_duration=st.get("duration"), codec=st.get("codec_name"),
                rate=st.get("sample_rate"), start_time=st.get("start_time"))


def decode_vlc(path, workdir, rate=48000, timeout=120):
    """VLC 3.0.24 headless: transcode to WAV and count the samples it decoded."""
    dst = os.path.join(workdir, os.path.basename(path) + ".vlc.wav")
    if os.path.exists(dst):
        os.remove(dst)
    sout = f"#transcode{{acodec=s16l,channels=1,samplerate={rate}}}:std{{access=file,mux=wav,dst='{dst}'}}"
    t0 = time.perf_counter()
    try:
        p = subprocess.run([VLC, "-I", "dummy", "--no-repeat", "--no-loop", "--play-and-exit", "--no-video",
                            path, f"--sout={sout}", "vlc://quit"], capture_output=True, timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    res = dict(rc=rc, wall_s=round(time.perf_counter() - t0, 2), samples=None)
    if os.path.exists(dst):
        b = open(dst, "rb").read()
        # find the data chunk; VLC may leave sizes unfixed, so count to EOF
        i = b.find(b"data")
        if i >= 0:
            res["samples"] = (len(b) - (i + 8)) // 2
        os.remove(dst)
    return res


def flac_streaminfo(path):
    """Read STREAMINFO from a native .flac file: total samples, min/max frame size, md5 set?"""
    b = open(path, "rb").read(64)
    if b[:4] != b"fLaC":
        return None
    si = b[8:8 + 34]
    rate = (si[10] << 12) | (si[11] << 4) | (si[12] >> 4)
    total = ((si[13] & 0x0F) << 32) | int.from_bytes(si[14:18], "big")
    return dict(rate=rate, total_samples=total, min_frame=int.from_bytes(si[4:7], "big"),
                max_frame=int.from_bytes(si[7:10], "big"), md5_zero=(si[18:34] == b"\0" * 16))


def ogg_pages(path):
    """Walk Ogg pages and check each CRC. Returns counts and the last granule position."""
    import zlib  # noqa: F401  (Ogg uses its own CRC polynomial; computed below)
    b = open(path, "rb").read()

    def crc_ogg(data):
        c = 0
        for byte in data:
            c ^= byte << 24
            for _ in range(8):
                c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        return c

    p, pages, bad, last_gp, eos, sizes = 0, 0, 0, None, False, []
    while True:
        i = b.find(b"OggS", p)
        if i < 0 or i + 27 > len(b):
            break
        nseg = b[i + 26]
        if i + 27 + nseg > len(b):
            bad += 1
            break
        body = sum(b[i + 27:i + 27 + nseg])
        end = i + 27 + nseg + body
        if end > len(b):
            bad += 1  # torn last page
            break
        page = bytearray(b[i:end])
        want = int.from_bytes(page[22:26], "little")
        page[22:26] = b"\0\0\0\0"
        ok = crc_ogg(bytes(page)) == want if len(page) < 70000 else True
        if not ok:
            bad += 1
        pages += 1
        sizes.append(end - i)
        last_gp = int.from_bytes(b[i + 6:i + 14], "little", signed=True)
        eos = bool(b[i + 5] & 4)
        p = end
    return dict(pages=pages, bad_or_torn=bad, last_granule=last_gp, eos=eos, tail_bytes=len(b) - p,
                median_page_bytes=(sorted(sizes)[len(sizes) // 2] if sizes else None))


def mkv_tail_info(path):
    """Segment size field (unknown or set) and the last Cluster's size field."""
    b = open(path, "rb").read()

    def vint(p, keep=False):
        first = b[p]; n = 1; m = 0x80
        while n <= 8 and not (first & m):
            n += 1; m >>= 1
        v = first if keep else first & (m - 1)
        for k in range(1, n):
            v = (v << 8) | b[p + k]
        unk = (not keep) and v == (1 << (7 * n)) - 1
        return v, n, unk

    try:
        _, n1, _ = vint(0, True); sz, n2, _ = vint(n1); p = n1 + n2 + sz
        _, n1, _ = vint(p, True); ssz, n2, sunk = vint(p + n1)
        q = p + n1 + n2
        clusters, last_cluster_unknown, cues = 0, None, False
        while q + 8 < len(b):
            eid, m1, _ = vint(q, True); csz, m2, cunk = vint(q + m1)
            if eid == 0x1F43B675:
                clusters += 1; last_cluster_unknown = cunk
            if eid == 0x1C53BB6B:
                cues = True
            if cunk:
                break
            q = q + m1 + m2 + csz
        return dict(segment_size_unknown=sunk, segment_size=None if sunk else ssz, clusters=clusters,
                    last_cluster_size_unknown=last_cluster_unknown, cues=cues, file_len=len(b))
    except Exception as e:  # noqa: BLE001
        return dict(error=str(e)[:200])
