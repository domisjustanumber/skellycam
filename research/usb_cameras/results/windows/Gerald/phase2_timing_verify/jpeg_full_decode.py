# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Full (non-reduced) decode of every saved C930e JPEG with Pillow in strict mode (truncated images raise)."""
import sys, json
from pathlib import Path
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = False
for d in sys.argv[1:]:
    ok = bad = 0; sizes = set(); errs = []
    for p in sorted(Path(d).glob("frame_*.jpg")):
        try:
            with Image.open(p) as im:
                im.load(); sizes.add(im.size)
            b = p.read_bytes()
            if b[:2] != b"\xff\xd8" or b[-2:] != b"\xff\xd9": raise ValueError("soi/eoi")
            ok += 1
        except Exception as e:
            bad += 1; errs.append(f"{p.name}: {e}")
    print(json.dumps({"dir": d, "ok": ok, "bad": bad, "sizes": sorted(sizes), "errs": errs[:5]}))
