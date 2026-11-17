"""The short, pasteable summary of a ``run_suite.py --plan`` run (summary.md top part, printed at the end).

Reads only the test result dicts the runner already holds (no camera access). Every lookup tolerates a missing
test, a skipped camera or an error: a missing value prints as '-'. Serial numbers appear here only as their form
(length, character class, usable); the exact strings stay in L-ID.json (skellyfileformat SFF-752 needs them).
"""
from __future__ import annotations

import re
from typing import Any

from common import identity
import v4l2


def g(d: Any, *path: Any, default: Any = None) -> Any:
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and -len(d) <= p < len(d):
            d = d[p]
        else:
            return default
        if d is None:
            return default
    return d


def num(x: Any, fmt: str = "{:.1f}") -> str:
    return fmt.format(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else "-"


def pct(x: Any) -> str:
    return f"{100 * x:.0f}%" if isinstance(x, (int, float)) else "-"


def kb(x: Any) -> str:
    return f"{x / 1024:.0f}k" if isinstance(x, (int, float)) else "-"


def serial_form(s: str | None) -> str:
    if not s:
        return "none"
    cls = ("hex" if re.fullmatch(r"[0-9A-Fa-f]+", s) else "alnum" if re.fullmatch(r"[0-9A-Za-z]+", s)
           else "other chars")
    ok, why = identity.serial_is_usable(s)
    return f"len {len(s)}, {cls}, {'usable' if ok else 'NOT usable: ' + str(why)}"


def per_cam(res: dict, key: str) -> dict:
    return g(res, "measurements", "cameras", key, default={}) or {}


def skip_text(ent: dict) -> str | None:
    return f"skipped ({ent.get('reason')})" if ent.get("skipped") else None


def mjpeg_lines(res: dict, cam: dict) -> list[str]:
    ent = per_cam(res, cam["key"])
    if not ent:
        return ["- native JPEG: - (L-MJPEG did not run)"]
    if skip_text(ent):
        return [f"- native JPEG: {skip_text(ent)}"]
    verdict = g(res, "verdicts", "G-MJPEG:raw_v4l2", "evidence", "per_camera", cam["key"], "rating", default="-")
    secs = g(res, "measurements", "seconds_per_mode", default=0) or 0
    out = [f"- native JPEG (V4L2 MJPG mmap, ctypes): **{verdict}**"]
    for m in ent.get("modes") or []:
        v = m.get("v4l2") or {}
        if m.get("skipped"):
            out.append(f"  - {m.get('mode')}: skipped ({m['skipped']})")
            continue
        c, ch, fm = v.get("counts") or {}, v.get("check") or {}, v.get("format") or {}
        fps_req = float(m["mode"].rsplit("@", 1)[1]) if "@" in (m.get("mode") or "") else 0
        bpf = ch.get("bytes_per_frame") or {}
        err = (v.get("error") or {}).get("message") or (v.get("error") or {}).get("errno_name")
        out.append(
            f"  - {m.get('mode')}: frames {v.get('frames', '-')}/{round(fps_req * secs)} expected, "
            f"fourcc {g(fm, 'returned', 'fourcc', default='-')} size_ok {v.get('size_ok')}, "
            f"SOI {pct(ch.get('soi_fraction'))} EOI {pct(ch.get('eoi_fraction'))} strict decode "
            f"{pct(ch.get('strict_ok_fraction'))} ({ch.get('n', 0)} decoded), "
            f"header SHA-1 {ch.get('n_distinct_header_sha1', '-')} distinct "
            f"(main {str(ch.get('dominant_header_sha1') or '-')[:12]}), "
            f"fps {num(v.get('fps_host'))} (buffer ts {num(v.get('fps_buffer_ts'))}), "
            f"seq missing {c.get('seq_missing', '-')}, error-flagged {c.get('error_flag', '-')}, "
            f"bytes/frame min {kb(bpf.get('min'))} med {kb(bpf.get('p50'))} p99 {kb(bpf.get('p99'))} "
            f"max {kb(bpf.get('max'))}" + (f"; ERROR {err}" if err else ""))
    return out


def cyc_line(res: dict, cam: dict) -> str:
    ent = per_cam(res, cam["key"])
    if not ent:
        return "- open/close: - (L-CYC did not run)"
    if skip_text(ent):
        return f"- open/close: {skip_text(ent)}"
    b = g(ent, "batches", "v4l2_inprocess", default={})
    s = b.get("summary") or {}
    t = s.get("timings_ms") or {}
    ff = t.get("first_frame_ms") or {}
    o2f = t.get("open_to_first_frame_ms") or {}
    fails = "; ".join(f"{f.get('count')}x {f.get('stage')} {f.get('name') or ''}".strip()
                      for f in s.get("failure_classes") or []) or "none"
    return (f"- open/close (V4L2 in-process, {s.get('n', '-')} cycles): {s.get('n_ok', '-')}/{s.get('n', '-')} ok; "
            f"STREAMON->first frame median {num(ff.get('p50'), '{:.0f}')} ms p95 {num(ff.get('p95'), '{:.0f}')} ms; "
            f"open->first frame median {num(o2f.get('p50'), '{:.0f}')} ms; failures: {fails}; health after: "
            f"{'ok' if g(ent, 'health_after', 'ok') else 'FAILED'}")


def ts_line(res: dict, cam: dict) -> str:
    ent = per_cam(res, cam["key"])
    if not ent:
        return "- timestamps: - (L-TS did not run)"
    if skip_text(ent):
        return f"- timestamps: {skip_text(ent)}"
    m = g(ent, "runs", "main", default={})
    if m.get("error") and not m.get("frames"):
        return f"- timestamps: no frames ({m.get('error')})"
    ck, gr, iv = m.get("clock") or {}, m.get("grid_buffer_ts") or {}, m.get("interval_ms") or {}
    fit = g(m, "frame_index_fit_soe_whole", "residual_stats_ms", default={})
    return (f"- timestamps ({m.get('mode')}, {m.get('frames')} frames): flags {ck.get('buffer_ts_flags')}, clock "
            f"**{ck.get('clock_name') or 'undetermined'}**, DQBUF minus stamp median "
            f"{num(ck.get('arrival_minus_buffer_ts_median_ms'), '{:.2f}')} ms; grid "
            f"{'yes ' + num(gr.get('step_ms'), '{:.3f}') + ' ms' if gr.get('quantized') else 'none found'} "
            f"(stamps in us); interval mean {num(iv.get('mean'), '{:.3f}')} sd {num(iv.get('std'), '{:.3f}')} ms; "
            f"jitter vs fitted period sd {num(fit.get('std'), '{:.3f}')} ms max {num(fit.get('max'), '{:.2f}')} ms; "
            f"seq drops {g(m, 'seq_drops', 'drops', default='-')}")


def ctrl_lines(res_list: dict, res_eff: dict, cam: dict) -> list[str]:
    walk = per_cam(res_list, cam["key"]).get("controls") or []
    want = ("auto_exposure", "exposure_time_absolute", "exposure_dynamic_framerate", "gain_automatic", "gain",
            "focus_automatic_continuous", "focus_absolute", "white_balance_automatic", "white_balance_temperature")
    by = {v4l2.CID_NAME.get(c["id"]): c for c in walk if c.get("id") is not None}
    listed = ", ".join(f"{w} [{by[w].get('min')}..{by[w].get('max')} cur {by[w].get('value')}]"
                       for w in want if w in by) or "none listed"
    absent = [w for w in want if w not in by]
    out = [f"- controls listed: {listed}" + (f"; absent: {', '.join(absent)}" if walk else "")]
    ent = per_cam(res_eff, cam["key"])
    if not ent:
        return out + ["- control effect: - (L-CTRL-EFFECT did not run)"]
    if skip_text(ent):
        return out + [f"- control effect: {skip_text(ent)}"]
    for name, e in (ent.get("experiments") or {}).items():
        t = (e.get("trials") or [{}])[-1]
        steps = ", ".join(num(x, "{:.1f}") for x in t.get("per_step") or [])
        out.append(f"- {name} manual (auto off): values {t.get('values')} readback ok {t.get('set_readback_ok')}, "
                   f"image {t.get('metric')} per step [{steps}] -> effect {t.get('effect_ok')}"
                   + (f"; error {t.get('error')}" if t.get("error") else ""))
    if not ent.get("experiments"):
        out.append("- control effect: no exposure/focus control to test")
    p = ent.get("persistence") or {}
    if p:
        out.append(f"- manual exposure after close/reopen: mode kept {p.get('manual_kept')}, value kept "
                   f"{p.get('exposure_kept')}")
    out.append(f"- control API path: {ent.get('api_path', '-')}; restore error: "
               f"{g(ent, 'restore', 'error') or 'none'}")
    return out


def multi_line(res: dict, cam: dict) -> str:
    runs = g(res, "measurements", "phase_a", default=[]) or []
    if not runs:
        return "- all cameras at once: - (L-MULTI did not run)"
    r = next((x for x in runs[0].get("results") or [] if x.get("camera") == cam["key"]), None)
    if r is None:
        return "- all cameras at once: not included (skipped, dead or no in-scope mode)"
    err = r.get("error") or {}
    return (f"- all cameras at once ({r.get('mode')}): frames {r.get('frames')} over {num(r.get('stream_seconds'))} s, "
            f"fps {num(r.get('fps'))}, seq missing {r.get('seq_missing', '-')}, error-flagged "
            f"{r.get('error_flag_frames', '-')}, granted alt {r.get('granted_alt')}, domain "
            f"{g(res, 'measurements', 'camera_domains', cam['key'], default='-')}"
            + (f"; FAILED {err.get('stage')} {err.get('errno_name') or err.get('message')} -> class "
               f"{g(r, 'classification', 'class', default='-')}" if not r.get("ok") else ""))


def identity_lines(res_id: dict, cam: dict) -> list[str]:
    ids = {i.get("key"): i for i in g(res_id, "measurements", "identity", default=[]) or []}
    i = ids.get(cam["key"], {})
    u = g(res_id, "measurements", "udev", cam["key"], default={}) or {}
    bus = next((e.get("bus_info") for e in g(res_id, "measurements", "v4l2_enum", "first_run", default=[]) or []
                if e.get("node") == cam.get("node") and e.get("bus_info")), None)
    return [f"- identity: key `{cam['key']}` ({cam.get('key_kind')}); serial {serial_form(cam.get('serial'))}; "
            f"port_path `{cam.get('port_path')}`; sysfs `{cam.get('usb_name')}` bus {cam.get('busnum')} "
            f"devnum {cam.get('devnum')}; speed {cam.get('speed')}",
            f"- OS ids: node {cam.get('node')} (meta {cam.get('meta_node')}); QUERYCAP bus_info `{bus}`; udev "
            f"ID_PATH `{u.get('ID_PATH')}`; by-path {i.get('by_path') or cam.get('by_path')}; by-id "
            f"{len(i.get('by_id') or cam.get('by_id') or [])} link(s) (exact names in L-ID.json)"]


def env_lines(done: dict, run_info: dict, ctx) -> list[str]:
    env = run_info.get("environment") or {}
    os_ = env.get("os") or {}
    m = g(done, "L-ENV", "measurements", default={}) or {}
    sess = m.get("session") or {}
    pk = "; ".join(x for x in (g(m, "packages", "dpkg", default=[]) or [])
                   if x.startswith(("pipewire ", "wireplumber ")))
    desk = g(done, "L-DESK", "measurements", default={}) or {}
    holders = sorted({h.get("comm") for c in (desk.get("cameras") or {}).values()
                      for h in g(c, "busy", "other_holders", default=[]) or []})
    access = sorted({c.get("access_via") for c in (desk.get("cameras") or {}).values()})
    pw = desk.get("pipewire_video_objects")
    lines = [f"- OS: {g(os_, 'os_release', 'PRETTY_NAME', default='-')}; kernel {os_.get('kernel')}; "
             f"session {g(os_, 'session', 'XDG_SESSION_TYPE', default='none')}"
             f"{' (SSH)' if sess.get('ssh') else ''}; Python {env.get('python')}; packages {env.get('packages')}",
             f"- uvcvideo parameters (read only): {g(m, 'uvcvideo', 'parameters', default='-')}",
             f"- permissions: camera access via {', '.join(map(str, access)) or '-'}; video group "
             f"{sess.get('in_video_group')}; other processes holding cameras: {', '.join(map(str, holders)) or 'none'}"
             f"; PipeWire video objects {len(pw) if isinstance(pw, list) else 'pw-dump not installed'}"
             + (f"; {pk}" if pk else "")]
    if any(c.get("access_via") == "none" for c in (desk.get("cameras") or {}).values()):
        lines.append("- **PERMISSION PROBLEM: at least one camera node is not writable by this user** (run from the "
                     "desktop session, or add the user to the 'video' group); its results are not measurements")
    return lines


def build(ctx, done: dict[str, dict], run_info: dict) -> str:
    stamp = run_info.get("stamp")
    tests_run = list(done)
    n_err = sum(len(r.get("errors") or []) for r in done.values())
    L = [f"# skellycam capture-plan run, Linux, {stamp}", "",
         f"Tests: {', '.join(tests_run)} ({n_err} error record(s) in total; each test JSON has them).", ""]
    L += env_lines(done, run_info, ctx)
    if ctx.dead:
        for k, d in ctx.dead.items():
            L.append(f"- **Kiyo Pro {k} DEAD since {d.get('since_test')}** ({d.get('utc')}, after "
                     f"{d.get('stream_starts')} stream starts): skipped from then on; diagnostics in run.json")
    if ctx.suspect:
        L.append(f"- Kiyo Pro suspect at the end (one failed stream command): {sorted(ctx.suspect)}")
    topo = g(done, "L-TOPO", "measurements", default={}) or {}
    L.append(f"- USB topology: {len(topo.get('controllers') or [])} controller(s), "
             f"{len(topo.get('domains') or [])} bandwidth domain(s); camera domains: "
             + ", ".join(f"{c.get('name')} -> {c.get('domain')}" for c in topo.get("cameras") or []))
    for cam in ctx.cameras:
        L += ["", f"## {cam.get('name')} ({cam.get('vid')}:{cam.get('pid')}"
                  f"{', Kiyo Pro' if cam.get('is_kiyo') else ''})"]
        L += identity_lines(done.get("L-ID") or {}, cam)
        L += mjpeg_lines(done.get("L-MJPEG") or {}, cam)
        L.append(cyc_line(done.get("L-CYC") or {}, cam))
        L.append(ts_line(done.get("L-TS") or {}, cam))
        L += ctrl_lines(done.get("L-CTRL-LIST") or {}, done.get("L-CTRL-EFFECT") or {}, cam)
        L.append(multi_line(done.get("L-MULTI") or {}, cam))
    if not ctx.cameras:
        L += ["", "**No USB camera found in /sys/class/video4linux.**"]
    L += ["", "Not in this preset: PyAV/OpenCV/GStreamer legs, per-process and mode-switch cycles, L-FMT-NOGRAB, "
              "L-KIYO, UVC metadata/PTS/SCR, auto-mode toggles, bandwidth pairs."]
    # serial-based keys ('vid:pid:sn=<serial>') show only the serial's length here
    return re.sub(r"sn=([^\s`,;)\]]+)", lambda m: f"sn=<{len(m.group(1))} chars>", "\n".join(L)) + "\n"
