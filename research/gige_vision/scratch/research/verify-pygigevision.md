# Fact-check: pyGigEVision claims (verifier notes, 2026-10-25)

Repo checked: https://github.com/ladisk/pyGigEVision at 2de253135b8766c1eb752226539a16b810a1cf0f (v0.2.2, 2026-07-08 11:37 UTC).
Clone: scratchpad/research/src/verify-pygigevision/pygev. Aravis 0.8.26 clone (tag commit e977fa4e, 2023-02-17): src/verify-pygigevision/aravis.
Latest Aravis release is 0.8.36 (2026-04-26, `gh api repos/AravisProject/aravis/releases/latest`); 0.8.26 is the Debian bookworm package used in Docker.
Wireshark GVCP dissector: release-4.4 @ 40d923914bcbd1818ea5ebb3cb6b5b3b020fe875, epan/dissectors/packet-gvcp.c.

Test harness (all mine): scratchpad/research/verify-pygigevision-work/{Dockerfile,v_grab.py,v_aravis.py,v_synth.py,v_ext2.py,v_multi.py} and logs grab.log, aravis.log, aravis_noraw.log, synth.log, ext2.log, multi.log.
Image: `docker build -t verify-pygev:1 .` (python:3.12-bookworm + aravis-tools 0.8.26-1 + gir1.2-aravis-0.8).

## Results per claim
- C1 supported: pyproject L9-10 (MIT, >=3.10), L37-40 (numpy>=1.20, psutil>=5.9); PyPI JSON requires_dist matches. Classifiers list only Windows + Linux (L27-28).
- C2 supported: gvcp.py L29-41, gvsp.py L32-43 imports only stdlib + psutil/numpy. README L19 "no vendor SDKs, no GenTL producers".
- C3 supported (minor): GitHub created_at 2026-05-11T12:54:11Z, pushed 2026-07-08, 6 stars, 3 forks; 70 commits incl. 1 github-actions bot (67 by Jasa Sonc identities). PyPI: 0.0.1 (2026-05-12), 0.2.1 (2026-06-11), 0.2.2 (2026-07-08). Changelog says 0.2.1 was the "first release published to PyPI" which contradicts PyPI 0.0.1. PR #3/#4 opened 2026-10-20 by external user jacob-amodo. PR #3 raises cap only to 2448*2048 (5,013,504 px) -> 2592x1944 (5,038,848 px) still dropped.
- C4 supported: genicam.py L13-19; examples/03 L40-44 placeholder registers. README L10-17: intended as a protocol base for vendor drivers (pyTelops, pyFlir).
- C5 supported: command table gvcp.py L49-56 (no ACTION 0x0100, no EVENT); CMD_WRITEMEM defined but unused; grep finds no ptp/1588/multicast.
- C6 PARTIAL: Bayer correct (uint16 614400 B, complete 0/89). RGB8 is WRONG in claim: frames come back uint16 (480,640) 614,400 B and are flagged complete=True 89/89 (silent corruption: 1/3 of the image discarded).
- C7 PARTIAL: dropped (2048x2049, 2448x2048, 2592x1944 -> no frame; 2048x2048 OK), but not fully "silent": setup_buffer logs logger.warning (gvsp.py L142-144).
- C8 supported: FIRST_URL 'Local:arv-fake-camera.xml;10000;3e67' -> parse (10000, 15975); fetch returns 15975 bytes all zero; reading 0x10000 returns '<?xml'. Aravis arvmisc.c L1010-1032 strtoll base 16; fake camera prints %x (arvfakecamera.c L1030-1032). GenTL 1.6 Table 4-1 (sec 4.1.2.1): address and length "must be expressed in hexadecimal form without a prefix", and the "///"-less form is "compatible to the GigE Vision local format". https://www.emva.org/wp-content/uploads/GenICam_GenTL_1_6.pdf
- C9 PARTIAL: SO_RCVBUF after lib init = 425,984 in Docker; default buffers -> Mono8 1/79, Mono16 0/85 complete in 3 s (numbers vary run to run); SO_RCVBUFFORCE 32MB -> 92/92, 89/89. Aravis baseline with Docker default caps 90/90, 89/89, 90/90 BUT that uses the PF_PACKET ring (arvgvstream.c L1371-1372) because Docker grants CAP_NET_RAW; with --cap-drop NET_RAW (UDP socket path) Aravis got 81/86, 73/90, 79/89.
- C10 PARTIAL: reproduced ~100 fps complete 1080p100 Mono8 1500B per receiver process with forced buffer (~62% CPU incl. my poll loop) with a synthetic sender; did not reproduce the 2048x2048@60/9000B or Aravis-rate numbers.
- C11 supported: one process, 2 receivers: ~23-26 fps each, 112-120% CPU; two processes: 100/100 fps each, ~62% CPU each.
- C12 supported: lossless synthetic sender, 20 x 1080p Mono8 frames: spurious resend requests 84.5% (110 MB/s), 78.5% (280), 76.7% (1000); library counts all as "recovered".
- C13 supported (conditional): with extended IDs, block 65535 gap -> incomplete frame, thread alive; block 65536 gap -> struct.error "'H' format requires 0 <= number <= 65535", thread dead, get_frame None. Requires a gap check to run before the trailer (every 128 pkts or 50 ms socket idle); small frames that finish in <128 packets do not trigger it.
  Also: extended-ID resend for block 7 sent as legacy 12-byte payload with flag byte 0x01 (hex 42010040000c0001000000070000000500000005); Aravis uses a 20-byte payload with EXTENDED_IDS flag and 64-bit block id (arvgvcp.c L404-439), as does Wireshark's dissector (packet-gvcp.c L1555-1619).
- C14 supported: no read of 0x093C/0x0940/0x0944 anywhere; fake camera reports 1e9 (arvfakecamera.c L1068-1069); deltas 33,333,000-33,334,000.
- C15 supported: 85 passed in 0.32s; test.yml L16-17.
- C16 supported for 0.8.26 (arvgvfakecamera.c L157-216 switch; fake XML has 0 matches for ptp/1588/Action/Timestamp).
- C17 supported: Windows Python 3.12.13 getsockopt 65536 -> 16777216.

## Missed points
1. SCPS bit constants wrong: standard.py L33-35 SC_PACKET_SIZE_MASK=0xFFFC, DO_NOT_FRAGMENT=1<<1, FIRE_TEST=1<<0 (and test_standard.py enshrines them); Wireshark packet-gvcp.c L3825-3847: FireTest 0x80000000, DoNotFragment 0x40000000, PixelEndianness 0x20000000, PacketSize 0x0000FFFF; Aravis arvgvcpprivate.h (0.8.26) L128-133 the same.
2. Data packets that arrive before the leader are not stored (_raw_buffer None, gvsp.py L160) and the leader then replaces the buffer (L608-621), so reordering = loss.
3. PR #3 cap (2448*2048) still excludes 2592x1944.
4. Aravis comparisons in Docker run with CAP_NET_RAW use packet-socket capture, not UDP.
