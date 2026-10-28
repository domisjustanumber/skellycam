import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
defs = dict(re.findall(r"#define\s+(GVSP_PIX_\w+)\s+\(?\s*(0x[0-9A-Fa-f]+)", src))
tbl = src[src.index("static const value_string pixeltypenames[]"):]
tbl = tbl[:tbl.index("};")]
out = []
for sym, name in re.findall(r"\{\s*(GVSP_PIX_\w+)\s*,\s*\"([^\"]+)\"", tbl):
    out.append((int(defs[sym], 16), name.split(" ")[0]))
print(len(out))
items = [f"0x{v:08X}: \"{n}\"" for v, n in out]
lines, cur = [], "    "
for it in items:
    if len(cur) + len(it) + 2 > 110:
        lines.append(cur.rstrip()); cur = "    "
    cur += it + ", "
lines.append(cur.rstrip())
open(sys.argv[2], "w").write("PFNC_NAMES: dict[int, str] = {\n" + "\n".join(lines) + "\n}\n")
