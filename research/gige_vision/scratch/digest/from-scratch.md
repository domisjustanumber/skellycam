# from-scratch

## Bottom line
A from-scratch **transport** (GVCP control plus GVSP streaming) is small and well documented. I built a pure-Python, stdlib-only client in about 830 lines (`tests/gev_scratch_probe.py`). In Docker it discovered Aravis's software GigE camera (`arv-fake-gv-camera-0.8`), took control, fetched the GenICam XML and streamed **75/75 complete frames**.

There are two hard parts:
1. **GenApi evaluation.** This means turning the camera's XML description into readable and writable features.
2. **Keeping packet loss at zero.** This depends on socket receive-buffer limits and, in Python, the GIL.

PTP needs no new protocol code. It is a few bootstrap registers, or the equivalent GenApi features.

**Premise correction.** IEEE 1588 (PTP) arrived in **GigE Vision 2.0**, not 3.0. Wireshark names the capability bit `hf_gvcp_capability_1588_v2_0` (mask 0x00080000) and the enable bit `..._1588_enable_v2_0` in register 0x0954 ([packet-gvcp.c L3474-3477, L3604-3607](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L3474-3477)). GigE Vision 3.0 (released 2026-05-12) adds RoCEv2/RDMA streaming (GVRSP), per the [press release](https://www.vision-systems.com/directory/software/machine-vision-imaging-software/press-release/55377111/association-for-advancing-automation-a3-a3-officially-releases-gige-vision-30-opening-new-possibilities-in-machine-vision). Pure Python can't implement GVRSP, and none of the open-source stacks I checked support it.

## Minimum protocol surface (permalinks in notes)
- **Commands.** Codes 0x0002 through 0x0101 are listed in [Wireshark L177-197](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L177-197). Aravis's enum has neither FORCEIP nor ACTION.
- **Discovery.** The acknowledgement field offsets are in [Wireshark L2121-2195](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L2121-2195).
- **Bootstrap registers** are in Aravis [arvgvcpprivate.h L38-137](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L38-L137):
  - control-channel privilege (CCP) at 0x0A00
  - heartbeat timeout at 0x0938
  - XML URL at 0x0200
  - stream channel 0 at 0x0D00, 0x0D04 and 0x0D18
- **XML fetch.** The `Local:` URL and zip handling are in [arvgvdevice.c L1266-1397](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L1266-L1397).
- **Packet-size negotiation** (fire-test packet with do-not-fragment, binary search): [L614-784](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L614-L784).
- **Packet resend**, including the 64-bit block-ID form: [arvgvcp.c L406-440](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcp.c#L406-L440).
- **Stream headers** (GVSP, standard and extended IDs): [arvgvspprivate.h](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L132-L192).
- **Missing-packet logic:** [arvgvstream.c L659-746](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L659-L746).
- **ACTION_CMD**: device key, group key, group mask, plus a 64-bit time when flag 0x80 is set ([Wireshark L2092-2115](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L2092-2115)). Only viva-genicam implements it ([action.rs](https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/crates/viva-gige/src/action.rs#L17-L211)).

**Raw or compressed.** Frames arrive raw by default: payload type 1 is image data in a standard (PFNC) pixel format. GEV 2.0 also defines JPEG, JPEG2000 and H.264 payload types ([packet-gvsp.c L43-54](https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvsp.c#L43-54)). Every image leader packet carries a 64-bit device timestamp.

**PTP.** Controlled and read through registers:
- capability 0x0934, bit 0x00080000
- enable 0x0954, bit 0x00080000
- status 0x096C, low 4 bits
- profiles 0x0974–0x097C

A real Hikrobot XML maps `GevIEEE1588` to bit 12 of the register at 0x0954 and `GevIEEE1588Status` to 0x096C bits 31..28 ([Hikrobot.xml L51846-51900](https://github.com/valstad-shipworks/telegenic/blob/eb9de6579dde096b4a60ccead934edcc3795d6c3/tests/data/Hikrobot.xml#L51846-L51900)). Both match the Wireshark masks under GenApi's big-endian bit numbering.

## GenApi is the hard part
I counted node types in real camera XMLs (from telegenic's test data):

| XML | Nodes | SwissKnife formulas | Converters | Selectors | Availability predicates | Invalidators | Computed addresses |
|---|---|---|---|---|---|---|---|
| Hikrobot | 2165 | 283 | 58 | 41 | 406 | 370 | 513 |
| Imperx | 1386 | 402 | — | 7 | 193 | 392 | 11 |

- My toy formula translator parses 93–97% of the formulas. The failures are nested `?:`.
- Parsing is the easy part; selectors, invalidation and computed addresses are not.
- Existing evaluators are large: about 14.7k lines of C in Aravis, 11.8k lines of Rust in cameleon-genapi, 21.5k in viva-genicam's two GenApi crates.
- pyGigEVision (v0.2.2, MIT, 2026-07-08) has **no** evaluator. Its README tells users to write vendor registers themselves ([README L30-47](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/README.rst#L30-L47)).
- **Tested working:** the official EMVA `genicam` 1.6.0 wheel's NodeMap, driven through an `AbstractPort` subclass on top of my pure-Python control client (the harvesters pattern, [port.py L31-67](https://github.com/genicam/harvesters/blob/383494e36ebb80e2daa271ac0e980dde2093970c/src/harvesters/_private/core/port.py#L31-L67)). It evaluated PayloadSize and executed AcquisitionStart.
- **Wheel caveats:**
  - On Linux it needs the shared `libpython3.12.so`.
  - There is no macOS x86_64 wheel.
  - It is under the GenICam license.

## Performance (measured; scripts saved)
**Line rate at 1 GbE:** 81,274 packets/s at MTU 1500 and 13,830 at MTU 9000. At 10 GbE: 813k and 138k.

**`udp_recv_benchmark.py`, loopback:**
- At 1 Gbit/s, one Python receiver with a 16 MiB buffer has **0% drops** at about 21–34% of one core (MTU 1500) and 5–8% (MTU 9000).
- The single-thread ceiling is about 340–410k packets/s on Windows and 620–870k on Linux.
- With Linux's default buffer, MTU 9000 at 1 Gbit/s dropped **7.2%**.
- Requesting 16 MiB with `SO_RCVBUF` was silently capped to 425,984 bytes. `SO_RCVBUFFORCE` got 32 MiB ([socket(7)](https://man7.org/linux/man-pages/man7/socket.7.html)).

**Against the fake camera:**
- With the capped buffer, kernel UDP receive-buffer errors rose by 641 in 3 s, and only 3 of 53 frames were complete, at just 50 Mbit/s. Each frame arrives as one burst and the tail gets dropped.
- With the forced 32 MiB buffer: 0 errors, 75/75 frames complete.
- Aravis's C receiver kept up with a buffer sized to one frame (the same cap); its fixed default buffer also dropped packets.

**`udp_multicam_threads_benchmark.py`, several cameras in one process:**
- N receiver threads, 1 Gbit/s per simulated camera.
- With the GIL, drops at MTU 1500 reached **39–75% at 4 cameras** and 77–88% at 8.
- The same Python 3.14.0rc3 free-threaded build with `-X gil=0` dropped **0% at 8 × 1 GbE** (679k packets/s, 1.39 cores). With `-X gil=1` it collapsed again.
- SkellyCam can already run one process per camera (`WorkerMode` in `managed_worker.py`).

**Buffer limits by OS:**
- macOS caps buffers at `kern.ipc.maxsockbuf`, default 8 MiB ([xnu socketvar.h L193](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/sys/socketvar.h#L193)).
- Windows' default was 64 KiB here. Vendors ship NDIS filter drivers (Windows only) to cut CPU load ([Basler docs](https://docs.baslerweb.com/pylon-software-suite)). A from-scratch client only gets the plain socket path.
  > **Correction (2026-10-28):** the Basler page does not say "NDIS", and "only the plain socket path" is overstated. A from-scratch client cannot use vendor kernel drivers, but on Linux it can go beyond recvfrom, for example with PF_PACKET RX_RING as Aravis does (verifier C19).

## Options and effort (person-weeks)
| Option | Effort | Main risks |
|---|---|---|
| (a) Pure Python with the EMVA genicam wheel | 6–9 | GIL (use one process per camera, or Python 3.14t); buffer and firewall setup |
| (a′) Pure Python with our own GenApi | 12–18 | — |
| (b) Rust + PyO3 from scratch | 10–16 (4–6 less if reusing `cameleon-genapi`) | — |
| (b′) **Adopt/extend telegenic** or **viva-genicam** | 1–3 integration | young projects (first released 2026-04 and 2026-06), single maintainers |
| (c) C++ with nanobind/pybind11 plus the EMVA GenApi library | 9–14 | native build matrix, licensing |

Telegenic (Apache-2.0, 2.1.0, 2026-10-20) and viva-genicam (MIT, 0.10.0, 2026-10-17) are both Rust with Python bindings and already on PyPI. Telegenic lacks ACTION_CMD.

> **Correction (2026-10-28):** in row (b′) of the table above, the first-release dates are in the wrong order for the names. viva-genicam was first released in 2026-04 (crates.io 2026-04-11, PyPI 2026-04-14) and telegenic in 2026-06 (crates.io 2026-06-13, PyPI as telegenicam 2026-06-21) (verifier missed point).

## Open questions

- Behaviour on real NICs is unmeasured. Loopback has no interrupt load, no NIC ring overruns and no wire bursts at line rate. The pure-Python receiver needs re-measuring on real 1 GbE and 10 GbE links. gev_scratch_probe.py --stream-seconds and udp_recv_benchmark.py --host <ip> are provided for this.
- PACKETRESEND recovery is untested end to end: the Aravis 0.8.30 fake camera ignores resend commands. Resend latency and success need a real camera.
- Fire-test packet negotiation, the timestamp latch, IEEE1588 status and profile registers, and ACTION_CMD acknowledgements could not be exercised (the fake camera has none of them). They need a PTP-capable GEV 2.x camera.
- Why the GIL makes threaded receivers collapse even at 4 x MTU9000 (only about 56k pps in total) is not explained. The suspected cause is GIL hand-off and convoy effects with blocking recv. Untested: whether sys.setswitchinterval, larger batches or asyncio change this.
- macOS was not measured: no Mac here. The real ENOBUFS behaviour and kern.ipc.maxsockbuf headroom for 16 MiB requests are unverified.
- GigE Vision 3.0 spec contents (GVRSP details, the expanded control channel and any PTP changes) were not read. The automate.org FAQ returned 403 and the spec itself needs an A3 licence.
- Licensing of redistributing the EMVA GenApi reference library (genicam wheel, LicenseRef-GenICam-1.6) inside SkellyCam wheels was not reviewed.
- Effort estimates are based on lines of code in reference implementations and project histories, not on any SkellyCam-specific prototype. They should be refined after a spike against a real camera.
- Whether telegenic or viva-genicam work against the user's specific PTP cameras (vendor quirks, PTP feature names) is unknown. Both are under 7 months old.
- Aravis's default PF_PACKET receive path got 0 packets over loopback in the container. This is probably a loopback/BPF artifact and was not investigated on real NICs.

## Verification: Counter({'supported': 17, 'partially-supported': 3})

- [partially-supported] C6: PACKETRESEND payload: standard IDs {u16 channel, u16 block_id, u32 first(24b), u32 last(24b)}; extended IDs {u32 0, u32 first, u32 last, u64 block_id} with header flag 0x10. GVSP extended-ID header is status u16, flags u16, infos u32 (bit31 EI), block_id u64, packet_id u32.
  REASON: The layouts are correct with two nuances. (1) In the extended form, Aravis writes data[0]=0 (arvgvcp.c L429), but Wireshark dissects a u16 stream-channel index at offset 0 in both forms (packet-gvcp.c L1600-1618). So the first word is {u16 channel, u16 reserved}, not a mandatory u32 zero; Aravis just hard-codes channel 0. (2) The status u16 is in ArvGvspPacket (arvgvspprivate.h L252-255), not in the cited ArvGvspExtendedHeader (L132-145). The EI mask 0x80000000 is at L32.
  CORRECTED: Extended-ID PACKETRESEND payload is {u16 stream_channel_index, u16 reserved, u32 first_packet_id, u32 last_packet_id, u64 block_id}, with GVCP flag 0x10. Aravis always sends channel 0 by zeroing the whole first word. The GVSP extended header is status u16 (ArvGvspPacket), flags u16, packet_infos u32 (bit 31 = EI), block_id u64, packet_id u32.
  BETTER: ['https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L1597-1620', 'https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L247-L255']

- [partially-supported] C17: Socket buffer limits cause loss: Linux SO_RCVBUF is capped by net.core.rmem_max (16 MiB request -> 425,984 B) and SO_RCVBUFFORCE (CAP_NET_ADMIN) bypasses it; with the cap, MTU9000 at 1 Gbit/s dropped 7.2% (default buffer) and against the fake camera 641 kernel RcvbufErrors / 3-of-53 complete frames at only 50 Mbit/s, vs 0 errors / 75-of-75 with a forced 32 MiB buffer. macOS caps at kern.ipc.maxsockbuf (SB_MAX 8 MiB default); Windows default measured 64 KiB.
  REASON: socket(7) confirms that SO_RCVBUF is capped by rmem_max (and doubled), and that SO_RCVBUFFORCE with CAP_NET_ADMIN overrides the cap. However, the 7.2% MTU9000 drop was measured with the default 212,992 B buffer; with the capped 425,984 B buffer the same test lost 0.04%. My rerun reproduced the fake-camera result: with the capped buffer, kernel errors were 675 and 621, with 0/50 and 5/55 frames complete. The result is variable, though: the researcher's own probe B with the capped buffer got 28/58 complete. On macOS, xnu SB_MAX is 8 MiB (socketvar.h L193) and sbreserve silently clamps to sb_max (uipc_socket2.c L806-823). Both sb_max and high_sb_max are rescaled at boot from nmbclusters (uipc_mbuf.c L1481-1499), and sysctl can only raise the limit up to high_sb_max.
  CORRECTED: With Linux's default 212,992 B receive buffer, MTU 9000 at 1 Gbit/s dropped 7.2%; with rmem_max capping a 16 MiB request to 425,984 B the loss was 0.04%. Against the fake camera at about 50 Mbit/s, the capped buffer produced 400-700 RcvbufErrors per 3 s and lost most frames (0-28 complete out of 50-58 across runs). A forced 32 MiB buffer gave 0 errors.
  BETTER: ['https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_socket2.c#L806-L823', 'https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_mbuf.c#L1481-L1499']

- [partially-supported] C19: Windows vendor stacks ship NDIS filter drivers to reduce CPU load (Basler pylon GigE Vision Filter Driver, Windows only; Performance Driver deprecated in pylon 7.1); a from-scratch client is limited to the plain socket path (Basler's 'Socket Driver ... uses the Socket API').
  REASON: The Basler page says the GigE Vision Filter Driver lowers CPU load, and the text next to it states 'This driver is available for Windows only'. It says the Performance Driver was 'deprecated in pylon version 7.1', and that the Socket Driver 'uses the Socket API of the given operating system'. The page never says 'NDIS'. The inference that a from-scratch client is limited to plain sockets is overstated. Aravis already uses PF_PACKET with PACKET_RX_RING on Linux (arvgvstream.c L1227-1367). recvmmsg and AF_XDP on Linux, or RIO on Windows, are other user-space options, though I did not measure any of them.
  CORRECTED: Basler ships a Windows-only GigE Vision Filter Driver to reduce CPU load (the Performance Driver was deprecated in pylon 7.1), and its cross-platform Socket Driver uses the OS socket API. A from-scratch client cannot use vendor kernel drivers. On Linux it can still go beyond plain recvfrom, for example with PF_PACKET RX_RING as Aravis does.
  BETTER: 

## Missed points

- The EMVA genicam 1.6.0 wheel has no free-threaded (cp313t/cp314t) builds; its wheels are cp310-cp314 only. Option (a), the pure-Python transport using the genicam wheel for GenApi, therefore cannot use the measured 3.14t no-GIL receiver advantage. It has to rely on one process per camera, which is SkellyCam's default WorkerMode.PROCESS. https://pypi.org/pypi/genicam/json
- viva-genicam's own backlog says there are 'No PTP (IEEE 1588) helpers' (TC-35, 'Not planned'). JPEG, multipart and GenDC payloads are 'counted, not assembled' (TC-36). XML fetch supports only Local: URLs (TC-33). These gaps matter for the 'adopt viva' option. https://github.com/VitalyVorobyev/viva-genicam/blob/60c9c329a4175290b7065a74027c151cb0acd9ef/docs/backlog.md#L41-L44
- Telegenic contains no PTP/1588 code (grep of src/ and py_src/ at eb9de65 is empty) and no ACTION_CMD. PTP would have to be driven through generic GenApi features such as GevIEEE1588 or PtpEnable. https://github.com/valstad-shipworks/telegenic/blob/eb9de6579dde096b4a60ccead934edcc3795d6c3/src/gige/proto/gvcp.rs#L26-L46
- Aravis HEAD (482547a, meson version 0.9.3, 2026-10-22) also has no ACTION_CMD and no PTP-specific code. Its command enum stops at PENDING_ACK, so PTP in Aravis is only reachable through camera GenApi features. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L267-L281
- The standalone probe's 'frames reassembled' check passes even when no frame is complete (complete+incomplete>0). My rerun with the default buffer printed PASS with complete=0, incomplete=50. Tighten this before giving the test to users with real cameras. https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvfakecamera.c#L157-L215 (fake camera used); probe file: C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/tests/gev_scratch_probe.py L810
- 'Pure Python can't implement GVRSP' is true only in the strict sense. rdma-core ships pyverbs, Cython bindings to libibverbs and librdmacm, so a Python RoCEv2 receiver is feasible on Linux with an RDMA-capable NIC (untested). https://github.com/linux-rdma/rdma-core/tree/8009440e92f91e339ad3554b9ccf8800d05e5743/pyverbs
- On macOS, xnu rescales sb_max and high_sb_max at boot from the mbuf cluster pool, and sysctl can raise kern.ipc.maxsockbuf only up to high_sb_max. sbreserve silently clamps oversize requests rather than failing. https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_mbuf.c#L1481-L1499
- The summary has the 'young projects' dates reversed. viva-genicam's first crates.io release was 2026-04-11 and its first PyPI release 2026-04-14. Telegenic's first crates.io release was 2026-06-13 and its first PyPI release (as telegenicam) 2026-06-21. https://crates.io/api/v1/crates/viva-genicam and https://crates.io/api/v1/crates/telegenic
- In the Wireshark dissector, the extended-ID PACKETRESEND keeps a u16 stream channel index at offset 0. Aravis zeroes that whole word, so it only works for stream channel 0. A from-scratch multi-channel client should follow Wireshark's layout. https://gitlab.com/wireshark/wireshark/-/blob/98a6cfdba1ab23f3c835b17df802004bc9429040/epan/dissectors/packet-gvcp.c#L1597-1620