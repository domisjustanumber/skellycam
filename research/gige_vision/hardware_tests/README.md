# GigE Vision hardware tests (draft)

Stand-alone scripts that check whether GigE Vision cameras, the network and a host PC can do what
SkellyCam needs for synchronized multi-camera capture:

- **PTP clock sync.** IEEE 1588 clock sync between the cameras.
- **Scheduled action commands.** Exposures triggered at the same instant on every camera.
- **Clean streaming.** Uncompressed frames that arrive complete.

> **Status: draft, verified only against software-emulated cameras.** The emulators were Aravis
> `arv-fake-gv-camera-0.8` and viva-genicam's `FakeGigeCamera`. Neither implements PTP, the timestamp
> latch registers or the Action trigger sources. Paths that only real PTP cameras reach were tested by
> simulating those registers (see "What was verified"). Expect rough edges on real hardware, and please
> send back the outputs listed under "What to send back".

## Which GigE Vision versions are covered

- **PTP and scheduled actions are GigE Vision 2.0 features, not GEV 3.0 features.** These tests work with
  GEV 2.x and GEV 3.0 cameras over the normal GVSP stream protocol.
- **What GEV 3.0 adds.** GEV 3.0 (2026) adds optional RDMA streaming (GVRSP over RoCEv2, 10 GbE and faster)
  and larger control packets.
- **How GEV 3.0 is detected.** A GEV 3.0 device reports `DeviceTLVersionMajor = 3` (per LUCID)
  and is assumed to report bootstrap Version major = 3 (not confirmed; the GEV 3.0 spec text was not read)
  (corrected 2026-10-28; was stated as fact for both). The scripts report both, and GEV 3.x devices are expected to stream with 64-bit
  (extended) block ids.
- **GVRSP / RDMA is not supported.** No open-source library supports it. If a camera has
  `GevStreamingMode = GVRSP`, `viva_sync_capture_test.py --force-gvsp` switches it back to GVSP.

## Files

| Script | Needs | What it answers |
|---|---|---|
| `gev_common.py` | stdlib | Shared helpers. Keep it next to the scripts. `python gev_common.py` runs the offline selftest. |
| `gev_probe.py` | stdlib | Which cameras are there, what GEV version, and which features they have (PTP, scheduled action, action, resend, packet size, XML features). Read-only by default. |
| `udp_recv_benchmark.py` | stdlib | Can this PC (NIC, socket buffers, Python) receive 1 Gbit/s or more of GVSP-sized UDP without loss? No camera needed. |
| `gvsp_capture_report.py` | stdlib (optional viva-genicam) | Is the camera sending raw or compressed frames? Are frames complete? What pixel format and packet size, are extended ids in use, do resends work? Runs live, or on a Wireshark/tcpdump capture. |
| `gev_ptp_sync_test.py` | stdlib | Do the cameras elect one PTP master, agree on time and drift together? Do they accept immediate and scheduled ACTION_CMDs? Uses bootstrap registers. |
| `viva_sync_capture_test.py` | `pip install viva-genicam` | Uses GenICam features to enable PTP and stream from every camera. Measures the device-timestamp spread across cameras in free-run, and the exposure-start spread when scheduled actions trigger the frames. Writes a CSV of every frame. |

**Requirements and running the scripts:**

- **Where they live.** In the SkellyCam repo the scripts are in `research/gige_vision/hardware_tests/`
  (they moved there from `skellycam/system/diagnostics/gige/` on 2026-10-28 and are no longer part of the
  `skellycam` package). From the repo root, run them as
  `python research/gige_vision/hardware_tests/<script>.py ...`. The commands below are written as
  `python <script>.py`, i.e. run from inside this folder (or from your copy of it on the test PC).
- Every script runs directly: `python research/gige_vision/hardware_tests/<script>.py --help`.
- Every script has `--selftest`, which checks packet encoding/decoding without any network access.
  The pytest wrapper runs all of them: `python -m pytest research/gige_vision/hardware_tests/tests -q`
  (beartype is no longer applied automatically now that the scripts are outside the package).
- They need Python 3.9 or newer and nothing from SkellyCam. Copy the whole `hardware_tests/` folder to the
  test PC.
- viva-genicam (MIT) ships wheels for Windows x64, macOS arm64 and Linux x86_64. It was tested with
  version 0.10.0.

**Exit codes:**

- **0** means no check failed.
- **1** means at least one check FAILed.
- **2** means there was nothing to test: no camera found, a missing dependency or bad arguments.

**Result labels:**

- **PASS**: supported and working.
- **FAIL**: supported or required, but misbehaving.
- **SKIP**: the camera does not support or implement it, or a prerequisite failed.
- **WARN**: it works, but something is off.
- **INFO**: a measurement, with no judgement.

## Before you start (all operating systems)

1. **Close vendor viewers.** Only one application can control a camera, so close pylon Viewer,
   SpinView, ArenaView, Vimba Viewer, eBUS Player, SkellyCam and similar programs first.
2. **Use one subnet.**
   - Give the camera NIC an address on the cameras' subnet.
   - Cameras without DHCP fall back to link-local 169.254.x.x/16. Either give the NIC an address in that range
     (Windows and macOS do this automatically after about a minute), or set persistent static IPs on the
     cameras with the vendor IP tool and a matching static IP on the NIC.
   - `gev_probe.py` warns when a camera is not on any NIC's subnet.
   - With several NICs on 169.254.0.0/16, pass `--iface <NIC IP>`.
3. **PoE.** Use a PoE switch or injectors with enough power budget (802.3af gives up to 15.4 W per port;
   check the camera datasheet).
4. **Switch.** PTP messages are multicast to 224.0.1.129 on UDP 319/320, and the cameras elect a
   master among themselves, so no host master is needed.
   - An **unmanaged** switch is fine.
   - On a **managed** switch, **disable IGMP snooping** (Basler KB: PTP fails with IGMP snooping on), or use a
     PTP-aware (transparent-clock) switch.
   - Keep all cameras on one switch and one subnet.
   - After changing switch settings, **power-cycle the cameras**: some stay stuck as Master.
5. **Jumbo frames (recommended).**
   - Set the NIC MTU to 9000 and make sure the switch supports jumbo frames.
   - Then test with `gvsp_capture_report.py --packet-size 8192 --test-packet`.
   - Windows: Device Manager, then the adapter, then Advanced, then "Jumbo Packet" = 9014.
   - Linux: `sudo ip link set dev <nic> mtu 9000`
   - macOS: `sudo ifconfig <enX> mtu 9000`, or System Settings, then Network, then the adapter, then
     Details, then Hardware, then MTU.
6. **Socket receive buffers.** A frame arrives as one burst of packets, and a small buffer drops the
   tail. In the emulator tests, Linux's capped buffer completed only 23 of 77 frames in one run
   (73 of 76 and 64 of 76 in two others; results varied a lot), while a 64 MiB buffer completed all 76
   frames (corrected 2026-10-28; was "completed only 23 of 77 frames" with the other runs omitted).
   - **Linux:** `sudo sysctl -w net.core.rmem_max=67108864`. To keep it, put the line
     `net.core.rmem_max=67108864` in `/etc/sysctl.d/90-gige.conf`.
     - Alternatively run the scripts as root with `--force-rcvbuf`.
     - Optionally enlarge the NIC ring: `sudo ethtool -G <nic> rx 4096`.
   - **macOS:** `sudo sysctl -w kern.ipc.maxsockbuf=33554432` (lost at reboot). macOS can't raise it
     beyond its boot-time maximum.
   - **Windows:** large `SO_RCVBUF` requests are honoured. In the NIC's Advanced properties:
     - set "Receive Buffers" to the maximum;
     - keep "Interrupt Moderation" on;
     - turn off "Energy Efficient Ethernet" / "Green Ethernet".
   - The scripts report the effective buffer and print **WARN ... CAPPED** with the right command when the OS
     limits it.
7. **Firewall.** The camera's video stream and some discovery replies are unsolicited inbound UDP, so a
   firewall silently drops them. The symptom is "found the camera but received 0 packets".
   - **Windows** (admin PowerShell, adjust the python.exe path):
     ```powershell
     New-NetFirewallRule -DisplayName "GigE Vision tests" -Direction Inbound -Action Allow -Protocol UDP `
       -Program "C:\Path\To\python.exe" -RemoteAddress 169.254.0.0/16,LocalSubnet -Profile Any
     ```
     - Also accept the "allow Python to communicate" prompt on first run.
     - To get a fixed stream port that you can open by port instead, use `--port 50010`.
     - Vendor filter drivers (pylon GigE Vision Filter Driver, eBUS Universal Pro) can hide packets from
       sockets and Npcap. Disable them on the camera NIC while testing.
   - **Linux:** with ufw, run `sudo ufw allow in on <nic>`. With firewalld, run
     `sudo firewall-cmd --zone=trusted --change-interface=<nic>`.
   - **macOS:** System Settings, then Network, then Firewall, then Options: allow incoming connections for
     the Python you use, or turn the firewall off for the test.

## Running the tests (suggested order)

**Collecting the outputs.** Collect everything in one folder.

Linux/macOS:

```bash
mkdir -p gige_results
```

Windows PowerShell:

```powershell
mkdir gige_results
```

**Appending a log.** Add the matching suffix to any command below to keep a log of its console output:
- bash: `2>&1 | tee gige_results/<name>.log`
- PowerShell: `2>&1 | Tee-Object gige_results\<name>.log`

### 0. Offline selftest (any machine, no camera)

From the SkellyCam repo root:

```
python research/gige_vision/hardware_tests/gev_probe.py --selftest
python research/gige_vision/hardware_tests/viva_sync_capture_test.py --fake-cameras 1 --duration 3    # dry run with viva's emulator (needs viva-genicam)
```

Or, inside this folder / your copy of it on the test PC:

```
python gev_probe.py --selftest
python viva_sync_capture_test.py --fake-cameras 1 --duration 3    # dry run with viva's emulator (needs viva-genicam)
```

### 1. Inventory: `gev_probe.py` (read-only)

```
python gev_probe.py --json gige_results/probe.json --save-xml gige_results/xml
```

**What it does:**

- Broadcasts discovery on every IPv4 interface, or unicasts with `--ip A --ip B`.
- For each camera, reads the bootstrap registers and downloads the GenICam XML. The download is
  read-only, using READMEM.
- Prints a table with one row per camera: GEV version, 1588 (PTP) support, PTP enabled/state, scheduled
  action, action, packet resend, tick frequency, packet size, extended ids, and whether TriggerSource has
  Action1.
- Lists the PTP feature names in the XML:
  - SFNC names: `PtpEnable`/`PtpStatus`/`PtpDataSetLatch`/`PtpOffsetFromMaster`
  - deprecated names: `GevIEEE1588*`
  - vendor names: `PtpMode`, `PtpSlaveOnly`
- Also lists the timestamp-latch, action, compression and transport-version features (`DeviceTLVersionMajor`,
  `GevStreamingMode`), and the supported pixel formats.
- The last line per camera says whether the PTP + scheduled-action prerequisites are all there.

`--enable-ptp --ptp-wait 30` changes camera state: it sets the IEEE 1588 enable bit and shows the
Master/Slave election. The bit stays set until the camera is power-cycled.

### 2. Host receive capacity: `udp_recv_benchmark.py`

```
python udp_recv_benchmark.py --json gige_results/bench_local.json
```

**Local mode** runs a paced sender and a receiver on this PC. It measures the Python and OS cost per
packet. 1 GbE at line rate is about 81,000 packets/s at MTU 1500 and about 13,800 at MTU 9000.

**Two-PC mode** is the realistic test: real NIC, switch and MTU. Put a second PC on the camera switch.

On the capture PC:

```
python udp_recv_benchmark.py --role receiver --port 50000 --max-runs 2 --json gige_results/bench_rx.json
```

On the other PC:

```
python udp_recv_benchmark.py --role sender --target <capture PC IP> --port 50000 --sizes 1472,8972 --rates 1000 --seconds 5
```

**PASS** means at most 0.1 % lost at the paced rate. A WARN about a capped socket buffer explains most
losses.

### 3. Raw or compressed? Complete frames? `gvsp_capture_report.py`

**Live, per camera:**

```
python gvsp_capture_report.py --ip <cam IP> --seconds 5 --json gige_results/capture_<cam>.json --save-frame gige_results/frames
python gvsp_capture_report.py --ip <cam IP> --seconds 5 --packet-size 8192 --test-packet --json gige_results/capture_<cam>_jumbo.json
```

**What the live mode does:**

- Takes control of the camera, points stream channel 0 at this PC, and runs AcquisitionStart. The command
  is resolved from the camera XML by a tiny built-in resolver.
- Receives the stream and requests lost packets with PACKETRESEND.
- Restores every register it changed.
- If the camera's AcquisitionStart is too complex for the built-in resolver, the script says so. Then add
  `--control viva` (needs viva-genicam), or use the pcap mode.

**From a capture.** Use this to cross-check the live result: Wireshark sees the wire, so it is unaffected
by Python receive limits. Capture while any program streams. `-s 128` keeps only the headers, which is
enough for the report.

- Linux/macOS: `sudo tcpdump -i <nic> -s 128 -w gev.pcap udp`
- Windows: `"C:\Program Files\Wireshark\dumpcap.exe" -i <nic> -s 128 -w gev.pcapng -f udp`

Then analyse it:

```
python gvsp_capture_report.py --pcap gev.pcapng --tick-hz 1000000000 --json gige_results/capture_pcap.json
```

**What the report shows:**

- **Verdict:**
  - **UNCOMPRESSED**: IMAGE payload, standard PFNC pixel format, full-size frames.
  - **COMPRESSED**: JPEG, JPEG 2000 or H.264 payload types.
  - **LIKELY-COMPRESSED**: a custom or vendor pixel format (for example LUCID `QOI_*`), or frames smaller
    than the pixel format implies.
  - **VENDOR-SPECIFIC**: a device-specific payload type.
  - **CONTAINER**: multipart or GenDC.
- **Frame and packet details:**
  - complete, incomplete and never-seen frames;
  - packet size and whether jumbo frames are in use;
  - extended-id usage;
  - resend statistics;
  - device timestamp deltas and the device frame rate.
- **OpenCV hint.** For Bayer formats the report gives the OpenCV demosaic code. PFNC `BayerRG8` decodes
  with `cv2.COLOR_BayerBG2BGR`, because OpenCV names the pattern by the second row.
- **Pass mark.** The test passes when at least 99 % of frames are complete (`--min-complete`).

### 4. PTP + action commands over raw GVCP: `gev_ptp_sync_test.py`

```
python gev_ptp_sync_test.py --enable-ptp --duration 60 --json gige_results/ptp.json
```

**What it does (all cameras, or `--ip ...`):**

1. Checks the IEEE 1588 capability.
2. With `--enable-ptp`, sets the PTP enable bit. It stays on at exit unless you pass `--restore-ptp`.
3. Waits up to `--ptp-timeout` for exactly one Master and the rest Slave. With `--external-master`, all
   Slave is accepted.
4. Checks the timestamp latch.
5. Latches every camera clock every 0.25 s for `--duration`, with host clock reads bracketing each latch.
   It reports the inter-camera offset and drift:
   - PTP-synced cameras drift about 0 ppm against each other.
   - Free-running clocks drift by 1 to 50 ppm and usually differ by seconds.
   - The latch resolves offsets only to about half a GVCP round trip, typically tens to hundreds of µs.
     It answers "are the clocks synchronized", not "to how many µs". Test 5 measures the µs-level spread.
6. Writes action keys to the bootstrap action registers (restored at exit) and sends four ACTION_CMDs:
   - one with a wrong key, which must be ignored;
   - an immediate one, which needs ACK SUCCESS from every camera;
   - one scheduled 500 ms ahead in camera ticks, which needs ACK SUCCESS;
   - one scheduled 1 s in the past: ACK ACTION_LATE, or SUCCESS if the vendor executes late actions
     immediately.

**Options:**

- `--action-dest`: `auto` (subnet broadcast of the camera NIC), `broadcast`, `unicast`, or an IP.
- `--device-key`, `--group-key`, `--group-mask`.

The final "verdict" lines summarise PTP sync and scheduled-action acceptance.

### 5. GenICam-level sync and exposure alignment: `viva_sync_capture_test.py`

```
pip install viva-genicam
python viva_sync_capture_test.py --pixel-format BayerRG8 --fps 30 --duration 30 --out gige_results/viva_freerun
python viva_sync_capture_test.py --mode scheduled-action --pixel-format BayerRG8 --fps 30 --triggers 300 --out gige_results/viva_scheduled
```

**Opening the cameras and enabling PTP:**

- Opens every camera, or `--ip ...` in the order given; the first camera is the reference.
- Reports the GEV version, `DeviceTLVersionMajor` and `GevStreamingMode`.
- Enables PTP with whichever feature the camera has: `PtpEnable`, `GevIEEE1588`, or `PtpMode` (with
  `--ptp-mode`, default Auto).
- Latches with `PtpDataSetLatch` if present, reads `PtpStatus` by name and checks `PtpOffsetFromMaster`.
- PTP is enabled **before** streams open, because some cameras change tick frequency when PTP starts.
- Options:
  - LUCID: `--ptp-slave-only` makes every camera except camera 0 a slave.
  - `--external-master` accepts an external grandmaster.

**Free-run mode:**

- Streams at `--fps` and pairs frames across cameras by device timestamp.
- Reports:
  - the spread (median, p95 and max);
  - the per-camera phase offset and frame-clock drift;
  - dropped frames, counted from block-id gaps plus incomplete frames.
- Free-running cameras have an arbitrary phase. The spread is only judged with `--expect-aligned`, after you
  have enabled a vendor PTP-synchronous free-run mode (for example Basler Synchronous Free Run or LUCID
  `AcquisitionStartMode=PTPSync`).

**Scheduled-action mode:**

- Sets TriggerSelector=FrameStart, TriggerMode=On and TriggerSource=Action1 (falling back to Action0). Also
  sets ActionSelector, ActionDeviceKey, ActionGroupKey and ActionGroupMask, and disables
  AcquisitionFrameRateEnable.
- Latches camera 0's clock and schedules actions at T0 + k/fps. Each action is sent `--lead-ms` early with
  viva-genicam `send_action` (`--action-sender stdlib` uses the built-in sender, which also reports
  ACTION_LATE).
- For every trigger it reports:
  - the exposure-start (frame timestamp) spread across cameras;
  - each camera's lag behind the scheduled time.
- **PASS** when p95 spread ≤ `--max-spread-us` (default 100 µs). For reference, the sample output in LUCID's app note
  implies about 9 µs across 7 cameras (our arithmetic from its printed timestamps; LUCID states no figure)
  (corrected 2026-10-28; was "LUCID's app note shows"), and Allied Vision reports under 1 µs between camera clocks.
- Keep the exposure time below the trigger period. The script warns about this.
- Many cameras queue only 1 to 4 scheduled actions; `gev_probe.py` shows the queue size.

**Outputs:**

- `frames.csv`: one row per frame. Device timestamp ticks and ns, block id and status are in separate
  columns from the host receive time.
- `summary.json`
- Every feature it changed is restored at exit. PTP stays on unless `--restore-ptp`.

## What to send back

Zip the `gige_results/` folder. It holds:

- `probe.json` and `xml/` (the camera XML files);
- `bench_*.json`;
- `capture_*.json` (and the `.pcapng` if it is small);
- `ptp.json`;
- the `viva_*` folders (`summary.json`, `frames.csv`);
- any `.log` files.

Please add:

- camera vendor, model and firmware;
- switch model, and whether IGMP snooping is on;
- NIC model, MTU and driver;
- OS version;
- how the cameras are powered;
- anything you changed between runs.

## State changes at a glance

| Script | Changes | Undone at exit? |
|---|---|---|
| `gev_probe.py` | nothing (only with `--enable-ptp`: the PTP enable bit) | PTP bit stays on |
| `udp_recv_benchmark.py` | nothing on cameras | - |
| `gvsp_capture_report.py` (live) | control privilege, stream channel 0 destination/port/packet size, 64-bit block id enable, TLParamsLocked, AcquisitionStart/Stop | yes |
| `gev_ptp_sync_test.py` | control privilege, PTP enable bit (`--enable-ptp`), bootstrap action keys | keys yes; PTP only with `--restore-ptp` |
| `viva_sync_capture_test.py` | control privilege, PTP features, PixelFormat, trigger/action/frame-rate features | yes; PTP only with `--restore-ptp` |

If a script is killed, the camera drops control after its heartbeat timeout (usually 3 s). Settings
that were not restored stay until the camera is power-cycled, unless they were saved to a user set
(these scripts never save user sets).

## What was verified (and what was not)

**Verified on Windows 11 (Python 3.9, 3.10 and 3.12) and in Docker Ubuntu 24.04 (Python 3.12):**

- Every `--selftest` and `--help`.
- tshark 4.2.2 decodes the generated ACTION_CMD (immediate and scheduled), PACKETRESEND (16- and 64-bit
  block ids), READREG, WRITEREG, READMEM and DISCOVERY packets, and the synthetic GVSP standard and
  extended-id streams, as intended.
- On a real Aravis-fake capture, tshark and this report agree on leader and trailer counts, payload type,
  pixel format and size.
- Against **Aravis `arv-fake-gv-camera-0.8`** (reports GEV 0.0, no capabilities): every script ran cleanly
  without crashing. PTP, latch and action checks SKIP. Live and pcap capture worked. A capped Linux
  receive buffer gave incomplete frames, which were correctly reported as FAIL. `SO_RCVBUFFORCE` fixed it.
- Against **viva-genicam `FakeGigeCamera`** (GEV 2.0, no 1588 or action capability bits, but it ACKs
  actions with matching keys):
  - discovery, probe and XML download;
  - live capture with PACKETRESEND recovery of dropped packets;
  - immediate ACTION_CMD ACKs, and the wrong-key ACTION_CMD being ignored;
  - viva free-run and scheduled-action dry runs (`--skip-trigger-config`).
- Multi-camera runs on a dedicated Docker network, with emulators in separate containers.
- **Simulated paths** (scratch harnesses that inject PTP status and capability registers and synthetic
  clocks):
  - PTP role settling;
  - two-Masters failure;
  - inter-camera offset and drift PASS/FAIL;
  - scheduled and late ACTION_CMD handling;
  - viva PTP lock and restore.
  - Camera-side control loss mid-capture (the emulator revokes control, as a camera does after a heartbeat
    timeout): reported as FAIL, registers restored after re-taking control, outputs still written.

**Not verified (needs real cameras):**

- Real PTP behaviour: election, lock time, offsets, vendor status naming.
- Real timestamp-latch register behaviour.
- Scheduled actions actually triggering exposures, and the measured µs spread.
- ACTION_LATE responses.
- Fire-test packets: neither emulator implements them.
- PACKETRESEND against real cameras, and the status 0x0100 / flag marker.
- GEV 3.0 devices and extended-id-only streams.
- Vendor-compressed formats.
- Performance on real 1/10 GbE NICs.
- macOS.
- The mini GenICam resolver on real camera XMLs. It handles simple register commands; otherwise use
  `--control viva`.
