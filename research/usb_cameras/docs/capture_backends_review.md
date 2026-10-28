# Capture backends: openpnp-capture branches, the MF tool, and MF vs DirectShow

2026-10-28 · Dom

Three questions asked after the goal-1 MJPEG work, answered against this study's results:

1. How do the PyAV/FFmpeg and Media Foundation (MF) results compare with the openpnp-capture backend on skellycam branches `dom/openpnp-capture` and `dom/openpnp-capture-mf` (May 2026)?
2. How does the "MF native MJPG" path work, and how would it get into Python?
3. What are the pros and cons of MF against DirectShow (DS), given reports that MF capture is flaky?

Confidence labels follow [REPORT.md](../REPORT.md): **measured** (a result file supports it), **inferred** (from source code or docs, not run), **web** (external report, re-checked by an adversarial verifier but not reproduced here).

## 1. The openpnp-capture branches

### What the branches actually run

- `dom/openpnp-capture` (2026-05-09 to 05-13) replaced OpenCV capture with openpnp-capture through a local editable package, `../openpnp-capture-python` (sibling of the skellycam checkout, commit `0aec3cc`).
- `dom/openpnp-capture-mf` (2026-05-19, worktree `../skellycam-opnpc-mf`) adds raw-MJPEG passthrough (`raw_frame_bytes`, `raw_frame_byte_count`) and a `hardware_timestamp_ns` field. Its doc `docs/mjpg-vs-rgb-capture.md` says these work with a "MediaFoundation DLL (built with `-DCAP_MEDIAFOUNDATION=ON` from `domisjustanumber/openpnp-capture`)".
- **That MF build does not exist.** The DLL the wrapper loads, `openpnp-capture-python/openpnp_capture/_vendor/openpnp_capture/win-x64/openpnp-capture.dll`, has SHA-256 `3280266977f6ee70687d997455cd7463507ed5077d5de1235c4ef5d8f8e77b21`. That is the stock upstream v0.0.30 build this study probed ([prior_art/SURVEY.md](../prior_art/SURVEY.md)). The fork `domisjustanumber/openpnp-capture` is at upstream `32a9bdd` (local checkout and `git ls-remote origin`, 2026-10-28). It has no `build/` folder, and the string `CAP_MEDIAFOUNDATION` appears nowhere in it. **Measured** (hash, git state).
- Upstream's Windows backend is DirectShow with a sample grabber forced to `MEDIASUBTYPE_RGB24` (`openpnp-capture/win/platformstream.cpp:393`). Its `SampleCB(double time, IMediaSample*)` discards `time` (`platformstream.cpp:82`). The study's probe saw decoded pixels (first bytes `dbf4ffdb`, not `FFD8`) at full rate: C922 29.9 fps, generic 25.7 fps ([prior_art_openpnp_capture/result.json](../results/windows/Gerald/prior_art_openpnp_capture/result.json)). **Measured.**

### Comparison (Windows)

| | openpnp-capture (both branches) | PyAV / FFmpeg DS `vcodec=mjpeg` | MF IMFSourceReader, native MJPG |
| --- | --- | --- | --- |
| Camera's own JPEG bytes | No: always RGB24 | Yes, headers = MF | Yes (reference) |
| Frame rate | Full | Full | Full |
| CPU per camera | Not measured. Inferred to be near OpenCV CAP_DSHOW (24.6–40% of a core), since both decode MJPEG in DS | 0.9–1.6% | 0.7–2.2% |
| Per-frame time | `perf_counter_ns` around copying an already-decoded frame; `hardware_timestamp_ns` always 0 | `pkt.pts` nominal (33.333 ms steps) | OS time on a 16 ms grid, or UVC PTS (~0.5 ms) with the metadata registry value |
| Camera ID | `<name> <DS device path>`; DS paths changed after the C930e driver swap (REPORT finding 23) | DS name / alternative name | MF symbolic link (also unstable) |
| Enumeration | Opens every camera | Opens only the named one | Can filter by symbolic link |

### Defects on `dom/openpnp-capture-mf` with the stock DLL

1. **Camera loop crash in normal light. Measured offline.** `OpenPnPCamera.capture_raw_frame_into` sets the byte count to the last `FF D9` pair in the buffer. In RGB data that is any pixel with R=255, G=217. `openpnp_get_frame` slices to that count, and `reshape(h, w, 3)` raises `ValueError`, which reaches `kill_everything()`. Replayed on synthetic 720p buffers: a dim frame works, one warm highlight pixel fails, and a bright gradient frame has 1,688 matching pairs. Script: [prior_art/openpnp_raw_capture_eoi_check.py](../prior_art/openpnp_raw_capture_eoi_check.py). Result: [eoi_scan_check.json](../results/windows/Gerald/prior_art_openpnp_capture/eoi_scan_check.json). Dim test rooms would hide it.
2. **`hardware_timestamp_ns` is always 0. Inferred.** The ctypes binding passes a 5th argument that upstream `Cap_captureFrame` lacks. On x64 Windows the callee ignores it, so nothing errors.
3. **No CPU saving even with a raw-MJPEG DLL. Inferred.** The raw branch still runs `cv2.imdecode` on every frame to fill `image[0]`. Only the frontend re-encode is skipped.
4. **Minor:**
   - The end-marker scan over an over-sized buffer can include stale bytes from an earlier, larger frame. The C API should return the length.
   - `raw_frame_bytes` (h×w×3) doubles the shared memory per frame.

### What holds up

- **The bandwidth-contention mapping matches findings 16–17.** The branch starts workers together and turns "a peer streams, this camera never delivers" into HTTP 409 `usb_bandwidth_contention` (`skellycam/core/camera_group/usb_bandwidth.py`).
- **Its user guidance partly conflicts with the study:**
  - "Lower resolution… reduces bandwidth" does not hold. The C930e reserves the same max alt at 720p and 1080p, and only slightly less at 480p.
  - "Different host controller" is stricter than needed: cameras on different root ports did not compete.
- **Worth keeping regardless of backend:** the frontend passthrough of camera JPEG bytes (`frontend_payload_bytearray.py`), the contention error, and the format-selection UI.

## 2. How the MF native-MJPG path works

The measured MF path is C++, not Python: [mjpeg/msmf/mf_mjpeg_capture.cpp](../mjpeg/msmf/mf_mjpeg_capture.cpp), built by [build.bat](../mjpeg/msmf/build.bat) with MSVC against `mfplat`, `mf`, `mfreadwrite` and `mfuuid`. [run_one.py](../mjpeg/run_one.py) runs the `.exe` as a subprocess, which writes `frames_<i>.bin` and `frames.jsonl`, and Python validates them afterwards. So the 0.7–2.2% CPU figure is for the C++ process alone.

1. **Startup:** `CoInitializeEx` and `MFStartup`.
2. **Find the camera:** `MFEnumDeviceSources` lists video capture sources without opening any. Match by VID/PID in the symbolic link, then `ActivateObject` only that one.
3. **Create the reader:** `MFCreateSourceReaderFromMediaSource` with `MF_READWRITE_DISABLE_CONVERTERS = TRUE`. The reader may then not insert a decoder, so a format it can't pass through fails instead of silently decoding.
4. **Pick the native mode:** loop `GetNativeMediaType` (the camera's UVC formats), choose `MFVideoFormat_MJPG` at the wanted size and rate, and `SetCurrentMediaType` with that object. Read back `GetCurrentMediaType` to confirm MJPG, which proves no decoder.
5. **Read loop, one thread per camera:** a blocking `ReadSample` returns an `IMFSample` carrying:
   - the bytes via `ConvertToContiguousBuffer` + `Lock`, one complete JPEG with its exact length;
   - a 100 ns timestamp (on the 16 ms grid);
   - `MFSampleExtension_CaptureMetadata` with the UVC payload header (PTS/SCR), once `MetadataBufferSizeInKB0` is set. The timing tool [timing/src/mf_uvc_timing.cpp](../timing/src/mf_uvc_timing.cpp) reads this.
6. **Frame Server:** on Windows 10 and later, frames reach the process through the Windows Camera Frame Server service. Its CPU is unmeasured because it needs elevation.

**Routes into skellycam (none measured from Python yet):**
- A small C++ extension (nanobind or pybind11) doing steps 2–5 and returning `(bytes, os_ts, uvc_header)` or writing to shared memory. This is the main recommendation.
- Pure ctypes/comtypes: pywin32/comtypes lack the MF interfaces, so their method tables would have to be declared by hand.
- PyAV: FFmpeg has no MF input (`dshow`, `gdigrab`, `vfwcap` only), so it is DS.
- GStreamer `mfvideosrc` (pip `gstreamer-bundle`) and SDL3's MF camera API, which both delivered native JPEG here with no compiling.
- nokhwa via PyO3.

## 3. MF vs DirectShow

Evidence: workflow `wf_31366494-74f` (script [workflows/mf-vs-dshow-reliability-wf_31366494-74f.js](../workflows/mf-vs-dshow-reliability-wf_31366494-74f.js)). Four gatherers each fed one adversarial verifier, which checked 100 claims and refuted none. The 69 claims on MF vs DS (gatherers `local` and `web-ds-downsides`) came out 48 confirmed and 21 weakened. The other 31 were on the timer question (see below). Full output: [results/agent_reports/mf_vs_dshow_reports_and_verifications.json](../results/agent_reports/mf_vs_dshow_reports_and_verifications.json); journal: `journal_wf_31366494-74f.jsonl`.

**Limitation:** the run was interrupted and resumed after a new user question about Windows timers. Two of the four web gatherers (`web-mf-flaky`, `web-app-choices`) researched that timer question instead (see [windows_timer_resolution.md](windows_timer_resolution.md)). The MF-flakiness evidence below comes from the local gatherer, the DS-downsides gatherer, and the verifiers' "missed" lists. OpenCV's backend-priority history and GStreamer's choice of default source were not researched.

### Where the "MF is flaky" reputation comes from

| Source | What failed | MF itself? |
| --- | --- | --- |
| OpenCV `CAP_MSMF` | Opening each Logitech camera took 39–41 s here (generic camera 3.4–3.7 s). The [OpenCV forum](https://forum.opencv.org/t/initializing-msmf-camera-and-setting-properties-appears-to-take-40-seconds/18958) shows ~40 s plus ~39 s per property set, with DS instant. MSMF also repeats frames on the generic camera (48 of ~300) and decodes at 46–156% of a core. **Measured** + **web**. | No. Raw MF setup on the same cameras took 26–92 ms. skellycam's `determine_backend.py` comments ("MSMF adds 5–10 ms latency") are about this wrapper and unmeasured. |
| Frame Server, 2016 | Windows 10 1607 stopped delivering MJPEG/H.264 to apps, breaking Skype and many webcams ([Kinovea admin, 2016-08-23](https://www.kinovea.org/en/forum/viewtopic.php?id=814)). **Web.** | It hit DS apps too, and Microsoft fixed it. |
| Frame Server, ongoing | Frame Server (Monitor) crashing repeatedly on Windows 11 22H2 with a C920 ([Q&A 2023](https://learn.microsoft.com/en-us/answers/questions/4102987/windows-camera-frame-server-monitor-continually-cr), [Q&A](https://learn.microsoft.com/en-us/answers/questions/4213515/the-windows-camera-frame-server-service-terminated), [Ed Tittel](https://www.edtittel.com/blog/fighting-camera-frame-server-crashes.html)), unresolved. **Web.** | Yes: every MF capture depends on the service. |
| Hot-plug | `ActivateObject` froze for 5–10 minutes after frequent plug/unplug on Windows 11 ([Q&A 2024-07](https://learn.microsoft.com/en-us/answers/questions/1819830/why-does-the-interface-get-stuck-for-5-10-minutes)), unresolved. **Web**, one report. | Yes. |
| Chromium | MF has been the default since 2019 ([c4f58b38](https://github.com/chromium/chromium/commit/c4f58b3898a92a0f7001f45415acf215b6481c65)). [`kModelIdsBlockedForMediaFoundation`](https://raw.githubusercontent.com/chromium/chromium/main/media/capture/video/win/video_capture_device_factory_win.cc) forces ~25 VID:PIDs to DS: mostly capture cards (Elgato, Hauppauge, Empia) and laptop built-in cameras, few standalone webcams. MF+D3D11 is also blocked for two webcams (`E_MF_SAMPLEALLOCATOREMPTY`), and VMware's virtual webcam hangs under MF. **Web** (source code). | Device-specific. |
| nokhwa 0.10.11 | Its format list keeps at most 2 FourCCs and hides MJPEG on the Logitech cameras; exact MJPEG requests still stream. **Measured.** | No, a wrapper. |

### Measured on Gerald (short runs: 10 s cells, ≤ ~32 s sessions)

- **Frame data is equivalent.** Identical JPEG headers, same fps, ~1–2% of a core on both ([mjpeg/RESULTS.md](../mjpeg/RESULTS.md) findings 1–2).
- **Bandwidth refusal surfaces differently.**
  - DS (PyAV) fails at open with `OSError(5)`; OpenCV DSHOW reports "open failed".
  - MF activate + reader + `SetCurrentMediaType` succeed (26–71 ms), then the first `ReadSample` fails with `0x800718CF` ("A camera interface doesn't have the desired bandwidth").
  - So an MF health check must read one sample.
- **`MF_E_REBOOT_REQUIRED`, self-inflicted (10-25).** Setting `MetadataBufferSizeInKB0` (needed for MF's UVC metadata) plus a device restart vetoed by LogiTuneAgent left `DN_NEED_RESTART` on the camera interfaces. MF then failed at `ActivateObject` with `0xC00D7167` on the C922, C930e and Kiyo, while PyAV DS still captured 192 valid MJPEG frames from the C922. A replug cleared it ([PROGRESS.md](../PROGRESS.md) hazards).
- **Overnight rerun 10-27/28.** The only failures were expected bandwidth refusals on both APIs, plus two transient MF DeviceNotFound misses of the generic camera. In one of those, the camera re-enumerated ~150 ms after MF released it. One MF multi-open batch stalled ~94 s and was killed. The cause is unknown: synchronous `ReadSample` has no timeout, but the harness is also a suspect ([RERUN_20261027.md](../results/windows/Gerald/RERUN_20261027.md)).
- **mf_uvc_timing sessions.** In 106 `*.session.json` files (50,894 frames), errors appear only in 4 Kiyo sessions.
- **Kiyo fault.** It hit every API (KS, MF, OpenCV, PyAV, a minimal DS graph). Once, inside the reboot-required window, PyAV DS opened it as raw YUY2, while SDL3 over MF delivered MJPEG.
- **Controls.** C930e manual exposure was not reliably applied on any API. LogiTuneAgent was running throughout. The MJPEG matrix set controls via DS even for its MF cells.
- **Enumeration.** MF lists 8 sources here; DS lists 15 (adds OBS-Camera 1–4, OBS Virtual Camera, NVIDIA Broadcast, SpoutCam).
- **Not tested on either API:** runs over ~32 s, one process per camera (skellycam's model), mid-stream unplug, sleep/resume, and another app holding the camera.

### Pros and cons

**Media Foundation**
- **Pros:**
  - The only Windows API route found to the camera's own timestamps: UVC PTS/SCR in `MFSampleExtension_CaptureMetadata`, ~0.5 ms (the method floor) vs 4.4–5.0 ms for OS times. **Measured.** Whether DS/KS clients can read it was not tested.
  - Self-describing errors.
  - Lists only real cameras.
  - Microsoft's supported path: camera sharing between apps ([Windows-Camera wiki](https://github.com/microsoft/Windows-Camera/wiki): "not in DirectShow apps"), sensor groups ("not supported in DShow capture pipeline"), MF virtual cameras, Device MFTs. **Web** (Microsoft docs).
- **Cons:**
  - Depends on Frame Server, whose CPU and latency are unmeasured.
  - Needs native code, GStreamer or SDL3.
  - Timestamps need an admin registry value plus a replug per camera, and on a LogiTune machine that step caused the reboot-required lockout.
  - Blocking `ReadSample` needs async mode (`IMFSourceReaderCallback`) or a per-process watchdog.
  - Bandwidth refusal shows up only at the first read.
  - Can't open DS-only virtual cameras; Chromium adds them from DS for this reason.
  - OS settings can strip MJPEG on the Frame Server path:
    - a Video rotation other than "No rotation" in camera Settings removes compressed types ([camera settings page](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-settings-page));
    - `EnableDshowRedirection` bit 0x2 decodes MJPEG in Frame Server;
    - the Windows 11 "Allow multiple apps" option forces a single media type ([Windows-Camera #72](https://github.com/microsoft/Windows-Camera/issues/72)).

**DirectShow**
- **Pros:**
  - Pure Python today via PyAV.
  - Fails fast at open.
  - Sees DS virtual cameras.
  - Kept working through the reboot-required lockout.
  - For these cameras it probably bypasses Frame Server: no `EnableDshowRedirection` value in their Device Parameters, read 2026-10-28. **Inferred**, never observed.
  - `qcap.dll` and `mfksproxy.dll` still get servicing builds (10.0.26100.x).
- **Cons:**
  - Microsoft labels DS legacy, superseded by MF, and says the DS camera pipeline "being in maintenance mode, lags behind" ([DirectShow](https://learn.microsoft.com/en-us/windows/win32/directshow/directshow), [DShow Bridge guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/dshow-bridge-implementation-guidance-for-usb-video-class-devices)). No removal date.
  - No camera sharing or sensor groups.
  - Device sample times are synthesized on these cameras (constant 333,333 per frame); DS timestamps were never scored against the flash ground truth.
  - Wrapper quirks:
    - OpenCV negotiates YUY2 at ~10 fps if FOURCC is set before size;
    - OpenCV uses the preview pin (no timestamps);
    - FFmpeg dshow drops frames when its real-time buffer fills, with only a log line.
  - A bridge can route DS through Frame Server anyway. The 2016 breakage hit DS apps. This machine also has an undocumented per-application list, `HKLM\SOFTWARE\Microsoft\OEM\DshowBridge\1` = `Launcher_Main.exe` (Logitech Camera Software), which `mfksproxy.dll` reads.

### Recommendation

Use the Chromium pattern: MF as the primary path for its UVC timestamps, with DS (PyAV) as a per-camera fallback. On the MF side:
- async reading or a per-process watchdog;
- a startup health check that reads one frame;
- automatic fallback on open or read errors.

The deciding evidence is still missing: a soak test of both stacks with one process per camera, 1 h or more, including a mid-stream replug. That needs the cameras under camlock and a human for the replug. Listed in [REPORT.md](../REPORT.md) further investigation.
