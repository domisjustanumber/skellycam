"""Make synthetic "camera originals" (inputs only): MJPEG video + AAC stereo audio in MP4, like a camera file.

AAC is used here only because that is what cameras deliver; it is never an output codec in this study.
Usage: python -I gen_source.py <outdir>
Writes cam30_48k.mp4, cam30_44k.mp4, cam60_48k.mp4, cam30_48k_vstart.mp4 (video stream starts 0.1 s after audio)
and sources.json (flash frames, rates, start offsets).
"""
import json, os, sys

import av
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SECONDS = 20


def make(path, fps, sr, v_start_frames=0):
    n_frames = SECONDS * fps
    flashes = C.flash_frames(n_frames)
    v_start_s = v_start_frames / fps
    n_samples = int(round((SECONDS + v_start_s) * sr))
    # burst for frame n sits at the frame's presentation time: v_start + n/fps
    audio = C.make_audio(n_samples, sr, [f + v_start_frames for f in flashes], fps)
    out = av.open(path, "w", format="mp4")
    vs = out.add_stream("mjpeg", rate=fps); vs.width, vs.height = C.W, C.H
    vs.codec_context.pix_fmt = "yuvj420p"
    tb = C.F(1, fps); vs.time_base = tb
    ast = out.add_stream("aac", rate=sr); ast.layout = "stereo"; ast.bit_rate = 192000
    spf = sr // fps  # 1600, 1470, 800: integer for these combinations
    a_pos = 0
    # audio first (priming), then interleave
    for i in range(n_frames + v_start_frames):
        chunk = audio[:, a_pos:a_pos + spf]
        if chunk.shape[1]:
            af = av.AudioFrame.from_ndarray(np.ascontiguousarray(chunk), format="fltp", layout="stereo")
            af.sample_rate = sr; af.pts = a_pos; af.time_base = C.F(1, sr)
            for p in ast.encode(af):
                out.mux(p)
            a_pos += chunk.shape[1]
        k = i - v_start_frames
        if 0 <= k < n_frames:
            ok, jpg = cv2.imencode(".jpg", C.make_frame_bgr(k, k in flashes), [cv2.IMWRITE_JPEG_QUALITY, 90])
            p = av.Packet(jpg.tobytes()); p.stream = vs; p.time_base = tb
            p.pts = p.dts = k + v_start_frames; p.is_keyframe = True
            out.mux(p)
    for p in ast.encode(None):
        out.mux(p)
    out.close()
    return dict(path=os.path.basename(path), fps=fps, sr=sr, frames=n_frames, v_start_s=v_start_s,
                flash_frames=flashes)


def main():
    outdir = sys.argv[1]; os.makedirs(outdir, exist_ok=True)
    srcs = {}
    for name, fps, sr, vsf in [("cam30_48k", 30, 48000, 0), ("cam30_44k", 30, 44100, 0),
                               ("cam60_48k", 60, 48000, 0), ("cam30_48k_vstart", 30, 48000, 3)]:
        srcs[name] = make(os.path.join(outdir, name + ".mp4"), fps, sr, vsf)
    # probe what the demuxer reports
    for name, s in srcs.items():
        with av.open(os.path.join(outdir, s["path"])) as c:
            v, a = c.streams.video[0], c.streams.audio[0]
            s["probe"] = dict(v_start=float(v.start_time * v.time_base) if v.start_time is not None else None,
                              a_start=float(a.start_time * a.time_base) if a.start_time is not None else None,
                              a_codec=a.codec_context.name, a_rate=a.rate, a_channels=a.channels,
                              v_frames=v.frames)
    json.dump(srcs, open(os.path.join(outdir, "sources.json"), "w"), indent=1)
    print(json.dumps({k: v["probe"] for k, v in srcs.items()}, indent=1))


if __name__ == "__main__":
    main()
