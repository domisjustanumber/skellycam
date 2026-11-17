"""Scan every per-frame MJPEG size record (jsonl + W-PYMF-ALL frames.bin) under skellycam-raw and the repo
research tree (read-only), dedupe identical files, and write one row per file to scan_files.jsonl."""
import json, os, re, struct, hashlib, sys
import numpy as np

ROOTS = [r'C:\Users\Dom\Documents\skellycam-raw', r'C:\Users\Dom\GitHub\freemocap\skellycam\research']
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scan_files.jsonl')
CAM_RE = [(re.compile(r'046d[-_:]?(?:pid_)?085c|c922', re.I), 'C922'),
          (re.compile(r'046d[-_:]?(?:pid_)?0843|c930e', re.I), 'C930e'),
          (re.compile(r'4c4a[-_:]?(?:pid_)?4a55|generic|usbcam|vid_4c4a', re.I), 'generic'),
          (re.compile(r'1532[-_:]?(?:pid_)?0e05|kiyo|vid_1532', re.I), 'Kiyo Pro')]
SKIP_DIRS = re.compile(r'W-OCV-CTRL|W-RAW|-decode|decoded|opencv-msmf-raw|opencv-dshow-raw|recording_upgrade|skellycam_recording|frame_ring_buffer|mock|unit_test|drafts', re.I)
RES_RE = re.compile(r'(\d{3,4})x(\d{3,4})')
FPS_RE = re.compile(r'(\d{3,4})x(\d{3,4})(?:at|_|@)(\d{1,3})(?!\d)')


def cam_of(s):
    # deepest path component naming exactly one camera wins (pair/multi dirs name several)
    for comp in reversed(re.split(r'[/\\]', s)):
        hits = {name for rx, name in CAM_RE if rx.search(comp)}
        if len(hits) == 1:
            return hits.pop()
    return None


def file_hash(p):
    h = hashlib.sha1()
    with open(p, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def summary_info(d):
    """width/height/fps from a nearby summary.json, if present."""
    for name in ('summary.json',):
        p = os.path.join(d, name)
        if os.path.exists(p):
            try:
                s = json.load(open(p))
            except Exception:
                return {}
            req = s.get('requested') or {}
            out = {k: req.get(k) for k in ('width', 'height', 'fps') if isinstance(req.get(k), (int, float))}
            return out
    return {}


def ts_fps(ts):
    ts = np.asarray([t for t in ts if t], dtype=np.float64)
    if len(ts) < 5:
        return None
    d = np.diff(ts)
    d = d[d > 0]
    return 1e9 / np.median(d) if len(d) else None


def emit(out, path, cam, sizes, w, h, fps_nom, fps_meas, kind):
    sizes = np.asarray(sizes, dtype=np.int64)
    if not len(sizes):
        return
    out.write(json.dumps(dict(path=path, cam=cam, w=w, h=h, fps_nom=fps_nom, fps_meas=fps_meas, kind=kind,
                              n=int(len(sizes)), sizes=sizes.tolist())) + '\n')


def do_jsonl(path, out):
    recs = []
    with open(path) as f:
        for line in f:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    if not recs:
        return 'empty'
    r0 = recs[0]
    if 'dtype' in r0 or 'raw_len' in r0 or 'raw' in r0:
        return 'raw'
    key = next((k for k in ('bytes', 'mjpeg_len', 'payload_bytes', 'bytesused') if k in r0), None)
    if key is None:
        return 'nokey'
    d = os.path.dirname(path)
    cam = cam_of(path) or cam_of(str(r0.get('camera_key', '')))
    si = summary_info(d)
    sizes, ws, hs, ts, cams = [], [], [], [], []
    for r in recs:
        b = r.get(key)
        if not isinstance(b, int) or b <= 0:
            continue
        if r.get('soi') is False or r.get('is_valid_jpeg') is False:
            continue
        sizes.append(b)
        sh = r.get('frame_shape')
        ws.append(r.get('sof0_w') or r.get('sof_w') or r.get('width') or (sh[1] if isinstance(sh, list) and len(sh) > 1 else None))
        hs.append(r.get('sof0_h') or r.get('sof_h') or r.get('height') or (sh[0] if isinstance(sh, list) and len(sh) > 1 else None))
        ts.append(r.get('qpc_ns') or r.get('host_arrival_ns') or r.get('os_timestamp_ns'))
        cams.append(cam_of(str(r.get('camera_key', ''))) if r.get('camera_key') else None)
    w0 = si.get('width')
    h0 = si.get('height')
    m = FPS_RE.search(path)
    fps_nom = si.get('fps') or (int(m.group(3)) if m else None)
    if (not w0) and RES_RE.search(os.path.basename(d) + os.sep + os.path.basename(path)):
        mm = RES_RE.search(os.path.basename(d) + os.sep + os.path.basename(path))
        w0, h0 = int(mm.group(1)), int(mm.group(2))
    if not w0:
        txt = ''
        for nm in ('command.txt', 'result.json', 'analyze_frames.json'):
            pp = os.path.join(d, nm)
            if os.path.exists(pp):
                txt += open(pp, errors='replace').read()[:20000]
        mw = re.search(r'--width[ =](\d+)', txt) or re.search(r'"width":\s*(\d+)', txt)
        mh = re.search(r'--height[ =](\d+)', txt) or re.search(r'"height":\s*(\d+)', txt)
        if mw and mh:
            w0, h0 = int(mw.group(1)), int(mh.group(1))
        else:
            mm = re.search(r'(?:s|_|\\)(2160|1440|1080|720|480)p?(?:\D|$)', path)
            if mm:
                w0, h0 = {'2160': (3840, 2160), '1440': (2560, 1440), '1080': (1920, 1080), '720': (1280, 720), '480': (640, 480)}[mm.group(1)]
    groups = {}
    for b, w, h, t, c in zip(sizes, ws, hs, ts, cams):
        k = (c or cam, w or w0, h or h0)
        g = groups.setdefault(k, ([], []))
        g[0].append(b); g[1].append(t)
    for (c, w, h), (bs, tt) in groups.items():
        emit(out, path, c, bs, w, h, fps_nom, ts_fps(tt), os.path.basename(path))
    return 'ok'



def do_bin(path, out):
    fmt = '<IqqqIIBHH'
    n = struct.calcsize(fmt)
    data = open(path, 'rb').read()
    recs = [struct.unpack_from(fmt, data, i) for i in range(0, len(data) - n + 1, n)]
    # fields seq qpc_ns sample_time sample_dur bytes reader_flags bits sof_w sof_h
    sizes = [r[4] for r in recs if r[4] > 0 and (r[6] & 1)]
    w = next((r[7] for r in recs if r[7]), None)
    h = next((r[8] for r in recs if r[8]), None)
    part = os.path.basename(os.path.dirname(os.path.dirname(path)))
    m = re.search(r'(\d+)p(\d+)', part)
    fps_nom = int(m.group(2)) if m else None
    emit(out, path, cam_of(path), sizes, w, h, fps_nom, ts_fps([r[1] for r in recs]), 'frames.bin')
    return 'ok'


def main():
    seen = set()
    stats = {}
    with open(OUT, 'w') as out:
        for root in ROOTS:
            for dp, dn, fn in os.walk(root):
                if SKIP_DIRS.search(dp):
                    continue
                for f in fn:
                    p = os.path.join(dp, f)
                    if f.endswith('.jsonl') and ('frame' in f or f in ('cells.jsonl','probes.jsonl')):
                        kind = do_jsonl
                    elif f == 'frames.bin':
                        kind = do_bin
                    else:
                        continue
                    hh = file_hash(p)
                    if hh in seen:
                        stats['dup'] = stats.get('dup', 0) + 1
                        continue
                    seen.add(hh)
                    try:
                        r = kind(p, out)
                    except Exception as e:
                        r = 'err:' + type(e).__name__
                    stats[r] = stats.get(r, 0) + 1
    print(stats)


if __name__ == '__main__':
    main()
