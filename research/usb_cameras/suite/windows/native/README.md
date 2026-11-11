# wincam: Windows native camera probe for the UVC suite

`wincam.exe` is the native half of the Windows suite (plan `docs/xplat_capture_plan.md` §6, contract 2). It is one C++17 file that uses only the Windows SDK: Media Foundation and DirectShow. The Python runner (`suite/windows/run_suite.py`) calls it in a child process under `tools/camlock.py`. It serves tests W-FMT, W-FMT-NOGRAB, W-CTRL-LIST, W-CTRL-EFFECT, W-MJPEG, W-RAW, W-TS, W-CYC and W-KIYO. It stays the reference probe for the tests; the product's capture module is planned in native Python (ctypes/comtypes calling the same OS APIs).

Version 1.1 (2026-11-06) added: `activity` (who uses each camera, without opening one), `formats --hold-ms`, `capture --stop-file`, `"stream_started": false` in `formats`, and the fields described under "Fields added after the first self-test" below.

Version 1.2 (2026-11-08) added raw (uncompressed) capture for W-RAW, and `fps_measured` in cycle rows (see "Raw subtypes" and the 1.2 table below):
- `capture` and `cycle` take any native subtype (`--subtype YUY2|NV12|<FOURCC>`). Raw frames are checked by buffer length, not JPEG markers.
- A type flagged `likely_mf_synthesized` is refused unless `--allow-synthesized` is given.
- The negotiated record carries the readback subtype, the expected frame length and how it was derived.

Code borrowed from this study folder:
- `mjpeg/msmf/mf_mjpeg_capture.cpp`: native MJPG selection with converters off, the DS caps walk, and controls through the MF source or the DS filter;
- `timing/src/mf_uvc_timing.cpp`: the `KSCAMERA_METADATA_ITEMHEADER` → `KSSTREAM_UVC_METADATA` walk, and `IAMCameraControl` queried from `IMFMediaSource`;
- `bandwidth/mf_multi_open.cpp`: per-step HRESULTs, and `FormatMessage` via `mferror.dll`;
- `timing/src/dshow_open_probe.cpp`: DS enumeration.

## Build

```bat
research\usb_cameras\suite\windows\native\build.bat
```

- Calls the VS 2022 Community `vcvars64.bat` (the same path as `mjpeg/msmf/build.bat`), with a `vswhere` fallback for other editions and the Build Tools. Only VS 2022 with the C++ x64 tools is required.
- Compiles at `/W4 /permissive- /std:c++17` with no warnings. vcvars64 itself prints one harmless "'vswhere.exe' is not recognized" line.
- Output: `build\wincam.exe`. `build/` is ignored by `suite/.gitignore`.
- Windows SDK: an installed SDK is used when vcvars64 finds one (`windows.h` on `INCLUDE`; the line "Windows SDK: installed, ..." is printed). Otherwise `build.bat` falls back to the Windows SDK 10.0.22621 NuGet packages `Microsoft.Windows.SDK.CPP` and `Microsoft.Windows.SDK.CPP.x64`, version 10.0.22621.3233 ("Windows SDK: NuGet ..."):
  - The first build downloads both packages from nuget.org with `curl.exe` into `build\sdk\` (git-ignored), checks each against a SHA-256 pinned in `build.bat`, unpacks them with `tar.exe`, and deletes the archives. About 200 MB is downloaded and 800 MB unpacked.
  - Later builds re-use `build\sdk\`. Nothing is installed system-wide; deleting `build\sdk\` forces a fresh download.
  - `INCLUDE` gets the packages' `ucrt`, `um`, `shared`, `winrt` and `cppwinrt` folders and `LIB` their x64 `ucrt` and `um` folders; the `cl` line is the same either way.
  - `WINCAM_SDK_DIR=<folder>` uses another folder; `WINCAM_FORCE_NUGET_SDK=1` uses the NuGet SDK even when an installed SDK is found.
- Why: the Windows SDK headers and libs disappeared from Gerald on 2026-11-07 at 18:34 (`C:\Program Files (x86)\Windows Kits\10` has no `Include` or `Lib`), so the old `build.bat` failed with "Cannot open include file: 'windows.h'". Reinstalling "Windows 11 SDK 10.0.22621" in the VS Installer would also work; `build.bat` then uses it.
- 2026-11-09: version 1.2 built with no warnings both from a fresh nuget.org download (into a test folder via `WINCAM_SDK_DIR`, hashes matched) and from `build\sdk\` re-used; `wincam.exe --version` prints `wincam 1.2 (2026-11-08)`. The 1.1 binary is kept as `build\wincam_1.1_20261106.exe`.

## Safety design

- **No driver, registry or device-state changes.** It never restarts, disables or removes a device. It never writes the registry. It never touches WinUSB or libusb.
- **Every blocking camera call is bounded.** Each call runs on a helper MTA thread, and the main thread waits at most `--timeout-ms` for it. This covers enumerate, `ActivateObject`, `BindToObject`, every control call, reader creation, `SetCurrentMediaType`, `ReadSample` issue, each sample wait, `Flush`, the final reader `Release`, release of the control interfaces, `IMFMediaSource::Shutdown` and `IMFActivate::ShutdownObject`.
  - A call that does not return is recorded as `"timed_out": true` with error class `timeout`, and its thread is abandoned.
  - An abandoned `ActivateObject` shuts down its own source if it ever completes.
  - When any thread was abandoned, the process ends with `TerminateProcess(rc)` and skips `MFShutdown`/`CoUninitialize`, which could block on the hung objects.
- **Process watchdog** (`--watchdog-ms`; the default is derived from the request). It is the last resort if something hangs outside a bounded call. It prints a JSON object with `watchdog_fired: true`, the stage and partial counters, writes the same into `summary.json` for capture and cycle, and exits 5.
- **Capture is async.** It uses the async source reader (`IMFSourceReaderCallback`), so a stalled stream is a per-sample timeout, not a blocked `ReadSample`. `frames.jsonl` is flushed per line, so a kill loses nothing already delivered.
- **Release order, every time:** stop issuing reads → wait for any in-flight `ReadSample` issue → `Flush` (wait for `OnFlush`) → final reader `Release` → release `IAMCameraControl`/`IAMVideoProcAmp`/`IKsControl` → `IMFMediaSource::Shutdown` → `IMFActivate::ShutdownObject`. The reader is created with `MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN`, so the shutdowns are explicit and timed. A step that does not return sets `unreleasable: true` and exit 5.
- **Explicit media type.** The type must match subtype, width and height exactly, and the frame rate within 0.5 fps (nearest wins). It is never the first match: MF lists a synthesized NV12 type right before each MJPG type. After `SetCurrentMediaType`, `GetCurrentMediaType` is read back and compared, and a mismatch is a failure. Converters are disabled.
- **No MF-synthesized frames by accident (1.2).** The whole native list is read before choosing, and an NV12 type listed immediately before an MJPG type of the same size and rate (the `formats` flag `likely_mf_synthesized`) is skipped. If it is the only match, the type is refused (`set_type` fails with `MF_E_INVALIDMEDIATYPE`, `negotiated.synthesized_refused: true`) unless `--allow-synthesized` is given.
- **Devices are named by the caller.** `--device` is matched at run time, never against a built-in list:
  1. exact symlink or DevicePath (case-insensitive);
  2. else a substring of it, or of its normalized form, which lets an MF symlink find the DS DevicePath of the same interface;
  3. else a substring of the friendly name.

  If more than one device matches, the tool exits 2 and lists the matches. `cycle` re-enumerates the device every cycle.

## Subcommands

Common options:
- `--timeout-ms T`: per-call bound; default 5000; required for capture and cycle.
- `--watchdog-ms MS`.
- `--out FILE`: list, formats, controls and activity only. It writes the JSON to FILE instead of stdout.

All JSON objects carry the same header: `tool`, `version`, `subcommand`, `utc_started`, `utc_finished`, `pid`, `argv`, `timeout_ms`, `exit_code`, `abandoned_threads`. They also carry `error` (null, or `{stage, hr, hr_name, message, class, reason}`).

**Per-call HRESULT fields are `null` when the call was not made.** Internally a call that was never made holds the sentinel `HR_NOT_CALLED` (`0xA0DE0001`, a customer-bit code no API returns); the JSON writer prints it as `null` (both the hex field and its `_name`). Before 2026-11-06 the initial value was `E_NOINTERFACE` `0x80004002`, so an `iam_get` of `0x80004002` in older results may mean "not called" (W-KIYO's `not_called_codes` marks it).

### `list`
MF `MFEnumDeviceSources` (`index`, `friendly_name`, `symlink`) and DirectShow `CLSID_VideoInputDeviceCategory` (`index`, `friendly_name`, `device_path` from the `DevicePath` property, `clsid`, `clsid_is_ksproxy`), with `elapsed_ms` per API. It reads only property bags: no `ActivateObject`, no `BindToObject`.

Each entry also carries:
- `usb`: `{vid, pid, mi, instance}`, parsed from the link;
- `match_key`: the link without `\\?\` and without the interface-class GUID, which is the same for MF and DS.

Virtual cameras (NDI, OBS, NVIDIA Broadcast, SpoutCam) appear too. The OBS, NVIDIA Broadcast and SpoutCam entries have no DevicePath and are not ksproxy.

### `formats --api mf --device X [--hold-ms H]`
Activates the source. It never calls `IMFMediaSource::Start` or `ReadSample` (`"stream_started": false` in the JSON). It then gives:
- `streams[]`: the presentation-descriptor streams with all their attributes, including `MF_DEVICESTREAM_STREAM_CATEGORY` (capture/still/...), the handler type count and the major type.
- `reader_streams[]`: from a sync source reader with converters disabled, every native type on every stream: `stream_index`, `type_index`, `subtype` (FOURCC, or the name/GUID for non-FOURCC subtypes such as `MFVideoFormat_H264_ES`), `width`, `height`, `fps_num`, `fps_den`, `fps`, frame-rate range, sample size and `flags`. `flags` contains `nv12_immediately_before_same_mode_mjpg:likely_mf_synthesized_decode` for the MF-inserted NV12.
- Per stream: `subtype_counts`, plus `mjpg_sizes` (de-duplicated sizes, each with its list of rates).
- `--hold-ms H` (W-FMT-NOGRAB): after the listing, the activated source AND the converters-off source reader stay open for H ms before the normal release. stderr gets two machine-readable lines, `[wincam] HOLD_BEGIN qpc_ns=<n> hold_ms=<H> holding=mf_source_and_reader` and `[wincam] HOLD_END qpc_ns=<n>` (QPC in ns, the same clock as `capture`'s `qpc_ns` and Python's `time.perf_counter_ns`), so a caller can sample the USB pipes and try a concurrent open while the device is held. The JSON gets `hold`: `{requested_ms, done, holding, begin_qpc_ns, end_qpc_ns, begin_utc, end_utc}`. The reader step's bound becomes `--timeout-ms` + H, and the default watchdog grows by H.

### `formats --api ds --device X [--hold-ms H]`
Binds the capture filter (no filter graph, no `IMediaControl::Run`; `"stream_started": false`) and lists every pin with: name, direction, category GUID and name (from `AMPROPSETID_Pin`), and `IAMVideoControl::GetCaps`.

For pins with `IAMStreamConfig`:
- `caps[]`: every `GetStreamCaps` entry, with `header_kind` (`VIH` | `VIH2` | `MPEG2VI` | `H264VI` | `other`), subtype, w, h, min/max frame interval and fps, and `GetFrameRateList` for that caps index (`frame_rate_list_hr` is `null` when the pin has no `IAMVideoControl`, i.e. the call was not made).
  - **H.264 caps.** A UVC 1.5 H.264 pin (the C930e's second capture pin) carries a `KS_H264VIDEOINFO` format block (`formattype` `KSDATAFORMAT_SPECIFIER_H264_VIDEO` {2017BE05-6629-4248-AAED-7E1A47BC9B9C}); its size and interval come from `wWidth`, `wHeight` and `dwFrameInterval` (`header_kind` `H264VI`).
  - **Unrecognised format blocks** (`header_kind` `other`): the size comes from `VIDEO_STREAM_CONFIG_CAPS.InputSize`, else `MaxOutputSize` (`size_source` names which; null = nowhere, 0x0), and the entry records `format_type_guid`, `format_type` and `format_block_bytes` (and a stderr line), instead of reporting 0x0.
  - **Caps with zero intervals** (the H.264 pin reports 0): the min/max interval falls back to the format block's `AvgTimePerFrame`, and `interval_source` says "format block (caps intervals are 0)".
- `modes[]`: the entries de-duplicated by (subtype, w, h), each with `header_kinds`, `caps_indices`, the interval range, and the merged discrete `frame_rate_list_100ns` / `fps_list`.
- `--hold-ms H`: the filter stays bound for H ms after the listing, with the same `HOLD_BEGIN` (`holding=ds_bound_filter`) / `HOLD_END` stderr lines and `hold` record as for MF.

Pins without `IAMStreamConfig` list their `IEnumMediaTypes`. `any_unknown_pin_category` flags an *output* pin whose category has no name, which is where a metadata pin would show. None was seen on Gerald.

### `controls --api mf|ds --device X [--read-only | --set id=v,... [--set-flags auto|manual] [--restore]]`
- **MF:** `QueryInterface` on the activated `IMFMediaSource`. **DS:** on the bound capture filter.
- **Ids covered:** every `PROPSETID_VIDCAP_CAMERACONTROL` id 0–23 (0–19 are defined, including `auto_exposure_priority` = 19; 20–23 are probes) and every `VIDEOPROCAMP` id 0–15 (0–13 defined).
- **How each id is read:** through `IAMCameraControl` / `IAMVideoProcAmp` (GetRange + Get). When those reject the id, through `IKsControl` with `KSPROPERTY_TYPE_BASICSUPPORT` (range), `DEFAULTVALUES` and `GET`. The KS read always runs as a cross-check.
- **Per control:** `supported`, `via`, `min`, `max`, `step`, `default`, `caps_flags` (+ names), `value`, `flags` (+ names), `value2` (for two-value controls), `ks_basicsupport` (KS range/default, byte count, member-list count, raw hex when nothing parses), `iam_ks_range_agree`, an HRESULT and its name for each call, and `call_ms`.
- **Degenerate IAM ranges.** When the IAM range is 0..0 step 0 but KS gives a real range, the KS range is reported and `note` says so.
- **Sets:**
  - `--set` takes ids as names (`exposure`, `focus`, `gain`, `white_balance`, `wb`, ...), as `cc.<name>` / `pa.<name>`, or as `cc<N>` / `pa<N>`.
  - A value is an integer, or `auto` / `manual` (keep the current value, change only the flag).
  - Integers use `--set-flags` (default `manual`).
  - Each set records the before value and flags, the set value and flags, `hr_set`, and the readback value and flags, plus `matches`.
  - `--restore` puts back each control's value and flags as read before the set, in reverse order.
- **Two-value controls are listed, not set:** `pantilt`, `pantilt_relative` and `white_balance_component` return `E_NOTIMPL`.
- **Did the device answer?** Every supported control has `get_ok` (the value GET that was made returned a value) and `get_hr` / `get_hr_name` (the HRESULT of that GET: the KS GET on the `IKsControl` path, else the IAM `Get`, else the IAM `GetRange`). The top level has `get_ok_count`, `get_failed_count`, `get_failed_controls` (keys) and `device_not_answering`: true when every device-backed GET failed (`focal_length` is left out because the driver answers it from the descriptors; it still answered on the wedged Kiyo). Then the tool exits **4** with `error.stage` `control_get` and the first failing GET's HRESULT (the Kiyo signature is `0x8007001F`), and attempts no set. Before this, a read-only run on a wedged camera returned rc 0.

### `capture --api mf --device X --width W --height H --fps F [--subtype MJPG|YUY2|NV12|<FOURCC>] (--frames N | --seconds S) --timeout-ms T --out-dir D [--save none|all|every:K] [--schedule "ms:id=v;..."] [--controls-before id=v,...] [--stop-file F] [--allow-synthesized]`
Runs as described under "Safety design". Writes:

- `D/frames.jsonl`, one line per sample:
  - `seq`, `qpc_ns` (QPC at callback entry, converted to ns), `sample_time_100ns`, `sample_duration` (100 ns), `readsample_ts_100ns`, `flags`, `discontinuity`, `bytes`;
  - `soi`, `eoi` (last two bytes are FFD9) and `eoi_trailing_bytes` (0 = at the end; >0 = padding after the last EOI; -1 = none in the last 4 KB);
  - `sof0_w`, `sof0_h` (from SOFn), `sof_marker` (only when it is not SOF0);
  - `uvc_pts`, `uvc_scr_stc`, `uvc_scr_sof`, `uvc_eof_pts`, `uvc_eof_scr_stc`, `uvc_eof_scr_sof`, `has_metadata` (UVC header item parsed), `capture_metadata_attr`. The tool still writes these, but since 2026-11-09 the suite is tier 0 only and no test reads them;
  - `mf_device_timestamp`;
  - `mjpeg_offset` and `mjpeg_len` when the frame was saved.
- `D/frames.mjpeg`: the saved samples, concatenated byte-exact (only when `--save` is not `none`).
- `D/summary.json`, which is also printed to stdout:
  - `negotiated`: native type index, readback subtype/size/rate, `readback_ok`, the candidate rates;
  - `steps[]`: `{step, hr, hr_name, ms, timed_out}` for enumerate, activate, reader_create, set_type, read_sample_issue, first_sample, flush, reader_release, control_interfaces_release, source_shutdown and activate_shutdown_object;
  - `timings`: `enumerate_ms`, `activate_ms`, `reader_ms`, `settype_ms`, `first_frame_ms` (first `ReadSample` → first sample), `open_to_first_frame_ms`, `flush_ms`, `reader_release_ms`, `shutdown_ms`, `shutdown_object_ms`, `close_ms`;
  - `frames`: total, ok (SOI + EOI + SOF size = request), `soi_eoi_ok`, `sof0_size_match`, `with_uvc_metadata`, ticks, nulls, discontinuities, bytes, saved;
  - `fps_measured`, `duration_s`;
  - `cpu`: `GetProcessTimes` over the streaming window, and the process total;
  - `metadata.uvc_pts_present`;
  - `controls_before[]` and `schedule[]`;
  - `unreleasable`, `ok`, `error`.
- **`--schedule` times** are ms after the first frame's arrival. Each event is set on the same `IMFMediaSource` (IAM interfaces, KS fallback) on a bounded thread. It records `applied_qpc_ns`, `applied_ms_after_first_frame`, `frames_before_apply`, `done_qpc_ns` and the readback.
- **After a control call times out,** the remaining schedule events are skipped, and the capture continues.
- **`--controls-before`** applies sets after activation and before the reader is created.
- **Nothing is restored automatically.** The runner ends a schedule with `id=auto`, or calls `controls --restore`.
- **`--stop-file F`**: the streaming loop also ends, cleanly and with the same release order, as soon as file F exists (checked every ≤ 50 ms). `--frames` / `--seconds` stay the upper bound. The JSON gets `stop_file` and `stopped_by_stop_file`. W-FMT-NOGRAB uses it to keep a background stream running exactly as long as its listing methods need (`helpers/pyav_ds.py capture --stop-file` does the same for DirectShow).
- **Large captures:** pass a `--out-dir` outside the repo (`C:/Users/Dom/Documents/skellycam-raw/...`).

#### Raw subtypes (1.2)

Any subtype that is not compressed (not MJPG, H.264, HEVC, VP8/9 or MP4V, and the type does not set `MF_MT_COMPRESSED`) is captured as raw frames: YUY2 on every Gerald camera, the Kiyo's native NV12, or any FOURCC from the native list.
- **Expected length** (`negotiated.raw_frame`): `|stride| x height`, times 3/2 for 4:2:0 formats (NV12, NV21, I420, IYUV, YV12). The stride comes from `MF_MT_DEFAULT_STRIDE` when the native type carries it, else from width x bytes per pixel (YUY2/UYVY/YVYU 2, grey 1, RGB24 3, RGB32 4). The last resort is `MF_MT_SAMPLE_SIZE` for fixed-size samples. `basis` says which rule applied, `layout` names the format family, and `native_type_attrs` lists the type's `default_stride`, `sample_size`, `fixed_size_samples` and `compressed`. A locked contiguous buffer always has the minimum stride, so this is the length `IMFMediaBuffer::Lock` reports. Examples: YUY2 1280x720 = 1,843,200 B; NV12 1280x720 = 1,382,400 B.
- **Per frame** (`frames.jsonl`): `raw: true`, `raw_len_ok` (length equals the expected length; any length > 0 when the layout is unknown) and `flat` (every sampled byte has one value: delivered but blank). `soi`, `eoi`, `eoi_trailing_bytes`, `sof0_w` and `sof0_h` are `null`. Saved frames go to `frames.raw`, with `raw_offset` / `raw_len` (MJPEG keeps `frames.mjpeg` with `mjpeg_offset` / `mjpeg_len`).
- **`frames.ok` for raw** counts frames with `raw_len_ok`; `frames.ok_rule` states the rule used. `frames` also gets `raw`, `raw_len_ok`, `raw_flat`, `raw_expected_bytes`, `raw_len_min`, `raw_len_max`, `raw_len_counts` (the first 16 distinct lengths, then `raw_len_other`) and `buffer` (first sample: `buffer_count`, `is_2d_buffer`, `pitch` from `IMF2DBuffer::Lock2D`, `contiguous_length`).
- **`negotiated`** also gets `requested_subtype`, `raw`, `likely_mf_synthesized` (whether the chosen type carries the flag), `likely_mf_synthesized_candidates`, `readback_default_stride`, and the candidate list, in which flagged rates are marked.
- `files.frames_raw` names the saved raw file; `files.frames_mjpeg` is null for raw captures.

### `cycle --api mf --device X --width W --height H --fps F [--subtype S] --cycles K --frames N --timeout-ms T --out D [--alt-width W2 --alt-height H2 --alt-fps F2] [--gap-ms G] [--allow-synthesized]`
- **Each cycle, in process:**
  1. re-enumerate;
  2. activate;
  3. create the async reader;
  4. set the explicit type;
  5. wait for the first frame;
  6. take N frames;
  7. close in the safe order.
- **Alternate modes:** odd cycles use the `--alt-*` mode.
- **`D/cycles.jsonl`** has one line per cycle: `i`, `mode`, `ok`, `stage_failed`, `hr`, `hr_name`, `error_class`, `timed_out`, `enumerate_ms`, `activate_ms`, `reader_ms`, `settype_ms`, `first_frame_ms`, `open_to_first_frame_ms`, `frames`, `frames_ok`, `with_uvc_metadata`, `close_ms` (+ flush/release/shutdown parts), `in_use_by_other`, `activity_pids`, `unreleasable`, `negotiated_ok`, `t_start_qpc_ns`, `utc`, `steps[]`.
- **1.2 additions per cycle row:**
  - `fps_measured`: (frames − 1) / (last − first arrival), QPC at callback entry, as in `capture`. It is `null` with fewer than 2 frames. It includes the start-up interval, so with N = 30 frames it is a short-window figure. This fixes the W-CYC harness bug in windows_results_20261106.md §11, where MF/DS fps was never judged.
  - `duration_s`, `negotiated_subtype`, `likely_mf_synthesized` and `raw`; for raw cycles also `raw_expected_bytes` and `raw_flat`. `frames_ok` uses the raw length rule for raw subtypes.
  - The summary gets `fps_measured_p50` and `fps_measured_min` over the successful cycles.
  - Odd cycles use the `--alt-*` mode with the same `--subtype`.
- **`in_use_by_other`** comes from `IMFSensorActivityMonitor` (loaded from `mfsensorgroup.dll`), evaluated at the end of each cycle. It is true when another PID is streaming the device and null until the monitor has sent a report. It sees Frame Server (MF) clients only; DirectShow/ksproxy clients are invisible to it.
- **A hung cycle** (a timed-out step) is recorded, and the tool moves on. It stops with exit 5 when a release step does not return (`unreleasable`) or after two hung setup steps.
- **`D/summary.json`** (also on stdout) holds: success rate, timeouts, `longest_failure_run`, `recovered_after_failure`, `first_frame_ms` p50/p95/max, `first_frame_within_2s`, activate/close p50, and failures by stage and by class. `suite/common/cycstats.py` does the full statistics.

### `activity [--wait-ms W] [--device X]` (opens no camera)
Which processes use each camera right now, without activating or binding anything, so it needs no camera lock and can run while another process streams (W-KIYO polls it every round; W-MJPEG and W-CYC record it before each camera's first stream; W-FMT-NOGRAB before each camera).
- **`IMFSensorActivityMonitor`** (`MFCreateSensorActivityMonitor` from `mfsensorgroup.dll`): the tool waits up to W ms (default 1500) for the first activity report (it usually arrives within ~3 ms of `Start`), lets a burst settle for 150 ms, then stops the monitor. `monitor`: `{available, hr, source, report_received, reports, wait_ms, first_report_ms}`.
- **`devices[]`**: every MF video-capture device (`MFEnumDeviceSources`, property bags only) with `friendly_name`, `symlink`, `match_key` (same normalisation as `list`, so the DS DevicePath of the same interface matches), `usb`, `processes[]` (`pid`, `streaming`, `image` and `name` from `QueryFullProcessImageNameW` with `PROCESS_QUERY_LIMITED_INFORMATION`, null when access is denied, `self`), `in_use` (some process has the sensor open; **null** when no report arrived, i.e. unknown) and `streaming` (some process streams it). Reported links without an MF device entry are appended with `not_in_mf_list: true`. `--device X` filters by symlink, match key or name.
- **`consent_store`**: read-only scan of `HKCU` and `HKLM` `Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam` (packaged apps and `NonPackaged` exe paths with `#` for `\`): `in_use[]` lists apps whose `LastUsedTimeStop` is 0 or earlier than `LastUsedTimeStart` (`app`, `kind`, `hive`, `last_used_start_utc`, `last_used_stop_utc`), plus `hives_opened` and `apps_with_timestamps`.
- **Coverage.** The activity monitor sees Frame Server (MF / WinRT) clients only; DirectShow (ksproxy) clients are invisible to it. The ConsentStore covers MF and DirectShow apps, but per capability, not per camera.
- Measured on Gerald 2026-11-06 (no suite stream running): `LogiTuneAgent.exe` holds every USB camera (`streaming: false`), and `RazerAppEngine.exe` also holds the Kiyo. Whole command ≈ 0.3 s.

## Fields added after the first self-test (summary)

| Where | Field | Meaning |
| --- | --- | --- |
| every per-call HRESULT | `null` | the call was not made (`HR_NOT_CALLED` sentinel; was `0x80004002` before 2026-11-06) |
| `controls` per control | `get_ok`, `get_hr`, `get_hr_name` | the value GET answered / its HRESULT |
| `controls` top level | `get_ok_count`, `get_failed_count`, `get_failed_controls`, `device_not_answering` | all device-backed GETs failed → exit 4, `error.stage` `control_get` |
| `formats --api ds` caps | `header_kind` `H264VI`, `format_type_guid`, `format_type`, `format_block_bytes`, `size_source`, `interval_source` | H.264 and unrecognised format blocks (see above) |
| `formats` | `stream_started` (always false), `hold` | the listing never starts a stream; `--hold-ms` record |
| `capture` | `stop_file`, `stopped_by_stop_file` | `--stop-file` |
| `activity` | `monitor`, `devices[].processes`, `consent_store` | new subcommand |

## Fields added in 1.2 (2026-11-08)

| Where | Field | Meaning |
| --- | --- | --- |
| `capture`, `cycle` | `--subtype <any native FOURCC>`, `--allow-synthesized` | raw capture; accept an NV12 type flagged as likely MF-synthesized |
| `negotiated` | `requested_subtype`, `raw`, `raw_frame{expected_frame_bytes, basis, stride, layout, native_type_attrs}`, `likely_mf_synthesized`, `likely_mf_synthesized_candidates`, `synthesized_refused`, `readback_default_stride` | what was asked for, what the chosen native type is, and the length each raw frame must have |
| `capture` `frames` | `raw`, `ok_rule`, `raw_len_ok`, `raw_flat`, `raw_expected_bytes`, `raw_len_min`, `raw_len_max`, `raw_len_counts`, `raw_len_other`, `buffer{...}` | raw frame checks (MJPEG captures carry only `raw: false` and `ok_rule`) |
| `frames.jsonl` (raw) | `raw`, `raw_len_ok`, `flat`, `raw_offset`, `raw_len`; JPEG fields `null` | per-frame raw checks; saved frames in `frames.raw` |
| `capture` `files` | `frames_raw` | the saved raw frames |
| `cycles.jsonl` | `fps_measured`, `duration_s`, `negotiated_subtype`, `likely_mf_synthesized`, `raw`, `raw_expected_bytes`, `raw_flat` | per-cycle delivered rate and format |
| `cycle` summary | `fps_measured_p50`, `fps_measured_min` | over the successful cycles |

Not yet run on a camera (2026-11-08: cameras were being replugged). Checked so far: a clean `/W4` build, `--version`, usage errors, the W-RAW offline tests (`suite/windows/tests/test_w_raw_offline.py`), and the source markers those tests check.

## Exit codes and error classes

| Exit | Meaning |
| --- | --- |
| 0 | ok |
| 2 | usage (including an ambiguous `--device`) |
| 3 | device not found |
| 4 | camera failure (see `error`; for cycle, any cycle failed) |
| 5 | timeout (a bounded call, `unreleasable`, or the watchdog) |

`error.class` (from the code alone; deciding `bandwidth_probable` needs topology context, so `suite/common/topology_model.classify_failure` does it):

| Class | HRESULTs |
| --- | --- |
| `bandwidth_certain` | `0x800718CF` (Win32 6351) |
| `in_use` | `MF_E_HW_MFT_FAILED_START_STREAMING` `0xC00D3704`, `MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED` `0xC00D3EA3`, `ERROR_DEVICE_IN_USE`, `ERROR_BUSY` |
| `permission` | `E_ACCESSDENIED` `0x80070005` (privacy setting; for DirectShow it can also mean bandwidth) |
| `device_error` | `0x8007001F` (Kiyo signature), `MF_E_REBOOT_REQUIRED` `0xC00D7167`, `MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED` `0xC00D3EA2`, device not connected / removed / no such device, I/O error, not ready, or the device missing at re-enumeration |
| `timeout` | a bounded call did not return |
| `other` | everything else, including `MF_E_SHUTDOWN` and `MF_E_INVALIDREQUEST`, each with a reason |

`hr_name` comes from a table that includes `0xC00D36B4` `MF_E_INVALIDMEDIATYPE`, `0xA00F4271`/`0xA00F4244`/`0xA00F4243` (Camera-app codes), the `VFW_E_*` codes and `E_PROP_ID_UNSUPPORTED`. Codes outside the table show as hex. `message` is `FormatMessage` text (system, then `mferror.dll`).

## Self-test on Gerald, 2026-11-06 (measured)

Outputs: `results/windows/Gerald/suite_build_selftest_20261106/wincam/` (`INDEX.json` summarises every run, and `selftest_log.txt` holds the commands and exit codes). Every camera-touching run went through camlock with an inner `--timeout-ms`, and device symlinks came from `wincam list`.

**Listings:**
- `list`: MF 2.5 ms, DS 6.8 ms. The 4 USB cameras plus 4 NDI virtual cameras in MF; the 4 USB cameras, 4 NDI and 7 virtual DS devices in DS.
- **MJPEG sizes and rates are identical in MF and DS** on all four cameras (C930e 17 sizes, C922 17, generic 5 + 3 still, Kiyo 4). So are **all control ranges and defaults** (C930e/C922/Kiyo 16 supported, generic 11). MF lists one NV12 before every MJPG type on the C930e (119), C922 (120) and generic, not on the Kiyo.
- The generic camera has a second MF stream, and a DS still pin with category `PIN_CATEGORY_STILL`. The C930e has a second H.264 capture pin/stream.
- `auto_exposure_priority` reports 0..0 step 0 through both IAM and KS BASICSUPPORT.
- For `pantilt`, BASICSUPPORT returns a description with zero member lists (raw hex recorded).

**Capture and cycle:**
- **C930e:** capture 60/60 valid frames, SOF0 1280x720, 29.8 fps, native type index 294, readback ok. `first_frame_ms` ≈ 450, final reader release ≈ 350 ms. Cycle 3/3 alternating 720p30 and 640x480@30; `in_use_by_other` false.
- **Kiyo (1532:0E05):** it did not hang today. Capture 60/60 valid frames, **every frame with UVC PTS/SCR** (tier-1 value present on its instance), first frame ≈ 960 ms, close ≈ 1.1–1.2 s. Cycle 3/3.

**Control sets on the C930e:**
- Exposure, focus, white balance and gain set exactly through the MF source, and `--restore` returned them to auto.
- A capture with `--controls-before exposure=-6 --schedule "700:exposure=-9;1400:exposure=auto"` applied the events within about 1 ms of plan, and the readback matched.
- Final read-only checks show exposure, focus and WB in auto on the C930e and the Kiyo.

**Timeout paths (forced on the C930e, because the Kiyo stayed healthy):**
- `--timeout-ms 300`: first-sample timeout, then the reader release did not finish, so the tool reported `unreleasable` and exited 5 with full JSON.
- Cycle with `--timeout-ms 400`: every cycle timed out at first sample, each closed cleanly, and the tool moved on (exit 4).
- `--watchdog-ms 2500` on a 6 s capture: the watchdog fired mid-stream, wrote partial JSON, and exited 5.
- A normal capture right afterwards was 60/60.

**Usage paths:** an ambiguous `--device vid_046d` exits 2 and lists both Logitech cameras; an unknown device exits 3.

## Known gaps

- There is no DirectShow capture here; `helpers/pyav_ds.py` covers that.
- Two-value KS controls are listed but not settable.
- `in_use_by_other` (cycle) and `activity`'s per-camera process list do not see DirectShow clients (the ConsentStore part of `activity` does, per capability only).
- Frame Server CPU is not measured (`mf_mjpeg_capture.cpp` has code for it if needed).
- No real camera hang has yet been seen by this tool. The timeout paths were exercised with short timeouts on a healthy camera.

## Self-test of the 1.1 additions on Gerald, 2026-11-06 (measured)

- `activity`: 0.3 s; first report 2.8 ms after `Start`; LogiTuneAgent on every camera, RazerAppEngine on the Kiyo, nothing streaming; ConsentStore: 44 apps with timestamps, none in use.
- `formats --hold-ms 1500` on the C922 under camlock: MF listing 85 ms then a 1.50 s hold (`holding=mf_source_and_reader`); DS listing 32 ms then the hold (`ds_bound_filter`); both rc 0, `stream_started` false.
- `capture --stop-file` (C922, 720p30, `--seconds 20`): stop file written after 3 s → 81 frames, `stopped_by_stop_file` true, rc 0, normal release.
- W-FMT-NOGRAB quick self-test on the C922 and the C930e: `results/windows/Gerald/suite_build_selftest_20261106/nograb_quick/`.
