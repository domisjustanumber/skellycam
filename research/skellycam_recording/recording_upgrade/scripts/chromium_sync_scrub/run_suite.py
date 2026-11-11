# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Run chromium_sync_scrub harness suites in Electron 35.7.5 (skellycam-ui pin) or 45.2.3 (newest stable).

Prerequisites (one-off):
  1. clips:  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/gen_clips.py
  2. mp4box.js (only for the 'mp4box' functional test):
       npm install --prefix C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/chromium_sync_scrub/npm_mp4box --ignore-scripts --save-exact mp4box@2.4.1
Usage (repo root):
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite functional
  .venv/Scripts/python.exe .../run_suite.py --electron 45 --suite bench_seek      [--smoke] [--only <substring>]
Suites: functional | bench_seek | bench_step | bench_sync | bench_scrub
  functional_targeted: deterministic frame lists (VFR near-duplicate pair, seeks after the last frame)
  --contents hdr329 (functional only): supplementary seek batch for clip contents generated later
Outputs:
  functional -> research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/functional/e<ver>/<name>.json
  bench_*    -> research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/bench/e<ver>/<suite>/<id>.json
               (one Electron launch per configuration; nvidia-smi sampled before and after each launch)
Intra-only suites (added 2026-11-09 for topic intra_playback; clips from scripts/intra_playback/gen_intra_clips.py,
PyAV 19.0.2; media root .../recording_upgrade_20261109/intra_playback, served via CSS_MEDIA_ROOT):
  intra_functional   caps, random seeks, steps, playback pattern check, decoder names (Media domain), JPEG-in-MKV
                     byte-range test -> results/intra_playback/functional/<e35|e45|c156>/
  bench_intra_seek | bench_intra_sync | bench_intra_scrub   TIMED, 1080p: JPEG sequence vs H.264/HEVC intra
                     (<video> + rVFC, WebCodecs) -> results/intra_playback/bench/<e35|e45>/<suite>/
  --electron chrome  runs the same pages in Chrome 156 via harness/run_chrome.cjs (Node + DevTools protocol)
  --skip <substring> drops configurations whose id contains it (e.g. --skip _qsv_)
Functional results contain NO timing fields (page runs without bench=1). Bench results carry timing and
app.getAppMetrics() CPU/memory samples and must only be produced on a quiet machine.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
HARNESS = Path(__file__).resolve().parent / "harness"
RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub"
SCRATCH = Path("C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad")
MANIFEST = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/clips/manifest.json")
ELECTRON = {
    "35": REPO / "skellycam-ui/node_modules/electron/dist/electron.exe",
    "45": SCRATCH / "shared/electron-latest/node_modules/electron/dist/electron.exe",
    "chrome": Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),  # run via harness/run_chrome.cjs
}
INTRA_MEDIA = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback")
INTRA_MANIFEST = INTRA_MEDIA / "clips/manifest.json"
INTRA_RESULTS = REPO / "research/skellycam_recording/recording_upgrade/results/intra_playback"
INTRA_RUN = {"env": {"CSS_MEDIA_ROOT": str(INTRA_MEDIA)}, "args": ["--noocclusion=1"]}


def label(ver: str) -> str:
    return "c156" if ver == "chrome" else f"e{ver}"
JPEG_PATHS = ["jpeg-range-bitmap", "jpeg-range-imagedecoder", "jpeg-folder-bitmap", "jpeg-folder-imagedecoder"]


def clips():
    return json.loads(MANIFEST.read_text())["clips"]


def nvsmi() -> str:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=encoder.stats.sessionCount,utilization.gpu,utilization.decoder,memory.used",
                               "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"error {e}"


def run_electron(ver: str, test: str, out: Path, params: str = "", configs: list | None = None, timeout_s: int = 3000,
                 run: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "ELECTRON_RUN_AS_NODE"}  # set by some hosts; breaks Electron apps
    env.update((run or {}).get("env", {}))
    if ver == "chrome":
        cmd = ["node", str(HARNESS / "run_chrome.cjs"), f"--test={test}", f"--out={out}", f"--timeout={timeout_s}"]
    else:
        cmd = [str(ELECTRON[ver]), str(HARNESS), f"--test={test}", f"--out={out}", f"--timeout={timeout_s}"]
    cmd += [a for a in (run or {}).get("args", []) if ver != "chrome" or not a.startswith("--noocclusion")]
    if params:
        cmd.append(f"--params={params}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    if configs is not None:
        fd, name = tempfile.mkstemp(suffix=".json", dir=str(out.parent))
        os.close(fd)
        tmp = Path(name)
        tmp.write_text(json.dumps(configs))
        cmd.append(f"--configs={tmp}")
    before = nvsmi()
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout_s + 60)
    after = nvsmi()
    if tmp:
        tmp.unlink(missing_ok=True)
    if not out.exists():
        raise RuntimeError(f"no output {out}\n{p.stdout[-3000:]}\n{p.stderr[-3000:]}")
    d = json.loads(out.read_text())
    d["nvidia_smi"] = {"query": "encoder.stats.sessionCount,utilization.gpu,utilization.decoder,memory.used", "before": before, "after": after}
    out.write_text(json.dumps(d, indent=1))
    return d


def video_clips(c, contents=None):
    return [k for k, v in c.items() if v["kind"] == "video" and (contents is None or v["content"] in contents)]


def functional(ver: str, smoke: bool, contents: list[str] | None = None) -> None:
    c = clips()
    out = RESULTS / "functional" / f"e{ver}"
    n = "20" if smoke else "200"
    if not contents:
        run_electron(ver, "caps", out / "caps.json")
    seek = []
    for k in video_clips(c, contents):
        modes = ["mid", "ui"] + (["ptsexact", "cfrmid"] if c[k]["vfr"] or c[k]["content"] == "c720p30" else [])
        for m in modes:
            seek.append({"test": "seek", "clip": k, "path": "video", "mode": m, "n": n, "seed": "1"})
        seek.append({"test": "seek", "clip": k, "path": "webcodecs", "n": n, "seed": "1"})
    for k in [k for k, v in c.items() if v["kind"] == "mjpeg" and (not contents or v["content"] in contents)]:
        for p in JPEG_PATHS:
            seek.append({"test": "seek", "clip": k, "path": p, "n": n, "seed": "1"})
    if smoke:
        seek = seek[::7]
    if contents:  # supplementary run for clips added later; summarize.py merges seek_batch*.json
        run_electron(ver, "batch", out / f"seek_batch_{'_'.join(contents)}.json", configs=seek)
        return
    run_electron(ver, "batch", out / "seek_batch.json", configs=seek)
    step = []
    for content in ["c720p30", "c1080p30", "vfr720p", "c720p60"]:
        for v in ["av1_gop.mp4", "vp9_gop.webm", "h264_gop.mp4", "av1_intra.mp4"]:
            k = f"{content}/{v}"
            if k not in c:
                continue
            for m in ["ui", "mid"]:
                step.append({"test": "seek", "pattern": "step", "m": "20", "clip": k, "path": "video", "mode": m, "n": "120" if not smoke else "60", "seed": "2"})
            step.append({"test": "seek", "pattern": "step", "m": "20", "clip": k, "path": "webcodecs", "n": "120" if not smoke else "60", "seed": "2"})
        step.append({"test": "seek", "pattern": "step", "m": "20", "clip": f"{content}/mjpeg", "path": "jpeg-range-imagedecoder", "n": "120" if not smoke else "60", "seed": "2"})
    if smoke:
        step = step[::5]
    run_electron(ver, "batch", out / "step_batch.json", configs=step)
    run_electron(ver, "jpegcompat", out / "jpegcompat.json", params=f"tag=e{ver}&maxframes={'5' if smoke else '30'}")
    run_electron(ver, "mp4box", out / "mp4box.json")
    # sync/scrub: functional smoke only (does it run, errors); no timing reported from these
    ss = []
    for p in ["video-free", "video-leader", "wc-master", "jpeg-master-range-bitmap"]:
        clip = "c720p30/mjpeg" if p.startswith("jpeg") else "c720p30/av1_gop.mp4"
        ss.append({"test": "sync", "clip": clip, "path": p, "n": "4", "dur": "3", "readpattern": "1"})
    for p in ["video-ui", "video-gated", "webcodecs", "jpeg-range-imagedecoder"]:
        clip = "c720p30/mjpeg" if p.startswith("jpeg") else "c720p30/av1_gop.mp4"
        ss.append({"test": "scrub", "clip": clip, "path": p, "n": "2", "dur": "2"})
    run_electron(ver, "batch", out / "sync_scrub_smoke.json", configs=ss)


def functional_targeted(ver: str) -> None:
    """Deterministic frame lists: (1) the 0.011 ms capture-time pair (VFR frames 81/82, 1 ms apart in WebM);
    (2) seeks right after landing on the last frame (anomaly seen in the random runs)."""
    c = clips()
    cfgs = []
    for k in video_clips(c, ["vfr720p"]):
        for m in ["mid", "ptsexact"]:
            cfgs.append({"test": "seek", "clip": k, "path": "video", "mode": m, "ks": "79,80,81,82,83,84,82,81,80", "keeprows": "1"})
        cfgs.append({"test": "seek", "clip": k, "path": "webcodecs", "ks": "79,80,81,82,83,84,82,81,80", "keeprows": "1"})
    for k in ["c720p30/av1_gop.webm", "c720p30/vp9_intra.webm", "c720p30/av1_intra.mp4", "c720p30/h264_gop.mp4", "c720p60/av1_intra.mp4"]:
        for m in ["ptsexact", "mid", "ui"]:
            cfgs.append({"test": "seek", "clip": k, "path": "video", "mode": m, "ks": "300,599,586,8,300,598,300,599,0,300", "keeprows": "1"})
    run_electron(ver, "batch", RESULTS / "functional" / f"e{ver}" / "targeted.json", configs=cfgs)


def intra_clips() -> dict:
    return {k: v for k, v in json.loads(INTRA_MANIFEST.read_text())["clips"].items() if v.get("kind") != "error"}


def intra_functional(ver: str, smoke: bool, contents: list[str] | None, only: str, skip: str, parts: str = "") -> None:
    """Functional (no timing) checks for intra-only H.264/HEVC vs the JPEG path; one batch file per content and kind."""
    c = intra_clips()
    out = INTRA_RESULTS / "functional" / label(ver)
    run = {**INTRA_RUN, "args": INTRA_RUN["args"] + ["--medialog=1"]}
    sfx = "_smoke" if smoke else ""

    def pick(k):
        return (not only or only in k) and (not skip or skip not in k)

    if not only and not contents and not parts:
        run_electron(ver, "caps", out / f"caps{sfx}.json", run=run)
        run_electron(ver, "jpegmkv", out / f"jpegmkv_seq{sfx}.json", params="order=sequential" + ("&maxframes=20" if smoke else ""), run=run)
        run_electron(ver, "jpegmkv", out / f"jpegmkv_random{sfx}.json", params="order=random&seed=3&maxframes=" + ("20" if smoke else "150"), run=run)
    n, ns, nhw = ("12", "30", "6") if smoke else ("100", "120", "30")
    conts = sorted({v["content"] for v in c.values() if "content" in v})
    for content in conts:
        if contents and content not in contents:
            continue
        if smoke and not contents and content != "c720p30":
            continue
        vids = [k for k, v in c.items() if v.get("content") == content and v["kind"] == "video" and pick(k)]
        jpgs = [k for k, v in c.items() if v.get("content") == content and v["kind"] == "mjpeg" and pick(k)]
        if smoke:
            vids = [k for k in vids if "nvenc" in k or "mjpeg" in k][:7]
        seek, step, play = [], [], []
        for k in vids:
            if c[k].get("video_only_expect_fail"):
                seek.append({"test": "seek", "clip": k, "path": "video", "mode": "mid", "n": "5", "seed": "1", "medialog": "1"})
                continue
            for m in ["cfrmid", "mid"]:
                seek.append({"test": "seek", "clip": k, "path": "video", "mode": m, "n": n, "seed": "1", "medialog": "1"})
            # intra: every chunk is a key frame; flush() right after it makes the decoder emit the frame now (wcflush=1).
            # The no-flush variant (wait 200 ms, then flush as a fallback) documents which streams need it.
            seek.append({"test": "seek", "clip": k, "path": "webcodecs", "n": n, "seed": "1", "wcflush": "1", "medialog": "1"})
            seek.append({"test": "seek", "clip": k, "path": "webcodecs", "n": nhw, "seed": "5", "medialog": "1"})
            seek.append({"test": "seek", "clip": k, "path": "webcodecs-hw", "n": nhw, "seed": "4", "medialog": "1"})
            seek.append({"test": "seek", "clip": k, "path": "webcodecs-sw", "n": nhw, "seed": "4", "medialog": "1"})
            step.append({"test": "seek", "pattern": "step", "m": "20", "clip": k, "path": "video", "mode": "mid", "n": ns, "seed": "2"})
            step.append({"test": "seek", "pattern": "step", "m": "20", "clip": k, "path": "webcodecs", "n": ns, "seed": "2", "wcflush": "1"})
            play.append({"test": "sync", "clip": k, "path": "video-free", "n": "1", "dur": "5", "readpattern": "1", "medialog": "1"})
            play.append({"test": "sync", "clip": k, "path": "wc-master", "n": "1", "dur": "5", "readpattern": "1", "medialog": "1"})
        for k in jpgs:
            for p in ["jpeg-range-bitmap", "jpeg-range-imagedecoder"]:
                seek.append({"test": "seek", "clip": k, "path": p, "n": n, "seed": "1"})
                step.append({"test": "seek", "pattern": "step", "m": "20", "clip": k, "path": p, "n": ns, "seed": "2"})
            play.append({"test": "sync", "clip": k, "path": "jpeg-master-range-bitmap", "n": "1", "dur": "5", "readpattern": "1"})
        for name, cfgs in [("seek", seek), ("step", step), ("play", play)]:
            if cfgs and (not parts or name in parts.split(",")):
                run_electron(ver, "batch", out / f"{name}_{content}{sfx}.json", configs=cfgs, run=run)
                print(f"{label(ver)} {name}_{content}: {len(cfgs)} configs done", flush=True)
    if not only and (not contents or "c1080p30" in contents) and (not parts or "sync4" in parts.split(",")):  # multi-stream functional smoke of the bench paths
        ss = []
        for k in ["c1080p30/h264_nvenc_intra.mp4", "c1080p30/hevc_nvenc_intra.mp4"]:
            for p in ["video-free", "video-rvfc", "wc-master"]:
                ss.append({"test": "sync", "clip": k, "path": p, "n": "4", "dur": "3", "readpattern": "1"})
        for k in ["c1080p30/jpeg_seq", "c1080p30/jpeg_in_mkv"]:
            ss.append({"test": "sync", "clip": k, "path": "jpeg-master-range-bitmap", "n": "4", "dur": "3", "readpattern": "1"})
        ss = [x for x in ss if x["clip"] in c]
        if ss:
            run_electron(ver, "batch", out / f"sync4{sfx}.json", configs=ss, run=run)


INTRA_BENCH_VIDEO = ["c1080p30/h264_nvenc_intra.mp4", "c1080p30/hevc_nvenc_intra.mp4",
                     "c1080p30/h264_qsv_intra.mp4", "c1080p30/hevc_qsv_intra.mp4"]
INTRA_BENCH_JPEG = ["c1080p30/jpeg_seq", "c1080p30/jpeg_in_mkv"]


def intra_bench_configs(suite: str):
    cfgs = []
    if suite == "bench_intra_seek":
        for k in INTRA_BENCH_VIDEO:
            cfgs.append((f"{k}|video|mid", {"clip": k, "path": "video", "mode": "mid", "n": "200", "seed": "11"}))
            cfgs.append((f"{k}|webcodecs", {"clip": k, "path": "webcodecs", "n": "200", "seed": "11", "wcflush": "1"}))
        for k in INTRA_BENCH_JPEG:
            for p in ["jpeg-range-bitmap", "jpeg-range-imagedecoder"]:
                cfgs.append((f"{k}|{p}", {"clip": k, "path": p, "n": "200", "seed": "11"}))
        return "seek", cfgs
    if suite == "bench_intra_sync":
        for n in ["4", "8"]:
            for k in INTRA_BENCH_VIDEO:
                paths = ["video-free", "video-rvfc", "wc-master"] + (["video-leader"] if "nvenc" in k else [])
                for p in paths:
                    cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "15"}))
            for k, p in [("c1080p30/jpeg_seq", "jpeg-master-range-bitmap"), ("c1080p30/jpeg_seq", "jpeg-master-range-imagedecoder"),
                         ("c1080p30/jpeg_in_mkv", "jpeg-master-range-bitmap")]:
                cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "15"}))
        return "sync", cfgs
    if suite == "bench_intra_scrub":
        for n in ["4", "8"]:
            for k in INTRA_BENCH_VIDEO:
                for p in ["video-gated", "webcodecs"]:
                    cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "8", "speed": "90", **({"wcflush": "1"} if p == "webcodecs" else {})}))
            for k in INTRA_BENCH_JPEG:
                for p in ["jpeg-range-bitmap", "jpeg-range-imagedecoder"]:
                    cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "8", "speed": "90"}))
        return "scrub", cfgs
    raise SystemExit(f"unknown suite {suite}")


def bench_configs(suite: str, c: dict, smoke: bool) -> list[tuple[str, dict]]:
    cfgs = []
    if suite == "bench_seek":
        for k in video_clips(c, ["c720p30", "c1080p30", "c720p60"]):
            cfgs.append((f"{k}|video|mid", {"clip": k, "path": "video", "mode": "mid", "n": "200", "seed": "11"}))
            cfgs.append((f"{k}|webcodecs", {"clip": k, "path": "webcodecs", "n": "200", "seed": "11"}))
        for content in ["c720p30", "c1080p30", "c720p60"]:
            for p in JPEG_PATHS:
                cfgs.append((f"{content}/mjpeg|{p}", {"clip": f"{content}/mjpeg", "path": p, "n": "200", "seed": "11"}))
        test = "seek"
    elif suite == "bench_step":
        for content in ["c720p30", "c1080p30"]:
            for v in ["av1_gop.mp4", "av1_gop.webm", "vp9_gop.webm", "h264_gop.mp4", "av1_intra.mp4", "vp9_intra.webm", "h264_intra.mp4"]:
                k = f"{content}/{v}"
                cfgs.append((f"{k}|video|ui", {"clip": k, "path": "video", "mode": "ui", "pattern": "step", "m": "20", "n": "300", "seed": "12"}))
                cfgs.append((f"{k}|webcodecs", {"clip": k, "path": "webcodecs", "pattern": "step", "m": "20", "n": "300", "seed": "12"}))
            for p in ["jpeg-range-bitmap", "jpeg-range-imagedecoder"]:
                cfgs.append((f"{content}/mjpeg|{p}", {"clip": f"{content}/mjpeg", "path": p, "pattern": "step", "m": "20", "n": "300", "seed": "12"}))
        test = "seek"
    elif suite == "bench_sync":
        for n in ["4", "8"]:
            for v in ["av1_gop.mp4", "vp9_gop.webm", "h264_gop.mp4", "av1_intra.mp4"]:
                k = f"c1080p30/{v}"
                for p in ["video-free", "video-leader", "wc-master"]:
                    cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "15"}))
            for p in ["jpeg-master-range-bitmap", "jpeg-master-range-imagedecoder"]:
                cfgs.append((f"c1080p30/mjpeg|{p}|n{n}", {"clip": "c1080p30/mjpeg", "path": p, "n": n, "dur": "15"}))
        for p in ["video-free", "video-leader", "wc-master"]:
            cfgs.append((f"c720p30/av1_gop.mp4|{p}|n4", {"clip": "c720p30/av1_gop.mp4", "path": p, "n": "4", "dur": "15"}))
            cfgs.append((f"vfr720p/av1_gop.mp4|{p}|n4", {"clip": "vfr720p/av1_gop.mp4", "path": p, "n": "4", "dur": "15"}))
        test = "sync"
    elif suite == "bench_scrub":
        for n in ["1", "4"]:
            for content in ["c720p30", "c1080p30"]:
                for v in ["av1_gop.mp4", "vp9_gop.webm", "h264_gop.mp4", "av1_intra.mp4"]:
                    k = f"{content}/{v}"
                    for p in ["video-ui", "video-gated", "webcodecs"]:
                        cfgs.append((f"{k}|{p}|n{n}", {"clip": k, "path": p, "n": n, "dur": "8", "speed": "90"}))
                for p in ["jpeg-range-bitmap", "jpeg-range-imagedecoder"]:
                    cfgs.append((f"{content}/mjpeg|{p}|n{n}", {"clip": f"{content}/mjpeg", "path": p, "n": n, "dur": "8", "speed": "90"}))
        test = "scrub"
    elif suite.startswith("bench_intra_"):
        test, cfgs = intra_bench_configs(suite)
    else:
        raise SystemExit(f"unknown suite {suite}")
    out = []
    for cid, cfg in cfgs:
        cfg = {**cfg, "bench": "1"}
        if smoke:
            cfg.update({"n": "10" if test == "seek" else cfg["n"], "dur": "2" if "dur" in cfg else cfg.get("dur", "")})
            if test == "seek" and cfg.get("pattern") == "step":
                cfg.update({"m": "3", "n": "18"})
        out.append((cid, cfg))
    return test, out


def bench(ver: str, suite: str, smoke: bool, only: str, skip: str = "") -> None:
    intra = suite.startswith("bench_intra_")
    c = intra_clips() if intra else clips()
    test, cfgs = bench_configs(suite, c, smoke)
    if only:
        cfgs = [x for x in cfgs if only in x[0]]
    if skip:
        cfgs = [x for x in cfgs if skip not in x[0]]
    if smoke:  # one configuration per distinct path (and per N for sync/scrub)
        seen, pick = set(), []
        for cid, cfg in cfgs:
            key = (cfg["path"], cfg.get("mode"), cfg.get("n") if test != "seek" else None)
            if key not in seen:
                seen.add(key)
                pick.append((cid, cfg))
        cfgs = pick
    base = (INTRA_RESULTS if intra else RESULTS) / "bench" / label(ver) / (suite + ("_smoke" if smoke else ""))
    index = []
    for i, (cid, cfg) in enumerate(cfgs):
        fname = cid.replace("/", "_").replace("|", "__") + ".json"
        params = "&".join(f"{k}={v}" for k, v in cfg.items())
        t0 = time.time()
        try:
            d = run_electron(ver, test, base / fname, params=params, timeout_s=600, run=INTRA_RUN if intra else None)
            err = d["result"].get("error") if isinstance(d.get("result"), dict) else None
        except Exception as e:  # noqa: BLE001
            err = str(e)[:500]
        index.append({"id": cid, "file": fname, "error": err})
        print(f"[{i + 1}/{len(cfgs)}] {cid} {'ERROR ' + err if err else 'ok'} ({time.time() - t0:.0f}s)", flush=True)
    # --only runs (e.g. the QSV-file items of the 23:00 queue) keep their own index so the full run's _index.json
    # is not overwritten (added 2026-11-09; summarize.py reads the per-config JSONs, not the index)
    idx = "_index.json" if not only else "_index_only_" + "".join(ch if ch.isalnum() else "_" for ch in only) + ".json"
    (base / idx).write_text(json.dumps({"suite": suite, "electron": ver, "smoke": smoke, "runs": index,
                                                   "switches": INTRA_RUN if intra else None}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--electron", choices=sorted(ELECTRON), required=True)
    ap.add_argument("--suite", required=True)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--contents", default="", help="functional: only seek tests for these clip contents (comma list)")
    ap.add_argument("--skip", default="", help="drop configurations whose id contains this substring")
    ap.add_argument("--parts", default="", help="intra_functional: only these parts (comma list of seek,step,play,sync4)")
    a = ap.parse_args()
    if not ELECTRON[a.electron].exists():
        sys.exit(f"missing {ELECTRON[a.electron]}")
    if a.suite == "intra_functional":
        intra_functional(a.electron, a.smoke, [x for x in a.contents.split(",") if x] or None, a.only, a.skip, a.parts)
    elif a.suite == "functional_targeted":
        functional_targeted(a.electron)
    elif a.suite == "functional":
        functional(a.electron, a.smoke, [x for x in a.contents.split(",") if x] or None)
    else:
        bench(a.electron, a.suite, a.smoke, a.only, a.skip)


if __name__ == "__main__":
    main()
