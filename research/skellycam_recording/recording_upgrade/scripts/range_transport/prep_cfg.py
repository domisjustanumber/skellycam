"""Write cfg.json for electron/main.cjs from media.json and flac/electron_cfg.json.
Usage: python -I prep_cfg.py <media_dir> [reps]"""
import json, os, sys, urllib.parse
from pathlib import Path

media = sys.argv[1]
reps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
m = json.load(open(os.path.join(media, "media.json")))
fl = json.load(open(os.path.join(media, "flac", "electron_cfg.json")))
files = {
    "pattern.bin": m["pattern"]["path"], "cam0.mkv": m["cam0"]["path"], "h264.mp4": m["h264"]["path"],
    "big.mkv": m["big"]["path"],
    "f1_1ch_skau.mka": os.path.join(media, "flac", "f1_1ch_skau.mka"),
    "f1_2ch_skau.mka": os.path.join(media, "flac", "f1_2ch_skau.mka"),
}
sizes = {k: os.path.getsize(v) for k, v in files.items()}
q = "?recording_parent_directory=" + urllib.parse.quote(os.path.join(media, "rec"))
urls = {
    "file": {k: Path(v).as_uri() for k, v in files.items()},
    "http_asis": {k: f"http://127.0.0.1:53190/skellycam/playback/rangetest/videos/{k.rsplit('.', 1)[0]}{q}"
                  for k in ("cam0.mkv", "h264.mp4", "f1_1ch_skau.mka", "f1_2ch_skau.mka")},
    "http_fixed_real": {k: f"http://127.0.0.1:53190/fixed/{k}" for k in files},
    "http_fixed_bare": {k: f"http://127.0.0.1:53191/fixed/{k}" for k in files},
    "http_fixed_bare_nostore": {k: f"http://127.0.0.1:53191/fixed/{k}" for k in files},
    "http_fixed_real_ns": {k: f"http://127.0.0.1:53190/fixed_ns/{k}" for k in files},
    "http_fixed_bare_ns": {k: f"http://127.0.0.1:53191/fixed_ns/{k}" for k in files},
    "http_fixed_bare_localhost": {k: f"http://localhost:53191/fixed/{k}" for k in files},
    "skr": {k: f"skr://media/{k}" for k in files},
    "skn": {k: f"skn://media/{k}" for k in files},
}
flac = []
for t in fl["tests"]:
    if not t["name"].startswith("mka_skau"):
        continue
    t = dict(t)
    t["file"] = os.path.basename(urllib.parse.unquote(t["url"].replace("file:///", "")))
    flac.append(t)
cfg = {
    "scratch": media, "files": files, "sizes": sizes, "urls": urls, "flac": flac,
    "ports": {"http_asis": 53190, "http_fixed_real": 53190, "http_fixed_bare": 53191, "http_fixed_bare_nostore": 53191,
              "http_fixed_real_ns": 53190, "http_fixed_bare_ns": 53191},
    "media": {"cam0_sha": m["cam0"]["payload_sha256"], "big_sha": m["big"]["payload_sha256"], "big_ranges": m["big"]["range_sha256"]},
    "semanticsTransports": ["file", "http_asis", "http_fixed_real", "http_fixed_bare", "skr", "skn"],
    "correctTransports": ["file", "http_asis", "http_fixed_real", "http_fixed_real_ns", "http_fixed_bare_ns", "skr", "skn"],
    "bench": {"reps": reps, "sizes": [1536, 4096, 153600], "n1": 150, "n16": 640, "sustainedS": 3, "pacedS": 4,
              "transports": ["file", "http_asis", "http_fixed_real_ns", "http_fixed_bare_ns", "skr", "skn"]},
}
json.dump(cfg, open(os.path.join(media, "cfg.json"), "w"))
print("wrote", os.path.join(media, "cfg.json"), sizes)
