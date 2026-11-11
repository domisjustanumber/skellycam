"""Independent spot-check of tables.md cells against raw/*.json (does not import summarize.py).
Usage: python spotcheck.py <raw json> <key suffix> [<key suffix> ...]   e.g.  play|hevc_main_420__mp4
Prints the raw fields a table cell is built from."""
import json, sys
d = json.load(open(sys.argv[1]))
r = d["results"]
for suf in sys.argv[2:]:
    ks = [k for k in r if k.endswith("|" + suf)]
    for k in ks:
        v = r[k]
        dec = sorted({pl["props"].get("kVideoDecoderName") for pl in (v.get("media") or {}).values()} - {None})
        hw = sorted({pl["props"].get("kIsPlatformVideoDecoder") for pl in (v.get("media") or {}).values()} - {None})
        p = v.get("play") or {}
        seeks = [(s["k"], s.get("idx")) for s in v.get("seeks", [])]
        print(k)
        print("  ready=%s err=%s setupError=%s mseTypeSupported=%s" % (v.get("ready"), (v.get("error") or {}).get("message", "")[:70], str(v.get("setupError"))[:60], v.get("mseTypeSupported")))
        print("  play idxValid=%s idxEqExpected=%s monotonic=%s madMax=%s | seekExact=%s/%s | decoder=%s platform=%s" % (p.get("idxValid"), p.get("idxEqExpected"), p.get("monotonic"), p.get("madMax"), v.get("seekExact"), v.get("seekTotal"), dec, hw))
        if seeks: print("  seeks (k, idx):", seeks)
        if "outputs" in v: print("  wc isConfigSupported=%s outputs=%s inOrderCorrect=%s madMax=%s errors=%s formats=%s" % (v.get("isConfigSupported"), v.get("outputs"), v.get("inOrderCorrect"), v.get("madMax"), [e[:80] for e in v.get("errors", [])], v.get("formats")))
