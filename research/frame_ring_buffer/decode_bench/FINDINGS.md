# MJPEG decode to BGR24 benchmark (2026-11-18)

Machine: Intel Core i7-14700K (28 logical cores), Windows 11, Python 3.13.18. Overall CPU load before the run: 9.8 percent (5 s sample). Nothing else was run on purpose.
Packages (exact): numpy 2.5.5, opencv-contrib-python 5.1.0.95 (reports 5.1.0; the native-jpeg pyproject pins this, not 5.0.0), av 19.0.2, PyTurboJPEG 2.6.1, simplejpeg 1.9.0, pillow 13.0.0, psutil 7.2.2.
OpenCV is built with `build-libjpeg-turbo (ver 3.1.2-70)`, SIMD yes, so it already is libjpeg-turbo.
The libjpeg-turbo 3.x DLL for PyTurboJPEG came from the pip wheel `gstreamer-libs` 1.28.8 (cached, `bin/turbojpeg.dll`). The DLL in `pupil_labs_uvc` is 2.x and PyTurboJPEG 2.6.1 refuses it.

## Frames

Source: the local untracked sample frames in `research/frame_ring_buffer/jpeg_bound/frames/` (real camera JPEGs, read in place, not copied). Decoded from bytes in memory.

| Resolution | Frames | Cameras | Chroma | Bytes |
|---|---|---|---|---|
| 1280x720 | 8 | C922, C930e, generic: 4:2:2 (6 frames). Kiyo Pro: 4:2:0 (2 frames) | mixed | 74,922 to 276,269 |
| 1920x1080 | 6 | C922, C930e: 4:2:2 (4 frames). Kiyo Pro: 4:2:0 (2 frames) | mixed | 144,378 to 386,468 |

Two 1920x1080 generic frames were dropped: simplejpeg rejects them (extra bytes before EOI). cv2, turbojpeg and PyAV decode them with a warning. Per-frame names and sizes are in `results.json`.

## Method

400 timed decodes per decoder per resolution, cycling the frames, after 40 warm-up decodes. One thread, one process. Time includes the BGR conversion. Each output was checked for shape (h, w, 3) uint8 and compared with cv2 (mean absolute difference, max over frames, in `results.json`). Script: `bench.py`.

## Single process, ms per frame (median / p95 / p99 / max), frames/s per core

| Decoder | 1280x720 ms | fps | 1920x1080 ms | fps | Diff vs cv2 |
|---|---|---|---|---|---|
| cv2.imdecode, 1 thread | 2.60 / 3.39 / 3.51 / 3.63 | 370 | 5.42 / 6.12 / 6.42 / 7.42 | 184 | 0 |
| cv2.imdecode, default threads | 2.64 / 3.42 / 3.55 / 3.80 | 365 | 5.42 / 6.09 / 6.23 / 8.06 | 185 | 0 |
| turbojpeg BGR | 2.11 / 2.95 / 3.09 / 3.28 | 453 | 4.17 / 4.83 / 4.98 / 5.47 | 242 | 0 |
| turbojpeg BGR FASTDCT+FASTUPSAMPLE | 1.90 / 2.74 / 3.03 / 3.22 | 497 | 3.65 / 4.30 / 4.51 / 4.59 | 275 | 1.0 to 1.3 |
| turbojpeg FASTDCT only | 2.03 / 2.86 / 2.99 / 3.12 | 468 | 3.96 / 4.67 / 4.82 / 5.73 | 254 | 1.0 |
| turbojpeg FASTUPSAMPLE only | 1.99 / 2.83 / 2.90 / 3.31 | 482 | 3.93 / 4.53 / 4.69 / 5.39 | 258 | 0.1 to 0.7 |
| turbojpeg decode to YUV only | 1.77 / 2.62 / 2.71 / 3.33 | 539 | 3.42 / 4.12 / 4.48 / 5.47 | 294 | n/a |
| simplejpeg BGR | 2.10 / 2.89 / 2.92 / 3.42 | 455 | 4.15 / 4.84 / 5.02 / 5.52 | 242 | 0 |
| simplejpeg BGR fast flags | 1.87 / 2.65 / 2.70 / 2.73 | 510 | 3.78 / 4.87 / 5.65 / 5.88 | 260 | 1.0 to 1.3 |
| PyAV mjpeg + to_ndarray bgr24 | 2.49 / 5.17 / 5.45 / 5.68 | 330 | 4.43 / 7.65 / 8.05 / 8.28 | 198 | 0.7 to 1.1 |
| PyAV mjpeg, decode only (YUV frame) | 1.95 / 3.15 / 3.28 / 3.54 | 473 | 3.78 / 5.32 / 5.46 / 6.33 | 258 | n/a |
| Pillow RGB then flip to BGR | 6.74 / 7.72 / 8.15 / 9.46 | 147 | 14.43 / 15.68 / 16.18 / 16.38 | 69 | 0 |

Notes: the non-zero diffs come from fast flags (a coarser upsampling) and from swscale colour conversion in PyAV. Diffs of about 1 grey level are small but not bit-exact. cv2 with 1 thread and default threads are the same, so cv2 does not parallelise one JPEG decode.

## 8 processes decoding at once (spawn, barrier start, one decoder each, single thread)

Per-process median ms, then p99 (median over the 8 processes, and the worst process), ms.

| Decoder | 1280x720 median | p99 med / worst | 1920x1080 median | p99 med / worst |
|---|---|---|---|---|
| cv2 1 thread | 3.17 | 5.21 / 5.70 | 7.11 | 10.38 / 10.93 |
| turbojpeg | 2.32 | 4.16 / 4.22 | 4.47 | 7.03 / 7.48 |
| turbojpeg fast flags | 2.10 | 3.53 / 3.82 | 4.05 | 5.87 / 5.96 |
| simplejpeg fast flags | 2.27 | 3.85 / 4.19 | 3.88 | 5.66 / 5.83 |

With 8 processes each decode is 10 to 30 percent slower than alone (shared cache, clocks), still well under a 33 ms frame.

## Intel QSV (PyAV mjpeg_qsv)

PyAV 19.0.2 lists `mjpeg_qsv`, `mjpeg_cuvid` and the hwdevices cuda, dxva2, qsv, d3d11va, d3d12va, amf.
`CodecContext.create("mjpeg_qsv", "r", hwaccel=HWAccel(device_type="qsv"))` works: nv12 frames, 300 frames out per 300 in, to_ndarray(bgr24) gives the right shape. Creating `mjpeg_qsv` without a hwaccel object was not used. `mjpeg` with hwaccel d3d11va or qsv silently falls back to software (yuvj422p output), so it is not hardware.
Script `qsv_bench.py`, file `qsv_bench.json`, one process, includes download to system memory and nv12 to BGR:

| Resolution | median / p95 / p99 / max ms | fps |
|---|---|---|
| 1280x720 | 3.20 / 3.65 / 4.33 / 4.53 | 307 |
| 1920x1080 | 5.87 / 6.34 / 6.82 / 7.06 | 169 |

QSV is slower than CPU libjpeg-turbo at both sizes (about 1.5x slower than turbojpeg), and the swscale BGR conversion is on the CPU. It is not worth it for this stage. Not measured: QSV with 8 processes (several QSV sessions on one iGPU).

## Not verified

- That the QSV work really ran on the iGPU (no GPU-engine counter read), only that the QSV decoder path ran.
- Quality against a reference other than cv2 (no pixel-exact check of fast flags beyond the mean difference).
- Other CPUs, other turbojpeg builds (OpenCV bundles 3.1.2; the gstreamer-libs DLL version was not printed).
