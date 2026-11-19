# 9G2W — Python API of the frame ring, as the 2a tests assume it; clarifications, corrections and decisions on the 2a code

**Status:** accepted, 2026-11-18 (user; commit to dom/native-jpeg; was proposed, 2026-11-18 (agent)).

## Decision

[ADR-50G8](50G8-phase-2-frame-ring-spec.md) accepts [`specs/frame-ring.md`](../../specs/frame-ring.md).
The spec does not give each Python signature. The failing tests of step 2a in
`skellycam/tests/frame_ring/` use the signatures below. An agent chose them. The user accepted all
16 items on 2026-11-18. Each name is in `skellycam.core.ipc.frame_ring`, except items 13 to 15.

1. `FrameRingCreator.create(*, camera_id, camera_index, pixel_format, width, height, fps_num,
   fps_den, history_s=1.0, generation=0)`. It has `name` and `total_size`. It writes
   `creator_pid`, `utc_ns`, `perf_ns` and `utc_offset_s` itself. If `fps_num` or `fps_den` is not
   above 0, the ring uses 60 (3.7).
2. `creator.set_closed()` writes `closed = 1`. `creator.close_and_unlink()` sets `closed`, closes
   the handle and unlinks.
3. `FrameRingWriter.attach(name)`, `writer.write(payload, *, frame_number, arrival_ns, sample_ns,
   source_frame_number, flags, rotation_cw_deg, newer_frame_waiting=False) -> None`,
   `writer.log_largest_payload()`, `writer.close()`. `flags` comes from `check_jpeg`. The writer
   adds `OVERSIZE` and `DISCONTINUITY`. `newer_frame_waiting=True` skips and counts the write
   (5.3). On `closed = 1`, `write` does nothing.
4. `FrameRingReader.attach(name)` raises `ValueError` on a wrong `magic` or `layout_version`.
   `reader.read(frame_number)`, `reader.read_newest()` and `reader.read_nearest(t_ns)` return
   `FrameRead`. `reader.failed_checks` counts the failed R5, R10 and R12 checks. `reader.close()`.
   No other public call exists.
5. `check_jpeg(payload, *, delivered_len, driver_error) -> (payload, flags)`. The payload is the
   same object, except after a DHT insertion.
6. `ReadResult` is an `enum.Enum` with the eight names of 6.3. `FrameRead` has the fields of 6.6,
   in that order.
7. `PixelFormat` (`IntEnum`: `JPEG = 1`, `BGR24 = 2`), `FrameFlag` (`IntFlag`, the six names of
   section 4), `ERROR_FLAGS = 0x0F`, `MAGIC`, `LAYOUT_VERSION`, `RING_HEADER_SIZE`,
   `SLOT_HEADER_SIZE`.
8. `RING_HEADER_DTYPE` and `SLOT_HEADER_DTYPE`: numpy dtypes with the field names of tables 3.3 and
   3.4. `RING_HEADER_FORMAT` and `SLOT_HEADER_FORMAT`: `struct` formats that start with `<`. The
   reserved bytes are pad bytes (`x`).
9. `slot_capacity(pixel_format, width, height)`, `slot_count(history_s, fps)` and
   `ring_total_size(slot_count, slot_capacity)`. `slot_count` logs the value 60 when `fps` is
   `None` or not above 0.
10. `rotation_to_cw_deg(rotation: RotationTypes) -> int`.
11. `sweep_stale_rings() -> list[str]` (Linux) returns the names that it unlinked.
12. `create_session_rings(camera_configs, history_s=1.0) -> dict[camera_id, FrameRingCreator]`. It
    logs the sizes, checks `/dev/shm` on Linux and allocates. On a failure, it unlinks the rings
    that it made and raises `MemoryError`.
13. `CameraGroup.ring_infos: dict[camera_id, CameraRingInfo]`.
14. `run_opencv_camera_loop(ring_writer=...)` replaces the argument `camera_shm`. The other
    arguments do not change.
15. The interim relay (A4) keeps `CameraGroupManager.get_latest_frontend_payloads` and the
    `FRONTEND_*_DTYPE` wire format of `core/types/frontend_payload_bytearray.py`.
16. A size in a log line or an error message is `n` or `f"{n:,}"` bytes and
    `f"{n / 2**20:.1f} MiB"`. The largest-payload line holds the fraction as `0.60` or `60 %`.

The user also decided, on 2026-11-18, six clarifications (items 52 to 57 of the spec), two
corrections (58 and 59) and three decisions on the finished 2a code (60 to 62). On 2026-11-19 the
user decided five more (63 to 67). Section 14 of the spec states each one in full. In short:

1. Unknown frame rate: 60 slots, and the header holds `fps_num = 0`, `fps_den = 1`.
2. A skipped frame number before the first wrap reads as `LAPPED`.
3. The generation in a ring name counts per process.
4. The first frame of a new ring has no `DISCONTINUITY`.
5. `frontend_payload_bytearray.py` stays with its wire-format types only.
6. T-RING-08 runs 60 s for each slot count.
7. A slot header copy with `frame_number == -1` gives `LAPPED` before any CRC check.
8. One JPEG write target: p99 at most 1.0 ms at 1080p for a writer paced at 60 frames per second,
   with or without readers. M2 is closed (items 59 and 66).
9. T-RING-31 (idle CPU) is a known failure until phase 3. The redesign of the wait of the OpenCV
   loop is dropped (items 60 and 65).
10. The translated copies of the architecture page are not updated in 2a.
11. `run_opencv_camera_loop` has the optional argument `shm_subscription`. `FrameRingWriter.name`
    is public, and `NO_SAMPLE_NS` is exported.
12. The build of step 2b is approved: tests first, then the review of each open point, then the
    code. The decode path is built and tested on synthetic JPEGs now (items 63 and 64).
13. T-RING-34 (Apple Silicon) is on hold for the certify suite of a later task. T-RING-35 (arm64
    CI) is not decided (item 67).

## Reason

- The tests must fix one signature for each call that they make. The user decides the API
  before the 2a code, as for each item of the spec.
- Each choice is the smallest that the tests need. The spec fixes the rest.
- `failed_checks` lets T-RING-08 detect a torn copy through the public API. Section 3.10 lets
  readers count their own results.
- Items 13 to 15 are the seams that T-RING-25 to 27, T-RING-23, T-RING-31 and T-RING-33 need
  outside the ring package.
- The clarifications fix points that the tests or the code must decide and that the spec left
  open. This entry holds them because its commits are not pushed (Rules of the index).

## Alternatives rejected

- Put the signatures into the spec: the spec is accepted. A new choice goes in a proposed entry.
- A writer that parses JPEG: A22 keeps `check_jpeg` separate.

## Open work

See [open-work.md](../open-work.md).
