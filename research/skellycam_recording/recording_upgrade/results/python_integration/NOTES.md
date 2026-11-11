# python_integration - how the recording upgrades fit the Python implementation (G1-G9)

2026-11-09, Gerald (Windows 11, i7-14700K, RTX 3070, driver 610.88). Functional tests only: no timing, throughput or CPU number from this stage is reported, because other agents shared the machine. Timing questions are covered by the benchmark scripts in section 9 (bench manifest).

Labels:
- **measured**: a result file, either written in this study (path given) or a prior study's result file.
- **source**: a primary source (library source at a pinned tag, a changelog), accessed 2026-11-09.
- **code**: repo source, as file:line.
- **inferred**: reasoning, kept short.

Paths: `skellycam/...` = this repo at `dom/research` @ `55f851e4` (no changes under `skellycam/`). `sfn26:` = `git show upstream/sfn26:<path>` @ `765bf82d`. `fmc:` = `C:/Users/Dom/GitHub/freemocap/freemocap`, checked out on `development` @ `5632778a`; `fmc-sfn26:` = `upstream/sfn26` @ `3ae9842d` of that repo. `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`. `S/` = `research/skellycam_recording/recording_upgrade/scripts/python_integration/`. Media went to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/python_integration/` and never into the repo.

## 0. Bottom line

1. **The camera's JPEG bytes have no way into today's recorder.** OpenCV `retrieve()` decodes into the shared frame array, and the recorder encodes from that array. Raw JPEG needs a new capture backend whose `read()` returns the bytes. code + measured (§1)
2. **The prototype `RecordingWriter(jpeg_bytes, frame_number, timestamp_ns)` works.** On every MJPEG corpus set (7 sets, 1,862 real frames) it round-trips the camera JPEGs byte-exact through MKV, fragmented MP4 and AVI. Sidecar timestamps come back exact to the nanosecond, and container PTS equal sidecar PTS on every frame. measured: `R/roundtrip.md`
3. **For FreeMoCap the video file must be CFR, with the real timestamps kept in a sidecar.**
   - With PTS = frame index / fps, OpenCV 4.12 (the pin) and 5.0.0.93 return an exact `CAP_PROP_FRAME_COUNT`, an exact sequential order and exact `CAP_PROP_POS_FRAMES` seeks for every codec/container tested (MJPEG, FFV1, VP9, AV1, H.264 in MKV, WebM, MP4 and AVI).
   - With real (VFR) PTS, OpenCV's count is wrong for MKV (888 for 891 real frames) and its seeks land 1-2 frames off in MKV and MP4.
   - measured: `R/cv2_read_probe_*.json`, `R/roundtrip.md`; mechanism: source, OpenCV `cap_ffmpeg_impl.hpp`
4. **Only MKV gives a recoverable file without help after a hard kill.**
   - Its demuxer drops the torn last block, so every packet it returns is a whole frame.
   - fMP4 and AVI return a torn last JPEG, which PyAV and cv2 decode **without any corrupt flag**.
   - In every case, a killed MKV or AVI reports a garbage or zero `CAP_PROP_FRAME_COUNT` until a remux. FreeMoCap reads the count through `CAP_PROP_FRAME_COUNT`, so it would get that garbage until recovery runs.
   - The sidecar CRC finds the torn frame. `recover()` (startup scan plus remux of the matched prefix) restores a correct count.
   - measured: `R/crash.md`
5. **FFmpeg's Matroska muxer fixes timestamps at 1 ms.** One real C930e frame pair arrived 0.118 ms apart and had to be bumped by 1 tick. MP4 keeps the 1/1,000,000 time base it is given. Either way, exact ns times need the sidecar. source + measured
6. **The PyAV 18.0.0 → 19.0.2 bump changes no codec availability in the list tested.** The bundled FFmpeg goes from 8.1.2 to 9.0.2. The recorder code runs unchanged, but `time_base` now returns `av.AVRational` instead of `Fraction`. It also stops holding the GIL during header/trailer writes. measured + source (§7)
7. **Decode cost for the live UI on real camera JPEGs is not measured yet.** The prior p8 numbers used synthetic ~540 KB JPEGs under a 5-camera load, so a benchmark is listed. One functional result: simplejpeg's default `strict=True` rejects every generic-camera frame, while cv2 and PyTurboJPEG accept them. measured (§3)

## 1. Today's Python recording path (what has to change)

| Step | Where | What it does today | Change for G1/G2/G3/G9 |
|---|---|---|---|
| Capture | `skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py:53-73` | `grab()` and `retrieve(image=frame_rec_array.image[0])`, stamped with `perf_counter_ns` | New backend `read() -> (jpeg_bytes, sample_time, arrival_ns, flags)` (timestamps doc §6.2). OpenCV 4.12 never returns JPEG bytes (measured, `research/usb_cameras/docs/mjpeg_passthrough_summary.md` "Results matrix") |
| Overlay | `opencv_get_frame.py:79-84` | `putText` into the same array that is recorded | Drop it. Send the frame number and camera id as data (G3). The JPEG path cannot burn in anyway (inferred) |
| Lockstep gate | `opencv_camera_loop.py:67-69`, `camera_orchestrator.py:96-109` | grab only when every camera's count is >= this one's | Unchanged by recording. The writes leave the loop (row "Write") |
| Record decision | `opencv_camera_loop.py:89-91`, `camera_orchestrator.py:80-94` | frame-number window `[first, last)` | Unchanged |
| Shared memory | `opencv_camera_loop.py:95-97`; dtype `skellycam/core/types/frame_dtype_factories.py:16-26` | fixed-shape pixel array plus metadata | Pixels still needed by the UI and FreeMoCap realtime: decode at source into the slot (§3). Raw bytes are variable-size and do not fit this dtype (code) |
| Write | `handle_video_recording_loop.py:78-83` → `video_recorder.py:87-109` (`video_writer.write(image)` at :102) | synchronous encode in the camera loop. Lockstep makes every camera wait for the slowest write (REPORT §3.2) | `RecorderThread.submit(jpeg_bytes, frame_number, ts_ns)`: an enqueue. Container mux and sidecar on a thread in the camera process (§4) |
| Per-frame metadata | `video_recorder.py:108` appends to a list; sent at stop in one `RecordingFinishedMessage` (`handle_recording_updates.py:50-57`) | R9: ~694 B/frame pickled at stop | Sidecar record appended and flushed per frame (§5) |
| Writer setup | `handle_recording_updates.py:39-43`, `video_recorder.py:42-85` | codec probe per start; CFR rate = pre-recording median estimate (`opencv_camera_loop.py:80-84`) | Writer opens a container. No probe. The nominal rate is the negotiated mode rate |
| Finalize | `camera_group.py:317-379` → `recording_finalizer.py:53-67` | waits for all messages, writes CSVs/JSON on the event loop, validates | Build CSVs from the sidecars, off the loop (`asyncio.to_thread`, REPORT §10.2). Run `find_unfinished()` at startup (§6) |
| Playback serve | `skellycam/api/http/playback/playback_router.py:397-437` (`FileResponse`, range requests), `_ensure_web_compatible` :115-139 | serves the file, transcoding non-web codecs to `.web.mp4` | MJPEG is not playable in Chromium (measured by the concurrent chromium_codecs topic, `results/chromium_codecs/tables.md` rows `mjpeg_camera__*`: `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` / `COULD_NOT_OPEN`). A proxy or JS decode path is needed (UI topics) |
| Timestamps for UI | `playback_router.py:253-298` picks the **first** CSV column whose name contains `timestamp`/`time`/`elapsed`/`seconds` | | Serve the sidecar-derived times explicitly |
| UI player | `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:332-335` (seek = frame/fps), `:377-378` (frame = leader.currentTime × fps), `:101,:420-425` (followers re-seeked when >2 frames off); per-camera timestamps only label frames (`:291-299`) | Assumes CFR files with equal frame counts | A CFR file plus a sidecar keeps this model working (inferred). Identical on sfn26 (`git diff --stat` of `components/playback` and `PlaybackContext.tsx` is empty) |

**upstream/sfn26.**
- **Python path.**
  - Same recorder model: the default backend, the burned-in overlay and the CFR fast header are unchanged (REPORT §11, verified statically by the upstream check).
  - The playback router serves files as-is (`sfn26:skellycam/api/http/playback/playback_router.py:233-277`, `serve_path = video_path`).
  - New readers:
    - `sfn26:skellycam/core/recorders/videos/video_file_metadata.py:21-42` rejects a non-finite, non-integer or <1 `CAP_PROP_FRAME_COUNT`. A killed, unrecovered MKV (count −2.77e17 in `R/crash.md`) would raise "Invalid reported video frame count" (inferred from code + measured value).
    - `sfn26:.../sequential_video_reader.py:16-53` decodes frame-indexed with PyAV and raises on `is_corrupt`. That check would not catch the torn fMP4/AVI tail, which decodes unflagged (measured, `R/crash.md`).
  - `sfn26:.../browser_stream.py:44-108` (pull-driven H.264 fMP4 fragments for the browser) is used only by tests (`git grep` finds callers only in `skellycam/tests/`).
- **Rust backend** (opt-in), the design the Python prototype mirrors:
  - **JPEG entry:** the camera thread hands JPEG bytes to the dispatcher. It rotates them losslessly (`sfn26:skellycam-rust/src/camera_group/dispatcher.rs:197-214`; `jpeg_transform.rs:1-5` "no decode to pixels"), wraps them once in `Arc<[u8]>` shared by frontend and recording (`dispatcher.rs:216-221`), and sends them to the recording thread with `grab_timestamp_ns: frame.timestamps.frame_available_ns` (`dispatcher.rs:298-321`).
  - **Recording thread:** an unbounded channel "so the dispatcher never blocks on ffmpeg pipe writes" (`recording_thread.rs:1-6`, `:96-101`). It calls `feed_frame` and then `write_row` per camera (`:284-311`).
  - **Encode:** `feed_frame` writes the JPEG to ffmpeg stdin for a libx264 re-encode, CFR at the negotiated rate (`recorder.rs:137-155`, `:199-222`; rate from `dispatcher.rs:380-390`). So it is not transcode-less.
  - **Timestamps:** the native CSV is written and flushed per row (`timestamps/csv_writer.rs:53-75`). Python maps its columns onto the old dtype at stop (`sfn26:skellycam/core/camera_group/rust_recording.py:32-44`).
  - **Frontend:** gets the camera JPEGs packed in the same wire format as Python (`frontend_encoder.rs:1-10`). The pyo3 bridge exposes the raw per-camera JPEGs plus timestamps to Python (`pyo3_bridge/py_camera_group_manager.rs:128-167`).

## 2. Where raw JPEG enters, and what "record packets" changes

- **Entry point.** In the camera loop, between the frame read (`opencv_camera_loop.py:74`) and `put_frame` (`:96`). The new backend returns bytes plus stamps. The loop then:
  - decodes into the shm slot for consumers (§3);
  - calls `recorder.submit(jpeg, frame_number, ts_ns)` where `handle_video_recording` is called today (`:99-105`).
  - (code for the locations; design inferred)
- **What changes in the recorder** (prototype `S/recwriter.py`):
  - **Input:** `bytes`, not an image. There is no rotation by `cv2.rotate` (`video_recorder.py:92-98`); use a lossless DCT transform, as Rust does.
  - **Validation:** no image-shape validation per frame (`video_recorder.py:141-147`). Width and height are fixed at writer open. A mode change needs a new file (inferred).
  - **Muxing:** `av.Packet(jpeg_bytes)` with `pts=dts`, `is_keyframe=True`, muxed into a stream created with `add_stream("mjpeg")` plus width, height and `pix_fmt="yuvj422p"`. No encoder is opened (code `S/recwriter.py`, class `RecordingWriter.write`).
  - **Frame gaps:** frame-number gaps are recorded as a flag, not raised (`FLAG_FRAME_GAP`). The test flagged index 10 of 60 as expected (measured, `R/roundtrip.json` `gap_test`). Today a gap raises (`video_recorder.py:149-156`).
  - **GIL:** PyAV releases the GIL around `av_interleaved_write_frame` (source: PyAV 18.0.0 `av/container/output.py:627-628`, installed in the venv: `with cython.nogil: ret = lib.av_interleaved_write_frame(...)`).
- **Byte-exactness** (measured, `R/roundtrip.md`):

| Container | PTS mode | Sets × frames | Byte-exact | Container time base | cv2 4.12 FRAME_COUNT (real camera bytes, c930e 891 frames) |
|---|---|---|---|---|---|
| MKV | real (VFR) | 7 sets, 1,862 frames | all | 1/1000 (forced) | 888 (wrong) |
| MKV | index (CFR) | 7 / 1,862 | all | 1/1000 | 891 |
| fMP4 (`frag_keyframe+empty_moov+default_base_moof`) | real | 7 / 1,862 | all | 1/1,000,000 (kept) | 891 |
| AVI | real | 7 / 1,862 | all | 1/600 (muxer pads with empty chunks) | 17,761 (FPS prop 600) |
| AVI | index | 7 / 1,862 | all | 1/fps | 891 |

- **MKV timestamp resolution** (source, FFmpeg n8.1.2 `libavformat/matroskaenc.c`, the version PyAV 18.0.0 bundles):
  - :2593 `put_ebml_uint(pb, MATROSKA_ID_TIMECODESCALE, 1000000);`
  - :3533-3534 `// ms precision is the de-facto standard timescale for mkv files` / `avpriv_set_pts_info(st, 64, 1, 1000);`
  - Measured consequence: in the real C930e capture, frames arrived 0.118 ms apart, so one PTS had to be bumped by 1 ms (`pts_adjusted_frames: 1`, `R/roundtrip.md`). The sidecar keeps the exact ns value.
- **Container overhead per frame** (measured, `R/roundtrip.md`): MKV 45 B, fMP4 132 B, AVI CFR 31 B at 720p. Real-PTS AVI costs 485 B because of the padding.

## 3. The live UI and FreeMoCap still need decoded frames

- **What exists today.** Each camera's BGR frame goes into shm. The UI relay resizes it and re-encodes it to JPEG (`skellycam/core/types/frontend_payload_bytearray.py:137-147`). (code)
- **With camera JPEGs there are three options** (prior measurements, `research/frame_ring_buffer/prototypes/results/p6_ui_path.md` and `p8_e2e_summary.md`, synthetic q90 JPEGs; the p6 footnote says real camera JPEGs are ~160-167 KB vs ~540 KB synthetic at 1080p):

| Option | Prior evidence (measured, p6/p8) | Note |
|---|---|---|
| Forward camera JPEG bytes to the UI, no decode | p6 `jpeg_forward`: build 0.25 ms median (1080p), 0.13 ms (720p), payload 2,685 / 1,195 KB synthetic | Full-resolution payload. The real-camera size is in the corpus index (57-192 KB/frame) |
| Reduced decode plus re-encode on threads | p6 `jpeg_reduced_reencode_threads`: event-loop block 0.04 / 0.03 ms median, build 5.91 / 3.03 ms (1080p / 720p) | Uses the decoder's DCT scaling |
| Decode at source into the shm slot (Design A, timestamps doc §6.2) | p8 decode median: cv2.imdecode 9.09 ms, simplejpeg 5.82 ms at 1080p; imdecode 3.37 ms at 720p (5 cameras, 60 fps, synthetic) | Keeps shm, FreeMoCap realtime and the recorder unchanged. In p8 `imdecode_off_passthrough` (decode on a separate thread, passthrough recorder) tick→written was 0.8 ms median, 1.5 ms p99 at 1080p |

- **Missing numbers.** Decode cost on the real camera JPEGs, per library, at 720p and 1080p. The bench is `S/bench_jpeg_decode.py` (CPU: cv2, simplejpeg, PyTurboJPEG, PyAV) plus `S/bench_nvjpeg_decode.py` (nvJPEG through NVIDIA nvImageCodec). Both are smoke-tested; numbers are deliberately not reported.
- **Functional results from the smoke runs** (measured, `R/bench/jpeg_decode_smoke.json`, `R/bench/nvjpeg_decode_smoke.json`; not timing):
  - All methods decode all 5 sets with these exceptions: simplejpeg 1.9.0 with its default `strict=True` raises `ValueError('Corrupt JPEG data: 534 extraneous bytes before marker 0xd9')` on generic_1080p. With `strict=False` it decodes. cv2 4.12 decodes these frames, and PyTurboJPEG 2.6.1 + libjpeg-turbo 3.2.0 decodes them with a warning.
  - cv2.imdecode, simplejpeg (default DCT) and PyTurboJPEG give **identical** BGR (max abs diff 0 vs cv2) on the first frame of every set.
  - simplejpeg `fastdct+fastupsample` differs by up to 26.
  - PyAV's libavcodec mjpeg → bgr24 differs by up to 24 (different IDCT/upsampling/colour conversion path; not investigated).
  - simplejpeg can decode straight into a preallocated array (`buffer=`), which suits a shm slot. Smoke-tested.
  - nvImageCodec 0.9.0.20 decodes all 5 sets to 1080×1920×3 / 720×1280×3 on the RTX 3070.
  - The nvImageCodec env failed to import from the long scratchpad uv-cache path: `ImportError: DLL load failed while importing nvimgcodec_impl: The filename or extension is too long`. It worked from a short cache path.
- **Lenient decode needed.** The generic camera's frames need a decoder that tolerates extra bytes before EOI, so simplejpeg must be called with `strict=False` (measured above). This matches the strict/lenient finding in `mjpeg_passthrough_summary.md` (footnote under "Results matrix").

## 4. Threading model: writes out of the lockstep loop

**Prior evidence** (measured):
- A decoupled recorder behind a ring loses nothing with the drop or block policy. The overwrite policy silently loses frames once a stall exceeds the ring (`p3_lossless_record.md` table A). With the real cv2 MSMF encoder as a decoupled recorder, 6,005 / 6,005 frames were recorded through a 1.5 s stall (`p3` table B).
- MJPEG passthrough recorder at 5×1080p60: recorder CPU 0.95 ms/frame, tick→written 0.8 / 1.8 ms. Decode + MSMF re-encode: 32.1 ms/frame, 10.8 / 15.0 ms (`p4_mjpeg_passthrough.md`).
- Disk: 5×1080p passthrough is 162 MB/s. With buffered writes and `FlushFileBuffers` at stop, the worst write was 3.4 ms. Unbuffered write-through had 5 writes >100 ms (`p12_disk_sustained.md`).
- Rust uses the same shape: an unbounded channel to a recording thread (`recording_thread.rs:1-6`, `:96-101`). It is unbounded, so the queue can grow without limit (upstream check, `rust_recording_overview.md` §8).

**Prototype:** `RecorderThread` (`S/recwriter.py`), one per camera, inside the camera process:
- `submit()` is `queue.put_nowait((bytes, fn, ts))`. A `bytes` object is immutable, so the enqueue passes a reference and makes no copy. If the backend hands out a view into a reusable buffer, it must be copied to `bytes` first. (inferred, Python semantics)
- Bounded queue (default 256). The policy is `drop` (counted, explicit) or `block` (back-pressure, which p3 showed stalls the sensor instead).
- The thread writes the container and sidecar. Errors are stored and draining continues, so the producer never deadlocks.
- `stop()` drains, closes, and reports `dropped` and `max_queue_depth`.
- Smoke run (`S/bench_recwriter.py --quick`, phase B, 5 cameras paced at 30 and 60 fps): 0 drops, every file byte-exact afterwards (`R/bench/recwriter_smoke.json`). Timing is not reported.

**Why a thread is enough** (inferred): the writer's per-frame work is a mux call that releases the GIL (§2) plus a 48-byte sidecar write. Running the thread in the camera process avoids moving variable-size JPEGs across processes. The per-call cost and its tail are what the bench measures.

## 5. Per-frame PTS and streaming timestamps

**Where the time comes from:**
- **Today:** the midpoint of the `grab()` stamps (`create_camera_csvs.py:50-51`). On OpenCV DirectShow this stamp is not tied to frame arrival (`skellycam_timestamps_review.md` §1, P1-P3).
- **Recommended:** MF arrival or sample time, raw per frame, plus an offline lattice fit "run at finalisation" (`timestamp_accuracy_options.md` §6.2, §7.2 step 2).
- **Rust:** `frame_available_ns` (`dispatcher.rs:315`).

**Consequence for the file** (inferred from the above + §8 measurements):
- The live writer only has the raw stamp.
- The best time (fitted) exists only after the recording.
- FreeMoCap needs CFR to count and seek correctly (§8).
- So: write **CFR PTS (index/fps)** into the container, the **raw ns stamp** into the sidecar per frame, and add **fitted times at finalize**, in the CSV or a second sidecar column.
- `pts_mode="real"` remains available for consumers that want true timing in the file (fMP4 keeps µs; MKV ms).

**Sidecar format** (`S/recwriter.py`):
- A 64-byte header: magic `SKCAMFR1`, version, width/height, fourcc, container time base, t0_ns.
- 48-byte records: frame_number, timestamp_ns, pts, size, CRC32 of the JPEG, flags, write_index, CRC32 of the record.
- Appended and flushed after every frame, plus a CSV mirror flushed per row.
- `fsync_every=N` is optional and its cost goes in the bench. Without fsync, a power loss can lose OS-cached rows, the same limit as the Rust CSV (`csv_writer.rs:72`; upstream check).
- What the round trip showed (measured, `R/roundtrip.md`): sidecar timestamps equal the input on every frame of every set, and container PTS equal sidecar PTS everywhere. With real PTS, |PTS − (t − t0)| ≤ half a tick on every non-adjusted frame (MKV max 0.497 ms; fMP4 max 0.5 µs).

**Replaces R9.** Nothing large is sent at stop. The finalizer reads the sidecars, so a kill-flag ending still leaves timestamps on disk (inferred; the kill test shows the sidecar survives TerminateProcess with 0 torn bytes, `R/crash.md`).

## 6. Recovery on startup

- **Manifest.** `S.recording.json` is written atomically (`os.replace`). It says `"state": "recording"` while open and `"closed"` after `close()`.
- **Scan.** `find_unfinished(folder)` lists stems still in `recording`. It found every killed stem in the kill test (measured, `R/crash.md` column `find_unfinished_lists_it`).
- **`recover(stem)`** compares container packets with sidecar records by index (size, CRC32, PTS). It remuxes the matched prefix into `S.recovered.<ext>`, so the file gets an index and a duration, then marks the manifest `recovered`.

Hard kill of the writer process (TerminateProcess after ≥300 sidecar records; measured, `R/crash.md` part A):

| Container / PTS | Sidecar records (valid, torn bytes) | Killed file: packets / cv2 FRAME_COUNT / cv2 frames read | Torn last packet returned? | After `recover()`: matched / cv2 FRAME_COUNT / read |
|---|---|---|---|---|
| MKV real | 300, 0 | 297 / **−2.77e17** / 297 | no | 297 / 297 / 297 |
| MKV index | 300, 0 | 297 / **−2.77e17** / 297 | no | 297 / 297 / 297 |
| fMP4 real | 300, 0 | 298 / 298 / 298 | **yes**: packet 297 is 22,582 B of 82,954, decoded unflagged | 297 / 297 / 297 |
| AVI index | 301, 0 | 301 / **0** / 301 | **yes**: packet 300 is 68,228 B of 75,691 | 300 / 300 / 300 |

Truncated copies of a closed 300-frame file (measured, `R/crash.md` part B):
- **MKV:** every returned packet is byte-exact. The 50% cut gives 149, 90% gives 270, 99.9% gives 299, −1 byte gives 300. cv2 still reports 300 from the header Duration while reading fewer frames.
- **fMP4 and AVI:** the last returned packet is a partial JPEG at the 50%, 90% and 99.9% cuts. Neither PyAV (`is_corrupt` 0) nor cv2 notices. This confirms the timestamps doc §5.4 "Corrupt frames pass silently" on real camera bytes.
- **Comparison with p11:** p11 `mjpeg_mkv` killed: 298 of 300, or 359 when killed mid-write (`p11_crash_container.md`).
- **Why up to 3 frames are lost in MKV** (source, matroskaenc.c n8.1.2): a cluster is buffered until the next one starts. A new cluster starts on a video keyframe once the current one exceeds 4 KB (:3160-3165, `cluster_size > 4 * 1024`), and every JPEG is a keyframe larger than 4 KB. So the last frame waits in memory for the next one, and whatever sits in the AVIO buffer is lost too. The sidecar, written after `mux()`, is therefore always ≥ the container. That is why recovery matches by prefix (inferred from source + measured 300 vs 297).

## 7. PyAV 19.0.2 vs 18.0.0 (version bump allowed)

| Item | 18.0.0 (venv) | 19.0.2 (uv, isolated) | Evidence |
|---|---|---|---|
| Bundled FFmpeg | 8.1.2 (libavcodec 62.28.102) | 9.0.2 (libavcodec 63.1.102) | measured `av.ffmpeg_version_info`, `R/pyav_version_probe_*.json` |
| Encoders/decoders in the tested list (45 names: mjpeg, ffv1, libsvtav1, libdav1d, av1/vp9/h264/hevc nvenc/qsv/amf/mf, libvpx-vp9, libx264, prores_ks, dnxhd, utvideo, jpeg2000, png, opus, flac, ...) | | **no difference** | measured, same files |
| Not in either wheel | libaom-av1, librav1e, libopenh264, libjxl, libopenjpeg | same | measured |
| recwriter round trip (mkv/mp4f/avi, real/index) | byte-exact | byte-exact, unchanged code | measured |
| `Stream.time_base` type | `Fraction` | `av.AVRational` ("Rational attributes ... now return av.AVRational rather than fractions.Fraction, and are never None", CHANGELOG v19.0.0 Major) | source + measured (type printed) |
| GIL during header/trailer/close | held | released ("avio_open(), avformat_write_header(), av_write_trailer(), and avio_closep() held the GIL", CHANGELOG v19.0.0 Fixes) | source |
| Closed OutputContainer | still usable | raises "Container is not open" (v19.0.0 Major) | source |
| `stream_options` arg to `av.open` | exists | removed (v19.0.0 Major) | source. skellycam's `pyav_video_writer.py:14-28` does not use it (code) |
| `VideoFrame.reformat` SwsContext | per frame | one per thread, which fixes RSS growth with FFmpeg 8 (v19.0.0 Fixes) | source |
| 18.1.0 (between) | | `Packet.rescale_ts()`, `av.AVRational` introduced, frame-rate-after-add_stream fix (CHANGELOG v18.1.0) | source |
| Compat clips decode (15 clips) | all, except av1svt_mp4_vfr = 119/120 | identical counts | measured |

- **Sources:** `https://raw.githubusercontent.com/PyAV-Org/PyAV/v19.0.2/CHANGELOG.rst` and `.../v18.1.0/CHANGELOG.rst`, accessed 2026-11-09. Copies are in the scratchpad, not the repo.
- **Constraints:** sfn26 already requires `av>=18.1.0` (`sfn26:pyproject.toml:68`), and this repo pins `av>=12.0.0` (`pyproject.toml:68`). PyAV 19 requires Python ≥3.12 (PyPI `requires_python`).
- **Verdict** (inferred): no format-support reason to bump PyAV for this recorder. The GIL release on close is a small plus for a threaded recorder. The `AVRational` change needs care only where code compares `time_base` with `None`.

## 8. FreeMoCap compatibility

**How FreeMoCap reads `synchronized_videos`** (code):
- **File list:** files are listed by `VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}`. This set is imported from skellycam `parse_video_filename.py:18` (`fmc:freemocap/core/pipeline/posthoc/video_group_helper.py:15`) and re-declared in `fmc:freemocap/api/http/playback/playback_router.py:47` and `fmc:freemocap/system/recording_status/recording_status.py:19`. On fmc-sfn26 it comes from skellycam's `video_filename` module (`video_group_helper.py:13`), because sfn26 skellycam deleted `parse_video_filename.py`.
- **Opening and counts:**
  - `VideoHelper` opens with `cv2.VideoCapture(path)` and takes `CAP_PROP_FRAME_COUNT` and `CAP_PROP_FPS` (`fmc:.../video_group_helper.py:151-166`).
  - It reads sequentially and bounds every read by that count (`:195-214`).
  - It **raises when counts differ across cameras** (`:381-392`).
- **Posthoc:** `VideoNode` uses `cv2.VideoCapture(path, cv2.CAP_FFMPEG)` and the same count (`fmc:.../video_node.py:297-301`).
- **Seeking:** fmc-sfn26 also seeks with `CAP_PROP_POS_FRAMES` (`fmc-sfn26:freemocap/core/pipeline/dataflow/annotation_workers.py:56-57`).
- **What OpenCV does underneath** (source, OpenCV 4.12.0 `modules/videoio/src/cap_ffmpeg_impl.hpp`):
  - Frame count: `nbf = ic->streams[video_stream]->nb_frames; if (nbf == 0) nbf = floor(get_duration_sec() * get_fps() + 0.5)` (:1980-1989).
  - FPS is `avg_frame_rate` (:1957-1960).
  - Frame↔time is `fps * sec` (:1991-1995).
  - So VFR files get a duration×fps count and time-based seeks.

**OpenCV versions** (measured, from build info / `R/cv2_read_probe_*.json`):
- The venv has `opencv-contrib-python 4.12.0.88`; the pin is `opencv-contrib-python==4.12.*` (`pyproject.toml:55`).
- Its FFmpeg backend is avcodec 58.134.100 / avformat 58.76.100, i.e. FFmpeg 4.4 (`cv2.getBuildInformation()`).

**Compat clips** (`S/make_compat_clips.py`):
- 120 real C930e frames with a 16-bit frame-index barcode. Encoded by PyAV 18 at CFR 30 unless marked VFR. The VFR timing is jittered ±3 ms with one 2-frame gap after frame 60.
- Probe: `S/cv2_read_probe.py`. Each (clip, API) runs in a child process with a 180 s timeout.
- The table shows `CAP_ANY` and `CAP_FFMPEG` results. They were identical in 4.12; `CAP_ANY` picked the FFMPEG backend for every file.

**Versions:** OpenCV 4.12.0 (venv; FFmpeg 4.4 libs) vs opencv-python 5.0.0.93 (uv; `cv2.getBuildInformation()` shows avcodec 61.19.100 / avformat 61.7.100, i.e. FFmpeg 7.1). Results were **identical** in every field for every clip and API, CAP_MSMF included (measured, `R/cv2_compat_table.md` "Differences 4.12 -> 5.0.0.93: none"; raw data in `R/cv2_read_probe_cv2_4.12_venv.json` and `R/cv2_read_probe_cv2_5.0.0.93_uv.json`).

| Clip (120 frames unless noted) | Backend | FRAME_COUNT | FPS prop | Frames read | Order exact | POS_FRAMES seeks exact (11 targets incl. backward) |
|---|---|---|---|---|---|---|
| MJPEG-in-MKV, CFR | FFMPEG | 120 | 30 | 120 | yes | yes |
| MJPEG-in-MKV, VFR | FFMPEG | **122** | 30 | 120 | yes | **no** (119→117) |
| MJPEG-in-AVI, CFR | FFMPEG | 120 | 30 | 120 | yes | yes |
| MJPEG-in-fMP4, VFR | FFMPEG | 120 | 29.50 | 120 | yes | **no** (59→60, 61→62, 62→63, 77→78) |
| FFV1-in-MKV (level 3, slicecrc) | FFMPEG | 120 | 30 | 120 | yes | yes |
| FFV1-in-AVI | FFMPEG | 120 | 30 | 120 | yes | yes |
| VP9 GOP 30 in WebM / MKV / MP4 | FFMPEG | 120 | 30 | 120 | yes | yes |
| VP9 intra-only in WebM | FFMPEG | 120 | 30 | 120 | yes | yes |
| AV1 (SVT-AV1, GOP 30) in WebM / MKV / MP4 | FFMPEG | 120 | 30 | 120 | yes | yes |
| AV1 (SVT-AV1) in MP4, VFR | FFMPEG | 120 | 29.50 | **119** | **no** (starts at frame 1) | **no** |
| H.264 (libx264) in MP4, reference | FFMPEG | 120 | 30 | 120 | yes | yes |
| Camera bytes c930e 891 frames: MKV index PTS | FFMPEG | 891 | 30 | 891 | n/a | n/a |
| same, MKV real PTS | FFMPEG | **888** | 30 | 891 | n/a | n/a |
| same, fMP4 real PTS | FFMPEG | 891 | 30.10 | 891 | n/a | n/a |
| same, AVI index PTS | FFMPEG | 891 | 30 | 891 | n/a | n/a |
| same, AVI real PTS | FFMPEG | **17,761** | **600** | 891 | n/a | n/a |

**What this means for FreeMoCap** (inferred from the table and the code above):
- Every CFR file in the table opens, counts, orders and seeks correctly in both OpenCV versions. That covers MJPEG/FFV1/AVI/MKV, VP9 and AV1 in WebM/MKV/MP4.
- FreeMoCap's `.webm`/`.mkv` extension filter already admits them.
- VFR PTS break the count (MKV, AVI) or the seeks (MKV, MP4).
- Bumping OpenCV to 5.0.0.93 changes nothing here, so it gives no format reason to bump.

**Other results:**
- **AV1 on the GPU encoder:** `av1_nvenc` cannot open on the RTX 3070: `avcodec_open2("av1_nvenc") -> Generic error in an external library` (measured, `make_compat_clips` output; the clip was skipped). The gpu_encode topic covers why.
- **MSMF (`CAP_MSMF`)** is not used by FreeMoCap:
  - `CAP_PROP_POS_FRAMES` `set()` returns False on every file.
  - It read 0 frames from fMP4 and FFV1-AVI.
  - It hung more than 180 s on FFV1-MKV (killed).
  - It read 122 / 17,742 frames on VFR MKV / VFR AVI.
  - (measured, `R/cv2_read_probe_cv2_4.12_venv.json`)
- **Unexplained (NOT VERIFIED):** SVT-AV1 in MP4 with VFR PTS decodes 119 of 120 frames in PyAV 18, PyAV 19 and cv2 4.12, starting at barcode 1 (measured; cause not investigated).
- **Cross-topic note:** the concurrent jpeg_passthrough topic reports MP4/MOV as frame-exact under cv2 for VFR camera bytes (`results/jpeg_passthrough/NOTES.md` §0). Here VFR fMP4 seeks were off by one after frame ~59. This clip has a 2-frame gap (a simulated drop), and OpenCV seeks by k/avg_fps. Both results fit that mechanism (inferred).

## 9. Benchmarks written (not run for timing here)

Each script was smoke-tested with `--quick` (outputs `R/bench/*_smoke.json`; do not use their numbers). Full commands are in the bench manifest returned with this note.

| Script | Measures | Output |
|---|---|---|
| `S/bench_jpeg_decode.py` (uv, PEP 723 pins: opencv-python 4.12.0.88, simplejpeg 1.9.0, PyTurboJPEG 2.6.1, av 18.0.0, numpy 2.2.6) | per-call decode ms on real camera JPEGs, 5 sets (720p ×2, 1080p ×3): cv2 full and reduced/2, simplejpeg default, fast and min_h360, decode into buffer, PyTurboJPEG full and 1/2, PyAV bgr24 and native YUV; 1-thread and 5-thread aggregate rate | `R/bench/jpeg_decode_<tag>.json` |
| `S/bench_nvjpeg_decode.py` (uv: nvidia-nvimgcodec-cu12[all] 0.9.0.20) | nvJPEG decode to GPU, to host, batch of 5; nvidia-smi before/after | `R/bench/nvjpeg_decode_<tag>.json` |
| `S/bench_recwriter.py` (venv) | A: `write()` cost for mkv / mp4f / avi / folder-of-JPEGs × fsync off / every 30, at 720p and 1080p; B: 5-camera RecorderThread submit cost, queue depth and drops at 30/60 fps; C: open, count and seek cost on a 10-minute file, MKV vs fMP4 | `R/bench/recwriter_<tag>.json` |

## 10. Commands used (repo root, Bash)

```
.venv/Scripts/python.exe S/test_roundtrip.py                      # -> R/roundtrip.{json,md}
.venv/Scripts/python.exe S/test_crash.py                          # -> R/crash.{json,md}
.venv/Scripts/python.exe S/make_compat_clips.py                   # -> raw/python_integration/compat/
.venv/Scripts/python.exe S/cv2_read_probe.py --tag cv2_4.12_venv  # -> R/cv2_read_probe_cv2_4.12_venv.json
UV_CACHE_DIR=<scratchpad>/python_integration/uv_cache uv run --script S/cv2_read_probe.py --tag cv2_5.0.0.93_uv
.venv/Scripts/python.exe S/summarize_cv2_probe.py                   # -> R/cv2_compat_table.md
.venv/Scripts/python.exe S/pyav_version_probe.py --tag pyav_18.0.0_venv
UV_CACHE_DIR=<scratchpad>/python_integration/uv_cache uv run --script S/pyav_version_probe.py --tag pyav_19.0.2_uv
uv run --script S/bench_jpeg_decode.py --tag smoke --quick --turbojpeg-dll <dl>/x/bin/turbojpeg.dll
UV_CACHE_DIR=C:/Users/Dom/AppData/Local/Temp/pi_uv uv run --script S/bench_nvjpeg_decode.py --tag smoke --quick
.venv/Scripts/python.exe S/bench_recwriter.py --tag smoke --quick
```
(S/ and R/ as defined at the top; `uv` 0.11.8.)

**Third-party downloads** (all into the scratchpad, none installed system-wide):
- libjpeg-turbo 3.2.0 `https://github.com/libjpeg-turbo/libjpeg-turbo/releases/download/3.2.0/libjpeg-turbo-3.2.0-vc-x64.exe`, sha256 `662761d8ba8dae04aec74023ebaeceb856c2b56b9b59cfd180759d26300dda42`, extracted with 7-Zip. The installer was not run.
- PyPI wheels via uv: av 19.0.2, opencv-python 5.0.0.93, numpy 2.2.6, simplejpeg 1.9.0, PyTurboJPEG 2.6.1, opencv-python 4.12.0.88, nvidia-nvimgcodec-cu12 0.9.0.20 (+ its `[all]` extras).
- FFmpeg sources (n8.1.2 `matroskaenc.c`, `movenc.c`, `matroskadec.c`), OpenCV 4.12.0 `cap_ffmpeg_impl.hpp` and the PyAV changelogs, from raw.githubusercontent.com.
- GPU state recorded around GPU work (`nvidia-smi encoder.stats.sessionCount,utilization.gpu`): `0, 6 %` before / `0, 13 %` after making the clips (av1_nvenc attempt); `0, 24 %` / `0, 39 %` around the nvJPEG smoke test. Utilisation is not attributed: Parsec and Sunshine run on this machine.

## 11. Limits

- **No timing.** Everything here is functional. Decode, write, submit and open costs are in the bench manifest.
- **Timestamps.** Only the two flash sets have real per-frame timestamps (MF `host_arrival_ns`). The short sets use a synthetic lattice. The kill test uses `perf_counter_ns` at write time.
- **Kill test scope.** One kill per variant, at ≥300 frames, writer paced at ~30 fps. Not repeated, not a power-loss test (no fsync). The kill came from the parent. Killing the whole skellycam process tree was not tested here (see the crash_resilience topic).
- **Compat clips.** The barcode clips were encoded by PyAV/FFmpeg 8.1.2, not by a GPU encoder. Hardware-encoded AV1/VP9 bitstreams could differ in reader behaviour (NOT VERIFIED).
- **Not tested:**
  - FreeMoCap's own code end to end (its venv is stale, REPORT §4a). The tests reproduce its OpenCV calls.
  - Linux and macOS (OpenCV wheels there bundle different FFmpeg builds; NOT VERIFIED).
  - A Python lossless JPEG rotation (see the jpeg_passthrough topic, `rotation.json`).
  - Audio (G9 sync with audio).
- **Prototype scope.** `recwriter.py` is a research prototype. It is not skellycam code and has no multi-stream or audio support.
