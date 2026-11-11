"""Functional test of resumable_recorder.py: crash, restart, continue, verify.

Scenarios (frames from corpus c930e_720p_flash; frame number f carries corpus frame f % 891, so every recovered
packet can be checked byte-for-byte against the camera's JPEG; capture_ns = time.time_ns() at 30 fps pacing;
segment length 2 s):
  kill_mid_segment    kill after 170 frames written in that run, resume, record 90 more, close
  kill_after_rollover kill right after the 2nd segment boundary (first frame of seg 2), resume, close
  double_crash        kill, resume, kill again, resume, close
  powerloss_<seed>    kill, then truncate the last segment, timestamps.bin and manifest.jsonl at random offsets
                      (emulated power loss), resume, close   (5 seeds)
  ffv1_kill_mid       kill_mid_segment with FFV1 (lossless) instead of MJPEG passthrough
Checks: every segment readable by ffprobe; sum of video frames == timestamp records; frame numbers unique and
increasing, every gap listed as lost in the journal; MJPEG packets byte-exact; pts == (capture_ns - t0) // 1e6;
join_session() gives one MKV with all frames and monotonic pts.

usage: python run_resumable_demo.py          (writes results/crash_resilience/resumable_demo.json/.md)
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common_cr as cc  # noqa: E402


def child(session_dir: str, payload: str, n: int, seg_s: float):
    import av
    from resumable_recorder import ResumableRecorder
    from av.video.frame import PictureType
    jp = cc.load_jpegs(cc.DEFAULT_SET, 891)
    rec = ResumableRecorder(Path(session_dir), payload=payload, segment_seconds=seg_s)
    print("RECOVERY " + json.dumps(rec.report.__dict__), flush=True)
    dec = av.CodecContext.create("mjpeg", "r") if payload != "mjpeg" else None
    t0 = time.perf_counter()
    for i in range(n):
        dt = t0 + i / cc.FPS - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
        fn = rec.next_frame
        b = jp[fn % len(jp)]
        if payload == "mjpeg":
            rec.write(b, time.time_ns())
        else:
            fr = dec.decode(av.Packet(b))[0].reformat(format="yuv422p")
            fr.pict_type = PictureType.NONE
            rec.write(fr, time.time_ns())
        print(f"W {fn}", flush=True)
    rec.close()
    print("CLOSED", flush=True)


def run_child(sd: Path, payload: str, n: int, kill_at: int | None, seg_s: float = 2.0) -> dict:
    pr = subprocess.Popen([str(cc.VENV_PY), __file__, "--child", str(sd), payload, str(n), str(seg_s)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rec = None
    last = None
    closed = False
    written = 0
    for line in pr.stdout:
        line = line.strip()
        if line.startswith("RECOVERY "):
            rec = json.loads(line[9:])
        elif line.startswith("W "):
            last = int(line[2:])
            written += 1
            if kill_at is not None and written >= kill_at:
                pr.kill()
                break
        elif line == "CLOSED":
            closed = True
    pr.wait(timeout=120)
    err = pr.stderr.read()[-500:] if pr.stderr else ""
    return {"recovery": rec, "last_frame_reported": last, "closed": closed, "exit": pr.returncode,
            "stderr_tail": err if pr.returncode not in (0, 1) else ""}


def powerloss(sd: Path, seed: int) -> dict:
    """Truncate the newest segment, timestamps.bin and manifest.jsonl at random offsets."""
    rng = random.Random(seed)
    out = {}
    segs = sorted(sd.glob("seg_*.mkv"))
    if segs:
        s = segs[-1]
        b = s.read_bytes()
        cut = rng.randrange(1, len(b))
        s.write_bytes(b[:cut])
        out["segment"] = [s.name, len(b), cut]
    t = sd / "timestamps.bin"
    b = t.read_bytes()
    cut = rng.randrange(max(1, len(b) - 32 * 40), len(b))  # lose up to ~40 records, usually mid-record
    t.write_bytes(b[:cut])
    out["timestamps"] = [len(b), cut]
    m = sd / "manifest.jsonl"
    b = m.read_bytes()
    cut = len(b) - rng.randrange(1, 30)  # tear the last journal line
    m.write_bytes(b[:cut])
    out["manifest"] = [len(b), cut]
    return out


def verify(sd: Path, payload: str) -> dict:
    import av
    from resumable_recorder import read_manifest, read_timestamps, join_session
    recs = read_manifest(sd / "manifest.jsonl")
    ts = read_timestamps(sd / "timestamps.bin")
    t0 = recs[0]["t0_ns"]
    lost = sorted({f for r in recs if r["type"] == "resume" for f in r["lost_frames"]})
    segs = sorted(sd.glob("seg_*.mkv"))
    seg_frames = [cc.ffprobe_count(str(s))["frames"] for s in segs]
    jp = cc.load_jpegs(cc.DEFAULT_SET, 891)
    pkts = []
    for s in segs:
        with av.open(str(s)) as c:
            st = c.streams.video[0]
            for p in c.demux(st):
                if p.size:
                    pkts.append((int(p.pts), bytes(p) if payload == "mjpeg" else None))
    fns = [t[0] for t in ts]
    res = {"segments": len(segs), "frames_per_segment": seg_frames, "video_frames": sum(seg_frames),
           "timestamp_records": len(ts), "session_closed": recs[-1]["type"] == "session_closed",
           "resumes": sum(1 for r in recs if r["type"] == "resume"), "lost_frames": lost,
           "frame_numbers_unique_increasing": all(b > a for a, b in zip(fns, fns[1:])),
           "gaps_all_listed_as_lost": set(range(0, (fns[-1] + 1) if fns else 0)) - set(fns) <= set(lost),
           "video_eq_timestamps": sum(seg_frames) == len(ts) == len(pkts)}
    if len(pkts) == len(ts):
        res["pts_match_capture_ns"] = all(p[0] == (t[1] - t0) // 1_000_000 for p, t in zip(pkts, ts))
        if payload == "mjpeg":
            res["byte_exact"] = sum(1 for p, t in zip(pkts, ts) if p[1] == jp[t[0] % len(jp)])
    j = join_session(sd, sd / "joined.mkv")
    res["joined"] = j
    res["joined_ffprobe_frames"] = cc.ffprobe_count(str(sd / "joined.mkv"))["frames"]
    gaps = [(b[1] - a[1]) / 1e6 for a, b in zip(ts, ts[1:])]
    res["max_capture_gap_ms"] = round(max(gaps), 1) if gaps else None
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--child", nargs=4, default=None)
    a = ap.parse_args()
    if a.child:
        sd, payload, n, seg = a.child
        child(sd, payload, int(n), float(seg))
        return
    base = cc.MEDIA / "resumable"
    cc.rm(base)
    base.mkdir(parents=True)
    out = {"env": cc.env_versions(), "scenarios": []}

    def scen(name, payload, steps, plseed=None):
        sd = base / name
        log = []
        for i, (n, kill_at) in enumerate(steps):
            r = run_child(sd, payload, n, kill_at)
            log.append(r)
            if plseed is not None and i == 0:
                log.append({"powerloss": powerloss(sd, plseed)})
        v = verify(sd, payload)
        out["scenarios"].append({"name": name, "payload": payload, "steps": log, "verify": v})
        print(name, json.dumps(v), flush=True)
        (cc.RES / "resumable_demo.json").write_text(json.dumps(out, indent=1, default=str))

    scen("kill_mid_segment", "mjpeg", [(600, 170), (90, None)])
    scen("kill_after_rollover", "mjpeg", [(600, 121), (60, None)])
    scen("double_crash", "mjpeg", [(600, 100), (600, 75), (60, None)])
    for seed in range(5):
        scen(f"powerloss_{seed}", "mjpeg", [(600, 170), (60, None)], plseed=seed)
    scen("ffv1_kill_mid", "ffv1", [(600, 170), (90, None)])
    L = ["# Resumable recorder prototype - functional results (generated by run_resumable_demo.py)", "",
         "Segment length 2 s, 30 fps pacing, corpus c930e_720p_flash. 'kill' = Popen.kill() (TerminateProcess).", "",
         "| scenario | payload | killed at frame (reported) | recovered/repaired seg frames | lost frames | segments | video frames | ts records | video==ts | unique+increasing | gaps listed | pts==capture | byte-exact | joined frames | max gap ms |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in out["scenarios"]:
        v = s["verify"]
        kills = [str(x.get("last_frame_reported")) for x in s["steps"] if "closed" in x and not x["closed"]]
        recov = [str(x["recovery"]["frames_in_repaired_segment"]) for x in s["steps"] if x.get("recovery") and x["recovery"]["was_incomplete"]]
        L.append(f"| {s['name']} | {s['payload']} | {','.join(kills)} | {','.join(recov)} | {len(v['lost_frames'])} {v['lost_frames'][:6]} | "
                 f"{v['segments']} | {v['video_frames']} | {v['timestamp_records']} | {v['video_eq_timestamps']} | "
                 f"{v['frame_numbers_unique_increasing']} | {v['gaps_all_listed_as_lost']} | {v.get('pts_match_capture_ns')} | "
                 f"{v.get('byte_exact', 'n/a')} | {v['joined_ffprobe_frames']} | {v['max_capture_gap_ms']} |")
    (cc.RES / "resumable_demo.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
