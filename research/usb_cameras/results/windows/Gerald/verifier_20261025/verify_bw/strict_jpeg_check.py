# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==12.0.0", "simplejpeg==1.8.2", "numpy<2.3"]
# ///
"""Adversarial verifier: strict completeness check of saved MJPEG frames.

  uv run --script strict_jpeg_check.py RUNDIR [RUNDIR...] [--selftest] [--out OUT.json]

Per JPEG: (1) marker walk: SOF dims, DRI interval, every marker inside the entropy-coded segment (RSTn order mod 8,
expected RST count = ceil(MCUs / Ri) - 1), EOI position and trailing bytes; (2) Pillow full decode (warnings=error),
(3) libjpeg-turbo strict decode (simplejpeg strict=True; any libjpeg warning such as "Corrupt JPEG data: premature end" fails). Field names cv_* = strict decode.
--selftest: also builds corrupted copies of the first JPEG (drop 3072 B from the middle; drop 1020 B; zero-fill 3072 B)
and reports which checks detect them.
"""
from __future__ import annotations
import argparse, json, math, os, sys, tempfile, warnings
from pathlib import Path


def marker_walk(b: bytes) -> dict:
    r = {"soi": b[:2] == b"\xff\xd8", "w": None, "h": None, "dri": 0, "rst": 0, "rst_order_ok": True,
         "other_markers_in_scan": 0, "eoi_at": None, "trailing_after_eoi": None, "mcus": None, "expected_rst": None, "ok": False}
    i, n = 2, len(b)
    samp = []
    while i + 4 <= n:
        if b[i] != 0xFF:
            r["err"] = f"no marker at {i}"; return r
        m = b[i + 1]
        if m == 0xFF:
            i += 1; continue
        L = (b[i + 2] << 8) | b[i + 3]
        if m in (0xC0, 0xC1, 0xC2):
            r["h"] = (b[i + 5] << 8) | b[i + 6]; r["w"] = (b[i + 7] << 8) | b[i + 8]
            nc = b[i + 9]
            samp = [(b[i + 10 + 3 * k + 1] >> 4, b[i + 10 + 3 * k + 1] & 15) for k in range(nc)]
        elif m == 0xDD:
            r["dri"] = (b[i + 4] << 8) | b[i + 5]
        elif m == 0xDA:
            j = i + 2 + L
            exp = 0
            while j + 1 < n:
                if b[j] == 0xFF and b[j + 1] != 0x00:
                    mm = b[j + 1]
                    if 0xD0 <= mm <= 0xD7:
                        if (mm - 0xD0) != (exp % 8):
                            r["rst_order_ok"] = False
                        exp += 1; r["rst"] += 1; j += 2; continue
                    if mm == 0xD9:
                        r["eoi_at"] = j; r["trailing_after_eoi"] = n - (j + 2); break
                    if mm == 0xFF:
                        j += 1; continue
                    r["other_markers_in_scan"] += 1; j += 2; continue
                j += 1
            break
        i += 2 + L
    if samp and r["w"]:
        hmax = max(s[0] for s in samp); vmax = max(s[1] for s in samp)
        r["mcus"] = math.ceil(r["w"] / (8 * hmax)) * math.ceil(r["h"] / (8 * vmax))
        if r["dri"]:
            r["expected_rst"] = math.ceil(r["mcus"] / r["dri"]) - 1
    r["ok"] = bool(r["soi"] and r["eoi_at"] is not None and r["rst_order_ok"] and r["other_markers_in_scan"] == 0
                   and (r["expected_rst"] is None or r["rst"] == r["expected_rst"]))
    return r


def pil_ok(b: bytes) -> tuple[bool, str]:
    from PIL import Image
    import io
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            im = Image.open(io.BytesIO(b)); im.load()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:80]}"


def cv_decode(b: bytes) -> tuple[bool, str]:
    """libjpeg-turbo via simplejpeg with strict=True: any libjpeg warning (corrupt / premature end) raises."""
    import simplejpeg
    try:
        simplejpeg.decode_jpeg(b, strict=True)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:120]}"


def check(b: bytes) -> dict:
    mw = marker_walk(b)
    po, pwhy = pil_ok(b)
    co, cwhy = cv_decode(b)
    return {"marker_ok": mw["ok"], "pil_ok": po, "pil_why": pwhy, "cv_ok": co, "cv_why": cwhy, "walk": mw}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    doc = {"tool": "strict_jpeg_check", "command": " ".join(sys.argv), "runs": []}
    for rd in a.runs:
        d = Path(rd)
        jp = sorted(d.glob("frame_*.jpg"))
        fl = d / "frames.jsonl"
        nframes = sum(1 for l in fl.read_text().splitlines() if l.strip()) if fl.exists() else None
        agg = {"run": d.name, "frames_logged": nframes, "jpegs": len(jp), "marker_ok": 0, "pil_ok": 0, "cv_ok": 0,
               "cv_fail_examples": [], "marker_fail_examples": [], "dri_values": set(), "rst_counts": set(),
               "trailing_after_eoi": set(), "dims": set()}
        for p in jp:
            r = check(p.read_bytes())
            agg["marker_ok"] += r["marker_ok"]; agg["pil_ok"] += r["pil_ok"]; agg["cv_ok"] += r["cv_ok"]
            w = r["walk"]
            agg["dri_values"].add(w["dri"]); agg["rst_counts"].add(w["rst"]); agg["trailing_after_eoi"].add(w["trailing_after_eoi"])
            agg["dims"].add(f'{w["w"]}x{w["h"]}')
            if not r["cv_ok"] and len(agg["cv_fail_examples"]) < 3:
                agg["cv_fail_examples"].append({"file": p.name, "why": r["cv_why"]})
            if not r["marker_ok"] and len(agg["marker_fail_examples"]) < 3:
                agg["marker_fail_examples"].append({"file": p.name, "walk": w})
        for k in ("dri_values", "rst_counts", "trailing_after_eoi", "dims"):
            agg[k] = sorted(agg[k], key=str)[:20]
        if a.selftest and jp:
            b = jp[0].read_bytes(); mid = len(b) // 2
            st = {}
            for name, bb in {"original": b, "drop3072_mid": b[:mid] + b[mid + 3072:], "drop1020_mid": b[:mid] + b[mid + 1020:],
                             "zero3072_mid": b[:mid] + bytes(3072) + b[mid + 3072:],
                             "truncate_half_plus_eoi": b[:mid] + b"\xff\xd9"}.items():
                r = check(bb)
                st[name] = {"marker_ok": r["marker_ok"], "pil_ok": r["pil_ok"], "cv_ok": r["cv_ok"], "cv_why": r["cv_why"][:100],
                            "rst": r["walk"]["rst"], "expected_rst": r["walk"]["expected_rst"]}
            agg["selftest_on_" + jp[0].name] = st
        doc["runs"].append(agg)
        print(json.dumps({k: v for k, v in agg.items()}, default=str)[:1500])
    if a.out:
        Path(a.out).write_text(json.dumps(doc, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
