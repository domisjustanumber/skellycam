# Phase 4 preview specification, step 4b: the UI side, the connection of the sender, the deletion

Status: accepted in principle by the user on 2026-11-20, with his answers to the nine questions of
revision 2 (section 12.1,
[ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).
The user gave the go-ahead for the failing tests of step 4b. The product code of step 4b waits for a
later go-ahead. An agent wrote revisions 1 and 2 on 2026-11-20
([ADR-EE0E](../decisions/entries/EE0E-step-4b-preview-spec-and-agent-choices.md),
[ADR-R1TD](../decisions/entries/R1TD-revision-2-of-the-step-4b-preview-spec.md)). Revision 3 of
2026-11-20 puts the answers into the body and gives the full test list (section 7).
[ADR-W674](../decisions/entries/W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md)
holds the agent choices of revision 3. The user answered the four new questions Q10 to Q13 of
revision 3 on 2026-11-20, and decided the pull request target (section 12.1). One question, Q14,
is open (section 12.3). The accepted step 4a spec [`preview.md`](preview.md) does not change. This
file adds step 4b. Revision 4 of 2026-11-25 puts the answers Q824 to Q836 of the user on the 4b tests into
5.1, 5.4, 5.8, 6.2, 7.4, 7.7 and 7.8 [ADR-NA1N](../decisions/entries/NA1N-answers-of-the-user-to-the-questions-of-the-step-4b-tests.md).

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
  branch to `development-streaming` only after 4b (now upstream `development` [PR]); an interface
  note at the end of 4b; no read-back of a tile canvas; websocket compression off.
- **[Q864]** to **[Q873]**, **[Q885]**, **[Q893]** to **[Q897]**: the answers of the user of 2026-11-26 on the 4b
  code [ADR-BPP8](../decisions/entries/BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md).
- **[Q824]** to **[Q836]**: the answers of the user of 2026-11-25 on the 4b tests (global numbers)
  [ADR-NA1N](../decisions/entries/NA1N-answers-of-the-user-to-the-questions-of-the-step-4b-tests.md).
- **[Q1]** to **[Q9]**: the answer of the user of 2026-11-20 to question n of revision 2
  (section 12.1). **[Q10]** to **[Q13]**: the answer of the user of 2026-11-20 to question n of
  revision 3 (section 12.1). **[Q14]**: an open question (section 12.3).
- **[PR]**: the decision of the user of 2026-11-20 on the pull request target (section 12.1).
- **[S]**: a note of the supervisor (section 12.2). It is not a decision of the user.
- **[4a x.y]**: section x.y of [`preview.md`](preview.md), accepted
  ([ADR-WB08](../decisions/entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md)).
- **[player x.y]**: section x.y of `specs/player.md` on branch `dom/player`, accepted there
  (`ADR-YV3V` of that branch), read on 2026-11-20. The code facts are from
  `skellycam-ui/src/player/tile/tile.ts` of that branch.
- **[cap x.y]**: section x.y of `specs/windows-capture.md` on branch `dom/native-jpeg`, which has
  `replaced_count` in 8.4. The copy on this branch does not have it yet.
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md).
- **[demo]**: a commit of branch `dom/demo`, read on 2026-11-20. The commits wait for review (5.7).
- **[M source]**: measured; the source holds the result. **[NV]**: not verified.
- **[agent n]**: an agent filled a gap. Section 11 lists each one.

This spec uses British spelling. Code names are from `dom/preview`, `dom/player`, `dom/native-jpeg`
and `dom/demo`, read on 2026-11-20. It cites files, not line numbers, except where a review finding
cites a line.

## 1. Purpose, scope, non-goals

### 1.1 Purpose

Step 4b makes the UI read the camera message of [4a 3]. It connects `PreviewRelay` to the live
websocket endpoint, deletes the old group message and its code, and draws each camera in the shared
tile [P1, P5, P6]. After 4b, the wire carries one format, and the UI reads it [A1].

### 1.2 Scope

- Server: the connection of `PreviewRelay` to `/websocket/connect`, the lifecycle for each
  connection, the guard test of the ring-reader close (section 4).
- UI: the parser of the camera message, the flow control for each camera, the shared tile for each
  camera, the overlay values, the camera list label on the tile, the grid, the frame rate viewer with
  the two series "Captured" and "Displayed" (section 5).
- The deletion of the old group message, its code, its tests and its docs (section 3).
- The measurement of 8 cameras on the main-thread tile: at 30 fps with the full outside proof, and
  at 60 fps with the inside counts (section 6) [T, Q9].
- The tests (section 7) and the interface note for the FreeMoCap session (section 8) [P5].

### 1.3 Non-goals

- A resize, a quality setting, a rate cap, a rate setting, a remote-UI mode [E, P2].
- A worker for the tile. Section 6.4 gives the only way to add one [T, Q6].
- A change of the flow rules of the sender [4a 4]. A lock in the sender: fix F8 of the capture
  branch keeps each reader close on the event loop (4.3) [Q4].
- A change of the player, the take reader or the tile, except `TileLabel.frame` `null` [Q1]. The
  label and the tile order in the player [Q5] belong to `specs/player.md` and the recorder spec
  [Q11].
- A display of `measured_fps` of the camera status [agent 14].
- The performance page [ring A5].
- A change of the Redux camera slice (`connectionStatus`, `failure`). The demo commits change it
  (5.7).
- A warning of the recorder in the UI. "Captured" does not show a recorder problem as a lower line
  [Q3]. The recorder work adds the warning [Q12].
- The exposure modes, the frame rate control and the USB label of the camera list.
  `specs/camera-requests.md` (another branch) specifies them (5.6).
- The row text of a `too_slow` camera and the rule of "Update Cameras" for it [Q10]. 4b changes
  only the "N Streaming" count (5.7).
- A translation of new text into the 40 other UI locales and into the docs copies [Q8].

## 2. The base branch [Q2, S]

The user answered Q2 "yes": merge `dom/native-jpeg` into `dom/preview` now, and `dom/player` before
the first UI test commit; the 4b PR then also carries phase 3a and the 6a player, unless they land
first [Q2].

A later decision of the same day changes the base. The supervisor relays it [S]:

- The work moves onto a new integration branch, `dom/integration`. It holds the native capture, the
  new recorder, the new player and the merge of upstream `sfn26`. Each Rust part is removed. The
  camera "backend" selector of the UI is removed. The record stop becomes `POST`. The server has no
  public pause route: `PUT /group/all/pause` is removed, and the pause is a freeze of the UI display
  only ([ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md), [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md) K1).
- Pull requests go against upstream `development`. This is a decision of the user of 2026-11-20
  [PR]. It replaces `development-streaming` in the wording of A1 of ADR-G651. ADR-G651 does not
  change.

Thus the tests and the code of 4b are written on top of `dom/integration` when it exists. Before
that, no 4b test commit. The merges of Q2 then happen as part of `dom/integration`, not into
`dom/preview`. `dom/integration` must hold:

1. the capture code of `dom/native-jpeg`, with the camera states, `replaced_count` [cap 8.4] and
   fix F8 (4.3);
2. the player of `dom/player`, with the shared tile `skellycam-ui/src/player/` [player 4.1], the UI
   test runners [player 12.1], `.github/workflows/player.yml`, and the tile change of [Q1];
3. the 4a commits of `dom/preview`: `PreviewRelay`, the 4a tests, compression off [A9]. The list of
   the supervisor does not name them [S] (section 12.2).

The sections that the new base changes:

| Section | Change |
|---|---|
| 2 | The base is `dom/integration`, not `dom/preview` with two merges. |
| 3.1, 3.2, 7.7 | The paths and names are from `dom/preview`. The merge of upstream `sfn26` can move or change them. The test writer checks each one on `dom/integration` before T-PRV-30 is written. The camera "backend" selector is not an item of 4b. |
| 4.3, 4.5 | The code facts are from `dom/native-jpeg`. The test writer checks them on `dom/integration`. |
| 5.3 rule 7, 5.4 | The server has no public pause route ([ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md), [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md) K1). The UI pause of rule 7 is the only pause of the display. |
| 5.5, 5.6, 5.7 | The demo commits move onto `dom/integration` (5.7). |
| 7.8 | The CI triggers name `dom/integration`. The PR goes against upstream `development` [PR]. |
| 10 | A1 names `development-streaming`; [PR] replaces it. Section 6 of `AGENTS.md` names upstream `development` (section 12.2). |

Import path of the tile:

- React code: `import { Tile } from '@/player/index.ts'` and
  `import type { CameraStateName, TileUpdate } from '@/player/index.ts'`, as
  `CanvasTakePlayer.tsx` of `dom/player` does.
- A file that the Node unit tests load: a relative `import type` of `../../../player/index.ts`.
  Node type stripping does not know the `@/` alias [player 4.2].
- No product file outside `src/player/` imports another file of the module. T-PLAY-35 checks it
  [player 4.2]. 4b does not copy the tile [P6]. A test file may import `src/player/tests/` (7.6).

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
| `CameraView.tsx`: the label and frame rate box in the DOM (`#index · id`, `D:`, `S:`) | The overlay of the tile, with the camera list label [player 8.4, Y3, Q5] |
| `framerate-store.ts` and the frame rate viewer: the two series "Server" (`backend`) and "Display" (`frontend`) | The two series "Captured" and "Displayed" for each camera, and the counts (5.8) [Q3] |
| The docs of the group message (5.9) | The camera message, the ready message and the new `framerate_update` |

After the merge of 4b, `CameraGroup.read_latest_ring_frames` and `WebsocketServer._send_json` have
no caller in the product. A later lane deletes both [Q871]. The `FRAMERATE` subscription
of `CameraGroupManager` stays [agent 13].

### 3.2 Tests

| Deleted test | Its rule | What keeps the rule |
|---|---|---|
| `skellycam/tests/test_image_payload.py` | The layout of the group message | T-PRV-01 [4a 9.2]; T-PRV-25 and T-PRV-32 (one fixture, Python and TypeScript) |
| T-RING-33 in `skellycam/tests/frame_ring/test_camera_process.py` | The relay sends the ring JPEG untouched | T-PRV-02 [4a 9.2]; T-PRV-26 (the product endpoint) |
| T-CAP-86 in `skellycam/tests/capture/test_states.py`, with `_collect`, and `parse_relay` in `capture_session.py` | Each camera on its own while one camera reopens | T-PRV-09, T-PRV-14, T-PRV-15 [4a 9.2]; T-PRV-48 (the UI) |
| `test_websocket_frame_acknowledgment` in `skellycam/tests/test_websocket.py` | A client text keeps the connection open, and `ping` works after it | T-PRV-21 [4a 9.2]; T-PRV-27 (the product endpoint) |
| The mocks `get_latest_frontend_payloads` and `get_backend_framerate_updates` in `skellycam/tests/conftest.py` | none (mocks) | The mock manager gets `closing = False` instead |
| The two T-TIM-19 tests of the interim relay in `skellycam/tests/capture_timings/test_main_process.py` | the steps of the interim relay (`capture-timings.md` 6.5) | none: the relay is gone. The send-lock test of T-TIM-19 runs through `WebsocketServer.__init__` and its `PreviewRelay` [ADR-BPP8](../decisions/entries/BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md) |

Two tests that used a deleted name keep their rule [Q872]: `test_group_watch.py` reads the ring
reader on the event loop with no lock, as `PreviewRelay` does [Q871], and `test_websocket_internals.py` imports `ServerFramerateCalculator` from
`framerate_tracker`. The counting relay of `ui_server.py` passes each keyword of the constructor of
`PreviewRelay` on, and `test_pace_marker.py` lists the two halves of T-PRV-26 [Q872].

The other three tests of `test_websocket.py` (connect, `ping`, `app_state`) fail on `dom/preview`
today. `websocket_server_connect` calls `logger.success`, which exists only after
`skellylogs.configure_logging`, and no test configures it: each test stops with
`AttributeError: 'Logger' object has no attribute 'success'` (run on 2026-11-20). On
`dom/integration`, the fixture `logging_runtime` of `skellycam/tests/conftest.py`, which the `app` fixture
uses, gives `logger.success` and the other logging prerequisites. Thus 4b adds no session fixture, and
these three tests and T-PRV-26 to T-PRV-28 pass [Q872] (it replaces agent 19). `test_websocket_internals.py` and `test_websocket_compression.py` stay.

## 4. Server

### 4.1 The connection of `PreviewRelay` to the endpoint

In `WebsocketServer`:

1. `__init__` makes `self._preview = PreviewRelay(self._cgm, self._send_bytes_in_lock,
   self._send_msgspec_json, step_set=self._preview_timings.steps, send_lock=self._send_lock)`. The
   two sends hold the send lock [4a agent 27]: `_send_msgspec_json` takes it, and the relay takes
   `send_lock` around `_send_bytes_in_lock`, so that the `preview_send` bracket starts after the
   lock (`capture-timings.md` 6.5, Q839). The lock and the bracket are in the relay; the server passes its
   lock in [Q865] ([ADR-BPP8](../decisions/entries/BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md)). ADR-24FZ item 2
   allows `_send_msgspec_json` as `send_json`.
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

### 4.3 The ring-reader close on the event loop [Q4]

**The fault.** Before fix F8, the watch thread of `CameraGroup` (`_watch_workers`) on
`dom/native-jpeg` called `_close_rings` for the camera of an ended process. The sender reads on the
event-loop thread with no lock [4a 5.1]. A read could thus run while another thread closed its
reader: a read of a released buffer. The independent review of revision 1 reproduced it.

**The fix, on the capture branch.** Fix F8 (`ADR-BM73` item 8 of `dom/native-jpeg`) is in. The
watch thread no longer closes a ring reader. It hands the close to the event loop with
`call_soon_threadsafe`. The callback closes the rings only if the camera still has the ring of the
ended process. Thus [4a 5.1] stays true as written, and the sender has no lock [Q4].

**The guard.** T-PRV-29 fails if a ring reader closes on a thread that is not the event-loop
thread. It can pass before the code of 4b. It keeps F8 true when other code changes.

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
| Replaced count | `status.replaced_count` | "Replaced" in the frame rate viewer (5.8) [A2] |
| Measured rate of the rate check | `status.measured_fps` | not shown [agent 14] |
| Failure stage and reason | `status.failure` | the row of the camera list [demo] (5.7); not on the tile |
| Camera list number and name | `index` and `name` of the camera in the camera list of the store; else `configs[<camera id>].camera_index` and `camera_name` | `label.camera` of the tile: `Camera <number> · <name>` (5.4) [Q5] |

`app_state` comes at most one time each second, when it changes [4a 6.1]. A state change thus
shows on the tile within about 1 s.

The group flag `alive` is not a filter for the tiles [Q7]. On `dom/native-jpeg`, `CameraGroup.alive`
is `False` when a worker process has ended, or when a status is not `connected`, is `closed`, is
`closing` or has `error`; and `connected` is set only after the camera opens (`camera_loop.py`,
line 304). One camera in `starting`, `failed` or `dead` thus makes the whole group not alive. Since
[ADR-NYT6](../decisions/entries/NYT6-choices-of-fix-lane-2.md), `alive` has the meaning of
[`camera-requests.md`](camera-requests.md) 1.5: at least one selected camera lives.

## 5. UI

### 5.1 Files [agent 3]

| Path | Content |
|---|---|
| `skellycam-ui/src/services/server/preview/camera-message.ts` | `parseCameraMessage` (5.2). No import except types. |
| `skellycam-ui/src/services/server/preview/preview-tiles.ts` | `PreviewTiles`: the newest pending message, the flow control, the tile updates (5.3, 5.4). It imports only `import type` of the tile. |
| `skellycam-ui/src/services/server/preview/server-messages.ts` | Pure functions from an `app_state` or a `framerate_update` object, and the camera list, to the values of 5.5. The provider calls them. Node can load the file, so T-PRV-40 tests it. |
| `skellycam-ui/src/store/slices/cameras/camera-labels.ts` | From the demo commits [demo]. It has `cameraLabel` and `labelText` (5.4) [agent 20, Q825]. No import. |
| `skellycam-ui/src/services/server/preview/tests/unit/` | The Node unit tests (7.4). |
| `skellycam-ui/src/services/server/preview/tests/camera-messages.json` | The shared fixture. `tools/write_camera_message_fixture.py` writes it (7.2). |
| `skellycam-ui/src/components/camera-views/tests/browser/` | The component tests (7.4). |
| `skellycam-ui/src/components/camera-views/tests/harness/preview/` | The harness page `index.html` with `page.tsx` (7.2). |
| `skellycam-ui/src/components/camera-views/tests/bench/` | The benchmarks (section 6). |
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
  and drops the message. A reason is the text of the error: one line for each distinct text [Q872]. It sends no ready message for it, because its camera id is not trusted.
- `jpeg` is a view, not a copy. The tile decodes from it [player 8.1].
- A message with a bit of 0x0F has `jpeg` `null` [4a 3.3]. Its mark is `flagged` (5.4).

### 5.3 Flow control: `PreviewTiles` [P2, A6] [agent 5]

```ts
type TileLike = Pick<Tile, 'update'>;
export class PreviewTiles {
  constructor(sendReady: (cameraId: string) => void,
              onDrawn?: (cameraId: string, atMs: number) => void,   // default: does nothing
              now?: () => number);                                  // default: performance.now
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

`onDrawn` and `now` feed the series "Displayed" (5.8) [agent 22].

State for each camera: `pending` (the newest camera message not yet given to the tile), `busy`
(one tile update in flight), the overlay values, `overlayChanged`, the last label and mark, and the
frame number of the last drawn frame (`null` before the first frame).

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
   `'drawn'` and the update had a JPEG, `drawnCount` of the camera goes up by one, and `PreviewTiles`
   calls `onDrawn(cameraId, now())`. These count resolved updates, so they also count a JPEG that
   did not decode (6.1).
5. **An overlay change with no new frame.** At `tick`, for a camera with a tile, `busy` false, no
   `pending` message and `overlayChanged`: set `busy`, call `tile.update` with `jpeg: null` and the
   current overlay. Its `label.frame` is the frame number of the last drawn frame, or `null` before
   the first frame [Q1]. When it resolves, clear `busy`. No ready message. No `onDrawn`. A frame
   update also carries the current overlay and clears `overlayChanged`.
6. **The display drives the draws.** The provider calls `tick` in a `requestAnimationFrame` loop,
   as today's loop does. Thus a tile draws at most one camera message for each display refresh. The
   camera that `tick` gives its update first turns by one at each refresh, so that no camera is always last
   [Q893]. A
   hidden page runs no `requestAnimationFrame` in the product window (default
   `backgroundThrottling`) [NV on Linux and macOS, 7.5]. It then draws nothing, sends no ready
   message, and the server sends only the safety-net messages: one each second for each camera
   [A6, 4a 4.1]. The UI has no timer of its own: the 1 s safety net is the server's.
7. **Paused.** `setPaused(true)` (today's `setStreamPaused`, the playback tab) makes `tick` do
   nothing. Messages stay newest-pending. This is the only pause of the display: the server has no
   public pause route, and the pause works also during a recording ([ADR-V8RS](../decisions/entries/V8RS-pause-freezes-the-ui-display-only.md), [ADR-6QFG](../decisions/entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md) K1).
8. **No tile yet.** A message for a camera with no tile stays in `pending` and gets no ready
   message. When `setTile` gives the tile, the next `tick` draws it.
9. **Tile removed.** `setTile(id, null)` drops the `pending` message and the state of that camera.
   The caller closes the tile.
10. **Connection closed.** The provider calls `clearPending()` on each close. It drops each
    `pending` message. The tiles and their images stay. An update in flight can send its ready
    message on the next connection; the server ignores a ready message for a camera that is ready
    [4a 4.1]. The provider calls it at each state that is not `CONNECTED`.
11. **A failed update.** An update whose promise rejects clears `busy` and writes one `console.error`.
    It sends no ready message; the safety net of the server sends the next message [Q872].

The state of a camera starts at its first message or overlay. Before its first label, the label of an
update has `camera: ''`. The last frame number and the mark of an overlay update are those of the last
message given to the tile [Q872].

### 5.4 The tile for each camera

`CameraView` makes `new Tile(canvas, {}, {timing})` with the default options [player 8.3] and the timing handle of
`capture-timings.md` 7 (`timing` is `getTileTimings().handle(cameraId, null)` of `useServer()`), and calls
`previewTiles.setTile(cameraId, tile)` through `setTile(cameraId, tile)` of `useServer()`, which also gives a
new tile the overlay values that the provider keeps: rule 9 of 5.3 drops them at a removal [Q872]. On unmount it calls `setTile(cameraId, null)` and
`tile.close()`. The tile draws on the main thread with ImageDecoder [T, player 8.1].

The update of rule 3 of 5.3:

| `TileUpdate` field | Value |
|---|---|
| `jpeg` | `message.jpeg` (`null` for a flagged message) |
| `rotationCwDeg` | `message.rotationCwDeg`, from the header [E, 4a 3.3] |
| `label` | `{ frame: Number(message.frameNumber), frameDigits: 6, camera: <camera list label>, timeNs: null, nominalFps: 0 }` [agent 6, Q5]; in an overlay update before the first frame, `frame: null` [Q1] |
| `rateText` | `<mean_frames_per_second to 1 decimal> fps` from `delivered_framerate` [4a 6.2]: the "Captured" rate (5.8); `null` when it is `null` [agent 7, A3] |
| `cameraState` | `status.state` of `app_state`, when it is one of the eight states; else `null` [A4] |
| `mark` | `{ kind: 'flagged' }` when `flags & 0x0F`; else `null` [P4] |
| `receivedAtMs` | `now()` of `PreviewTiles` at the `receive` of the message; absent in an overlay update (`capture-timings.md` 7) |

- `Number(frameNumber)` is exact up to 2^53. A frame number of a camera does not reach it.
- **The camera list label** [Q5] [agent 20]. It is `Camera <number> · <name>`, for example
  `Camera 6 · c922 Pro Stream Webcam`, as the row of the camera list shows the camera
  (`CameraTreeItem.tsx`: `Camera {camera.index}`, then `{camera.name}`). `<number>` and `<name>`
  are `index` and `name` of the camera in the camera list of the store (`cameras` of the cameras
  slice). When the camera id is not in that list, they are `camera_index` and `camera_name` of
  `configs[<camera id>]` in `app_state`. The label never holds the hex camera id. One function,
  `cameraLabel({ id, index, name })` in `camera-labels.ts`, makes it [Q825]. The separator is
  `" · "` (U+00B7 with one space on each side). This replaces the label `camera_name` of [4a 6.1]
  for the UI; the 4a spec does not change.
- **One label form everywhere** [Q13]. `labelText(text, cameras)` of `camera-labels.ts`
  (`camera-requests.md` 1.8) also uses `cameraLabel` [Q825]. Thus a server reason text says `Camera 1 · USB Camera`, not
  `Camera 1 (USB Camera)`.
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
| `failed` before any frame | Black, with `failed` and the label with no frame part [Q1]. |
| `dead`, or `failed` after frames | The last image stays, with `dead` or `failed`. The rate text goes away when `delivered_framerate` becomes `null`. |
| A ring recreated (a mode change, "apply again", "Update Cameras" [demo]) | The frames of the new ring show. Their frame numbers start again at 0 [4a 4.4]. |
| The camera leaves `app_state` | The tile leaves the grid and closes. |
| The connection drops; `WebSocketConnection` tries again (`RECONNECTING`) | Each tile keeps its last image and overlay. |
| The connection is `DISCONNECTED` or `FAILED` | The provider clears its camera lists, as it clears today's list, and also the frame rate store and its kept overlay values [Q872]. The grid shows its empty state. |
| A hidden page or the playback tab | No draw. The tile keeps its last image. |

The product never reads a tile canvas back (`getImageData`, `toDataURL`, `toBlob`, `readPixels`)
[T, player 8.3]. T-PRV-42 checks it. No test reads a tile canvas back either (7.3).

### 5.5 Text messages in the provider

`server-messages.ts` holds the logic. The provider only calls it and stores the results.

- `app_state`: as today, `serverStateReceived` goes to the store. Also, for each group and each
  camera id in its `cameras`, with no filter on `alive` (4.5) [Q7]:
  `setOverlay(id, { label, cameraState: status.state })`, with the label of 5.4, and two lists:
  - `gridCameraIds`: each camera id in the `cameras` of each group, in the order of the camera
    list: ascending camera list number (5.4), then the camera id [Q5] [agent 21]. The grid shows
    one tile for each [Q7].
  - `connectedCameraIds`: the ids of `gridCameraIds` whose state is `checking`, `too_slow`,
    `ready` or `recording`: the states that have a preview [cap 8.1] [Q7]. A `too_slow` camera
    keeps its tile and counts as streaming [Q10].
- `framerate_update`: for each camera of `cameras`, `setOverlay(id, { rateText })`, and the
  frame rate store (5.8). The guard checks `message_type` and that `cameras` is an object.
- `log_record`, `pong`: as today.

`useServer()` also gives `cameraLabels`, the label of each camera of the grid. A new camera list of the
store computes the overlays and the two lists again from the last `app_state` [Q872].

The functions of `server-messages.ts` [Q824]: `appStateValues(message, cameraList)` gives
`{overlays, gridCameraIds, connectedCameraIds}`, with `overlays[id]` = `{label, cameraState}`;
`rateTexts(message)` gives the rate text of each camera; `isFramerateUpdate(data)` is the guard.

### 5.6 The grid and the camera list

The grid, the settings modal and the layout code stay: `CameraViewsGrid.tsx`,
`CameraGridCell.tsx`, `CameraGridSettingsModal.tsx`, the tiling, the drag swap and the resize.
`ResizableCameraView.tsx` stays (nothing imports it today).

One rule forces one change. Today, `connectedCameraIds` holds the cameras of the last group message.
A camera in `starting` or `failed` sends no frame, so it would get no tile, and the tile could not
show those states [A4]. Today's grid also uses `selectConnectedCameras` of the Redux slice, which
marks a camera connected only when its group is `alive` (4.5). In 4b, the grid shows
`gridCameraIds` (5.5), in the order of the camera list, and does not filter on
`selectConnectedCameras` [Q7, Q5]. A drag swap of the grid stays a change of the layout only. The
cells of the camera grid have no transition: a tile does not grow or slide into place (the 0.2 s animation of
`react-grid-layout` is off for this grid) [Q895].
`useServer()` gives `getPreviewTiles()` and `gridCameraIds`, and each tile canvas has the attribute
`data-camera-id` [Q824].

`connectedCameraIds` has these other users. Each keeps the meaning "the cameras that stream" [Q7]:

| User | Use |
|---|---|
| `CameraTreeItem.tsx` | `isStreaming`, the streaming mark of a camera |
| `CameraConfigSidebarPanel.tsx`, `CameraConfigModal.tsx` | the count "N Streaming" of the camera list. It changes from `selectConnectedCameras` to `connectedCameraIds` [Q10]. |
| `CamerasViewSettingsOverlay.tsx` | the count "Connected Cameras" and `getAutoColumns`. The columns change to `gridCameraIds.length`, because they lay out the grid [agent 8]. |
| `ConnectionSettingsModal.tsx`, `ServerConnectionStatus.tsx` | the count of cameras in the status text |
| `RecordingInfoPanel.tsx`, `LeftSidePanelContent.tsx` | "no camera" checks |
| `WelcomeModal.tsx`, `BasePanelLayout.tsx` | the first camera closes the welcome modal; the "connect cameras" prompt |

`CameraView` keeps its `PAUSED` box: it is not an item of the tile overlay [player 8.3 "One
place"]. Its label and frame rate box in the DOM go (3.1).

The camera list (`camera-config-tree-view/`) also gets the changes of `specs/camera-requests.md`
(another branch): the exposure modes Manual and Auto, one frame rate control at the top of the
list, and a USB 2 or USB 3 label next to each camera; the label of a virtual camera reads
"virtual". That spec specifies them. 4b changes nothing in the rows of the camera list, except
through `connectedCameraIds`.

### 5.7 Overlap with the demo commits [Q7, S]

The user noted on 2026-11-20 that commits of `dom/demo` change the same area. They wait for review,
and they move onto `dom/integration` [S]. 4b keeps each of their changes.

| Demo commit (subject) | Change | 4b sections that it touches |
|---|---|---|
| "Keep the tiles of the other cameras when one camera fails; show the failure in its row" | The cameras slice judges each camera by its own server state. A `failed`, `dead` or `too_slow` camera gets `connectionStatus` `'error'` and `failure` (`stage: reason`). Its row shows the reason. The "N Streaming" count of the camera list leaves it out. | 1.3, 4.5, 5.5, 5.6, T-PRV-40, T-PRV-44; [Q10] |
| "Show the camera list label in place of the camera id in server reasons" | `camera-labels.ts` with `withCameraLabels`: `Camera 1 (USB Camera)` in the server reasons | 5.1, 5.4; [Q13] changes the form to `Camera 1 · USB Camera` |
| "Start virtual cameras (NDI) unticked in the camera list"; "Grey out virtual cameras and keep them unselectable" | A virtual camera is never selected, so it is never in a group | 5.5: it gets no tile. No 4b change. |
| "Add a Retry button to the row of a failed camera"; "Update Cameras: open, close or retry only the changed cameras" | One "Update Cameras" button sends only the differences: retry the failed cameras, close the unticked cameras, add the ticked cameras | 5.4 (a ring recreated), T-PRV-48. No 4b change. |

The user settled the differences on 2026-11-20:

- **A `too_slow` camera** [Q10], in the accepted words: "A too-slow camera keeps its tile and counts
  as streaming. Its row says "Too slow at this exposure: lower the exposure", not "Failed". Update
  Cameras does not reopen it; the remedy is a changed setting." Thus:
  - 4b: the "N Streaming" count uses `connectedCameraIds` (5.6), so it counts `checking`,
    `too_slow`, `ready` and `recording` [Q7].
  - Not 4b: the row text and the rule of "Update Cameras" change the demo commits, which re-add a
    `too_slow` camera and show `Failed: <stage>: <reason>`. That change goes with the demo commits
    onto `dom/integration` [S]. The row of a `too_slow` camera shows the sentence above, not the
    failure text.
- **The label form** [Q13]: one form, `Camera <n> · <name>`, also in the server reasons (5.4).

One difference stays:

- **The key set.** The demo reads `group.configs`. 4b reads `group.cameras` [Q7]. The two hold the
  same ids while a group runs [NV].

### 5.8 The frame rate viewer [A7, P4] [Q3]

The viewer has two series for each camera, named for what they mean [Q3]:

- **Captured**: the frames that the camera delivered to the server. The source is
  `delivered_framerate` of `framerate_update` [4a 6.2]. The sender computes it from
  `source_frame_number` and `arrival_ns` of the ring slots [4a 6.3], so it is measured where the
  frames enter the ring, and it does not depend on the client [A3]. During a take, the recorder
  reads the same ring first [ring], so this is what goes to disk. A problem of the recorder shows
  as a warning, not as a lower line [Q3]. 4b has no recorder warning; the recorder work adds it
  [Q12].
- **Displayed**: the frames that this window drew. The source is `onDrawn` of `PreviewTiles`
  (rule 4 of 5.3) [agent 22]. It is a count of the product about itself (6.1). A hidden window and
  a paused window draw nothing, so the series gets no new value.

`FramerateStore` keeps one record for each camera id:

- the Captured values: each `delivered_framerate` that arrives, in the windowed statistics of today
  (`TimestampedRingBuffer`; one function `statsOf` in place of the class `WindowedStats` [Q872]);
- the Displayed values: `recordDrawn(cameraId, atMs)` adds the time from the previous drawn frame of
  that camera to the same kind of windowed statistics. A time longer than 1 s is not added: it is a
  pause or a hidden page. It only sets the start of the next time [agent 22]. The Displayed rate (the
  current value) is the rate over the frames drawn in the last 1 s of `now` [Q826]. A camera that has
  drawn before and draws nothing for 1 s shows 0 [Q864];
- the four counts.

The API of the store [Q824]: the constructor takes the clock `now` (default `performance.now`) [Q864];
`recordFramerateUpdate(message)`, `recordAppState(message)`,
`recordDrawn(cameraId, atMs)`, `cameraIds()`, `clear()` and `getCamera(id)`. `getCamera` gives `null`, or
`{captured, displayed, notShown, ringSkipped, oversize, replaced}`, where `captured` and `displayed` are
`{current, aggregate}`, each a `DetailedFramerate` or `null`. The viewer keeps the classes
`.framerate-viewer` and `.framerate-collapsed-summary`. Each series element is
`svg [data-camera-id][data-series]`, with its colour as the fill of a `rect`, else as the stroke. The labels
are in the SVG texts or in an HTML legend. Each count header starts with its English text of the table
below. The collapsed text of a camera is `<label>: Captured <x> fps, Displayed <y> fps`.

| i18n key | English text | Source | Tooltip (English) |
|---|---|---|---|
| `capturedFramerate` | Captured | `delivered_framerate` of `framerate_update` [A3, Q3] | Frames each second that the camera delivered to SkellyCam, measured where the frames enter the frame ring. During a recording, these are the frames that go to disk. |
| `displayedFramerate` | Displayed | `onDrawn` of `PreviewTiles` [Q3] | Frames each second that this window drew for the camera. |
| `notShownCount` | Not shown | `not_shown_count` | Frames that the server did not send, because the screen was slower than the camera. |
| `ringSkippedCount` | Ring skipped | `ring_skipped_count` [A8] | Frames that the camera ring skipped. |
| `oversizeCount` | Oversize | `oversize_count` [ring 5.8] | Frames that were larger than their ring slot. |
| `replacedCount` | Replaced | `status.replaced_count` of `app_state` [A2] | Frames that the gate replaced. |

- "Not shown" and "Ring skipped" are two numbers. The viewer never adds them [A7].
- The timeline and the histogram show the two series for each camera. Each camera has one colour
  from `d3.schemeTableau10`, in the order of the camera list [Q3]. The Captured line is solid; the
  Displayed line is dashed. The histogram has one panel for each series [agent 23].
- The statistics table has two rows for each camera, labelled `<camera list label>` with
  "Captured" and "Displayed". Each row has the columns of today (recent, mean, median, standard
  deviation, maximum, minimum). The Captured row also has the four counts [agent 24].
- The collapsed view lists `<camera list label>: Captured <x> fps, Displayed <y> fps` for each
  camera [agent 24].
- "Not shown" counts for this connection since it started [4a 6.2]. Two windows thus show
  different "Not shown" values. Displayed is also for this window.
- The tile shows only the Captured rate [A3].
- The keys `server`, `display`, `capturesFramesFromCamera` and `rendersReceivedFrames` are not used
  any more. The locale files keep them. The key `deliveredFramerate` of revision 2 is not added
  [agent 25].
- The new keys go into `en-english.json`. The other 40 locales fall back to English
  (`fallbackLng`) [Q8]. The tooltips have the keys `<key>Tooltip`, and the source column the key
  `framerateSourceTooltip` [Q872].
- `viewer-cameras.ts` gives the cameras of the grid with their label and colour. A camera with no camera
  list label shows its hex camera id in the viewer. One HTML legend names each camera with both series.
  The two histogram panels are one component with a `series` property. Each row of the table has the four
  count columns; only the Captured row fills them [Q872].
- The store and the viewer keep `performance.now()` times, so that the timeline has one clock. The table
  and the collapsed view read the store on their 500 ms timers, so Displayed drops to 0 on the screen with
  no new frame [Q864].

### 5.9 Docs

- `skellycam-docs/docs/technical/websocket-protocol.mdx`: replace the binary section, the client
  messages and `framerate_update` with the camera message [4a 3], the ready message and the safety
  net [4a 4.1], and the new shape [4a 6.2].
- `docs/core/real-time-streaming.mdx` (the packing and the backpressure text) and
  `docs/technical/architecture.mdx` (the WebSocket Server item, the flow diagram, steps 3 and 4, and
  the FrameProcessor item): the camera message, the flow control for each camera and the tile.
- The copies of these three pages in `skellycam-docs/i18n/` (`zh-CN`, `es`, `ar`, where a copy
  exists): the same tables and code blocks, with English prose for the changed parts [Q8]. Each copy keeps
  its translated headings and the prose of the parts that do not change [Q872].
- `docs/intro.mdx`: its table row "Binary frame format, JSON messages, backpressure" stays true.

## 6. The measurement: 8 cameras on the main-thread tile, at 30 and 60 fps [T, Q9]

### 6.1 What it measures, and what each observer proves

The preview of the product, end to end: the sender, the websocket, the parser, `PreviewTiles`, the
tiles on the main thread with ImageDecoder, in Electron 45.3.4. It runs on the Windows test machine
by hand, as the player benchmarks do [player 12.1].

The observers:

- **The outside observer**: the capture of the composited window by the Electron main process
  (`beginFrameSubscription`), as in the player bench. It gives about 30 captures each second. It
  sees each composited image, not each canvas draw. It can prove that each tile shows an image of
  its own camera, and that the image is fresh, compared with the other tiles in the same capture.
- **The ready messages that the server counts**, and the send-to-ready time. They are outside the
  page, but they count resolved tile updates, not images on the screen. A JPEG that does not
  decode also resolves `'drawn'` [player 8.3], and an update can resolve `'superseded'` (rule 4 of
  5.3).
- **The draw count of the product** (`drawnCount` of 5.3). It is a claim of the product about
  itself. It is not an outside proof.

The user decided the split [Q9]:

- **30 fps: the full outside proof.** The outside observer checks each capture. At 30 fps, it sees
  about each frame. 30 fps is the frame rate of the cameras of the user, and his floor: "we will
  not be doing anything lower than 30fps". T-PRV-51.
- **60 fps: the inside counts only.** The ready messages that the server counts and the draw count
  of the product. The UI offers 60 fps only when each ticked camera passed a real 60 fps check
  (`specs/camera-requests.md`). T-PRV-52.

The capture times of the observer and the frame times of the cameras are not in step. Thus at
30 fps, a frame can fall between two captures, and two captures can show one frame. "Each picture
checked" means each capture, not each camera frame. The B-1a criterion of 6.3 allows for it.

### 6.2 Method [agent 9]

- **Server.** `ui_server.py` (7.2) with the product websocket route, compression off [A9], and 8
  fake rings. The writers run in a second process, as the script of ADR-HDC9 does, all 8 rings at
  the same frame number at the same time. Each ring gets 60 distinct JPEGs, 1920 x 1080, about
  190 kB, in turn: noise with the barcode of 7.2 (camera number 1 to 8, frame number modulo 60),
  made with `cv2.imencode`. 190 kB is near the mean 1080p JPEG of the C922 (192,382 B) [player 12.2].
  The barcode JPEGs come out at about 172 kB, inside the 10 % of the player bench. Each run gets a new
  server and a new app. The send-to-ready time starts again at a safety-net resend [Q834].
  The JPEGs are checked to decode before the run. The server binds `127.0.0.1` on a port that the
  system chooses, never 53117.
- **Page.** The harness page `preview` (7.2) with the real `ServerContextProvider` and
  `CameraViewsGrid`. The window is 1400 x 1000, shown inactive with opacity 0, as the player
  harness does, so that `requestAnimationFrame` runs at the display rate [ADR-1ACK evidence of
  `dom/player`].
- **No test tool attached.** The bench runs the harness app with no Playwright attached: the devtools link of
  Playwright copies each websocket frame of the page and overflows at 256 MB with 8 cameras at 1080p (first run,
  2026-11-26). The harness main process runs the run (`src/player/tests/harness/preview-bench-run.ts`): it starts
  the page, takes the observer rows, the CDP metrics of its own debugger and the process metrics, reads
  `drawnCount` at the end, and writes them to a file. It prints a line at the start and the end of the
  measurement, so that the bench reads the counts of `ui_server.py` at the same times [Q869].
- **Observers outside the page.** The page reads no canvas back [T].
  - The Electron main process captures the composited window with `beginFrameSubscription` and
    reads the barcode of each tile with the observer of 7.2.
  - The server counts the `camera_ready` messages of each camera in each second, and the time from
    the start of each send of a camera message to the receipt of its ready message.
  - The Electron main process reads `TaskDuration` of the page through the debugger of its
    `webContents` (CDP `Performance.getMetrics`) [NV: that `TaskDuration` counts only the main
    thread of the renderer], `screen.getPrimaryDisplay().displayFrequency` (R), and
    `app.getAppMetrics()` (CPU and memory of each process).
- **The claim of the product.** At the end of each run, the bench reads `drawnCount` of
  `PreviewTiles` through the harness page. It is reported as the claim of the product (6.1).
- **Runs.** For each frame rate F (30 and 60): 3 runs of 2 s warm-up and 60 s measurement. Each
  target uses the median of the runs. The result file keeps, for B-1a, each second of each camera below its
  ratio, with the frames that the observer read in that second [Q894].

### 6.3 Targets [Q6, Q9] [agent 10, agent 26]

F is the frame rate of the run. C is the number of captures each second that the observer got in
the run. R is the display refresh rate.

| ID | Runs | Target | Proof | Basis |
|---|---|---|---|---|
| B-1a | F = 30 | After the first second, in each capture, each tile shows a readable barcode of its own camera, and its frame number is at most 2 frames lower than the highest frame number of the 8 tiles in that capture. For each tile, the count of distinct frame numbers each second is at least 0.9 x min(30, C). | outside (captures) [Q9] | At about 30 captures and 30 frames each second, about one frame passes between captures. The writers keep the 8 rings at one frame number. 2 frames is 67 ms. |
| B-1b | F = 30 and F = 60 | For each camera, the median count of ready messages each second is at least 0.9 x min(F, R), and `drawnCount` is at least 0.9 x min(F, R) x the run time. | ready messages: outside, but they count resolved updates; `drawnCount`: claim of the product (6.1) | The sender alone sent 475 of 480 messages each second at 8 x 1080p60, with 1.2 % not shown (mean) and 3.8 % (largest camera) [M ADR-HDC9]. A tile draws at most once for each refresh (rule 6 of 5.3). |
| B-2 | F = 30 and F = 60 | Send-to-ready time, all cameras: p95 at most 50 ms. | outside (server) | Decode 2.7 ms (1 camera) and 3.7 ms (4 cameras), draw 0.4 to 0.5 ms, overlay 0.1 ms or less, medians [M ADR-1ACK evidence, `dom/player`, Electron 45.3.4, about 190 kB at 1080p]; plus at most one refresh (16.7 ms) of wait for `requestAnimationFrame`. 50 ms is three refreshes at 60 Hz. |
| B-3 | F = 30 and F = 60 | Main thread of the page: `TaskDuration` at most 50 % of the run time. | outside (CDP) [NV] | At 60 fps, 480 draws each second x (0.5 + 0.1) ms is about 29 % [same source]. ImageDecoder decodes off the main thread [NV]. The rest leaves room for React and the input. |

At F = 60, the outside observer also runs. Its values are recorded, with no target [Q9].

Recorded, with no target: the CPU of each Electron process and of the Python event-loop thread, the
working set, `not_shown_count` of each camera, the frames written. For comparison: the player used
1.44 cores for 8 cameras at 1080p30 with ImageDecoder [player 11.2, M `IP` F20], and drew 55 to 57
frames each second on each of 8 tiles during a scrub [M ADR-1ACK evidence].

### 6.4 The rule for a worker [T, Q6]

- A worker is added only if B-1b, B-2 or B-3 misses its target in the median of the three runs, at
  F = 30 or at F = 60.
- Then the evidence entry records the result. The agent tells the user. A later spec, after the
  decision of the user, adds the worker.
- A miss of B-1a is a defect of the preview. It does not add a worker.
- CPU and memory never decide a worker. A worker moves work to another thread. It does not remove
  work.
- A miss does not stop the other parts of 4b.

## 7. Tests

### 7.1 Kinds

- **fake**, **ws**: Python tests as [4a 9.1], with fake rings and no camera.
- **capture-fake**: a Python test with the real `CameraGroup` and the fake sources of
  `skellycam/tests/capture/` (`fake_source.py`, `capture_session.py`).
- **tool**: a test in `tools/tests/`.
- **search**, **doc**: Python tests in `skellycam/tests/preview/` that read files. A search test is
  allowed here because the rule is a deletion [P5]. The doc test checks a deliverable.
- **unit**: TypeScript under `node --test --experimental-strip-types`, as the player unit tests
  [player 12.1]. Fake tiles, a fake `sendReady`, a manual `tick`. No browser. No server.
- **component**: Playwright 1.65.1 and Electron 45.3.4 with the player harness [player 12.1]: the
  harness main process opens the page `preview`. The page connects to `ui_server.py` (7.2).
- **benchmark**: section 6. Windows test machine, by hand. Not in CI.

### 7.2 Helpers [agent 11, agent 27, agent 28]

- **The logging prerequisites.** The fixture `logging_runtime` of `skellycam/tests/conftest.py` gives them
  (3.2). 4b adds no session fixture [Q872].
- **The shared fixture.** `tools/write_camera_message_fixture.py` writes
  `skellycam-ui/src/services/server/preview/tests/camera-messages.json` with `pack_camera_frame`.
  `--check` compares the tracked file with a new output, and writes nothing. Each case has its input
  fields (64-bit values as decimal strings) and the message as hex. Cases: the example of [4a 3.2];
  a `FLAGGED` read with flags 0x04; an `OVERSIZE` read; flags 0x30 with rotation 270; a
  16-character camera id; `frame_number` 2^53 + 1 and `arrival_ns` 2^63 − 1. The JPEG bytes are
  synthetic, not a camera frame.
- **Barcode JPEGs.** `skellycam/tests/preview/barcode_jpegs.py` makes the JPEGs of the fake rings
  with `cv2.imencode`: noise, and the barcode of `skellycam-ui/src/player/tests/fixtures/jpeg.ts`
  (`barcodeBits`, `BARCODE_Y`, `CELL`: the camera number in 4 bits, then the frame number modulo
  60 in 12 bits). The camera numbers are 1 to 8, never 0, so a black tile does not read as a
  frame. Size: 640 x 360 for the component tests, 1920 x 1080 for the benchmarks.
- **`ui_server.py`.** It calls `configure_logging` as `skellycam/__main__.py` does. It runs uvicorn
  with the product websocket router, compression off [A9], and a manager patched in as the `app`
  fixture of `skellycam/tests/conftest.py` does. It binds `127.0.0.1` on a port that the system
  chooses, and prints the port. Never 53117. It has two modes:
  - **fake rings** (the default): the fake manager of `skellycam/tests/preview/preview_helpers.py`
    with a `to_state_dict` that gives a scripted `app_state` (with `camera_index` and
    `camera_name` in each config); the writers in a second process; the barcode JPEGs.
  - **capture fakes**: a real `CameraGroupManager` and `CameraGroup` with the fake sources of
    `skellycam/tests/capture/`, as `capture_app` of `capture_session.py` makes them. Its
    `app_state` is the real `to_state_dict`.

  It reads one JSON command for each line of its standard input: add, remove or restart a camera;
  set the scripted state or `replaced_count` of a camera (fake rings only); write a flagged frame,
  an oversize frame or a ring skip; stop or start a writer; set the frame rate of the writers;
  close the connections; print the counts of the ready messages and the send-to-ready times for
  each connection and camera; print the last `not_shown_count` of each connection and camera.
- **Harness page `preview`.** It mounts the real `ServerContextProvider` and `CameraViewsGrid` with
  the store of the app. It seeds the store with fake detected cameras: `id`, `index` and `name` for
  each camera, with list numbers that differ from the order of the ids. It sets the server host to
  `127.0.0.1` and the port of `ui_server.py` before it connects. It puts the `PreviewTiles` of the
  provider on `window.__previewTiles` for the tests. Only the harness page does this. The harness
  main process of the player (`src/player/tests/harness/main.ts`) adds the page `preview`, and an
  option to open a window with the default `backgroundThrottling` (T-PRV-49).
  The harness window fits the work area of the screen, at most 1400 x 1000, and the grid and the viewer of the
  page `preview` fit the window. The grid height is the inner height of the window on each machine, also where
  the window is 1400 x 1000 (before, 980 px ran past an inner height of about 935 px). A CI runner has a smaller screen: Windows cuts a larger window to the screen,
  and the part of a window past the edge of an xvfb screen is not drawn, so a tile there gives the observer no
  image of its own camera. `PLAYER_HARNESS_MAX_WINDOW=<width>x<height>` gives such a screen on a larger one
  ([ADR-FP47](../decisions/entries/FP47-choices-of-the-triage-of-the-first-ci-run-of-the-4b-component-tests.md),
  proposed).
- **The outside observer.** `observe` and `observed` of the player bench
  (`src/player/tests/bench/player.bench.ts`) move to `src/player/tests/harness/observer.ts`, with
  no change of their method: the Electron main process takes each composited image of the window
  (`beginFrameSubscription`) and reads the barcode row of each tile at the place that the page
  gives. The page gives the place of each tile from `getBoundingClientRect()` of its canvas and the
  image fit (`canvasPoint` of `src/player/tests/fixtures/barcode.ts`). This is layout, not a pixel
  read. A reading of a tile is its camera number and its frame number, or "none" when the barcode
  row has no light cell (a black tile). A window whose image does not change gives no capture, so a test
  that must see a still window (T-PRV-47, while `RECONNECTING`) forces one capture: `captureOnce` reads an
  image of `webContents.capturePage()` in the same way [Q867].
- **The clean-up after each test.** `PreviewKit.close` closes each app, then stops each `ui_server.py`, each step
  with a time limit (10 s for an app, 20 s for a server), inside the 60 s of the test. At a time-out it kills that
  process tree (on Windows `taskkill /T`; elsewhere the process group, [NV] off Windows), logs `hung step: <step>`
  and adds it to the test report as an annotation; the kill does not fail the test [Q896]. `ui_server.py` sets the graceful-shutdown limit of uvicorn to 5 s,
  so that its stop ends on its own also when a reset client connection never reports its loss; the time limit and
  the kill stay as the backstop [Q906].
- **The kept overlay text.** A test reads the overlay of a tile from `Tile.overlay`, which the tile
  keeps "so that a test can read it" [player 8.4], through `window.__previewTiles.tiles`. This is
  product state, not a pixel read.

### 7.3 Rules for each test

Each test of 4b obeys these rules. The test list adds the rules of each test.

- No camera. No test has the marker `camera_hardware` or `capture_local`.
- No app start: no product Electron app, no `npm run dev`, no `skellycam` server process. The
  servers are the `app` fixture, the test route of [4a 9.1], or `ui_server.py`. The windows are the
  windows of the harness.
- No port 53117. Each server binds `127.0.0.1` on a port that the system chooses.
- **No pixel read-back of a tile canvas**: no `getImageData`, `toDataURL`, `toBlob` or
  `readPixels` of a tile canvas, no `drawImage` of a tile canvas into another canvas, and no screen
  shot of a canvas element from the page. A test checks an image only with the outside observer
  of 7.2. Reason: in the player benchmark, `getImageData` reads of the tile canvases slowed play
  from 57 to 20 display refreshes each second and gave 0 % correct tiles, also after the reads
  stopped [player 8.3]. This replaces the line "Component tests may read tile pixels" of
  revision 2 [agent 27].
- Synthetic JPEGs only. No test writes a camera frame or a recording into the repository. The
  barcode JPEGs stay in memory or in a temporary folder.
- No new npm or Python package.

### 7.4 Test list

Each test has these items: **File** (the file to create; the test writer also creates the helpers
of 7.2), **Set-up** (the fakes, and the server parts that are real), **Steps**, **Pass**, **Runs**
(the marker or the selection, and the CI job on Windows, Linux and macOS) and **Must not** (in
addition to 7.3).

The CI jobs: `capture-windows`, `capture-linux` and `capture-macos` of `capture.yml` run
`uv run pytest skellycam/tests/capture skellycam/tests/preview -m "not camera_hardware and not capture_local"`.
`player-windows`, `player-linux` and `player-macos` of `player.yml` run `npm run test:player:unit`
and `npm run test:player:browser` (Linux under `xvfb-run`). `doc-checks.yml` runs
`uv run pytest tools/tests` on Linux. Section 7.8 gives the CI changes.

#### Python tests

**T-PRV-25** (tool). The shared fixture.

- File: `tools/tests/test_camera_message_fixture.py`; the tool `tools/write_camera_message_fixture.py`.
- Set-up: the real `pack_camera_frame`; the independent parser of
  `skellycam/tests/preview/preview_helpers.py` [4a 9.1].
- Steps: run the tool with `--check` in a subprocess. Load the JSON. Parse the hex of each case with
  the independent parser.
- Pass: exit code 0; the tracked file equals the new output, byte for byte; it has each case of 7.2;
  each parsed field equals the input field of its case.
- Runs: no marker. `capture-windows`, `capture-linux`, `capture-macos` with the selection of 7.8. Not
  in `doc-checks.yml`: it syncs no project package [Q836].
- Must not: write the tracked file in `--check` mode.

**T-PRV-26** (ws). The product endpoint sends camera messages.

- File: `skellycam/tests/preview/test_endpoint.py`.
- Set-up: real: the product route `/skellycam/websocket/connect`, `WebsocketServer`, `PreviewRelay`,
  the ring package. Fake: the manager of `preview_helpers.py`, patched in as the `app` fixture does,
  with two fake rings and paced writers at 30 fps. Starlette `TestClient`.
- Steps: connect. Answer each camera message with `camera_ready` at once. Send `ping` after 1 s.
  Run 3 s.
- Pass: each camera gets at least 80 % of its frames (a `pace` test; the blocking test checks for more
  camera messages than the safety net gives, on the same run, as 9.1 of [4a] says) [Q827]; each JPEG
  equals the ring payload; one
  `app_state` message arrives; each `framerate_update` has `cameras` with both ids and no
  `backend_framerate` key; `pong` arrives.
- Runs: no marker. `capture-windows`, `capture-linux`, `capture-macos`.
- Must not: replace `PreviewRelay` or `WebsocketServer` with a mock; use the 4a test route.

**T-PRV-27** (ws). Old and bad client texts.

- File: `skellycam/tests/preview/test_endpoint.py`.
- Set-up: as T-PRV-26, with one ring at 30 fps.
- Steps: send `{"frameNumber": 3, "displayImageSizes": null}`, `{not json`,
  `{"message_type": "camera_ready", "camera_id": 7}`, then `ping`.
- Pass: `pong` arrives; the connection stays open; camera messages continue; the global kill flag
  stays `False`; no record at ERROR.
- Runs: as T-PRV-26.
- Must not: as T-PRV-26.

**T-PRV-28** (ws). The tasks end after a close.

- File: `skellycam/tests/preview/test_endpoint.py`.
- Set-up: as T-PRV-26, with four rings at 60 fps and payloads of 607,032 bytes.
- Steps: the client answers at once. Close the client after 2 s.
- Pass: each task of `WebsocketServer` has ended within 1 s of the close; the global kill flag stays
  `False`; no record at ERROR.
- Runs: as T-PRV-26.
- Must not: as T-PRV-26.

**T-PRV-29** (capture-fake). Each ring-reader close runs on the event loop [Q4].

- File: `skellycam/tests/preview/test_ring_close_on_loop.py`.
- Set-up: real: `CameraGroupManager`, `CameraGroup` with its watch thread, the rings, `PreviewRelay`
  with fake send functions that record the messages. Fake: three fake sources of
  `skellycam/tests/capture/fake_source.py`, made as `capture_app` of `capture_session.py` does. A
  spy wraps `FrameRingReader.close` and records `threading.get_ident()` of each call.
- Steps: run the sender. When B has sent at least 3 camera messages [Q866], end the process of camera B (its
  fake source exits), so that the watch thread acts. Wait until the camera status of B changes. Restart B. Run 2 s more.
- Pass: each `close` of a ring reader runs on the thread of the event loop; A and C get camera
  messages during the whole test; B's camera messages come from the new ring after the restart.
- Runs: no marker. `capture-windows`, `capture-linux`, `capture-macos`. It can pass before the 4b
  code (4.3).
- Must not: patch the watch thread or `_close_ended_ring`; add a lock to the sender; skip on a
  system.

**T-PRV-30** (search). The old format is deleted.

- File: `skellycam/tests/preview/test_old_format_deleted.py`.
- Set-up: none. The names and the files of 7.7, checked on `dom/integration` [S].
- Steps: search the files of 7.7 for the names of 7.7. Do not search the decision log, `specs/` and
  `skellycam/tests/preview/`. Check that each deleted file of 3.1 does not exist, and that
  `WebsocketServer` has no `_send_json` (7.7).
- Pass: no hit; no deleted file exists; no `_send_json`. The rule is the deletion itself [P5].
- Runs: no marker. `capture-windows`, `capture-linux`, `capture-macos`.
- Must not: search `node_modules`, build output or `.venv`.

**T-PRV-31** (doc). The interface note.

- File: `skellycam/tests/preview/test_interface_note.py`.
- Set-up: none.
- Steps: read `specs/preview-interface-note.md` and table 3.2 of [`preview.md`](preview.md).
- Pass: the note exists; it has a heading for each item of section 8; its camera message table
  equals table 3.2 of [4a].
- Runs: no marker. `capture-windows`, `capture-linux`, `capture-macos`.
- Must not: check the prose.

#### UI unit tests

Each unit test runs with `npm run test:player:unit` in `player-windows`, `player-linux` and
`player-macos`, through the glob of 7.8. Each one obeys these rules too: no browser, no DOM, no
React, no server, no timer wait (the test resolves the promises of its fake tiles itself).

**T-PRV-32** (unit). The parser reads the shared fixture.

- File: `skellycam-ui/src/services/server/preview/tests/unit/camera-message.test.ts`.
- Set-up: `camera-messages.json` of T-PRV-25; the real `parseCameraMessage`.
- Steps: parse each case.
- Pass: each field equals its case: `frameNumber` and `arrivalNs` as `BigInt`, also above 2^53;
  `jpeg` is `null` for the two flagged cases and equals the bytes for the others; the camera id has
  no NUL.
- Must not: convert the 64-bit values to `number` before the compare.

**T-PRV-33** (unit). The parser refuses a bad message.

- File: `skellycam-ui/src/services/server/preview/tests/unit/camera-message.test.ts`.
- Set-up: the real `parseCameraMessage` and `PreviewTiles` with a fake tile and a fake `sendReady`;
  `console.error` replaced by a recorder.
- Steps: change a fixture case: `version` 0 and 2; 47 bytes; a length one byte too long and one too
  short; `rotation_cw_deg` 45; an empty camera id. Give each to `PreviewTiles.receive` two times.
- Pass: each throws in `parseCameraMessage` with its reason (the version text names both values);
  `receive` writes no second `console.error` for the same message; the seven messages write 4 to 7
  `console.error` calls [Q829]; no update; no ready message.
- Must not: check the full text of an error, except the two version values.

**T-PRV-34** (unit). Newest pending; one ready message for each draw.

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: `PreviewTiles` with a fake `sendReady`, a fake `onDrawn` and a fake `now`. Camera A has a
  fake tile whose `update` waits on a promise of the test.
- Steps: messages of frames 1, 2 and 3 arrive; then one `tick`; then resolve with `'drawn'`.
- Pass: one update, with frame 3; frames 1 and 2 never reach the tile; no ready message before the
  resolve; one `camera_ready` for A after it; `drawnCount` of A is 1; `onDrawn` was called one time,
  with A and the time of the fake `now`.
- Must not: call `tick` from a timer.

**T-PRV-35** (unit). One update in flight; a slow camera does not hold back another camera.

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: as T-PRV-34, with cameras A and B. B's update never resolves.
- Steps: frames 4 and 5 of A and of B arrive during A's update; three ticks; resolve A. Then one
  tick.
- Pass: while A is busy: no second update for A. After the resolve: one ready message for A, and
  the next tick draws frame 5 of A. A draws while B stays busy; B gets no second update and no
  ready message.
- Must not: as T-PRV-34.

**T-PRV-36** (unit). A flagged message.

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: as T-PRV-34.
- Steps: a good message and its draw; then a message with flags 0x04 and rotation 90; then a good
  message.
- Pass: the flagged update has `jpeg` `null`, mark `flagged`, the label frame of the flagged
  message and `rotationCwDeg` 90; one ready message after it; `drawnCount` and `onDrawn` do not
  change for it. The next update has the JPEG and mark `null`.
- Must not: as T-PRV-34.

**T-PRV-37** (unit). An overlay update with no frame; the label before the first frame [Q1].

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: as T-PRV-34, with no message yet.
- Steps: `setOverlay` with the label `Camera 2 · USB Camera`, state `starting` and a rate text; one
  tick; resolve. Then a frame update in flight; `setOverlay` with state `too_slow`; ticks; resolve.
- Pass: first: one update with `jpeg` `null`, `label.frame` `null`, the label, the state and the
  rate text; no ready message; no `onDrawn`. Second: no update while the frame update is in flight;
  one overlay update after the resolve, with `too_slow` and `label.frame` equal to the frame number
  of the drawn frame.
- Must not: as T-PRV-34.

**T-PRV-38** (unit). A hidden page and the UI pause.

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: as T-PRV-34.
- Steps: 100 messages for A with no tick (a hidden page). Then `setPaused(true)` and 10 ticks. Then
  `setPaused(false)` and one tick.
- Pass: no update and no ready message while there is no tick or while paused; then one update,
  with the newest message.
- Must not: as T-PRV-34.

**T-PRV-39** (unit). No tile yet; tile removed; connection closed.

- File: `skellycam-ui/src/services/server/preview/tests/unit/preview-tiles.test.ts`.
- Set-up: as T-PRV-34, with cameras A and C.
- Steps: messages for C with no tile; then `setTile(C)` and a tick; then `setTile(C, null)` and a
  new message. Then `clearPending()` with a pending message of A.
- Pass: no ready message for C before its tile; then one update with the newest message of C and
  one ready message; after the removal, no update for C; after `clearPending`, no update for A at
  the next tick; the tile of A stays.
- Must not: as T-PRV-34.

**T-PRV-40** (unit). The values from `app_state` and `framerate_update`: states, lists, label,
order [Q5, Q7].

- File: `skellycam-ui/src/services/server/preview/tests/unit/server-messages.test.ts`.
- Set-up: the real functions of `server-messages.ts` and `cameraLabel` and `labelText` of `camera-labels.ts`
  [Q825];
  plain objects for `app_state`, `framerate_update` and the camera list.
- Steps: give `app_state` objects: each of the eight states, `null`, `"unknown"`, no `status`; a
  group with `alive` `false` that has camera `c1` `failed`, `c2` `starting` and `c3` `ready`; a
  camera list with `c1` index 9, `c2` index 2 and `c3` index 6, name `c922 Pro Stream Webcam`; a
  fourth camera `c4` that is in `app_state` and not in the camera list, with `camera_index` 4 and
  `camera_name` `USB Camera`. Give `framerate_update` objects with `delivered_framerate` `null` and
  29.97.
- Pass: `cameraState` is each state, then `null`, `null`, `null`; for the eight states,
  `connectedCameraIds` holds the camera exactly for `checking`, `too_slow`, `ready` and
  `recording` [Q10]; `gridCameraIds` holds all four ids, in the order `c2`, `c4`, `c3`, `c1` (list
  numbers 2, 4, 6, 9); for the group that is not alive, `connectedCameraIds` holds only `c3`; the
  label of `c3` is
  `Camera 6 · c922 Pro Stream Webcam`; the label of `c4` is `Camera 4 · USB Camera`; no label holds
  a camera id; `labelText('camera c3 is failed', list)` gives
  `Camera 6 · c922 Pro Stream Webcam is failed` [Q13]; `rateText` is `null` and `"30.0 fps"`.
- Must not: import the store or React.

**T-PRV-41** (unit). The frame rate store keeps each camera and each count apart.

- File: `skellycam-ui/src/services/server/preview/tests/unit/framerate-store.test.ts`.
- Set-up: the real `FramerateStore`.
- Steps: two `framerate_update` messages for two cameras, one `app_state` with `replaced_count`, and
  `recordDrawn` calls for one camera.
- Pass: each camera has its own Captured rate, Displayed rate, `notShown`, `ringSkipped`,
  `oversize` and `replaced`; the Captured rate does not change after `recordDrawn`; no value is a
  sum of two counts; `clear()` empties each camera.
- Must not: read `Date.now()` for a pass value.

**T-PRV-42** (unit). The product code reads no canvas back.

- File: `skellycam-ui/src/services/server/preview/tests/unit/no-read-back.test.ts`.
- Set-up: none.
- Steps: search the product code of `skellycam-ui/src` (not the `tests/` folders) for
  `getImageData`, `toDataURL`, `toBlob` and `readPixels`.
- Pass: no hit [T, player 8.3].
- Must not: search `node_modules` or build output.

**T-PRV-53** (unit). The Displayed series comes from the drawn frames [Q3].

- File: `skellycam-ui/src/services/server/preview/tests/unit/framerate-store.test.ts`.
- Set-up: a real `PreviewTiles` with fake tiles that resolve `'drawn'` at once, a fake `now`, and
  `onDrawn` connected to a real `FramerateStore.recordDrawn`. The store gets the same fake `now` [Q864].
- Steps: camera A: 31 frames, one tick each, with `now` in steps of 33.333 ms. Then a gap of 2 s
  with no tick. Then 31 frames in steps of 16.667 ms. Also one flagged message and one overlay
  update for A. Then 1 s more with no drawn frame [Q864].
- Pass: Displayed of A (the rate over the last 1 s of drawn frames, 5.8) is 30.0 ± 0.1 after the first
  part and 60.0 ± 0.1 after the last part [Q826]; the
  gap of 2 s adds no value; the flagged message and the overlay update add no value; Captured of A
  stays empty; after the 1 s with no drawn frame, Displayed of A is 0 [Q864].
- Must not: use a real clock.

#### UI component tests

Each component test runs with `npm run test:player:browser` in `player-windows`, `player-linux`
(under `xvfb-run`) and `player-macos`, through the `testMatch` of 7.8, except T-PRV-49 (Windows
only). Each one has this set-up, unless the test says other: `ui_server.py` in a subprocess
(7.2); the harness main process of the player with the page `preview`; real: the websocket route,
`WebsocketServer`, `PreviewRelay`, the rings, `ServerContextProvider`, `CameraViewsGrid`,
`PreviewTiles`, `Tile` with ImageDecoder; fake: the camera list of the store, the manager and the
writers of `ui_server.py`. The pass thresholds are loose, so that a slow runner passes [agent 23
of 4a]. [NV]: that `beginFrameSubscription` gives the images of the harness window on the Linux
and macOS runners. If it does not, the test fails there, and the agent reports it to the user. No
test falls back to a pixel read-back.

**T-PRV-43** (component). Three cameras at 30 fps: each tile shows its own camera [Q9].

- File: `skellycam-ui/src/components/camera-views/tests/browser/preview.spec.ts`.
- Set-up: fake rings; 3 barcode cameras (640 x 360) at 30 fps.
- Steps: connect; run 5 s; observe the last 4 s with the outside observer.
- Pass: in each capture, each tile reads the camera number of its own camera; for each tile, the
  frame number changes in at least 50 % of consecutive captures; the server counts at least 80 % of
  the frames as ready messages for each camera; the kept overlay of each tile has the camera list
  label (`Camera <n> · <name>`), a rate text of 30.0 ± 0.5 fps and the state `ready`.
- Must not: check a frame against the clock of the page.

**T-PRV-44** (component). The states of the cameras, with no filter on `alive` [Q1, Q7].

- File: `skellycam-ui/src/components/camera-views/tests/browser/states.spec.ts`.
- Set-up: `ui_server.py` in the mode capture fakes: real `CameraGroupManager` and `CameraGroup`;
  camera A is a fake source that holds in `starting`; camera B fails to open (`failed`); camera C is
  `ready`. A camera cannot join a running group, so A fails its first open, and its second open (an apply
  with a retry of A) holds [Q830].
- Steps: connect. Then release A. Then C's fake source stops its frames for more than 2 s (`dead`).
- Pass: while A is `starting`: three tiles, with no filter on `alive` [Q830]; the observer reads
  "none" for A and B (black) and the camera of C; the kept overlay of A has `starting`, of B
  `failed`, of C `ready`; the overlays of A and B have the label and no frame part [Q1]. After the
  release: the observer reads A's camera, with `ready`. After the stall: the reading of C stops
  changing, with `dead`. Each state shows within 1.5 s of its change in `app_state`.
- Must not: script the states in `ui_server.py` (this test uses the real group state).

**T-PRV-47** (component). Reconnect and give up.

- File: `skellycam-ui/src/components/camera-views/tests/browser/preview.spec.ts`.
- Set-up: fake rings; 2 cameras at 30 fps.
- Steps: close the connections in `ui_server.py` while frames flow; the UI reconnects. While
  `RECONNECTING`, force a capture of the window (7.2) [Q867]. Then stop `ui_server.py` until the UI gives up.
- Pass: while `RECONNECTING`, the reading of each tile does not change and is not "none"; after the
  reconnect, the readings change again within 3 s; after the UI gives up (`DISCONNECTED` or `FAILED`),
  the grid shows its empty state (DOM), and the console has no error except the connection errors
  [Q831].
- Must not: stop `ui_server.py` with a kill that leaves a port bound for the next test.

**T-PRV-48** (component). Cameras come, go and restart; the order of the camera list [Q5].

- File: `skellycam-ui/src/components/camera-views/tests/browser/preview.spec.ts`.
- Set-up: fake rings; cameras A, B and C with the list numbers 7, 3 and 5 in the camera list of the
  store.
- Steps: check the order. Add camera D (list number 1). Remove camera B. Restart camera A with a new
  ring from frame 0.
- Pass: the grid cells are in the order of the list numbers, in the DOM and on the screen (B, C, A;
  then D, B, C, A after D is added; then D, C, A) [Q833]; D gets a tile
  that the observer reads within 2 s; B's tile leaves the grid; A's tile shows the frames of the new
  ring (the kept overlay frame starts again at a low number); the other cameras continue; each grid cell has a
  transition duration of 0 s [Q895].
- Must not: change the layout by a drag during the test.

**T-PRV-49** (component). A hidden window gets only the safety net.

- File: `skellycam-ui/src/components/camera-views/tests/browser/hidden-window.spec.ts`.
- Set-up: fake rings; 2 cameras at 30 fps; two windows with the page, each with its own connection.
  Window 2 has the default `backgroundThrottling` (the product setting).
- Steps: hide window 2 for 5 s, then show it.
- Pass: while hidden, window 2 draws nothing: `requestAnimationFrame` gives no frame in window 2 after its first
  check [Q885], and the server counts 0.5 to 1.6 messages each second for each camera of window 2; window 1 keeps at least 80 % of the
  frames; after the show, the observer reads new frames in window 2 within 1 s.
- Runs: `player-windows` only. The spec file skips on other systems with
  `test.skip(process.platform !== 'win32', ...)`, with the reason of 7.5.
- Must not: open window 2 with `backgroundThrottling: false`.
- The first run (Q835) showed that a hidden or minimised harness window keeps `document.visibilityState`
  `visible` while it draws nothing, so the test checks that drawing stops, not the visibility flag [Q885].

**T-PRV-50** (component). The frame rate viewer [Q3].

- File: `skellycam-ui/src/components/camera-views/tests/browser/framerate-viewer.spec.ts`.
- Set-up: fake rings; cameras A and B at 30 fps. Camera A: 3 oversize frames, 1 ring skip,
  `replaced_count` 7 in `app_state`.
- Steps: open the frame rate viewer, full and collapsed.
- Pass: the series and the table show "Captured" and "Displayed" for each camera, with the camera
  list label; in the Captured row of A, "Oversize" shows 3, "Ring skipped" shows 1 and "Replaced"
  shows 7 [Q832], and "Not shown" equals the last `not_shown_count` of the server for this
  connection; Captured of each camera is 30.0 ± 1 fps; Displayed of each camera is more than 0; no
  series or column is named "Server", "Display" or "Delivered"; the two cameras have two different
  colours; the collapsed view lists each camera with both values. The test reads the DOM and the SVG
  of the viewer, not a tile.
- Must not: check the exact Displayed value (it depends on the runner).

#### Benchmarks

Each benchmark runs by hand on the Windows test machine with
`playwright test -c playwright.player-bench.config.ts`, as the player benchmarks do. Not in CI. Each
one writes its result as JSON to `PLAYER_BENCH_OUT`. The results go to an evidence entry. A missed
target goes to the user, and section 6.4 applies.

**T-PRV-51** (benchmark). 8 cameras at 1080p30: the full outside proof [Q9].

- File: `skellycam-ui/src/components/camera-views/tests/bench/preview.bench.ts`.
- Set-up: section 6.2 with F = 30.
- Steps: 3 runs of 2 s warm-up and 60 s measurement.
- Pass: B-1a, B-1b, B-2 and B-3 of 6.3, each with its kind of proof, in the median of the runs.
- Must not: read `drawnCount` before the end of a run; give `drawnCount` as an outside proof.

**T-PRV-52** (benchmark). 8 cameras at 1080p60: the inside counts [Q9].

- File: `skellycam-ui/src/components/camera-views/tests/bench/preview.bench.ts`.
- Set-up: section 6.2 with F = 60.
- Steps: as T-PRV-51.
- Pass: B-1b, B-2 and B-3 of 6.3, in the median of the runs. The values of the outside observer are
  recorded, with no target.
- Must not: report a value of the outside observer at 60 fps as a pass or a miss.

Two unit tests of `preview/tests/unit/` are guards of the code lane, with no T-ID: `preview-tiles-order.test.ts`
(the order of the tile updates turns at each refresh [Q893]) and `preview-tiles-reject.test.ts` (a rejected tile
update clears `busy`). One Python test is a guard too: `skellycam/tests/preview/test_raw_camera_preview.py` (the
JPEGs of a YUY2 or NV12 camera of step 3b reach `PreviewRelay` like any other).

T-PRV-45 and T-PRV-46 were cut in revision 2: T-PRV-36 tests the flagged message, T-PLAY-41 tests
the rotation of the tile, and T-PRV-36 tests that the rotation reaches the tile.

### 7.5 Parity of the systems [P7]

| ID | Windows | Linux | macOS |
|---|---|---|---|
| T-PRV-25 to T-PRV-31 | runs | runs | runs |
| T-PRV-32 to T-PRV-42, T-PRV-53 | runs | runs | runs |
| T-PRV-43, T-PRV-44, T-PRV-47, T-PRV-48, T-PRV-50 | runs | runs, under `xvfb-run` | runs |
| T-PRV-49 | runs | not run: no one has verified that a hidden window under `xvfb-run` stops `requestAnimationFrame` [NV] [Q885] | not run: the same for the macOS runner [NV] |
| T-PRV-51, T-PRV-52 | runs (test machine, by hand) | owed | owed |

T-PRV-38 keeps the rule of the hidden page on each system. When someone verifies the behaviour on
Linux or macOS, T-PRV-49 can run there. The component tests need Python on each system, for
`ui_server.py`.

### 7.6 Tests of the player that 4b changes

The player owns these tests. They change on the branch that holds the player (`dom/player`, or
`dom/integration` when the player is in it) [Q1, agent 27]:

- **T-PLAY-37** (unit): `TileLabel.frame` `null` gives no frame part; the camera part stays.
- **T-PLAY-44** (component): with the label on and `frame` `null`, the kept overlay has no frame text
  and has the camera text.
- **T-PLAY-35** (unit): a file in a `tests/` folder outside the module may import a file of
  `src/player/tests/` (the observer and the barcode helpers of 7.2). A product file outside the
  module still imports only `index.ts` and the two files of `main/`.

The change of `tile.ts`, `format.ts` and section 8.3 of `specs/player.md` for `frame: null` goes
with them [Q1].

One test of the demo commits changes too [Q13]: `src/store/slices/cameras/camera-labels.test.ts`
expects `Camera 1 · USB Camera` and `Camera 5 · Kiyo Pro` in place of `Camera 1 (USB Camera)` and
`Camera 5 (Kiyo Pro)`. The unit glob of 7.8 runs it in CI.

### 7.7 What T-PRV-30 searches

Files: `skellycam/**/*.py`, `skellycam-ui/src/**`, `skellycam-docs/docs/**` and
`skellycam-docs/i18n/**`. A name matches only as a whole word, so `FRAME_HEADER_SIZE` does not match
`CAMERA_FRAME_HEADER_SIZE` of 5.2 [Q828]. Names:

- In Python files and docs: `frameNumber` (the old JSON key), `frameAcknowledgment`,
  `backend_framerate`, `frontend_framerate`.
- In Python files only: `frontend_payload_bytearray`, `FRONTEND_FRAME_HEADER_DTYPE`,
  `FRONTEND_PAYLOAD_HEADER_FOOTER_DTYPE`, `get_latest_ring_payload`, `get_latest_frontend_payloads`,
  `get_backend_framerate_updates`, `_frontend_image_relay`, `check_frame_acknowledgment_status`,
  `last_received_frontend_confirmation`, `BACKPRESSURE_WARNING_THRESHOLD`, `FramerateUpdateMessage`,
  `parse_relay`, `read_latest_ring_frames` [Q871].
- Not a name search: `WebsocketServer` has no attribute `_send_json` [Q871]. `PreviewRelay` keeps
  its own `_send_json`, the JSON send that the server passes in (4.1).
- In UI files: `frameAcknowledgment`, `backend_framerate`, `frontend_framerate`. Not
  `frameNumber`: the parser field `CameraMessage.frameNumber` (5.2) is in the UI.
- In UI files and docs: `parseMultiFramePayload`, `PAYLOAD_FOOTER`, `FRAME_HEADER_SIZE`,
  `FrameProcessor`, `CanvasManager`, `transferControlToOffscreen`, `bitmaprenderer`,
  `frame-decode.worker`, `offscreen-renderer.worker`.

The test writer checks each name and path on `dom/integration` first [S].

### 7.8 Counts and CI [agent 12]

- Python: T-PRV-25 (tool), T-PRV-26 to T-PRV-28 (ws), T-PRV-29 (capture-fake), T-PRV-30 (search),
  T-PRV-31 (doc): 7.
- UI: T-PRV-32 to T-PRV-42 and T-PRV-53 (unit): 12. T-PRV-43, T-PRV-44, T-PRV-47 to T-PRV-50
  (component): 6.
- Benchmarks: T-PRV-51 and T-PRV-52: 2. Total: 27. T-PRV-45 and T-PRV-46 are cut.
- Changed tests of the player: T-PLAY-35, T-PLAY-37, T-PLAY-44 (7.6). Changed test of the demo
  commits: `camera-labels.test.ts` (7.6).
- The npm script `test:player:unit` adds the globs
  `src/services/server/preview/tests/unit/**/*.test.ts` and `src/store/slices/cameras/**/*.test.ts`
  (the label tests of the demo commits) [agent 31]. `playwright.player.config.ts` adds
  `components/camera-views/tests/browser/**/*.spec.ts` to `testMatch`.
  `playwright.player-bench.config.ts` changes `testDir` to `./src` and its `testMatch` to the
  benches of the player and `components/camera-views/tests/bench/**/*.bench.ts`.
  `vite.player-harness.config.ts` and the harness main process add the page `preview`.
- CI, in its own PR [AGENTS.md section 6]: `player.yml` adds `dom/integration` to its branches [S],
  the trigger paths `skellycam-ui/src/services/server/**`,
  `skellycam-ui/src/components/camera-views/**`, `skellycam-ui/src/store/slices/cameras/**`,
  `skellycam/tests/preview/**` and `specs/preview-4b.md`, and a pinned uv set-up step in its three
  jobs, as `capture.yml` has. `capture.yml` adds `dom/integration` to its branches [S],
  `specs/preview-4b.md`, `tools/write_camera_message_fixture.py` and its test to its paths, and
  `tools/tests/test_camera_message_fixture.py` to the selection of its three jobs, so that T-PRV-25
  runs on the three systems.
- T-PRV-25 imports `skellycam`, and `doc-checks.yml` syncs only the dev group. T-PRV-25 runs only in the
  three capture jobs, which sync the project, and stays in `tools/tests/` [Q836]. The CI PR thus adds
  `--ignore=tools/tests/test_camera_message_fixture.py` to the pytest step of `doc-checks.yml`.

## 8. The interface note for the FreeMoCap session [P5]

At the end of 4b, write `specs/preview-interface-note.md` [agent 15]. T-PRV-31 checks it. It has
these headings, each with the facts of 4b:

1. **Camera message**: table 3.2 of [4a], the version rule [4a 3.3], the `BigInt` rule, the
   flagged message with `jpeg_len` 0.
2. **Ready message and safety net**: `camera_ready` [4a 4.1], newest pending, one ready message
   for each draw, the 1 s safety net of the server [A6].
3. **Deleted**: the group message, the `frameNumber` acknowledgement, `backend_framerate` and
   `frontend_framerate`.
4. **framerate_update**: the shape for each camera [4a 6.2], the meaning of each count, and the two
   series: Captured from `delivered_framerate`, Displayed computed by the client (5.8).
5. **Camera status**: where `state` and `replaced_count` are in `app_state`, and that `alive` is not
   a filter for the tiles (4.5).
6. **Tile**: the module `skellycam-ui/src/player/` and its import `@/player/index.ts`; a copy of the
   folder is the way for the FreeMoCap UI [player 4.3]; the `TileUpdate` values of 5.4, with the
   camera list label.
7. **Compression**: websocket compression is off [A9]. A client must not need it.

## 9. Conflicts found

1. **The tile label needed a frame number.** `TileLabel.frame` was a `number`, and `formatFrame`
   always drew it. Resolved: `frame` can be `null` [Q1] (7.6).
2. **An overlay update supersedes a decode.** A `tile.update` with `jpeg: null` during a decode
   makes the decode resolve `'superseded'` and drops its image (`tile.ts`, "newest wins"). Rule 2 of
   5.3 (one update in flight) avoids it. No change of the tile is needed.
3. **Phase 3a closed rings on another thread.** Resolved by fix F8 on the capture branch (4.3) [Q4].
   T-PRV-29 is the guard.
4. **Today's grid lists only cameras that sent a frame, of groups that are alive.** Resolved: 5.5
   and 5.6 take the list from `cameras` of `app_state` [Q7].
5. **The tile branch was local and unaccepted code.** The user accepted the merge [Q2]. The base is
   now `dom/integration` [S] (section 2).
6. **The status `state` can be `null`.** On `dom/native-jpeg`, `CameraStatus.state` is `None` before
   the first state. The tile then shows no state (5.4).
7. **The outside observer is too slow to see each frame at 60 fps.** Resolved: the full outside
   proof is at 30 fps; 60 fps uses the inside counts [Q9] (6.1).
8. **The harness windows do not throttle.** The player harness opens windows with
   `backgroundThrottling: false`. T-PRV-49 needs a window with the product setting (7.2).
9. **The display rate had no source after 4a.** Resolved: the client computes Displayed (5.8) [Q3].
10. **Two cameras of one model have one `camera_name`.** Resolved: the label holds the camera list
    number [Q5].
11. **The websocket tests fail today.** `logger.success` needs `configure_logging` (3.2).
12. **"Streaming" of a `too_slow` camera.** The demo and Q7 differed. Resolved: a `too_slow` camera
    counts as streaming [Q10] (5.7).
13. **Two label forms.** The demo wrote `Camera 1 (USB Camera)` in the server reasons. Resolved: one
    form, `Camera 1 · USB Camera` [Q13] (5.4).
14. **The label in the player.** The player shows `camera_label` of the take, which is 6 to 8 hex
    characters or `cam<N>` by the format (SFF-720, SFF-753 of `../skellyfileformat/spec/SPEC.md`).
    Resolved: the player shows `Camera <os_index> · <os_name>` from the take [Q11]. Still open: the
    `os_index` of a take can differ from the list number (section 12.2). Q14.
15. **The PR target.** A1 said `development-streaming`. Resolved: upstream `development` [PR].
    Section 6 of `AGENTS.md` names upstream `development` (section 12.2).

## 10. Decisions that bind 4b

P1, P2, P4, P5, P6, P7, A1 to A10 and the tile thread decision of
[ADR-G651](../decisions/entries/G651-phase-4-live-preview-decisions-p1-to-p7.md), with A1 changed by
[PR]; the answers Q1 to Q13 and the decision [PR] of 2026-11-20
([ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md));
the accepted 4a spec [`preview.md`](preview.md) with its sections 10 and 11; the decisions [T] of
section 0; `specs/player.md` section 8 on `dom/player`; the camera states and status of
`specs/windows-capture.md` section 8 on `dom/native-jpeg`.

## 11. Choices of the agent

Each item fills a gap. The body marks each one [agent n]. Items 1 to 19 are of revisions 1 and 2
([ADR-EE0E](../decisions/entries/EE0E-step-4b-preview-spec-and-agent-choices.md),
[ADR-R1TD](../decisions/entries/R1TD-revision-2-of-the-step-4b-preview-spec.md)). Items 20 to 31
are of revision 3
([ADR-W674](../decisions/entries/W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md)).
Revision 3 replaces items 10, 11 and 17.

1. `_preview_relay` wraps `PreviewRelay.run` with the `except` clauses of the other tasks.
2. (Revision 2: removed. No rename of `_ring_lock`. Revision 3: no lock in the sender [Q4].)
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
   `gridCameraIds`.
9. The method of the measurement (6.2): the real server with fake rings, the harness page, barcode
   JPEGs of about 190 kB, the observers outside the page, 3 runs of 60 s.
10. (Revision 3: replaced by item 26.)
11. (Revision 3: replaced by items 27 and 28.)
12. The UI tests join the scripts and the configs of the player runners; the CI change of 7.8, in
    its own PR.
13. The `FRAMERATE` subscription of `CameraGroupManager` stays. No process publishes on that topic
    today, but it is not part of the preview.
14. `measured_fps` is not shown. No decision asks for it.
15. The interface note is the file `specs/preview-interface-note.md`.
16. The UI component tests use the real Python server, not a server in TypeScript. A websocket
    server in Node needs a new npm package.
17. (Revision 3: replaced by item 24.)
18. (Revision 2: now Q8.)
19. (Revision 2.) A session fixture in `skellycam/tests/conftest.py` calls `configure_logging`.
20. The camera list label comes from `index` and `name` of the camera list of the store, else from
    `camera_index` and `camera_name` of the config; one function `cameraListLabel` in
    `camera-labels.ts` makes it; the separator is `" · "`.
21. The grid order: ascending camera list number, then the camera id.
22. Displayed: `PreviewTiles` gets `onDrawn` and `now`; `FramerateStore.recordDrawn` keeps the time
    between drawn frames in the windowed statistics of today; a time longer than 1 s is not added.
23. The viewer: one colour for each camera, a solid Captured line and a dashed Displayed line, one
    histogram panel for each series.
24. The statistics table: two rows for each camera, the counts in the Captured row; the collapsed
    view gives both values.
25. The i18n keys `capturedFramerate` and `displayedFramerate`; the wire field stays
    `delivered_framerate` [4a 6.2].
26. The targets of 6.3 for the split of Q9: B-1a at 30 fps only, with a lag of at most 2 frames and
    at least 0.9 x min(30, C) distinct frames each second; B-1b, B-2 and B-3 at 30 and at 60 fps;
    two benchmarks, T-PRV-51 and T-PRV-52.
27. The tests check images only with the outside observer and read the overlay from `Tile.overlay`;
    the observer moves to `src/player/tests/harness/observer.ts`; T-PLAY-35 allows a test file to
    import `src/player/tests/`; the tests of the player of 7.6.
28. The helpers of 7.2: barcode camera numbers 1 to 8; 640 x 360 JPEGs for the component tests;
    the new commands of `ui_server.py`; the camera list of the harness page.
29. The test files, the items of each test and the CI jobs of 7.4 and 7.8; the new unit test
    T-PRV-53; T-PRV-29 has only its first part [Q4].
30. Section 2 states the new base as a note of the supervisor, with the sections that it changes.
31. The unit glob also runs `src/store/slices/cameras/**/*.test.ts`, so that the changed label test
    of the demo commits runs in CI [Q13].

## 12. Decisions of the user of 2026-11-20

### 12.1 The answers of the user

The user answered the nine questions of revision 2 on 2026-11-20
([ADR-VYS7](../decisions/entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).
Then he accepted the spec with these answers, and gave the go-ahead for the tests of 4b, not the
code.

- **Q1, yes.** `TileLabel.frame` can be `null`. A tile shows its label and state with no frame part,
  before the first frame and for a failed camera (5.3, 5.4, 7.6).
- **Q2, yes.** Merge `dom/native-jpeg` into `dom/preview` now, and `dom/player` before the first UI
  test commit. The 4b PR then also carries 3a and the 6a player, unless they land first. Section
  12.2 gives the later base (section 2).
- **Q3, changed.** The user: "the intent of this is to show how fast the camera frames are being
  delivered to disk, the other is to show how fast the ui is updating." Two series for each camera,
  named for what they mean. "Captured": the frames that the camera delivered to the server,
  measured where the frames enter the ring; during a take, this is what goes to disk; a problem of
  the recorder shows as a warning, not as a lower line. "Displayed": the frames that the UI drew.
  One colour for each camera, as revision 2 proposed (5.8).
- **Q4, settled.** Fix F8 is in on the capture branch: the watch thread hands each close to the
  event loop. No question. T-PRV-29 part 1 stays as the guard (4.3).
- **Q5, changed.** The tile label is the list number and the name of the camera, as the camera list
  shows it, for example `Camera 6 · c922 Pro Stream Webcam`, not the hex camera id. It is the same
  in the live view and in the player, and the tiles are in the order of the camera list (5.4, 5.5).
  The player part is Q11.
- **Q6, yes.** The targets B-1a to B-3 and the rule of the worker: a worker only after B-1b, B-2 or
  B-3 misses in the median of three runs, by a later spec (6.3, 6.4).
- **Q7, yes.** One tile for each camera in `cameras` of `app_state`, with no filter on `alive`.
  `connectedCameraIds` is the cameras in `checking`, `too_slow`, `ready` or `recording` (5.5, 5.6).
  The user noted the demo commits (5.7).
- **Q8, yes.** The new labels and the changed parts of the docs are in English only, until the
  translation process translates them (5.8, 5.9).
- **Q9, changed.** Test the UI with fake cameras at 30 fps with the full outside proof: the outside
  observer, which sees about 30 images each second, checks each picture. At 60 fps, use the inside
  counts only: the ready messages that the server counts, and the draw count of the product. 30 fps
  is the frame rate of the cameras of the user, and his floor (6.1, 6.3).

The user answered the four questions of revision 3 on 2026-11-20:

- **Q10, settled** by an earlier decision of the same day, in these accepted words: "A too-slow
  camera keeps its tile and counts as streaming. Its row says "Too slow at this exposure: lower the
  exposure", not "Failed". Update Cameras does not reopen it; the remedy is a changed setting."
  Thus the "N Streaming" count uses `connectedCameraIds`, and the row text is that sentence, not
  the failure text of the demo (5.6, 5.7).
- **Q11, yes.** The player label is `Camera <os_index> · <os_name>` from the camera config of the
  take, and the tiles are in the order of `group_position`. An older take without them shows
  `camera_label`. The change goes into `specs/player.md` and the recorder spec, not 4b (1.3). The
  user was told that nobody had checked that `os_index` equals the list number. Section 12.2 gives
  the check, and Q14 asks for the fix.
- **Q12, yes.** 4b shows no recorder warning. The recorder work adds it (1.3, 5.8).
- **Q13, yes.** One label form everywhere: the server reason texts use `Camera 1 · USB Camera`
  through `cameraListLabel` (5.4, 7.6).

Decision **[PR]** of 2026-11-20: the pull request target is upstream `development`. It replaces
`development-streaming` in the wording of A1. ADR-G651 does not change; ADR-VYS7 records the
decision (section 2).

### 12.2 Notes of the supervisor [S]

These notes are not decisions of the user. The supervisor relayed them on 2026-11-20.

- **The base.** A later decision of 2026-11-20 moves the work onto a new integration branch,
  `dom/integration` (section 2). Section 2 lists the sections of 4b that this changes.
- **Done.** `dom/integration` holds the 4a commits of `dom/preview` (the merge commits "Merge
  dom/preview into dom/integration" and "Merge dom/preview again"). 4b needs them (section 2,
  item 3).
- **Done.** Section 6 of `AGENTS.md` says "Open each PR against `development` of upstream"
  ([ADR-EQY4](../decisions/entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md)), as [PR]
  says for 4b.
- **Other decisions of 2026-11-20.** The exposure modes become Manual and Auto only (Auto: SkellyCam
  finds a manual value). One frame rate control for all cameras at the top of the camera list; 60
  fps only when each ticked camera passed a real 60 fps check. A USB 2 or USB 3 label next to each
  camera; a virtual camera reads "virtual". [`camera-requests.md`](camera-requests.md) specifies
  them. 4b only refers to them (1.3, 5.6, 6.1).
- **The check of `os_index`** [Q11], code of `dom/integration` read on 2026-11-20:
  - The list number. The UI shows `Camera {camera.index}`. `camera.index` is `index` of the
    detection response (`cameras-thunks.ts`). The server gives the position of the camera in the
    Media Foundation list on Windows, or the index of `cv2_enumerate_cameras` on Linux and macOS
    (`detect_cameras_devices.py`, `media_foundation/detect.py`).
  - The take value. `CameraGroup._take_camera` writes
    `os_index=device.index if device is not None else config.camera_index`, where `device` is
    `CameraGroupManager.detected_cameras[camera_id]`: the last detection of the server.
  - Normal case: equal. The detect route stores the same detection result that it gives to the UI.
  - They can differ:
    1. The apply request detects again on the server when a ticked camera is not in
       `detected_cameras` (for example after a replug). The positions can change. The list of the
       UI keeps the old numbers until the UI detects again.
    2. A detection by another window or client replaces `detected_cameras` for all windows.
    3. The fallback `config.camera_index` comes from `desiredConfig`. The UI keeps an older
       `desiredConfig` from memory (`existing.desiredConfig`) or from local storage
       (`saved.desiredConfig` over the defaults), so its `camera_index` can be a number of an older
       detection. The same stale value can reach the label fallback of 5.4.
  - Q14 proposes the smallest fix.

### 12.3 New question

The question is worded so that "yes" accepts the recommendation.

- **Q14.** The take writes the number that the camera list showed when the cameras were applied.
  Two one-line changes, outside 4b: (1) in `cameras-thunks.ts`, `camera_index` and `camera_name`
  of `desiredConfig` always come from the current detection (`index`, `name`), also over a kept or
  stored `desiredConfig`; (2) in `CameraGroup._take_camera`, `os_index` is `config.camera_index`
  (the number of the apply request), not `device.index`. Yes? Recommendation: yes. Then the
  player label of [Q11] equals the list label at the apply, in the three cases of 12.2. A detection
  after the apply, with no new apply, can still change the list number while the take keeps the
  old one. With change (1) only, cases 1 and 2 stay.
