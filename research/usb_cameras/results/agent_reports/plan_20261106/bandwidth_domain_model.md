# Bandwidth domain model: which USB cameras share bandwidth, and which ports to suggest

Topic: `bandwidth_domain_model`. Plan workflow of 2026-11-06. Author: research subagent. No camera was opened or streamed for this report.

Labels: **measured** = a repo result file, or a read-only command run on Gerald today (command and output given). **doc** = a spec or source code (URL and line). **web** = forum or secondary source. **inferred** = my reasoning from the above.

Companion files:
- Model comparison script: [`bandwidth/domain_model_compare.py`](../../../bandwidth/domain_model_compare.py). Its output is [`bandwidth_domain_model_compare.json`](bandwidth_domain_model_compare.json). Offline, stdlib only, runs in under 1 s.
- Linux sources were read at torvalds/linux master commit `f66469d9905b` (2026-11-06T02:00Z). The line numbers below refer to that commit.

---

## 1. Answer in brief

1. **For a high-speed (USB 2.0, 480 Mb/s) camera, the unit that runs out is the USB 2.0 link from an xHCI root port.** Everything plugged in below that root port, through any number of hubs, shares one 480 Mb/s bus. At most 80% of each 125 µs microframe can be reserved for periodic (isochronous and interrupt) transfers. A hub repeats high-speed traffic; it does not add bandwidth. Within that tree, the root-port link is always the bottleneck: every link below it carries a subset of its traffic at the same 480 Mb/s.
2. **On the Intel xHCI we measured, each root port is a separate domain.** Two max-alt cameras on different root ports of the same controller (8086:7A60) both streamed. Together they used 98.4% of a microframe, which would have been refused had the controller pooled all ports. Two cameras behind one root port were refused once the combined load passed about 80% (measured; section 3).
3. **That per-root-port model is what the xHCI spec and Linux describe.** The xHCI spec defines each root port as a primary bandwidth domain and each TT as a secondary domain, and its Get Port Bandwidth command reports available bandwidth per root port (doc). It is not universal:
   - EHCI-era controllers have one high-speed bus for the whole controller.
   - Integrated hubs merge ports: the Raspberry Pi 4 VL805 and most docks.
   - Behaviour of AMD, ASMedia, Renesas, VIA and Fresco controllers is **not established**. I found no measurement that separates per-port from per-controller behaviour on them.
4. **USB 2.0 and USB 3 traffic do not compete.** A USB 3 hub is two hubs in one box. A USB 2.0 camera behind it uses the hub's USB 2.0 half, which can even sit on a *different controller* from the USB 3 half. Gerald has this right now: the Genesys GL3523 hub's SuperSpeed half is on the Thunderbolt 4 xHCI, and its USB 2.0 half is on the chipset xHCI (measured).
5. **A portable library should therefore:**
   - key each high-speed camera's domain as `(controller, USB 2.0 root port)`;
   - use the USB 2.0 §5.11.3 budget at 80% of a microframe (26/26 on Gerald);
   - count every periodic pipe in the domain, not just cameras;
   - keep a per-controller policy that can widen the domain to the whole controller when failures show it is pooled;
   - learn each camera mode's real alt the first time it is opened alone.

   On a refusal it names the shared hop and lists empty user-visible connectors whose USB 2.0 root port has room, grouped by controller and panel. It also offers a lower mode that fits where the camera already is.

---

## 2. Standards and implementations: where the domain boundary is

### 2.1 USB 2.0 periodic budget (doc)

- USB 2.0 §5.6.4: high-speed periodic transfers may reserve at most 80% of a 125 µs microframe, i.e. 100 µs.
- §5.11.3 gives the worst-case transaction time. For a high-speed isochronous IN transaction of `n` bytes:

  `t = 38·8·2.083 + 2.083·floor(3.167 + 1.1667·8·n)` ns

  This is implemented in [`bandwidth/hs_budget_model.py`](../../../bandwidth/hs_budget_model.py), with Host_Delay taken as 0.
- An alt setting with base packet `b` and `m` transactions per microframe costs `m·t(b)`.
- Worked values:
  - 3×1024 (C930e alt 11) costs 61.6 µs, 49.3% of a microframe.
  - 3×1023 (the generic camera's only alt) also costs 49.3%.
  - So two max-alt cameras need 98.6% against an 80% limit.
- The Linux UVC FAQ states the same 80% rule and notes that it caps *allocation*, not use (web, <https://www.ideasonboard.org/uvc/faq/>).

### 2.2 xHCI: root ports are primary domains, TTs are secondary (doc)

- Sarah Sharp's 2011 Linux commit [`839c817ce671`](https://github.com/torvalds/linux/commit/839c817ce67178ca3c7c7ad534c571bba1e69ebe) "xhci: Store information about roothubs and TTs" says: *"Each root port is a separate primary bandwidth domain, and each high speed hub's TT (and potentially each port on a multi-TT hub) is a secondary bandwidth domain."* It also says that full- or low-speed devices plugged directly into a root port are treated as a primary domain, "since there isn't really a high speed bus between the roothub and the host".
- In `drivers/usb/host/xhci.h` lines 602–607 (master f66469d): *"Each root port is allocated the full bus bandwidth. We must also treat TTs (including each port under a multi-TT hub) as a separate bandwidth domain. The direct memory interface (DMI) also limits the total bandwidth (across all domains) that can be used."* Lines 773–778 say the same: each TT of a hub on a root port is a separate domain.
- **xHCI 1.2 Get Port Bandwidth command** (§4.6.15, output layout §6.2.6): returns one byte per root port, the available bandwidth in percent for a given device speed. A Hub Slot ID selects a TT instead.
  - Linux has exposed it since commit `59d50e53e070` (2025-05-21; probably v6.16, inferred) as `/sys/kernel/debug/usb/xhci/<pci>/port_bandwidth/{HS_BW,FS_BW,SS_BW}`, with lines like `port[N] available bw: X%.` (`xhci-debugfs.c` lines 673–743).
  - The SS query was wrong until fix `452af0f9ffe1` (2026-04-02). HS and FS were right from the start, because kernel and xHCI speed IDs agree up to high speed.
  - It needs root, because it is debugfs.
  - The patch's test log shows FS_BW dropping from 90% to 76% on the ports concerned after a full-speed audio device was plugged in (web, [LKML v6](https://lkml.iu.edu/hypermail/linux/kernel/2504.0/01523.html)).
  - **This is the one direct, controller-reported view of the domain boundary.** I could not read the xHCI 1.2 §4.16 "Bandwidth Management" text itself: the public Intel PDF download was blocked from this session. The spec citations here come via the Linux sources.
- **Bandwidth errors from the controller:** if a Configure Endpoint command (issued on SET_INTERFACE to a streaming alt) over-subscribes a domain, the controller completes it with Bandwidth Error (code 8) or Secondary Bandwidth Error (code 35, TT). Linux maps both to `-ENOSPC` and logs *"Not enough bandwidth for new device state."* (`xhci.c` lines 2135–2140, doc). Resource Error (out of endpoint contexts) maps to `-ENOMEM` (lines 2129–2133), which is a different failure.

### 2.3 Intel's software bandwidth table (Panther Point only) (doc and inferred)

- `XHCI_SW_BW_CHECKING` is set only for `PCI_DEVICE_ID_INTEL_PANTHERPOINT_XHCI`, the 7-series chipset of 2012 (`xhci-pci.c` lines 354–358, together with a 64-endpoint limit).
- `xhci_check_bw_table` (`xhci.c` lines 2444–2610) keeps one table per root port, `xhci->rh_bw[hw_portnum]`, plus one per TT. Its rules:
  - It counts in 4-byte "blocks" for high speed.
  - It adds `HS_OVERHEAD` = 26 blocks per packet.
  - It reserves `HS_BW_RESERVED` = 20% of `HS_BW_LIMIT` = 1607 blocks (`xhci.h` lines 624–661).
  - It charges `TT_HS_OVERHEAD` = 125 blocks of the root port's high-speed budget for every active TT.
- Failure returns `-ENOMEM`, not `-ENOSPC` (lines 2997–3003). So **on Panther Point, a bandwidth refusal looks like a resource error** at VIDIOC_STREAMON (inferred).
- Applied to Gerald's pairs (script output), this model is *stricter* than what Gerald's Raptor Lake controller (8086:7A60) did:
  - it predicts that C930e alt 8 plus the generic camera fails (1620 blocks > 1607);
  - Gerald streamed that pair 5 of 5 times.
  - So it agrees with Gerald in 20/26 rows, against 26/26 for the USB 2.0 model.
- Admission thresholds therefore differ between controller generations, even from one vendor. The domain *shape* (per root port) is the same.

### 2.4 Other software schedulers in Linux (doc)

- **MediaTek xHCI** (`xhci-mtk-sch.c` lines 117–150):
  - *"each HS root port is treated as a single bandwidth domain, but each SS root port is treated as two bandwidth domains, one for IN eps, one for OUT eps."*
  - The high-speed limit is `HS_BW_BOUNDARY` = 6144 payload bytes per microframe, from USB 2.0 Table 5-5. It adds no per-packet overhead.
  - So this model *admits* two max-alt cameras on one root port (6141 B ≤ 6144). It disagrees with Gerald in 16/26 rows. Thresholds differ a lot between vendors.
- **EHCI** (`ehci-sched.c`, `ehci-sysfs.c` lines 62–120):
  - One periodic schedule for the whole controller, with `uframe_periodic_max` defaulting to 100 µs and tunable from 100 to 124 µs through sysfs (root). Refusal returns `-ENOSPC` (lines 776 and 1531).
  - An EHCI controller is one 480 Mb/s bus, so **on EHCI the domain is the whole controller.** That includes Intel 5/6/7-series chipsets, where each EHCI has an internal rate-matching hub in front of all its ports.
  - Separate hubs on one EHCI controller do not help. This is the source of the old advice "put each camera on a different controller", as in the Linux UVC FAQ (web).

### 2.5 Windows (measured and doc)

- Windows' USB 3 stack has no software bandwidth table for xHCI; the controller decides (inferred: none is documented, and the Gerald outcomes match the hardware model).
- What an application sees (measured):
  - **Media Foundation:** activation, reader creation and SetCurrentMediaType succeed. The first `ReadSample` then fails with `0x800718CF`, which is `HRESULT_FROM_WIN32(6351)`. `FormatMessage` on Gerald today gives *"A camera interface doesn't have the desired bandwidth for data transfer."* (PowerShell `([ComponentModel.Win32Exception]6351).Message`, run 2026-11-06). The code is not in SDK 10.0.22621's `winerror.h`.
  - **DirectShow:** fails as `OSError(5)`, access denied. That is ambiguous with "camera in use" and privacy blocks.
  - Sources: [`docs/capture_backends_review.md`](../../../docs/capture_backends_review.md), [`RERUN_20261027.md`](../../windows/Gerald/RERUN_20261027.md).
- `usb.h` (SDK 10.0.22621, line 318) defines `USBD_STATUS_NO_BANDWIDTH 0x80000700`, which is what a kernel client sees (doc).

### 2.6 Hubs (doc and inferred)

- **USB 2.0 hub, high-speed devices:** the hub repeats; every high-speed device below it shares its upstream link and, through it, the root-port link. Single-TT and multi-TT only matter for full- and low-speed devices: a multi-TT hub gives each port its own 12 Mb/s TT domain.
- **Full- and low-speed periodic devices behind a high-speed hub** still use high-speed bandwidth for split transactions. Intel's software model charges each active TT a fixed 125 blocks, about 7.8% of the root port's budget (doc, `xhci.h` lines 641–647). Gerald's Microchip 2137 hub, with a full-speed Unifying receiver and a 04d8:0b2a device, sat on root port 13 throughout. The measured thresholds already include any such cost.
- **USB 3 hub:** an internal USB 2.0 hub plus a SuperSpeed hub, sharing a ContainerId. A USB 2.0 camera in it uses the USB 2.0 hub, and therefore the USB 2.0 root port on the *USB 2.0 wires* of the upstream connector. A SuperSpeed camera such as the Kiyo Pro uses the SuperSpeed root port, a separate domain on Intel and MediaTek (doc). **A USB 3 camera and USB 2.0 cameras on one USB 3 hub do not compete for periodic bandwidth** (inferred from the dual-bus architecture; not measured).

### 2.7 Thunderbolt, USB4 and docks (web and measured)

- **USB4 or Thunderbolt 4 dock on a USB4/TB4 host:** USB 3 is tunnelled to the host xHCI. USB 2.0 runs on the separate D+/D− pair to the host connector's USB 2.0 port.
  - On Intel Thunderbolt hosts (Maple Ridge, Tiger Lake and later) that USB 2.0 port belongs to the chipset or SoC xHCI, not the Thunderbolt controller: "the regular USB2 controller of the system is used and USB2 just routed" (web, [Framework community](https://community.frame.work/t/details-about-usb-thunderbolt-and-dock-operation/15793/8); the USB 2.0 pins are separate, [Wikipedia USB4](https://en.wikipedia.org/wiki/USB4)).
  - **So every USB 2.0 camera on such a dock shares one high-speed domain:** the host connector's USB 2.0 root port.
- **Thunderbolt 3 dock, or any TB dock on a TB3 host:** the dock's own PCIe xHCI (Titan Ridge or Goshen Ridge) serves all its ports, typically through an internal hub, "480 Mbps for USB 2.0" across all ports (web, MacRumors thread quoted in search results). The domain is the dock xHCI's USB 2.0 root port, usually one for the whole dock.
- **Measured on Gerald today** (read-only PowerShell, `Get-PnpDevice` with `DEVPKEY_Device_LocationPaths`, `DEVPKEY_Device_Parent` and `DEVPKEY_Device_ContainerId`):
  - The second controller is `PCI\VEN_8086&DEV_1138`, "Intel(R) USB 3.10 eXtensible Host Controller", behind PCIe root port RP05 and `ACPI(TBDU)`. This is the Thunderbolt 4 (Maple Ridge) xHCI.
  - The SuperSpeed half of the GL3523 USB 3 hub (05E3:0625) is on its port SS04.
  - The hub's USB 2.0 half (05E3:0610 `5&CC3F949&0&13`) is on the **chipset** xHCI 8086:7A60 at `ACPI(HS13)`. Both report ContainerId `{C6399911-…}`.
  - The same pairing repeats one level down (0626/0610 `{9F4B56F0-…}`, 5537/2137 `{63736D73-…}`).
  - **A library that took the "controller" of a USB 2.0 camera from the SuperSpeed parent chain would get it wrong.** It must walk the USB 2.0 parent chain.

### 2.8 Apple Silicon and Intel Macs (doc, web, inferred)

- Apple M1 (t8103) has one DWC3-based xHCI per USB-C port, each with its own PHY carrying both USB 2.0 and USB 3: `dwc3_0` and `dwc3_1` with `atcphy0` and `atcphy1` (doc, `arch/arm64/boot/dts/apple/t8103.dtsi` lines 1021–1108). So on the Thunderbolt/USB-C ports, **each connector is its own controller and domain.**
- USB-A ports on some Apple Silicon Macs are behind a separate PCIe xHCI shared by the two ports, for example an ASMedia ASM3142 on M1 Max (web, MacRumors thread in search results).
- One user reports that only two USB 2.0 webcams worked per TB4 port (web; details not retrievable, 403).
- Intel Macs with T2: Alpine Ridge or Titan Ridge Thunderbolt controllers, each with an integrated xHCI serving two ports (web and inferred).
- The macOS error code is unverified. `kIOReturnNoBandwidth` (0xE00002EC, IOKit `IOReturn.h`) is the likely low-level code (inferred). How AVFoundation surfaces it is an open question.

### 2.9 Vendor matrix (what is and is not known)

| Controller family | High-speed domain | Evidence | Label |
| --- | --- | --- | --- |
| Intel xHCI, 8-series and later (Gerald: Raptor Lake 8086:7A60) | per USB 2.0 root port; threshold ≈ USB 2.0 80% model | 26/26 on one root port; cross-port 98.4% admitted | measured |
| Intel Panther Point (7-series) xHCI | per root port, stricter: software table, 20% reserve, 26-block overhead per packet, TT charge; error `-ENOMEM` | Linux source | doc |
| Intel Thunderbolt xHCI (Maple Ridge 8086:1138) | carries SuperSpeed of TB ports; USB 2.0 of those connectors is on the chipset xHCI | Gerald PnP tree | measured (pairing inferred from ContainerId and port numbers) |
| MediaTek xHCI | per root port; 6144 B/µframe payload, no overhead (more permissive) | Linux source | doc |
| EHCI (any vendor) | whole controller | Linux ehci-sched; USB 2.0 architecture | doc |
| Apple Silicon USB-C (DWC3) | one controller per connector | device tree | doc |
| VIA VL805 (Raspberry Pi 4) | all 4 USB 2.0 ports behind one internal hub (2109:3431) on one root port | forum and lsusb posts | web |
| TB3 dock xHCI, TB4/USB4 dock | one high-speed domain for the whole dock (dock xHCI root port, or host connector's USB 2.0 port) | forum posts | web |
| AMD (CPU and Promontory/ASMedia chipset), ASMedia, Renesas, VIA, Fresco add-in | **unknown**: spec says per root port; no isolating measurement found | — | open |

---

## 3. What Gerald's data says

Sources:
- [`RERUN_20261027.md`](../../windows/Gerald/RERUN_20261027.md) goal 3;
- [`bw_rerun_20261027_analysis/model_vs_observed_rerun.json`](../../windows/Gerald/bw_rerun_20261027_analysis/model_vs_observed_rerun.json);
- [`bw_concurrency_rerun_20261027/r08_cross_rootport_no_kiyo.json`](../../windows/Gerald/bw_concurrency_rerun_20261027/r08_cross_rootport_no_kiyo.json) and `rv_solo_and_crossport.json`;
- `phase2_bw_alt/coexist_*.json` and `topology_2137Z_audio_iso_active.json`.

Topology on 10-27:
- The C922 was alone on chipset root port 1.
- The C930e and generic were on an inner Genesys 0610 hub, inside the GL3523's USB 2.0 half on root port HS13.
- A PreSonus 194f:0422 audio interface was on HS13 port 2.

**Same root port: threshold between 75.2% and 80.9% of a microframe** (measured):

| Pair on HS13 | USB 2.0 model | Observed |
| --- | --- | --- |
| C930e alt 5 (1×800) + generic | 62.2% | both stream |
| C930e alt 6 / 7 / 8 + generic | 64.5 / 70.2 / 75.2% | both stream (alt 8: 5/5) |
| C930e alt 9 (2×992) + generic | 81.1% | refused (5/5) |
| C930e alt 10 / 11 + generic | 92.6 / 98.6% | refused |
| Earlier window, audio iso active: C930e alt 6 / alt 7 + generic + audio | 75.2 / 80.9% | alt 6 passes, alt 7 refused |

- The audio row: the 10-27 snapshot shows the 194f:0422 holding two isochronous IN/OUT pipes of 312 B at bInterval 1. Each costs 6.7 µs, 10.7% together (computed from `topology_2137Z_audio_iso_active.json`).
- The audio window was "probable, not verified" in REPORT finding 17. These numbers make that explanation quantitatively consistent: alt 7 + generic + audio = 80.9%, just over 80%.
- **Caveat:** the 26 rows contain only 7 distinct load totals. Several rows repeat the same pair, so they are not 26 independent tests.

**Different root ports: not pooled** (measured, r08 and rv):
- C922 at 1080p30 (alt 11, 3×1020) on root port 1 and C930e at 1080p30 (alt 11, 3×1024) on HS13 both streamed. As one domain that is 98.4% of a microframe, which this controller refuses within one root port.
- The three-camera `three_cams_max_fit` row also streamed: C922 alt 11 + C930e alt 8 + generic, 124% controller-wide.
- So the 7A60 does not apply a controller-wide 80% high-speed limit.

**Each camera reserves a different alt per mode** (measured, `r02/r03/r04/r06` in `bw_concurrency_rerun_20261027/`):

| Mode | C922 alt (B/µframe) | C930e alt (B/µframe) | Generic |
| --- | --- | --- | --- |
| MJPEG 640x480@30 | **4 (640)** | 10 (2688) | 1 (3069) |
| MJPEG 1280x720@30 | 9 (1984) | 11 (3072) | 1 |
| MJPEG 1920x1080@30 | 11 (3060) | 11 | 1 |
| MJPEG 1920x1080@5 | **5 (800)** | 11 | — |
| MJPEG 640x480@15 / @5 | — | 8 (1600) / 3 (512) | — |
| MJPEG 640x360 / 480x270 / 352x288 @30 | — | 9 / 7 / 6 | — |
| MJPEG 320x240@30 | — | 5 (800) | — |
| YUY2 640x480@30 | 10 | 10 | 1 |

**Can the alt be predicted from descriptors alone? Only roughly** (measured, computed from `topology_idle_0307Z.json` frame descriptors against the 28 observed camera-mode alts):
- The smallest alt with capacity ≥ `dwMaxVideoFrameBufferSize·fps/8000` matched 12/28, predicted too *small* in 13/28 and too large in 3/28.
- The same rule using `dwMaxBitRate/64000` matched 13/28 and was too small in 9/28.
- The largest alt matched 8/28 and was never too small.
- The camera's PROBE answer (`dwMaxPayloadTransferSize`) is what the class driver uses. Linux `uvc_video.c` lines 2044–2089 pick the smallest alt whose bytes per interval ≥ `dwMaxPayloadTransferSize` (doc), and usbvideo behaves the same per the table above.
- PROBE is a class request to the interface the camera driver owns. It is **not** sendable without the driver swap on Windows or detaching uvcvideo on Linux. The repo's PROBE data came from libusb on WinUSB.
- So **before opening, only the largest alt is a safe upper bound.** The true reservation must be learned by opening the mode once and reading the selected alt:
  - Windows: hub IOCTL open pipes, 89/90 measured, no admin.
  - Linux: `/sys/bus/usb/devices/<intf>/bAlternateSetting` and `ep_XX/wMaxPacketSize`, world-readable (doc, `Documentation/ABI/testing/sysfs-bus-usb`).
  - macOS: IORegistry interface properties (inferred, unverified).

**Prediction for today's layout** (measured topology, model computed):
- The C922 and the generic camera are now both on HS13 → inner hub, ports 4 and 2. The C930e is alone on HS07. The Kiyo is SuperSpeed on the TB4 xHCI.
- So C922 MJPEG 720p30 (alt 9) + generic = 81.1% → **predicted refused**.
- C922 MJPEG 640x480@30 (alt 4) + generic = 59.7% → predicted fits. So does 1080p@5 (alt 5, 62.2%).
- This is a ready test for the Windows run (section 7).

---

## 4. Data model (OS-neutral)

```text
Controller  id, os_ref, pci_vid:did (or platform compatible), vendor, friendly_name,
            kind {xhci, ehci, ohci/uhci, dwc3-apple, tb-xhci, dock-xhci}, location_path,
            policy {hs_domain: "root_port" | "controller", threshold_us: 100, source: default|table|learned}
Port        controller_id, hub_chain [root_port, p2, ...], half {usb2, usb3}, companion_port_id,
            connectable {user|internal|not_used|unknown}, connector {A, C, internal, unknown},
            pld {panel, vpos, hpos, color, group_token, group_pos} (optional), label (best available), occupant
Device      key, vid:pid, serial, bcdUSB, speed {LS, FS, HS, SS, SS+}, port_path (USB2-side), parent_hub,
            is_hub, hub_tt {single, multi, none}, container_id, open_periodic_pipes [(ep, type, bytes, mult, interval)]
Camera      key (naming/camera_identity.py: serial if unique else port path), device, vs_interface,
            alt_table [(alt, base, mult, interval)], current_alt, mode_alt_cache {(vid,pid,bcdDevice,fmt,w,h,fps) -> alt}
Domain      key, kind {hs_link, tt, fs_root, ss_in, ss_out, controller}, budget_us, members, load_us (observed),
            predicted_load_us, bracket {max_pass_us, min_fail_us} (learned per controller model)
```

### 4.1 Domain key derivation per OS

High-speed cameras only, which is the case that matters here. Full-/low-speed and SuperSpeed cameras get the analogous keys from section 2.

| OS | Controller | USB 2.0 root port | Notes |
| --- | --- | --- | --- |
| Windows | walk `CM_Get_Parent` from the camera's composite device until a `PCI\…` (or ACPI) host controller. The repo's `win_usb_topology.py` already does this | port index on `USB\ROOT_HUB30\…` (or `ROOT_HUB20`) in the location path, e.g. `#USBROOT(0)#USB(13)`, or ACPI `#ACPI(HS13)` | the USB 2.0 half is the devnode chain the high-speed camera actually hangs from. Do not use the SuperSpeed twin hub. Pair halves by `DEVPKEY_Device_ContainerId` (measured) or, for root ports, `IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES.CompanionPortNumber/CompanionHubSymbolicLinkName` (doc, other topic) |
| Linux | `realpath /sys/bus/usb/devices/usbN/..` gives the PCI or platform device. An xHCI registers **two** buses (USB 2.0 and USB 3 root hubs) under one PCI function, so group buses by that parent | first element of the device name `N-P.x.y` (P = root port) on the bus whose `speed` is 480 | `portN/peer` links USB 2.0 and USB 3 halves. `portN/connect_type` gives hotplug, hardwired or not used, and `portN/location` the raw _PLD (doc, sysfs-bus-usb). All readable without root |
| macOS | IORegistry parent chain to the `AppleUSBXHCI*` / `AppleT*USBXHCI` controller | top nibbles of `locationID` (0xBBPPPPPP: bus byte, then one nibble per tier) | details in the macOS topic report. Each Apple Silicon USB-C connector is its own controller (doc) |

`domain_key = (controller.id, "hs", root_port)` when `controller.policy.hs_domain == "root_port"`, else `(controller.id, "hs", "*")`.

### 4.2 Default policy table (then learned)

| Match | hs_domain | threshold | Basis |
| --- | --- | --- | --- |
| EHCI (class 0x0C0320), or an Intel rate-matching hub (8087:0020/0024) at the root | controller | 100 µs | doc |
| Intel xHCI 8086:1E31 (Panther Point) | root_port | stricter: use Intel software blocks (≤1607 incl. reserve) | doc |
| Intel xHCI (other) | root_port | 100 µs | measured (7A60) |
| MediaTek xHCI | root_port | 6144 B payload | doc |
| Apple Silicon DWC3 | root_port (= controller) | 100 µs | doc |
| anything else (AMD, ASMedia 1B21, Renesas 1912, VIA 1106, Fresco 1B73, Etron, …) | root_port, **flag uncertain** | 100 µs | spec default; unverified |

**Learned escalation:**
- If a bandwidth-class refusal happens and the refusing domain's observed plus predicted load is < 75% of the budget, look at the whole controller.
- If the controller-wide load is > 80%, set `policy.hs_domain = "controller"` for that `pci_vid:did`. Persist it in the user's config, and say so in the message ("on this controller all ports appear to share bandwidth").
- Conversely, record per controller model the largest load that passed and the smallest that failed (`bracket`). Use the bracket instead of the 100 µs default once both ends exist.

### 4.3 Load and budget per domain

- `cost_us(ep) = mult · t(base)` for isochronous IN with bInterval 1, using the §5.11.3 formula (IN and OUT costs are near-identical).
- For endpoints with period `2^(bInterval−1)` > 1 microframe, use the full cost. This is conservative. Such endpoints are tiny HID or audio-feedback pipes, and the host may stack them.
- For full-/low-speed devices behind a high-speed hub, add the split cost: about 7.8% of the high-speed budget per active TT, after Intel's model. This is conservative for others.
- **Observed load** = the sum over all devices in the domain of their *currently open* periodic pipes:
  - Windows: `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX` open-pipe list, no admin, measured.
  - Linux: each interface's current `bAlternateSetting`, plus the `ep_XX` attributes.
  - Root-only extra on Linux ≥ 6.16: debugfs `HS_BW` gives the controller's own % available per root port. Use it for diagnostics and the vendor test only.
- **Predicted load** for a camera about to open in a given mode = `cost(mode_alt_cache[...])` if known. Otherwise `cost(largest alt)`, marked "worst case". The descriptor estimate (§3) is shown only as "likely".
- **Verdicts:**
  - `fits` if predicted ≤ 0.8·budget·(learned factor, default 1);
  - `marginal` if within the bracket, or between 75 and 80 µs before a bracket exists. Gerald's measured bracket is 94.0–101.1 µs: pass at 75.2%, refusal at 80.9%;
  - `over` otherwise.
  - Never refuse to try on a prediction alone. The prediction drives the message and the open order.

---

## 5. Runtime algorithm

1. **Map.** Enumerate controllers, root ports, hubs and devices. Use OS tree APIs only: no camera open, no libusb enumeration, since libusb sends GET_DESCRIPTOR to every device (REPORT "Enumeration touches cameras").
   - Build domains and compute observed loads.
   - Attach camera keys from `camera_identity.py`.
2. **Plan.** For the requested cameras and modes, compute predicted loads per domain.
   - If a domain is `over`, warn *before* opening, with the same message as step 5 marked "predicted". Show the lower-mode alternatives from `mode_alt_cache`.
3. **Open in priority order with a stagger.** Gerald showed that with no stagger the loser is random (3 of 4 over-budget combos changed loser), and with a 2.5 s stagger the second always loses.
   - Open sequentially. Treat a camera as admitted only after its **first frame** arrives: MF fails at the first ReadSample, not at open.
   - Then read back its selected alt (Windows open pipes, Linux sysfs) and update `mode_alt_cache` and the domain load.
4. **Classify a failure.**
   - **Bandwidth (certain):** Windows MF `0x800718CF`; Linux `ENOSPC` from `VIDIOC_STREAMON`, which covers xHCI codes 8 and 35 and EHCI.
   - **Bandwidth (probable):** DirectShow `E_ACCESSDENIED`/`OSError(5)`, or Linux `ENOMEM` on an Intel Panther Point controller, *and* another camera in the same domain is streaming *and* predicted load is over. Optionally confirm: the failing camera opens alone, or after the other stops.
   - **Not bandwidth:** Linux `ENOMEM` elsewhere means endpoint-context exhaustion, which on Windows shows as the "Not enough USB controller resources" notification: a different fix, fewer devices per controller. `EBUSY` means in use. Also not bandwidth: `0x8007001F` (device not functioning) and privacy denials.
   - **macOS:** open question (`kIOReturnNoBandwidth` is likely underneath).
   - After a refused start, expect one zero-frame start on retry (REPORT finding 19). Retry once before reporting.
5. **Report and suggest** (section 6). After the user moves a camera, re-map on device arrival and confirm that the camera landed in a domain with room. This catches mislabeled ports.

### 5.1 Suggested-port selection

1. **Candidates:** every root-port USB 2.0 half (with its USB 3 companion as the same physical connector) whose `connectable` is user or unknown, on any controller. Exclude internal, not-used and hard-wired ports: Intel `USBR` redirection ports and internal Bluetooth (8087:0033 on HS14).
2. **Compute each candidate's high-speed domain load:**
   - Empty connector: 0, and the domain is free unless the controller policy is "controller", in which case it is the controller's load.
   - Connector holding a hub or devices: their observed load.
3. **Keep candidates where** `load + cost(moving camera's mode) ≤ threshold` and the domain is not the conflicting one.
   - Prefer, in order:
     a) empty connectors on a controller whose policy is known per-root-port;
     b) empty connectors on a *different* controller when the current controller is "uncertain" or "controller";
     c) occupied connectors with room, flagged "shares with: <devices>".
   - Inside a rank, prefer the same panel group as the camera's current port, then connector type matching the camera's plug: USB-A, unless the user has adapters.
4. **Group the result by `(controller.friendly_name, pld.panel/group_token or "unlabelled")`.** List the best available label per connector.
5. **Also compute the "stay here" alternative:** for each camera in the conflicting domain, the highest mode in `mode_alt_cache` (or the descriptor ladder, marked unverified) that makes the domain fit.

---

## 6. User message template

```text
{A.name} and {B.name} share USB bandwidth: both connect through {shared_hop}.
When I tried to open them both at the same time, {loser.name} failed with a USB bandwidth error ({code}).
At these settings they need about {pct_total}% of what that USB 2.0 link allows
({A.name} {mode_A}: {pct_A}%, {B.name} {mode_B}: {pct_B}%{, other devices on the link: {pct_other}%}).

Suggest moving one of those cameras to any of the following controller ports:
  {group_label_1}: {port_label}, {port_label}, ...
  {group_label_2}: ...
Or, to keep both where they are, lower {B.name} to {alt_mode_B} (about {pct_alt_B}%){, or {A.name} to {alt_mode_A}}.
```

| Field | Best (labels available) | Fallback 1 | Fallback 2 | Fallback 3 |
| --- | --- | --- | --- | --- |
| `shared_hop` | "the USB hub 'Genesys GL3523' plugged into the rear USB-C port (Intel USB 3.20 controller)" | "the same USB hub (05E3:0610)" | "the same port on the Intel(R) USB 3.20 eXtensible Host Controller (port 13)" | "the same USB connection to the computer" |
| `group_label` | "Rear panel, Intel USB 3.20 controller" (from _PLD panel, or a group token shared by companion ports) | "Intel(R) USB 3.20 eXtensible Host Controller" (OS friendly name) | "USB controller #2 (PCI 8086:7A60)" | "a different USB port directly on the computer" |
| `port_label` | "USB-C, second from top (blue)" (_PLD position, color, connector) | "port 7 (USB-A, user-accessible)" | "HS07 / location path `…#USB(7)`" | "any empty port **not** on {hub name} / {dock name}" |
| `code` | "0x800718CF: not enough USB bandwidth" | "ENOSPC" | "access denied (probably bandwidth: see details)" | — |

Rules:
- Never suggest a port on the same hub, dock, or USB4/TB dock. Never suggest the SuperSpeed twin of the conflicting connector: a USB 2.0 camera there would use the same USB 2.0 root port.
- When the controller policy is "uncertain", add: "If the error persists after moving, try a port on a different controller ({other controller names})."
- When the camera is behind a dock or Pi-style integrated hub, say so explicitly: "all USB 2.0 ports on this dock share one connection".
- If nothing fits anywhere, show only the lower-mode alternative, plus "add a USB controller card with one controller per port".

Example built from the measured layout of 2026-11-06 (the labels shown are from fallback level 1–2, the only ones I can confirm without running the port-property IOCTL):

> C922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (Genesys 05E3:0610) on port 13 of the Intel(R) USB 3.20 eXtensible Host Controller. When I tried to open them both at the same time, USB Camera failed with a USB bandwidth error (0x800718CF). At 1280x720 MJPEG 30 fps they need about 101% of what that USB 2.0 link allows (C922 40%, USB Camera 62%). Suggest moving one of those cameras to any of the following controller ports: Intel(R) USB 3.20 eXtensible Host Controller: any empty port directly on the computer other than port 13 (port 7 is in use by the C930e and is also full). Or lower the C922 to 640x480 MJPEG 30 fps (13%), which fits next to USB Camera.

Percentages in messages are of the 80% budget (100 µs), not of the microframe. C922 alt 9 is 31.9% of a microframe, i.e. 39.9% of budget. The generic camera is 49.3% of a microframe, i.e. 61.6% of budget. "Port 7 is full" follows from the C930e at 720p30 using 61.6% of budget, leaving no room for a second max-alt camera.

---

## 7. Recommended tests

| # | Platform | Test | Decides | Human? |
| --- | --- | --- | --- | --- |
| T1 | Windows (Gerald, current layout) | C922 + generic on HS13: MJPEG 720p30 + generic (predicted refused at 81.1%), 640x480@30 + generic (predicted fits, 59.7%), 1080p@5 + generic (62.2%). Read alts from open pipes | that the model holds for a new pair on the same root port, and how close 81.1% is to the true threshold | no (cameras already in place) |
| T2 | Windows | Port-property IOCTL dump of empty ports (`IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES`, `…INFORMATION_EX_V2`) plus `DEVPKEY_Device_PhysicalDeviceLocation` for occupied ports. Check which labels are reachable without admin | message label fallback level on Windows | no |
| T3 | Linux, ≥ 6.16, root once | stream camera A on root port 1; read debugfs `port_bandwidth/HS_BW` for all ports; add camera B on port 2 and on a hub under port 1 | **per-root-port vs per-controller domain** on that controller; repeat on AMD, ASMedia, Renesas, VIA | needs camera moves |
| T4 | Linux, no root | ENOSPC at STREAMON with two max-alt cameras behind one hub; check dmesg line text and errno; sysfs `bAlternateSetting` readback | error classification and observed-load readback | no |
| T5 | Any, with a TB4/USB4 dock and a TB3 dock | two cameras on two dock ports vs one dock port and one host port | dock = one high-speed domain | yes |
| T6 | macOS (Apple Silicon) | two max-alt cameras via one USB-C hub (expect refusal) and on two USB-C ports (expect success); capture the AVFoundation and IOKit error | macOS error code, and per-connector domains | yes |
| T7 | Windows/Linux | 3+ cameras on one root port at small modes (e.g. C930e 320x240 alt 5 ×2 + C922 640x480 alt 4) | additivity of the model beyond pairs | yes |

## 8. Open questions

- AMD, ASMedia, Renesas, VIA and Fresco: does one high-speed root port form a domain, or does the controller pool periodic bandwidth across ports? And with what threshold?
- The xHCI 1.2 §4.16 text was not read directly (blocked download). The spec claims here rest on the Linux commit and comments.
- How does macOS AVFoundation report a refused isochronous reservation?
- Are `_PLD` panel and position available for **empty** ports on Windows without a kernel component? (ACPI evaluation is kernel-side; Linux exposes `location` and `firmware_node/physical_location`.)
- Is Gerald's measured threshold really 80%, or is it in 75.2–80.9% because of the Host_Delay term (taken as 0) or the hub, TT and interrupt load?
- Does the C922's mode-dependent `dwMaxPayloadTransferSize` (alt 4 at 640x480 MJPEG, alt 5 at 1080p@5) vary with firmware (bcdDevice)? That decides the `mode_alt_cache` key.

---

## Verifier notes

Adversarial verifier, 2026-11-06. No camera was opened or streamed. What I re-checked:
- Linux sources re-downloaded at `f66469d9905b39d2c260a15d7d6db450f4db67c1`: `xhci.h`, `xhci.c`, `xhci-pci.c`, `xhci-mtk-sch.c`, `xhci-debugfs.c`, `usb-acpi.c`, `uvc_video.c`, `ehci-sysfs.c`, `t8103.dtsi`, and the sysfs ABI files.
- The three cited commits, read as `.patch` from github.com.
- `domain_model_compare.py`, re-run into the scratchpad. Its output matches the committed JSON.
- The Gerald result files: r02, r03, r04, r06, r08, rv*, the three topology snapshots and zero_frame.
- A read-only PowerShell PnP query (`Get-PnpDevice` plus LocationPaths, Parent and ContainerId) and `[ComponentModel.Win32Exception]6351`.
- A grep of SDK 10.0.19041 and 10.0.22621.

### V1. AMD pools high-speed bandwidth: the report's own source contradicts it (refutes C26, changes the policy table)

The commit that added debugfs `port_bandwidth` (`59d50e53e070`, Xu Rao, author date 2025-05-15, not 05-21) was **tested on an AMD Raven USB 3.1 xHCI** (03:00.3). Its log shows:
- `HS_BW` read 79% on root ports 1-4.
- After "plug in hs usb video ID 0408:1040" it read **39% on all four ports at once**.
- `FS_BW` likewise fell from 90% to 76% **on all four ports** after one full-speed audio device was plugged in.

Section 2.2 of the report quotes only the FS drop, "on the ports concerned". The log actually shows that this AMD controller accounts for (at least reports) high-speed periodic bandwidth **controller-wide**. That is the opposite of the per-root-port default the design gives AMD.

Source: <https://github.com/torvalds/linux/commit/59d50e53e070ce03c811e31c4fb583d3b0f88cfc> (commit message); also LKML v4-v6 of the patch. Label: doc (a test log in the commit, one controller, one sample). Whether admission really refuses across ports on AMD is still unmeasured.

**Correction:** default AMD xHCI (PCI vendor 1022) to `hs_domain = controller` until measured, not "root_port, uncertain". T3 becomes "confirm per vendor", and it is cheap: one camera on one port, then read HS_BW for all ports.

### V2. The design's load accounting contradicts the 26/26 calibration (C27 design use, section 4.3)

The 26/26 USB 2.0 model (`model_vs_observed_rerun.json`) counts **only the cameras' isochronous endpoints**. On 10-27, HS13 also carried:
- interrupt pipes from both cameras (C930e 64 B bInterval 8, generic 16 B bInterval 4);
- three hub status pipes;
- an **active TT**: the Microchip 2137 hub, with the Unifying receiver's three interrupt pipes and 04d8:0b2a's two 64 B interrupt pipes at bInterval 1. See `bw_topology_rerun_20261027/topology_idle_0307Z.json` and `topology_before_shared_hub_0313Z.json`, which I re-read.

Section 4.3 says to count every open periodic pipe at full cost and to add ~7.8% per active TT. That turns the measured passing pair (C930e alt 8 + generic) into a predicted **over**:
- interrupts at full cost add about 4.8 us, 3.9% of a microframe;
- the TT adds 7.8% of budget;
- together that is about 75.2 + 3.9 + 6.2, roughly 85% of a microframe, against an 80% limit.

Yet the pair streamed in every one of its runs. The same applies to the Panther Point model: `domain_model_compare.py` omits the `TT_HS_OVERHEAD * num_active_tts` term that `xhci_check_bw_table` applies (xhci.c, `!virt_dev->tt_info && HIGH` branch). With the term included, alt 7 + generic becomes 1665 > 1607, and agreement falls to 19/26.

**Correction:** a threshold or bracket is only valid under the accounting used to derive it.
- Either keep the calibrated accounting (camera and audio isochronous endpoints only), or re-derive the bracket with the full accounting.
- Do not mix the two.
- Treat the TT charge as Panther-Point-only (doc), not as a conservative default.

### V3. Claim-level checks

- **Confirmed:**
  - C1 and C2: 7 distinct totals, re-run gives agree usb2 26, intel_sw 20, mtk 10.
  - C3: in r08, both cameras streamed with `streamed = true`, about 30 fps, 262/198 samples; `three_cams_max_fit` gave 30, 15 and 25.8 fps.
  - C5, C6, C7: HS_BW_LIMIT 1607 and HS_BW_RESERVED 20; `bw_used += bw_reserved; if (bw_used > max_bandwidth) return -ENOMEM`; `XHCI_SW_BW_CHECKING` only at `xhci-pci.c:355-358`.
  - C9, C10 (`xhci.c:2129-2140`), C12 (`ehci-sysfs.c`: `<100 || >=125` rejected, RW), C13 and C14 (PowerShell output identical to the report).
  - C15: the alt table re-derived from `pipes_while_streaming.matched_alt_settings`, 33 rows, of which 28 are non-generic.
  - C19 and C22 (RERUN lines 169-173), C21 (absent in 19041 too), C23 (`t8103.dtsi:1021-1108`), C25, C29 (arithmetic re-done).
- **C6 caveat:** the quoted comment opens "Some Intel xHCI host controllers need software to keep track of the bus bandwidth". It describes the Panther Point software model, which mimics Intel hardware. The DMI ceiling as a general Intel property is inferred.
- **C4 is weakened.** The numbers are consistent: two 312 B isochronous pipes at bInterval 1 plus a 4 B bInterval 4 feedback pipe, about 10.7-11.2%. But the audio pipes come from a snapshot taken *after* the window, so "quantitatively explained" upgrades REPORT finding 17's "probable" without new evidence. Keep it as "consistent with".
- **C11:** confirmed; the date is the author date 2025-05-15, and the fix `452af0f9ffe1` (Pecio, 2026-04-02) is confirmed. The commit's AMD numbers are the important part (V1).
- **C16:** unverifiable here. I did not recompute the descriptor estimates; the count of 28 is consistent.
- **C17:** confirmed. It now uses `usb_endpoint_max_periodic_payload`. **Missed:** when no alt is large enough, uvcvideo returns **-EIO** ("No fast enough alt setting", `uvc_video.c` ~L2081). That is a separate failure class, often from bad PROBE values, and the classifier should not call it bandwidth contention.
- **C18 is weakened.** `portX/location` is **not** raw _PLD. `usb-acpi.c:221-222` stores `VALID | group_token<<8 | group_position`, which is useful only for pairing companions. Panel, vertical and horizontal position, dock and lid come from `.../physical_location/` (ABI `sysfs-devices-physical_location`, 2022). Colour and shape are not exposed at all.
- **C20:** confirmed (FormatMessage text re-run). No public web documentation of 0x800718CF was found, so the classifier must hard-code it.
- **C24:** confirmed for TB4/USB4 hosts, from web sources. It generalises beyond discrete Maple Ridge (inferred from Gerald plus Intel TCSS design): on Intel laptops with integrated Thunderbolt, the USB-C ports' SuperSpeed sits on the TCSS xHCI while their USB 2.0 sits on the PCH xHCI.
- **C28:** acceptable as inferred.
- **C30 is weakened.** Every zero-frame-after-refusal case in `phase2_bw_alt_verify/zero_frame_after_refused_start.json` is the **libuvc/WinUSB path**: the refused start is `-1 I/O error`, not MF. The retry-once rule is unverified for MF and usbvideo.
- **C31 is weakened.** The design reads `alt_table` from config descriptors via `IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION`. That sends the same real GET_DESCRIPTOR(config) on EP0 that RERUN blames on libusb. Both are harmless standard requests, and neither opens a stream. The stated reason to avoid libusb ("to avoid touching cameras") is therefore not a difference. Linux sysfs `descriptors` is a cached copy with no bus traffic.

### V4. Other design corrections and gaps

1. **ContainerId is not a safe pairing key.** On Gerald today the GL3523's inner hub halves (0626 and 0610) both report `{9F4B56F0-1DF6-11E0-AC64-0800200C9A66}`. That is a time-based 2011 UUID, almost certainly fixed in the Genesys firmware's BOS Container ID capability, so two identical hubs would probably collide (inferred; untested). Pair by `IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES` companion info (root ports), or Linux `portN/peer`, plus topology position. Use ContainerId only as a tie-break.
2. **Group suggestions by the USB 2.0 companion's controller.** A USB-C port on Gerald's TB4 xHCI (8086:1138, "USB 3.10") has its USB 2.0 pins on the chipset 7A60. A "try a port on a different controller" message keyed on the connector's SuperSpeed controller name would send a USB 2.0 camera back to the same controller.
3. **Candidate set is too narrow.** Many motherboards put several rear ports behind a soldered hub on one root port, and front-panel headers often go through hubs too. Requiring "root-port connectors" excludes empty ports on hard-wired internal hubs, which are valid suggestions when that hub's root port has room. Include them, and label them with the hub's domain.
4. **The escalation rule is fragile.** One refusal below 75% permanently flips a PCI ID. Hidden periodic load (an audio device starting later), the PPT-style TT charge, or a wrong cached alt also produce refusals below 75%. Require two consistent events, or debugfs HS_BW confirmation, before persisting. With V1, AMD should start as "controller" anyway.
5. **The libusb/WinUSB path is missing from the error classifier.** The repo's own refusals there surface as `LIBUSB_ERROR_IO` (-1) at stream start (zero_frame file). Add it for a libuvc backend.
6. **Platforms missed:**
   - Raspberry Pi 5: RP1 has **two xHCI controllers, each with one USB 3 and one USB 2 port** (raspberrypi.com I/O-controllers docs). Unlike the Pi 4, the two black USB-A ports sit on different controllers and different root ports.
   - Jetson dev kits put the USB-A ports behind an onboard hub (inferred from NVIDIA forum threads; not verified).
   - Mac mini M1 and Mac Studio USB-A ports are on a separate PCIe xHCI. Asahi calls it ASMedia; the M1 Mac mini part is unverified. So on those Macs the USB-A pair is one controller. The report's "ASM3142 on M1 Max" refers to the Mac Studio desktop (forum source), not a laptop.
7. **Intel rate-matching-hub IDs:** 8087:0020 and 8087:0024 are incomplete. The 8-series and 9-series RMHs are 8087:8000, 8001, 8008 and 8009 (inferred from memory, check `usb.ids`).
8. **Add-in-card advice:** the cards that actually fix contention have one controller per port (for example 4-chip cards marketed as a dedicated channel per port). The report's last-resort "add a USB controller card with one controller per port" is right, but it should warn that common single-chip 4-port cards (Renesas uPD720201, ASMedia) give no benefit if the vendor pools (V1), or if the ports sit behind one root port.

### V5. Verdict on the design

The core idea holds:
- key HS domains from the USB 2.0 parent chain;
- learn real alts by readback;
- open with a stagger and admit a camera at its first frame;
- MF 0x800718CF and Linux ENOSPC are the certain signals.

Must change before implementation:
- AMD default (V1);
- load-accounting consistency (V2);
- ContainerId pairing (V4.1);
- the controller used for grouping USB 2.0 suggestions (V4.2);
- empty ports on internal hubs (V4.3).
