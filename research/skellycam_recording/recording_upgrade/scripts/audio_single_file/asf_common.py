"""Shared helpers: one standard audio file + one CSV timing sidecar (audio_single_file desk test, 2026-11-15).

Synthetic signal only (no microphone). Stereo int16 at 48 kHz:
  L = low 16 bits of the absolute sample index n (so every decoded sample says where it came from),
  R = a hash of n (noise, so FLAC frames have realistic sizes and a stale/duplicated block is caught).
`locate()` turns any decoded run back into its first sample index and checks it sample by sample.

Writers take (1024, 2) int16 blocks as a PortAudio callback delivers them and write them to disk at once.
Imported by the uv scripts in this folder (they carry the pinned dependencies).
"""
import fractions
import json
import os
import struct
import subprocess
import time
import wave
import zlib

import av
import numpy as np

SCRATCH = os.path.normpath(os.environ.get(
    "ASF_SCRATCH",
    r"C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file",
))
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results", "audio_single_file")
VLC = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
RATE, CH, BLOCK = 48000, 2, 1024
MUL = np.uint64(0x9E3779B97F4A7C15)


def sig(n0, n):
    """Index signal for samples [n0, n0+n), shape (n, 2) int16."""
    idx = np.arange(n0, n0 + n, dtype=np.uint64)
    left = (idx & np.uint64(0xFFFF)).astype(np.uint16).view(np.int16)
    right = (((idx * MUL) >> np.uint64(50)).astype(np.int32) - 8192).astype(np.int16)
    return np.stack([left, right], axis=1)


def locate(x, approx=0):
    """First sample index of decoded run x (n, 2) int16 and whether the whole run matches sig exactly.
    approx disambiguates the 16-bit wrap of L (pass the expected index, e.g. a seek target)."""
    if len(x) == 0:
        return dict(n0=None, exact=False, matched=0)
    low = int(np.uint16(x[0, 0].view(np.uint16)))
    best = None
    for k in range(-40, 41):
        base = ((approx >> 16) + k) << 16
        n = base + low
        if n < 0:
            continue
        if int(sig(n, 1)[0, 1]) == int(x[0, 1]) and np.array_equal(sig(n, min(64, len(x))), x[:64]):
            if best is None or abs(n - approx) < abs(best - approx):
                best = n
    if best is None:
        return dict(n0=None, exact=False, matched=0)
    ref = sig(best, len(x))
    eq = np.all(ref == x, axis=1)
    bad = np.flatnonzero(~eq)
    return dict(n0=int(best), exact=bool(len(bad) == 0), matched=int(bad[0]) if len(bad) else int(len(x)))


# ---------------------------------------------------------------- writers
PYAV = {
    # name: (container format, extension, codec, codec options, muxer options)
    "flac_pyav": ("flac", ".flac", "flac", {"frame_size": "1024"}, {"flush_packets": "1"}),
    "wav_pyav": ("wav", ".wav", "pcm_s16le", {}, {"flush_packets": "1"}),
    "rf64auto_pyav": ("wav", ".wav", "pcm_s16le", {}, {"flush_packets": "1", "rf64": "auto"}),
    "rf64always_pyav": ("wav", ".wav", "pcm_s16le", {}, {"flush_packets": "1", "rf64": "always"}),
    "mka_flac_pyav": ("matroska", ".mka", "flac", {"frame_size": "1024"}, {"flush_packets": "1", "cluster_time_limit": "1"}),
}
EXT = {k: v[1] for k, v in PYAV.items()}
EXT.update({"wav_stdlib": ".wav", "wav_sf": ".wav", "flac_sf": ".flac"})
FORMATS = list(EXT)


class PyAVWriter:
    def __init__(self, name, path):
        fmt, _, codec, copts, mopts = PYAV[name]
        self.out = av.open(path, "w", format=fmt, options=dict(mopts))
        self.st = self.out.add_stream(codec, rate=RATE, layout="stereo")
        self.st.codec_context.options = dict(copts)
        self.st.time_base = fractions.Fraction(1, RATE)
        self.n = 0

    def write(self, block):
        fr = av.AudioFrame.from_ndarray(np.ascontiguousarray(block.reshape(1, -1)), format="s16", layout="stereo")
        fr.sample_rate, fr.pts, fr.time_base = RATE, self.n, fractions.Fraction(1, RATE)
        self.n += len(block)
        for p in self.st.encode(fr):
            self.out.mux(p)

    def close(self):
        for p in self.st.encode(None):
            self.out.mux(p)
        self.out.close()


class StdlibWavWriter:
    """Python's wave module (what skellycam's recorder uses today, at stop). writeframes() re-patches the
    RIFF/data sizes after every call; the file object is flushed after each block."""

    def __init__(self, name, path):
        self.f = open(path, "wb")
        self.w = wave.open(self.f, "wb")
        self.w.setnchannels(CH); self.w.setsampwidth(2); self.w.setframerate(RATE)

    def write(self, block):
        self.w.writeframes(block.tobytes())
        self.f.flush()

    def close(self):
        self.w.close(); self.f.close()


class SoundfileWriter:
    """libsndfile via soundfile; flush() after each block."""

    def __init__(self, name, path):
        import soundfile as sf
        fmt = "WAV" if name == "wav_sf" else "FLAC"
        self.f = sf.SoundFile(path, "w", samplerate=RATE, channels=CH, subtype="PCM_16", format=fmt)

    def write(self, block):
        self.f.write(block)
        self.f.flush()

    def close(self):
        self.f.close()


def open_writer(name, path):
    if name in PYAV:
        return PyAVWriter(name, path)
    if name == "wav_stdlib":
        return StdlibWavWriter(name, path)
    return SoundfileWriter(name, path)


# ---------------------------------------------------------------- CSV timing sidecar (proposal under test)
CSV_COLUMNS = "block,first_sample,n_samples,host_ns,adc_ns,flags,crc32"


def csv_header(take_uuid, codec, container, extra=None):
    lines = ["# skellycam_audio_timing=0", f"# take_uuid={take_uuid}", f"# sample_rate={RATE}", f"# channels={CH}",
             f"# codec={codec}", f"# container={container}", "# clock=QPC", "# host_ns_origin=take_start",
             "# sample_index_origin=first_sample_in_file"]
    lines += [f"# {k}={v}" for k, v in (extra or {}).items()]
    return "\n".join(lines) + "\n" + CSV_COLUMNS + "\n"


def csv_row(block, first, n, host_ns, adc_ns, flags):
    body = f"{block},{first},{n},{host_ns},{adc_ns},{flags}"
    return f"{body},{zlib.crc32(body.encode()):08x}\n"


def parse_csv(path):
    """Strict reader: '#' lines are header/footer; a data row counts only if it ends in a newline and its crc32
    matches. Stops at the first bad row."""
    meta, rows, bad, torn, footer = {}, [], 0, 0, []
    with open(path, "rb") as f:
        data = f.read()
    lines = data.split(b"\n")
    if lines and lines[-1] != b"":
        torn = len(lines[-1])
    for ln in lines[:-1]:
        s = ln.decode(errors="replace")
        if s.startswith("#"):
            if rows:
                footer.append(s)
            else:
                k, _, v = s[2:].partition("=")
                meta[k] = v
            continue
        if s == CSV_COLUMNS:
            continue
        body, _, crc = s.rpartition(",")
        if f"{zlib.crc32(body.encode()):08x}" != crc:
            bad += 1
            break
        rows.append([int(v) for v in body.split(",")])
    return dict(meta=meta, rows=rows, bad_rows=bad, torn_bytes=torn, footer=footer)


# ---------------------------------------------------------------- readers
def decode_pyav(path):
    """All samples PyAV gets, as (n, 2) int16, plus header duration."""
    res = dict(samples=0, error=None, duration_s=None)
    chunks = []
    try:
        with av.open(path) as c:
            st = c.streams.audio[0]
            res["duration_s"] = float(c.duration / 1e6) if c.duration else None
            res["stream_duration_s"] = float(st.duration * st.time_base) if st.duration else None
            for fr in c.decode(st):
                a = fr.to_ndarray()
                if fr.format.is_planar:
                    a = a.T
                else:
                    a = a.reshape(-1, fr.layout.nb_channels)
                if a.dtype != np.int16:
                    a = np.round(a * 32768).clip(-32768, 32767).astype(np.int16)
                chunks.append(a)
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"[:300]
    x = np.concatenate(chunks) if chunks else np.zeros((0, 2), np.int16)
    res["samples"] = int(len(x))
    return res, x


def ffprobe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], capture_output=True)
    try:
        j = json.loads(p.stdout or b"{}")
    except Exception:  # noqa: BLE001
        j = {}
    fmt, st = j.get("format", {}), (j.get("streams") or [{}])[0]
    return dict(rc=p.returncode, stderr=p.stderr.decode(errors="replace")[-200:], format=fmt.get("format_name"),
                duration=fmt.get("duration"), stream_duration=st.get("duration"))


def ffmpeg_samples(path):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-"], capture_output=True)
    return dict(samples=len(p.stdout) // 4, rc=p.returncode, stderr=p.stderr.decode(errors="replace")[-200:])


def read_wav_out(path):
    """Read a VLC afile WAV (VLC may leave sizes unfixed: count to EOF)."""
    if not os.path.exists(path):
        return None
    b = open(path, "rb").read()
    i = b.find(b"data")
    if i < 0:
        return np.zeros((0, 2), np.int16)
    raw = b[i + 8:]
    raw = raw[: len(raw) // 4 * 4]
    return np.frombuffer(raw, np.int16).reshape(-1, 2)


def vlc_afile(path, dst, start_s=None, run_s=None, timeout=180):
    """VLC playback path (dummy interface, afile audio output, real time). Returns decoded (n, 2) int16."""
    path, dst = os.path.normpath(path), os.path.normpath(dst)  # VLC writes nothing for paths with mixed slashes
    if os.path.exists(dst):
        os.remove(dst)
    args = [VLC, "-I", "dummy", "--dummy-quiet", "--no-video", "--play-and-exit", "--aout=afile",
            f"--audiofile-file={dst}", "--audiofile-wav", "--audiofile-format=s16", "--audiofile-channels=2"]
    if start_s is not None:
        args.append(f"--start-time={start_s:.3f}")
    if run_s is not None:
        args.append(f"--run-time={run_s:.3f}")
    t0 = time.perf_counter()
    try:
        rc = subprocess.run(args + [path, "vlc://quit"], capture_output=True, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    x = read_wav_out(dst)
    if x is not None:
        os.remove(dst)
    return rc, round(time.perf_counter() - t0, 2), x


# ---------------------------------------------------------------- headers and in-place repair
def flac_streaminfo(path):
    b = open(path, "rb").read(42)
    if b[:4] != b"fLaC":
        return None
    si = b[8:42]
    total = ((si[13] & 0x0F) << 32) | int.from_bytes(si[14:18], "big")
    return dict(total_samples=total, md5_zero=si[18:34] == b"\0" * 16)


def riff_info(path):
    """RIFF/RF64 header fields: the 32-bit RIFF size, the data chunk's 32-bit size, ds64 values if present."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        b = f.read(min(size, 1 << 16))
    if b[:4] not in (b"RIFF", b"RF64"):
        return None
    out = dict(magic=b[:4].decode(), riff_size=struct.unpack("<I", b[4:8])[0], file_size=size)
    i = 12
    while i + 8 <= len(b):
        cid, csz = b[i:i + 4], struct.unpack("<I", b[i + 4:i + 8])[0]
        if cid == b"ds64":
            out["ds64_riff"], out["ds64_data"], out["ds64_samples"] = struct.unpack("<QQQ", b[i + 8:i + 32])
        if cid == b"data":
            out["data_size"], out["data_offset"] = csz, i + 8
            break
        out.setdefault("chunks", []).append(f"{cid.decode(errors='replace')}:{csz}")
        i += 8 + csz + (csz & 1)
    return out


def repair_in_place(path):
    """Lossless header fix-up after a kill. FLAC: STREAMINFO total samples = decodable samples (MD5 stays 0 =
    'unknown'). WAV: RIFF and data sizes from the file length (trailing partial sample frame dropped).
    RF64: ds64 sizes and sample count. Only header bytes change. Returns what was written."""
    t0 = time.perf_counter()
    if path.endswith(".flac"):
        n = decode_pyav(path)[0]["samples"]
        with open(path, "r+b") as f:
            f.seek(8 + 13)
            b13 = f.read(1)[0]
            f.seek(8 + 13)
            f.write(bytes([(b13 & 0xF0) | ((n >> 32) & 0x0F)]) + (n & 0xFFFFFFFF).to_bytes(4, "big"))
        return dict(kind="flac_total_samples", value=n, ms=round((time.perf_counter() - t0) * 1e3, 2))
    info = riff_info(path)
    if info is None:
        return None
    data = (info["file_size"] - info["data_offset"]) // 4 * 4
    big = info["data_offset"] + data - 8 > 0xFFFFFFFF
    with open(path, "r+b") as f:
        f.truncate(info["data_offset"] + data)
        head = open(path, "rb").read(info["data_offset"])
        if info["magic"] == "RF64" or info.get("ds64_data") is not None or big:
            # Rebuild the header region in place: RF64, ds64 FIRST (FFmpeg rejects a ds64 after fmt), then the
            # other chunks; an rf64=auto file killed before conversion gives up its 28-byte JUNK for the ds64.
            chunks, i = [], 12
            while i < info["data_offset"] - 8:
                cid, csz = head[i:i + 4], struct.unpack("<I", head[i + 4:i + 8])[0]
                if cid not in (b"JUNK", b"ds64"):
                    chunks.append(head[i:i + 8 + csz + (csz & 1)])
                i += 8 + csz + (csz & 1)
            ds64 = b"ds64" + struct.pack("<IQQQI", 28, info["data_offset"] + data - 8, data, data // 4, 0)
            new = b"RF64" + b"\xff" * 4 + b"WAVE" + ds64 + b"".join(chunks) + b"data" + b"\xff" * 4
            if len(new) != info["data_offset"]:
                raise ValueError("over 4 GiB and no 28-byte JUNK/ds64 room in the header")
            f.seek(0); f.write(new)
        else:
            f.seek(4); f.write(struct.pack("<I", info["data_offset"] + data - 8))
            f.seek(info["data_offset"] - 4); f.write(struct.pack("<I", data))
    return dict(kind=("rf64" if big or info["magic"] == "RF64" else "riff") + "_sizes", data_bytes=data, ms=round((time.perf_counter() - t0) * 1e3, 2))
