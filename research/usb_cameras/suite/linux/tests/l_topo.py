"""L-TOPO: USB topology map, bandwidth domains, free ports with labels, each camera's domain and the predicted
conflicts for its default mode (plan 5 and 6.2 TOPO). Opens no camera: sysfs only (linuxlib/topology.py).

Verdict: G-BW mapper readiness only (refusal prediction is rated in L-MULTI against real opens).
"""
from __future__ import annotations

from typing import Any

from common import rating, results, topology_model as tm
import topology
from tutil import mode_text

TEST = "L-TOPO"
INFO = {"goal": "G-BW", "summary": "sysfs tree -> snapshot, domains, free ports + labels, predicted conflicts",
        "opens_cameras": False}


def plan(ctx) -> dict[str, Any]:
    return {"child_runs": 0, "est_seconds": 3, "steps": ["collect snapshot", "compute domains", "predict defaults",
                                                         "free ports by domain", "pre-open messages"]}


def free_ports(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Empty, user-connectable-or-unknown ports with a USB 2.0 half (or a USB 3 port whose companion is empty),
    grouped by the high-speed domain of their USB 2.0 half, with the best label."""
    ports = {p["id"]: p for p in snap["ports"]}
    devs = {d["id"]: d for d in snap["devices"]}
    out = []
    for p in snap["ports"]:
        if p["occupant_device_id"] or p["connectable"] in ("not_used", "internal"):
            continue
        comp = ports.get(p.get("companion_id"))
        if p["half"] == "usb3":
            if comp is not None:
                continue  # listed through its USB 2.0 half
            hs_root = None
        else:
            if comp is not None and comp.get("occupant_device_id"):
                continue  # the connector holds a SuperSpeed device
            hs_root = p["id"] if p["is_root_port"] else None
            cur = p
            seen = set()
            while hs_root is None and cur is not None and cur["id"] not in seen:
                seen.add(cur["id"])
                hub = devs.get(cur.get("hub_device_id"))
                if hub is None:
                    break
                cur = ports.get(hub.get("port_id"))
                if cur is not None and cur["is_root_port"]:
                    hs_root = cur["id"]
        try:
            label = tm.port_label(snap, p["id"])
        except Exception as e:
            label = f"{p['id']} ({e})"
        out.append({"port_id": p["id"], "label": label, "controller_id": p["controller_id"], "half": p["half"],
                    "usb2_root_port": hs_root, "on_hub": not p["is_root_port"], "connectable": p["connectable"],
                    "connector": p["connector"], "companion_id": p.get("companion_id"),
                    "acpi_name": p["label_parts"].get("acpi_name"), "panel": p["label_parts"].get("panel")})
    return out


def run(ctx) -> dict[str, Any]:
    res = ctx.new_result(TEST)
    errors: list[dict] = []
    try:
        snap = topology.collect_snapshot(ctx.cameras)
    except Exception as e:
        results.finish_result(res, errors=[{"stage": "collect", "message": f"{type(e).__name__}: {e}"}],
                              verdicts={"G-BW": rating.untested("topology collection failed")})
        return res
    ctx.topology = snap
    ctx.write("l_topo/topology_snapshot.json", snap)
    doms = tm.compute_domains(snap)
    cams = {c["key"]: c for c in ctx.cameras}
    per_cam = []
    requests = []
    for sc in snap["cameras"]:
        c = cams.get(sc["key"])
        m = (c or {}).get("modes", {}).get("default")
        dk = None
        try:
            dk = tm.domain_key(snap, sc["device_id"]) if sc["device_id"] else None
        except KeyError as e:
            errors.append({"camera": sc["key"], "stage": "domain_key", "message": str(e)})
        per_cam.append({"key": sc["key"], "name": sc["name"], "device_id": sc["device_id"], "domain": dk,
                        "default_mode": mode_text(m), "alt_table": sc.get("alt_table"),
                        "current_alt": sc.get("current_alt"), "is_kiyo": sc["is_kiyo"],
                        "max_alt_cost_us": max((tm.cost_us(a["max_packet"], a["mult"],
                                                           "SS" if (c or {}).get("speed") in ("SS", "SS+") else "HS")
                                                for a in (sc.get("alt_table") or [])), default=None)})
        if m:
            requests.append({"camera_key": sc["key"], "mode": mode_text(m)})
    pred = tm.predict(snap, requests, ctx.mode_alt_cache)
    expl = tm.explain(snap, requests, ctx.mode_alt_cache)
    fp = free_ports(snap)
    by_dom: dict[str, list[str]] = {}
    for p in fp:
        by_dom.setdefault(f"{p['controller_id']}|{p['usb2_root_port'] or p['port_id']}", []).append(p["label"])
    ctrls = [{"id": c["id"], "name": c["name"], "pci_id": c["pci_id"], "kind": c["kind"], "buses": c["buses"],
              "policy": tm.policy_for(c)} for c in snap["controllers"]]
    labels_raw = not any(p.get("panel") for p in fp)
    meas = {"controllers": ctrls, "n_ports": len(snap["ports"]), "n_devices": len(snap["devices"]),
            "domains": doms, "cameras": per_cam, "free_ports": fp, "free_ports_by_domain": by_dom,
            "prediction_default_modes": {"requests": requests, "domains": pred["domains"],
                                         "conflicts": pred["conflicts"], "warnings": pred.get("warnings")},
            "pre_open_messages": [m["message"] for m in expl["messages"]],
            "snapshot_file": "l_topo/topology_snapshot.json", "snapshot_warnings": snap.get("warnings"),
            "labels": {"any_physical_location_panel": not labels_raw,
                       "ports_with_typec_connector": sum(1 for p in snap["ports"] if p["label_parts"].get("type_c")),
                       "ports_with_acpi_name": sum(1 for p in snap["ports"] if p["label_parts"].get("acpi_name")),
                       "pld_all_zero_ports": sum(1 for p in snap["ports"] if p["label_parts"].get("pld_all_zero"))},
            "mode_alt_cache_entries": len(ctx.mode_alt_cache)}
    crit = [{"criterion": "topology collected without root", "met": True, "detail": f"{len(snap['ports'])} ports"},
            {"criterion": "every camera mapped to a domain", "met": all(p["domain"] for p in per_cam) if per_cam
             else None, "detail": [p["domain"] for p in per_cam]},
            {"criterion": "free ports labelled better than raw (physical_location present)", "met": not labels_raw,
             "detail": meas["labels"]}]
    verdict = {"rating": "untested", "criteria": crit, "evidence": {"note": "refusal prediction is rated in L-MULTI"},
               "note": "mapper output only"}
    results.finish_result(res, measurements=meas, verdicts={"G-BW-mapper": verdict}, errors=errors)
    return res
