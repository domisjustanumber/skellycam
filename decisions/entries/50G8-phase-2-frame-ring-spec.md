# 50G8 — Phase 2 follows the frame ring spec: two rings per camera, copy then CRC-32 reads

**Status:** accepted, 2026-11-18 (user; commit to dom/native-jpeg).

## Decision

Phase 2 of the native JPEG capture work follows [`specs/frame-ring.md`](../../specs/frame-ring.md).
The user accepted the spec and its 51 numbered items on 2026-11-18. Section 14 of the spec lists the
items. The main rules are:

1. Two rings per camera: one JPEG ring always, and one BGR ring only when the per-camera config
   asks for it (`bgr_ring: bool = False`).
2. One shared-memory block per ring: a 4,096-byte ring header, a table of 64-byte slot headers and
   fixed slots. Each ring has one writer. The main skellycam process creates and unlinks each ring.
3. A reader copies the slot header and the payload out. Then it checks `header_crc32` and
   `payload_crc32` on its private copy. `head` is only a hint. The same read path runs on Windows,
   Linux and macOS.
4. Recorder first: a frame goes to the recorder queue before a ring write. A ring write never
   blocks or waits. When the camera process is behind, the write is skipped and counted.
5. Error-flag rule: a frame with an error flag (`OVERSIZE`, `CAPTURE_ERROR`, `NO_SOI_EOI`,
   `DECODE_ERROR`; mask 0x0F) must never reach a decoder or tracking. The capture check sets
   `NO_SOI_EOI` and `CAPTURE_ERROR`. A reader returns no payload for a flagged frame.
6. History: 1 second by default, one setting for both rings.
   `slot_count = max(2, ceil(history_s x fps))`.
7. Layout version rule: `layout_version` is 1. Each layout or meaning change increases it by one.
   A reader refuses an unknown `magic` or `layout_version` with an error that names both values.
8. Step 2a (the JPEG ring) comes first: failing tests, then code. The build of step 2b (the BGR ring
   and the decode stage) waits for a separate approval and guidance of the user.
9. Item 45 has a condition. Step 2a compares the frame timing on the four test cameras before and
   after the change of the 10 µs wait of the OpenCV loop. It keeps the change only if the grab
   timing is not worse.
10. Each item that the user accepted in bulk can be reopened when the tests are written. Section 14
    of the spec lists these items.

## Reason

- The user, 2026-11-18: accept the spec with all 51 items, item 45 with the condition above; 13
  items one by one and 38 items in bulk; the spec and the phase 2 work live on `dom/native-jpeg`;
  the 2b build waits.
- The current ring has nine shared-memory segments and 1 GiB per camera. It checks for a lap before
  the copy, not after. An earlier test accepted 39,854 to 41,834 torn frames.
- Python has no memory fence or atomic API. A CRC check of a private copy does not depend on the
  store order: the bytes that the reader uses are the bytes that it checked.
- FreeMoCap takes the native format of each camera. It asks for BGR on cameras in an uncompressed
  mode. The UI and the recorder use JPEG.

## Evidence

Each path is on branch `dom/research` at commit 04322eace of this repository. The spec cites the
lines of `research/frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md` (`N:`) and of
`research/NATIVE_JPEG_CAPTURE_PLAN.md` (`P:`).

- `research/frame_ring_buffer/jpeg_bound/FINDINGS.md`: the largest real JPEG frames fill 0.29 of
  the slot at 720p and 1080p (Kiyo Pro).
- `research/frame_ring_buffer/decode_bench/FINDINGS.md`: `cv2.imdecode` (OpenCV 5.1.0,
  libjpeg-turbo 3.1.2), one thread, 2.60 ms at 720p and 5.42 ms at 1080p; Intel QSV through PyAV
  3.20 and 5.87 ms.
- `research/frame_ring_buffer/encode_bench/FINDINGS.md`: `cv2.imencode` q90 4:2:0, 1.53 ms at 720p
  and 2.97 ms at 1080p; the OpenCV 5.1.0 Python binding refuses a `dst` argument.
- `research/frame_ring_buffer/yuy2_range/FINDINGS.md`: the range flag of the OS for the test
  cameras.
- CRC-32 (Python 3.12.13, zlib 1.3.1, i7-14700K): 42 to 46 µs for 100 kB, 178 to 195 µs for
  540 kB (notes, N:152-153).

## Alternatives rejected

- A JPEG-only ring, one ring per camera (2026-11-17, N:10, N:162): replaced on 2026-11-18. FreeMoCap
  asks for BGR on cameras in an uncompressed mode. A BGR ring has its own slot size and its own
  writer (the decode thread), so it is a separate block.
- Lossless reader cursors (N:14): the recorder does not read the ring. It is a writer thread that a
  queue feeds. The ring serves the UI and FreeMoCap.
- Sequence-number reads: the earlier prototype relied on the store order of Intel. Apple Silicon
  does not give that order (N:149-151, N:241).
- Media Foundation MJPEG decoders: the source reader gives one output type per stream, so the JPEG
  would be lost (N:130-131). Quick Sync decode: slower than `cv2.imdecode` (N:126-129).
- 3 seconds of history: a round number from the old ring (2.87 s at 1080p60). The UI reads the
  newest frame. At 1080p60, 3 s of both rings is 357 + 1,068 MiB per camera (N:116-121, N:135).
- A packed byte ring, pipes, or one segment per frame (N:143-145): more wrap code, no latest-frame
  or fan-out reads, or names that leak on a crash.

## Not repeated

- The range flag of the OS cannot be trusted. Media Foundation reported limited range for the YUY2
  modes of the Kiyo Pro and the generic camera, which send full range.
- A decoder cannot detect a cut-off frame. The GPU decoder of skellytracker returns a full-size
  image with garbage and no error for a JPEG cut at half (N:254-258). Flag it at capture.
- `cv2.imdecode` in Python cannot decode into a given buffer. The BGR writer makes one copy.
- A pure-Python thread that never sleeps slows each decode about 15 times (GIL hand-back)
  (N:281-283).
- Do not check for a lap before the copy. Check the private copy after the copy.

## Open work

See [open-work.md](../open-work.md).
