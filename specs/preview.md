# Phase 4 preview specification: the per-camera websocket message and its sender (4a)

Status: accepted by the user on 2026-11-19, with its test list
([ADR-WB08](../decisions/entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md)).
[ADR-162X](../decisions/entries/162X-step-4a-preview-spec-and-agent-choices.md) holds the agent
choices. An agent wrote it on 2026-11-19. The user decided P1 to P7 and answered A1 to A8 on 2026-11-19
([ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)). Section 15
gives each one. The second revision of 2026-11-19 applies A1 to A7 and the faults of an independent
review. The third revision applies the fixes of a second review, and A8. No review has read the
third revision. No question is open. A dated note of 2026-11-20 in section 8.4 applies the answers
A9 and A10. The agent choices of section 13 wait for the acceptance of the
user. The failing tests of step 4a come before the product code of step 4a.

## 0. How to read this spec

Marks:

- **[Pn]**: decision n of the user for phase 4, 2026-11-19 (section 15).
- **[An]**: answer n of the user: A1 to A8 to the drafts of this spec, 2026-11-19; A9 and A10 to the
  measurements of 4a, 2026-11-20 (section 15).
- **[E]**: a binding statement of the user from before P1 to P7 (section 15).
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md), the accepted phase 2 spec
  ([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)). **[ring An]**: item n of
  section 14 of that spec.
- **[cap x.y]**: section x.y of [`windows-capture.md`](windows-capture.md), the accepted phase 3 spec
  ([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)).
- **[M source]**: measured; the source holds the result. **[M review]**: measured by the independent
  review of 2026-11-19 on a Windows test machine. No evidence entry records it yet. **[NV]**: not
  verified.
- **[agent n]**: an agent filled a gap that the decisions, the answers and the earlier specs do not
  fix. Section 13, item n, lists each one.

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
| 4a | The per-camera message (section 3), its sender in Python (sections 4 and 5), the JSON data that the UI needs for P4 (section 6), and the tests against fake rings (section 9) [P1]. No dependency on phase 3 [P1]. The sender has no route [A1]. |
| 4b | The UI side: the parser, the shared tile, the overlay [P1]. The connection of the sender to the websocket endpoint, and the deletion of the old group message and its code, together with the UI change [P5, A1]. Section 10 lists what 4b must do. It is not a full spec. |

### 1.3 Non-goals

- A resize, a quality setting, a rate cap or a rate setting [E, P2].
- A rotation in the server. The UI rotates when it draws [E].
- A preview from a remote machine. The UI runs on the machine with the cameras [E].
- The BGR ring. The sender reads only the JPEG ring.
- The shared tile. The player spec specifies it as its own module [P6]. Section 11 states what it
  needs from phase 4.
- A change of the performance page [ring A5] or of `CameraGroup.read_latest_ring_frames`.
- A worker thread for the reads (section 8.3).
- The `replaced_count` of the camera status. Step 3a adds it [A2] (section 6.1).

### 1.4 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| Ring reader, read results, retry rule, lookups | [ring 6.2 to 6.5] | Section 5 uses them, with one new property [A5]. |
| Flag bits and the error mask 0x0F | [ring 4] | Section 3.3 copies the bits. |
| Rotation per frame, `rotation_cw_deg` | [ring 3.4] | Section 3.3 copies the value. |
| What the ring gives the UI: newest lookup, untouched JPEG, rotation per frame, oversize count | [ring 6.6, 5.8] | Sections 3, 5 and 6. |
| Ring recreation on a mode change; `closed` | [ring 7.4, 7.5] | Section 4.4. |
| The interim relay | [ring 2.3, A4], [cap 5.8, U13] | 4b deletes it (section 2.3). |
| Camera states and the status report | [cap 8.1, 8.4] | Section 6 uses them. The tile shows all eight states [A4]. |
| The shared tile and its decoder (ImageDecoder) | `specs/player.md` on branch `dom/player` [P6] | Section 11. |

### 1.5 Terms

| Term | Meaning |
|---|---|
| camera message | One binary websocket message for one camera frame (section 3). |
| sender | The object `PreviewRelay` that reads the rings and sends camera messages for one websocket connection (section 7). |
| connection | One websocket connection of one client. |
| ready | The state of a camera for a connection in which the sender can send its next camera message (section 4). |
| ready message | The JSON message of the client that says "camera X is ready" [P2]. |
| safety net | The send of the newest unsent frame of a camera that has had no ready message for 1 s [A6]. |
| pass | One run of the sender over all cameras (section 4.3). |
| tick | The run of the sender every 0.25 s that feeds the frame rate and sends `framerate_update` (section 6.2). |
| not shown | A frame of a camera that the sender did not send, because the screen was slower than the camera [A7]. |
| old relay | `WebsocketServer._frontend_image_relay` with `CameraGroup.get_latest_ring_payload`: the group message of today [ring 2.3, cap 5.8]. |

## 2. What 4a adds, what 4b deletes, and how the two coexist

### 2.1 Code that 4a adds or moves [agent 1]

| Path | Content |
|---|---|
| `skellycam/api/websocket/preview_relay.py` | `CAMERA_FRAME_VERSION`, `CAMERA_FRAME_HEADER` (a `struct.Struct`), `pack_camera_frame`, `PreviewRelay` (section 7). |
| `skellycam/core/ipc/frame_ring/reader.py` | Two read-only properties of `FrameRingReader`: `oversize_count` [A5] and `skipped_count` [A8]. |
| `skellycam/core/recorders/framerate_tracker.py` | `ServerFramerateCalculator`, moved from `api/websocket/websocket_server.py`, with the two changes of 6.3 [agent 19]. The old relay and `tests/test_websocket_internals.py` import it from here. Thus `preview_relay.py` and `websocket_server.py` do not import each other in a circle. |
| `skellycam/tests/preview/` | The tests of section 9, a fake group manager, and a test route that wires `PreviewRelay` to a websocket as 4b will. |

### 2.2 Code that 4a does not change [A1]

- `WebsocketServer` and the endpoint `/websocket/connect` stay as they are, except for the import of
  `ServerFramerateCalculator`. The endpoint keeps the old relay and its `frameNumber`
  acknowledgement.
- The UI keeps its parser of the old group message.
- Thus, while only 4a is in the code, the UI shows the preview as today, and the wire carries only
  the old format.

### 2.3 Code that 4b deletes [P5]

| Item (file) | Replacement |
|---|---|
| `WebsocketServer._frontend_image_relay`, `check_frame_acknowledgment_status`, the `frameNumber` branch of `_client_message_handler`, the fields `last_sent_frame_number`, `last_received_frontend_confirmation`, `_last_sent_by_group`, `_display_image_sizes`, `_server_framerate_calculators`, `_display_framerate_trackers`, `_last_framerate_send_time`, `FramerateUpdateMessage`, `BACKPRESSURE_WARNING_THRESHOLD` (`api/websocket/websocket_server.py`) | `PreviewRelay.run` and `PreviewRelay.handle_text` |
| `CameraGroup.get_latest_ring_payload` (`core/camera_group/camera_group.py`) | `pack_camera_frame` |
| `CameraGroupManager.get_latest_frontend_payloads` and `CameraGroupManager.get_backend_framerate_updates` (`core/camera_group/camera_group_manager.py`); their mocks in `tests/conftest.py` | The sender reads `ring_readers` itself (section 5) and computes the rates (section 6). |
| `core/types/frontend_payload_bytearray.py` (the whole file) [ring A56] | `CAMERA_FRAME_HEADER` |
| `tests/test_image_payload.py` | T-PRV-01 |
| T-RING-33 in `tests/frame_ring/test_camera_process.py` | T-PRV-02 |
| T-CAP-86 and its helpers `parse_relay` and `_collect` (`tests/capture/`) | T-PRV-09, T-PRV-14, T-PRV-15 |
| `test_websocket_frame_acknowledgment` in `tests/test_websocket.py` | T-PRV-21 |
| The parser of the group message in the UI and its `frameAcknowledgment` message | Section 10 |

`read_latest_ring_frames` stays for `get_latest_performance_data` [ring A5].

### 2.4 One format on the wire, and no time without a preview [A1]

1. 4a adds the sender with no route. The live endpoint keeps the old relay (2.2). The 4a tests reach
   the sender through a test route in `skellycam/tests/preview/` (9.1).
2. 4b connects the sender, deletes the old code (2.3) and changes the UI together. No commit of the
   branch sends both formats, and no commit sends a format that its UI cannot read.
3. The branch goes to `development-streaming` only after 4b.

Thus both formats exist only as code on the branch, between 4a and 4b. The new code has no route in
that time.

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

## 4. Flow control [P2, A6]

### 4.1 The ready message [agent 9]

The client sends one text message for each camera message that it has handled:

```json
{"message_type": "camera_ready", "camera_id": "a1b2"}
```

- The client sends it after the tile has drawn the frame [P2]. It also sends it after a header-only
  message, and after a JPEG that it cannot decode. If it does not, the tile of that camera gets only
  the safety net: one frame each second [A6].
- The client must keep only the newest pending camera message of each camera. A new message
  replaces a message that waits to be drawn. The client sends one ready message after each draw, not
  one for each received message. Thus a client that draws slower than one frame each second (for
  example a hidden tab) gets the safety-net messages and never falls behind by more than one message
  for each camera.
- A ready message has no frame number [P2].
- A message whose `message_type` is `camera_ready` and whose `camera_id` is not a string: the sender
  logs one WARNING record and ignores the message. The connection stays open [agent 21].
- A ready message for a camera id that the sender does not know: the sender ignores it with no log
  record. The camera can be removed while the message travels [agent 21].
- A ready message for a camera that is already ready: no effect.
- `PreviewRelay.handle_text(text)` returns `True` when the text was a ready message (valid or not),
  and `False` for each other text. Thus the handler of the endpoint keeps `ping` and `pong`.

### 4.2 State of each camera, for each connection

| Field | Start value | Meaning |
|---|---|---|
| `reader` | the reader in `ring_readers` | The reader of the last look-up. A different object means a new ring. |
| `last_tried` | -1 | The `frame_number` of the last frame that the sender read for a send, with any result [agent 7]. |
| `last_sent` | -1 | The `frame_number` of the last camera message of this ring. |
| `ready` | `True` | The sender can send the next camera message [agent 10]. |
| `sent_at` | none | The `time.monotonic()` of the last camera message. |
| `skipped_at_send` | none | The ring skipped count (5.2) at the last camera message (6.1). |
| `not_shown` | 0 | The count of frames not shown on this connection (6.1) [A7]. |
| `rate` | a new `ServerFramerateCalculator` | Section 6.3. |
| `bad_id_logged` | `False` | Section 3.3. |

A new ring sets `reader`, and sets `last_tried`, `last_sent` and `skipped_at_send` back to their start
values. It does not change `ready`, `sent_at`, `not_shown` or `rate` [agent 12].

### 4.3 The rule of the sender

The sender runs passes. A pass starts 10 ms after the end of the previous pass, or at once after a
ready message [agent 13]. In each pass, for each group of `list(manager.camera_groups.values())`,
and for each camera id of `list(group.ring_readers)` [agent 14]:

1. **Look up.** `reader = group.ring_readers.get(camera_id)`, immediately before the reads of this
   camera. If it is `None`, go to the next camera. If the camera has no state, make one (4.2). If
   the reader is a different object, apply the new-ring rule of 4.2.
2. **Ready.** If `ready` is `False` and less than 1 s has passed since `sent_at`, go to the next
   camera. After 1 s, the camera is ready for this pass: the safety net [A6].
3. **Camera id.** If the camera id does not fit the message (3.3), log it one time (`bad_id_logged`)
   and go to the next camera.
4. **Check.** `q = reader.read(last_tried + 2)`. If `q.result` is `CLOSED`, go to the next camera.
5. **Probe and newest** [A5] [agent 15]:
   - If `q.result` is `NOT_YET_WRITTEN`: `p = reader.read(last_tried + 1)`. If `p.result` is
     `NOT_YET_WRITTEN` or `CLOSED`, go to the next camera. Else `p` is the newest frame: `read = p`.
   - Else: `read = reader.read_newest()` [ring 6.5].

   `NOT_YET_WRITTEN` comes from step R2 of [ring 6.2], before any copy. Thus a camera with no new
   frame costs no copy.
6. Set `last_tried = read.frame_number`, except when `read.result` is `LAPPED`. A frame that
   `read_newest` gives as `LAPPED` is thus tried again in the next pass.
7. **Send.** If `read.result` is `OK`, `FLAGGED` or `OVERSIZE`, and `read.frame_number > last_sent`:
   1. Build the camera message (3.2).
   2. Before the send, update the state: `not_shown` (6.1), `skipped_at_send`,
      `last_sent = read.frame_number`, `ready = False`, `sent_at = time.monotonic()`, and `rate`
      (6.3) [agent 16].
   3. `await` the send.
8. If not, send nothing. The next probe starts after `last_tried` (5.3).

After all cameras, the sender removes the state of each camera id that is no longer in any
`ring_readers`.

Thus the server sends the newest frame that it has not sent, and it skips all older frames [P2].
The sender keeps no queue. A connection has at most one camera message in flight for each camera.

### 4.4 Cases

| Case | What the sender does |
|---|---|
| First frame, before any ready message | Each camera starts `ready` (4.2). The first pass with a frame sends the newest frame [agent 10]. |
| The client never answers for a camera | The safety net sends the newest unsent frame of that camera one time each second [A6]. The other cameras continue at their own rate. |
| The client answers late | The ready message makes the camera `ready`. The sender sends the newest frame at once, or at the first pass with a newer frame. |
| Reconnect | A new connection gets a new sender with new state. Each camera starts `ready`. The old sender ends with its connection. |
| A camera appears (a new camera, a new group, or a reopen with a new process) | A new key in `ring_readers` gets a new state, `ready`. Its newest frame goes out at the first pass with a frame. |
| A ring is recreated (a mode change [ring 7.5], or "apply again" [cap 8.3]) | `CameraGroup` puts a new reader under the same camera id. Step 1 of 4.3 applies the new-ring rule. The next camera message holds a frame of the new ring. Its `frame_number` can be lower than the last one. |
| A reader is removed or replaced while a send waits | Step 1 looks the reader up again after the `await`. The sender never reads through a reader that it found before an `await`. |
| A camera fails or dies [cap 8.1] | Its ring gets no new frame. Steps 4 and 5 find nothing new. The tile keeps the last frame. `app_state` gives the state (section 6). |
| A camera is removed (unselect [cap 8.3]) | Its key leaves `ring_readers`. The sender removes its state. A late ready message for it is ignored (4.1). The UI removes the tile from `app_state`. |
| A ring is closed while its reader is still in `ring_readers` | The probe gives `CLOSED`. No message (5.3). |
| Several clients | Each connection has its own sender and its own state. A slow client does not hold back another client [agent 17]. Each sender reads the rings for itself. |
| The manager closes | While `CameraGroupManager.closing` is `True`, a pass and a tick read nothing and send nothing [agent 26]. |
| A send fails because the client is gone | The sender ends, as the old relay ends today (`WebSocketDisconnect`, a closed websocket). |

## 5. Ring reads

### 5.1 Process and thread [agent 14]

- The sender runs in the main skellycam process, on the asyncio event-loop thread of the server, as
  the old relay does.
- It reads through the readers that `CameraGroup` already holds in `ring_readers` (the JPEG ring of
  each camera [ring 7.1, A32]). It attaches no reader of its own.
- `CameraGroup.update_camera_settings` is a coroutine. It can run during each `await` of the sender,
  and `_close_rings` then removes and closes readers. Thus:
  - The sender loops over copies (`list(...)`) of `camera_groups` and of `ring_readers`. A change of
    a dict during an `await` cannot stop the loop.
  - It looks each reader up again in step 1 of 4.3, after the last `await`. `_close_rings` removes a
    reader from the dict before it closes it, on the same thread. Thus a reader that the look-up
    finds is open.
  - The reads of one camera (steps 4 to 6) are synchronous calls with no `await` between them. No
    other coroutine can close the reader during them.
  - A tick (6.3) reads all cameras before its first `send_json`. It does not read after an `await`.
  - A closed ring whose reader is still in the dict gives `CLOSED` (5.3): no frame.
- The sends of one connection are in series, under the send lock of the connection [agent 27].

### 5.2 Calls

| Call | Exists | Use |
|---|---|---|
| `FrameRingReader.read(k)` | yes [ring 6.2] | The check (step 4) and the probe (step 5). `k > head` gives `NOT_YET_WRITTEN` with no copy (R2); `head - k >= N` gives `LAPPED` with no copy (R3). |
| `FrameRingReader.read_newest()` | yes [ring 6.5] | The newest frame (step 5) and the tick read (6.3). |
| `FrameRingReader.oversize_count` | new [A5] | The `oversize_count` field of the ring header, one 8-byte load [ring 3.3, 5.8]. This adds to the reader API of [ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) by decision of the user. |
| `FrameRingReader.skipped_count` | new [A8] | The `skipped_count` field of the ring header, one 8-byte load [ring 3.3]. For display only. This adds to the reader API of ADR-9G2W by decision of the user. |

The ring skipped count is `reader.skipped_count` [A8].

There is no `head` property [A5].

Copies for each camera message (steps 4 and 5):

- The client keeps up: frame `last_tried + 1` is the newest. The check gives `NOT_YET_WRITTEN` with no
  copy. One copy, by the probe.
- The client is more than 1 s behind (slot count of 1 s [ring 3.7]): the check gives `LAPPED` with no
  copy. One copy, by `read_newest`.
- Between these two: two copies (the check, `read_newest`).

### 5.3 Read results

| Result | Sender |
|---|---|
| `OK` | Send the header and the JPEG. |
| `FLAGGED`, `OVERSIZE` | Send the header only (3.3). |
| `NOT_YET_WRITTEN` (check or probe) | The check: go to the probe. The probe: nothing. No copy. |
| `LAPPED` (check) | Go to `read_newest` (step 5). |
| `LAPPED` (probe, or after the second `read(head)` of `read_newest`) | Nothing. `last_tried` does not change, so the next pass tries again. |
| `MISSING`, `CORRUPT` | Nothing. `last_tried` is set, so the next pass does not read this frame again [agent 7]. |
| `CLOSED` | Nothing. A new reader replaces it, or the camera leaves `ring_readers`. |

The sender writes no log record for one failed read [agent 18]. The reader counts its failed checks
in `failed_checks`.

### 5.4 No dependency on the gate or on the camera states

- The sender does not call `CameraOrchestrator.all_ready`, `should_grab_by_id` or any other part of
  the orchestrator [E].
- It does not read the camera states. A camera with a new frame in its ring is shown. A camera
  without one is not [cap 8.1: no ring frame in `starting`, `waiting`, `failed`, `dead`].
- It does not wait for equal frame numbers. Each camera is independent [P2].

## 6. State and counts for the UI [P4]

### 6.1 What the UI needs, and where it comes from

| Item | Source | Message |
|---|---|---|
| Camera label [P4] | `configs[camera_id].camera_name` | `app_state` (existing, unchanged) |
| Frame rate of the camera [P4, A3] | The rate at which the camera delivers frames to skellycam: `source_frame_number` and `arrival_ns` (6.3). It does not depend on the client [A3]. | `framerate_update`, new shape (6.2) |
| State, all eight of [cap 8.1] [P4, A4] | `state` of the camera status [cap 8.4] | `app_state` (existing; phase 3 adds the key) |
| Mark of a flagged frame [P4] | `flags & 0x0F` of the camera message | the camera message (3.2) |
| Not shown [A7] | The sender: at each camera message, `not_shown += (frame_number - last_sent - 1) - (ring skipped count - skipped_at_send)`, when `last_sent >= 0` in the same ring [agent 20] | `framerate_update` (6.2) |
| Ring skipped count [A7] | `reader.skipped_count` (5.2) [A8] | `framerate_update` (6.2) |
| Replaced count [P4, A2] | `replaced_count` of the camera status, counted from the first frame that the camera takes in the gate. Step 3a adds it [A2]. The sender does not compute it. | `app_state` (existing) |
| Oversize count [P4] | `oversize_count` of the ring header [ring 5.8, A5] | `framerate_update` (6.2) |

- "Not shown" and the ring skipped count are two numbers with two names. The viewer never adds them
  [A7].
- While the lockstep gate exists, the ring `skipped_count` stays 0 [cap 5.1, agent 6 of that spec].
  Then "not shown" is the sum of the gaps of `frame_number`.
- A frame that the sender did not send because of a failed read (5.3) also counts as not shown. It
  is rare.
- `app_state` stays as it is. Its sender sends it at most one time each second, when it changes. A
  state change thus shows on the tile within about 1 s.

### 6.2 The new shape of `framerate_update` [agent 19]

The sender sends one message for each camera group at each tick (every 0.25 s, as the old relay):

```json
{
  "message_type": "framerate_update",
  "camera_group_id": "g1",
  "cameras": {
    "a1b2": {
      "delivered_framerate": {"mean_frames_per_second": 29.97, "...": "..."},
      "not_shown_count": 12,
      "ring_skipped_count": 0,
      "oversize_count": 0
    }
  }
}
```

- `delivered_framerate` is a `CurrentFramerate` (`core/recorders/framerate_tracker.py`, unchanged),
  or `null` while the calculator has fewer than 2 frame durations.
- `not_shown_count` is `not_shown` of 4.2, for this connection, since the connection started.
- `ring_skipped_count` and `oversize_count` are the ring header values at the tick.
- The message has no `backend_framerate` and no `frontend_framerate`. 4b changes the frame rate
  viewer to the per-camera values.
- The sender sends the message only for a group that has at least one camera in `ring_readers`.

### 6.3 The frame rate of the camera [A3] [agent 19]

- The sender feeds `rate` with `update(source_frame_number, arrival_ns)`. When `source_frame_number`
  is -1 (the OpenCV loop before phase 3 writes -1), it uses `frame_number`.
- It feeds `rate` at each camera message, and at each tick with one `read_newest()` of each camera.
  The tick read sends nothing. Thus `rate` gets at least four observations each second, also from a
  client that never answers [A3].
- A tick has two parts. First, for each camera, it looks the reader up, reads the newest frame, feeds
  `rate`, and reads `oversize_count` and the ring skipped count (5.2). Then it builds the messages
  and sends them. It reads nothing after its first `send_json` (5.1).
- The tick read does not change `last_sent`, `last_tried`, `ready` or `sent_at`. Thus it has no
  effect on the flow control or on the safety net.
- The tick read copies one JPEG for each camera, each tick and each connection, also when no camera
  is ready: about 16 ms each second for 8 cameras (8 x 4 x 0.5 ms, from 8.1).
- The formula is exact over skipped frames: `(s_b - s_a) / (t_b - t_a)`, as the rate check
  [cap 10.1].
- After each `framerate_update`, the sender calls `clear()` on each calculator, as the old relay
  does.
- Two changes of `ServerFramerateCalculator`, from the review:
  - `clear()` removes the frame durations, and keeps the last observation. Thus the first update after
    `clear()` gives one interval, and the value does not depend on how often the client answers.
  - `update` adds at most `maxlen` durations of its duration deque for one interval. A large jump of
    the frame counter cannot make a long loop.

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
        """Passes (4.3) and ticks (6.2, 6.3) until the task is cancelled."""
    def handle_text(self, text: str) -> bool:
        """A ready message (4.1): mark the camera ready, wake `run`, return True. Else False."""
```

- `pack_camera_frame` builds one `bytes` object: the 48-byte header, then the JPEG. This is one copy
  of the JPEG [agent 25].
- `run` is the only coroutine that reads rings and sends. `handle_text` only sets `ready` and an
  `asyncio.Event`. Thus two sends for one camera cannot race.
- The sender uses only `camera_groups`, `closing`, and the `id` and `ring_readers` of each group. The
  tests give a fake manager (9.1).

## 8. Performance

### 8.1 Measured numbers that apply

| Item | Number | Source |
|---|---|---|
| Largest real JPEG, 720p / 1080p (Kiyo Pro) | 276,269 / 607,032 bytes | [ring 3.6] [M] |
| Largest frame in a four-camera run at 720p30 | 0.10 to 0.22 of a 925,696-byte slot (about 93 to 204 kB) | [open-work.md](../decisions/open-work.md), fact of 2026-11-18 [M] |
| Copy, CRC-32 and pack of a 607 kB JPEG (one read and one message) | 0.43 ms p50, 0.54 ms p99 | [M review] |
| The send of uvicorn | about two more copies of the message | [M review] |
| `asyncio.sleep(0.01)` on Windows | 10 to 12 ms on one test machine; it depends on the machine | [M review] |
| `zlib.crc32` releases the GIL; the R11 copy holds it | Python 3.13.18, Windows | [ADR-ETJ1](../decisions/entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md) [M] |
| Readers do not make the writer slower | JPEG write p99 0.75 ms at 1080p with four readers | [ring A66] [M] |

### 8.2 Load, from 8.1

- One camera message of 607 kB costs about 0.5 ms of the event-loop thread, plus the copies of
  uvicorn, when the client keeps up (one read, 5.2).
- 8 cameras at 60 fps with one client that keeps up: about a quarter of the event-loop thread
  [M review estimate]. Each more client adds the same again.
- A client between 1 frame and 1 s behind costs two reads for each message (5.2), at a lower message
  rate.
- The tick reads cost four reads each second for each camera and client: about 16 ms each second for
  8 cameras (6.3).
- A camera with no new frame costs no copy (step 4 of 4.3).

### 8.3 No worker thread now

The reads stay on the event-loop thread. A worker thread could not use the readers of
`CameraGroup`: `_close_rings` closes them on the event-loop thread, and a read in another thread at
that time would read a released buffer. A worker thread would need its own readers, attached by
ring name, with its own close rules. 4a adds a worker thread only if M-PRV-3 misses its target and
the user decides it.

### 8.4 Targets of 4a (each one to measure in 4a)

No number below is measured, except the row marked [A10].

| Item | Target | Basis |
|---|---|---|
| `read` of a 1080p JPEG, p99 | at most 0.5 ms | the provisional read target of [ring 11.3]. To measure in 4a. |
| Event-loop time of the sender, 4 cameras at 1080p30, one client that keeps up | at most 19 % of one core [A10] | Measured in 4a with compression off [A9]: 13 to 19 %, median 16 %, in six runs. The first target was 10 % (120 messages/s x about 0.6 ms). |
| HTTP response time of `GET /health` while the sender runs, 8 cameras at 1080p60, one client that keeps up, p99 | at most 50 ms | To measure in 4a. |
| Time from `published_ns` to the start of the send, client that keeps up, p99 | at most 25 ms | 10 ms between passes plus the sleep error of 8.1. To measure in 4a. |
| Frames sent, client that keeps up, 30 fps | each frame (T-PRV-10 allows more loss on a CI runner) | The period (33 ms) is longer than a pass. At 60 fps: to measure in 4a. |

Note of 2026-11-20 [A9, A10]: the measurements of 4a
([ADR-HDC9](../decisions/entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md))
found that uvicorn turns on permessage-deflate by default. Each JPEG was compressed on the event-loop
thread: 12.7 ms for a 1080p message, against 0.31 ms with compression off (16.9 ms against 0.23 ms
with the websocket implementation of the product). A9 turns compression off.
A10 sets the event-loop target to the number measured with compression off. The table above has the
changed target. The estimate "about 0.6 ms" for each message (8.2) holds only with compression off.

### 8.5 Measurements of 4a

| ID | Measurement |
|---|---|
| M-PRV-1 | `read` time (p50, p99) for 720p and 1080p JPEGs of the largest real size, on Python 3.13.18, Windows. This is ring M3 with one reader. |
| M-PRV-2 | `pack_camera_frame` time and the send time through uvicorn (p50, p99) for the same sizes. |
| M-PRV-3 | CPU of the event-loop thread with the sender, and the response time of `GET /health` at the same time: 4 cameras at 720p30 and 1080p30, 8 cameras at 1080p60; one client that keeps up; one client that never answers. |
| M-PRV-4 | Time from `published_ns` to the start of the send, p50 and p99, Windows and Linux. The actual interval between passes on Windows. |
| M-PRV-5 | Frames not shown at 60 fps with a client that keeps up, Windows. |

A script makes them with fake rings and no camera. An evidence entry records the result. The user
decides each target that the result does not meet.

## 9. Tests

### 9.1 Kinds and helpers

- **fake**: a test that calls `PreviewRelay` or `pack_camera_frame` directly, with fake rings, a
  fake manager and fake send functions. It runs on each OS and in CI [P7].
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
  `ring_readers` (camera id to `FrameRingReader`). The test can add, replace, remove and close
  readers, as `CameraGroup` does. It has no orchestrator and no camera.
- **Stub reader.** An object with `oversize_count`, `skipped_count`, and scripted `read` and
  `read_newest`, for read results that a real ring gives only by chance (`LAPPED`).
- **Slow send.** A fake `send_bytes` that waits on an `asyncio.Event` that the test controls. While
  it waits, other coroutines run.
- **Test route.** A FastAPI app with one websocket route. It accepts, makes a `PreviewRelay` with the
  send functions of the websocket, starts `run` as a task, and gives each text message to
  `handle_text`. When the client disconnects, it cancels the `run` task and waits for its end
  [agent 22]. 4b moves these lines into `WebsocketServer`, whose tasks already end that way.
- **Independent parser.** A test-only parser that uses `struct.unpack_from` at the offsets of table
  3.2. It does not import `CAMERA_FRAME_HEADER`.

"Camera message" in a pass criterion means a binary message. `framerate_update` and other JSON
messages also flow during each ws test; a criterion about camera messages does not count them. The
pass thresholds are [agent 23]. They are loose so that a slow CI runner (macOS) passes. They can
change when the tests are written.

A share of frames and a count of camera messages in a time window depend on the pace of the
machine. They are `pace` tests ([cap 16.1]), split from the blocking tests on the same run (Q669,
Q670) [ADR-F4N7](../decisions/entries/F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md):

- A share of frames (T-PRV-05, T-PRV-09, T-PRV-10, T-PRV-13) is at least 80 % on a real machine
  (margin 1, or no margin set). When a margin above 1 is set (CI), the warning level is a fixed
  40 %. This level does not change with the value of the margin (Q690)
  [ADR-B1DE](../decisions/entries/B1DE-decisions-of-the-user-on-the-share-level-and-the-test-clock.md).
- A count of camera messages in a window (T-PRV-15, T-PRV-16) is the time to the n-th camera
  message. Its nominal value is n frame periods (n / 30 s), and its tolerance is the window minus
  that time, times the margin [ADR-B7YV](../decisions/entries/B7YV-choices-of-fix-lane-6.md).
- The blocking half keeps each other check. In place of the share, it checks that an answered camera
  gets more camera messages than the safety net can give (more than the seconds of the run plus 2);
  in place of the count, it waits for the n-th camera message with a loose time limit (10 times the
  window) [ADR-B7YV](../decisions/entries/B7YV-choices-of-fix-lane-6.md). T-PRV-54 checks the rule
  of 4.3, which does not depend on the pace.

### 9.2 Test list

| ID | Kind | Input and action | Pass criterion |
|---|---|---|---|
| T-PRV-01 | fake | `pack_camera_frame` for the example of 3.2; also a `FLAGGED` read with flags 0x04 and one with `OVERSIZE`. Check `CAMERA_FRAME_HEADER.size` and the offset of each field. | The bytes equal the example of 3.2, byte for byte; the flagged messages are 48 bytes with `jpeg_len` 0 and the ring flags; size 48; offsets of table 3.2. |
| T-PRV-02 | ws | Three fake rings at 30 fps for 5 s; the client answers at once. A second reader per ring reads each received `frame_number`. | Each field that the independent parser reads equals the slot field of that frame; the JPEG bytes equal the ring payload (the rule of T-RING-33). |
| T-PRV-03 | fake | Frames with each flag bit 0x01 to 0x20, and with 0x30 and 0x14. | Each message has the 32 bits of the slot; 0x10, 0x20 and 0x30 carry the JPEG; each frame with a bit of 0x0F has `jpeg_len` 0 and no bytes after the header. |
| T-PRV-04 | ws | One ring; rotation 0, then 90, 180, 270, 0 on consecutive frames; the client answers at once. | Each camera message has the rotation of its own frame. |
| T-PRV-05 | ws | Camera ids `a1b2`, `abcdefghijklmnop` (16), `abcdefghijklmnopq` (17) and `cámara`. | The first two are sent, NUL-padded to 16 bytes; the last two get no camera message and one ERROR record each for the connection; the first two are not affected: at least 80 % of their frames in 1.5 s (`pace`; 40 % on CI) (9.1). |
| T-PRV-06 | ws | Two rings with frames 0 to 9; connect; send no ready message; the writers continue. | Exactly one camera message per camera, frame 9 or newer, within 1 s of the connect; no other camera message until 0.8 s after it. |
| T-PRV-07 | ws | After T-PRV-06, within its 0.8 s: pause the writers at frame 20; send a ready message for one camera. | One camera message for that camera, frame 20; none for the other camera until its safety net. |
| T-PRV-08 | ws | A ready message while the newest frame is the last sent frame; then write one frame. | No camera message before the write; one camera message with the new frame within 0.5 s after the write. |
| T-PRV-09 | ws | Three rings at 30 fps for 5 s; the client answers at once for cameras A and B; it never answers for camera C. | A and B each get at least 80 % of the frames written in that time (`pace`; 40 % on CI) (9.1); C gets 4 to 7 camera messages (the safety net). |
| T-PRV-10 | ws | Four rings at 30 fps for 10 s; the client answers at once. | Each camera gets at least 80 % of its frames (`pace`; 40 % on CI) (9.1); `frame_number` increases in the camera messages of each camera. |
| T-PRV-11 | ws | Two rings at 30 fps; the client never answers; 5.5 s. | Each camera gets 4 to 7 camera messages; each holds a frame that was written after the previous camera message of that camera; the intervals are 0.9 to 1.6 s. |
| T-PRV-12 | ws | Connect, receive, close; connect again with a new client; send no ready message. | The `run` task of the first connection has ended within 1 s of the close; the new client gets the newest frame of each camera. |
| T-PRV-13 | ws | Two clients on two rings at 30 fps for 5 s. Client 1 answers at once; client 2 never. | Client 1 gets at least 80 % of the frames (`pace`; 40 % on CI) (9.1); client 2 gets only safety-net camera messages (4 to 7 per camera). |
| T-PRV-14 | ws | Two rings; after 1 s, add a third reader to the fake manager and write frames to it. | The newest frame of the third camera arrives with no ready message, within 0.5 s after its first commit. |
| T-PRV-15 | ws | Ring A at frame 500, sent. (1) The client has answered; replace A's reader with a new ring at frames 0 to 3. (2) The client has not answered; replace it in the same way, then answer within 0.5 s of the last camera message for A (before the safety net). | (1) The next camera message for A has frame 3 of the new ring. (2) No camera message for A before the answer; then frame 3 or newer of the new ring. B continues in both cases (the rule of T-CAP-86): 8 camera messages after the new frame of A, within 0.5 s (`pace`) (9.1). |
| T-PRV-16 | ws | Two rings at 30 fps; A's writer stops (a failed or dead camera); the client answers at once. | After A's last frame, no camera message for A in 2 s; B gets at least 30 camera messages in those 2 s (`pace`) (9.1). |
| T-PRV-17 | ws | Remove A's reader from the fake manager, then close it, as `_close_rings` does; then send a ready message for A. | No exception; no camera message for A; no log record at WARNING or above; B continues. |
| T-PRV-18 | fake | Set A's ring `closed` while its reader stays in the fake manager; later replace the reader with a new ring. | No camera message for A while it is closed, and no exception; A's frames come again from the new ring. |
| T-PRV-19 | fake | (1) Flip one payload bit of A's newest frame after commit (`CORRUPT`); run 20 passes; then write the next frame. A spy counts the reads of the passes by frame number; it does not count the tick reads. (2) A stub reader whose `read` gives `NOT_YET_WRITTEN` for the check and `LAPPED` for the probe two times, then `OK`; the test calls the passes directly, with no tick. | (1) No message for the bad frame; the passes read it in one pass only; the next frame goes out. (2) No message for the two `LAPPED` passes; the `OK` frame goes out. No log record at WARNING or above in either case. |
| T-PRV-20 | fake | (1) Slow send. Cameras A, B, C in group 1; camera D in group 2. While the send of A waits: remove and close B's reader; replace C's reader with a new ring; remove group 2; call `handle_text` with a ready message for A. Then release the send. (2) A slow `send_json`: while the first `framerate_update` of a tick waits, remove and close B's reader and remove group 2. Then release it. | No exception, and `run` continues; no read through a closed reader (the closed reader raises if it is read); no message for B or D; C's next message is from the new ring; A is `ready` after the send (the ready message is not lost). (2) The same, for the tick: no read after its first `send_json`. |
| T-PRV-21 | fake | `handle_text` with: a valid ready message; `camera_id` missing; `camera_id` 7; an unknown camera id; text that is not JSON; `{"frameNumber": 3}`; `ping`. | Valid: `True`, camera `ready`. Missing and 7: `True`, one WARNING record each, nothing changes. Unknown id: `True`, no record. Not JSON, `frameNumber` and `ping`: `False`. No exception. |
| T-PRV-22 | fake | Ring 1: `arrival_ns` in steps of 33,333,333 ns and `source_frame_number` in steps of 2; three frames flagged `OVERSIZE`; one write skipped with `newer_frame_waiting=True`. Ring 2: `arrival_ns` in steps of 33,333,333 ns and `source_frame_number` -1. Two runs of 1.1 s: the fake client answers at once; the fake client never answers. | 3 or more `framerate_update` messages for the group in each run; `delivered_framerate.mean_frames_per_second` is 60.0 ± 0.5 for ring 1 and 30.0 ± 0.5 for ring 2, in both runs; `oversize_count` is 3; `ring_skipped_count` is 1 [A8]; for ring 1, `not_shown_count` equals (last sent − first sent + 1) − the frames sent − the skipped writes between the first and the last sent frame; no `backend_framerate` key. |
| T-PRV-23 | fake | Set `closing = True` on the fake manager for 0.5 s, then `False`. | No read and no message while it is `True`; messages again after. |
| T-PRV-24 | fake | `ServerFramerateCalculator`: update, `clear()`, update; also one update with a jump of 10^9 frames. `oversize_count` of a ring after two oversize frames; `skipped_count` of a ring after three writes with `newer_frame_waiting=True`. | After `clear()`, one update gives one exact interval; the jump returns at once and keeps at most `maxlen` durations; `oversize_count` is 2; `skipped_count` is 3. |
| T-PRV-54 | ws | Four rings at 30 fps for 5 s; the client answers late. After each camera message, the writer of that ring writes 5 more frames and pauses, as in T-PRV-07. Then the client answers. While the writer pauses, the newest frame at the send is the pause frame. | After each answer, the next camera message of that camera holds the newest frame at the send or one older (4.3): its `frame_number` is at least the pause frame minus 1. `frame_number` increases. Each camera gets more camera messages than the safety net can give. Blocking: the rule does not depend on the pace (Q670) [ADR-F4N7](../decisions/entries/F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md). |

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
| T-PRV-54 | runs | runs | runs |

Short form: each of the 25 tests runs on Windows, Linux and macOS. No test has a counterpart or a
reason to skip. The rings use `multiprocessing.shared_memory` on each system [ring 1.1].

### 9.4 CI [P7] [agent 24]

- The three jobs of `.github/workflows/capture.yml` (`capture-windows`, `capture-linux`,
  `capture-macos`) add `skellycam/tests/preview` to their test selection.
- The trigger paths add `specs/preview.md`. `skellycam/api/**` and `skellycam/tests/**` are already
  in them.
- This change is a CI change. It goes in its own PR ([AGENTS.md](../AGENTS.md#6-git-rules)).

## 10. What 4b must do

4b is the UI side [P1]. It needs its own spec. This list gives only what 4a needs from it.

1. **Server connection** (together with items 2 to 6 [A1]). In `WebsocketServer.run`, replace the
   task `_frontend_image_relay` with `PreviewRelay.run`. In `_client_message_handler`, give each text
   to `PreviewRelay.handle_text` first. Delete the items of 2.3.
2. **Parser.** Replace `binary-protocol.ts` and `binary-frame-parser.ts` with a parser of the
   48-byte header of 3.2 (DataView, little-endian). Refuse an unknown `version` (3.3).
   `frame_number` and `arrival_ns` are 64-bit: read them with `getBigInt64`. A JavaScript `number`
   is exact only up to 2^53, and `perf_counter_ns` values can be larger.
3. **Tile.** One tile for each camera, from the shared tile module of `specs/player.md` [P6], fed as
   section 11 states. After each draw, after a header-only message and after a failed decode, it
   sends the ready message of 4.1 for its camera [P2]. It keeps only the newest pending camera
   message of each camera, and sends one ready message for each draw (4.1). Delete the
   `frameAcknowledgment` message.
4. **Overlay** [P4]: the camera label, the frame rate of the camera (6.2), the state (all eight
   [A4]), and a mark while the last message of the camera has a bit of 0x0F.
5. **Frame rate viewer** [P4, A7]: per camera, "not shown" and the ring skipped count as two numbers
   with two names, the oversize count (6.2) and the replaced count (`app_state`, [A2]).
6. **Docs.** `skellycam-docs/docs/technical/websocket-protocol.mdx` and its `zh-CN`, `es` and `ar`
   copies [ring 2.1, A7]. Check `core/real-time-streaming.mdx`, `technical/api-reference.mdx` and
   `intro.mdx` for the old format.
7. **Tests.** The UI tests run in the TypeScript test runner of the player, on Windows, Linux and
   macOS [P7]. 4b measures 8 cameras at 60 fps on the main thread (section 11).
8. **Interface note** for the FreeMoCap session, at the end of 4b [P5]. It lists: the camera message
   (3.2) and its `version` rule; the ready message (4.1) and the safety net; the deletion of the group
   message and of the `frameNumber` acknowledgement; the new shape of `framerate_update` (6.2), which
   drops `backend_framerate` and `frontend_framerate`.

## 11. What the shared tile needs from phase 4

`specs/player.md` on branch `dom/player` specifies the shared tile [P6]. Phase 4 needs these from it:

- **A live source.** The preview feeds the tile from the camera messages. The tile must not need the
  take reader of the player.
- **A frame rate text** for each camera, from `delivered_framerate` (6.2) [P4, A3].
- **The camera state**, each of the eight states of [cap 8.1] [P4, A4].
- **A flagged-frame mark that keeps the last image.** A header-only message gives a draw with no new
  image: the tile keeps the last image and shows the mark [P4].
- **A rotation per frame**: the tile turns each image by its `rotation_cw_deg` when it draws [E].
- **The thread.** The tile runs on the main thread of the page and decodes with ImageDecoder
  (decision of the user). 4b measures 8 cameras at 60 fps. The tile moves to a worker only if that
  measurement misses its target.
- **A signal after each draw**, so that the preview can send the ready message (4.1).

## 12. Open points and weak points

### 12.1 Differences from the earlier specs

The earlier specs are accepted, so this spec does not edit them:

1. P4 lists six states. [cap 8.1] has eight. A4 decides: the tile shows all eight.
2. A2 adds `replaced_count` to the camera status in step 3a. [cap 8.4] and the tests of step 3a do
   not have it yet. They must get it with the code of step 3a.
3. A5 adds `oversize_count` to the reader API of
   [ADR-9G2W](../decisions/entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md).
   A8 adds `skipped_count` in the same way (5.2).
4. T-RING-33 [ring 12] and T-CAP-86 [cap 16.2] test the old relay. 4b deletes them. T-PRV-02,
   T-PRV-09, T-PRV-14 and T-PRV-15 keep their rules.
5. [ring 2.1] keeps `frontend_payload_bytearray.py` for the interim relay [ring A56]. 4b deletes the
   file.

### 12.2 Known weak points

- The sender polls. `asyncio.sleep(0.01)` gave 10 to 12 ms on one Windows machine [M review]. Other
  machines can differ. M-PRV-4 measures it.
- The reads run on the event-loop thread that also serves the HTTP API. 8 cameras at 60 fps use about
  a quarter of that thread for each client [M review estimate]. M-PRV-3 measures the effect on the
  HTTP response time.
- Each client reads the rings for itself. Two clients double the read cost.
- A client between 1 frame and 1 s behind costs two reads for each message (5.2).
- The tick reads copy JPEGs also when no client is ready (6.3).
- "Not shown" also counts a frame that a failed read stopped (6.1).
- Phase 3 must keep `CameraGroup.ring_readers` as a dict from camera id to reader, and must put a
  new reader object there for each new ring. 4b adapts the sender if phase 3 changes it.

## 13. Choices of the agent

Each item fills a gap that the decisions, the answers and the earlier specs do not fix. The body
marks each one [agent n].

1. The module layout and names of 2.1, the API of section 7 and the helpers of 9.1.
2. Byte 0 is `version` = 1, and it is also the message type; the rule to increase it; a parser
   refuses an unknown value.
3. The field order and offsets of 3.2: a 48-byte header, each field aligned to its size.
4. `camera_id` in 16 ASCII bytes, NUL-padded, as the old format and the ring `camera_key`; no
   message and one ERROR record for an id that does not fit.
5. "The camera's frame number" of P3 is the ring `frame_number` [ring 1.4], not
   `source_frame_number`.
6. The 32 bits of `flags` are copied, also the bits that are not errors.
7. `last_tried`: the probe starts after the last frame read with any result except `LAPPED`, so a
   `CORRUPT` or `MISSING` frame is read one time only by the passes.
8. A flagged or oversize frame goes out as a header-only message with `jpeg_len` 0. `jpeg_len` is
   the count of bytes in the message, not the ring `payload_len`.
9. The ready message `{"message_type": "camera_ready", "camera_id": ...}`.
10. Each camera starts `ready` on a new connection. Thus the first frame goes out with no ready
    message.
11. The safety net counts 1 s from `sent_at`, on `time.monotonic()`.
12. A new ring resets `last_tried`, `last_sent` and `skipped_at_send`, and keeps `ready`, `sent_at`,
    `not_shown` and `rate`.
13. A pass 10 ms after the previous pass (the `await_10ms` of today), and at once after a ready
    message.
14. The sender runs on the event-loop thread, loops over copies of the dicts, and looks each reader
    up again after each `await`.
15. Steps 4 and 5 of 4.3: `read(last_tried + 2)` first tells with no copy if frame
    `last_tried + 1` is the newest, so a client that keeps up costs one copy for each message, and a
    client that is behind costs two.
16. The state of a camera changes before the `await` of its send.
17. Each connection has its own sender, state and reads.
18. A failed read sends nothing and writes no log record.
19. The new shape of `framerate_update`; the frame rate fed at each message and by one tick read for
    each camera; a tick reads all cameras before its first send; the move of `ServerFramerateCalculator` to `framerate_tracker.py`; `clear()` keeps
    the last observation; the duration loop is bounded by `maxlen`.
20. The formula of "not shown": the gap of `frame_number` minus the increase of the ring
    `skipped_count`, for each connection, since the connection started.
21. A ready message with a bad `camera_id` gets one WARNING record; an unknown camera id is ignored
    with no record; neither closes the connection.
22. The test route cancels `run` when the client disconnects.
23. The pass thresholds of 9.2, loose for slow CI runners.
24. The CI change of 9.4, in its own PR.
25. One message is one `bytes` object: header and JPEG together, one copy of the JPEG.
26. No reads and no messages while `CameraGroupManager.closing` is `True`.
27. The sends of one connection are in series under its send lock.

## 14. Questions for the user

None open. The user answered Q1 on 2026-11-19 (A8).

## 15. Decisions and answers of the user

The user decided these on 2026-11-19
([ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)). They are
binding.

Earlier binding statements [E]: one websocket message for each camera frame; the JPEG untouched, no
resize, no re-encode; the preview does not depend on the group gate; the UI rotates when it draws;
the tile decodes with ImageDecoder and is shared with the player (Y3); the UI runs on the machine
with the cameras.

Decisions P1 to P7 (Q233 to Q239):

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

Answers A1 to A8 to the first draft:

- A1: 4a adds the sender and its tests with no route. The endpoint keeps the old relay. 4b connects
  the sender, deletes the old code and changes the UI together. The branch goes to
  `development-streaming` only after 4b.
- A2: Step 3a adds `replaced_count` to the status of each camera, counted from the first frame that
  the camera takes in the gate. The app state carries it. The sender does not compute it.
- A3: The frame rate of the tile is the rate at which the camera delivers frames to skellycam, not
  the rate that reaches the screen. It must not depend on the client.
- A4: The tile shows all eight states of the capture spec.
- A5: The ring reader gets one new read-only property, `oversize_count`. No `head` property: the
  sender uses `reader.read(last_sent + 1)` and its `NOT_YET_WRITTEN` result. This adds to the reader
  API of ADR-9G2W by decision of the user.
- A6: Safety net: when a camera has had no ready message for 1 s, the server sends its newest unsent
  frame anyway.
- A7: The frame rate viewer shows two separate numbers with clear names: "not shown" (frames that
  the server did not send because the screen was slower than the camera) and the ring's own skipped
  count. Never one mixed number.
- A8 (answer to Q1): The ring reader gets a second read-only property, `skipped_count`, of the same
  kind as `oversize_count`, for display only. This adds to the reader API of ADR-9G2W by decision of
  the user.

Answers A9 and A10 to the measurements of 4a (2026-11-20), recorded in ADR-G651:

- A9: Turn off websocket compression: the server starts uvicorn with `ws_per_message_deflate=False`.
- A10: The event-loop target of 8.4 (4 cameras at 1080p30, one client that keeps up) becomes the
  number measured in 4a with compression off.

Decision on the tile thread (relayed with A1 to A7): the tile runs on the main thread of the page
with ImageDecoder. 4b measures 8 cameras at 60 fps. A worker only if the target is missed.
