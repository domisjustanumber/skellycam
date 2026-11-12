"""Check every test file from make_media.py with each reader, and test the sidecar appender on a rotated MKV.

Per file: Matroska element scan of Tracks/Tags, ffprobe side data, FFmpeg CLI autorotated decode, OpenCV
(CAP_FFMPEG, orientation props), PyAV (stream coded side data, frame.rotation / frame side data), source JPEG
bytes vs muxed packets, and VLC 3 (real Direct3D11 window, screen grab; see vlc_window.py).
Orientation is read from pixels: where the red (top-left) and green (top-right) blocks land.

Usage: python -I probe_all.py <media_dir> <result_json> [--no-vlc]
"""
import glob, json, os, shutil, struct, subprocess, sys
import av, cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "sidecar_embedding"))
import vlc_window                      # noqa: E402
from append_attachment import append   # noqa: E402

NAMES = {0x18538067: "Segment", 0x1654AE6B: "Tracks", 0xAE: "TrackEntry", 0xE0: "Video", 0x55B0: "Colour",
         0x7670: "Projection", 0x7671: "ProjectionType", 0x7672: "ProjectionPrivate", 0x7673: "ProjectionPoseYaw",
         0x7674: "ProjectionPosePitch", 0x7675: "ProjectionPoseRoll", 0xB0: "PixelWidth", 0xBA: "PixelHeight",
         0x54B0: "DisplayWidth", 0x54BA: "DisplayHeight", 0x54B2: "DisplayUnit", 0x9A: "FlagInterlaced",
         0x1254C367: "Tags", 0x7373: "Tag", 0x63C0: "Targets", 0x67C8: "SimpleTag", 0x45A3: "TagName",
         0x4487: "TagString", 0x1941A469: "Attachments", 0x86: "CodecID", 0x83: "TrackType"}
MASTERS = {0x1654AE6B, 0xAE, 0xE0, 0x55B0, 0x7670, 0x1254C367, 0x7373, 0x63C0, 0x67C8}
FLOATS = {0x7673, 0x7674, 0x7675}
STRINGS = {0x45A3, 0x4487, 0x86}


def vint(b, p, keep=False):
    f = b[p]; n = 1; m = 0x80
    while n <= 8 and not (f & m): n += 1; m >>= 1
    v = f if keep else f & (m - 1)
    for i in range(1, n): v = (v << 8) | b[p + i]
    return v, n, (not keep) and v == (1 << (7 * n)) - 1


def walk(b, p, end, depth, out, path):
    while p < end:
        eid, n1, _ = vint(b, p, True); sz, n2, unk = vint(b, p + n1)
        d = p + n1 + n2
        name = NAMES.get(eid, hex(eid))
        e = dict(path=path + "/" + name, id=hex(eid), pos=p, size=sz)
        if eid in FLOATS:
            e["value"] = struct.unpack(">f" if sz == 4 else ">d", b[d:d + sz])[0]
        elif eid in STRINGS:
            e["value"] = b[d:d + sz].decode(errors="replace")
        elif eid not in MASTERS and sz <= 8:
            e["value"] = int.from_bytes(b[d:d + sz], "big")
        out.append(e)
        if eid in MASTERS:
            walk(b, d, d + sz, depth + 1, out, path + "/" + name)
        p = d + sz


def ebml_scan(path):
    b = open(path, "rb").read()
    eid, n1, _ = vint(b, 0, True); sz, n2, _ = vint(b, n1)
    p = n1 + n2 + sz
    eid, n1, _ = vint(b, p, True); ssz, n2, unk = vint(b, p + n1)
    seg = p + n1 + n2; end = len(b) if unk else seg + ssz
    out = []; q = seg
    while q < end:
        eid, n1, _ = vint(b, q, True); sz, n2, unk = vint(b, q + n1)
        d = q + n1 + n2
        if eid in (0x1654AE6B, 0x1254C367):
            out.append(dict(path="/" + NAMES[eid], id=hex(eid), pos=q, size=sz))
            walk(b, d, d + sz, 1, out, "/" + NAMES[eid])
        elif eid == 0x1941A469:
            out.append(dict(path="/Attachments", id=hex(eid), pos=q, size=sz))
        if unk: break
        q = d + sz
    video = [e for e in out if "/Video/" in e["path"]]
    proj = {e["path"].split("/")[-1]: e.get("value") for e in out if "/Projection/" in e["path"]}
    tags = [(e["value"]) for e in out if e["path"].endswith("TagName")]
    return dict(video_children=[(e["path"].split("Video/")[1], e["id"], e.get("value")) for e in video],
                projection=proj or None, tag_names=tags, has_attachments=any(e["path"] == "/Attachments" for e in out))


def ffprobe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,width,height:stream_side_data:stream_tags", "-of", "json", path],
                       capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    sd = [x for x in s.get("side_data_list", []) if x.get("side_data_type") == "Display Matrix"]
    return dict(codec=s["codec_name"], w=s["width"], h=s["height"], rotation=sd[0]["rotation"] if sd else None,
                tags={k: v for k, v in s.get("tags", {}).items() if k.lower() != "duration"})


def orient(img):
    """Locate red (TL in source) and green (TR in source) blocks; return dims + label."""
    if img is None: return None
    h, w = img.shape[:2]
    b, g, r = (img[..., i].astype(int) for i in range(3))
    def corner(mask):
        ys, xs = np.nonzero(mask)
        if len(xs) < 50: return None
        x, y = xs.mean() / w, ys.mean() / h
        return ("T" if y < 0.5 else "B") + ("L" if x < 0.5 else "R")
    red = corner((r > 180) & (g < 80) & (b < 80)); green = corner((g > 180) & (r < 80) & (b < 80))
    label = {("TL", "TR"): "none", ("TR", "BR"): "rot90cw", ("BR", "BL"): "rot180", ("BL", "TL"): "rot90ccw"}.get(
        (red, green), f"other(red={red},green={green})")
    return dict(w=w, h=h, red=red, green=green, label=label)


def ffmpeg_ref(path, png):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-frames:v", "1", png],
                   capture_output=True)
    return orient(cv2.imread(png))


def opencv(path):
    res = {}
    for auto in (None, 0):
        cap = cv2.VideoCapture(path, cv2.CAP_FFMPEG)
        if auto is not None:
            cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, auto)
        ok, fr = cap.read()
        res["auto_default" if auto is None else "auto_off"] = dict(
            orientation_meta=cap.get(cv2.CAP_PROP_ORIENTATION_META), orientation_auto=cap.get(cv2.CAP_PROP_ORIENTATION_AUTO),
            frame=orient(fr) if ok else None)
        cap.release()
    return res


def pyav(path):
    with av.open(path) as c:
        s = c.streams.video[0]
        csd = {k: v.hex() for k, v in s.codec_context.coded_side_data.items()}
        fr = next(c.decode(s))
        fsd = [str(x) for x in fr.side_data]
        img = fr.to_ndarray(format="bgr24")
        return dict(stream_coded_side_data=csd, frame_rotation=fr.rotation, frame_side_data=fsd, frame=orient(img))


def frame_bytes(path, jpeg_dir):
    src = [open(f, "rb").read() for f in sorted(glob.glob(os.path.join(jpeg_dir, "*.jpg")))]
    data = open(path, "rb").read()
    with av.open(path) as c:
        pk = [bytes(p) for p in c.demux(c.streams.video[0]) if p.size]
    return dict(n_src=len(src), n_pkts=len(pk), packets_identical=sum(a == b for a, b in zip(pk, src)),
                contiguous_in_file=sum(data.find(x) >= 0 for x in src))


def vlc(path, out):
    r = vlc_window.run(path, out)
    png = os.path.join(out, "window.png")
    return dict(client_w=r.get("client_w"), client_h=r.get("client_h"), rc=r.get("rc"),
                frame=orient(cv2.imread(png)) if os.path.exists(png) else None)


def probe(path, jpeg_dir, work, do_vlc):
    name = os.path.basename(path)
    res = dict(ffprobe=ffprobe(path), ffmpeg_cli_autorotate=ffmpeg_ref(path, os.path.join(work, f"ref_{name}.png")),
               opencv=opencv(path), pyav=pyav(path))
    if path.endswith(".mkv"):
        res["ebml"] = ebml_scan(path)
    if not name.startswith("H"):   # H*.mkv/mp4 are H.264 controls, not JPEG passthrough
        res["frame_bytes"] = frame_bytes(path, jpeg_dir)
    if do_vlc:
        res["vlc"] = vlc(path, os.path.join(work, "vlc_" + name))
    return res


def main(media, out_json, do_vlc=True):
    results = {}
    for size_dir in sorted(glob.glob(os.path.join(media, "*x*"))):
        size = os.path.basename(size_dir)
        jpeg_dir = os.path.join(size_dir, "jpeg")
        work = os.path.join(size_dir, "probe"); os.makedirs(work, exist_ok=True)
        # appender test on the PyAV 90-degree file
        att = os.path.join(size_dir, "B90_att.mkv")
        shutil.copyfile(os.path.join(size_dir, "B90.mkv"), att)
        app = append(att, b"dummy sidecar " * 100, "dummy.skfr")
        R = results[size] = {"_append_B90_att": app}
        files = sorted(glob.glob(os.path.join(size_dir, "*.mkv")) + glob.glob(os.path.join(size_dir, "*.mp4")))
        for f in files:
            name = os.path.basename(f)
            r = R[name] = probe(f, jpeg_dir, work, do_vlc)
            v = r.get("vlc", {}).get("frame") or {}
            print(size, name, "ffprobe", r["ffprobe"]["rotation"], "ref", (r["ffmpeg_cli_autorotate"] or {}).get("label"),
                  "cv2", (r["opencv"]["auto_default"]["frame"] or {}).get("label"),
                  "pyav", r["pyav"]["frame_rotation"], "vlc", v.get("label"), r.get("vlc", {}).get("client_w"),
                  r.get("vlc", {}).get("client_h"), "proj", (r.get("ebml") or {}).get("projection"), flush=True)
        json.dump(results, open(out_json, "w"), indent=1)
    json.dump(results, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--no-vlc" not in sys.argv)
