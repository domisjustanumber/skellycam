# Goal 1: native MJPEG extraction, results

Status: the Windows matrix was re-run on 2026-10-27/28 overnight (UTC 2026-10-28 03:09 onward) on the test machine
"Gerald" (Windows 11, i7-14700K, 28 logical CPUs), unattended, in a dark room. The Linux and macOS harnesses are drafts:
they parse and pass static checks but have never run on those OSes.

**Cameras:** Logitech C922 (046D:085C), Logitech C930e (046D:0843), and a generic "USB Camera" (4C4A:4A55). The C930e and
the generic camera share a hub. **The Razer Kiyo Pro (1532:0E05) was excluded on purpose.** The user excluded it as known
flaky: it stops answering EP0 a few minutes after each plug-in, and then every API fails with 0x8007001F. The harness
defaults (`mjpeg_common.DEFAULT_CAMS`) leave it out, and the MF tool's `--list` now activates only the `--dev` matches.
No Kiyo row in this file comes from the rerun.

## How to reproduce

All camera access goes through `tools/camlock.py`, one matrix cell per lock hold. Commands are run from the repo root.

```bash
# formats (opens only the named cameras)
uv run --script research/usb_cameras/tools/camlock.py -- uv run --script research/usb_cameras/mjpeg/list_formats.py --cams c922,c930e,usbcam
# matrix: each run_matrix.py call writes cells under --root; existing cells are skipped, never overwritten
export MJPEG_SCRATCH=<scratch dir for raw payloads>
R=research/usb_cameras/results/windows/Gerald/mjpeg_rerun_20261027
uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $R --backend msmf --backend pyav-dshow --modes common,max --sets single,all
uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $R --backend winrt --backend opencv-dshow-decode --modes common --sets single,all
uv run --script research/usb_cameras/mjpeg/run_matrix.py --root $R --backend opencv-msmf-raw --backend opencv-msmf-decode --backend opencv-dshow-raw --modes common --sets single
# the exact sequence run on 2026-10-27/28: results/windows/Gerald/mjpeg_rerun_20261027/drivers/run_mjpeg_matrix{,2,3,4}.sh
uv run --script research/usb_cameras/mjpeg/aggregate.py --root $R --markdown          # -> $R/table.json, $R/table.md
# earlier (2026-10-25) raw captures re-validated with the same validator, no camera access:
MJPEG_SCRATCH=<old scratch>/runs uv run --script research/usb_cameras/mjpeg/resummarize.py --out-root research/usb_cameras/results/windows/Gerald/mjpeg_resummarized_20261025_data
MJPEG_SCRATCH=<old scratch>/runs/mjpeg uv run --script research/usb_cameras/mjpeg/resummarize.py --out-root research/usb_cameras/results/windows/Gerald/mjpeg_resummarized_20261025_data_b
uv run --script research/usb_cameras/mjpeg/compare_runs.py --old <earlier roots> --new $R --out $R/compare_vs_20261025.json
```

Each cell does the following:

1. `run_one.py` records the PnP DevNodeStatus of every test camera and the whole-machine CPU% over 1 s.
2. It sets manual exposure 2^-7 s, white balance 4500 K and auto-exposure priority 0 through the DirectShow filter's
   IAMCameraControl, IAMVideoProcAmp and IKsControl. The C930e accepts −5 at most.
3. The capture runs: 2 s warm-up, then a 10 s measured window. It is killed after 120 s.
4. `run_one.py` reads the controls back and records the machine CPU% and DevNodeStatus again.
5. `summarize.py` checks every payload: SOI, EOI, a full Pillow decode and a libjpeg-turbo decode.

It writes these files:

- `summary.json`
- `frames.jsonl`, the per-frame log in the README schema
- `controls.json`
- `sample_*.jpghdr`. To keep the user's room private, this holds only the JPEG header bytes (SOI to SOS), not image data.

Each result field means the following:

- **fps** is (n−1) divided by the span of host arrival times inside the window.
- **valid %** is the share of in-window frames with SOI, EOI, a Pillow decode, a lenient libjpeg-turbo decode and the
  requested size. The strict libjpeg-turbo share is also kept in `summary.json`.
- **process CPU %** is QueryProcessCycleTime divided by the calibrated TSC rate, as a percentage of one core, for the
  capture process only. Frame Server CPU cannot be read without elevation (OpenProcess error 5), so it is excluded.
- **machine CPU %** is psutil's mean over 28 logical CPUs for 1 s before and after the capture. Other agents were
  running.
- **luma** is the mean 8-bit luma of every 30th in-window frame. For JPEG it is decoded at 1/8 scale in GRAY with
  simplejpeg. For OpenCV pixel frames it is BT.601 on a 1/8 subsample.
  The two scales differ. JPEG Y is read raw, so a near-black scene shows Y of about 16, while the decoded BGR maps
  that to about 4. Compare luma only within one kind of path.
- **native?** compares the dominant JPEG header fingerprint (SHA-1 over DQT+SOF+DHT, `mjpeg_common.jpeg_header`) with
  the bytes the Media Foundation reader delivered for the same camera and mode in the same root. The MF reader ran with
  MF_READWRITE_DISABLE_CONVERTERS, and its output subtype was verified to still be MJPG. A host-side decode and
  re-encode would emit different tables.

## Findings (Windows, Gerald)

Every number comes from `results/windows/Gerald/mjpeg_rerun_20261027/` (index: `table.json`, `table.md`) unless another
source is named. "Earlier" means the 2026-10-25 captures, re-validated with today's validator, in
`mjpeg_resummarized_20261025_data/table.json`; the cell-by-cell comparison is in
`mjpeg_rerun_20261027/compare_vs_20261025.json`.

1. **Media Foundation IMFSourceReader with the native MJPG type delivers the camera's own JPEG bytes on all three
   cameras.** The tool selects the native MJPG media type with MF_READWRITE_DISABLE_CONVERTERS=TRUE. The reader's
   current output subtype is still MJPG afterwards (`delivered_codecs`), so no decoder MFT sits in the reader.
   - **Validity:** 100% valid JPEG in every cell that streamed. Single cameras: 300 frames for the C922, 301 for the
     C930e and 257–258 for the generic camera per 10 s window, with 0 gaps over 1.5 periods.
   - **Frame rate:** C922 30.00, C930e 30.05, generic camera 25.76–25.78 fps, at both 1280x720@30 and 1920x1080@30.
   - **Process CPU** (one camera, % of one core): 0.7–2.2%.
   - **Payload p50:** at 720p, 100 kB (C922), 122 kB (C930e) and 66 kB (generic); at 1080p, 182, 208 and 118 kB.
   - **Compared with earlier:** fps and validity reconfirmed. Payloads differ because the scene and light differ.
2. **PyAV / FFmpeg dshow with `vcodec=mjpeg` (demux only, never decoded) delivers byte-identical JPEG headers to MF.**
   - For each camera and mode, the full header bytes from SOI to SOS have the same SHA-1 on both APIs (`header_bytes_shared_with_mf`).
     The C922 and C930e each emit 1 header per mode. The generic camera changes its quantisation tables between frames:
     it emitted 11–14 distinct headers per 10 s, and every one of them is also in the MF set.
   - Validity: 100%. Frame rate matches MF (C922 30.0, C930e 30.04–30.05, generic 25.74).
   - Process CPU: 0.9–1.6% for one camera; 2.7% (720p) and 3.1% (1080p) for two streaming cameras.
   - The DQT, SOF and DHT tables of each camera and mode were identical on 2026-10-25 and 2026-10-27
     (`compare_vs_20261025.json`, same_dominant_fingerprint = true in all 11 matched rows).
   - The C922 and C930e share the same DQT, SOF and DHT tables (Logitech encoder; first luma quantisers 3,3,3,3,3,3,4,4),
     but their full headers differ (APP0/COM). So the full-header match is the stronger "same bytes" check.
3. **The generic 4C4A:4A55 camera runs MJPG at about 25.7 fps when 30 fps is requested, on every native path and on
   both days.**
   - Measured: MF 25.76–25.78, PyAV 25.74, OpenCV DSHOW 25.71–25.77 fps. Earlier: 25.74–25.78 fps
     (`mjpeg_resummarized_20261025_data`).
   - Light does not explain it. Exposure was manual (2^-7 s, AE priority 0), the same rate was measured in daylight on
     10-25, and luma was 15–22 on both days.
   - OpenCV CAP_MSMF reports 30 fps for this camera, but that is padding. 48 of about 300 in-window frames are
     pixel-identical to the previous one (per-frame CRC of a 1/4-subsampled image), so the unique rate is 25.3–25.4 fps
     (`mjpeg_opencv-msmf-decode/*_usbcam_duphash`).
   - Control: OpenCV CAP_DSHOW on the same camera gave 0 repeats at 25.7 fps (`mjpeg_opencv-dshow-decode/*_usbcam_duphash`).
4. **With all three cameras open, the C930e and the generic camera, which share a hub, cannot both stream MJPG at 720p
   or 1080p.**
   - **MF:** the camera that loses fails ReadSample with 0x800718CF, which is HRESULT_FROM_WIN32(6351): "A camera
     interface doesn't have the desired bandwidth for data transfer". At 720p the C930e lost; at 1080p the generic
     camera lost.
   - **DirectShow (PyAV and OpenCV):** the generic camera, opened last, fails to open (FFmpeg OSError 5; OpenCV
     "open failed"). In OpenCV MSMF it fails at the first grab.
   - The C922, on its own controller path, always streamed. DevNodeStatus stayed 0x0180200A, with no DN_NEED_RESTART,
     before and after every cell.
   - This matches goal 3: each camera requests its maximum alt setting, and usbvideo grants it.
5. **WinRT MediaFrameReader with outputSubtype "MJPG" delivers nothing.**
   - Every TryAcquireLatestFrame raised 0x80070057 (E_INVALIDARG) on all three cameras, at 720p and 1080p, single and
     all three, and in every variant: Cpu or Auto memory, buffered or realtime.
   - With no output subtype, frames arrive as decoded NV12 (1,382,400 B): C930e 30.6–30.7 fps, generic 25.9–26.1 fps,
     at 12–22% of one core (`mjpeg_winrt_variants/none_*`).
   - With outputSubtype "NV12": 0 frames and no callbacks.
   - The single-camera C930e 720p cell got no FrameArrived callbacks at all (`mjpeg_winrt/common_1280x720at30_c930e`).
   - The 10-25 C922-only result is reconfirmed and now extends to the C930e and the generic camera.
6. **OpenCV 4.12 (the skellycam baseline) never returns JPEG bytes.**
   - **CAP_DSHOW with FOURCC=MJPG:** BGR arrays, 24.6–28.3% of one core at 720p and 37–40% at 1080p, at full camera rate.
   - **CAP_DSHOW with CONVERT_RGB=0:** still BGR (720,1280,3).
     - With the size-first property order (now the default), MJPG is negotiated and runs at 30 fps.
     - The 10-25 "10.01 fps YUY2" result came from the fourcc-first order. So it is order-specific, not a property of
       CONVERT_RGB=0.
   - **CAP_MSMF:**
     - Opening the C922 or the C930e takes 39–41 s; the generic camera takes 3.4–3.7 s.
     - Decoding to BGR costs 46–54% of one core at 720p and 143–156% at 1080p.
     - FORMAT=-1 with CONVERT_RGB=0 returns NV12 as a one-row Mat (1,382,400 B). That is MF-decoded pixels, not JPEG.
       It cost 12–13% at 30 fps for the C922 and C930e; on the generic camera it ran at 17.1 fps and 4.8%.
   - The 10-25 "0 frames, about 93% CPU" result was a harness artifact. The script waited only 30 s for open, so the
     window started mid-open. The open wait is now a parameter (default 90 s), and the four cells affected tonight are
     marked INVALID and re-run as `*_openwait90`.
7. **MF with its own MJPEG decoder (NV12 output):** 3.3–3.7% of one core at 720p at full camera rate, against
   0.7–1.8% for native MJPG on the same camera. On 10-25 it was 1.83% against 0.77% on the C922.
8. **Timestamps each API attaches** (fields in `frames.jsonl`; analysis is goal 2's):
   - **MF:** ReadSample llTimestamp equals IMFSample::GetSampleTime, which equals MFSampleExtension_DeviceTimestamp, for
     100% of frames in every MF cell.
     - MFSampleExtension_CaptureMetadata carries the 32-byte UVC payload header on the C922 and C930e (353 of 353 and
       348 of 348 frames), where the UVC metadata registry value is set, and is absent on the generic camera, where it
       is not.
     - The 10-25 report said capture metadata was absent; the registry value was set later.
     - No FIRST/LAST_SCANLINE QPC attributes were present.
     - Sample-time deltas step in about 16 ms units: p50 32.0 ms.
     - Arrival minus sample time is about 0.3–1 ms or about 16 ms for the Logitech cameras, varying by run, and about
       32–33 ms for the generic camera.
   - **PyAV dshow:** pkt.pts deltas are exactly 33.333 ms for every camera, including the generic camera, which really
     runs at 25.7 fps (33.338 ms). The pts are nominal, not capture times. On the generic camera, arrival minus pts
     reaches about 1.06–1.09 s within 10 s.
   - **OpenCV:** only CAP_PROP_POS_MSEC (logged as `pos_msec`).
   - **WinRT:** SystemRelativeTime (QPC-relative), only on the NV12 path.

### Night conditions

- The room was dark. Luma p50 (0–255, JPEG Y) was about 17 on the C922 (near the JPEG black level of about 16), about
  78–81 on the C930e, and 15–22 on the generic camera.
- Exposure was manual in every cell: 2^-7 s requested on all three. The C930e reads back −5 (2^-5 s) in every cell, as
  it did on 10-25.
- UVC auto-exposure priority was 0, and readback after each capture confirmed the settings.
- So low light could not lower the frame rate, and no fps change against 10-25 was observed: the C922 and C930e stayed
  at 30.0–30.05 and the generic camera at 25.7–25.8.
- Daylight luma on 10-25 was 22–33 (C922) and 43–128 (C930e).
- The cameras were left in this manual state, as the 10-25 runs also left them.

### CPU load and caveats

- Whole-machine CPU was 2–11% before and after almost every cell. One exception: before `mjpeg_msmf/common_1280x720at30_c930e`
  it was 60%, and 19% after. The values are in `summary.json` under `machine_cpu`.
- Several single-camera process-CPU numbers are 1.3–2.3x the 10-25 values even at low machine load. Examples:
  - MF C922 720p: 1.79 vs 0.77.
  - OpenCV DSHOW decode C922 720p: 27.4 vs 18.3.
  - MF decode to NV12: 3.7 vs 1.83.
- Others match, for example MF C930e 720p (0.70 vs 0.69) and MF C922 1080p (0.86 vs 0.93). Each cell is a single 10 s
  run, so treat sub-2% differences as noise.
- The ranking does not change: native passthrough is about 1–2%, a host decode is 3.3% (MF) to 155% (OpenCV MSMF).
- Frame Server CPU cannot be measured without elevation (`frameserver_open_error: 5`), so MF, WinRT and OpenCV-MSMF
  costs exclude it.

## Matrix (2026-10-27 rerun)

- **fps** is the achieved frame rate over the 10 s window.
- **process CPU** is per cell: in "all 3" rows it is the whole process, which holds all the cameras.
- **native?** is "yes" when the dominant DQT/SOF/DHT fingerprint equals the MF native reference for that camera and
  mode. "n/a (pixels)" means the API returned decoded pixels.
- "did not open" rows in "all 3" sets are the bandwidth refusals described in finding 4.
- Cells marked INVALID (the four OpenCV MSMF cells hit by the open-wait bug) are not listed. Their re-runs are the
  `openwait90` rows.

| approach | mode | set | camera | fps | valid JPEG % | payload p50 kB | process CPU % (cell) | luma p50 | native bytes? | delivered | cell |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | single | c922 | 30.00 | 100.0 | 100 | 1.8 | 17.1 | yes | MJPG | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_c922/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | single | c930e | 30.05 | 100.0 | 122 | 0.7 | 78.1 | yes | MJPG | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_c930e/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | single | usbcam | 25.78 | 100.0 | 66 | 1.7 | 22.2 | yes | MJPG | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | all 3 | c922 | 30.00 | 100.0 | 101 | 1.7 | 17.2 | yes | MJPG | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | all 3 | c930e | - | - | - | 1.7 | - | n/a (no frames) | MJPG ReadSample 0x800718cf | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1280x720at30 | all 3 | usbcam | 25.77 | 100.0 | 58 | 1.7 | 20.2 | yes | MJPG | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | single | c922 | 30.00 | 100.0 | 182 | 0.9 | 17.2 | yes | MJPG | [max_1920x1080at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_c922/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | single | c930e | 30.05 | 100.0 | 208 | 2.1 | 79.3 | yes | MJPG | [max_1920x1080at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_c930e/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | single | usbcam | 25.76 | 100.0 | 118 | 1.1 | 21.2 | yes | MJPG | [max_1920x1080at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | all 3 | c922 | 30.00 | 100.0 | 182 | 2.0 | 17.2 | yes | MJPG | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | all 3 | c930e | 30.05 | 100.0 | 209 | 2.0 | 80.7 | yes | MJPG | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (b) MF IMFSourceReader, native MJPG | 1920x1080at30 | all 3 | usbcam | - | - | - | 2.0 | - | n/a (no frames) | MJPG ReadSample 0x800718cf | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | single | c922 | 30.04 | 100.0 | 101 | 0.9 | 17.3 | yes | mjpeg | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_c922/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | single | c930e | 30.04 | 100.0 | 124 | 1.3 | 79.2 | yes | mjpeg | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_c930e/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | single | usbcam | 25.74 | 100.0 | 56 | 1.3 | 19.8 | yes | mjpeg | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | all 3 | c922 | 30.00 | 100.0 | 101 | 2.7 | 17.2 | yes | mjpeg | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | all 3 | c930e | 30.05 | 100.0 | 124 | 2.7 | 79.2 | yes | mjpeg | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1280x720at30 | all 3 | usbcam | did not open | - | - | - | - | - | open failed: OSError(5, 'I/O error' | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | single | c922 | 30.00 | 100.0 | 183 | 1.6 | 17.3 | yes | mjpeg | [max_1920x1080at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_c922/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | single | c930e | 30.05 | 100.0 | 210 | 1.5 | 80.7 | yes | mjpeg | [max_1920x1080at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_c930e/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | single | usbcam | 25.74 | 100.0 | 109 | 1.1 | 19.7 | yes | mjpeg | [max_1920x1080at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | all 3 | c922 | 30.00 | 100.0 | 183 | 3.0 | 17.3 | yes | mjpeg | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | all 3 | c930e | 29.85 | 100.0 | 209 | 3.0 | 80.2 | yes | mjpeg | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (a) PyAV dshow vcodec=mjpeg | 1920x1080at30 | all 3 | usbcam | did not open | - | - | - | - | - | open failed: OSError(5, 'I/O error' | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_pyav-dshow/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | single | c922 | - | - | - | 20.1 | - | n/a (no frames) | MJPG | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_c922/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | single | c930e | - | - | - | 0.0 | - | n/a (no frames) | MJPG | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_c930e/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | single | usbcam | - | - | - | 10.7 | - | n/a (no frames) | MJPG | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | all 3 | c922 | - | - | - | 36.0 | - | n/a (no frames) | MJPG | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | all 3 | c930e | - | - | - | 36.0 | - | n/a (no frames) | MJPG | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1280x720at30 | all 3 | usbcam | - | - | - | 36.0 | - | n/a (no frames) | MJPG | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | single | c922 | - | - | - | 32.3 | - | n/a (no frames) | MJPG | [max_1920x1080at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_c922/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | single | c930e | - | - | - | 34.0 | - | n/a (no frames) | MJPG | [max_1920x1080at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_c930e/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | single | usbcam | - | - | - | 24.6 | - | n/a (no frames) | MJPG | [max_1920x1080at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | all 3 | c922 | - | - | - | 48.1 | - | n/a (no frames) | MJPG | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | all 3 | c930e | - | - | - | 48.1 | - | n/a (no frames) | MJPG | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT MediaFrameReader, MJPG subtype | 1920x1080at30 | all 3 | usbcam | - | - | - | 48.1 | - | n/a (no frames) | MJPG | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG auto buffered | c930e | - | - | - | 11.6 | - | n/a (no frames) | MJPG | [MJPG_auto_buffered_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_auto_buffered_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG auto buffered | usbcam | - | - | - | 8.4 | - | n/a (no frames) | MJPG | [MJPG_auto_buffered_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_auto_buffered_vid_4c4a_pid_4a55/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG cpu buffered | c930e | - | - | - | 22.4 | - | n/a (no frames) | MJPG | [MJPG_cpu_buffered_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_cpu_buffered_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG cpu buffered | usbcam | - | - | - | 16.7 | - | n/a (no frames) | MJPG | [MJPG_cpu_buffered_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_cpu_buffered_vid_4c4a_pid_4a55/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG cpu realtime | c930e | - | - | - | 20.2 | - | n/a (no frames) | MJPG | [MJPG_cpu_realtime_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_cpu_realtime_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader MJPG cpu realtime | usbcam | - | - | - | 17.8 | - | n/a (no frames) | MJPG | [MJPG_cpu_realtime_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/MJPG_cpu_realtime_vid_4c4a_pid_4a55/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader NV12 cpu buffered | c930e | - | - | - | 0.1 | - | n/a (no frames) | NV12 | [NV12_cpu_buffered_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/NV12_cpu_buffered_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader NV12 cpu buffered | usbcam | - | - | - | 0.1 | - | n/a (no frames) | NV12 | [NV12_cpu_buffered_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/NV12_cpu_buffered_vid_4c4a_pid_4a55/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader none auto buffered | c930e | 30.73 | - | 1382 | 14.5 | - | n/a (pixels) | NV12 | [none_auto_buffered_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/none_auto_buffered_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader none auto buffered | usbcam | 25.91 | - | 1382 | 12.3 | - | n/a (pixels) | NV12 | [none_auto_buffered_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/none_auto_buffered_vid_4c4a_pid_4a55/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader none cpu buffered | c930e | 30.58 | - | 1382 | 22.0 | - | n/a (pixels) | NV12 | [none_cpu_buffered_vid_046d_pid_0843](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/none_cpu_buffered_vid_046d_pid_0843/summary.json) |
| (c) WinRT variants | 1280x720at30 | single, reader none cpu buffered | usbcam | 26.10 | - | 1382 | 20.1 | - | n/a (pixels) | NV12 | [none_cpu_buffered_vid_4c4a_pid_4a55](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_winrt_variants/none_cpu_buffered_vid_4c4a_pid_4a55/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | single | c922 | 30.00 | - | 2765 | 27.4 | 17.0 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_c922/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | single | c930e | 30.04 | - | 2765 | 28.2 | 80.1 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_c930e/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | single | usbcam | 25.77 | - | 2765 | 24.6 | 20.2 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | single (duphash) | usbcam | 25.72 | - | 2765 | 26.9 | 14.6 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_usbcam_duphash](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_usbcam_duphash/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | all 3 | c922 | 30.04 | - | 2765 | 44.7 | 17.0 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | all 3 | c930e | 30.04 | - | 2765 | 44.7 | 79.8 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1280x720at30 | all 3 | usbcam | did not open | - | - | - | - | - | index 1: open failed | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | single | c922 | 30.00 | - | 6221 | 39.1 | 4.2 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_c922/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | single | c930e | 30.04 | - | 6221 | 39.6 | 59.1 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_c930e/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | single | usbcam | 25.76 | - | 6221 | 37.4 | 15.7 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | single (duphash) | usbcam | 25.75 | - | 6221 | 38.8 | 15.1 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_usbcam_duphash](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_usbcam_duphash/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | all 3 | c922 | 30.00 | - | 6221 | 69.7 | 4.2 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | all 3 | c930e | 30.05 | - | 6221 | 69.7 | 59.1 | n/a (pixels) | MJPG (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW decode | 1920x1080at30 | all 3 | usbcam | did not open | - | - | - | - | - | index 1: open failed | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_DSHOW CONVERT_RGB=0 | 1280x720at30 | single | c922 | 30.00 | - | 2765 | 27.8 | 4.2 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-raw/common_1280x720at30_c922/summary.json) |
| (d) OpenCV CAP_DSHOW CONVERT_RGB=0 | 1280x720at30 | single | c930e | 29.92 | - | 2765 | 28.7 | 58.6 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-raw/common_1280x720at30_c930e/summary.json) |
| (d) OpenCV CAP_DSHOW CONVERT_RGB=0 | 1280x720at30 | single | usbcam | 25.71 | - | 2765 | 28.2 | 15.8 | n/a (pixels) | MJPG (720, 1280, 3)/uint8 | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-dshow-raw/common_1280x720at30_usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | single (openwait90) | c922 | 30.02 | - | 2765 | 48.8 | 4.4 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_c922_openwait90](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_c922_openwait90/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | single (openwait90) | c930e | 29.93 | - | 2765 | 46.3 | 58.7 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_c930e_openwait90](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_c930e_openwait90/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | single | usbcam | 30.02 | - | 2765 | 50.7 | 15.3 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | single (duphash) | usbcam | 30.11 | - | 2765 | 53.6 | 14.7 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_usbcam_duphash](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_usbcam_duphash/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | all 3 | c922 | 29.99 | - | 2765 | 68.9 | 4.4 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | all 3 | c930e | 29.94 | - | 2765 | 68.9 | 58.7 | n/a (pixels) | fourcc=22 (720, 1280, 3)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1280x720at30 | all 3 | usbcam | - | - | - | 68.9 | - | n/a (pixels) | fourcc=22 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | single | c922 | 30.04 | - | 6221 | 148.0 | 4.4 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_c922/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | single | c930e | 29.93 | - | 6221 | 142.6 | 60.0 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_c930e/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | single | usbcam | 29.97 | - | 6221 | 154.7 | 14.5 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | single (duphash) | usbcam | 30.04 | - | 6221 | 155.8 | 14.5 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_usbcam_duphash](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_usbcam_duphash/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | all 3 | c922 | 29.99 | - | 6221 | 146.4 | 4.4 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | all 3 | c930e | 29.94 | - | 6221 | 146.4 | 60.0 | n/a (pixels) | fourcc=22 (1080, 1920, 3)/uint8 | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF decode | 1920x1080at30 | all 3 | usbcam | - | - | - | 146.4 | - | n/a (pixels) | fourcc=22 | [max_1920x1080at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-decode/max_1920x1080at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | single (openwait90) | c922 | 29.99 | - | 1382 | 13.4 | - | n/a (pixels) | NV12 (1, 1382400)/uint8 | [common_1280x720at30_c922_openwait90](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_c922_openwait90/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | single (openwait90) | c930e | 30.05 | - | 1382 | 12.2 | - | n/a (pixels) | NV12 (1, 1382400)/uint8 | [common_1280x720at30_c930e_openwait90](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_c930e_openwait90/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | single | usbcam | 17.13 | - | 1382 | 4.8 | - | n/a (pixels) | NV12 (1, 1382400)/uint8 | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_usbcam/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | all 3 | c922 | 29.99 | - | 1382 | 16.1 | - | n/a (pixels) | NV12 (1, 1382400)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | all 3 | c930e | 30.03 | - | 1382 | 16.1 | - | n/a (pixels) | NV12 (1, 1382400)/uint8 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (d) OpenCV CAP_MSMF FORMAT=-1, CONVERT_RGB=0 | 1280x720at30 | all 3 | usbcam | - | - | - | 16.1 | - | n/a (pixels) | NV12 | [common_1280x720at30_c922+c930e+usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_opencv-msmf-raw/common_1280x720at30_c922+c930e+usbcam/summary.json) |
| (ref) MF with its MJPEG decoder -> NV12 | 1280x720at30 | single | c922 | 30.00 | - | 1382 | 3.7 | - | n/a (pixels) | NV12 | [common_1280x720at30_c922](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf-decoded-nv12/common_1280x720at30_c922/summary.json) |
| (ref) MF with its MJPEG decoder -> NV12 | 1280x720at30 | single | c930e | 30.04 | - | 1382 | 3.3 | - | n/a (pixels) | NV12 | [common_1280x720at30_c930e](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf-decoded-nv12/common_1280x720at30_c930e/summary.json) |
| (ref) MF with its MJPEG decoder -> NV12 | 1280x720at30 | single | usbcam | 25.78 | - | 1382 | 3.2 | - | n/a (pixels) | NV12 | [common_1280x720at30_usbcam](../results/windows/Gerald/mjpeg_rerun_20261027/mjpeg_msmf-decoded-nv12/common_1280x720at30_usbcam/summary.json) |

Earlier (2026-10-25) matrix, re-validated with the same validator and no new camera access:
[`../results/windows/Gerald/mjpeg_resummarized_20261025_data/table.md`](../results/windows/Gerald/mjpeg_resummarized_20261025_data/table.md).
It combines `mjpeg_resummarized_20261025_data` and `_data_b`, and covers only cells whose raw captures still existed and
are not marked INVALID or SUPERSEDED.

## Earlier results marked invalid

Device-state incidents on 2026-10-25 (local time is UTC−4):

- MF_E_REBOOT_REQUIRED from 14:04 to about 14:17, and from about 14:33 to 14:45.
- The Kiyo in ERROR_GEN_FAILURE (0x8007001F) from about 14:30, and again after its re-plug.

`INVALID.txt` or `SUPERSEDED.txt` now sits in each affected cell under `results/windows/Gerald/`:

- **Marked earlier:**
  - `mjpeg_devtest/*`, `mjpeg_dshow_formats`, `mjpeg_mf_blocked`, `mjpeg_mf_recheck`, `mjpeg_pyav_dshow_format_probe` (kiyo.json)
  - `mjpeg_msmf/common_1280x720at30_c922+kiyo+c930e`
  - `mjpeg_pyav-dshow/common_1280x720at30_c922+kiyo+c930e`
  - the two 3-camera SUPERSEDED cells
  - `mjpeg_opencv-dshow-decode/..._order-size-first`
- **Added 2026-10-27:**
  - `mjpeg_msmf/common_1280x720at30_kiyo` and `max_1920x1080at60_kiyo` (0x8007001F, 0 frames)
  - `mjpeg_pyav-dshow/common_1280x720at30_kiyo` and `max_1920x1080at60_kiyo` (open failed)
  - the three 4-camera cells with a faulted Kiyo
  - `mjpeg_winrt/common_1280x720at30_c922` (SUPERSEDED: old script)
  - `mjpeg_matrix/` (SUPERSEDED: stale table)

**Kiyo coverage:**

- The earlier "Kiyo delivers rawvideo YUY2 under PyAV dshow" observation came from `prior_art_pyav_dshow-kiyo-720p` and was
  never reproduced in this matrix.
- Kiyo 1080p60 MJPEG was never measured.
- Neither was re-tested: the Kiyo is excluded.

## Harness state (one version of each tool)

| file | role |
| --- | --- |
| `mjpeg_common.py` | Run-dir contract, JPEG validation (SOI/EOI, Pillow, strict and lenient libjpeg-turbo), header fingerprint, CPU accounting, luma, machine CPU, DevNodeStatus. `DEFAULT_CAMS` excludes the Kiyo. |
| `msmf/mf_mjpeg_capture.cpp` (`build.bat`, builds to `build/`) | MF native-MJPG capture. Also `--list [--dev]` (activates only `--dev` matches), `--list-enum` and `--list-dshow` (open no camera), `--dshow-formats` and `--controls-only --via-dshow`. |
| `pyav/pyav_capture.py`, `pyav/pyav_dshow_format_probe.py` | PyAV demux-only capture (dshow, v4l2, avfoundation). Flags a silent format fallback. |
| `winrt/winrt_capture.py`, `winrt/run_winrt_variants.sh` | WinRT MediaFrameReader, plus a variant sweep (3rd argument = results root). |
| `opencv/opencv_capture.py` | OpenCV baseline. `--open-wait` (default 90 s), per-frame CRC and repeat count, luma. |
| `run_one.py` | Sets and reads back controls, DevNodeStatus and machine CPU around one capture; kills the process tree after `--timeout-s`. |
| `run_matrix.py` | One camlock hold per cell. `--root` is a fresh results root; existing cells are skipped, never deleted. Writes an `index_*.json`. |
| `summarize.py`, `resummarize.py` | Validate and summarize a run dir, refusing to overwrite. `resummarize.py` re-validates scratch captures into a NEW `--out-root`. |
| `aggregate.py`, `results_table.py`, `compare_runs.py` | Matrix table from one or more roots, with native and header comparison against the MF reference (`--ref-test` on Linux/macOS). Also this file's table, and the earlier-vs-new comparison. |
| `list_formats.py` | DirectShow and MF MJPEG modes of the named cameras. Writes `mjpeg_formats/<stamp>/`. |
| `drafts/linux/run_linux_mjpeg.sh`, `drafts/linux/v4l2_mmap_mjpeg.py` | Linux runner: V4L2 via PyAV `input_format=mjpeg`, and pure-Python mmap V4L2. |
| `drafts/macos/run_macos_mjpeg.sh`, `drafts/macos/avf_mjpeg_probe.py` | macOS runner: PyAV avfoundation attempts, and the pyobjc AVCaptureVideoDataOutput native-format check (videoSettings nil vs {}). |
| `drafts/check_drafts.py` | Static checks of the drafts. |

## Linux and macOS drafts

Status: unverified. The drafts have never run on Linux or macOS.

**Static check:** `uv run --script research/usb_cameras/mjpeg/drafts/check_drafts.py` passed (all_ok true), written to
`../results/windows/Gerald/mjpeg_drafts_check/20261028T044052Z/summary.json`. It checks:

- `py_compile` passes for every `.py` under `mjpeg/`.
- `bash -n` passes for every `.sh`.
- `v4l2_mmap_mjpeg.py --selftest` passes: ctypes struct sizes and offsets and ioctl numbers match the LP64 reference.
- Every script each runner references exists.
- Each runner writes into a fresh `results/<os>/<host>/mjpeg_run_<UTC stamp>/` root and passes `--root` to every
  result-writing call (5 of 5 per runner).

**What each runner does:**

- **Linux** (`drafts/linux/run_linux_mjpeg.sh`): runs each camera at 1280x720@30, then all cameras together, then each
  camera at its max mode, with both V4L2 backends. It then aggregates with `--ref-test mjpeg_v4l2_mmap`, so the
  PyAV-v4l2 bytes are checked against the pure-V4L2 bytes.
- **macOS** (`drafts/macos/run_macos_mjpeg.sh`): runs the AVF probe with videoSettings nil and {}, then the PyAV
  avfoundation attempts (default, each pixel_format, vcodec=mjpeg). It aggregates with
  `--ref-test mjpeg_avf_videodataoutput`.

## Open questions

- Why does OpenCV CAP_MSMF take 39–41 s to open the two Logitech cameras but 3.5 s to open the generic camera? Its open
  path enumerates every native type, and the Logitech cameras expose about 335 of them, but this is unmeasured.
- OpenCV CAP_MSMF raw (NV12) on the generic camera ran at 17.1 fps, while every other path ran at 25.7. Not
  investigated.
- Which camera loses the bandwidth race on the shared hub (C930e at 720p, generic at 1080p under MF) looks
  order-dependent. Goal 3 covers forced alternate settings.
- The process-CPU differences against 10-25 at low machine load are unexplained (see "CPU load and caveats").
- Kiyo Pro: no data from this rerun, by design.
