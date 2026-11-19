# EN7A — Phase 3 decisions: Windows native capture through Media Foundation (D1 to D49)

**Status:** accepted, 2026-11-19 (user; grilling session of 2026-11-19; commit to dom/native-jpeg).

## Decision

The user decided D1 to D49 for phase 3 on 2026-11-19. In short (section 20 of
`specs/windows-capture.md` gives each one in full):

1. **Route** (D1 to D5). Pure-Python Media Foundation through `comtypes`, no compiled extension, no
   Rust, on `development-streaming`; `sfn26` gives ideas only. Steps: 3a MJPG passthrough,
   3b YUY2 and NV12 (encoder, Quick Sync check, range rule), 3c full mode list and controls. A spec
   before code; fake-source tests in CI, hardware tests on the user's word. No H.264 mode is
   opened. Phase order: 3, 4, 5, 6, certify, 0, 7, 8.
2. **Structure** (D6 to D10). One shared loop (gate, recorder, rings) with a capture interface (open,
   read a frame, set controls, close) and three sources: Media Foundation, OpenCV (Linux, macOS, with
   the JPEG re-encode) and a fake. A new, smaller module from the prototype calls; `comtypes` pinned
   exactly, Windows only. A setting chooses the source on Windows during the build (OpenCV default);
   the last commit of phase 3 deletes it and the OpenCV source on Windows after the comparison run.
   The old recorder stays until phase 5, fed by one `cv2.imdecode` per JPEG that also feeds the BGR
   ring. Each Media Foundation call that can hang has a time limit; on a hang the camera process
   reports, then ends itself hard.
3. **Detection and modes** (D11 to D19). Windows detection uses Media Foundation from 3a;
   `camera_id` is today's hash of the device path; open by path, never by index. "In use by another
   program" is a failure; duplicate IDs are refused. `supported_modes` in the `sfn26` shape (MJPG,
   one entry per size, area then width descending, rates ascending, rounded) from 3a; the richer list
   is a second field in 3c. Mode: exact size, MJPG, nearest rate within 0.5 fps, else fail with the
   mode list. Auto rate: 30 if present, else the highest. The config stores the mode rate; rates
   compare with a relative tolerance of 0.0001. One mode rate per group while the gate exists. 3b
   uses `capture_fourcc`.
4. **Start-up** (D20 to D25). Open, mode, stream, first frame, set controls, read back, warm-up.
   90 warm-up frames, ready within 15 s, wait paused until all are ready. Rate check over warm-up
   frames 6 to 90: (frames - 1) / (last - first arrival); fail more than 3 % below or above the mode
   rate that Media Foundation reports; no median. A failed camera is flagged; the other cameras
   stay open; recording is blocked until "apply again" or "unselect"; skellycam never reopens it by
   itself. The generic camera fails by design. The slow message gives both rates and two hints.
5. **Open cameras** (D26 to D35). The gate takes the newest frame not taken, or waits; replaced frames
   are counted and logged. `source_frame_number` is the delivered count. Frame time is the arrival
   time; the sample time goes into `sample_ns`, unused. Exposure modes MANUAL, AUTO, RECOMMEND stay;
   the status reports current exposure, gain and focus, also in auto. Exposure, gain and focus change
   live; a resolution or rate change reopens only that camera. After a live change: skip 15, check 60
   frames at 3 %, decide early; a failure is "too slow" with preview, recording blocked; "checking"
   blocks recording. A drop after a change is normal. Exposure in log2 seconds.
6. **Recording** (D36 to D39). Setting changes are refused. A control in auto at the start: record
   anyway, warn with camera and control, note it in the capture info. Dead at once on device removed,
   or after 2 s without a frame; it leaves the gate, its files are finished, the session reports it
   and its last frame, and the other cameras keep recording. A slow camera only gets a warning.
7. **Reporting and controls** (D40 to D46). A failure is an object (camera ID, stage, reason) and
   the text `Camera {id} failed during {stage}: {reason}`; the first failure is kept and written
   before any shutdown flag. Timestamp columns only for stamped stages; a frame with a wrong camera
   ID is refused. The Windows fix of T-RING-46 in 3a: a pipe as the error output of each camera
   process before OpenCV loads. 3c: gain and focus in the config; white balance and power line
   frequency read only, into the capture info; an absent control is reported, and a set of it is an
   error. Not in phase 3: the USB link display and the event-log check. The start-up rules apply to
   OpenCV too, with the rate check only when OpenCV reports a rate above 0.
8. **Tests and done** (D47 to D49). A CI workflow runs the fake-source tests on Windows (and loads
   the Media Foundation module) and on Linux, on pushes to `dom/native-jpeg`, pinned; the arm64 job
   stays. 3a is done with the four conditions of D48; 3b and 3c get matching lists. D49 lists the
   hardware tests.

D23 replaces the plan statement "a camera that fails or hangs at open stops the session from
starting". D38 replaces the plan statement that native capture only "reports a slow or stalled
camera" mid-take. Both are in `research/NATIVE_JPEG_CAPTURE_PLAN.md` §3 on branch `dom/research`.

## Reason

- The user, 2026-11-19, in a grilling session. Only these decisions are accepted. The spec waits for
  the user.

## Evidence

On branch `dom/research` at commit fc95be447 of this repository:

- `research/usb_cameras/docs/startup_rate_check_20261119.md`: the median passed the generic camera in
  564 of 564 opens; the elapsed-time rate caught it; 194 live control changes.
- `research/usb_cameras/docs/windows_results_20261113.md`: four cameras for 600 s in one process,
  0 lost frames; in-use refusal `0xC00D3704`.
- `research/frame_ring_buffer/decode_bench/FINDINGS.md`: `cv2.imdecode` 2.60 ms at 720p, 5.42 ms at
  1080p.

## Alternatives rejected

- Rust; a merge of `sfn26` (D1). The median (D22). Stop the group on one failed or dead camera (D23,
  D38).

## Open work

See [open-work.md](../open-work.md).
