"""Compare JPEG header segments (everything before SOS + SOS header) across capture paths.
usage: python jpeghdr.py label=path[.jpg|.bin|dir-with-.bin] ...
.bin = mf_mjpeg_capture/pyav records (u32 cam, u64 seq, u32 len, bytes); first 5 frames used.
Prints per source: marker list, sha1 of each segment class (APPn, DQT, DHT, SOF, DRI, SOS-header), and
whether the image has 0xFFD9 at the end. Same camera via different APIs => identical header digests
means the bytes were passed through, not re-encoded (a re-encoder would emit its own DQT/DHT/APP0)."""
import hashlib, struct, sys, os, glob


def segs(b):
    assert b[:2] == b'\xff\xd8', 'no SOI'
    i, out = 2, []
    while i < len(b):
        if b[i] != 0xFF:
            raise ValueError('bad marker at %d' % i)
        m = b[i + 1]
        if m == 0xD8 or 0x01 == m or 0xD0 <= m <= 0xD7:
            out.append((m, b'')); i += 2; continue
        L = struct.unpack('>H', b[i + 2:i + 4])[0]
        out.append((m, b[i + 4:i + 2 + L]))
        if m == 0xDA:
            break
        i += 2 + L
    return out


def name(m):
    return {0xC0: 'SOF0', 0xC4: 'DHT', 0xDB: 'DQT', 0xDA: 'SOS', 0xDD: 'DRI', 0xFE: 'COM'}.get(m, 'APP%d' % (m - 0xE0) if 0xE0 <= m <= 0xEF else hex(m))


def summarize(b):
    s = segs(b)
    d = {}
    for m, p in s:
        d.setdefault(name(m), []).append(p)
    dig = {k: hashlib.sha1(b''.join(v)).hexdigest()[:10] for k, v in d.items()}
    sof = d.get('SOF0', [b''])[0]
    sofinfo = struct.unpack('>BHHB', sof[:6]) if len(sof) >= 6 else None
    app = {k: (v[0][:24]) for k, v in d.items() if k.startswith('APP') or k == 'COM'}
    return [name(m) for m, _ in s], dig, sofinfo, app, b[-2:] == b'\xff\xd9'


def frames(path, n=5):
    if os.path.isdir(path):
        path = sorted(glob.glob(os.path.join(path, 'frames_*.bin')))[0]
    if path.endswith('.jpg'):
        yield open(path, 'rb').read(); return
    with open(path, 'rb') as f:
        k = 0
        while k < n:
            h = f.read(16)
            if len(h) < 16:
                return
            cam, seq, L = struct.unpack('<IQI', h)
            b = f.read(L)
            if seq < 30:
                continue
            yield b; k += 1


for arg in sys.argv[1:]:
    label, path = arg.split('=', 1)
    for b in frames(path):
        marks, dig, sof, app, eoi = summarize(b)
        print(f'{label:22s} len={len(b):7d} eoi={eoi} sof(P,H,W,Nc)={sof} markers={"/".join(marks)}')
        print(f'{"":22s} digests={dig} app={app}')
        break
