# JPEG ring: design notes for the phase 2 spec (2026-11-17)

Status: input for the phase 2 spec, not the spec. The decisions marked **[D]** are Dom's, from the grilling
session of 2026-11-17 (see `../../NATIVE_JPEG_CAPTURE_PLAN.md` §4). The layout below is a **proposal** from a
sub-agent's design study of the same day; no prototype of it exists. Phase 2 writes the spec and the test
list for Dom's review before any code.

## Decided

- [D] ~~The ring carries JPEG only. No BGR mode, no legacy read call, no decode helper.~~ Replaced on
  2026-11-18: every camera has a JPEG ring, and a BGR ring on request. See "Two rings per camera" below.
  Still no legacy read call.
- [D] Fixed slots, one shared-memory block per ring: ring header, table of 64-byte frame headers, slots.
- [D] No lossless reader cursors. The recorder does not read the ring (it is a writer thread in the camera
  process, fed by a queue). The ring serves the UI and FreeMoCap.
- [D] Slot size = `2 x (2,048 + 0.5 x width x height)` bytes, rounded up to 4 KiB, from the resolution only.
  Evidence: `../jpeg_bound/FINDINGS.md`.
- [D] Oversize guard: the writer checks each frame's length; a frame that does not fit is not copied, its slot
  is flagged oversize, a counter goes up. The ring also carries the driver's error flag.
- [D] Self-check: log each camera's largest frame as a fraction of its slot, warn above 50 %, show the
  oversize count in the UI.
- [D] ~~About 3 seconds of history per camera, as a setting.~~ Replaced on 2026-11-18: 1 second by default,
  one setting for both rings.
- [D] Every reader copies the frame out, then checks a CRC-32 of the header and of the JPEG. One read path on
  all three OSes.
- [D] Frame headers carry capture times; the ring offers "frame nearest to time t". FreeMoCap groups frames
  itself.
- [D] The UI rotates when drawing, from a rotation value in the frame header.
- [D] (Q78) A frame that arrives with no Huffman tables (no DHT segment) gets the standard tables inserted
  at capture, so the ring and the recorded MKV always hold a self-contained JPEG. None of the four test
  cameras sends such a frame (84 sample frames scanned: all have DHT; C922 and C930e also use restart
  markers).
- [D] (Q79) ~~History stays about 3 s.~~ (1 s from 2026-11-18.) A reader starts reading only once its pipeline is ready (a TensorRT
  engine build can take about a minute); the ring is not sized for start-up.
- [D] (Q80) The ring only carries the rotation value. Who applies it for tracking is decided between
  FreeMoCap and skellytracker, and does not change the ring.
- [D] (Q81) The old ring's extra `copy()` in `put_data` is not fixed. Phase 2 deletes that ring; the
  one-copy rule goes into the phase 2 spec instead (see "Carried over" below).
- skellytracker does not read the ring (FreeMoCap does and passes it one image per camera per call). It has
  no timing constraint on the ring change. A frame flagged capture-error or oversize must not be passed to a
  decoder.
- Phase 2 also affects the image preprocessing in skellytracker; Dom sets up a skellytracker session to
  coordinate with.

## Two rings per camera (decided by Dom, grilling session of 2026-11-18)

Input for the phase 2 spec. The decode stage is built only after Dom's approval and guidance.

| Topic | Decision [D] |
|---|---|
| Rings | Per camera: one JPEG ring always, and one BGR ring only when the consumer asks for it (never on by default). Same layout, one shared-memory block each, the format in the ring header. |
| Recorder | JPEG only, unchanged. |
| Mode list | skellycam lists each mode with resolution, frame rate and format (for example "720p30 MJPG"), and labels YUY2, NV12 and RAW modes as uncompressed. If a resolution and frame rate exist in both MJPG and YUY2, both are listed and the consumer picks; with no pick, MJPG is used. |
| H.264 modes | Listed, never selected. No H.264 decode code. May change later. |
| Choice | In the per-camera config, fixed when the camera session starts. A change recreates the ring. |
| MJPG mode | JPEG ring: the camera's JPEG, untouched. BGR ring: decoded with `cv2.imdecode`. |
| Uncompressed mode | JPEG ring: JPEG encoded at capture, also while not recording; the recorder uses the same JPEG. BGR ring: colour conversion only. |
| BGR ring | BGR 24-bit only, unrotated, the same rotation value in the frame header, slots of exactly `width x height x 3` bytes, no oversize guard. |
| History | 1 second by default for both rings, one setting. skellycam logs the total shared memory at start. |
| Decode stage | One function, in its own thread in the camera process, after the frame has gone to the recorder queue and the JPEG ring. If it falls behind, the BGR ring skips frames (counted and logged); capture and recording are not delayed. `cv2.setNumThreads(1)` in the camera process. No Media Foundation decoder and no Quick Sync decode. |
| Frame numbers | Both rings use the camera's frame numbers and capture times, so a BGR frame can be matched to its JPEG. |
| Errors | A JPEG frame flagged capture-error or cut-off is not decoded; its BGR slot is flagged and has no pixels. A failed decode sets a new `DECODE_ERROR` flag and a counter. |
| Reads | The same read path for both rings: copy out, then CRC-32. Phase 2 measures the cost on BGR frames before anything cheaper is considered. |
| UI | Unchanged: the JPEG ring's frames over the websocket, untouched. |
| FreeMoCap | Accepts JPEG or BGR and takes the native format per camera: it asks for the BGR ring on cameras whose mode is labelled uncompressed. It treats "lapped" as a skip in every reader path, and counts and logs its lapped reads. This goes into the interface note; the work is the freemocap session's. |

Details decided later the same day (rounds 7 to 12 of the grilling) [D]:

| Topic | Decision [D] |
|---|---|
| Owner | The skellycam research session writes the phase 2 ring spec and test list for both rings. |
| Build order | Step 2a is the JPEG ring; step 2b is the BGR ring with the decode stage. One spec covers both. Dom's approval and guidance for the decode stage is given at the spec review. |
| Layout | Both rings share the ring header and the 64-byte slot header. New: a `pixel_format` field in the ring header (JPEG or BGR24), a named rotation field in the slot header (degrees clockwise to make the stored image upright: 0, 90, 180, 270), `payload_crc32` as the name of the payload CRC, and a `DECODE_ERROR` flag. For a BGR ring `payload_len` is the same in every slot. |
| Frame size | Width and height are in the ring header only. A rotation change between upright (0/180) and sideways (90/270) sets `DISCONTINUITY`. |
| Error flags | One rule: a frame with any error flag (`OVERSIZE`, `CAPTURE_ERROR`, `NO_SOI_EOI`, `DECODE_ERROR`) never reaches a decoder or tracking. `NO_SOI_EOI` covers a cut-off frame. |
| Ring names | skellycam gives the consumer each ring's shared-memory name in the per-camera info (a JPEG ring name always, a BGR ring name or none). The consumer never builds a name. |
| Recorder first | A frame goes to the recorder queue before any ring is written. The recorder never loses a frame. A ring write never blocks or waits, and is skipped and counted when the camera process is behind. The recorder's path uses the camera process's own buffers; each ring gets a copy (no conversion straight into a ring slot). |
| MJPG mode, BGR ring | One waiting place between capture and the decode thread. The newest frame wins; a replaced frame is counted as skipped. |
| Times | A BGR slot copies `arrival_ns` and `sample_ns` from its JPEG frame and sets its own `published_ns`. |
| Uncompressed modes | YUY2 and NV12 are converted. Other uncompressed formats (for example Bayer RAW) are listed and not selected, as with H.264. |
| JPEG encoder | Intel Quick Sync (`mjpeg_qsv` through PyAV) where available, on Windows and Linux; `cv2.imencode` otherwise, and always on macOS (Apple Silicon only is supported). No separate libjpeg-turbo package: OpenCV contains it. This replaces the fallback of 2026-11-11. |
| Encoder check | The main skellycam process checks once per app run, by encoding one small test frame, and only if a camera of the session is in an uncompressed mode. The camera processes are told the result. A camera whose own encoder does not open, or fails during a take, uses `cv2.imencode` from then on; the frames the encoder still held are re-encoded from the raw frames, which the process keeps until their JPEG has come out. The event is counted, logged and flagged `DISCONTINUITY`. |
| Encoder settings | Quality 90 by default, one setting passed to both encoders. Chroma layout of the source (4:2:2 from YUY2, 4:2:0 from NV12). `IMWRITE_JPEG_OPTIMIZE` off. Quick Sync `async_depth` 2 (one frame held). |
| Conversion to BGR | With Quick Sync: only when the BGR ring was requested, as ring work that may be skipped. With `cv2.imencode`: on the recorder's path for every frame, because that encoder takes BGR. |
| Input range | Read per mode from the operating system; limited range is assumed if it does not say. The JPEG is always full range: for limited-range input Quick Sync gets a range-expanding table first and `cv2` converts as it does by default; for full-range input Quick Sync gets the frame unchanged and `cv2` uses a full-range conversion. The range of the test cameras' YUY2 modes is measured before the spec fixes this. |
| Too-large request | The total shared memory is always logged. If an allocation fails, the session does not start, and the message names the total size. No automatic shortening of the history. |
| Tests | The JPEG ring suite runs again with BGR payloads (laps, torn reads, CRC, find by time). New: a slow decode skips BGR frames and delays neither capture nor the JPEG ring; a flagged JPEG frame gives a flagged BGR slot with no pixels and the decoder is not called; each BGR frame has its JPEG frame's number and capture times; a JPEG that fails to decode sets `DECODE_ERROR` and the counter. Also a rule with a test: no thread in the camera process spins. |
| Huffman tables | Q78 stands: inserted at capture when a frame has none. |
| Start-up | Up to about 1.2 s more for a session with uncompressed cameras on a Quick Sync machine is accepted. |

Evidence for these rows:

- `cv2.imencode` (`../encode_bench/FINDINGS.md`): quality 90, 4:2:2, one thread: 1.79 ms at 720p and 3.63 ms
  at 1080p; YUY2 to BGR 0.64 and 1.45 ms; no real frame above 32 % of its slot; the cameras' own JPEGs match
  `cv2` quality 87 to 91 by size.
- Quick Sync against `cv2` (`../encode_qsv_bench/FINDINGS.md`): 1080p YUY2 at 30 fps costs 1.64 ms of CPU per
  frame against 6.41 ms; 16 cameras 2.57 cores against 5.75; depth 2 is as fast as depth 4 and holds one
  frame; depth 1 blocks about 17 ms per call. The two encoders assume opposite input ranges.
- AMD and Apple (a short web study, mostly not verified): FFmpeg has no JPEG encoder for AMD AMF or for
  Apple VideoToolbox, so a hardware JPEG encoder reachable through PyAV is Intel only.
- The 2026-11-10 study measured Quick Sync and libjpeg-turbo, not `cv2.imencode`
  (`../../skellycam_recording/recording_upgrade/results/encoder_pairing/FINDINGS.md`).

Still to measure: the range of real YUY2 modes; the CRC cost on BGR frames; Quick Sync on Linux; the image
quality of `cv2.imencode` after the YUY2 to BGR to YUV round trip.

Sizes per camera (MiB), JPEG ring / BGR ring:

| Mode | 1 s | 3 s |
|---|---|---|
| 720p30 | 27 / 79 | 80 / 237 |
| 720p60 | 53 / 158 | 159 / 475 |
| 1080p30 | 60 / 178 | 179 / 534 |
| 1080p60 | 119 / 356 | 357 / 1,068 |

Evidence:

- Decode to BGR, one thread, i7-14700K, 14 real frames (`../decode_bench/FINDINGS.md`, a sub-agent's run, not
  rerun): `cv2.imdecode` (OpenCV 5.1.0, built with libjpeg-turbo 3.1.2) 2.60 ms at 720p and 5.42 ms at 1080p;
  libjpeg-turbo direct 2.11 and 4.17 ms with identical pixels; Intel QSV through PyAV 3.20 and 5.87 ms. With 8
  processes at once: `cv2` 3.17 and 7.11 ms. `cv2.imdecode` was chosen because it is already a dependency.
  simplejpeg rejects two of the generic camera's 1080p frames.
- This machine has three Media Foundation MJPEG decoders registered (in-box, Intel, NVIDIA; all give YUY2 or
  NV12). Not used: the source reader gives one output type per stream, so the JPEG would be lost.
- The UI today (upstream `development-streaming`, read in code): skellycam and FreeMoCap both send JPEG over a
  websocket, encoded by the server from the BGR ring (`cv2.imencode`, quality 60, at most half size). Neither
  UI shows an uncompressed frame.
- History: the 3 seconds was a round number (the old 1 GiB ring holds 2.87 s at 1080p60). The UI reads the
  newest frame. The only delay figure for FreeMoCap is about 205 ms per inference batch (a printed note in
  its benchmark script). FreeMoCap waits up to 2.0 s for a skeleton result, and `camera_node.py:279-282`
  (upstream `development-streaming`) ends the pipeline on an overwritten frame today.

Not verified: the CRC cost on BGR frames (about 0.9 ms at 720p and 2 ms at 1080p, extrapolated); decode speed
on Linux, macOS and other CPUs; the colour conversion cost for uncompressed modes; FreeMoCap's real delay
behind the newest frame.

## Why fixed slots and a CRC (from the study)

- The current ring: each ring is 9 shared-memory segments; a slot is 632 B of metadata (512 B of it the
  camera id, repeated every frame) plus a BGR image; 1 GiB per camera. Publish has no fence. `get_data_by_index`
  checks for a lap before the copy, not after: an earlier test accepted 39,854 to 41,834 torn frames.
- Python has no memory fence or atomic API. The earlier sequence-number prototype relied on Intel store
  ordering, which Apple Silicon does not give. Validating a private copy with a CRC does not depend on
  ordering: the bytes that are used are the bytes that were checked. Not tested on ARM.
- CRC cost measured on this machine (Python 3.12.13, zlib 1.3.1): 42 to 46 µs for 100 kB, 53 to 71 µs for
  210 kB, 178 to 195 µs for 540 kB. Copy out of shared memory: 2.8 / 7.1 / 31.6 µs.
- A packed byte ring with an index saves commit charge only, for 100 to 150 more lines in wrap and capacity
  checks. Pipes give no latest-frame, by-number or fan-out reads. One segment per frame leaks names on a
  crash.
- Shared-memory pages are allocated on first touch (inferred, not measured), so physical memory follows the
  real frame sizes if slots are not prefaulted.

## Proposed layout (not decided)

One block per camera: a 4,096-byte ring header, then `slot_count x 64` bytes of slot headers, then
`slot_count x slot_capacity` bytes of payload. A resolution change recreates the ring under a new name.

Ring header:

| Offset | Field | Type |
|---|---|---|
| 0 | magic `SKR2` | u32 |
| 4 | layout_version | u32 |
| 8 | slot_count | u32 |
| 12 | slot_capacity | u32 |
| 16 | table_offset | u64 |
| 24 | payload_offset | u64 |
| 32 | width, height | u32 each |
| 40 | fps_num, fps_den | u32 each |
| 48 | camera_key | 16 bytes ASCII |
| 64 | utc_ns, perf_ns (timebase mapping) | i64 each |
| 80 | utc_offset_s | i32 |
| 84 | closed | u32 |
| 88 | oversize_count, corrupt_count | u64 each |
| 128 | head (newest frame number) | i64, on its own 64-byte line |

The study also had `gate_drop_count`, `gate_block_ns` and eight lossless cursors from offset 192. They are
left out here because of the "no lossless cursors" decision.

Slot header (64 bytes):

| Offset | Field | Type | Notes |
|---|---|---|---|
| 0 | frame_number | i64 | -1 = empty or being written |
| 8 | arrival_ns | i64 | host clock |
| 16 | sample_ns | i64 | device or OS sample time, or INT64_MIN |
| 24 | published_ns | i64 | |
| 32 | source_frame_number | i64 | or -1 |
| 40 | payload_len | u32 | |
| 44 | flags | u32 | OVERSIZE, NO_SOI_EOI, CAPTURE_ERROR, EMPTY, DISCONTINUITY |
| 48 | jpeg_crc32 | u32 | zlib CRC-32 |
| 52 | reserved | u32 x 2 | one of these can hold the display rotation |
| 60 | header_crc32 | u32 | over bytes 0 to 59 |

Writer, frame k, slot `s = k % slot_count`:

1. `table[s].frame_number = -1`
2. copy the JPEG into `payload[s]` (skip if oversize)
3. write the slot header, header CRC last
4. `head = k`

Reader: copy the header, copy the payload, then check both CRCs and `frame_number`. Results:

- `k > head`: not yet written
- `head - k >= slot_count`, or the slot holds a later frame: lapped
- a CRC or frame-number mismatch: retry once, then lapped
- a flag set: oversize or corrupt, returned with the header

Find by time: copy the `arrival_ns` and `frame_number` columns of the table, take the nearest, then read and
validate that frame.

## Carried over from the 2026-10-28 ring study (proposed spec rules, not decided)

The study's rank 9 was "remove `copy.copy` from `SharedMemoryRingBuffer.put_data`"
(`skellycam/core/ipc/shared_memory/ring_buffer_shared_memory.py` line 132: `... = copy(data)` allocates a
new frame and the slot assignment copies it again). Measured there, 5 x 1080p, synthetic 60 fps cameras:
54.14 to 58.84 / 58.98 fps, `put_frame` 3.61 to 1.29-1.38 ms (`frame_ring_buffer_report.md`,
`../revision/README.md`). It was prototyped as a monkeypatch and never applied. Phase 2 deletes that ring, so
the line goes; the rule it stands for must be written into the spec so the new writer does not repeat it:

- Writer: the capture layer hands over one `bytes` object per frame. That same object goes to the recorder
  queue (no copy) and is slice-assigned once into the slot. The CRC is computed over that object. No
  per-frame allocation beyond it; no `np.frombuffer(...).copy()` or `.tobytes()` round trips.
- Reader: one copy out of the slot, the CRC on that copy, the same object passed on.
- Ring indices and headers are numpy views or `struct` on the one block, not `SharedMemoryNumber` objects
  (study rank 13: 4,423 ns against 53 ns per access).
- The UI server wakes on a new frame or polls at 2 ms, not 10 ms, and does not build payloads on the event
  loop (study rank 12: 51 frames/s forwarded with the 10 ms poll, 60.1 with 2 ms). Avoid `header + jpeg`
  concatenation where the websocket can send two parts.
- Test for the spec: count allocations and copies per published frame in the writer (for example with
  `tracemalloc` on a synthetic writer) and fail if there is more than the one slot copy.

Moot under the new design: retrieve-into-slot (rank 11, no decode at capture), reader views (rank 15, a JPEG
copy costs microseconds; the CRC is now the larger reader cost), seqlock cursors (rank 6, replaced by copy
then CRC), decoupled recorder (rank 7, now a writer thread and queue). `cv2.setNumThreads(1)` (rank 10)
still applies while any OpenCV decode remains.

## From the skellytracker decode session (2026-11-17, its measurements, not rerun here)

On the 84 sample frames, `cv2.imdecode` 5.0.0 and nvJPEG (nvImageCodec 0.10.0.9, RTX 3070) both decode
all of them. What it means for the ring spec (proposed, not decided):

Corrected on 2026-11-18 from that session's check of this section (skellytracker-95). The GPU decode
(nvImageCodec) is planned for the cuda and trt-rtx providers (Dom confirmed it there on 2026-11-18; not built
yet); the CPU decode is the path for every other provider and the fallback.

- A decoder cannot be the detector of a cut-off frame: nvJPEG returned a full-size image with garbage and
  no error for a 4:2:0 frame (Kiyo Pro) cut in memory at 50 %. A cut-off 4:2:2 frame (C922) fails properly
  on nvJPEG. `cv2.imdecode` returns None for both, and skellytracker then refuses the whole call. The writer
  must validate at capture (SOI at the start, EOI at the end, delivered length) and set the `NO_SOI_EOI` /
  `CAPTURE_ERROR` flag; a reader must not hand a flagged frame to a decoder.
- The reader returns `bytes`. The skellytracker call accepts JPEG data only as `bytes` or `bytearray`. A
  numpy array is always read as a decoded BGR image, also a 1-D uint8 array. A `memoryview` is refused.
- No DHT: `cv2` decodes it. On the RTX 3070 the default nvImageCodec path also decodes it on the GPU (at
  most 3 uint8 steps from `cv2`, on a C922 and a Kiyo Pro frame); only a decoder limited to the GPU-only
  backend fails. So Q78 (insert the tables at capture) is not forced by the decoder on this hardware; it
  remains the safe choice for other backends and GPUs.
- A decoded BGR array can also carry the rotation value; the run turns it before the first node, as for a
  decoded JPEG. An unturned BGR ring frame with the ring's rotation value goes straight into the call.
- The rotation must reach the call as a Python int, one of 0, 90, 180, 270. A float, a bool or another value
  refuses the call.
- Requests for the slot header and the reader steps: the rotation in a fixed field with a fixed meaning, for
  both rings; a frame with any error flag (oversize, capture error, cut-off, no SOI/EOI, `DECODE_ERROR`) is
  never passed to a call; a reader can see each frame's stored width and height without decoding, or is told
  when they change (it batches JPEG decodes by stored size).
- Timing from that session: three `cv2.imdecode` calls in a row on one thread take 8.2 ms at 720p and
  17.0 ms at 1080p (one synthetic JPEG), which agrees with 2.60 and 5.42 ms per frame in `../decode_bench/`.
  nvJPEG for the same three frames, including the wait: 2.3 ms at both sizes.
- Threaded CPU decode (that session, 2026-11-18, the 8 real frames per resolution): `cv2.imdecode` releases
  the GIL and scales in a thread pool, 2.3x with 3 threads and 3.9x with 6. Three 1080p frames: 15.1 ms in a
  row, 6.5 ms in a pool; six: 30.5 and 7.8 ms.
- Two points for skellycam's camera process from the same run: a pure-Python thread that never sleeps slows
  every decode about 15 times (GIL hand-back), so no thread in the camera process may spin; and libjpeg
  prints a warning to stderr on every decode of the generic camera's 1080p frames (extra bytes before EOI),
  which the decode stage must not let flood the log.
- Bytes after EOI (1 KiB of zeros or 0xFF) harm neither decoder. Two of the 84 frames make `cv2` print
  "extraneous bytes before marker 0xd9" and still decode.
- Rotation, as relayed by that session (Dom's decision there, later the same day; it replaces an Exif
  orientation-tag idea that was measured and withdrawn): FreeMoCap passes the header's rotation value to
  the skellytracker run with the JPEG bytes, and the run turns the decoded frame right after the decode
  (0.06 to 0.15 ms per frame on the GPU; on the CPU the turn is `cv2.rotate`). Nobody writes an Exif tag;
  both decoders ignore one. The ring and the MKV stay unturned. A lossless turn of the JPEG data is ruled
  out: it cannot turn every size because of a partial block at the edge, and it is slower than decode plus
  turn.
- Proposed header rotation value, which that session now takes as its input: degrees clockwise that the
  stored image must be turned to be upright (0, 90, 180, 270). Today's enum: NO_ROTATION -> 0,
  CLOCKWISE_90 -> 90, ROTATE_180 -> 180, COUNTERCLOCKWISE_90 -> 270.
- Its request: a rotation change between 0/180 and 90/270 changes its decoded frame size and rebuilds its
  preprocess session, so flag a rotation change like a resolution change (DISCONTINUITY) if possible.
- The generic camera's 1920x1080 frame has 601 junk bytes before EOI; both decoders accept it. The capture
  check must not reject such a frame.

## Tests proposed by the study (no cameras needed)

- Synthetic payloads whose bytes are a function of the frame number; sizes 0, 1, random, capacity,
  capacity + 1.
- The adversarial lap test of the earlier ring study: an unthrottled writer process, slot counts 2, 8 and
  real, readers at oldest, newest and by number; assert no wrong bytes are ever accepted.
- Reordering injection, to imitate ARM on x86: a test writer publishes the header and `head` before the
  payload, or writes the payload in halves with a sleep between; every such read must be rejected.
- A bit flipped after commit gives corrupt.
- A writer killed in the middle of a write; a reader killed in the middle of a read.
- Two writers at different rates for the find-by-time lookup.
- The same suite on an Apple Silicon Mac (the plan requires this) and on arm64 CI runners.

## Not verified

- That numpy emits single 8-byte loads and stores.
- First-touch paging and commit behaviour of `multiprocessing.shared_memory` on each OS.
- CRC speed on Python 3.13, macOS or ARM.
- No prototype of this layout has run.
