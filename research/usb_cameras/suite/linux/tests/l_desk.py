"""L-DESK: desktop-session interference (plan 2.6 / 6.2 DESK; Fedora KDE and Ubuntu GNOME).

- Who holds /dev/video* (fuser -v and our own /proc scan), whether the camera is streaming now (VS alt != 0).
- PipeWire / WirePlumber state (pw-dump Video nodes and their state, wpctl status, user services).
- EBUSY probe ONLY where another process holds the node: open + REQBUFS(1) (camworker desk_probe). REQBUFS sends
  nothing to the camera; we never S_FMT/TRY_FMT a node someone else streams (S_FMT sends a PROBE before it returns
  EBUSY: linux.md verifier L27). Expect EBUSY when the other holder streams, success when it only monitors.
- Permissions: node mode/group/ACL, video-group membership, session vs SSH (uaccess ACL only for the active seat).

This test runs before the camera tests so that the only holders are other applications.
"""
from __future__ import annotations

import grp
import os
import stat
from typing import Any

from common import results
import sysfs
from tutil import have, sh, outcome

TEST = "L-DESK"
INFO = {"goal": "G-ID/G-CTRL context", "summary": "holders, PipeWire state, EBUSY probe (REQBUFS only, only when "
                                                  "another holder exists), permissions", "opens_cameras": "probe only"}


def plan(ctx) -> dict[str, Any]:
    return {"child_runs": "0..N (probe only where another process holds a camera)", "est_seconds": 10,
            "steps": ["fuser -v", "/proc holder scan", "pw-dump/wpctl", "REQBUFS probe if held", "permissions"]}


def _perm(node: str) -> dict[str, Any]:
    out: dict[str, Any] = {"node": node}
    try:
        st = os.stat(sysfs.root() + node)
        out.update(mode=stat.filemode(st.st_mode), uid=st.st_uid, gid=st.st_gid)
        try:
            out["group"] = grp.getgrgid(st.st_gid).gr_name
        except KeyError:
            out["group"] = str(st.st_gid)
        out["readable"] = os.access(sysfs.root() + node, os.R_OK)
        out["writable"] = os.access(sysfs.root() + node, os.W_OK)
    except OSError as e:
        out["error"] = repr(e)
    return out


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    nodes = sorted({n for c in ctx.cameras for n in (c.get("node"), c.get("meta_node")) if n})
    meas: dict[str, Any] = {}
    fu = sh(ctx, ["fuser", "-v", *nodes], 15) if nodes else {"available": have("fuser"), "out": None}
    meas["fuser"] = {"available": fu["available"], "rc": fu.get("rc"), "stdout": fu.get("out"), "stderr": fu.get("err")}
    meas["holders_proc_scan"] = sysfs.holders(nodes, exclude_pids=sysfs.ancestors_and_self())
    if have("pw-dump"):
        r = sh(ctx, ["pw-dump", "-N"], 15)
        nodes_pw = []
        try:
            import json
            for o in json.loads(r.get("out") or "[]"):
                props = (o.get("info") or {}).get("props") or {}
                if str(props.get("media.class", "")).startswith("Video/") or props.get("device.api") in ("v4l2",
                                                                                                          "libcamera"):
                    nodes_pw.append({"id": o.get("id"), "type": o.get("type"), "media.class": props.get("media.class"),
                                     "device.api": props.get("device.api"), "api.v4l2.path": props.get("api.v4l2.path"),
                                     "node.name": props.get("node.name"), "state": (o.get("info") or {}).get("state"),
                                     "node.disabled": props.get("node.disabled")})
        except ValueError as e:
            errors.append({"stage": "pw-dump", "message": str(e)})
        meas["pipewire_video_objects"] = nodes_pw
    else:
        meas["pipewire_video_objects"] = None
    if have("wpctl"):
        meas["wpctl_status"] = (sh(ctx, ["wpctl", "status"], 10).get("out") or "")[:6000]
    if have("systemctl"):
        meas["user_services"] = {u: (sh(ctx, ["systemctl", "--user", "is-active", u], 8).get("out") or "")[:40]
                                 for u in ("pipewire", "wireplumber", "xdg-desktop-portal")}
    sess = {"ssh": bool(os.environ.get("SSH_CONNECTION")), "xdg_session_type": os.environ.get("XDG_SESSION_TYPE"),
            "xdg_session_id": os.environ.get("XDG_SESSION_ID")}
    try:
        sess["in_video_group"] = "video" in {grp.getgrgid(g).gr_name for g in os.getgroups()}
    except KeyError:
        sess["in_video_group"] = None
    meas["session"] = sess
    per_cam = {}
    for c in ctx.cameras:
        b = ctx.busy(c)
        perm = _perm(c["node"])
        acl = sh(ctx, ["getfacl", "-p", sysfs.root() + c["node"]], 8) if have("getfacl") else {"available": False}
        user = os.environ.get("USER") or ""
        acl_user = bool(acl.get("out") and f"user:{user}:" in acl["out"])
        access_via = ("acl (uaccess, active seat)" if acl_user else
                      ("video group" if sess["in_video_group"] and perm.get("group") == "video" else
                       ("world/other" if perm.get("writable") else "none")))
        entry: dict[str, Any] = {"busy": b, "permissions": perm, "acl": acl.get("out"), "access_via": access_via}
        if b["other_holders"]:
            r = ctx.camcmd(ctx.worker_cmd("desk_probe", "--device", c["node"]), timeout_s=20)
            j = r.get("json") or {}
            entry["probe"] = {"reqbufs_errno": j.get("reqbufs_errno"), "open_errno": j.get("open_errno"),
                              "expected": "EBUSY" if b["streamed_by_other"] else "success (holder only monitors)",
                              "child": outcome(r)}
            got = j.get("reqbufs_errno")
            entry["probe"]["as_expected"] = (got == "EBUSY") if b["streamed_by_other"] else (got is None)
        else:
            entry["probe"] = {"skipped": "no other process holds this camera: nothing to arbitrate"}
        per_cam[c["key"]] = entry
    meas["cameras"] = per_cam
    probes = [e["probe"] for e in per_cam.values() if "as_expected" in e["probe"]]
    crit = [{"criterion": "camera accessible to this user without sudo",
             "met": all(e["permissions"].get("writable") for e in per_cam.values()) if per_cam else None,
             "detail": {k: e["access_via"] for k, e in per_cam.items()}},
            {"criterion": "busy device reported as EBUSY without sending a PROBE",
             "met": all(p["as_expected"] for p in probes) if probes else None,
             "detail": f"{len(probes)} probe(s); attended item: start a browser/portal stream and rerun --only DESK"}]
    v = {"rating": "untested" if not probes else ("yes" if all(p["as_expected"] for p in probes) else "partial"),
         "criteria": crit, "evidence": {"probes": probes}}
    if not probes:
        v["note"] = "no other holder during the run; the EBUSY case needs an attended run with a PipeWire client"
    results.finish_result(res, measurements=meas, verdicts={"DESK": v}, errors=errors)
    return res
