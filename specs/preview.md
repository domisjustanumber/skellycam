# Phase 4 preview specification: the per-camera websocket message and its sender (4a)

Status: proposed by an agent on 2026-11-19. It waits for the user
([ADR-162X](../decisions/entries/162X-step-4a-preview-spec-and-agent-choices.md)). The user decided
P1 to P7 on 2026-11-19
([ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)). Section 14 gives
each one. The agent choices of section 12 and the questions of section 13 wait for the user. The
failing tests of step 4a come before the product code of step 4a.

## 0. How to read this spec

Marks:

- **[Pn]**: decision n of the user for phase 4, 2026-11-19 (section 14,
  [ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)).
- **[E]**: a binding statement of the user from before P1 to P7 (section 14).
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md), the accepted phase 2 spec
  ([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)). **[ring An]**: item n of
  section 14 of that spec.
- **[cap x.y]**: section x.y of [`windows-capture.md`](windows-capture.md), the accepted phase 3 spec
  ([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)).
- **[M source]**: measured; the source holds the result. **[NV]**: not verified.
- **[agent n]**: an agent filled a gap that P1 to P7, [E] and the earlier specs do not fix. Section
  12, item n, lists each one. Section 13 holds the questions for the user.

This spec uses British spelling. Code names are from branch `dom/preview`, read on 2026-11-19. The
spec cites files, not line numbers. It cites the ring spec and the capture spec. It does not repeat
them.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Phase 4 replaces the group message of the websocket preview with one message for each camera frame
[E]. Each message holds the JPEG of the ring, untouched: no resize, no re-encode [E]. Each camera has
its own flow control. A slow tile does not hold back the other tiles [P2]. The preview does not
depend on the lockstep gate [E].

### 1.2 Scope

| Step | Delivers |
|---|---|
| 4a | The per-camera message (section 3), its sender in Python (sections 4 and 5), the JSON data that the UI needs for P4 (section 6), and the tests against fake rings (section 9) [P1]. No dependency on phase 3 [P1]. |
| 4b | The UI side: the parser, the shared tile, the overlay [P1]. The switch of the websocket endpoint to the sender of 4a, and the deletion of the old group message and its code [P5]. Section 10 lists what 4b must do. It is not a full spec. |

### 1.3 Non-goals

- A resize, a quality setting, a rate cap or a rate setting [E, P2].
- A rotation in the server. The UI rotates when it draws [E].
- A preview from a remote machine. The UI runs on the machine with the cameras [E].
- The BGR ring. The sender reads only the JPEG ring.
- The shared tile. The player spec specifies it as its own module [P6].
- A change of the performance page [ring A5] or of `CameraGroup.read_latest_ring_frames`.
- A change of the capture states or of the status report [cap 8.1, 8.4]. Section 13 holds one
  question about the replaced count.

### 1.4 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| Ring reader, read results, retry rule, lookups | [ring 6.2 to 6.5] | Section 5 uses them as they are. |
| Flag bits and the error mask 0x0F | [ring 4] | Section 3.3 copies the bits. |
| Rotation per frame, `rotation_cw_deg` | [ring 3.4] | Section 3.3 copies the value. |
| What the ring gives the UI: newest lookup, untouched JPEG, rotation per frame, oversize count | [ring 6.6, 5.8] | Sections 3, 5 and 6. |
| Ring recreation on a mode change; `closed` | [ring 7.4, 7.5] | Section 4.4. |
| The interim relay | [ring 2.3, A4], [cap 5.8, U13] | 4b deletes it (section 2.3). |
| Camera states and the status report | [cap 8.1, 8.4] | Section 6 uses them. |
| The shared tile and its decoder (ImageDecoder) | `specs/player.md` on branch `dom/player` [P6] | Section 10 refers to it. |

### 1.5 Terms

| Term | Meaning |
|---|---|
| camera message | One binary websocket message for one camera frame (section 3). |
| sender | The object `PreviewRelay` that reads the rings and sends camera messages for one websocket connection (section 7). |
| connection | One websocket connection of one client. |
| ready | The state of a camera for a connection in which the sender can send its next camera message (section 4). |
| ready message | The JSON message of the client that says "camera X is ready" [P2]. |
| pass | One run of the sender over all cameras (section 4.3). |
| old relay | `WebsocketServer._frontend_image_relay` with `CameraGroup.get_latest_ring_payload`: the group message of today [ring 2.3, cap 5.8]. |

## 2. What 4a adds, what 4b deletes, and how the two coexist

### 2.1 Code that 4a adds [agent 1]

| Path | Content |
|---|---|
| `skellycam/api/websocket/preview_relay.py` | `CAMERA_FRAME_VERSION`, `CAMERA_FRAME_HEADER` (a `struct.Struct`), `pack_camera_frame`, `PreviewRelay` (section 7). |
| `skellycam/core/ipc/frame_ring/reader.py` | Two read-only properties of `FrameRingReader`: `head` and `oversize_count` (section 5.2) [agent 15]. |
| `skellycam/tests/preview/` | The tests of section 9, a fake group manager, and a test route that wires `PreviewRelay` to a websocket as 4b will. |

### 2.2 Code that 4a does not change

- `WebsocketServer` and the endpoint `/websocket/connect` stay as they are. The endpoint keeps the
  old relay and its `frameNumber` acknowledgement [agent 22].
- The UI keeps its parser of the old group message.
- Thus, while only 4a is in the code, the UI shows the preview as today, and the wire carries only
  the old format.

### 2.3 Code that 4b deletes [P5]

| Item (file) | Replacement |
|---|---|
| `WebsocketServer._frontend_image_relay`, `check_frame_acknowledgment_status`, the `frameNumber` branch of `_client_message_handler`, the fields `last_sent_frame_number`, `last_received_frontend_confirmation`, `_last_sent_by_group`, `_display_image_sizes`, `_server_framerate_calculators`, `_display_framerate_trackers`, `_last_framerate_send_time`, `FramerateUpdateMessage`, `BACKPRESSURE_WARNING_THRESHOLD` (`api/websocket/websocket_server.py`) | `PreviewRelay.run` and `PreviewRelay.handle_text` |
| `CameraGroup.get_latest_ring_payload` (`core/camera_group/camera_group.py`) | `pack_camera_frame` |
| `CameraGroupManager.get_latest_frontend_payloads` (`core/camera_group/camera_group_manager.py`) | The sender reads `ring_readers` itself (section 5). |
| `core/types/frontend_payload_bytearray.py` (the whole file) [ring A56] | `CAMERA_FRAME_HEADER` |
| `tests/test_image_payload.py` | T-PRV-01 |
| T-RING-33 in `tests/frame_ring/test_camera_process.py` | T-PRV-02 |
| T-CAP-86 and its helpers `parse_relay` and `_collect` (`tests/capture/`) | T-PRV-09, T-PRV-14, T-PRV-15 |
| `test_websocket_frame_acknowledgment` in `tests/test_websocket.py`; the mock of `get_latest_frontend_payloads` in `tests/conftest.py` | T-PRV-21 |
| The parser of the group message in the UI and its `frameAcknowledgment` message | Section 10 |

`ServerFramerateCalculator` stays. The sender uses it (section 6.2). `read_latest_ring_frames`
stays for `get_latest_performance_data` [ring A5].

### 2.4 One format on the wire, and no time without a preview

P1 puts 4a before 4b. P5 forbids a period with both formats. A preview gap is also not acceptable.
If 4a switched the endpoint, the UI of today could not read the new messages until 4b. If 4a kept
both senders on the wire, both formats would exist at the same time.

The smallest way out [agent 22, Q1]:

1. 4a adds the sender with no route. The live endpoint keeps the old relay (2.2). The 4a tests reach
   the sender through a test route in `skellycam/tests/preview/` (9.1).
2. 4b switches the endpoint, deletes the old code (2.3) and changes the UI in one commit group. No
   commit of the branch sends both formats, and no commit sends a format that its UI cannot read.
3. The branch goes to `development-streaming` only after 4b.

Thus both formats exist only as code on the branch, between 4a and 4b. The new code has no route in
that time. Question Q1 asks the user to accept this.

## 3. The camera message

### 3.1 Conventions

- One binary websocket message holds one camera message: the header, then the JPEG bytes [E].
- Each field is little-endian, as in the ring [ring 3.2]. Each field is aligned to its own size.
- Reserved bytes are zero. A parser ignores them.
- The server copies the fields from the ring slot header and the JPEG from the ring payload. It adds
  no value of its own, except `version` and `jpeg_len` [P3] [agent 2, agent 8].
- Width and height come from the JPEG, not from the header [P3].

### 3.2 Layout (48 bytes, then the JPEG) [agent 3]

| Offset | Size | Type | Name | Value | Source |
|---|---|---|---|---|---|
| 0 | 1 | u8 | `version` | 1 for this spec. It is also the message type. | constant |
| 1 | 3 | | reserved | zero | |
| 4 | 4 | u32 | `flags` | the ring flags, all 32 bits | slot `flags` |
| 8 | 8 | i64 | `frame_number` | the frame number of the camera | slot `frame_number` |
| 16 | 8 | i64 | `arrival_ns` | `perf_counter_ns` at the capture callback | slot `arrival_ns` |
| 24 | 4 | u32 | `rotation_cw_deg` | 0, 90, 180 or 270 | slot `rotation_cw_deg` |
| 28 | 4 | u32 | `jpeg_len` | the number of JPEG bytes after the header; 0 for a flagged frame | `len(FrameRead.payload)`, or 0 |
| 32 | 16 | ASCII | `camera_id` | the camera id, NUL-padded | the key of `ring_readers` |
| 48 | `jpeg_len` | bytes | JPEG | the bytes of the ring, untouched | `FrameRead.payload` |

The Python form is `struct.Struct("<B3xIqqII16s")`. Its size is 48. The message length is
`48 + jpeg_len`.

Example: camera `a1b2`, frame 258, arrival 1,000,000,007 ns, rotation 90, flags 0x30
(`DISCONTINUITY` and `DHT_INSERTED`), and the 4 bytes `FF D8 FF D9` as the JPEG:

```text
 0: 01 00 00 00 30 00 00 00 02 01 00 00 00 00 00 00
16: 07 ca 9a 3b 00 00 00 00 5a 00 00 00 04 00 00 00
32: 61 31 62 32 00 00 00 00 00 00 00 00 00 00 00 00
48: ff d8 ff d9
```

### 3.3 Field rules

- **`version`.** Each change to an offset, a size, a type or the meaning of a field must increase it
  by one. A parser that sees another value must refuse the message and log both values, as
  [ring 3.9] does for the ring [agent 2].
- **`flags`.** A copy of the 32 bits of the slot header [ring 4] [agent 6]. The error mask is 0x0F.
  A frame with an error bit is a flagged frame.
- **`frame_number`.** The ring `frame_number`: "the frame counter of the camera" [ring 1.4]. It is
  not `source_frame_number` [agent 5]. It starts again at 0 in a new ring [ring 7.5].
- **`rotation_cw_deg`.** The value of each frame [ring 3.4]. The UI turns the image by this value
  when it draws [E].
- **`jpeg_len` and the frames that the sender sends** [agent 8]:

  | `FrameRead.result` | Message |
  |---|---|
  | `OK` | The header, then the JPEG. `jpeg_len` is `payload_len`. |
  | `FLAGGED` | The header only. `jpeg_len` is 0. `flags` has the error bit. |
  | `OVERSIZE` | The header only. `jpeg_len` is 0. `flags` has `OVERSIZE`. |
  | each other result | No message (section 5.3). |

  The ring never gives a payload for a flagged frame [ring 4]. Thus the header-only message is the
  only way for the UI to show the mark of P4.
- **`camera_id`.** The ASCII bytes of the camera id, NUL-padded to 16 bytes. Today's ids have 4 hex
  digits [cap 7.2]. If an id is not ASCII or is longer than 16 bytes, the sender sends no message
  for that camera. It logs one ERROR record for each connection and camera that names the id
  [agent 4].

## 4. Flow control [P2]

### 4.1 The ready message [agent 9]

The client sends one text message for each camera message that it has handled:

```json
{"message_type": "camera_ready", "camera_id": "a1b2"}
```

- The client sends it after the tile has drawn the frame [P2]. It also sends it after a header-only
  message, and after a JPEG that it cannot decode. If it does not, the tile of that camera stops.
- A ready message has no frame number [P2].
- A message whose `message_type` is `camera_ready` and whose `camera_id` is not a string: the sender
  logs one WARNING record and ignores the message. The connection stays open [agent 21].
- A ready message for a camera id that the sender does not know: the sender ignores it with no log
  record. The camera can be removed while the message travels [agent 21].
- A ready message for a camera that is already ready: no effect.
- `PreviewRelay.handle_text(text)` returns `True` when the text was a ready message (valid or not),
  and `False` for each other text. Thus the handler of the endpoint keeps `ping` and `pong`.

### 4.2 State of each camera, for each connection

The sender keeps, for each camera id:

| Field | Start value | Meaning |
|---|---|---|
| `reader` | the reader in `ring_readers` | The reader of the last pass. A different object means a new ring. |
| `last_sent` | -1 | The `frame_number` of the last camera message of this ring. |
| `ready` | `True` | The sender can send the next camera message [agent 10]. |
| `rate` | a new `ServerFramerateCalculator` | Section 6.2. |
| `bad_id_logged` | `False` | Section 3.3. |

### 4.3 The rule of the sender

The sender runs passes. A pass starts at most 10 ms after the previous pass. A ready message wakes
the sender at once [agent 13]. In each pass, for each camera of each group in
`CameraGroupManager.camera_groups`, in the order of `ring_readers`:

1. Get the reader from `group.ring_readers`. If the camera has no state, make one (4.2). If the
   reader is a different object, set `reader` to it and `last_sent` to -1. Do not change `ready`
   [agent 12].
2. If `ready` is `False`, go to the next camera.
3. If the camera id does not fit the message (3.3), log it one time (`bad_id_logged`) and go to the
   next camera.
4. If `reader.head <= last_sent`, go to the next camera. There is no new frame. This makes no copy
   (5.2).
5. `read = reader.read_newest()` [ring 6.5].
6. If `read.result` is `OK`, `FLAGGED` or `OVERSIZE`, and `read.frame_number > last_sent`: send the
   camera message (3.2). Then set `last_sent = read.frame_number`, set `ready = False`, and update
   `rate` (6.2).
7. If not, send nothing. The next pass tries again (5.3).

After all cameras, the sender removes the state of each camera id that is no longer in any
`ring_readers`.

Thus the server sends the newest frame that it has not sent, and it skips all older frames [P2].
The sender keeps no queue. A connection has at most one camera message in flight for each camera.

### 4.4 Cases

| Case | What the sender does |
|---|---|
| First frame, before any ready message | Each camera starts `ready` (4.2). The first pass with a frame sends the newest frame [agent 10]. |
| The client never answers for a camera | That camera stays not `ready`. The sender sends nothing more for it and reads nothing from its ring. No time limit [agent 11]. The other cameras continue. |
| The client answers late | The ready message makes the camera `ready`. The sender sends the newest frame at once, or at the first pass with a newer frame. |
| Reconnect | A new connection gets a new sender with new state. Each camera starts `ready`. The old sender ends with its connection. |
| A camera appears (a new camera, a new group, or a reopen with a new process) | A new key in `ring_readers` gets a new state, `ready`. Its newest frame goes out at the first pass with a frame. |
| A ring is recreated (a mode change [ring 7.5], or "apply again" [cap 8.3]) | `CameraGroup` puts a new reader under the same camera id. Rule 4.3 step 1 sets `last_sent = -1`. The next camera message holds a frame of the new ring. Its `frame_number` can be lower than the last one. |
| A camera fails or dies [cap 8.1] | Its ring gets no new frame. Step 3 finds nothing new. The tile keeps the last frame. `app_state` gives the state (section 6). |
| A camera is removed (unselect [cap 8.3]) | Its key leaves `ring_readers`. The sender removes its state. A late ready message for it is ignored (4.1). The UI removes the tile from `app_state`. |
| A ring is closed while its reader is still in `ring_readers` | `read_newest` gives `CLOSED`. No message (5.3). |
| Several clients | Each connection has its own sender and its own state. A slow client does not hold back another client [agent 17]. Each sender reads the rings for itself. |
| The manager closes | While `CameraGroupManager.closing` is `True`, a pass reads nothing and sends nothing [agent 26]. |
| A send fails because the client is gone | The sender ends, as the old relay ends today (`WebSocketDisconnect`, a closed websocket). |

## 5. Ring reads

### 5.1 Process and thread [agent 14]

- The sender runs in the main skellycam process, on the asyncio event-loop thread of the server, as
  the old relay does.
- It reads through the readers that `CameraGroup` already holds in `ring_readers` (the JPEG ring of
  each camera [ring 7.1, A32]). It attaches no reader of its own.
- It gets `group.ring_readers` again in each pass. It never keeps a reader between passes for a read.
  `CameraGroup._close_rings` removes a reader from the dict before it closes it. All of this runs on
  the same thread. Thus the sender never reads through a closed reader.
- Each read is a synchronous call between two `await` points. No other coroutine can close a reader
  during a read.
- The sends of one connection are in series, under the send lock of the connection [agent 27].

### 5.2 Calls

| Call | Exists | Use |
|---|---|---|
| `FrameRingReader.read_newest()` | yes [ring 6.5] | The newest frame: `read(head)`, and one more `read(head)` after `LAPPED`. Each read has the retry rule of [ring 6.4]. |
| `FrameRingReader.head` | new [agent 15] | The `head` field, one 8-byte load, no copy. -1 before the first commit. It is a hint only [ring 6.2]. |
| `FrameRingReader.oversize_count` | new [agent 15] | The `oversize_count` field of the ring header, one 8-byte load [ring 3.3, 5.8]. |

`head` makes step 4 of 4.3 free. Without it, each pass would copy and check the newest frame of each
ready camera again: about 100 copies each second for each camera.

### 5.3 Read results

| Result of `read_newest` | Sender |
|---|---|
| `OK` | Send the header and the JPEG. |
| `FLAGGED`, `OVERSIZE` | Send the header only (3.3). |
| `NOT_YET_WRITTEN` | Nothing. |
| `LAPPED` (after the second `read(head)`) | Nothing. The next pass tries again. |
| `MISSING` | Nothing. (The newest frame cannot be missing. This is a guard only.) |
| `CORRUPT` | Nothing. The next frame is newer and goes out normally. |
| `CLOSED` | Nothing. A new reader replaces it, or the camera leaves `ring_readers`. |

The sender writes no log record for one failed read [agent 16]. The reader counts its failed checks
in `failed_checks`.

### 5.4 No dependency on the gate or on the camera states

- The sender does not call `CameraOrchestrator.all_ready`, `should_grab_by_id` or any other part of
  the orchestrator [E].
- It does not read the camera states. A camera with a new frame in its ring is shown. A camera
  without one is not [cap 8.1: no ring frame in `starting`, `waiting`, `failed`, `dead`].
- It does not wait for equal frame numbers. Each camera is independent [P2].

## 6. State and counts for the UI [P4]

### 6.1 What the UI needs, and where it comes from

| Item [P4] | Source | Message |
|---|---|---|
| Camera label | `configs[camera_id].camera_name` | `app_state` (existing, unchanged) |
| Delivered frame rate of the camera | `source_frame_number` and `arrival_ns` of the frames that the sender reads (6.2) [Q3] | `framerate_update`, new shape (6.2) |
| Phase 3 state | `state` of the camera status [cap 8.4] | `app_state` (existing; phase 3 adds the key) |
| Mark of a flagged frame | `flags & 0x0F` of the camera message | the camera message (3.2) |
| Skipped count | Gaps of `frame_number` between camera messages of one camera [agent 18] | none: the UI counts them (section 10) |
| Replaced count | `replaced_count` of capture [cap 4.1, 5.2] | not available today [Q2] |
| Oversize count | `oversize_count` of the ring header [ring 5.8] | `framerate_update`, new shape (6.2) |

`app_state` stays as it is. The sender of `app_state` sends it at most one time each second, when
it changes. A state change thus shows on the tile within about 1 s.

### 6.2 The new shape of `framerate_update` [agent 19, agent 20]

The sender sends one message for each camera group, every 0.25 s, as the old relay does:

```json
{
  "message_type": "framerate_update",
  "camera_group_id": "g1",
  "cameras": {
    "a1b2": {"delivered_framerate": {"mean_frames_per_second": 29.97, "...": "..."}, "oversize_count": 0}
  }
}
```

- `delivered_framerate` is a `CurrentFramerate` (`core/recorders/framerate_tracker.py`, unchanged),
  or `null` when the window has fewer than 2 frame durations.
- The sender computes it with `ServerFramerateCalculator.update(source_frame_number, arrival_ns)` at
  each camera message (4.3 step 6). When `source_frame_number` is -1 (the OpenCV loop before phase 3
  writes -1), it uses `frame_number` [agent 19]. The formula is exact over skipped frames:
  `(s_b - s_a) / (t_b - t_a)`, as the rate check [cap 10.1].
- After each message, the sender calls `clear()` on each calculator, as the old relay does. Thus
  each value covers the last 0.25 s.
- `oversize_count` is `reader.oversize_count` at the time of the message.
- The message has no `backend_framerate` and no `frontend_framerate`. 4b changes the frame rate
  viewer to the per-camera values [agent 20].
- The sender sends the message only for a group that has at least one camera in `ring_readers`.

## 7. Python API of 4a [agent 1]

```python
CAMERA_FRAME_VERSION: int = 1
CAMERA_FRAME_HEADER: struct.Struct  # "<B3xIqqII16s", size 48

def pack_camera_frame(camera_id: str, read: FrameRead) -> bytes:
    """The camera message of `read` (3.2). `read.result` is OK, FLAGGED or OVERSIZE.
    Raises ValueError for a camera id that is not ASCII or longer than 16 bytes."""

class PreviewRelay:
    def __init__(self, camera_group_manager: CameraGroupManager,
                 send_bytes: Callable[[bytes], Awaitable[None]],
                 send_json: Callable[[object], Awaitable[None]]) -> None: ...
    async def run(self) -> None:
        """Passes (4.3) and framerate updates (6.2) until the task is cancelled."""
    def handle_text(self, text: str) -> bool:
        """A ready message (4.1): mark the camera ready, wake `run`, return True. Else False."""
```

- `pack_camera_frame` builds one `bytes` object: the 48-byte header, then the JPEG. This is one copy
  of the JPEG [agent 25].
- `run` is the only coroutine that sends camera messages. `handle_text` only sets `ready` and an
  `asyncio.Event`. Thus two sends for one camera cannot race.
- `run` gets the manager from its argument. The tests give a fake manager (9.1). The sender uses only
  `camera_groups`, `closing`, the `id` and `ring_readers` of each group.

## 8. Performance

### 8.1 Measured numbers that apply

| Item | Number | Source |
|---|---|---|
| Largest real JPEG, 720p / 1080p (Kiyo Pro) | 276,269 / 607,032 bytes | [ring 3.6] [M] |
| Largest frame in a four-camera run at 720p30 | 0.10 to 0.22 of a 925,696-byte slot (about 93 to 204 kB) | [open-work.md](../decisions/open-work.md), fact of 2026-11-18 [M] |
| Copy out of shared memory, 540 kB | 31.6 µs | [ring 11.1] [M, Python 3.12.13] |
| CRC-32, 540 kB | 178 to 195 µs | [ring 11.1] [M, Python 3.12.13] |
| `zlib.crc32` releases the GIL; the R11 copy holds it | Python 3.13.18, Windows | [ADR-ETJ1](../decisions/entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md) [M] |
| Readers do not make the writer slower | JPEG write p99 0.75 ms at 1080p with four readers | [ring A66] [M] |

### 8.2 Targets of 4a (each one to measure in 4a)

These are estimates from 8.1. No number below is measured.

| Item | Target | Basis |
|---|---|---|
| `read_newest` of a 1080p JPEG, p99 | at most 0.5 ms | the provisional read target of [ring 11.3]; ring measurement M3 is not made. To measure in 4a. |
| `pack_camera_frame` of a 600 kB JPEG, p99 | at most 0.1 ms | one copy of 600 kB, from the copy figure of 8.1. To measure in 4a. |
| Event-loop time of the sender, 4 cameras at 1080p30, one client that answers at once | at most 5 % of one core | 120 frames/s x about 0.3 ms. To measure in 4a. |
| Event-loop time of the sender, no camera ready | at most 1 % of one core with 16 cameras | 100 passes/s x 16 `head` loads. To measure in 4a. |
| Time from `published_ns` to the start of the send, client that answers at once, p99 | at most 25 ms | 10 ms between passes plus the timer step of Windows (15.6 ms) [NV]. To measure in 4a. |
| Frames sent, client that answers at once, 30 fps | each frame (T-PRV-10 allows 5 % loss on a CI runner) | the period (33 ms) is longer than a pass. At 60 fps: to measure in 4a. |

### 8.3 Measurements of 4a

| ID | Measurement |
|---|---|
| M-PRV-1 | `read_newest` time (p50, p99) for 720p and 1080p JPEGs of the largest real size, on Python 3.13.18, Windows. This is ring M3 with one reader. |
| M-PRV-2 | `pack_camera_frame` time (p50, p99) for the same sizes. |
| M-PRV-3 | CPU of the event-loop thread with the sender: 4 cameras at 720p30 and 1080p30; 16 cameras at 1080p60; one client that answers at once; and no camera ready. |
| M-PRV-4 | Time from `published_ns` to the start of the send, p50 and p99, Windows and Linux. The actual interval between passes on Windows. |
| M-PRV-5 | Frames skipped by the sender at 60 fps with a client that answers at once, Windows. |

A script makes them with fake rings and no camera. An evidence entry records the result. The user
decides each target that the result does not meet.

## 9. Tests

### 9.1 Kinds and helpers

- **fake**: a test that calls `PreviewRelay` or `pack_camera_frame` directly, with fake rings and a
  fake manager. It runs on each OS and in CI [P7].
- **ws**: a test that connects a test websocket client (Starlette `TestClient.websocket_connect`) to
  the test route. It runs on each OS and in CI [P7].
- No test needs a camera [P7].

Helpers in `skellycam/tests/preview/` [agent 1]:

- **Fake ring.** A real ring of the ring package in the test process: `FrameRingCreator.create`
  (JPEG), and `FrameRingWriter.attach` as its writer. The test writes synthetic payloads (bytes that
  are a function of the frame number [ring 12]) with scripted `arrival_ns`, `source_frame_number`,
  `flags` and `rotation_cw_deg`. A paced writer thread writes at a given rate. The sender does not
  parse JPEG, so a payload does not have to be a JPEG.
- **Fake manager.** An object with `closing` and `camera_groups`: a dict of objects with `id` and
  `ring_readers` (camera id to `FrameRingReader`). The test can add, replace and remove readers, as
  `CameraGroup` does. It has no orchestrator and no camera.
- **Stub reader.** An object with `head`, `oversize_count` and a scripted `read_newest`, for read
  results that a real ring gives only by chance (`LAPPED`).
- **Test route.** A FastAPI app with one websocket route. It accepts, makes a `PreviewRelay` with the
  send functions of the websocket, runs `run`, and gives each text message to `handle_text`. 4b
  moves these lines into `WebsocketServer`.
- **Independent parser.** A test-only parser that uses `struct.unpack_from` at the offsets of table
  3.2. It does not import `CAMERA_FRAME_HEADER`.

The pass thresholds of 9.2 are [agent 24]. They can change when the tests are written.

### 9.2 Test list

| ID | Kind | Input and action | Pass criterion |
|---|---|---|---|
| T-PRV-01 | fake | `pack_camera_frame` for the example of 3.2; also a `FLAGGED` read with flags 0x04 and one with `OVERSIZE`. Check `CAMERA_FRAME_HEADER.size` and the offset of each field. | The bytes equal the example of 3.2, byte for byte; the flagged messages are 48 bytes with `jpeg_len` 0 and the ring flags; size 48; offsets of table 3.2. |
| T-PRV-02 | ws | Three fake rings at 30 fps for 5 s; the client answers at once. A second reader per ring reads each received `frame_number`. | Each field that the independent parser reads equals the slot field of that frame; the JPEG bytes equal the ring payload (the rule of T-RING-33). |
| T-PRV-03 | fake | Frames with each flag bit 0x01 to 0x20, and with 0x30 and 0x14. | Each message has the 32 bits of the slot; 0x10, 0x20 and 0x30 carry the JPEG; each frame with a bit of 0x0F has `jpeg_len` 0 and no bytes after the header. |
| T-PRV-04 | ws | One ring; rotation 0, then 90, 180, 270, 0 on consecutive frames; the client answers at once. | Each message has the rotation of its own frame. |
| T-PRV-05 | ws | Camera ids `a1b2`, `abcdefghijklmnop` (16), `abcdefghijklmnopq` (17) and `cámara`. | The first two are sent, NUL-padded to 16 bytes; the last two get no message and one ERROR record each for the connection; the first two are not affected. |
| T-PRV-06 | ws | Two rings with frames 0 to 9; connect; send no ready message; the writers continue for 1 s. | Exactly one message per camera, frame 9 or newer, within 1 s of the connect; no other message in that second. |
| T-PRV-07 | ws | After T-PRV-06: pause the writers at frame 20; send a ready message for one camera. | One message for that camera, frame 20; none for the other camera. |
| T-PRV-08 | ws | A ready message while `head` equals the last sent frame; then write one frame. | No message before the write; one message with the new frame within 100 ms after the write. |
| T-PRV-09 | ws | Three rings at 30 fps for 5 s; the client answers at once for cameras A and B; it never answers for camera C. | A and B each get at least 95 % of the frames written in that time; C gets exactly one message. |
| T-PRV-10 | ws | Four rings at 30 fps for 10 s; the client answers at once. | Each camera gets at least 95 % of its frames; `frame_number` increases in each camera's messages. |
| T-PRV-11 | ws | Two rings at 30 fps; the client never answers; 5 s. A spy counts `read_newest` calls. | No message after the first message of each camera; one `read_newest` call per camera. |
| T-PRV-12 | ws | Connect, receive, close; connect again with a new client; send no ready message. | The new client gets the newest frame of each camera; the task of the first sender has ended. |
| T-PRV-13 | ws | Two clients on two rings at 30 fps for 5 s. Client 1 answers at once; client 2 never. Then client 2 sends one ready message. | Client 1 gets at least 95 % of the frames; client 2 gets one message per camera, then one more for the camera of its ready message; client 1 is not affected. |
| T-PRV-14 | ws | Two rings; after 1 s, add a third reader to the fake manager and write frames to it. | The third camera's newest frame arrives with no ready message, within 100 ms after its first commit. |
| T-PRV-15 | ws | Ring A at frame 500, sent. (1) The client has answered; replace A's reader with a new ring at frames 0 to 3. (2) The client has not answered; replace it in the same way, then answer. | (1) The next message for A has frame 3 of the new ring. (2) No message for A before the answer; then frame 3 or newer of the new ring. B continues in both cases (the rule of T-CAP-86). |
| T-PRV-16 | ws | Two rings at 30 fps; A's writer stops (a failed or dead camera); the client answers at once. | After A's last frame, no message for A in 2 s; B gets at least 55 messages in those 2 s. |
| T-PRV-17 | ws | Remove A's reader from the fake manager, then close it, as `_close_rings` does; then send a ready message for A. | No exception; no message for A; no log record at WARNING or above; B continues. |
| T-PRV-18 | fake | Set A's ring `closed` while its reader stays in the fake manager; later replace the reader with a new ring. | No message for A while it is closed, and no exception; A's frames come again from the new ring. |
| T-PRV-19 | fake | (1) Flip one payload bit of A's newest frame after commit (`CORRUPT`), then write the next frame. (2) A stub reader whose `read_newest` gives `LAPPED` two times, then `OK`. | (1) No message for the bad frame; the next frame goes out. (2) No message for the two `LAPPED` passes; the `OK` frame goes out. No log record at WARNING or above in either case. |
| T-PRV-20 | fake | The fake manager has no orchestrator and no camera states. Search `preview_relay.py` for `all_ready`, `should_grab_by_id` and `orchestrator`. | Messages go out; none of the names occurs. |
| T-PRV-21 | fake | `handle_text` with: a valid ready message; `camera_id` missing; `camera_id` 7; an unknown camera id; text that is not JSON; `{"frameNumber": 3}`; `ping`. | Valid: `True`, camera `ready`. Missing and 7: `True`, one WARNING record each, nothing changes. Unknown id: `True`, no record. Not JSON, `frameNumber` and `ping`: `False`. No exception. |
| T-PRV-22 | fake | One ring: `arrival_ns` in steps of 33,333,333 ns and `source_frame_number` in steps of 2; three frames flagged `OVERSIZE`. A second ring with `source_frame_number` -1. A fake send collects JSON for 1.1 s. | 4 or 5 `framerate_update` messages for the group; `delivered_framerate.mean_frames_per_second` is 60.0 ± 0.1 for the first ring and 30.0 ± 0.1 for the second; `oversize_count` is 3; no `backend_framerate` key. |
| T-PRV-23 | fake | `head` of an empty ring, then after commits 0 to 4; `oversize_count` after two oversize frames. `tracemalloc` over 1,000 `head` reads. | -1, then 4; 2; no allocation of 1 KiB or more. |
| T-PRV-24 | fake | Set `closing = True` on the fake manager for 0.5 s, then `False`. | No `read_newest` call and no message while it is `True`; messages again after. |
| T-PRV-25 | ws | 4a only: connect to `/websocket/connect` of the real app. | `websocket_server.py` does not import `preview_relay`; the existing tests of the old relay pass unchanged. 4b deletes this test. |

### 9.3 Parity of the systems [P7]

The states are those of [cap 16.7]. "runs": the test runs on that system and in its CI job.

| ID | Windows | Linux | macOS |
|---|---|---|---|
| T-PRV-01 | runs | runs | runs |
| T-PRV-02 | runs | runs | runs |
| T-PRV-03 | runs | runs | runs |
| T-PRV-04 | runs | runs | runs |
| T-PRV-05 | runs | runs | runs |
| T-PRV-06 | runs | runs | runs |
| T-PRV-07 | runs | runs | runs |
| T-PRV-08 | runs | runs | runs |
| T-PRV-09 | runs | runs | runs |
| T-PRV-10 | runs | runs | runs |
| T-PRV-11 | runs | runs | runs |
| T-PRV-12 | runs | runs | runs |
| T-PRV-13 | runs | runs | runs |
| T-PRV-14 | runs | runs | runs |
| T-PRV-15 | runs | runs | runs |
| T-PRV-16 | runs | runs | runs |
| T-PRV-17 | runs | runs | runs |
| T-PRV-18 | runs | runs | runs |
| T-PRV-19 | runs | runs | runs |
| T-PRV-20 | runs | runs | runs |
| T-PRV-21 | runs | runs | runs |
| T-PRV-22 | runs | runs | runs |
| T-PRV-23 | runs | runs | runs |
| T-PRV-24 | runs | runs | runs |
| T-PRV-25 | runs | runs | runs |

Short form: each of the 25 tests runs on Windows, Linux and macOS. No test has a counterpart or a
reason to skip. The rings use `multiprocessing.shared_memory` on each system [ring 1.1].

### 9.4 CI [P7] [agent 23]

- The three jobs of `.github/workflows/capture.yml` (`capture-windows`, `capture-linux`,
  `capture-macos`) add `skellycam/tests/preview` to their test selection.
- The trigger paths add `specs/preview.md`. `skellycam/api/**` and `skellycam/tests/**` are already
  in them.
- This change is a CI change. It goes in its own PR ([AGENTS.md](../AGENTS.md#6-git-rules)).

## 10. What 4b must do

4b is the UI side [P1]. It needs its own spec. This list gives only what 4a needs from it.

1. **Server switch** (one commit group with items 2 to 5, section 2.4). In `WebsocketServer.run`,
   replace the task `_frontend_image_relay` with `PreviewRelay.run`. In `_client_message_handler`,
   give each text to `PreviewRelay.handle_text` first. Delete the items of 2.3.
2. **Parser.** Replace `binary-protocol.ts` and `binary-frame-parser.ts` with a parser of the
   48-byte header of 3.2 (DataView, little-endian). Refuse an unknown `version` (3.3).
3. **Tile.** One tile for each camera, from the shared tile module of `specs/player.md` [P6]. The
   tile decodes with ImageDecoder [E] and turns the image by `rotation_cw_deg` when it draws [E].
   After each draw, after a header-only message and after a failed decode, it sends the ready
   message of 4.1 for its camera [P2]. Delete the `frameAcknowledgment` message.
4. **Overlay** [P4]: the camera label, the delivered rate (6.2), the state (6.1), and a mark while
   the last message of the camera has a bit of 0x0F. The tile keeps the last image under a
   header-only message.
5. **Frame rate viewer** [P4]: per camera, the skipped count from gaps of `frame_number` (a lower
   number means a new ring, not a skip), the oversize count (6.2) and the replaced count (Q2).
6. **Docs.** `skellycam-docs/docs/technical/websocket-protocol.mdx` and its `zh-CN`, `es` and `ar`
   copies [ring 2.1, A7]. Check `core/real-time-streaming.mdx`, `technical/api-reference.mdx` and
   `intro.mdx` for the old format.
7. **Tests.** The UI tests run in the TypeScript test runner of the player, on Windows, Linux and
   macOS [P7].
8. **Interface note** for the FreeMoCap session, at the end of 4b [P5].

## 11. Open points and weak points

### 11.1 Differences from the earlier specs

The earlier specs are accepted, so this spec does not edit them. The user decides each one:

1. P4 lists six states. [cap 8.1] has eight: it also has `waiting` and `checking`. The tile shows
   the value of `state` as `app_state` gives it [Q4].
2. P4 puts the replaced count in the frame rate viewer. [cap 5.2] only logs `replaced_count` at stop.
   No message carries it [Q2].
3. [ring 6.6] lists the reader calls. This spec adds `head` and `oversize_count` [agent 15]. This
   changes the reader API of
   [ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md).
4. T-RING-33 [ring 12] and T-CAP-86 [cap 16.2] test the old relay. 4b deletes them. T-PRV-02,
   T-PRV-09, T-PRV-14 and T-PRV-15 keep their rules.
5. [ring 2.1] keeps `frontend_payload_bytearray.py` for the interim relay [ring A56]. 4b deletes the
   file.

### 11.2 Known weak points

- The sender polls. The interval between passes on Windows can be longer than 10 ms [NV]. M-PRV-4
  measures it.
- The reads run on the event-loop thread that also serves the HTTP API. Many cameras at a high rate
  can make the API slower. M-PRV-3 measures it.
- Each client reads the rings for itself. Two clients double the read cost.
- A client that answers slowly gives few observations for `delivered_framerate`. A window of 0.25 s
  can then hold fewer than 2 durations, and the value is `null`.
- A new ring can pass the last `frame_number` of the old ring before the client answers. The UI then
  counts the gap as skips one time (10 item 5).
- Phase 3 must keep `CameraGroup.ring_readers` as a dict from camera id to reader, and must put a
  new reader object there for each new ring. 4b adapts the sender if phase 3 changes it.

## 12. Choices of the agent

Each item fills a gap that P1 to P7, [E] and the earlier specs do not fix. The body marks each one
[agent n].

1. The module layout and names of 2.1, the API of section 7 and the helpers of 9.1.
2. Byte 0 is `version` = 1, and it is also the message type; the rule to increase it; a parser
   refuses an unknown value.
3. The field order and offsets of 3.2: a 48-byte header, each field aligned to its size.
4. `camera_id` in 16 ASCII bytes, NUL-padded, as the old format and the ring `camera_key`; no
   message and one ERROR record for an id that does not fit.
5. "The camera's frame number" of P3 is the ring `frame_number` [ring 1.4], not
   `source_frame_number`.
6. The 32 bits of `flags` are copied, also the bits that are not errors.
7. `rotation_cw_deg` as a u32, the type of the slot header.
8. A flagged or oversize frame goes out as a header-only message with `jpeg_len` 0. `jpeg_len` is
   the count of bytes in the message, not the ring `payload_len`.
9. The ready message `{"message_type": "camera_ready", "camera_id": ...}`.
10. Each camera starts `ready` on a new connection. Thus the first frame goes out with no ready
    message.
11. No time limit for a client that never answers.
12. On a new ring, `last_sent` goes back to -1, and `ready` does not change.
13. A pass at most 10 ms after the previous pass (the `await_10ms` of today), and at once after a
    ready message.
14. The sender runs on the event-loop thread of the main process and reads through
    `CameraGroup.ring_readers`, looked up in each pass.
15. Two read-only properties of `FrameRingReader`: `head` and `oversize_count`.
16. A failed read sends nothing and writes no log record; the next pass tries again.
17. Each connection has its own sender, state and reads.
18. "Skipped" in P4 is the count of frames that the sender did not send to the client. The UI counts
    it from gaps of `frame_number`. The ring `skipped_count` stays 0 while the gate exists
    [cap 5.1, agent 6 of that spec].
19. The delivered rate from `source_frame_number` and `arrival_ns` with `ServerFramerateCalculator`,
    `frame_number` when `source_frame_number` is -1; every 0.25 s, then `clear()`, as the old relay.
20. The new shape of `framerate_update`: per camera `delivered_framerate` and `oversize_count`; no
    `backend_framerate` or `frontend_framerate`.
21. A ready message with a bad `camera_id` gets one WARNING record; an unknown camera id is ignored
    with no record; neither closes the connection.
22. 4a does not change `WebsocketServer` or the endpoint; the tests use a test route (2.4).
23. The CI change of 9.4, in its own PR.
24. The pass thresholds of 9.2.
25. One message is one `bytes` object: header and JPEG together, one copy of the JPEG.
26. No reads and no messages while `CameraGroupManager.closing` is `True`.
27. The sends of one connection are in series under its send lock.

## 13. Questions for the user

Each question is worded so that "yes" accepts the recommendation.

- **Q1.** P1 (4a before 4b) and P5 (no period with both formats, no preview gap) cannot both hold if
  4a switches the endpoint. Do you accept this way out: 4a adds the sender and its tests with no
  route, and the endpoint keeps the old relay; 4b switches the endpoint, deletes the old code and
  changes the UI in one commit group; the branch goes to `development-streaming` only after 4b?
  Recommendation: yes. It is the smallest change, and no build sends a format that its UI cannot
  read.
- **Q2.** P4 puts the replaced count in the frame rate viewer. Phase 3 only logs `replaced_count`
  at stop [cap 5.2]. Should step 3a add `replaced_count` (counted from the first frame that the
  camera takes in the gate) to the camera status of [cap 8.4], so that `app_state` carries it?
  Recommendation: yes. The count is in the camera process, and the status already goes to the UI.
  4a then adds nothing for it.
- **Q3.** Is "the camera's own delivered frame rate" of P4 the rate of the frames that the camera
  delivers to skellycam, from `source_frame_number` and `arrival_ns`, and not the rate of the frames
  that reach the tile? Recommendation: yes. Under the gate, all cameras take frames at the group
  rate. Only the delivered rate shows which camera is slow.
- **Q4.** P4 lists six states. [cap 8.1] also has `waiting` and `checking`. Should the tile show each
  of the eight states as `app_state` gives it? Recommendation: yes. The states come from one field,
  and a filter would hide a real state.

## 14. Decisions of the user

The user decided these on 2026-11-19 (Q233 to Q239, all accepted)
([ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)). They are
binding.

Earlier binding statements [E]: one websocket message for each camera frame; the JPEG untouched, no
resize, no re-encode; the preview does not depend on the group gate; the UI rotates when it draws;
the tile decodes with ImageDecoder and is shared with the player (Y3); the UI runs on the machine
with the cameras.

- P1 (Q233): Two steps. 4a is the new websocket message and its sender in Python, tested against
  fake rings, with no dependency on phase 3. 4b is the UI side: the parser, the shared tile, the
  overlay.
- P2 (Q234): Flow control for each camera. The UI says "camera X is ready" after it has drawn a
  frame. The server then sends the newest frame of camera X that it has not sent, and it skips all
  older frames. A slow tile does not hold back the others. No rate setting.
- P3 (Q235): The message header holds the camera id, the frame number of the camera, the arrival
  time, the rotation, the ring flags and the JPEG length. Width and height come from the JPEG. The
  server copies ring data and adds nothing.
- P4 (Q236): The tile shows the camera label, the delivered frame rate of the camera, its phase 3
  state (starting, ready, too_slow, failed, dead, recording) and a mark for a flagged frame. The
  counts (skipped, replaced, oversize) go in the existing frame rate viewer, not on the tile.
- P5 (Q237): 4b deletes the old group message and its code. No period with both formats. An
  interface note for the FreeMoCap session is written at the end of 4b.
- P6 (Q238): The player spec (`specs/player.md`, branch `dom/player`) specifies the shared tile one
  time, as its own module. 6a or 4b, whichever starts first, builds it.
- P7 (Q239): Parity. The Python tests of 4a run on Windows, Linux and macOS in CI with fake rings.
  The UI tests of 4b run in the TypeScript test runner of the player, on the three systems.
