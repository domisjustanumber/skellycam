# viva-genicam 0.10.0: tested Python API reference for a SkellyCam GigE backend

Written 2026-10-25. This covers **viva-genicam 0.10.0**, the latest PyPI release (2026-10-17, MIT, `requires_python >=3.10`). It ships abi3 wheels for `win_amd64`, `macosx_11_0_arm64` and `manylinux_2_28_x86_64`. There is no Intel-mac wheel and no Linux aarch64 wheel.

Source is pinned to tag `py-v0.10.0` = `d53a48f9a68e625715fd09bcd3f7f53795c903c7`. The `.py` and `.pyi` files installed by the wheel are byte-identical to that tag (checked with `diff`).

Permalink prefix used below:
`https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/`. **PY** = `crates/viva-pygenicam/python/viva_genicam/` and **RS** = `crates/viva-pygenicam/src/`.

Where things are:
- **Clone:** `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad/research/src/viva-api/`
- **Venv:** `.../scratchpad/venvs/viva` (CPython 3.12.13, viva-genicam 0.10.0, numpy, opencv-python-headless).
- **Test scripts and logs:** `.../scratchpad/research/viva-api-tests/` (`t1`–`t9`, `*.win.log`, `*.docker.log`, plus `docker/Dockerfile`, image `skellycam-viva-api:1` = python:3.12-bookworm + aravis-tools 0.8.26 + viva-genicam 0.10.0).
- **Example:** `.../scratchpad/impl/viva_api_example.py`. Tested on Windows with 2 fakes and in Docker with 3 fakes.

Legend: **[T-win]** means tested natively on Windows 11. **[T-lin]** means tested in Docker on Linux (WSL2 kernel). **[src]** means read from the source only, not run. **[UNTESTED]** means no hardware was available to test it.

---

## 0. Summary for the backend author

| Need | viva 0.10.0 answer |
|---|---|
| Discover | `vg.discover(timeout_ms=500, iface=None, all=False) -> list[GigeDeviceInfo]`. It always blocks for the full timeout. Loopback (and so the fake) is only searched with `all=True` or `iface="127.0.0.1"`. [T-win][T-lin] |
| Open by IP / MAC | Not available directly. Run discovery, filter on `.ip` / `.mac`, then `vg.connect_gige(info)`. `GigeDeviceInfo` cannot be built by hand and cannot be pickled. `discover_ip()` exists only on unreleased main. [T-win] |
| Open by serial | `GigeDeviceInfo` has no serial field. Connect, then read `DeviceSerialNumber`. [T-win] |
| Control privilege | `connect_gige` claims control and runs its own heartbeat on a Rust thread, so a busy Python thread cannot starve it. A second controller gets `TransportError ... ACCESS_DENIED (0x8006)`. `monitor=True` opens read-only. [T-win][T-lin] |
| Features | `get/set` work as strings. There are also `get_integer/float/bool/enum/string` and their setters. Enumerations are set **by entry name**. `node_info(name) is None` means the feature is absent. `available_enum_entries` gives the entries selectable now. [T-win] |
| Raw registers | `read_register(addr, length=4) -> bytes` and `write_register(addr, data: bytes)` give big-endian bootstrap access. [T-win] |
| Streaming | `with cam.stream(...) as frames:` starts acquisition on entry. Pull frames with `frames.next_frame(timeout_ms)` (blocking, **GIL released**) or `for f in frames` (5 s timeout). No callbacks and no asyncio. [T-win][T-lin] |
| Frame | Fields: `width`, `height`, `pixel_format` (PFNC name), `pixel_format_code`, `block_id`, `ts_dev` (raw device ticks), `ts_host` (mapped, only after `time_calibrate`), `status`, `missing_packets`, `payload_type`, `padding_x`, `chunks`. Data comes from `to_numpy()` (one copy, writeable) or `payload()` (bytes, one copy). Nothing is zero-copy. **There is no host receive timestamp.** [T-win] |
| Queue | Each stream has a receive thread and a **4-frame** delivery queue that drops the oldest frame (`stats().frames_backpressure`). [src][T-win] |
| Action commands | `vg.send_action(device_key, group_key, group_mask, scheduled_time=None, destination="255.255.255.255", timeout_ms=200) -> AckSummary(sent, acks)`. It always waits `timeout_ms`, unless that is 0. Scheduled actions work on the fake. [T-win][T-lin] |
| PTP | **No helpers.** Use generic features (`PtpEnable`/`GevIEEE1588` and so on) and bootstrap registers. `time_calibrate()` is a host↔device least-squares fit over GVCP and has nothing to do with PTP. |
| GEV 3.0 | Plain GVSP streaming should work, because the protocol is unchanged. Nothing GEV3-specific exists: no GVRSP/RDMA and no `GevStreamingMode`. [src][UNTESTED] |
| Threads | One `Camera` can be shared across threads; calls are serialised on a mutex. **One `FrameStream` must be read by one thread at a time.** A second concurrent `next_frame` raises `RuntimeError: Already borrowed`. [T-win][T-lin] |
| Processes | `Camera`, `Frame` and `GigeDeviceInfo` cannot be pickled. Create everything inside the camera process, which works with `spawn`. [T-win] |
| Fake camera | `viva_genicam.testing.FakeGigeCamera` runs in-process on Windows, Linux and macOS. Its pixel formats are Mono8, Mono16, RGB8 and BayerRG8, plus any PFNC name. It has **no PTP enable/status nodes and no Action trigger source**. It counts action commands but they do not trigger frames. Several fakes need **one host IPv4 address each**. [T-win][T-lin] |

---

## 1. Install

```bash
uv venv <dir> --python 3.12
VIRTUAL_ENV=<dir> uv pip install viva-genicam==0.10.0 numpy
```

The install pulls in only `numpy` and the native `_native.pyd`/`.so`, which contains the whole Rust stack and a Tokio runtime. It also installs the `viva-camctl` console script, a diagnostic CLI with `list`, `get`, `features`, `read-reg`, `action`, `stream`, `bench` and other commands. It takes `-v/-vv` and is the only way to see the library's Rust `tracing` warnings, because the Python binding installs no log bridge (see Gaps).

`import viva_genicam` does **not** import `viva_genicam.testing`. Import that explicitly.

## 2. Discovery

`discover(timeout_ms: int = 500, iface: Optional[str] = None, all: bool = False) -> list[GigeDeviceInfo]` ([PY/discovery.py#L94-L116](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/discovery.py#L94-L116), native [RS/discovery.rs#L122-L145](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/discovery.rs#L122-L145))

How it behaves:
- With `iface=None, all=False` it sends `DISCOVERY_CMD` on every routable non-loopback IPv4 interface. Each one goes to the subnet-directed broadcast and to 255.255.255.255.
- `all=True` adds loopback.
- `iface=` takes either an IPv4 address of the host NIC or its OS name (a GUID on Windows). It searches only that interface.

On loopback the command is **unicast to the interface's own address**, not broadcast ([viva-gige/src/gvcp.rs#L654-L674](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/gvcp.rs#L654-L674)). That is why fakes bound to 127.0.0.2 or 127.0.0.3 are invisible on Windows: loopback only reports 127.0.0.1 there. They are found on Linux once `ip addr add 127.0.0.2/8 dev lo` has been run. [T-win][T-lin]

Measured: every call took the full timeout (0.50 s for 500 ms). Results come back sorted by IP. A bad `iface` raises `ParseError`, and the message lists the host's interfaces. [T-win]

`GigeDeviceInfo` is a frozen dataclass with `ip: str`, `mac: str` ("DE:AD:BE:EF:CA:FE"), `manufacturer: Optional[str]`, `model: Optional[str]`, `transport="gige"` and `to_dict()`.
- It holds a hidden native `_handle`, and `connect_gige` needs that handle. You cannot construct one from an IP.
- It **cannot be pickled**: `TypeError: cannot pickle 'viva_genicam._native.GigeDeviceInfo'`. [T-win]
- The Rust `DeviceInfo` does carry `serial`, `user_name`, `version` and other fields ([viva-gige/src/gvcp.rs#L209-L235](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/gvcp.rs#L209-L235)), but the binding does not expose them.

Unicast discovery of a camera across a router is `gige::discover_ip` in Rust ([gvcp.rs#L366-L403](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/gvcp.rs#L366-L403)). It has **no Python binding in 0.10.0**. Unreleased main (60c9c32, 2026-10-24) adds `vg.discover_ip(ip, timeout_ms=500)`, plus `discover(..., allow_broadcast_ack=False)` and `connect_gige(..., exclusive=False)`. It also changes `_native.send_action` to return a 3-tuple with refusals.

To select a camera, filter on IP or MAC:
```python
info = next(d for d in vg.discover(timeout_ms=1000, all=True) if d.ip == ip)   # or d.mac == mac
```

## 3. Opening, closing and control privilege

`connect_gige(device_info: GigeDeviceInfo, iface: Optional[str] = None, monitor: bool = False) -> Camera` ([PY/camera.py#L590-L606](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L590-L606), [RS/camera.rs#L255-L284](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/camera.rs#L255-L284))

It claims CCP control, fetches and parses the GenICam XML (`cam.xml`, 43 KB on the fake) and starts a heartbeat keepalive task on the library's Tokio runtime. The keepalive reads `GevHeartbeatTimeout`, which is 3000 ms on the fake. Because this runs in Rust, a busy Python thread cannot starve it.

`Camera` lifetime ([PY/camera.py#L46-L94](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L46-L94)):
- `close()` releases control at once and is idempotent.
- `closed` reports whether it has been closed.
- It works as a context manager.
- After close, every call raises `GenicamError: the camera is closed`. [T-win]

Control state ([PY/camera.py#L508-L529](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L508-L529)):
- `cam.control_state -> ControlState`. The values are `HELD`, `MONITOR`, `LOST` and `RELEASED` (a `str` Enum).
- `cam.reclaim_control()` and `cam.release_control()`.
- `cam.set_persistent_ip(ip, subnet, gateway="0.0.0.0")` and `vg.force_ip(mac, ip, subnet, gateway="0.0.0.0", iface=None)`.

Tested on the fake [T-win][T-lin]:
- **Second controlling connect:** `TransportError: claim control: device reported status ACCESS_DENIED (0x8006)`.
- **`monitor=True`:**
  - `control_state` is `MONITOR` and reads work.
  - Writes raise `GenApiError: register I/O failed: the camera was opened as a read-only monitor ...`.
  - It can only open `stream(monitor=True)`, which watches a multicast stream.
- **Camera revokes control** (`fake.revoke_control()`):
  - `control_state` becomes `LOST`, detected after 0.5 s on Windows and 0.05 s on Linux.
  - Writes raise `GenApiError ... control of the camera was lost ...`.
  - `reclaim_control()` gives back `HELD`.
- **After `release_control()`:**
  - Writes raise.
  - `stream()` **re-claims** control implicitly, and the state goes back to `HELD`.
- **Camera disappears mid-stream** (`t9_disconnect.py`):
  - `next_frame` simply keeps raising `TransportError: timeout waiting for frame`.
  - `control_state` **stayed `HELD` for at least 8 s**, so the heartbeat failure did not show up within that window.
  - The stream's `__exit__` then raised `GenApiError ... os error 10054`.
  - `close()` returned in 0.16 s.
  - **The backend must treat N consecutive timeouts as a disconnect.**

## 4. Features (GenApi), by name

All of these are on `Camera` ([PY/camera.py#L110-L217](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L110-L217)):

```
get(name) -> str                      set(name, value: str) -> None        # parsed per node type
get_integer / set_integer(name, int)  get_float / set_float(name, float)
get_bool / set_bool(name, bool)       get_enum(name) -> str / set_enum(name, entry: str)
get_string / set_string               get_register(name) -> bytes / set_register(name, bytes)
feature_state(name) -> FeatureState(kind, value, access, is_implemented, is_available,
                                    range: ValueRange(min,max,inc)|None, enum_entries, unit, polling_time, caching)
enum_entries(name) -> list[str]       # all declared entries
available_enum_entries(name) -> list[str]   # pIsImplemented/pIsAvailable now
invalidate(name) / invalidate_all()   generation() / changed_since(gen) / poll()
nodes() -> list[str]   node_info(name) -> NodeInfo|None   all_node_info()   categories()   skipped()
execute(name, *, wait=True, timeout=5.0) -> bool    is_done(name) -> bool
acquisition_start() / acquisition_stop()      # writes TLParamsLocked then AcquisitionStart
```

There are also convenience helpers that try SFNC and legacy names. They are `exposure_time`, `set_exposure_time`, `gain`, `set_gain`, `set_frame_rate` (which returns the feature it wrote), `enable_trigger(selector, source)`, `disable_trigger`, `trigger_software`, `roi`, `set_roi(Roi)`, `binning`, `set_binning`, `user_sets`, `load_user_set`, `save_user_set`, `save_features(path)` and `load_features(path)`.

The Python facade and the `.pyi` stub differ in a few places. Code should follow the facade, which is the public API:
- `execute(..., timeout=)` versus the native `timeout_s`.
- `set_roi(Roi)` versus the native `(x, y, w, h)`.
- `events()` versus the native `open_event_stream`.

Checking availability, tested [T-win]:
- `node_info("PtpEnable")` returns `None` when the feature is absent.
- `get` or `feature_state` on a missing feature raises `GenApiError: node not found: PtpEnable`. `GenApiError` is a subclass of `GenicamError`.
- `available_enum_entries("PixelFormat")` returned `['Mono8','Mono16']` while `enum_entries` returned all four. The fake gates its entries on `SensorType`.
- Setting an unavailable entry raises `GenApiError: enum PixelFormat's entry BayerRG8 is not available now`.

Other tested behaviour [T-win][T-lin]:
- `set_integer("Width", 3)` raises `GenApiError: Width: 3 is below the minimum 16`.
- `set("AcquisitionStart", "1")` raises `GenApiError ... is a Command, not a feature that is set`.
- `get_integer` on an Enumeration raises `GenApiError ... is an Enumeration, not an Integer`.
- `set("Width", ...)` while streaming raises `GenApiError: node Width is locked by TLParamsLocked`, because `acquisition_start` writes `TLParamsLocked=1`.
- `execute("TimestampLatch")` returns `True` (it polls `IsDone`, or returns at once for write-only commands). On timeout it issues a `RuntimeWarning` and returns `False`.

**Caching gotcha.** Values are cached per `<Caching>` in the XML, which is usually WriteThrough. Registers the library writes itself, such as `GevSCPSPacketSize` from `stream(packet_size=...)`, can read back **stale**. After `stream(packet_size=576)`, `get("GevSCPSPacketSize")` still returned 9000 while 571 packets per frame proved that 576 was in effect. Call `cam.invalidate(name)` before reading any value that something other than this `Camera` may have changed. That includes values changed by `write_register`, which does call `invalidate_all()`, and latched values. [T-win]

## 5. Raw registers (bootstrap fallbacks)

`read_register(address: int, length: int = 4) -> bytes` and `write_register(address: int, data: bytes) -> None` ([PY/camera.py#L496-L504](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L496-L504), [RS/camera.rs#L823-L853](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/camera.rs#L823-L853))

- They go straight to READMEM/WRITEMEM (or READREG) and bypass GenApi. Bytes are big-endian as the device holds them.
- `read_register(0x0948, 8)` returns 8 bytes. [T-win]
- A write needs control privilege, a read does not.

Bootstrap values read from the fakes:

| Register | viva fake | Aravis fake 0.8.26 |
|---|---|---|
| Version `0x0000` | `0x00020000` (GEV 2.0) | `0x00000000` |
| GVCP capability `0x0934` | `0x08000027`: no 1588, scheduled-action or action bits, even though the fake **does** answer ACTION_CMD | `0x00000000` |
| Tick frequency `0x093C/0x0940` | 1 000 000 000 | 1 000 000 000 |
| Timestamp control `0x0944`/`0x0948` | write 2 then read: the fake returns **0**, because its latch exists only as the GenApi `TimestampLatch` node | not tested |

Conclusion: capability bits are a hint only. On the viva fake they under-report what it does. On a real camera, combine them with feature presence.

## 6. Streaming

`Camera.stream(iface=None, packet_size=None, auto_packet_size=False, multicast=None, destination_port=None, packet_delay_ns=None, resend=True, deliver_incomplete=False, monitor=False) -> FrameStream` ([PY/camera.py#L533-L587](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L533-L587), [RS/stream.rs#L171-L240](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/stream.rs#L171-L240))

`stream()` opens the socket and configures the camera's stream channel immediately. Acquisition starts in `FrameStream.__enter__`, and `__exit__` runs `acquisition_stop()` and then `close()` ([PY/stream.py#L64-L117](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/stream.py#L64-L117)). To start acquisition yourself, call `frames.__enter__()`, as the tests did, or call `stream()` and then `cam.acquisition_start()`.

How frames are delivered, by the test results [T-win][T-lin]:
- Only by **blocking pull**:
  - `FrameStream.next_frame(timeout_ms: Optional[int] = None) -> Optional[Frame]`. The default timeout is 5 s. It raises `TransportError("timeout waiting for frame")` on timeout and returns `None` on a clean end.
  - Iteration (`for f in frames`) also uses the 5 s timeout and raises on expiry.
  - There are no callbacks and no async API.
- The wait runs with the **GIL released** ([RS/stream.rs#L100-L125](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/stream.rs#L100-L125)). See section 9 for the measurement.
- **Architecture:**
  - One `std::thread` per stream reads the socket with a 5 ms tick, reassembles blocks and sends resend requests.
  - Finished frames go into a **delivery queue of capacity 4 that drops the oldest frame** when full ([viva-genicam/src/stream/receiver.rs#L1-L40](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-genicam/src/stream/receiver.rs#L1-L40)).
  - Seen in practice: printing and decoding the first frame for about 130 ms cost 5 frames (`frames_backpressure=5`, block ids 1, 7, 8, ...). [T-win]
  - **The SkellyCam grab loop must call `next_frame` promptly, and the queue depth is not configurable.**
- **One reader at a time.** `next_frame` takes `&mut self`, so two threads calling it at once gives one `RuntimeError: Already borrowed`. Handing the stream to a worker thread is fine. [T-win][T-lin]
- **Two streams at once.** Calling `cam.stream()` a second time while the first is open **succeeds**: no error, and the camera is redirected. Do not do it. [T-win]
- **After `close()`,** `next_frame` raises `ParseError: frame stream is closed`.
- **Incomplete frames:**
  - By default only complete frames are delivered.
  - `deliver_incomplete=True` also yields frames with `status=FrameStatus.INCOMPLETE` and `missing_packets=N`. Missing bytes are zero.
  - Tested with `FakeGigeCamera(drop_packets=[(2,5),(3,7)])`:

    | Camera resend | `deliver_incomplete` | Frames received | Stats |
    |---|---|---|---|
    | on | either | 1, 2, 3, 4 all Complete | `resend_requested=2 recovered=2` |
    | off | False | 1, 4, 5, 6 (blocks 2 and 3 skipped) | `frames_incomplete=2` |
    | off | True | 1, (2 Incomplete, 1 missing), (3 Incomplete, 1 missing), 4 | |

    [T-win][T-lin]

Stream tuning [T-win][T-lin]:
- **`packet_size=N`** writes `GevSCPSPacketSize` as a ceiling, and a test-packet probe may lower it. 9000 gave 37 packets per VGA Mono8 frame; 576 gave 571.
- **`auto_packet_size=True`** derives the size from the NIC MTU and then probes. It gave 1500 on Windows loopback and about 44 KB on Linux `lo` (7 packets per frame).
  - Passing both `packet_size` and `auto_packet_size` raises `ParseError`.
  - **Caution:** on Linux `lo` with an RGB8 640x480 fake, `auto_packet_size` lost 413 of 513 frames, where the default 1500 lost none. That is a loopback and kernel-buffer artefact, but it shows that large packets plus a small `SO_RCVBUF` lose frames silently.
- **`packet_delay_ns`** writes `GevSCPD`, converted to ticks. It was accepted, but the fake has no `GevSCPD` node, so its effect could not be verified.
- **`destination_port`** receives on a fixed UDP port, which helps with Windows firewall rules. It worked.
- **`resend=False`** turns resend requests off. It worked.
- **`iface=`** is the receive NIC.
- **`multicast="239.x.x.x"`** and **`monitor=True`** are supported in source but untested here.
- **Socket buffer:** the engine requests `SO_RCVBUF = max(4 MiB, 2 × frame)` ([viva-gige/src/nic.rs#L23-L26](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/nic.rs#L23-L26), [receiver.rs#L379-L414](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-genicam/src/stream/receiver.rs#L379-L414)).
  - **There is no Python argument to change it.** The Rust `StreamBuilder::rcvbuf_bytes` exists but is not bound.
  - If the kernel grants less than half, the library logs a `tracing` warning that Python never sees.
  - On Linux, raise `net.core.rmem_max` (for example to 32 MiB) on capture hosts.

`FrameStream.stats() -> StreamStats` ([PY/stream.py#L12-L61](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/stream.py#L12-L61)) is a frozen dataclass:
- Frame fates: `frames_complete`, `frames_incomplete`, `frames_missed`, `frames_backpressure`, `frames_unsupported` and `frames_lost`.
- Packet counters: `packets_*`.
- Resend counters: `resend_requested`, `resend_recovered` and `resend_unavailable`.
- Also: `bytes`, `last_frame_dt`, `avg_fps`, `avg_mbps`, `avg_latency_ms`, `elapsed` and `packets_per_second`.

**Do not trust `avg_fps` / `avg_mbps`.** They read 44.8 on Windows (about right), but 496 on Linux and 2856 against the Aravis fake, for streams that really ran at 25–47 fps. Compute rates yourself. The counters looked right.

## 7. Frame object

Source: [PY/frame.py#L15-L165](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/frame.py#L15-L165) and [RS/frame.rs](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/frame.rs).

| Field | Type | Meaning (verified) |
|---|---|---|
| `width`, `height` | int | From the GVSP leader. |
| `pixel_format` | str | PFNC name such as `"Mono8"` or `"BayerRG8"`. **The RGB8 fakes report `"RGB8Packed"`** (same code 0x02180014), so compare `pixel_format_code`, not the name. |
| `pixel_format_code` | int | Raw PFNC code, for example 0x01080001. |
| `block_id` | int | The camera's block id: 16-bit widened, or the 64-bit extended id. It is **not unwrapped**: the Aravis fake ran 65420..65521, so it wraps 65535 → 1 with standard ids. Counts from 1 at each acquisition start on the viva fake. |
| `ts_dev` | Optional[int] | The **raw GVSP leader timestamp in device ticks**. Divide by `GevTimestampTickFrequency` for seconds. It is not converted and is `Some` whenever a leader arrived; 0 means the camera does not timestamp. On the viva fake it is nanoseconds from its stream clock. The Aravis fake puts host Unix-epoch nanoseconds there. |
| `ts_host` | Optional[float] | `ts_dev` mapped to POSIX seconds through the `time_calibrate()` fit. `None` unless the camera was calibrated **before** `stream()`. It is **not** a host arrival time. See section 8. |
| `status` | `FrameStatus` | `COMPLETE`, `INCOMPLETE`, `DEVICE_STATUS` or `TRAILER_MISSING`. `is_complete` is a bool. |
| `missing_packets` | Optional[int] | Set for `INCOMPLETE`. |
| `device_status` | Optional[int] | Set for `DEVICE_STATUS`. |
| `payload_type` | int | 0x0001 is an image; 0x4001 is an image with chunks. |
| `padding_x` | int | Line padding. `to_numpy` skips it. |
| `chunks` | Optional[dict[int, bytes]] | Chunk data by id. Decode with `cam.chunk_features(frame)` after `cam.configure_chunks(["Timestamp", "FrameID"])`. |

Data access:
- **`to_numpy(demosaic=False)`:**
  - Mono8 → `(H,W) uint8`; Mono10–16 and packed → `(H,W) uint16`.
  - **Bayer\*8 → `(H,W) uint8`, the raw mosaic**. This was tested for all four Bayer orders on the Aravis fake.
  - RGB8/BGR8 → `(H,W,3) uint8`, always RGB order. Unknown formats → `(N,) uint8` of raw bytes.
  - The result is **writeable** and **always a copy** (a Rust `Vec` is moved into numpy), so it is never zero-copy.
- **`payload() -> bytes`** is also one copy, and `np.frombuffer(payload(), np.uint8)` gives a read-only view of it.
- **`to_rgb8()`** always returns `(H,W,3) uint8`. It raises `UnsupportedPixelFormatError` for formats it cannot handle.
- **`demosaic=True`** is bilinear and for preview only.
- `Frame.from_bytes(payload, w, h, pixel_format, padding_x=0)` builds a frame from saved bytes.

Measured cost per call for 1280×1024 frames:

| Call | Windows | Linux |
|---|---|---|
| Mono8 `to_numpy` | 0.44 ms | 0.06 ms |
| Mono8 `frombuffer(payload())` | 0.43 ms | 0.06 ms |
| **BayerRG8 `to_numpy`** | **0.75 ms** | **0.26 ms** |
| BayerRG8 `frombuffer(payload())` | 0.28 ms | 0.04 ms |
| `to_rgb8` / `demosaic=True` on Bayer | 2.8 ms | 4.2 ms |

The Bayer path in `to_numpy` widens every sample to u16 and back ([RS/frame.rs#L67-L87](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/frame.rs#L67-L87)). For 8-bit formats with `padding_x == 0`, `np.frombuffer(frame.payload(), np.uint8).reshape(h, w)` (add `, 3` for RGB8) is the fastest route. Use `.copy()` if the array must be writeable, or copy straight into SkellyCam's shared-memory slot.

Bayer orientation: the fake's test pattern is too flat to validate the CFA phase. viva's demosaic differed from both `cv2.COLOR_BayerRG2RGB` and `cv2.COLOR_BayerBG2RGB` by less than 1 grey level on it, so nothing can be concluded. Keep the `skellycam-arch.md` mapping (PFNC BayerRG8 → `cv2.COLOR_BayerBG2BGR`), which was verified against a real pattern.

## 8. Time: `time_calibrate`, `map_dev_ts`, `ts_host`

`time_calibrate(samples: int = 8, interval_ms: int = 20) -> None`, `time_reset()` and `map_dev_ts(ticks: int) -> Optional[float]` ([PY/camera.py#L434-L457](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/camera.py#L434-L457); algorithm in [viva-genicam/src/lib.rs#L393-L509](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-genicam/src/lib.rs#L393-L509))

How it works:
- It executes the first latch command present (`GevTimestampControlLatch`, `TimestampControlLatch`, `TimestampLatch`). Then it invalidates and reads the first value node present (`GevTimestampValue`, `TimestampValue`, `TimestampLatchValue`, `Timestamp`), with the name lists in [viva-sfnc/src/lib.rs#L118-L162](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-sfnc/src/lib.rs#L118-L162).
- It pairs each reading with `Instant::now()` taken **after** the GVCP round trip, and fits a straight line.
- It takes at least 2 samples; `samples=1` raises `TransportError: time calibration: it takes at least two samples`. The default call took 0.15–0.17 s.
- It uses no PTP and is accurate only to about one GVCP round trip.
- Only streams opened afterwards get `ts_host`.

**Pitfall, tested** [T-win][T-lin]: the mapping is `origin + a·ticks + b`, and any tick value that maps to before the first calibration sample is **clamped to the origin** ([viva-gige/src/time.rs#L245-L259](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/time.rs#L245-L259)).
- On the viva fake, the GVSP leader clock restarts at its stream-sender start, while the `GevTimestampValue` latch counts from fake start. So every frame mapped to the **same constant `ts_host`**.
- A real camera uses one clock for both, so this should not happen there [UNTESTED]. It would happen after a device timestamp reset or a PTP step backwards.
- Recommendation: **store `ts_dev` (and the tick frequency) and do any mapping in SkellyCam.** Do not rely on `ts_host`.

**No host receive timestamp exists on `Frame`.** Take `time.perf_counter_ns()` right after `next_frame` returns. That includes up to one 5 ms receive tick plus queueing.

**PTP:** the library has no PTP API at all (`git grep -i ptp` finds only the fake). Use the generic feature calls:
- `set_bool("PtpEnable", True)`, or `GevIEEE1588`.
- `execute("PtpDataSetLatch")`.
- `invalidate("PtpStatus")` and then `get_enum("PtpStatus")`.
- `get_integer("PtpOffsetFromMaster")`.

As raw fallbacks, use bootstrap `0x0954` bit 0x00080000 with `write_register` / `read_register`. **Enable PTP before `stream()`.** The fake does expose a read-only `GevIEEE1588OffsetFromMasterLatched_Val` (it reads −1234567), but it has no enable or status nodes. [UNTESTED on real PTP hardware]

## 9. GIL and threading

GIL, measured with a pure-Python spin thread counting loop iterations for 3 s while the main thread did the work [T-win][T-lin]:

| Main-thread work | Windows | Linux |
|---|---|---|
| None (baseline) | 115.7 M | 54.0 M |
| Streaming 1280×1024 @ 30 fps (all `next_frame` waits) | 117.4 M (102 %) | 57.4 M (106 %) |
| Uncached GVCP reads, 105–128 /s | 115.4 M (100 %) | 56.3 M (104 %) |

So waits do not hold the GIL. Every native method uses `py.detach` ([RS/camera.rs#L1-L10](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/camera.rs#L1-L10), [#L165-L207](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/camera.rs#L165-L207)), and so do decoding in `to_numpy` and `to_rgb8`.

Threading rules:
- **Camera across threads: yes.**
  - A worker thread pulled 30 frames while the main thread did more than 26 000 `get`/`get_float` calls on the same camera, with no errors. [T-win][T-lin]
  - Calls are serialised on a Rust mutex, so a slow GVCP call blocks other callers of the same camera, but not the stream's receive thread.
- **FrameStream:** one reader at a time (section 6).
- **Frame:** a frozen, read-only object that may be passed to any thread.
- **Processes:**
  - `Camera`, `Frame` and `GigeDeviceInfo` cannot be pickled.
  - A `spawn` child that rediscovered by IP, connected and grabbed 10 frames worked in 1.06 s, while the fake ran in the parent. [T-win]
  - So pass IP or MAC strings to the camera process, and build everything inside it.

## 10. Action commands

`send_action(device_key: int, group_key: int, group_mask: int, scheduled_time: Optional[int] = None, destination: str = "255.255.255.255", timeout_ms: int = 200) -> AckSummary(sent: int, acks: int)` ([PY/network.py#L12-L41](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/network.py#L12-L41), [RS/gige.rs#L41-L64](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/gige.rs#L41-L64), [viva-gige/src/action.rs#L93-L185](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-gige/src/action.rs#L93-L185))

What goes on the wire:
- One datagram to `destination:3956` with ACK_REQUIRED set.
- The BROADCAST flag and `SO_BROADCAST` are added **only** when the destination is exactly 255.255.255.255.
- `scheduled_time` adds flag 0x80 and a 20-byte payload. Its value is **in device ticks**, so with PTP it is PTP time in the camera's tick units.
- The socket binds 0.0.0.0, so the OS route decides the egress NIC. **There is no `iface` argument.**

Tested behaviour [T-win][T-lin]:
- **Matching keys, unicast to the fake:** returned `AckSummary(sent=1, acks=1)` and `fake.actions()` went up by 1. The same held with `scheduled_time=latched_ticks+50 ms`.
- **Wrong device key:** returned `acks=0` and the fake did not act.
- **Return timing:**
  - The call **always waits `timeout_ms`** to collect acks: 52 ms at 50, 201 ms at 200.
  - `timeout_ms=0` returns in 0.2–1 ms with `acks=0`, and the command still reached the fake.
  - Sending one command per camera therefore costs N × timeout. Use `timeout_ms=0` in the trigger path, or a thread per destination, and validate acks once at setup.
- **Destinations:**

  | Destination | Windows | Linux |
  |---|---|---|
  | Directed broadcast (172.30.239.255 on vEthernet) | delivered, `acks=1` | `TransportError ... Permission denied (os error 13)`, because `SO_BROADCAST` is not set |
  | 255.255.255.255 | sent on the default route only; fakes on other interfaces got nothing | with only `lo`: `Network is unreachable` |

  **For multi-NIC rigs, send one unicast per camera IP**, or 255.255.255.255 only when the cameras sit on the default-route NIC.
- **A NACKed command** (for example `NOT_IMPLEMENTED`, which a real Manta G-125B returned per upstream commit 644bff8) is only logged in Rust and simply shows up as `acks=0`.
- Against the **Aravis fake**: `acks=0`, because Aravis does not implement ACTION_CMD.
- Errors: a bad IP string raises `ParseError`, and socket errors raise `TransportError`.

Camera-side configuration is generic feature writes. viva has no helpers for it. They are `ActionDeviceKey`, `ActionSelector`, `ActionGroupKey`, `ActionGroupMask`, `TriggerSelector=FrameStart`, `TriggerSource=Action1` (or `Action0`) and `TriggerMode=On`. `cam.enable_trigger("FrameStart", "Action1")` does the last three. The fake has **no `Action*` nodes, and its TriggerSource entries are only `Line1` and `Software`**: `set_enum("TriggerSource", "Action1")` raised `GenApiError: enum TriggerSource has no entry named Action1`. So **"action triggers a frame" cannot be tested on the fake.** The fake only counts accepted commands. [UNTESTED end-to-end]

## 11. Errors

All exceptions derive from `vg.GenicamError`, which derives from `Exception` ([PY/errors.py](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/errors.py)):

| Exception | Raised for |
|---|---|
| `GenApiError` | Missing node, out of range, locked, wrong type, register I/O refused because control is not held. |
| `TransportError` | Timeouts (frame wait included), ACCESS_DENIED, network errors, calibration failure, fake not running. |
| `ParseError` | Bad `iface`, IP or option combination; using a closed stream. |
| `MissingChunkFeatureError`, `UnsupportedPixelFormatError` | As named. |
| plain `GenicamError` | Camera closed, mutex poisoned. |
| `RuntimeError: Already borrowed` | PyO3: concurrent `next_frame` on one stream. Not a `GenicamError`. |

A frame timeout is a `TransportError` whose message is `"timeout waiting for frame"`. Match on the message, or treat any `TransportError` during a pull as a soft failure.

## 12. Cleanup order

The order that worked everywhere: leave the `with frames:` block (AcquisitionStop, unlock TLParams, join the receive thread), then `cam.close()` (release control), then `fake.stop()`.

`FakeGigeCamera.stop()` blocks until its port is free. `close()` after the camera vanished still returned in 0.16 s.

## 13. `viva_genicam.testing.FakeGigeCamera`

Source: [PY/testing.py#L31-L160](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/python/viva_genicam/testing.py#L31-L160) and [RS/testing.rs#L59-L381](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-pygenicam/src/testing.rs#L59-L381).

```python
FakeGigeCamera(width=640, height=480, fps=30, bind_ip="127.0.0.1", port=3956, pixel_format="Mono8", *,
               packet_resend=True, drop_packets: Sequence[tuple[block_id, packet_id]] | None = None,
               delay_ack: Mapping[register_addr, seconds] | None = None)
start() / stop() / with ...: ; .ip ; .port ; device_info(timeout_ms=1500) -> GigeDeviceInfo (runs discover(all))
controller() -> "ip:port"|None ; revoke_control() ; peek(addr, n) -> bytes ; software_triggers() ; actions() ; blocks_sent() ; writes()
class attrs: DEVICE_KEY=0x42, GROUP_KEY=0x1, GROUP_MASK=0x1, MAC="DE:AD:BE:EF:CA:FE", REGISTERS={name: addr}
```

Runtime and platforms:
- It runs **in-process** on the library's Tokio runtime, so it needs no binary or subprocess.
- It worked natively on Windows with no firewall prompt, for both loopback and the vEthernet address. It also worked on Linux.
- Startup takes about 1–3 ms. [T-win][T-lin]

Pixel formats:
- `pixel_format` accepts any PFNC name. The XML enumeration offers Mono8, Mono16, RGB8 and BayerRG8, gated by `SensorType` ([viva-fake-gige/src/registers.rs#L725-L746](https://github.com/VitalyVorobyev/viva-genicam/blob/d53a48f9a68e625715fd09bcd3f7f53795c903c7/crates/viva-fake-gige/src/registers.rs#L725-L746)).
- When constructed with `pixel_format="BayerRG8"`, the fake still reports `SensorType=Monochrome`, so `available_enum_entries` does not list the current format.
- Resolutions: Width 16–4096, plus binning and offsets.

Frame rate:
- On Windows the fake delivers about 25 fps when asked for 30, and about 44 fps when asked for 60. That is timer granularity: it sleeps `1/fps` after sending.
- `AcquisitionFrameRate` reads 30 whatever `fps` is.

Timestamps:
- The tick frequency is 1 GHz (node and bootstrap).
- `GevTimestampValue` and `TimestampLatch` are present. There is no timestamp reset command, so `time_reset()` only clears the fit.
- Leader timestamps are nanoseconds on the stream-sender clock, a **different origin** from the latch clock (see section 8).
- `ChunkTimestamp`, `ChunkFrameID` and the `ExposureEnd` event exist.

PTP and actions:
- PTP: only `GevIEEE1588OffsetFromMasterLatched_Val`, which is constant at −1234567. There is no PtpEnable, PtpStatus or GevIEEE1588.
- Actions: it answers ACTION_CMD (scheduled or not) when the keys match, ACKs, and increments `actions()`. Nothing is triggered, and the scheduled time is ignored.
- Its capability register (0x08000027) does **not** advertise action support.
- `TriggerSource` offers only `Line1` and `Software`. `TriggerSoftware` works: in trigger mode a frame arrived only after `trigger_software()`.

Several fakes at once:
- Discovery and `connect_gige` only reach port 3956, so each fake needs **its own host IPv4 address**, bound with `bind_ip`.
- **Windows:** only 127.0.0.1 and real NIC addresses work. 127.0.0.2 and up bind but cannot be discovered. On this machine that allowed 2 fakes, 127.0.0.1 and 172.30.224.1 (the WSL vEthernet). I deliberately did not bind a fake to the 10G NIC 192.168.6.86. **3 fakes on Windows were not possible without adding a loopback address**, which needs admin rights.
- **Linux** (`--cap-add NET_ADMIN`; `ip addr add 127.0.0.2/8 dev lo`): 3 fakes were discovered and streamed 100 frames each in parallel threads. BayerRG8 lost 0. Mono8 lost 1 frame (13 resends). The RGB8 fake lost 0 but needed 387 resends under default Docker `rmem` (`t3_multi_capture.docker.log`).
- A fake bound to a non-loopback IP on **Linux** is **not found** by broadcast discovery, because a socket bound to a unicast address does not get broadcasts. On Windows it is found.
- All fakes share one MAC, so do not select fakes by MAC.

Results with 2 Windows fakes ([T-win], `t3_multi_capture.win.log`):
- 100 frames each, Mono8 and BayerRG8, captured in parallel.
- 0 lost, block ids 1..100.
- Unicast and scheduled actions acked by each fake.

## 14. Aravis `arv-fake-gv-camera-0.8` (0.8.26, Debian bookworm) for comparison [T-lin]

`docker run --network none skellycam-viva-api:1`, then `arv-fake-gv-camera-0.8 -i lo` and `t6_aravis.py` (`t6_aravis.docker.log`):
- **Discovery and connect:** discovery with `all=True` found `Aravis/Fake` at 127.0.0.1. It connected with 65 nodes and 0 skipped.
- **Missing nodes:**
  - No `GevTimestampTickFrequency` or `GevSCPSPacketSize` node, although bootstrap 0x093C reads 1 GHz.
  - No PTP nodes and no `DeviceSerialNumber`.
  - `TriggerSource` offers Line0 and Software only.
- **Pixel formats:** all 7 offered decoded correctly through viva:
  - BayerBG8, BayerGB8, BayerGR8 and BayerRG8 give (512,512) uint8 mosaics.
  - Mono8 gives (512,512) uint8, and Mono16 gives uint16.
  - RGB8 gives (512,512,3), and the name came back as `RGB8Packed`.
- **Streaming 100 frames:**
  - Took 4.30 s at about 23 fps.
  - Block ids were near the 16-bit wrap (65420..65521).
  - `ts_dev` holds host epoch ns, 40 ms apart.
  - **5 frames were incomplete**, and there were no resends because the Aravis fake advertises no capabilities.
- **Time and actions:**
  - `time_calibrate()` raised `GenApiError: node not found: TimestampValue`.
  - `send_action` returned `acks=0`.

So the Aravis fake is useful for checking pixel formats and interoperability, but not for sync.

## 15. GigE Vision 3.0 notes

- viva reads no GEV-3-specific registers or features. `git grep -i "gvrsp|rocev2|rdma|GevStreamingMode"` finds nothing in the Rust or Python code; the only `DeviceTLVersionMajor` hits are in the GenTL producer crate.
- A GEV 3.0 camera that streams GVSP should look like a GEV 2.x device to viva. Read `read_register(0x0000)` and check `>>16 == 3` to log the version.
- GVRSP/RDMA is unsupported. [src] [UNTESTED: no GEV 3 hardware]
- Larger GEV3 control packets are not used.

## 16. Gaps and risks, honestly stated

1. **No PTP helpers.** There is no enable, status, offset, wait-for-slave or vendor-name abstraction. Everything goes through generic features and registers. PTP configuration is untested because neither fake has PTP enable or status nodes.
2. **Action → frame cannot be tested on any fake.**
   - Neither fake has `TriggerSource=Action*` or `Action*` key nodes, and the viva fake ignores the scheduled time.
   - `send_action` has no `iface`.
   - It sets `SO_BROADCAST` only for 255.255.255.255, so a directed broadcast fails with EACCES on Linux.
   - It always blocks for `timeout_ms`.
   - NACK statuses are swallowed (fixed on main: it returns refusals).
3. **No host arrival timestamp on Frame.** `ts_host` is a GVCP-latency-limited linear map from `time_calibrate()` and clamps ticks earlier than calibration to a constant. Store `ts_dev` and the tick frequency separately, and stamp host time yourself.
4. **4-frame drop-oldest delivery queue**, not configurable. The grab loop must not stall.
5. **No `SO_RCVBUF` knob in Python**, and **no Python logging bridge** for Rust `tracing` warnings such as a short rcvbuf, a TLParamsLocked refusal or action NACKs. Use `viva-camctl -vv` to diagnose.
6. **Discovery:**
   - It always waits the full timeout.
   - There is no unicast `discover_ip` in 0.10.0 (it is on main).
   - `GigeDeviceInfo` has no serial and cannot be built from an IP or pickled.
   - Loopback needs `all=True`.
7. **Disconnect detection:** a vanished camera shows only as repeated frame timeouts. `control_state` stayed `HELD` for at least 8 s.
8. **Stream hazards:**
   - A second `stream()` on the same camera succeeds silently.
   - Concurrent `next_frame` raises PyO3 `RuntimeError`.
   - `get("GevSCPSPacketSize")` can be stale. Invalidate first.
9. **Decode:**
   - Nothing is zero-copy, and `to_numpy()` on Bayer8 is about 3× slower than `frombuffer(payload())`.
     > **Correction (2026-10-28):** about 3× on Windows (0.754 vs 0.281 ms, `t7_misc.win.log`) but about 6× on Linux (0.259 vs 0.043 ms, `t7_misc.docker.log`). See the table in section 7.
   - Formats with no converter (for example YUV422 variants, Bayer10/12 packed beyond those listed, vendor formats) come back as a flat `(N,) uint8`.
   - `pixel_format` names can be legacy (`RGB8Packed`). Compare codes.
   - Bayer CFA orientation was not validated.
10. **`StreamStats.avg_fps` / `avg_mbps` are wrong** in some runs (496 or 2856 fps reported). The counters are fine.
11. **Platforms:**
    - Wheels exist only for win_amd64, macOS arm64 and manylinux x86_64. Intel macOS and Linux aarch64 users would need to build with Rust and maturin.
    - macOS itself was not tested here.
12. **Maturity:** 0.x releases come every few days (0.6.0 on 2026-09-24 through 0.10.0 on 2026-10-17). The Python API changed on unreleased main: the `_native.send_action` return shape, plus new `exclusive`, `discover_ip` and `allow_broadcast_ack`. **Pin `viva-genicam==0.10.0`**, and wrap `send_action` so the change in what it returns is absorbed in one place.
13. **Real hardware throughput** (multi-camera, full-rate GigE or 10 GigE without loss on Windows and macOS) is **UNTESTED**. Only loopback with fakes was measured.

## 17. Test inventory (all in `.../scratchpad/research/viva-api-tests/`)

| Script | What it covers | Logs |
|---|---|---|
| `t1_single.py` | discovery variants, nodes, features, enums, bootstrap registers, 100-frame stream, close | `t1_single.win.log`, `t1_t4_t5.docker.log` |
| `t2_multi_probe.py` | which bind IPs can run and be discovered as concurrent fakes | `t2_multi_probe.*.win.log`, `t3_multi_capture.docker.log` |
| `t3_multi_capture.py` | N fakes × 100 frames in parallel threads; unicast, broadcast, scheduled and wrong-key actions | `t3_multi_capture.win.log` (2 fakes), `t3_multi_capture.docker.log` (3 fakes) |
| `t4_behaviour.py` | GIL, decode cost, threading, time mapping, trigger and timeout, exceptions, control privilege, stream knobs, incomplete and resend | `t4_behaviour.win.log`, `t1_t4_t5.docker.log` |
| `t5_timemap.py` | latch clock vs leader clock, `map_dev_ts` clamping | `t5_timemap.win.log`, `t1_t4_t5.docker.log` |
| `t6_aravis.py` | viva against the Aravis fake | `t6_aravis.docker.log` |
| `t7_misc.py` | `send_action` timing, directed broadcast, Bayer decode cost | `t7_misc.win.log`, `t7_misc.docker.log` |
| `t8_process.py` | pickling, spawn child process | `t8_process.win.log` |
| `t9_disconnect.py` | camera vanishing mid-stream | `t9_disconnect.win.log` |
| `../../impl/viva_api_example.py` | the end-to-end example | `example.win.log` (2 fakes), `example.docker.log` (3 fakes) |
