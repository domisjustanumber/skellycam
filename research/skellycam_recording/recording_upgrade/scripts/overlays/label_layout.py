"""Overlap-avoidance demo (G3): deterministic label placement + HUD lanes, vs today's fixed offsets.

Algorithm (identical to electron_harness/layout.js placeLabels):
  anchors processed in ascending id; for each, try 8 directions (E, NE, SE, N, S, W, NW, SW) x 3 rings;
  accept the first text box inside the image that intersects no placed label and no marker box;
  otherwise put it in the nearest side lane at the free slot closest to the anchor y, with a leader line;
  if both lanes are full, hide it and count it.
HUD lanes: the per-frame text panels (skellycam stamp, ChArUco status, undetected-corner list) are stacked in
one top-left column in a fixed order, each measured, so they cannot overlap; the undetected list is wrapped
into lines of a fixed width instead of one line per corner.

Overlap counts are geometry (deterministic). Text is measured with cv2.getTextSize (FONT_HERSHEY_SIMPLEX).
Cases: the synthetic 100-corner board (overlay_model.make_frames 'charuco') at 720p and 1080p, drawn three ways:
  A skellytracker CharucoAnnotator style:  "Corner#<id>" at (+1% H, +1% H), scale 0.5, thickness 2  (charuco_annotator.py:84-94)
  B freemocap-ui drawPoints style:         "<id>" at (+r+3, -r-3), r=5, ~10 px font  (image-overlay-system.ts:150-160)
  C placed:                                "<id>" placed by place_labels (same font as B)
Images (on a real corpus frame; they show the room) -> <raw>/overlays/layout/ ; counts -> results/overlays/label_layout.json/.md

Run from repo root:
  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/overlays/label_layout.py [--frames 60]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import overlay_model as M  # noqa: E402

RAW = Path("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109")
OUT = RAW / "overlays" / "layout"
RES = HERE.parents[1] / "results" / "overlays"
FONT = cv2.FONT_HERSHEY_SIMPLEX


def inter(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def place_labels(items, measure, bw, bh, marker_r=6, gap=3, rings=3):
    """items: [(id, x, y, text)] -> (placed [(id, x, y, w, h, lane, leader)], hidden [ids]). Boxes are top-left x,y,w,h."""
    items = sorted(items, key=lambda t: t[0])
    markers = [(x - marker_r, y - marker_r, 2 * marker_r, 2 * marker_r) for _, x, y, _ in items]
    dirs = [(1, 0), (1, -1), (1, 1), (0, -1), (0, 1), (-1, 0), (-1, -1), (-1, 1)]
    max_w = max((measure(t)[0] for *_, t in items), default=0)
    lane_w = max_w + 4
    lanes = {"L": [], "R": []}
    boxes, placed, hidden = [], [], []
    for cid, x, y, text in items:
        w, h = measure(text)
        best = None
        for ring in range(1, rings + 1):
            d = marker_r + gap + (ring - 1) * (h + gap)
            for dx, dy in dirs:
                cx, cy = x + dx * d, y + dy * d
                bx = cx if dx > 0 else cx - w if dx < 0 else cx - w / 2
                by = cy if dy > 0 else cy - h if dy < 0 else cy - h / 2
                b = (bx, by, w, h)
                if bx < 0 or by < 0 or bx + w > bw or by + h > bh:
                    continue
                if any(inter(o, b) for o in boxes) or any(inter(m, b) for m in markers):
                    continue
                best = b
                break
            if best:
                break
        if best:
            boxes.append(best)
            placed.append((cid, *best, None, None))
            continue
        done = False
        for side in (["R", "L"] if x > bw / 2 else ["L", "R"]):
            lx = 2 if side == "L" else bw - lane_w - 2
            slots = list(range(2, int(bh - 2 - h) + 1, h + 1))
            slots.sort(key=lambda s: (abs(s + h / 2 - y), s))
            for sy in slots:
                b = (lx, sy, w, h)
                if any(inter(o, b) for o in lanes[side]) or any(inter(o, b) for o in boxes):
                    continue
                lanes[side].append(b)
                boxes.append(b)
                placed.append((cid, *b, side, (x, y, lx + w if side == "L" else lx, sy + h / 2)))
                done = True
                break
            if done:
                break
        if not done:
            hidden.append(cid)
    return placed, hidden


def count(boxes, markers, bw, bh):
    ll = sum(1 for i in range(len(boxes)) for j in range(i + 1, len(boxes)) if inter(boxes[i], boxes[j]))
    lm = sum(1 for b in boxes for m in markers if inter(b, m))
    oob = sum(1 for b in boxes if b[0] < 0 or b[1] < 0 or b[0] + b[2] > bw or b[1] + b[3] > bh)
    return {"label_label": ll, "label_marker": lm, "out_of_bounds": oob}


def cv_measure(scale, thick):
    cache = {}

    def m(t):
        if t not in cache:
            (w, h), base = cv2.getTextSize(t, FONT, scale, thick)
            cache[t] = (w, h + base)
        return cache[t]
    return m


def hud_lane(panels, x0=5, y0=5, gap=4):
    """panels: [(name, [lines], scale, thick)] -> list of (name, box, line positions); stacked top-down, never overlapping."""
    out, y = [], y0
    for name, lines, scale, thick in panels:
        m = cv_measure(scale, thick)
        w = max(m(l)[0] for l in lines) + 8
        lh = max(m(l)[1] for l in lines) + 4
        box = (x0, y, w, lh * len(lines) + 4)
        out.append((name, box, [(x0 + 4, y + 2 + lh * (i + 1) - 4, l) for i, l in enumerate(lines)], scale, thick))
        y += box[3] + gap
    return out


def wrap_ids(prefix, ids, max_chars=34):
    lines, cur = [], prefix
    for i in ids:
        tok = f"{i},"
        if len(cur) + len(tok) > max_chars:
            lines.append(cur)
            cur = "  "
        cur += tok
    lines.append(cur.rstrip(","))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=60)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    rows = []
    for (w, h, corpus, frac) in ((1280, 720, "c930e_720p_flash", 0.55), (1920, 1080, "c930e_1080p", 0.55), (1280, 720, "c930e_720p_flash", 0.2)):
        frames = M.make_frames(a.frames, w, h, "charuco", board_frac=frac)
        styles = {
            "A_skellytracker_Corner#id": (cv_measure(0.5, 2), lambda x, y, tw, th: (x + max(1, int(h * 0.01)), y + max(1, int(h * 0.01)) - th), lambda i: f"Corner#{i}"),
            "B_freemocap_ui_id": (cv_measure(0.35, 1), lambda x, y, tw, th: (x + 8, y - 8 - th), lambda i: f"{i}"),
        }
        tot = {k: {"label_label": 0, "label_marker": 0, "out_of_bounds": 0} for k in list(styles) + ["C_placed_id"]}
        lane_n = hidden_n = 0
        determ = True
        undet_max = 0
        for fd in frames:
            pts = list(zip(fd.ch_ids.tolist(), fd.ch_xy.tolist()))
            markers = [(x - 6, y - 6, 12, 12) for _, (x, y) in pts]
            for k, (meas, pos, txt) in styles.items():
                bxs = []
                for cid, (x, y) in pts:
                    tw, th = meas(txt(cid))
                    px, py = pos(x, y, tw, th)
                    bxs.append((px, py, tw, th))
                c = count(bxs, markers, w, h)
                for kk in c:
                    tot[k][kk] += c[kk]
            meas = styles["B_freemocap_ui_id"][0]
            items = [(cid, x, y, str(cid)) for cid, (x, y) in pts]
            p1, hid = place_labels(items, meas, w, h)
            p2, _ = place_labels(items, meas, w, h)
            determ &= p1 == p2
            c = count([tuple(p[1:5]) for p in p1], markers, w, h)
            for kk in c:
                tot["C_placed_id"][kk] += c[kk]
            lane_n += sum(1 for p in p1 if p[5])
            hidden_n += len(hid)
            undet_max = max(undet_max, M.N_CORNERS - len(pts))
        n_labels = sum(len(fd.ch_ids) for fd in frames)
        rows.append({"res": f"{w}x{h} board {frac:.0%} of height", "frames": len(frames), "labels_total": n_labels, "counts": tot, "placed_in_lane": lane_n,
                     "hidden": hidden_n, "deterministic": determ, "max_undetected_in_a_frame": undet_max})

        # today's "Undetected Corners" list: one line per id at y = 40 + i*20 (charuco_annotator.py:163-187)
        fits = (h - 40) // 20 + 1
        rows[-1]["undetected_list_lines_that_fit_in_frame_height"] = int(fits)

        # images for frame 0 on a real corpus frame
        fd = frames[0]
        base = cv2.imdecode(np.fromfile(RAW / "corpus" / corpus / "frame_000000.jpg", np.uint8), cv2.IMREAD_COLOR)
        img_a = base.copy()
        M.burn_in(img_a, M.primitives(fd, w, h))  # skellytracker-style (Corner#id + undetected list) + skellycam stamp
        # the FreeMoCap UI charuco info panel sits at fillRect(5,5,500,85) (charuco-overlay-renderer.ts:164-165) over the stamp at (10,40)
        cv2.rectangle(img_a, (5, 5), (505, 90), (40, 40, 40), 1)
        cv2.imwrite(str(OUT / f"A_today_{h}p_board{int(frac*100)}.png"), img_a)
        img_c = base.copy()
        meas = styles["B_freemocap_ui_id"][0]
        items = [(cid, x, y, str(cid)) for cid, (x, y) in zip(fd.ch_ids.tolist(), fd.ch_xy.tolist())]
        placed, hid = place_labels(items, meas, w, h)
        for mid, c in fd.aruco:
            cv2.polylines(img_c, [c.astype(np.int32)], True, (0, 255, 0), 2)
        for cid, (x, y) in zip(fd.ch_ids.tolist(), fd.ch_xy.tolist()):
            cv2.drawMarker(img_c, (int(x), int(y)), (255, 0, 255), cv2.MARKER_DIAMOND, 10, 2)
        for cid, bx, by, bw_, bh_, lane, leader in placed:
            if leader:
                cv2.line(img_c, (int(leader[0]), int(leader[1])), (int(leader[2]), int(leader[3])), (0, 200, 0), 1)
            cv2.putText(img_c, str(cid), (int(bx), int(by + bh_ - 3)), FONT, 0.35, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img_c, str(cid), (int(bx), int(by + bh_ - 3)), FONT, 0.35, (0, 255, 0), 1, cv2.LINE_AA)
        undet = sorted(set(range(M.N_CORNERS)) - set(fd.ch_ids.tolist()))
        panels = [("stamp", [fd.stamp], 0.6, 1),
                  ("charuco", [f"Charuco: {len(fd.ch_ids)}/{M.N_CORNERS} | ArUco: {len(fd.aruco)}"], 0.5, 1),
                  ("undetected", wrap_ids("Undetected: ", undet), 0.45, 1)]
        lane = hud_lane(panels)
        bxs = [b for _, b, *_ in lane]
        rows[-1]["hud_panels_overlapping_pairs"] = sum(1 for i in range(len(bxs)) for j in range(i + 1, len(bxs)) if inter(bxs[i], bxs[j]))
        for name, (x0, y0, bw_, bh_), lines, scale, thick in lane:
            sub = img_c[int(y0):int(y0 + bh_), int(x0):int(x0 + bw_)]
            sub[:] = (sub * 0.35).astype(np.uint8)
            for lx, ly, t in lines:
                cv2.putText(img_c, t, (int(lx), int(ly)), FONT, scale, (230, 230, 230), thick, cv2.LINE_AA)
        cv2.imwrite(str(OUT / f"C_placed_{h}p_board{int(frac*100)}.png"), img_c)
    (RES / "label_layout.json").write_text(json.dumps(rows, indent=1))
    md = ["| res | frames | labels | style | label-label overlaps | label-marker overlaps | out of bounds |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        for k, c in r["counts"].items():
            md.append(f"| {r['res']} | {r['frames']} | {r['labels_total']} | {k} | {c['label_label']} | {c['label_marker']} | {c['out_of_bounds']} |")
    md.append("")
    for r in rows:
        md.append(f"- {r['res']}: placed in side lane {r['placed_in_lane']}, hidden {r['hidden']}, deterministic {r['deterministic']}, "
                  f"HUD panels overlapping pairs {r['hud_panels_overlapping_pairs']}; today's undetected list fits {r['undetected_list_lines_that_fit_in_frame_height']} lines "
                  f"(max undetected in a frame here {r['max_undetected_in_a_frame']})")
    (RES / "label_layout.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
