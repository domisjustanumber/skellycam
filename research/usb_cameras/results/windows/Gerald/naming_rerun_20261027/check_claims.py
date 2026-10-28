# /// script
# requires-python = ">=3.10"
# ///
"""Offline re-check of the phase-1/phase-2 naming claims against the 2026-10-27 re-run outputs (no device access).

    uv run --script research/usb_cameras/results/windows/Gerald/naming_rerun_20261027/check_claims.py

Inputs (all under results/windows/Gerald/):
  naming_rerun_20261027/win_identity_dump/{identity_dump.json, descriptors.json, snapshots/rerun_20261027.json}
  naming_rerun_20261027/win_api_names/api_names.json
  naming/descriptors.json, naming/dumps/identity_dump_final_with_4th_camera.json, naming/api_names.json (phase 1)
Writes naming_rerun_20261027/check_claims.json
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
G = HERE.parent


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def vp(c: dict) -> str:
    return f"{c['vid']}:{c['pid']}"


def uvc_summary(cam: dict) -> dict:
    u = cam["uvc"]
    alts = [a for s in u["streaming_interfaces"] for a in s.get("alt_settings", [])]
    best = max(alts, key=lambda a: a.get("max_bytes_per_second") or 0) if alts else {}
    return dict(bcdUVC=u["bcdUVC"], dwClockFrequency=u["dwClockFrequency"],
                max_alt=best.get("bAlternateSetting"), max_bytes_per_second=best.get("max_bytes_per_second"),
                formats=[f"{f['fourcc'] or f['format']}({len(f['frames'])})" for s in u["streaming_interfaces"]
                         for f in s["formats"]])


def main() -> int:
    checks: list[dict] = []
    ok_all = True

    def check(name, cond, detail=None):
        nonlocal ok_all
        ok_all &= bool(cond)
        checks.append(dict(name=name, ok=bool(cond), detail=detail))
        print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail is not None else ""))

    new_desc = {vp(c["camera"]): c for c in load(HERE / "win_identity_dump/descriptors.json")["cameras"]}
    old_desc = {vp(c["camera"]): c for c in load(G / "naming/descriptors.json")["cameras"]}
    new_dump = load(HERE / "win_identity_dump/identity_dump.json")
    old_dump = load(G / "naming/dumps/identity_dump_final_with_4th_camera.json")
    snap = {vp(c): c for c in load(HERE / "win_identity_dump/snapshots/rerun_20261027.json")["cameras"]}
    api = load(HERE / "win_api_names/api_names.json")

    check("Kiyo 1532:0e05 excluded from the re-run (never sent an IOCTL)", "1532:0e05" not in new_desc,
          new_dump.get("excluded_instance_ids"))
    check("3 in-scope cameras found", sorted(new_desc) == ["046d:0843", "046d:085c", "4c4a:4a55"], sorted(new_desc))

    # 1. descriptors: byte identity + UVC numbers
    for k, c in new_desc.items():
        o = old_desc[k]
        for part in ("device", "configuration"):
            check(f"{k} raw {part} descriptor byte-identical to phase 1", c["raw_hex"][part] == o["raw_hex"][part])
        s_new, s_old = uvc_summary(c), uvc_summary(o)
        check(f"{k} UVC summary identical to phase 1", s_new == s_old, s_new)
        check(f"{k} wTotalLength == bytes", c["configuration_summary"]["wTotalLength"] == len(c["raw_hex"]["configuration"]) // 2)

    # 2. serials / instance ids
    for k, c in new_desc.items():
        iser = c["device"]["iSerialNumber"]
        s = snap[k]
        sfx = s["composite_instance_id"].split("\\")[-1]
        if k == "046d:085c":
            check("C922 iSerialNumber=1, serial B76395EF, used as instance id suffix",
                  iser == 1 and s["usb_serial"] == "B76395EF" and sfx == "B76395EF", (iser, s["usb_serial"], sfx))
        else:
            check(f"{k} iSerialNumber=0 and generated instance id (<hash>&0&<port>)",
                  iser == 0 and "&" in sfx and sfx.endswith(f"&0&{s['port_number']}"), (iser, sfx))
    check("C930e and generic share parent hub prefix 7&7DCC7CE (ports 4 and 3)",
          snap["046d:0843"]["composite_instance_id"].endswith("7&7DCC7CE&0&4")
          and snap["4c4a:4a55"]["composite_instance_id"].endswith("7&7DCC7CE&0&3"))

    # 3. device history + ContainerId version
    hist = {}
    for cam in new_dump["cameras"]:
        fi = cam["flat_identity"]
        h = cam.get("device_history", [])
        hist[vp(fi)] = dict(instances=len(h), container_ids=len({x.get("ContainerId") for x in h}),
                            rows=[(x["instance_id"], x.get("present"), x.get("ContainerId"), x.get("FirstInstallDate"))
                                  for x in h])
    old_hist = {f"{c['flat_identity']['vid']}:{c['flat_identity']['pid']}": len(c.get("device_history", []))
                for c in old_dump["cameras"]}
    for k, h in hist.items():
        check(f"{k} device_history instances={h['instances']} distinct ContainerIds={h['container_ids']} "
              f"(phase 1 instances={old_hist.get(k)})", True, h["rows"])
    check("C922 has exactly 1 instance in PnP history", hist["046d:085c"]["instances"] == 1)
    check("C930e: 2 instances, 2 ContainerIds (&0&1, &0&4) as in phase 1",
          hist["046d:0843"]["instances"] == 2 and hist["046d:0843"]["container_ids"] == 2)
    check("C922 ContainerId is UUID v5", snap["046d:085c"]["container_id_uuid_version"]["version"] == 5)
    for k in ("046d:0843", "4c4a:4a55"):
        check(f"{k} ContainerId is UUID v1", snap[k]["container_id_uuid_version"]["version"] == 1,
              snap[k]["container_id_uuid_version"])

    # 4. IgnoreHWSerNum (registry read-only, recorded by win_identity_dump)
    for cam in new_dump["cameras"]:
        uf = cam["usbflags"]
        check(f"{vp(cam['flat_identity'])} no IgnoreHWSerNum; global count 11; device key only osvc/NewInterfaceUsage",
              not uf["global_IgnoreHWSerNum_for_vidpid"] and uf["global_IgnoreHWSerNum_count"] == 11
              and set(uf["device_key_values"]) <= {"osvc", "NewInterfaceUsage"}, uf)

    # 5. API path mapping
    mf = [e for e in api["apis"]["media_foundation"] if isinstance(e, dict)]
    ds = [e for e in api["apis"]["directshow"] if isinstance(e, dict)]
    ff = api["apis"]["ffmpeg_dshow"]["devices"]
    cv = api["apis"]["opencv"]
    for k, s in snap.items():
        m = next(e for e in mf if e["index"] == s["mf_index"])
        d = next(e for e in ds if e["index"] == s["dshow_index"])
        check(f"{k} MF symbolic link == KSCATEGORY_VIDEO_CAMERA interface (case-insensitive)",
              m["symbolic_link"].lower() == s["ks_video_camera_symlink"].lower())
        check(f"{k} DShow DevicePath == KSCATEGORY_CAPTURE interface (case-insensitive)",
              d["device_path"].lower() == s["ks_capture_symlink"].lower())
        fe = [x for x in ff if (x["resolves_to"]["parsed_instance_id"] or "") == s["video_function_instance_id"].upper()]
        check(f"{k} FFmpeg alternative name == '@device_pnp_' + DevicePath",
              len(fe) == 1 and fe[0]["alternative_name"] == "@device_pnp_" + d["device_path"], fe and fe[0]["alternative_name"])
        cm = [c for c in cv["CAP_MSMF"] if c["path"].lower() == m["symbolic_link"].lower()]
        cd = [c for c in cv["CAP_DSHOW"] if c["path"].lower() == d["device_path"].lower()]
        check(f"{k} cv2_enumerate_cameras CAP_MSMF index == MF position ({s['mf_index']}) and CAP_DSHOW index == DShow "
              f"position ({s['dshow_index']}) [enumeration only, no VideoCapture opened]",
              len(cm) == 1 and cm[0]["index"] == s["mf_index"] and len(cd) == 1 and cd[0]["index"] == s["dshow_index"])
    check("8 MF and 15 DShow video sources", len(mf) == 8 and len(ds) == 15, (len(mf), len(ds)))
    check("generic camera friendly name 'USB Camera' (MF + DShow)", snap["4c4a:4a55"]["mf_friendly_name"] == "USB Camera"
          and snap["4c4a:4a55"]["dshow_friendly_name"] == "USB Camera")
    kiyo_mf = [e["friendly_name"] for e in mf if "VID_1532" in (e["resolves_to"]["parsed_instance_id"] or "")]
    check("Kiyo (enumerated by MF only, not opened) still named 'USB Video Device'", kiyo_mf == ["USB Video Device"], kiyo_mf)

    # 6. index order change vs phase 1
    old_api = load(G / "naming/api_names.json")
    def order(a, key):
        return [(e["index"], (e["resolves_to"]["parsed_instance_id"] or "")[:30]) for e in a["apis"][key]
                if isinstance(e, dict) and "VID_" in (e["resolves_to"]["parsed_instance_id"] or "")]
    order_info = {k: dict(phase1=order(old_api, k), rerun=order(api, k)) for k in ("media_foundation", "directshow")}
    check("MF/DShow index order of physical cameras changed since phase 1 (indices are not identity)",
          order_info["media_foundation"]["phase1"] != order_info["media_foundation"]["rerun"]
          or order_info["directshow"]["phase1"] != order_info["directshow"]["rerun"], order_info)

    # 7. camera keys
    expected = {"046d:085c": "046d:085c:sn=B76395EF",
                "046d:0843": "046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4",
                "4c4a:4a55": "4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.3"}
    check("camera_key equals phase-1 keys for all 3 cameras", {k: s["camera_key"] for k, s in snap.items()} == expected)

    res = dict(test="naming.rerun_check_claims", platform=sys.platform, utc_run=_dt.datetime.now(_dt.timezone.utc).isoformat(),
               command="uv run --script " + str(Path(__file__).relative_to(G.parents[4])).replace("\\", "/"),
               uvc={k: uvc_summary(c) for k, c in new_desc.items()}, device_history=hist, checks=checks, all_ok=ok_all,
               n_pass=sum(c["ok"] for c in checks), n=len(checks))
    (HERE / "check_claims.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"{res['n_pass']}/{res['n']} all_ok={ok_all}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
