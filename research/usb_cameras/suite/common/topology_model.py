"""OS-neutral USB bandwidth-domain model, prediction, failure classification, port suggestions and user message.

Source: results/agent_reports/plan_20261106/bandwidth_domain_model.md (sections 2-6 and its verifier notes, which
win where they disagree) and docs/xplat_capture_plan.md section 5. Stdlib only; never touches a device. Each OS's
topology collector (suite/windows/helpers/win_topology.py, the Linux sysfs and macOS IORegistry collectors)
produces a *snapshot* dict and everything here works on that dict:

    {"os": "windows"|"linux"|"macos", "collected_utc": str,
     "controllers": [{"id","name","pci_id" ("8086:7A60"),"vendor","kind","policy_hint"}],
     "ports":   [{"id","controller_id","hub_device_id"|None,"port_number","path","is_root_port",
                  "half":"usb2"|"usb3"|"unknown","companion_id"|None,
                  "connectable":"user"|"internal"|"not_used"|"unknown","connector":"A"|"C"|"internal"|"unknown",
                  "label_parts":{...},"occupant_device_id"|None,"speed_max"|None}],
     "devices": [{"id","vid","pid","serial"|None,"name","speed":"LS"|"FS"|"HS"|"SS"|"SS+"|"unknown","port_id",
                  "parent_device_id"|None,"is_hub","hub_tt"("single"|"multi"|None),"controller_id","root_port_id",
                  "bcd_device"|None,
                  "periodic_pipes":[{"ep","type":"iso"|"int","max_packet","mult","interval"}]}],
     "cameras": [{"key","device_id","name","is_kiyo","alt_table":[{"alt","max_packet","mult"}]|None,
                  "current_alt"|None}]}

Conventions:
- ``periodic_pipes`` are the pipes OPEN NOW (Windows hub IOCTL open-pipe list, Linux current bAlternateSetting +
  ep_XX, macOS IORegistry). ``max_packet`` is the base packet size (wMaxPacketSize bits 0-10) and ``mult`` the
  transactions per (micro)frame (1-3 at high speed; for SuperSpeed give bursts x mult).
- For a high-speed device, ``root_port_id``/``controller_id`` must describe the USB 2.0 parent chain. If a collector
  hands over the USB 3 half of a connector, the model follows ``companion_id`` to the USB 2.0 half (Gerald's
  Thunderbolt USB-C ports have SuperSpeed on 8086:1138 and USB 2.0 on the chipset 8086:7A60).
- ``label_parts`` (all optional): acpi_name ("HS07"), panel ("rear"; only if trustworthy: the collector must drop
  the all-zero _PLD defaults), position_text ("second from top"), color, type_c (bool), usb3_capable (bool),
  user_visible (bool), socket_evidence (str/bool: phantom history, _PLD user_visible, USB-C geometry),
  friendly (OS port name), location_path.

Cost model (doc: USB 2.0 section 5.11.3 / 5.6.4, as in bandwidth/hs_budget_model.py): a high-speed isochronous
IN transaction of n bytes takes ``38*8*2.083 + 2.083*floor(3.167 + 1.1667*8*n)`` ns (worst-case bit stuffing,
Host_Delay = 0); an alt with base packet b and mult m costs m*t(b). Periodic transfers may reserve at most 80% of
a 125 us microframe = 100 us = the domain budget.

Accounting (verifier V2): the Gerald bracket (pass at 75.2%, refuse at 80.9% of a microframe) and the 26/26
agreement were derived counting ONLY isochronous endpoints (cameras, audio). ``accounting="calibrated"`` (the
default) does the same. ``accounting="full"`` also counts interrupt pipes at full cost and a TT charge per active
transaction translator; never mix full accounting with the calibrated thresholds.

Domains (doc + measured): a high-speed device's domain is (controller, USB 2.0 root port) on per-root-port
controllers and the whole controller on pooled ones (EHCI, Intel rate-matching hubs, AMD per verifier V1).
SuperSpeed and full/low-speed-on-a-root-port devices get their own domains (USB 2.0 and USB 3 traffic do not
compete). Policy table: ``policy_for``; learned escalation: ``LearnedPolicies``.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

# ----------------------------------------------------------------------------------------------- constants
MICROFRAME_US = 125.0
HS_BUDGET_US = 100.0                 # 80% of a microframe (USB 2.0 section 5.6.4)
MARGINAL_FRACTION = 0.9375           # 75% of a microframe = 93.75% of the budget: "marginal" starts here
SS_BUDGET_US = 112.5                 # 90% of a 125 us bus interval (USB 3.x periodic limit)
FS_FRAME_US = 1000.0
FS_BUDGET_US = 900.0                 # 90% of a 1 ms full-speed frame
INTEL_SW_BLOCK_CAPACITY = 1285       # 1607 blocks minus the 20% reserve (Panther Point software table)
INTEL_SW_TT_BLOCKS = 125             # TT_HS_OVERHEAD per active TT (Panther Point only, verifier V2)
MTK_HS_PAYLOAD_BYTES = 6144          # HS_BW_BOUNDARY (MediaTek scheduler, payload only)
FULL_ACCOUNTING_TT_US = INTEL_SW_TT_BLOCKS / 1607 * HS_BUDGET_US  # ~7.8 us per active TT ("full" accounting)

#: Intel rate-matching hubs (8/9-series RMHs per verifier V4.7, plus the older 0020/0024): the whole EHCI behind
#: them is one high-speed bus.
INTEL_RMH_VIDPID = {"8087:0020", "8087:0024", "8087:8000", "8087:8001", "8087:8008", "8087:8009"}

MESSAGE_SUGGEST_LINE = "Suggest moving one of those cameras to any of the following controller ports:"

#: measured admission brackets per controller model (calibrated accounting): the largest high-speed domain load that
#: streamed and the smallest that was refused. Intel 8086:7A60 (Gerald): 93.97 us (75.2 % of a microframe, C922
#: 960x720@30 + generic 720p30) streamed 6/6 on 11-06 and passed on 10-27; 101.1 us (80.9 %) was refused on 10-27.
#: Without it the 93.75 us default limit called the 93.97 us pair "marginal" and stay-here advice skipped it
#: (windows_results_20261106 section 11). A learned or hinted bracket replaces it.
MEASURED_BRACKETS = {"8086:7a60": {"max_pass_us": 94.0, "min_fail_us": 101.1}}


def _vidpid(vid: Any, pid: Any) -> str:
    def h(x: Any) -> str:
        if x is None:
            return "????"
        if isinstance(x, int):
            return f"{x:04x}"
        s = str(x).lower()
        return s[2:] if s.startswith("0x") else s
    return f"{h(vid)}:{h(pid)}"


# ----------------------------------------------------------------------------------------------- cost model
def t_hs_ns(n_bytes: int, transfer: str = "iso") -> float:
    """USB 2.0 section 5.11.3 high-speed transaction time in ns (worst-case bit stuffing, Host_Delay 0).
    Isochronous: 38 bytes of overhead; interrupt: 55 (adds the handshake)."""
    overhead = 55 if transfer == "int" else 38
    return overhead * 8 * 2.083 + 2.083 * math.floor(3.167 + 1.1667 * 8 * n_bytes)


def t_fs_ns(n_bytes: int, transfer: str = "iso") -> float:
    """USB 2.0 section 5.11.3 full-speed transaction time in ns (isochronous IN: 7268 ns base; interrupt: 9107)."""
    base = 9107 if transfer == "int" else 7268
    return base + 83.54 * math.floor(3.167 + 1.1667 * 8 * n_bytes)


def cost_us(max_packet: int, mult: int = 1, speed: str = "HS", transfer: str = "iso") -> float:
    """Bus time in us that one (micro)frame's worth of a periodic endpoint reserves.

    HS: mult x t_hs(max_packet) per 125 us microframe (the formula of bandwidth/hs_budget_model.py).
    FS/LS: per 1 ms frame (5.11.3 full-speed formula; LS approximated with the FS formula x 8).
    SS/SS+: approximate wire time of mult (= bursts x mult) packets of max_packet bytes plus ~30 bytes of packet
    framing each, at 5 Gb/s 8b/10b (SS) or 10 Gb/s 128b/132b (SS+); labelled approximate, not a spec formula.
    """
    max_packet = int(max_packet or 0)
    mult = int(mult or 1)
    sp = (speed or "HS").upper()
    if sp in ("SS", "SS+"):
        bits = (max_packet + 30) * mult * 8
        if sp == "SS":
            return bits * 10 / 8 / 5e9 * 1e6
        return bits * 132 / 128 / 10e9 * 1e6
    if sp == "FS":
        return mult * t_fs_ns(max_packet, transfer) / 1000.0
    if sp == "LS":
        return mult * 8 * t_fs_ns(max_packet, transfer) / 1000.0
    return mult * t_hs_ns(max_packet, transfer) / 1000.0


def _cost_eq_us(max_packet: int, mult: int, budget_kind: str, transfer: str = "iso") -> float:
    """Cost in 'budget-equivalent us' (budget = 100) for the controller's budget model."""
    mult = int(mult or 1)
    if budget_kind == "intel_sw_blocks":
        blocks = math.ceil(int(max_packet) * mult / 4) + 26 * mult
        return blocks * HS_BUDGET_US / INTEL_SW_BLOCK_CAPACITY
    if budget_kind == "mtk_payload":
        return int(max_packet) * mult * HS_BUDGET_US / MTK_HS_PAYLOAD_BYTES
    return cost_us(max_packet, mult, "HS", transfer)


def verdict_for(load_us: float, budget_us: float = HS_BUDGET_US, bracket: dict | None = None) -> str:
    """'fits' / 'marginal' / 'over'. With a learned bracket {max_pass_us, min_fail_us} (both set, pass < fail):
    fits <= max_pass, over >= min_fail, marginal between. Otherwise fits <= 93.75% of the budget (75% of a
    microframe), marginal up to the budget, over above it. A prediction never blocks an attempt."""
    if bracket and bracket.get("max_pass_us") is not None and bracket.get("min_fail_us") is not None \
            and bracket["max_pass_us"] < bracket["min_fail_us"]:
        if load_us <= bracket["max_pass_us"] + 1e-9:
            return "fits"
        if load_us >= bracket["min_fail_us"] - 1e-9:
            return "over"
        return "marginal"
    if load_us <= MARGINAL_FRACTION * budget_us + 1e-9:
        return "fits"
    if load_us <= budget_us + 1e-9:
        return "marginal"
    return "over"


# ----------------------------------------------------------------------------------------------- policies
def _clean_controller_name(name: str | None) -> str | None:
    if not name:
        return None
    return re.sub(r"\s*-\s*\d+(\.\d+)*\s*\(Microsoft\)\s*$", "", name).strip() or name


def policy_for(controller: dict | None, learned: "LearnedPolicies | None" = None) -> dict[str, Any]:
    """High-speed domain policy for a controller (bandwidth_domain_model.md 4.2 with verifier V1/V4.7):

    {"hs_domain": "root_port"|"controller", "budget_us": 100.0, "budget_kind": "usb2_5113"|"intel_sw_blocks"|
     "mtk_payload", "uncertain": bool, "source": "table"|"hint"|"learned", "basis": str, "bracket": {...}|None}

    ``policy_hint`` on the controller ("root_port" / "controller" or a dict with those keys) overrides the table;
    a learned entry (LearnedPolicies) overrides both.
    """
    c = controller or {}
    pci = (c.get("pci_id") or "").lower()
    ven = pci.split(":")[0] if ":" in pci else (str(c.get("vendor") or "").lower() if re.fullmatch(
        r"[0-9a-fA-F]{4}", str(c.get("vendor") or "")) else "")
    kind = (c.get("kind") or "").lower()
    name = (c.get("name") or "").lower()
    vendor_text = str(c.get("vendor") or "").lower()
    pol: dict[str, Any] = {"hs_domain": "root_port", "budget_us": HS_BUDGET_US, "budget_kind": "usb2_5113",
                           "uncertain": True, "source": "table", "bracket": None,
                           "basis": "spec default (xHCI: each root port is a primary domain); unverified vendor"}
    if kind in ("ehci", "ohci", "uhci") or "ehci" in name or "enhanced host" in name:
        pol.update(hs_domain="controller", uncertain=False,
                   basis="EHCI: one high-speed bus for the whole controller (doc, Linux ehci-sched)")
    elif pci == "8086:1e31":
        pol.update(budget_kind="intel_sw_blocks", uncertain=False,
                   basis="Intel Panther Point: software bandwidth table, 20% reserve, 26 blocks/packet (doc)")
    elif ven == "8086" or "intel" in vendor_text or name.startswith("intel"):
        pol.update(uncertain=False,
                   basis="Intel xHCI: per USB 2.0 root port, threshold ~ USB 2.0 80% model "
                         + ("(measured on this model, 8086:7A60)" if pci == "8086:7a60"
                            else "(measured on 8086:7A60; other Intel xHCI assumed the same)"))
        if pci in MEASURED_BRACKETS:
            pol["bracket"] = dict(MEASURED_BRACKETS[pci])
    elif ven == "14c3" or "mediatek" in vendor_text:
        pol.update(budget_kind="mtk_payload", uncertain=False,
                   basis="MediaTek xHCI: per root port, 6144 B payload per microframe, no overhead (doc)")
    elif kind == "dwc3-apple" or ("apple" in vendor_text and "dwc" in name):
        pol.update(uncertain=False, basis="Apple silicon DWC3: one controller per USB-C connector (doc)")
    elif ven == "1022" or "amd" in vendor_text or "advanced micro" in vendor_text:
        pol.update(hs_domain="controller", uncertain=True,
                   basis="AMD xHCI: debugfs HS_BW fell on all root ports at once in the Linux commit's test log "
                         "(verifier V1); treated as pooled until measured")
    # collector / user hint
    hint = c.get("policy_hint")
    if isinstance(hint, str) and hint in ("root_port", "controller"):
        pol.update(hs_domain=hint, source="hint", basis=f"policy_hint={hint}; " + pol["basis"])
    elif isinstance(hint, dict):
        for k in ("hs_domain", "budget_us", "budget_kind", "uncertain", "bracket"):
            if k in hint:
                pol[k] = hint[k]
        pol["source"] = "hint"
    if learned is not None and pci:
        ent = learned.get(pci)
        if ent:
            if ent.get("hs_domain"):
                if ent["hs_domain"] != pol["hs_domain"]:
                    pol["basis"] = f"learned from {len(ent.get('events', []))} refusals; " + pol["basis"]
                pol["hs_domain"] = ent["hs_domain"]
                pol["source"] = "learned"
            br = ent.get("bracket") or {}
            if br.get("max_pass_us") is not None and br.get("min_fail_us") is not None:
                pol["bracket"] = dict(br)
    return pol


class LearnedPolicies:
    """Per controller model (pci_id) learned facts, persisted as JSON:

    {"schema": "skellycam.learned_policies/1",
     "controllers": {"8086:7a60": {"hs_domain": "root_port"|"controller"|None,
                                   "bracket": {"max_pass_us": float|None, "min_fail_us": float|None},
                                   "events": [{"utc","outcome","cls","domain_load_us","controller_load_us"}]}}}

    Escalation rule (bandwidth_domain_model.md 4.2, hardened per verifier V4.4): a bandwidth-class refusal whose
    domain load was < 75% of the budget while the controller-wide load was > 80% of it is a *pooling event*; only
    after ``min_events`` (default 2) such events is the controller flipped to ``hs_domain = "controller"``.
    The bracket records the largest domain load that streamed and the smallest that was refused at >= 75% of the
    budget (refusals below that say "pooled or hidden load", not "threshold"). Only valid for the accounting the
    loads were computed with (calibrated by default).
    """

    SCHEMA = "skellycam.learned_policies/1"

    def __init__(self, data: dict | None = None, path: str | os.PathLike | None = None, min_events: int = 2):
        self.path = Path(path) if path else None
        self.min_events = min_events
        self.data = data or {"schema": self.SCHEMA, "controllers": {}}
        self.data.setdefault("controllers", {})

    @classmethod
    def load(cls, path: str | os.PathLike, min_events: int = 2) -> "LearnedPolicies":
        p = Path(path)
        data = None
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                data = None
        return cls(data, p, min_events)

    def save(self, path: str | os.PathLike | None = None) -> Path:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save LearnedPolicies to")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, p)
        return p

    def get(self, pci_id: str) -> dict | None:
        return self.data["controllers"].get((pci_id or "").lower())

    def record(self, pci_id: str, outcome: str, domain_load_us: float, controller_load_us: float | None = None,
               cls: str | None = None, budget_us: float = HS_BUDGET_US, utc: str | None = None) -> dict:
        """Record one admission outcome ('pass' or 'refused') for a controller model; returns the entry.
        ``cls`` is classify_failure()['class'] for refusals."""
        ent = self.data["controllers"].setdefault((pci_id or "").lower(),
                                                  {"hs_domain": None, "bracket": {"max_pass_us": None,
                                                                                  "min_fail_us": None},
                                                   "events": []})
        ev = {"utc": utc, "outcome": outcome, "cls": cls, "domain_load_us": round(float(domain_load_us), 3),
              "controller_load_us": None if controller_load_us is None else round(float(controller_load_us), 3)}
        ent["events"].append(ev)
        br = ent.setdefault("bracket", {"max_pass_us": None, "min_fail_us": None})
        if outcome == "pass":
            if br.get("max_pass_us") is None or domain_load_us > br["max_pass_us"]:
                br["max_pass_us"] = round(float(domain_load_us), 3)
        elif outcome == "refused" and cls in ("bandwidth_certain", "bandwidth_probable"):
            if domain_load_us >= 0.75 * budget_us:
                if br.get("min_fail_us") is None or domain_load_us < br["min_fail_us"]:
                    br["min_fail_us"] = round(float(domain_load_us), 3)
            pooled = [e for e in ent["events"]
                      if e["outcome"] == "refused" and e["cls"] in ("bandwidth_certain", "bandwidth_probable")
                      and e["domain_load_us"] < 0.75 * budget_us
                      and (e["controller_load_us"] or 0) > 0.80 * budget_us]
            if len(pooled) >= self.min_events:
                ent["hs_domain"] = "controller"
        return ent


# ----------------------------------------------------------------------------------------------- snapshot index
class _Index:
    def __init__(self, snap: dict):
        self.snap = snap
        self.controllers = {c["id"]: c for c in snap.get("controllers", [])}
        self.ports = {p["id"]: p for p in snap.get("ports", [])}
        self.devices = {d["id"]: d for d in snap.get("devices", [])}
        self.cameras = {c["key"]: c for c in snap.get("cameras", [])}
        self.cam_by_dev = {c.get("device_id"): c for c in snap.get("cameras", [])}
        self.ports_by_hub: dict[Any, list] = {}
        for p in snap.get("ports", []):
            self.ports_by_hub.setdefault(p.get("hub_device_id"), []).append(p)

    def hub_chain(self, dev: dict) -> list[str]:
        """Hub device ids from the device's parent up to the hub on the root port (excludes dev itself)."""
        chain, seen = [], set()
        cur = dev
        while cur is not None:
            pid = cur.get("parent_device_id")
            if pid is None:
                port = self.ports.get(cur.get("port_id"))
                pid = port.get("hub_device_id") if port else None
            if pid is None or pid in seen or pid not in self.devices:
                break
            seen.add(pid)
            chain.append(pid)
            cur = self.devices[pid]
        return chain

    def root_port_of_port(self, port: dict | None) -> dict | None:
        seen = set()
        while port is not None and not port.get("is_root_port"):
            if port["id"] in seen:
                return None
            seen.add(port["id"])
            hub = self.devices.get(port.get("hub_device_id"))
            if hub is None:
                return None
            port = self.ports.get(hub.get("port_id"))
        return port

    def usb2_root(self, dev: dict) -> tuple[Any, Any]:
        """(controller_id, root_port_id) of the device's USB 2.0 chain (follows companion_id off a usb3 half)."""
        rp_id = dev.get("root_port_id")
        rp = self.ports.get(rp_id)
        if rp is None:
            rp = self.root_port_of_port(self.ports.get(dev.get("port_id")))
            rp_id = rp["id"] if rp else rp_id
        ctrl = dev.get("controller_id")
        if rp is not None:
            if rp.get("half") == "usb3" and (dev.get("speed") or "unknown") not in ("SS", "SS+") \
                    and rp.get("companion_id") in self.ports:
                rp = self.ports[rp["companion_id"]]
                rp_id = rp["id"]
            ctrl = rp.get("controller_id", ctrl)
        return ctrl, rp_id

    def port_hs_root(self, port: dict) -> tuple[Any, Any]:
        rp = self.root_port_of_port(port)
        if rp is None:
            return port.get("controller_id"), None
        if rp.get("half") == "usb3" and rp.get("companion_id") in self.ports:
            rp = self.ports[rp["companion_id"]]
        return rp.get("controller_id"), rp["id"]

    def chain_has_rmh(self, hub_ids: Iterable[str]) -> bool:
        for h in hub_ids:
            d = self.devices.get(h)
            if d and _vidpid(d.get("vid"), d.get("pid")) in INTEL_RMH_VIDPID:
                return True
        return False


def _policies_lookup(idx: _Index, policies: Any, learned: LearnedPolicies | None = None) -> dict:
    """controller_id -> policy dict. ``policies`` may be None, a LearnedPolicies, or {controller_id: policy}."""
    if isinstance(policies, LearnedPolicies):
        learned, policies = policies, None
    out = {}
    for cid, c in idx.controllers.items():
        if isinstance(policies, dict) and cid in policies:
            out[cid] = {**policy_for(c, learned), **policies[cid]}
        else:
            out[cid] = policy_for(c, learned)
    return out


def _speed(dev: dict) -> str:
    s = (dev.get("speed") or "unknown").upper()
    return {"SUPER": "SS", "SUPERPLUS": "SS+", "HIGH": "HS", "FULL": "FS", "LOW": "LS"}.get(s, s)


def _domain_key_idx(idx: _Index, dev: dict, pols: dict) -> tuple[str, str, Any, Any]:
    """(key, kind, controller_id, root_port_id) for a device."""
    sp = _speed(dev)
    if sp in ("SS", "SS+"):
        ctrl, rp = dev.get("controller_id"), dev.get("root_port_id")
        if rp is None:
            r = idx.root_port_of_port(idx.ports.get(dev.get("port_id")))
            rp = r["id"] if r else None
        if rp in idx.ports:
            ctrl = idx.ports[rp].get("controller_id", ctrl)
        return f"ss|{ctrl}|{rp}", "ss_link", ctrl, rp
    ctrl, rp = idx.usb2_root(dev)
    chain = idx.hub_chain(dev)
    if sp in ("FS", "LS") and not chain:
        return f"fs|{ctrl}|{rp}", "fs_root", ctrl, rp
    pol = pols.get(ctrl) or policy_for(idx.controllers.get(ctrl))
    if pol["hs_domain"] == "controller" or idx.chain_has_rmh(chain):
        return f"hs|{ctrl}|*", "controller", ctrl, None
    return f"hs|{ctrl}|{rp}", "hs_link", ctrl, rp


def domain_key(snapshot: dict, device_id: Any, policies: Any = None) -> str:
    """Bandwidth-domain key of a device: 'hs|<controller>|<usb2 root port>' (per-root-port controllers),
    'hs|<controller>|*' (pooled controller, EHCI, Intel RMH in the chain), 'ss|<controller>|<root port>'
    (SuperSpeed) or 'fs|<controller>|<root port>' (full/low speed directly on a root port)."""
    idx = _Index(snapshot)
    dev = idx.devices.get(device_id)
    if dev is None:
        raise KeyError(f"device {device_id!r} not in snapshot")
    return _domain_key_idx(idx, dev, _policies_lookup(idx, policies))[0]


def _budget(kind: str, pol: dict) -> float:
    if kind == "ss_link":
        return SS_BUDGET_US
    if kind == "fs_root":
        return FS_BUDGET_US
    return float(pol.get("budget_us") or HS_BUDGET_US)


def _pipe_cost(pipe: dict, dev_speed: str, kind: str, pol: dict, accounting: str) -> float:
    t = (pipe.get("type") or "iso").lower()
    if t not in ("iso", "int"):
        return 0.0
    if accounting != "full" and t != "iso":
        return 0.0
    mp, m = int(pipe.get("max_packet") or 0), int(pipe.get("mult") or 1)
    if mp <= 0:
        return 0.0
    if kind == "ss_link":
        return cost_us(mp, m, dev_speed if dev_speed in ("SS", "SS+") else "SS", t)
    if kind == "fs_root":
        return cost_us(mp, m, "LS" if dev_speed == "LS" else "FS", t)
    if dev_speed in ("FS", "LS"):
        return 0.0  # behind a TT: covered by the per-TT charge (full accounting only)
    return _cost_eq_us(mp, m, pol.get("budget_kind", "usb2_5113"), t)


def _device_load(idx: _Index, dev: dict, kind: str, pol: dict, accounting: str) -> float:
    sp = _speed(dev)
    return sum(_pipe_cost(p, sp, kind, pol, accounting) for p in dev.get("periodic_pipes") or [])


def _active_tts(idx: _Index, members: list[dict]) -> int:
    """Count active transaction translators: FS/LS devices with periodic pipes behind a high-speed hub
    (one TT per single-TT hub, one per port on a multi-TT hub)."""
    tts = set()
    for d in members:
        if _speed(d) not in ("FS", "LS") or not d.get("periodic_pipes"):
            continue
        chain = idx.hub_chain(d)
        for h in chain:  # the nearest HS hub upstream provides the TT
            hub = idx.devices.get(h)
            if hub and _speed(hub) in ("HS", "unknown", "UNKNOWN"):
                if (hub.get("hub_tt") or "single") == "multi":
                    tts.add((h, d.get("port_id")))
                else:
                    tts.add((h, None))
                break
    return len(tts)


def _domain_records(idx: _Index, pols: dict, accounting: str) -> dict[str, dict]:
    doms: dict[str, dict] = {}
    for dev in idx.devices.values():
        key, kind, ctrl, rp = _domain_key_idx(idx, dev, pols)
        pol = pols.get(ctrl) or policy_for(idx.controllers.get(ctrl))
        d = doms.setdefault(key, {"key": key, "kind": kind, "controller_id": ctrl, "root_port_id": rp,
                                  "members": [], "_devs": [], "cameras": [], "load_us": 0.0,
                                  "budget_us": _budget(kind, pol), "policy": pol})
        d["members"].append(dev["id"])
        d["_devs"].append(dev)
        cam = idx.cam_by_dev.get(dev["id"])
        if cam:
            d["cameras"].append(cam["key"])
        d["load_us"] += _device_load(idx, dev, kind, pol, accounting)
    for d in doms.values():
        if d["kind"] in ("hs_link", "controller"):
            ntt = _active_tts(idx, d["_devs"])
            d["active_tts"] = ntt
            if ntt:
                pol = d["policy"]
                if pol.get("budget_kind") == "intel_sw_blocks":
                    d["load_us"] += ntt * INTEL_SW_TT_BLOCKS * HS_BUDGET_US / INTEL_SW_BLOCK_CAPACITY
                elif accounting == "full":
                    d["load_us"] += ntt * FULL_ACCOUNTING_TT_US
    return doms


def _finish_domain(d: dict) -> dict:
    out = {k: v for k, v in d.items() if not k.startswith("_")}
    b = out["budget_us"]
    out["load_us"] = round(out["load_us"], 3)
    out["marginal_from_us"] = round(MARGINAL_FRACTION * b, 3)
    out["pct_budget"] = round(100 * out["load_us"] / b, 1) if b else None
    hs_usb2 = out["kind"] in ("hs_link", "controller") and out["policy"].get("budget_kind") == "usb2_5113"
    out["pct_microframe"] = round(100 * out["load_us"] / MICROFRAME_US, 1) if hs_usb2 else None
    out["uncertain"] = bool(out["policy"].get("uncertain"))
    out["verdict"] = verdict_for(out["load_us"], b, out["policy"].get("bracket"))
    return out


def compute_domains(snapshot: dict, policies: Any = None, accounting: str = "calibrated") -> list[dict]:
    """Observed bandwidth domains (only domains that have at least one device). Each:
    {key, kind ('hs_link'|'controller'|'ss_link'|'fs_root'), controller_id, root_port_id, members (device ids),
     cameras (camera keys), load_us (observed, from open periodic pipes), budget_us, marginal_from_us, pct_budget,
     pct_microframe (HS USB 2.0 model only), verdict, uncertain, policy, active_tts}.
    ``policies``: None, a LearnedPolicies, or {controller_id: policy overrides}."""
    idx = _Index(snapshot)
    pols = _policies_lookup(idx, policies)
    return [_finish_domain(d) for _, d in sorted(_domain_records(idx, pols, accounting).items())]


# ----------------------------------------------------------------------------------------------- modes and cache
_FMT_ALIASES = {"MJPEG": "MJPG", "JPEG": "MJPG", "YUYV": "YUY2", "YUV2": "YUY2", "H.264": "H264"}


def parse_mode(mode: Any) -> dict | None:
    """'MJPG 1280x720@30' / '1280x720@30' / 'MJPEG 640x480@29.97fps' / {format|fmt|subtype, width|w,
    height|h, fps} -> {"format": "MJPG", "width": 1280, "height": 720, "fps": 30.0}; None if unparsable."""
    if mode is None:
        return None
    if isinstance(mode, dict):
        fmt = mode.get("format") or mode.get("fmt") or mode.get("subtype") or "MJPG"
        w, h, fps = mode.get("width", mode.get("w")), mode.get("height", mode.get("h")), mode.get("fps")
        if w is None or h is None:
            return None
        fmt = str(fmt).upper()
        return {"format": _FMT_ALIASES.get(fmt, fmt), "width": int(w), "height": int(h),
                "fps": float(fps) if fps is not None else None}
    s = str(mode).strip()
    m = re.match(r"^(?:([A-Za-z0-9.]+)\s*[ :])?\s*(\d+)\s*[xX]\s*(\d+)(?:\s*@\s*([\d.]+)\s*(?:fps)?)?$", s)
    if not m:
        return None
    fmt = (m.group(1) or "MJPG").upper()
    return {"format": _FMT_ALIASES.get(fmt, fmt), "width": int(m.group(2)), "height": int(m.group(3)),
            "fps": float(m.group(4)) if m.group(4) else None}


def _fps_text(fps: float | None) -> str:
    if fps is None:
        return "?"
    return str(int(fps)) if abs(fps - round(fps)) < 1e-6 else f"{fps:.3f}".rstrip("0").rstrip(".")


def mode_text(mode: Any) -> str:
    """Human text for a mode: '1280x720 MJPEG 30 fps' (falls back to str(mode))."""
    p = parse_mode(mode)
    if not p:
        return str(mode) if mode is not None else "the requested mode"
    fmt = "MJPEG" if p["format"] == "MJPG" else p["format"]
    return f"{p['width']}x{p['height']} {fmt} {_fps_text(p['fps'])} fps" if p["fps"] else \
        f"{p['width']}x{p['height']} {fmt}"


def _bcd_text(bcd: Any) -> str:
    if bcd is None or bcd == "":
        return "????"
    if isinstance(bcd, int):
        return f"{bcd:04x}"
    s = str(bcd).lower()
    return s[2:] if s.startswith("0x") else s


class ModeAltCache:
    """Learned alt setting per camera mode, persisted as JSON keyed (vid, pid, bcd_device, format, w, h, fps).

    Key text: '046d:085c:0016:MJPG:1280x720@30'. Entry: {"alt", "max_packet", "mult", "source", "utc", "note"}.
    The camera picks its alt from its own PROBE answer, which a non-owning app cannot send, so the only way to
    know a mode's real cost is to open it once alone and read the granted alt back (Windows open pipes, Linux
    sysfs bAlternateSetting). ``get`` falls back to an entry for the same VID:PID and mode with another bcdDevice,
    marked ``other_firmware`` (whether the alt varies with firmware is an open question)."""

    SCHEMA = "skellycam.mode_alt_cache/1"

    def __init__(self, entries: dict | None = None, path: str | os.PathLike | None = None):
        self.entries: dict[str, dict] = dict(entries or {})
        self.path = Path(path) if path else None

    @staticmethod
    def make_key(vid: Any, pid: Any, bcd_device: Any, fmt: str, w: int, h: int, fps: float | None) -> str:
        f = str(fmt or "MJPG").upper()
        f = _FMT_ALIASES.get(f, f)
        return f"{_vidpid(vid, pid)}:{_bcd_text(bcd_device)}:{f}:{int(w)}x{int(h)}@{_fps_text(fps)}"

    @classmethod
    def load(cls, path: str | os.PathLike) -> "ModeAltCache":
        p = Path(path)
        entries = {}
        if p.exists():
            try:
                entries = json.loads(p.read_text(encoding="utf-8")).get("entries", {})
            except ValueError:
                entries = {}
        return cls(entries, p)

    def save(self, path: str | os.PathLike | None = None) -> Path:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save ModeAltCache to")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"schema": self.SCHEMA, "entries": self.entries}, indent=1, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, p)
        return p

    def put(self, vid: Any, pid: Any, bcd_device: Any, fmt: str, w: int, h: int, fps: float | None, alt: int,
            max_packet: int | None = None, mult: int | None = None, source: str = "observed",
            utc: str | None = None, note: str | None = None) -> str:
        k = self.make_key(vid, pid, bcd_device, fmt, w, h, fps)
        self.entries[k] = {"alt": alt, "max_packet": max_packet, "mult": mult, "source": source, "utc": utc,
                           "note": note}
        return k

    def get(self, vid: Any, pid: Any, bcd_device: Any, fmt: str, w: int, h: int, fps: float | None) -> dict | None:
        k = self.make_key(vid, pid, bcd_device, fmt, w, h, fps)
        if k in self.entries:
            return {**self.entries[k], "key": k, "other_firmware": False}
        head = f"{_vidpid(vid, pid)}:"
        tail = k.split(":", 3)[3]
        for kk, e in self.entries.items():
            if kk.startswith(head) and kk.split(":", 3)[3] == tail:
                return {**e, "key": kk, "other_firmware": True}
        return None

    def get_mode(self, vid: Any, pid: Any, bcd_device: Any, mode: Any) -> dict | None:
        p = parse_mode(mode)
        if not p:
            return None
        return self.get(vid, pid, bcd_device, p["format"], p["width"], p["height"], p["fps"])

    def modes_for(self, vid: Any, pid: Any, bcd_device: Any = None) -> list[dict]:
        """Every cached mode of this VID:PID (exact bcd first, others marked other_firmware)."""
        head = f"{_vidpid(vid, pid)}:"
        bcd = _bcd_text(bcd_device)
        out, seen = [], set()
        for kk in sorted(self.entries, key=lambda x: (x.split(":")[2] != bcd, x)):
            if not kk.startswith(head):
                continue
            parts = kk.split(":", 3)
            tail = parts[3]
            if tail in seen:
                continue
            seen.add(tail)
            fmt, rest = tail.split(":", 1)
            mode = parse_mode(f"{fmt} {rest}")
            out.append({**self.entries[kk], "key": kk, "mode": mode, "other_firmware": parts[2] != bcd})
        return out

    def merge(self, other: "ModeAltCache | dict", overwrite: bool = True) -> int:
        """Copy entries from another cache (or its entries dict); ``overwrite`` False keeps existing entries.
        Returns the number of entries copied."""
        src = other.entries if isinstance(other, ModeAltCache) else dict(other or {})
        n = 0
        for k, e in src.items():
            if overwrite or k not in self.entries:
                self.entries[k] = dict(e)
                n += 1
        return n

    def __len__(self) -> int:
        return len(self.entries)


# ----------------------------------------------------------------------------------------------- prediction
def _alt_entry(cam: dict, alt: Any) -> dict | None:
    for a in cam.get("alt_table") or []:
        if a.get("alt") == alt:
            return a
    return None


def _largest_alt(cam: dict, budget_kind: str, speed: str) -> dict | None:
    best, bc = None, -1.0
    for a in cam.get("alt_table") or []:
        if not a.get("max_packet"):
            continue
        c = _alt_cost(a.get("max_packet"), a.get("mult"), budget_kind, speed)
        if c > bc:
            best, bc = a, c
    return best


def _alt_cost(mp: Any, mult: Any, budget_kind: str, speed: str) -> float:
    if speed in ("SS", "SS+"):
        return cost_us(int(mp), int(mult or 1), speed)
    return _cost_eq_us(int(mp), int(mult or 1), budget_kind)


def _resolve_request_cost(idx: _Index, req: dict, cam: dict | None, dev: dict | None, pol: dict,
                          cache: ModeAltCache | None) -> dict:
    """Cost of one request: explicit packet > explicit alt > cache > largest alt (worst case) > unknown."""
    speed = _speed(dev) if dev else "HS"
    bk = pol.get("budget_kind", "usb2_5113")
    out = {"camera_key": req.get("camera_key"), "mode": req.get("mode"), "alt": None, "max_packet": None,
           "mult": None, "cost_us": None, "cost_source": "unknown"}
    if req.get("max_packet"):
        out.update(max_packet=int(req["max_packet"]), mult=int(req.get("mult") or 1), alt=req.get("alt"),
                   cost_source="request")
    elif req.get("alt") is not None and cam and _alt_entry(cam, req["alt"]):
        a = _alt_entry(cam, req["alt"])
        out.update(alt=a["alt"], max_packet=a["max_packet"], mult=a.get("mult") or 1, cost_source="request_alt")
    else:
        hit = None
        if cache is not None and dev is not None and req.get("mode") is not None:
            hit = cache.get_mode(dev.get("vid"), dev.get("pid"), dev.get("bcd_device"), req["mode"])
        if hit:
            mp, mult = hit.get("max_packet"), hit.get("mult")
            if not mp and cam and _alt_entry(cam, hit.get("alt")):
                a = _alt_entry(cam, hit["alt"])
                mp, mult = a["max_packet"], a.get("mult") or 1
            if mp:
                out.update(alt=hit.get("alt"), max_packet=int(mp), mult=int(mult or 1),
                           cost_source="cache_other_firmware" if hit.get("other_firmware") else "cache")
        if out["max_packet"] is None and cam:
            a = _largest_alt(cam, bk, speed)
            if a:
                out.update(alt=a["alt"], max_packet=a["max_packet"], mult=a.get("mult") or 1,
                           cost_source="worst_case")
    if out["max_packet"]:
        out["cost_us"] = round(_alt_cost(out["max_packet"], out["mult"], bk, speed), 3)
    return out


def _dev_name(dev: dict | None, cam: dict | None = None) -> str:
    if cam and cam.get("name"):
        return cam["name"]
    if dev:
        return dev.get("name") or f"USB device {_vidpid(dev.get('vid'), dev.get('pid')).upper()}"
    return "a camera"


def _port_number_text(port: dict | None) -> str | None:
    if not port:
        return None
    lp = port.get("label_parts") or {}
    n = port.get("port_number")
    acpi = lp.get("acpi_name")
    if n is not None and acpi:
        return f"port {n} ({acpi})"
    if n is not None:
        return f"port {n}"
    return acpi


def _controller_display(idx: _Index, ctrl_id: Any) -> str:
    c = idx.controllers.get(ctrl_id) or {}
    name = _clean_controller_name(c.get("name"))
    if name:
        return name
    if c.get("pci_id"):
        n = list(idx.controllers).index(ctrl_id) + 1 if ctrl_id in idx.controllers else "?"
        return f"USB controller #{n} (PCI {c['pci_id'].upper()})"
    return "USB controller"


def _shared_hop(idx: _Index, dom: dict, dev_ids: list) -> tuple[str, bool]:
    """Text naming what the devices share, and whether it is a dock / integrated hub."""
    ctrl_text = _controller_display(idx, dom.get("controller_id"))
    if dom.get("kind") == "controller":
        return f"the same USB controller ({ctrl_text}), whose ports all share one USB 2.0 bus", False
    devs = [idx.devices[d] for d in dev_ids if d in idx.devices]
    rp = idx.ports.get(dom.get("root_port_id"))
    rp_text = _port_number_text(rp)
    chains = [idx.hub_chain(d) for d in devs]
    common = None
    if chains and all(chains):
        for h in chains[0]:
            if all(h in c for c in chains[1:]):
                common = h
                break
    is_dock = False
    if common:
        hub = idx.devices[common]
        is_dock = bool(hub.get("is_dock"))
        hub_name = hub.get("name") or "USB hub"
        vp = _vidpid(hub.get("vid"), hub.get("pid")).upper()
        where = f" on {rp_text} of the {ctrl_text}" if rp_text else f" on the {ctrl_text}"
        return f"the same USB hub ({hub_name} {vp}){where}", is_dock
    if rp_text:
        return f"the same port on the {ctrl_text} ({rp_text})", False
    return "the same USB connection to the computer", False


def predict(snapshot: dict, requests: list[dict], mode_alt_cache: ModeAltCache | None = None,
            policies: Any = None, accounting: str = "calibrated") -> dict:
    """Predict per-domain load if the requested cameras stream in the requested modes.

    requests: [{"camera_key", "mode" ('MJPG 1280x720@30' or dict), "alt"|None, "max_packet"|None, "mult"|None}].
    Cost per request: explicit max_packet/mult > explicit alt (camera alt_table) > mode_alt_cache > the camera's
    largest alt ('worst_case', the only safe bound before a mode has been opened once) > unknown.
    A requested camera's currently open pipes are replaced by its requested cost; every other device's open
    periodic pipes stay in the load.

    Returns {"domains": [{key, kind, controller_id, root_port_id, predicted_load_us, other_load_us, budget_us,
                          pct_budget, pct_microframe, verdict ('fits'|'marginal'|'over'), members (camera keys),
                          incomplete, policy}],
             "conflicts": [{domain_key, cameras, camera_info, other_load_us, other_pct_budget, other_devices,
                            predicted_load_us, pct_total, pct_microframe, verdict, shared_hop, is_dock,
                            controller_id, controller_name, root_port_id, uncertain, policy_source,
                            other_controllers}],
             "warnings": [same shape as conflicts, for 'marginal' domains],
             "requests": [resolved cost per request]}
    A conflict is any domain predicted 'over' that holds at least one requested camera.
    """
    idx = _Index(snapshot)
    pols = _policies_lookup(idx, policies)
    recs = _domain_records(idx, pols, accounting)
    req_dev_ids = set()
    resolved = []
    by_dom: dict[str, list[dict]] = {}
    for req in requests:
        cam = idx.cameras.get(req.get("camera_key"))
        dev = idx.devices.get(cam.get("device_id")) if cam else None
        if dev is None:
            r = {"camera_key": req.get("camera_key"), "mode": req.get("mode"), "cost_us": None,
                 "cost_source": "unknown", "error": "camera not in snapshot"}
            resolved.append(r)
            continue
        key, kind, ctrl, rp = _domain_key_idx(idx, dev, pols)
        pol = pols.get(ctrl) or policy_for(idx.controllers.get(ctrl))
        r = _resolve_request_cost(idx, req, cam, dev, pol, mode_alt_cache)
        r.update(domain_key=key, device_id=dev["id"], name=_dev_name(dev, cam),
                 mode_text=mode_text(req.get("mode")))
        resolved.append(r)
        req_dev_ids.add(dev["id"])
        by_dom.setdefault(key, []).append(r)
    domains, conflicts, warnings = [], [], []
    other_ctrl_names = {cid: _controller_display(idx, cid) for cid in idx.controllers}
    for key, reqs in sorted(by_dom.items()):
        rec = recs.get(key)
        if rec is None:
            continue
        pol = rec["policy"]
        other = 0.0
        other_devs = []
        for dev in rec["_devs"]:
            if dev["id"] in req_dev_ids:
                continue
            ld = _device_load(idx, dev, rec["kind"], pol, accounting)
            other += ld
            if not dev.get("is_hub"):
                other_devs.append({"device_id": dev["id"], "name": _dev_name(dev, idx.cam_by_dev.get(dev["id"])),
                                   "load_us": round(ld, 3)})
        if rec["kind"] in ("hs_link", "controller"):
            ntt = rec.get("active_tts") or 0
            if pol.get("budget_kind") == "intel_sw_blocks":
                other += ntt * INTEL_SW_TT_BLOCKS * HS_BUDGET_US / INTEL_SW_BLOCK_CAPACITY
            elif accounting == "full":
                other += ntt * FULL_ACCOUNTING_TT_US
        req_sum = sum(r["cost_us"] or 0.0 for r in reqs)
        total = other + req_sum
        b = rec["budget_us"]
        hs_usb2 = rec["kind"] in ("hs_link", "controller") and pol.get("budget_kind") == "usb2_5113"
        verdict = verdict_for(total, b, pol.get("bracket"))
        d = {"key": key, "kind": rec["kind"], "controller_id": rec["controller_id"],
             "root_port_id": rec["root_port_id"], "predicted_load_us": round(total, 3),
             "other_load_us": round(other, 3), "budget_us": b, "pct_budget": round(100 * total / b, 1),
             "pct_microframe": round(100 * total / MICROFRAME_US, 1) if hs_usb2 else None,
             "verdict": verdict, "members": [r["camera_key"] for r in reqs],
             "cost_sources": {r["camera_key"]: r["cost_source"] for r in reqs},
             "incomplete": any(r["cost_us"] is None for r in reqs), "uncertain": bool(pol.get("uncertain")),
             "policy": pol}
        domains.append(d)
        if verdict in ("over", "marginal"):
            hop, is_dock = _shared_hop(idx, rec, [r["device_id"] for r in reqs])
            c = {"domain_key": key, "cameras": [r["camera_key"] for r in reqs],
                 "camera_info": [{"key": r["camera_key"], "name": r["name"], "mode": r.get("mode"),
                                  "mode_text": r["mode_text"], "alt": r.get("alt"), "cost_us": r["cost_us"],
                                  "pct_budget": None if r["cost_us"] is None else round(100 * r["cost_us"] / b, 1),
                                  "pct_microframe": (None if (r["cost_us"] is None or not hs_usb2)
                                                     else round(100 * r["cost_us"] / MICROFRAME_US, 1)),
                                  "cost_source": r["cost_source"]} for r in reqs],
                 "other_load_us": round(other, 3), "other_pct_budget": round(100 * other / b, 1),
                 "other_devices": other_devs, "predicted_load_us": round(total, 3),
                 "budget_us": b, "pct_total": round(100 * total / b, 1), "pct_microframe": d["pct_microframe"],
                 "verdict": verdict, "shared_hop": hop, "is_dock": is_dock, "kind": rec["kind"],
                 "controller_id": rec["controller_id"],
                 "controller_name": _controller_display(idx, rec["controller_id"]),
                 "root_port_id": rec["root_port_id"], "uncertain": bool(pol.get("uncertain")),
                 "policy_source": pol.get("source"), "policy_hs_domain": pol.get("hs_domain"),
                 "other_controllers": [n for cid, n in other_ctrl_names.items() if cid != rec["controller_id"]]}
            (conflicts if verdict == "over" else warnings).append(c)
    return {"domains": domains, "conflicts": conflicts, "warnings": warnings, "requests": resolved,
            "accounting": accounting}


# ----------------------------------------------------------------------------------------------- error codes
HRESULT_NAMES: dict[int, str] = {
    0x800718CF: "HRESULT_FROM_WIN32(6351): camera interface lacks USB bandwidth",
    0x80000700: "USBD_STATUS_NO_BANDWIDTH",
    0xC00D3704: "MF_E_HW_MFT_FAILED_START_STREAMING",
    0xC00D3EA2: "MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED",
    0xC00D3EA3: "MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED",
    0xC00D7167: "MF_E_REBOOT_REQUIRED",
    0xC00D36B2: "MF_E_INVALIDREQUEST",
    0xC00D36B3: "MF_E_INVALIDSTREAMNUMBER",
    0xC00D36B4: "MF_E_INVALIDMEDIATYPE",
    0xC00D36B5: "MF_E_NOTACCEPTING",
    0xC00D36B6: "MF_E_NOT_INITIALIZED",
    0xC00D36B9: "MF_E_NO_MORE_TYPES",
    0xC00D36BB: "MF_E_UNEXPECTED",
    0xC00D36C8: "MF_E_NO_SAMPLE_TIMESTAMP",
    0xC00D36E6: "MF_E_ATTRIBUTENOTFOUND",
    0xC00D3E82: "MF_E_INVALID_STATE_TRANSITION",
    0xC00D3E84: "MF_E_END_OF_STREAM",
    0xC00D3E85: "MF_E_SHUTDOWN",
    0xC00D5212: "MF_E_TOPO_CODEC_NOT_FOUND",
    0xC00DA7FD: "MF_E_HW_STREAM_NOT_CONNECTED",
    0xC00DABE0: "MF_E_NO_CAPTURE_DEVICES_AVAILABLE",
    0xC00DABE7: "MF_E_CAPTURE_SOURCE_NO_VIDEO_STREAM_PRESENT",
    0xC00DABED: "MF_E_UNSUPPORTED_CAPTURE_DEVICE_PRESENT",
    0xA00F4271: "0xA00F4271 (Camera app / MediaCapture start failure)",
    0x80070005: "E_ACCESSDENIED",
    0x80004005: "E_FAIL",
    0x80004004: "E_ABORT",
    0x80004001: "E_NOTIMPL",
    0x80004002: "E_NOINTERFACE",
    0x80004003: "E_POINTER",
    0x8000FFFF: "E_UNEXPECTED",
    0x8007000E: "E_OUTOFMEMORY",
    0x80070057: "E_INVALIDARG",
    0x80070002: "HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND)",
    0x80070006: "E_HANDLE",
    0x80070015: "HRESULT_FROM_WIN32(ERROR_NOT_READY)",
    0x8007001F: "HRESULT_FROM_WIN32(ERROR_GEN_FAILURE)",
    0x80070020: "HRESULT_FROM_WIN32(ERROR_SHARING_VIOLATION)",
    0x80070032: "HRESULT_FROM_WIN32(ERROR_NOT_SUPPORTED)",
    0x80070079: "HRESULT_FROM_WIN32(ERROR_SEM_TIMEOUT)",
    0x800700AA: "HRESULT_FROM_WIN32(ERROR_BUSY)",
    0x800701B1: "HRESULT_FROM_WIN32(ERROR_NO_SUCH_DEVICE)",
    0x800701E3: "HRESULT_FROM_WIN32(ERROR_DEVICE_HARDWARE_ERROR)",
    0x800703E3: "HRESULT_FROM_WIN32(ERROR_OPERATION_ABORTED)",
    0x8007045D: "HRESULT_FROM_WIN32(ERROR_IO_DEVICE)",
    0x8007048F: "HRESULT_FROM_WIN32(ERROR_DEVICE_NOT_CONNECTED)",
    0x80070490: "HRESULT_FROM_WIN32(ERROR_NOT_FOUND)",
    0x800704EC: "HRESULT_FROM_WIN32(ERROR_ACCESS_DISABLED_BY_POLICY)",
    0x800705AA: "HRESULT_FROM_WIN32(ERROR_NO_SYSTEM_RESOURCES)",
    0x800705B4: "HRESULT_FROM_WIN32(ERROR_TIMEOUT)",
    0x80070651: "HRESULT_FROM_WIN32(ERROR_DEVICE_REMOVED)",
    0x800710DF: "HRESULT_FROM_WIN32(ERROR_DEVICE_NOT_AVAILABLE)",
}
_HRESULT_BY_SHORT = {v.split(":")[0].split(" ")[0]: k for k, v in HRESULT_NAMES.items()}
_HRESULT_BY_SHORT.update({"ERROR_GEN_FAILURE": 0x8007001F, "ERROR_BUSY": 0x800700AA,
                          "ERROR_NO_SYSTEM_RESOURCES": 0x800705AA, "ERROR_SHARING_VIOLATION": 0x80070020,
                          "ERROR_DEVICE_NOT_CONNECTED": 0x8007048F, "ERROR_NOT_FOUND": 0x80070490})

LINUX_ERRNO = {1: "EPERM", 2: "ENOENT", 4: "EINTR", 5: "EIO", 6: "ENXIO", 11: "EAGAIN", 12: "ENOMEM", 13: "EACCES",
               16: "EBUSY", 19: "ENODEV", 22: "EINVAL", 25: "ENOTTY", 28: "ENOSPC", 32: "EPIPE", 62: "ETIME",
               71: "EPROTO", 75: "EOVERFLOW", 95: "EOPNOTSUPP", 108: "ESHUTDOWN", 110: "ETIMEDOUT",
               121: "EREMOTEIO"}
MACOS_ERRNO = {1: "EPERM", 2: "ENOENT", 5: "EIO", 6: "ENXIO", 12: "ENOMEM", 13: "EACCES", 16: "EBUSY",
               19: "ENODEV", 22: "EINVAL", 28: "ENOSPC", 32: "EPIPE", 60: "ETIMEDOUT"}
#: IOKit IOReturn values (IOReturn.h: iokit_common_err(0x2bc + n) = 0xE0000000 | code)
IORETURN_NAMES = {0xE00002BC: "kIOReturnError", 0xE00002BD: "kIOReturnNoMemory", 0xE00002BE: "kIOReturnNoResources",
                  0xE00002C0: "kIOReturnNoDevice", 0xE00002C1: "kIOReturnNotPrivileged",
                  0xE00002C2: "kIOReturnBadArgument", 0xE00002C5: "kIOReturnExclusiveAccess",
                  0xE00002C7: "kIOReturnUnsupported", 0xE00002CA: "kIOReturnIOError", 0xE00002CD: "kIOReturnNotOpen",
                  0xE00002D5: "kIOReturnBusy", 0xE00002D6: "kIOReturnTimeout", 0xE00002D8: "kIOReturnNotReady",
                  0xE00002D9: "kIOReturnNotAttached", 0xE00002E2: "kIOReturnNotPermitted",
                  0xE00002E9: "kIOReturnDeviceError", 0xE00002EB: "kIOReturnAborted",
                  0xE00002EC: "kIOReturnNoBandwidth", 0xE00002ED: "kIOReturnNotResponding",
                  0xE00002F0: "kIOReturnNotFound"}
#: AVFoundation AVError codes (from AVError.h as remembered; verify on the first Mac run)
AVERROR_NAMES = {-11800: "AVErrorUnknown", -11804: "AVErrorDeviceAlreadyUsedByAnotherSession",
                 -11805: "AVErrorNoDataCaptured", -11808: "AVErrorDeviceWasDisconnected",
                 -11814: "AVErrorDeviceNotConnected", -11815: "AVErrorDeviceInUseByAnotherApplication",
                 -11817: "AVErrorDeviceLockedForConfigurationByAnotherProcess",
                 -11819: "AVErrorMediaServicesWereReset", -11852: "AVErrorApplicationIsNotAuthorizedToUseDevice"}
LIBUSB_NAMES = {-1: "LIBUSB_ERROR_IO", -3: "LIBUSB_ERROR_ACCESS", -4: "LIBUSB_ERROR_NO_DEVICE",
                -6: "LIBUSB_ERROR_BUSY", -7: "LIBUSB_ERROR_TIMEOUT", -9: "LIBUSB_ERROR_PIPE",
                -11: "LIBUSB_ERROR_NO_MEM"}


def hresult_name(code: Any) -> str | None:
    """Symbolic name of an HRESULT (int, signed int or '0x...' string), or None."""
    try:
        v = int(code, 16) if isinstance(code, str) and code.lower().startswith("0x") else int(code)
    except (TypeError, ValueError):
        return None
    v &= 0xFFFFFFFF
    n = HRESULT_NAMES.get(v)
    if n:
        return n.split(":")[0]
    if (v & 0xFFFF0000) == 0x80070000:
        return f"HRESULT_FROM_WIN32({v & 0xFFFF})"
    return None


def _norm_code(osname: str, code: Any) -> tuple[int | None, str | None]:
    """(numeric code, symbolic name) from an int, '0x...' text, decimal text, 'OSError(5)', '[WinError 5]',
    'Errno 28', an errno name ('ENOSPC') or a known HRESULT / IOReturn symbol."""
    if code is None:
        return None, None
    if isinstance(code, bool):
        return None, None
    if isinstance(code, int):
        v = code
    else:
        s = str(code).strip()
        if not s:
            return None, None
        m = re.search(r"0x([0-9a-fA-F]{1,8})", s)
        if m:
            v = int(m.group(1), 16)
        elif re.fullmatch(r"-?\d+", s):
            v = int(s)
        else:
            m = re.search(r"(?:OSError|WinError|Errno|errno)\D{0,3}(-?\d+)", s)
            if m:
                v = int(m.group(1))
            else:
                up = s.upper()
                if s.lower() in ("timeout", "timed_out", "timed out", "watchdog", "hang", "hung"):
                    return None, "timeout"
                if up.split("(")[0] in _HRESULT_BY_SHORT:
                    v = _HRESULT_BY_SHORT[up.split("(")[0]]
                    return v, hresult_name(v)
                for k, nm in IORETURN_NAMES.items():
                    if nm.lower() in s.lower():
                        return k, nm
                for k, nm in AVERROR_NAMES.items():
                    if nm.lower() in s.lower():
                        return k, nm
                tables = (MACOS_ERRNO, LINUX_ERRNO) if osname == "macos" else (LINUX_ERRNO, MACOS_ERRNO)
                for table in tables:
                    for num, nm in table.items():
                        if up == nm or re.search(rf"\b{nm}\b", up):
                            return num, nm
                return None, s
    if osname == "windows":
        if v < 0 and v >= -0x80000000:
            v &= 0xFFFFFFFF
        name = hresult_name(v) if v > 0xFFFF else ({5: "OSError(5)"}.get(v) or f"code {v}")
        return v, name
    if osname == "macos":
        if v < 0 and v in AVERROR_NAMES:
            return v, AVERROR_NAMES[v]
        if v < 0 and v >= -0x80000000 and (v & 0xFFFFFFFF) in IORETURN_NAMES:
            v &= 0xFFFFFFFF
        if v in IORETURN_NAMES:
            return v, IORETURN_NAMES[v]
        return abs(v), MACOS_ERRNO.get(abs(v), f"code {v}")
    return abs(v), LINUX_ERRNO.get(abs(v), f"code {v}")


#: An open that fails after longer than this met a device that was dropping off the bus (re-enumerating), not a
#: bandwidth refusal: on Gerald 2026-11-06 refusals failed in 0.50-0.68 s (generic) / 1.02-1.47 s (C922), the
#: not-ready opens in 3.66-10.36 s (multi_topo.md verifier note 5).
DEVICE_NOT_READY_OPEN_S = 2.0
#: FFmpeg dshow log line that marks a graph that could not even be built (device not ready), as opposed to the
#: "Could not run graph" signature of a refused start.
DSHOW_RENDERSTREAM_TEXT = "could not renderstream"


def log_text(log: Any) -> str:
    """Flatten an FFmpeg log (str, [str], or [{"msg": str}]) into one lower-case string."""
    if not log:
        return ""
    if isinstance(log, str):
        return log.lower()
    parts = []
    for x in log:
        parts.append(str(x.get("msg") or x.get("message") or "") if isinstance(x, dict) else str(x))
    return "\n".join(parts).lower()


def _device_not_ready(ctx: dict) -> str | None:
    """Reason text when the context says the camera was not ready (re-enumerating), else None."""
    why = []
    if DSHOW_RENDERSTREAM_TEXT in log_text(ctx.get("log")):
        why.append("the DirectShow graph could not be built ('Could not RenderStream to connect pins')")
    od = ctx.get("open_duration_s")
    if isinstance(od, (int, float)) and od > DEVICE_NOT_READY_OPEN_S:
        why.append(f"the open failed only after {od:.2f} s (refusals fail within {DEVICE_NOT_READY_OPEN_S:g} s)")
    if ctx.get("device_gone"):
        why.append("the camera was removed or re-arrived within about 1 s of the failure")
    return "; ".join(why) if why else None


def classify_failure(os: str, code: Any, context: dict | None = None) -> dict[str, Any]:  # noqa: A002
    """Classify a camera open/stream failure, then apply the device-not-ready override (see below).

    Extra context keys for the override: log (FFmpeg log lines), open_duration_s (seconds from launch to the
    failure), device_gone (bool: the camera was removed or re-arrived within about 1 s of the failure end).
    A failure classed bandwidth_probable / other / timeout becomes ``device_not_ready`` when the log has
    "Could not RenderStream", the open took longer than DEVICE_NOT_READY_OPEN_S, or device_gone is set
    (bandwidth_certain, device_error, in_use and permission are never overridden).
    """
    out = _classify_failure_base(os, code, context)
    ctx = dict(context or {})
    if out.get("class") in ("bandwidth_probable", "other") and "could not run graph" in log_text(ctx.get("log")):
        out["reason"] = f"{out.get('reason')} [FFmpeg log: 'Could not run graph']"
    if out.get("class") in ("bandwidth_probable", "other", "timeout"):
        why = _device_not_ready(ctx)
        if why:
            out["class_before_override"] = out["class"]
            out["reason_before_override"] = out.get("reason")
            out.update({"class": "device_not_ready", "retry_advised": True,
                        "reason": f"camera not ready (re-enumerating), not a bandwidth refusal: {why}"})
    return out


def _classify_failure_base(os: str, code: Any, context: dict | None = None) -> dict[str, Any]:  # noqa: A002
    """Classify a camera open/stream failure.

    os: 'windows' | 'linux' | 'macos'. code: HRESULT (int / '0x800718CF' / signed int), errno (int or name such
    as 'ENOSPC'), 'OSError(5)', an IOReturn/AVError code, a libusb code with context api='libusb', 'timeout', or
    None (e.g. zero frames with no error).
    context (all optional): api ('mf','ds','pyav_ds','opencv','v4l2','avf','libusb'), stage ('activate','open',
    'settype','first_frame','streamon','control',...), timed_out (bool), frames (int), other_streaming_in_domain
    (bool: another camera in the same bandwidth domain was streaming), predicted_verdict ('fits'|'marginal'|
    'over'), in_use_by_other (bool, e.g. IMFSensorActivityMonitor), privacy_denied (bool), controller_pci_id.

    Returns {"class": "bandwidth_certain"|"bandwidth_probable"|"in_use"|"device_error"|"permission"|"timeout"|
    "device_not_ready"|"other", "reason", "code", "code_hex", "name", "retry_advised"}.
    Rules: bandwidth_domain_model.md 5 step 4 and verifier notes (EIO at STREAMON = "no fast enough alt", not
    contention; Panther Point ENOMEM; libusb -1 at stream start).
    """
    ctx = dict(context or {})
    osn = (os or "").lower()
    osn = {"win32": "windows", "darwin": "macos"}.get(osn, osn)
    api = (ctx.get("api") or "").lower()
    stage = (ctx.get("stage") or "").lower()
    contention = bool(ctx.get("other_streaming_in_domain")) and ctx.get("predicted_verdict") in ("over", "marginal")
    num, name = _norm_code(osn, code)
    out: dict[str, Any] = {"class": "other", "reason": "", "code": num if num is not None else code,
                           "code_hex": (f"0x{num & 0xFFFFFFFF:08X}" if isinstance(num, int) and
                                        (num > 0xFFFF or num < 0) else None),
                           "name": name, "retry_advised": False}

    def done(cls: str, reason: str, retry: bool = False) -> dict:
        out.update({"class": cls, "reason": reason, "retry_advised": retry})
        return out

    if ctx.get("timed_out") or name == "timeout":
        return done("timeout", "the call did not finish before the watchdog timeout (hang recorded, child killed)")

    lv = None
    if api == "libusb":
        try:
            lv = int(code) if not isinstance(code, bool) else None
        except (TypeError, ValueError):
            lv = next((k for k, v in LIBUSB_NAMES.items() if v in str(code).upper()), None)
    if lv is not None:
        out["code"], out["code_hex"] = lv, None
        out["name"] = LIBUSB_NAMES.get(lv, f"libusb {lv}")
        if lv == -1:
            if contention:
                return done("bandwidth_probable", "LIBUSB_ERROR_IO at stream start while another camera in the "
                                                  "same domain streams and the predicted load is over", True)
            return done("device_error", "LIBUSB_ERROR_IO")
        if lv == -6:
            return done("in_use", "LIBUSB_ERROR_BUSY")
        if lv == -3:
            return done("permission", "LIBUSB_ERROR_ACCESS")
        if lv == -4:
            return done("device_error", "LIBUSB_ERROR_NO_DEVICE")
        if lv == -7:
            return done("timeout", "LIBUSB_ERROR_TIMEOUT")
        return done("other", out["name"] or "libusb error")

    if num is None:
        frames = ctx.get("frames")
        if frames == 0 and contention:
            return done("bandwidth_probable", "zero frames with no error while another camera in the same domain "
                                              "streams and the predicted load is over (silent refusal)", True)
        if frames == 0:
            return done("other", "zero frames and no error code; retry once (a refused start can be followed by "
                                 "one zero-frame start)", True)
        return done("other", f"unrecognised failure {code!r}")

    if osn == "windows":
        v = num
        if v == 0x800718CF:
            return done("bandwidth_certain", "Media Foundation reported HRESULT_FROM_WIN32(6351): 'A camera "
                                             "interface doesn't have the desired bandwidth for data transfer'", True)
        if v == 0x80000700:
            return done("bandwidth_certain", "USBD_STATUS_NO_BANDWIDTH", True)
        if v in (0x80070005, 5, 0x800705AA):
            what = {0x80070005: "access denied (E_ACCESSDENIED)",
                    5: "OSError(5) (POSIX EIO, FFmpeg 'I/O error') from the FFmpeg/PyAV DirectShow open",
                    0x800705AA: "insufficient system resources (ERROR_NO_SYSTEM_RESOURCES, DirectShow Run)"}[v]
            if contention:
                return done("bandwidth_probable", f"{what} while another camera in the same bandwidth domain "
                                                  "streams and the predicted load is over", True)
            if ctx.get("in_use_by_other"):
                return done("in_use", f"{what}; another application holds the camera")
            if ctx.get("privacy_denied"):
                return done("permission", f"{what}; camera access is blocked by privacy settings")
            return done("other", f"{what} with no bandwidth contention in this domain: camera in use by another "
                                 "app, privacy setting, or a device fault (ambiguous)", True)
        if v in (0xC00D3704, 0xC00D3EA3, 0x800700AA, 0x80070020):
            extra = " (Chromium treats MF_E_HW_MFT_FAILED_START_STREAMING as 'in use by another application')" \
                if v == 0xC00D3704 else ""
            return done("in_use", f"{hresult_name(v)}{extra}")
        if v in (0x8007001F, 0xC00D3EA2, 0xC00D7167, 0x8007048F, 0x80070490, 0x800701B1, 0x800701E3, 0x8007045D,
                 0x80070651, 0x800710DF, 0x80070015, 0xA00F4271, 0xC00DABE0, 0x80070002):
            hint = {0x8007001F: "device attached but not functioning (the Kiyo Pro control-transfer fault); needs "
                                "a replug, never a programmatic restart",
                    0xC00D7167: "devnode needs a restart (DN_NEED_RESTART); MF is locked out until a replug, "
                                "DirectShow may still work",
                    0xC00D3EA2: "device invalidated (unplug or re-enumeration)"}.get(v, "")
            return done("device_error", f"{hresult_name(v)}" + (f": {hint}" if hint else ""))
        if v == 0x800704EC:
            return done("permission", "access disabled by policy")
        if v in (0x80070079, 0x800705B4):
            return done("timeout", f"{hresult_name(v)}")
        if v == 0xC00D36B2:
            return done("other", "MF_E_INVALIDREQUEST: transient; Chromium retries up to 200 x 50 ms", True)
        if v == 0xC00D3E85:
            return done("other", "MF_E_SHUTDOWN: a shut-down source was reused (cached IMFActivate without "
                                 "ShutdownObject): harness bug, not a camera failure")
        if v in (0xC00D36B4, 0xC00D36B9, 0x80070057):
            return done("other", f"{hresult_name(v)}: mode not accepted")
        return done("other", f"{hresult_name(v) or out['code_hex'] or v}")

    if osn == "linux":
        nm = LINUX_ERRNO.get(num, name)
        if nm == "ENOSPC":
            return done("bandwidth_certain", "ENOSPC at VIDIOC_STREAMON: the xHCI/EHCI refused the isochronous "
                                             "bandwidth reservation ('Not enough bandwidth for new device state')",
                        True)
        if nm == "ENOMEM":
            pci = (ctx.get("controller_pci_id") or "").lower()
            if pci == "8086:1e31" and contention:
                return done("bandwidth_probable", "ENOMEM on Intel Panther Point (software bandwidth table returns "
                                                  "-ENOMEM) with contention in the domain", True)
            return done("other", "ENOMEM: xHCI resource error (endpoint contexts exhausted: too many devices on the "
                                 "controller), not bandwidth")
        if nm == "EBUSY":
            return done("in_use", "EBUSY: another process (PipeWire, a browser) streams from the device")
        if nm == "EIO":
            if stage in ("streamon", "stream_start", "start", "first_frame"):
                return done("other", "EIO at STREAMON: uvcvideo 'No fast enough alt setting' (bad PROBE values or "
                                     "a mode no alt can carry), not contention")
            return done("device_error", "EIO: USB transfer failed")
        if nm in ("EPIPE", "EPROTO", "EREMOTEIO", "ETIME", "EOVERFLOW"):
            return done("device_error", f"{nm}: USB control/stream transfer failed (stall or protocol error)")
        if nm == "ETIMEDOUT":
            return done("device_error", "ETIMEDOUT: USB control transfer timed out (device not answering; the Kiyo "
                                        "Pro LPM symptom)")
        if nm in ("EACCES", "EPERM"):
            if stage == "control":
                return done("other", f"{nm} on a control: usually the auto mode is still on (set manual first)")
            return done("permission", f"{nm}: no permission for the video node (session ACL / video group)")
        if nm in ("ENODEV", "ENXIO", "ENOENT", "ESHUTDOWN"):
            return done("device_error", f"{nm}: device gone or not ready")
        if nm == "EINVAL":
            return done("other", "EINVAL: format or control value not accepted")
        return done("other", f"{nm}")

    if osn == "macos":
        if num in IORETURN_NAMES:
            nm = IORETURN_NAMES[num]
            if nm == "kIOReturnNoBandwidth":
                return done("bandwidth_certain", "kIOReturnNoBandwidth (the likely low-level code; how AVFoundation "
                                                 "surfaces it is unverified)", True)
            if nm == "kIOReturnNoResources" and contention:
                return done("bandwidth_probable", "kIOReturnNoResources with contention in the domain", True)
            if nm in ("kIOReturnExclusiveAccess", "kIOReturnBusy"):
                return done("in_use", nm)
            if nm in ("kIOReturnNotPermitted", "kIOReturnNotPrivileged"):
                return done("permission", nm)
            if nm == "kIOReturnTimeout":
                return done("timeout", nm)
            if nm in ("kIOReturnNoDevice", "kIOReturnNotResponding", "kIOReturnNotAttached", "kIOReturnDeviceError",
                      "kIOReturnIOError", "kIOReturnAborted", "kIOReturnNotReady"):
                return done("device_error", nm)
            return done("other", nm)
        if num in AVERROR_NAMES or name in AVERROR_NAMES.values():
            nm = AVERROR_NAMES.get(num, name)
            if nm in ("AVErrorDeviceInUseByAnotherApplication", "AVErrorDeviceAlreadyUsedByAnotherSession",
                      "AVErrorDeviceLockedForConfigurationByAnotherProcess"):
                return done("in_use", nm)
            if nm == "AVErrorApplicationIsNotAuthorizedToUseDevice":
                return done("permission", nm + " (TCC camera permission belongs to the launching app)")
            if nm in ("AVErrorDeviceNotConnected", "AVErrorDeviceWasDisconnected"):
                return done("device_error", nm)
            if nm == "AVErrorNoDataCaptured" and contention:
                return done("bandwidth_probable", nm + " with contention in the domain", True)
            return done("other", nm)
        nm = MACOS_ERRNO.get(num, name)
        if nm == "EBUSY":
            return done("in_use", nm)
        if nm in ("EACCES", "EPERM"):
            return done("permission", nm)
        return done("other", f"{nm}")

    return done("other", f"unknown OS {os!r}; code {code!r}")


# ----------------------------------------------------------------------------------------------- socket evidence
#: Name fragments of devices that live on INTERNAL USB headers (PSU monitoring, AIO pumps, RGB/fan controllers,
#: on-board radios). A phantom of such a device at a port says "internal header", not "real socket". A name
#: heuristic is brittle (multi_topo.md verifier): it only moves a port to the END of the list, never removes it.
HEADER_DEVICE_PATTERNS = (
    r"power\s*supply", r"\bpsu\b", r"\b(hx|rm|ax)\d{3,4}i\b", r"corsair\s*link", r"commander", r"lighting\s*node",
    r"\bicue\b", r"\baura\b", r"\brgb\b", r"\bargb\b", r"led\s*controller", r"\baio\b", r"kraken", r"hydro",
    r"\bpump\b", r"fan\s*(hub|controller)", r"smart\s*device", r"\bnzxt\b", r"capellix", r"bluetooth",
    r"wireless\s*radio", r"\bcooler\b", r"platinum", r"\bh1[05]0i\b",
)


def is_header_device_name(name: Any) -> bool:
    """True if a device name looks like an internal-header device (see HEADER_DEVICE_PATTERNS)."""
    s = str(name or "").lower()
    return bool(s) and any(re.search(p, s) for p in HEADER_DEVICE_PATTERNS)


def socket_evidence(port: dict) -> dict:
    """Evidence that an empty port is a real, user-reachable socket.

    Returns {"level": "strong"|"weak"|"header"|None, "strong": [...], "weak": [...], "header": [...]}:
      strong  phantom history of a non-header device, _PLD USB-C receptacle geometry, _PLD user_visible on a
              ROOT port;
      weak    only _UPC-derived facts (connectable, the Type-C connector flag of the hub connector IOCTL) or a
              _PLD user_visible on a HUB port (suspicious: hub ports have no ACPI socket of their own);
      header  a phantom of an internal-header device (PSU, AIO, RGB/fan controller, Bluetooth): ranked last.
    "header" wins over "strong" (a port that once held a PSU is a header whatever else it says).
    Works on any collector's snapshot: reads label_parts (user_visible, type_c, pld) and phantom_history."""
    lp = port.get("label_parts") or {}
    strong, weak, header = [], [], []
    for h in port.get("phantom_history") or []:
        nm = h.get("name") or h.get("instance_id")
        hdr = h.get("header_device")
        if hdr is None:
            hdr = is_header_device_name(nm)
        (header if hdr else strong).append(f"phantom history: {nm}")
    pld = lp.get("pld") or {}
    if pld.get("width_mm") and pld.get("height_mm") and pld.get("shape") == 1:
        strong.append(f"_PLD receptacle {pld['width_mm']}x{pld['height_mm']} mm oval (USB-C geometry)")
    if lp.get("user_visible"):
        (strong if port.get("is_root_port") else weak).append(
            "_PLD user_visible" + ("" if port.get("is_root_port") else " on a hub port"))
    if lp.get("type_c") or port.get("connector") == "C":
        weak.append("Type-C connector flag (_UPC)")
    if port.get("connectable") == "user":
        weak.append("_UPC connectable")
    level = "header" if header else ("strong" if strong else ("weak" if weak else None))
    return {"level": level, "strong": strong, "weak": weak, "header": header}


def _evidence_rank(port: dict) -> int:
    """0 strong socket evidence, 1 none / _UPC only, 2 internal-header evidence (sorts last)."""
    return {"strong": 0, "header": 2}.get(socket_evidence(port)["level"], 1)


# ----------------------------------------------------------------------------------------------- label tiers
#: Label quality tiers, best first (bandwidth_domain_model.md section 6 fallback chain). Only the last two are
#: "raw" (shared rule of W-TOPO and W-MULTI / rate_bw: raw = ACPI names / location paths only).
LABEL_TIERS = ("panel_position", "friendly_name", "controller_port_number", "acpi_or_location_path",
               "location_unknown")
RAW_LABEL_TIERS = ("acpi_or_location_path", "location_unknown")


def label_tier(label: Any) -> str:
    """Tier of a port label made by port_label(): 'panel_position' (connector + _PLD position), 'friendly_name'
    (an OS port name), 'controller_port_number' ('port N (HSnn, ...)' or 'port N of the hub ...'),
    'acpi_or_location_path' (bare ACPI name or PCIROOT/USBROOT location path), 'location_unknown' (nothing usable)."""
    s = str(label or "").strip()
    if not s or s.lower() in ("an empty usb port", "usb port"):
        return "location_unknown"
    up = s.upper()
    if "PCIROOT" in up or "USBROOT" in up or "ACPI(" in up or "#USB(" in up or \
            re.fullmatch(r"[HS]S\d{1,2}(\s*/.*)?", up) or re.fullmatch(r"[A-Z0-9_.\\]+(\s*/\s*[A-Z0-9_.#()\\]+)+", up):
        return "acpi_or_location_path"
    if re.match(r"^port \d+", s):
        return "controller_port_number"
    # port_label's _PLD form: '<connector>, <position>[ (colour)][ [ACPI]]'
    if re.match(r"^(USB-C|USB-A|USB 3 Type-A|USB 3, not USB-C|USB 2\.0-only|USB port), ", s) and \
            re.search(r"\b(top|bottom|middle|left|right|centre|center|upper|lower|front|rear|back|side|from)\b",
                      s.lower()):
        return "panel_position"
    return "friendly_name"


def label_is_raw(label: Any) -> bool:
    return label_tier(label) in RAW_LABEL_TIERS


def labels_raw(labels: Iterable[Any]) -> bool | None:
    """True if every label is raw (ACPI / location path / generic); None for no labels."""
    labels = list(labels)
    if not labels:
        return None
    return all(label_is_raw(lb) for lb in labels)


# ----------------------------------------------------------------------------------------------- suggestions
def port_label(snapshot: dict, port_id: Any) -> str:
    """Best available human label for a port, with the fallbacks of bandwidth_domain_model.md section 6:
    _PLD panel/position/colour + connector -> 'port N (ACPI, connector kind, user-accessible)' ->
    'ACPI name / location path' -> 'port N'. Hub ports say which hub they are on."""
    idx = _Index(snapshot)
    return _port_label_idx(idx, idx.ports[port_id])


def _connector_text(idx: _Index, port: dict) -> str | None:
    lp = port.get("label_parts") or {}
    conn = port.get("connector") or "unknown"
    if conn == "C" or lp.get("type_c"):
        return "USB-C"
    usb3 = lp.get("usb3_capable")
    if usb3 is None:
        usb3 = port.get("companion_id") is not None
    if conn == "A":
        return "USB 3 Type-A" if usb3 else "USB-A"
    if usb3:
        return "USB 3, not USB-C"
    if port.get("half") == "usb2":
        return "USB 2.0-only"
    return None


def _port_label_idx(idx: _Index, port: dict) -> str:
    lp = port.get("label_parts") or {}
    conn = _connector_text(idx, port)
    n = port.get("port_number")
    if not port.get("is_root_port"):
        hub = idx.devices.get(port.get("hub_device_id")) or {}
        hub_name = hub.get("name") or "USB hub"
        rp = idx.root_port_of_port(port)
        rp_txt = _port_number_text(rp)
        where = f" (on {rp_txt})" if rp_txt else ""
        return f"port {n} of the hub '{hub_name}' {_vidpid(hub.get('vid'), hub.get('pid')).upper()}{where}"
    if lp.get("position_text") or lp.get("vpos") or lp.get("hpos"):  # panel alone goes in the group label
        bits = [conn or "USB port"]
        pos = lp.get("position_text") or ", ".join(x for x in (lp.get("vpos"), lp.get("hpos")) if x)
        if pos:
            bits.append(pos)
        txt = ", ".join(bits)
        if lp.get("color"):
            txt += f" ({lp['color']})"
        if lp.get("acpi_name"):
            txt += f" [{lp['acpi_name']}]"
        return txt
    if lp.get("friendly"):
        return str(lp["friendly"])
    if n is not None:
        # "user-accessible" only with evidence beyond _UPC (which over-reports: header ports say connectable too)
        ev = socket_evidence(port)
        accessible = port.get("connectable") == "user" and ev["level"] == "strong"
        extra = [x for x in (lp.get("acpi_name"), conn, "user-accessible" if accessible else None) if x]
        return f"port {n}" + (f" ({', '.join(extra)})" if extra else "")
    if lp.get("acpi_name") or lp.get("location_path") or port.get("path"):
        return " / ".join(str(x) for x in (lp.get("acpi_name"), lp.get("location_path") or port.get("path")) if x)
    return "an empty USB port"


def _group_label(idx: _Index, ctrl_id: Any, panel: str | None) -> str:
    c = idx.controllers.get(ctrl_id)
    if c is None:
        return "a different USB port directly on the computer"
    name = _controller_display(idx, ctrl_id)
    if panel:
        return f"{str(panel).capitalize()} panel, {name}"
    return name


def _hs_domain_for_port(idx: _Index, port: dict, pols: dict) -> tuple[str, Any, Any]:
    ctrl, rp = idx.port_hs_root(port)
    pol = pols.get(ctrl) or policy_for(idx.controllers.get(ctrl))
    chain: list = []
    hub_id = port.get("hub_device_id")
    if hub_id is not None and hub_id in idx.devices:
        chain = [hub_id] + idx.hub_chain(idx.devices[hub_id])
    if pol["hs_domain"] == "controller" or idx.chain_has_rmh(chain):
        return f"hs|{ctrl}|*", ctrl, None
    return f"hs|{ctrl}|{rp}", ctrl, rp


def suggest_ports(snapshot: dict, conflict: dict, moving_camera_key: str,
                  mode_alt_cache: ModeAltCache | None = None, policies: Any = None,
                  accounting: str = "calibrated", prediction: dict | None = None,
                  max_ports_per_group: int | None = None) -> list[dict]:
    """Free ports a camera could move to, grouped for the message (bandwidth_domain_model.md 5.1 + verifier V4).

    Returns [{"group_label", "controller_id", "panel", "best_rank",
              "ports": [{"port_id", "label", "rank", "shares_with": [names], "domain_key", "domain_load_us",
                         "load_after_us", "pct_budget_after", "on_hub", "tight"}]}], best group first.
    Empty list when nothing fits anywhere.

    Candidates: empty USB 2.0-capable ports (root ports or ports on any hub, internal hubs included) that are
    user-connectable or unknown, whose USB 3 companion is not occupied, outside the conflicting domain (so never
    the same hub/dock and never the SuperSpeed twin of the conflicting connector), where the domain's load plus the
    moving camera's cost stays within the budget. ``prediction`` (from predict) adds the cost of other cameras the
    session will open in candidate domains.
    Ranks: 1 empty domain on a controller known to be per-root-port; 2 empty domain on a different controller;
    3 empty domain on the same uncertain controller; 4 a domain that already carries other devices (shares_with).
    Within a rank: ports with internal-header evidence (socket_evidence level "header") last; then strong socket
    evidence before none / _UPC-only; root port before hub port, USB 3-capable before USB 2.0-only (USB 2.0-only
    root ports are often headers), the camera's current panel, USB-A, then unknown, then USB-C (camera plugs are
    USB-A), then port number.
    """
    idx = _Index(snapshot)
    pols = _policies_lookup(idx, policies)
    recs = _domain_records(idx, pols, accounting)
    conflict_key = conflict.get("domain_key")
    conflict_ctrl = conflict.get("controller_id")
    cpol = pols.get(conflict_ctrl) or policy_for(idx.controllers.get(conflict_ctrl))
    conflict_weak = bool(cpol.get("uncertain")) or cpol.get("hs_domain") == "controller"
    # moving camera cost
    cost = None
    for ci in conflict.get("camera_info") or []:
        if ci.get("key") == moving_camera_key and ci.get("cost_us"):
            cost = float(ci["cost_us"])
    cam = idx.cameras.get(moving_camera_key)
    cam_dev = idx.devices.get(cam.get("device_id")) if cam else None
    if cost is None and cam:
        a = _largest_alt(cam, "usb2_5113", "HS")
        if a:
            cost = _alt_cost(a["max_packet"], a.get("mult") or 1, "usb2_5113", "HS")
    if cost is None:
        cost = cost_us(1024, 3)  # largest legal HS isochronous alt
    cam_panel = None
    if cam_dev is not None:
        _, rp_id = idx.usb2_root(cam_dev)
        rp = idx.ports.get(rp_id)
        cam_panel = (rp.get("label_parts") or {}).get("panel") if rp else None
    # Domains the session will also open cameras in: use the predicted load (requested cameras' costs replace
    # their currently open pipes) instead of the observed load. The moving camera lives in the conflicting
    # domain, which is never a candidate, so it is not counted twice.
    planned: dict[str, float] = {}
    if prediction:
        for d in prediction.get("domains", []):
            planned[d["key"]] = float(d["predicted_load_us"])
    cands = []
    for port in idx.ports.values():
        if port.get("occupant_device_id") is not None:
            continue
        if port.get("half") not in ("usb2", "unknown", None):
            continue
        if port.get("connectable") in ("internal", "not_used"):
            continue
        comp = idx.ports.get(port.get("companion_id"))
        if comp is not None and comp.get("occupant_device_id") is not None:
            continue  # the physical connector is used by a SuperSpeed device
        hub = idx.devices.get(port.get("hub_device_id")) if port.get("hub_device_id") is not None else None
        if hub is not None and _speed(hub) in ("SS", "SS+"):
            continue
        key, ctrl, rp = _hs_domain_for_port(idx, port, pols)
        if key == conflict_key:
            continue
        rec = recs.get(key)
        pol = pols.get(ctrl) or policy_for(idx.controllers.get(ctrl))
        load = planned[key] if key in planned else (rec["load_us"] if rec else 0.0)
        budget = rec["budget_us"] if rec else float(pol.get("budget_us") or HS_BUDGET_US)
        after = load + cost
        v = verdict_for(after, budget, pol.get("bracket"))
        if v == "over":
            continue
        members = [idx.devices[m] for m in (rec["members"] if rec else []) if m in idx.devices]
        shares = [_dev_name(d, idx.cam_by_dev.get(d["id"])) for d in members if not d.get("is_hub")]
        empty_domain = not shares
        known = (not pol.get("uncertain")) and pol.get("hs_domain") == "root_port"
        if empty_domain and known and (ctrl != conflict_ctrl or not conflict_weak):
            rank = 1
        elif empty_domain and ctrl != conflict_ctrl:
            rank = 2
        elif empty_domain:
            rank = 3
        else:
            rank = 4
        lp = port.get("label_parts") or {}
        rp_port = idx.ports.get(rp)
        panel = lp.get("panel") or ((rp_port.get("label_parts") or {}).get("panel") if rp_port else None)
        conn = port.get("connector") or "unknown"
        usb3 = lp.get("usb3_capable")
        if usb3 is None:
            usb3 = comp is not None
        ev_rank = _evidence_rank(port)
        sort_key = (rank, ev_rank, 0 if port.get("is_root_port") else 1,
                    0 if usb3 or lp.get("type_c") or conn == "C" else 1,
                    0 if (cam_panel and panel == cam_panel) else 1,
                    {"A": 0, "C": 2}.get(conn, 1), port.get("port_number") or 0, str(port["id"]))
        cands.append({"sort": sort_key, "group": (ctrl, panel), "port_id": port["id"],
                      "label": _port_label_idx(idx, port), "rank": rank, "shares_with": shares,
                      "domain_key": key, "domain_load_us": round(load, 3), "load_after_us": round(after, 3),
                      "pct_budget_after": round(100 * after / budget, 1), "on_hub": not port.get("is_root_port"),
                      "tight": v == "marginal", "evidence": socket_evidence(port)["level"]})
    cands.sort(key=lambda c: c["sort"])
    groups: dict[tuple, dict] = {}
    for c in cands:
        g = groups.get(c["group"])
        if g is None:
            ctrl, panel = c["group"]
            g = groups[c["group"]] = {"group_label": _group_label(idx, ctrl, panel), "controller_id": ctrl,
                                      "panel": panel, "best_rank": c["rank"], "_best": c["sort"], "ports": []}
        if max_ports_per_group is None or len(g["ports"]) < max_ports_per_group:
            g["ports"].append({k: v for k, v in c.items() if k not in ("sort", "group")})
    out = sorted(groups.values(), key=lambda g: g["_best"])
    for g in out:
        g.pop("_best", None)
    return out


def stay_here_alternatives(snapshot: dict, conflict: dict, mode_alt_cache: ModeAltCache | None,
                           policies: Any = None) -> list[dict]:
    """For each camera of the conflict, the best cached mode that makes the domain fit with the other cameras
    unchanged. Preference (motion capture needs the frame rate): same format, then a frame rate at least the
    requested one, then the largest w*h, then the higher rate; a lower rate is offered only when no mode at the
    requested rate fits (multi_topo.md B13: w*h*fps preferred MJPEG 1080p@5 over 640x480@30).
    [{camera_key, name, mode, mode_text, alt, cost_us, pct_budget, domain_pct_after, verified, keeps_fps}] best
    first; empty when no cached mode fits (descriptor ladders are not used: alt per mode is only known after
    opening it once)."""
    if mode_alt_cache is None:
        return []
    idx = _Index(snapshot)
    pols = _policies_lookup(idx, policies)
    total = float(conflict.get("predicted_load_us") or 0.0)
    budget = float(conflict.get("budget_us") or HS_BUDGET_US)
    pol = pols.get(conflict.get("controller_id")) or policy_for(idx.controllers.get(conflict.get("controller_id")))
    out = []
    for ci in conflict.get("camera_info") or []:
        cam = idx.cameras.get(ci.get("key"))
        dev = idx.devices.get(cam.get("device_id")) if cam else None
        if dev is None or ci.get("cost_us") is None:
            continue
        cur = parse_mode(ci.get("mode")) or {}
        best = None
        for e in mode_alt_cache.modes_for(dev.get("vid"), dev.get("pid"), dev.get("bcd_device")):
            mp, mult = e.get("max_packet"), e.get("mult")
            if not mp and _alt_entry(cam, e.get("alt")):
                a = _alt_entry(cam, e["alt"])
                mp, mult = a["max_packet"], a.get("mult") or 1
            if not mp or not e.get("mode"):
                continue
            c = _alt_cost(mp, mult or 1, pol.get("budget_kind", "usb2_5113"), "HS")
            after = total - float(ci["cost_us"]) + c
            if verdict_for(after, budget, pol.get("bracket")) != "fits":
                continue
            m = e["mode"]
            score = _stay_score(m, cur)
            if best is None or score > best[0]:
                best = (score, e, c, after)
        if best:
            score, e, c, after = best
            out.append({"camera_key": ci["key"], "name": ci.get("name"), "mode": e["mode"],
                        "mode_text": mode_text(e["mode"]), "alt": e.get("alt"), "cost_us": round(c, 3),
                        "pct_budget": round(100 * c / budget, 1), "domain_pct_after": round(100 * after / budget, 1),
                        "verified": not e.get("other_firmware"), "keeps_fps": bool(score[1]),
                        "_score": score})
    out.sort(key=lambda a: a["_score"], reverse=True)
    for a in out:
        a.pop("_score", None)
    return out


def _stay_score(m: dict, cur: dict) -> tuple:
    """Same format first, then a rate at least the requested one, then the rate closest to it from below (so a
    720p60 conflict falls back to a 30 fps mode, never to 1080p@5), then the largest size, then the higher rate."""
    want = cur.get("fps") or 0
    fps = m.get("fps") or 0
    return (m.get("format") == cur.get("format"), fps + 1e-6 >= want, min(fps, want), m["width"] * m["height"], fps)


# ----------------------------------------------------------------------------------------------- message
def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _code_text(failure: dict) -> str:
    cls = failure.get("class")
    code = failure.get("code")
    hx = failure.get("code_hex")
    name = failure.get("name")
    if cls == "bandwidth_certain":
        if hx == "0x800718CF" or code == 0x800718CF:
            return "0x800718CF: not enough USB bandwidth"
        return f"{name or hx or code}"
    if code == 5 or name == "OSError(5)":
        # POSIX EIO as FFmpeg prints it ("I/O error"), NOT Win32 ERROR_ACCESS_DENIED (also 5)
        return "a DirectShow start error, FFmpeg: I/O error"
    if code == 0x80070005 or (name and "ACCESSDENIED" in name):
        return "E_ACCESSDENIED: access denied"
    if cls == "timeout" or name == "timeout":
        return "timed out"
    return f"{name or hx or code}"


def _when_text(failure: dict, both: str, n_names: int) -> str:
    """'When I tried to open them both at the same time' or, for staggered starts, 'When I opened them both one
    after another, 2.5 s apart'."""
    if n_names < 2:
        return "When I tried to open it"
    st = failure.get("stagger_s")
    if isinstance(st, (int, float)) and st > 0:
        return f"When I opened {both} one after another, {_fps_text(float(st))} s apart"
    return f"When I tried to open {both} at the same time"


def _pct(x: Any) -> str:
    try:
        return f"{round(float(x)):d}"
    except (TypeError, ValueError):
        return "?"


def build_message(conflict: dict, failure: dict | None = None, suggestions: list[dict] | None = None,
                  alternatives: list[dict] | None = None, max_ports_per_group: int = 8) -> str:
    """User message following the template of docs/xplat_capture_plan.md section 5:

        {A} and {B} share USB bandwidth: both connect through {shared_hop}.
        When I tried to open them both at the same time, {loser} failed with a USB bandwidth error ({code}).
        At these settings they need about {pct_total}% of what that USB 2.0 link allows ({A} {mode_A}: {pct_A}%,
        {B} {mode_B}: {pct_B}%).
        Suggest moving one of those cameras to any of the following controller ports:
          {controller_or_panel_group}: {port_label}, {port_label}, ...
        Or, to keep both where they are, lower {B} to {alt_mode_B} (about {pct_alt_B}%).

    conflict: an entry of predict()['conflicts']. failure: classify_failure() output plus "loser" (camera key or
    name) and optionally "stagger_s" (> 0: the cameras were opened that many seconds apart, so line 2 does not say
    "at the same time") and "loser_position" ("first"/"last" among the conflict's cameras); None = a prediction
    made before opening (line 2 then says so). Only bandwidth_* classes are called a USB bandwidth error; a
    timeout or other class says "did not start (...); this may be a USB bandwidth problem".
    suggestions: suggest_ports() output.
    alternatives: stay_here_alternatives() output. Percentages are of the 80% periodic budget (100 us), rounded.
    """
    info = conflict.get("camera_info") or [{"key": k, "name": k} for k in conflict.get("cameras", [])]
    names = [ci.get("name") or ci.get("key") for ci in info]
    key_to_name = {ci.get("key"): (ci.get("name") or ci.get("key")) for ci in info}
    hop = conflict.get("shared_hop") or "the same USB connection to the computer"
    lines = []
    if len(names) >= 3:
        lines.append(f"{_join_names(names)} share USB bandwidth: all connect through {hop}.")
        both, keep = "them all", "them all"
    elif len(names) == 2:
        lines.append(f"{names[0]} and {names[1]} share USB bandwidth: both connect through {hop}.")
        both, keep = "them both", "both"
    else:
        others = [d.get("name") for d in conflict.get("other_devices") or [] if d.get("name")]
        with_txt = _join_names(others) if others else "other devices"
        lines.append(f"{names[0] if names else 'The camera'} and {with_txt} share USB bandwidth: "
                     f"they connect through {hop}.")
        both, keep = "it", "it"
    if failure:
        loser = failure.get("loser")
        loser_name = key_to_name.get(loser, loser) or "one of them"
        pos = failure.get("loser_position")
        if pos in ("first", "last") and len(names) >= 2 and (failure.get("stagger_s") or 0) > 0:
            loser_name = f"{loser_name} (opened {pos})"
        when = _when_text(failure, both, len(names))
        cls = failure.get("class")
        if cls == "bandwidth_certain":
            lines.append(f"{when}, {loser_name} failed with a USB bandwidth error ({_code_text(failure)}).")
        elif cls == "bandwidth_probable":
            lines.append(f"{when}, {loser_name} failed with an error that is probably a USB bandwidth error "
                         f"({_code_text(failure)}).")
        elif cls == "timeout":
            lines.append(f"{when}, {loser_name} did not start (timed out); this may be a USB bandwidth problem.")
        else:
            lines.append(f"{when}, {loser_name} did not start ({_code_text(failure)}); this may be a USB bandwidth "
                         "problem.")
    else:
        if len(names) >= 2:
            lines.append(f"If I open {both} at the same time, one of them will probably fail with a USB bandwidth "
                         f"error (predicted from the USB layout, not yet tried).")
        else:
            lines.append("If I open it now, it will probably fail with a USB bandwidth error (predicted from the "
                         "USB layout, not yet tried).")
    parts = []
    for ci in info:
        parts.append(f"{ci.get('name') or ci.get('key')} {ci.get('mode_text') or mode_text(ci.get('mode'))}: "
                     f"{_pct(ci.get('pct_budget'))}%")
    if (conflict.get("other_pct_budget") or 0) >= 0.5:
        parts.append(f"other devices on the link: {_pct(conflict['other_pct_budget'])}%")
    they = "they need" if len(names) != 1 else "it and the other devices need"
    lines.append(f"At these settings {they} about {_pct(conflict.get('pct_total'))}% of what that USB 2.0 link "
                 f"allows ({', '.join(parts)}).")
    if conflict.get("is_dock"):
        lines.append("All USB 2.0 ports on this dock share one connection.")
    if conflict.get("policy_source") == "learned" and conflict.get("policy_hs_domain") == "controller":
        lines.append("On this controller all ports appear to share bandwidth.")
    groups = [g for g in (suggestions or []) if g.get("ports")]
    if groups:
        lines.append(MESSAGE_SUGGEST_LINE if len(names) >= 2 else
                     MESSAGE_SUGGEST_LINE.replace("one of those cameras", "the camera"))
        for g in groups:
            labels = [p["label"] + (f" (shares with {_join_names(p['shares_with'])})" if p.get("shares_with") else "")
                      for p in g["ports"]]
            more = len(labels) - max_ports_per_group
            shown = labels[:max_ports_per_group]
            if more > 0:
                shown.append(f"and {more} more")
            lines.append(f"  {g['group_label']}: {', '.join(shown)}")
        if conflict.get("uncertain"):
            others = conflict.get("other_controllers") or []
            lines.append("If the error persists after moving, try a port on a different controller"
                         + (f" ({_join_names(others)})." if others else "."))
    else:
        lines.append("No free port with enough USB bandwidth was found on this computer. To use these settings, add "
                     "a USB controller card with one controller per port (common single-chip 4-port cards do not "
                     "help).")
    alts = alternatives or []
    if alts:
        first = alts[0]
        tail = ""
        if len(alts) > 1:
            tail = "".join(f", or {a.get('name') or a.get('camera_key')} to {a['mode_text']} "
                           f"(about {_pct(a.get('pct_budget'))}%)" for a in alts[1:])
        lines.append(f"Or, to keep {keep} where they are, lower {first.get('name') or first.get('camera_key')} to "
                     f"{first['mode_text']} (about {_pct(first.get('pct_budget'))}%){tail}."
                     if len(names) >= 2 else
                     f"Or, to keep it where it is, lower it to {first['mode_text']} "
                     f"(about {_pct(first.get('pct_budget'))}%).")
    return "\n".join(lines)


def explain(snapshot: dict, requests: list[dict], mode_alt_cache: ModeAltCache | None = None,
            failure: dict | None = None, policies: Any = None, accounting: str = "calibrated") -> dict:
    """Convenience: predict + suggestions + alternatives + message for every conflict.
    Returns {"prediction": ..., "messages": [{"domain_key", "moving_camera_key", "suggestions", "alternatives",
    "message"}]}. The camera to move is the failure's loser if given, else the last camera of the conflict."""
    pred = predict(snapshot, requests, mode_alt_cache, policies, accounting)
    msgs = []
    for c in pred["conflicts"]:
        loser = (failure or {}).get("loser") if failure else None
        moving = loser if loser in c["cameras"] else c["cameras"][-1]
        sugg = suggest_ports(snapshot, c, moving, mode_alt_cache, policies, accounting, prediction=pred)
        alts = stay_here_alternatives(snapshot, c, mode_alt_cache, policies)
        f = failure if (failure and failure.get("loser") in c["cameras"]) else None
        msgs.append({"domain_key": c["domain_key"], "moving_camera_key": moving, "suggestions": sugg,
                     "alternatives": alts, "message": build_message(c, f, sugg, alts)})
    return {"prediction": pred, "messages": msgs}
