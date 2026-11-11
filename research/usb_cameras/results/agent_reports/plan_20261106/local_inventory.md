# Local inventory: reusable harness code for the 2026-11-06 per-OS test suites

Topic: `local_inventory` (read-only survey). Date: 2026-11-06. Study folder: `research/usb_cameras/` (all paths below are relative to it unless absolute).

No camera was opened, streamed or enumerated for this report. The only things run were toolchain version checks (`vswhere`, `uv`, `python`, `cargo`, `ffmpeg -version`, `wsl -l -v`), file listings and line counts, and four offline self-tests that open no device: `naming/usbdesc.py --selftest`, `naming/camera_identity.py --selftest`, `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py --selftest` and `timing/linux/v4l2_uvc_timing.py --self-test`. All four passed.

Labels: **measured** = a hardware result in `results/windows/Gerald/` supports it (path given); **inferred** = from reading the code or my own reasoning; **doc** = from source code or docs in the repo.

Test IDs used below come from the brief: T-ENUM/ID, T-FMT, T-CTRL-LIST, T-CTRL-EFFECT, T-MJPEG-ALL, T-CYCLE, T-BW, T-TS.

---

## 1. Toolchain on Gerald (checked 2026-11-06)

| Item | Value | How checked |
|---|---|---|
| OS | Windows 11 Home, build 26300 (10.0.26300) | `Win32_OperatingSystem` |
| Visual Studio | VS Community 2022 17.12.4 (`C:\Program Files\Microsoft Visual Studio\2022\Community`, installationVersion 17.12.35707.178); also VS Build Tools 2019 16.11.43 | `vswhere -all` |
| MSVC toolsets | 14.42.34433 (VS 2022) and 14.29.30133 (VS 2019) | `VC\Tools\MSVC` folder listing |
| Windows SDK | 10.0.22621.0 and 10.0.19041.0 | `Windows Kits\10\Include` listing |
| `cl` on PATH | **No.** Every `build*.bat` calls the hard-coded `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat` itself, and that file exists. | `which cl` |
| uv | 0.11.8 (2026-04-27) | `uv --version` |
| Python that `uv run --script` resolves by default | **3.12.13 from the skellycam `.venv`** (`uv python find` returns `skellycam\.venv\Scripts\python.exe`, because that venv is on PATH). Also installed: 3.14.2 (python.org), 3.13.13, 3.11.11, 3.10.20 (uv-managed). | `uv python find`, `uv python list --only-installed` |
| Rust | rustc 1.99.1 (2026-10-13), cargo 1.99.1 (user-level rustup) | `cargo --version` |
| FFmpeg CLI | 9.0.2 full_build (gyan.dev, winget). PyAV wheels ship their own FFmpeg, so this binary is not what PyAV uses. | `ffmpeg -version` |
| PowerShell 7 / gh | pwsh 7.6.9, gh 2.92.0 | version flags |
| GStreamer | Not on PATH (`gst-launch-1.0` not found) | `which` |
| CMake | Not on PATH (`libusb/build` used a CMake 3.29.5 from an earlier session) | `which cmake` |
| WSL / Docker | WSL2 "Ubuntu" and "docker-desktop" both Running | `wsl -l -v` |

Implication: the Windows suite can rebuild every C++ tool without installing anything. Because uv defaults to the skellycam venv's 3.12.13, the suite's runner should pin `--python 3.12` or `3.13` explicitly so results do not depend on which venv happens to be active.

## 2. Built binaries vs source (timestamps)

| Binary | Built | Source last edited (mtime) | Status |
|---|---|---|---|
| `mjpeg/build/mf_mjpeg_capture.exe` | 2026-10-27 23:05 | `mjpeg/msmf/mf_mjpeg_capture.cpp` 23:05 | current |
| `bandwidth/build/mf_multi_open.exe` | 2026-10-27 23:40 | `bandwidth/mf_multi_open.cpp` 23:36 | current |
| `timing/build/mf_uvc_timing.exe`, `flash_timecode.exe`, `devrestart.exe` | 2026-10-25 14:38 | `timing/src/*.cpp` 14:15–14:38 | current |
| `timing/build/dshow_open_probe.exe`, `kiyo_ks_mf_probe.exe`, `usb_ep0_probe.exe` | 2026-10-25 15:23 | 15:04–15:23 | current |
| `rust/build/release/{nokhwa_probe,mf_native_types,uvc_iso}.exe` | 2026-10-25 14:02–17:42 | `rust/*/src/*.rs` 13:59–17:31 | current |
| `libusb/build/cmake/bin/Release/*.exe`, `libusb/build/tests/win_usb_frame_qpc.exe` | earlier sessions | — | out of scope (libusb needs WinUSB) |

All in-scope binaries are at least as new as their sources. Git shows every source last committed 2026-10-28 09:47, which is the bulk commit, not an edit. Binaries are not in git (`.gitignore`), so a fresh checkout on another Windows PC has to run `mjpeg/msmf/build.bat`, `bandwidth/build.bat`, `timing/build_mf.bat` and `timing/build_kiyo_probe.bat`.

## 3. camlock

`tools/camlock.py` (64 lines, stdlib only) takes an exclusive OS lock on `research/usb_cameras/.camlock` (Windows `msvcrt.locking`, POSIX `fcntl.flock`), runs the command, and returns its exit code. If the process dies, the OS releases the lock. Exit code 75 means the lock wait timed out (default `--timeout-s 1800`).

Usage: `uv run --script research/usb_cameras/tools/camlock.py [--timeout-s N] -- <cmd...>`. `run_matrix.py`, `rust/run_windows_nokhwa.sh` and the timing wrappers take it once per cell, so each camera hold lasts under a minute.

Known defects (RERUN_20261027.md, "Harness bugs still open"):
- an exe has to be given by absolute path, and Git Bash by its full path;
- an outer `timeout` also counts the time spent waiting for the lock.

It serializes agents; it does not protect the cameras. On a single-user Linux or macOS box it costs nothing, and it works there unchanged (the flock branch). (inferred)

## 4. Windows inventory

Status column: **HW** = verified on hardware (result folder given); **draft** = never run on hardware; **do not reuse** = conflicts with the hazards or the no-driver-change rule.

### 4.1 Capture and format tools (C++, Media Foundation / DirectShow)

| Path | Lang / size | What it does | Flags that matter | Output | Status | Known defects | Serves |
|---|---|---|---|---|---|---|---|
| `mjpeg/msmf/mf_mjpeg_capture.cpp` (+ `build.bat`) | C++17, 683 lines | IMFSourceReader. Picks the **native** MJPG (or `--subtype`) type with `MF_READWRITE_DISABLE_CONVERTERS`, checks that the output subtype is still MJPG, and records every sample's bytes plus all MF timestamps (`llTimestamp`, sample time, DeviceTimestamp, `MFSampleExtension_Timestamp`, presence of capture metadata, scanline QPC). Also measures process and Frame Server CPU, open time and first-frame latency. Listing modes: `--list-enum` (MF order, **activates nothing**), `--list-dshow` (DS order + DevicePath, binds nothing), `--list --dev X` (activates only the matching sources and dumps native types), `--dshow-formats --dev X` (IAMStreamConfig caps). Controls: `ControlsJson` reads exposure, focus, WB, gain, backlight, powerline and AE priority (GetRange + Get) through IAMCameraControl / IAMVideoProcAmp / IKsControl, **from the MF source** (default) or **from the DS filter** (`--controls-only --via-dshow`). Sets only exposure, WB and AE priority. | `--dev SUBSTR` (repeatable, matched against the symlink), `--width/--height/--fps` or `--mode WxH@F` per dev, `--seconds`, `--warmup`, `--out`, `--exposure`, `--wb`, `--ae-priority`, `--decode-to NV12\|RGB32`, `--no-payload`, `--attr-dump N` | `meta.json`, `frames.jsonl`, `frames_<i>.bin` (u32 cam, u64 seq, u32 len, bytes); validated by `mjpeg_common.summarize_run` | **HW**: `results/windows/Gerald/mjpeg_rerun_20261027/` (table.md), `mjpeg_formats/20261028T030920Z/` | Records only the **size** of the UVC payload header blob, not PTS/SCR (that is in `mf_uvc_timing`). Focus/gain/zoom/brightness etc. are never set; brightness, contrast, saturation, sharpness, zoom, pan/tilt and focus-auto are never read. Holds every frame in RAM (a long 1080p60 run could reach GBs; inferred). One open per process, no cycle option. **No valid Kiyo capture on record**: `mjpeg_msmf/common_1280x720at30_kiyo/` is INVALID (read_error 0x8007001F, 0 frames). | T-FMT (MF + DS lists), T-MJPEG-ALL (any WxH@F), T-CTRL-LIST (7 controls, MF-source vs DS-filter), T-CTRL-EFFECT (exposure/WB only), T-CYCLE (per-process loop via wrapper), T-ENUM (`--list-enum/--list-dshow`) |
| `timing/src/mf_uvc_timing.cpp` (`timing/build_mf.bat`) | C++17, 386 lines | MF Source Reader, one thread per camera. Logs QPC arrival, MF sample time, every `MFSampleExtension_*`, and parses `KSCAMERA_METADATA_ITEMHEADER` / `KSSTREAM_UVC_METADATA` into **UVC PTS, SCR STC, SCR SOF** for the first and last payload of each frame. Sets exposure/WB, reads focus. | `--cam "<symlink substr>,W,H,FPS[,exp_log2[,wb_K]]"` (repeatable), `--seconds`, `--out`, `--save-mjpeg`, `--list` | `<key>.frames.jsonl`, `<key>.session.json`, `<key>.mjpeg` | **HW**: `results/windows/Gerald/timing/rerun_20261027/` (compact_table_all_runs.txt), `timing/flash_*` | The camera key is built from the symlink (instance ID), so it changes when a serial-less camera moves port (inferred). PTS needs the registry value (§4.3). Kiyo attempt `timing/kiyo_check/` = 0 frames, 21 errors (Kiyo fault). | T-TS (core), T-CTRL-EFFECT (exposure readback + image), T-MJPEG-ALL (`--save-mjpeg`) |
| `bandwidth/mf_multi_open.cpp` (`bandwidth/build.bat`) | C++17, 402 lines | Opens N cameras at once through MF (native type, converters off). Per camera: which step failed and its HRESULT, first-sample latency, steady fps, payload B/s, stalls. Prints `STREAMING` once all cameras have started or failed, so a wrapper can take a pipe snapshot. | `--cam "substr:MJPG:WxH@F"` (repeatable), `--seconds`, `--stagger-ms`, `--exposure`, `--wb` (previous values restored), `--save-dir/--save-max`, `--arrivals`, `--list [--list-match]` | one JSON | **HW**: `results/windows/Gerald/bw_concurrency_rerun_20261027/` (r05/r07 shared hub, r08 cross root port) | `steady_fps` hides start bursts; one open per process. | T-BW (core), T-CYCLE (concurrent opens per process), T-MJPEG-ALL (multi-camera `--save-dir`) |
| `timing/src/dshow_open_probe.cpp` (`timing/build_kiyo_probe.bat`) | C++17, 85 lines | Minimal DirectShow graph (capture filter → Null Renderer) with the HRESULT of each stage: bind, IAMCameraControl Get(Exposure), IAMStreamConfig SetFormat, RenderStream, Run, state after 1.5 s, Stop. | `--dev`, `--sub MJPG`, `--w/--h/--fps` | JSON on stdout | **HW** (rerun wrapper `results/windows/Gerald/timing/rerun_20261027/tools/dshow_probe_all.ps1`) | Gets **no sample bytes and no timestamps** (Null Renderer). One camera per run. | T-CYCLE (DS open stages, per process), T-BW (DS refusal stage), T-FMT (SetFormat acceptance) |
| `timing/src/kiyo_ks_mf_probe.cpp` | C++17, 174 lines | Path A: KS direct, `IOCTL_KS_PROPERTY` GET of exposure/focus/brightness/WB (a UVC GET_CUR on EP0, no streaming). Path B: MF reader stages plus a ReadSample HRESULT histogram and the count of frames carrying capture metadata. | `--dev`, `--ks-only`, `--mf-only`, `--no-controls`, `--seconds` | JSON | **HW** (10-25 Kiyo diagnosis, `results/windows/Gerald/timing/kiyo_lens/`) | Kiyo-named but camera-agnostic. | **Kiyo health gate** before each Kiyo test; T-CTRL-LIST via KS (third control path) |
| `timing/src/usb_ep0_probe.cpp` | C++17, 66 lines | Through the parent hub IOCTL, sends standard GET_DESCRIPTOR (device, LANGID, iProduct) to an instance ID. Checks whether EP0 answers at all, independent of usbvideo/MF. | `<USB\VID..\instance>` | JSON | **HW** (10-25 Kiyo) | Needs the instance ID, which changes when a serial-less camera moves port. | Kiyo health gate (EP0 alive?), T-ENUM |
| `timing/src/flash_timecode.cpp` | C++17 / D3D11, 152 lines | Full-screen pseudo-random black/white flash. Logs DXGI frame statistics (vblank QPC per present) as ground truth. | `--out`, `--seconds`, `--monitor`, `--seed`, `--list` | `display.jsonl`, `display.session.json` | **HW** (`results/windows/Gerald/timing/flash_*`, `rerun_20261027/`) | Floor about 0.5 ms; scan-out/rolling-shutter offset about 35 ms across image blocks (`timing/VERIFY_method.md`). | T-TS (optional ground truth) |
| `timing/src/devrestart.cpp`, `timing/scripts/recover_restart_cameras*.ps1`, `naming/win_restart_*` | C++ / PS | Restart PnP devices programmatically (optionally killing LogiTune first). | — | — | **Do not reuse.** LogiTune vetoes the restart and leaves DN_NEED_RESTART, after which MF fails with MF_E_REBOOT_REQUIRED (PROGRESS.md hazards; memory note). | none. Recovery = ask Dom to replug |

### 4.2 Python drivers, analysis and enumeration (Windows)

| Path | Lang / size | What it does | Flags | Output | Status | Known defects | Serves |
|---|---|---|---|---|---|---|---|
| `mjpeg/mjpeg_common.py` | Py, 659 lines (pillow, simplejpeg, psutil) | Camera table `WINDOWS_CAMERAS` (VID/PID substrings), `DEFAULT_CAMS` / `EXCLUDED_CAMS`, `RunWriter`, `summarize_run` (SOI/EOI, Pillow decode, simplejpeg strict and lenient decode, `wh` vs requested = SOF dims, fps, CPU), `jpeg_header` (DQT/SOF/DHT fingerprint, SHA-1 of the header up to SOS), `mf_controls()` (calls the MF tool with `--controls-only --via-dshow`), `devnode_status()` (Get-PnpDevice for all four VID/PIDs, flags DN_NEED_RESTART / DN_HAS_PROBLEM) | — | `summary.json` | **HW** (all mjpeg cells) | **`DEFAULT_CAMS = ("c922","c930e","usbcam")` excludes the Kiyo by default** (line ~121). Matching by VID/PID substring breaks if two cameras of one model are present (inferred). `aggregate.py` pools MF headers across cells. | T-MJPEG-ALL (validation core), T-CTRL-EFFECT (luma), device-health tagging for every test |
| `mjpeg/run_one.py` | Py, 59 lines | Applies controls through the MF tool's DS path, runs one capture command with a kill-on-timeout, reads controls back, and records DevNodeStatus and machine CPU before and after. | `--cams`, `--run-dir`, `--no-set`, `--exposure`, `--wb`, `--timeout-s`, `-- cmd` | `controls.json`, `capture_log.txt` | **HW** | Controls are always set via the DS filter, even for MF cells. | T-CTRL-EFFECT (before-stream set + readback), wrapper for every capture |
| `mjpeg/run_matrix.py` | Py, 178 lines | Matrix driver: backends × modes × sets, camlock per cell, never overwrites. | `--backend` (msmf, msmf-decoded-nv12, pyav-dshow, winrt, opencv-*), `--modes common,max`, `--sets single,all`, `--cams`, `--seconds`, `--root` | `<root>/mjpeg_<backend>/<label>/summary.json` | **HW** (`mjpeg_rerun_20261027/`) | Only "common" (1280x720@30) and "max" (taken from the **hard-coded** `max_mjpeg` table). No "every advertised mode". Kiyo excluded unless named. | T-MJPEG-ALL (add `--modes all`), T-CYCLE (outer loop) |
| `mjpeg/list_formats.py` | Py, 81 lines | DS IAMStreamConfig caps plus MF native types for the named cameras. Summarizes MJPG modes per API and the max mode, and records MF and DS enumeration order. | `--cams` | `results/windows/<host>/mjpeg_formats/<stamp>/summary.json` + raw JSON | **HW** (`mjpeg_formats/20261028T030920Z/`, `mjpeg_formats/summary.json` with Kiyo on 10-25) | DS caps are **collapsed to max_fps per size**, while MF lists each discrete rate, so "MF has 120 MJPG modes vs DS 17" for the C922 is a harness artifact. Frame sizes actually match exactly (C922 17/17, C930e 17/17, generic 5/5, Kiyo 4/4). No comparison with the USB descriptors. | T-FMT (both API lists; needs a descriptor diff and per-interval DS output) |
| `mjpeg/pyav/pyav_capture.py` | Py, 138 lines (`av>=12`, unpinned) | FFmpeg dshow/v4l2/avfoundation demux of MJPEG packets (never decoded), one thread per device. Logs packet pts and QPC arrival. | `--input-format`, `--device` (repeatable; Windows uses `video=@device_pnp_<path>` via `mjpeg_common.dshow_alt_name`), `--size`, `--fps`, `--dshow-graph-clock`, `--option k=v` | run dir (RunWriter contract) | **HW** (`results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/`) | `av` version not pinned (the probe used av 19.0.2). On 10-25 the Kiyo fell back to YUY2 under PyAV dshow (`mjpeg_pyav_dshow_format_probe/` is INVALID / Kiyo fault window). | T-MJPEG-ALL (DS byte path), T-CYCLE (DS in-process loop needs a new small script), T-TS (DS pts = synthesized) |
| `mjpeg/pyav/pyav_dshow_format_probe.py` | Py, 81 lines | Tries a list of modes through FFmpeg dshow, with or without `vcodec=mjpeg`, and reports which pin format was negotiated. | `--cam`/`--device`, `--mode` (repeatable), `--no-vcodec`, `--extra` | JSON | HW only for the Kiyo fault window (INVALID) | — | T-FMT (DS negotiation vs advertised), T-MJPEG-ALL fallback detection |
| `mjpeg/opencv/opencv_capture.py`, `mjpeg/winrt/winrt_capture.py` | Py, 175 / 229 lines | OpenCV CAP_DSHOW/MSMF and WinRT MediaFrameReader baselines. | `--api`, `--index`, `--set-order`, `--open-wait`; WinRT `--subtype`, `--reader-subtype` | run dir | **HW** (rejected paths, `mjpeg_rerun_20261027/`) | OpenCV opens by **index**, and indices changed (REPORT finding 23). | Baseline row only |
| `prior_art/pyav_dshow_probe.py` | Py, 265 lines (av==19.0.2, pillow) | PyAV on dshow/v4l2/avfoundation: are packets JPEG? Open by unique path; pts vs arrival, with and without `use_video_device_timestamps=0`. | `--seconds`, `--only`, `--device`, `--wallclock`, `--width/--height/--fps`, env `USBCAM_RESULTS_DIR` | `results/<plat>/<host>/prior_art_pyav_<fmt>/result.json` | **HW** Windows (`prior_art_pyav_dshow*`); Linux/macOS branches never run | Cross-platform by design. | T-MJPEG-ALL / T-TS on all three OSes (PyAV row) |
| `prior_art/cv2_enumerate_probe.py` | Py, 49 lines | `cv2_enumerate_cameras` index → name/path/VID/PID for MSMF/DSHOW/V4L2/AVF. | — | result.json | **HW** Windows (`prior_art_cv2_enumerate/`) | Enumeration only. | T-ENUM (OpenCV index mapping, all OSes) |
| `tools/dshow_exposure_read.py` | Py, 160 lines (comtypes) | Binds only the matching DS filters and **reads** exposure, brightness, gain and backlight (value, flags, range). | `--vidpid` (repeatable), `--out` | JSON | **HW** (rerun night context) | Read-only by design. | T-CTRL-LIST (pure-Python DS readback) |
| `tools/analyze_frames.py` | Py, 362 lines (numpy) | Schema-driven per-frame timing analysis for any backend: interval stats, drops, jitter vs a fitted periodic clock, device-clock ppm, PTS→host mapping that follows Linux `uvc_video_clock_update()`, STC−PTS latency. | `FRAMES.jsonl...`, `--device-clock-hz`, `--skip-first`, `--scr-window` | result JSON | **HW** + selftest (`results/windows/Gerald/timing/selftest_analyze_frames.json`) | — | T-TS on all OSes (already reads the Linux metadata `uvc_host_sof_ns`) |
| `timing/scripts/flash_analyze.py` (+ `flash_verify_*`, `flash_rows.py`, `flash_step_response.py`, `quantization_check.py`, `verify_grid_phase.py`) | Py | Flash ground-truth scoring, rolling-shutter / PTS semantics, step response (exposure effect), 16 ms grid check. | `--display`, `--capture`, `--mf-glob` | JSON | **HW** (`timing/rerun_20261027/`) | `flash_verify_method/extra`, `flash_rows` and `flash_exposure_scan` **crash on cameras without UVC metadata** (generic, Kiyo unless set). `flash_verify_method` assumes nominal E = 7.8125 ms. `flash_step_response` `rise_10_90` is wrong. `mf_fixed_gt.py` is circular. | T-TS (quantization, jitter, optional ground truth), T-CTRL-EFFECT (step rise as an exposure check) |
| `timing/scripts/run_flash_test.ps1` | PS, 28 lines | Starts `flash_timecode.exe` on every monitor plus `mf_uvc_timing.exe --save-mjpeg`. | `-RunDir`, `-Seconds`, `-Monitors`, `-Cams` | run dir | **HW** | **Default `-Cams` includes the Kiyo but not the generic camera**. Wrapper `results/windows/Gerald/timing/rerun_20261027/tools/run_flash_rerun.ps1` has the absolute repo path hard-coded. | T-TS |
| `timing/scripts/enable_uvc_metadata.ps1` / `revert_uvc_metadata.ps1` | PS, 48 / 5 lines | **Elevated.** Sets or removes `MetadataBufferSizeInKB0=5` under `DeviceClasses\{KSCATEGORY_VIDEO_CAMERA, KSCATEGORY_CAPTURE}\##?#USB#<inst>#...\#GLOBAL\Device Parameters`, then **`pnputil /restart-device` unless `-NoRestart`**. | `-Instances`, `-SizeKB`, `-Remove`, `-NoRestart`, `-Log` | log | **HW** (`results/windows/Gerald/timing/registry_enable_metadata*.log`) | **Default `-Instances` are 3 hard-coded instance IDs** (Kiyo `A&34494D13&0&0000`, C922 `8&268DA596&0&0000`, C930e `8&39DEC205&0&0000`). The C930e one is already stale (it became `&1&0000` after the 10-25 rollback), and any serial-less camera that moved port has a new ID. The default restart is the vetoed-restart hazard; revert also restarts. | T-TS **tier-1 option** (one-time admin config); must use `-NoRestart` + replug and resolve IDs at runtime |
| `bandwidth/win_usb_topology.py` | Py stdlib/ctypes, 446 lines | Hub tree up to the PCI controller, per-port connection info, **open pipes** (the alt the driver selected), full config descriptor per UVC device, VS alt settings with bytes per interval (HS mult and SS companion handled), formats/frames. | `--out`, `--pipes-only`, `--exclude VID:PID` | `results/windows/<host>/bw_topology/topology.json` | **HW** (`bw_topology_rerun_20261027/`) | Sends GET_DESCRIPTOR to every camera unless excluded (EP0 traffic; matters for the Kiyo). The pipe snapshot fires at a fixed time when called from `run_concurrency`. | T-BW (reserved bandwidth per mode, who shares which hub), T-FMT (descriptor side), T-ENUM (port chain) |
| `bandwidth/run_concurrency.py` | Py, 160 lines | Runs combos through `mf_multi_open.exe` and takes the pipe snapshot during `STREAMING`. | `--batch`, `--combo "label\|spec;spec"`, `--seconds`, `--stagger-ms`, `--budget-s`, `--list`, `--out-dir`, `--exclude`, `--save-dir`, `--exe` | `<batch>.json` | **HW** (`bw_concurrency_rerun_20261027/`) | No per-combo timeout. Snapshot at a fixed time. | T-BW, T-CYCLE (repeat combos) |
| `bandwidth/hs_budget_model.py`, `bandwidth/headroom.py` | Py, 123 / 106 lines | Offline USB 2.0 §5.11.3 microframe budget model vs observed refusals; reserved/used ratio and minimum alt per mode. | `--concurrency-dir`, `--solo-glob`, `--pair-glob`, `--topology`, `--out` | JSON | **HW** (`results/windows/Gerald/bw_budget_model/`, 26/26 agree) | **`hs_budget_model.py` line 81 hard-codes the shared-hub pair as PIDs `0843`/`4a55` ("same 05e3:0610 hub")**; it must derive sharing from the topology now that cameras moved. HS only (no SuperSpeed model for the Kiyo). | T-BW (prediction vs observation) |
| `bandwidth/verify/strict_jpeg_check.py` | Py, 140 lines (pillow 12.0.0, simplejpeg 1.8.2) | Marker walk (SOF dims, DRI/RST order, EOI position, trailing bytes) plus Pillow (warnings=error) plus libjpeg-turbo strict; `--selftest` corrupts copies. | `RUNDIR...`, `--out`, `--selftest` | JSON | **HW** (`results/windows/Gerald/phase2_bw_alt_verify/strict_jpeg_check_sweep.json`, `bw_rerun_20261027_analysis/`) | Keeps only 3 failure examples. | T-MJPEG-ALL (strict decode, SOF0 dims) on any OS |
| `naming/usbdesc.py` | Py stdlib, 474 lines | Parser for device/config/BOS/string descriptors and UVC VC/VS: **decodes Camera Terminal / Processing Unit `bmControls` into control names**, formats, frames (discrete/continuous intervals), alt settings, `dwClockFrequency`. | `--selftest` | dict | selftest OK (2026-11-06); used in every HW naming run | — | T-CTRL-LIST and T-FMT descriptor side on all OSes (bytes come from the hub IOCTL, sysfs or ioreg) |
| `naming/win_identity_dump.py` | Py ctypes, 711 lines | cfgmgr32 PnP properties (instance, LocationPaths, ContainerId, Address, parents), interface symlinks for the KS/MF categories, and descriptors through the parent hub. | `--out-dir`, `--label`, `--no-descriptors`, `--exclude-vidpid` (opt-in, env `NAMING_EXCLUDE_VIDPID`) | `identity_dump.json`, `descriptors.json`, `snapshots/<label>.json` | **HW** (`naming_rerun_20261027/`, `check_claims.json` 46/46) | Does not record the port's LastArrivalDate. | T-ENUM/ID, T-FMT/T-CTRL-LIST descriptor side |
| `naming/win_api_names.py` | Py, 334 lines (opencv-contrib 4.12.0.88, cv2-enumerate-cameras 1.4.0, imageio-ffmpeg 0.5.1) | Names, paths and order as seen by MF, DirectShow, FFmpeg dshow and OpenCV, each mapped back to the USB device. | `--out-dir`, `--exclude-vidpid` | `api_names.json` | **HW** (`naming_rerun_20261027/win_api_names/`) | Enumeration only; opens no stream. | T-ENUM/ID (index ↔ key per API) |
| `naming/camera_identity.py` | Py, 260 lines | The key scheme: `vid:pid:sn=<serial>` if the serial is usable and unique, else `vid:pid:port=<controller>/<chain>`. Windows implemented; Linux/macOS call the drafts. | `--selftest`, `--exclude-vidpid`, `--out` | JSON | **HW** Windows; selftest OK 2026-11-06 | Its self-test fixtures embed Gerald's `PCIROOT(0)#PCI(1400)`/`PCI(1C04)` and serial C922SN01 as test data (harmless). | T-ENUM/ID (the key every test should log) |
| `naming/identity_diff.py`, `naming/win_stability_workflow.ps1` | Py 116 / PS 47 | Snapshot diff per identifier; attended baseline / reboot / replug / port-move workflow. | `-Step` | `stability_*.json` | diff **HW** on opportunistic snapshots; workflow **draft** (never run end to end) | `identity_diff.py` multi-snapshot mode drops a camera missing from any snapshot. | T-ENUM/ID (index stability) |

### 4.3 Things that touch drivers or libusb (excluded by the 2026-11-06 constraint)

`libusb/**` (libuvc + patch 0001, WinUSB install/rollback, py_libusb1, pyuvc), `rust/uvc_iso`, `rust/nusb_pr233_probe`, `bandwidth/libuvc_forced_alt/**`, `bandwidth/alt_sweep_*.sh`, `driver_swap/**` and `naming/libusb_identity.py` (libusb enumeration sends GET_DESCRIPTOR(config) to every device) all depend on WinUSB on Windows or on detaching uvcvideo on Linux/macOS. **Do not port them into the new suites.** The exception is reference material: libuvc's PTS/SCR parsing and the payload-assembler tests can serve as oracles for the OS-native parsers. (inferred)

## 5. Linux inventory (all drafts; never run on Linux hardware)

`results/linux/Gerald/naming/` is a WSL2 fake-sysfs run and `results/linux/docker-ubuntu24.04/` holds libuvc build smoke tests. Neither is a hardware result.

| Path | Lang / size | What it does | Flags | Output | Status | Known defects / risks | Serves |
|---|---|---|---|---|---|---|---|
| `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py` (+ `run_linux_mjpeg.sh`, 185 lines) | Py ctypes/fcntl, 839 lines (pillow, simplejpeg, psutil) | Pure V4L2 mmap capture of native MJPEG: QUERYCAP, ENUM_FMT / FRAMESIZES / FRAMEINTERVALS listing, S_FMT, S_PARM, REQBUFS/QBUF/DQBUF. Detects silent format fallback (exit 2). Logs the buffer timestamp, its flags (MONOTONIC / SOE) and the sequence number. Reuses `mjpeg_common.summarize_run`. | `--list`, `--device` (repeatable), `--size`, `--fps`, `--seconds`, `--exposure-abs`, `--manual-wb`, `--keep-samples`, `--selftest` | `results/linux/<host>/mjpeg_v4l2_*` | **draft**. `--selftest` PASS (2026-11-06, Windows). A mock-V4L2 smoke test exists (`mjpeg/drafts/linux/mock_smoketest/`). | Controls are a fixed 5-entry table (exposure auto/abs/priority, WB auto/temp). No focus, gain or full QUERYCTRL walk (`V4L2_CTRL_FLAG_NEXT_CTRL`). No cycle option. Its `camera_key` format (`usb-vid:pid-serial@port`) differs from `camera_identity.py`. LP64 only. | T-FMT, T-MJPEG-ALL, T-CTRL-EFFECT (partial), T-CYCLE (extend) |
| `timing/linux/v4l2_uvc_timing.py` (+ `run_linux_timing.sh`, 60 lines) | Py, 1335 lines (stdlib) | V4L2 capture plus the paired **metadata node** (`V4L2_META_FMT_UVC` 'UVCH'). Parses `uvc_meta_buf {ns, sof, length, flags, PTS, SCR}` per payload. Logs buffer ts, PTS/SCR and host SOF/ns for first and last block. The runner optionally does a second pass with `hwtimestamps=1` through `sudo -n` and restores it. | `--device`, `--size`, `--fps`, `--seconds`, `--exposure-abs`, `--wb-k`, `--buffers`, `--no-meta`, `--list`, `--self-test` | `results/linux/<host>/timing/v4l2_uvc_timing/<tag>/` | **draft**; `--self-test` OK (2026-11-06) | Kernel semantics follow v6.12 and are marked "[verify on the target kernel]". The `hwtimestamps` write is a global module parameter (tier 1, root). | T-TS (core), T-ENUM (metadata-node pairing) |
| `bandwidth/linux/uvc_bw_probe.py` | Py, 461 lines | `list` (VS alts from sysfs), `ramp` (1..N cameras, STREAMON errno, the `bAlternateSetting` actually selected, read from sysfs while streaming; no root), `compare` (root: writes `quirks`/`trace` and **unbinds/rebinds uvcvideo** per camera, then reads dmesg). | `list`, `ramp --mode`, `compare --mode`, `--seconds` | `results/linux/<host>/bw_probe/*.json` | **draft**; Windows-side self-test only (`results/windows/Gerald/bw_linux_selftest/`) | `compare` performs a kernel-driver unbind/rebind, which the new constraint forbids. Replace it with a modprobe-options + replug "tier 1" variant or drop it. `list` and `ramp` are tier 0. | T-BW (ramp = tier 0) |
| `naming/linux_identity.py` (+ `linux_stability_workflow.sh`) | Py, 223 lines | sysfs, udev properties, `/dev/v4l/by-id` and `by-path`, QUERYCAP, sysfs `descriptors` parsed by `usbdesc`. Snapshot workflow. | `--label` | `results/linux/<host>/naming/` | **draft**; fake-sysfs plumbing test passed in WSL2 (`naming/test_linux_fake_sysfs.py`) | — | T-ENUM/ID, T-FMT/T-CTRL-LIST descriptor side |
| `prior_art/drafts/linux/linux_prior_art_probe.py` | Py, 195 lines (linuxpy 0.25.0) | uvcvideo parameters and writability, linuxpy MJPEG capture, metadata-node presence, optional `hwtimestamps=1` (root), `cam -l`, `gst-device-monitor`. | `--seconds`, `--try-hwtimestamps` | `results/linux/<host>/prior_art_linux/` | **draft** | — | T-ENUM (libcamera/GStreamer IDs), T-TS (hwtimestamps leg, tier 1) |
| `prior_art/pyav_dshow_probe.py`, `mjpeg/pyav/pyav_capture.py --input-format v4l2` | Py | PyAV v4l2 MJPEG packets | — | — | **draft** on Linux | — | T-MJPEG-ALL (PyAV row) |
| `naming/99-skellycam-cameras.rules.example`, `libusb/linux/70-skellycam-uvc.rules` | udev | Symlink rules / libusb access | — | — | untested | The libusb rule is only useful for streaming paths that detach uvcvideo, which are out. | (tier-1 naming option only) |

## 6. macOS inventory (all drafts; never run on a Mac)

| Path | Lang / size | What it does | Status | Known defects / risks | Serves |
|---|---|---|---|---|---|
| `mjpeg/drafts/macos/avf_mjpeg_probe.py` (+ `run_macos_mjpeg.sh`, 159 lines) | Py/pyobjc (`>=10`), 639 lines | AVCaptureVideoDataOutput with empty/nil `videoSettings` or a chosen subtype: are CMSampleBuffers compressed 'dmb1'/'jpeg' (CMBlockBuffer bytes) or decoded CVPixelBuffers? Lists formats, records every fallback, summarizes with `mjpeg_common`. | **draft** | The docstring warns that pyobjc call patterns (CMBlockBufferCopyDataBytes, CMTime) "may need small fixes on first run". TCC camera prompt needed. | T-FMT, T-MJPEG-ALL (the gating question for macOS) |
| `prior_art/drafts/macos/avf_native_mjpeg_probe.py` | Py/pyobjc, 221 lines | Same question, smaller; per-frame PTS (host-time clock) vs arrival. | **draft** | — | T-MJPEG-ALL, T-TS |
| `timing/macos/avf_timing.py` (+ `run_macos_timing.sh`) | Py/pyobjc **pinned ==10.3.1**, 189 lines | Per-frame CMSampleBuffer PTS vs `CMClockGetHostTimeClock`, all attachments, exposure Locked vs Custom support. | **draft** | The pyobjc 10.3.1 pin (mid-2024) may lack wheels for the Python versions current in 2026 (inferred; check before a Mac run). | T-TS, T-CTRL-EFFECT (exposure lock only) |
| `bandwidth/macos/avf_multi_open.py` | Py/pyobjc, 187 lines | Opens N cameras at once, ramps k = 1..N, records `AVCaptureSessionRuntimeError` codes and dropped-frame callbacks; uniqueID parsed as locationID + VID + PID for hub sharing. | **draft** | No bandwidth control exists in AVFoundation; this observes only. | T-BW, T-CYCLE (concurrent) |
| `naming/macos_identity.py` (+ `macos_stability_workflow.sh`) | Py, 201 lines | AVFoundation uniqueID/modelID plus `ioreg -c IOUSBHostDevice` (serial, locationID); tests uniqueID == `0x<locationID><vid><pid>` (forum-reported, undocumented). | **draft**; fake-ioreg plumbing test passed on Windows (`naming/test_macos_fake_ioreg.py`, `results/windows/Gerald/naming/test_macos_fake_ioreg.json`) | — | T-ENUM/ID; descriptors not read (no ioreg descriptor dump), so T-FMT/T-CTRL-LIST descriptor side is missing |
| UVC control side channel (IOKit `DeviceRequest` on the VideoControl interface, as uvc-util / CameraController do) | — | — | **does not exist** (only a plan line, `docs/test_gap_plan.md` MX5) | AVFoundation exposes almost no UVC controls for external webcams (inferred; the drafts only probe exposure lock). | T-CTRL-LIST / T-CTRL-EFFECT on macOS: **gap** |

## 7. Test → reusable component → gap

| Test | Windows (reuse) | Windows gap | Linux (reuse) | Linux gap | macOS (reuse) | macOS gap |
|---|---|---|---|---|---|---|
| **T-ENUM/ID** | `mf_mjpeg_capture --list-enum/--list-dshow` (no activation), `win_api_names.py`, `win_identity_dump.py`, `camera_identity.py`, `identity_diff.py`, `win_stability_workflow.ps1` | A driver that repeats enumeration K times (in-process and per process) and reports index → key per API per run. The attended port-move/replug steps (the workflow has never run). Fix `identity_diff` dropping cameras. | `linux_identity.py`, `linux_stability_workflow.sh`, `v4l2_uvc_timing.py --list` (metadata pairing) | Unify the key with `camera_identity.py`; a repeat-enumeration driver | `macos_identity.py`, workflow | Same driver; first hardware run |
| **T-FMT** | `list_formats.py` (MF + DS), `win_usb_topology.py` / `win_identity_dump.py` descriptors + `usbdesc.py`; data already exist: `results/windows/Gerald/naming/descriptors.json` (MJPEG frames C922 17, C930e 17, generic 5, Kiyo 4) and `mjpeg_formats/` | A **diff script** (descriptor frames × intervals vs MF native types vs DS caps with per-interval and range output); stop collapsing DS to max_fps; YUY2/H264/NV12 too | `v4l2_mmap_mjpeg.py --list`, `linux_identity.py` descriptors | Same diff script (V4L2 vs sysfs descriptors) | `avf_mjpeg_probe.py --list` | No descriptor source; add `ioreg`/IOKit config-descriptor read or accept AVF-only |
| **T-CTRL-LIST** | `mf_mjpeg_capture --controls-only` (7 controls, MF-source vs DS-filter), `tools/dshow_exposure_read.py`, `kiyo_ks_mf_probe --ks-only` (KS direct); descriptor `bmControls` names already decoded in `descriptors.json` (C922/C930e/Kiyo: CT 7 + PU 9; generic: CT 2 + PU 9) | Enumerate **all** `KSPROPERTY_CAMERACONTROL_*` (0–19) and `KSPROPERTY_VIDEOPROCAMP_*` (0–10) ranges, defaults, caps flags, on both the MF source and the DS filter. Compare with descriptor bmControls. Optionally MF `IMFCameraControlDefaults` / `IMFExtendedCameraController` (none in the repo). | `v4l2_mmap_mjpeg.py` `query_ctrl` (5 controls) | Full `VIDIOC_QUERY_EXT_CTRL` walk with `NEXT_CTRL`, plus menus | — | **New**: AVF properties plus an IOKit UVC GET_INFO/MIN/MAX/RES/DEF probe |
| **T-CTRL-EFFECT** | `mf_uvc_timing` (exposure/WB set, readback), `mf_mjpeg_capture --exposure/--wb`, `run_one.py`, luma in `mjpeg_common`, `flash_step_response.py` | Sets after stream start (+0.5 s, +2 s), toggling, **focus set** and **gain set** (never implemented), out-of-range clamp, `tools/sharpness.py` (planned, does not exist) | `v4l2_mmap_mjpeg.py --exposure-abs/--manual-wb`, `v4l2_uvc_timing.py --exposure-abs/--wb-k` | After-STREAMON sets, focus, gain | `avf_timing.py --lock-exposure` | Everything beyond exposure lock |
| **T-MJPEG-ALL** | `mf_mjpeg_capture` (any WxH@F), `pyav_capture.py`, `run_matrix.py`, `summarize_run` + `strict_jpeg_check.py` (SOF dims, strict decode) | `run_matrix --modes all` that iterates every advertised (size, interval) from the T-FMT listing instead of the hard-coded `max_mjpeg` table; Kiyo included; payload streaming to disk for long or high-rate cells | `v4l2_mmap_mjpeg.py`, `run_linux_mjpeg.sh` | Iterate all modes; first hardware run | `avf_mjpeg_probe.py` | Whole path unproven (gating) |
| **T-CYCLE** | Per process: wrap `mf_mjpeg_capture`, `mf_multi_open`, `dshow_open_probe`, `pyav_capture` in a K-loop (each already reports open time, first-frame latency, per-step HRESULT); `devnode_status()` and the Kiyo gates (`kiyo_ks_mf_probe`, `usb_ep0_probe`) between iterations | **In-process** open → first frame → N frames → close × K: needs a `--cycles K` option in `mf_mjpeg_capture` / `mf_multi_open` or a new tool, and a PyAV in-process loop. No DS C++ tool delivers samples (`dshow_open_probe` uses a Null Renderer). | none | New V4L2 open/STREAMON/STREAMOFF/close loop (small change to `v4l2_mmap_mjpeg.py`) | `avf_multi_open.py --ramp` (concurrent) | Session start/stop loop |
| **T-BW** | `mf_multi_open` + `run_concurrency.py` + `win_usb_topology.py --pipes-only` + `hs_budget_model.py` / `headroom.py` | Remove the hard-coded hub pair in `hs_budget_model.py`. Per-combo timeout. DS concurrency (PyAV multi-device) refusal capture. SuperSpeed (Kiyo) budget. Recovery (refused start → zero-frame start → next start; REPORT finding 19) as an explicit cycle. | `uvc_bw_probe.py list/ramp` | Remove or replace `compare` (unbind) | `avf_multi_open.py` | First run |
| **T-TS** | `mf_uvc_timing` (PTS/SCR/OS ts), `quantization_check.py`, `verify_grid_phase.py`, `analyze_frames.py`, `flash_timecode` + `flash_analyze.py` (optional ground truth), `enable_uvc_metadata.ps1` (tier 1) | Metadata-less robustness in the flash scripts. Runtime instance-ID lookup plus `-NoRestart` in the registry script. A per-camera "metadata present?" report with and without the value. The DS timestamp source via PyAV only. | `v4l2_uvc_timing.py`, `run_linux_timing.sh`, `analyze_frames.py`, `flash_timecode_py.py` (draft) | Hardware run; kernel-version check of the metadata/hwtimestamps semantics | `avf_timing.py`, `avf_native_mjpeg_probe.py` | Hardware run; pyobjc pin |

## 8. Hard-coded Kiyo exclusions and IDs that break now

Dom wants the Kiyo included everywhere, and the cameras have moved ports.

**Kiyo excluded by default:**
- `mjpeg/mjpeg_common.py` `DEFAULT_CAMS = ("c922","c930e","usbcam")` and `EXCLUDED_CAMS` (lines ~118–122). This feeds `list_formats.py`, `run_matrix.py` and `aggregate.py` defaults.
- `results/windows/Gerald/timing/rerun_20261027/tools/dshow_probe_all.ps1` (Kiyo omitted from the request list; absolute exe path).
- `mjpeg/compare_runs.py` drops "+kiyo" sets on purpose (comparison logic, fine).
- The naming and bandwidth `--exclude*` flags are **opt-in** (no default exclusion).

**Kiyo hard-coded in (the reverse problem):**
- `timing/scripts/run_flash_test.ps1` default `-Cams` = C922, C930e, Kiyo, without the generic camera.
- `rust/run_windows_nokhwa.sh` hard-codes the Kiyo (open bug).

**Hard-coded instance IDs / topology (break after port moves):**
- `timing/scripts/enable_uvc_metadata.ps1` default `-Instances` (3 IDs; the C930e one already stale).
- `hs_budget_model.py` line 81 (shared hub = PIDs 0843 + 4a55).
- `timing/scripts/recover_restart_cameras{,3}.ps1` (`7&7DCC7CE&0&4`, `9&3A0ECB01&0&4`): do not reuse anyway.
- `rust/platform/run_windows_phase2.sh` and `libusb/winusb/*.ps1`: excluded anyway.
- `rust/tools/devnode_status.ps1` misses VID_4C4A.
- `results/.../run_flash_rerun.ps1` uses an absolute repo path.

**Robust to port moves:**
- Everything that matches by VID/PID substring: `mjpeg_common.WINDOWS_CAMERAS`, `--dev`, `--cam`, `mf_uvc_timing --cam`, `mf_multi_open --cam`, `pyav_capture` via `dshow_alt_name`.
- This will break only if two cameras of one model are attached (none in hand).
- The `mf_uvc_timing` per-camera output key embeds the instance ID, so file names change after a move. The data are unaffected.

**Re-arming needed after a move:** `MetadataBufferSizeInKB0` lives on the per-instance interface key. A serial-less camera (C930e, generic, Kiyo) that moved port has a **new** instance and has lost the value; the C922 (serial C922SN01) keeps its instance. (inferred from REPORT finding 26 and the C930e `&0&`→`&1&` precedent.)

## 9. Third-party footprint inside the harness

- **Own code, no third-party runtime:**
  - the three MF/DS C++ tools (`mf_mjpeg_capture` 683, `mf_uvc_timing` 386, `mf_multi_open` 402 lines; Windows SDK only);
  - `win_usb_topology.py`, `usbdesc.py`, `win_identity_dump.py`, `camera_identity.py`, `v4l2_uvc_timing.py` (stdlib/ctypes).
- **Validation dependencies:** pillow, simplejpeg (libjpeg-turbo), numpy, psutil. All are actively released (inferred).
- **Third-party capture paths:**
  - PyAV (`av`; the FFmpeg dshow/v4l2/avfoundation demuxers);
  - comtypes (`dshow_exposure_read.py`);
  - opencv + cv2-enumerate-cameras + imageio-ffmpeg (`win_api_names.py` only);
  - pyobjc (all macOS);
  - linuxpy (Linux prior-art probe only);
  - nokhwa 0.10.11 (Rust probe).
- If the suites keep the "own C++/ctypes core plus PyAV as the second path" split, they depend on the smallest set of external packages. (inferred)

## 10. What the next phase needs to build (summary)

1. **Windows suite runner:**
   - a single Python driver that resolves cameras at runtime by VID/PID + `camera_identity` key (Kiyo included);
   - gates each Kiyo step on `usb_ep0_probe` / `kiyo_ks_mf_probe --ks-only` and `devnode_status()`;
   - calls the existing exes under camlock per cell;
   - is pinned to `uv run --python 3.12`.
2. **New or extended code (Windows):**
   - a full KS control enumerator (MF source + DS filter) and a descriptor diff;
   - `--cycles K` (in-process) for `mf_mjpeg_capture` and `mf_multi_open`;
   - focus/gain set plus after-start re-apply;
   - `run_matrix --modes all`;
   - a topology-driven `hs_budget_model`;
   - a PyAV in-process cycle script;
   - metadata-less-safe flash scripts;
   - `enable_uvc_metadata.ps1` with runtime ID lookup and `-NoRestart` by default.
3. **Linux:**
   - extend `v4l2_mmap_mjpeg.py` with a full QUERY_EXT_CTRL walk, focus/gain, after-STREAMON sets and a cycle loop;
   - keep `v4l2_uvc_timing.py` for T-TS;
   - keep `uvc_bw_probe.py list/ramp`;
   - drop or replace the unbind-based `compare` with a tier-1 modprobe-options + replug variant.
4. **macOS:**
   - run `avf_mjpeg_probe.py` first (gating);
   - add an IOKit UVC control probe (new);
   - refresh the pyobjc pins.


## Verifier notes

Adversarial check, 2026-11-06. Read-only: no camera was opened, streamed or enumerated. Run by the verifier: two offline self-tests (`naming/usbdesc.py --selftest` and `mjpeg/drafts/linux/v4l2_mmap_mjpeg.py --selftest`; both PASS, neither touches a device), toolchain version commands, greps, and reads of local result files. Web: PyPI JSON for pyobjc-core, Microsoft Learn for `IAMVideoControl::GetFrameRateList`, and news reports on the Fedora 45 release.

| ID | Verdict | Evidence / correction |
| --- | --- | --- |
| C1 | weakened | The source has 683 lines, and the exe and the .cpp are both stamped 2026-10-27 23:05 (confirmed). "Any requested WxH@F" is overstated: hardware results exist only for 1280x720@30 and each camera's max mode (`run_matrix.py` modes common/max). Every other advertised mode is still untested. |
| C2 | weakened | That `--list-enum`/`--list-dshow` open no camera comes from the tool's header comment (`mf_mjpeg_capture.cpp:15-18`), not from a measurement. The cited `mjpeg_formats/20261028T030920Z/summary.json` **excluded the Kiyo**. The only Kiyo listing is the 10-25 run (`mjpeg_formats/summary.json`, utc_started 2026-10-25T19:04Z). |
| C3 | confirmed | `mf_mjpeg_capture.cpp:272-285`: 7 reads; sets only exposure, WB and AE priority. **Correction to the implication:** VIDEOPROCAMP spans ids **0-13**, not 0-10 (`ksmedia.h` 10.0.22621.0 ~l.5245-5265: DIGITAL_MULTIPLIER 10, DIGITAL_MULTIPLIER_LIMIT 11, WHITEBALANCE_COMPONENT 12, POWERLINE_FREQUENCY 13). The tool already reads id 13. CAMERACONTROL 0-19 is right (~l.5700-5723). |
| C4 | confirmed | No cycle/repeat option in `mf_mjpeg_capture.cpp`, `mf_multi_open.cpp` or `mf_uvc_timing.cpp` (grep). |
| C5 | confirmed | `mf_uvc_timing.cpp:159-184` walks `KSCAMERA_METADATA_ITEMHEADER` and reads `KSSTREAM_UVC_METADATA` Start/EndOfFrame PTS/SCR. |
| C6 | confirmed | `enable_uvc_metadata.ps1:12-20`. Also missed: the default list has **no generic 4C4A camera at all**, so the generic has never had metadata (PROGRESS.md machine state). |
| C7 | weakened | The gatherer gave no source for "moved port". Today's topology file (`results/agent_reports/plan_20261106/topology_windows_run/win_usb_topology_20261106.json`, 15:20Z) shows the C930e now on root-hub port 7 (`USB\VID_046D&PID_0843\5&CC3F949&0&7`), so its MI_00 ID has very likely changed again. For the Kiyo and the generic it is unverified. |
| C8 | confirmed | `r07_shared_hub_threshold_staggered.json` exists. REPORT finding 17 gives alt 8 pass / alt 9 refuse, 5/5. |
| C9 | confirmed | `win_usb_topology.py:191,325-352`: sends `IOCTL_USB_GET_DESCRIPTOR_FROM_NODE_CONNECTION` unless the device is `--exclude`d. |
| C10 | confirmed (now demonstrably wrong) | `hs_budget_model.py:81`. Today's topology puts **C922 (port 4) + generic (port 2)** on the 05e3:0610 hub and the C930e on root port 7, so the hard-coded 0843/4a55 pair no longer matches the hardware. |
| C11 | confirmed | RERUN_20261027.md l.269. |
| C12 | confirmed | Frame-size sets are equal (C922 17/17, C930e 17/17, generic 5/5, Kiyo 4/4). The Kiyo figure is from the **10-25** run only. Root cause of the "17 vs 120": `VIDEO_STREAM_CONFIG_CAPS` gives only a Min/MaxFrameInterval per caps entry. The discrete rate list needs `IAMVideoControl::GetFrameRateList` (https://learn.microsoft.com/en-us/windows/win32/api/strmif/nf-strmif-iamvideocontrol-getframeratelist), which no tool calls. |
| C13 | confirmed | `naming/descriptors.json` (2026-10-25): generic IT has 2 controls (AE mode, exposure abs), PU 9. The other three have CT 7 + PU 9. Note: all four report bcdUVC 1.00, so no UVC 1.5 controls are expected. |
| C14 | confirmed | Re-run by the verifier today: "usbdesc selftest OK". The cited `test_parsers.json` is dated 2026-10-25, and the gatherer's 11-06 run left no result file. The selftest checks one synthetic descriptor. |
| C15 | confirmed | `check_claims.json`: 46/46, all_ok, utc_run 2026-10-28T03:17Z. |
| C16 | confirmed | RERUN_20261027.md l.276 and l.281 ("Still needs a human: controlled naming stability"). |
| C17 | confirmed | `mjpeg_common.py:419` `validate_jpeg`, `:471` `summarize_run`. |
| C18 | confirmed | `mjpeg_common.py:121-122`. |
| C19 | confirmed | `run_matrix.py` docstring: modes common/max only. |
| C20 | confirmed | Every Kiyo MF cell (`mjpeg_msmf/*kiyo*/`) has INVALID.txt with read_error 0x8007001F. `timing/kiyo_check/*.frames.jsonl` has 0 lines, and session.json shows frames 0, errors 21. |
| C21 | confirmed | Headers of `usb_ep0_probe.cpp` (instance ID -> hub IOCTL GET_DESCRIPTOR) and `kiyo_ks_mf_probe.cpp` (KS-direct GET_CUR plus MF stages). Note that both are themselves EP0 traffic to the Kiyo. |
| C22 | confirmed | `dshow_open_probe.cpp:1-6`: capture filter -> Null Renderer. |
| C23 | confirmed | `pyav_capture.py:3`: `av>=12`. REPORT finding 2 used PyAV 19.0.2, and other scripts pin `av==19.0.2`. |
| C24 | confirmed | `mjpeg_common.py:178` passes `--controls-only --via-dshow`. Note: `run_one.py`'s docstring says "set through the Media Foundation tool", which hides that the DS-filter path is used. Sets happen before the stream starts and rely on the device keeping the state while LogiTuneAgent keeps respawning (PROGRESS.md; C930e reads back -5). |
| C25 | confirmed | The toolchain exists and has run on hardware. Note: the flash scripts depend on `opencv-python-headless==4.10.0.84`. |
| C26 | confirmed | RERUN_20261027.md l.268. |
| C27 | confirmed | `run_flash_test.ps1:10`, `run_windows_nokhwa.sh:12-13`, `rust/tools/devnode_status.ps1:9` (VID_1532/VID_046D only). |
| C28 | confirmed | PROGRESS.md hazards. |
| C29 | confirmed | (inferred) The dividing line is not clean, though: the kept tools `win_usb_topology.py` and `usb_ep0_probe` also send EP0 GET_DESCRIPTOR. What rules the libusb code out is the driver swap, not EP0 traffic. |
| C30 | confirmed | vswhere 17.12.4; MSVC 14.29.30133 + 14.42.34433; SDKs 10.0.19041/22621; all 4 .bat files hard-code the VS 2022 **Community** vcvars64.bat (present). A PC with only VS 2026 or Build Tools needs a vswhere-based .bat (inferred). |
| C31 | confirmed | `uv 0.11.8 (2026-04-27)`; `uv python find` -> skellycam `.venv`. |
| C32 | weakened | The flock branch has never run on POSIX, so "works unchanged" is inferred, not measured. The lock binds only processes that use camlock. `subprocess.call` with no process-group kill means that killing camlock frees the lock while the child may still hold the camera (`tools/camlock.py`). |
| C33 | confirmed | Re-run today: SELFTEST PASS. Caveat: it compares struct sizes, offsets and ioctl numbers against values hard-coded by the same author, not against kernel headers. |
| C34 | confirmed | `v4l2_uvc_timing.py:23,46`: semantics follow **v6.12**. `run_linux_timing.sh:48-57` uses `sudo -n` for `hwtimestamps`. Newer info: **Fedora 45 shipped 2026-11-03 on Linux 7.2** (https://phoronix.com/news/Fedora-45-Ships-Next-Week, https://www.warp2search.net/story/fedora-linux-45-officially-released-gnome-51-linux-72-kernel-and-breaking-changes/), 8+ releases after v6.12. |
| C35 | confirmed | `uvc_bw_probe.py:14-18`: compare writes `/sys/module/uvcvideo/parameters/{quirks,trace}` and rebinds. |
| C36 | confirmed | `macos_identity.py:22,44` uses `ioreg` only and reads no descriptors. Fake-tree tests only (`results/linux/Gerald/naming/test_linux_fake_sysfs.json`). |
| C37 | confirmed | `avf_timing.py:3-9` pins pyobjc ==10.3.1. `avf_mjpeg_probe.py` uses `>=10`. Newer info: pyobjc-core 10.3.1 dates from 2024-06-11. The **latest is 13.0 (2026-10-30, requires Python >=3.11)**; the 12.0 files were yanked (https://pypi.org/pypi/pyobjc-core/json). |
| C38 | confirmed | A grep finds no UVC control-request code for macOS. IOKit appears only in `ioreg` identity parsing and the rust rawusb iso path (`rust/platform/run_macos.sh`). |
| C39 | weakened | OpenCV (`opencv-python-headless==4.10.0.84`) is a dependency of about 14 timing-analysis scripts (`timing/scripts/flash_*.py`, `display_model_check.py`), not only enumeration. The pywinrt `winrt-*>=2.0` backend (`mjpeg/winrt/winrt_capture.py`) is omitted. `v4l2_mmap_mjpeg.py` and the avf drafts do **not** use PyAV; PyAV reaches v4l2/avfoundation only through `pyav_capture.py --input-format`. prior_art adds `pygrabber==0.2`, `linuxpy==0.25.0` and `gstreamer-bundle`. |
| C40 | confirmed | `mf_uvc_timing.cpp:150-156` `key_from_link` embeds the instance ID. `mjpeg_common.py:126-160` matches VID/PID substrings. |

**Missed items**
- A Windows topology snapshot from today exists: `results/agent_reports/plan_20261106/topology_windows_run/win_usb_topology_20261106.json` (written 5 s after this report). It answers the open question "which port/hub layout": C922 and generic on the Genesys 05e3:0610 hub, C930e on root port 7, Kiyo at `USB\VID_1532&PID_0E05\9&3A0ECB01&0&4` (excluded from descriptor reads). It was produced by `win_usb_topology.py`, which sent GET_DESCRIPTOR to the C922, C930e and generic. Strictly, that breaches this phase's "no enumeration" rule, so the orchestrator should know.
- DS per-interval mode listing needs `IAMVideoControl::GetFrameRateList` (Learn URL above). Fixing `list_formats.py` alone cannot produce it.
- PROGRESS.md: the generic 4C4A re-arrived twice overnight without explanation (2026-10-28 03:18Z and 04:12Z). T-CYCLE and T-ENUM must log LastArrivalDate and USB address per cycle, or a re-arrival will be scored as an API failure.
- Version facts for the plan: Fedora 45 is on kernel 7.2 (released 2026-11-03); pyobjc is at 13.0.
