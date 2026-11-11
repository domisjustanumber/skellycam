"""List probe entries (canPlayType / MSE / MediaCapabilities / WebCodecs / ImageDecoder / features) that differ between runs.
Usage: python probe_diff.py a_main.json b_main.json [c_main.json]"""
import json, sys
def probe(p):
    d = json.load(open(p)); return next(v for k, v in d["results"].items() if k.endswith("|probe"))
P = [probe(p) for p in sys.argv[1:]]
def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from flat(v, f"{pre}/{k}")
    else: yield pre, o
F = [dict(flat({k: p[k] for k in ("containersBare", "video", "audio", "audioWebCodecs", "webcodecs", "imageDecoder", "features")})) for p in P]
for k in F[0]:
    vals = [f.get(k) for f in F]
    if any(v != vals[0] for v in vals): print(k, " | ".join(map(str, vals)))
