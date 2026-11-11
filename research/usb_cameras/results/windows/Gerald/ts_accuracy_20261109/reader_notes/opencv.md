# OpenCV 4.12 on Windows: what it can and cannot do for frame timing

Written 2026-11-09 on Gerald. skellycam development-streaming pins `opencv-contrib-python==4.12.*` (`pyproject.toml:55`); the venv has 4.12.0.88 and every probe reported `cv2_version 4.12.0`.

Labels: **measured** (a result file below supports it), **code** (read from source), **inferred** (reasoned, not tested).

**Sources.** Upstream tag 4.12.0, `modules/videoio/src/{cap_dshow.cpp, cap_msmf.cpp, cap.cpp, ...}` and `include/opencv2/videoio.hpp`, saved in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/opencv_src/`. Line numbers below are for that tag. The earlier review (`research/usb_cameras/docs/skellycam_timestamps_review.md`) used 4.x HEAD, so its line numbers are a few lines off. Its conclusions about DirectShow still hold for 4.12.0.

**New runs (today, C930e only, 1280x720 MJPG @30, all under camlock).** Harnesses are in `.../scratchpad/opencv_scripts/` and results in `.../scratchpad/opencv_results/` (full paths in §6).
- `dshow_timing.py`: OpenCV CAP_DSHOW loop, with 0, 20 or 50 ms of simulated work per iteration.
- `msmf_timing.py`: OpenCV CAP_MSMF: open time, `CAP_PROP_POS_MSEC`, and the `CONVERT_RGB=0` output.
- `fit_stamps.py`: the study's frame-slot fit (`suite/common/tsanalysis.fit_frame_index`) applied to those stamps.
- `jpeg_decode_bench.py` and `nv12_bench.py`: decode costs (no camera).

Scope limits: one camera and one run per variant, with no ground truth. These runs score regularity and mechanism, not accuracy against capture time.

## 1. DirectShow backend (CAP_DSHOW, skellycam's Windows path)

### 1.1 What each call does (**code**, `cap_dshow.cpp`)

| Call | What it does in 4.12.0 | Lines |
| --- | --- | --- |
| `grab()` | `return !g_VI.isDeviceDisconnected(m_index);` It drains graph events and looks for `EC_DEVICE_LOST`. It does not wait and does not touch a frame. | 3633–3636, 2443–2462 |
| `retrieve()` | Sizes the output Mat, then calls `getPixels(m_index, ptr, flipRedAndBlue=false, flipImage=true)`. | 3637–3653 |
| `getPixels` | `WaitForSingleObject(hEvent, 1000)`. On timeout it returns false. Otherwise, under the critical section, it copies the stored frame with a vertical flip (`processPixels`), clears `newFrame`, leaves the section, then `ResetEvent`. | 1543–1594, 2225 |
| `SampleCB(double, IMediaSample*)` | **Returns at once if the event is still set**, so a frame is unread. Otherwise it `memcpy`s the sample into `pixels`, sets `newFrame`, then `SetEvent`. The sample-time argument is unnamed and never read. No `IMediaSample::GetTime`/`GetMediaTime` call exists anywhere in the file. | 703–723 |
| `BufferCB` | `E_NOTIMPL` (SampleCB mode is used: `SetCallback(sgCallback, 0)`) | 727–729, 2870 |
| event | Manual reset (`CreateEvent(NULL, true, false, NULL)`) | 656 |
| `isFrameNew` (freeze check, auto-reconnect) | Exists, but the VideoCapture path never calls it | 1641–1676 |

Consequences (**code**):
- `retrieve()` returns **the first frame that arrived after the previous `retrieve()` finished**, not the newest. Every later frame is discarded inside `SampleCB` until it is read. There is no counter of discarded frames.
- There is one slot, not a queue. A frame that sits unread keeps its place, and its age is invisible to the caller.
- **Where the MJPEG decode happens.** The sample grabber's media type is forced to `MEDIASUBTYPE_RGB24` for anything except 8/16-bit, Y16 or NV12 (2885–2899). With MJPG on the capture pin, `RenderStream` (2929) therefore inserts a decoder (MJPEG Decompressor, plus a colour converter if needed) between the camera and the grabber. The DirectShow samples are pushed on the capture pin's streaming thread, so decode, conversion and `SampleCB`'s 2.76 MB `memcpy` all run serially on that thread **before** `SetEvent` (**inferred** from DirectShow's push model; **code** for the RGB24 type). `retrieve()` itself only waits, copies and flips.
- **No graph clock.** `SetSyncSource(NULL)` (2945) leaves the graph without a reference clock. That doesn't matter here, because the sample times are never read.

### 1.2 Properties (**code**, confirmed by **measured** return values in `dshow_c930e_aep0/summary.json`)

| Property | Behaviour | Lines | Measured |
| --- | --- | --- | --- |
| `CAP_PROP_BUFFERSIZE` | No case in `setProperty` (it falls through to `return false`) or in `getProperty` (it returns −1). The skellycam comments saying DSHOW honours it are wrong. | 3456–3630, 3453 | `set` → False, `get` → −1 |
| `CAP_PROP_POS_MSEC`, `CAP_PROP_POS_FRAMES` | Not handled, so −1 | 3391–3455 | −1 on every frame (also all 15 DSHOW cells of 10-27, via `posmsec_stats.py`) |
| `CAP_PROP_FPS` (get) | `getFPS()` returns `1e7 / requestedFrameTime`, **the requested rate, not the negotiated or delivered one**. It returns 0 if no rate was ever requested. | 1470–1481 | Reported 30.00003 while the C930e delivered 16.0 fps (AE priority 1, run `dshow_c930e_run1`) |
| `CAP_PROP_FPS` (set) | If it differs from `getFPS()`: `stopDevice`, `setIdealFramerate`, then `setupDevice(w,h)` **without the FOURCC**. That restarts the graph, and the format falls back to the first type in `mediaSubtypes[]` (RGB24, …, YUY2 before MJPG) that `SetFormat` accepts. | 3498–3511, 1086–1110, 2587–2637 | (10-27 "10 fps YUY2" with FOURCC-first, `mjpeg/RESULTS.md` finding 6) |
| `CAP_PROP_FOURCC`, `FRAME_WIDTH/HEIGHT` | Stored. Once both width and height are known and differ from the current ones: `stopDevice` → `setIdealFramerate(getFPS())` → `setupDeviceFourcc(w,h,fourcc)`, i.e. a **full graph rebuild**. A width or height set alone doesn't restart. `setIdealFramerate` is a no-op while the device is set up (1155–1161), so it only takes effect because `stopDevice` runs first. | 3472–3487, 3550–3575 | Size-first order gave MJPG 1280x720 at 30.05 fps |
| `CAP_PROP_CONVERT_RGB=0` | Only changes output for Y16. MJPG still decodes to RGB24 → BGR 8UC3. **OpenCV DSHOW cannot return JPEG bytes.** | 1563–1574, 3538–3545, 3644–3650 | `(720,1280,3)` (10-27 `mjpeg_opencv-dshow-raw`) |
| Open with params (`VideoCapture(i, CAP_DSHOW, [W,H,FOURCC])`) | `setupDeviceFourcc` before `open()`, so one graph build in the requested format. The FPS param is ignored, so the rate stays whatever the format's default `AvgTimePerFrame` is. | 3361–3383 | not run |
| Timeouts | `retrieve()` has a fixed 1 s wait. Open has none, and `CAP_PROP_OPEN/READ_TIMEOUT_MSEC` are for FFmpeg/GStreamer only (`videoio.hpp:196-197`). | 1551 | — |

## 2. The best per-frame stamp a Python loop can get from CAP_DSHOW

### 2.1 What the loop sees (**measured**, `dshow_c930e_aep0`, C930e at 30.05 fps)

| Work per iteration | Delivered fps | `grab()` ms p50 | `retrieve()` ms p5 / p50 / p95 | Retrieve blocked (>2 ms) | Post-retrieve steps on a 16 ms multiple (±2 ms) | Frames lost |
| --- | --- | --- | --- | --- | --- | --- |
| 0 ms | 30.05 | 0.002 | 31.4 / 31.9 / 47.9 | 100% | 96% | 0 |
| 20 ms | 30.04 | 0.005 | 11.5 / 12.0 / 28.0 | 100% | 99.7% | 0 |
| 50 ms | **19.90** | 0.006 | **0.20 / 0.24 / 0.32** | 0.5% | 0% (steps = loop period 50.25 ms, sd 0.06) | ~1 in 3, **silently** |

- `grab()` takes 2–6 µs, so the skellycam stamp (midpoint of pre/post grab, `opencv_get_frame.py:53-55`) is just "when the loop started waiting".
- In a free-running loop it equals the previous frame's post-retrieve time plus 0.10 ms (p50; max 0.21 ms). That makes it **one frame period early**: 31.9 ms p50, 47.9 ms p95, against the frame's own post-retrieve time (**measured**, `fit_stamps.py`).
- Under skellycam's lockstep gate the offset varies between −P and 0 when retrieve blocks. When the frame was waiting it is late by the frame's age (**inferred**, from the code and the 50 ms row).
- **Post-retrieve stamps carry the same 16 ms delivery grid as MF.** A frame-slot fit gives residual sd 4.64 ms (work 0) and 4.68 ms (work 20). OpenCV MSMF's real sample time on the same camera gives 4.47 ms (§3), and 16/√12 = 4.62 ms (**measured**, `fit_stamps.json`).
- **A fit on stale stamps is silently wrong.** On the 50 ms run the fit returns 19.90 fps with 0.21 ms residual sd, 0 skipped slots and `fit_unreliable: false`. It has fitted the loop, not the camera (**measured**). Stale frames must be removed before fitting.

### 2.2 Recipe and error terms

1. Stamp `t_pre = perf_counter_ns()` just before `retrieve()` and `t_post` just after it. On DSHOW, `grab()` stamps carry no information.
2. **Classify each frame.** `b = t_post − t_pre`.
   - `b < 1 ms`: **stale**. The frame was already waiting; its age lies between 0 and `t_pre − t_post(previous)`. Immediate retrieves measured 0.20–0.32 ms (p5–p95); blocked ones were ≥11.5 ms (p5) at 20 ms of work (**measured**).
   - Otherwise **fresh**, and `t_post` is tied to delivery.
3. Fit `t_k = a + P·k` on fresh frames only, with slots by rounding and a lower envelope (`tsanalysis.fit_frame_index`).
4. A stale frame's slot is the **first slot after `t_post(previous)`**, because `SampleCB` latches the first frame after the last `ResetEvent`. This is ambiguous whenever `t_post(previous)` falls within the delivery jitter (up to ~16 ms) of a slot (**inferred**, from code 703–716 and 1590).

Error terms of a fresh `t_post` relative to the moment the frame reached the host:

| Term | Size | Label |
| --- | --- | --- |
| KS/USB delivery grid (also present in MF) | 0–16 ms, sd ≈ 4.6 ms. It is removed by the fit, which scored at the method floor (0.47–0.68 ms against flash) on **MF** arrival for the C922 (REPORT.md table row "Frame index fitted to arrival envelope"); never scored on DSHOW | measured (grid); inferred (fit on DSHOW) |
| MJPEG decode + RGB conversion + 2.76 MB `memcpy` on the streaming thread before `SetEvent` | About 8–9 ms CPU per frame at 720p: the DSHOW graph uses 24.6–28.3% of a core at 30 fps (REPORT.md finding 3). It varies with JPEG size and scene content, and is larger under CPU load. The fit absorbs the frame-to-frame part; the constant part stays as an **unknown per-camera bias** (cameras differ: C922 frames 207 kB vs C930e 76 kB) | inferred |
| `getPixels` copy and flip | 0.20–0.32 ms, constant | measured |
| Event wake-up and return to Python | tens of µs (loop overhead in total 0.10 ms p50) | measured (upper bound) / inferred |
| 1 s timeout | Only on failure: `retrieve()` returns False and the frame state is unchanged | code |

### 2.3 Counting lost frames on DSHOW

There is **no counter**:
- `POS_FRAMES` is −1, and `SampleCB` counts nothing (**code**, **measured**).
- Losses can only be inferred:
  - **Upstream drops** (camera rate change, USB, KS starvation) show as slot gaps (≥2P) between consecutive **fresh** frames (**inferred**).
  - **OpenCV-side discards** happen only when the loop is slower than the frame period. They appear only as the slot jump from a stale frame's inferred slot (step 4 above), and in aggregate as (span × fitted fps) − frames delivered (**inferred**).
- skellycam already stores `pre_frame_retrieve_ns` and `post_frame_retrieve_ns` (`opencv_get_frame.py:71-73`), so existing recordings can be checked for stale frames without new code (**code**).

**Consequence for different frame rates (inferred, from code plus the 50 ms row).** Lockstep (`camera_orchestrator.py:96-109`) holds every camera to the slowest one's loop. A faster camera then has the slower camera's iteration time as its "work", which is exactly the 50 ms row: its `retrieve()` returns a waiting frame, newer frames are dropped inside `SampleCB`, and its stamps follow the slow camera's loop. For any DSHOW-based fix to hold, each camera's grab/retrieve has to run in its own unthrottled loop, with pairing done afterwards on stamps.

## 3. Media Foundation backend (CAP_MSMF)

### 3.1 Mechanism (**code**, `cap_msmf.cpp`)

- **Async source reader.** A `SourceReaderCB` is set as `MF_SOURCE_READER_ASYNC_CALLBACK` (1219–1232).
  - `OnReadSample` pushes `{llTimestamp, sample}` into a queue and re-issues `ReadSample` (449–497).
  - When the queue already holds `MSMF_READER_MAX_QUEUE_SIZE = 3`, it **clears the whole queue** and keeps only the new frame (411, 458–468).
  - `grab()` waits up to 10 s, then **pops the front (oldest)** entry and sets `usedVideoSampleTime = llTimestamp` (508–550, 1757–1811).
- **`CAP_PROP_POS_MSEC`** returns `usedVideoSampleTime / 1e4`. That is the MF sample time, in ms on the QPC timebase, i.e. the same clock as `time.perf_counter_ns()` (2136–2137).
- **`POS_FRAMES`** returns `nFrame`, which only the synchronous file path increments (1536, 1547). It stays 0 for cameras.
- **`CAP_PROP_BUFFERSIZE`.** `set` returns false (2385). `get` falls through to `return audioBaseIndex` (2233–2235); the measured value 1.0 is that, not a buffer size.
- **`CAP_PROP_FOURCC` set** calls `configureVideoOutput(fmt, fourcc)`, which treats the FOURCC as an output *mode*. Unless `CONVERT_RGB=0`, that hits `default: return false` (1155–1156, 2285). **It cannot choose the MJPG native type.**
- **Native type choice** (`findBestVideoFormat`, 633–647; `VideoIsBetterThan`, 318–339) ignores the subtype. It ranks by resolution, then by frame rate, and keeps the first of tied types. MF lists an MF-synthesized NV12 type right before each MJPG type (`suite/windows/native/README.md`, line 40), so the NV12 type wins.
- **Output.**
  - With `CONVERT_RGB=1` the reader converts to RGB24, or to RGB32 in D3D11 mode (1135–1141): `ENABLE_ADVANCED_VIDEO_PROCESSING` is true (962), and D3D11 is used by default (`CAP_PROP_HW_ACCELERATION` defaults to ANY, 1063–1071; measured `hw_accel` 2).
  - With `CONVERT_RGB=0` the reader's output is the native type, and `retrieve()` returns the buffer as a 1×N `CV_8UC1` Mat (1926).
- **Open time knob.** `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS` (default true) is read into `MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS` (956–959).
- **No access to MF sample attributes.** OpenCV never reads `MFSampleExtension_CaptureMetadata`, so UVC PTS/SCR (tier 1) cannot be reached through OpenCV, even on Gerald with the registry value set.

### 3.2 Measured (C930e; `msmf_c930e/` and `msmf_c930e_rawfirst/`; 10-27 cells re-analysed with `posmsec_stats.py`)

| Variant | Open → first frame | Output | POS_MSEC steps | post-grab − POS_MSEC (p5 / p50 / p95) | Slow loop (50 ms work) |
| --- | --- | --- | --- | --- | --- |
| default env, CONVERT_RGB=1 | **32.3 s** (39–41 s on 10-27) | BGR | **exactly 33.333 ms, sd 0**, i.e. synthesized | −8 / 3 / 14 ms (the host stamp can precede the "sample time") | — |
| `..._HW_TRANSFORMS=0`, CONVERT_RGB=1 | **0.91 s** | BGR | exactly 33.333 ms | −9 / 1.7 / 12.5 ms | — |
| `HW_TRANSFORMS=0`, CONVERT_RGB=0 set **after** streaming started | (same open) | 1×3,686,400 B = RGB32 bytes. `set` returned False but the flag stuck | exactly 33.333 ms | −13 / 13 / 31 ms | 17.4 fps |
| `HW_TRANSFORMS=0`, CONVERT_RGB=0 set **before the first read** | **0.86 s** | 1×1,382,400 B **NV12** (MF-decoded, not JPEG) | **16 ms grid** (32.0 / 46.7 ms; fit residual sd 4.47 ms) | **0.007 / 0.10 / 16.1 ms** | 17.6 fps; **POS_MSEC gaps count the 99 lost frames exactly** (fit: 30.05 fps, 99 skipped slots); frame age visible (up to 111 ms) |

Further points:
- **Synthesized timestamps when a converter is in the chain.** Exact 33.333 ms steps appeared in every OpenCV MSMF decode cell of 10-27 (15 camera-cells) and today. The generic camera's decode path also pads 25.3 fps with duplicate frames (`mjpeg/RESULTS.md` finding 3). The likely cause is the reader's video processor doing frame-rate conversion (**inferred**).
- **Real sample time** appears only when the output is the native NV12 type. 10-27's `opencv-msmf-raw` cells agree: 32.0 / 46.7 ms steps, 16 ms grid (**measured**).
- **The real sample time is essentially an arrival stamp.** It sat 0.1 ms (median) before the host stamp taken right after `grab()` returned (**measured**). It is not an earlier device-side time.
- **Open-time cause.** The 30–40 s Logitech open is `MF_READWRITE_ENABLE_HARDWARE_TRANSFORMS`: setting the environment variable to 0 cut it to 0.86–0.91 s. This is n=1 per variant on one camera (**measured**). Not tested: the C922 and the Kiyo, and `CAP_PROP_HW_ACCELERATION=NONE`.
- **Retrieve cost** is 6–8 ms per frame in D3D11 mode, for both NV12 and RGB (**measured**). That is probably a GPU-to-CPU readback (**inferred**). NV12→BGR with `cv2.cvtColor` adds 0.27 ms single-threaded, or 0.04 ms with 28 threads (**measured**). The 10-27 CPU for the NV12 path was 12–13% of a core (REPORT.md finding 3).
- **Slow loops lose frames in bursts.** Because of the queue-of-3 clear, a slow loop shows 128–144 ms POS_MSEC gaps, i.e. four slots per gap (**measured**), and frames up to about 3.5 periods old.

### 3.3 Is "OpenCV MSMF + sample time" a middle option?

**For timing, partly yes. For raw MJPEG, no.**

What it gives:
- With `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0` and `CONVERT_RGB=0` set before the first read, OpenCV MSMF opens in under 1 s.
- `POS_MSEC` is then a real per-frame OS stamp. It has the same 16 ms grid as DSHOW post-retrieve (4.47 vs 4.64 ms raw fit residual), so the per-frame precision for fresh frames is no better.
- It is **robust where DSHOW is not**: late frames keep their true stamp, lost frames are counted exactly from gaps, and there is no decode offset in front of the stamp (**measured**).

Costs and limits:
- Frames come as MF-decoded NV12, not JPEG. Recording would still need a re-encode. OpenCV cannot select the MJPG type (**code**, **measured**).
- It depends on an order-sensitive property sequence that silently degrades to synthesized stamps if the order changes (**measured**).
- Retrieve costs 6–8 ms, and the queue-clear drops come in bursts.
- MF device indices include virtual cameras (NDI etc. on Gerald).
- No path to PTS/SCR.

As a stopgap that keeps OpenCV it is reasonable. It is dominated by custom MF native-MJPG capture, which gives the same sample time plus JPEG bytes at 1–2% CPU (REPORT.md findings 1 and 3).

## 4. Other OpenCV knobs and costs

- **Not available on these backends:**
  - `CAP_PROP_ORIENTATION_AUTO` (FFmpeg/AVFoundation only, `videoio.hpp:192`).
  - `CAP_PROP_OPEN_TIMEOUT_MSEC` and `READ_TIMEOUT_MSEC` (FFmpeg/GStreamer only, 196–197). Opens must be wrapped in a watchdog.
  - `VideoCapture::waitAny` (V4L only, `cap.cpp:633-655`).
  - `CAP_PROP_BUFFERSIZE` (neither backend).
  - The `CAP_FFMPEG` backend is file/stream only (`videoio_registry.cpp:69-72`). Opening `dshow` devices through it, to get packets via `CAP_PROP_FORMAT=-1`, would need avdevice in the wheel's FFmpeg. **Not tested**; PyAV covers that route.
- **Debug only:**
  - `OPENCV_DSHOW_SAVEGRAPH_FILENAME` saves the built DirectShow graph, showing which decoder was inserted (`cap_dshow.cpp:2975-2990`).
  - `OPENCV_LOG_LEVEL=DEBUG` makes MSMF log "drop previous frames" (466), but nothing is exposed to code.
- **`read()` = `grab()` + `retrieve()`** (`cap.cpp:554-564`), so skellycam's split gains nothing on DSHOW.
- **Decoding MJPEG yourself** (raw bytes from MF or PyAV), real camera JPEGs, single thread, i7-14700K (**measured**, `decode_bench.json`):

| Frame | Bytes | `cv2.imdecode` p50 | `simplejpeg` (libjpeg-turbo) p50 | PyAV mjpeg p50 (uses several threads) |
| --- | --- | --- | --- | --- |
| C922 720p | 207,570 | 3.13 ms | 2.50 ms | 2.95 ms |
| Kiyo 720p | 124,044 | 2.53 ms | 1.84 ms | 2.24 ms |
| C930e 720p | 76,214 | 2.22 ms | 1.59 ms | 1.91 ms |
| generic 720p | 64,520 | 2.17 ms | 1.49 ms | 1.69 ms |
| C922 1080p | 227,823 | 5.61 ms | 4.22 ms | 4.25 ms |

- **Decode cost in context.**
  - With four threads decoding at once, per-call times rose by only 5–15% (e.g. C922 720p: cv2 3.42 ms, simplejpeg 2.61 ms).
  - Four cameras at 720p30 means 120 decodes/s, about 0.2–0.4 of one core with simplejpeg or cv2.
  - OpenCV DSHOW's in-graph decode uses ~25–28% of a core **per camera** (REPORT.md finding 3), roughly 3x cv2.imdecode's cost.
  - Decoding off the capture thread also takes decode time out of the timestamp path entirely.
  - The machine was not idle: other agents were running, and whole-machine CPU is in `decode_bench.json`.

## 5. Answers in brief

| Question | Answer |
| --- | --- |
| DSHOW grab/retrieve | `grab` is a no-op. `retrieve` waits up to 1 s for **the first frame after the previous retrieve**; newer frames are discarded while one is unread. The decode runs in the graph before the event fires. No sample time, no `BUFFERSIZE`, no `POS_*`. FPS get echoes the request. Format and rate sets rebuild the graph. `CONVERT_RGB=0` is still BGR. (code; measured) |
| Best DSHOW stamp | `t_post` after a `retrieve()` that blocked; reject `retrieve < 1 ms` as stale; slot-fit fresh frames only. Raw residual 4.64 ms (16 ms grid), the same as MF. It includes an unknown, roughly constant per-camera decode delay (~ms). Losses can only be inferred from slot gaps. A fit on stale stamps is falsely clean. (measured; inferred) |
| Gain from revising DSHOW (option 1) | From "one period early in a free-running loop, −P..+age under lockstep, silent staleness" to the 16 ms grid floor per frame (~4.6 ms sd), and plausibly ~0.5–1 ms after the fit. The fit has been scored only on MF arrival, never on DSHOW. This holds only if the capture loop never goes stale, which means ending lockstep throttling of the capture loop. (measured; inferred) |
| MSMF via OpenCV | Real sample time only for native NV12 output, with `CONVERT_RGB=0` before the first read; otherwise synthesized 33.333 ms steps. Open drops from 32–41 s to 0.9 s with `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`. Exact drop counts. No JPEG and no PTS. (measured; code) |
| What custom MF native MJPG adds (option 2) | Not better per-frame precision for fresh frames (same OS grid). It adds: stamps that stay right when the app is late, exact drop counts, no decode delay or jitter before the stamp, JPEG bytes, 1–2% CPU, and the path to PTS/SCR at tier 1. (measured, REPORT.md; inferred for the combination) |

## 6. Files and reproduction

Scratchpad root: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad`

- Sources: `.../scratchpad/opencv_src/` (OpenCV 4.12.0 videoio files, fetched from raw.githubusercontent.com).
- Harnesses: `.../scratchpad/opencv_scripts/`:
  - `dshow_timing.py` and `msmf_timing.py` (camera, one worker thread, watchdog exit 5);
  - `run_dshow_c930e.sh`, `run_msmf_c930e.sh` and `run_msmf_c930e_rawfirst.sh` (set C930e `auto_exposure_priority` 0, run, then restore 1 and exposure −7 manual);
  - `fit_stamps.py`, `posmsec_stats.py`, `jpeg_decode_bench.py` and `nv12_bench.py` (no camera).
- Results: `.../scratchpad/opencv_results/`:
  - `dshow_c930e_run1/` (AE priority 1, 16 fps), `dshow_c930e_aep0/`, `msmf_c930e/{hwT0,hwT_default}/` and `msmf_c930e_rawfirst/hwT0_rawfirst/`, each with `summary.json`, `frames_*.jsonl` and the wincam controls before/set/restore/after;
  - `fit_stamps.json`, and `decode_bench/{decode_bench.json,nv12_bench.json}`.
- Reproduce, from `research/usb_cameras`:
  - `uv run --script tools/camlock.py -- "C:/Program Files/Git/bin/bash.exe" <scratchpad>/opencv_scripts/run_dshow_c930e.sh <name>` (the DS index for the C930e was 3, from `wincam list`; MF index 0).
  - Then `python -I <scratchpad>/opencv_scripts/fit_stamps.py suite <scratchpad>/opencv_results`.
- **Side effects.**
  - The C930e's `auto_exposure_priority` was set to 0 for the runs and restored to 1.
  - Its exposure read −5 after each streaming run, from −7 before; it was set back to −7 manual. `controls_after.json` matches the state before the runs. This is consistent with REPORT.md's note that C930e manual exposure is unreliable; the cause was not investigated.
  - No registry, driver or device-state changes. Other cameras were not opened.
