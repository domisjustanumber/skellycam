"""Classify what check_sync.py saw: per variant and panel (sync off / on), paused and 1x playback.

  python -I analyse.py <take dir> <runs dir> <summary.json>

Overlay classes for a displayed (image frame F, overlay frame A):
  match A == F | stale_untracked A < F, F has no tracking result | stale_tracked A < F, F has a result
  missing no overlay, F has a result | empty_ok no overlay, F has none | future A > F
  no_image nothing readable drawn (sync "waiting" state or blank) | garbled overlay unreadable
Image check: F == last frame whose log_time <= playhead.
"""
import bisect, json, sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

take = json.loads((Path(sys.argv[1]) / "take.json").read_text())
runs = Path(sys.argv[2])
arrival = take["arrival"]
PANELS = ("Image!off", "Image!on")


def ph_ns(text):
    try:
        return int(Decimal(text) * 10**9)
    except Exception:
        return None


def expected_img(t):
    return bisect.bisect_right(arrival, t) - 1


def classify(img, ann, tracked):
    if img is None:
        return "no_image"
    if ann is None:
        return "garbled"
    if ann == -1:
        return "missing" if img in tracked else "empty_ok"
    if ann == img:
        return "match"
    if ann > img:
        return "future"
    return "stale_tracked" if img in tracked else "stale_untracked"


assert classify(5, 5, {5}) == "match" and classify(6, 5, {5}) == "stale_untracked" and classify(6, -1, {6}) == "missing"
assert expected_img(arrival[3]) == 3 and expected_img(arrival[3] - 1) == 2

summary = {}
for f in sorted(runs.glob("*.json")):
    R = json.loads(f.read_text())
    v = R["variant"]
    tracked = {m[0] for m in take["variants"][v]["messages"] if m[2] == "result"}
    S = {"spec": R["spec"], "console_types": Counter(c[1] for c in R["console"]), "pageerrors": R["pageerrors"],
         "errors": sorted({c[2][:300] for c in R["console"] if c[1] == "error"}),
         "warnings": sorted({c[2][:200] for c in R["console"] if c[1] == "warning" and "GL Driver" not in c[2]}),
         "blocked": len(R["blocked"]), "cpu": R["cpu"], "raf": R.get("raf")}
    for pid in PANELS:
        P = {}
        # Paused
        cls, img_ok, examples, stale_age = Counter(), 0, [], []
        paused = [s for s in R["steps"] if s.get("label", "").startswith("paused_")]
        for s in paused:
            c = s["cur"].get(pid) or {}
            img, ann = c.get("img"), c.get("ann")
            k = classify(img, ann, tracked)
            cls[k] += 1
            exp = expected_img(ph_ns(s["ph"]))
            img_ok += img == exp
            if k.startswith("stale"):
                stale_age.append(img - ann)
            examples.append([s["ph"], exp, img, ann, k])
        P["paused"] = {"n": len(paused), "classes": dict(cls), "img_equals_playhead_frame": img_ok,
                       "max_stale_frames": max(stale_age, default=0), "samples": examples}
        # 1x playback window
        t_play = next(s["perf"] for s in R["steps"] if s.get("label") == "play")
        t_pause = next(s["perf"] for s in R["steps"] if s.get("label") == "pause")
        rows = [r for r in R.get("probe_log", []) if r[1] == pid and t_play + 500 <= r[0] <= t_pause]
        dur, seq, holds, lags = Counter(), [], [], []
        arrive, fut_runs, fut_t = Counter(), [], 0.0  # arrive: overlay class on the first row that shows each new image
        last_change = None
        for r, nxt in zip(rows, rows[1:] + [[t_pause, None, None, None]]):
            _, _, img, ann, ph = r
            dt = nxt[0] - r[0]
            k = classify(img, ann, tracked)
            dur[k] += dt
            if img is not None and (not seq or seq[-1] != img):
                arrive[k] += 1
            fut_t += dt if k == "future" else 0
            if k != "future" and fut_t:
                fut_runs.append(fut_t); fut_t = 0.0
            if img is not None:
                if not seq or seq[-1] != img:
                    if last_change is not None:
                        holds.append(r[0] - last_change)
                    seq.append(img); last_change = r[0]
                t = ph_ns(ph)
                if t:
                    lags.append(expected_img(t) - img)
        total = sum(dur.values()) or 1
        steps = Counter(b - a for a, b in zip(seq, seq[1:]))
        lags.sort()
        P["play"] = {"rows": len(rows), "seconds": round(total / 1000, 2),
                     "time_pct": {k: round(100 * d / total, 1) for k, d in dur.most_common()},
                     "on_image_arrival": dict(arrive.most_common()),
                     "future_run_ms_median_max": [round(sorted(fut_runs)[len(fut_runs) // 2]), round(max(fut_runs))] if fut_runs else None,
                     "distinct_images": len(seq), "first_last": [seq[0], seq[-1]] if seq else None,
                     "frame_steps": dict(sorted(steps.items())), "backwards_steps": sum(n for d, n in steps.items() if d < 0),
                     "image_fps": round(len(seq) / (total / 1000), 1),
                     "max_hold_ms": round(max(holds, default=0)), "median_hold_ms": round(sorted(holds)[len(holds) // 2]) if holds else None,
                     "lag_frames_median_max": [lags[len(lags) // 2], lags[-1]] if lags else None,
                     "image_sequence": seq}
        S[pid] = P
    summary[v] = S

Path(sys.argv[3]).write_text(json.dumps(summary, indent=1, default=dict))
for v, S in summary.items():
    for pid in PANELS:
        p, q = S[pid]["paused"], S[pid]["play"]
        print(f"{v:18s} {pid[6:]:3s} paused n={p['n']} img_ok={p['img_equals_playhead_frame']} {p['classes']} maxstale={p['max_stale_frames']}")
        print(f"{'':22s} play fps={q['image_fps']} imgs={q['distinct_images']} {q['first_last']} hold med/max={q['median_hold_ms']}/{q['max_hold_ms']}ms "
              f"lag={q['lag_frames_median_max']} back={q['backwards_steps']} {q['time_pct']}")
        print(f"{'':22s} on_arrival={q['on_image_arrival']} future runs med/max ms={q['future_run_ms_median_max']}")
    print(f"{'':22s} console={dict(S['console_types'])} pageerrors={len(S['pageerrors'])} errors={S['errors'][:2]}")
