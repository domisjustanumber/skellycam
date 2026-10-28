# prep-viva-api (completed agent result)

## viva-genicam 0.10.0: tested API reference

viva-genicam 0.10.0 works for a SkellyCam backend on Windows and Linux. Discovery, streaming and action commands all work against its fake camera. Neither fake camera has PTP enable/status nodes or an Action trigger source, so the parts that matter most for sync (PTP, and an action command actually triggering a frame) are untested. No real camera was available.

- **Version:** PyPI latest, released 2026-10-17, MIT. Wheels exist for win_amd64, macOS arm64 and manylinux x86_64 only. Source is pinned to tag `py-v0.10.0` = `d53a48f`; the installed `.py`/`.pyi` files are byte-identical to it.
- **Clone:** `.../scratchpad/research/src/viva-api/`.
- **Venv:** `.../scratchpad/venvs/viva`.
- **Test scripts and logs:** `t1`–`t9` with `*.win.log` / `*.docker.log` in `.../scratchpad/research/viva-api-tests/`.
- **Docker image:** `skellycam-viva-api:1` (python:3.12-bookworm + aravis-tools 0.8.26).

### What was run
- **Windows, natively:**
  - One fake: 100 frames, no frames lost.
  - Two fakes at once (127.0.0.1 and the WSL vEthernet address 172.30.224.1): 100 frames each in parallel, 0 lost.
  - Unicast and scheduled action commands were acked by each fake.
  - No firewall problems.
- **Docker (Linux):**
  - Three viva fakes on loopback addresses (`ip addr add 127.0.0.x/8 dev lo`): 100 frames each.
  - The Aravis `arv-fake-gv-camera-0.8`: all 7 of its pixel formats decoded, 100 frames captured.
  - Aravis does not ack action commands and `time_calibrate` fails on it (no timestamp value node).
- **Example script:** runs on both (2 fakes on Windows, 3 in Docker).

### API facts
- **Discovery:**
  - `vg.discover(timeout_ms=500, iface=None, all=False)` always waits the full timeout.
  - Loopback, where the fake answers, is only searched with `all=True`.
  - There is no way to open a camera directly by IP in 0.10.0. Discover, then filter on `.ip`/`.mac`.
  - The device info has no serial number; connect and read `DeviceSerialNumber`.
  - `Camera`, `Frame` and the device info cannot be pickled, so build them inside the camera process. That works with `spawn`.
- **Control privilege:**
  - `vg.connect_gige(info, iface=None, monitor=False)` claims control and keeps the heartbeat alive on a Rust thread.
  - A second controller gets `ACCESS_DENIED`. `monitor=True` opens read-only.
  - A lost connection shows up as `control_state == LOST`.
- **Features:**
  - `get`/`set` (strings), typed getters and setters, `set_enum` by entry name.
  - `node_info(name) is None` means the feature is absent; `available_enum_entries` lists entries selectable now.
  - Values are cached: call `invalidate(name)` before re-reading anything changed outside this `Camera` object. `GevSCPSPacketSize` read back stale.
- **Raw registers:** `read_register(addr, length=4)` and `write_register(addr, bytes)` work for the bootstrap fallbacks.
- **Streaming:**
  - `with cam.stream(...) as frames:` then `frames.next_frame(timeout_ms)` is a blocking pull. There are no callbacks.
  - The GIL is released: a busy Python thread kept 100–106% of its speed while frames streamed and while settings were read from the camera.
  - One receive thread per stream feeds a 4-frame queue that drops the oldest frame. The grab loop must not stall.
  - Only one thread may read a stream at a time; a second concurrent `next_frame` raises `RuntimeError: Already borrowed`.
  - Options: `packet_size`, `auto_packet_size`, `packet_delay_ns`, `destination_port`, `resend`, `deliver_incomplete`, `multicast`.
  - There is no receive-buffer size setting in Python.
- **Frame:**
  - Fields: `width`, `height`, `pixel_format` (and `pixel_format_code`), `block_id`, `ts_dev`, `ts_host`, `status`, `missing_packets`, `payload_type`, `padding_x`, `chunks`.
  - `block_id` is 16-bit and wraps.
  - `ts_dev` is the raw device timestamp in ticks.
  - `to_numpy()` and `payload()` each make one copy; nothing is zero-copy. For Bayer8, `np.frombuffer(payload())` is about 3× faster than `to_numpy()`.
- **Actions:**
  - `vg.send_action(dk, gk, gm, scheduled_time=None, destination="255.255.255.255", timeout_ms=200)` returns `AckSummary(sent, acks)`.
  - It always blocks for `timeout_ms`; `timeout_ms=0` returns immediately and the command is still delivered.
  - Matching keys get an ack, wrong keys get 0.
- **Time:**
  - `time_calibrate()` and `map_dev_ts()` are a host-side line fit over the control connection. They have nothing to do with PTP.
  - Device ticks earlier than the calibration window are clamped to one constant time. On the fake this made `ts_host` the same for every frame.
  - There is no host arrival timestamp on frames: take one yourself, and keep `ts_dev` separate.
- **PTP:** no helpers at all; only generic feature reads and writes.
- **GigE Vision 3:** nothing GEV3-specific in the code; plain streaming should be the same as 2.x. RDMA streaming is unsupported.

### Fake camera
- `viva_genicam.testing.FakeGigeCamera` runs in-process on Windows.
- Each fake needs its own host IPv4 address. On Windows only 127.0.0.1 and real NIC addresses work; 127.0.0.2 and up cannot be discovered. So only 2 fakes ran here; I deliberately left the 10G NIC (192.168.6.86) alone.
- Its capability register does not advertise action support, even though it acks actions.

## Structured fields

```json
{
 "notes_file": "C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/impl/viva_api.md",
 "example_script": "C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/impl/viva_api_example.py",
 "windows_fake_camera_works": true,
 "gaps": [
  "No PTP helpers in viva-genicam 0.10.0; PTP must be configured via generic features/registers, and PTP configuration is UNTESTED (neither viva's FakeGigeCamera nor the Aravis fake has PtpEnable/PtpStatus/GevIEEE1588 nodes; viva fake only has a constant GevIEEE1588OffsetFromMasterLatched_Val).",
  "An action command actually triggering a frame is UNTESTED: neither fake has TriggerSource=Action0/1 or Action* key nodes; viva's fake only counts/acks ACTION_CMD and ignores scheduled_time; the Aravis fake does not implement ACTION_CMD at all.",
  "send_action: no iface parameter (OS route picks NIC); SO_BROADCAST only set for 255.255.255.255 so subnet-directed broadcast fails with EACCES on Linux (works on Windows); always blocks for timeout_ms; NACK statuses (e.g. NOT_IMPLEMENTED) are swallowed and appear as acks=0 (changed on unreleased main).",
  "Frame has no host receive timestamp; ts_host is a GVCP-latency-limited linear fit from time_calibrate() and clamps ticks earlier than the calibration window to a constant origin (observed: identical ts_host on every fake frame).",
  "Delivery queue is fixed at 4 frames, drop-oldest (frames_backpressure); not configurable.",
  "No Python control of SO_RCVBUF (Rust StreamBuilder::rcvbuf_bytes not bound) and no Python logging bridge for Rust tracing warnings (short rcvbuf, TLParamsLocked refusal, action NACK); use viva-camctl -vv to see them.",
  "Discovery always waits the full timeout; no unicast discover_ip in 0.10.0 (only on unreleased main); GigeDeviceInfo has no serial, cannot be built from an IP, and cannot be pickled; loopback needs all=True.",
  "Camera vanishing mid-stream shows only as repeated TransportError timeouts; control_state stayed HELD for >= 8 s, so disconnects must be inferred from consecutive timeouts.",
  "Opening a second stream() on the same Camera silently succeeds (hazard); concurrent next_frame on one stream raises PyO3 RuntimeError 'Already borrowed' (not a GenicamError).",
  "Cached feature values can be stale (GevSCPSPacketSize after stream(packet_size=...)); must invalidate() before reading values changed outside the Camera object.",
  "Nothing is zero-copy; to_numpy() on Bayer8 is ~3x slower than np.frombuffer(payload()); formats without a converter return flat (N,) uint8; pixel_format names may be legacy ('RGB8Packed'); Bayer CFA orientation could not be validated with the fakes' flat test pattern.",
  "StreamStats.avg_fps/avg_mbps reported nonsense (496 and 2856 fps) on Linux and against the Aravis fake; counters are fine.",
  "block_id is not unwrapped (16-bit ids wrap at 65535 on GEV 1.x/2.x without extended ids; Aravis fake started near 65420).",
  "No GigE Vision 3.0 specific handling (no GVRSP/RDMA, no GevStreamingMode, no larger control packets); GEV3 cameras over plain GVSP are expected to work but are UNTESTED.",
  "Windows can run only one FakeGigeCamera per host IPv4 address (127.0.0.2+ binds but is not discoverable); only 2 simultaneous fakes were possible natively here (127.0.0.1 + WSL vEthernet). 3 fakes were run only in Docker/Linux with loopback aliases.",
  "Wheels only for win_amd64, macOS arm64, manylinux x86_64 (no Intel macOS, no Linux aarch64); macOS not tested.",
  "Library is pre-1.0 with releases every few days and API changes on unreleased main (send_action return shape, exclusive=, discover_ip, allow_broadcast_ack); pin viva-genicam==0.10.0.",
  "Real-hardware throughput (multi-camera full-rate GigE/10GigE, packet loss on Windows/macOS) is UNTESTED; only loopback against fakes was measured."
 ]
}
```