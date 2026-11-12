"""Dump top-level Matroska structure and SeekHead entries."""
import sys
NAMES = {0x1A45DFA3:"EBML",0x18538067:"Segment",0x114D9B74:"SeekHead",0xEC:"Void",0x1549A966:"Info",
 0x1654AE6B:"Tracks",0x1F43B675:"Cluster",0x1C53BB6B:"Cues",0x1941A469:"Attachments",0x1254C367:"Tags",
 0x1043A770:"Chapters",0xBF:"CRC32",0x4DBB:"Seek",0x53AB:"SeekID",0x53AC:"SeekPosition"}
def vint(b, p, keep_marker=False):
    first = b[p]; n = 1; m = 0x80
    while n <= 8 and not (first & m): n += 1; m >>= 1
    v = first if keep_marker else first & (m - 1)
    for i in range(1, n): v = (v << 8) | b[p+i]
    unknown = (not keep_marker) and v == (1 << (7*n)) - 1
    return v, n, unknown
def elem(b, p):
    eid, n1, _ = vint(b, p, True); size, n2, unk = vint(b, p+n1)
    return eid, p+n1+n2, (None if unk else size), n1+n2, n2
def main(path):
    b = open(path,'rb').read()
    p = 0
    eid, d, size, hl, _ = elem(b, 0); print(f"{NAMES.get(eid,hex(eid))} @0 hdr={hl} size={size}"); p = d+size
    eid, d, size, hl, szlen = elem(b, p); seg_data = d
    print(f"Segment @{p} hdr={hl} sizefield_len={szlen} size={size} data_start={d} file_len={len(b)} end={d+size if size is not None else None}")
    q = d; end = d+size if size is not None else len(b)
    nclusters = 0
    while q < end:
        eid, dd, sz, hl, _ = elem(b, q)
        name = NAMES.get(eid, hex(eid))
        if name == "Cluster":
            nclusters += 1
            if nclusters <= 2: print(f"  Cluster @{q} (rel {q-seg_data}) size={sz}")
        else:
            print(f"  {name} @{q} (rel {q-seg_data}) hdr={hl} size={sz}")
        if name == "SeekHead":
            r = dd
            while r < dd+sz:
                e2, d2, s2, _, _ = elem(b, r)
                if e2 == 0x4DBB:
                    s = d2; sid = None; spos = None
                    while s < d2+s2:
                        e3, d3, s3, _, _ = elem(b, s)
                        if e3 == 0x53AB: sid = int.from_bytes(b[d3:d3+s3],'big')
                        if e3 == 0x53AC: spos = int.from_bytes(b[d3:d3+s3],'big')
                        s = d3+s3
                    print(f"     Seek {NAMES.get(sid,hex(sid))} -> rel {spos} (abs {spos+seg_data})")
                r = d2+s2
        if sz is None: print("  unknown size; stop"); break
        q = dd+sz
    print(f"  clusters={nclusters}")
if __name__ == "__main__": main(sys.argv[1])
