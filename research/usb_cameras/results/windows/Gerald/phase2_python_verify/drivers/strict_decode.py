# /// script
# requires-python = ">=3.10"
# dependencies = ["simplejpeg", "numpy"]
# ///
import sys, json, inspect, simplejpeg
print("simplejpeg", simplejpeg.__version__, "strict" in str(inspect.signature(simplejpeg.decode_jpeg)) if hasattr(simplejpeg.decode_jpeg,'__text_signature__') else simplejpeg.decode_jpeg.__doc__[:300].replace("\n"," "))
out = {}
for p in sys.argv[1:]:
    data = open(p, "rb").read()
    i = 0; n = ok = 0; bad = []; sizes = []; dims=set(); trailing=0
    while i + 4 <= len(data):
        L = int.from_bytes(data[i:i+4], "little"); b = data[i+4:i+4+L]; i += 4 + L; n += 1
        sizes.append(L)
        try:
            h = simplejpeg.decode_jpeg_header(b)
            arr = simplejpeg.decode_jpeg(b, strict=True)
            dims.add(arr.shape); ok += 1
            # trailing bytes after EOI
            e = b.rfind(b"\xff\xd9")
            if e != len(b) - 2: trailing += 1
        except Exception as ex:
            bad.append((n, repr(ex)[:100]))
    out[p.rsplit("/",1)[-1]] = {"frames": n, "strict_ok": ok, "bad_first5": bad[:5], "n_bad": len(bad), "dims": [list(d) for d in dims], "eoi_not_last": trailing, "min_bytes": min(sizes), "max_bytes": max(sizes)}
    print(p.rsplit("/",1)[-1], out[p.rsplit("/",1)[-1]], flush=True)
json.dump(out, open(sys.argv[0].rsplit("/",1)[0] + "/strict_decode_result.json", "w"), indent=1)
