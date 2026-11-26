# Interface note of the live preview for the FreeMoCap session (step 4b)

Status: written at the end of step 4b ([`preview-4b.md`](preview-4b.md) section 8). It states the facts of the
preview interface after 4b, for a client such as the FreeMoCap UI. The binding texts are
[`preview.md`](preview.md) (4a) and [`preview-4b.md`](preview-4b.md). T-PRV-31 checks the headings and the table of
section 1.

## 1. Camera message

Each binary websocket message of `/skellycam/websocket/connect` is one camera message: one frame of one camera
([`preview.md`](preview.md) 3.2). The Python form is `struct.Struct("<B3xIqqII16s")`. All values are little-endian.

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

- **Version.** A change of an offset, a size, a type or the meaning of a field increases `version` by one. A client
  that sees a value other than 1 refuses the message and logs both values ([`preview.md`](preview.md) 3.3).
- **BigInt.** `frame_number` and `arrival_ns` are 64-bit. A JavaScript client reads them with `getBigInt64`. A frame
  number of a camera stays below 2^53, so `Number(frameNumber)` is exact for a label.
- **Flagged frame.** When `flags & 0x0F` is not zero, the message is the header only: `jpeg_len` is 0. The client
  keeps the last image and shows the mark "flagged frame".
- The message length is `48 + jpeg_len`. A client refuses a message of another length, a rotation outside the four
  values and an empty camera id. The JPEG is the ring JPEG, untouched: no resize, no re-encode, no rotation. The
  client turns the image by `rotation_cw_deg`.

## 2. Ready message and safety net

- After the client has drawn the frame of a camera message, it sends one text message for that camera:
  `{"message_type": "camera_ready", "camera_id": "a1b2"}` ([`preview.md`](preview.md) 4.1). It also sends it after a
  header-only message and after a JPEG that does not decode.
- **Newest pending.** The client keeps only the newest camera message of each camera that waits for a draw. A newer
  message replaces it; a replaced message gets no ready message.
- **One ready message for each draw**, not one for each received message. The client gives each tile one update at a
  time, at most one for each display refresh.
- **Safety net.** The server sends a camera its next message only after the ready message of the last one, or 1 s
  after the last send. A hidden window that draws nothing thus gets one message each second for each camera.

## 3. Deleted

Step 4b deleted these, with no period of two formats:

- the group message: one binary message with the frames of all cameras of a group, with its payload header, frame
  headers and footer (`frontend_payload_bytearray.py`);
- the `frameNumber` acknowledgement of the client (`{"frameNumber": ..., "displayImageSizes": ...}`);
- `backend_framerate` and `frontend_framerate` of `framerate_update`.

## 4. framerate_update

The server sends one message for each group every 0.25 s, with one item for each camera
([`preview.md`](preview.md) 6.2):

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

- `delivered_framerate`: a `CurrentFramerate`, or `null`. It is measured where the frames enter the ring, from the
  frame numbers and the arrival times, so it does not depend on the client.
- `not_shown_count`: the frames that the server did not send on this connection since it started, because the client
  was slower than the camera.
- `ring_skipped_count`: the frames that the ring skipped. `oversize_count`: the frames larger than their ring slot.
- The counts are separate numbers. A client never adds them.
- The two series of the SkellyCam viewer ([`preview-4b.md`](preview-4b.md) 5.8): **Captured** is
  `delivered_framerate`. **Displayed** is computed by the client: the rate over the frames that its window drew in
  the last 1 s.

## 5. Camera status

- The status of each camera is in `app_state`, at `state.camera_groups[<group id>].cameras[<camera id>].status`:
  `state` (one of `starting`, `waiting`, `failed`, `checking`, `too_slow`, `ready`, `recording`, `dead`, or `null`
  before the first state) and `replaced_count` (the frames that the gate replaced).
- `app_state` comes at most one time each second, when it changes.
- The group flag `alive` is not a filter for the tiles: each camera in `cameras` gets a tile, also a camera in
  `starting`, `failed` or `dead`. The cameras that stream are the cameras in `checking`, `too_slow`, `ready` or
  `recording`.

## 6. Tile

- The tile is the module `skellycam-ui/src/player/`. React code imports it with
  `import { Tile } from '@/player/index.ts'`. A copy of the folder is the way for the FreeMoCap UI
  (`specs/player.md` 4.3).
- The tile decodes the JPEG with `ImageDecoder` and draws on the main thread. The product never reads a tile canvas
  back.
- The `TileUpdate` of a camera message: `jpeg` (`null` for a flagged message), `rotationCwDeg` from the header,
  `label` = `{frame: Number(frameNumber), frameDigits: 6, camera: <camera list label>, timeNs: null, nominalFps: 0}`,
  `rateText` = the Captured rate to 1 decimal and " fps" (or `null`), `cameraState` from `app_state`, and `mark`
  `{kind: 'flagged'}` for a flagged message. Before the first frame, `label.frame` is `null`.
- The camera list label is `Camera <number> · <name>`, for example `Camera 6 · c922 Pro Stream Webcam`: the number and
  the name of the camera list, else `camera_index` and `camera_name` of the config. It never holds the camera id.

## 7. Compression

Websocket compression is off on the server ([`preview.md`](preview.md) A9). A client must not need it.
