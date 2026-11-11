"""L-ID: every Linux enumeration path mapped to the camera_identity key, repeated (plan 6.2 ID, G-ID).

APIs: sysfs (/sys/class/video4linux), V4L2 QUERYCAP bus_info (camworker 'enum', opens nodes read-only, no
streaming), /dev/v4l/by-id, /dev/v4l/by-path (plain and usbv2/usbv3), udev properties (ID_PATH,
ID_PATH_WITH_USB_REVISION, ID_SERIAL), PipeWire nodes (pw-dump) when present. Each run lists the keys in that API's
order; rate_id checks 1:1 mapping and stable order over --id-repeats runs (20). Reboot / replug / port-move
persistence is attended item A1 (left None).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from common import rating, results
import sysfs
from tutil import have, sh, outcome, worker_error

TEST = "L-ID"
INFO = {"goal": "G-ID", "summary": "sysfs / QUERYCAP bus_info / by-id / by-path / udev / PipeWire -> identity keys, "
                                   "N repeats", "opens_cameras": "read-only QUERYCAP"}


def plan(ctx) -> dict[str, Any]:
    n = ctx.args.id_repeats
    return {"child_runs": 1 + (n if have("pw-dump") else 0), "est_seconds": 5 + n * 0.5,
            "steps": [f"{n} x sysfs", f"camworker enum --repeat {n}", f"{n} x by-id/by-path", "3 x udevadm",
                      f"{n} x pw-dump (if installed)"]}


def _bus_info_key(bus_info: str | None, cams: list[dict]) -> str | None:
    m = re.match(r"usb-(.+)-([\d.]+)$", bus_info or "")
    if not m:
        return None
    hits = [c["key"] for c in cams if c.get("pci_controller") == m.group(1) and c.get("devpath") == m.group(2)]
    return hits[0] if len(hits) == 1 else None


def _link_runs(cams: list[dict], kind: str, n: int) -> tuple[list[list[str | None]], dict[str, Any]]:
    node_key = {os.path.realpath(sysfs.root() + c["node"]): c["key"] for c in cams}
    runs = []
    detail: dict[str, Any] = {}
    d = sysfs.P(f"/dev/v4l/{kind}")
    for _ in range(n):
        keys = []
        names = sorted(p.name for p in d.glob("*")) if d.is_dir() else []
        idx0 = [x for x in names if x.endswith("-video-index0")]
        plain = [x for x in idx0 if "usbv2" not in x and "usbv3" not in x]
        for name in plain:
            keys.append(node_key.get(os.path.realpath(str(d / name))))
        runs.append(keys)
        detail = {"links_index0": idx0, "plain": plain, "with_usb_revision": [x for x in idx0 if x not in plain]}
    return runs, detail


def _pipewire(ctx, cams: list[dict], n: int) -> tuple[list[list[str | None]] | None, dict[str, Any]]:
    if not have("pw-dump"):
        return None, {"available": False}
    node_key = {c["node"]: c["key"] for c in cams}
    runs, last, times = [], None, []
    for _ in range(n):
        t0 = time.monotonic()
        r = sh(ctx, ["pw-dump", "-N"], 15)
        times.append(round((time.monotonic() - t0) * 1000, 1))
        if r.get("rc") != 0:
            return None, {"available": True, "error": r.get("err")}
        try:
            objs = json.loads(r["out"] or "[]")
        except ValueError as e:
            return None, {"available": True, "error": f"pw-dump JSON: {e}"}
        nodes = []
        for o in objs:
            props = ((o.get("info") or {}).get("props") or {})
            if props.get("media.class") == "Video/Source" or str(props.get("media.class", "")).startswith("Video/"):
                nodes.append({"id": o.get("id"), "node.name": props.get("node.name"),
                              "node.description": props.get("node.description"),
                              "object.path": props.get("object.path"), "api.v4l2.path": props.get("api.v4l2.path"),
                              "bus_info": props.get("api.v4l2.cap.bus_info"),
                              "device.api": props.get("device.api"), "media.role": props.get("media.role"),
                              "state": (o.get("info") or {}).get("state")})
        keys = []
        for nd in nodes:
            k = node_key.get(nd.get("api.v4l2.path") or "") or _bus_info_key(nd.get("bus_info"), cams)
            keys.append(k)
        runs.append(keys)
        last = nodes
    return runs, {"available": True, "nodes_last_run": last, "pw_dump_ms": times}


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    n = ctx.args.id_repeats
    cams = ctx.cameras
    errors: list[dict] = []
    api_runs: dict[str, list[list[str | None]]] = {}
    meas: dict[str, Any] = {"repeats": n}

    # sysfs
    t = []
    runs = []
    for _ in range(n):
        t0 = time.monotonic()
        runs.append([c["key"] for c in sysfs.discover_cameras()])
        t.append(round((time.monotonic() - t0) * 1000, 2))
    api_runs["sysfs"] = runs
    meas["sysfs_ms"] = t

    # V4L2 QUERYCAP bus_info (opens nodes read-only)
    r = ctx.camcmd(ctx.worker_cmd("enum", "--repeat", n), timeout_s=30 + 5 * n)
    j = r.get("json") or {}
    if j.get("runs"):
        q_runs = []
        for run_ in j["runs"]:
            keys = []
            for e in run_["entries"]:
                if e.get("is_capture") and e.get("driver") == "uvcvideo":
                    keys.append(_bus_info_key(e.get("bus_info"), cams))
            q_runs.append(keys)
        api_runs["v4l2_bus_info"] = q_runs
        meas["v4l2_enum"] = {"elapsed_ms": [x["elapsed_ms"] for x in j["runs"]],
                             "first_run": j["runs"][0]["entries"],
                             "open_errors": sorted({(e.get("error") or {}).get("errno_name") for x in j["runs"]
                                                    for e in x["entries"] if e.get("error")} - {None})}
    else:
        errors.append({"api": "v4l2_bus_info", "error": worker_error(r), "child": outcome(r)})

    for kind in ("by-id", "by-path"):
        runs, det = _link_runs(cams, kind, n)
        api_runs[kind] = runs
        meas[kind] = det

    # udev
    udev = {}
    for c in cams:
        u = sh(ctx, ["udevadm", "info", "--query=property", f"--name={c['node']}"], 10)
        props = dict(ln.split("=", 1) for ln in (u.get("out") or "").splitlines() if "=" in ln)
        udev[c["key"]] = {k: props.get(k) for k in ("ID_PATH", "ID_PATH_WITH_USB_REVISION", "ID_PATH_TAG",
                                                    "ID_SERIAL", "ID_SERIAL_SHORT", "ID_V4L_CAPABILITIES",
                                                    "ID_V4L_PRODUCT", "TAGS", "CURRENT_TAGS")} if props else \
            {"error": u.get("err") or "udevadm unavailable"}
    meas["udev"] = udev
    serials = [u.get("ID_SERIAL") for u in udev.values() if u.get("ID_SERIAL")]
    meas["by_id_collisions"] = sorted({s for s in serials if serials.count(s) > 1})

    pw_runs, pw = _pipewire(ctx, cams, n)
    if pw_runs is not None:
        api_runs["pipewire"] = pw_runs
    meas["pipewire"] = pw

    keys = [c["key"] for c in cams]
    meas["identity"] = [{"key": c["key"], "key_kind": c.get("key_kind"), "serial": c.get("serial"),
                         "serial_reason": c.get("serial_reason"), "port_path": c.get("port_path"),
                         "usb_name": c["usb_name"], "speed": c["speed"], "node": c["node"],
                         "meta_node": c.get("meta_node"), "by_id": c.get("by_id"), "by_path": c.get("by_path")}
                        for c in cams]
    meas["key_collisions"] = sorted({k for k in keys if keys.count(k) > 1})
    meas["port_path_note"] = ("port paths drop the bus number (camera_identity scheme): a USB 2.0 and a USB 3 root "
                              "port with the same number give the same path; key_collisions above would show it")
    meas["api_runs_first"] = {k: (v[0] if v else None) for k, v in api_runs.items()}
    meas["opencv_index_note"] = "OpenCV CAP_V4L2 index N opens /dev/videoN: mappable through the node (sysfs row)"
    if not cams:
        verdict = rating.untested("no camera found")
    else:
        verdict = rating.rate_id(api_runs, keys, persistence=None, min_runs=min(20, n))
    per_api = {}
    for api, runs in api_runs.items():
        per_api[api] = rating.rate_id({api: runs}, keys, None, min_runs=min(20, n))["rating"] if cams else "untested"
    meas["per_api_rating"] = per_api
    results.finish_result(res, measurements=meas, verdicts={"G-ID": verdict}, errors=errors)
    return res
