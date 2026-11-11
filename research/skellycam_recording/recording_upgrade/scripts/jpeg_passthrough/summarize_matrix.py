"""Turn mux_matrix.json into compact Markdown tables (mux_matrix.md).

Run: .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/jpeg_passthrough/summarize_matrix.py [in.json] [out.md]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jp_common as C  # noqa: E402


def g(d, *ks, default=""):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def be(c):
    if not c:
        return "-"
    return "yes" if c.get("byte_exact_all") else f"NO {c.get('in_order_matches')}/{c.get('n_in')} (out {c.get('n_out')})"


def ts(t):
    if not t:
        return "-"
    s = f"{t['max_abs_err_us']:.0f}"
    if t.get("max_abs_err_vs_next_us") is not None and t["max_abs_err_vs_next_us"] < t["max_abs_err_us"] / 4:
        s += f" (vs next frame {t['max_abs_err_vs_next_us']:.0f})"
    if not t.get("strictly_increasing", True):
        s += " non-mono"
    return s


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else C.RESULTS / "mux_matrix.json"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".md")
    j = json.loads(src.read_text())
    rows = j["rows"]
    L = [f"# mux_matrix results ({src.name})", "", f"Generated from `{src.name}`; meta: `{json.dumps(j['meta'])}`", "",
         "Columns: write = writer result; bytes pyav / ffx = PyAV demux packets / `ffmpeg -c:v copy -f image2` files SHA-256-equal to input, in order;",
         "cv2 n = CAP_FFMPEG frames read (FRAME_COUNT prop); seek = CAP_PROP_POS_FRAMES+read equal to sequential frame k;",
         "ANY = backend chosen by cv2.VideoCapture(path) and its FRAME_COUNT; MSMF = frames read via CAP_MSMF; FMC = FreeMoCap VideoHelper frame_count / reads ok;",
         "ts err = max |reported - input| timestamp in us after aligning first frame (pyav pts, ffprobe pts_time, cv2 POS_MSEC).", ""]
    L += aggregate(rows)
    sets = []
    for r in rows:
        if r["set"] not in sets:
            sets.append(r["set"])
    for s in sets:
        L += [f"## {s}", "", "| writer/mode | container | write | file bytes | bytes pyav | bytes ffx | ffprobe nb_frames / pkts | cv2 n (prop) | seek | ANY backend (prop) | MSMF n | FMC count / reads ok | ts err pyav | ts err ffprobe | ts err cv2 | pyav decode errs |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in [x for x in rows if x["set"] == s]:
            w = r["write"]
            rd = r.get("readers", {})
            wcell = "ok" if w.get("ok") else ("FAIL: " + (w.get("error") or "; ".join(w.get("stderr_flags", [])))[:90]).replace("|", "/")
            cvf = rd.get("cv2_ffmpeg", {})
            cvcell = f"{cvf.get('frames_read', '-')} ({cvf.get('frame_count_prop', '-')})" if cvf.get("opened") else ("not opened" if cvf else "-")
            seek = f"{cvf.get('seek_exact')}/{cvf.get('seek_total')}" if "seek_total" in cvf else "-"
            an = rd.get("cv2_any", {})
            ancell = f"{an.get('backend', '-')} ({an.get('frame_count_prop', '-')})" if an.get("opened") else ("not opened" if an else "-")
            ms = rd.get("cv2_msmf", rd.get("cv2_images", {}))
            mscell = (str(ms.get("frames_read")) if ms.get("opened") else "not opened") if ms else "-"
            fm = rd.get("freemocap_videohelper", {})
            if "error" in fm:
                fmcell = "ERR " + fm["error"][:50]
            elif fm:
                fmcell = f"{fm.get('frame_count')} / {sum(1 for x in fm.get('reads', []) if x.get('ok') and x.get('match_cv2_sequential'))}/{len(fm.get('reads', []))}"
            else:
                fmcell = "-"
            fp = rd.get("ffprobe", {})
            fpcell = f"{fp.get('nb_frames', '-')} / {fp.get('nb_read_packets', '-')}" if fp.get("returncode") == 0 else ("ERR" if fp else "-")
            pv = rd.get("pyav", {})
            L.append("| " + " | ".join(str(x).replace("|", "/") for x in [
                f"{r['writer']}/{r['mode']}", r["container"], wcell, w.get("bytes", "-"), be(rd.get("pyav_bytes")), be(rd.get("ffmpeg_extract_bytes")),
                fpcell, cvcell, seek, ancell, mscell, fmcell, ts(rd.get("pyav_ts")), ts(rd.get("ffprobe_ts")), ts(rd.get("cv2_ffmpeg_ts")),
                pv.get("decode_error_count", "-")]) + " |")
        L.append("")
        hc = [(r["writer"], r["mode"], r["container"], r["readers"]["header_change_frame0"]) for r in rows
              if r["set"] == s and "header_change_frame0" in r.get("readers", {})]
        if hc:
            L += ["Header changes on frame 0 (ffmpeg extraction):", ""]
            for wtr, mode, c, h in hc:
                L.append(f"- {wtr}/{mode} {c}: in `{h['input']}` ({h['size_in']} B) -> out `{h['extracted']}` ({h['size_out']} B)")
            L.append("")
    dst.write_text("\n".join(L) + "\n")
    print("wrote", dst)


def aggregate(rows: list[dict]) -> list[str]:
    """One line per writer/mode/container across all sets."""
    keys = []
    for r in rows:
        k = (r["writer"], r["mode"], r["container"])
        if k not in keys:
            keys.append(k)
    L = ["## Across all sets", "",
         "| writer/mode | container | sets written / tried | byte-exact pyav / ffx (sets) | cv2 FRAME_COUNT == frames (sets) | cv2 frames read == frames (sets) | cv2 seek exact (sum) | FMC count == frames (sets) | MSMF read all (sets) | max ts err us pyav / ffprobe / cv2 | pyav decode errors |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in keys:
        rs = [r for r in rows if (r["writer"], r["mode"], r["container"]) == k]
        ok = [r for r in rs if r["write"].get("ok")]
        def cnt(f):
            return sum(1 for r in ok if f(r))
        rd = lambda r: r.get("readers", {})  # noqa: E731
        pb = cnt(lambda r: g(rd(r), "pyav_bytes", "byte_exact_all") is True)
        fb = cnt(lambda r: g(rd(r), "ffmpeg_extract_bytes", "byte_exact_all") is True)
        fc = cnt(lambda r: g(rd(r), "cv2_ffmpeg", "frame_count_prop") == r["frames_in"])
        fr = cnt(lambda r: g(rd(r), "cv2_ffmpeg", "frames_read") == r["frames_in"])
        se = sum(g(rd(r), "cv2_ffmpeg", "seek_exact", default=0) or 0 for r in ok)
        st = sum(g(rd(r), "cv2_ffmpeg", "seek_total", default=0) or 0 for r in ok)
        fm = cnt(lambda r: g(rd(r), "freemocap_videohelper", "frame_count") == r["frames_in"])
        ms = cnt(lambda r: g(rd(r), "cv2_msmf", "frames_read") == r["frames_in"] or g(rd(r), "cv2_images", "frames_read") == r["frames_in"])
        def mx(key):
            v = [g(rd(r), key, "max_abs_err_us", default=None) for r in ok]
            v = [x for x in v if isinstance(x, (int, float))]
            return f"{max(v):.0f}" if v else "-"
        de = sum(g(rd(r), "pyav", "decode_error_count", default=0) or 0 for r in ok)
        L.append(f"| {k[0]}/{k[1]} | {k[2]} | {len(ok)}/{len(rs)} | {pb} / {fb} | {fc} | {fr} | {se}/{st} | {fm} | {ms} | {mx('pyav_ts')} / {mx('ffprobe_ts')} / {mx('cv2_ffmpeg_ts')} | {de} |")
    return L + [""]


if __name__ == "__main__":
    main()
