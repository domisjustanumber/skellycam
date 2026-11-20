# Phase 4 preview specification, step 4b: the UI side, the connection of the sender, the deletion

Status: proposed. An agent wrote it on 2026-11-20. The user has not read it.
[ADR-EE0E](../decisions/entries/EE0E-step-4b-preview-spec-and-agent-choices.md) holds the agent
choices of revision 1. Revision 2 of 2026-11-20 applies the faults of an independent review.
[ADR-R1TD](../decisions/entries/R1TD-revision-2-of-the-step-4b-preview-spec.md) lists its changes
and the choices of revision 1 that it replaces. The accepted step 4a spec [`preview.md`](preview.md)
does not change. This file adds step 4b. The failing tests of step 4b come before the product code
of step 4b, and only after the user accepts this spec.

## 0. How to read this spec

Marks:

- **[Pn]**, **[An]**: decision n and answer n of the user for phase 4
  ([ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md)).
- **[E]**: an earlier binding statement of the user, as section 15 of [`preview.md`](preview.md)
  lists them.
- **[T]**: a decision of the user on the tile and on step 4b that the task of 2026-11-20 relayed:
  one tile for the player and the preview; the main thread with ImageDecoder; 8 cameras at 60 fps
  measured in 4b with an observer outside the page; a worker only if the target is missed; the
  counts in the frame rate viewer under separate names; the newest pending message per camera and
  one ready message per draw; the old group message deleted with no period of two formats; the
  branch to `development-streaming` only after 4b; an interface note at the end of 4b; no read-back
  of a tile canvas; websocket compression off.
- **[4a x.y]**: section x.y of [`preview.md`](preview.md), accepted
  ([ADR-WB08](../decisions/entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md)).
- **[player x.y]**: section x.y of `specs/player.md` on branch `dom/player`, accepted there
  (`ADR-YV3V` of that branch), read on 2026-11-20. The code facts are from
  `skellycam-ui/src/player/tile/tile.ts` of that branch.
- **[cap x.y]**: section x.y of `specs/windows-capture.md` on branch `dom/native-jpeg`, which has
  `replaced_count` in 8.4. The copy on this branch does not have it yet.
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md).
- **[M source]**: measured; the source holds the result. **[NV]**: not verified.
- **[agent n]**: an agent filled a gap. Section 11 lists each one. **[Qn]**: question n of section 12.

This spec uses British spelling. Code names are from `dom/preview`, `dom/player` and
`dom/native-jpeg`, read on 2026-11-20. It cites files, not line numbers, except where a review
finding cites a line.

## 1. Purpose, scope, non-goals

### 1.1 Purpose

Step 4b makes the UI read the camera message of [4a 3]. It connects `PreviewRelay` to the live
websocket endpoint, deletes the old group message and its code, and draws each camera in the shared
tile [P1, P5, P6]. After 4b, the wire carries one format, and the UI reads it [A1].

### 1.2 Scope

- Server: the connection of `PreviewRelay` to `/websocket/connect`, the lifecycle for each
  connection, the thread that closes ring readers (section 4).
- UI: the parser of the camera message, the flow control for each camera, the shared tile for each
  camera, the overlay values, the grid, the frame rate viewer (section 5).
- The deletion of the old group message, its code, its tests and its docs (section 3).
- The measurement of 8 cameras at 60 fps on the main-thread tile (section 6) [T].
- The tests (section 7) and the interface note for the FreeMoCap session (section 8) [P5].

### 1.3 Non-goals

- A resize, a quality setting, a rate cap, a rate setting, a remote-UI mode [E, P2].
- A worker for the tile. Section 6.4 gives the only way to add one [T].
- A change of the flow rules of the sender [4a 4]. The fallback of 4.3 adds a lock only if the
  capture branch cannot keep the closes on the event-loop thread [Q4].
- A change of the player, the take reader or the tile, except the one change of [Q1].
- A display of `measured_fps` of the camera status [agent 14].
- The performance page and `CameraGroup.read_latest_ring_frames` [ring A5].
- A change of the Redux camera slice (`connectionStatus`).
- A translation of new text into the 40 other UI locales and into the docs copies [Q8].

## 2. Before the code: the merges and their order [Q2]

4b needs code from two other branches. Merge each one into `dom/preview` with `git merge`:

1. **`dom/native-jpeg`, now.** It holds the camera states and `replaced_count` of the status
   [cap 8.4], and the capture code whose ring closes 4.3 discusses. It also changes
   `get_latest_ring_payload` and T-CAP-86, which 4b deletes. A merge after the deletion would
   conflict. `git merge-tree` finds one conflict: `decisions/README.md`.
2. **`dom/player`, before the first UI test commit.** It holds the shared tile
   `skellycam-ui/src/player/` [player 4.1], the UI test runners [player 12.1] and
   `.github/workflows/player.yml`. The branch exists only on the development machine now. It is not
   pushed, and its code choices (ADR-1ACK of that branch) wait for the user. The merge before that
   acceptance is the decision of the user [Q2]. `git merge-tree` finds two conflicts:
   `decisions/README.md` and `decisions/open-work.md`.

In each conflict, keep the rows and the items of both sides. The Python tests of 4b (T-PRV-25 to
T-PRV-31) need only the first merge.

Import path of the tile:

- React code: `import { Tile } from '@/player/index.ts'` and
  `import type { CameraStateName, TileUpdate } from '@/player/index.ts'`, as
  `CanvasTakePlayer.tsx` of `dom/player` does.
- A file that the Node unit tests load: a relative `import type` of `../../../player/index.ts`.
  Node type stripping does not know the `@/` alias [player 4.2].
- No file outside `src/player/` imports another file of the module. T-PLAY-35 checks it
  [player 4.2]. 4b does not copy the tile [P6].

The 4b PR to `development-streaming` thus also carries the code of the merged branches, unless they
land first. The branch goes to `development-streaming` only after 4b [A1].

## 3. What 4b deletes, and what replaces it [P5]

### 3.1 Code

| Item | Replacement |
|---|---|
| `skellycam/api/websocket/websocket_server.py`: `_frontend_image_relay`, `check_frame_acknowledgment_status`, the JSON branch of `_client_message_handler` with its `frameNumber` case, the fields `last_sent_frame_number`, `last_received_frontend_confirmation`, `_last_sent_by_group`, `_display_image_sizes`, `_server_framerate_calculators`, `_display_framerate_trackers`, `_last_framerate_send_time`, `FramerateUpdateMessage`, `BACKPRESSURE_WARNING_THRESHOLD`, and the imports that only they use | `PreviewRelay.run` and `PreviewRelay.handle_text` (4.1) |
| `skellycam/core/camera_group/camera_group.py`: `get_latest_ring_payload` and its imports of `frontend_payload_bytearray` | `pack_camera_frame` [4a 7] |
| `skellycam/core/camera_group/camera_group_manager.py`: `get_latest_frontend_payloads`, `get_backend_framerate_updates`, and the imports that only they use | The sender reads `ring_readers` and computes the rates [4a 5, 6] |
| `skellycam/core/types/frontend_payload_bytearray.py` (the whole file) | `CAMERA_FRAME_HEADER` [4a 3.2] |
| `skellycam-ui/src/services/server/server-helpers/frame-processor/` (the whole folder: `binary-protocol.ts`, `binary-frame-parser.ts`, `frame-processor.ts`, `frame-decode.worker.ts` with its copy of the protocol constants) | `preview/camera-message.ts` (5.2); the decode of the tile [player 8.1] |
| `skellycam-ui/src/services/server/server-helpers/canvas-manager.ts` and `offscreen-renderer.worker.ts` | The shared tile on the main thread [T, player 8.1] |
| In `ServerContextProvider.tsx`: the pending group payload, the decode loop, `dispatchFrames`, the `frameAcknowledgment` send, the old `framerate_update` type and guard, `serverFpsRef`, `getFps`, `getServerFps`, `setCanvasForCamera`, the camera list from frames | `PreviewTiles` (5.3); `preview/server-messages.ts` (5.5) |
| `skellycam-ui/src/services/server/index.ts`: the exports of the deleted files | The exports of `preview/` |
| `CameraView.tsx`: the label and frame rate box in the DOM (`#index · id`, `D:`, `S:`) | The overlay of the tile [player 8.4, Y3] |
| `framerate-store.ts` and the frame rate viewer: the two series "Server" (`backend`) and "Display" (`frontend`) | The values for each camera (5.7) [Q3] |
| The docs of the group message (5.8) | The camera message, the ready message and the new `framerate_update` |

`read_latest_ring_frames` stays for the performance data [ring A5]. The `FRAMERATE` subscription
of `CameraGroupManager` stays [agent 13].

### 3.2 Tests

| Deleted test | Its rule | What keeps the rule |
|---|---|---|
| `skellycam/tests/test_image_payload.py` | The layout of the group message | T-PRV-01 [4a 9.2]; T-PRV-25 and T-PRV-32 (one fixture, Python and TypeScript) |
| T-RING-33 in `skellycam/tests/frame_ring/test_camera_process.py` | The relay sends the ring JPEG untouched | T-PRV-02 [4a 9.2]; T-PRV-26 (the product endpoint) |
| T-CAP-86 in `skellycam/tests/capture/test_states.py`, with `_collect`, and `parse_relay` in `capture_session.py` | Each camera on its own while one camera reopens | T-PRV-09, T-PRV-14, T-PRV-15 [4a 9.2]; T-PRV-48 (the UI) |
| `test_websocket_frame_acknowledgment` in `skellycam/tests/test_websocket.py` | A client text keeps the connection open, and `ping` works after it | T-PRV-21 [4a 9.2]; T-PRV-27 (the product endpoint) |
| The mocks `get_latest_frontend_payloads` and `get_backend_framerate_updates` in `skellycam/tests/conftest.py` | none (mocks) | The mock manager gets `closing = False` instead |

The other three tests of `test_websocket.py` (connect, `ping`, `app_state`) fail on `dom/preview`
today. `websocket_server_connect` calls `logger.success`, which exists only after
`skellylogs.configure_logging`, and no test configures it: each test stops with
`AttributeError: 'Logger' object has no attribute 'success'` (run on 2026-11-20). 4b adds a
session fixture to `skellycam/tests/conftest.py` that calls `configure_logging` as
`skellycam/__main__.py` does. Then these three tests and T-PRV-26 to T-PRV-28 can pass
[agent 19]. `test_websocket_internals.py` and `test_websocket_compression.py` stay.

## 4. Server

### 4.1 The connection of `PreviewRelay` to the endpoint

In `WebsocketServer`:

1. `__init__` makes `self._preview = PreviewRelay(self._cgm, self._send_bytes,
   self._send_msgspec_json)`. The two send functions hold the send lock [4a agent 27]. ADR-24FZ
   item 2 allows `_send_msgspec_json` as `send_json`.
2. `run` starts the task `_preview_relay` in place of `_frontend_image_relay`. `_preview_relay`
   awaits `self._preview.run()`. It has the same `except` clauses and the same `finally:
   self._signal_shutdown()` as `_logs_relay` [agent 1].
3. `_client_message_handler` gives each text to `self._preview.handle_text(text)` first. When the
   result is `True`, it does nothing more. Else it keeps `ping` (answers `pong`) and `pong`, and it
   logs each other text at INFO, as today [4a 4.1].
4. The JSON branch with `frameNumber` is deleted. A text that starts with `{` and is not valid JSON
   is now logged at INFO. Before 4b, it raised `ValueError`, which set the global kill flag.

### 4.2 Lifecycle for each connection

| Event | What happens |
|---|---|
| Accept | `websocket_server_connect` makes one `WebsocketServer`. It makes one `PreviewRelay` with new state. Each camera starts ready [4a 4.4]. |
| Run | Four tasks: `_preview_relay`, `_logs_relay`, `_client_message_handler`, `_app_state_sender`. |
| A `camera_ready` text | `handle_text` marks the camera ready and wakes `run` [4a 4.1]. |
| The client disconnects | `_client_message_handler` calls `_signal_shutdown`. It cancels each task, also `_preview_relay`. The sender and its state end with the connection. |
| A send fails | `PreviewRelay.run` raises [ADR-MZ02 item 6]. `_preview_relay` catches it as the other tasks do and calls `_signal_shutdown`. |
| Reconnect | A new connection gets a new `WebsocketServer` and a new sender [4a 4.4]. |

### 4.3 The thread that closes a ring reader [Q4]

**The fault.** On `dom/native-jpeg`, the watch thread of `CameraGroup` (`_watch_workers`) calls
`_close_rings` for the camera of an ended process, under `CameraGroup._ring_lock` (a
`threading.RLock`). The sender reads on the event-loop thread with no lock [4a 5.1]. After the merge
of 2, a read can thus run while another thread closes its reader: a read of a released buffer. The
independent review reproduced it on the merged tree.

**The planned fix, on the capture branch.** The supervisor has asked the capture branch to make
"a ring reader is closed only on the event-loop thread" true: the watch thread hands the close to
the event loop (for example with `loop.call_soon_threadsafe`). Then [4a 5.1] stays true as written,
and the sender does not change. T-PRV-29 part 1 fails while a reader is closed on another thread.

**The fallback, only if that fix is not possible** [Q4]. The sender then holds the lock of the group
(`_ring_lock`, with no rename) for each part that touches a reader or the dict:

- in a pass, for each camera, from the look-up (step 1 of [4a 4.3]) to the update of the state
  before the send, also the read of `reader.skipped_count` (step 7.2); it releases the lock before
  the `await` of the send;
- the copy `list(group.ring_readers)` at the start of the pass, and the final loop that removes the
  state of each camera id that is no longer present;
- in a tick, the copy of the camera ids and the reads of each camera, released before the first
  `send_json` [4a 6.3].

The sender never holds the lock across an `await`. The fake group of the tests then gets
`_ring_lock = threading.RLock()`. T-PRV-29 part 2 tests the fallback. The lock is held for at most
two reads and one pack: about 0.6 ms at 1080p
[ADR-HDC9](../decisions/entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md).

### 4.4 Other messages of the endpoint

| Message | Direction | Source | Change in 4b |
|---|---|---|---|
| Camera message (binary) | server to client | `PreviewRelay` [4a 3] | new on the wire |
| `framerate_update`, the shape for each camera | server to client | `PreviewRelay` tick [4a 6.2] | new on the wire; the old shape is deleted |
| `app_state` | server to client | `_app_state_sender` | none; it carries the camera status (4.5) |
| `log_record` | server to client | `_logs_relay` | none |
| `pong` | server to client | `_client_message_handler` | none |
| `camera_ready` | client to server | the UI (5.3) | new |
| `ping`, `pong` | client to server | `WebSocketConnection` heartbeat | none |
| `frameAcknowledgment` | client to server | deleted | deleted |

### 4.5 How the camera status reaches the UI

The camera status of [cap 8.4] is in `app_state`, at
`state.camera_groups[<group id>].cameras[<camera id>].status`. `CameraGroup.to_state` puts it there
through `CameraWorker.to_state` (`status=...serialize()`). 4b adds no message for it.

| Value | Key | Use in the UI |
|---|---|---|
| State | `status.state`: one of the eight states [cap 8.1], or `null` before the first state | `cameraState` of the tile (5.4) [A4] |
| Replaced count | `status.replaced_count` | "Replaced" in the frame rate viewer (5.7) [A2] |
| Measured rate of the rate check | `status.measured_fps` | not shown [agent 14] |
| Camera label | `configs[<camera id>].camera_name` | `label.camera` of the tile [4a 6.1] [Q5] |

`app_state` comes at most one time each second, when it changes [4a 6.1]. A state change thus
shows on the tile within about 1 s.

The group flag `alive` is not a filter for the tiles. On `dom/native-jpeg`, `CameraGroup.alive` is
`False` when a worker process has ended, or when a status is not `connected`, is `closed`, is
`closing` or has `error`; and `connected` is set only after the camera opens (`camera_loop.py`,
line 304). One camera in `starting`, `failed` or `dead` thus makes the whole group not alive.

## 5. UI

### 5.1 Files [agent 3]

| Path | Content |
|---|---|
| `skellycam-ui/src/services/server/preview/camera-message.ts` | `parseCameraMessage` (5.2). No import except types. |
| `skellycam-ui/src/services/server/preview/preview-tiles.ts` | `PreviewTiles`: the newest pending message, the flow control, the tile updates (5.3, 5.4). It imports only `import type` of the tile. |
| `skellycam-ui/src/services/server/preview/server-messages.ts` | Pure functions from an `app_state` or a `framerate_update` object to the values of 5.5. The provider calls them. Node can load the file, so T-PRV-40 tests it. |
| `skellycam-ui/src/services/server/preview/tests/unit/` | The Node unit tests (7.1). |
| `skellycam-ui/src/services/server/preview/tests/camera-messages.json` | The shared fixture. `tools/write_camera_message_fixture.py` writes it (7.2). |
| `skellycam-ui/src/components/camera-views/tests/` | The component tests, the harness page `preview/index.html` with `page.tsx`, and the benchmark (7.1, section 6). |
| `skellycam/tests/preview/ui_server.py` | The server of the UI tests (7.2). |

The new `.ts` files of `preview/` use only syntax that Node type stripping removes, and relative
imports that name the `.ts` file, as the player module does [player 4.2].

### 5.2 The parser

```ts
export const CAMERA_FRAME_VERSION = 1;
export const CAMERA_FRAME_HEADER_SIZE = 48;
export interface CameraMessage {
  flags: number;             // u32 at offset 4
  frameNumber: bigint;       // i64 at offset 8, getBigInt64
  arrivalNs: bigint;         // i64 at offset 16, getBigInt64
  rotationCwDeg: 0 | 90 | 180 | 270;
  cameraId: string;          // ASCII at offset 32, up to the first NUL
  jpeg: Uint8Array | null;   // a view of the bytes after the header; null when flags & 0x0F
}
export function parseCameraMessage(data: ArrayBuffer): CameraMessage;   // throws Error(reason)
```

- It reads the header of [4a 3.2] with one `DataView`, little-endian.
- `frame_number` and `arrival_ns` are `BigInt` [4a 10 item 2].
- It refuses a message and throws an `Error` that names the reason [agent 4]:
  - `version` is not 1. The text holds both values [4a 3.3];
  - the message is shorter than 48 bytes, or its length is not `48 + jpeg_len`;
  - `rotation_cw_deg` is not 0, 90, 180 or 270;
  - `camera_id` is empty.
- `PreviewTiles` catches the error. It writes one `console.error` for each reason and connection,
  and drops the message. It sends no ready message for it, because its camera id is not trusted.
- `jpeg` is a view, not a copy. The tile decodes from it [player 8.1].
- A message with a bit of 0x0F has `jpeg` `null` [4a 3.3]. Its mark is `flagged` (5.4).

### 5.3 Flow control: `PreviewTiles` [P2, A6] [agent 5]

```ts
type TileLike = Pick<Tile, 'update'>;
export class PreviewTiles {
  constructor(sendReady: (cameraId: string) => void);
  readonly tiles: Map<string, TileLike>;
  readonly drawnCount: Map<string, number>;         // updates that resolved 'drawn' with a JPEG
  setTile(cameraId: string, tile: TileLike | null): void;
  receive(data: ArrayBuffer): void;                 // a binary websocket message
  setOverlay(cameraId: string, values: Partial<{ label: string | null;
             cameraState: CameraStateName | null; rateText: string | null }>): void;
  setPaused(paused: boolean): void;
  clearPending(): void;                             // the connection closed
  tick(): void;                                     // one display refresh
}
```

State for each camera: `pending` (the newest camera message not yet given to the tile), `busy`
(one tile update in flight), the overlay values, `overlayChanged`, the last label and mark.

Rules:

1. **Newest pending.** `receive` parses the message and puts it in `pending` of its camera. A newer
   message replaces it. A replaced message is never drawn and gets no ready message [T, 4a 4.1].
2. **One update in flight.** `tick` gives a tile an update only when `busy` is false. Thus the
   tile never supersedes an update of the preview.
3. **A camera message to the tile.** At `tick`, for each camera with a tile, `busy` false and a
   `pending` message: take the message out of `pending`, set `busy`, and call `tile.update` (5.4).
4. **One ready message for each draw.** When that promise resolves, with `'drawn'` or
   `'superseded'`, clear `busy` and call `sendReady(cameraId)`. The provider sends
   `{"message_type": "camera_ready", "camera_id": ...}` [4a 4.1]. The tile resolves `'drawn'` also
   after a JPEG that does not decode [player 8.3], so a bad JPEG also gets its ready message
   [4a 4.1]. With rule 2, `'superseded'` comes only from `tile.close()`. When the result is
   `'drawn'` and the update had a JPEG, `drawnCount` of the camera goes up by one. It counts
   resolved updates, so it also counts a JPEG that did not decode (6.3).
5. **An overlay change with no new frame.** At `tick`, for a camera with a tile, `busy` false, no
   `pending` message and `overlayChanged`: set `busy`, call `tile.update` with `jpeg: null` and the
   current overlay. When it resolves, clear `busy`. No ready message. A frame update also carries
   the current overlay and clears `overlayChanged`.
6. **The display drives the draws.** The provider calls `tick` in a `requestAnimationFrame` loop,
   as today's loop does. Thus a tile draws at most one camera message for each display refresh. A
   hidden page runs no `requestAnimationFrame` in the product window (default
   `backgroundThrottling`) [NV on Linux and macOS, 7.4]. It then draws nothing, sends no ready
   message, and the server sends only the safety-net messages: one each second for each camera
   [A6, 4a 4.1]. The UI has no timer of its own: the 1 s safety net is the server's.
7. **Paused.** `setPaused(true)` (today's `setStreamPaused`, the playback tab) makes `tick` do
   nothing. Messages stay newest-pending.
8. **No tile yet.** A message for a camera with no tile stays in `pending` and gets no ready
   message. When `setTile` gives the tile, the next `tick` draws it.
9. **Tile removed.** `setTile(id, null)` drops the `pending` message and the state of that camera.
   The caller closes the tile.
10. **Connection closed.** The provider calls `clearPending()` on each close. It drops each
    `pending` message. The tiles and their images stay. An update in flight can send its ready
    message on the next connection; the server ignores a ready message for a camera that is ready
    [4a 4.1].

### 5.4 The tile for each camera

`CameraView` makes `new Tile(canvas)` with the default options [player 8.3], and calls
`previewTiles.setTile(cameraId, tile)`. On unmount it calls `setTile(cameraId, null)` and
`tile.close()`. The tile draws on the main thread with ImageDecoder [T, player 8.1].

The update of rule 3 of 5.3:

| `TileUpdate` field | Value |
|---|---|
| `jpeg` | `message.jpeg` (`null` for a flagged message) |
| `rotationCwDeg` | `message.rotationCwDeg`, from the header [E, 4a 3.3] |
| `label` | `{ frame: Number(message.frameNumber), frameDigits: 6, camera: <label>, timeNs: null, nominalFps: 0 }` [agent 6] |
| `rateText` | `<mean_frames_per_second to 1 decimal> fps` from `delivered_framerate` [4a 6.2]; `null` when it is `null` [agent 7] |
| `cameraState` | `status.state` of `app_state`, when it is one of the eight states; else `null` [A4] |
| `mark` | `{ kind: 'flagged' }` when `flags & 0x0F`; else `null` [P4] |

- `Number(frameNumber)` is exact up to 2^53. A frame number of a camera does not reach it.
- `<label>` is `camera_name` of the config [4a 6.1]. With "yes" to [Q5], it is
  `<camera_name> · <camera id>`.
- `timeNs` is `null`, so the label has no time part. `arrival_ns` is a `perf_counter_ns` value, not
  a time from a start.
- The rate text and the state come from `framerate_update` and `app_state`. `setOverlay` stores
  them (rule 5 of 5.3).

What a tile shows:

| Case | Tile |
|---|---|
| Before the first frame | Black, with the state (for example `starting`) and the label with no frame part [Q1]. |
| A frame | The image, turned by its rotation, with the label, the rate text and the state [player 8.4]. |
| A flagged frame | The last image stays. The mark "flagged frame" shows. The frame part is the number of the flagged frame. The next good frame removes the mark [P4, 4a 10 item 4]. |
| `failed` before any frame | Black, with `failed` and the label [Q1]. |
| `dead`, or `failed` after frames | The last image stays, with `dead` or `failed`. The rate text goes away when `delivered_framerate` becomes `null`. |
| A ring recreated (a mode change, "apply again") | The frames of the new ring show. Their frame numbers start again at 0 [4a 4.4]. |
| The camera leaves `app_state` | The tile leaves the grid and closes. |
| The connection drops; `WebSocketConnection` tries again (`RECONNECTING`) | Each tile keeps its last image and overlay. |
| The connection is `DISCONNECTED` or `FAILED` | The provider clears its camera lists, as it clears today's list. The grid shows its empty state. |
| A hidden page or the playback tab | No draw. The tile keeps its last image. |

The product never reads a tile canvas back (`getImageData`, `toDataURL`, `toBlob`, `readPixels`)
[T, player 8.3]. T-PRV-42 checks it.

### 5.5 Text messages in the provider

`server-messages.ts` holds the logic. The provider only calls it and stores the results.

- `app_state`: as today, `serverStateReceived` goes to the store. Also, for each group and each
  camera id in its `cameras`, with no filter on `alive` (4.5):
  `setOverlay(id, { label, cameraState: status.state })`, and the two lists of [Q7]:
  - `gridCameraIds`: each camera id in the `cameras` of each group, in the order of
    `configs[id].camera_index`. The grid shows one tile for each.
  - `connectedCameraIds`: the ids of `gridCameraIds` whose state is `checking`, `too_slow`,
    `ready` or `recording`: the states that have a preview [cap 8.1].
- `framerate_update`: for each camera of `cameras`, `setOverlay(id, { rateText })`, and the
  frame rate store (5.7). The guard checks `message_type` and that `cameras` is an object.
- `log_record`, `pong`: as today.

### 5.6 The grid

The grid, the settings modal and the layout code stay: `CameraViewsGrid.tsx`,
`CameraGridCell.tsx`, `CameraGridSettingsModal.tsx`, the tiling, the drag swap and the resize.
`ResizableCameraView.tsx` stays (nothing imports it today).

One rule forces one change. Today, `connectedCameraIds` holds the cameras of the last group message.
A camera in `starting` or `failed` sends no frame, so it would get no tile, and the tile could not
show those states [A4]. Today's grid also uses `selectConnectedCameras` of the Redux slice, which
marks a camera connected only when its group is `alive` (4.5). In 4b, the grid shows
`gridCameraIds` (5.5) and does not filter on `selectConnectedCameras` [Q7].

`connectedCameraIds` has these other users. With "yes" to [Q7], each keeps the meaning "the cameras
that stream":

| User | Use |
|---|---|
| `CameraTreeItem.tsx` | `isStreaming`, the streaming mark of a camera |
| `CamerasViewSettingsOverlay.tsx` | the count "Connected Cameras" and `getAutoColumns`. The columns change to `gridCameraIds.length`, because they lay out the grid [agent 8]. |
| `ConnectionSettingsModal.tsx`, `ServerConnectionStatus.tsx` | the count of cameras in the status text |
| `RecordingInfoPanel.tsx`, `LeftSidePanelContent.tsx` | "no camera" checks |
| `WelcomeModal.tsx`, `BasePanelLayout.tsx` | the first camera closes the welcome modal; the "connect cameras" prompt |

`CameraView` keeps its `PAUSED` box: it is not an item of the tile overlay [player 8.3 "One
place"]. Its label and frame rate box in the DOM go (3.1).

### 5.7 The frame rate viewer [A7, P4] [Q3]

`FramerateStore` keeps one record for each camera id. The viewer shows these numbers for each
camera. "Not shown" and "Ring skipped" are two numbers. The viewer never adds them [A7].

| i18n key | English text | Source | Tooltip (English) |
|---|---|---|---|
| `deliveredFramerate` | Delivered | `delivered_framerate` of `framerate_update` [A3] | The rate at which the camera delivers frames to skellycam. |
| `notShownCount` | Not shown | `not_shown_count` | Frames that the server did not send, because the screen was slower than the camera. |
| `ringSkippedCount` | Ring skipped | `ring_skipped_count` [A8] | Frames that the camera ring skipped. |
| `oversizeCount` | Oversize | `oversize_count` [ring 5.8] | Frames that were larger than their ring slot. |
| `replacedCount` | Replaced | `status.replaced_count` of `app_state` [A2] | Frames that the gate replaced. |

- The statistics table has one row for each camera, labelled with the camera label. It keeps its
  columns for the delivered rate (recent, mean, median, standard deviation, maximum, minimum) and
  adds the four counts [agent 17].
- The timeline and the histogram show one series for each camera: the delivered rate. The colours
  come from `d3.schemeTableau10`, in the order of the cameras [Q3].
- The collapsed view lists `<label>: <delivered fps>` for each camera.
- "Not shown" counts for this connection since it started [4a 6.2]. Two windows thus show
  different "Not shown" values.
- The keys `server`, `display`, `capturesFramesFromCamera` and `rendersReceivedFrames` are not used
  any more. The locale files keep them.
- The new keys go into `en-english.json`. The other 40 locales fall back to English
  (`fallbackLng`) [Q8].

### 5.8 Docs

- `skellycam-docs/docs/technical/websocket-protocol.mdx`: replace the binary section, the client
  messages and `framerate_update` with the camera message [4a 3], the ready message and the safety
  net [4a 4.1], and the new shape [4a 6.2].
- `docs/core/real-time-streaming.mdx` (the packing and the backpressure text) and
  `docs/technical/architecture.mdx` (the WebSocket Server item, the flow diagram, steps 3 and 4, and
  the FrameProcessor item): the camera message, the flow control for each camera and the tile.
- The copies of these three pages in `skellycam-docs/i18n/` (`zh-CN`, `es`, `ar`, where a copy
  exists): the same tables and code blocks, with English prose for the changed parts [Q8].
- `docs/intro.mdx`: its table row "Binary frame format, JSON messages, backpressure" stays true.

## 6. The measurement: 8 cameras at 60 fps on the main-thread tile [T]

### 6.1 What it measures, and what the outside observer can prove

The preview of the product, end to end: the sender, the websocket, the parser, `PreviewTiles`, the
tiles on the main thread with ImageDecoder, in Electron 45.3.4. It runs on the Windows test machine
by hand, as the player benchmarks do [player 12.1]. It is T-PRV-51.

The user asks for an observer outside the page [T]. The one outside observer that the player bench
has, the capture of the composited window by the Electron main process (`beginFrameSubscription`),
gives about 30 captures each second. Thus:

- **It can prove**: each tile shows an image of its own camera; the image changes at the rate of the
  captures (about 30 times each second); the image is fresh, compared with the other tiles in the
  same capture. It sees each composited image, not each canvas draw.
- **It cannot prove**: more than about 30 new images each second for one tile. A camera at 60 fps
  needs about 60.
- **The ready messages that the server counts** are outside the page, but they count resolved tile
  updates, not images on the screen. A JPEG that does not decode also resolves `'drawn'`
  [player 8.3], and an update can resolve `'superseded'` (rule 4 of 5.3).
- **The draw count of the product** (`drawnCount` of 5.3) is a claim of the product about itself.
  It is not an outside proof.

[Q9] asks the user to accept this measurement, or to ask for an outside observer at 60 captures
each second or more.

### 6.2 Method [agent 9]

- **Server.** `ui_server.py` (7.2) with the product websocket route, compression off [A9], and 8
  fake rings. The writers run in a second process, as the script of ADR-HDC9 does, all 8 rings at
  the same frame number at the same time. Each ring gets 60 distinct JPEGs, 1920 x 1080, about
  190 kB, in turn: noise with a barcode of the camera index and the frame number modulo 60, made
  with `cv2.imencode`. 190 kB is near the mean 1080p JPEG of the C922 (192,382 B) [player 12.2].
  The JPEGs are checked to decode before the run. The server binds `127.0.0.1` on a port that the
  system chooses, never 53117.
- **Page.** The harness page `components/camera-views/tests/preview/` with the real
  `ServerContextProvider` and `CameraViewsGrid`. The window is 1400 x 1000, shown inactive with
  opacity 0, as the player harness does, so that `requestAnimationFrame` runs at the display rate
  [ADR-1ACK evidence of `dom/player`].
- **Observers outside the page.** The page reads no canvas back [T].
  - The Electron main process captures the composited window with `beginFrameSubscription` and
    reads the barcode of each tile with the reader of the player benchmark
    (`src/player/tests/harness/bench.ts`).
  - The server counts the `camera_ready` messages of each camera in each second, and the time from
    the start of each send of a camera message to the receipt of its ready message.
  - The Electron main process reads `TaskDuration` of the page through the debugger of its
    `webContents` (CDP `Performance.getMetrics`) [NV: that `TaskDuration` counts only the main
    thread of the renderer], `screen.getPrimaryDisplay().displayFrequency` (R), and
    `app.getAppMetrics()` (CPU and memory of each process).
- **The claim of the product.** At the end of each run, the bench reads `drawnCount` of
  `PreviewTiles` through the harness page. It is reported as the claim of the product (6.1).
- **Runs.** 3 runs of 2 s warm-up and 60 s measurement. Each target uses the median of the runs.

### 6.3 Targets [Q6] [agent 10]

| ID | Target | Proof | Basis |
|---|---|---|---|
| B-1a | After the first second, in each capture, each tile shows a barcode of its own camera, and its frame number is at most 4 frames lower than the highest frame number of the 8 tiles in that capture. Its frame number changes in at least 90 % of consecutive captures. | outside (captures) | At about 30 captures and 60 frames each second, about two frames pass between captures. The writers keep the 8 rings at one frame number. |
| B-1b | For each camera, the median count of ready messages each second is at least 0.9 x min(60, R), and `drawnCount` is at least 0.9 x min(60, R) x the run time. | ready messages: outside, but they count resolved updates; `drawnCount`: claim of the product (6.1) | The sender alone sent 475 of 480 messages each second at 8 x 1080p60, with 1.2 % not shown (mean) and 3.8 % (largest camera) [M ADR-HDC9]. A tile draws at most once for each refresh (rule 6 of 5.3). |
| B-2 | Send-to-ready time, all cameras: p95 at most 50 ms. | outside (server) | Decode 2.7 ms (1 camera) and 3.7 ms (4 cameras), draw 0.4 to 0.5 ms, overlay 0.1 ms or less, medians [M ADR-1ACK evidence, `dom/player`, Electron 45.3.4, about 190 kB at 1080p]; plus at most one refresh (16.7 ms) of wait for `requestAnimationFrame`. 50 ms is three refreshes at 60 Hz. |
| B-3 | Main thread of the page: `TaskDuration` at most 50 % of the run time. | outside (CDP) [NV] | 480 draws each second x (0.5 + 0.1) ms is about 29 % [same source]. ImageDecoder decodes off the main thread [NV]. The rest leaves room for React and the input. |

Recorded, with no target: the CPU of each Electron process and of the Python event-loop thread, the
working set, `not_shown_count` of each camera, the frames written. For comparison: the player used
1.44 cores for 8 cameras at 1080p30 with ImageDecoder [player 11.2, M `IP` F20], and drew 55 to 57
frames each second on each of 8 tiles during a scrub [M ADR-1ACK evidence].

### 6.4 The rule for a worker [T]

- A worker is added only if B-1b, B-2 or B-3 misses its target in the median of the three runs.
- Then the evidence entry records the result. The agent tells the user. A later spec, after the
  decision of the user, adds the worker.
- A miss of B-1a is a defect of the preview. It does not add a worker.
- CPU and memory never decide a worker. A worker moves work to another thread. It does not remove
  work.
- A miss does not stop the other parts of 4b.

## 7. Tests

### 7.1 Kinds

- **fake**, **ws**: Python tests as [4a 9.1], with fake rings and no camera. They run on Windows,
  Linux and macOS in the three jobs of `.github/workflows/capture.yml`, which already run
  `skellycam/tests/preview` [P7]. The session fixture of 3.2 configures `skellylogs`.
- **capture-fake**: a Python test with the real `CameraGroup` and the fake sources of
  `skellycam/tests/capture/` (`fake_source.py`, `capture_session.py`). It runs where the capture
  fake-source tests run.
- **tool**: a test in `tools/tests/`. It runs with `uv run pytest tools/tests`.
- **search**, **doc**: Python tests in `skellycam/tests/preview/` that read files. A search test is
  allowed here because the rule is a deletion [P5]. The doc test checks a deliverable.
- **unit**: TypeScript under `node --test --experimental-strip-types`, as the player unit tests
  [player 12.1]. Fake tiles, a fake `sendReady`, a manual `tick`. No browser. No server.
- **component**: Playwright 1.65.1 and Electron 45.3.4 with the player harness [player 12.1]: the
  harness main process opens the page `preview`. The page connects to `ui_server.py` (7.2).
- **benchmark**: section 6. Windows test machine, by hand. Not in CI.

### 7.2 Helpers [agent 11]

- **The shared fixture.** `tools/write_camera_message_fixture.py` writes
  `skellycam-ui/src/services/server/preview/tests/camera-messages.json` with `pack_camera_frame`.
  `--check` compares the tracked file with a new output. Each case has its input fields (64-bit
  values as decimal strings) and the message as hex. Cases: the example of [4a 3.2]; a `FLAGGED`
  read with flags 0x04; an `OVERSIZE` read; flags 0x30 with rotation 270; a 16-character camera id;
  `frame_number` 2^53 + 1 and `arrival_ns` 2^63 − 1. The JPEG bytes are synthetic, not a camera
  frame.
- **`ui_server.py`.** It calls `configure_logging` as `skellycam/__main__.py` does. It runs uvicorn
  with the product websocket router, compression off [A9], and a manager patched in as the `app`
  fixture of `skellycam/tests/conftest.py` does. It binds `127.0.0.1` on a port that the system
  chooses, and prints the port. Never 53117. It has two modes:
  - **fake rings** (the default): the fake manager of `skellycam/tests/preview/preview_helpers.py`
    with a `to_state_dict` that gives a scripted `app_state`; the writers in a second process;
    barcode JPEGs made with `cv2.imencode`.
  - **capture fakes**: a real `CameraGroupManager` and `CameraGroup` with the fake sources of
    `skellycam/tests/capture/`, as `capture_app` of `capture_session.py` makes them. Its
    `app_state` is the real `to_state_dict`.

  It reads one JSON command for each line of its standard input: add, remove or restart a camera;
  set the scripted state of a camera (fake rings only); write a flagged frame, an oversize frame or
  a ring skip; stop or start a writer; close the connections; print the counts of the ready
  messages for each connection and camera.
- **Harness page `preview`.** It mounts the real `ServerContextProvider` and `CameraViewsGrid` with
  the store of the app. It seeds the store with fake detected cameras. It sets the server host to
  `127.0.0.1` and the port of `ui_server.py` before it connects. It puts the `PreviewTiles` of the
  provider on `window` for the tests. Only the harness page does this.
- Component tests may read tile pixels to check them [player 8.3]. The benchmark may not.

### 7.3 Test list

| ID | Kind | Input and action | Pass criterion |
|---|---|---|---|
| T-PRV-25 | tool | Run `tools/write_camera_message_fixture.py --check`. Parse each case with the independent parser of [4a 9.1]. | The tracked file equals the new output, byte for byte. Each parsed field equals the input field of its case. |
| T-PRV-26 | ws | The product route `/skellycam/websocket/connect` with the fake manager: two rings at 30 fps for 3 s. The client answers each camera message with `camera_ready` at once, and sends `ping` after 1 s. | Each camera gets at least 80 % of its frames; each JPEG equals the ring payload; one `app_state` message arrives; each `framerate_update` has `cameras` with both ids and no `backend_framerate` key; `pong` arrives. |
| T-PRV-27 | ws | On the product route, send `{"frameNumber": 3, "displayImageSizes": null}`, `{not json`, `{"message_type": "camera_ready", "camera_id": 7}`, then `ping`. | `pong` arrives; the connection stays open; camera messages continue; the global kill flag stays `False`; no record at ERROR. |
| T-PRV-28 | ws | Four rings at 60 fps with payloads of 607,032 bytes; the client answers at once; close the client after 2 s. | Each task of `WebsocketServer` has ended within 1 s of the close; the global kill flag stays `False`; no record at ERROR. |
| T-PRV-29 | capture-fake, fake | (1) The real `CameraGroup` with three fake sources, `PreviewRelay` running; end the process of one camera (the fake source exits), so that the watch thread acts; restart the camera. A spy wraps `FrameRingReader.close` and records the thread of each call. (2) Only with the fallback of 4.3: four fake rings at 60 fps; a fake reader whose `read` copies in two halves with `time.sleep(0.001)` between them (the GIL is free) and records whether its `close` ran during a read; a thread removes and closes a reader under `_ring_lock`, then adds a new ring, 200 times; while a slow send waits, a thread takes `_ring_lock` with a timeout of 0.1 s. | (1) Each `close` of a ring reader runs on the event-loop thread; the other cameras continue. (2) No `close` during a read; no read through a closed reader; `run` continues; the thread gets the lock each time. |
| T-PRV-30 | search | Search the files of 7.5 for the names of 7.5. The decision log, `specs/` and `skellycam/tests/preview/` are not searched. Also check that the deleted files of 3.1 do not exist. | No hit; no deleted file exists. The rule is the deletion itself [P5]. |
| T-PRV-31 | doc | Read `specs/preview-interface-note.md`. | It exists. It has a heading for each item of section 8, and the camera message table equals table 3.2 of [4a]. |
| T-PRV-32 | unit | Parse each case of `camera-messages.json`. | Each field equals its case: `frameNumber` and `arrivalNs` as `BigInt`, also above 2^53; `jpeg` is `null` for the two flagged cases and equals the bytes for the others; the camera id has no NUL. |
| T-PRV-33 | unit | Change a fixture case: `version` 0 and 2; 47 bytes; a length one byte too long and one too short; `rotation_cw_deg` 45; an empty camera id. Give each to `PreviewTiles.receive` two times. | Each throws in `parseCameraMessage` with its reason (the version text names both values); `receive` writes one `console.error` for each reason, not two; no update; no ready message. |
| T-PRV-34 | unit | Camera A with a fake tile whose `update` waits on a promise of the test. Messages of frames 1, 2 and 3 arrive; then one `tick`; then resolve with `'drawn'`. | One update, with frame 3; frames 1 and 2 never reach the tile; no ready message before the resolve; one `camera_ready` for A after it; `drawnCount` of A is 1. |
| T-PRV-35 | unit | Cameras A and B. B's update never resolves. Frames 4 and 5 of A and of B arrive during A's update; three ticks; resolve A. Then one tick. | While A is busy: no second update for A. After the resolve: one ready message for A, and the next tick draws frame 5 of A. A draws while B stays busy; B gets no second update and no ready message. |
| T-PRV-36 | unit | A message with flags 0x04 and rotation 90 after an image, then a good message. | First update: `jpeg` `null`, mark `flagged`, the label frame of the flagged message, `rotationCwDeg` 90; one ready message after it; `drawnCount` does not change. Second update: the JPEG, mark `null`. |
| T-PRV-37 | unit | No pending message; `setOverlay` with state `too_slow` and rate text; one tick. Then a frame update in flight; `setOverlay` again; ticks; resolve. | First: one update with `jpeg` `null`, the state and the rate text; no ready message. Second: no update while the frame update is in flight; one overlay update after the resolve, with the new values. |
| T-PRV-38 | unit | 100 messages for A with no tick (a hidden page). Then `setPaused(true)` and 10 ticks. Then `setPaused(false)` and one tick. | No update and no ready message while there is no tick or while paused; then one update, with the newest message. |
| T-PRV-39 | unit | Messages for C with no tile; then `setTile(C)` and a tick; then `setTile(C, null)` and a new message. Then `clearPending()` with a pending message of A. | No ready message for C before its tile; then one update with the newest message of C and one ready message; after the removal, no update for C; after `clearPending`, no update for A at the next tick; the tile of A stays. |
| T-PRV-40 | unit | `server-messages.ts` with `app_state` objects: each of the eight states, `null`, `"unknown"`, no `status`; a group with `alive` `false` that has one camera `failed`, one `starting` and one `ready`; and `framerate_update` objects with `delivered_framerate` `null` and 29.97. | `cameraState` is each state, `null`, `null`, `null`; the group that is not alive gives all three ids in `gridCameraIds`, ordered by `camera_index`, and only the `ready` id in `connectedCameraIds`; `rateText` `null` and `"30.0 fps"`; the label is the camera name. |
| T-PRV-41 | unit | `FramerateStore` with two `framerate_update` messages for two cameras and one `app_state`. | Each camera has its own delivered rate, `notShown`, `ringSkipped`, `oversize` and `replaced`; no value is a sum of two counts; `clear()` empties each camera. |
| T-PRV-42 | unit | Search the product code of `skellycam-ui/src` (not `tests/` folders) for `getImageData`, `toDataURL`, `toBlob` and `readPixels`. | No hit [T, player 8.3]. |
| T-PRV-43 | component | `ui_server.py` (fake rings) with 3 barcode cameras at 30 fps for 5 s; the harness page. | Each tile shows the barcode of its own camera; the barcode frame changes; the server counts at least 80 % of the frames as ready messages for each camera; the overlay text has the label, a rate text of 30.0 ± 0.5 fps and the state `ready`. |
| T-PRV-44 | component | `ui_server.py` (capture fakes): camera A is a fake source that holds in `starting`; camera B fails to open (`failed`); camera C is `ready`. Then release A. Then C's fake source stops its frames for more than 2 s (`dead`). | While A is `starting`: three tiles, although the group is not `alive`; A is black with `starting`, B is black with `failed`, C shows images with `ready`; each tile has its label [Q1]. After the release: A shows images with `ready`. After the stall: C keeps its last image with `dead`. Each state shows within 1.5 s of its change in `app_state`. |
| T-PRV-45 | cut | Revision 2: T-PRV-36 tests the flagged message. | none |
| T-PRV-46 | cut | Revision 2: T-PLAY-41 tests the rotation of the tile; T-PRV-36 tests that the rotation reaches the tile. | none |
| T-PRV-47 | component | Close the connections in `ui_server.py` while frames flow; the UI reconnects. Then stop `ui_server.py` until the UI gives up. | While `RECONNECTING`, each tile keeps its last image; after the reconnect, frames flow again within 3 s; after `FAILED`, the grid shows its empty state and no console error comes from `preview/`. |
| T-PRV-48 | component | Three cameras (fake rings). Add camera D; remove camera B; restart camera A with a new ring from frame 0. | D gets a tile that draws within 2 s; B's tile leaves the grid; A's tile shows the frames of the new ring (the label frame starts again at a low number); the other cameras continue. |
| T-PRV-49 | component | Two windows with the page, each with its own connection. Hide window 2 with the default `backgroundThrottling` (the product setting) for 5 s, then show it. | While hidden, `document.visibilityState` is `hidden` in window 2, and the server counts 0.5 to 1.6 messages each second for each camera of window 2; window 1 keeps at least 80 % of the frames; after the show, window 2 draws within 1 s. |
| T-PRV-50 | component | Camera A: 3 oversize frames, 1 ring skip, `replaced_count` 7 in `app_state`. Open the frame rate viewer, full and collapsed. | The table shows "Delivered", "Not shown", "Ring skipped", "Oversize" and "Replaced" for each camera, with 3, 1 and 7 for A, and "Not shown" equal to the last `not_shown_count` of the server for this connection; no "Server" or "Display" text; the collapsed view lists each camera. |
| T-PRV-51 | benchmark | Section 6: 8 cameras at 1080p60, 3 runs of 60 s. | B-1a to B-3 of 6.3, each with its kind of proof; the results go to an evidence entry; 6.4 applies. |

Section 7.6 gives the counts.

### 7.4 Parity of the systems [P7]

| ID | Windows | Linux | macOS |
|---|---|---|---|
| T-PRV-25 to T-PRV-31 | runs | runs | runs |
| T-PRV-32 to T-PRV-42 | runs | runs | runs |
| T-PRV-43, T-PRV-44, T-PRV-47, T-PRV-48, T-PRV-50 | runs | runs, under `xvfb-run` | runs |
| T-PRV-49 | runs | not run: no one has verified that a hidden window under `xvfb-run` is `hidden` and stops `requestAnimationFrame` [NV] | not run: the same for the macOS runner [NV] |
| T-PRV-51 | runs (test machine, by hand) | owed | owed |

T-PRV-38 keeps the rule of the hidden page on each system. When someone verifies the behaviour on
Linux or macOS, T-PRV-49 can run there. The component tests need Python on each system, for
`ui_server.py`.

### 7.5 What T-PRV-30 searches

Files: `skellycam/**/*.py`, `skellycam-ui/src/**`, `skellycam-docs/docs/**` and
`skellycam-docs/i18n/**`. Names:

- In Python files and docs: `frameNumber` (the old JSON key), `frameAcknowledgment`,
  `backend_framerate`, `frontend_framerate`.
- In Python files only: `frontend_payload_bytearray`, `FRONTEND_FRAME_HEADER_DTYPE`,
  `FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE`, `get_latest_ring_payload`, `get_latest_frontend_payloads`,
  `get_backend_framerate_updates`, `_frontend_image_relay`, `check_frame_acknowledgment_status`,
  `last_received_frontend_confirmation`, `BACKPRESSURE_WARNING_THRESHOLD`, `FramerateUpdateMessage`,
  `parse_relay`.
- In UI files: `frameAcknowledgment`, `backend_framerate`, `frontend_framerate`. Not
  `frameNumber`: the parser field `CameraMessage.frameNumber` (5.2) is in the UI.
- In UI files and docs: `parseMultiFramePayload`, `PAYLOAD_FOOTER`, `FRAME_HEADER_SIZE`,
  `FrameProcessor`, `CanvasManager`, `transferControlToOffscreen`, `bitmaprenderer`,
  `frame-decode.worker`, `offscreen-renderer.worker`.

### 7.6 Counts and CI [agent 12]

- Python: T-PRV-25 (tool), T-PRV-26 to T-PRV-28 (ws), T-PRV-29 (capture-fake and fake), T-PRV-30
  (search), T-PRV-31 (doc): 7.
- UI: T-PRV-32 to T-PRV-42 (unit): 11. T-PRV-43, T-PRV-44, T-PRV-47 to T-PRV-50 (component): 6.
- Benchmark: T-PRV-51: 1. Total: 25. T-PRV-45 and T-PRV-46 are cut.
- The npm script `test:player:unit` adds the glob `src/services/server/preview/tests/unit/**/*.test.ts`.
  `playwright.player.config.ts` adds `components/camera-views/tests/**/*.spec.ts` to `testMatch`.
  `vite.player-harness.config.ts` and the harness main process add the page `preview`.
- CI, in its own PR [AGENTS.md section 6]: `player.yml` adds the trigger paths
  `skellycam-ui/src/services/server/**`, `skellycam-ui/src/components/camera-views/**`,
  `skellycam/tests/preview/ui_server.py` and `specs/preview-4b.md`, and a pinned uv set-up step in
  its three jobs, as `capture.yml` has; it runs T-PRV-49 only in its Windows job. `capture.yml`
  adds `specs/preview-4b.md`, `tools/write_camera_message_fixture.py` and its test to its paths,
  and that test to the selection of its three jobs, so that T-PRV-25 runs on the three systems.

## 8. The interface note for the FreeMoCap session [P5]

At the end of 4b, write `specs/preview-interface-note.md` [agent 15]. T-PRV-31 checks it. It has
these headings, each with the facts of 4b:

1. **Camera message**: table 3.2 of [4a], the version rule [4a 3.3], the `BigInt` rule, the
   flagged message with `jpeg_len` 0.
2. **Ready message and safety net**: `camera_ready` [4a 4.1], newest pending, one ready message
   for each draw, the 1 s safety net of the server [A6].
3. **Deleted**: the group message, the `frameNumber` acknowledgement, `backend_framerate` and
   `frontend_framerate`.
4. **framerate_update**: the shape for each camera [4a 6.2] and the meaning of each count (5.7).
5. **Camera status**: where `state` and `replaced_count` are in `app_state`, and that `alive` is not
   a filter for the tiles (4.5).
6. **Tile**: the module `skellycam-ui/src/player/` and its import `@/player/index.ts`; a copy of the
   folder is the way for the FreeMoCap UI [player 4.3]; the `TileUpdate` values of 5.4.
7. **Compression**: websocket compression is off [A9]. A client must not need it.

## 9. Conflicts found

1. **The tile label needs a frame number.** `TileLabel.frame` is a `number`, and `formatFrame`
   always draws it. Thus the tile cannot show the camera label before the first frame, or on a
   camera that failed before any frame [A4, P4]. [Q1] proposes `frame: null`.
2. **An overlay update supersedes a decode.** A `tile.update` with `jpeg: null` during a decode
   makes the decode resolve `'superseded'` and drops its image (`tile.ts`, "newest wins"). Rule 2 of
   5.3 (one update in flight) avoids it. No change of the tile is needed.
3. **Phase 3a closes rings on another thread.** [4a 5.1] assumes that only the event-loop thread
   closes readers. The watch thread of `dom/native-jpeg` closes them. 4.3 and [Q4] answer it.
4. **Today's grid lists only cameras that sent a frame, of groups that are alive.** A camera in
   `starting` or `failed` would have no tile, and on `dom/native-jpeg` such a camera makes its group
   not alive (4.5). 5.5 and 5.6 take the list from `cameras` of `app_state` [Q7].
5. **The tile branch is local and unaccepted code.** `dom/player` is not pushed, and its code
   choices (ADR-1ACK of that branch) wait for the user. 4b needs it merged [Q2].
6. **The status `state` can be `null`.** On `dom/native-jpeg`, `CameraStatus.state` is `None` before
   the first state. The tile then shows no state (5.4).
7. **The outside observer is too slow to see each frame at 60 fps.** `beginFrameSubscription` gives
   about 30 captures each second. 6.1 states what each observer proves [Q9].
8. **The harness windows do not throttle.** The player harness opens windows with
   `backgroundThrottling: false`. T-PRV-49 needs a window with the product setting.
9. **The display rate has no source after 4a.** The old `frontend_framerate` and the "Display" row
   go. A7 replaces them with "Not shown".
10. **Two cameras of one model have one `camera_name`.** [4a 6.1] makes `camera_name` the label.
    Today's UI shows `#index · camera id`. [Q5].
11. **The websocket tests fail today.** `logger.success` needs `configure_logging` (3.2).

## 10. Decisions that bind 4b

P1, P2, P4, P5, P6, P7, A1 to A10 and the tile thread decision of
[ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md); the accepted 4a
spec [`preview.md`](preview.md) with its sections 10 and 11; the decisions [T] of section 0;
`specs/player.md` section 8 on `dom/player`; the camera states and status of
`specs/windows-capture.md` section 8 on `dom/native-jpeg`.

## 11. Choices of the agent

Each item fills a gap. The body marks each one [agent n]. Items 2 and 18 of revision 1 are now
questions Q4 and Q8; revision 2 changes items 8, 10 and 11
([ADR-R1TD](../decisions/entries/R1TD-revision-2-of-the-step-4b-preview-spec.md)).

1. `_preview_relay` wraps `PreviewRelay.run` with the `except` clauses of the other tasks.
2. (Revision 2: removed. No rename of `_ring_lock`; see Q4.)
3. The file layout of 5.1: `preview/camera-message.ts`, `preview/preview-tiles.ts`,
   `preview/server-messages.ts`, the tests under `preview/tests/` and
   `components/camera-views/tests/`.
4. The parser throws with a reason; `PreviewTiles` logs one `console.error` for each reason and
   connection, and sends no ready message for a refused message. A message with an empty camera id
   or a rotation outside the four values is refused.
5. The interface of `PreviewTiles` and rules 1 to 10 of 5.3: one update in flight for each camera,
   the `requestAnimationFrame` loop as the clock of the draws, the overlay update with no ready
   message, no generation counter for the connection, `drawnCount`.
6. The label: `frameDigits` 6, `timeNs` `null`, `nominalFps` 0.
7. The rate text: `mean_frames_per_second` with one decimal and " fps"; `null` hides it.
8. (Revision 2.) The automatic columns of `CamerasViewSettingsOverlay` use the length of
   `gridCameraIds`. The rest of old item 8 is Q7.
9. The method of the measurement (6.2): the real server with fake rings, the harness page, barcode
   JPEGs of about 190 kB, the observers outside the page, 3 runs of 60 s.
10. (Revision 2.) The targets B-1a, B-1b, B-2 and B-3 (6.3), each with its kind of proof.
11. (Revision 2.) The helpers of 7.2: a tool that writes the shared fixture; `ui_server.py` with
    `configure_logging`, two modes and commands on its standard input; the harness page `preview`.
12. The UI tests join the scripts and the configs of the player runners; the CI change of 7.6, in
    its own PR.
13. The `FRAMERATE` subscription of `CameraGroupManager` stays. No process publishes on that topic
    today, but it is not part of the preview.
14. `measured_fps` is not shown. No decision asks for it.
15. The interface note is the file `specs/preview-interface-note.md`.
16. The UI component tests use the real Python server, not a server in TypeScript. A websocket
    server in Node needs a new npm package.
17. Statistics table: one row for each camera, with the four counts as more columns.
18. (Revision 2: now Q8.)
19. (Revision 2.) A session fixture in `skellycam/tests/conftest.py` calls `configure_logging`.

## 12. Questions for the user

Each question is worded so that "yes" accepts the recommendation.

- **Q1.** Allow `TileLabel.frame` to be `null` in the shared tile (no frame part). Then a tile shows
  its label and state before the first frame and on a camera that failed with no frame (section 9,
  item 1). The change is in `tile.ts`, `format.ts`, section 8.3 of `specs/player.md`, T-PLAY-37 and
  T-PLAY-44, on `dom/player`, before its merge. Yes? Recommendation: yes. With "no", a failed camera
  shows "failed" with no name.
- **Q2.** Merge `dom/native-jpeg` into `dom/preview` now, and merge `dom/player` only before the
  first UI test commit; the UI imports the tile from `@/player/index.ts`. The merge of `dom/player`
  comes before you accept its code choices (ADR-1ACK of that branch); that is your decision. The 4b
  PR then also carries phase 3a and the 6a player, unless they land first. Yes? Recommendation: yes.
  Else the UI part of 4b waits for 6a, which lands with recorder step 5a [player 1.1].
- **Q3.** In the timeline and the histogram of the frame rate viewer, replace the series "Server"
  and "Display" with one series of the delivered rate for each camera, coloured from
  `d3.schemeTableau10`. Yes? Recommendation: yes. The alternative deletes the two charts.
- **Q4.** After the merge of `dom/native-jpeg`, the watch thread closes ring readers while the sender
  reads them on the event loop; the review reproduced a read of a released buffer (4.3). The fix is
  planned on the capture branch: the watch thread hands each close to the event loop, so [4a 5.1]
  stays as written, and T-PRV-29 part 1 fails while a close runs on another thread. If that fix is
  not possible, the sender holds `_ring_lock` for each camera's reads (the fallback of 4.3). Yes?
  Recommendation: yes.
- **Q5.** The tile label is `<camera_name> · <camera id>`, not `camera_name` alone [4a 6.1], so that
  two cameras of one model have different labels. Yes? Recommendation: yes.
- **Q6.** Accept the targets B-1a to B-3 (6.3) and the rule of 6.4: a worker only after B-1b, B-2 or
  B-3 misses in the median of three runs, by a later spec. Yes? Recommendation: yes. No number is
  measured for the preview tile yet.
- **Q7.** The grid shows one tile for each camera in `cameras` of `app_state`, with no filter on
  `alive`; `connectedCameraIds` becomes the cameras in a state with a preview (`checking`,
  `too_slow`, `ready`, `recording`). Thus the camera counts, the streaming mark of the camera tree
  and the welcome modal count only streaming cameras, and a `failed` camera has a tile but is not
  "streaming" (5.5, 5.6). Yes? Recommendation: yes. The alternative, one list for both, marks a
  failed camera as streaming.
- **Q8.** The five new viewer labels are in English only; the other 40 locales fall back to English.
  The changed parts of the translated copies of `websocket-protocol.mdx`, `architecture.mdx` and
  `real-time-streaming.mdx` get the new tables and English prose, until the translation process
  translates them. Yes? Recommendation: yes. The alternative is to translate in 4b, which the
  project marks as unreviewed AI text (`TRANSLATING.md`).
- **Q9.** The outside observer of the player bench sees about 30 images each second, so it can
  prove image correctness and freshness at that resolution (B-1a), not 54 draws each second. Accept
  B-1b as stated in 6.1: the ready messages counted by the server (resolved updates) and the draw
  count of the product (a claim of the product). Yes? Recommendation: yes. With "no", 4b needs an
  outside observer at 60 captures each second or more, for example a screen capture by the
  operating system outside Electron; nobody has tested one here [NV].
