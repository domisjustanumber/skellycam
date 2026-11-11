"""M-TOPO: IORegistry topology -> common snapshot -> bandwidth domains, each camera's domain, predicted conflicts
for each camera's default mode, free ports with the best available labels, the user message for every predicted
conflict. Opens no camera (plan 6.2 TOPO, section 5; topology_macos.md MT1/MT7)."""
from __future__ import annotations

import suitectx
from common import rating, results, topology_model

NAME = "M-TOPO"


def plan(ctx) -> list[str]:
    return ["ioreg -a -l -w0 -p IOService -r -c AppleUSBHostController (+ AppleHPM -d 1, IOPCIDevice -d 2, "
            "IOUSBHostInterface -d 1); raw plists to the raw dir",
            "snapshot -> compute_domains / predict (default mode per camera, mode->alt cache) / suggest_ports / "
            "build_message",
            "schema report: port classes and port-number keys per macOS version (port / usb-port-number / port-number), "
            "port-status values outside the SDK 11.3 layout, AppleHPM labels"]


def requests_for(ctx, cams: list[dict]) -> list[dict]:
    reqs = []
    for c in cams:
        mode = suitectx.pick_scoped_default(c, ctx.args)[0] or suitectx.pick_default_mode(c)  # streaming default
        reqs.append({"camera_key": c["key"], "mode": (mode or {}).get("mode_text") or "MJPG 1280x720@30",
                     "alt": None, "max_packet": None, "mult": None})
    return reqs


def free_ports(snap: dict) -> list[dict]:
    out = []
    for p in snap.get("ports", []):
        if p.get("occupant_device_id") is not None:
            continue
        try:
            label = topology_model.port_label(snap, p["id"])
        except Exception as e:
            label = f"(label error {e!r})"
        out.append({"id": p["id"], "path": p.get("path"), "half": p.get("half"), "connectable": p.get("connectable"),
                    "connector": p.get("connector"), "label": label, "is_root_port": p.get("is_root_port"),
                    "maybe_occupied_by_non_usb": p.get("maybe_occupied_by_non_usb"), "controller": p.get("controller_id")})
    return out


def run(ctx) -> dict:
    res = ctx.new_result(NAME)
    errors: list = []
    snap = ctx.snapshot or {}
    m: dict = {"schema_report": snap.get("schema_report"), "warnings": snap.get("warnings"),
               "ioreg_queries": snap.get("ioreg_queries"), "raw_plists_dir": snap.get("raw_plists_dir")}
    try:
        doms = topology_model.compute_domains(snap)
        m["domains"] = doms
        devs = {d["id"]: d for d in snap.get("devices", [])}
        m["camera_domains"] = {c["key"]: topology_model.domain_key(snap, c["device_id"]) for c in snap.get("cameras", [])
                               if c.get("device_id") in devs}
        cache = ctx.mode_alt_cache()
        reqs = requests_for(ctx, [c for c in ctx.cameras if c.get("device_id")])
        ex = topology_model.explain(snap, reqs, cache)
        m["requests"] = reqs
        m["prediction"] = ex["prediction"]
        m["messages"] = ex["messages"]
        m["free_ports"] = free_ports(snap)
        m["note_free_ports"] = ("a USB-C port holding a charger or a display has no USB child but is not free; "
                                "suggestions must be read as 'if nothing is plugged into it'")
        labels = [p["label"] for p in m["free_ports"]]
        hpm = (snap.get("schema_report") or {}).get("hpm_labels")
        m["labels_raw"] = not hpm and all(l.startswith("port ") or "/" in l for l in labels) if labels else None
        ctx.store["topo"] = {"domains": doms, "camera_domains": m["camera_domains"], "prediction": ex["prediction"],
                             "labels_raw": m["labels_raw"]}
    except Exception as e:
        import traceback
        errors.append({"error": f"topology model failed: {e!r}", "traceback": traceback.format_exc()[-2000:]})
    ctx.write("topo_snapshot", snap)
    v = {"G-BW": rating.untested("mapper only: refusals are observed in M-MULTI",
                                 {"n_domains": len(m.get("domains") or []),
                                  "predicted_conflicts": len((m.get("prediction") or {}).get("conflicts") or []),
                                  "labels_raw": m.get("labels_raw")})}
    return results.finish_result(res, m, v, errors)
