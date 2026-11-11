# USB topology and bandwidth domains on Windows (topic: topology_windows)

Written 2026-11-06 for the bandwidth-domain plan. Machine: Gerald (Windows 11 Home 10.0.26300, i7-14700K, ASUS board, SUBSYS 1043). The process ran at **Medium integrity, not elevated** (`whoami /groups` shows `Medium Mandatory Level`; `IsInRole(Administrator)` = False). No camera was opened or streamed.

Labels: **measured** (a repo result file, or a read-only command run on this machine, with the output path), **doc** (official docs or source), **web** (forums, vendor KBs, mailing lists), **inferred**.

Evidence produced for this report, all in [`topology_windows_run/`](topology_windows_run/):

| File | What it is |
| --- | --- |
| `win_usb_topology_20261106.json` + `_console.txt` | The existing tool `bandwidth/win_usb_topology.py --exclude 1532:0e05`. It sends GET_DESCRIPTOR through the hub to the three in-scope cameras. The faulty Kiyo was excluded, so no request reached it. |
| `win_topology_probe.py` | New probe for this report (stdlib + ctypes). It sends **no request to any device**: only CfgMgr reads, hub query IOCTLs answered from hub-driver state, and read-only host-controller `USBUSER` codes 1/2/5/6/8. An `assert` allow-list blocks CYCLE_PORT (273), RESET_HUB (275), the DIAG codes and every `USBUSER_OP_*` code. |
| `probe_20261106.json` + `_console.txt` | Probe output: controllers, every hub and **every port, empty ones included**, the camera interface → USB device mapping, present and phantom devnodes with decoded `_PLD`, and the list of ACPI tables. The whole probe took 0.24 s; the hub IOCTLs alone took 0.010 s. |
| `acpi_dsdt_check.txt` | Whether the ACPI DSDT and SSDTs can be read without admin, and where the USB `_PLD`/`_UPC` objects live. |
| `eventlog_check.txt` | Contents of the USBXHCI Operational and FrameServer event logs (read without admin). |

---

## 1. Short answer

- **Everything the topology mapper needs is readable without admin and without touching any device.** The controller list, root hubs, every port (connected or empty), negotiated speed, each port's protocols (USB 2 vs USB 3), the user-connectable and Type-C flags, the USB2↔USB3 companion port pairing, the hub type and multi-TT capability, and the open pipes of every device (which give the periodic bandwidth it currently holds) all come from documented user-mode hub IOCTLs. The mapping from an MF symbolic link or DirectShow device path to the USB device, hub and port is pure CfgMgr (**measured**, 0.24 s total, not elevated).
- **The bandwidth domain on this Intel PCH xHCI is the root port.** For a high-speed camera it is the HS root port its hub chain hangs from; for a SuperSpeed camera it is the SS root port. Every hub below a root port shares that root port's single link. Cameras on different root ports did not compete (REPORT finding 17, **measured**). This matches the xHCI design: the controller exposes available bandwidth **per root-hub port** through its Get Port Bandwidth command (**doc/web**). Windows does not expose that command to user mode (**inferred**: no IOCTL exists in the 10.0.22621 SDK).
- **On Gerald today, C922 and the generic camera share one domain**: PCH root port HS13. They are behind two Genesys USB2.1 hubs, which are the USB 2.0 half of a USB 3.2 dock/hub on the rear Thunderbolt USB-C port. The C930e is alone on HS07. The Kiyo Pro is a **SuperSpeed** device on the Thunderbolt xHCI, root port SS04 → hub port 4 (**measured**).
- **Thunderbolt USB-C ports split across two controllers.** Their USB 2.0 pins go to the PCH Intel xHCI (HS12 and HS13), and only their SuperSpeed lanes go to the Maple Ridge xHCI (8086:1138). A USB 2.0 camera in a "Thunderbolt port" therefore lands on the PCH controller. The companion-port IOCTL shows this directly (**measured**).
- **Free ports grouped by domain can be listed, but good human labels mostly cannot.** The `_PLD` data this ASUS BIOS supplies is generic: panel "top", position "upper-left", no color, `group_position` equal to the port number. The only useful label inputs are the controller friendly name, USB-C vs not, USB 3-capable vs USB 2-only, user-visible vs internal, and the root port ACPI name (HS05, SS01, ...). The most reliable labelling method is a **plug-in-to-identify** step: watch device arrival and tell the user which domain the port they just used belongs to (**inferred**, recommended).
- **The OS does not expose the controller's own reserved-bandwidth accounting usefully.** `USBUSER_GET_BANDWIDTH_INFORMATION` succeeds without admin on both xHCIs but returns identical constants: DeviceCount 0, AllocedIso 0, TotalBusBandwidth 448000, while the bus reports 15 and 5 devices (**measured**, idle). It looks unimplemented for USBXHCI; this needs one check while a camera streams. USB ETW needs admin (**measured**: the UAC prompt in `bw_etw/etw01`; **doc**). Per-device reservations **are** available: each device's currently open isochronous and interrupt pipes (wMaxPacketSize, mult, bInterval) come from `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX` without admin. An earlier run caught the C922 at alt 4 (640 B/µframe) this way (**measured**). Summing these per domain gives reserved bandwidth per domain.
- **Classifying a failure as bandwidth:**
  - MF fails at the first `ReadSample` with `0x800718CF` = HRESULT_FROM_WIN32(6351), "A camera interface doesn't have the desired bandwidth for data transfer". This is unambiguous (**measured**: FormatMessage and repo runs).
  - DirectShow through FFmpeg/PyAV loses the HRESULT. `IMediaControl_Run` failing becomes `AVERROR(EIO)` → `OSError(5)` with the log line "Could not run graph (sometimes caused by a device already in use...)" (**doc**: FFmpeg source). That is ambiguous: it needs a native DS check of the `Run` HRESULT, or a topology-plus-budget inference.
  - No event-log entry is written for a refusal: the USBXHCI Operational log has nothing newer than 2026-05-10, although the 10-27/28 runs logged dozens of refusals (**measured**).

---

## 2. What is on Gerald (measured, `probe_20261106.json`)

### 2.1 Controllers

| Controller | PCI | `USBUSER_GET_CONTROLLER_INFO_0` | Root hub (HighestPortNumber) | Notes |
| --- | --- | --- | --- | --- |
| Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft), 8086:7A60 rev 0x11 | PCI bus 0, dev 20, fn 0 = `PCIROOT(0)#PCI(1400)`, ACPI `\_SB.PC00.XHCI` | NumberOfRootPorts **16**, HcFeatureFlags 0x8 (TIME_SYNC_API) | `USB\ROOT_HUB30\4&2fd48294&0&0`, **25 ports** | Ports 1–16 are USB 2.0 (ACPI HS01–HS16) and ports 17–25 are USB 3 (SS01–SS09). NumberOfRootPorts=16 ≠ 25, so use the root hub's HighestPortNumber. |
| Intel(R) USB 3.10 eXtensible Host Controller - 1.10 (Microsoft), 8086:1138 (Thunderbolt 4 "Maple Ridge") | PCI bus 11 behind a PCIe switch on root port RP05: `PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)`, ACPI `...RP05.PXSX.TBDU.XHCI` | NumberOfRootPorts 2 | `USB\ROOT_HUB30\7&37b53fb&0&0`, **4 ports** | Ports 1–2 report USB 2.0 protocol but are **not connectable** (no USB2 wiring). Ports 3–4 are USB 3, Type-C, with companions PCH HS12 and HS13. |

### 2.2 Root ports and empty ports (PCH xHCI). uc = `PortIsUserConnectable`, TC = `PortConnectorIsTypeC`

| Port (ACPI) | Protocol | uc | TC | Companion | Connected now |
| --- | --- | --- | --- | --- | --- |
| 1 (HS01) | USB 2 | 1 | 0 | port 17 (SS01) | **empty** |
| 2 (HS02) | USB 2 | 1 | 0 | 18 (SS02) | **empty** |
| 3 (HS03) | USB 2 | 1 | 0 | 19 | DYMO LabelWriter (FS, bulk) |
| 4 (HS04) | USB 2 | 1 | 0 | 20 (SS04) | **empty** |
| 5 (HS05) | USB 2 | 1 | 0 | 21 | **empty** |
| 6 (HS06) | USB 2 | 1 | 0 | 22 | **empty** |
| 7 (HS07) | USB 2 | 1 | 0 | 23 | **Logitech C930e** (HS) |
| 8 (HS08) | USB 2 | 1 | 0 | 24 | Microsoft 2.4 GHz transceiver (FS) |
| 9 (HS09) | USB 2 | 1 | **1** | 25 (SS09, TC) | **empty** (USB-C) |
| 10 (HS10) | USB 2 | 0 | 0 | none | internal Genesys 05e3:0608 4-port hub, all 4 ports user-connectable and **empty** (probably a front-panel header; **inferred**) |
| 11 (HS11) | USB 2 | 0 | 0 | none | ASUS AURA LED controller (internal) |
| 12 (HS12) | USB 2 | 1 | **1** | **TB xHCI port 3** | **empty** (Thunderbolt USB-C #1) |
| 13 (HS13) | USB 2 | 1 | **1** | **TB xHCI port 4** | Genesys USB2.1 hub 05e3:0610 = USB2 half of the dock → see 2.3 |
| 14 (HS14) | USB 2 | 0 | 0 | none | Intel Bluetooth 8087:0033 (iso pipes open at 0 bytes) |
| 15, 16 | USB 2 | 1 | 0 | none | **empty** (USB 2.0-only) |
| 17–24 (SS01–SS08) | USB 3 | 1 | 0 | HS01–HS08 | all **empty** |
| 25 (SS09) | USB 3 | 1 | 1 | HS09 | **empty** |

The SS port numbering (17 = SS01) is confirmed by a phantom devnode: hub 05e3:0626 at PCH port 20 has the location path `ACPI(...RHUB)#ACPI(SS04)`.

### 2.3 The dock on the rear Thunderbolt USB-C port (HS13 + TB SS04)

```
PCH xHCI  HS13 ── 05e3:0610 "USB2.1 Hub" (USB2 half of 05e3:0625 USB3.2 hub; multi-TT)
                   ├─ p1 ── 05e3:0610 "USB2.1 Hub" (USB2 half of 05e3:0626)
                   │         ├─ p1 empty   ├─ p2 USB Camera 4C4A:4A55 (HS)   ├─ p3 empty   └─ p4 C922 (HS, sn C922SN01)
                   ├─ p2 ── PreSonus Revelator IO 24 194f:0422 (HS, 4 bulk pipes now)
                   ├─ p3 ── Microchip 0424:2137 7-port hub (USB2 half of 0424:5537)
                   │         ├─ p2 Logitech receiver   ├─ p5 Dell U2717D hub controller (internal)   └─ p1,p3,p4 empty (p6,p7 internal)
                   └─ p4 empty
TB xHCI   SS04 ── 05e3:0625 "USB3.2 Hub" (SS)
                   ├─ p1 05e3:0626 (SS) ─ 4 empty SS ports
                   ├─ p3 0424:5537 (SS) ─ empty SS ports
                   └─ p4 Razer Kiyo Pro 1532:0E05 (SuperSpeed: V2 flag op_ss=1; the legacy Speed field says "high")
TB xHCI   SS03     empty (companion HS12)
```

Bandwidth domains now: **HS13** = {C922, generic camera, Revelator, receiver, monitor hub}; **HS07** = {C930e}; **TB-SS04** = {Kiyo}. The free ports in *other* HS domains are HS01, 02, 04, 05, 06, 09 (C), 12 (C), 15, 16, plus HS10's internal hub (one domain with 4 ports).

### 2.4 Camera interface → device → port (pure CfgMgr, nothing opened)

| MF symbolic link (KSCATEGORY_VIDEO_CAMERA) / DS path (KSCATEGORY_VIDEO) | USB device instance | LocationPaths[0] → port key path | ACPI path |
| --- | --- | --- | --- |
| `\\?\USB#VID_046D&PID_085C&MI_00#8&268DA596&0&0000#{e5323777-...}\GLOBAL` | `USB\VID_046D&PID_085C\C922SN01` (serial) | `PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.4` | `...RHUB#ACPI(HS13)#USB(1)#USB(4)` |
| `\\?\USB#VID_4C4A&PID_4A55&MI_00#8&232e60d4&0&0000#...` | `USB\VID_4C4A&PID_4A55\7&7DCC7CE&0&2` | `.../USBROOT(0)/13.1.2` | `...HS13#USB(1)#USB(2)` |
| `\\?\USB#VID_046D&PID_0843&MI_00#6&2206973F&0&0000#...` | `USB\VID_046D&PID_0843\5&CC3F949&0&7` | `.../USBROOT(0)/7` | `...ACPI(HS07)` |
| `\\?\USB#VID_1532&PID_0E05&MI_00#A&34494D13&0&0000#...` | `USB\VID_1532&PID_0E05\9&3A0ECB01&0&4` | `PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | `...TBDU#ACPI(XHCI)#ACPI(RHUB)#ACPI(SS04)#USB(4)` |
| `\\?\ROOT#MEDIA#0002#...\VidSource0..3` | `ROOT\MEDIA\0002` | none (virtual camera, not USB) | – |

The mapping is: interface path → `CM_Get_Device_Interface_PropertyW(DEVPKEY_Device_InstanceId)` → `CM_Locate_DevNodeW` → for an `&MI_xx` function, `CM_Get_Parent` gives the composite USB device → `CM_Get_Parent` again gives the hub; the port is `DEVPKEY_Device_Address`. The hub's `GUID_DEVINTERFACE_USB_HUB` path is the handle for the IOCTLs. Non-USB enumerators (ROOT\MEDIA, NVIDIA Broadcast, OBS) must be excluded. MF listed 8 sources and DS 15 on this machine (repo `docs/capture_backends_review.md`).

---

## 3. API recipe (ordered), data model, admin needs

### 3.1 Calls, in order (all measured working at Medium integrity unless noted)

1. **Controllers.** `CM_Get_Device_Interface_ListW(GUID_DEVINTERFACE_USB_HOST_CONTROLLER {3abf6f2d-71c4-462a-8a92-1e6861e6af27})`. For each: devnode properties `FriendlyName` ("Intel(R) USB 3.20 eXtensible Host Controller ..."), `LocationInfo` ("PCI bus 0, device 20, function 0"), `LocationPaths` (PCI and ACPI forms), PCI VEN/DEV from the instance ID, and parent ("PCI Express Downstream Switch Port" reveals a Thunderbolt or add-in path). Then `CreateFileW(GENERIC_WRITE)` on the interface and:
   - `IOCTL_USB_GET_ROOT_HUB_NAME` (HCD fn 258) → root hub symbolic name;
   - `IOCTL_USB_USER_REQUEST` (HCD fn 270) with **only** `USBUSER_GET_CONTROLLER_INFO_0` (1), optionally `GET_BANDWIDTH_INFORMATION` (5), `GET_BUS_STATISTICS_0` (6) and `GET_USB_DRIVER_VERSION` (8). Never use `USBUSER_OP_*` (0x1xxxxxxx/0x2xxxxxxx: send packet, raw reset, root-port feature). usbuser.h is `#pragma pack(1)` (**doc**: SDK 10.0.22621 `um/usbuser.h` line 38).
2. **Hubs.** `CM_Get_Device_Interface_ListW(GUID_DEVINTERFACE_USB_HUB)`. Open each with `GENERIC_WRITE`, `FILE_SHARE_READ|WRITE` (usbview does the same; **doc**: Windows-driver-samples `usb/usbview/enum.c`). Then:
   - `IOCTL_USB_GET_NODE_INFORMATION` (258): hub descriptor, `bNumberOfPorts`, `wHubCharacteristics`;
   - `IOCTL_USB_GET_HUB_INFORMATION_EX` (277): `HubType` (Root/Usb20/Usb30) and `HighestPortNumber`, which is the port loop bound (**doc**: the port connector IOCTL page says ConnectionIndex ranges up to it);
   - `IOCTL_USB_GET_HUB_CAPABILITIES_EX` (276): `HubIsHighSpeed`, `HubIsMultiTt`, `HubIsRoot`. Multi-TT matters only for FS/LS devices behind a HS hub.
3. **Per port, 1..HighestPortNumber, connected or not:**
   - `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX` (274): `ConnectionStatus` (NoDeviceConnected → empty port; also DeviceNotEnoughBandwidth / DeviceFailedEnumeration), the legacy `Speed`, `DeviceIsHub`, the cached device descriptor (VID/PID/bcdUSB/iSerial index), and the **open pipes** with `wMaxPacketSize` and `bInterval` (the current periodic reservation);
   - `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX_V2` (279), input `Length=16`, `SupportedUsbProtocols=7`: the **port's** protocols (USB 1.1/2.0 vs USB 3 → tells an HS port from an SS port even when empty) and the flags `DeviceIsOperatingAtSuperSpeedOrHigher` / `...SuperSpeedPlus...`. The legacy Speed field reports "high" for SS devices (Kiyo here), so V2 decides SS vs HS (**measured**; also noted in `win_usb_topology.py`). SS+ is only a flag; Gen 2 vs Gen 2x2 and lane count are not in the public SDK (**doc**: usbioctl.h 10.0.22621 lines 1739–1750);
   - `IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES` (278), two-call pattern (first call returns `ActualLength`): `PortIsUserConnectable`, `PortConnectorIsTypeC`, `PortIsDebugCapable`, `PortHasMultipleCompanions`, `CompanionPortNumber`, `CompanionHubSymbolicLinkName`. Loop `CompanionIndex` when multiple companions are flagged (**doc**: Microsoft Learn page for the IOCTL, Windows 8+, "user-mode I/O control request" targeting `GUID_DEVINTERFACE_USB_HUB`);
   - `IOCTL_USB_GET_NODE_CONNECTION_ATTRIBUTES` (272): `PortAttributes` was 0x0 on every port here, so it adds nothing;
   - for connected ports, `IOCTL_USB_GET_NODE_CONNECTION_DRIVERKEY_NAME` (264), which matches the device's `SPDRP_DRIVER` / `DEVPKEY_Device_Driver` to give the devnode, and `IOCTL_USB_GET_NODE_CONNECTION_NAME` (261) for child hubs.
4. **Devices and cameras.** `CM_Get_Device_ID_ListW("USB")` with `CM_Locate_DevNodeW` for properties: `LocationPaths` (`PCIROOT(..)#PCI(..)#USBROOT(n)#USB(p)...` plus the ACPI form `ACPI(_SB_)#...#ACPI(RHUB)#ACPI(HS13)#USB(1)#USB(4)`), `Address` (= port), `BusReportedDeviceDesc` (the product string with no device I/O), `PhysicalDeviceLocation` (the raw `_PLD` buffer), and `ContainerId`. Camera interfaces are listed per KSCATEGORY as in 2.4. The key comes from `naming/camera_identity.py`: a usable serial, else `LocationPaths[0]` split at `USBROOT(n)`.
5. **Optional label sources:** phantom devnodes (`CM_LOCATE_DEVNODE_PHANTOM`) for past `_PLD` and location data of now-empty ports; ACPI tables (section 5).

Do **not** call `IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION` during routine mapping. It sends a real control request to the device: usbview and `win_usb_topology.py` do it, and the Kiyo stops answering control requests after a few minutes (REPORT "Kiyo"). Everything needed for domains comes from cached hub state. The cameras' alt-setting table, which gives each camera's max-alt cost, can be read once per camera and cached by key, or from the OS-cached configuration descriptor (open question 4).

### 3.2 Data model (proposed)

```
Controller { id: PCI instance id, pci_vid_did, friendly_name, location_info, acpi_path, is_thunderbolt_or_downstream_switch: bool,
             root_hub_id, quirk_domain: "root_port" | "controller" | "unknown"  (from a vendor table + learned failures) }
Hub        { id, interface_path, controller_id, parent_port_ref, hub_type: root|usb20|usb30, highest_port, multi_tt,
             companion_hub_id (the other half of a USB3 hub), upstream_speed }
Port       { hub_id, number, acpi_name ("HS05"/"SS01"/None), protocols: {usb2, usb3}, user_connectable, type_c,
             companion: (hub_id, port), connected_device_id | None, pld: decoded _PLD | None (+ source: live | phantom),
             hs_domain_id, ss_domain_id }
Device     { instance_id, vid, pid, serial (devnode/instance), bus_desc, speed: LS|FS|HS|SS|SS+, port_ref, location_paths,
             open_pipes: [{ep, type, bytes_per_interval, interval_us}], reserved_hs_ns_per_uframe (computed),
             is_camera, camera_key, mf_links[], ds_paths[], max_alt_cost (from cached descriptor) }
Domain     { id: (controller_id, "HS"|"SS", root_port_number) or controller_id when quirk_domain=="controller",
             speed_class, budget_ns_per_uframe (HS: 100 000 ns = 80% of 125 µs), reserved_now, members[device], free_ports[] }
```

### 3.3 Admin needs (summary)

| Item | Admin? | Evidence |
| --- | --- | --- |
| CfgMgr properties, interface lists, phantom devnodes | No | **measured** (`probe_20261106.json`, elevated=false) |
| Hub IOCTLs 258/261/264/272/274/276/277/278/279 | No | **measured**; **doc** (user-mode IOCTLs) |
| HCD `IOCTL_USB_GET_ROOT_HUB_NAME`, `USBUSER` codes 1/5/6/8 | No | **measured** |
| ACPI DSDT (`GetSystemFirmwareTable`) and all SSDTs (`HKLM\HARDWARE\ACPI\SSD1..SSDC`) | No | **measured** (`acpi_dsdt_check.txt`) |
| USB ETW (`logman -ets` with USBXHCI/UCX/USBHUB3) | **Yes** (or Performance Log Users) | **measured** (`results/windows/Gerald/bw_etw/etw01/console_output.txt`: UAC requested and cancelled); **doc** (Microsoft Learn "How to capture a USB event trace") |
| Reading the USBXHCI Operational / FrameServer event logs | No | **measured** (`eventlog_check.txt`) |

Caveat: the user on Gerald is an Administrators-group member running a UAC-filtered (Medium) token. A real standard-user account has not been tested (recommended test T6).

---

## 4. Bandwidth domains

### 4.1 Rule (Intel xHCI, measured basis)

- **HS/FS/LS camera** → domain = (controller, **HS root port** at the top of its USB 2.0 hub chain). Every hub between the camera and the root port, including the USB 2.0 half of a USB 3 hub, forwards everything over that one 480 Mb/s root-port link. Budget: 80% of each 125 µs microframe = 100 µs of HS isochronous/interrupt time (USB 2.0 §5.6.4 and §5.11.3). This model predicted 26/26 shared-hub outcomes (`bandwidth/hs_budget_model.py`, `results/windows/Gerald/bw_budget_model/model_vs_observed.json`, **measured**).
- **FS/LS camera behind a HS hub** → also a TT sub-domain: the whole hub if single-TT, per port if multi-TT (`HubIsMultiTt`). This is rare for cameras.
- **SS/SS+ camera** → domain = (controller, **SS root port**). It does not compete with HS devices, even those on the same physical USB-C/A connector (the companion HS port is a separate link).
- **Different root ports of the same Intel PCH xHCI did not compete** (REPORT finding 17 and `bw_concurrency_rerun_20261027/r08_cross_rootport_no_kiyo.json`: C922 1080p MJPEG at alt 11 with C930e 1080p at alt 11 on different root ports both streamed at 29.95–30.0 fps, **measured**).
- The xHCI architecture backs this up. The xHCI 1.2 Get Port Bandwidth command (§4.6.15, context §6.2.6) returns available bandwidth as a **percentage per root-hub port**, per speed. Linux added a debugfs reader for it in 2025 (`/sys/kernel/debug/usb/xhci/<pci>/port_bandwidth/{SS,HS,FS}_BW`, sample "port[5] available bw: 90%"; **web**: LKML "[RESEND PATCH V6] usb:xhci: Add debugfs support for xHCI port bandwidth", 2025-04, tested on an AMD controller). Windows has no user-mode equivalent (**inferred**).
- Controller-wide limits still exist on top of per-port bandwidth. The best known is a cap on endpoints/device contexts ("Not enough USB controller resources"; 96 endpoints is the figure quoted for Intel, ~254 for AMD; **web**: Plugable KB, Intel community thread, not confirmed by Intel or Microsoft). A UVC camera uses 2–4 endpoints (plus audio), so this is unlikely to bind for <10 cameras, but the message logic should know it exists.

### 4.2 By controller type

| Controller | Domain expectation | Evidence |
| --- | --- | --- |
| Intel PCH xHCI (8086:7A60 here) | Per root port | **measured** (finding 17, r08) |
| Intel Thunderbolt 4 xHCI (8086:1138) | SS only; its USB2 side is on the PCH, so HS domain = PCH HS12/HS13 | **measured** (companion IOCTL; ports 1–2 not connectable) |
| USB4 / TB4 docks (USB3 tunneled to the host xHCI, USB2 over the host port's D+/D-) | All HS devices in the dock share **one** host HS root port | **measured** for this dock (all dock HS hubs under HS13); **web** (MacRumors on USB tunneling) |
| TB3 docks / TB3 hosts with a dock that has its own PCIe xHCI | A **new controller** appears (a PCI device behind a "Downstream Switch Port") and the dock's ports are its root ports | **web** (MacRumors forum), **inferred**; detectable from the controller's parent chain |
| AMD (CPU xHCI, Promontory/ASMedia chipset xHCI), ASMedia, VIA (VL805 etc.), Renesas uPD72020x add-in cards | Unknown on Windows. Admission is done by controller firmware, not the OS (**web**: linux-usb maintainer quote in "xHCI bandwidth error with USB webcam" thread). Some boards and cards put an internal USB2 hub in front of all ports (e.g. VL805-based designs), which the topology walk sees as a hub (**inferred**) | needs hardware (test T7) |
| Apple Silicon / T2 | Not Windows; out of scope (Boot Camp on T2 Macs uses Apple's controller, untested) | – |

Design consequence: compute domains with the per-root-port rule, but keep a **per-controller (PCI VID:DID) quirk table** with `domain = root_port | controller`. Update it locally when two cameras in *different* computed domains fail together with a bandwidth code (learned evidence), and ship known entries as they are measured.

### 4.3 Reserved bandwidth (item e)

- **Per device: yes, without admin.** The open pipes from `IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX` are the endpoints of the currently selected alt settings, with `wMaxPacketSize` (base + mult) and `bInterval`. Example: `results/windows/Gerald/bw_concurrency_rerun_20261027/r02_c922_alt_by_mode.json` caught the C922 streaming with iso EP 0x81, wMaxPacketSize 0x0280, matched to alt 4 = 640 B/µframe (**measured**). Each pipe converts to HS ns/µframe with `t_iso_in_ns()` from `hs_budget_model.py`; summing over the domain's devices gives the domain's load. Idle devices hold only interrupt pipes (e.g. 64 B every 2^(8-1) µframes for Logitech status endpoints).
- **Per controller: not usefully.** `USBUSER_GET_BANDWIDTH_INFORMATION` returned status Success, DeviceCount 0, TotalBusBandwidth 448000, Total32secBandwidth 14336000, AllocedBulkAndControl 2867200, AllocedIso 0 on *both* controllers, while `GET_BUS_STATISTICS_0` reported DeviceCount 15 and 5 with all byte counters 0 (**measured**, idle). Microsoft's page still tells users to read allocated bandwidth from the controller's Device Manager *Advanced* tab (**doc**: "USB Bandwidth Allocation", ms.date 2024-01-17). That tab belongs to the USB 2.0 port driver; on USBXHCI the values look like static placeholders (**inferred**; test T2).
- **ETW:** the USBXHCI/UCX/USBHUB3 providers log endpoint configuration, but capturing them needs an elevated session (3.3), so they are not usable in the library.
- **Event logs:** `Microsoft-Windows-USB-USBXHCI-Operational` holds 6 events, the newest from 2026-05-10 (TB controller errors), and none from the 10-27/28 refusal runs. So refusals are not logged there (**measured**). The FrameServer log only covers 2026-11-04 → 11-06, so it cannot answer the question (`eventlog_check.txt`).

---

## 5. Human labels for free ports (item d)

What exists and what it is worth on this board (**measured**):

- **`_PLD` (`DEVPKEY_Device_PhysicalDeviceLocation`)** exists only on devnodes attached directly to an ACPI-described root port (HS03, HS07, HS08, HS10, HS11, HS13, HS14, TB SS04). Its content is generic: panel = "top", vertical "upper", horizontal "left", color ignored, and `group_position` = the port number. HS13 and TB SS04 carry `group_position` 19 and shape 1, HS12 carries 18 and shape 1, so **companion ports share group_position** (consistent with Microsoft's guidance that USB ports need both `_UPC` and `_PLD`; **doc**: "Using ACPI to Configure USB Ports on a Computer"). Panel and position cannot be used to say "rear panel" on this BIOS.
- **Stale `_PLD` pitfall:** devices with a serial keep one devnode across ports, and their `_PLD` property is **not refreshed** when moved to a port without `_PLD`. The C922 (at HS13.1.4 now) still carries group_position 1 from when it sat on HS01 (`results/windows/Gerald/naming/identity_dump.json`, cameras[1] = root port 1). The Revelator carries 6. Only trust `_PLD` on a device whose `LocationPaths` ends at an `ACPI(HSnn|SSnn)` element.
- **Phantom devnodes** (47 here) keep the last location and `_PLD` of devices once plugged in. They label some empty ports (HS01, HS02, HS04, PCH SS04 ...) and show board-specific ACPI children such as `HS10#ACPI(PRT3)`.
- **ACPI tables are readable without admin:** DSDT 572 KB via `GetSystemFirmwareTable`, and every SSDT under `HKLM\HARDWARE\ACPI\SSD1..SSDC`. `GetSystemFirmwareTable` returns only the first SSDT. The USB port objects sit in SSDT `INTEL xh_rps14` (30 `_PLD`, 30 `_UPC`) as **methods** (`GPLD`/`GUPC` calls), and in `TbtTypeC`/`UsbCTabl`. Extracting per-port values needs an AML interpreter, and the values are the same generic ones. Not worth it (**measured** + **inferred**).
- **Usable label parts:** controller friendly name and PCI location; "USB-C" (TC flag); "USB 3 port" (has an SS companion) vs "USB 2.0-only port"; internal vs user-visible; root port ACPI name; for hub ports, "port N of the hub that <device name> is also plugged into" (BusReportedDeviceDesc of a sibling); for docks, the dock hub's product string ("USB3.2 Hub", "USB5537B").
- **Recommended UX: plug-in-to-identify.** skellycam registers `CM_Register_Notification` for `GUID_DEVINTERFACE_USB_DEVICE` arrivals. It asks the user to move the camera, then confirms "that port is on a separate bandwidth group ✓" or "that port still shares bandwidth with <camera>". This replaces labels that cannot be trusted with direct feedback (**inferred**).

Example message for Gerald's current layout, if C922 and the generic camera fail together:

> "C922 Pro Stream Webcam (serial C922SN01) and USB Camera 4C4A:4A55 (port …/13.1.2) share bandwidth: both connect through the same USB 2.0 link (root port HS13 of the Intel(R) USB 3.20 eXtensible Host Controller, via the USB hub on your rear Thunderbolt USB-C port), and I encountered an error when attempting to open them both at the same time. Suggest moving one of those cameras to any of the following controller ports: Intel USB 3.20 controller – any empty USB 3 Type-A port (HS01/SS01, HS02/SS02, HS04/SS04, HS05/SS05, HS06/SS06), the USB-C port HS09/SS09, the other Thunderbolt USB-C port (HS12), the USB 2.0 ports HS15/HS16, or the internal USB 2.0 hub on HS10 (4 free ports). Do not use other ports on the same dock/hub, and avoid HS07, which already carries the C930e."

---

## 6. Free-port suggestion algorithm

1. Build the tree (section 3). Assign every port an `hs_domain` and an `ss_domain`: the controller plus the root port reached by walking up `parent_port`. For a USB 3 hub, the USB2 half and the SS half are separate hubs, linked by companion info.
2. For the failing camera C (speed class S, max-alt cost `cost_C` from its cached descriptor; usbvideo always picks the largest alt the mode allows, REPORT finding 16): candidate ports are those that are `user_connectable`, empty, of protocol S (an HS camera fits any USB2-capable port, including the HS half of a USB 3 or Type-C port), and whose domain ≠ the failing domain and has `reserved_now + planned(other cameras the session will open in that domain) + cost_C ≤ budget`.
3. Rank: an empty domain first (a whole root port to itself), then domains with headroom. Root ports before hub ports. Avoid domains that contain audio interfaces or other isochronous devices (they may reserve on demand; REPORT finding 17's audio window).
4. If the controller's quirk entry says `controller`, exclude the whole controller and suggest a different controller. If no other controller exists, say so and suggest a lower resolution or frame rate (alt cost table) or a PCIe USB card.
5. Group candidates by controller → by label (USB-C / USB 3 Type-A / USB 2-only / internal hub) for the message.

Failure classification feeding step 2:

| Path | Bandwidth signature | Confidence |
| --- | --- | --- |
| MF Source Reader | `ReadSample` (first) → `0x800718CF` (Win32 6351 "A camera interface doesn't have the desired bandwidth for data transfer"). Activate, reader creation and `SetCurrentMediaType` succeed first (26–71 ms) | **measured** (repo runs; FormatMessage) |
| DirectShow native | `IMediaControl::Run` HRESULT, probably the same code (unverified) | test T3 |
| DirectShow via FFmpeg/PyAV | `OSError(5)` = `AVERROR(EIO)` with log "Could not run graph (sometimes caused by a device already in use by other application)": the HRESULT is discarded | **doc** (FFmpeg `libavdevice/dshow.c` master, ~line 1818–1826) + **measured** (repo) |
| Any | After a refusal, the next start can deliver 0 frames, and MF can briefly not find the device (`DeviceNotFound`). Retry once after ~0.5–1 s before declaring failure | **measured** (REPORT finding 19, RERUN_20261027) |
| Not bandwidth | `0x8007001F` (device not functioning, the Kiyo fault), `0xC00D7167` MF_E_REBOOT_REQUIRED, `0x800700AA` in use, device removed | **measured** (repo) |

When the error is ambiguous (DS EIO), classify it as "probably bandwidth" only if the topology puts the camera in a domain whose computed load plus its cost exceeds the budget.

---

## 7. Pitfalls

- The legacy `Speed` field cannot say SuperSpeed; use the V2 flags (**measured**: the Kiyo shows "high" + op_ss).
- `USB_CONTROLLER_INFO_0.NumberOfRootPorts` (16) ≠ root hub ports (25) on the Intel PCH; loop over `HighestPortNumber`.
- A "Thunderbolt port" is two controllers. A USB2 camera's port path is on the PCH (`PCI(1400)/13...`); a USB3 camera in the same connector is on the TB xHCI path. Its port key changes if the camera's speed changes.
- Serial-keyed devnodes keep a stale `_PLD` (section 5).
- `IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION`, usbview, and libusb enumeration all send requests to devices. Keep routine mapping on cached hub state.
- Virtual cameras (ROOT\MEDIA, OBS, NVIDIA Broadcast) have no USB topology; skip them.
- The topology snapshot is a moment in time. Re-map on `CM_Register_Notification` arrival/removal before suggesting ports.
- Hub-internal ports (`user_connectable=0`, e.g. 0424:2137 ports 5–7, root ports 10/11/14) must never be suggested.
- Load from non-camera periodic devices (audio interfaces, headsets) only shows up while they stream. A domain that looks empty can fill later.

---

## 8. Recommended tests

| ID | Test | Decides | Human? |
| --- | --- | --- | --- |
| T1 | Run `win_topology_probe.py` (or a pipes-only variant) while 1–2 cameras stream under camlock, on the same and on different domains | That open-pipe sums per domain match the alt each camera got, and that the reserved-bandwidth computation works live | No |
| T2 | Same as T1, also reading `USBUSER_GET_BANDWIDTH_INFORMATION`/`BUS_STATISTICS_0` before, during and after streaming | Whether USBXHCI's controller-level bandwidth numbers are static (unusable) or live | No |
| T3 | Native DirectShow graph (C++ or comtypes) on a bandwidth-refused camera; log the `IMediaControl::Run` HRESULT and `IAMStreamConfig` results | Whether DS has an unambiguous bandwidth code (and which) | No (uses the existing shared-hub pair: move C930e back next to the generic camera, or use C922 + generic on HS13 now) |
| T4 | C922 + generic (both on HS13 now) opened together at 720p MJPEG under MF and DS | Confirms the current placement reproduces the refusal and exercises the message generator end-to-end | No |
| T5 | Move one camera to a suggested port (HS05 or HS12) and repeat T4; also try a camera in HS12 (TB USB-C #1) vs HS13 (TB USB-C #2 with the dock) | That suggestions are correct, including the claim that the two Thunderbolt USB-C ports are separate HS domains | **Yes** (replug) |
| T6 | Run the probe from a true standard-user (non-admin) account | No-admin claim beyond a UAC-filtered admin token | Yes (log in) |
| T7 | Same shared/separate root-port pair tests on an AMD chipset, an ASMedia/VIA/Renesas PCIe card, and a TB3 dock with its own xHCI | The per-vendor domain rule (root port vs controller) for the quirk table | Yes (other hardware) |
| T8 | 3+ cameras on separate PCH root ports at max alt | That a controller-wide limit does not appear before per-port limits on Intel | No |
| T9 | Plug-in-to-identify prototype: register for arrivals, ask the user to move a camera, report the domain | Whether the UX can stand in for missing `_PLD` labels | Yes |

## 9. Open questions

1. Is `0x800718CF` also what native DirectShow / KS returns at pin `RUN`, and does WinRT MediaCapture surface the same HRESULT?
2. On AMD and ASMedia/Renesas/VIA xHCIs, do different root ports share a hidden HS budget? Do any of them expose a rate-matching hub that does not enumerate?
3. Does the USBXHCI controller return live `AllocedIso` in `USBUSER_GET_BANDWIDTH_INFORMATION` while something streams?
4. Can a camera's full configuration descriptor (for max-alt cost) be read from OS-cached state without a device request? Candidates are KS property sets on the function and a per-device registry cache. Otherwise read it once with the descriptor IOCTL and cache it by camera key.
5. Do USB4 v2 / Thunderbolt 5 hosts route USB2 on their Type-C ports the same way (to the PCH), and how do USB4 docks present their USB2 hub tree?
6. Does a standard (non-admin) user get the same hub-interface access (device object ACL) as a filtered admin?

## Sources

- Repo: `REPORT.md` findings 16–19, 22–24; `bandwidth/win_usb_topology.py`; `bandwidth/hs_budget_model.py`; `naming/camera_identity.py`, `naming/win_identity_dump.py`; `results/windows/Gerald/bw_topology_rerun_20261027/*.json`, `bw_concurrency_rerun_20261027/r02_*.json`, `r08_*.json`, `bw_etw/etw01/console_output.txt`, `naming/identity_dump.json`, `RERUN_20261027.md`; `docs/capture_backends_review.md`.
- [IOCTL_USB_GET_PORT_CONNECTOR_PROPERTIES](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbioctl/ni-usbioctl-ioctl_usb_get_port_connector_properties) (Microsoft Learn, updated 2024-02-22).
- [Using ACPI to Configure USB Ports on a Computer](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/using-acpi-to-configure-usb-ports-on-a-computer) (Microsoft Learn, updated 2025-03-25).
- [USB Bandwidth Allocation](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/usb-bandwidth-allocation) (Microsoft Learn, ms.date 2024-01-17).
- [How to capture a USB event trace](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/how-to-capture-a-usb-event-trace) (Microsoft Learn).
- Windows SDK 10.0.22621: `shared/usbioctl.h`, `shared/usbiodef.h`, `um/usbuser.h`, `shared/usb.h` (local copies on Gerald).
- [usbview source](https://github.com/microsoft/Windows-driver-samples/tree/main/usb/usbview) (`enum.c`: hub IOCTLs, `USBUSER_GET_CONTROLLER_INFO_0`/`POWER_STATE_MAP`; no bandwidth query; sends GET_DESCRIPTOR to every device).
- [FFmpeg libavdevice/dshow.c](https://github.com/FFmpeg/FFmpeg/blob/master/libavdevice/dshow.c) ("Could not run graph" → `AVERROR(EIO)`).
- [LKML: usb:xhci: Add debugfs support for xHCI port bandwidth (V6, 2025-04)](https://lkml.iu.edu/hypermail/linux/kernel/2504.0/01523.html) (xHCI 1.2 §4.6.15 Get Port Bandwidth, per root port).
- [linux-usb: xHCI bandwidth error with USB webcam](https://linux-usb.vger.kernel.narkive.com/UkyWZrdj/xhci-bandwidth-error-with-usb-webcam) (admission is done by the xHCI hardware, not the driver).
- [Plugable KB: Not Enough USB Controller Resources](https://kb.plugable.com/en_US/not-enough-usb-controller-resources-error); [Intel community: hardware limitations on USB endpoints (xHCI)](https://community.intel.com/t5/Embedded-Intel-Core-Processors/Hardware-limitations-on-USB-endpoints-XHCI/m-p/264577).
- [MacRumors forum on USB tunneling vs a dock's xHCI](https://forums.macrumors.com/threads/owcs-upcoming-thunderbolt-hub-adds-more-thunderbolt-3-ports-to-your-mac.2270255/page-7).


---

## Verifier notes

Adversarial verifier, 2026-11-06, same machine (Gerald), Medium integrity. No camera was opened or streamed, and no device IOCTL was sent. Everything below comes from re-reading the gatherer's output files, from read-only commands (`whoami /groups`, `Get-PnpDevice -PresentOnly`, `[ComponentModel.Win32Exception]::new(6351)`), from reading the SDK headers and local source checkouts, and from fetching web pages.

### Verdicts on the claims

| ID | Verdict | Evidence and correction |
| --- | --- | --- |
| C1 | confirmed | `probe_20261106.json`: `elevated=false`, `t_hubs_s=0.0099`, `t_total_s=0.2405`. `whoami /groups` shows `Medium Mandatory Level`. **Caveat:** the token also holds `BUILTIN\Performance Log Users` (S-1-5-32-559) and is a filtered admin token. A true standard user has still not been tested (T6). |
| C2 | weakened | The allow-list in `win_topology_probe.py` (line 193: `{258,261,264,265,270,272,274,276,277,278,279}`, plus USBUSER codes 1,2,5,6,7,8) proves that no descriptor, cycle or reset IOCTL was *issued*. It does not show that the bus stayed silent: nobody ran ETW or a USB analyzer. That hub IOCTLs 274/279/278 are answered from cache is **inferred**. That opening a hub handle never wakes a selectively suspended hub is also unverified. |
| C3 | confirmed | `controllers[]`: 8086:7A60 at `PCIROOT(0)#PCI(1400)`, 25-port root hub; 8086:1138 at bus 11, parent "PCI Express Downstream Switch Port", 4-port root hub. |
| C4 | confirmed, plus a pattern | NumberOfRootPorts is 16 against 25 ports on the PCH, and **2 against 4 on the TB xHCI**. In both cases it equals the number of USB2-protocol root ports. The pitfall stands (loop to HighestPortNumber); the pattern is **inferred**. |
| C5 | confirmed | PCH port 12 → companion TB `ROOT_HUB30#7&37b53fb` port 3; port 13 → port 4. TB ports 1-2 are `user_connectable=False`. |
| C6 | confirmed | Re-read `win_usb_topology_20261106_console.txt` and the `camera_paths[]` / hub port tables. |
| C7 | confirmed | 05e3:0625 port 4 and TB root port 4 show `legacy_speed=high` with `op_ss`. **Missed:** TB root port 4 (the hub's upstream link) also shows `op_ssp`, so it runs at SuperSpeedPlus. The probe already exposes SS vs SS+ per link. |
| C8 | confirmed | SDK 10.0.22621 `usbioctl.h` lines 1739-1750: only the four flags. `IOCTL_USB_GET_TRANSPORT_CHARACTERISTICS` (fn 281, `MaxPotentialBandwidth`) exists but is a **client-driver (kernel) request** (Microsoft Learn: "The client driver sends this request"; it sits outside the `#ifndef USB_KERNEL_IOCTL` user block). It is not a user-mode way to get the link rate. |
| C9 | confirmed | Empty ports report `port_protocols` (e.g. PCH 17-25 `usb3`, 1-16 `usb1.1,usb2.0`). |
| C10 | confirmed | Microsoft Learn page (updated 2024-02-22): "is a user-mode I/O control request… targets… GUID_DEVINTERFACE_USB_HUB". ConnectionIndex goes from 1 to the HighestPortNumber of IOCTL_USB_GET_HUB_INFORMATION_EX. Loop on CompanionIndex until CompanionPortNumber is 0 and the name is NULL. Minimum version Windows 8. |
| C11 | confirmed | 0610 (`5&cc3f949&0&13`) ports 1-4 ↔ 0625 ports 1-4; 0610 (`6&f6f0942&0&1`) ↔ 0626; 2137 ports 1-4 ↔ 5537. **Extra signal:** the USB2-half hubs show `ss_capable` on their *upstream* port (PCH p13; 0610 p1/p3), which flags "USB2 half of a USB3 hub" even without the companion lookup. |
| C12 | confirmed | 2137 p5-7, PCH 10/11/14 have `uc=False`; the 0608 hub on HS10 has p1-4 `uc=True`. **Correction:** a phantom Corsair 1B1C:1C1F at `HS10#ACPI(PRT3)` (`group_position` 43) suggests HS10's hub feeds **internal 9-pin headers** used by AIO and RGB controllers, not necessarily front-panel sockets. Do not suggest these ports first. |
| C13 | confirmed | `camera_paths[]` maps each MI_00 function to its USB device with LocationPaths. |
| C14 | confirmed | 4 VID_CAMERA and 4 VIDEO entries with `function_instance ROOT\MEDIA\0002`, no `usb_device`. |
| C15 | confirmed | Phantom `USB\VID_05E3&PID_0626\5&cc3f949&0&20` → `...RHUB)#ACPI(SS04)`. |
| C16 | weakened | `group_position` equals the port number only for HS01-HS08 and their SS companions (HS04 and SS04 phantoms both 4). The Type-C ports use 18 (HS12) and 19 (HS13/TB SS04), and an HS10 hub port uses 43. The "top / upper / left" values are the **all-zero defaults** (Panel 0 = Top), so they mean "unspecified", not "top". The Type-C entries are `_PLD` rev 1 with **8×3 mm, shape 1 (oval)**: the receptacle geometry is real data and can confirm USB-C. |
| C17 | confirmed, citation fix | The C922's `_PLD` group 1 is stale (now at 13.1.4); the Revelator's 6 is stale (now at 13.2). The C922-on-port-1 record is `identity_dump.json` **cameras[2]**, not cameras[1] (cameras[1] is the Kiyo). |
| C18 | confirmed | `acpi_dsdt_check.txt`: DSDT 572,509 B; SSD1-SSDC listed; `xh_rps14` has 30 `_PLD`, 30 `_UPC`, 31 GPLD, 31 GUPC. |
| C19 | weakened | **27 phantom devnodes, not 47.** The 47 is `usb_devnodes_all_incl_phantom`, which includes the 20 present ones. The phantoms do label HS01, HS02, HS04, HS07, HS12, PCH SS04 and TB SS03 with past devices. |
| C20 | confirmed, scope fix | `r08_cross_rootport_no_kiyo.json`: in the "different root ports" pair, the C922 was on **HS01** and the C930e on **HS13 via the 0610 hub**. Only that one pair of root ports was tested. The stronger datum is `three_cams_max_fit`: HS01 held 3060 B/µframe (0x13fc) while HS13 held 3069 + 1600 B (0x13ff + 0x0b20). That totals ~7.7 kB/µframe on one controller, above any single 6 kB (80%) HS budget, so the two root ports are not one HS budget. |
| C21 | confirmed | The patch (Xu Rao, V6 2025-04-01, tested on AMD Raven 03:00.3) is now in mainline: `xhci-debugfs.c` master has `debugfs_create_dir("port_bandwidth")`, `SS_BW`, `HS_BW` and `xhci_get_port_bandwidth`. `xhci_queue_get_port_bw()` is commented "get root hub port bandwidth" and queues the TRB with no hub slot, so root ports only. |
| C22 | weakened | The cited source is Sarah Sharp, **2010-04-12**, about an NEC controller. Later Linux code does software admission for some controllers: `xhci-pci.c` sets `XHCI_SW_BW_CHECKING` for Intel Panther Point, and MediaTek xHCI uses a software scheduler (`xhci-mtk-sch.c`). That software model keeps a bandwidth table **per root port** (`rh_bw[]`), which supports the per-root-port domain idea. Whether Windows USBXHCI adds any software check is unknown. |
| C23 | weakened | The Plugable KB gives **96 endpoints for the "Intel 8 Series" (2013)** xHCI only, relayed from community reports. It does not mention AMD, so the "~254 for AMD" figure is unsourced. The cited Intel community thread contains no numbers. Treat the figures as anecdotal and do not apply them to 700-series PCHs. |
| C24 | weakened | The topology is confirmed. But the device on HS13 + TB SS04 is a **Genesys 05e3:0625 USB 3.2 Gen 2 hub** (USB2 half 0610) with a Dell monitor hub (0424:2137/5537) behind it. `Get-PnpDevice` shows no Thunderbolt or USB4 peripheral, only the host's "Thunderbolt(TM) Controller - 1137". So this is a USB-C hub running in native USB mode, **not a TB4/USB4 dock**. In §4.2, "USB4/TB4 docks… measured for this dock" should read **doc/inferred**: USB4 carries USB 2.0 on the separate D+/D- pair, untunnelled. It is not measured. |
| C25 | confirmed | `r02_c922_alt_by_mode.json` contains `"wMaxPacketSize": "0x0280"`. r08 also has live pipes (e.g. 0x13fc, 0x0be0) via the same IOCTL, so the live-load path is already exercised in the repo (partly answers T1). |
| C26 | confirmed | Identical values on both controllers. Also note `AllocedBulkAndControl 2867200` = exactly 20% of `Total32secBandwidth 14336000`, and `PciInterruptCount 1` with all counters 0. These are computed placeholders, which strengthens "static". |
| C27 | confirmed | The page's ms.date is 2024-01-17 (updated_at 2025-07-18). It still says "Select the controller's properties then look under the Advanced tab". |
| C28 | **refuted as measured** | `bw_etw/etw01/console_output.txt` shows the script ran `Start-Process powershell -Verb RunAs`. It *asked* for elevation and never tried a non-elevated `logman -ets`. Dom's token is in **Performance Log Users**, and Microsoft's StartTrace docs say members of that group "can control event tracing sessions" (the NT Kernel Logger excepted). Non-admin USB ETW is therefore **untested and plausible on Gerald**. For end users the practical conclusion still holds, because joining that group needs admin once. |
| C29 | confirmed | `[ComponentModel.Win32Exception]::new(6351)` → "A camera interface doesn't have the desired bandwidth for data transfer." r08 `c922_alt9_c930e_alt11_gen_fail_expected` shows `failed_stage ReadSample(first)`, `error_hr 0x800718CF`. |
| C30 | confirmed, plus a nuance | FFmpeg master `dshow_read_header`: `int ret = AVERROR(EIO)`. If `IMediaControl_Run` returns `S_FALSE`, `r = IMediaControl_GetState(control, 0, &pfs)`. Any `r != S_OK` logs "Could not run graph…" and goes to `error`. A graph that is merely slow to reach Running (GetState with a 0 ms timeout returns `VFW_S_STATE_INTERMEDIATE`) therefore also gives EIO. That makes EIO **more** ambiguous than stated. |
| C31 | confirmed | `eventlog_check.txt`: 6 events, newest 2026-05-10 (ID 50, TB controller). FrameServer log covers only 2026-11-04 to 11-06. |
| C32 | confirmed | `win_usb_topology.py` line 57 `_ctl(260)` and `_get_descriptor`. |
| C33 | confirmed | Console alt tables: C930e alt 11 3072, C922 alt 11 3060, generic alt 1 3069. **Caveat for the design:** cost depends on the mode (REPORT 16: C930e 480p takes alt 10, 2688 B). `Device.max_alt_cost` should be a (camera key, format, size, fps) → alt table, not one number. |
| C34 | unverifiable (inferred) | This is a reasonable design choice; there is no evidence either way yet (T9). |

### What the report missed

1. **skellycam's current Windows capture path cannot see a bandwidth refusal at all.** The `dom/openpnp-capture` branch uses openpnp-capture (DirectShow). In both upstream master (fetched 2026-11-06) and the local checkout `C:/Users/Dom/GitHub/freemocap/openpnp-capture/win/platformstream.cpp` lines 489-499 the code is `//FIXME: add error handling` / `m_control->Run();`. The HRESULT is discarded, the two filter `Run(0)` results are not checked, and `open()` returns `true`. A refused stream looks like "opened, then no frames". On that backend, detection needs a **first-frame watchdog** combined with the topology/budget inference, or a patched `Run` check. This changes design step 8.
2. **OpenCV MSMF surfaces the HRESULT only in a log line.** The repo has `cap_msmf.cpp:488 … OnReadSample … async ReadSample() call is failed with error status: -2147024865` (`results/windows/Gerald/timing/kiyo_lens/run2/cv_msmf_v2.stderr.txt`). A bandwidth refusal would print `-2147018545` (= 0x800718CF), and `read()` just returns False. OpenCV DSHOW only reports "open failed".
3. **The libusb/libuvc-on-WinUSB signature is missing from the classification table.** It is `uvc_start_streaming` → `-1 "I/O error"` (LIBUSB_ERROR_IO) (`results/windows/Gerald/phase2_bw_alt_verify/zero_frame_after_refused_start.json`). The "next start delivers 0 frames" evidence (REPORT 19) comes **only from this libuvc path**, not from MF or DS. The MF follow-on symptom is a transient `DeviceNotFound` (RERUN_20261027.md line 41). The table's "Any" row overgeneralizes.
4. **`PortIsUserConnectable` comes from BIOS `_UPC`, and desktop BIOSes often mark unwired ports connectable.** On Gerald, 13 of 16 HS and all 9 SS PCH ports claim to be connectable. The message should not list HS15/HS16 ("USB 2.0-only") or HS10's hub as real sockets without other evidence: phantom-devnode history (a device was once there), a `_PLD` with `user_visible`, or plug-in-to-identify.
5. **"USB 3 Type-A" is inferred.** `TypeC=0` with an SS companion could also be a front-panel USB 3 19-pin header or an internal port. Say "USB 3 port (not USB-C)" unless `_PLD` shape or history shows otherwise.
6. **No SuperSpeed budget is given.** SS/SS+ domains need their own admission number. USB 3.x allows at most 90% of a bus interval for periodic transfers (**doc**, USB 3.2 spec §8.12.6 / §4.4.8; not re-fetched here). The single-HS-budget `Domain` model leaves SS cameras (Kiyo) unmodelled.
7. **Integrated Thunderbolt and USB4 hosts are not covered.** These include the Intel CPU TCSS xHCI on mobile Tiger Lake and later, and AMD USB4 routers with the Windows USB4 connection manager. They split USB2 and SS in a different way from a discrete Maple Ridge. The companion IOCTL should still reveal the split, but this is unmeasured.
8. **The probe already shows per-link SS vs SS+** (TB root port 4 `op_ssp`) and the "USB2 half of a USB3 hub" signal (`ss_capable` on an HS upstream port). The report does not use either.
9. **Phantom `VID_0000&PID_0002` devnodes** (failed enumerations at HS02, HS03, HS07 and on the dock) are a no-admin record of past enumeration failures on a port. They could help flag flaky ports in suggestions.

### Corrections to the proposed design

- Step 8 (failure classification) must branch on the backend. MF Source Reader gives an unambiguous `0x800718CF`. OpenCV MSMF only logs the HRESULT. FFmpeg/PyAV DS gives an ambiguous EIO, also hit by slow `S_FALSE` transitions. openpnp-capture DS gives no error at all, so use a first-frame timeout. libuvc/WinUSB gives LIBUSB_ERROR_IO and then a zero-frame start. When there is no code, classify as bandwidth only when the domain model predicts overflow.
- Step 9 (suggestions): rank ports with evidence of a real socket first (phantom history, `_PLD` `user_visible` with ACPI HS/SS name, USB-C geometry). Put header-like ports last (HS10 hub, USB2-only HS15/16), and do not call them "Type-A".
- Data model: keep the cost per (camera, mode), not per device. Add an SS domain budget (90%). Store the SS vs SS+ link flag per hub port.
- Retitle the §4.2 USB4/TB4 dock row as doc/inferred. The measured device is a USB 3.2 hub in native USB mode.
- ETW: re-test non-elevated `logman -ets` as a Performance Log Users member before writing "needs admin". Keep it out of the library either way.
