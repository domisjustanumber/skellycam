"""Print OpenCV reads and seeks near the holes. Usage: python summarize_opencv.py MEDIA_DIR"""

import json
import sys
from pathlib import Path

r = json.loads((Path(sys.argv[1]) / "opencv_results.json").read_text())
for n in ["full", "B-one", "B-run", "B-tail", "B-tail-dur10", "B-head", "B-head30", "A-one", "A-run"]:
    o = r[n]["opencv"]
    print(f"## {n}  max ident dist {o['max_ident_dist']}  min margin {o['min_ident_margin']}")
    reads = o["all_reads"]
    idx = [i for i in range(len(reads)) if i < 3 or 97 <= i <= 103 or 187 <= i <= 192 or i >= len(reads) - 2]
    print(" read i:drawn/POS_FRAMES/POS_MSEC", " ".join(f"{reads[i]['i']}:{reads[i]['num']}/{reads[i]['pos_frames']:g}/{reads[i]['pos_msec']:g}" for i in idx))
    for by in ["frames", "msec"]:
        print(f" seek {by}:", " ".join(f"{s['n']}->{s['num']}{'' if s['set_ok'] else '(setF)'}{'' if s['read_ok'] else '(readF)'}" for s in o["seeks"] if s["by"] == by))
