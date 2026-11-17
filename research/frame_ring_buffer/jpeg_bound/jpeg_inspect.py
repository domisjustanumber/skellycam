"""Parse baseline JPEG structure: markers, DQT (natural order), sampling, DHT presence, DRI/RST count,
header vs entropy bytes, 0xFF00 stuffing, bytes after EOI."""
import struct

ZZ = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21,
      28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61,
      54, 47, 55, 62, 63]


def inspect(b):
    assert b[:2] == b'\xff\xd8', 'no SOI'
    i = 2
    out = dict(segments=[], dqt={}, dht=[], dri=0, sof=None, app=[])
    while i < len(b):
        if b[i] != 0xFF:
            raise ValueError(f'bad marker at {i}')
        m = b[i + 1]
        if m == 0xFF:
            i += 1
            continue
        L = struct.unpack('>H', b[i + 2:i + 4])[0]
        seg = b[i + 4:i + 2 + L]
        out['segments'].append((hex(m), L + 2))
        if m == 0xDB:
            j = 0
            while j < len(seg):
                pq, tq = seg[j] >> 4, seg[j] & 15
                n = 64 * (2 if pq else 1)
                vals = struct.unpack('>64H', seg[j + 1:j + 1 + n]) if pq else tuple(seg[j + 1:j + 65])
                nat = [0] * 64
                for k, v in enumerate(vals):
                    nat[ZZ[k]] = v
                out['dqt'][tq] = nat
                j += 1 + n
        elif m == 0xC4:
            out['dht'].append(L + 2)
        elif m == 0xDD:
            out['dri'] = struct.unpack('>H', seg[:2])[0]
        elif m in (0xC0, 0xC1, 0xC2):
            P, Y, X, Nf = seg[0], struct.unpack('>H', seg[1:3])[0], struct.unpack('>H', seg[3:5])[0], seg[5]
            comps = [(seg[6 + 3 * c], seg[7 + 3 * c] >> 4, seg[7 + 3 * c] & 15, seg[8 + 3 * c]) for c in range(Nf)]
            out['sof'] = dict(type=hex(m), P=P, W=X, H=Y, comps=comps)
        elif 0xE0 <= m <= 0xEF or m == 0xFE:
            out['app'].append((hex(m), L + 2, bytes(seg[:8])))
        if m == 0xDA:
            i += 2 + L
            out['header_bytes'] = i
            break
        i += 2 + L
    # entropy-coded segment
    j = i
    rst = stuff = 0
    while j < len(b) - 1:
        if b[j] == 0xFF:
            n = b[j + 1]
            if n == 0x00:
                stuff += 1
                j += 2
                continue
            if 0xD0 <= n <= 0xD7:
                rst += 1
                j += 2
                continue
            if n == 0xFF:
                j += 1
                continue
            if n == 0xD9:
                break
            break
        j += 1
    out['entropy_bytes'] = j - i
    out['rst_markers'] = rst
    out['stuffed_ff00'] = stuff
    out['eoi_at'] = j if j < len(b) - 1 and b[j + 1] == 0xD9 else None
    out['after_eoi'] = len(b) - (j + 2) if out['eoi_at'] is not None else None
    out['total'] = len(b)
    return out


def ijg_quality(nat, base):
    """best IJG quality matching table nat against IJG base table (natural order)."""
    best = None
    for q in range(1, 101):
        s = 5000 // q if q < 50 else 200 - 2 * q
        t = [min(255, max(1, (v * s + 50) // 100)) for v in base]
        err = sum(abs(a - c) for a, c in zip(nat, t))
        if best is None or err < best[1]:
            best = (q, err)
    return best


IJG_LUMA = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29,
            51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121,
            120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
IJG_CHROMA = [17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99, 99,
              99, 99, 99, 99] + [99] * 32
