# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF10: merge raw per-config JSON (TEMP/raw/<tag>/) into results/intra_playback/gapfill/GF10_wc_scrub_memory.json
and print a Markdown table. No timing fields are read or written.

  uv run --script .../GF10/summarize_gf10.py --tags main[,extra] > TEMP/table.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TEMP = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF10")
OUT = Path(__file__).resolve().parents[4] / "results/intra_playback/gapfill/GF10_wc_scrub_memory.json"
MODES = {"reuse": 0, "pool": 1, "baseline": 2}
CODECS = {"h264_nvenc": 0, "hevc_nvenc": 1, "h264_qsv": 2}


def row(path: Path, tag: str) -> dict:
    d = json.loads(path.read_text())
    ver, mode, codec, n = path.stem.split("__")
    r = d.get("result") or {}
    base = {"tag": tag, "file": path.name, "electron": d.get("versions", {}).get("electron"), "chrome": d.get("versions", {}).get("chrome"),
            "mode": mode, "codec": codec, "n": int(n[1:]), "gpu_device": (d.get("gpu_info") or {}).get("gpuDevice")}
    base["gpu_feature_status_end"] = {k: (d.get("gpu_feature_status") or {}).get(k) for k in ("video_decode", "gpu_compositing")}
    base["child_process_gone"] = d.get("child_process_gone") or []
    if "error" in r:
        return {**base, "error": r["error"]}
    if mode.startswith("origscrub"):  # control: original bench scrub page logic, no marks, 500 ms sampler only
        bg = d.get("bg_samples_gpu", [])
        pids = list(dict.fromkeys(x["pid"] for x in bg))
        return {**base, "drive": "original scrub loop (wall-clock target, harness.mjs:461-515)", "errors_per_stream": [x["errors"] for x in r["per_stream"]],
                "errors_total": sum(x["errors"] for x in r["per_stream"]), "gpu_private_kb_peak_bg500ms": max((x["private_kb"] for x in bg), default=None),
                "gpu_pids": pids, "gpu_replacements": max(0, len(pids) - 1), "bg_samples_gpu": bg}
    ps = r["per_stream"]
    marks = r["marks"]
    gpu_pids = []
    for m in marks:
        for g in m["gpu"]:
            if g["pid"] not in gpu_pids:
                gpu_pids.append(g["pid"])
    for s in d.get("bg_samples_gpu", []):
        if s["pid"] not in gpu_pids:
            gpu_pids.append(s["pid"])
    run_marks = [m for m in marks if m["count"] > 0]

    def mx(ms):
        v = [g["private_kb"] for m in ms for g in m["gpu"]]
        return max(v) if v else None

    last_run = run_marks[-1] if run_marks else None
    errs: dict[str, int] = {}
    cb: dict[str, int] = {}
    for s in ps:
        for k, v in s["errors_by_message"].items():
            errs[k] = errs.get(k, 0) + v
        for k, v in s["decoder_error_messages"].items():
            cb[k] = cb.get(k, 0) + v
    decoders = {}
    for p in d.get("media_players_at_end") or []:
        nm = p.get("kVideoDecoderName")
        decoders[nm] = decoders.get(nm, 0) + 1
    return {**base,
            "targets_per_stream": r["targets_total"], "aborted_at_count": r.get("aborted_at_count"),
            "errors_total": sum(s["errors"] for s in ps), "errors_per_stream": [s["errors"] for s in ps],
            "errors_by_message": errs, "decoder_error_callbacks": sum(s["decoder_error_callbacks"] for s in ps),
            "decoder_error_messages": cb, "rebuilds_total": sum(s["rebuilds"] for s in ps),
            "drive": r.get("drive", "lockstep"), "readevery": r.get("readevery", 1),
            "checked_per_stream": [s["checked"] if "checked" in s else (0 if r.get("readevery", 1) == 0 else s["targets"] - s["errors"]) for s in ps],
            "exact_per_stream": [s["exact"] for s in ps], "wrong_total": sum(s["wrong"] for s in ps),
            "unreadable_total": sum(s["unreadable"] for s in ps),
            "resets_total": sum(s.get("resets", 0) for s in ps), "configures_total": sum(s.get("configures", 0) for s in ps),
            "stray_outputs_closed": sum(s.get("stray_outputs_closed", 0) for s in ps),
            "gpu_private_kb_baseline": mx([m for m in marks if m["label"] == "baseline_before_decoders"]),
            "gpu_private_kb_configured": mx([m for m in marks if m["label"] == "configured"]),
            "gpu_private_kb_peak_marks": mx(run_marks), "gpu_private_kb_final_run": mx([last_run]) if last_run else None,
            "gpu_private_kb_after_close": mx([m for m in marks if m["label"] == "after_close"]),
            "gpu_private_kb_after_close_settle3s": mx([m for m in marks if m["label"] == "after_close_settle3s"]),
            "gpu_private_kb_peak_bg500ms": max((s["private_kb"] for s in d.get("bg_samples_gpu", [])), default=None),
            "gpu_pids": gpu_pids, "gpu_replacements": max(0, len(gpu_pids) - 1),
            "decoder_names_media_log": decoders,
            "marks": [{"label": m["label"], "count": m["count"], "gpu": m["gpu"]} for m in marks],
            "bg_samples_gpu": d.get("bg_samples_gpu", []),
            "error_examples": [e for s in ps for e in s["error_examples"]][:12],
            "wrong_examples": [e for s in ps for e in s["wrong_examples"]][:12]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="main")
    a = ap.parse_args()
    rows = []
    targets = None
    for tag in a.tags.split(","):
        for p in sorted((TEMP / "raw" / tag).glob("e*__*.json")):
            rows.append(row(p, tag))
        t = TEMP / "raw" / tag / "_targets.json"
        if t.exists() and targets is None:
            targets = json.loads(t.read_text())
    rows.sort(key=lambda x: (x["mode"] != x["mode"].split("_")[0], MODES.get(x["mode"].split("_")[0], 9), x["mode"], CODECS.get(x["codec"], 9), x["n"], x["electron"] or ""))
    OUT.write_text(json.dumps({
        "gapfill": "GF10", "date": "2026-11-10", "machine": "Gerald (i7-14700K, RTX 3070 driver 610.88, UHD 770)",
        "note": "Functional run on a shared machine. No scrub rate, latency, fps or CPU is recorded. private_kb = Electron "
                "app.getAppMetrics() memory.privateBytes, raw unit (Electron docs: 'Kilobytes'; 1000 vs 1024 NOT VERIFIED).",
        "scripts": "scripts/intra_playback/gapfill/GF10/{run_gf10.py,summarize_gf10.py,harness/}",
        "clips": "C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/clips/c1080p30/<codec>_intra.mp4 (PyAV 19.0.2, gen_intra_clips.py)",
        "target_list": targets, "configs": rows}, indent=1))
    print("| mode | codec | N | Electron | errors | rebuilds | exact | peak private_kb (marks) | final run mark | after close +3 s | baseline | GPU repl. | decoders (media log) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        if x["mode"].startswith("origscrub"):
            print(f"| {x['mode']} (control) | {x['codec']} | {x['n']} | {x['electron'][:2]} | {x['errors_total']} | none (no recovery) | not read | "
                  f"{x['gpu_private_kb_peak_bg500ms']:,} (500 ms sampler) | | | | {x['gpu_replacements']} (gone {len(x['child_process_gone'])}) | |")
            continue
        if "error" in x:
            print(f"| {x['mode']} | {x['codec']} | {x['n']} | {x['electron']} | RUN ERROR: {str(x['error'])[:80]} |||||||||")
            continue
        ex = sum(x["exact_per_stream"])
        tot = x["targets_per_stream"] * x["n"]
        chk = sum(x["checked_per_stream"])
        exs = "not read (readevery=0)" if x["readevery"] == 0 else f"{ex}/{chk} checked" + ("" if chk == tot else f" (of {tot} targets)")
        ab = f" (aborted at {x['aborted_at_count']})" if x["aborted_at_count"] else ""
        dn = ", ".join(f"{k} ×{v}" for k, v in x["decoder_names_media_log"].items())
        print(f"| {x['mode']} | {x['codec']} | {x['n']} | {x['electron'][:2]} | {x['errors_total']} | {x['rebuilds_total']} | {exs}{ab} | "
              f"{x['gpu_private_kb_peak_marks']:,} | {x['gpu_private_kb_final_run']:,} | {x['gpu_private_kb_after_close_settle3s']:,} | "
              f"{x['gpu_private_kb_baseline']:,} | {x['gpu_replacements']} (gone {len(x['child_process_gone'])}{', video_decode ' + str(x['gpu_feature_status_end']['video_decode']) if x['gpu_feature_status_end']['video_decode'] != 'enabled' else ''}) | {dn} |")


if __name__ == "__main__":
    main()
