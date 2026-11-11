"""Writer process for the kill / truncation tests. The parent kills it with Popen.kill() (TerminateProcess).

usage: writer_child.py <payload> <container> <out_path> <n_frames> <mode> [set_name]
  mode: clean       write n frames, close the container (trailer/index written), print CLOSED
        idle:K      feed K frames, print IDLE, block (encoder NOT drained, trailer never written) -> parent kills
        drained:K   feed K frames, drain the encoder (flush), print IDLE, block -> parent kills
        busy        write frames forever as fast as possible (corpus looped, pts keep rising) -> parent kills
        rt          like busy but paced at 30 fps (frame i fed at t0 + i/30 s), the shape of a live recording
stdout: one line "M <packets_muxed> <frames_fed>" after every mux call returns, so the parent knows (via a pipe that
survives the kill) exactly what libavformat had accepted before death.
"""
from __future__ import annotations

import os
import sys
import zlib
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def say(s: str):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def block():
    say("IDLE")
    sys.stdin.readline()  # parent never writes; it kills us
    os._exit(9)


def main():
    say(f"PID {os.getpid()}")  # the venv python.exe is a launcher; the parent kills THIS pid directly
    payload, cont, outp, n, mode = sys.argv[1:6]
    set_name = sys.argv[6] if len(sys.argv) > 6 else cc.DEFAULT_SET
    n = int(n)
    kill_after = None
    drain = False
    if mode.startswith("idle:"):
        kill_after = int(mode.split(":")[1])
    elif mode.startswith("drained:"):
        kill_after = int(mode.split(":")[1])
        drain = True
    busy = mode in ("busy", "rt")
    paced = mode == "rt"
    import time
    t_start = [None]

    def pace(i):
        if not paced:
            return
        if t_start[0] is None:
            t_start[0] = time.perf_counter()
        dt = t_start[0] + i / cc.FPS - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
    w, h = cc.corpus_dims(set_name)
    jpegs = cc.load_jpegs(set_name, n)
    fmt, ext, fopts, kind = cc.spec(cont)
    out = Path(outp)
    frames_to_feed = len(jpegs) if not kill_after else kill_after

    # ---------------- custom (non-libavformat) writers
    if kind == "rawidx":
        out.mkdir(parents=True, exist_ok=True)
        fd = open(out / "frames.mjpeg", "wb")
        fi = open(out / "frames.idx", "wb")
        off = 0
        i = 0
        while True:
            pace(i)
            b = jpegs[i % len(jpegs)]
            fd.write(b)
            fd.flush()  # data before its index record
            fi.write(cc.IDX_REC.pack(i, off, len(b), zlib.crc32(b), int(i * 1e9 / cc.FPS)))
            fi.flush()
            off += len(b)
            i += 1
            say(f"M {i} {i}")
            if not busy and i >= frames_to_feed:
                break
        if kill_after:
            block()
        fd.close()
        fi.close()
        say("CLOSED")
        return
    if kind == "folder":
        out.mkdir(parents=True, exist_ok=True)
        i = 0
        while True:
            pace(i)
            with open(out / f"frame_{i:06d}.jpg", "wb") as f:
                f.write(jpegs[i % len(jpegs)])
            i += 1
            say(f"M {i} {i}")
            if not busy and i >= frames_to_feed:
                break
        if kill_after:
            block()
        say("CLOSED")
        return

    # ---------------- libavformat writers
    import av
    from av.video.frame import PictureType
    opts = dict(fopts)
    target = str(out)
    if kind == "segment":
        out.mkdir(parents=True, exist_ok=True)
        opts["segment_list"] = str(out / "list.csv")
        target = str(out / f"seg_%05d.{ext}")
    try:
        c = av.open(target, "w", format=fmt, options=opts)
    except Exception as e:
        say(f"OPENFAIL {type(e).__name__}: {e}")
        sys.exit(3)
    spec = cc.PAYLOADS[payload]
    try:
        if spec is None:
            st = c.add_stream("mjpeg", rate=cc.FPS)
            st.width, st.height = w, h
            st.pix_fmt = "yuvj422p"
            tb = Fraction(1, 1000)
        else:
            st = c.add_stream(spec["codec"], rate=cc.FPS)
            st.width, st.height = w, h
            st.pix_fmt = spec["pix_fmt"]
            st.codec_context.gop_size = spec["gop"]
            st.codec_context.time_base = Fraction(1, cc.FPS)
            st.options = dict(spec["options"])
            if spec["codec"] == "h264_nvenc":
                st.options["g"] = str(spec["gop"])
            dec = av.CodecContext.create("mjpeg", "r")
            frames = []
            for b in jpegs:
                for fr in dec.decode(av.Packet(b)):
                    f2 = fr.reformat(format=spec["pix_fmt"])
                    # decoded JPEGs carry pict_type=I, which libsvtav1 honours as a forced key frame (every frame
                    # became a key frame in the first smoke test); clear it so the encoder's GOP applies.
                    f2.pict_type = PictureType.NONE
                    frames.append(f2)
    except Exception as e:
        say(f"STREAMFAIL {type(e).__name__}: {e}")
        sys.exit(3)

    muxed = 0
    fed = 0

    def mux_pkts(pkts):
        nonlocal muxed
        for p in pkts:
            c.mux(p)
            muxed += 1
            say(f"M {muxed} {fed}")

    try:
        i = 0
        while True:
            pace(i)
            if spec is None:
                b = jpegs[i % len(jpegs)]
                pkt = av.Packet(b)
                pkt.stream = st
                pkt.time_base = tb
                pkt.pts = pkt.dts = round(i * 1000 / cc.FPS)
                pkt.is_keyframe = True
                fed += 1
                c.mux(pkt)
                muxed += 1
                say(f"M {muxed} {fed}")
            else:
                fr = frames[i % len(frames)]
                fr.pts = i
                fr.time_base = Fraction(1, cc.FPS)
                fed += 1
                mux_pkts(st.encode(fr))
            i += 1
            if not busy and i >= frames_to_feed:
                break
        if kill_after:
            if drain and spec is not None:
                mux_pkts(st.encode(None))
            block()
        if spec is not None:
            mux_pkts(st.encode(None))
        c.close()
    except Exception as e:
        say(f"MUXFAIL {type(e).__name__}: {e}")
        sys.exit(4)
    say("CLOSED")


if __name__ == "__main__":
    main()
