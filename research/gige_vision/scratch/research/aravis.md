# Aravis evaluation for SkellyCam GigE Vision backend

Research date: 2026-10-25. All source permalinks are pinned to Aravis `main` at commit
`482547a3d56e3aa8d22d7ffed33c9f1588bfe17a` (committed 2026-10-22), abbreviated below as `@HEAD`:
`https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/<path>`.

Local clone: `scratchpad/research/src/aravis/` (and `src/aravis-rs/` for the Rust bindings).

## 1. Identity, license, maintenance

| Item | Value | Source |
|---|---|---|
| License | LGPL-2.1-or-later | [README.md#L25](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/README.md#L25), SPDX header e.g. [src/arvcamera.c#L5](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.c#L5), full text [COPYING](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/COPYING) |
| Latest stable | **0.8.36**, tagged 2026-04-23 (commit 97ff5e33), GitHub release 2026-04-26 marked "Latest" | `git log -1 0.8.36`; `gh release list --repo AravisProject/aravis` |
| Latest dev | **0.9.2**, tagged 2026-04-23 (commit c1a23267), "Pre-release"; `main` is 0.9.3 with API version 0.10 | [meson.build#L1-L7](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/meson.build#L1-L7) |
| Versioning | odd minor = development, even minor = stable; stable series are parallel-installable (`-0.8`, `-0.10` suffixes) | [docs/reference/aravis/building.md#L30-L38](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/building.md#L30-L38) |
| Activity | last commit 2026-10-22; 49 commits in the 12 months before 2026-10-25 (`git log --since=2025-10-25 --oneline | wc -l`) | local clone |
| CI | Linux, macOS, MinGW, MSVC, MSVC-Conan2 workflows; all four checked were `success` on 2026-10-23 (e.g. [macOS run](https://github.com/AravisProject/aravis/actions/runs/39925980711), [MinGW run](https://github.com/AravisProject/aravis/actions/runs/39925980920), [MSVC run](https://github.com/AravisProject/aravis/actions/runs/39925980937), [Linux run](https://github.com/AravisProject/aravis/actions/runs/39925980689)) | [README.md#L6-L10](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/README.md#L6-L10), `gh run list` |
| Clean-room caveat | GV/U3V protocol code must **not** be based on A3 (AIA) spec documents, because A3 forbids using them for open-source implementations | [README.md#L57-L63](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/README.md#L57-L63), also [ethernet.md "Legacy endianess"](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/ethernet.md) |

### License implications for SkellyCam (AGPL-3.0-or-later, see `pyproject.toml` classifier)
- LGPL-2.1 §3 lets any recipient convert the LGPL'd copy to "the ordinary GNU GPL, version 2, or any later version" ([COPYING#L211-L221](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/COPYING#L211-L221)); combined with "or-later" this makes Aravis usable inside an AGPL-3.0 application. No conflict found.
- LGPL-2.1 §6 governs a distributed "work that uses the Library" (e.g. a PyInstaller bundle). Option (b) is satisfied by "a suitable shared library mechanism" that "will operate properly with a modified version of the library" ([COPYING#L271-L304](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/COPYING#L271-L304)). A PyInstaller **onedir** build that ships `libaravis-0.8*.so/.dylib/.dll` as a separate replaceable file fits that; a onefile build unpacks the same shared libs to a temp dir at runtime, which is weaker but still dynamic linking. §6 also requires prominent notice + a copy of the license. Since SkellyCam is itself AGPL/source-available, offering Aravis source (6a/6c) is trivial anyway. (This is my reading of the license text, not legal advice.)
- Transitive deps are also LGPL (glib, libxml2 is MIT, zlib is zlib) — not separately verified here.

## 2. Platform support and Python installation

### Linux (primary)
- Distro packages exist; Ubuntu 24.04 ships **0.8.30** (`aravis-tools`, `aravis-tools-cli`, `gir1.2-aravis-0.8`, `libaravis-0.8-0`, all `0.8.30-1build2`) — verified by `dpkg -l` in the container run below (log: `aravis_docker_run.log`).
- Packet-socket (AF_PACKET / TPACKET_V3 `PACKET_RX_RING`) fast path is Linux-only: [meson.build#L103-L119](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/meson.build#L103-L119), ring setup [src/arvgvstream.c#L1240-L1265](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1240-L1265), selection at thread start (falls back to the normal socket loop if `socket(PF_PACKET…)` fails) [src/arvgvstream.c#L1386-L1392](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1386-L1392). Requires `cap_net_raw` (`sudo setcap cap_net_raw+ep <binary>`): [ethernet.md#L94-L103](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/ethernet.md#L94-L103). For a Python app the capability would have to be on the python interpreter binary — a deployment wrinkle.
- My HEAD build in Docker reports `#define ARAVIS_HAS_PACKET_SOCKET 1` (log `aravis_head_meson_test.log`).

### macOS
- **Homebrew formula `aravis` 0.8.36**, bottles for arm64 Sonoma/Sequoia/Tahoe/"golden_gate" and x86_64 Sonoma, plus Linux; `gobject-introspection` is a build dependency (so the typelib should be built since `introspection` defaults to `auto` — [meson_options.txt#L23](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/meson_options.txt#L23)); formula last changed 2026-10-06 ([Formula/a/aravis.rb](https://github.com/Homebrew/homebrew-core/blob/62967b0a1e5adb912fde3b160b73aa696c12672e/Formula/a/aravis.rb), [formulae.brew.sh JSON](https://formulae.brew.sh/api/formula/aravis.json)). The formula's own `test do` only compiles/links a C program; it does not test Python.
- Upstream macOS CI builds with **`-Dintrospection=disabled`** ([.github/workflows/aravis-macos.yml#L30](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/.github/workflows/aravis-macos.yml#L30)) — Python-on-macOS is not exercised upstream.
- Upstream doc: "Using the GNU build system on macOS is not directly supported, but can be mimicked…" ([building.md#L73-L91](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/building.md#L73-L91)).
- Open macOS issues include [#1092](https://github.com/AravisProject/aravis/issues/1092) (2026-08: `--gv-discovery-interface` does not pin GVCP broadcast to selected NIC on macOS) and [#887](https://github.com/AravisProject/aravis/issues/887) (buffer timestamp 0 with Lucid Atlas10 on macOS M1, unresolved; maintainer says pop vs timeout_pop are identical).

### Windows
- Official statement: "[MSYS2](https://msys2.org) provides native Aravis packages … The package includes the DLL, headers and utilities" + MSVC/Conan build path ([building.md#L93-L109](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/building.md#L93-L109)).
- MSYS2 package [`mingw-w64-aravis`](https://packages.msys2.org/base/mingw-w64-aravis) is at **0.8.33-4** (behind 0.8.36), for ucrt64 / clang64 / clangarm64 (no `mingw64` listed on the page today).
- CI: MinGW builds **with introspection** and `-Dgv-n-buffers=1` ([aravis-mingw.yml#L52](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/.github/workflows/aravis-mingw.yml#L52)); MSVC builds with introspection **disabled** ([aravis-msvc-conan2.yml#L77](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/.github/workflows/aravis-msvc-conan2.yml#L77)). `gv-n-buffers` = number of packets fetched per `g_socket_receive_messages()` call ([meson_options.txt#L19](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/meson_options.txt#L19), [arvgvstream.c#L995-L1060](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L995-L1060)), i.e. Windows CI receives one packet per syscall.
- Windows links ws2_32 + iphlpapi; no packet socket ([meson.build#L96-L101](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/meson.build#L96-L101)).
- Field reports: [#752](https://github.com/AravisProject/aravis/issues/752) (open; 4K iDS/Hikrobot GigE camera, ~20 MiB/s and timeouts on Win10 vs ~90 MiB/s on Ubuntu with the same camera; unresolved, MTU/jumbo suspected), [#830](https://github.com/AravisProject/aravis/issues/830) (open; Windows firewall blocks GVSP, then 0 fps "Control lost" over Wi-Fi), [#759](https://github.com/AravisProject/aravis/issues/759) (open; "Problem popping buffer in windows"), [#1064](https://github.com/AravisProject/aravis/issues/1064) (open, 2026-03; arv-viewer + fake GV camera on Win11 needed extra GStreamer plugin packages).

### Python access (PyGObject / GObject Introspection)
- Aravis has **no PyPI package** (`https://pypi.org/pypi/aravis/json` → 404) and **no conda-forge package** (`api.anaconda.org/package/conda-forge/aravis` → 404; `conda-forge/aravis-feedstock` does not exist; only `teraview/aravis 0.5.12` on anaconda.org).
- PyGObject on PyPI (3.58.1, 2026-10-09) ships **sdist only, no wheels in any release** (checked the PyPI JSON for every release) → `pip install pygobject` needs a C compiler + gobject-introspection/cairo dev files. conda-forge has `pygobject` 3.58.1 for linux-64/aarch64, osx-64/arm64, win-64 (`api.anaconda.org/package/conda-forge/pygobject`), but no matching Aravis typelib there.
- Practical per-OS route: Linux = distro `gir1.2-aravis-0.8` + `python3-gi` (system Python, not a uv venv unless built); macOS = `brew install aravis pygobject3` (Homebrew Python); Windows = MSYS2 Python + `python-gobject` (not python.org CPython). None of these fit SkellyCam's uv/PyPI-wheel workflow out of the box.
- Alternative that avoids GI: Aravis is a plain C API (`arv_*` functions, [src/arvcamera.h](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h)), so ctypes/cffi or a small pybind11/nanobind/PyO3 shim over the shared library is feasible; you'd still have to ship glib/gobject/gio/libxml2/zlib shared libraries. Not prototyped here.
- Upstream Python tests exist and pass in my build: [tests/fake.py](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/tests/fake.py) etc.

## 3. API surface relevant to SkellyCam

| Capability | API | Source |
|---|---|---|
| Discovery | `arv_update_device_list()`, `arv_get_n_devices()`, `arv_get_device_id/address/vendor/model/serial_nbr/protocol(i)`; interface selection `arv_select_interface`, `arv_enable_interface` | [src/arvsystem.h#L35-L53](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvsystem.h#L35-L53) |
| Open | `arv_camera_new(name)` — accepts device id or IP (I used `"127.0.0.1"`) | [src/arvcamera.h#L56](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L56) |
| Feature access by name | `arv_device_get/set_{integer,float,boolean,string}_feature_value`, `arv_device_execute_command`, generic `arv_device_get_feature_value(GValue)`, `arv_device_set_features_from_string` | [src/arvdevice.h#L143-L179](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvdevice.h#L143-L179) |
| Stream + buffer pool | `arv_camera_create_stream(cam, cb, user_data, destroy, &err)` (0.10 API; 0.8 lacks `destroy`), `arv_buffer_new_allocate(payload)`, `arv_stream_push_buffer`, `arv_stream_timeout_pop_buffer` | [arvcamera.h#L60](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L60), [porting-0.10.md](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/porting-0.10.md) |
| GV tuning | packet size / auto packet size / packet delay / stream channel / multipart / stream options | [arvcamera.h#L237-L266](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L237-L266) |
| Socket buffer | stream properties `socket-buffer` (FIXED/AUTO) + `socket-buffer-size` | [ethernet.md#L16-L32](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/ethernet.md#L16-L32), [arvgvstream.c#L225-L260](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L225-L260) |
| Packet resend | property `packet-resend` default `ALWAYS`, forced to `NEVER` when the device's GVCP capability register lacks the resend bit | [arvgvstream.c#L1850-L1859](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1850-L1859), [arvgvdevice.c#L1904-L1905](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L1904-L1905), [arvgvdevice.c#L2072](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L2072). Verified: fake camera stream reported `packet-resend = NEVER`. |
| Stats | `arv_gv_stream_get_statistics(n_resent, n_missing)`; note in Python `stream.get_statistics()` on a GvStream resolves to this 2-tuple, not the 3-tuple `ArvStream` one | [arvgvstream.h#L74-L76](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.h#L74-L76); test output `(n_resent_packets=0, n_missing_packets=0)` |
| Triggers | `arv_camera_set_trigger/_source`, `software_trigger`, `clear_triggers` | [arvcamera.h#L124-L131](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L124-L131) |
| Chunk data | `arv_camera_set_chunk_mode/_state/set_chunks`, `arv_camera_create_chunk_parser`, `arv_chunk_parser_get_{integer,float,string,boolean}_value(parser, buffer, "ChunkX")` | [arvcamera.h#L281-L288](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L281-L288); unit test [tests/genicam.c#L1159-L1230](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/tests/genicam.c#L1159-L1230) (passed in my run) |
| Multipart | `arv_camera_gv_is_multipart_supported/_set_multipart`; leader parsing per part | [arvcamera.h#L242-L244](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvcamera.h#L242-L244), [arvgvstream.c#L497-L528](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L497-L528) |
| Thread-safety | not thread-safe per object; different objects in different threads OK (except `ArvInterface`); push/pop buffer are safe from callback thread | [thread-safety.md](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/docs/reference/aravis/thread-safety.md) |

### Raw vs compressed frames
- `ArvBufferPayloadType` enumerates IMAGE, CHUNK_DATA, EXTENDED_CHUNK_DATA, MULTIPART, GenDC, and JPEG / JPEG2000 / H264 — the latter three documented as "**(not supported)**" ([src/arvbuffer.h#L64-L92](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.h#L64-L92)). The GVSP leader handler only fills image geometry/timestamps for IMAGE / EXTENDED_CHUNK / CHUNK / MULTIPART; anything else gets only the host timestamp ([arvgvstream.c#L439-L531](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L439-L531)).
- So with Aravis, frames arrive as **uncompressed GenICam PFNC pixel data** (Mono8/Mono16/Bayer/RGB…) laid out in the buffer; the test frame was `pixel_format=0x01080001` (Mono8), 512×512 = 262144 bytes = payload exactly. Debayering/encoding is the application's job.

## 4. Timestamps and PTP

- `arv_buffer_get_timestamp()` = **camera timestamp in ns** ("Not all devices provide reliable timestamp…"), `arv_buffer_get_system_timestamp()` = host time when the frame was received: [src/arvbuffer.c#L379-L437](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.c#L379-L437).
- How it is computed: on the GVSP **leader** packet, `system_timestamp_ns = g_get_real_time()*1000` (host wall clock, µs resolution) and the 64-bit leader timestamp is converted with the device's tick frequency; if tick frequency is 0 the device timestamp silently falls back to the system timestamp ([arvgvstream.c#L460-L531](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L460-L531)). Leader parse: [arvgvspprivate.h#L452-L464](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L452-L464); tick→ns: [arvgvspprivate.h#L729-L743](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L729-L743); tick frequency read once from bootstrap registers 0x93C/0x940 at stream creation ([arvgvdevice.c#L571-L597](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvdevice.c#L571-L597), [arvgvstream.c#L1617](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvstream.c#L1617)). Note the `system_timestamp` is taken at leader arrival, i.e. before the frame is complete.
- **PTP: no dedicated API in libaravis.** `grep -rni "ptp\|1588" src/` returns nothing at HEAD. The only PTP mention is in the GStreamer element: optional `add-reference-timestamp-meta` property (added 2026-10-03, commit ee31d82f1, not in any release yet) that attaches the raw device timestamp with caps `timestamp/x-ptp`, documented as "Only an absolute time if the device clock is PTP-synchronized" ([gst/gstaravis.c#L563-L567](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L563-L567), [#L631-L641](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L631-L641), [#L1203-L1209](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/gst/gstaravis.c#L1203-L1209)).
- Maintainer position ([issue #258](https://github.com/AravisProject/aravis/issues/258), closed 2019): PTP "only requires to set the correct values of a set of Genicam features … using the arv_device_*feature_value family of functions". I.e. enabling PTP (`PtpEnable` / older `GevIEEE1588`, status, latch) is done through generic feature access; Aravis itself never touches PTP.
- Host↔camera clock correlation: bootstrap timestamp-control/latch register offsets are defined ([arvgvcpprivate.h#L116-L120](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L116-L120)) but no `.c` file uses them (`grep -rn -i "latch\|TIMESTAMP_CONTROL" src/*.c` → empty). Application must do latch via GenICam features.
- **Action commands (scheduled / synchronous triggering): not implemented.** GVCP command enum stops at PENDING_ACK; no ACTION_CMD ([arvgvcpprivate.h#L249-L282](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L249-L282)); only the capability bit and "action late" status/error codes are defined ([#L102](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvcpprivate.h#L102), [arvgvspprivate.h#L92](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvgvspprivate.h#L92) commented "GEV 2.0"). Feature request [issue #184](https://github.com/AravisProject/aravis/issues/184) "Scheduled Action Commands" is open since 2018-08-09 (last activity 2023-12-16). Draft [PR #468 "camera: action API support"](https://github.com/AravisProject/aravis/pull/468) (opened 2021-02-09, 186 additions, still open; commit message "Without implementation for now"; maintainer: "I'm not fond of the current API. It is too low level."). A SkellyCam PTP+scheduled-trigger workflow would need to hand-craft GVCP ACTION_CMD UDP packets itself (outside Aravis), or rely on free-running PTP-timestamped frames, or use the camera's PTP-synced timer/"scheduled" features where vendors expose them as GenICam features.

## 5. Executed tests (Docker on Windows 11 host, Docker Desktop)

### 5a. Distro Aravis 0.8.30 + PyGObject 3.48.2, fake GigE Vision camera on loopback
Image: `scratchpad/research/docker_aravis/Dockerfile` (`ubuntu:24.04` + `aravis-tools aravis-tools-cli gir1.2-aravis-0.8 python3-gi python3-numpy`).
Driver: `scratchpad/research/run_aravis_docker.sh`. Script: `scratchpad/research/aravis_fake_camera_capture.py`.

```
docker build -t skellycam-aravis-test docker_aravis
docker run --rm --network none -v <research>:/work:ro skellycam-aravis-test bash /work/run_aravis_docker.sh
#   arv-fake-gv-camera-0.8 -i 127.0.0.1 &
#   arv-tool-0.8
#   python3 -I /work/aravis_fake_camera_capture.py --device 127.0.0.1 --frames 100
#   python3 -I /work/aravis_fake_camera_capture.py --device 127.0.0.1 --frames 100 --frame-rate 100
```
Output (full in `aravis_docker_run.log`):
```
arv-tool-0.8 -> Aravis-Fake-GV01 (127.0.0.1)
[0] id='Aravis-Fake-GV01' protocol='GigEVision' address='127.0.0.1' vendor='Aravis' model='Fake' serial='GV01'
feature Width: '512'  Height: '512'  PixelFormat: 'Mono8'  AcquisitionFrameRate: '25'  GevSCPSPacketSize: '1400'
feature PtpEnable / GevIEEE1588 / ActionDeviceKey: <not in GenICam XML>     (fake camera has no PTP)
GevTimestampTickFrequency (bootstrap register): 1000000000 Hz
payload=262144 bytes, pixel_format=Mono8, region=(0,0,512,512)
GvStream packet-resend=NEVER socket-buffer=FIXED socket-buffer-size=0 packet-timeout=20000 frame-retention=100000
first frame: width=512 height=512 pixel_format=0x01080001 bytes=262144 payload_type=IMAGE
frame_id, device_timestamp_ns, system_timestamp_ns, d_device_ms, d_system_ms
65401, 1792950110704996000, 1792950110707606000, 0.000, 0.000
65402, 1792950110720003000, 1792950110727766000, 15.007, 20.160
65403, 1792950110760003000, 1792950110767622000, 40.000, 39.856
...
fps (device timestamps) = 24.66   fps (system timestamps) = 24.57
buffer.get_data() copy time: mean=0.026 ms for 262144 bytes
fps (wall clock incl. startup) = 24.51  ok=100 bad=0
--- at --frame-rate 100 ---
device-timestamp interval ms: mean=9.984 std=0.160
system-timestamp interval ms: mean=10.001 std=10.383
fps (device timestamps) = 100.16   fps (system timestamps) = 99.99
fps (wall clock incl. startup) = 91.77  ok=100 bad=0
stream.get_statistics() raw: (n_resent_packets=0, n_missing_packets=0)
```
Observations:
- The fake camera's "device" timestamp is just host `g_get_real_time()*1000` ([src/arvfakecamera.c#L795-L796](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvfakecamera.c#L795-L796)), so this proves the plumbing, not real PTP accuracy. Even so, at 100 Hz the device-stamped intervals had 0.16 ms std while host receive stamps had ~10 ms std (frames arrived in pairs: ~20 ms then ~0.05 ms), illustrating why host receive time must not be used for sync.
- `buffer.get_data()` via PyGObject returns a **copy** as Python `bytes` (`(array length=size) (element-type guint8)` annotation, [arvbuffer.c#L144-L156](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/src/arvbuffer.c#L144-L156)); 0.026 ms for 256 KiB here, so ~1 ms for a 10 MB frame would be expected (extrapolated, not measured).
- **Pitfall found:** my first run (without `--network none`) discovered a *different* fake camera at `172.17.0.2` on the shared Docker bridge with the same id `Aravis-Fake-GV01`; `update_device_list()` listed only one device (id collision), `Camera.new('Aravis-Fake-GV01')` opened the foreign one and `start_acquisition` failed with `GigEVision write_register timeout`. Lessons: open by IP/serial, isolate camera NICs, and be aware discovery broadcasts on all interfaces.
- Upstream-API trap: 0.8.30's GIR lacks `ArvDevice.get_feature_value` generic accessor (added 0.8.32 per [NEWS.md](https://github.com/AravisProject/aravis/blob/482547a3d56e3aa8d22d7ffed33c9f1588bfe17a/NEWS.md)); `get_string_feature_value('Width')` errors with "Not a ArvGcString"; `dev.get_feature(name).get_value_as_string()` works everywhere.

### 5b. Aravis HEAD (0.9.3-dev, API 0.10) built from source + upstream test suite + same Python script
Image `docker_aravis_build/Dockerfile` (ubuntu:24.04 + meson/ninja/gcc/glib/libxml2/libusb/gobject-introspection dev). Driver `build_aravis_head.sh`. Run with `--network none`.
```
meson setup -Dviewer=disabled -Dgst-plugin=disabled -Ddocumentation=disabled -Dintrospection=enabled -Dtests=true build
ninja -C build && meson test -C build
 1/10 evaluator OK | buffer OK | misc OK | dom OK | genicam OK (includes chunk_data_test)
 6/10 python/device.py OK | python/fake.py OK | python/exception.py OK | fake OK
10/10 aravis:network / fakegv OK 16.83s       -> Ok: 10, Fail: 0
#define ARAVIS_HAS_PACKET_SOCKET 1
Python (Aravis-0.10.typelib, arv-fake-gv-camera-0.10 on 127.0.0.1, --frame-rate 100):
  PyGObject (3, 48, 2), Aravis GIR namespace version 0.10 ... ok=100 bad=0
  fps (device timestamps) = 90.71, wall 68.51 (startup included)
```
(When the same build ran *with* the default Docker bridge network, `fakegv` timed out at 60 s after a 9.8 s discovery — plausibly the same foreign-fake-camera interference; with `--network none` it passed.) Full log: `aravis_head_meson_test.log`. The same capture script runs unchanged against both GIR namespaces 0.8 and 0.10.

## 6. Rust bindings: aravis-rs
- [robohouse-delft/aravis-rs](https://github.com/robohouse-delft/aravis-rs): crates `aravis` + `aravis-sys` **0.11.1** (published 2025-02-10; last commit a911bf0 2025-02-10 "Bump version to v0.11.1"), BSD-2-Clause (crates.io API), 174,899 downloads.
- Generated from GIR with gtk-rs `gir`; README: "Not all of the API has been tested. Some parts … may be missing" ([README.md](https://github.com/robohouse-delft/aravis-rs/blob/a911bf002a0511a1c9a0c68a0bcd7ef4aa32aabe/README.md)).
- Links dynamically to system `aravis-0.8` via pkg-config/system-deps; feature flags up to `v0_8_31` ([aravis-sys/Cargo.toml](https://github.com/robohouse-delft/aravis-rs/blob/a911bf002a0511a1c9a0c68a0bcd7ef4aa32aabe/aravis-sys/Cargo.toml), [aravis/Cargo.toml](https://github.com/robohouse-delft/aravis-rs/blob/a911bf002a0511a1c9a0c68a0bcd7ef4aa32aabe/aravis/Cargo.toml)) — no 0.10 API support, no vendoring; so it inherits exactly the same native-dependency distribution problem as PyGObject. Not compiled/run here.

## 7. Verdict
- **Linux:** viable and the best-supported target (distro packages, packet-socket fast path, CI, passing test suite, verified Python capture).
- **macOS:** probably viable via Homebrew (bottled 0.8.36 incl. arm64); Python/GI on macOS is not tested upstream (CI builds without introspection) and I could not test it here.
- **Windows:** library builds and CI passes (MinGW, MSVC), but: MSYS2 package lags (0.8.33), Python bindings require MSYS2's Python, MSVC CI has no introspection, no packet socket, one-packet-per-syscall receive in CI config, and an open unresolved throughput report (#752). Viable for low/moderate bandwidth; risky for multi-camera high-bandwidth capture without own benchmarking.
- **Sync:** Aravis gives you the camera's 64-bit timestamp per frame (PTP time if the camera is PTP-locked), chunk parsing, and generic feature access to enable PTP — but no PTP helper and **no action-command support** (open since 2018). Frame-level sync would have to be "free-run + PTP timestamps + post-hoc alignment", or camera-side PTP-synchronised frame start via vendor features, or a hand-written GVCP ACTION_CMD sender.
- **Packaging:** the biggest practical blocker for SkellyCam: there is no pip-installable or conda-forge Aravis, and PyGObject has no wheels. Shipping it means bundling glib/gobject/gio/libxml2 + Aravis shared libs per OS (LGPL-compliant as separate shared libs) and either PyGObject or a custom ctypes/cffi/extension binding.
- Overall: **viable as an optional Linux-first backend; not a drop-in, pip-installable, equally-good backend on all three OSes.**
