"""Does the audio track change OpenCV's CAP_PROP_FRAME_COUNT? (MKV has no per-stream frame count, so OpenCV
derives it from the container duration x fps, and the container duration is the longest track.)

For fps in (30, 60, 120) and 20 consecutive frame counts, write small JPEG-in-MKV files with audio covering exactly the
video window (frame_count / fps), in these modes:
  opus_full      - all N samples; the last 20 ms Opus packet is padded (Matroska DiscardPadding)
  opus_trim      - N cut down so pre-skip + N is a whole number of 960-sample packets (audio ends <= 20 ms early)
  opus_end_aligned - N minus the 312-sample pre-skip, so the Opus track ends where the video ends
  flac           - all N samples
Records cv2 CAP_PROP_FRAME_COUNT, frames actually read, and ffprobe's format duration.
Usage: python -I duration_test.py <scratch dir> <out json>
"""
import fractions, json, os, subprocess, sys

import av
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

SR = 48000


def write(path, n_frames, fps, mode, jpg):
    out = av.open(path, "w", format="matroska")
    vs = out.add_stream("mjpeg", rate=fps); vs.width, vs.height = 160, 96; vs.codec_context.pix_fmt = "yuvj420p"
    TB = fractions.Fraction(1, fps); vs.time_base = TB
    n_samples = n_frames * SR // fps
    if mode == "opus_trim":
        n_samples = ((n_samples + 312) // 960) * 960 - 312
    elif mode == "opus_end_aligned":
        n_samples -= 312  # container end = video end (FFmpeg counts the 6.5 ms pre-skip in the track duration)
    a = (np.random.default_rng(1).standard_normal((2, n_samples)) * 0.05).astype(np.float32)
    ast = out.add_stream("libopus" if mode.startswith("opus") else "flac", rate=SR); ast.layout = "stereo"
    if mode == "flac": ast.format = "s16"
    pos = 0
    for k in range(n_frames):
        end = min(n_samples, (k + 1) * SR // fps)
        if end > pos:
            f = av.AudioFrame.from_ndarray(np.ascontiguousarray(a[:, pos:end]), format="fltp", layout="stereo")
            f.sample_rate = SR; f.pts = pos; f.time_base = fractions.Fraction(1, SR)
            for p in ast.encode(f): out.mux(p)
            pos = end
        p = av.Packet(jpg); p.stream = vs; p.time_base = TB; p.pts = p.dts = k; p.is_keyframe = True
        out.mux(p)
    for p in ast.encode(None): out.mux(p)
    out.close()
    return n_samples


def main():
    sp, out_json = sys.argv[1], sys.argv[2]
    d = os.path.join(sp, "dur"); os.makedirs(d, exist_ok=True)
    ok, enc = cv2.imencode(".jpg", cv2.resize(C.make_frame_bgr(1, False), (160, 96)))
    jpg = enc.tobytes()
    res = dict(av=av.__version__, cv2=cv2.__version__, rows=[])
    for fps in (30, 60, 120):
        for n in range(300, 320):
            for mode in ("opus_full", "opus_trim", "opus_end_aligned", "flac"):
                p = os.path.join(d, f"d_{fps}_{n}_{mode}.mkv")
                ns = write(p, n, fps, mode, jpg)
                cap = cv2.VideoCapture(p, cv2.CAP_FFMPEG)
                cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); read = 0
                while cap.read()[0]: read += 1
                cap.release()
                dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                           capture_output=True, text=True).stdout.strip())
                res["rows"].append(dict(fps=fps, frames=n, mode=mode, audio_samples=ns, cv2_count=cnt, cv2_read=read,
                                        format_duration=dur, audio_excess_ms=round((dur - n / fps) * 1000, 2)))
                os.remove(p)
    summ = {}
    for r in res["rows"]:
        k = f"{r['fps']}fps {r['mode']}"
        s = summ.setdefault(k, dict(files=0, count_ok=0, read_ok=0, max_excess_ms=-1e9, min_excess_ms=1e9))
        s["files"] += 1; s["count_ok"] += r["cv2_count"] == r["frames"]; s["read_ok"] += r["cv2_read"] == r["frames"]
        s["max_excess_ms"] = max(s["max_excess_ms"], r["audio_excess_ms"]); s["min_excess_ms"] = min(s["min_excess_ms"], r["audio_excess_ms"])
    res["summary"] = summ
    json.dump(res, open(out_json, "w"), indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
