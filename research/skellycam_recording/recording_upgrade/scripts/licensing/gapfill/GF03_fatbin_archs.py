# Static read of CUDA fatbinary headers inside a DLL (no execution). Usage: fatbin_archs.py <whl> <member>
import sys, zipfile, struct, collections, json
whl, member = sys.argv[1:3]
b = zipfile.ZipFile(whl).read(member)
MAGIC = struct.pack("<I", 0xBA55ED50)
pos, res, nfat = 0, collections.Counter(), 0
while True:
    i = b.find(MAGIC, pos)
    if i < 0: break
    try:
        magic, ver, hsz, fsz = struct.unpack_from("<IHHQ", b, i)
    except struct.error: break
    if hsz != 16 or fsz == 0 or i + hsz + fsz > len(b):
        pos = i + 4; continue
    nfat += 1
    off, end = i + hsz, i + hsz + fsz
    while off + 64 <= end:
        kind, ever, ehsz, psz = struct.unpack_from("<HHIQ", b, off)
        sm = struct.unpack_from("<I", b, off + 28)[0]
        if kind not in (1, 2) or ehsz < 32 or ehsz > 256: break
        res[("PTX" if kind == 1 else "ELF/SASS", sm)] += 1
        off += ehsz + psz
    pos = end
print(json.dumps({"member": member, "bytes": len(b), "fatbins": nfat,
  "entries": [{"kind": k, "sm": s, "count": c} for (k, s), c in sorted(res.items(), key=lambda x:(x[0][1], x[0][0]))]}, indent=1))
