# pyGigEVision deep evaluation (TOPIC_KEY=pygigevision)

Evaluated: 2026-10-25. Repo: https://github.com/ladisk/pyGigEVision
Commit evaluated: `2de253135b8766c1eb752226539a16b810a1cf0f` (2026-07-08, "Sync version to 0.2.2"; tag v0.2.2 = `169e0278`).
Permalink base used below: `PG = https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f`
Reference implementation used for comparison: Aravis 0.8.26 (`e977fa4eedc8c4f4747ff370d53621b369930fe9`), `AR = https://github.com/AravisProject/aravis/blob/0.8.26`

Local clone: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/src/pygigevision/repo`
Test scripts: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/scripts/pygigevision/` (Dockerfile, t1..t9)

## 1. Project facts

| Item | Value | Source |
|---|---|---|
| License | MIT | [pyproject.toml#L9](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L9), [LICENSE](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/LICENSE) |
| Python | >=3.10 | [pyproject.toml#L10](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L10) |
| Runtime deps | numpy>=1.20, psutil>=5.9 only | [pyproject.toml#L37-L40](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L37-L40) |
| Declared OS | Windows, Linux (no macOS classifier) | [pyproject.toml#L27-L28](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L27-L28) |
| Created | 2026-05-11 (first commit 2026-05-12) | GitHub API `repos/ladisk/pyGigEVision` (`created_at`), `git log --reverse` |
| Last commit / push | 2026-07-08 (no commits in 3.5 months as of 2026-10-25) | `git log`, GitHub API `pushed_at` |
| Tags | v0.1.0 (2026-05-14), v0.2.0 (2026-06-10), v0.2.1 (2026-06-11), v0.2.2 (2026-07-08) | `git tag`, [changelog.rst](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/docs/source/changelog.rst) |
| PyPI | 0.0.1 (2026-05-12 placeholder), 0.2.1 (2026-06-11), 0.2.2 (2026-07-08) | https://pypi.org/pypi/pyGigEVision/json |
| Authors / maintainers | Jaša Šonc, Janko Slavič (authors); + Lorenzo Capponi (maintainer). Univ. of Ljubljana (fs.uni-lj.si emails). Commit authorship: ~67 of 69 commits by Jaša Šonc (bus factor 1). | [pyproject.toml#L11-L20](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyproject.toml#L11-L20), `git log --format=%an` |
| Popularity | 6 stars, 3 forks, 2 open PRs (#3, #4, both 2026-10-20 by `jacob-amodo`, awaiting CI approval) | GitHub API |
| Status | "Development Status :: 4 - Beta" | pyproject classifiers |
| Downstream users | pyTelops (ladisk, 2 stars, pushed 2026-09-15), pyFlir (LolloCappo, 3 stars, pushed 2026-09-04) | [README.rst "Projects using"](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/README.rst), GitHub API |

Open PRs worth noting:
- #3 "Make MAX_PIXELS constant accessible and increase to 5MP" (https://github.com/ladisk/pyGigEVision/pull/3): confirms the 2048x2048 cap bites real users.
- #4 "Send first packet to disable macOS firewall filtering" (https://github.com/ladisk/pyGigEVision/pull/4): macOS GVSP reception is not working out of the box for at least one user.

## 2. Architecture / dependencies

Pure Python implementation of GVCP + GVSP over `socket`; **no** vendor SDK, **no** GenTL/Harvesters, **no** Aravis. Stated at [README.rst](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/README.rst) ("no vendor SDKs, no GenTL producers") and confirmed by imports: [gvcp.py#L29-L41](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L29-L41), [gvsp.py#L32-L43](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L32-L43). Total package source is about 2,000 lines (gvcp.py 951, gvsp.py 784, genicam.py 134, bootstrap.py 67, standard.py 37).

## 3. Feature matrix (with permalinks)

| Feature | Status | Evidence |
|---|---|---|
| Device discovery (broadcast, all NICs via psutil) | YES | [gvcp.py#L309-L423](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L309-L423); ACK parsing [L124-L182](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L124-L182). The camera IP is the UDP **source address** ([L410-L416](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L410-L416)), not the ACK's current-IP field, and results are de-duplicated by that source IP. |
| FORCEIP | YES | [gvcp.py#L425-L503](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L425-L503) |
| Register read/write (READREG/WRITEREG), float helpers | YES, one register per command | [gvcp.py#L610-L725](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L610-L725), raw [L868-L877](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L868-L877) |
| READMEM | YES (512 B chunks, 4-byte aligned) | [gvcp.py#L727-L773](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L727-L773) |
| WRITEMEM | NO: the constant is defined, but there is no method | [gvcp.py#L55](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L55); no `CMD_WRITEMEM` use anywhere (grep) |
| Retries / PENDING_ACK / stale ACK | YES | [gvcp.py#L787-L866](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L787-L866) |
| CCP exclusive control + heartbeat thread | YES (reads CCP every 2 s) | connect [L507-L581](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L507-L581) (uses `print()` for a warning at L558), heartbeat [L929-L951](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L929-L951) |
| GenICam XML download (+zip) | YES (but see URL bug below) | [genicam.py#L91-L134](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L91-L134) |
| GenICam XML parsing / feature get/set by name (Width, PixelFormat, PtpEnable...) | **NO, by design** ("Parsing the XML itself is left to the vendor driver") | [genicam.py#L15-L19](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L15-L19); example 03 hard-codes a placeholder register [examples/03_grab_one_frame.py#L40-L44](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/examples/03_grab_one_frame.py#L40-L44) |
| Standard bootstrap register constants | Minimal: CCP, heartbeat, FIRST_URL, SC0 port/packet size/delay/dest only | [standard.py#L20-L37](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/standard.py#L20-L37) |
| Stream channel setup | Manual: the user writes SC registers ([example 03 L77-L89](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/examples/03_grab_one_frame.py#L77-L89)) | |
| GVSP receive & reassembly | YES, 1 Python thread per receiver, `recvfrom` per packet, bytearray slice copy | loop [gvsp.py#L548-L574](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L548-L574), parse [L576-L606](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L576-L606), write [L156-L183](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L156-L183) |
| Extended IDs (GEV 2.x 64-bit block id) | Parsed on receive; **resend crashes** for block_id > 65535 (see T8) | [gvsp.py#L582-L592](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L582-L592), [L754](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L754) |
| Payload types | The leader `payload_type` is read but never checked, so every block is treated as an uncompressed image. No chunk data, no JPEG/H.264, no multi-part. | [gvsp.py#L608-L621](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L608-L621) |
| Packet resend | YES, sent from the stream socket; capped at 25% per check | [gvsp.py#L689-L767](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L689-L767); also `GVCPClient.send_packetresend` [gvcp.py#L892-L925](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L892-L925) |
| Pixel formats | Mono8/10/12/14/16 only (unpacked). **Unknown formats default to 2 bytes/pixel and uint16**, so Bayer*8, RGB8, YUV and packed formats are mis-sized. | [gvsp.py#L55-L76](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L55-L76), default `2` at [L147](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L147), [L226-L227](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L226-L227) |
| Max frame size | Hard cap 2048*2048 px; larger frames are silently dropped | [gvsp.py#L140-L145](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L140-L145), [L222-L224](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L222-L224) |
| Timestamps | Raw 64-bit leader timestamp in ticks (`info["timestamp"]`). The tick frequency (bootstrap 0x093C/0x0940) is not read, and there is no latch or host-clock correlation. | [gvsp.py#L614](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L614), [L673-L681](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L673-L681); offsets in Aravis [arvgvcpprivate.h#L116-L120](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvcpprivate.h#L116-L120) |
| PTP (IEEE 1588) enable/status/offset | **NONE**: no code, no constants, no docs (grep for `ptp|1588` in package/docs: 0 hits) | grep over repo |
| Action commands (ACTION_CMD 0x0100) | **NONE**: not in the command list | [gvcp.py#L49-L56](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvcp.py#L49-L56) |
| Scheduled action / event channel / multicast | NONE | grep |
| Multi-camera | One GVCPClient + one GVSPReceiver per camera; there is no camera-group abstraction | API |
| Socket buffer | Requests 16 MB SO_RCVBUF, **silently ignores failure / cap** | [gvsp.py#L347-L351](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L347-L351) |
| Packet payload size assumption | `packet_size - 8`, self-corrected on packet id 1. GVSP packet size includes IP and UDP headers (Aravis `ARV_GVSP_PACKET_UDP_OVERHEAD` = 20+8), so the initial value is off by 28 bytes. | [gvsp.py#L340](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L340), [L161-L169](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L161-L169); [Aravis arvgvspprivate.h#L215](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvspprivate.h#L215) |

### Tests and CI
- 85 unit tests, all mock-based; **no hardware or emulator integration tests** ("pyGigEVision has no hardware tests", [tests/conftest.py#L1-L2](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/tests/conftest.py#L1-L2)). I reran them in Docker (python:3.12-bookworm): `85 passed in 0.39s`.
- CI: GitHub Actions on ubuntu-latest and windows-latest, Python 3.10–3.13, plus ruff and a Sphinx -W docs build ([test.yml#L16-L17](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/.github/workflows/test.yml#L16-L17)); tag-triggered PyPI release ([release-and-publish-to-pypi.yml](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/.github/workflows/release-and-publish-to-pypi.yml)). **No macOS in CI.** The last CI runs (2026-07-08) succeeded; the PR runs from 2026-10-20 show `action_required` (not approved by a maintainer).

## 4. Hands-on tests (Docker Desktop 29.9.2, image `python:3.12-bookworm` + Debian `aravis-tools` 0.8.26)

Dockerfile (`scripts/pygigevision/Dockerfile`):
```
FROM python:3.12-bookworm
RUN apt-get update -qq && apt-get install -y -qq aravis-tools gir1.2-aravis-0.8 python3-gi iproute2
RUN pip install -q numpy psutil pytest
```
The repo is mounted read-only at /src. Each run starts `arv-fake-gv-camera-0.8 -i eth0` in the background, then runs `python -I /scripts/tN.py`.

### T1: discover + bootstrap (XML download). Discovery PASSES; XML download returns **all zeros**.
```
discover() 1.50s -> [{'ip': '172.17.0.2', 'spec_version': '0.0', 'mac': '00:00:00:00:00:00', 'manufacturer': 'Aravis', 'model': 'Fake', 'device_version': '0.8.26', ... 'serial': 'GV01', 'interface_ip': '172.17.0.2'}]
bootstrap() 0.00s xml bytes=15975     # file content: 15975 x b'\x00'
```
Root cause (T2): FIRST_URL = `b'Local:arv-fake-camera.xml;10000;3e67'` (bare hex, emitted by [arvfakecamera.c#L1030-L1032](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvfakecamera.c#L1030-L1032)). `parse_first_url` gives `('arv-fake-camera.xml', 10000, 15975)`: "10000" is read as **decimal** because `int(field, 0)` is tried first ([genicam.py#L74-L79](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/genicam.py#L74-L79)), and a unit test enshrines this behaviour ([tests/test_genicam.py#L62-L65](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/tests/test_genicam.py#L62-L65)). Aravis always parses these fields base-16 ([arvmisc.c#L1010-L1032](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvmisc.c#L1010-L1032)). Any camera whose bare-hex address has only digits 0-9 (e.g. 10000, 200000) gets the wrong address. Workaround in T2: parse base 16 and read the XML (15,975 bytes) correctly.

### T3: grab frames (registers hand-mapped from the fake XML: Width 0x100, Height 0x104, PixelFormat 0x128, AcquisitionCommand 0x124, FramePeriod 0x138)
Default Linux socket buffer (SO_RCVBUF requested 16 MB, effective **425,984** because of the rmem_max cap; failure suppressed). 640x480 @30 fps, 2 s:
```
Mono8   frames=43 complete=1  resend requested=1114 recovered=0 failed=52
Mono16  frames=49 complete=0  missing up to 235/420 packets
BayerRG8 -> first frame shape (480,640) dtype uint16 nbytes 614400 (expected 307200), complete=0 always
RGB8     -> shape (480,640) dtype uint16 nbytes 614400 (expected 921600: data truncated), complete=0
tick_frequency register (0x093C/0x0940 read raw): 1000000000; leader timestamp diffs median 33333000 ticks = 33.3 ms
```
Same config with `SO_RCVBUFFORCE` = 32 MB (test-only patch, `--cap-add NET_ADMIN`):
```
Mono8  640x480@30: frames=83 complete=83, rx latency (host recv - leader ts) ~1.8 ms
Mono16 640x480@30: frames=88 complete=88
```
Aravis baseline on the same fake camera and container (`t4_aravis_baseline.py`, GI bindings, packet-socket mode): Mono8 ok=91 bad=0; Mono16 ok=82 bad=0; n_missing_packets=0.

### T5: throughput, single camera (4 s each, Mono8)
pyGigEVision with forced 32 MB buffer:

| config | fps achieved | complete | MB/s | CPU (one core) |
|---|---|---|---|---|
| 1280x1024@90, pkt 1500 | 86.8 | 347/347 | 113.7 | 32% |
| 1920x1080@100, pkt 1500 | 95.2 | 381/381 | 197.5 | 49% |
| 1920x1080@100, pkt 9000 | 99.8 | 399/399 | 206.8 | 20% |
| 2048x2048@60, pkt 9000 | 59.2 | 237/237 | 248.5 | 21% |

Same rates with the **default** capped buffer (fair comparison, `--cap-drop NET_RAW` so Aravis uses its standard UDP socket path):

| config | pyGigEVision complete | pyGigEVision CPU | Aravis ok/bad | Aravis CPU |
|---|---|---|---|---|
| 1280x1024@90/1500 | 0/318 (222,352 pkts resend-requested) | 53% | 307/18 | 8% |
| 1920x1080@100/1500 | 0/354 | 85% | 351/41 | 14% |
| 1920x1080@100/9000 | 0/359 | 19% | 23/362 | 6% |
| 2048x2048@60/9000 | 0/213 | 19% | 1/236 | 7% |

(Aravis's default on Linux with CAP_NET_RAW is a packet socket, which did not see the loopback traffic: 0 frames. Both receivers suffer under the capped buffer at 9000-byte packets on loopback.)

Caveat: the fake camera bursts packets unpaced over loopback ([arvgvfakecamera.c#L342-L380](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvfakecamera.c#L342-L380)), which is harsher than a real 1/2.5/10 GbE NIC.

Windows host check (Python 3.12.13): default SO_RCVBUF = 65536, and after requesting 16 MB it reads back 16777216, so the request is honored on Windows.

### T6: two cameras, one process (dummy0 + eth0, two fake cameras, forced 32 MB buffers)
```
1280x1024@60 pkt1500: GV01 35.0 fps (132/140 complete), GV02 39.5 fps (148/158); process CPU 115%
1920x1080@100 pkt1500: 20.0 / 20.2 fps (71/80, 71/81); CPU 114%
1920x1080@100 pkt9000: 87.8 / 84.2 fps (310/351, 289/337); CPU 114%
```
These numbers point to the GIL limiting receive. Two cameras in one process give less total throughput than one camera alone at 1500-byte packets.

Two cameras in **two processes** (explicit IPs):
```
1280x1024@60/1500: 225/225 and 219/219 complete, 21% CPU each
1920x1080@100/1500: 399/399 and 392/392, ~60% CPU each
1920x1080@100/9000: 400/400 and 399/399, ~22% CPU each
```
Environment artifact: with two emulators on one host, the discovery serial-to-IP mapping varied between runs (e.g. `[('GV01','172.17.0.2'),('GV01','10.9.9.1')]`). This is because pyGigEVision takes the IP from the UDP source and de-duplicates on it. Real cameras have distinct IPs, so this is not a demonstrated real-world bug.

### T7: spurious resend requests (lossless paced Python sender, 20 frames of 1920x1080 Mono8, 1417 packets/frame, forced 32 MB buffer, listener on 127.0.0.1:3956 counting PACKETRESEND)
```
rate=110MB/s  frame_tx~18.9ms: complete 20/20; spurious PACKETRESEND cmds=80 packets_requested=23410 (82.6% of all packets sent); stats "recovered"=23410
rate=280MB/s  frame_tx~7.4ms : 23538 (83.1%)
rate=1000MB/s frame_tx~2.1ms : 22386 (79.0%)
```
Cause: once a frame is older than `initial_packet_timeout` (5 ms) since its leader, **every** not-yet-received packet counts as missing, including packets the camera has not sent yet ([gvsp.py#L714-L730](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L714-L730), `missing_packets()` [L185-L189](https://github.com/ladisk/pyGigEVision/blob/2de253135b8766c1eb752226539a16b810a1cf0f/pyGigEVision/gvsp.py#L185-L189)). Aravis only considers packets below the highest received packet_id, each with its own timeout ([arvgvstream.c#L644-L680](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvstream.c#L644-L680)). On a real camera that honors resend, this would add a large amount of extra retransmit traffic. The `recovered` statistic counts late-arriving originals as recovered.

### T8: extended IDs (GEV 2.x), block_id > 65535 plus one dropped packet
```
block_id=5      -> frame ok
block_id=70000  -> frame ok
block_id=70001 drop=2 -> Traceback ... gvsp.py line 754: struct.pack(">HHII", 0, block_id, ...) struct.error: 'H' format requires 0 <= number <= 65535
                 -> frame=NO, receiver_thread_alive=False
```
The receiver thread dies, and from then on `get_frame()` only returns None, with no error reaching the caller. At 100 fps, block_id passes 65535 after about 11 minutes. Extended-ID PACKETRESEND also uses a different payload layout, which this code does not implement.

### T9: frames above 2048x2048 px
```
2048x2048 (4.2 MP): delivered (2048,2048)
2448x2048 (5.0 MP): NO (frame silently dropped; only a log warning)
2592x1944 (5.0 MP): NO
```

### What the fake camera cannot test
The fake camera implements only DISCOVERY/READMEM/WRITEMEM/READREG/WRITEREG ([arvgvfakecamera.c#L158-L212](https://github.com/AravisProject/aravis/blob/0.8.26/src/arvgvfakecamera.c#L158-L212)), so it cannot test resend recovery, PTP or action commands. Its XML has no PTP or timestamp features (grep for ptp/timestamp/tick in `out/fake_camera.xml`: 0 hits).

## 5. Verdict

**Not suitable as SkellyCam's base. Useful as compact, readable reference code for GVCP/GVSP framing (MIT).**

Reasons:
1. **None of the user's sync goals are covered**: no PTP control or status, no action or scheduled-action commands, no timestamp-tick or latch handling. GenICam features are not exposed by name, so adding PTP would mean writing a GenICam XML node-map engine (SwissKnife, Converter, pIndex, Enumeration, etc.) first.
2. **Pixel formats** are limited to Mono*. Bayer and RGB colour cameras, which mocap rigs commonly use, come back mis-sized and garbled (T3). Frames above 4.2 MP are silently dropped (T9; PR #3 is pending).
3. **Correctness bugs found**: digit-only bare-hex XML URL misparsed (T1/T2); extended-ID resend crash kills the receiver silently (T8); resend storm of about 80% of packets with zero real loss (T7); silent SO_RCVBUF cap on Linux (T3).
4. **Performance**: in a separate process with a large forced buffer it handles about 200–250 MB/s per camera on loopback (T5, T6), which is good for pure Python. With default Linux buffers, though, it delivered 0% complete frames where Aravis delivered about 90%. Several receivers in one process are limited by the GIL (T6).
5. **Maturity**: about 5 months old, 6 stars, one primary author, no commits since 2026-07-08, no macOS CI, and macOS firewall issue PR #4 is open.

Still worth reusing as reference: discovery across NICs (psutil), the FORCEIP payload layout, the PENDING_ACK/stale-ACK handling in `_send_cmd`, and the pre-allocated buffer reassembly pattern.
