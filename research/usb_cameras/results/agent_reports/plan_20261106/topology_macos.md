# USB topology and bandwidth domains on macOS (topic: topology_macos)

Plan input for the 2026-11-06 requirement: skellycam maps the USB topology, works out which cameras share periodic bandwidth, and when a concurrent open fails says *"these cameras share bandwidth and I encountered an error when attempting to open them both at the same time. Suggest moving one of those cameras to any of the following controller ports: …"*.

Written 2026-11-06 on Gerald (Windows). **No Mac was available**, so nothing macOS-side is *measured*. Every macOS fact below is **doc** (Apple SDK headers, Apple-published open source, Linux device trees for Apple hardware, libusb source), **web** (forums or blogs, including Apple-staff forum replies) or **inferred**. The only **measured** items are offline checks run here, with commands and outputs in §10. No camera was opened or streamed.

Related reports in this folder: [macos.md](macos.md) covers the macOS versions, the AVFoundation stack, identity and the MX test suite. This report covers only the topology and bandwidth-domain side, and corrects one point in it (§6.4).

---

## 1. Answers in brief

| Need | macOS answer | Admin? | Label |
| --- | --- | --- | --- |
| (a) Tree controller → root port → hubs → devices | IORegistry **IOService plane**: an xHCI controller object (e.g. `AppleT8103USBXHCI`, `AppleT6000USBXHCI`, `AppleUSBXHCITR`, `AppleIntelCNLUSBXHCI`) → port objects (all subclass **`AppleUSBHostPort`**: `AppleUSB20XHCIPort`, `AppleUSB30XHCIPort`, `AppleUSB20XHCITypeCPort`, `AppleT8103USB40XHCITypeCPort`, `AppleUSB20HubPort`, `AppleUSB30HubPort`) → `IOUSBHostDevice` → `IOUSBHostInterface`. A hub's ports hang under its hub driver (`AppleUSB20Hub`/`AppleUSB30Hub`). Read with `ioreg -a -l -w0 -p IOService` (plist) or in-process IOKit | No | doc + web |
| Camera function ↔ USB device | `AVCaptureDevice.uniqueID` = hex(`locationID<<32 \| VID<<16 \| PID`). Apple Media Engineer (Oct 2025): "We need to retain that pattern for backward compatibility". Join to the `IOUSBHostDevice` with that `locationID` | No (listing) | web (Apple staff) |
| Camera key | `USB Serial Number` / `kUSBSerialNumberString` on the `IOUSBHostDevice`, else the port path. **But** the locationID's top byte is *not* stable for PCIe/Thunderbolt-attached controllers across reboots (§5.3), so the port key must name the controller by a stable identity, not by the bus byte | No | web + inferred |
| (b) Link speed | `IOUSBHostDevice` has `USBSpeed` (tIOUSBHostConnectionSpeed: 1 FS, **2 LS**, 3 HS, 4 SS, 5 SS+ 10G, 6 SS+ 20G) and legacy `Device Speed` (0 LS, 1 FS, 2 HS, 3 SS, 4 SS+, 5 SS+x2). The port has `port-status` with the connected speed in bits 8–10 (same numbering as `USBSpeed`) | No | doc + web |
| USB 2.0 camera behind a USB 3 hub | Visible directly: the hub shows up twice (an `AppleUSB30Hub` under the SuperSpeed root port and an `AppleUSB20Hub` under the HS root port). The camera's locationID path starts at the **HS** root port, e.g. on Apple silicon `0x0N1x…` (port 1 = HS) and not `0x0N2x…` (port 2 = SS) | No | doc + web + inferred |
| (c) Bandwidth domain | **Apple silicon built-in USB-C/Thunderbolt ports: one xHCI controller per port**, with exactly one HS root port (port 1) and one SS root port (port 2), so domain = that physical port. Everything behind a hub or dock on that port shares one HS link (USB4/TB4 docks included, because USB 2.0 is never tunnelled). **Mac mini/Studio USB-A ports: a separate PCIe xHCI** with several root ports; per-port vs per-controller sharing is unknown. **Intel Macs:** PCH xHCI (per-root-port on Intel, measured on Windows) plus Thunderbolt-controller xHCIs (`AppleUSBXHCIAR`/`TR`, two USB-C ports each). **TB3 docks/PCIe cards:** their own controller, with a new bus byte | No | doc + web + inferred |
| (d) Free ports + labels | Port objects with no `IOUSBHostDevice` child and `port-status` speed field 0. Labels: `UsbConnector` (ACPI `_UPC` type: 0 = USB2 Type-A, 3 = USB3 Type-A, 9/10 = Type-C), `UsbCPortNumber`, `UsbCompanionPortNumber` (USB2↔USB3 pairing), `UsbConnectable`, `removable`, port type bits 0–3 of `port-status` (Standard/Captive/Internal/Accessory), the node name (`usb-drd0-port-hs`, `HS01`, `SS01`), the controller class and the PCI vendor of a PCIe controller. **No ACPI `_PLD` panel/position/colour found in the IOService plane.** Apple silicon has no ACPI, so human labels such as "USB-C Back-left" need a per-model table (the Asahi Linux device trees have one) | No | doc + web + inferred |
| (e) Reserved bandwidth per endpoint | **Not exposed** in IORegistry as far as found (`kUSBBusCurrentAllocation` is bus **current** in mA, not bandwidth). Two options: (1) predict it from descriptors (largest VS alt per camera) with the repo's 80%-microframe model; (2) observe it: the UVC stack (`UVCAssistant`) logs "Stream alternate setting N" in the unified log, but `log stream` needs an admin user | No for (1); admin user for (2) | web + inferred |
| Bandwidth-failure signal | xHCI Configure Endpoint "Bandwidth Error" → IOKit `kIOReturnNoBandwidth` = **0xE00002EC** (signed −536870164; `IOReturn.h`: "bus bandwidth would be exceeded"). How this reaches AVFoundation is **undocumented and unobserved**. Reported symptoms: a black/frozen second camera with no error dialog (OBS, M1, 2021–2023), and a silently stalled session (visionOS 26.4). Detection must combine topology prediction, a zero-frame watchdog and any NSError (domain `IOUSBHostErrorDomain`, code −536870164) | No (logs: admin) | doc + web + inferred |

---

## 2. IORegistry structure (IOService plane)

### 2.1 Classes and parent chain

- **Port base class.** A port's class chain is `IORegistryEntry:IOService:AppleUSBHostPort:AppleUSBHubPort:AppleUSB20HubPort`, and its child is `IOUSBHostDevice@14110000` (class chain `IOService:IOUSBNub:IOUSBDevice`, `IOClassNameOverride = IOUSBDevice`). Under the camera's `IOUSBHostInterface@0/@1` sit `UVCAssistant@14110000` clients. **web** (Apple developer forum attachment, ioreg excerpt of a UVC device behind a USB 2.0 hub): https://developer.apple.com/forums/content/attachment/43dcce6e-3a08-465d-9b08-f7d3d76025b5
  - So **`IOServiceMatching("AppleUSBHostPort")` (or `ioreg -r -c AppleUSBHostPort`) enumerates every root and hub port, empty or not**.
- **Apple silicon root ports.** Seen on an M1 Pro/Max (`AppleT6000USBXHCI`):
  - `usb-drd1-port-hs@01100000`, class `AppleUSB20XHCITypeCPort`, `"port" = <01000000>`, `"port-status" = 0` (empty);
  - `usb-drd1-port-ss@01200000`, class `AppleT8103USB40XHCITypeCPort`, `"port" = <02000000>`, `"port-status" = 5376` (0x1500 → speed field 5 = SS+ 10 Gb/s), `"kUSBBusCurrentAllocation" = 896`;
  - its child `IOUSBHostDevice` has `"USBSpeed" = 5`, `"Device Speed" = 4`, `"locationID" = 18874368` (0x01200000), `"USBPortType" = 0`.

  **web**: https://gist.github.com/patricorgi/7138b0baa104fbe38ec113177d0a21df . The gist shows no `UsbCPortNumber`/`UsbConnector` on those nodes; that macOS version is unknown.
- **Port property keys** (Apple SDK header `IOKit/usb/IOUSBHostFamilyDefinitions.h`, SDK 11.3, lines 242–263). **doc**: https://github.com/phracker/MacOSX-SDKs/blob/master/MacOSX11.3.sdk/System/Library/Frameworks/IOKit.framework/Versions/A/Headers/usb/IOUSBHostFamilyDefinitions.h
  - `port-status` (`kUSBHostPortPropertyStatus`); `port` (`kUSBHostPortPropertyPortNumber`, value is OSData little-endian); `removable`; `UsbConnectable`; `UsbConnector`; `UsbMux`; `kUSBCompanionIndex`; `UsbCPortNumber`; `UsbCompanionPortNumber` ("OSData key to set/get the port number of the companion port"); `UsbPowerSource`; `Usb3Mode`; `kUSBBusCurrentAllocation`; `UsbHostPortOvercurrent`.
  - Controller keys: `Revision`, `UsbCompanionControllerName`, `kUSBIsochronousRequiresContiguous`, `UsbHostControllerTierLimit`.
  - Device keys: `kUSBSerialNumberString`, `kUSBContainerID`, `kUSBAddress`, `kUSBCurrentConfiguration`.
- **`port-status` bit layout** (same header, lines 99–152): bits 0–3 are the port type (`kIOUSBHostPortTypeStandard`=0, `Captive`, `Internal`, `Accessory`, `ExpressCard`); bits 8–10 are the connected speed (0 = none, 1 FS, 2 LS, 3 HS, 4 SS, 5 SS+, 6 SS+x2); plus enabled/suspended/overcurrent bits. **doc.**
- **Speed numberings differ** (pitfall). `USBSpeed` uses `tIOUSBHostConnectionSpeed`, where **Full = 1 and Low = 2**. The legacy `Device Speed` uses Low = 0, Full = 1, High = 2, Super = 3, SuperPlus = 4, SuperPlusBy2 = 5. Both the gist (5/4 for a 10 G device) and the forum attachment (`USBSpeed 3`, `Device Speed 2` for an HS camera) agree. **doc + web.**

### 2.2 The port-number key changed in macOS 26

- libusb issue #1661 reports three spellings: `"port"` on macOS ≤ 15.5; `"usb-port-number"` (plus `"usb-c-port-number"` and `"UsbCPortNumber" = 3`) on 26 beta 4; and `"port-number"` on the 26.0 RC, where `"port"` returned nothing. **web**: https://github.com/libusb/libusb/issues/1661
- libusb master's fix: the device's own `PortNum` property first; otherwise its parent's `"port"` when the OS is below 26 and `"usb-port-number"` from 26 on (`libusb/os/darwin_usb.c`, `get_device_port`, lines ~1558–1582 of master fetched 2026-11-06). **doc.**
- **Design consequence:** read `port`, `usb-port-number`, `port-number` and `PortNum`, and use the locationID nibble as the source of truth. No macOS 27 report was found (inferred: treat it as unknown).

### 2.3 locationID encoding

- 32 bits `0xBBPPPPPP`. `BB` is a controller ("bus") byte, then one 4-bit nibble per tier (the port number on that tier), ending at the first 0. `camera_identity.port_path_from_mac_location_id` implements this. **web** (forum and ioreg excerpts) + **inferred**.
- **Max 15 ports per tier and 6 tiers.** This matches the hackintosh rule that macOS has a 15-port limit per controller (Dortania: "each USB controller has it's own port limit"). **web**: https://dortania.github.io/OpenCore-Post-Install/usb/manual/manual.html
- **What `BB` is:**
  - Intel Macs' PCH xHCI shows up as `XHC1@14…`, so 0x14 is the PCI device number of the xHCI (inferred from the `@14100000` naming).
  - On Apple silicon `BB` is the DRD index (`usb-drd1` → 0x01).
  - Thunderbolt-attached PCIe controllers get high numbers. A Mac Studio M3 Ultra showed `0x22`, `0x25` and `0x26` for USB PCIe cards in TB enclosures. **web**: https://developer.apple.com/forums/thread/836729
- **Decoded forum uniqueIDs (measured offline, §10):**

  | uniqueID | locationID | Port path |
  | --- | --- | --- |
  | `0x2000000fd9009b` | `0x00200000` | bus00/2 (SS root port of controller 0) |
  | `0x12000000fd9009b` | `0x01200000` | bus01/2 |
  | `0x262000000fd9009b` | `0x26200000` | bus26/2 |

  These are consistent with "port 1 = HS, port 2 = SS" per Apple-silicon controller.

### 2.4 system_profiler and `ioreg -p IOUSB`

- `system_profiler SPUSBDataType` lists the devices on macOS ≤ 15 (15.7.9: lists only SPUSBDataType; SPUSBHostDataType returns an empty list). On **macOS 26** SPUSBDataType returns an empty list and **SPUSBHostDataType** is the only USB type listed and does show devices (26.6.2). Keys include `USBDeviceKeyVendorID`, `USBDeviceKeyProductID`, `USBKeyLocationID` and `USBDeviceKeySerialNumber`; a missing serial reads "Not Provided". **web** (GitHub Actions probe, 2026-10-12/13): https://github.com/rusty-photon/rusty-photon/pull/1500 ; Apple Community, 26.1, 2025-11-04: https://discussions.apple.com/thread/256180514 (one user says SPUSBHostDataType showed only controllers there; inconsistent).
  - **Design:** do not depend on system_profiler. It is slow (seconds), its keys changed between versions and it shows no port objects.
- `ioreg -p IOUSB` shows the USB plane: devices only, no empty ports, no port properties. It is fine for a quick human view; the mapper needs `-p IOService`.

### 2.5 Admin rights

- `ioreg`, `IOServiceGetMatchingServices` and `IORegistryEntryCreateCFProperties` read the registry as a normal user. No TCC prompt is involved because nothing is opened (inferred; widely used unprivileged by `ioreg`, FFmpeg and libusb listing).
- AVFoundation **listing** is expected not to need camera permission; **streaming** needs the Camera TCC grant, not admin ([macos.md](macos.md), inferred).
- `log stream` / `log show` (to read UVCAssistant alt-setting and error lines) need an **admin user**. For a normal user the log comes back blank. **web**: https://eclecticlight.co/2017/07/11/how-to-read-sierras-unified-log-as-a-normal-user/

---

## 3. Controller families on Macs and what shares bandwidth

### 3.1 Apple silicon built-in USB-C / Thunderbolt ports: one xHCI per port

- **Linux device trees** for Apple hardware (Asahi, upstream):
  - M1 `t8103.dtsi` defines `dwc3_0` (`usb@382280000`) and `dwc3_1` (`usb@502280000`), each with its own `atcphyN` USB2 + USB3 PHY.
  - M1 Mac Studio `t600x-j375.dtsi` ties four `usb-c-connector`s ("USB-C Back Left", "Back Left Middle", "Back Right Middle", "Back Right") one-to-one to `dwc3_0…dwc3_3`.

  **doc**: https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/apple/t600x-j375.dtsi (lines 51–220), `t8103.dtsi` lines 1021–1100.
- **Apple-silicon Thunderbolt ports normally have one port per bus** ("each of those has its own bus"), whereas Intel Macs have two ports per bus. **web**: https://eclecticlight.co/2023/02/28/getting-best-performance-from-thunderbolt-on-apple-silicon-macs-a-practical-guide/
- In macOS each controller has one HS root port (`usb-drdN-port-hs`, port 1) and one SS root port (`…-port-ss`, port 2) (gist above, web).
- **Domain:** for a USB 2.0 camera, the domain is the physical USB-C port: all HS traffic below that port shares one 480 Mb/s HS link and its 80% periodic budget. Two max-alt MJPEG cameras behind one hub on one USB-C port cannot both stream; on two different USB-C ports they never compete. **inferred** (the USB 2.0 spec model plus REPORT finding 17, measured on Windows).

### 3.2 Apple silicon USB-A ports (Mac mini, Mac Studio) and other PCIe xHCIs

- The M1 Mac mini's Type-A ports are on a **PCIe xHCI**: U-Boot commit "Type-A ports are handled by this PCIe controller" (web), and the Linux RFC "PCIe … used for the USB type-A ports" (https://lore.kernel.org/all/YRmIPL3NA4zHkReL@sunset/T/).
- The M1 Mac Studio has `port03 { /* USB xHCI */ }` on PCIe (`t600x-j375.dtsi` lines 398–402). **doc.**
- The chip vendor is not confirmed by any source found; no source places a Fresco FL1100 in the M1 mini.
- **Domain:** one controller with several root ports. Whether its root ports have separate HS periodic budgets depends on the vendor's scheduler (unknown) → **mark "same controller, unverified" until test MT3**.
- Identify the vendor through the parent `IOPCIDevice`'s `vendor-id` property (0x1B73 Fresco, 0x1B21 ASMedia, 0x1912 Renesas, 0x1106 VIA, 0x8086 Intel). That read needs no admin (inferred).

### 3.3 Intel Macs (macOS ≤ 26 only; macOS 27 is Apple-silicon-only)

- A 2018–2019 T2 MacBook Pro shows three controllers:
  - `AppleIntelCNLUSBXHCI` (PCH, 8086:A36D);
  - two `AppleUSBXHCITR` (Titan Ridge 8086:15EC, bus 0x00 and 0x01) for the USB-C ports;
  - the T2 "iBridge" bus `AppleUSBVHCIBCE`, which carries the built-in FaceTime camera at locationID `0x80200000`. That is a virtual bus, not a real USB link: exclude it from domains and suggestions.

  **web**: Android Studio test data, https://android.googlesource.com/platform/tools/base/+/001c1e04082e39cf0052a9b04c6d689ba04f870f/usb-devices/testData/mac2.txt
- **Domain:** on PCH ports, the root port (Intel per-root-port; REPORT finding 17, **measured** on Windows with Intel xHCI; transferable because the controller enforces it, **inferred**). On TB controllers, each controller serves two USB-C ports; whether those two share one periodic budget is unknown.
- Intel PCH ports carry ACPI-derived names (`HS01`, `SS01`) and `UsbConnector` from ACPI `_UPC`. **web** (Dortania).

### 3.4 Docks and hubs

- **USB4 / TB4 docks on Apple silicon:** USB 3 is tunnelled to the host xHCI, but **USB 2.0 is not tunnelled**: it runs on the cable's D+/D− pair to the host's HS root port. The USB4 host and hub definitions include a separate USB 2.0 host/hub. So every USB 2.0 camera on a TB4/USB4 dock shares the HS budget of the one host USB-C port the dock is plugged into. **web**: https://en.wikipedia.org/wiki/USB4 + **inferred**.
- **TB3 docks and PCIe USB cards:** their own xHCI over PCIe tunnelling. That gives a separate controller, a new `BB` byte and a separate domain, even on the same Mac port (forum: bus 0x22/0x25/0x26). Many TB3 docks have one xHCI with all USB ports behind one internal hub, so a dock is one domain unless it shows several controllers. **web + inferred.**
- **Low/full-speed devices** behind a hub use the hub's TT (single-TT: one per hub; multi-TT: one per port). That matters for FS audio or HID devices, **not** for HS cameras (§6.4).

---

## 4. Proposed mapper design (macOS)

### 4.1 Sources, in order

1. `ioreg -a -l -w0 -p IOService -r -c AppleUSBHostPort` → every port, with the attached device subtree as children. Stdlib `plistlib`, no admin.
   - Plus `ioreg -a -l -w0 -p IOService -r -c IOUSBHostDevice` (what `naming/macos_identity.py` already runs) for devices.
   - And the controller list: `-r -c AppleUSBXHCI` (class name to verify in MT1; the fallback is one full `ioreg -a -l -w0 -p IOService` dump walked in Python).
   - Production: ctypes on IOKit.framework (`IOServiceMatching`, `IORegistryEntryCreateCFProperties`, `IORegistryEntryGetParentEntry(kIOServicePlane)`, `IORegistryEntryGetPath`, `IORegistryEntryGetRegistryEntryID`) to avoid a subprocess and to get the **registry path** of each controller.
2. AVFoundation discovery session (External devices) → `uniqueID`, `modelID`, `localizedName`, `transportType`. Parse `uniqueID` → locationID/VID/PID (numerically, un-padded) and join to `IOUSBHostDevice.locationID`.
3. Optional descriptors for the budget model:
   - `IOUSBDeviceInterface::GetConfigurationDescriptorPtr`, which returns the OS's cached copy (inferred);
   - **not libusb enumeration**, which calls `USBDeviceOpenSeize` and sends GET_DESCRIPTOR to **every** device (`darwin_usb.c` `darwin_cache_device_descriptor`, lines ~1425–1450, **doc**). That is the same hazard as REPORT's "Enumeration touches cameras".
4. Hot-plug: IOKit `kIOFirstMatchNotification` / `kIOTerminatedNotification` on `IOUSBHostDevice` → re-map (no admin).

### 4.2 Data model

```text
Controller  id (stable, see 5.3), registry_path, class (AppleT6000USBXHCI...), bus_byte, kind (apple_drd | pci | tb_pci | t2_virtual),
            pci_vendor_id/device_id (if PCI), drd_index (Apple silicon), model_label (from table), revision
Port        registry_id, controller_id, parent_hub_device (None = root port), number (nibble), name (usb-drd0-port-hs / HS01 / ...),
            class, role (hs|ss), location_id (port's own), port_status raw + decoded {type, speed}, connector (UsbConnector),
            usbc_port_number, companion_port_number, connectable, removable, occupied (bool)
Device      location_id, vid, pid, bcdDevice, serial, product, speed (decoded USBSpeed), address, session_id, parent_port,
            is_hub, hub_tt (bDeviceProtocol 0/1/2), interfaces [class], is_uvc, avf_unique_id, avf_name, camera_key
Domain      id = f"{controller_id}/{role}-root{root_port_number}"  (HS domain for HS/FS/LS devices, SS domain for SS devices)
            scope = "port" | "controller" | "unknown->controller" (from vendor table), members [Device], free_ports [Port],
            predicted_load_ns (sum of max-alt costs of member cameras), label
```

### 4.3 Domain computation

1. For each device, walk up the ports to the root port R on controller C. Root role: an HS device whose path starts at an HS root port (on Apple silicon port 1; on Intel the `HSxx` port, matched to `SSxx` through `UsbCompanionPortNumber`).
2. HS domain = (C, R_hs). If the vendor table says the controller shares one periodic budget across root ports, the domain is (C). Defaults:
   - Apple DRD: n/a (one HS root port);
   - Intel PCH: per root port (measured on Windows);
   - everything else: **controller, unverified**.
3. SS cameras get an SS domain (C, R_ss). It is ignored for the USB 2.0 budget.
4. FS/LS devices get a TT sub-domain (hub, TT or port); they still consume HS microframe time on the parent HS link (inferred from the USB 2.0 spec).
5. Predicted load: per member camera, the largest VS alt cost (`hs_budget_model.t_iso_in_ns × mult`), because macOS, like usbvideo, picks the alt from the camera's `dwMaxPayloadTransferSize`, which these cameras pin at max (inferred, to verify in MT4). Other isochronous devices in the domain (USB audio) are flagged as "unknown reservation".

### 4.4 Free-port suggestion

- Candidates are ports with `occupied == False`, excluding:
  - type Internal or Captive;
  - `UsbConnector == 255`;
  - `UsbConnectable` false;
  - T2 virtual bus ports;
  - SS-only port objects (offer the physical connector through its HS companion instead).
- Keep candidates whose HS domain ≠ the conflicting domain and whose `predicted_load_ns + cost(moved camera) ≤ 100 000 ns`. Rank:
  1. empty root ports on other controllers (Apple silicon: another USB-C port);
  2. empty ports of a hub on another domain with no cameras;
  3. same-controller other root port, only where the vendor table says per-port.
- Group by domain and label:
  - *Apple silicon:* the per-model table keyed by `hw.model`/`target-type` + DRD index ("USB-C Back-left (controller usb-drd0)"); the table is seeded from the Asahi DTS `usb-c-connector` labels, which **are not provided by macOS**.
  - *Intel:* "USB-C/USB-A (`UsbConnector`) port HS02 on Intel PCH controller".
  - *Hub ports:* "free port 3 of 'USB2.0 Hub' (Genesys 05E3:0610) on USB-C Back-right".
- **Message example.** "C930e (046d:0843:port=…) and USB Camera (4c4a:4a55:port=…) share bandwidth (both on the USB 2.0 link of USB-C port 'Back-left', controller usb-drd0); opening both failed. Suggest moving one of those cameras to any of the following controller ports: USB-C 'Back-right' (usb-drd1, empty); USB-A ports 1–2 (PCIe xHCI, empty). Note: on a Mac laptop a moved camera may need approval under 'Allow accessories to connect'."
  - That prompt applies to Apple-silicon portable Macs on macOS 13+, for direct USB-C connections. **web**: https://www.caldigit.com/macos-ventura-and-usb-thunderbolt-device-security/ , https://www.macrumors.com/2022/06/06/usb-c-accessories-user-permission-macos-ventura/

---

## 5. Pitfalls

1. **The port-number key differs by macOS version** (§2.2). Decode the locationID instead of trusting `port`.
2. **`USBSpeed` ≠ `Device Speed` numbering** (§2.1). Full is 1 in one and Low is 2 in the other.
3. **The bus byte is not stable for hot-pluggable PCIe controllers.** On a Mac Studio M3 Ultra (macOS 26.5.2), two Elgato 4K X units behind PCIe USB cards in TB enclosures swapped uniqueIDs `0x26…` ↔ `0x25…` across a reboot with no cables moved; built-in-port swaps behaved as port keys should. **web**: https://developer.apple.com/forums/thread/836729 (Jul–Aug 2026; Apple DTS: "the reason bus location was factored into this was actually to make the uniqueID MORE stable when dealing with cheap hardware", and suggested an IOKit accessor). → The camera **port key** (`camera_identity`: `bus26/2`) is unstable there. Use a controller identity built from the controller's registry path minus volatile parts (DRD name for built-ins; PCI/TB path for others), to be tested (MT5).
4. **The PID can change with the negotiated speed** (the Elgato 4K X enumerates with different PIDs on USB 2/5G/10G; same thread, non-Apple reply). That is not an issue for USB 2.0-only webcams, but the key should tolerate it.
5. **15-port / 6-tier locationID limit.** Large hubs are internally cascaded hubs, so the path has more tiers than the user sees. Labels should say "hub X port Y" from the *visible* hub, not the internal chain.
6. **MJPEG appears as a decoded `420v` format and YUY2 as `yuvs`/`2vuy`.** Picking the "same size" format can silently choose the uncompressed mode with a bigger alt:
   - a Brio on macOS 27.0.1 behind a monitor hub logged `0xe00002ed` transaction errors and blinked until the MJPEG-backed format was chosen; UVCAssistant logged "compressed: 0/1" and "alternate setting 7" (web, 2026-10-24: https://obsproject.com/forum/threads/solved-brio-picture-blinks-in-obs-on-macos-%E2%80%94-uncompressed-stream-through-a-hub-hidden-mjpeg-format-fixes-it.196683/ );
   - see [macos.md](macos.md) for uvc-avf's 420v/yuvs finding.

   `bandwidth/macos/avf_multi_open.py` takes the first format matching the size and fps. It must record and choose by subtype.
7. **Enumeration must not touch cameras.** Never use libusb or pyusb enumeration for mapping (§4.1).
8. **Virtual and non-USB cameras** (Continuity Camera, Desk View, CMIO extensions, the T2 FaceTime camera) have no USB link: filter by `transportType == 'usb '` and a successful locationID join.
9. **USB 2.0 camera on a USB-C port through a USB 3 hub:** its domain is the HS root port of that USB-C port. The USB 3 side of the hub adds no USB 2.0 capacity.
10. **macOS 27 is Apple-silicon-only**; Intel paths (AppleUSBXHCI\* PCH/AR/TR, T2) matter only for macOS ≤ 26 users. **web**: https://mac.install.guide/macos/macos27 (and [macos.md](macos.md) §2).

---

## 6. Detecting that a failure was bandwidth (macOS)

1. **IOKit code:** `kIOReturnNoBandwidth = iokit_common_err(0x2ec)` "bus bandwidth would be exceeded" = 0xE00002EC = −536870164 signed. Neighbours: `kIOReturnNotResponding` 0x2ed, `kIOReturnIsoTooOld` 0x2ee, `kIOReturnOverrun` 0x2e8, `kIOReturnExclusiveAccess` 0x2c5, `kIOReturnNoResources` 0x2be. **doc**: https://github.com/apple-oss-distributions/xnu/blob/main/iokit/IOKit/IOReturn.h
   - UVC-stack errors appear as `Error Domain=IOUSBHostErrorDomain Code=-536870168` (kIOReturnOverrun) in UVCAssistant logs (hackintosh trace, macOS 26, web: https://www.insanelymac.com/forum/topic/363309-uvcprobefix-for-macos-tahoe-fix-broken-usb-webcam-video-and-black-screen-on-hackintosh ). By analogy a bandwidth refusal would read `Code=-536870164` (inferred).
2. **What AVFoundation shows is unknown.** The reports are a black second/third camera and no error in OBS (M1/M1 Max, 2021–2023, https://obsproject.com/forum/threads/problems-using-5-usb-cameras-in-obs-with-a-macbook-pro-m1.145681/ ; fixed by 960x540 or by moving a camera to a direct port), and a silent stall with no error or interruption notification (visionOS 26.4, https://developer.apple.com/forums/thread/823696 ). → skellycam must not wait for an error.
3. **Proposed classifier:**
   - **`bandwidth_confirmed`** if any NSError, or its `NSUnderlyingErrorKey` chain, has code −536870164 or 0xE00002EC.
   - **`bandwidth_likely`** if the camera's session is running but delivers 0 frames within T (≈2 s + 2 frame periods) **and** another streaming camera is in the same HS domain **and** the predicted load > 100%.
   - **`not_bandwidth`** if the conflict partner is in another domain, or the camera fails alone.
   - Optional with an admin user: scan `log show --last 30s --predicate 'process == "UVCAssistant" OR subsystem CONTAINS "UVC"'` for `e00002ec`, "bandwidth" or "Start Stream Failed".
4. **Correction to [macos.md](macos.md) §8:** "one MJPEG camera per USB 2.0 hub TT" mixes things up. TTs serve only FS/LS devices; HS cameras behind any HS hub (single- or multi-TT) share the hub's upstream HS link. The TT type does not change the HS camera result. **inferred** (USB 2.0 spec §11.14; the repo's own budget model treats the hub link as the unit).

---

## 7. Review of the existing drafts

- **`naming/macos_identity.py`:**
  - Correct on the uniqueID join (numeric compare, so un-padded IDs work) and on the dedupe of `ioreg -r` roots. The fake test passes (§10).
  - For topology it reads only `IOUSBHostDevice`, so it misses controllers, ports (and so empty ports) and port properties. It records `Device Speed` without decoding it.
  - Extend it, or add `bandwidth/macos/macos_usb_topology.py`, per §4. Keep both tools stdlib-only plus pyobjc for AVFoundation.
- **`camera_identity.port_path_from_mac_location_id`:** the decoding is right, but the `bus{BB}` prefix is unstable for PCIe/TB controllers (pitfall 3). Replace BB with a stable controller id from the registry path when available.
- **`bandwidth/macos/avf_multi_open.py`:**
  - Good skeleton (1 s stagger → deterministic loser; RuntimeError observer).
  - Add:
    - a topology/domain snapshot before each k;
    - time-to-first-frame and a zero-frame watchdog;
    - logging of `NSUnderlyingErrorKey` codes;
    - `AVCaptureSessionWasInterruptedNotification` and `AVCaptureDeviceWasDisconnectedNotification`;
    - choosing the format by subtype (420v = MJPEG-backed vs yuvs/2vuy) and recording which;
    - an optional `log show` capture when the user is an admin;
    - an `ioreg` snapshot taken *while streaming*, to see whether any alt or bandwidth property appears.
  - [macos.md](macos.md) separately notes it unlocks the configuration before `startRunning()`.
- **Test fixture `naming/test_macos_fake_ioreg.py`:** its synthetic `locationID 0x14140000` is Intel-style. Add an Apple-silicon fixture built from the gist (`usb-drd1-port-hs@01100000`, `port-status` 0, SS 0x1500) and a USB 3 hub with a USB 2.0 camera on the HS half.

---

## 8. Recommended tests (Mac needed; none open a camera except MT3/MT4)

| ID | Test | Decides | Human? |
| --- | --- | --- | --- |
| MT1 | `ioreg -a -l -w0 -p IOService` full dump + `-r -c AppleUSBHostPort` + `-r -c AppleUSBXHCI` on macOS 27 (Apple silicon), 26 (Apple silicon), 26 (Intel), 15. Save the raw plists | Class names, port keys per version (`port`/`usb-port-number`/`port-number`), and whether `UsbCPortNumber`/`UsbConnector`/`UsbCompanionPortNumber` exist on Apple silicon | No |
| MT2 | Plug a USB 3 hub with a USB 2.0 camera into a USB-C port; dump again | Whether the camera sits under the HS root port (port 1) and the hub appears twice; validates the domain walk | Yes (plug) |
| MT3 | Two max-alt MJPEG cameras: (a) same hub on one USB-C port; (b) on two USB-C ports; (c) on two USB-A ports of a Mac mini/Studio; (d) on a TB4 dock vs a TB3 dock. 1 s stagger, both orders (`avf_multi_open.py` extended) | Domain scope per controller family (per port vs per controller); the failure signal on macOS | Yes (wiring) |
| MT4 | During MT3, read `log show` (admin user) for UVCAssistant alt settings and error codes, plus the committed `dwMaxPayloadTransferSize` via ep0 (the [macos.md](macos.md) MX6 method) | Whether macOS also picks the max alt; the exact error code/domain that reaches AVFoundation | Yes (admin) |
| MT5 | Reboot with a TB enclosure/dock holding a camera; check whether the bus byte and registry path stay stable | Which controller identity to use in port keys and labels | Yes (reboot) |
| MT6 | Apple-silicon laptop: move a camera to a new port with "Ask for new accessories" set | Whether the suggestion message must mention the approval prompt; how an unapproved device looks in IORegistry | Yes |
| MT7 | Offline: run the mapper on MT1/MT2 plists in CI (fake-ioreg tests) | Parser regression across macOS versions | No |

---

## 9. Open questions

- What does AVFoundation actually surface when the xHCI refuses bandwidth on macOS 26/27: a runtime error (code?), a silent 0-frame session, or reduced fps?
- Do the Mac mini/Studio USB-A PCIe xHCI (vendor unknown) and the Intel Titan/Alpine Ridge xHCIs budget periodic bandwidth per root port or per controller?
- Do `UsbCPortNumber` (or HPM/Type-C nodes) give a stable physical label on Apple silicon (matching "Port 1/2/3" or the System Information receptacle number), so the per-model label table can be avoided?
- Is any ACPI `_PLD` (panel/position/colour) reachable from the IOService plane on Intel Macs? None was found.
- Does the M4/M5 Mac mini or Studio front USB-C (non-TB) sit on its own controller, or on the PCIe xHCI?
- Does macOS 27 change the port-number key again?
- Does `IOUSBHostInterface.bAlternateSetting` in IORegistry reflect the live alt while streaming (that would answer (e) without admin)?

---

## 10. Offline checks run on Gerald (measured; no Mac, no camera)

1. Fake-ioreg plumbing test of the macOS identity draft:
   `uv run --script naming/test_macos_fake_ioreg.py --out-dir C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/ed14458d-4969-4aea-a6cb-2c09fa511eeb/scratchpad/fake_ioreg`
   → `PASS 3 usb devices, deduped / PASS 2 video devices / PASS uniqueID matched for both (incl. unpadded) / PASS C922 serial key / PASS C930e port key / all_ok = True`. This shows plumbing only, not real macOS behaviour.
2. Decoding forum and gist values with `camera_identity.port_path_from_mac_location_id` (python -I one-liner):
   - `0x2000000fd9009b` → loc `0x200000`, vid `0xfd9`, pid `0x9b` → `bus00/2`; `0x12000000fd9009b` → `bus01/2`; `0x262000000fd9009b` → `bus26/2`; `0x252000000fd9009b` → `bus25/2`; `0x222000000fd9009c` → `bus22/2`;
   - `17825792` → `0x1100000` → `bus01/1`; `18874368` → `0x1200000` → `bus01/2`;
   - `port-status` 5376 → `0x1500`, speed field 5, type 0;
   - `0xE00002EC` → −536870164; `0xE00002E8` → −536870168.
3. Sources fetched into the scratchpad for line references: libusb `darwin_usb.c` (master, 2026-11-06); `IOUSBHostFamilyDefinitions.h` (SDK 11.3); Linux `arch/arm64/boot/dts/apple/{t8103.dtsi,t8103-j274.dts,t8112-j473.dts,t600x-j375.dtsi,t8103-jxxx.dtsi}`; cyme `src/profiler/macos.rs` (still parses only SPUSBDataType).

---

## Verifier notes

Adversarial check, 2026-11-06, on Gerald (Windows). No Mac, and no camera was opened, streamed or enumerated. What I re-ran or re-read:

- the SDK header `IOUSBHostFamilyDefinitions_11.3.h`, libusb master `darwin_usb.c` and the Linux Apple DTS files that the gatherer saved in the session scratchpad (`dl_sdk/`, `dl_libusb/`, `dl_dts/`);
- `uv run --script naming/test_macos_fake_ioreg.py --out-dir <scratchpad>/fake_ioreg_verify`, which prints `all_ok = True` (**measured**);
- the locationID decoder `camera_identity.port_path_from_mac_location_id`, re-run with `python -I` on the forum values and on the M4 Mac mini values below (**measured**);
- the restorekit 0.5.15 crate source (`src/dfu/port.rs`), downloaded from static.crates.io into `<scratchpad>/verif_macos/rk/`;
- each cited web page, fetched again.

### Verdicts in brief

- **Confirmed** (source re-read): C1, C2, C3, C5, C6, C8, C12, C13, C14, C15, C16, C17, C18, C21, C23, C27, C28, C29.
  - C3: `0x1500` also has bit 12 set (`kIOUSBHostPortStatusEnabled`).
  - C8: the page is `system_profiler` output. CNL PCH + Titan Ridge + T2 also matches a 2018 Mac mini, so "MacBook Pro" is not established.
  - C23: correct per the USB 2.0 spec; it is an inference, not a measurement.
  - C27: Apple's own page is https://support.apple.com/102282 . It covers USB, Thunderbolt and SD accessories, on Apple-silicon laptops only.
- **Weakened:**
  - **C4.** The legacy `Device Speed` table (Low 0 to SuperPlusBy2 5) is not in `IOUSBHostFamilyDefinitions.h`; lines 73-93 hold only `tIOUSBHostConnectionSpeed`. The legacy values come from IOUSBLib `USB.h` (`kUSBDeviceSpeed*`). The values are right; the citation is wrong.
  - **C7.** The vendor is not unknown:
    - Asahi's Nov 2022 progress report says the Type-A and non-Thunderbolt Type-C ports on Mac Studio and the iMacs are on an **ASMedia** PCIe xHCI that needs driver-loaded firmware (https://asahilinux.org/2022/11/november-2022-report/).
    - An Asahi user's `lspci` on an M1 Mac mini shows `02:00.0 USB controller: Fresco Logic FL1100 USB 3.0 Host Controller (rev 10)` (https://gist.github.com/ipatch/b3afd59b52ae6e1c84779250bd1530f1; one source, web). Bus 02 matches `&port01 { bus-range = <2 2>; }` in `t8103-j274.dts`.
    - Their per-port vs per-controller scheduling is still unknown.
  - **C9.** Eclectic Light talks about Thunderbolt buses, not USB 2.0. It corroborates per-port controllers only indirectly.
  - **C10.** The quote is accurate. The accepted answer in the same thread (ssmith_c, not Apple) says the format "has changed in the past, it might change at any time". On the positive side, the format is still in use on macOS 26.5.2 (thread 836729 shows `0x2000000fd9009b`).
  - **C11.** DTS's "isn't ACTUALLY possible" is about guaranteeing *uniqueness* (serials are not required to be unique), not about cross-reboot identity. The reboot swap was intermittent: the 2nd reboot changed nothing and the 3rd swapped the IDs.
  - **C19.** Overstated. In that thread, "move a camera to a direct port" was only *suggested*; nobody reported testing it. Only 960x540 is reported to have worked. No macOS versions are given. One case was a CalDigit TB4 hub on an M1 Max, which supports "TB4 dock = one HS domain".
  - **C20.** This is visionOS. The poster argues the hub has enough bandwidth and that the serialization is a software policy. Apple did not comment. This is weak evidence for a *bandwidth* silent stall on macOS.
  - **C22.** The claim is right (USB4 does not tunnel USB 2.0), but the cited forum thread 836729 does not mention tunnelling at all. Only the Wikipedia citation supports it.
  - **C24.** "Intel PCH per root port" comes from one Windows machine's Intel xHCI. It is not the Cannon Lake PCH in Intel Macs (inferred transfer).
  - **C25.** The source for "the log is blank for non-admin users" is a 2017 (Sierra) article; whether that holds on macOS 26/27 is unverified. Also, without admin, `OSLogStore` reads only the calling process, so it cannot read UVCAssistant lines either.
  - **C26.** The header itself defines `kUSBHostInterfacePropertyAlternateSetting = "bAlternateSetting"`. So the "does it track the live alt" test (MT4) is the obvious next step, not an open idea.
- **Refuted, or refuted as stated:**
  - **C30 and design §4.4 ("per-model label table needed").** Apple silicon exposes physical port labels in the IORegistry.
    - restorekit (crate 0.5.15, `src/dfu/port.rs` lines 1-11 and 239-270) reads, "from read-only IORegistry (no root)", each `AppleHPM` service's `RID`, `port-number` and **`port-location`** (device-tree text, doc example `"left-back"`).
    - It matches `port-number` to the `AppleUSBHostController` with the same `port-number`. That controller's `locationID & 0xff000000` is the bus byte of every device on that physical port.
    - So a label such as "left-back USB-C" can come from macOS itself, and the per-model table becomes a fallback. Label: **doc** (third-party source code; the values were not seen on a Mac here).
  - **C6 implication and §3.1 ("different USB-C ports never compete").** This does not hold for every Apple-silicon USB-C connector.
    - Twocanoes' M4 Mac mini port guide gives the per-port addresses of DFU targets: rear `0x00100000`, `0x01100000`, `0x03100000`; front `0x02110000` and `0x02120000`. It says the two front ports "share a single USB 3.1 bus".
    - Decoded here (**measured** offline), the front addresses are `bus02/1.1` and `bus02/1.2`. Both front USB-C ports therefore sit behind a hub tier under one HS root port: **one HS domain**. Source: https://twocanoes.com/knowledge-base/m4-mac-mini-port-guide/ (web).
    - The §4.3 walk handles this correctly as long as it keys on the locationID root rather than "one connector = one controller". The one-controller-per-connector rule holds for the Thunderbolt/USB4 connectors (DTS), not for the M4 mini front ports.

### Design corrections

1. **Enumerate controllers by the class `AppleUSBHostController`**, the IOUSBHostFamily base class that restorekit matches. The name `AppleUSBXHCI` is unverified and does not cover every controller.
2. **Use `AppleHPM` `port-location` + `port-number` for physical labels on Apple silicon.** Join them to the controller's `port-number` and the locationID top byte. Keep the table seeded from Asahi only as a fallback.
3. **"Free" must mean physically free, not only USB-empty.**
   - A USB-C connector holding a charger, a DP-alt-mode display or a power-only cable has no `IOUSBHostDevice` child, but nothing else can be plugged into it.
   - Check the Type-C side: the `AppleHPM` connection state and the `IOPortTransportState` nodes. macOS logs these per `Port-USB-C@N` with CC/USB2/USB3 transports (web, gist keigoi/9a9e3990...).
   - Otherwise word the suggestion as "if nothing is plugged into it".
4. **Do not trust `port-status` bits alone on macOS 26 and later.**
   - The libusb #1661 beta-4 excerpt shows `"port-status" = 5` beside `"usb-port-number" = <02000000>` and `"UsbCPortNumber" = 3`. Under the SDK 11.3 layout that decodes to type 5 (out of range) and speed 0.
   - Hackintosh reports say Tahoe changed the USB port schema beyond the port-number key: USBMap and UTBMap needed Tahoe-specific maps (web, low confidence).
   - Use "has an `IOUSBHostDevice` child" as the main occupancy signal. MT1 must record `port-status` on 15, 26 and 27.
5. **Pair the two halves of a USB 3 hub with `kUSBContainerID`** (the BOS Container ID, defined in the header) when the hub exposes it. Fall back to companion ports + VID + parent path. The message can then name one physical hub instead of a "USB2.0 Hub" and a "USB3.0 Hub".
6. **Remove "Start Stream Failed" from the bandwidth log signature.**
   - In the Tahoe UVCProbeFix thread it comes from a broken PROBE/COMMIT (Lenovo case) and a probe overrun (`-536870168`, HP case). Neither involves bandwidth.
   - Keep only `e00002ec` / `-536870164` as confirming.
   - Also observe `AVCaptureSessionRuntimeErrorNotification`. The only older multi-webcam bandwidth report I found (Qt forum, macOS 10.7/10.9, 2014) surfaced as "Runtime camera error", not as silence.
7. **"Unknown vendor ⇒ whole controller" must not empty the suggestion list.** On the 2-port FL1100/ASMedia USB-A controllers, list the other USB-A port as "may share bandwidth (unverified for this controller)" rather than dropping it.
8. **Reading descriptors carries risk.**
   - UVCAssistant is attached to the camera's interfaces as an `AppleUSBHostFrameworkInterfaceClient` user client (forum attachment). Avoid any `IOUSBHostObject` init or device open while it holds them.
   - It is unverified that creating an IOUSBLib plugin only to call `GetConfigurationDescriptorPtr` causes no bus traffic and no contention. Test this in MT1, or cache `wMaxPacketSize` per camera from a run when the camera was idle.

### Missed by the gatherer

- AppleHPM `port-location` labels (above).
- The two M4 Mac mini front USB-C ports share one HS domain behind a hub tier.
- Vendors of the PCIe xHCI: ASMedia on Studio/iMac, Fresco FL1100 on the M1 mini.
- `kUSBContainerID` for grouping a physical device.
- `bAlternateSetting` is already a defined interface property key.
- In the Brio post, UVCAssistant chose "Stream Alternate Setting 7", the largest alt, even for 720p raw. That is weak web support for "macOS picks the max alt".
- USB-C ports occupied by a charger or a display break the "free port" test.
- `OSLogStore` cannot read other processes without admin.
- macOS 26 changed more of the USB port schema than the port-number key, so MT1 must diff 15, 26 and 27.
