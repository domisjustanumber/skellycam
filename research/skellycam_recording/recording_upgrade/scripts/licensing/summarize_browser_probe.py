"""Print a Markdown comparison table from electron/chrome codec probe JSON files.
Usage: python summarize_browser_probe.py a.json b.json ..."""
import json, sys
fs = sys.argv[1:]
ds = [json.load(open(f, encoding="utf-8")) for f in fs]
def label(d):
    v = d.get("electron_versions")
    return f"Electron {v['electron']} (Chromium {v['chrome']})" if v else d["userAgent"].split("Chrome/")[1].split()[0].join(["Chrome ", ""])
print("| item | " + " | ".join(label(d) for d in ds) + " |"); print("|---" * (len(ds) + 1) + "|")
def cell(r):
    if r.get("event") == "loadeddata" and not r.get("play_error") and r.get("decoded_frame_ok", True) and (r.get("played_currentTime") or 0) > 0:
        return "plays + decodes" if "decoded_frame_ok" in r else "plays"
    if r.get("error"): return f"error {r['error']['code']}: {r['error']['message'][:60]}"
    return json.dumps({k: r.get(k) for k in ("event", "decoded_frame_ok", "played_currentTime", "play_error") if r.get(k) is not None})[:80]
for i, r in enumerate(ds[0]["video"]): print(f"| video `{r['file']}` | " + " | ".join(cell(d["video"][i]) for d in ds) + " |")
for i, r in enumerate(ds[0]["audio"]): print(f"| audio `{r['file']}` | " + " | ".join(cell(d["audio"][i]) for d in ds) + " |")
for i, r in enumerate(ds[0]["images"]): print(f"| img `{r['file']}` | " + " | ".join(str(d["images"][i]["event"]) for d in ds) + " |")
for m in ds[0]["canPlayType"]: print(f"| canPlayType / MSE `{m}` | " + " | ".join(f"'{d['canPlayType'][m]}' / {d['mseIsTypeSupported'][m]}" for d in ds) + " |")
for k in ds[0]["webcodecs"]["decoder"]: print(f"| WebCodecs dec / enc `{k}` | " + " | ".join(f"{d['webcodecs']['decoder'][k]} / {d['webcodecs']['encoder'][k]}" for d in ds) + " |")
for m in ds[0]["imageDecoder"]: print(f"| ImageDecoder `{m}` | " + " | ".join(str(d["imageDecoder"][m]) for d in ds) + " |")
