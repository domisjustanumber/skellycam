# JPEG ring: design notes for the phase 2 spec (2026-11-17)

Status: input for the phase 2 spec, not the spec. The decisions marked **[D]** are Dom's, from the grilling
session of 2026-11-17 (see `../../NATIVE_JPEG_CAPTURE_PLAN.md` §4). The layout below is a **proposal** from a
sub-agent's design study of the same day; no prototype of it exists. Phase 2 writes the spec and the test
list for Dom's review before any code.

## Decided

- [D] The ring carries JPEG only. No BGR mode, no legacy read call, no decode helper.
- [D] Fixed slots, one shared-memory block per camera: ring header, table of 64-byte frame headers, JPEG slots.
- [D] No lossless reader cursors. The recorder does not read the ring (it is a writer thread in the camera
  process, fed by a queue). The ring serves the UI and FreeMoCap.
- [D] Slot size = `2 x (2,048 + 0.5 x width x height)` bytes, rounded up to 4 KiB, from the resolution only.
  Evidence: `../jpeg_bound/FINDINGS.md`.
- [D] Oversize guard: the writer checks each frame's length; a frame that does not fit is not copied, its slot
  is flagged oversize, a counter goes up. The ring also carries the driver's error flag.
- [D] Self-check: log each camera's largest frame as a fraction of its slot, warn above 50 %, show the
  oversize count in the UI.
- [D] About 3 seconds of history per camera, as a setting.
- [D] Every reader copies the frame out, then checks a CRC-32 of the header and of the JPEG. One read path on
  all three OSes.
- [D] Frame headers carry capture times; the ring offers "frame nearest to time t". FreeMoCap groups frames
  itself.
- [D] The UI rotates when drawing, from a rotation value in the frame header.
- Phase 2 also affects the image preprocessing in skellytracker; Dom sets up a skellytracker session to
  coordinate with.

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
