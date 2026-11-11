"""W-POLICY: OS policy that can alter what an API delivers (plan section 2.1 "Trap 2", windows_mf_vs_ds.md 1.3).

Read-only registry / service / PnP reads; opens no camera; writes nothing. Records:
  * Frame Server registration per camera (FrameServer\\SensorGroups entry matched by MF symbolic link: friendly
    name, CameraDeviceCompatFlags, SensorGroupProfiles, publish time);
  * how DirectShow reaches each camera: the interface key's CLSID (ksproxy {17CCA71B-...} = DirectShow talks to
    KS directly and bypasses Frame Server) and any EnableDshowRedirection value (interface keys, Enum hardware and
    function keys), CacheUVCControl, DMFT chain values (CameraDeviceMftClsidChain, EnablePlatformDmft,
    CameraPostProcessingPluginCLSID);
  * the DShow Bridge per-app list HKLM\\SOFTWARE\\Microsoft\\OEM\\DshowBridge\\*;
  * EnableFrameServerMode (Windows Media Foundation\\Platform, also WOW6432Node);
  * Settings page state: video rotation and the multi-app camera toggle. Their storage location is undocumented;
    a bounded search of the camera-related keys looks for value/key names (rotation, multi-app, share, effects).
    Windows writes them only after the user changes the setting, so "not found" means default (no rotation,
    multi-app off) OR an unknown location; the result says which keys were searched;
  * camera privacy consent (CapabilityAccessManager ConsentStore\\webcam, HKCU and HKLM): a Deny makes every API
    fail with E_ACCESSDENIED, which the bandwidth classifier must not confuse with a refusal;
  * Studio Effects / NPU presence (PnP device names) and the build's feature availability (multi-app needs
    26100.3321+, share mode 26100+);
  * FrameServer / FrameServerMonitor service state.
Verdicts: a "traps" pseudo-rating summarising which of the known traps are active (context for G-MJPEG/G-CTRL).
Rotation and multi-app (ctrl_id_env B10, V2): their storage is undocumented, so "no value found" is ``met`` None
("not found; location unknown") unless corroborated by W-FMT (MF lists native MJPG types and more than one native
type on every camera: a rotation strips compressed types and multi-app mode forces one media type); a value that is
found and means "on" is ``met`` False, one whose meaning is unknown is None. None counts as not-yes: the pseudo-rating
is 'yes' only when every trap is checked and off ('partial' with summary_label 'trap active' / 'not all traps
verified'). W-FMT runs after W-POLICY in the suite, so the live run is usually uncorroborated; the offline
re-analysis (``python w_policy.py --reanalyze <run_dir>``) uses the run's W-FMT.json.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _enum_util as U  # noqa: E402

TEST_ID = "W-POLICY"
KSPROXY_CLSID = "{17CCA71B-ECD7-11D0-B908-00A0C9223196}"
NAME_PAT = re.compile(r"rotat|multi.?app|multipleapp|sharemode|share.?mode|effect|blur|eye.?contact|framing|"
                      r"portrait|background|dshowredirection|dshowbridge|frameservermode|platformdmft|devicemft|"
                      r"postprocessing|cacheuvccontrol|metadatabuffer|customcapturesource", re.I)


def _walk(path: str, hive, max_keys: int, deadline: float) -> tuple[list[dict], int, bool]:
    """Bounded recursive read-only walk; returns (matching values/keys, keys visited, truncated)."""
    import winpnp as wp
    hits, stack, n = [], [path], 0
    while stack:
        if n >= max_keys or time.monotonic() > deadline:
            return hits, n, True
        p = stack.pop()
        n += 1
        vals = wp.reg_values(p, hive)
        if vals is None:
            continue
        if NAME_PAT.search(p.rsplit("\\", 1)[-1]):
            hits.append({"key": p, "match": "key name"})
        for k, val in vals.items():
            if NAME_PAT.search(k):
                hits.append({"key": p, "value": k, "data": val if not isinstance(val, str) or len(val) < 300
                             else val[:300] + "..."})
        for s in wp.reg_subkeys(p, hive) or []:
            stack.append(f"{p}\\{s}")
    return hits, n, False


_ON = {1, "1", True, "on", "enabled", "true", "yes"}
_OFF = {0, "0", False, "off", "disabled", "false", "no"}


def _value_meaning(hits: list[dict], kind: str) -> bool | None:
    """True = trap on, False = off, None = unknown. Rotation: a numeric value other than 0 (90/180/270 or 1-3) is on.
    Multi-app: 1/on is on. A key-name-only hit or an unrecognised value is unknown."""
    seen = []
    for h in hits:
        if "value" not in h:
            seen.append(None)
            continue
        d = h.get("data")
        dl = d.lower() if isinstance(d, str) else d
        if kind == "rotation" and isinstance(d, (int, float)) and not isinstance(d, bool):
            seen.append(d != 0)
        elif dl in _ON:
            seen.append(True)
        elif dl in _OFF:
            seen.append(False)
        else:
            seen.append(None)
    if any(x is True for x in seen):
        return True
    if seen and all(x is False for x in seen):
        return False
    return None


def fmt_corroboration(fmt_result: dict | None, keys: list[str]) -> dict:
    """From a W-FMT result: does MF list native MJPG types and more than one native type on every camera?"""
    if not fmt_result:
        return {"available": False}
    cams = {c.get("key"): c for c in (fmt_result.get("measurements") or {}).get("cameras") or []}
    per = {}
    for k in keys:
        cnt = (cams.get(k) or {}).get("counts") or {}
        per[k] = {"mf_mjpeg_types": cnt.get("mf_mjpeg_types"),
                  "mf_native_capture_modes": cnt.get("mf_native_capture_modes"),
                  "ok": bool((cnt.get("mf_mjpeg_types") or 0) > 0 and (cnt.get("mf_native_capture_modes") or 0) > 1)}
    return {"available": True, "per_camera": per, "all_ok": bool(per) and all(x["ok"] for x in per.values())}


def traps_rot_multi(rot: list[dict], multi: list[dict], corr: dict) -> list[dict]:
    """The rotation and multi-app trap criteria (B10 / V2)."""
    out = []
    for kind, hits, crit in (("rotation", rot, "no Settings video rotation set (rotation strips MJPEG/H.264 on the MF "
                                               "path)"),
                             ("multi_app", multi, "multi-app camera mode off (forces one media type on MF)")):
        if hits:
            on = _value_meaning(hits, kind)
            met = None if on is None else (not on)
            detail = {"found": hits, "meaning": {True: "on", False: "off", None: "unknown"}[on]}
        elif corr.get("all_ok"):
            met, detail = True, {"found": None, "corroborated_by": "W-FMT: MF lists native MJPG types and more than "
                                                                   "one native type on every camera",
                                 "per_camera": corr.get("per_camera")}
        else:
            met, detail = None, {"found": None, "note": "not found; storage location unknown (default, or a key this "
                                                        "search does not know); not corroborated",
                                 "w_fmt_available": corr.get("available", False)}
        out.append({"criterion": crit, "met": met, "detail": detail})
    return out


def traps_verdict(traps: list[dict]) -> dict:
    bad = [t for t in traps if t["met"] is False]
    unk = [t for t in traps if t["met"] is None]
    v = {"rating": "yes" if not bad and not unk else "partial", "criteria": traps,
         "evidence": {"note": "pseudo-rating: 'yes' = every known trap checked and off; None = unknown, counts as "
                              "not-yes; not a plan section 3 goal",
                      "active": [t["criterion"] for t in bad], "unverified": [t["criterion"] for t in unk]}}
    v["summary_label"] = ("partial (trap active)" if bad else "partial (not all traps verified)" if unk else "yes")
    return v


def reanalyze(run_dir: Path) -> dict:
    """Re-rate the stored W-POLICY.json (no registry read): rotation / multi-app per B10 + V2, corroborated by the
    run's W-FMT.json; the other four criteria as stored."""
    import json
    run_dir = Path(run_dir)
    d = json.loads((run_dir / "W-POLICY.json").read_text(encoding="utf-8"))
    try:
        fmt = json.loads((run_dir / "W-FMT.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fmt = None
    m = d.get("measurements") or {}
    sp = m.get("settings_page") or {}
    keys = [c.get("key") for c in m.get("cameras") or []]
    old = (d.get("verdicts") or {}).get("policy_traps") or {}
    rest = [t for t in old.get("criteria") or [] if not t["criterion"].startswith(("no Settings video rotation",
                                                                                   "multi-app camera mode"))]
    traps = traps_rot_multi(sp.get("rotation_values") or [], sp.get("multi_app_values") or [],
                            fmt_corroboration(fmt, keys)) + rest
    v = traps_verdict(traps)
    return {"test": TEST_ID, "reanalysis_of": str(run_dir / "W-POLICY.json"), "verdicts": {"policy_traps": v},
            "changes": [] if old.get("rating") == v["rating"] else [{"cell": "policy_traps", "from": old.get("rating"),
                                                                    "to": v["rating"]}],
            "fixes_applied": ["B10 rotation met None unless corroborated (W-FMT)", "V2 multi-app found -> not met; "
                              "None counts as not-yes"]}


def run(ctx) -> dict:
    def body(res, m, v, e):
        import winreg
        import winpnp as wp
        HKLM, HKCU = winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER
        # ---- Frame Server sensor groups
        sg_base = "SOFTWARE\\Microsoft\\Windows Media Foundation\\FrameServer\\SensorGroups"
        groups = {}
        for sub in wp.reg_subkeys(sg_base) or []:
            vals = wp.reg_values(f"{sg_base}\\{sub}") or {}
            link = str(vals.get("SymbolicLinkName") or "")
            groups[link.lower()] = {"sensor_group": sub, **{k: vals.get(k) for k in (
                "SensorGroupFriendlyName", "CameraDeviceCompatFlags", "SensorGroupProfiles", "FingerprintPrefix",
                "PublishTimestamp", "EnableTimestamp", "FaceAuthInfo")}}
        m["frameserver_sensor_group_count"] = len(groups)
        per_cam = []
        for c in ctx.cameras:
            fid = c.get("function_instance_id") or ""
            inst = fid.replace("\\", "#")
            rec = {"key": c["key"], "name": c.get("name"), "mf_symlink": c.get("mf_symlink"),
                   "ds_path": c.get("ds_path"), "ds_clsid_is_ksproxy_wincam": c.get("ds_clsid_is_ksproxy")}
            rec["frameserver_sensor_group"] = groups.get(str(c.get("mf_symlink") or "").lower())
            ifaces = {}
            for cat in ("KSCATEGORY_CAPTURE", "KSCATEGORY_VIDEO_CAMERA"):
                g = wp.GUIDS[cat].upper()
                base = f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{g}"
                found = next((s for s in wp.reg_subkeys(base) or [] if s.upper() == f"##?#{inst}#{g}".upper()), None)
                dp = wp.reg_values(f"{base}\\{found}\\#GLOBAL\\Device Parameters") if found else None
                ifaces[cat] = {"interface_key": found, "device_parameters": dp}
            rec["interface_keys"] = ifaces
            rec["enum_device_parameters"] = c.get("device_parameters")
            rec["enum_function_device_parameters"] = c.get("function_device_parameters")
            clsids = {cat: (x["device_parameters"] or {}).get("CLSID") for cat, x in ifaces.items()}
            rec["clsid"] = clsids
            redir = {}
            for where, vals in (("interface_capture", ifaces["KSCATEGORY_CAPTURE"]["device_parameters"]),
                                ("interface_video_camera", ifaces["KSCATEGORY_VIDEO_CAMERA"]["device_parameters"]),
                                ("enum_device", c.get("device_parameters")),
                                ("enum_function", c.get("function_device_parameters"))):
                for k, val in (vals or {}).items():
                    if k.lower() in ("enabledshowredirection", "cacheuvccontrol", "uvc-enableplatformdmft",
                                     "enableplatformdmft", "cameradevicemftclsidchain",
                                     "camerapostprocessingpluginclsid", "customcapturesourceclsid"):
                        redir[f"{where}:{k}"] = val
            rec["redirection_and_mft_values"] = redir
            dshow_redirect = any(k.lower().endswith("enabledshowredirection") and val not in (0, "0", None, "")
                                 for k, val in redir.items())
            mft_chain = any(("mftclsidchain" in k.lower() or "postprocessingplugin" in k.lower()
                             or "customcapturesource" in k.lower()) and val not in (None, "", 0)
                            for k, val in redir.items())
            rec["ds_bypasses_frameserver"] = (str(clsids.get("KSCATEGORY_CAPTURE") or "").upper() == KSPROXY_CLSID
                                              and not dshow_redirect)
            rec["dmft_or_plugin_active"] = mft_chain
            per_cam.append(rec)
        m["cameras"] = per_cam
        # ---- DShow bridge, FrameServerMode
        bridge = {}
        for sub in wp.reg_subkeys("SOFTWARE\\Microsoft\\OEM\\DshowBridge") or []:
            bridge[sub] = wp.reg_values(f"SOFTWARE\\Microsoft\\OEM\\DshowBridge\\{sub}")
        m["dshow_bridge_app_list"] = {"exists": wp.reg_subkeys("SOFTWARE\\Microsoft\\OEM\\DshowBridge") is not None,
                                      "entries": bridge}
        m["enable_frameserver_mode"] = {
            "HKLM\\SOFTWARE\\Microsoft\\Windows Media Foundation\\Platform":
                (wp.reg_values("SOFTWARE\\Microsoft\\Windows Media Foundation\\Platform") or {}).get(
                    "EnableFrameServerMode"),
            "HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows Media Foundation\\Platform":
                (wp.reg_values("SOFTWARE\\WOW6432Node\\Microsoft\\Windows Media Foundation\\Platform") or {}).get(
                    "EnableFrameServerMode")}
        # ---- Settings page state (bounded search)
        deadline = time.monotonic() + 20
        roots = [("HKLM", HKLM, "SOFTWARE\\Microsoft\\Windows Media Foundation", 3000),
                 ("HKCU", HKCU, "Software\\Microsoft\\Windows Media Foundation", 500),
                 ("HKCU", HKCU, "Software\\Microsoft\\Windows\\CurrentVersion\\CameraSettings", 500),
                 ("HKLM", HKLM, "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CameraSettings", 500),
                 ("HKCU", HKCU, "Software\\Microsoft\\Camera", 500)]
        for c in ctx.cameras:
            fid = c.get("function_instance_id") or ""
            roots.append(("HKLM", HKLM, f"SYSTEM\\CurrentControlSet\\Enum\\{fid}", 200))
            for cat in ("KSCATEGORY_CAPTURE", "KSCATEGORY_VIDEO_CAMERA"):
                g = wp.GUIDS[cat].upper()
                roots.append(("HKLM", HKLM, f"SYSTEM\\CurrentControlSet\\Control\\DeviceClasses\\{g}\\##?#"
                                            f"{fid.replace(chr(92), '#')}#{g}", 200))
        searched, hits = [], []
        for hname, hive, path, cap in roots:
            h, n, trunc = _walk(path, hive, cap, deadline)
            searched.append({"root": f"{hname}\\{path}", "keys_visited": n, "truncated": trunc})
            hits += [dict(x, key=f"{hname}\\{x['key']}") for x in h]
        rot = [x for x in hits if re.search(r"rotat", f"{x.get('value', '')}{x['key']}", re.I)]
        multi = [x for x in hits if re.search(r"multi.?app|multipleapp|share.?mode", f"{x.get('value', '')}{x['key']}",
                                              re.I)]
        m["settings_page"] = {"searched": searched, "matches": hits, "rotation_values": rot,
                              "multi_app_values": multi,
                              "interpretation": ("no rotation / multi-app value found in the searched keys: default "
                                                 "settings, or a storage location this search does not know")
                              if not rot and not multi else "values found: see matches"}
        # ---- privacy
        cs = "Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam"
        priv = {"HKCU": wp.reg_value(cs, "Value", HKCU), "HKLM": wp.reg_value(cs.replace("Software", "SOFTWARE"),
                                                                              "Value", HKLM)}
        np_vals = {}
        recent_cut = (time.time() + 11644473600 - 14 * 86400) * 1e7   # FILETIME 14 days ago
        for sub in wp.reg_subkeys(cs + "\\NonPackaged", HKCU) or []:
            vv = wp.reg_values(f"{cs}\\NonPackaged\\{sub}", HKCU) or {}
            stop = vv.get("LastUsedTimeStop") or 0
            if re.search(r"python|wincam|skelly|ffmpeg", sub, re.I) and (stop >= recent_cut or "wincam" in sub.lower()):
                np_vals[sub] = {"Value": vv.get("Value"),
                                "LastUsedTimeStart": wp._filetime_iso(vv.get("LastUsedTimeStart") or 0),
                                "LastUsedTimeStop": wp._filetime_iso(stop)}
        priv["nonpackaged_relevant"] = np_vals
        priv["nonpackaged_count"] = len(wp.reg_subkeys(cs + "\\NonPackaged", HKCU) or [])
        m["camera_privacy"] = priv
        # ---- Studio Effects / NPU, build
        effects = []
        for iid in wp.id_list(None, present_only=True):
            dn = wp.locate(iid)
            if dn is None:
                continue
            p = wp.devnode_props(dn, ["FriendlyName", "DeviceDesc", "Class"], status=False)
            txt = f"{p.get('FriendlyName') or ''} {p.get('DeviceDesc') or ''}"
            if re.search(r"studio effects|neural|\bnpu\b|ai boost|windows camera effects", txt, re.I):
                effects.append({"instance_id": iid, **p})
        m["studio_effects_or_npu_devices"] = effects
        env = res.get("environment", {}).get("os", {})
        build, ubr = env.get("windows_build"), env.get("windows_ubr")
        m["feature_availability"] = {"windows_build": build, "ubr": ubr,
                                     "share_mode_attribute": bool(build and build >= 26100),
                                     "multi_app_camera_setting": bool(build and (build > 26100 or
                                                                                 (build == 26100 and (ubr or 0) >= 3321))),
                                     "settings_camera_page": bool(build and build >= 22000)}
        m["services"] = {}
        for svc in ("FrameServer", "FrameServerMonitor"):
            q = ctx.run(["sc", "queryex", svc], timeout_s=15)
            st = re.search(r"STATE\s*:\s*(\d+)\s+(\w+)", q["stdout"])
            pid = re.search(r"PID\s*:\s*(\d+)", q["stdout"])
            m["services"][svc] = {"state": st.group(2) if st else None, "pid": int(pid.group(1)) if pid else None}
        # ---- traps summary
        import json as _json
        fmt_file = Path(ctx.out_dir) / "W-FMT.json"
        try:
            fmt = _json.loads(fmt_file.read_text(encoding="utf-8")) if fmt_file.exists() else None
        except (OSError, ValueError):
            fmt = None
        corr = fmt_corroboration(fmt, [c["key"] for c in ctx.cameras])
        m["rotation_multi_app_corroboration"] = corr
        traps = traps_rot_multi(rot, multi, corr) + [
            {"criterion": "DirectShow bypasses Frame Server on every camera (ksproxy CLSID, no EnableDshowRedirection)",
             "met": all(c["ds_bypasses_frameserver"] for c in per_cam) if per_cam else None,
             "detail": {c["key"]: c["ds_bypasses_frameserver"] for c in per_cam}},
            {"criterion": "no DMFT / post-processing plugin active", "met": not any(c["dmft_or_plugin_active"]
                                                                                   for c in per_cam),
             "detail": {c["key"]: c["redirection_and_mft_values"] for c in per_cam}},
            {"criterion": "camera privacy allows desktop apps", "met": priv["HKCU"] != "Deny" and priv["HKLM"] != "Deny",
             "detail": {"HKCU": priv["HKCU"], "HKLM": priv["HKLM"]}},
            {"criterion": "EnableFrameServerMode not set", "met": all(x is None for x in m["enable_frameserver_mode"].values()),
             "detail": m["enable_frameserver_mode"]},
        ]
        v["policy_traps"] = traps_verdict(traps)
    return U.guarded(ctx, TEST_ID, body)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--reanalyze":
        from common import results as _r
        _out = reanalyze(Path(sys.argv[2]))
        print(_r.write_json(Path(sys.argv[2]) / "reanalysis" / f"{TEST_ID}.json", _out), _out["changes"])
        sys.exit(0)
    sys.exit(U.standalone(run, TEST_ID))
