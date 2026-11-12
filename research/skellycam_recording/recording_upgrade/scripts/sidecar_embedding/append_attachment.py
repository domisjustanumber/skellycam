"""Append a Matroska Attachments element at the end of a finalised MKV, in place, without remux.

Steps (each in-place write is small; bulk data is never moved):
  1. parse EBML header, Segment header, first SeekHead and the Void that follows it
  2. append Attachments{AttachedFile{FileName, FileMediaType, FileUID, FileData}} at EOF
  3. rewrite the Segment size (8-byte vint, same width) to cover the new element
  4. rewrite SeekHead (+1 Seek entry -> Attachments) inside the old SeekHead+Void span, re-padding with Void
Refuses: unknown-size Segment, Segment not ending at EOF, no room in SeekHead+Void, existing Attachments.
Usage: python append_attachment.py <file.mkv> <payload> [name]
"""
import os, sys, struct, zlib

ID_SEGMENT, ID_SEEKHEAD, ID_VOID = 0x18538067, 0x114D9B74, 0xEC
ID_SEEK, ID_SEEKID, ID_SEEKPOS = 0x4DBB, 0x53AB, 0x53AC
ID_ATTACHMENTS, ID_ATTACHEDFILE = 0x1941A469, 0x61A7
ID_FILENAME, ID_FILEMEDIATYPE, ID_FILEDATA, ID_FILEUID = 0x466E, 0x4660, 0x465C, 0x46AE

def read_vint(b, p, keep_marker=False):
    first = b[p]; n = 1; m = 0x80
    while n <= 8 and not (first & m): n += 1; m >>= 1
    if n > 8: raise ValueError(f"bad vint at {p}")
    v = first if keep_marker else first & (m - 1)
    for i in range(1, n): v = (v << 8) | b[p + i]
    unknown = (not keep_marker) and v == (1 << (7 * n)) - 1
    return v, n, unknown

def read_elem(b, p):
    eid, n1, _ = read_vint(b, p, True)
    size, n2, unk = read_vint(b, p + n1)
    return eid, p + n1 + n2, (None if unk else size), n2

def enc_id(eid): return eid.to_bytes((eid.bit_length() + 7) // 8, "big")

def enc_size(n, width=None):
    if width is None:
        width = 1
        while n >= (1 << (7 * width)) - 1: width += 1   # all-ones is reserved for "unknown"
    if n >= (1 << (7 * width)) - 1: raise ValueError("size does not fit")
    return ((1 << (7 * width)) | n).to_bytes(width, "big")   # marker bit at top of first byte

def el(eid, payload, width=None): return enc_id(eid) + enc_size(len(payload), width) + payload
def uint(v): return v.to_bytes(max(1, (v.bit_length() + 7) // 8), "big")

def void_of_total(total):
    """A Void element occupying exactly `total` bytes (total >= 2)."""
    if total < 2: raise ValueError("cannot pad 1 byte")
    for w in range(1, 9):
        body = total - 1 - w
        if body >= 0 and body < (1 << (7 * w)) - 1:
            return bytes([ID_VOID]) + enc_size(body, w) + b"\x00" * body
    raise ValueError

def parse_seekhead(b, d, sz):
    entries = []; r = d
    while r < d + sz:
        e2, d2, s2, _ = read_elem(b, r)
        if e2 == ID_SEEK:
            s = d2; sid = spos = None
            while s < d2 + s2:
                e3, d3, s3, _ = read_elem(b, s)
                if e3 == ID_SEEKID: sid = int.from_bytes(b[d3:d3 + s3], "big")
                elif e3 == ID_SEEKPOS: spos = int.from_bytes(b[d3:d3 + s3], "big")
                s = d3 + s3
            entries.append((sid, spos))
        r = d2 + s2
    return entries

def append(path, payload, name="skellycam_frames.skfr", mime="application/x-skellycam-frames"):
    with open(path, "r+b") as f:
        head = f.read(64 * 1024)
        file_len = os.fstat(f.fileno()).st_size
        eid, d, size, _ = read_elem(head, 0)
        if eid != 0x1A45DFA3: raise ValueError("not EBML")
        seg_pos = d + size
        eid, seg_data, seg_size, seg_szlen = read_elem(head, seg_pos)
        if eid != ID_SEGMENT: raise ValueError("no Segment")
        if seg_size is None: raise ValueError("unknown-size Segment (unfinalised file): remux first")
        if seg_data + seg_size != file_len: raise ValueError("Segment does not end at EOF")
        eid, sh_data, sh_size, _ = read_elem(head, seg_data)
        if eid != ID_SEEKHEAD: raise ValueError("first child is not SeekHead")
        entries = parse_seekhead(head, sh_data, sh_size)
        if any(sid == ID_ATTACHMENTS for sid, _ in entries): raise ValueError("already has Attachments")
        span_end = sh_data + sh_size
        eid, vd, vsz, _ = read_elem(head, span_end)
        if eid == ID_VOID: span_end = vd + vsz
        span = span_end - seg_data   # bytes available for the new SeekHead (+ pad)

        att_rel = file_len - seg_data   # position relative to Segment data start
        new_entries = entries + [(ID_ATTACHMENTS, att_rel)]
        sh_body = b"".join(el(ID_SEEK, el(ID_SEEKID, enc_id(i)) + el(ID_SEEKPOS, uint(p))) for i, p in new_entries)
        had_crc = read_elem(head, sh_data)[0] == 0xBF
        if had_crc:   # keep the EBML CRC-32 (RFC 8794 s11.3.1): zlib CRC of the following children, little-endian
            sh_body = b"\xbf\x84" + struct.pack("<I", zlib.crc32(sh_body)) + sh_body
        new_sh = el(ID_SEEKHEAD, sh_body)
        pad = span - len(new_sh)
        if pad == 1:   # widen the SeekHead size field by one byte to absorb it
            new_sh = el(ID_SEEKHEAD, sh_body, width=len(enc_size(len(sh_body))) + 1); pad = 0
        if pad < 0: raise ValueError(f"no room: need {len(new_sh)} have {span}")
        new_span = new_sh + (void_of_total(pad) if pad else b"")
        assert len(new_span) == span

        uid = int.from_bytes(os.urandom(8), "big") or 1
        af = (el(ID_FILENAME, name.encode()) + el(ID_FILEMEDIATYPE, mime.encode()) +
              el(ID_FILEUID, uid.to_bytes(8, "big")) + el(ID_FILEDATA, payload))
        attachments = el(ID_ATTACHMENTS, el(ID_ATTACHEDFILE, af))

        # 1. append (outside the Segment until step 2: harmless trailing bytes if we crash here)
        f.seek(file_len); f.write(attachments); f.flush(); os.fsync(f.fileno())
        # 2. Segment size, same width
        f.seek(seg_pos + len(enc_id(ID_SEGMENT)))
        f.write(enc_size(seg_size + len(attachments), seg_szlen)); f.flush(); os.fsync(f.fileno())
        # 3. SeekHead + Void, same span
        f.seek(seg_data); f.write(new_span); f.flush(); os.fsync(f.fileno())
        filedata_abs = file_len + len(attachments) - len(payload)
        return dict(seekhead_crc32_kept=had_crc, attachments_abs=file_len, attachments_len=len(attachments),
                    filedata_abs=filedata_abs, payload_len=len(payload), seekhead_span=span,
                    new_seekhead_len=len(new_sh), void_pad=pad)

if __name__ == "__main__":
    payload = open(sys.argv[2], "rb").read()
    print(append(sys.argv[1], payload, *(sys.argv[3:4] or [])))
