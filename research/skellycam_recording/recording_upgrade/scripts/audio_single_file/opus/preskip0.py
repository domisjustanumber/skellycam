# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Variant: signal pre-skip 0, so every reader also plays the 312 encoder priming samples and (if they all obey it)
every player puts file sample i at i/48000 s, with device sample 0 at file sample 312. Lossless in-place header
patch of copies of the clean Opus files (no re-encode):
  Ogg  : OpusHead pre-skip (2 bytes) + that page's CRC (4 bytes)
  MKA/WebM : CodecPrivate OpusHead pre-skip (2 bytes) + CodecDelay value (0x56AA) set to 0
  MP4  : dOps PreSkip (2 bytes) + elst media_time set to 0
Checks: PyAV, ffmpeg CLI, VLC afile playback start offset; VLC --start-time landing at 5 s. libvlc set_time,
Chromium and Blender pick up <scratch>/opus/preskip0 through libvlc_seek_opus.py / electron_opus.py / blender_opus.py.

Usage: uv run --script .../opus/preskip0.py     Output: results/audio_single_file/opus/preskip0.json
"""
import glob
import json
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402

C = O.C
_T = []


def ogg_crc(b):
    if not _T:
        for i in range(256):
            r = i << 24
            for _ in range(8):
                r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
            _T.append(r & 0xFFFFFFFF)
    c = 0
    for x in b:
        c = ((c << 8) & 0xFFFFFFFF) ^ _T[((c >> 24) ^ x) & 0xFF]
    return c


def patch(path):
    d = bytearray(open(path, "rb").read())
    done = []
    i = d.find(b"OpusHead")
    if i >= 0:
        d[i + 10:i + 12] = b"\0\0"; done.append("OpusHead.pre_skip")
        if path.endswith(".opus"):
            ps = d.rfind(b"OggS", 0, i)
            nseg = d[ps + 26]
            plen = 27 + nseg + sum(d[ps + 27:ps + 27 + nseg])
            d[ps + 22:ps + 26] = b"\0\0\0\0"
            d[ps + 22:ps + 26] = struct.pack("<I", ogg_crc(d[ps:ps + plen])); done.append("ogg_page_crc")
    if path.endswith((".mka", ".webm")):
        j = d.find(b"\x56\xAA", 0, 8192)
        if j >= 0 and d[j + 2] & 0x80:
            n = d[j + 2] & 0x7F
            d[j + 3:j + 3 + n] = bytes(n); done.append(f"CodecDelay({n} bytes)")
    if path.endswith(".m4a"):
        j = d.find(b"dOps")
        if j >= 0:
            d[j + 6:j + 8] = b"\0\0"; done.append("dOps.PreSkip")
        j = d.find(b"elst")
        if j >= 0:
            v, cnt = d[j + 4], struct.unpack(">I", d[j + 8:j + 12])[0]
            for e in range(cnt):
                if v == 1:
                    off = j + 12 + e * 20 + 8; old = struct.unpack(">q", d[off:off + 8])[0]; d[off:off + 8] = struct.pack(">q", 0)
                else:
                    off = j + 12 + e * 12 + 4; old = struct.unpack(">i", d[off:off + 4])[0]; d[off:off + 4] = struct.pack(">i", 0)
                done.append(f"elst.media_time {old}->0")
    open(path, "wb").write(d)
    return done


def main():
    pdir = os.path.join(O.SCRATCH, "preskip0"); os.makedirs(pdir, exist_ok=True)
    vdir = os.path.join(O.SCRATCH, "vlc_out"); os.makedirs(vdir, exist_ok=True)
    res = dict(note="expected if obeyed: click offset +312 in every reader (priming played)", files={})
    for p in sorted(glob.glob(os.path.join(O.SCRATCH, "clean", "*__clean.*"))):
        if not p.endswith((".opus", ".mka", ".webm", ".m4a")):
            continue
        q = os.path.join(pdir, os.path.basename(p).replace("__clean", "__preskip0"))
        shutil.copy(p, q)
        r = dict(patched=patch(q))
        info, x = O.decode_all(q)
        r["pyav"] = dict(O.timing(x, 12 * O.RATE), error=info["error"])
        r["ffmpeg"] = O.timing(O.ffmpeg_f(q)[0], 12 * O.RATE)
        rc, _, y = C.vlc_afile(q, os.path.join(vdir, os.path.basename(q) + ".play.wav"))
        r["vlc_play"] = O.timing(y, 12 * O.RATE) if y is not None else dict(rc=rc)
        rc, _, y = C.vlc_afile(q, os.path.join(vdir, os.path.basename(q) + ".seek.wav"), start_s=5.0, run_s=1.0)
        r["vlc_start_time_5s"] = O.seek_landing(y, O.src_f(12 * O.RATE), 5 * O.RATE) if y is not None and len(y) > 4800 else dict(rc=rc)
        res["files"][os.path.basename(q)] = r
        print(os.path.basename(q), r["patched"], {k: (v.get("click_offsets"), v.get("samples"), v.get("error_samples")) for k, v in r.items() if k != "patched"}, flush=True)
    json.dump(res, open(os.path.join(O.RESULTS, "preskip0.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
