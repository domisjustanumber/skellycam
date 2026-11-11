# Linux USB topology mapper for bandwidth errors

Topic: `topology_linux`. Written 2026-11-06 for the skellycam USB camera study. It answers Dom's 2026-11-06 requirement: map the USB tree, work out which cameras share periodic bandwidth, and, when a concurrent open fails, tell the user which cameras collided and which empty ports would avoid the collision. The mapper must not change any driver and should not need root.

No camera was opened or streamed for this report. Labels:

- **measured**: a read-only command run on Gerald on 2026-11-06, or a repo result file.
- **doc**: kernel or systemd source, or official documentation. Kernel source is read at torvalds/linux master `f66469d9905b` (committed 2026-11-06), with release versions found by `gh api repos/torvalds/linux/compare/<tag>...<sha>`.
- **web**: a mailing list post, a blog or a news report.
- **inferred**: my reasoning from the above.

## 1. Summary

1. **Without root, sysfs alone gives the whole tree, the negotiated link speeds, the current reservations, the companion-port pairing and the physical labels.** Root is needed only for `debugfs` (xHCI Get Port Bandwidth) and raw ACPI tables, and the mapper uses neither in normal operation.
2. **The bandwidth domain depends on the controller vendor, and Linux cannot ask the hardware for it without root.** Linux's own xHCI code models each root port as a "primary bandwidth domain" and each high-speed hub TT (transaction translator) as a secondary one. This matches Gerald (Intel 8086:7A60), where two max-alt cameras on root ports 1 and 13 of the same controller streamed together. However, a 2025 kernel patch shows an **AMD Raven** xHCI where one high-speed video device cut the available HS bandwidth on **all four** HS root ports from 79% to 39%. That is evidence of a controller-wide HS domain on AMD. The mapper therefore needs a per-vendor policy table, with the controller as the conservative default, and should learn conflicts at runtime.
3. **A bandwidth failure on Linux is `VIDIOC_STREAMON` failing with `ENOSPC` (28).** The kernel logs `Not enough bandwidth for new device state.` (xHCI) and `Not enough bandwidth for altsetting N` (usbcore). `ENOMEM` at the same step means the controller ran out of resources (endpoint or slot contexts), not bus time. `EIO` with "No fast enough alt setting" is a camera or mode problem.
4. **The draft camera key has a collision bug.** `camera_identity.port_path_from_linux()` drops the bus number. But an xHCI controller has two root hubs (USB 2 and USB 3), each numbering its ports from 1, so `pci-0000:00:14.0/1` can name two different connectors. systemd hit the same bug and added `ID_PATH_WITH_USB_REVISION` in v254. The V4L2 `bus_info` string has the same ambiguity.

## 2. What sysfs exposes, and when it was added

Everything in this table is mode 0444 (`DEVICE_ATTR_RO`, `BIN_ATTR_RO`), so any user can read it. **doc**: `drivers/usb/core/{sysfs.c,port.c,endpoint.c}`, `drivers/base/physical_location.c`, `Documentation/ABI/testing/sysfs-bus-usb`, `sysfs-devices-physical_location`.

| Object (path) | Attributes used | First kernel | Notes |
|---|---|---|---|
| Root hub `/sys/bus/usb/devices/usbN` | `busnum`, `speed` (480 = USB 2 bus; 5000/10000/20000 = USB 3 bus), `version`, `maxchild`, `product`; `readlink -f` gives the controller (`/sys/devices/pci0000:00/0000:00:14.0/usbN`) | old | An xHCI controller registers **two** buses: a USB 2 root hub and a USB 3 root hub (the `shared_hcd`). EHCI, dwc2 and MUSB register one. |
| Device `N-p1.p2…` (e.g. `3-13.1`) | `devpath` (`13.1`), `speed` (**negotiated**: `udev->speed`, despite the ABI text saying "max speed"), `version` (bcdUSB, i.e. capability), `idVendor`, `idProduct`, `serial`, `product`, `removable`, `maxchild` (hubs), `rx_lanes`, `tx_lanes`, binary `descriptors` (all configurations), symlink `port` → its upstream port object | old (lanes 4.18) | A USB 3-capable camera that enumerated at 480 shows `version` ≥ 3.00 with `speed`=480: a cable or port problem worth warning about. |
| Interface `N-p:C.I` | `bInterfaceClass` (0e = video, 01 = audio), `bInterfaceSubClass` (1 = VC, 2 = VS), `bAlternateSetting` (**current** alt), `ep_XX/{type,wMaxPacketSize,interval,direction}` for the current alt | old | Any interface with `bAlternateSetting` ≠ 0 and an isochronous endpoint is holding periodic bandwidth now (see section 6). |
| Port `<hub>/<hub>:1.0/<hub>-portK` (root: `usbN/N-0:1.0/usbN-portK`; external: `3-13/3-13:1.0/3-13-port1`) | `connect_type` (`hotplug` / `hardwired` / `not used` / `unknown`), symlink `device` → child if occupied, symlink `peer` → USB 2/USB 3 companion port, `location`, `over_current_count`, `quirks`, `usb3_lpm_permit` (SS ports) | connect_type 3.9 (cef7468caff2, Jan 2013); peer **3.16**; location **4.20**; quirks 4.18; over_current_count 4.17 | Port names come from `dev_set_name("%s-port%d")` (port.c:783). `connect_type` is derived from ACPI `_UPC` connectable plus `_PLD` user_visible (usb-acpi.c:203-245). `location` is `0x80000000 \| group_token<<8 \| group_position` from `_PLD`, and both companions of one physical connector carry the same value. |
| Port (newer) | `disable` (rw, root to write), `state` (`not-attached`, …, `configured`, `suspended`; supports poll) | disable **6.0**; state **6.5** | |
| Port (Type-C) | symlink `connector` → `/sys/class/typec/portX` | **5.17** | This is the only USB-C indicator in sysfs. `_UPC` connector type is evaluated but **not exported**. |
| Any device with an ACPI companion that has `_PLD` (USB **ports** included) | `physical_location/{panel, vertical_position, horizontal_position, dock, lid}` | **5.19** (commit 6423d2951087) | So not 6.x as the brief guessed. Created in `device_add_attrs()` when `has_acpi_companion(dev)`. The USB port companion is bound in `device_platform_notify()`, which `device_add()` calls before `device_add_attrs()` (core.c), via `usb_acpi_find_companion_for_port`. USB port objects should therefore get it whenever the firmware has `_PLD`. **Inferred from source; not yet seen on hardware.** |
| `firmware_node` symlink on ports and devices | `firmware_node/path` (e.g. `\_SB_.PC00.XHCI.RHUB.HS03`) | old | Readable without root. The `HSxx`/`SSxx` names are a useful raw label and show the pairing. |
| PCI controller `/sys/bus/pci/devices/0000:00:14.0` | `vendor`, `device`, `class` (0x0c0330 = xHCI), `driver` → `xhci_hcd` (`xhci_pci`), `label` (SMBIOS, rare) | old | The friendly name comes from hwdb (`udevadm info -q property /sys/bus/pci/devices/…` → `ID_MODEL_FROM_DATABASE`) or `lspci -mm`, both without root. |

**Measured on Gerald (WSL2 kernel 5.15.153, `vhci_hcd`, read-only):** `usb1` has speed 480, version 2.00, maxchild 8; `usb2` has speed 5000, version 3.00, maxchild 8. `usb1-portK` has `peer` → `usb2-portK` for every K. That is the default root-hub peering through `shared_hcd` (port.c:657-672), which applies when the firmware gives no `location`. `connect_type`, `location`, `quirks` and `over_current_count` are present. `state` and `disable` are absent, as expected on 5.15. `/sys/kernel/debug` is `drwx------ root`. Command: `wsl.exe -d Ubuntu -- sh wsl_usb_ro.sh`. Script and output: [`topology_linux_evidence/`](topology_linux_evidence/). This is a virtual controller, so it proves the attribute layout only, not any real board's ACPI.

**Distros (web):** Ubuntu 24.04 ships GA kernel 6.8 (HWE kernels later), so it has everything above except the debugfs bandwidth file. Ubuntu 26.04 LTS shipped kernel 7.0 ([Ubuntu Discourse](https://discourse.ubuntu.com/t/26-04-lts-resolute-raccoon-shipping-with-the-final-7-0-linux-kernel/80838)). Fedora 45 (KDE edition: Plasma 6.8) is on 7.2 ([linuxiac](https://linuxiac.com/?p=222316)). All three targets therefore have `peer`, `location`, `connector`, `physical_location`, `disable` and `state`.

### /dev/videoN to USB device to port path

1. Start from `/sys/class/video4linux/videoN`. Keep `index` = 0, which is the capture node; index 1 is the UVC metadata node.
2. `device` resolves to the VideoControl interface, e.g. `…/usb3/3-13/3-13.1/3-13.1:1.0`. Its parent directory is the USB device `3-13.1`.
3. Port chain: `devpath` = `13.1`, bus = `busnum` = 3. The bus's `speed` tells whether `13` is a USB 2 or a USB 3 root port number.
4. Upstream ports: `3-13.1/port` → `3-13-port1`, then `3-13/port` → `usb3-port13`. Following `port` symlinks to the root gives the domain anchor.
5. udev (`udevadm info -q property -n /dev/videoN`, no root) adds `ID_PATH=pci-0000:00:14.0-usb-0:13.1:1.0`, `ID_SERIAL` and `ID_SERIAL_SHORT`. On systemd ≥ 254 it also adds `ID_PATH_WITH_USB_REVISION=pci-…-usbv2-0:13.1:1.0` (**doc**: systemd commit 873be895ed, 2023-05-01, "xHCI host controller may register two … root hubs … devices under the hubs may have same ID_PATH"; `rules.d/60-persistent-v4l.rules` creates `/dev/v4l/by-path/*usbv2*` links). Ubuntu 24.04 ships systemd 255 (inferred: ≥ 254).
6. `lsusb -t` (usbutils, sysfs-based, no root) prints the same tree with `Driver=uvcvideo, 480M`. It is useful for humans and bug reports but not needed by the code.

## 3. Speed and "USB 2 camera behind a USB 3 hub"

- **Link speed** is each device's `speed`: 1.5 = LS, 12 = FS, 480 = HS, 5000 = SS, 10000 or 20000 = SS+. Lanes are in `rx_lanes`/`tx_lanes`. A device's **upstream link** runs at the lower of its own speed and its parent hub's speed, and the parent's `speed` is readable too. **doc** (sysfs.c `speed_show`).
- **A USB 3 hub is two hubs**: a USB 2 half enumerated on the USB 2 bus (e.g. `3-2`, speed 480) and a SuperSpeed half on the USB 3 bus (e.g. `4-1`, speed 5000). A USB 2 camera plugged into it appears under the **USB 2 half** (`3-2.1`) and uses only the USB 2 wires of the root connector. Detection without root:
  - the camera's parent hub has `speed`=480;
  - the parent's upstream port has a `peer`;
  - that peer port's `device` is a hub with `speed` ≥ 5000.
  
  This follows from the peering code (port.c `find_and_link_peer`: root hubs pair through `shared_hcd`, external hub ports pair by "upstream peer" plus the same port number, unless firmware `location` data overrides). **doc** + **inferred**.
- **Consequence:** a USB 3 camera on the SS half and a USB 2 camera on the USB 2 half of the same hub or connector **do not compete**. They use different wires and different bandwidth tables (xhci.c `xhci_check_bw_table` sends SS devices to `xhci_check_ss_bw`, which tracks IN and OUT separately). **doc** (Panther Point software checker; the 2011 commit 2b69899934c6 says "each direction has the full USB 3.0 bandwidth"); **inferred** for hardware checkers.

## 4. Bandwidth domains: which cameras compete

### What Linux does

Apart from one Intel controller, the Linux xHCI driver **does not decide** admission. It sends a Configure Endpoint command (as part of `usb_set_interface` → `usb_hcd_alloc_bandwidth` → `xhci_check_bandwidth`), and the **controller hardware** accepts it or answers `COMP_BANDWIDTH_ERROR` / `COMP_SECONDARY_BANDWIDTH_ERROR`. The driver turns that into `-ENOSPC` and logs `"Not enough bandwidth for new device state."` (xhci.c:2135-2139). **doc**.

The domain structure is therefore the silicon's, the same as on Windows. Linux has a software model only for Intel Panther Point (8086:1E31, 7-series), via quirk `XHCI_SW_BW_CHECKING` (xhci-pci.c:354-358). That model is useful as a statement of the intended structure:

- `struct xhci_root_port_bw_info`, one per root port: "If a high speed hub is attached to the roothub, each TT associated with that hub is a separate bandwidth domain" (xhci.h:775-784).
- The commit that introduced it (839c817ce671, Sarah Sharp, Intel, 2011-09-02): "Each root port is a separate primary bandwidth domain, and each high speed hub's TT (and potentially each port on a multi-TT hub) is a secondary bandwidth domain."
- Limits are in "blocks" (HS_BLOCK = 4 B): `HS_BW_LIMIT 1607`, `HS_BW_RESERVED 20` (percent kept for non-periodic transfers), `SS_BW_LIMIT_IN/OUT 3906` with 10% reserved (xhci.h:624-661).
- When the software model refuses, it returns **`-ENOMEM`** with `"Not enough bandwidth\n"` (xhci.c:2997-3003), not `-ENOSPC`. This matters only on Panther Point.

TTs matter only for FS and LS devices behind an HS hub. **HS cameras behind a hub all share that hub's single upstream HS link, so they compete with each other and with everything else in the root port's domain.** **doc** + **inferred**.

### By controller (evidence)

| Controller | HS domain | Evidence | Label |
|---|---|---|---|
| Intel PCH xHCI, e.g. 8086:7A60 (Raptor Lake) on Gerald | **root port**: the USB 2 root port of the physical connector, including any hubs behind it | Gerald: C922 on root port 1 and C930e on root port 13 of the **same** controller 8086:7A60 streamed together at 1080p30 MJPEG, both at alt 11 (~62% each). Two cameras behind the Genesys hub on root port 13 hit the 80% model 26/26 (`results/windows/Gerald/bw_concurrency_rerun_20261027/r08_cross_rootport_no_kiyo.json`, `bw_topology_rerun_20261027/topology_idle_0307Z.json`, RERUN_20261027.md "Different root ports don't compete"). Linux sends the same Configure Endpoint command to the same silicon, so the result should transfer. | measured (Windows); inferred for Linux |
| Intel Panther Point (8086:1E31) | root port, plus TT, in software | xhci.c/xhci.h as above | doc |
| AMD Raven USB 3.1 (1022:15E0/15E1 family; patch shows "Raven USB 3.1" at 03:00.3) | **whole USB 2 root hub of the controller** (all HS root ports together) | Get Port Bandwidth before and after plugging in an HS video device (0408:1040): ports 1–4 **all** went from 79% to 39%; FS audio took ports 1–4 from 90% to 76% ([LKML, raoxu, 2025-03-05](https://lkml.iu.edu/2503.0/06096.html)) | web (patch text); the domain reading is inferred |
| Newer AMD (Promontory/ASMedia chipset xHCI, Rembrandt, Phoenix, Strix USB4 hosts) | unknown | none found | open question; treat as controller |
| ASMedia 1b21, Renesas 1912 (µPD720201/202), VIA 1106 (VL805), Fresco 1b73, Etron 1b6f add-in cards | unknown per port. Multi-controller cards (e.g. 4× Renesas D720201) give **one controller per port**, so per port in practice | vendor datasheets only ([search summary](https://www.farnell.com/datasheets/3774381.pdf)) | web/inferred; treat as controller |
| MediaTek `xhci-mtk` (ARM SoCs) | software scheduler: "each HS root port is treated as a single bandwidth domain, but each SS root port is treated as two bandwidth domains, one for IN eps, one for OUT" | xhci-mtk-sch.c:119-150; returns `-ENOSPC` at :991 | doc |
| EHCI / dwc2 (Raspberry Pi 0–3) / MUSB | whole bus | "iso sched full" (EHCI); dwc2 "Insufficient periodic bandwidth"; uvcvideo "Failed to submit URB 0 (-28)" ([Good Penguin, 2020/2022](https://www.thegoodpenguin.co.uk/blog/multiple-uvc-cameras-on-linux/)) | web |
| Thunderbolt 3 dock | the dock has **its own xHCI**, which appears as another PCI controller behind TB bridges, so it is a separate controller domain | inferred from the PCI tree; check `/sys/bus/thunderbolt` | inferred |
| USB4 dock using host USB3 tunnelling | SS traffic is tunnelled to the host's USB4-port xHCI. USB 2 runs on separate D+/D− wires to the host root port, so HS cameras on the dock share **that host root port's** USB 2 domain | inferred | inferred |

**Root-only ground truth (research, not product):** since 6.16, `/sys/kernel/debug/usb/xhci/<pci>/port_bandwidth/{HS_BW,FS_BW,SS_BW}` prints `port[i] available bw: N%.` for every **hardware** port by issuing the xHCI Get Port Bandwidth command. **doc**: commit 59d50e53e070 is in v6.16 and not v6.15. `SS_BW` returned 0% on Gen1 controllers until fix 452af0f9ffe1 (in v7.1, not v6.19), which says "instead of SuperSpeed we were querying SuperSpeed+. Gen1 hardware rejects such commands". So Ubuntu 26.04's 7.0 may show a wrong SS_BW unless the fix was backported.

Port `i` is the xHCI hardware port number (one numbering space across USB 2 and USB 3), not the sysfs per-bus number. Mapping between them needs `reg-ext-protocol` in the same debugfs directory. Running this with one camera streaming is the cheapest way to find any controller's domain structure (section 9).

## 5. Free ports, grouped by domain, with labels

- **Empty:** the port object has no `device` symlink. On ≥ 6.5 you can also check `state` = `not-attached`. Drop `connect_type` = `not used` and `hardwired` (internal webcams, Bluetooth). Keep `hotplug`, and keep `unknown` (no ACPI data, common on add-in cards and hubs).
- **One physical connector:** merge a USB 2 port and its `peer` into one entry. Present it as one connector with its USB 2 and USB 3 halves. Where `location` ≠ 0, ports with equal `location` are the same connector (usb-acpi.c). A USB 2 port with no peer is a USB 2-only connector (or a USB 3 connector whose firmware lacks pairing; inferred).
- **Labels available without root:**
  - `physical_location/panel` (top/bottom/left/right/front/back/unknown), `vertical_position`, `horizontal_position`, `dock`, `lid` (5.19+, when the firmware provides `_PLD`; desktop boards often report "unknown", inferred);
  - `connector` symlink means USB-C (5.17+, needs UCSI or ACPI connector description);
  - SS `peer` present and no `connector` probably means USB 3 Type-A (inferred);
  - the ACPI path leaf (`HS03`/`SS03`) from `firmware_node/path`;
  - the controller's hwdb name and PCI address;
  - for ports on external hubs, the hub's `product` string and VID:PID.
- **Not available without root:** the `_UPC` connector-type byte (Type-A vs C vs proprietary) is evaluated by the kernel but not exported. Raw `_PLD` colour, shape and group fields live only in ACPI tables (`/sys/firmware/acpi/tables/*`), which are root-only. **doc** (usb-acpi.c reads `_UPC` element 0 only; the `physical_location` subset is fixed). The tables directory is 755 under WSL (measured), but the files themselves should be root-only (inferred).
- **Grouping:**
  - Intel: domain = controller PCI address + USB 2 root port (+ SS root port for SS cameras).
  - AMD and unknown vendors: domain = controller + bus speed.
  
  A free port is a **valid suggestion** for camera X if its domain holds no other camera that is streaming or about to stream, and the predicted reservation fits (section 6). Prefer, in order:
  1. a root-level connector on a different controller (always correct);
  2. a root-level connector on another root port of the same controller (correct on Intel only);
  3. never a port on a hub that sits behind the colliding root port.

## 6. Current reservation per device (no root)

`bAlternateSetting` on each interface gives the alt currently in use, and `ep_XX/wMaxPacketSize` gives its endpoints. For HS: bytes per microframe = (wMaxPacketSize & 0x7FF) × (1 + ((wMaxPacketSize >> 11) & 3)), divided by 2^(bInterval−1) microframes. For SS, take `wBytesPerInterval` from the SS endpoint companion descriptor, parsed from the device's `descriptors` file.

Summing over every isochronous or interrupt endpoint of every device in a domain estimates the periodic load **without root and without asking the controller**. That includes audio interfaces, such as a webcam microphone opened by PipeWire. Gerald's earlier "audio device on the same root-port link" case is exactly this. **doc** (endpoint.c, sysfs.c `usb_intf_attr(bAlternateSetting)` reads `cur_altsetting`) + **inferred**.

The `bw_probe` draft already parses alt tables from `descriptors`. A camera's max-alt bytes, checked against the 80%-of-microframe model (6000 B/µframe HS, validated 26/26 on Gerald's Intel), predicts the collision **before** opening.

Not usable: `/sys/kernel/debug/usb/devices` (root). Its `B: Alloc=` line is fed by `bus->bandwidth_allocated`, which xHCI does not maintain (inferred). usbmon is root-only.

## 7. Detecting that a failure was bandwidth

On every HCD, the bus-bandwidth failure surfaces at **`VIDIOC_STREAMON`**. uvcvideo picks the **smallest** alt whose payload ≥ `dwMaxPayloadTransferSize` (uvc_video.c:2062-2079; Windows `usbvideo` picks the max) and then calls `usb_set_interface` (:2101).

| Stage / errno | Meaning | Kernel log | Label |
|---|---|---|---|
| STREAMON → **ENOSPC (28)**, "No space left on device" | **Bus periodic bandwidth.** xHCI refused the alt (Configure Endpoint), or EHCI/dwc2/MTK refused at URB submit | xHCI: `usb 3-13.1: Not enough bandwidth for new device state.`, then `usb 3-13.1: Not enough bandwidth for altsetting 11` (message.c:1645, dev_info). EHCI etc.: `uvcvideo …: Failed to submit URB 0 (-28).` (uvc_video.c:2129) | doc |
| STREAMON → **ENOMEM (12)** | xHCI `COMP_RESOURCE_ERROR`: out of endpoint or slot contexts ("Not enough host controller resources for new device state.", xhci.c:2129-2132). Also Panther Point's software check ("Not enough bandwidth"). Suggest a different **controller**, not a different port. | as quoted | doc |
| STREAMON → **EIO** + "No fast enough alt setting for requested bandwidth" | The camera asks for more than any alt it has. Camera or mode problem, not topology. | uvc dbg only (needs `trace` param) | doc |
| S_FMT / TRY_FMT → ENOSPC | uvc probe with `UVC_QUIRK_PROBE_MINMAX` when the camera's request exceeds its own max packet (uvc_video.c:466-473). **Not the bus.** | none | doc |
| open/S_FMT/REQBUFS → EBUSY | another process owns the node | — | inferred |
| ENODEV / EPROTO / ETIMEDOUT / EPIPE | disconnect, signalling, stall | various | inferred |

Rules for the library:

- Classify by **(ioctl stage, errno)**, not by log text, because logs are often unreadable. Ubuntu sets `kernel.dmesg_restrict=1` since 20.10 ([Launchpad 1902934](https://bugs.launchpad.net/bugs/1902934)). `journalctl -k` usually works for `adm`/`wheel` members (inferred). Fedora's default is unverified.
- Use logs only as optional confirmation. Frontends hide errno: GStreamer says "Failed to allocate required memory" (Good Penguin), and OpenCV reports a failed `read()`. The capture path must call V4L2 directly, or check errno right after STREAMON.
- With simultaneous starts, which camera loses is a race (measured on Windows). Start cameras **sequentially**, in domain order.

## 8. Review of the existing drafts

- `naming/camera_identity.py` `port_path_from_linux("0000:00:14.0","3-13.1.4") → "pci-0000:00:14.0/13.1.4"` (line 95, selftest line 210) **collides across the USB 2 and USB 3 root hubs of one controller**. Fix: either tag the bus speed (`…/usb2/13.1.4` vs `…/usb3/2.1`, as systemd does with `usbv2`/`usbv3`), or, better for stability, **normalise to the USB 2 companion chain** by mapping each SS port to its `peer` number. Then a USB 3 camera keeps its key if it falls back to HS, and a USB 2 and a USB 3 camera on one connector cannot collide. Note that Windows `LocationPaths` uses xHCI hardware port numbers, which also differ from Linux per-bus numbers, so a port key is not portable across OSes (inferred).
- `naming/linux_identity.py`:
  - It reads `port/connect_type` and `port/location` through the device's `port` link, which works.
  - It lacks: the root hub `speed` (bus kind), `peer`, `state`, `physical_location`, `firmware_node/path`, the parent hub chain, free ports and the hwdb controller name.
  - `pci_controller()` (element before `usbN`) also works behind Thunderbolt bridges, but it names the dock's xHCI for TB3 docks, which is correct for domains.
  - The V4L2 `bus_info` it records (`usb-0000:00:14.0-13.1`) has the same USB 2/USB 3 ambiguity.
- `bandwidth/linux/uvc_bw_probe.py`:
  - The docstring says "xHCI budgets bandwidth per root-hub port". That is true for Intel; AMD Raven evidence contradicts it.
  - `root_port` is the per-bus number, so a USB 2 root port 1 and a USB 3 root port 1 are different connectors.
  - `xhci_port_bw()` reads the debugfs files, but its port indices are hardware numbers, and `SS_BW` is wrong on Gen1 before 7.1.
  - `compare` is the only subcommand needing root, and it changes module parameters (that is a module option, not a driver swap, but it still needs to be flagged).

## 9. Design: Linux topology mapper (no root)

**Calls, in order** (all are file reads; `udevadm` is optional):

1. **Controllers.** `glob /sys/bus/usb/devices/usb*`. For each root hub, read `busnum`, `speed` and `maxchild`, then `realpath` → controller sysfs dir. If its `subsystem` is pci, read `vendor`, `device` and `driver`, and the name from `udevadm info -q property <pcidir>` → `ID_VENDOR_FROM_DATABASE`/`ID_MODEL_FROM_DATABASE` (fallback: parse `/usr/share/hwdata/pci.ids`). Group root hubs by controller dir: an xHCI controller gets `usb2_bus` and `usb3_bus`. Detect Thunderbolt by a `thunderbolt`/`pcieport` chain in the path.
2. **Ports.** For each hub device (root or external, `maxchild` > 0), for K in 1..maxchild, read `<hub>:1.0/<hub>-portK`: `connect_type`, `location`, `state` (if present), `peer` (realpath), `device` (realpath or none), `connector` (exists?), `physical_location/*`, `firmware_node/path`, `over_current_count`, `disable` (read-only).
3. **Devices.** For each `N-*` device dir without `:`: `devpath`, `speed`, `version`, VID/PID/serial/product, `removable`, `port` link, interfaces (`*:*.*`), class, `bAlternateSetting`, `ep_*/{type,wMaxPacketSize,interval,direction}`, and `descriptors` bytes (reuse `usbdesc.parse_sysfs_descriptors`).
4. **Cameras.** `/sys/class/video4linux/video*` with `index`=0 → interface → device. Optionally read udev `ID_SERIAL`, `ID_PATH_WITH_USB_REVISION`, `/dev/v4l/by-id`, `by-path`. Key = `camera_identity.derive()` with the fixed port path.
5. **Domains.** For each device, walk `port` links up to the root port R on bus B of controller C. Then:
   - `policy = POLICY.get((C.vendor, C.device)) or POLICY.get(C.vendor) or "controller"`;
   - HS/FS/LS device: `domain = (C, "hs", R)` if policy == "root_port" else `(C, "hs", "*")`;
   - SS device: `domain = (C, "ss", R_ss, direction)` for root_port policy, else `(C, "ss", "*")`;
   - FS/LS behind an HS hub: also record a secondary TT domain (`hub`, `ttport` if multi-TT) for completeness. Webcams are HS, so this rarely matters.
   
   Initial POLICY: Intel 8086 → root_port; Panther Point → root_port; xhci-mtk → root_port; AMD 1022 → controller; everything else → controller. A runtime-learned override table (key: controller vendor:device) moves a vendor to root_port when two cameras on different root ports of it have streamed together, and records conflicts per (controller, root port pair) when they have not.
6. **Load and prediction.** `reserved_now[domain]` is the sum of current-alt periodic bytes per µframe over all devices in the domain (section 6). `need[camera, mode]` is the max-alt bytes per µframe from descriptors; under uvcvideo it is really the smallest alt ≥ dwMaxPayloadTransferSize, which is unknown until probe, so use the max alt as the conservative value (it equalled the max for MJPEG on all Gerald cameras). Fits if `reserved_now + Σ need ≤ 6000` for HS (the Gerald 80% model), and ≤ 90% of the per-direction SS capacity for SS.
7. **Free ports.** Ports from step 2 with no `device`, `connect_type` ∈ {hotplug, unknown}, `disable` ≠ 1. Merge peers into connectors. Annotate each connector with its domain(s), its predicted headroom and a label:
   - label = `f"{panel} {vpos}/{hpos}"` if `physical_location` is present and not unknown;
   - plus `"USB-C"` if `connector`, `"USB 3"` if an SS peer exists, else `"USB 2"`;
   - plus `f"on {controller_name} ({pci})"`;
   - plus `f"hub {product}"` if the port is on an external hub;
   - plus `firmware_node` leaf as a fallback.
8. **On failure** (STREAMON → ENOSPC for camera X):
   1. Re-read `bAlternateSetting` everywhere (cheap).
   2. Find the other devices with a non-zero isochronous alt in X's domain.
   3. Message: "Cameras {X} and {Y} share USB bandwidth ({domain label}), and I got an error when opening them at the same time. Suggest moving {X or Y} to any of these ports: {connectors in other domains with enough headroom, best first}." If the occupant is not a camera (e.g. audio), name it.
   
   For ENOMEM, say the controller ran out of resources and list ports on other controllers only.

**Data model** (one JSON snapshot, usable on any OS):

- `Controller{id: pci_addr|platform_name, vendor, device, name, driver, kind: xhci|ehci|dwc2|mtk|…, buses: {hs: busnum, ss: busnum|None}, policy, policy_source: table|learned|default, thunderbolt: bool}`
- `Port{id: "usb3-port13" | "3-13-port1", controller, bus_speed, number, hub_device, connect_type, location, state, peer, connector_typec: bool, physical_location{panel,vpos,hpos,dock,lid}|None, acpi_path, occupied_by: device_id|None}`
- `Connector{ports: [hs_port, ss_port?], label, user_visible: bool}`
- `Device{id: sysfs_name, busnum, devpath, speed, bcdUSB, vid, pid, serial, product, is_hub, parent_port, root_port_hs, root_port_ss, periodic_now: [{intf, alt, ep, dir, bytes_per_uframe}], max_alt_bytes_per_uframe}`
- `Camera{key, key_kind, device, video_node, by_path, by_id}`
- `Domain{id, controller, speed_class, root_port|"*", devices, reserved_now, budget, free_connectors}`

**Admin needs:** none for steps 1–8. Root is needed only for the research checks: debugfs `port_bandwidth`, `trace` on uvcvideo, ACPI tables, `disable` writes.

**Pitfalls:**

- Bus numbers change across boots (key on the controller address).
- `maxchild` includes "not used" ports.
- On boards without ACPI `_PLD`/`_UPC`, everything is `unknown` and peering falls back to same-number pairing, which can be wrong (kernel 6.8 commit 69c63350e573 stopped peering unused ports by location).
- External hub ports have no `physical_location`.
- Hubs with multiple TTs.
- Composite cameras whose audio interface PipeWire keeps open.
- A USB 3 camera that enumerated at HS.
- Hot-plug while mapping: re-scan on udev events, or simply re-scan on error.

## 10. Recommended tests

1. **Linux, Intel desktop (or Gerald dual-boot / live USB, Ubuntu 26.04), no root.** Run the mapper with the three cameras placed as on Windows (C922 on root port 1; C930e + generic on the Genesys hub). Then stream C922 + C930e at 1080p MJPEG concurrently on different root ports, then C930e + generic on the hub. Decides whether Linux on Intel 8086:7A60 reproduces "different root ports don't compete" and gives ENOSPC with the expected log for the shared hub.
2. **Same machine, root, 7.1+ kernel (Fedora 45).** Read `port_bandwidth/HS_BW` idle and with one camera streaming. Decides whether only that hardware port's availability drops (root-port domain) or all of them (controller domain), and calibrates the 80% model against the controller's own number.
3. **An AMD Ryzen machine (CPU xHCI and chipset xHCI).** Test 2, plus two cameras on different root ports of one controller. Decides the AMD policy row; the Raven patch suggests "controller".
4. **A PCIe add-in card (ASMedia ASM3142 or Renesas µPD720202) and a TB3/USB4 dock.** Same as test 3. Decides the add-in-card and dock rows.
5. **Laptop and desktop, no root.** Dump `physical_location`, `connect_type`, `location`, `peer`, `connector` and `firmware_node/path` for all ports. Decides how often human labels exist in practice; the hypothesis is that desktop boards often have `_PLD` panel = unknown.
6. **Any Linux box.** A USB 3 camera (e.g. Kiyo Pro) and a USB 2 camera on the same USB 3 hub, streaming together. Decides the claim that the SS and HS halves do not compete.
7. **Errno capture.** Force a collision and record the errno at STREAMON from raw V4L2, OpenCV, PyAV and GStreamer, plus whether `journalctl -k` is readable as the default user on Ubuntu 26.04 and Fedora 45. Decides the classifier and whether logs can be used.

## 11. Open questions

- AMD (newer than Raven), ASMedia, Renesas, VIA and Etron domain structure: no primary evidence found.
- Does `physical_location` actually appear under `usbN-portK` on common desktop and laptop firmware? The source says it should whenever the port's ACPI node has `_PLD`; it has not been observed.
- Do USB4 hosts and docks put tunnelled-USB3 devices and the USB 2 wires in the same xHCI domains as the host port?
- What does uvcvideo request as `dwMaxPayloadTransferSize` for MJPEG on these cameras? Is it the same 3072 B/µframe that `usbvideo` gets, so that the smallest-sufficient-alt rule still picks the max?
- What is Fedora's `dmesg_restrict` default, and who can read the kernel journal by default?
- Has fix 452af0f9ffe1 (SS_BW) been backported to Ubuntu 26.04's 7.0 kernel?

## Sources

- Kernel source (master f66469d9905b): `drivers/usb/core/{port.c,usb-acpi.c,sysfs.c,endpoint.c,hub.c,message.c}`, `drivers/usb/host/{xhci.c,xhci.h,xhci-mem.c,xhci-pci.c,xhci-debugfs.c,xhci-mtk-sch.c}`, `drivers/media/usb/uvc/uvc_video.c`, `drivers/base/{core.c,physical_location.c}`; [sysfs-bus-usb ABI](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/ABI/testing/sysfs-bus-usb); [sysfs-devices-physical_location](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-devices-physical_location).
- Commits, with the version each first appeared in: b7e38eac8826 (peer, 3.16), 355c74e55e99 (location, 4.20), 8c67d06f3fd9 (connector, 5.17), 6423d2951087 (physical_location, 5.19; [Phoronix](https://www.phoronix.com/news/Linux-5.19-Physical-Location)), f061f43d7418 (disable, 6.0), 83cb2604f641 (state, 6.5), 59d50e53e070 (port_bandwidth, 6.16), 452af0f9ffe1 (SS_BW fix, 7.1), 839c817ce671 / c29eea621900 / 2b69899934c6 (xHCI bandwidth domains and software checking, 2011).
- systemd 873be895ed (ID_PATH_WITH_USB_REVISION, v254), [issue 19406](https://github.com/systemd/systemd/issues/19406).
- [AMD Raven port bandwidth patch](https://lkml.iu.edu/2503.0/06096.html); [Nyman reply](https://lkml.iu.edu/hypermail/linux/kernel/2504.0/01732.html); [Magewell / Get Port Bandwidth thread 2018](https://www.spinics.net/lists/linux-usb/msg164934.html); [Greg KH on root hubs per laptop, 2019](https://www.spinics.net/lists/linux-usb/msg182835.html); [Good Penguin multi-UVC](https://www.thegoodpenguin.co.uk/blog/multiple-uvc-cameras-on-linux/).
- Repo: `naming/linux_identity.py`, `naming/camera_identity.py`, `bandwidth/linux/uvc_bw_probe.py`, `results/windows/Gerald/RERUN_20261027.md`, `results/windows/Gerald/bw_concurrency_rerun_20261027/r08_cross_rootport_no_kiyo.json`, `results/windows/Gerald/bw_topology_rerun_20261027/topology_idle_0307Z.json`, [`topology_linux_evidence/`](topology_linux_evidence/).


## Verifier notes

Adversarial verification, 2026-11-06. No camera was opened or streamed. Sources:

- Kernel source re-read at torvalds/linux master (raw.githubusercontent.com, fetched 2026-11-06).
- Release versions re-checked with `gh api repos/torvalds/linux/compare/<tag>...<sha>`.
- xHCI 1.2 spec: Intel `extensible-host-controler-interface-usb-xhci.pdf`, converted with pdftotext.
- New read-only evidence: `wsl.exe -d Ubuntu -- sh verifier_wsl_ep_format.sh`. Script and output are in [`topology_linux_evidence/`](topology_linux_evidence/).

### Overall

Most source citations hold.

- Every first-release version in C3 (systemd v254), C4, C5 and C22 re-checked exactly.
- The xhci.c error mapping, uvcvideo alt selection, port peering and connect_type logic are as stated.
- device_add order is as stated: platform_notify runs before add_attrs.
- The AMD Raven numbers match the raw patch text for all eight ports.

However, the **load estimator in the design (section 6 and design step 6) is wrong as written**, and three domain-model claims are stated more strongly than the evidence allows.

### Errors to fix

1. **sysfs `ep_XX/wMaxPacketSize` has its multiplier bits stripped.** The formula `(w & 0x7FF) * (1 + ((w >> 11) & 3))` therefore always gives mult = 1.
   - Cause: endpoint.c `wMaxPacketSize_show` prints `usb_endpoint_maxp()`, which is `wMaxPacketSize & USB_ENDPOINT_MAXP_MASK (0x07ff)` (include/uapi/linux/usb/ch9.h:451, 659-662).
   - Effect: a 3 x 1024 B high-bandwidth camera alt reads as `0400`, so the design counts 1024 B instead of 3072 B. That is a 3x underestimate exactly where it matters.
   - Fix: take the current alt number from `bAlternateSetting`, then look up that alt's endpoint in the `descriptors` blob. `uvc_bw_probe.parse_vs_alts` already does this correctly (uvc_bw_probe.py:107-108).
   - Label: **doc** (source). Measured format: `wMaxPacketSize=0004` on the vhci root hub endpoint (`verifier_wsl_ep_format.out.txt`).
2. **`ep_XX/interval` is a decoded string (`125us`, `1ms`, `256ms`), not bInterval.**
   - The raw value is the separate hex attribute `bInterval` (`0c`). endpoint.c:76-93 uses `usb_decode_interval()`.
   - **Measured:** `interval=256ms`, `bInterval=0c` (same output file).
   - The design's `/ 2^(bInterval-1)` must read `bInterval`, or parse the string.
3. **The per-µframe formula is right only for HS (and SS) endpoints.**
   - FS/LS periodic endpoints are scheduled in 1 ms frames, and FS/LS interrupt `bInterval` is linear, not 2^(n-1).
   - FS devices directly on an xHCI root port use the FS bus instance, not the HS budget.
   - FS devices behind an HS hub cost HS split-transaction time plus TT overhead. In the Panther Point model that overhead is `TT_HS_OVERHEAD = 31+94` blocks (xhci.h).
   - So summing FS audio bytes into the 6000 B HS budget is wrong in both directions. Keep FS/LS load separate, per TT.
4. **eUSB2 and SSP isochronous endpoints can exceed 3 x 1024 B/µframe.**
   - uvcvideo moved to `usb_endpoint_max_periodic_payload()` / `max_esit_payload` (commit 0aa0b0326cc5, "eUSB2 double isochronous bandwidth support", 2025-09).
   - Laptop internal cameras on eUSB2 can declare up to 2x HS isochronous bandwidth.
   - The parser must handle the eUSB2 companion descriptor, or at least flag it.

### Claims weakened or refuted

- **C11.** "Apart from Panther Point, admission is done by controller hardware" is true for xhci-pci. MediaTek xhci-mtk also uses a software scheduler (C21), so the claim needs "and xhci-mtk".
- **C14 is weakened as written.**
  - Since **v6.17**, `uvc_fixup_video_ctrl()` clamps `dwMaxPayloadTransferSize` to the largest alt ("UVC non compliance: Reducing max payload transfer size", dev_warn_ratelimited). The change is commit 9764401bf6f8, "Fix bandwidth issue for Alcor camera"; compare places it in v6.17 and not in v6.8.
  - On Ubuntu 26.04 (7.0) and Fedora 45 (7.2), `EIO "No fast enough alt setting"` is therefore effectively unreachable for multi-alt cameras. They get the max alt instead.
  - It is still possible on Ubuntu 24.04 GA (6.8).
  - That warning in the log is a useful hint that a camera wants more than it can get.
- **C17/C26/C19 ("Intel = root port") overstate the evidence.**
  - **DMI cap.** The Linux comment quoted is incomplete. The same struct comment (xhci.h:600-605) goes on: "*The direct memory interface (DMI) also limits the total bandwidth (across all domains) that can be used*" (`DMI_BW_LIMIT_IN/OUT 3906` blocks). So even Intel has a controller-wide cap on top of the per-root-port domains. It is unlikely to bite with HS webcams, but "a different root port always fits" is not guaranteed.
  - **The xHCI 1.2 spec leaves the domain to the implementation.** §4.16.2 says "Each Bus Instance (BI) represents a 'unit' bandwidth ... or a Bandwidth Domain". The glossary and §4.6.15 add "*multiple Root Hub ports may share the bandwidth of a single BI*". So per-root-port is Intel's design choice, not an xHCI rule. This directly supports reading AMD Raven as one HS BI for all four HS ports.
  - **One measured Intel controller (8086:7A60) does not justify a vendor-wide `8086 -> root_port` row.** Intel TCSS xHCIs, Thunderbolt-controller xHCIs (8086:15xx in TB3 docks) and older PCHs are different silicon. Key the table on vid:did, and give other Intel parts an "assumed" source.
- **C20: the numbers are confirmed; the interpretation is still inferred.**
  - The raw patch lists port[1..4] HS 79% to 39%, and port[5..8] SS 90%.
  - It does **not** say whether the 0408:1040 webcam was streaming or only plugged in. A plugged-in UVC camera holds only its VC interrupt endpoint, so a 40-point drop would itself be odd; most likely something was streaming.
  - Nyman's reply (2025-04-02) only schedules testing.
  - The xHCI spec text above now makes "one shared HS BI" the natural reading, but it is still one machine. Keep it at medium.
- **C23 is weakened.** Controllers that list USB2 ports first give an HS hardware index equal to the Linux USB 2 bus port number. Intel PCH does this, and AMD Raven also shows HS = 1-4 and SS = 5-8. Only the SS indices differ. The docstring line is 22, not 16-17.
- **C25 has the right fact but the wrong citation.**
  - LP #1902934 is "dmesg is not restricted in linux-raspi kernel". It only implies that PC kernels were restricted from 20.10.
  - The default Ubuntu desktop user is in `adm`, so `journalctl -k` usually works without sudo. Measured: Gerald's WSL user `dom` is in group 4(adm) (`id`).
- **C1 is confirmed and strengthened.**
  - Measured as uid 1000: port `connect_type`/`location`, device `descriptors` and the ep attributes are mode 444. `quirks` and `authorized` are 644, so also readable by all.
  - The original script never checked modes; the verifier script does (`stat -c %a`).
- **C2 is confirmed, with a caveat.** The peering was seen on the virtual vhci_hcd. On real Intel PCHs (14 USB2 and about 10 USB3 ports), same-number default peering is usually *wrong* when ACPI `location` is absent. Treat `peer` without `location` as a guess.
- **C3, C4, C5, C7, C8, C9, C10, C12, C13, C15, C18, C21 and C22 are confirmed** against source and compare. In C22, the SS_BW fix 452af0f9ffe1 has no `Cc: stable` tag, so a 7.0 backport is unlikely unless Canonical cherry-picks it.
- **C6 is still inferred, but stronger.**
  - `connect_type`/`location` are filled in by the same `usb_acpi_find_companion_for_port` path during `device_platform_notify` (usb-acpi.c).
  - So a non-`unknown` connect_type on real hardware means the companion was bound before `device_add_attrs`. `physical_location` should then exist wherever `_PLD` does.
  - No public sighting was found.
- **C24 is confirmed.**
  - Fedora 45 was released 2026-11-03 with kernel 7.2 (kernel-7.2.15-300.fc45).
  - 7.2 reached upstream EOL on 2026-11-01, so Fedora will rebase to 7.3 soon.
  - Ubuntu 26.10 ships 7.3.
- **C28 (USB4) is consistent with source.** usb-acpi.c `usb_acpi_add_usb4_devlink()` adds a device link to the NHI for USB devices on ports that have a `usb4-host-interface` reference. Tunnelled SS devices can therefore be detected without root, through a `supplier:` link or `/sys/class/devlink`.
- **C29 and C19 are confirmed.**
  - C29: RERUN_20261027.md goal 3 table, b05 row.
  - C19: the r08 combo `c922_alt11_c930e_alt11_diff_rootports` streamed both cameras at MJPEG 1080p30 (C922 29.95 fps, `streamed: true`, `error_hr: null`).

### Missed

1. **Intel Type-C ports are split across two controllers, and the kernel will not peer them.**
   - On Tiger Lake and later laptops, a Type-C connector's SS lanes go to the TCSS xHCI and its USB 2 pair goes to the PCH xHCI. coreboot's tigerlake `xhci.c` lists TCSS with 1 USB2 / 4 USB3 ports and PCH with 10 USB2 / 4 USB3.
   - `match_location()` (port.c:623-650) peers only when `peer_hcd == hcd->shared_hcd`, that is, within one controller. So `peer` is absent for these connectors.
   - The mapper must merge across controllers by equal `location` itself.
   - An HS camera in such a USB-C port lives in the **PCH** HS domain. "Other controller first" would wrongly rank a USB-C port as another controller for an HS camera.
2. **Integrated or onboard hubs can leave no alternative port at all.**
   - Raspberry Pi 4 (VL805): bus 1 has one root port, which leads to a hardwired VIA 2109:3431 hub feeding the USB 2 halves of all four connectors (web: OctoPi #621 `usb-devices` output).
   - xHCI spec §4.24.2 also allows integrated USB2 hubs.
   - Desktop boards often put rear ports behind a hardwired Genesys or ASMedia hub.
   - The design must handle "no valid free port": say so, and suggest a lower mode (compute the largest alt that fits) or a PCIe card. Suggest a powered USB 3 hub only for USB 3 cameras.
3. **The xHCI spec anticipates Dom's exact message.**
   - §4.6.15 says Get Port Bandwidth exists so that "*system software [can] recommend topology changes to the user if they were unable to enumerate a device due to a Bandwidth Error*".
   - On Linux it is root-only (debugfs, 6.16+).
   - An optional privileged one-shot helper (polkit or sudo) could give ground truth on unknown controllers.
4. **A bandwidth signal that needs no errno and works with any frontend.**
   - OpenCV logs the STREAMON errno only at DEBUG level (cap_v4l.cpp:2027 `CV_LOG_DEBUG ... failed VIDIOC_STREAMON: errno=`). The user only sees `read()` return False.
   - After a failed start, re-read the camera's VS interface `bAlternateSetting`. If it is still 0 while another device in the same domain holds a non-zero isochronous alt, the cause is almost certainly bandwidth.
   - This works for OpenCV, GStreamer and PyAV, without root or logs.
   - For OpenCV, `OPENCV_LOG_LEVEL=DEBUG` plus stderr capture is a fallback.
5. **The learning rule is unsafe as written.** "Two cameras on different root ports streamed together, so mark root_port" proves nothing unless their combined reservation would have exceeded one domain's budget (for example, both above 50%). Only learn when the summed reserved bytes exceed 6000 B/µframe.
6. **Windows and Linux port numbers are not always different.**
   - On USB2-first controllers, Windows `USB(13)` equals Linux `usb<hs>-port13`.
   - A cross-OS key is possible for HS ports if both OSes normalise to "USB 2 root port number".
   - This informs the open key-design question.
7. **Fedora defaults are still unverified** (dmesg_restrict, journal groups). Fedora's first user is in `wheel`, which is typically allowed to read the journal (inferred).
