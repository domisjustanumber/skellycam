export const meta = {
  name: 'usb-camera-investigation-phase1',
  description: 'Build + run Windows camera test harnesses per goal, draft Linux/macOS tests, then adversarially verify every claim',
  phases: [
    { title: 'Investigate', detail: 'one agent per topic: research, write harness, run on this Windows machine, draft other-OS tests' },
    { title: 'Verify', detail: 'skeptic per topic re-reads results and re-runs key commands to refute claims' },
  ],
}

const COMMON = `
You are part of an investigation for the skellycam project (multi-camera motion capture with low-cost USB UVC webcams).
Repo root: C:\\Users\\Dom\\GitHub\\freemocap\\skellycam  (Windows 11, Git Bash + PowerShell available, NOT elevated).
All your work goes under research\\usb_cameras\\ — read research\\usb_cameras\\README.md FIRST for layout, the per-frame log schema and result-JSON conventions. Do NOT modify the skellycam package itself. Do NOT git commit.

The overall goals (the user's words):
 1. Native (M)JPEG extraction from cameras (no decode/re-encode).
 2. Obtain as accurate as possible timing of when light hits the glass on every camera.
 3. USB bandwidth allocation control so as many cameras as possible run on one USB bus. On Linux 'modprobe uvcvideo quirks=128' does what the user needs but needs sudo; something controllable from inside an app is wanted.
 4. Consistent naming of USB devices across reboots/USB reconnects.
 5. Works across macOS, Linux, Windows with as much shared code as possible.
OpenCV is already used and needs no investigation (use it only as a baseline for comparison). libuvc (https://github.com/libuvc/libuvc) is a suggested candidate. Python, Rust or C++ from-scratch approaches are all in scope.

HARD RULE FROM THE USER: make no assertion without a test result and a reproducible harness. Every finding you report must cite the result file(s) that support it and the exact command that produced them. Facts you only read in docs/source must be labelled status "documented-untested" and should, where possible, become a drafted test for a platform you cannot run here. Open the actual pages/source you cite (WebSearch/WebFetch are available via ToolSearch: query "select:WebSearch,WebFetch"); a search snippet is not a source.

This machine's cameras (all bound to Windows usbvideo.sys):
 - Razer Kiyo Pro  VID 1532 PID 0E05  (composite instance USB\\VID_1532&PID_0E05\\9&3A0ECB01&0&4)
 - Logitech C922   VID 046D PID 085C  (composite instance USB\\VID_046D&PID_085C\\B76395EF)
 - Logitech C930e  VID 046D PID 0843  (composite instance USB\\VID_046D&PID_0843\\7&7DCC7CE&0&4)
USB controllers: Intel USB 3.20 xHCI (PCI\\VEN_8086&DEV_7A60) and Intel USB 3.10 xHCI (PCI\\VEN_8086&DEV_1138).
The C930e is RESERVED: a later phase will swap its driver to WinUSB. Do not change any driver in this phase.

Shared hardware discipline (several agents run at once):
 - EVERY command that opens a camera must be wrapped: uv run --script research/usb_cameras/tools/camlock.py -- <command...>
 - Hold the lock for at most ~3 minutes per invocation; never hold it while compiling or researching. If you wait a long time, that is other agents testing — keep working on something else.
 - Fix exposure/white-balance manually where an API allows it when measuring timing or fps, and record the settings.

Toolchain:
 - Python: write PEP 723 single-file scripts run with 'uv run --script' (uv is on PATH, Python 3.12). Do not use the repo .venv.
 - Rust: installed just now at %USERPROFILE%\\.cargo\\bin (cargo.exe, rustc.exe) — NOT on PATH in your shells; use the full path or prepend it. MSVC toolchain.
 - C/C++: Visual Studio 2022 Community, MSVC 14.42, Windows SDK 10.0.22621. Use "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat" then cl/cmake (CMake is bundled under Common7\\IDE\\CommonExtensions\\Microsoft\\CMake\\CMake\\bin). Build outputs go under research\\usb_cameras\\<your dir>\\build (add a .gitignore there for binaries).
 - Downloads (source tarballs, binaries) go in their own empty directory under C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\\scratchpad\\downloads\\<name>\\ ; vendored source you build may be placed under research\\usb_cameras\\<dir>\\third_party\\ with a note of the exact URL + commit/tag.
 - Admin actions: only where your brief explicitly allows; do them via Start-Process powershell -Verb RunAs -ArgumentList '-File <script>' with the script writing a log to a file you then read (the user clicks the UAC prompt; wait up to ~5 minutes polling for the log). Always write a matching revert script.

Privacy: frames from these cameras show the user's room. Keep saved sample images to the minimum needed as evidence (a few per camera), store them under results/, and do not describe people/room contents in your report beyond what the test needs.

For OTHER platforms (Linux, macOS) you cannot run here: write complete stand-alone tests the user can run (PEP 723 Python, shell, or small C/Rust programs with build instructions), with a header comment saying exactly what to run, what hardware/permissions it needs, and what JSON it writes to results/<platform>/<hostname>/<test>/. Make them robust (clear errors, no interactive prompts unless unavoidable). Note: every drafted test is unverified until the user runs it — say so.

Your final answer is returned to an orchestrator, not a human: return the structured object requested, with concrete numbers, file paths (repo-relative) and commands.`

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    summary: { type: 'string', description: 'Dense paragraph: what was built, what was measured, headline numbers, verdict for this topic' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          status: { type: 'string', enum: ['verified-here', 'refuted-here', 'documented-untested', 'inconclusive'] },
          platform: { type: 'string' },
          evidence_files: { type: 'array', items: { type: 'string' } },
          command: { type: 'string' },
          numbers: { type: 'string', description: 'key measured values with units' },
          sources: { type: 'array', items: { type: 'string' }, description: 'URLs actually opened' },
        },
        required: ['claim', 'status', 'platform', 'evidence_files', 'command'],
      },
    },
    harness_files: { type: 'array', items: { type: 'string' } },
    drafted_tests: {
      type: 'array',
      items: {
        type: 'object',
        properties: { platform: { type: 'string' }, path: { type: 'string' }, run: { type: 'string' }, measures: { type: 'string' }, needs: { type: 'string' } },
        required: ['platform', 'path', 'run', 'measures'],
      },
    },
    candidate_assessment: {
      type: 'array',
      description: 'one row per library/approach examined in this topic',
      items: {
        type: 'object',
        properties: {
          approach: { type: 'string' }, language: { type: 'string' },
          windows: { type: 'string' }, linux: { type: 'string' }, macos: { type: 'string' },
          verdict: { type: 'string' },
        },
        required: ['approach', 'verdict'],
      },
    },
    system_changes: { type: 'array', items: { type: 'string' }, description: 'anything changed on this machine (registry, drivers, installs) + how to revert' },
    open_questions: { type: 'array', items: { type: 'string' } },
    handoff_for_phase2: { type: 'string', description: 'what the WinUSB/libuvc phase or later phases need from you' },
  },
  required: ['topic', 'summary', 'findings', 'harness_files', 'drafted_tests', 'candidate_assessment', 'system_changes', 'open_questions'],
}

const TOPICS = [
  {
    key: 'naming',
    prompt: `TOPIC: Goal 4 — consistent device identity across reboots / reconnects. Your directory: research/usb_cameras/naming/.
1. Write a no-admin Windows Python (ctypes) tool that, for every UVC camera, gathers ALL identity-relevant data: SetupAPI device instance IDs for the composite parent and video function, hardware/compatible IDs, DEVPKEY_Device_LocationPaths and LocationInfo, ContainerId, BusReportedDeviceDesc, parent hub + port number chain, the device interface symbolic links used by Media Foundation / DirectShow (KSCATEGORY_VIDEO_CAMERA / KSCATEGORY_CAPTURE), AND the raw USB descriptors read through the parent hub with IOCTL_USB_GET_NODE_CONNECTION_INFORMATION_EX(_V2) and IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION (device descriptor, iManufacturer/iProduct/iSerialNumber strings, full configuration descriptor including every VideoStreaming alternate setting's wMaxPacketSize/bandwidth and UVC format/frame descriptors, VC header dwClockFrequency, bcdUVC). Save the parsed descriptors to results/windows/<hostname>/naming/descriptors.json — the bandwidth and timing agents will reuse it, so make the parsed structure clean and document it. Also record what the names/paths exposed by OpenCV (cv2_enumerate_cameras path), Media Foundation (MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK), DirectShow/FFmpeg dshow device names ("@device_pnp_..." alternative names) are, and map each back to the USB identity.
2. Determine for each camera whether it has a USB serial number, whether Windows uses it in the instance ID (check the IgnoreHWSerNum usbflags registry values under HKLM\\SYSTEM\\CurrentControlSet\\Control\\UsbFlags read-only), and what would identify it if two identical models were plugged in.
3. Persistence test here: you MAY use one UAC-elevated script that runs 'pnputil /restart-device' on each camera's composite parent (hold camlock while doing it) and re-dump, to test reconnect stability of each identifier. Reboot and physical replug can't be done by you: write a Windows script the user runs before/after (a) reboot, (b) replug same port, (c) move to a different port, that saves snapshots and diffs them into a stability table.
4. Linux draft: script gathering /dev/v4l/by-id, /dev/v4l/by-path, udevadm info properties (ID_SERIAL, ID_SERIAL_SHORT, ID_PATH, ID_PATH_TAG, devpath), sysfs serial/busnum/devpath, plus the same before/after diff workflow; and an example udev rule pattern for stable symlinks (documented-untested). macOS draft: pyobjc AVFoundation AVCaptureDevice uniqueID/modelID/localizedName + IOKit (ioreg -p IOUSB -l -w0 / IORegistry via pyobjc or subprocess) locationID, USB Serial Number, and how AVFoundation uniqueID maps to locationID+VID+PID; same diff workflow.
5. Produce a recommended cross-platform identity scheme (e.g. serial when present and unique per VID:PID, else port path) with per-platform derivation, backed by the data. Include a small reusable Python module research/usb_cameras/naming/camera_identity.py implementing it for Windows (tested) and Linux/macOS (drafted).`,
  },
  {
    key: 'mjpeg',
    prompt: `TOPIC: Goal 1 — native MJPEG extraction (raw compressed JPEG bytes straight from the camera, no decode). Your directory: research/usb_cameras/mjpeg/.
Build and test on Windows, each producing per-frame logs in the README schema plus a summary JSON (fps achieved vs requested per mode, % valid JPEG (SOI..EOI + decodes with Pillow/turbojpeg), payload sizes, process CPU% per camera, and whether frames were ever decoded/re-encoded by the pipeline):
 (a) PyAV (already a skellycam dependency) with FFmpeg's dshow input and vcodec=mjpeg passthrough: demux packets without decoding. Check timestamps PyAV gives.
 (b) Media Foundation IMFSourceReader selecting the camera's native MJPG media type with no decoder (C++ with cl, and if practical a Python ctypes/comtypes version). Record MFSampleExtension timestamps the sample carries (sample time, MFSampleExtension_DeviceTimestamp, MFSampleExtension_Timestamp etc.) so the timing agent can reuse — but leave timing analysis to them.
 (c) WinRT Windows.Media.Capture MediaFrameReader in MJPG subtype (Python 'winrt-*' packages or C++/WinRT) — does it hand over compressed buffers? SystemRelativeTime?
 (d) DirectShow with MJPG pin and no decoder (only if cheap; PyAV path already covers dshow).
 (e) OpenCV baseline: CAP_DSHOW and CAP_MSMF with MJPG fourcc and decode, plus OpenCV's CAP_PROP_FORMAT=-1 / CAP_PROP_CONVERT_RGB=0 raw mode if it yields raw JPEG — measure CPU of decode path for comparison (this is a baseline only).
Run each at a common mode all cameras support (e.g. 1280x720@30 MJPEG) and at each camera's max MJPEG mode, single camera and all three cameras together. Note any API that silently gives decoded data.
Drafts: Linux — (1) PyAV v4l2 input_format=mjpeg passthrough, (2) a pure-Python V4L2 mmap capture (raw ioctl via fcntl, or the 'linuxpy' package) requesting V4L2_PIX_FMT_MJPEG, both logging v4l2 buffer timestamps/flags; macOS — (1) PyAV avfoundation input (does it support passthrough? test whether pixel_format/vcodec options allow mjpeg), (2) pyobjc AVCaptureVideoDataOutput with videoSettings=None / CMFormatDescription media subtype check for 'dmb1'/'jpeg' to see if compressed buffers are deliverable. Both write the same summary JSON.
Also quickly check (documented + if cheap, tested) openpnp-capture and GStreamer (mfvideosrc/ksvideosrc ! image/jpeg ! appsink) as cross-platform options.`,
  },
  {
    key: 'timing',
    prompt: `TOPIC: Goal 2 — most accurate possible estimate of when light hits the sensor for every frame on every camera. Your directory: research/usb_cameras/timing/.
Key idea to test: UVC payload headers carry PTS (per UVC spec: device-clock time when raw frame capture begins) and SCR (device clock + USB SOF counter), from which capture start can be mapped onto the host clock. Open and cite the UVC 1.1/1.5 spec text (or a faithful mirror) and the Linux uvcvideo clock code (drivers/media/usb/uvc/uvc_video.c uvc_video_clock_*) for semantics.
1. Windows UVC metadata: find in Microsoft docs exactly how usbvideo.sys exposes UVC payload headers (MetadataBufferSizeInKB<pin> registry value — exact key path, the device-interface key vs device key — KSSTREAM_UVC_METADATA / KSCAMERA_METADATA_ITEMHEADER, MF_CAPTURE_METADATA_FRAME_RAWSTREAM / MFSampleExtension_CaptureMetadata). You ARE allowed (user approved) to set this registry value for the three cameras via one UAC-elevated script and restart the devices with pnputil /restart-device (hold camlock while restarting). Write the revert script and record the change in system_changes.
2. Build a capture tool (C++ Media Foundation is likely simplest; Python if practical) that logs per frame: host QPC on arrival, MF sample time, every MFSampleExtension timestamp present, and parsed UVC metadata (PTS, SCR STC, SCR SOF, and the host-side timestamp usbvideo attaches if any). Read dwClockFrequency from research/usb_cameras/naming results if present (the naming agent dumps descriptors to results/windows/<hostname>/naming/descriptors.json) or read it yourself.
3. Write research/usb_cameras/tools/analyze_frames.py (shared, schema-driven) computing: inter-frame interval mean/std/min/max, timestamp jitter vs a fitted linear clock model, offsets between host arrival and each OS/device timestamp (mean, std), device-clock drift vs host (ppm), and SCR→host mapping following the Linux approach; plus a cross-API comparison of which timestamp is least noisy.
4. Ground-truth: build a screen-flash/timecode harness: a full-screen window showing a high-contrast pattern that changes every display refresh with a large binary/bar timecode of the QPC time at Present (use something with reliable flip timing, e.g. a small C++ D3D11/DXGI flip-model app logging frame statistics, or pygame/pyglet with vsync and logged swap times — justify the choice). Cameras viewing the screen decode the timecode in each frame → per-frame (capture timestamp − displayed time) for each camera; the constant display latency cancels between cameras, giving inter-camera relative accuracy of each timestamp source. The user has said they will point the cameras at the monitor: FIRST grab one frame per camera (under camlock) and look at it (Read the image) to see whether the screen is visible; if it is, run the test; if not, build/smoke-test the harness and report it ready for phase 2. Also measure each camera's exposure time setting and note rolling-shutter row position of the timecode.
5. Drafts: Linux — V4L2 buffer timestamps (flags TSTAMP_SRC_SOE/EOF, monotonic) + the UVC metadata capture node (V4L2_META_FMT_UVC / 'UVCH' via /dev/videoN+1) giving PTS/SCR + host SOF timestamps, same frame-log schema; macOS — AVFoundation CMSampleBuffer presentation timestamps vs host time (CMClockGetHostTimeClock / mach_absolute_time), same schema. Plus the screen-flash harness runnable on Linux/macOS if feasible (Python + pyglet/pygame).`,
  },
  {
    key: 'bandwidth',
    prompt: `TOPIC: Goal 3 — USB isochronous bandwidth allocation control. Your directory: research/usb_cameras/bandwidth/.
1. Source-level facts (open and cite the actual code): Linux drivers/media/usb/uvc — uvc_fixup_video_ctrl (what UVC_QUIRK_FIX_BANDWIDTH=0x80 really does, and crucially whether it applies to compressed/MJPEG formats in current mainline vs older kernels; cite the commit(s) that changed it), uvc_video_init / alt-setting selection in uvc_video_start_streaming (best_psize >= dwMaxPayloadTransferSize), the quirks module parameter and whether it can be set per-device at runtime (sysfs /sys/module/uvcvideo/parameters/quirks writability, whether a value change takes effect on rebind via /sys/bus/usb/drivers/uvcvideo/unbind+bind), and any per-device quirk mechanism (usb quirks via usbcore.quirks, uvc_ids table). Same for libuvc: how uvc_stream_start picks the alt setting from dwMaxPayloadTransferSize and whether an app can override it (look at src/stream.c). And Windows usbvideo.sys: any documented control over the alt setting / bandwidth (likely none) — open MS docs.
2. Windows measurements: using descriptors (results/windows/<hostname>/naming/descriptors.json from the naming agent, or read them yourself via hub IOCTLs) list every VS alt setting's bytes/microframe per camera and which controller/root port each camera is on. Then empirically find the limits on this machine: open increasing combinations of cameras/modes (MJPEG at several resolutions/fps, also YUY2 for contrast) simultaneously via Media Foundation or DSHOW/PyAV and record which combos start, fail (and the error/HRESULT), or degrade (fps drops). Try to infer which alt setting Windows picked (e.g. from failure thresholds, or from any ETW USB trace you can capture — elevated logman/xperf/pktmon USB capture is allowed via ONE UAC prompt if it gives the actual selected alt setting / bandwidth; revert any tracing config). If all cameras are on different controllers, say so — the test then doesn't stress one bus; report what a stress test would need (a hub) and write it as a user-runnable test.
3. Linux drafts: (a) a script that, for each camera at given mode, reads the negotiated dwMaxPayloadTransferSize and the chosen alt setting (uvcvideo trace parameter / dmesg, or /sys/kernel/debug/usb/devices, or usbmon) with default quirks and with quirks=128 to show the difference, and counts how many cameras can stream concurrently in each case (needs sudo — clearly labelled as the comparison baseline); (b) a no-sudo-at-runtime approach design: libusb/libuvc with a forced smaller alt setting after detaching uvcvideo, requiring only a one-time udev rule granting the user access to the USB device nodes — write the udev rule and the test program (C against libuvc, or Python libusb) measuring whether MJPEG streams survive a smaller alt setting and how many cameras then fit. macOS draft: what is possible (libusb on macOS: can it claim a UVC interface without root on macOS 12+? find the actual libusb/macOS docs and issue threads) plus a test program.
4. Quantify the theoretical budget: USB 2.0 high-speed periodic budget (80% of microframe = 6000 bytes... cite), USB 3 SuperSpeed isochronous limits, and what an MJPEG 1280x720@30 stream actually needs (measured payload sizes from the mjpeg agent's results if present, or your own quick capture) vs what each camera requests (dwMaxPayloadTransferSize); this gap is the headroom a bandwidth fix recovers. Read the UVC probe/commit values: on Windows this may not be reachable without driver access — note it, and leave the libusb-side measurement for phase 2.`,
  },
  {
    key: 'rust',
    prompt: `TOPIC: Rust candidates (cross-cutting goals 1,2,3,5). Your directory: research/usb_cameras/rust/. Cargo is at %USERPROFILE%\\.cargo\\bin\\cargo.exe (not on PATH).
1. nokhwa (cross-platform: MSMF / V4L2 / AVFoundation backends): build a small capture program that requests MJPEG and obtains the raw buffer without decoding; verify bytes are JPEG; log per-frame host arrival time and any timestamp nokhwa exposes (README frame-log schema JSONL). Check what its MSMF backend does under the hood (read the source in ~/.cargo/registry) re: decoding, timestamps, and device identity (what does it expose as a unique id?). Run with each camera and all three at once under camlock.
2. nusb (pure-Rust USB) and rusb (libusb bindings): determine from source/docs whether isochronous transfers are supported on each OS in the current released versions (cite versions). If nusb or rusb can do iso on Windows with WinUSB, sketch a from-scratch UVC streaming program (probe/commit, alt setting selection under app control, payload header parsing with PTS/SCR) — write it, make it compile, and leave it ready to run in phase 2 when the C930e is on WinUSB (do NOT change drivers now). Also check existing crates: 'uvc' (libuvc bindings), any pure-Rust UVC crate — compile-check them.
3. Draft Linux/macOS run instructions for these programs (cargo run commands, permissions needed).
Report build times, binary sizes, and how much code would be platform-specific.`,
  },
  {
    key: 'libusb',
    prompt: `TOPIC: libuvc / libusb based capture (user-space UVC stack) — prepare everything so phase 2 can test it on Windows the moment the C930e is on WinUSB, and draft Linux/macOS tests. Your directory: research/usb_cameras/libusb/.
1. Build libusb (latest release, from source or the official release binaries — cite URL/version) and libuvc (current master of https://github.com/libuvc/libuvc — note commit) on Windows with MSVC/CMake. libuvc needs pthreads etc. on Windows: find the least-hacky way (pthreads4w, a known Windows fork, or patches) and document every patch. Build its example + a custom test program research/usb_cameras/libusb/uvc_capture_test.c that: lists devices with VID/PID/serial/bus/port path; opens a chosen camera; prints the probe/commit negotiation (dwMaxPayloadTransferSize, dwMaxVideoFrameSize, bmFramingInfo); streams MJPEG at a requested mode; writes per-frame JSONL in the README schema with PTS/SCR from the payload headers (check whether libuvc exposes them: uvc_frame_t fields capture_time / capture_time_finished, and the stream's pts/last_scr — patch if necessary) and host QPC times; optionally FORCES a smaller isochronous alt setting than libuvc would choose (add a command-line override; patch libuvc's stream.c selection if needed) to test bandwidth reduction. Make sure it compiles and that running it now cleanly reports 'no accessible device' (cameras are on usbvideo).
2. pyuvc (Pupil Labs Python bindings to libuvc: https://github.com/pupil-labs/pyuvc) — they use it cross-platform with MJPEG + turbojpeg; read how they handle Windows drivers (libusbK), macOS permissions, bandwidth_factor (a bandwidth knob!), and timestamps. Can it be pip-installed on Windows/py3.12 today (wheels)? Try in an isolated uv env. Report.
3. From-scratch Python: a pure-Python UVC streamer over libusb using the 'libusb1' (python-libusb1) package's async isochronous transfers, implementing probe/commit, app-chosen alt setting, payload-header parsing (FID/EOF/PTS/SCR), MJPEG frame assembly, and the frame-log schema. Make it import-clean and dry-run against enumeration now; it gets tested in phase 2.
4. WinUSB swap tooling for phase 2 (WRITE ONLY, DO NOT RUN): an elevated script that installs the inbox WinUSB driver on the C930e composite parent USB\\VID_046D&PID_0843 (prefer Microsoft's inbox winusb.inf generic 'WinUsb Device' via SetupAPI/DiInstallDevice or pnputil — avoid installing self-signed certificates if possible; libwdi/wdi-simple is the fallback, document its cert install), plus the rollback script restoring usbccgp/usbvideo, plus a verification step. Research whether libusb on Windows needs the composite parent or the MI_00 function on WinUSB for a UVC IAD function, and choose accordingly with justification.
5. macOS: find (open the sources) whether libusb/libuvc can claim UVC interfaces on macOS 12+ without root / entitlements (libusb_detach_kernel_driver on darwin needs root or com.apple.vm.device-access), and draft a macOS test that checks it. Linux: draft the libuvc + udev-rule (no-sudo-at-runtime) test, runnable as-is.`,
  },
  {
    key: 'prior_art',
    prompt: `TOPIC: survey of existing cross-platform capture libraries and prior art relevant to all five goals, to make sure no strong candidate is missed. Your directory: research/usb_cameras/prior_art/ (write survey notes there as markdown + any tiny test scripts).
Examine at least: libuvc, pyuvc (Pupil Labs), openpnp-capture, nokhwa (Rust) — light touch since others test it, GStreamer (mfvideosrc/ksvideosrc/v4l2src/avfvideosrc), FFmpeg/libavdevice (dshow/v4l2/avfoundation), linuxpy, v4l2-python3, pygrabber, WinRT MediaCapture, AVFoundation via pyobjc, Linux libcamera (UVC pipeline handler!), DepthAI/Arducam/ELP vendor SDKs, OBS's capture code (libobs win-dshow/win-capture, v4l2, mac-avcapture), and multi-camera mocap projects that solved sync/naming with webcams (e.g. FreeMoCap history, Pupil Labs, OpenPose/anipose, Theia, Captury, 'mocap webcams sync' blogs/papers). Also any library that exposes UVC PTS/SCR on Windows or macOS, and anything that controls UVC bandwidth from userspace.
For each: language, license, platforms, MJPEG passthrough (Y/N/how), timestamp source exposed, device identity exposed, bandwidth control, maintenance status (last release date, commits in 2025-2026), and Python bindings. Open the repos/docs you cite (record URLs and the date/version seen).
Where a claim can be checked quickly on this Windows machine with a few lines of code (e.g. does GStreamer/pip-installable X give raw MJPEG? does pygrabber expose device paths?), DO test it under camlock and cite the result file; otherwise mark documented-untested. Return a ranked shortlist with reasons and the concrete claims other phases should verify.`,
  },
]

const VERIFY = (t, r) => `You are an adversarial verifier for one topic of a USB camera investigation. ${COMMON}

The '${t.key}' agent reported the findings below. Your job is to REFUTE what you can. For each finding:
 - open the cited evidence files and check that the numbers in the claim are actually in them and that the test measured what the claim says (e.g. 'raw MJPEG' claims: are the bytes really camera JPEG and not re-encoded? timing claims: is the clock domain right, units right, sample sizes adequate? naming claims: was stability actually tested across a reconnect?);
 - re-run the cited command for at least the 3 most important verified-here claims (under camlock if it touches a camera) and compare;
 - check that cited sources say what is claimed (open them);
 - check that drafted tests for other platforms at least parse/compile (python -m py_compile, cargo check, bash -n, etc.) and would write results where the README says.
Fix trivial harness bugs you find only if needed to re-run; record them. Do not broaden scope.

Return JSON: {topic, verdicts:[{claim, verdict: confirmed|weakened|refuted|unverifiable, reason, rerun_numbers}], harness_bugs:[...], drafted_test_issues:[...], corrected_summary}.

Findings to verify:
${JSON.stringify(r, null, 1)}`

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    verdicts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
      reason: { type: 'string' }, rerun_numbers: { type: 'string' } }, required: ['claim', 'verdict', 'reason'] } },
    harness_bugs: { type: 'array', items: { type: 'string' } },
    drafted_test_issues: { type: 'array', items: { type: 'string' } },
    corrected_summary: { type: 'string' },
  },
  required: ['topic', 'verdicts', 'harness_bugs', 'drafted_test_issues', 'corrected_summary'],
}

const results = await pipeline(
  TOPICS,
  t => agent(`${COMMON}\n\n${t.prompt}`, { label: `investigate:${t.key}`, phase: 'Investigate', schema: FINDINGS_SCHEMA }),
  (r, t) => r ? agent(VERIFY(t, r), { label: `verify:${t.key}`, phase: 'Verify', schema: VERDICT_SCHEMA }).then(v => ({ key: t.key, report: r, verification: v })) : { key: t.key, report: null, verification: null },
)
return results
