"""Summarise results/overlays/electron_*.json (functional runs of electron_harness) into electron_summary.md.

Run from repo root:
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/summarize_electron.py [file.json]
(with a file argument the summary goes to <file>_summary.md next to it)
"""
import json
import sys
from pathlib import Path

RES = Path(__file__).resolve().parents[2] / "results" / "overlays"
files = sorted(RES.glob("electron_*.json")) if len(sys.argv) < 2 else [Path(a) for a in sys.argv[1:]]
out = []
for f in files:
    d = json.loads(f.read_text())
    if "results" not in d:
        continue
    env = d.get("env", {})
    r = d["results"]
    out.append(f"## {f.name}: Electron {env.get('electron')} / Chromium {env.get('chrome')} (scaleFactor {env.get('scaleFactor')})\n")
    if d.get("error"):
        out.append(f"ERROR: {d['error']}\n")
    if "caps" in r:
        out.append("### Load / canPlayType\n\n| file | loads | error | barcode at load | textTracks |\n|---|---|---|---|---|")
        for k, v in r["caps"]["load"].items():
            out.append(f"| {k} | {v['ok']} | {v.get('msg') or ''} | {v.get('barcodeAtLoad')} | {v.get('textTracks')} |")
        out.append("\n| MIME | canPlayType |\n|---|---|")
        for k, v in r["caps"]["canPlayType"].items():
            out.append(f"| `{k}` | {v!r} |")
        out.append("")
    if "play" in r:
        out.append("### Playback alignment (play to end)\n")
        out.append("| file | rVFC callbacks | barcode decoded | overlay(rVFC mediaTime->pts lookup) == video frame | round(mediaTime*30) == frame | today's UI: floor(currentTime*30) in rAF == frame (n) | UI offsets | composited captures overlay==video | capture mismatches [video, overlay] | presented gaps / dropped |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for k, v in r["play"].items():
            if "error" in v:
                out.append(f"| {k} | error {v['error']} |"); continue
            dec = v["vfc"] - v["vfcDecodeFail"]
            out.append(f"| {k} | {v['vfc']} | {dec} | {v['overlayMatch']}/{dec} | {v['naiveMatch']}/{dec} | {v['rafUiMatch']}/{v['raf'] - v['rafDecodeFail']} | {v['rafUiOffsets']} | "
                       f"{v['captureMatch']}/{v['captures'] - v['captureFail']} | {v['captureMismatch'][:6]} | {v['presentedGaps']} / {v.get('droppedVideoFrames')} |")
        out.append("")
    if "seek" in r:
        out.append("### Paused seeks (exact pts / midpoint between pts)\n")
        out.append("| file | mode | n | presented == requested | presented == lookup(rVFC mediaTime) | decode fail | capture now: overlay==video | capture +100 ms: overlay==video | example requested!=presented |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for k, v in r["seek"].items():
            if "error" in v:
                out.append(f"| {k} | error |"); continue
            for mode, m in v["modes"].items():
                ok = v["n"] - m["decodeFail"]
                ex = "; ".join(f"f{x['f']}->{x['code']}" for x in m["mism"][:4])
                out.append(f"| {k} | {mode} | {v['n']} | {m['requestedMatch']}/{ok} | {m['lookupMatch']}/{ok} | {m['decodeFail']} | {m['captureMatch']}/{v['n'] - m['captureFail']} | "
                           f"{m.get('capture100Match')}/{v['n'] - m.get('capture100Fail', 0)} | {ex} |")
        out.append("")
    if "lastframe" in r:
        out.append("### Seek to the last frame, then seek elsewhere\n")
        out.append("| file | sequence (target -> presented barcode, rVFC fired, ended) |\n|---|---|")
        for k, v in r["lastframe"].items():
            seq = ", ".join(f"{s['target']}->{s['barcode']}{'' if s['vfc'] else ' (no rVFC)'}{' E' if s['ended'] else ''}" for s in v.get("steps", []))
            out.append(f"| {k} (n={v.get('n')}) | {seq} |")
        out.append("")
    if "vtt" in r:
        out.append("### WebVTT metadata track (cue id = frame index)\n")
        out.append("| case | cues loaded | playback: activeCue == presented frame (in rVFC) | offsets cue-frame | empty | cuechange events | paused seeks: activeCue == presented |")
        out.append("|---|---|---|---|---|---|---|")
        for k, v in r["vtt"].items():
            p = v["play"]
            out.append(f"| {k} ({v['file']} + {v['vtt']}) | {v['cues']} | {p['match']}/{p['vfc']} | {p['offsets']} | {p['empty']} | {v['cuechange']['events']} | {v['seek']['match']}/{v['seek']['n']} |")
        out.append("")
    if "inband" in r:
        out.append("### In-band subtitle tracks\n\n| file | loads | textTracks exposed | cues |\n|---|---|---|---|")
        for k, v in r["inband"].items():
            out.append(f"| {k} | {v['load'].get('ok')} | {len(v['textTracks'])} | {v['cuesAfterSeek']} |")
        out.append("")
    if "alpha" in r:
        a = r["alpha"]
        out.append("### VP9-alpha overlay layer\n")
        out.append(f"- loads: {a['load']}; frame 0 alpha==0 fraction {a.get('frame0_alpha_zero_fraction')}, alpha==255 fraction {a.get('frame0_alpha_full_fraction')}; overlay barcode frame 0 = {a.get('overlayBarcodeFrame0')}")
        s = a["dualVideoSync"]
        out.append(f"- two <video> elements played together: same frame in {s['match']}/{s['vfc'] - s['decodeFail']} base rVFC callbacks, offsets {s['offsets']}; composited captures {s['captureMatch']}/{s['captures'] - s['captureFail']} {s['captureMismatch'][:6]}")
        p = a["dualVideoSeek"]
        out.append(f"- paused seeks of both elements to the same time: {p['match']}/{p['n']} both on the requested frame; mismatches {p['mism'][:6]}\n")
    if "trunc" in r:
        out.append("### Truncated files\n\n| file | result |\n|---|---|")
        for k, v in r["trunc"].items():
            out.append(f"| {k} | {v} |")
        out.append("")
    if "webcodecs" in r:
        w = r["webcodecs"]
        out.append("### WebCodecs isConfigSupported (1920x1080)\n\n| codec/hw | encode | decode |\n|---|---|---|")
        for k in w.get("enc", {}):
            out.append(f"| {k} | {w['enc'][k]} | {w['dec'].get(k)} |")
        out.append("")
    if "layout" in r:
        L = r["layout"]
        out.append(f"### Label layout in the browser (12px Arial, {L['frames']} frames, ~95 corner labels each)\n")
        out.append("| method | label-label overlaps | label-marker overlaps | out of bounds | lane | hidden |\n|---|---|---|---|---|---|")
        out.append(f"| naive (+8,-8 offset, like freemocap-ui drawPoints) | {L['naive']['labelLabel']} | {L['naive']['labelMarker']} | {L['naive']['outOfBounds']} | - | - |")
        out.append(f"| placeLabels (layout.js) | {L['placed']['labelLabel']} | {L['placed']['labelMarker']} | {L['placed']['outOfBounds']} | {L['placed']['lane']} | {L['placed']['hidden']} |")
        out.append(f"\ndeterministic (two runs identical): {L['deterministic']}\n")
summary_path = RES / "electron_summary.md" if len(sys.argv) < 2 else files[0].with_name(files[0].stem + "_summary.md")
summary_path.write_text("# Electron overlay functional results (generated by summarize_electron.py)\n\n" + "\n".join(out) + "\n")
print("\n".join(out))
