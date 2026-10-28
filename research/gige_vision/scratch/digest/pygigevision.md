# pygigevision

## pyGigEVision (ladisk), evaluated at commit `2de2531` / v0.2.2

**Verdict: not suitable as SkellyCam's base. Useful as MIT-licensed reference code for GVCP/GVSP packet framing.**

### Facts
- MIT license, Python >=3.10. Its only dependencies are numpy and psutil ([pyproject.toml#L37-L40](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L37-L40)).
- It implements GVCP and GVSP itself in pure Python using `socket`. It does not use a vendor SDK, GenTL/Harvesters or Aravis.
- Created 2026-05-11. Last commit 2026-07-08. PyPI has 0.2.1 (2026-06-11) and 0.2.2 (2026-07-08).
- 6 stars. About 67 of 69 commits are by one author (Jaša Šonc, Univ. Ljubljana).
- Two open PRs from 2026-10-20: [#3](https://github.com/ladisk/pyGigEVision/pull/3) raises the 2048×2048 pixel cap, and [#4](https://github.com/ladisk/pyGigEVision/pull/4) works around the macOS firewall.
- CI runs on Ubuntu and Windows with Python 3.10–3.13. There is no macOS CI.
- The 85 unit tests are all mock-based ([conftest.py](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/tests/conftest.py#L1-L2) says there are no hardware tests). I reran them: 85 passed.

### What it supports
- **Discovery:** across all network interfaces ([gvcp.py#L309-L423](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L309-L423)), plus FORCEIP.
- **Control:** READREG, WRITEREG and READMEM, with retries and PENDING_ACK handling. CCP control and a heartbeat thread.
- **GenICam XML:** download only. It does **not** parse the XML or offer feature access by name ([genicam.py#L15-L19](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L15-L19)).
- **Streaming:** a GVSP receiver with one Python thread per stream and a `recvfrom` call per packet. It does packet resend.
- **Pixel formats:** only unpacked Mono8/10/12/14/16. Any other format defaults to 2 bytes per pixel ([gvsp.py#L55-L76](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L55-L76), [L147](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L147)).
- **Timestamps:** the raw 64-bit tick count from the leader packet ([gvsp.py#L614](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L614)). It does not read the tick frequency or offer a latch.

### What it lacks
- **PTP:** no support at all. Searching for `ptp`/`1588` finds nothing.
- **Action commands:** none in the command table ([gvcp.py#L49-L56](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L49-L56)).
- **Also missing:** WRITEMEM, events, multicast, chunk data, compressed/JPEG/H.264 payloads, and multi-part payloads.
- **Payload type:** read but never checked, so every block is treated as an uncompressed image.

### Hands-on: Docker with Aravis 0.8.26 `arv-fake-gv-camera-0.8`
1. **Discovery works.** But `bootstrap()` downloads 15,975 **zero bytes** instead of the XML. The camera's URL is `Local:arv-fake-camera.xml;10000;3e67`, and `parse_first_url` reads the digit-only hex `10000` as decimal ([genicam.py#L74-L79](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L74-L79)). A unit test asserts this decimal behaviour. Aravis always parses these fields as hex ([arvmisc.c#L1010-L1032](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvmisc.c#L1010-L1032)).
2. **Frame grab works after a manual workaround**, writing hand-mapped registers.
   - With Linux default buffers: Mono8 640×480@30 gave 1 of 43 frames complete, and Mono16 gave 0 of 49.
   - Cause: the 16 MB `SO_RCVBUF` request is capped to 425,984 bytes, and the library silently ignores that ([gvsp.py#L347-L351](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L347-L351)). Its docs do mention raising the OS buffer.
   - Aravis on the same fake camera got 91/91 and 82/82 complete.
   - With a 32 MB buffer forced through `SO_RCVBUFFORCE`, pyGigEVision got 100% complete frames.
3. **BayerRG8 and RGB8 frames come back wrong.** Both arrive as uint16 arrays of 614,400 bytes (expected 307,200 and 921,600) and are never marked complete.
4. **Throughput, one camera, 32 MB buffer:**
   - 1920×1080@100 with 1500-byte packets: 197 MB/s at about 49% of one core.
   - 2048×2048@60 with 9000-byte packets: 248 MB/s at about 21% of one core.
   - With the default capped buffer, pyGigEVision got 0% complete frames in all 4 configurations. Aravis's normal UDP socket path got 94% and 90% complete at 1500-byte packets, using 8–14% CPU.
5. **Two cameras in one process:** throughput falls to about 20 fps each at 1080p100, which points to GIL contention. **Two cameras in two processes:** each gets about 100% complete frames at about 200 MB/s.
6. **Too many resend requests.** I wrote a sender that drops nothing, paced at 110 MB/s (about 1 GigE). pyGigEVision still asked for **82.6% of all packets** to be resent. It counts every packet not yet received as missing once the frame is 5 ms old ([gvsp.py#L714-L730](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L714-L730)). Aravis only flags packets below the highest one received ([arvgvstream.c#L644-L680](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvstream.c#L644-L680)).
7. **Extended-ID streams (GigE Vision 2.x):** once the block ID passes 65535 and any packet is missing, `struct.pack('>HHII')` raises an uncaught error ([gvsp.py#L754](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L754)). The receiver thread dies and `get_frame()` returns None forever, with no error reported.
8. **Frames of 5 MP or more** (2448×2048, 2592×1944) are silently dropped because of the 2048×2048 cap ([gvsp.py#L140-L145](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145)).

The fake camera does not implement PACKETRESEND, PTP or action commands, so those paths could not be tested end to end.

### Why it is not a base for SkellyCam
- **Sync:** it has none of the sync pieces (PTP, action commands, timestamp handling).
- **No feature access by name:** you can't set things like `PtpEnable` or `PixelFormat` by name. That would need a full GenICam node-map engine written first.
- **Colour cameras:** they don't work.
- **Bugs:** several correctness bugs, including the silent receiver-thread crash.
- **Maintenance:** one main author and no commits for 3.5 months.

### What is worth reusing
- multi-NIC discovery
- the FORCEIP payload layout
- the GVCP ACK and retry handling
- the pre-allocated frame buffer pattern

These are compact and readable.

## Open questions

- Behaviour against real GigE Vision 2.x/3.x cameras is untested: real NIC pacing (1/2.5/10 GbE) is less bursty than the loopback fake camera, so the actual drop rate with default Linux buffers on real hardware is unknown.
- macOS: untested. Default kern.ipc.maxsockbuf may cause the 16 MB setsockopt to fail silently, and open PR #4 suggests the macOS firewall blocks unsolicited GVSP. Needs a Mac run.
- How often real cameras enable GEV 2.x extended-ID mode by default (which would trigger the block_id > 65535 resend crash after about 11 minutes at 100 fps) has not been verified against vendor docs.
- Whether real cameras honouring PACKETRESEND would be measurably harmed by the ~80% spurious resend requests (bandwidth inflation, more drops) needs a real-camera test. The fake camera ignores resend.
- Whether the GigE Vision spec mandates hex for FIRST_URL address/size fields: I only verified Aravis's base-16 parsing, not the paywalled spec text.
- The user's premise that 'GigE Vision 3' is what enables PTP sync is outside this topic and was not verified here. pyGigEVision has no version-specific or PTP logic either way.

## Verification: Counter({'supported': 13, 'partially-supported': 4})

- [partially-supported] C6: Only unpacked Mono8/10/12/14/16 pixel formats are supported; unknown formats default to 2 bytes/pixel uint16, so BayerRG8 and RGB8 frames come back mis-sized (614400 bytes vs expected 307200/921600) and never complete
  REASON: Re-run in Docker against arv-fake-gv-camera-0.8 (aravis-tools 0.8.26-1), 640x480@30, with a 32 MB SO_RCVBUFFORCE. BayerRG8 matches the claim: dtype uint16, 614,400 bytes, 0/89 complete, with logs like 'Frame 316: 210/420 packets unrecoverable'. RGB8 contradicts the claim: frames came back as uint16 (480,640), 614,400 bytes, but were flagged complete=True for 89/89. The buffer is sized to 2 bytes per pixel (gvsp.py L147, L166-168), so packets past expected_packets are dropped while received_count still reaches expected. The caller gets a frame marked complete that is actually truncated and has the wrong dtype. That is silent data corruption, which is worse than 'never complete'.
  CORRECTED: Only unpacked Mono8/10/12/14/16 are known. Any other format is assumed to be 2 bytes/pixel uint16. BayerRG8 (640x480) arrives as a 614,400-byte uint16 array and never completes, because half the expected packets never arrive. RGB8 (640x480, 921,600 bytes) arrives as a 614,400-byte uint16 array that is flagged complete=True, which is silent corruption.
  BETTER: ['https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L164-L177', 'https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L191-L197']

- [partially-supported] C7: Frames larger than 2048*2048 pixels are silently dropped (2448x2048 and 2592x1944 not delivered)
  REASON: Confirmed with my own synthetic GVSP sender in Docker using 9000-byte packets. 2048x2048 was delivered complete. 2048x2049, 2448x2048 and 2592x1944 produced no frame. The cap is on total pixel count: anything over 4,194,304 is dropped. It is not fully 'silent', though: setup_buffer emits logger.warning('invalid dimensions ... skipping') at L142-144. Nothing reaches the caller, and get_frame just times out. Open PR #3 raises the cap only to 2448*2048 = 5,013,504, so 2592x1944 (5,038,848 px) would still be dropped after that PR.
  CORRECTED: Frames over 2048*2048 = 4,194,304 pixels are dropped: setup_buffer logs a warning (gvsp.py L140-145) and assemble returns None (L222-224). The caller gets no frame and no error. Open PR #3 raises the limit to 2448*2048, which still excludes 2592x1944.
  BETTER: ['https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145', 'https://github.com/ladisk/pyGigEVision/pull/3/files']

- [partially-supported] C9: GVSPReceiver requests a 16 MB SO_RCVBUF but silently ignores the cap; on Linux default it is 425,984 bytes, yielding 1/43 (Mono8) and 0/49 (Mono16) complete 640x480@30 frames from the fake camera, while Aravis got 91/91 and 82/82; with SO_RCVBUFFORCE 32 MB pyGigEVision got 83/83 and 88/88
  REASON: The pyGigEVision half is confirmed. The setsockopt at gvsp.py L347-351 is wrapped in contextlib.suppress, and getsockopt then reports 425,984 inside Docker. With default buffers I got 1/79 complete (Mono8) and 0/85 (Mono16) in 3 s. With SO_RCVBUFFORCE I got 92/92 and 89/89. The researcher's exact counts (1/43, 0/49, 83/83, 88/88) depend on run length, but the pattern holds. The Aravis comparison is not like-for-like. In Docker's default capability set (which includes CAP_NET_RAW), Aravis 0.8.26 uses a PF_PACKET ring socket, not a UDP socket (arvgvstream.c L1371-1372). That run gave me 90/90, 89/89 and 90/90. With --cap-drop NET_RAW, which forces the plain UDP-socket path that pyGigEVision also uses, Aravis got 81/86 (Mono8), 73/90 (Mono16) and 79/89 (RGB8). That is still far better than pyGigEVision's default, but it is not 100%.
  CORRECTED: pyGigEVision's 16 MB SO_RCVBUF request is silently capped to 425,984 B on Linux, and most frames then come back incomplete (about 1% complete for Mono8 640x480@30 on loopback). Forcing a 32 MB buffer gives 100% complete frames. Aravis 0.8.26 gets 100% only via its CAP_NET_RAW packet-socket path. On its plain UDP path it gets about 81-94% complete under the same caps.
  BETTER: ['https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvstream.c#L1371-L1372', 'https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L347-L351']

- [partially-supported] C10: With a large buffer, a single pyGigEVision receiver sustained ~197 MB/s (1080p100, 1500B packets, ~49% of one core) and ~248 MB/s (2048x2048@60, 9000B packets, ~21%) from the loopback fake camera with 100% complete frames; with default Linux buffers it delivered 0% complete frames at these rates while Aravis's UDP-socket path delivered 94%/90% at 1500B packets using 8-14% CPU
  REASON: I reproduced only the single-receiver 1080p100 case: Mono8, 1500 B packets, forced 64 MB buffer, synthetic loopback sender, receiver in its own process. It gave 100.0 fps complete at about 62% CPU, which includes my polling loop; that is about 207 MB/s and agrees with the researcher's ~197 MB/s. The default-buffer collapse agrees with my fake-camera runs. I did not reproduce the 2048x2048@60/9000B figure (248 MB/s, 21%) or the Aravis 94%/90% UDP-path rates at those sizes. The cited code (L548-574) only shows the recvfrom loop, so it does not support the numbers by itself.
  CORRECTED: With a forced large receive buffer, one pyGigEVision receiver in its own process sustained about 200 MB/s (1080p100 Mono8, 1500 B packets) with 100% complete frames on loopback, using roughly half to two-thirds of a core. The other throughput figures were not independently reproduced.
  BETTER: 

## Missed points

- The stream-channel packet-size constants in pyGigEVision are wrong, and a unit test locks them in. standard.py L33-35 defines SC_PACKET_SIZE_MASK=0xFFFC, SC_SCPS_DO_NOT_FRAGMENT=1<<1 and SC_SCPS_FIRE_TEST_PACKET=1<<0 (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/standard.py#L27-L37). The GigE Vision register uses MSB-first bit numbering. Wireshark's dissector has FireTestPacket=0x80000000, DoNotFragment=0x40000000, PixelEndianness=0x20000000 and PacketSize=0x0000FFFF (https://github.com/wireshark/wireshark/blob/40d923914bcbd1818ea5ebb3cb6b5b3b020fe875/epan/dissectors/packet-gvcp.c#L3825-L3847). Aravis agrees (https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvcpprivate.h#L126-L135). Writing SC_SCPS_FIRE_TEST_PACKET would therefore change the packet size instead of firing a test packet.
- Extended-ID (GEV 2.x) PACKETRESEND is malformed even for block ids at or below 65535. pyGigEVision always sends the legacy 12-byte payload with flag byte 0x01. Bytes captured in Docker: 42010040000c0001000000070000000500000005 (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L739-L767). Aravis sets the EXTENDED_IDS flag and uses a 20-byte payload with a 64-bit block id (https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvcp.c#L404-L439). Wireshark's dissector does the same (https://github.com/wireshark/wireshark/blob/40d923914bcbd1818ea5ebb3cb6b5b3b020fe875/epan/dissectors/packet-gvcp.c#L1555-L1619). Aravis also sends resend requests with packet_flags 0 (no ACK requested). pyGigEVision's GVCPClient.send_packetresend instead goes through _send_cmd with FLAG_ACK and waits for an ACK (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L892-L925).
- RGB8 corruption is silent. Frames come back flagged complete=True but truncated to 614,400 bytes of uint16 instead of 921,600 bytes of RGB (89/89 frames in my run). A caller that filters on info['complete'] will not catch it (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L164-L197).
- Packet reordering causes loss. Data packets that arrive before the leader are never written, because _raw_buffer is None until the leader arrives (gvsp.py L160). The leader handler then replaces the per-block buffer with a fresh one (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L608-L632).
- The FIRST_URL hex question is settled by the GenTL 1.6 standard (section 4.1.2.1, Table 4-1). The address and length in a 'local:' URL 'must be expressed in hexadecimal form without a prefix', and the form without '///' is described as 'compatible to the GigE Vision local format' (https://www.emva.org/wp-content/uploads/GenICam_GenTL_1_6.pdf, 2,893,325 bytes, fetched 2026-10-25). pyGigEVision's decimal-first parsing therefore goes against the spec.
- The Aravis baselines in Docker are not like-for-like with pyGigEVision. With default container capabilities (CAP_NET_RAW present), Aravis 0.8.26 captures through a PF_PACKET ring socket (https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvstream.c#L1371-L1372). With --cap-drop NET_RAW, Aravis's UDP path on the fake camera at 640x480@30 gave 81/86, 73/90 and 79/89 complete frames for Mono8, Mono16 and RGB8, not 100%.
- Aravis 0.8.26, used for every comparison, is the Debian bookworm package. Its tag is from 2023-02-17. The current Aravis release is 0.8.36, published 2026-04-26 (https://github.com/AravisProject/aravis/releases), so conclusions about the fake camera's limits (no PTP, no resend, no actions) apply to 0.8.26 only.
- Open PR #3 raises the pixel cap only to 2448*2048 = 5,013,504 px. A 2592x1944 frame (5,038,848 px) would still be dropped after it merges (https://github.com/ladisk/pyGigEVision/pull/3/files). Both open PRs come from an outside contributor, jacob-amodo, and have had no maintainer response since 2026-10-20.
- pyGigEVision is explicitly a protocol layer for vendor-specific drivers, namely pyTelops (Telops IR) and pyFlir (https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/README.rst#L10-L17, https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/README.rst#L63-L69). The missing GenICam node map is a design choice, not an unfinished feature, so it is unlikely to be added upstream.