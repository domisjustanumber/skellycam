"""Identify the drawn number in the Blender renders and summarise. Usage: python identify_pngs.py MEDIA_DIR

Movie frame index n = scene frame - 1 (strip / clip / image starts at scene frame 1).
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

d = Path(sys.argv[1])
thumbs = np.load(d / "ref_thumbs.npy")
files = {f["file"][:-4]: f for f in json.loads((d / "files.json").read_text())["files"]}
table = defaultdict(dict)
worst = [0.0, 1e9]
for png in sorted((d / "blender_out").glob("*.png")):
    name, method, n = png.stem.split("__")
    img = cv2.imread(str(png), cv2.IMREAD_COLOR)
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (64, 48), interpolation=cv2.INTER_AREA).astype(np.float32)
    if g.max() < 5:
        table[(name, method)][int(n)] = None  # blank: nothing shown
        continue
    dist = np.abs(thumbs - g).mean(axis=(1, 2))
    o = np.argsort(dist)
    worst = [max(worst[0], float(dist[o[0]])), min(worst[1], float(dist[o[1]] - dist[o[0]]))]
    table[(name, method)][int(n)] = int(o[0])


def stored_rows(name):
    m = files[name]["missing"]
    lo, hi = (map(int, m.split("-")) if m != "none" else (-1, -2))
    return [r for r in range(300) if not lo <= r <= hi]


def runs(pairs):
    """Compress [(n, shown)] into 'n0-n1:shown' runs where the shown value is constant or n + const."""
    out, i = [], 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[j][0] + 1 and (
            pairs[j + 1][1] == pairs[j][1] or (pairs[j][1] is not None and pairs[j + 1][1] == pairs[j][1] + 1)):
            j += 1
        a, b = pairs[i], pairs[j]
        out.append(f"{a[0]}-{b[0]}->{a[1]}..{b[1]}" if j > i else f"{a[0]}->{a[1]}")
        i = j + 1
    return ", ".join(out)


print(f"max ident dist {worst[0]:.2f}, min margin to 2nd best {worst[1]:.2f}")
print("| file | path | n = row n | n = stored block n | blank | repeats prev | n != row n (runs n->shown) |")
print("|---|---|---|---|---|---|---|")
summary = {}
for (name, method), row in sorted(table.items()):
    st = stored_rows(name)
    shown = [row[n] for n in range(300)]
    eq_row = sum(shown[n] == n for n in range(300))
    eq_blk = sum(n < len(st) and shown[n] == st[n] for n in range(300))
    blank = sum(s is None for s in shown)
    rep = sum(shown[n] is not None and shown[n] == shown[n - 1] for n in range(1, 300))
    dev = runs([(n, shown[n]) for n in range(300) if shown[n] != n])
    summary[f"{name}|{method}"] = {"eq_row": eq_row, "eq_block": eq_blk, "blank": blank, "repeats": rep, "dev": dev, "shown": shown}
    print(f"| {name} | {method} | {eq_row} | {eq_blk} | {blank} | {rep} | {dev or '-'} |")
(d / "blender_ident.json").write_text(json.dumps(summary, indent=1))
