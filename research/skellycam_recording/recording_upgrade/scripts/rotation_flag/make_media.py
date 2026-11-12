"""Make test MKV/MP4 files for the rotation-flag desk test.

Frames: grey background, solid colour block per corner (TL red, TR green, BL blue, BR yellow),
white up-arrow in the centre, frame number as text. Encoded once as baseline JPEGs (cv2.imencode),
then muxed unchanged as MJPEG packets by PyAV (recording-style: index PTS, flush_packets=1).

Files (<out>/<WxH>/):
  A.mkv          PyAV, no rotation
  B<deg>.mkv     PyAV, VideoStream.set_display_rotation(deg) before start_encoding() (deg = 90, 180, 270)
  Bm<deg>.mkv    PyAV, VideoStream.set_display_matrix(<av_display_rotation_set-style matrix>) (deg = 90) [cross-check]
  C<deg>.mkv     ffmpeg -display_rotation <deg> -i A.mkv -c copy   (FFmpeg CLI, MKV)
  D<deg>.mp4     ffmpeg -display_rotation <deg> -i A.mkv -c copy   (FFmpeg CLI, MP4 control)
  T90.mkv        ffmpeg -c copy -metadata:s:v:0 rotate=90   (a `rotate` tag, no display matrix)
  H.mkv, H90.mkv, H90.mp4   H.264 controls (libx264), rotation flag added with -display_rotation 90 -c copy
  jpeg/NNN.jpg   the source JPEGs
Usage: python -I make_media.py <out_dir>
"""
import json, math, os, subprocess, sys
from fractions import Fraction
import av, cv2, numpy as np

N, FPS = 30, 30
SIZES = [(1280, 720), (1920, 1080)]
DEGS = [90, 180, 270]


def frame(w, h, i):
    img = np.full((h, w, 3), 128, np.uint8)
    b = h // 4
    img[:b, :b] = (0, 0, 255)            # TL red (BGR)
    img[:b, w - b:] = (0, 255, 0)        # TR green
    img[h - b:, :b] = (255, 0, 0)        # BL blue
    img[h - b:, w - b:] = (0, 255, 255)  # BR yellow
    cx, cy, s = w // 2, h // 2, h // 3   # up arrow
    pts = np.array([[cx, cy - s], [cx + s // 2, cy], [cx + s // 5, cy], [cx + s // 5, cy + s],
                    [cx - s // 5, cy + s], [cx - s // 5, cy], [cx - s // 2, cy]], np.int32)
    cv2.fillPoly(img, [pts], (255, 255, 255))
    cv2.putText(img, f"{i:03d} UP", (b + 20, b // 2), cv2.FONT_HERSHEY_SIMPLEX, h / 400, (0, 0, 0), 3)
    return img


def rot_matrix_cw_set(deg_cw):
    """av_display_rotation_set(m, angle) for angle = deg_cw, in 16.16 / 2.30 fixed point (FFmpeg layout)."""
    r = math.radians(-deg_cw)  # av_display_rotation_set: radians = -angle * M_PI / 180
    c, s = math.cos(r), math.sin(r)
    f = lambda x: int(round(x * (1 << 16)))
    return [f(c), f(-s), 0, f(s), f(c), 0, 0, 0, 1 << 30]


def write_pyav(path, jpegs, w, h, rot=None, matrix=None):
    with av.open(path, "w", format="matroska", options={"flush_packets": "1"}) as c:
        s = c.add_stream("mjpeg", rate=FPS)
        s.width, s.height, s.pix_fmt = w, h, "yuvj420p"
        s.time_base = Fraction(1, FPS)
        if rot is not None:
            s.set_display_rotation(rot)
        if matrix is not None:
            s.set_display_matrix(matrix)
        c.start_encoding()
        tb = s.time_base
        for i, jb in enumerate(jpegs):
            p = av.Packet(jb)
            p.stream = s
            p.time_base = tb
            p.pts = p.dts = int(round(Fraction(i, FPS) / tb))
            p.duration = int(round(Fraction(1, FPS) / tb))
            p.is_keyframe = True
            c.mux(p)


def ff(*args):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    return dict(rc=r.returncode, stderr=r.stderr.strip()[-500:])


def main(out):
    log = {}
    for w, h in SIZES:
        d = os.path.join(out, f"{w}x{h}")
        os.makedirs(os.path.join(d, "jpeg"), exist_ok=True)
        jpegs = []
        for i in range(N):
            ok, buf = cv2.imencode(".jpg", frame(w, h, i), [cv2.IMWRITE_JPEG_QUALITY, 90,
                                                           cv2.IMWRITE_JPEG_PROGRESSIVE, 0])
            jb = buf.tobytes()
            assert b"\xff\xc0" in jb and b"\xff\xc2" not in jb  # SOF0 baseline, no SOF2
            jpegs.append(jb)
            open(os.path.join(d, "jpeg", f"{i:03d}.jpg"), "wb").write(jb)
        L = log[f"{w}x{h}"] = {}
        a = os.path.join(d, "A.mkv")
        write_pyav(a, jpegs, w, h)
        L["A.mkv"] = "pyav none"
        for deg in DEGS:
            write_pyav(os.path.join(d, f"B{deg}.mkv"), jpegs, w, h, rot=deg)
            L[f"B{deg}.mkv"] = f"pyav set_display_rotation({deg})"
        # set_display_rotation(deg) calls av_display_rotation_set(m, -deg); the raw-matrix path must match it
        write_pyav(os.path.join(d, "Bm90.mkv"), jpegs, w, h, matrix=rot_matrix_cw_set(-90))
        L["Bm90.mkv"] = f"pyav set_display_matrix({rot_matrix_cw_set(-90)})"
        for deg in DEGS:
            L[f"C{deg}.mkv"] = ff("-display_rotation", str(deg), "-i", a, "-map", "0", "-c", "copy", os.path.join(d, f"C{deg}.mkv"))
            L[f"D{deg}.mp4"] = ff("-display_rotation", str(deg), "-i", a, "-map", "0", "-c", "copy", os.path.join(d, f"D{deg}.mp4"))
        # controls: a `rotate` stream tag in MKV, and H.264 (not MJPEG) with the same display rotation
        L["T90.mkv"] = ff("-i", a, "-map", "0", "-c", "copy", "-metadata:s:v:0", "rotate=90", os.path.join(d, "T90.mkv"))
        h264 = os.path.join(d, "H.mkv")
        L["H.mkv"] = ff("-i", a, "-c:v", "libx264", "-pix_fmt", "yuv420p", h264)
        L["H90.mkv"] = ff("-display_rotation", "90", "-i", h264, "-c", "copy", os.path.join(d, "H90.mkv"))
        L["H90.mp4"] = ff("-display_rotation", "90", "-i", h264, "-c", "copy", os.path.join(d, "H90.mp4"))
    json.dump(log, open(os.path.join(out, "make_log.json"), "w"), indent=1)
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
