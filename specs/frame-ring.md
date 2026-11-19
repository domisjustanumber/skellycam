# Phase 2 ring specification: JPEG ring (2a), BGR ring and decode stage (2b)

Status: accepted by the user on 2026-11-18
([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)). The tests of step 2a
(section 12) are in `skellycam/tests/frame_ring/`. The ring package of step 2a is in
`skellycam/core/ipc/frame_ring/`. The app uses it (step 2a, part B). `decisions/open-work.md` holds
the open items of step 2a. Step 2b (section 8) is specified. The build of step 2b waits for a separate approval and
guidance of the user on the decode stage [D N:72].

## 0. How to read this spec

Marks:

- **[D N:73]**: the user decided this before this spec. `N:` is a line of
  `research/frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md`. `P:` is a line of
  `research/NATIVE_JPEG_CAPTURE_PLAN.md`. Both files are on branch `dom/research` at commit
  04322eace of this repository. Each row of the decision tables of the notes is one line. Thus a
  citation of a line cites that row.
- **[An]**: the draft of this spec proposed item n, and the user accepted it on 2026-11-18.
  Section 14, item n, gives each accepted item again. The draft used the mark `[Pn]` with the same
  number. Items 52 to 57 are clarifications, items 58 and 59 are corrections, and items 60 to 62
  are decisions on the finished 2a code, that the user decided on 2026-11-18, after the first 51
  ([ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md)).
- **[M file]**: measured. The file holds the result. Each such file is on branch `dom/research` at
  commit 04322eace of this repository. **[NV]**: not verified.

Where two sources do not agree, the later source wins: the 2026-11-18 tables (N:49-90) override the
2026-11-17 text and the "Proposed layout" (N:160-217). The layout in section 3 is that proposal,
with updates.

This spec uses British spelling.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Phase 2 replaces the current per-camera BGR ring (nine shared-memory segments, 1 GiB per camera)
with one shared-memory block per ring. The block holds a ring header, a table of 64-byte slot
headers and fixed slots [D N:13]. Readers copy a frame out and check two CRC-32 values. The same
read path runs on Windows, Linux and macOS [D N:24].

### 1.2 Scope

| Step | Content |
|---|---|
| 2a | The JPEG ring: layout, writer, reader, lookups, lifecycle, the capture check, the deletion of the old ring classes and frontend-payload code [D P:27-28, P:196]. |
| 2b | The BGR ring on request, with the decode stage in the camera process [D N:51, N:60, N:72]. |

### 1.3 Non-goals

- Native capture (phase 3) [D P:197]. The ring spec states only what the writer receives from
  capture (section 5.1).
- The JPEG encoder for uncompressed modes, the encoder check and the input range rule (phase 3)
  [D N:81-85]. Section 8.7 states only what the BGR ring needs from them.
- The UI websocket message and the UI (phase 4) [D P:198]. Section 6 states what the ring gives the
  UI.
- The recorder (phase 5). Phase 2 keeps two rules: the recorder comes first, and a ring write never
  blocks [D N:77].
- The code of FreeMoCap and skellytracker [D P:23-24, N:39-41]. Their constraints shape the reader
  output (section 6.6).
- Lossless reader cursors [D N:14].
- Each H.264 decode, Media Foundation decoder or Quick Sync decode [D N:54, N:60].

### 1.4 Terms

| Term | Meaning |
|---|---|
| ring | One shared-memory block for one camera and one pixel format (JPEG or BGR24). |
| slot | A fixed region of the block. Frame k goes to slot `k % slot_count` [D P:82]. |
| frame number | The frame counter of the camera. Both rings of a camera use the same numbers [D N:61]. |
| writer | The one thread that writes a ring: the capture thread for the JPEG ring, the decode thread for the BGR ring. |
| creator | The process that creates and unlinks the ring ([A32]: the main skellycam process). |
| reader | A thread in a process that reads a ring. It never writes to the block. |
| consumer | A program that reads rings: the UI server, FreeMoCap, tests. |
| commit | The last two stores of the writer for a frame: the slot header, then `head`. |
| lapped | A later frame has overwritten the requested frame, or is in the process of overwriting it. |
| torn | The copy of a reader mixes bytes from two writes. The CRC checks reject it. |
| flagged | A frame whose slot header has an error flag (section 4). It has no usable payload. |

## 2. What is deleted and what replaces it

### 2.1 Code deleted in 2a [A1]

The callers come from branch `dom/native-jpeg`, read on 2026-11-18.

| Old class or function (file) | Callers today | Replacement |
|---|---|---|
| `SharedMemoryElement`, `SharedMemoryElementDTO` (`core/ipc/shared_memory/shared_memory_element.py`) | `SharedMemoryRingBuffer`, `SharedMemoryNumber` | None. The new ring uses one `multiprocessing.shared_memory.SharedMemory` directly. |
| `SharedMemoryNumber` (`shared_memory_number.py`) | `SharedMemoryRingBuffer` (`last_written_index`, `last_read_index`) | The `head` field in the ring header, read through `struct` or a numpy view (N:232, study rank 13: 4,423 ns against 53 ns per access). |
| `SharedMemoryRingBuffer`, `SharedMemoryRingBufferDTO` (`ring_buffer_shared_memory.py`; the extra `copy(data)` at line 132) | `CameraSharedMemoryRingBuffer` (subclass); `pubsub_topics.SetShmMessage.get_shm_dto_by_camera_id`; `system/diagnostics/check_shm_speed.py` | `FrameRingWriter`, `FrameRingReader` [A31]. The one-copy rule replaces the line-132 fix [D N:37-38]. |
| `CameraSharedMemoryRingBuffer` (`camera_shared_memory_ring_buffer.py`): `from_config`, `put_frame`, `retrieve_latest_frame`, `retrieve_next_frame`, `latest_frame_number` | `CameraGroupSharedMemory`; `opencv_camera_loop.run_opencv_camera_loop` (`put_frame`, line 103); `setup_opencv_camera_loop` (`recreate`, line 49); `opencv_camera_worker_method` (type); FreeMoCap (`get_data_by_index`, `.image[0]`) [P:213] | Writer in the camera process; readers in consumers. |
| `CameraGroupSharedMemory`, `CameraGroupSharedMemoryDTO` (`camera_group_shared_memory.py`): `create`, `recreate`, `get_latest_multiframe`, `get_images_by_frame_number`, `latest_multiframe_number`, `valid`, `unlink_and_close` | `CameraGroup.start` (line 121), `.close` (line 275), `.get_latest_frames` (line 137), `.get_frontend_payload_by_frame_number` (lines 164-166); `CameraGroupIPC.publish_shm_message`; `pubsub_topics.SetShmMessage`; FreeMoCap (`latest_multiframe_number`, `valid`) [P:213-216] | Per-camera ring info (section 9) and a dict of ring creators that `CameraGroup` holds [A32, A34]. |
| `SetShmMessage.camera_group_shm_dto`, `get_shm_dto_by_camera_id` (`core/ipc/pubsub/pubsub_topics.py`) | `CameraGroupIPC.publish_shm_message`; `setup_opencv_camera_loop` (lines 39-50) | The same topic carries a dict of `CameraRingInfo` by camera id [A34]. |
| `core/types/frontend_payload_bytearray.py`: only `create_frontend_payload`, `encode_image_payload`, `ImagePayloadFrame`, `ImagePayloadRequest`, `JPEG_ENCODING_PARAMETERS` (quality 60): the resize and encode code. The file stays with the wire-format types (`MessageType`, `FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE`, `FRONTEND_FRAME_HEADER_DTYPE`) that the interim relay needs [A4, A56]. | `CameraGroup.get_latest_frontend_payload`, `.get_frontend_payload_by_frame_number`; `CameraGroupManager.get_latest_frontend_payloads`; `websocket_server._frontend_image_relay`; FreeMoCap [P:214] | Phase 4. Until then, the interim relay [A4]. |
| `CameraGroup.get_latest_frames`, `.get_latest_frontend_payload`, `.get_frontend_payload_by_frame_number` | `CameraGroupManager.get_latest_frontend_payloads`, `.get_latest_performance_data` (`api/websocket/performance_data.extract_performance_data_from_frames`) | Interim relay [A4]; performance page from slot-header times [A5]. |
| `system/diagnostics/check_shm_speed.py` | none (a script) | Deleted. |

Step 2a deletes about 950 lines: 318 + 59 + 168 + 218 + 77, and about 110 of the 159 lines of
`frontend_payload_bytearray.py` [A56].

Tests that change in 2a [A1]:

| Test file | Change |
|---|---|
| `tests/test_shared_memory.py` | Deleted. Section 12 replaces it. |
| `tests/test_multiframe_ownership.py` | Deleted. |
| `tests/test_image_payload.py` | Kept for the wire-format dtypes, because [A4] is accepted. Without [A4], it would be deleted. |
| `tests/test_frontend_payload_and_recording.py` | Payload cases removed; recording cases kept. |
| `tests/test_camera_shutdown.py` (line 142), `tests/conftest.py` (line 79) | Mocks point at the new types. |
| `tests/reference_recordings/test_camera_loop_shared_memory.py`, `test_concurrent_camera_replay.py`, `test_camera_loop_failures.py` | Rewritten against the new writer. |

Docs: `skellycam-docs/docs/technical/architecture.mdx` names the old classes. Step 2a updates it.
The translated copies of this page (`zh-CN`, `es`, `ar`) are not updated in 2a. The translation
process updates them [A61].
The websocket protocol pages (and their `zh-CN`, `es`, `ar` copies) and
`skellycam-ui/.../binary-protocol.ts` change in phase 4 [A7].

### 2.2 What stays in 2a

- The BGR frame record (`core/types/frame_dtype_factories.create_frame_dtype`,
  `create_initial_frame_rec_array`) stays. The OpenCV loop and the recorder of today continue to use
  it until phases 3 and 5. Only its use as the ring slot type goes [A2].
- The lockstep gate (phase 8) stays [D P:202].

### 2.3 Interim between 2a and phases 3 to 5

These items keep the app usable after 2a. They are temporary. Each item goes when the later phase
lands.

- **Feed.** Capture is OpenCV on each OS until phase 3. OpenCV returns decoded BGR (P:48-50). The
  OpenCV loop encodes each frame with `cv2.imencode`. It passes the bytes to the capture check and
  the writer [A3]. Quality 90 is the decided encoder setting [D N:83]. The default chroma of OpenCV
  is 4:2:0. Cost: 1.53 ms at 720p and 2.97 ms at 1080p, one thread
  [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`]. Section 3 of the plan already names
  this path for Linux and macOS until native capture [D P:49, P:197].
- **UI.** The websocket relay keeps the wire format of today. It fills the message with the ring
  JPEG of each camera, untouched, at the newest frame number that all cameras have [A4]. The relay
  does not resize and does not re-encode. The server does not rotate. The UI rotates from phase 4
  [D N:28]. Until then, a rotated camera shows unrotated.
- **Performance page.** It reads `arrival_ns`, `sample_ns` and `published_ns` from the slot headers
  [A5].
- **Recorder order.** The inline recorder call in the OpenCV loop moves before the ring write [A6].
  This follows "recorder first" [D N:77]. The queue comes in phase 5 [D P:143-145].
- FreeMoCap does not use this skellycam until its own branch is ready [D P:28-29]. Thus the interim
  needs no FreeMoCap path.

## 3. Ring block layout

### 3.1 Block overview

| Region | Offset | Size |
|---|---|---|
| Ring header | 0 | 4,096 |
| Slot header table | `table_offset` = 4,096 | `slot_count x 64` |
| Padding | | up to `payload_offset` |
| Payload area | `payload_offset` = `roundup(4096 + 64 x slot_count, 4096)` | `slot_count x slot_capacity` |

Both rings use this layout. The ring header gives the format [D N:51, N:73]. The block sizes must
come from the header, never from `SharedMemory.size`. On Windows and macOS, `SharedMemory.size` can
be rounded up to a page [NV, Python docs] [A12].

### 3.2 Conventions [A10]

- Each field is little-endian. x86-64 and arm64 are both little-endian.
- Integers: `u32`, `u64`, `i32`, `i64` as named. Each field is aligned to its own size.
- Reserved bytes are zero at creation. Readers ignore them.
- CRC-32 is `zlib.crc32` with its default start value 0 (the IEEE 802.3 polynomial).
- Times are nanoseconds from `time.perf_counter_ns()`. This clock is system-wide on all three OSes
  [NV on macOS]. The ring header carries the timebase mapping to UTC.

### 3.3 Ring header (4,096 bytes) [A8]

The creator writes the static fields one time, before it gives out the name of the ring. The writer
writes `head` and the counters. No other thread writes the block, except the single `closed` store
of the creator at the end.

| Offset | Size | Type | Name | Meaning | Written by, when |
|---|---|---|---|---|---|
| 0 | 4 | 4 bytes | `magic` | `SKR2` (0x53 0x4B 0x52 0x32) | creator, at creation |
| 4 | 4 | u32 | `layout_version` | 1 for this spec | creator, at creation |
| 8 | 4 | u32 | `header_size` | 4,096 | creator, at creation |
| 12 | 4 | u32 | `pixel_format` | 1 = JPEG, 2 = BGR24 [D N:73] | creator, at creation |
| 16 | 4 | u32 | `slot_count` | N (section 3.7) | creator, at creation |
| 20 | 4 | u32 | `slot_capacity` | bytes per slot; also the slot stride | creator, at creation |
| 24 | 8 | u64 | `table_offset` | 4,096 | creator, at creation |
| 32 | 8 | u64 | `payload_offset` | see 3.1 | creator, at creation |
| 40 | 8 | u64 | `total_size` | `payload_offset + N x slot_capacity` | creator, at creation |
| 48 | 4 | u32 | `width` | stored width in pixels [D N:74] | creator, at creation |
| 52 | 4 | u32 | `height` | stored height in pixels [D N:74] | creator, at creation |
| 56 | 4 | u32 | `fps_num` | nominal frame rate, numerator | creator, at creation |
| 60 | 4 | u32 | `fps_den` | nominal frame rate, denominator | creator, at creation |
| 64 | 16 | ASCII | `camera_key` | camera id, first 16 bytes, NUL-padded; for logs only | creator, at creation |
| 80 | 4 | u32 | `camera_index` | camera index | creator, at creation |
| 84 | 4 | u32 | `creator_pid` | process id of the creator | creator, at creation |
| 88 | 8 | i64 | `utc_ns` | timebase mapping: UTC time | creator, at creation |
| 96 | 8 | i64 | `perf_ns` | timebase mapping: `perf_counter_ns` at the same instant | creator, at creation |
| 104 | 4 | i32 | `utc_offset_s` | local time offset from UTC, seconds | creator, at creation |
| 108 | 4 | u32 | `closed` | 0 = open, 1 = closed (section 7.4) | creator, at close |
| 112 | 4 | u32 | `history_ms` | the history setting used | creator, at creation |
| 116 | 12 | | reserved | zero | |
| 128 | 8 | i64 | `head` | newest committed frame number; -1 before the first | writer, last step of each commit |
| 136 | 56 | | reserved | zero; `head` is alone on its 64-byte line | |
| 192 | 8 | u64 | `frames_committed` | slots committed, flagged ones included | writer, each commit |
| 200 | 8 | u64 | `oversize_count` | frames flagged `OVERSIZE` [D N:18-19] | writer, each commit |
| 208 | 8 | u64 | `capture_error_count` | frames flagged `CAPTURE_ERROR` | writer, each commit |
| 216 | 8 | u64 | `cut_off_count` | frames flagged `NO_SOI_EOI` | writer, each commit |
| 224 | 8 | u64 | `decode_error_count` | BGR ring: frames flagged `DECODE_ERROR` [D N:62] | writer, each commit |
| 232 | 8 | u64 | `skipped_count` | frames not written to this ring [D N:60, N:77, N:78] | writer, on a skip |
| 240 | 8 | u64 | `dht_inserted_count` | JPEG ring: frames that got standard Huffman tables [D N:29-32] | writer, each commit |
| 248 | 8 | u64 | `largest_payload_len` | largest JPEG seen, oversize ones included [D N:20-21] | writer, each commit |
| 256 | 3,840 | | reserved | zero | |

### 3.4 Slot header (64 bytes) [A9]

The header of slot s is at `table_offset + 64 x s`. At commit, the writer writes all 64 bytes in
one slice assignment (section 5.4). The fields are those of N:189-200, with the names and additions
of the 2026-11-18 decisions.

| Offset | Size | Type | Name | Meaning | Written by, when |
|---|---|---|---|---|---|
| 0 | 8 | i64 | `frame_number` | k; -1 = empty or being written | writer: -1 at step W2, k at commit |
| 8 | 8 | i64 | `arrival_ns` | `perf_counter_ns` when the frame reached the capture callback of skellycam | writer, at commit |
| 16 | 8 | i64 | `sample_ns` | device or OS sample time on the same clock, or INT64_MIN | writer, at commit |
| 24 | 8 | i64 | `published_ns` | `perf_counter_ns` immediately before the commit of this header | writer, at commit |
| 32 | 8 | i64 | `source_frame_number` | the own counter of the capture layer (V4L2 sequence, Media Foundation sample count), or -1 | writer, at commit |
| 40 | 4 | u32 | `payload_len` | payload bytes; BGR: always `width x height x 3` [D N:73] | writer, at commit |
| 44 | 4 | u32 | `flags` | section 4 | writer, at commit |
| 48 | 4 | u32 | `payload_crc32` | CRC-32 of the payload [D N:73]; 0 when no payload was copied | writer, at commit |
| 52 | 4 | u32 | `rotation_cw_deg` | degrees clockwise to turn the stored image upright: 0, 90, 180, 270 [D N:73] | writer, at commit |
| 56 | 4 | u32 | reserved | zero | writer, at commit |
| 60 | 4 | u32 | `header_crc32` | CRC-32 of bytes 0 to 59 | writer, at commit |

A BGR slot copies `arrival_ns` and `sample_ns` from its JPEG frame and sets its own `published_ns`
[D N:79]. Both rings carry the same rotation value [D N:58]. The enum of today maps as follows:
`NO_ROTATION` (-1) to 0, `CLOCKWISE_90` to 90, `ROTATE_180` to 180, `COUNTERCLOCKWISE_90` to 270
[A9] (mapping from N:295-296).

### 3.5 Payload area

- The payload of slot s starts at `payload_offset + s x slot_capacity`.
- The first `payload_len` bytes are the frame. The bytes after them are stale. Readers never read
  them.
- JPEG: the bytes of the camera, untouched, except for inserted Huffman tables [D N:56, N:29-32].
- BGR: `height x width x 3` bytes, row-major, B G R per pixel, unrotated [D N:58].
- Each JPEG slot starts on a 4 KiB boundary. A BGR slot starts on a 64-byte boundary when
  `width x height` is a multiple of 64. This is true for each mode in the table below.

### 3.6 Slot capacity

| Format | Formula | Source |
|---|---|---|
| JPEG | `2 x (2,048 + 0.5 x width x height)`, rounded up to a multiple of 4,096 | [D N:16, P:84] |
| BGR24 | exactly `width x height x 3`; no rounding; no oversize guard | [D N:58] |

| Mode | JPEG slot | BGR slot |
|---|---|---|
| 640x480 | 311,296 | 921,600 |
| 1280x720 | 925,696 | 2,764,800 |
| 1920x1080 | 2,080,768 | 6,220,800 |
| 3840x2160 | 8,298,496 [NV: nothing above 1080p measured] | 24,883,200 |

The largest real frames that were measured fill 0.29 of the slot at 720p and 1080p (276,269 and
607,032 bytes, both Kiyo Pro) [M `research/frame_ring_buffer/jpeg_bound/FINDINGS.md`].

### 3.7 Slot count

- One history setting applies to both rings. The default is 1 second [D N:59, N:22-23].
- The ring is not sized for start-up. A reader starts to read when its pipeline is ready
  [D N:33-34].
- `slot_count = max(2, ceil(history_s x fps))`. `fps` is the frame rate of the opened mode. If
  capture reports no frame rate (for example the OpenCV "auto" value -1), skellycam uses 60 and
  logs it [A11]. Then the ring header holds `fps_num = 0` and `fps_den = 1`, which means "unknown"
  [A52].

### 3.8 Total size

`total_size = roundup(4096 + 64 x N, 4096) + N x slot_capacity`. For N up to 64, `payload_offset`
is 8,192.

Size per camera, 1 second of history (bytes, then MiB):

| Mode | N | JPEG ring | BGR ring |
|---|---|---|---|
| 720p30 | 30 | 27,779,072 (26.5) | 82,952,192 (79.1) |
| 720p60 | 60 | 55,549,952 (53.0) | 165,896,192 (158.2) |
| 1080p30 | 30 | 62,431,232 (59.5) | 186,632,192 (178.0) |
| 1080p60 | 60 | 124,854,272 (119.1) | 373,256,192 (356.0) |

These values agree with the table of the notes (N:114-121). Four cameras at 720p30 with JPEG rings
only: 106 MiB. Sixteen cameras at 1080p60 with both rings: 7.4 GiB. Today: 1 GiB per camera
(N:146-147).

### 3.9 Layout version rule [A13]

- `layout_version` is 1.
- Each change to an offset, size, type or meaning of a field, or to a flag bit, must increase it by
  one.
- A reader that sees a wrong `magic` or an unknown `layout_version` must refuse to attach. Its
  error must name both values. There is no compatibility path.

### 3.10 Changes from the "Proposed layout" of 2026-11-17

| Change | Why |
|---|---|
| `pixel_format` added to the ring header | [D N:73] |
| `rotation_cw_deg` in the slot header (was a reserved word) | [D N:73] |
| `jpeg_crc32` renamed `payload_crc32` | [D N:73] |
| `DECODE_ERROR` flag added; `EMPTY` flag dropped (`frame_number = -1` already says it) | [D N:73]; [A14] |
| History 1 s; lossless cursors and gate fields left out | [D N:59, N:14] |
| `corrupt_count` dropped from the ring header | Readers would write it. That breaks "one writer". Readers count their own results [A8]. |
| `header_size`, `total_size`, `creator_pid`, `camera_index`, `history_ms` and five counters added | Self-check, crash sweep and logs [A8]. |

## 4. Flags

`flags` is a u32 in the slot header. The bits are [A14]:

| Bit | Value | Name | Error | Meaning | Set by |
|---|---|---|---|---|---|
| 0 | 0x01 | `OVERSIZE` | yes | JPEG longer than the slot; not copied [D N:18-19] | JPEG writer |
| 1 | 0x02 | `CAPTURE_ERROR` | yes | the capture layer reported an error for this frame [D N:18-19] | capture check |
| 2 | 0x04 | `NO_SOI_EOI` | yes | no SOI at the start, no EOI at the end, or a length mismatch: a cut-off frame [D N:75] | capture check |
| 3 | 0x08 | `DECODE_ERROR` | yes | the decode of this frame failed [D N:62] | BGR writer |
| 4 | 0x10 | `DISCONTINUITY` | no | see below | writer |
| 5 | 0x20 | `DHT_INSERTED` | no | standard Huffman tables were inserted [A14] | capture check |
| 6-31 | | reserved | | zero | |

The error mask is 0x0F.

**The rule [D N:75]: a frame with an error flag must never reach a decoder or tracking.** The
reader returns no payload for it (section 6.3). The BGR stage never decodes it (section 8.5). For a
cut-off JPEG, the GPU decoder of skellytracker returns garbage with no error. Thus this flag is the
only protection on that path (N:254-258).

The writer sets `DISCONTINUITY` on the first frame after these events:

- a rotation change between upright (0, 180) and sideways (90, 270) [D N:74];
- a switch to `cv2.imencode` after an encoder failure (phase 3) [D N:82].

The first frame of a new ring does not get `DISCONTINUITY` [A55].

A BGR slot copies `DISCONTINUITY` and the error flags of its JPEG frame [A15].

## 5. Writer

### 5.1 What the writer receives from capture [A16]

For each frame, the capture layer gives these items to the writer:

| Item | Type | Notes |
|---|---|---|
| `payload` | `bytes` | One object per frame: the JPEG of the camera, or the JPEG encoded at capture for an uncompressed mode [D N:57]. |
| `frame_number` | int | Starts at 0 in each new ring, +1 per frame that capture delivers [A17]. |
| `arrival_ns`, `sample_ns`, `source_frame_number` | int | As in 3.4. |
| `delivered_len` | int | The length that the capture API reported (Media Foundation current length, V4L2 `bytesused`). |
| `driver_error` | bool | The error flag of the capture API for this frame. |
| `rotation_cw_deg` | int | From the camera config. |

For a BGR ring (2b), the writer receives an `ndarray` of shape `(height, width, 3)`, uint8,
C-contiguous, with the numbers and times of the JPEG frame (section 8).

### 5.2 Capture check

The writer must validate each frame at capture, because a decoder cannot detect a cut-off frame
[D N:75, N:254-258]. The check is one function, separate from the ring writer. Thus the recorder
gets the same result [A22]. The rules are [A18]:

1. SOI: the first two bytes must be `FF D8`. If not, set `NO_SOI_EOI`.
2. EOI: the last `FF D9` must be in the final 4,096 bytes, and each byte after it must be `00` or
   `FF`. If not, set `NO_SOI_EOI`. Bytes after EOI do not harm either decoder (N:285). The check
   accepts junk bytes of a camera before EOI. The generic camera sends 601 of them at 1920x1080
   (N:299-300).
3. Length: `len(payload) == delivered_len`. If not, set `NO_SOI_EOI`.
4. Header walk: from SOI, step through the marker segments to the first SOS (`FF DA`). If a segment
   length goes past the end, set `NO_SOI_EOI`.
5. If `driver_error` is true, set `CAPTURE_ERROR`.
6. Huffman tables: if no DHT segment (`FF C4`) comes before the first SOS, insert the standard
   tables [D N:29-32, N:89]. The tables are those of ITU-T T.81 Annex K.3, as one 420-byte DHT
   segment, inserted immediately before the first SOS [A19]. This makes one new `bytes` object. Set
   `DHT_INSERTED` and count the frame. None of the four test cameras sends such a frame (N:30-32).

A frame with `NO_SOI_EOI` or `CAPTURE_ERROR` skips step 6.

### 5.3 Order: recorder first [D N:77]

1. Capture check (5.2).
2. The frame goes to the recorder queue with its flags [A22]. Phase 5 specifies what the recorder
   does with a flagged frame.
3. The JPEG ring write (5.4).
4. 2b only: the frame goes to the waiting place of the decode stage (8.3).

The recorder never loses a frame. A ring write must never block, and it must never wait on a reader
or a lock [D N:77]. When the camera process is behind, the write is skipped and counted [D N:77].
The skip trigger [A23]: the capture layer already holds a newer frame for this camera when the write
would start. In 2a (OpenCV, synchronous) this never occurs. The counter stays 0.

### 5.4 Writer steps, JPEG frame k [A20]

`s = k % N`. The writer keeps one preallocated 64-byte `bytearray` to pack headers.

| Step | Action |
|---|---|
| W1 | `crc = zlib.crc32(payload)`, over the object received [A25, from N:228-230]. Skipped for a flagged or oversize frame (`crc = 0`). |
| W2 | `table[s].frame_number = -1` (one 8-byte store). This also breaks the header CRC of the slot. |
| W3 | If not flagged and `len(payload) <= slot_capacity`: `payload_area[s][0:len] = payload` (one slice assignment). |
| W4 | `published_ns = perf_counter_ns()`. Pack bytes 0 to 59 with `struct.pack_into`, then `header_crc32` over them. |
| W5 | `table[s][0:64] = header_buffer` (one 64-byte slice assignment). |
| W6 | `head = k` (one 8-byte store). |
| W7 | Update the counters and `largest_payload_len`. |

### 5.5 Writer steps, BGR frame k (2b)

The steps are the same, with these differences:

- W1: `zlib.crc32(array)` over the decoded array through the buffer protocol, with no copy.
- W3: one copy of the bytes of the array into the slot. `cv2.imdecode` cannot decode into the slot:
  the OpenCV 5.1.0 Python binding refuses a `dst` argument
  [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`].
- `payload_len` is `width x height x 3` in each slot [D N:73].

### 5.6 Flagged and oversize frames [A21]

- The writer does not copy an oversize JPEG [D N:18-19]. It commits the slot header with
  `OVERSIZE`, `payload_len` = the real length, and `payload_crc32` = 0.
- The writer also does not copy a JPEG flagged `NO_SOI_EOI` or `CAPTURE_ERROR`. `payload_len` = the
  delivered length.
- A flagged BGR slot has no pixels [D N:62]. `payload_len` stays `width x height x 3`, and
  `payload_crc32` is 0. The flags tell readers that there is no payload.
- Each flagged frame still uses its slot, advances `head` and counts in `frames_committed`.

### 5.7 One-copy rule [D N:37-38]

The wording of the rule comes from the details of the 2026-10-28 study (N:228-238) [A25]:

- The capture layer gives one `bytes` object per frame. The same object goes to the recorder queue
  (no copy). The writer slice-assigns it one time into the slot. The writer computes the CRC over
  that object.
- The write path must make no other per-frame allocation: no `copy()`, no
  `np.frombuffer(...).copy()`, no `.tobytes()`, no new header object.
- The one permitted extra copy is the DHT insertion of 5.2 step 6.
- Test: T-RING-15 counts allocations with `tracemalloc` on a synthetic writer.

### 5.8 Counters and self-check

- The writer keeps the counters in the ring header (3.3). The UI shows the oversize count from there
  (phase 4) [D N:20-21].
- The camera process logs the largest frame of each ring as a fraction of its slot, at session end
  and every 60 s [A24].
- It gives a warning one time per camera and session, the first time that a frame is larger than
  50 % of its slot [D N:20-21; one time per session is A24].
- skellycam logs the total shared memory at session start [D N:59, N:87] (section 7.8).

## 6. Reader

### 6.1 Attach [A30]

- The reader gets the name of the ring from the per-camera info (section 9). It never makes a name
  [D N:76].
- It opens `SharedMemory(name=..., create=False, track=False)`. `track=False` (Python 3.13) stops
  its resource tracker from unlinking the ring when the reader exits on Linux and macOS [NV on our
  machines].
- It checks `magic` and `layout_version` (3.9). Then it reads the static header fields one time.
- It reads through `shm.buf.toreadonly()`. It never writes to the block.
- It releases each view before `close()`. If it does not, `close()` raises `BufferError` (Python
  behaviour).
- Width, height and format do not change during the life of the ring, because a change recreates
  the ring under a new name [D N:55, N:74]. skellytracker asked to know stored sizes without a
  decode (N:273-274). This gives it that information.

### 6.2 `read(k)` steps [A27]

| Step | Action | Result if it fails |
|---|---|---|
| R1 | If `closed != 0`: stop. | `CLOSED` |
| R2 | `h = head`. If `h < 0` or `k > h`. | `NOT_YET_WRITTEN` |
| R3 | If `h - k >= N`. | `LAPPED` |
| R4 | Copy the 64-byte slot header `s = k % N` into a private buffer. | |
| R5 | If `frame_number` of the copy is -1, stop before any CRC check [A58]. Else check `header_crc32` over bytes 0 to 59 of the copy. | `LAPPED` (-1); retry rule (CRC) |
| R6 | Header `frame_number < k`. | `MISSING` (the writer skipped k) |
| R7 | Header `frame_number > k`. | `LAPPED` |
| R8 | `OVERSIZE` set. | `OVERSIZE`, header only |
| R9 | Another error flag set. | `FLAGGED`, header only |
| R10 | If `payload_len > slot_capacity`: treat as a CRC failure. Never copy past the slot. | retry rule |
| R11 | Copy `payload_len` bytes of slot s into a new object (one copy). | |
| R12 | Check `payload_crc32` over that object. | retry rule |
| R13 | Return the header fields and the object. | `OK` |

A skipped frame number that a reader asks for before the ring has wrapped one time reads as
`LAPPED`, not `MISSING`, because its slot still holds -1 (R5). This behaviour is accepted [A53].

`head` is only a hint. A stale, early or torn `head` can only cause `NOT_YET_WRITTEN`, `LAPPED`,
`MISSING` or a retry. It can never make the reader accept wrong bytes, because R5, R6/R7 and R12
check the private copy.

### 6.3 Read results [A26]

| Result | Meaning | Payload |
|---|---|---|
| `OK` | The frame, checked | yes |
| `NOT_YET_WRITTEN` | `k > head` | no |
| `LAPPED` | overwritten or being overwritten | no |
| `MISSING` | the writer skipped this frame number (5.3, 8.3) | no |
| `CORRUPT` | the slot is not being written, and its bytes fail a CRC check on two identical copies (6.4) | no |
| `OVERSIZE` | the frame did not fit the slot | no, header only |
| `FLAGGED` | `CAPTURE_ERROR`, `NO_SOI_EOI` or `DECODE_ERROR` | no, header only |
| `CLOSED` | the ring is closed; get the per-camera info again | no |

The plan names OK, not yet written, lapped, corrupt and oversize [D P:117]. This spec adds
`MISSING`, `FLAGGED` and `CLOSED` [A26]. FreeMoCap treats "lapped" as a skip in every reader path
and counts it [D N:65]. It should do the same for `MISSING` [A26].

### 6.4 Retry rule [A27]

The notes say "retry once, then lapped" (N:213). The notes also expect that a bit flip after commit
gives "corrupt" (N:310). This rule satisfies both:

1. On a failed check (R5, R10 or R12), copy the header and the payload again, one time,
   immediately.
2. A copy whose `frame_number` is -1 gives `LAPPED` at once, on the first copy or on the retry
   (R5). The writer is in the slot (step W2), or a writer was killed in the slot [A58].
3. If the second copy passes, return `OK`.
4. If the two header copies are byte-identical, carry `frame_number == k`, and pass the header CRC,
   the writer did not touch the slot. Thus the payload is bad. Return `CORRUPT`. Also return
   `CORRUPT` if the two header copies are identical and fail the header CRC.
5. If not, return `LAPPED`.

Thus `CORRUPT` means only one thing: the slot is not being written, and its stored bytes fail a
CRC check two times with identical copies [A58].

### 6.5 Lookups [D N:26-27, P:115] [A28]

| Lookup | Steps |
|---|---|
| newest | `read(head)`. If the result is `LAPPED`, read `head` again and try one more time. |
| by frame number | `read(k)`. |
| nearest to time t | Copy the full slot-header table (N x 64 bytes; 3,840 bytes at N = 60) in one slice. Keep the rows whose header CRC passes and whose `frame_number` is at least `head - N + 1`. Take the row with the smallest `abs(arrival_ns - t)`. A tie goes to the lower frame number. Then do `read(k)` of that row and check that `arrival_ns` agrees. Return that result. |

`t` is on the `perf_counter_ns` clock. The timebase mapping of the ring header converts from UTC.
skellycam does not group frames across cameras. FreeMoCap does [D N:26-27].

### 6.6 What the reader returns [A29]

The reader returns a frozen dataclass `FrameRead` with these fields: `result`, `frame_number`,
`arrival_ns`, `sample_ns`, `published_ns`, `source_frame_number`, `flags`, `rotation_cw_deg` (a
Python `int`), `payload_len`, and `payload`.

| Ring | `payload` type | Why |
|---|---|---|
| JPEG | `bytes` | skellytracker accepts JPEG only as `bytes` or `bytearray`. It reads each numpy array as a decoded BGR image, and it refuses a `memoryview` (N:259-260). |
| BGR | writable `numpy.ndarray`, shape `(height, width, 3)`, uint8 | skellytracker reads each numpy array as BGR (N:259-260), so this is the type that it expects. The reader copies the slot into a new `bytearray` (the one copy) and checks its CRC. Then it wraps it with `np.frombuffer(...).reshape(...)`, with no second copy. A `bytearray` makes the array writable. `bytes` would make it read-only, and it is not known if skellytracker writes into its input [NV]. BGR as `bytes` would be wrong: skellytracker would treat it as a JPEG. |
| any, not OK | `None` | Flagged and oversize frames have no payload (section 4). |

skellytracker gets the rotation value as an `int` in {0, 90, 180, 270}. It refuses a float, a bool
or another value (N:269).

What the ring gives the UI (phase 4) [D N:64]: the newest lookup, the JPEG bytes untouched, the
rotation per frame, and the oversize count in the header.

## 7. Ring lifecycle

### 7.1 Creation [A32]

- The main skellycam process creates each ring, as `CameraGroup.start` creates the shared memory
  today (line 121, after the cameras report their opened configs).
- Rings per camera: one JPEG ring always. One BGR ring only if the per-camera config asks for it
  [D N:51].
- The creator first computes the size of each ring. Then it logs the total (7.8). Then it
  allocates.
- It writes the static header fields, `head = -1`, and `frame_number = -1` in each slot header. It
  does not touch the payload area, so pages are allocated on first touch [NV N:157-158, N:318].
- Then it gives the names to the camera processes and consumers (7.3). Each camera process attaches
  as the writer of its rings.

### 7.2 Naming [A33]

- Format: `skc<creator pid, hex>_<camera index>_<J|B><generation>`, for example `skc1a2f3c_3_J0`.
- The generation increases by one each time that the ring of a camera is recreated in the same
  process. It counts up per skellycam process, not per session. Thus a name is never used again
  while the app runs [A54].
- At most 30 characters. macOS limits a POSIX shared-memory name to 31 bytes, including the leading
  slash [NV]. For this reason, the default names of Python have 14 characters.
- The prefix lets the Linux sweep (7.7) find stale rings.

### 7.3 Handing names to consumers [D N:76] [A34]

- skellycam gives the ring names of each camera in its per-camera info: a JPEG ring name always,
  and a BGR ring name or none (section 9).
- In skellycam, the `SetShmMessage` topic carries a dict of `CameraRingInfo` by camera id. This
  replaces `CameraGroupSharedMemoryDTO`.
- Consumers outside the process get the same info from the API. The interface note (phase 4) tells
  how [D P:206-211].

### 7.4 The `closed` field [A35]

- The creator sets `closed = 1` before it unlinks a ring, at session end and before a recreation.
- A reader checks `closed` at the start of each read (R1) and returns `CLOSED`. Then it closes its
  handle and asks for the per-camera info again.
- The writer checks `closed` before each write. If `closed` is set, the writer stops writing.

### 7.5 Recreation on a resolution or format change

- The resolution, frame rate, format and BGR request are fixed when the camera session starts. A
  change recreates the ring [D N:55].
- The new ring gets a new name (generation + 1) [A33, from the proposed layout N:163]. The creator
  closes the old ring (7.4). Then it unlinks the old ring at once. It does not wait for its writer
  to detach. A process that is attached keeps its mapping [A62].
- The camera loop gets the new ring name through the optional argument `shm_subscription` of
  `run_opencv_camera_loop` [A62].
- `FrameRingWriter.name` is public, and `NO_SAMPLE_NS` is exported by the ring package [A62].
- Frame numbers start again at 0 in the new ring [A17].
- A rotation change does not recreate the ring. Rotation is per frame. An upright/sideways change
  sets `DISCONTINUITY` [D N:74].

### 7.6 Normal cleanup

- Camera process: it closes its handles when its loop ends.
- Creator: it sets `closed` and waits for the camera processes to end (as `CameraGroup.close` does
  today). Then it calls `unlink()` and `close()`.
- Readers: each reader closes its own handles. With `track=False`, the exit of a reader never
  unlinks the ring.

### 7.7 Cleanup after a crash

| OS | What frees a ring | After a crash |
|---|---|---|
| Windows | The OS frees a named mapping when the last handle closes. `unlink()` does nothing (Python docs). | The OS frees it when each process that holds it has exited. A reader that survives keeps the memory until it closes its handle. The new name on recreation prevents a reattach to a stale block. [NV on our machines] |
| Linux | The segment stays in `/dev/shm` until a process unlinks it. The resource tracker of Python (a separate process) unlinks the segments that its process tree created, when it exits, with a "leaked shared_memory" warning. | Main process crash: the tracker unlinks [NV]. Main process and tracker both killed (`kill -9` of the group): the segment stays until reboot. Sweep [A37]: at start, unlink each `/dev/shm/skc*` whose `creator_pid` is not alive. |
| macOS | As Linux: POSIX shared memory, resource tracker. There is no `/dev/shm` to list. | A segment that a killed tracker leaves cannot be listed. It stays until reboot [NV]. This spec has no sweep for macOS. |

### 7.8 Too-large request [D N:87]

- skellycam always logs the total shared memory of the session at start, with the size of each ring
  [D N:59, N:87; per-ring sizes A38].
- If an allocation fails, the session does not start. The message gives the total size in bytes and
  MiB [D N:87; format A38]. skellycam closes and unlinks the rings that it already created for the
  session.
- skellycam never shortens the history automatically [D N:87].
- The failure of an allocation is different on each OS:
  - Windows: a pagefile-backed mapping charges its full size against the commit limit at creation.
    Thus creation fails with `OSError` [NV].
  - Linux: `/dev/shm` is tmpfs, and `ftruncate` reserves nothing. Creation succeeds, and the first
    write past the tmpfs capacity kills the writer with `SIGBUS` [NV]. Thus, on Linux, skellycam
    compares the free space of `/dev/shm` (`os.statvfs`) with the total before it creates rings.
    If the free space is too small, the session start fails in the same way [A36].
  - macOS: not known [NV].

## 8. Step 2b: BGR ring and decode stage

This section specifies step 2b. The build of step 2b waits for the approval and guidance of the
user [D N:72]. The acceptance of the items of this section on 2026-11-18 is not an approval to build
step 2b.

### 8.1 The BGR ring request

- The consumer asks for a BGR ring per camera in the per-camera config, at session start. It is
  never on by default [D N:51, N:55, P:102-103].
- The field is `bgr_ring: bool = False` on `CameraConfig` [A39].
- FreeMoCap asks for it on cameras whose mode has the label uncompressed [D N:65].
- The BGR ring has the layout of section 3, `pixel_format = 2`, slots of exactly
  `width x height x 3` bytes, and no oversize guard [D N:58].

### 8.2 The decode stage

- The decode stage is one function, in its own thread in the camera process [D N:60].
- It runs after the frame has gone to the recorder queue and the JPEG ring [D N:60, N:77].
- The camera process calls `cv2.setNumThreads(1)` one time [D N:60].
- It is the only writer of the BGR ring.

### 8.3 The waiting place [D N:78] [A40]

- One waiting place is between capture and the decode thread. It holds one frame at most.
- The capture thread puts the frame there and wakes the decode thread. If a frame is already there,
  the new frame replaces it, and the replaced frame counts as skipped [D N:78].
- A `threading.Condition` guards it. The capture thread never waits on it longer than the time to
  take the lock.
- The decode thread waits on the condition with a timeout of at least 100 ms. The timeout is only
  for the shutdown check.
- The waiting place counts replacements in a Python int under its lock. The decode thread copies the
  count to `skipped_count` in the BGR ring header. Thus the ring keeps one writer.
- If the decode falls behind, the BGR ring skips frames. Capture and recording are not delayed
  [D N:60]. skellycam counts and logs the skips [D N:60]. A reader that asks for a skipped number
  gets `MISSING`.

### 8.4 Decode, MJPG mode [D N:56]

1. Take the frame from the waiting place.
2. If its JPEG flags have an error bit, commit a flagged BGR slot with no pixels. Do not call the
   decoder [D N:62] (8.5).
3. `bgr = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)` [D N:56; flag value
   A41].
4. If `bgr` is `None`, or its shape is not `(height, width, 3)`, commit a slot flagged
   `DECODE_ERROR` with no pixels, and count it [D N:62; shape check A41].
5. If not, write it as in 5.5.

`cv2.imdecode` releases the GIL (skellytracker session, N:278-280). Cost: 2.60 ms at 720p, 5.42 ms
at 1080p, one thread; 3.17 and 7.11 ms with 8 processes at the same time
[M `research/frame_ring_buffer/decode_bench/FINDINGS.md`].

### 8.5 Flagged frames and decode errors

- skellycam does not decode a JPEG frame flagged capture-error or cut-off. Its BGR slot is flagged
  and has no pixels [D N:62].
- The BGR slot copies the flags of the JPEG frame (section 4) [A15].
- A failed decode sets `DECODE_ERROR` and increments `decode_error_count` [D N:62].

### 8.6 Frame numbers and times

- The BGR slot uses the number, `arrival_ns` and `sample_ns` of the JPEG frame, and sets its own
  `published_ns` [D N:61, N:79].
- The BGR slot also copies `source_frame_number` and `rotation_cw_deg` [D N:58 for rotation; A15
  for the counter].

### 8.7 Uncompressed modes (phase 3 capture; the ring side is specified here)

- skellycam converts YUY2 and NV12. It lists other uncompressed formats and does not select them
  [D N:80].
- The BGR ring needs only a colour conversion [D N:57].
- With Quick Sync, the conversion to BGR runs only when the BGR ring was requested, as ring work
  that can be skipped [D N:84].
- With `cv2.imencode`, the conversion runs on the path of the recorder for each frame, because that
  encoder takes BGR [D N:84].
- The path of the recorder uses the own buffers of the camera process. Each ring gets a copy.
  Nothing converts directly into a ring slot [D N:77].
- Hand-over [A43]:
  - `cv2.imencode` case: the path of the recorder copies its BGR buffer into a new array and puts
    that array in the waiting place (0.07 ms at 720p, 0.21 ms at 1080p for the copy alone
    [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`]). Then the decode thread writes it as
    in 5.5.
  - Quick Sync case: the raw YUY2 or NV12 frame (a new object) goes to the waiting place. The decode
    thread converts it. Cost: 0.64 / 1.45 ms (YUY2) and 0.59 / 1.61 ms (NV12) at 720p / 1080p
    [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`].
- The conversion uses the decided input range of the camera [D N:85]. Phase 3 specifies the range
  rule.

### 8.8 OpenCV capture as the source (until phase 3) [A42]

- OpenCV already gives BGR. A decode of the re-encoded JPEG of 2.3 would cost time and add loss.
- Thus, while a camera is on OpenCV capture, the waiting place gets the BGR frame of OpenCV as a new
  array. The decode thread writes it as in 8.7 (the `cv2.imencode` case).
- The decode thread is the same. Only its input is different.

### 8.9 libjpeg warnings must not flood the log [A44]

- libjpeg prints a warning to stderr on each decode of the 1080p frames of the generic camera (extra
  bytes before EOI) (N:281-284, N:285-286). It writes to file descriptor 2 directly, outside Python
  logging [NV for OpenCV 5.1.0].
- Step 2b first checks if the log level of OpenCV 5.1.0 controls these lines.
- If it does not, the camera process redirects descriptor 2 to a pipe at start. A thread blocks on
  the pipe. It forwards each different line to the log one time per minute at most, with a count.

### 8.10 No thread spins [D N:88]

- A pure-Python thread that never sleeps makes each decode about 15 times slower (GIL hand-back)
  (N:281-283).
- Rule: each thread in the camera process must wait by a block on a lock, condition, queue or I/O,
  or it must sleep at least 1 ms per loop [A45].
- The OpenCV loop calls `wait_10us()` (`time.sleep(1e-5)`) on each pass while the gate is closed
  (`opencv_camera_loop.py` line 68). That is almost a spin. It is not measured if it slows a decode
  [NV]. Step 2a raises it to at least 1 ms, or replaces it with a blocking wait [A45].
- Condition of the user on [A45]: step 2a first compares the frame timing before and after the
  change on the four test cameras. Step 2a keeps the change only if the grab timing is not worse.
- Tests: T-RING-31 (idle) and T-RING-44 (decode speed under load).
- Status of the 2a code: T-RING-31 fails, and it stays a known failure until the camera loop waits
  in another way. The fix is a blocking wait on the queues of the loop. It belongs to the same
  change as [A45], and the same four-camera timing comparison decides both [A60].

## 9. Mode list and per-camera info

This section gives only what the ring needs. Native capture (phase 3) makes the mode list.

- Each mode has a resolution, a frame rate and a format, for example "720p30 MJPG" [D N:53].
- YUY2, NV12 and RAW modes have the label uncompressed [D N:53]. There is no "not recommended" label
  [D N:86].
- A resolution and rate that exist in MJPG and YUY2 are in the list two times. The consumer picks.
  MJPG is the default [D N:53].
- H.264 modes are in the list. skellycam never selects them [D N:54]. Bayer RAW and other
  uncompressed formats are in the list. skellycam does not select them [D N:80].

Records [A46, A47]:

| `CameraMode` field | Type |
|---|---|
| `width`, `height` | int |
| `fps_num`, `fps_den` | int |
| `format` | str: `MJPG`, `YUY2`, `NV12`, `H264`, `RAW`, ... |
| `uncompressed` | bool |
| `selectable` | bool (false for H.264 and RAW) |

| `CameraRingInfo` field | Type |
|---|---|
| `camera_id`, `camera_index` | str, int |
| `mode` | `CameraMode`, the mode in use |
| `jpeg_ring_name` | str [D N:76] |
| `bgr_ring_name` | str or None [D N:76] |
| `rotation_cw_deg` | int, the current config value; the own value of each frame is in its slot header [D N:73] |

Width, height, frame rate and format are also in the ring header [D N:74]. In 2a, the mode list
holds only the opened mode, with the FOURCC of the config as its format [A47].

## 10. Concurrency and platform assumptions

- One writer thread per ring [D N:13 one block; the one-writer rule is A8]. The creator writes only
  the static fields before it publishes the name, and `closed` at the end.
- Many readers, in any process. Readers never write to the block.
- There are no locks between processes. No reader can slow the writer.
- Python has no memory fence or atomic API (N:149-151). The stores of the writer can become visible
  to a reader in any order. This is most likely on Apple Silicon, which does not keep the store
  order of Intel.
- Why copy-then-CRC is safe without ordering: the reader checks its private copy, not shared memory.
  It accepts a frame only if the copied header passes its CRC and holds frame number k, and the
  copied payload agrees with the `payload_crc32` of the header [D N:24-25]. Each mix of old and new
  bytes fails one check, except by a CRC-32 collision (probability 2^-32 per torn copy that gets to
  R12). The bytes that the reader uses are the bytes that it checked (N:150-151).
- `head` is only a hint (6.2). It does not matter for correctness if numpy emits single 8-byte loads
  and stores [NV N:317].
- Not verified on ARM: the full argument has never run on Apple Silicon or arm64 Linux
  [NV N:151, P:111-112]. T-RING-34 and T-RING-35 test it.
- Not verified: first-touch paging and commit behaviour of `multiprocessing.shared_memory` on each
  OS [NV N:318]; CRC speed on Python 3.13, macOS or ARM [NV N:319].

## 11. Performance budget

### 11.1 Measured

| Item | Number | Source |
|---|---|---|
| CRC-32, 100 kB | 42 to 46 µs | [M N:152-153, scratch benchmark, Python 3.12.13, zlib 1.3.1, i7-14700K] |
| CRC-32, 210 kB | 53 to 71 µs | same |
| CRC-32, 540 kB | 178 to 195 µs | same |
| Copy out of shared memory, 100 / 210 / 540 kB | 2.8 / 7.1 / 31.6 µs | same |
| BGR copy into a slot, 720p / 1080p | 0.07 / 0.21 ms | [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`] |
| `cv2.imdecode`, one thread, 720p / 1080p | 2.60 / 5.42 ms median | [M `research/frame_ring_buffer/decode_bench/FINDINGS.md`] |
| `cv2.imdecode`, 8 processes, 720p / 1080p | 3.17 / 7.11 ms median | same |
| `cv2.imencode` q90, 720p / 1080p (2a interim feed) | 1.53 / 2.97 ms (4:2:0) | [M `research/frame_ring_buffer/encode_bench/FINDINGS.md`] |

### 11.2 Extrapolated

| Item | Number |
|---|---|
| CRC-32 of a BGR frame, 720p / 1080p | about 0.9 / 2 ms [NV N:140] |
| JPEG writer per frame, largest 1080p frame (copy + CRC) | about 0.25 ms [NV] |
| BGR decode thread per 1080p frame (decode + copy + CRC) | about 7.7 ms, against a 16.7 ms period at 60 fps [NV] |
| BGR reader per 1080p frame (copy + CRC) | about 2.3 ms [NV] |

### 11.3 Measurements that phase 2 makes before it fixes a number [A49]

| ID | Measurement | Step |
|---|---|---|
| M1 | CRC-32 on JPEG sizes on Python 3.13.18, Windows | 2a |
| M2 | Writer cost per frame (p50, p99), JPEG, 720p and 1080p, 1 and 16 writer processes | 2a |
| M3 | Reader cost per frame, JPEG, with 1 and 4 readers per ring | 2a |
| M4 | Resident and committed memory after creation and after one lap, per OS | 2a |
| M5 | CRC-32 on BGR frames, 720p and 1080p, Python 3.13.18 [D N:63] | 2b |
| M6 | Decode thread CPU and BGR skip rate at 720p60 and 1080p60, 4 and 8 camera processes | 2b |
| M7 | Capture-thread timing jitter while the decode thread runs (does `zlib.crc32` release the GIL? [NV]) | 2b |
| M8 | M1, M3 and M5 on an Apple Silicon Mac | 2a, 2b |

Provisional targets. The measured numbers will replace them [A48]:

- JPEG write: p99 at most 0.5 ms per frame at 1080p, with no reader load. With four readers that
  read as fast as they can (the p99 case of T-RING-23), p99 at most 1.0 ms [A59].
- JPEG read: p99 at most 0.5 ms per frame at 1080p.
- BGR write, decode not included: p99 at most 3 ms at 1080p.
- BGR read: p99 at most 3 ms at 1080p.

Phase 2 must not consider a method that is cheaper than copy-then-CRC for BGR before M5 is done
[D N:63].

## 12. Test list

No test needs a camera, except T-RING-49 (optional). "Synthetic payload" means bytes that are a
function of the frame number. Thus a wrong frame is detectable (N:304-305). "Synthetic JPEG" means a
frame that `cv2.imencode` makes from a generated image, 4:2:0 and 4:2:2 (AGENTS.md: no camera
frames in git). The user accepted the pass thresholds [A50]. They can be reopened when the tests
are written.

| ID | Step | Purpose | Method | Pass rule |
|---|---|---|---|---|
| T-RING-01 | 2a | Layout | Check every offset, size and type of tables 3.3 and 3.4 with `struct.calcsize` and the numpy dtype. | All match; slot header is 64 bytes; `head` at 128. |
| T-RING-02 | 2a | Independent parser | A test-only `struct` parser reads a block written by the writer. | All fields equal what the writer was given. |
| T-RING-03 | 2a | Slot capacity | Formula for 640x480, 1280x720, 1920x1080, 3840x2160, JPEG and BGR. | Values of table 3.6. |
| T-RING-04 | 2a | Slot count and size | History 1 s at 30 and 60 fps; history 0.01 s; fps unknown. | Table 3.8; minimum 2 slots; unknown fps uses 60 and logs it. |
| T-RING-05 | 2a | Round trip | Synthetic payloads of 0, 1, random and `slot_capacity` bytes. | Each read is `OK` with identical bytes. |
| T-RING-06 | 2a | Oversize | Payload of `slot_capacity + 1`. | Slot bytes unchanged; `OVERSIZE` set; counter 1; reader gets `OVERSIZE`, no payload. |
| T-RING-07 | 2a | Read results | Empty ring; `k > head`; `head - k >= N`; skipped number; closed ring; a committed frame whose slot header then holds `frame_number = -1` [A58]. | `NOT_YET_WRITTEN`, `NOT_YET_WRITTEN`, `LAPPED`, `MISSING`, `CLOSED`, `LAPPED`. |
| T-RING-08 | 2a | Adversarial lap | Unthrottled writer process; slot counts 2, 8 and 60; readers at the oldest, the newest and by number; 60 s for each slot count, thus 3 minutes in total (N:306-307) [A57]. | Zero wrong bytes accepted; at least one torn copy detected (proves the race ran). |
| T-RING-09 | 2a | Reordering injection | Test writer publishes the header and `head` before the payload; and writes the payload in halves with a sleep between (N:308-309). | No read returns `OK` with wrong bytes. |
| T-RING-10 | 2a | Bit flip | Flip one payload bit after commit; separately one header bit. | `CORRUPT` both times (6.4). |
| T-RING-11 | 2a | Writer killed | Kill the writer process in the middle of a payload copy (N:311). | That frame never reads `OK`; earlier frames still read `OK`; no reader hangs. |
| T-RING-12 | 2a | Reader killed | Kill a reader in the middle of a copy (N:311). | Writer timing unchanged (p99 within 10 %); other readers unaffected. |
| T-RING-13 | 2a | Nearest to t | Two writers at 30 and 60 frames/s with known arrival times; 1,000 random t (N:312). | Expected frame every time; ties go to the lower number. |
| T-RING-14 | 2a | Newest under load | Writer at 60 frames/s, reader asks for the newest 10,000 times. | Always `OK` or one retry; frame number never goes back. |
| T-RING-15 | 2a | Writer one-copy | `tracemalloc` over 1,000 synthetic writes with preallocated payloads (N:237-238). | No allocation of 1 KiB or more in the write path; under 1 KiB in total per frame. |
| T-RING-16 | 2a | Reader one-copy | `tracemalloc` over 1,000 reads. | One allocation of about `payload_len` per read; the returned object is that allocation. |
| T-RING-17 | 2a | Capture check | Synthetic JPEGs: no SOI; no EOI; length mismatch; driver error; 1 KiB of `00` and of `FF` after EOI; 601 junk bytes before EOI. | Flags per 5.2; the last three are accepted unflagged. |
| T-RING-18 | 2a | **Cut-off frame never reaches a reader unflagged (critical)** | Cut synthetic JPEGs (4:2:0 and 4:2:2, with and without restart markers) at every 1 % of their length and at `len - 1`; also cut and zero-filled back to full length. Run each through check, write, read. | Every one reads `FLAGGED` with `NO_SOI_EOI` and `payload = None`. The reader API has no call that returns a flagged payload. |
| T-RING-19 | 2a | Huffman tables | Strip the DHT segment from a synthetic JPEG. Also a frame that has DHT. | Inserted before SOS; decodes with `cv2` to the pixels of the original; `DHT_INSERTED` and counter set. A frame with DHT is the same object (no copy). |
| T-RING-20 | 2a | Error-flag rule | Commit frames with each error flag; read by number, newest and nearest. | No lookup returns a payload for them. |
| T-RING-21 | 2a | Rotation | Config enum to `rotation_cw_deg`; change 0 to 180, 0 to 90, 90 to 270. | Values 0/90/180/270 as Python `int`; `DISCONTINUITY` only on the 0 to 90 change. |
| T-RING-22 | 2a | Self-check | Feed frames at 20 %, 51 % and 60 % of the slot. | One warning at the 51 % frame; periodic log line with the fraction; counters match. |
| T-RING-23 | 2a | Recorder first; no blocking | Instrumented recorder queue and ring; 4 readers hammering the ring. | Queue put precedes every ring write; write p99 within the M2 target for that load (1.0 ms [A59]); a failing ring write leaves the queue unaffected. |
| T-RING-24 | 2a | Skipped write | Fake capture layer reports a newer frame waiting. | `skipped_count` up; reader gets `MISSING` for that number. |
| T-RING-25 | 2a | Creation and names | Start a session with fake cameras. | Total and per-ring sizes logged; names in `CameraRingInfo`; a reader attaches by name alone; header matches the config. |
| T-RING-26 | 2a | Recreation | Change the resolution of a fake camera. | New name; old ring `closed = 1`; old readers get `CLOSED`; old segment gone after unlink (Linux: no `/dev/shm` entry; Windows: open by name fails). |
| T-RING-27 | 2a | Normal cleanup | Session start and stop, per OS. | No ring name left. |
| T-RING-28 | 2a | Crash cleanup | Kill the main process (Linux, Windows, macOS); on Linux also kill the tracker, then start again. | Windows: gone when processes exit. Linux: tracker unlinks; after a group kill, the sweep removes it. macOS: result recorded [NV]. |
| T-RING-29 | 2a | Too-large request | Ask for a history that cannot fit (Linux: a small tmpfs mounted for the test). | Session does not start; message has the total in bytes and MiB; no ring left. |
| T-RING-30 | 2a | Reader exit | A reader process attaches and exits (Linux, macOS). | Ring still readable by another process. |
| T-RING-31 | 2a | No spinning thread, idle | Camera process with a fake capture source, paused for 5 s. | Process CPU under 2 % of one core. Known failure in 2a [A60]. |
| T-RING-32 | 2a | Old code gone | Import the deleted modules; search for the deleted names. | Imports fail; no names left outside history docs. |
| T-RING-33 | 2a | Interim UI relay ([A4]) | Fake cameras; capture one websocket message. | JPEG bytes in the message equal the bytes of the ring. |
| T-RING-34 | 2a | Apple Silicon | Run T-RING-05 to T-RING-14, T-RING-28 and T-RING-30 on an Apple Silicon Mac [D P:111-112, P:174, N:313]. | All pass. |
| T-RING-35 | 2a | arm64 CI | Same set on an arm64 Linux CI runner [D N:313; runner A51]. | All pass. |
| T-RING-36 | 2b | BGR suite | T-RING-05, 07 to 14 with BGR payloads at 640x480 and one 1920x1080 case [D N:88]. | As the JPEG rules; T-RING-06 does not apply (no oversize guard). |
| T-RING-37 | 2b | BGR request | Config with and without `bgr_ring`. | Ring and name only when asked; size logged. |
| T-RING-38 | 2b | Slow decode skips | Decoder stub that sleeps 100 ms; synthetic capture at 60 frames/s [D N:88]. | JPEG ring gets every frame; capture interval p99 unchanged within 10 %; BGR skips counted; BGR frames are a subset. |
| T-RING-39 | 2b | Flagged JPEG frame | Feed a frame with `NO_SOI_EOI`, one with `CAPTURE_ERROR` [D N:88]. | BGR slot flagged, no pixels; decoder call count 0. |
| T-RING-40 | 2b | Both rings match | 10,000 frames; read every number from both rings [D N:61, N:88]. | Equal `frame_number`, `arrival_ns`, `sample_ns`; BGR `published_ns` not earlier than that of the JPEG. |
| T-RING-41 | 2b | Decode failure | A JPEG with valid SOI and EOI that `cv2.imdecode` rejects; one that decodes to the wrong size [D N:88]. | `DECODE_ERROR`; counter up; no pixels. |
| T-RING-42 | 2b | BGR writer one-copy | `tracemalloc` over the write step (decode excluded). | No allocation of 1 KiB or more. |
| T-RING-43 | 2b | BGR read type | Read a BGR frame. | Writable `ndarray`, `(h, w, 3)`, uint8; `np.shares_memory` with the block is false. |
| T-RING-44 | 2b | No spinning, under load | Time a reference decode in the decode thread while the capture stub runs, against the same decode alone [D N:88]. | At most 1.3 times the isolated time. |
| T-RING-45 | 2b | One OpenCV thread | Query in the camera process. | `cv2.getNumThreads() == 1`. |
| T-RING-46 | 2b | Log flooding | Decode 1,000 JPEGs with extra bytes before EOI. | At most one log line per distinct message per minute, with a count. |
| T-RING-47 | 2b | Uncompressed path | Synthetic YUY2 and NV12 frames; BGR ring requested; both hand-over cases of 8.7. | BGR matches a reference conversion; ring array never shares memory with the recorder buffer; BGR skips leave the encoder path untouched. |
| T-RING-48 | 2b | BGR on ARM | T-RING-36 on Apple Silicon and on arm64 CI. | All pass. |
| T-RING-49 | 2a | Four-camera smoke (optional; needs cameras and the user) | Four cameras at 720p30, 10 min, UI open. | Oversize 0; cut-off count logged; UI shows all four; no traceback. |

## 13. Open questions and unverified items

Open questions:

1. The interim of 2.3: is a preview gap from 2a to phase 4 acceptable, or should the relay be built
   [A4]? The plan deletes the frontend-payload calls in phase 2 (P:27-28) and builds the preview in
   phase 4. The user accepted [A4] (the relay) on 2026-11-18.
2. Should a flagged JPEG frame go to the recorder (phase 5)? The ring spec only passes the flags on
   [A22].
3. How does the capture layer tell the writer that a newer frame is waiting (5.3)? This is a detail
   of phase 3 [A23].
4. On macOS, a ring that a killed tracker leaked cannot be found. Accept this, or keep a list of
   names on disk?
5. Does skellytracker write into a BGR array that it gets (6.6)? The writable array covers either
   answer.
6. Does any USB camera pad after EOI with bytes other than `00` or `FF`? Rule 5.2.2 would flag such
   frames as cut-off, and skellycam would never decode them. The self-check count would show it.
7. Should the OpenCV interim (2a) mark its cameras so that FreeMoCap would ask for BGR? This
   question is moot while FreeMoCap does not use this branch [D P:28-29].

Not verified [NV]:

- No prototype of this layout has run (N:320).
- The Apple Silicon safety argument; arm64 Linux.
- CRC speed on Python 3.13.18, on macOS, on ARM; CRC on BGR frames.
- Whether `zlib.crc32` releases the GIL on large buffers.
- First-touch paging and commit per OS; `SharedMemory.size` rounding.
- Windows mapping lifetime after a crash; Linux resource-tracker cleanup in the process tree of
  skellycam; macOS behaviour after a crash and on a too-large request.
- The Linux tmpfs `SIGBUS` on a full `/dev/shm`.
- The macOS 31-byte name limit.
- Whether the log level of OpenCV 5.1.0 silences the warnings of libjpeg.
- Slot size above 1080p; decode speed on Linux, macOS and other CPUs.
- That `perf_counter_ns` is system-wide on macOS.

Conflicts between the sources, and how this spec resolves them:

| Conflict | Resolution |
|---|---|
| N:10 and P:25 (11-17) "JPEG only, no BGR" against N:49-65 (11-18) | 11-18 wins; both texts already say so. |
| "Proposed layout" (N:160-217) against N:73 and N:59 | Updated as in 3.10. |
| N:213 "retry once, then lapped" against N:310 "a bit flip gives corrupt" | Retry rule 6.4 [A27]. |
| N:214 and P:117 use "corrupt" for a flagged frame and for a CRC failure | Split into `FLAGGED` and `CORRUPT` [A26]. |
| N:181 `corrupt_count` in the ring header, which readers would write, against one writer | Dropped [A8]. |
| N:58 and N:73 "payload_len the same in every slot" against N:62 "flagged slot has no pixels" | `payload_len` stays; `payload_crc32 = 0` and the flags mark no payload [A21]. |
| N:228-230 "the same object goes to the queue and into the slot" against Q78 DHT insertion (N:29-32) | DHT insertion is the one permitted extra copy [A19, A25]. |
| P:355-356 (§13, waiting item 7) asks whether 3 s is enough | Superseded by 1 s [D N:59]. |

## 14. Accepted decisions

The user accepted items 1 to 51 on 2026-11-18. The user accepted items 3, 4, 17, 18, 23, 26, 27,
29, 32, 36, 37, 42 and 45 one by one. The user accepted items 1, 2, 5 to 16, 19 to 22, 24, 25, 28,
30, 31, 33 to 35, 38 to 41, 43, 44 and 46 to 51 in bulk. Each item accepted in bulk can be reopened
when the tests are written. Item 45 has a condition. The acceptance of items 39 to 45 and of the 2b
parts of other items is not an approval to build step 2b (section 8).

1. Step 2a deletes the six modules, `check_shm_speed.py` and the tests listed in 2.1. It rewrites
   the listed tests against the new ring.
2. The BGR frame record (`create_frame_dtype`, `create_initial_frame_rec_array`) stays for the
   OpenCV loop and the recorder of today until phases 3 and 5. Only its use as the ring slot type
   goes in 2a.
3. Until phase 3, the OpenCV loop encodes each frame with `cv2.imencode` at quality 90 (the default
   4:2:0 of OpenCV). It passes the bytes to the capture check and the JPEG ring writer, on all OSes.
4. In 2a, the websocket relay keeps the wire format of today. It fills it with the ring JPEG of each
   camera, untouched, at the newest frame number that all cameras have. There is no resize,
   re-encode or server rotation until phase 4.
5. In 2a, the performance page reads only the slot-header times (`arrival_ns`, `sample_ns`,
   `published_ns`) until phase 4.
6. In 2a, the OpenCV loop calls the inline recorder of today before the ring write.
7. Step 2a updates `architecture.mdx`. Phase 4 changes the websocket protocol docs and the UI
   parser.
8. The ring header is as in table 3.3: the field names and offsets, one writer (no counters that
   readers write, so `corrupt_count` is dropped), and the added `header_size`, `total_size`,
   `camera_index`, `creator_pid`, `history_ms` and counters.
9. The slot header is as in table 3.4: the names `rotation_cw_deg` and `source_frame_number` (the
   own counter of the capture layer, or -1); `arrival_ns` from `time.perf_counter_ns()` at the
   capture callback; `published_ns` taken immediately before the commit; the enum mapping
   -1/CW90/180/CCW90 to 0/90/180/270.
10. All fields are little-endian and aligned to their size. Reserved bytes are zero, and readers
    ignore them.
11. `slot_count = max(2, ceil(history_s x fps))` with the frame rate of the opened mode, and 60
    (logged) when capture reports no frame rate.
12. `payload_offset = roundup(4096 + 64 x N, 4096)`; BGR slot stride exactly `width x height x 3`;
    block sizes taken from the header, never from `SharedMemory.size`.
13. `layout_version` is 1. Each layout or meaning change increases it. A reader refuses an unknown
    magic or version with an error that names both.
14. Flag bits as in section 4 (0x01 `OVERSIZE`, 0x02 `CAPTURE_ERROR`, 0x04 `NO_SOI_EOI`, 0x08
    `DECODE_ERROR`, 0x10 `DISCONTINUITY`, 0x20 `DHT_INSERTED`), error mask 0x0F, no `EMPTY` flag.
15. A BGR slot copies the error flags, `DISCONTINUITY` and `source_frame_number` of its JPEG frame.
16. The writer receives, per frame, one `bytes` object plus `frame_number`, `arrival_ns`,
    `sample_ns`, `source_frame_number`, `delivered_len`, `driver_error` and `rotation_cw_deg`
    (table 5.1).
17. Frame numbers start at 0 in each new ring and increase by one per frame that capture delivers.
18. The capture check rules of 5.2: SOI first; the last `FF D9` in the final 4 KiB with only
    `00`/`FF` after it; `len == delivered_len`; a header walk to SOS. Each failure gives
    `NO_SOI_EOI`. A driver error gives `CAPTURE_ERROR`.
19. The ITU-T T.81 Annex K.3 tables fill missing Huffman tables, as one DHT segment immediately
    before the first SOS, with the `DHT_INSERTED` flag and a counter. This is the one permitted
    extra copy.
20. The writer step order W1 to W7 of 5.4: CRC first, `frame_number = -1`, payload copy, header
    packed into a preallocated buffer and written in one 64-byte assignment, then `head`.
21. The writer does not copy a flagged or oversize JPEG (`payload_len` = real length,
    `payload_crc32` = 0). A flagged BGR slot keeps `payload_len = width x height x 3` with
    `payload_crc32` = 0.
22. The capture check is a separate function that runs before the recorder queue. Its flags go with
    the frame to the recorder queue. The ring writer itself does not parse JPEG.
23. The writer skips (and counts) a JPEG ring write when the capture layer already holds a newer
    frame for that camera.
24. The camera process logs the largest frame of each ring as a fraction of its slot at session end
    and every 60 s. It gives a warning one time per camera and session at the first frame above
    50 %.
25. The wording of the one-copy rule of 5.7, and its test: no allocation of 1 KiB or more in the
    write path, under 1 KiB per frame in total, measured with `tracemalloc`.
26. The read results `OK`, `NOT_YET_WRITTEN`, `LAPPED`, `MISSING`, `CORRUPT`, `OVERSIZE`, `FLAGGED`,
    `CLOSED`. The interface note asks FreeMoCap to treat `MISSING` like `LAPPED`.
27. The reader steps R1 to R13 and the retry rule of 6.4 (one retry; identical bad copies give
    `CORRUPT`, all other cases `LAPPED`). Item 58 corrects it.
28. The lookups of 6.5: newest with one retry; by number; nearest to t on `arrival_ns`, only rows
    whose header CRC passes, ties to the lower frame number.
29. The reader returns a frozen `FrameRead`. The JPEG payload is `bytes`. The BGR payload is a
    writable `ndarray (h, w, 3)` that wraps the one `bytearray` copy. `rotation_cw_deg` is a Python
    `int`.
30. Readers attach with `track=False`, read through a read-only view, release views before
    `close()`, and never write to the block.
31. The code goes in `skellycam/core/ipc/frame_ring/`, with `FrameRingWriter`, `FrameRingReader`,
    `ReadResult`, `FrameRead` and `check_jpeg`.
32. The main skellycam process creates and unlinks each ring (as today). Each camera process
    attaches as the writer.
33. Ring names follow `skc<pid hex>_<camera index>_<J|B><generation>`, at most 30 characters.
34. In skellycam, `SetShmMessage` carries a dict of `CameraRingInfo` by camera id. Consumers get the
    same info from the API.
35. The creator sets `closed` = 1 before unlink and before recreation. Readers return `CLOSED`. The
    writer stops writing.
36. On Linux, skellycam compares the free space of `/dev/shm` with the session total before it
    creates rings. If the free space is too small, the session start fails with the size.
37. On Linux, at start, skellycam unlinks each `/dev/shm/skc*` ring whose `creator_pid` is not
    alive.
38. The start log and the too-large message give the total in bytes and MiB and the size of each
    ring.
39. The BGR ring request is the per-camera config field `bgr_ring: bool = False`.
40. The waiting place is a one-item slot that a `threading.Condition` guards. The decode thread
    waits with a timeout of at least 100 ms for shutdown checks. Replacements are counted under the
    lock, and the decode thread copies the count to the BGR ring header.
41. The decode call is `cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)`. A result
    of the wrong shape counts as `DECODE_ERROR`.
42. While a camera is on OpenCV capture, its BGR ring gets a copy of the BGR frame of OpenCV through
    the same waiting place, not a decode of the re-encoded JPEG.
43. Uncompressed hand-over as in 8.7: with `cv2.imencode`, a new array copied from the BGR buffer of
    the recorder path; with Quick Sync, the raw frame, converted on the decode thread with the
    decided range of the camera.
44. libjpeg warnings: first check the log level of OpenCV. If it does not silence them, redirect
    descriptor 2 of the camera process to a pipe. A blocking thread reads the pipe and logs each
    different line one time per minute at most, with a count.
45. No-spin mechanics: each thread of the camera process blocks or sleeps at least 1 ms per loop. In
    2a, the 10 µs wait of the OpenCV loop is raised to at least 1 ms or replaced by a blocking wait.
    Condition: step 2a first compares the frame timing before and after the change on the four test
    cameras. Step 2a keeps the change only if the grab timing is not worse.
46. `CameraRingInfo` has the fields of section 9.
47. `CameraMode` has the fields of section 9. In 2a, the list holds only the opened mode, with the
    FOURCC of the config as its format.
48. The provisional performance targets of 11.3 stay until the measurements replace them.
49. Phase 2 makes measurements M1 to M8 before it fixes a performance number.
50. The pass thresholds in the test table of section 12.
51. The arm64 CI run uses the `ubuntu-24.04-arm` runner of GitHub, pinned by exact label.

The user accepted items 52 to 57 on 2026-11-18, after the first 51. They are clarifications
([ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md)).

52. Unknown frame rate: the slot count uses 60 (item 11). The ring header then holds `fps_num = 0`
    and `fps_den = 1`, which means "unknown".
53. A skipped frame number that a reader asks for before the ring has wrapped one time reads as
    `LAPPED`, not `MISSING`. This behaviour is accepted.
54. The generation in a ring name counts up per skellycam process, not per session. A name is never
    used again while the app runs.
55. The first frame of a new ring does not get `DISCONTINUITY`.
56. Step 2a does not delete `core/types/frontend_payload_bytearray.py`. The file keeps only the
    wire-format types that the interim relay (item 4) needs. Its resize and encode functions are
    deleted. This corrects the count of six modules in item 1 and section 2.1 to five modules and
    a part of this file.
57. T-RING-08 runs 60 s for each slot count (2, 8 and 60), thus 3 minutes in total at the full
    duration.

The user accepted items 58 and 59 on 2026-11-18, after items 52 to 57. They are corrections
([ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md)).

58. A reader copy of a slot header that holds `frame_number == -1` gives `LAPPED`. The reader
    decides this before any CRC check, on the first copy or on the retry (R5, 6.4). Before this
    correction, a reader that asked for frame k while the writer overwrote its slot got `CORRUPT`
    through the retry rule: -1 also breaks the header CRC. This also covers a writer that was killed
    in mid-write. `CORRUPT` now means only: the slot is not being written, and its stored bytes
    fail a CRC check two times with identical copies.
59. The provisional JPEG write target (p99 at most 0.5 ms at 1080p) stays for a writer with no
    reader load. With four readers that read as fast as they can (the p99 case of T-RING-23), the
    target is 1.0 ms. Measured on a Windows test machine: 0.58 to 0.64 ms under that load, and
    0.28 ms without it.

The user accepted items 60 to 62 on 2026-11-18, after items 58 and 59. They are decisions on the
finished 2a code ([ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md)).

60. T-RING-31 (idle CPU, limit 2 % of one core) stays failing as a known failure until the waiting
    of the camera loop is redesigned. The fix is a blocking wait on the queues of the loop. It
    belongs to the same change as item 45 (the 10 µs wait), and the same four-camera timing
    comparison decides both. Measured on 2026-11-18: the paused loop uses 3.9 to 7.0 % of one core.
    The loop sleeps 1 ms and makes two queue polls in each pass. A 10 ms wait gave 0.3 to 4.7 %.
    Windows counts CPU time in steps of 15.6 ms.
61. The translated copies of the architecture page (`zh-CN`, `es`, `ar`) are not updated in step 2a.
    The translation process updates them.
62. Three additions of the 2a code are accepted. `run_opencv_camera_loop` has an optional argument
    `shm_subscription`, through which the loop receives the new ring name after a mode change. At a
    recreation, the creator unlinks the old ring at once and does not wait for its writer to detach
    (an attached process keeps its mapping). `FrameRingWriter.name` is public, and `NO_SAMPLE_NS`
    is exported.
