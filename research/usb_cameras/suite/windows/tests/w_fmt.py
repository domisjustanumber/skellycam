"""W-FMT: every format / size / rate per API vs the USB descriptors (plan section 2.1, 6.2; windows_mf_vs_ds W-FMT-1a).

Per camera (the Kiyo included):
  * descriptors: helpers/win_descriptors.py (shared per-run cache; EP0 GET_DESCRIPTOR in a child under camlock);
  * MF: ``wincam formats --api mf`` (activates the source; native types from a converters-off reader; the NV12 that
    MF synthesizes right before each MJPG type is flagged by wincam);
  * DS: ``wincam formats --api ds`` (binds the filter; IAMStreamConfig caps de-duplicated into modes, plus
    IAMVideoControl::GetFrameRateList per caps entry; every pin with its category).
Both wincam calls run under camlock with --timeout-ms inside and a process timeout outside.

Every list is normalized to (fourcc, width, height, frame interval in 100 ns) per capture stream/pin and diffed:
sizes per format, discrete rates per size (DS ranges vs the real rate list), modes missing or extra per API,
synthesized types, continuous vs discrete intervals, still pins/streams, DS VIH/VIH2 duplication. MJPEG is the
focus (G-MJPEG coverage); <out_dir>/mjpeg_modes.json lists every descriptor MJPEG mode per camera key with whether
MF and DS offer it (for W-MJPEG).
Also: identity cross-check of discovery's key (instance-ID serial) against the serial string descriptor.
Verdict: "fmt_equivalence" (answers "same resolutions in DS and MF?"): yes = MJPEG sizes and discrete rates equal in
descriptors, MF native types and DS rate lists on every camera.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402
from common import identity, results  # noqa: E402

TEST_ID = "W-FMT"
TOL = 3  # 100 ns units: MF fps_num/den and DS intervals round differently


def slug(c: dict) -> str:
    n = re.sub(r"[^a-z0-9]+", "_", (c.get("name") or "camera").lower()).strip("_")[:24]
    return f"{n}_{c.get('vid')}-{c.get('pid')}" + ("" if not c.get("serial") else "")


def _fourcc(fmt: dict) -> str:
    f = (fmt.get("format") or "").upper()
    if f == "MJPEG":
        return "MJPG"
    return (fmt.get("fourcc") or f or "?").upper()


def descriptor_modes(desc: dict | None) -> dict:
    """{stream_index: {"modes": set((fourcc,w,h,interval)), "continuous": [...], "still": [...]}}"""
    out: dict = {}
    cfg = (desc or {}).get("configuration") or {}
    for si, s in enumerate(((cfg.get("uvc") or {}).get("streaming_interfaces") or [])):
        rec = out.setdefault(si, {"interface": s.get("bInterfaceNumber"), "modes": set(), "continuous": [],
                                  "still": [], "transport": s.get("transport")})
        for f in s.get("formats") or []:
            fcc = _fourcc(f)
            for fr in f.get("frames") or []:
                w, h = fr.get("wWidth"), fr.get("wHeight")
                if fr.get("interval_type") == "continuous":
                    rec["continuous"].append({"fourcc": fcc, "w": w, "h": h, "min": fr.get("dwMinFrameInterval"),
                                              "max": fr.get("dwMaxFrameInterval"),
                                              "step": fr.get("dwFrameIntervalStep")})
                    for iv in (fr.get("dwMinFrameInterval"), fr.get("dwMaxFrameInterval")):
                        if iv:
                            rec["modes"].add((fcc, w, h, int(iv)))
                else:
                    for iv in fr.get("dwFrameInterval") or []:
                        rec["modes"].add((fcc, w, h, int(iv)))
            if f.get("still_image_frame"):
                rec["still"].append({"fourcc": fcc, **{k: v for k, v in f["still_image_frame"].items()}})
    return out


def mf_modes(obj: dict | None) -> dict:
    out: dict = {}
    for s in (obj or {}).get("reader_streams") or []:
        si = s.get("stream_index")
        rec = out.setdefault(si, {"modes": set(), "synthesized": set(), "other_subtypes": {}})
        for t in s.get("types") or []:
            num, den = t.get("fps_num") or 0, t.get("fps_den") or 1
            iv = int(round(1e7 * den / num)) if num else 0
            key = ((t.get("subtype") or "?").upper(), t.get("width"), t.get("height"), iv)
            if any("synthesized" in fl for fl in t.get("flags") or []):
                rec["synthesized"].add(key)
            else:
                rec["modes"].add(key)
    cats = {st.get("stream_index"): (st.get("attributes") or {}).get("MF_DEVICESTREAM_STREAM_CATEGORY")
            for st in (obj or {}).get("streams") or []}
    for si, r in out.items():
        r["category"] = cats.get(si)
    return out


def ds_modes(obj: dict | None) -> dict:
    out: dict = {}
    for p in (obj or {}).get("pins") or []:
        if p.get("direction") != "output":
            continue
        rec = out.setdefault(p.get("pin_index"), {"name": p.get("name"), "category": p.get("category_name"),
                                                  "modes": set(), "range_only": [], "caps_count": p.get("caps_count"),
                                                  "mode_count": p.get("mode_count"), "header_kinds": set()})
        for md in p.get("modes") or []:
            fcc = (md.get("subtype") or "?").upper()
            w, h = md.get("width"), md.get("height")
            rec["header_kinds"].update(md.get("header_kinds") or [])
            ivs = md.get("frame_rate_list_100ns") or []
            if ivs:
                for iv in ivs:
                    rec["modes"].add((fcc, w, h, int(iv)))
            else:
                rec["range_only"].append({"fourcc": fcc, "w": w, "h": h, "min": md.get("min_interval_100ns"),
                                          "max": md.get("max_interval_100ns")})
                for iv in (md.get("min_interval_100ns"), md.get("max_interval_100ns")):
                    if iv:
                        rec["modes"].add((fcc, w, h, int(iv)))
    return out


def _union(d: dict, field: str = "modes", category_pat: str | None = None) -> set:
    s = set()
    for r in d.values():
        if category_pat and not re.search(category_pat, str(r.get("category") or ""), re.I):
            continue
        s |= set(r.get(field) or set())
    return s


def _match(a: set, b: set) -> tuple[set, set]:
    """(in a not b, in b not a) with interval tolerance."""
    def near(x, pool):
        return any(x[0] == y[0] and x[1] == y[1] and x[2] == y[2] and abs(x[3] - y[3]) <= TOL for y in pool)
    return {x for x in a if not near(x, b)}, {y for y in b if not near(y, a)}


def _fps(iv: int) -> float:
    return round(1e7 / iv, 3) if iv else 0.0


def _fmt_modes(s: set) -> list[str]:
    return [f"{f} {w}x{h}@{_fps(iv):g}" for f, w, h, iv in sorted(s, key=lambda x: (x[0], -x[1] * x[2], x[3]))]


def _sizes(s: set, fcc: str | None = None) -> set:
    return {(f, w, h) for f, w, h, _ in s if fcc is None or f == fcc}


def run(ctx) -> dict:
    def body(res, m, v, e):
        tdir = ctx.test_dir(TEST_ID)
        desc = U.get_descriptors(ctx)
        per_cam, mjpeg_index = [], {}
        all_equal_mjpeg = True
        for c in ctx.cameras:
            rec: dict = {"key": c["key"], "name": c.get("name"), "is_kiyo": c.get("is_kiyo")}
            d = U.descriptor_for(desc, c)
            rec["descriptor_errors"] = (d or {}).get("errors")
            dm = descriptor_modes(d)
            # identity cross-check: key from the serial string descriptor vs discovery's key
            sn = (d or {}).get("serial_number")
            k2 = identity.camera_key(c["vid"], c["pid"], sn, c.get("port_path"),
                                     [(x["vid"], x["pid"], (U.descriptor_for(desc, x) or {}).get("serial_number"))
                                      for x in ctx.cameras])
            rec["identity_cross_check"] = {"serial_string_descriptor": sn, "key_from_descriptor_serial": k2,
                                           "discovery_key": c["key"], "agree": k2 == c["key"]}
            if k2 != c["key"]:
                e.append(f"{c['name']}: key from the serial string ({k2}) differs from discovery's key ({c['key']})")
            outs = {}
            for api, dev in (("mf", c.get("mf_symlink")), ("ds", c.get("ds_path"))):
                if not dev:
                    rec[f"{api}_error"] = f"no {api} device path"
                    outs[api] = None
                    continue
                argv = [str(ctx.wincam), "formats", "--api", api, "--device", dev, "--timeout-ms", "8000"]
                obj, run_rec = U.run_json(ctx, argv, 45, cam=True)
                rec[f"{api}_run"] = run_rec
                outs[api] = obj
                if obj is not None:
                    results.write_json(tdir / f"{slug(c)}_formats_{api}.json", obj)
                    if obj.get("error"):
                        rec[f"{api}_error"] = obj["error"]
                if obj is None or run_rec["rc"] not in (0,):
                    e.append({"camera": c["key"], "api": api, "rc": run_rec["rc"], "timed_out": run_rec["timed_out"],
                              "error": (obj or {}).get("error")})
            mm, dd = mf_modes(outs["mf"]), ds_modes(outs["ds"])
            D = _union(dm)
            # capture streams/pins only (still streams/pins are compared with the descriptor still frames below)
            MFall = {x for si, r in mm.items() if not re.search("STILL", str(r.get("category") or ""), re.I)
                     for x in r["modes"]}
            DSall = {x for pi, r in dd.items() if not re.search("STILL", str(r.get("category") or ""), re.I)
                     for x in r["modes"]}
            MFstill = _union(mm, category_pat="STILL")
            DSstill = _union(dd, category_pat="STILL")
            syn = _union(mm, "synthesized")
            cmp = {}
            for name, other in (("mf", MFall), ("ds", DSall)):
                miss, extra = _match(D, other)
                cmp[name] = {"missing_vs_descriptor": _fmt_modes(miss), "extra_vs_descriptor": _fmt_modes(extra),
                             "n_missing": len(miss), "n_extra": len(extra),
                             "mjpeg_missing": _fmt_modes({x for x in miss if x[0] == "MJPG"}),
                             "mjpeg_extra": _fmt_modes({x for x in extra if x[0] == "MJPG"})}
            miss, extra = _match(MFall, DSall)
            cmp["mf_vs_ds"] = {"only_mf": _fmt_modes(miss), "only_ds": _fmt_modes(extra)}
            d_still = sorted({(sz.get("wWidth"), sz.get("wHeight")) for r in dm.values() for st in r["still"]
                              for sz in st.get("sizes") or []})
            rec["still"] = {"descriptor_still_sizes": d_still,
                            "mf_still_stream_sizes": sorted({(w, h) for _, w, h, _ in MFstill}),
                            "ds_still_pin_sizes": sorted({(w, h) for _, w, h, _ in DSstill}),
                            "mf_still_modes": _fmt_modes(MFstill), "ds_still_modes": _fmt_modes(DSstill)}
            rec["still"]["sizes_equal"] = (set(map(tuple, d_still)) == set(rec["still"]["mf_still_stream_sizes"])
                                           == set(rec["still"]["ds_still_pin_sizes"]))
            dj, mj, sj = ({x for x in s if x[0] == "MJPG"} for s in (D, MFall, DSall))
            mjpeg_eq = bool(dj) and not any(_match(dj, mj)) and not any(_match(dj, sj))
            mjpeg_sizes = {"descriptor": sorted({(w, h) for _, w, h in _sizes(dj)}, key=lambda x: -x[0] * x[1]),
                           "mf": sorted({(w, h) for _, w, h in _sizes(mj)}, key=lambda x: -x[0] * x[1]),
                           "ds": sorted({(w, h) for _, w, h in _sizes(sj)}, key=lambda x: -x[0] * x[1])}
            rec.update(
                counts={"descriptor_modes": len(D), "mf_native_capture_modes": len(MFall),
                        "mf_still_modes": len(MFstill), "mf_synthesized": len(syn), "ds_capture_modes": len(DSall),
                        "ds_still_modes": len(DSstill),
                        "descriptor_mjpeg_modes": len(dj), "mf_mjpeg_types": len(mj), "ds_mjpeg_modes": len(sj),
                        "mjpeg_sizes": {k: len(x) for k, x in mjpeg_sizes.items()}},
                formats={"descriptor": sorted({f for f, *_ in D}), "mf": sorted({f for f, *_ in MFall}),
                         "ds": sorted({f for f, *_ in DSall})},
                mjpeg_equal_everywhere=mjpeg_eq, mjpeg_sizes=mjpeg_sizes, diff=cmp,
                synthesized_types=_fmt_modes(syn)[:12], synthesized_subtypes=sorted({f for f, *_ in syn}),
                descriptor_streams={si: {"interface": r["interface"], "n_modes": len(r["modes"]),
                                         "continuous": r["continuous"], "still": r["still"],
                                         "transport": r["transport"]} for si, r in dm.items()},
                mf_streams={si: {"category": r.get("category"), "n_native": len(r["modes"]),
                                 "n_synthesized": len(r["synthesized"]),
                                 "subtypes": sorted({f for f, *_ in r["modes"] | r["synthesized"]})}
                            for si, r in mm.items()},
                ds_pins={pi: {"name": r["name"], "category": r["category"], "caps_count": r["caps_count"],
                              "mode_count": r["mode_count"], "header_kinds": sorted(r["header_kinds"]),
                              "range_only_modes": r["range_only"], "n_modes_with_rates": len(r["modes"])}
                         for pi, r in dd.items()},
                ds_any_unknown_pin_category=(outs["ds"] or {}).get("any_unknown_pin_category"))
            if dj:
                all_equal_mjpeg &= mjpeg_eq
            else:
                all_equal_mjpeg = False
            mjpeg_index[c["key"]] = [{"width": w, "height": h, "fps": _fps(iv), "interval_100ns": iv,
                                      "in_mf": not _match({(f, w, h, iv)}, mj)[0],
                                      "in_ds": not _match({(f, w, h, iv)}, sj)[0]}
                                     for f, w, h, iv in sorted(dj, key=lambda x: (-x[1] * x[2], x[3]))]
            per_cam.append(rec)
        m["cameras"] = per_cam
        results.write_json(ctx.out_dir / "mjpeg_modes.json", {"utc": results.utc_now_iso(), "source": "W-FMT "
                           "(descriptor MJPEG frame x interval, with MF/DS availability)", "cameras": mjpeg_index})
        m["mjpeg_modes_file"] = str(ctx.out_dir / "mjpeg_modes.json")
        crit = [{"criterion": f"{r['name']}: MJPEG sizes and discrete rates equal in descriptors, MF and DS",
                 "met": r["mjpeg_equal_everywhere"],
                 "detail": {"counts": r["counts"], "mf_missing": r["diff"]["mf"]["missing_vs_descriptor"][:8],
                            "ds_missing": r["diff"]["ds"]["missing_vs_descriptor"][:8]}} for r in per_cam]
        crit.append({"criterion": "MF synthesized NV12 types flagged (Trap 1: select MJPG by subtype)",
                     "met": None, "detail": {r["name"]: r["counts"]["mf_synthesized"] for r in per_cam}})
        crit.append({"criterion": "(informational, not rated) every format equal: descriptor vs MF vs DS capture modes",
                     "met": all(not r["diff"]["mf"]["n_missing"] and not r["diff"]["mf"]["n_extra"] and
                                not r["diff"]["ds"]["n_missing"] and not r["diff"]["ds"]["n_extra"] for r in per_cam),
                     "detail": {r["name"]: {"mf_missing": r["diff"]["mf"]["missing_vs_descriptor"][:6],
                                            "mf_extra": r["diff"]["mf"]["extra_vs_descriptor"][:6],
                                            "ds_missing": r["diff"]["ds"]["missing_vs_descriptor"][:6],
                                            "ds_extra": r["diff"]["ds"]["extra_vs_descriptor"][:6]} for r in per_cam}})
        crit.append({"criterion": "(informational) still-image sizes equal in descriptors, MF still stream, DS still pin",
                     "met": all(r["still"]["sizes_equal"] for r in per_cam),
                     "detail": {r["name"]: r["still"] for r in per_cam if r["still"]["descriptor_still_sizes"]
                                or r["still"]["mf_still_stream_sizes"] or r["still"]["ds_still_pin_sizes"]}})
        tested = [r for r in per_cam if r["counts"]["descriptor_mjpeg_modes"]]
        v["fmt_equivalence"] = {"rating": ("yes" if tested and all_equal_mjpeg and len(tested) == len(per_cam)
                                           else "partial" if any(r["mjpeg_equal_everywhere"] for r in per_cam)
                                           else "no" if per_cam else "untested"),
                                "criteria": crit,
                                "evidence": {"note": "answers plan Q 'same resolutions in DS and MF?'; G-MJPEG "
                                                     "(bytes at every mode) is rated by W-MJPEG",
                                             "mjpeg_modes_file": m["mjpeg_modes_file"]}}
    return U.guarded(ctx, TEST_ID, body)


if __name__ == "__main__":
    sys.exit(U.standalone(run, TEST_ID))
