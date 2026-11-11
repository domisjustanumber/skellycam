"""GF02 shared code (gap-fill, 2026-11-10): container specs, a recwriter-compatible writer with flush_packets and the
MKV empty-packet variant, and PyAV-side file checks. Functional only: nothing here measures time.

Reuse (imported, not modified):
  - scripts/python_integration/recwriter.py: sidecar format (HEADER_FMT, RECORD_BODY_FMT, read_sidecar), manifest,
    recover(), find_unfinished(). GF02Writer copies RecordingWriter.__init__/write (recwriter.py:67-157) with three
    changes: add_mux_stream(width, height) instead of an encoder stream (as jpeg_passthrough FINDINGS §4.1 and
    verify_method_writer.py:43 does), flush_packets=1 in the muxer options, and an optional empty timestamped packet.
  - scripts/jpeg_passthrough/jp_common.py: corpus loading and real c930e/c922 capture timestamps.
  - movflags exactly as scripts/jpeg_passthrough/verify_method_writer.py:32-33 and jp_io.py:47-48 (FRAG1S / FRAGPF).
  - empty packet exactly as the write_throughput verifier (93366190 scratchpad verify_emptypkt_av19.py, write_mkv):
    av.Packet() with stream set, time_base 1/1e6, pts = dts = frame time in us + 1, muxed with mux_one().
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
import zlib
from fractions import Fraction
from pathlib import Path

RU = Path("C:/Users/Dom/GitHub/freemocap/skellycam/research/skellycam_recording/recording_upgrade")
sys.path.insert(0, str(RU / "scripts/python_integration"))
sys.path.insert(0, str(RU / "scripts/jpeg_passthrough"))
import jp_common as C  # noqa: E402
import recwriter as rw  # noqa: E402

RES = RU / "results/crash_resilience/gapfill"
MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/gapfill/GF02")
TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF02")
VENV_PY = Path("C:/Users/Dom/GitHub/freemocap/skellycam/.venv/Scripts/python.exe")
US = Fraction(1, 1_000_000)

FRAG = "frag_keyframe+empty_moov+default_base_moof"  # verify_method_writer.py:32-33, jp_io.py:47-48
# name -> (format, ext, muxer options, empty packet after each frame)
CONTAINERS = {
    "mkv_fp": ("matroska", "mkv", {"flush_packets": "1"}, False),
    "mkv_fp_empty": ("matroska", "mkv", {"flush_packets": "1"}, True),
    "fmp4pf_fp": ("mp4", "mp4", {"movflags": FRAG, "flush_packets": "1"}, False),
    "fmp4_1s_fp": ("mp4", "mp4", {"movflags": FRAG, "min_frag_duration": "1000000", "flush_packets": "1"}, False),
}
# recover() looks the container up in rw.CONTAINERS (recwriter.py:253); register ours in-process (file untouched).
for _k, (_f, _e, _o, _) in CONTAINERS.items():
    rw.CONTAINERS[_k] = (_f, _e, dict(_o))


def ffmpeg_versions() -> dict:
    import av
    return {"pyav": av.__version__, "ffmpeg": getattr(av, "ffmpeg_version_info", None),
            "libavformat": ".".join(map(str, av.library_versions["libavformat"])), "python": sys.version.split()[0]}


class GF02Writer:
    """recwriter.RecordingWriter with add_mux_stream, flush_packets=1 and the optional MKV empty packet."""

    def __init__(self, stem, width, height, container, pts_mode="real", nominal_fps=30):
        fmt, ext, opts, self.empty = CONTAINERS[container]
        self.stem = Path(stem)
        self.stem.parent.mkdir(parents=True, exist_ok=True)
        self.video_path = self.stem.with_name(self.stem.name + f".{ext}")
        self.bin_path = self.stem.with_name(self.stem.name + ".frames.bin")
        self.manifest_path = self.stem.with_name(self.stem.name + ".recording.json")
        for p in (self.video_path, self.bin_path):
            if p.exists():
                raise FileExistsError(p)
        if pts_mode not in ("real", "index"):
            raise ValueError(pts_mode)
        self.width, self.height, self.pts_mode, self.nominal_fps = width, height, pts_mode, nominal_fps
        tb = US if pts_mode == "real" else Fraction(1, nominal_fps)
        self._manifest = {"state": "recording", "container": container, "video": self.video_path.name,
                          "sidecar": self.bin_path.name, "width": width, "height": height, "codec": "mjpeg",
                          "pid": os.getpid(), "pts_mode": pts_mode, "started_unix_ns": time.time_ns(),
                          "writer": "GF02Writer (recwriter.py copy: add_mux_stream, flush_packets=1, empty packet opt)"}
        rw._atomic_write_json(self.manifest_path, self._manifest)
        import av
        self._av = av
        self._c = av.open(str(self.video_path), "w", format=fmt, options=dict(opts))
        self._s = self._c.add_mux_stream("mjpeg", rate=nominal_fps, width=width, height=height)
        self._s.time_base = tb
        self._c.start_encoding()  # header written; the muxer may replace the time base (MKV -> 1/1000)
        self.tb = self._s.time_base
        self._bin = open(self.bin_path, "wb")
        self._t0_ns = None
        self._last_pts = -1
        self._last_fn = None
        self.count = 0
        self._manifest["time_base"] = f"{self.tb.numerator}/{self.tb.denominator}"
        rw._atomic_write_json(self.manifest_path, self._manifest)

    def _pts(self, timestamp_ns):  # recwriter.py:111-115
        num = (timestamp_ns - self._t0_ns) * self.tb.denominator
        den = self.tb.numerator * 1_000_000_000
        return (2 * num + den) // (2 * den)

    def _pts_index(self, i):  # recwriter.py:117-121
        num = i * self.tb.denominator
        den = self.nominal_fps * self.tb.numerator
        return (2 * num + den) // (2 * den)

    def write(self, jpeg_bytes, frame_number, timestamp_ns):  # recwriter.py:123-157 + empty packet
        av = self._av
        if self._t0_ns is None:
            self._t0_ns = int(timestamp_ns)
            self._bin.write(struct.pack(rw.HEADER_FMT, rw.MAGIC, 1, rw.HEADER_SIZE, self.width, self.height, b"MJPG",
                                        self.tb.numerator, self.tb.denominator, self._t0_ns))
            self._manifest["t0_ns"] = self._t0_ns
            rw._atomic_write_json(self.manifest_path, self._manifest)
        flags = 0
        pts = self._pts_index(self.count) if self.pts_mode == "index" else self._pts(int(timestamp_ns))
        if pts <= self._last_pts:
            pts, flags = self._last_pts + 1, flags | rw.FLAG_PTS_ADJUSTED
        if self._last_fn is not None and frame_number != self._last_fn + 1:
            flags |= rw.FLAG_FRAME_GAP
        pkt = av.Packet(jpeg_bytes)
        pkt.stream = self._s
        pkt.time_base = self.tb
        pkt.pts = pkt.dts = pts
        pkt.is_keyframe = True
        self._c.mux(pkt)
        if self.empty:
            ep = av.Packet()
            ep.stream = self._s
            ep.time_base = US
            ep.pts = ep.dts = int(pts * self.tb * 1_000_000) + 1  # frame time in us + 1 us (WT verifier)
            self._c.mux_one(ep)
        crc = zlib.crc32(jpeg_bytes)
        body = struct.pack(rw.RECORD_BODY_FMT, int(frame_number), int(timestamp_ns), pts, len(jpeg_bytes), crc, flags,
                           self.count, 0)
        self._bin.write(body + struct.pack("<I", zlib.crc32(body)))
        self._bin.flush()
        self.count += 1
        self._last_pts, self._last_fn = pts, frame_number
        return pts

    def close(self):
        self._c.close()
        self._bin.close()
        self._manifest.update(state="closed", frames=self.count, closed_unix_ns=time.time_ns())
        rw._atomic_write_json(self.manifest_path, self._manifest)
        return dict(self._manifest)


# ------------------------------------------------------------------------------------------------ PyAV-side checks
def pyav_check(path: Path, expected: list[bytes]) -> dict:
    """Demux every packet. expected[i] = the JPEG written as frame i. Reports exact prefix, the first non-exact packet
    (size, is_corrupt flag, is it a prefix of the expected JPEG, does it decode), empty-packet count, errors."""
    import av
    out = {"packets": 0, "empty_packets": 0, "exact_prefix": 0, "all_exact": False, "first_non_exact": None,
           "demux_error": None}
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            out["time_base"] = str(st.time_base)
            out["stream_frames_hdr"] = st.frames
            prefix_open = True
            i = 0
            try:
                for pk in c.demux(st):
                    if pk.size == 0:
                        if pk.dts is not None:
                            out["empty_packets"] += 1
                        continue
                    b = bytes(pk)
                    exp = expected[i] if i < len(expected) else None
                    if prefix_open and b == exp:
                        out["exact_prefix"] += 1
                    elif prefix_open:
                        prefix_open = False
                        info = {"index": i, "bytes": len(b), "expected_bytes": len(exp) if exp else None,
                                "is_prefix_of_expected": bool(exp) and exp.startswith(b),
                                "packet_is_corrupt": bool(pk.is_corrupt), "ends_with_eoi": b.endswith(b"\xff\xd9")}
                        try:
                            fr = pk.decode()
                            info["decode"] = f"{len(fr)} frame(s), frame.is_corrupt={[bool(f.is_corrupt) for f in fr]}"
                        except Exception as e:  # noqa: BLE001
                            info["decode"] = f"raised {type(e).__name__}: {e}"[:200]
                        out["first_non_exact"] = info
                    i += 1
            except Exception as e:  # noqa: BLE001
                out["demux_error"] = f"{type(e).__name__}: {e}"[:200]
            out["packets"] = i
    except Exception as e:  # noqa: BLE001
        out["open_error"] = f"{type(e).__name__}: {e}"[:200]
    out["all_exact"] = out["exact_prefix"] == len(expected) and out["packets"] == len(expected)
    return out


def pyav_seek_identity(path: Path, k: int, pts_k: int, expected_k: bytes) -> dict:
    """Seek to frame k's own pts (sidecar value, stream time base), backward keyframe seek, then check that the next
    non-empty packet is byte-identical to the JPEG written as frame k (jpeg_passthrough pyav19_seek_ts_check method)."""
    import av
    r = {"k": k, "target_pts": pts_k}
    try:
        with av.open(str(path)) as c:
            st = c.streams.video[0]
            c.seek(pts_k, stream=st, backward=True, any_frame=False)
            for pk in c.demux(st):
                if pk.size == 0:
                    continue
                r["got_pts"] = pk.pts
                r["match"] = bytes(pk) == expected_k
                break
    except Exception as e:  # noqa: BLE001
        r["error"] = f"{type(e).__name__}: {e}"[:200]
        r["match"] = False
    return r


def ffprobe_count(path: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_packets,nb_frames,time_base,avg_frame_rate:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True)
    out = {"rc": p.returncode, "stderr": p.stderr.strip()[-300:]}
    try:
        j = json.loads(p.stdout)
        s = (j.get("streams") or [{}])[0]
        out.update(nb_read_packets=int(s["nb_read_packets"]) if s.get("nb_read_packets") else None,
                   nb_frames=s.get("nb_frames"), time_base=s.get("time_base"), avg_frame_rate=s.get("avg_frame_rate"),
                   duration=(j.get("format") or {}).get("duration"))
    except Exception as e:  # noqa: BLE001
        out["parse_error"] = repr(e)[:200]
    return out


def ffprobe_sizes(path: Path) -> dict:
    """Per-packet size list (inspection only) -> count of size-0 packets ffprobe lists."""
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    sizes = [int(x) for x in p.stdout.split() if x.strip().isdigit()]
    return {"listed": len(sizes), "zero_size": sum(1 for s in sizes if s == 0)}


def _vint(b, i, strip=True):  # copied from the WT verifier (verify_emptypkt_av19.py)
    first = b[i]
    ln, mask = 1, 0x80
    while ln <= 8 and not (first & mask):
        ln += 1
        mask >>= 1
    v = first & (mask - 1) if strip else first
    for k in range(1, ln):
        v = (v << 8) | b[i + k]
    return v, ln


def ebml_scan(path: Path) -> dict:
    """Count Clusters, SimpleBlocks and size-0 SimpleBlocks on disk (non-FFmpeg parser; WT verifier code)."""
    b = Path(path).read_bytes()
    out = {"clusters": 0, "simpleblocks": 0, "simpleblocks_size0": 0, "blockgroups": 0}
    MASTER = {0x18538067, 0x1F43B675, 0xA0}

    def walk(s, e):
        i = s
        while i < e:
            eid, l1 = _vint(b, i, strip=False)
            size, l2 = _vint(b, i + l1)
            unknown = size == (1 << (7 * l2)) - 1
            ds = i + l1 + l2
            de = e if unknown else min(ds + size, e)
            if eid == 0x1F43B675:
                out["clusters"] += 1
                walk(ds, de)
            elif eid in MASTER:
                if eid == 0xA0:
                    out["blockgroups"] += 1
                walk(ds, de)
            elif eid == 0xA3:
                _, lt = _vint(b, ds)
                out["simpleblocks"] += 1
                out["simpleblocks_size0"] += (size - lt - 3) == 0
            i = de
    walk(0, len(b))
    return out


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str))
