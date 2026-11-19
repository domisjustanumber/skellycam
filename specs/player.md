# Phase 6 player specification: step 6a, the canvas player for new takes (video only)

Status: proposed by an agent on 2026-11-19
([ADR-4K7V](../decisions/entries/4K7V-phase-6a-player-spec-and-test-list.md)). The user reviews it
before any code. The decisions Y1 to Y7 of the user are accepted
([ADR-J2BQ](../decisions/entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)). Section 18 gives each
one in full, with the earlier decisions E1 to E9 that the user listed with them. The failing tests of
step 6a come before the product code of step 6a.

## 0. How to read this spec

Marks:

- **[Yn]**: decision n of the user, 2026-11-19 (section 18,
  [ADR-J2BQ](../decisions/entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)).
- **[En]**: an earlier decision of the user that the decision list of 2026-11-19 cites (section 18.2).
  This spec numbers them for reference only.
- **[SFF-nnn]**: a requirement of the format spec `../skellyfileformat/spec/SPEC.md`, draft v2, read
  at commit d67679a of that repository. This spec cites it. It does not repeat it.
- **[M file]**: measured; the file holds the result. Each research file is on branch `dom/research`
  at commit fc95be447 of this repository. It is not on this branch. Short names:
  - `RT` = `research/skellycam_recording/recording_upgrade/results/range_transport/FINDINGS.md`;
  - `IP` = `research/skellycam_recording/recording_upgrade/results/intra_playback/FINDINGS.md`;
  - `CC` = `research/skellycam_recording/recording_upgrade/results/chromium_codecs/FINDINGS.md`;
  - `GF08` = `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/gapfill/GF08_ts_sync.md`;
  - `PLAN` = `research/NATIVE_JPEG_CAPTURE_PLAN.md`.

  The evidence index `research/skellycam_recording/recording_upgrade/results/EVIDENCE_INDEX.md`
  (sections 2.8 and 2.9) points to these files.
- **[C file]**: a code fact of this branch, read on 2026-11-19.
- **[NV]**: not verified. No evidence proves it.
- **[agent n]**: an agent filled a gap that the decisions, the format spec and the evidence do not
  fix. Section 16, item n, lists each one. Section 17 holds the questions for the user.
- **[Fn]**: feature n of the player of today (section 3).
- **[Pn]**: proposed change n to skellyfileformat (section 13).

This spec uses British spelling. It cites files, not line numbers, except where the evidence cites a
line.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Step 6a gives skellycam-ui a canvas player for takes in the new format: camera JPEGs in MKV, with CSV
timing sidecars [E1]. One master clock drives all cameras. Each tile fetches its JPEG by a byte range
at the CSV offset and decodes it with `ImageDecoder` [E1, Y3]. Step 6a closes the playback gap that
recorder step 5a opens, so the two can land together [Y1].

### 1.2 Scope of 6a

6a delivers [Y1]:

- the take reader: the manifest, the video sidecars, the camera files (section 6);
- the master clock and the frame choice (section 7);
- the canvas tile (section 8);
- play, pause, step, seek, scrub and speed, with each feature of the player of today (section 3);
- the file access through the Electron main process (section 5) [Y2];
- the self-contained module (section 4) [Y6];
- the tests, with fixtures that the tests build (section 12) [Y7].

### 1.3 What waits for later steps

| Step | Delivers | This spec |
|---|---|---|
| 6b | Audio in the player. It needs recorder step 5b [Y1]. | 6a reads no audio file [agent 14]. |
| 6c | The switch between the new player and the old `<video>` path, and old takes [Y1, E2]. | 6a does not read an old take. Question Q1 asks for the smallest route that 6a needs. |
| 6d | The "upgrade recording" converter [Y1]. | None. |
| recorder 5c | The repair step. | 6a opens an unfinished take read only and offers no repair [Y5]. |
| phase 4 | The live preview. | Section 8.6 states only the boundary of the tile [Y3]. |
| open work | Option B: the Python server serves the take files [Y2]. | Section 5.8 states the place in the module. Section 14.4 gives the open-work item. |

### 1.4 Non-goals

- A change in skellyfileformat. Section 13 proposes text. The user decides it there.
- Any feature beyond the features of today (section 3), unless a decision names it. Examples: zoom,
  pan, full screen, frame export, an A-B loop, a camera offset.
- A reload of a take that is still being written. The reader reads a snapshot at open [agent 12].
- The capture info JSON, the processing info JSON, the calibration TOML, the Parquet and the journal.
  The player needs none of them in 6a [agent 14].
- The full reader result of SFF-885 and the JavaScript test adapter of the conformance tests
  (question Q2).
- The design of phase 4.

### 1.5 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| The take folder, the files, the reader rules | `../skellyfileformat/spec/SPEC.md` draft v2 | Section 6 applies the reader rules for the scope `player` [SFF-892]. |
| A dead camera and a damaged frame give rows with no image; each camera has equal rows | Recorder decisions R2 and R3 [E9]; the recorder spec (another branch) | Section 6.7 reads such rows. Section 13 proposes the format text. Section 14.2 lists what the player needs from the recorder spec. |
| The rotation value of a ring frame | [`frame-ring.md`](frame-ring.md) section 3 (`rotation_cw_deg`) | Section 8.6: the same meaning as `display_rotation` [SFF-751]. |
| Error flags of a ring frame | [`frame-ring.md`](frame-ring.md) section 4 | Section 8.6: a flagged ring frame never reaches the tile. |
| The interim preview relay | [`frame-ring.md`](frame-ring.md) section 2.3, [`windows-capture.md`](windows-capture.md) section 5.8 | Not changed. Phase 4 replaces it. |
| The transport and the header rules | `RT` sections 6 to 8 | Section 5. |
| Frame choice by time, not by index | `GF08`, `IP` P2, [SFF-783], [E4] | Section 7. |

### 1.6 Terms

| Term | Meaning |
|---|---|
| take, take folder, camera file, timing sidecar, device pair, position, multi-camera frame, player time | As in section 1 of the format spec. |
| row | A data row of a video timing sidecar. Row k has position k. |
| usable row | A row that the reader uses [SFF-746, SFF-740]. |
| no-image row | A row for which the camera file holds no frame. This is the "gap row" of Y4 and of the recorder decisions R2 and R3 [E9]. It is not the same as a row with the format flag `gap` [SFF-756]: such a row has a frame, and the player shows it as any other frame [agent 41]. |
| lost camera | A camera whose rows are no-image rows from one row to the end of the file [Y4, E9]. |
| K | The number of multi-camera frames that the player shows: the smallest number of usable frames of the camera files that the reader reads [SFF-754]. |
| take time t | An integer number of nanoseconds, relative to the take start [SFF-705]. The master clock holds it. |
| p_c(k) | The player time of row k of camera c [SFF-781]. |
| T_k | The time of multi-camera frame k (section 7.2). |
| k* | The frame number that the controls show (section 7.2). |
| the module | The player module of section 4 [Y6]. |
| the host | The program that mounts the module: skellycam-ui now, the freemocap UI later. |
| tile | The canvas that shows one camera (section 8) [Y3]. |
| `TakeFiles` | The page-side interface for the bytes of the opened take (section 5.1) [Y2]. |
| handler | The Electron main-process code behind `TakeFiles` (section 5.2) [Y2]. |

## 2. Steps of phase 6 and the done list of 6a

Phase 6 has four steps: 6a, 6b, 6c and 6d. The tests of a step come first [Y1].

Step 6a is done when:

1. All unit, component and electron tests of section 12 pass on Windows, Linux and macOS, on the
   development machine and in the CI workflow of section 12.6 [Y7].
2. The benchmarks of section 12 run on the Windows test machine, and the results go to an evidence
   entry. A benchmark that misses its target goes to the user. It does not stop 6a by itself
   [agent 37].
3. A take that recorder step 5a writes opens and plays in the app (question Q1).
4. No code outside `skellycam-ui/src/player/` imports a file of the module, except through the
   public entry points of section 4.3. The boundary test passes (T-PLAY-32).

## 3. The player of today

### 3.1 Features of today

The player of today is `SyncedVideoPlayer.tsx` with `PlaybackControls.tsx`, in
`skellycam-ui/src/components/playback/` [C]. It plays one `<video>` element for each camera. The
first video is the leader. The others follow when they drift by more than 2 frames. It derives the
frame as `currentTime × fps` [C, `IP` F6]. Its features:

| # | Feature of today | Where |
|---|---|---|
| F1 | A tile grid with one tile for each camera. Auto tiling chooses the column count that gives the largest tile area, with a smallest tile of 80 × 60 pixels. The host can set a manual column count (`manualColumns`) and reset the layout (`resetKey`). | `SyncedVideoPlayer` |
| F2 | Drag a tile onto another tile to swap the two; drag a tile to move it; resize a tile (`react-grid-layout` 2.3.0, no compaction). | `SyncedVideoPlayer` |
| F3 | The image fits the tile ("contain"), on black, with a thin border. | `SyncedVideoPlayer` |
| F4 | Tile overlay, top right: the frame number as `F` and the number with leading zeros, padded to the digits of the total frame count. | `SyncedVideoPlayer` |
| F5 | Tile overlay, bottom left: the camera ID (the video file name). | `SyncedVideoPlayer` |
| F6 | Tile overlay, bottom right: the time. It is the CSV time of the first camera for every tile, or an estimate from frame / fps with a `~` in front. A tooltip tells which. | `SyncedVideoPlayer` |
| F7 | Setting: show or hide the overlays (default: show). | `PlaybackControls` settings popup |
| F8 | Setting: time format, seconds (`1.234s`) or timecode (`HH:MM:SS:FF`). | `PlaybackControls` settings popup |
| F9 | Play and pause: a button and the Space key. Play at the last frame starts again from frame 0. Pause sets the frame to a whole frame. | both |
| F10 | Previous frame and next frame: buttons, the arrow keys (1 frame) and Shift with an arrow key (10 frames). A step stops play. | both |
| F11 | Jump to the start (button, Home): play continues if it was on. Jump to the end (button, End): play stops. | both |
| F12 | Loop on or off (button, L key): at the end, play starts again from frame 0. | both |
| F13 | Speed menu: 0.1, 0.25, 0.5, 1, 1.5, 2, 4 and 8 times. | `PlaybackControls` |
| F14 | Seek bar: a range input in frames, from 0 to the last frame, in steps of 1. A drag stops play and shows each frame during the drag. The release starts play again if play was on before the drag. | both |
| F15 | Text: "Frame k / N", "Rec: fps" (the recording rate from the backend), the current time and the duration. | `PlaybackControls` |
| F16 | A sync information button with a warning tooltip ("Multi-camera sync may not be frame-perfect"). The dismissal is kept in local storage. | `PlaybackControls` |
| F17 | A settings popup that holds F7 and F8. | `PlaybackControls` |
| F18 | A loading message ("loading videos, ready / total") and an empty state ("no videos loaded"). | `SyncedVideoPlayer` |
| F19 | `initialFrame`: one seek when all videos are ready. `onFrameChange`: a callback at about 5 Hz, so the host keeps the frame across page changes. | `SyncedVideoPlayer`, `PlaybackContext` |
| F20 | The keys do nothing while the focus is in a text input or a text area. | `SyncedVideoPlayer` |
| F21 | The total frame count is the smallest frame count of the videos (duration × fps). | `SyncedVideoPlayer` |

The page `PlaybackPage.tsx` adds host features around the player: a back button, the recording name,
"open folder", a camera count, the total size, a fps chip, and the column and layout settings of
`CamerasViewSettingsOverlay` [C]. They stay host features.

The player of today has no zoom, no pan, no full screen, no audio, no frame export and no camera
offset [C].

### 3.2 What 6a does with each feature

All features F1 to F21 stay, on the new engine. These change, because the new engine reads the time
of each frame from its file [SFF-783, E4]:

- F4: the frame number is the position of the frame that the tile shows (section 8.4).
- F6: each tile shows the player time of its own frame. The `~` estimate goes away, because the player
  never computes a time from an index [SFF-783].
- F9: pause keeps the take time. It does not move to a whole frame [agent 21].
- F15: "Rec: fps" comes from `nominal_rate` of the sidecars [agent 31].
- F21: the total frame count is K [SFF-754].
- F16: question Q4.

## 4. The module [Y6]

### 4.1 Folder and layout [agent 1]

The module is the folder `skellycam-ui/src/player/`:

| Path | Content |
|---|---|
| `index.ts` | The public page entry: `openTake`, the types of section 4.4, `JpegTile`. |
| `files/` | `take-files.ts` (the `TakeFiles` interface), `electron-take-files.ts` (the page client of the handler). |
| `reader/` | The take reader: `take.ts`, `manifest.ts`, `sidecar.ts`, `fit.ts`, `matroska.ts`. |
| `clock/` | `clock.ts` (the master clock), `choose.ts` (the frame choice). |
| `tile/` | `jpeg-tile.ts` (decode and draw), `label.ts` (the label text). |
| `react/` | `PlayerTile.tsx`: a React component that binds a canvas to one camera of a player. |
| `main/` | `take-scheme.ts` (the handler, main process), `bridge.ts` (the preload bridge). |
| `tests/` | `unit/`, `browser/`, `bench/`, `fixtures/`, `harness/` (section 12). |

### 4.2 The boundary rule [Y6] [agent 2]

A file of the module imports only:

- another file of the module;
- the web platform (WebCodecs `ImageDecoder`, canvas, `fetch`, `BigInt`);
- `react` (pinned by the host, 19.3.1 in skellycam-ui), and only from `react/`;
- `electron` and `node:` modules, and only from `main/` and `tests/`;
- `@playwright/test` (1.65.1), and only from `tests/`.

A file of the module does not import a file of the rest of skellycam-ui, the `@/` alias, i18next,
Redux, `react-grid-layout`, the UI components of the app or the CSS of the app. T-PLAY-32 checks the
imports.

The module uses only TypeScript syntax that a type stripper can remove (no `enum`, no `namespace`,
no parameter properties). Its imports name the `.ts` file. Then Node runs the unit tests with no build
step. `tsconfig.json` gets `allowImportingTsExtensions` [agent 5].

### 4.3 How a host mounts the module [agent 3]

The module is the engine, the tile and one small React component. The controls bar, the tile grid
and the keys stay in the host. Thus the look of today stays, and the host keeps its own components.

A host does these steps:

1. In the main process, before `app` is ready: call `registerTakeScheme()` of `main/take-scheme.ts`.
   After `app` is ready: call `installTakeHandler()`.
2. In the preload script: call `exposeTakeBridge(contextBridge, ipcRenderer)` of `main/bridge.ts`.
3. In the page: `const files = await electronTakeFiles(folderPath)`, then
   `const player = await openTake(files)`.
4. Mount one `PlayerTile` (or one `JpegTile` on a canvas) for each camera of `player.state.cameras`.
5. Drive the commands of section 4.4 from the host controls. Read the state and the events.
6. Call `player.close()` when the host leaves the take.

In skellycam-ui, the new host view is `src/components/playback/CanvasTakePlayer.tsx`. It uses the grid
of today, `PlaybackControls.tsx` of today and the keys of today. The grid code and the key code move
out of `SyncedVideoPlayer.tsx` into two host parts that both players use, so that one copy exists
[agent 32].

The freemocap UI takes the module as a copy of the folder `skellycam-ui/src/player/`. It does the six
steps above, with its own grid and controls. A package publication is not part of 6a.

### 4.4 The public interface [agent 4]

The names below are the names that the tests use. The types are TypeScript.

```ts
openTake(files: TakeFiles): Promise<TakePlayer>

interface TakePlayer {
  readonly state: PlayerState;            // a new object after each change
  play(): void;
  pause(): void;
  step(frames: number): void;             // +1, -1, +10, -10; stops play
  seekFrame(k: number): void;             // the seek bar; newest wins
  seekTime(t: number): void;              // take time in ns; clamped to [T_0, T_(K-1)]
  setSpeed(rate: number): void;           // a rate of F13
  setLoop(on: boolean): void;
  setTileOptions(o: { showLabel: boolean; timeFormat: 'seconds' | 'timecode' }): void;
  attachTile(cameraIndex: number, canvas: HTMLCanvasElement): () => void;   // returns detach
  on(event: 'state' | 'frame' | 'error', listener: (e: PlayerEvent) => void): () => void;
  close(): Promise<void>;
}

interface PlayerState {
  playing: boolean; speed: number; loop: boolean;
  frame: number;                          // k*
  frameCount: number;                     // K
  time: number;                           // t
  firstTime: number; lastTime: number;    // T_0 and T_(K-1)
  nominalFps: number;                     // section 8.4
  take: { state: 'complete' | 'incomplete'; manifest: 'present' | 'missing' | 'invalid';
          unfinished: boolean; warnings: string[] };
  cameras: CameraState[];                 // in order of group_position, then file name [SFF-890]
}

interface CameraState {
  label: string;                          // camera_label
  name: string;                           // the path of the camera file
  state: 'finished' | 'repaired' | 'unfinished' | 'damaged' | 'invalid' | 'unsupported_version';
  reason: string | null;                  // a reason code of SFF-887
  rows: number | null;                    // usable rows [SFF-885]
  tornBytes: number | null;               // [SFF-791]
  fit: boolean | null;                    // [SFF-885]
  warnings: string[];                     // file warnings [SFF-887]
  rotation: 0 | 90 | 180 | 270;           // display_rotation
  lostAt: number | null;                  // section 6.7
  shown: { position: number; mark: TileMark | null } | null;
}

type TileMark = 'no_frame' | 'camera_lost' | 'unfinished' | 'read_error';
```

Events [agent 30]:

- `state`: after each command, and at most 5 times per second during play.
- `frame`: when k* changes, at most 5 times per second during play, and at once after a step, a seek or
  a pause. The host uses it for F19.
- `error`: a read error or a file that becomes `invalid` during play (sections 5.6 and 6.11).

## 5. File access [Y2]

### 5.1 The page-side interface

```ts
interface TakeFiles {
  readonly folderName: string;                          // for display only
  readonly entries: { path: string; size: number }[];   // the snapshot of section 5.3
  readRange(path: string, start: number, end: number, signal?: AbortSignal): Promise<Uint8Array>;
  readWhole(path: string, maxBytes: number): Promise<Uint8Array>;
  close(): Promise<void>;
}
```

- `path` is a path of `entries`, relative to the take folder, with `/` [SFF-885].
- `readRange` gives the bytes from `start` to `end - 1`. It fails when it gets fewer bytes.
- `readWhole` fails when the file has more than `maxBytes` bytes.
- The reader and the clock know only this interface. Thus a server path (section 5.8) and the Node
  test implementation (section 12.2) need no change of the player [Y2].

### 5.2 The handler in the Electron main process [agent 6]

- The scheme is `skellycam-take`. `registerTakeScheme()` registers it as privileged with `standard`,
  `secure`, `supportFetchAPI`, `stream` and `corsEnabled`, as the measured harness did [M `RT` §2].
  The handler uses `protocol.handle` on the default session [M `RT` §1, §4].
- A URL is `skellycam-take://<token>/<path>`. `<token>` is a random value of 128 bits that the main
  process makes for each open. `<path>` is the relative path, percent-encoded.
- The page client `electronTakeFiles` calls `fetch` with a `Range` header and `cache: 'no-store'`.
- The handler reads with positional reads (`FileHandle.read`) on the main-process event loop. It does
  no synchronous file call while it serves a request.

Why this transport: `protocol.handle` with its own range handler served 16 cameras × 60 fps ×
150 kB with 0 dropped ticks (median of 5, Electron 35.7.5 and 45.2.3). The bare FastAPI route was
about 4 % short, and 25 % short behind the logging middleware of skellycam [M `RT` §5, Y2].

### 5.3 Open and close [agent 7] [agent 12] [agent 40]

1. The page calls the bridge: `open(folderPath)`. The host gives the path, for example the path of a
   recording that the recording browser lists.
2. The main process takes the real path of the folder (`fs.realpath`). It refuses a path that is not a
   directory.
3. It lists the root of the folder and the media folder `synchronized_videos/` only [SFF-721]. It
   keeps each regular file. It leaves out each symbolic link, each junction and each other special
   file (by `lstat`). It does not follow a media folder that is a link.
4. It stores, for each kept file: the relative path, the size, the device and the inode (or file ID).
   This list is the snapshot. It also is the allow-list of the token.
5. It returns `{ token, folderName, entries }`. `entries` holds the relative paths and the sizes only.
   No absolute path goes to the page.
6. `close(token)` closes each cached file handle and deletes the token. A request with a deleted token
   gets 404.

### 5.4 The limit to the opened take folder [Y2] [agent 7] [agent 8]

- The handler decodes `<path>` and compares it, as a string, with the relative paths of the
  allow-list of the token. It serves only an exact match. Thus `..`, an encoded `..`, an absolute
  path, a `\` and a path in another subfolder all get 404. The handler never joins a path from the URL
  onto the folder path.
- At the first read of a file, the handler opens it, then compares `fstat` with the device and inode
  of the snapshot. When they differ, or when `lstat` shows a link, it refuses the file with 404 and
  does not cache a handle.
- It caches one handle for each file until `close(token)`.

### 5.5 Responses [M `RT` §6] [agent 9]

| Request | Response |
|---|---|
| GET with no `Range` | 200, `Content-Length: <size>`, `Accept-Ranges: bytes` |
| GET `bytes=a-b`, `bytes=a-`, `bytes=-n` (one range) | 206, `Content-Range: bytes s-e/<size>`, `Content-Length: e-s+1`, `Accept-Ranges: bytes`. `e` is clamped to `size - 1`. |
| `s >= size`, `bytes=-0`, a malformed range, more than one range | 416, `Content-Range: bytes */<size>` |
| HEAD | The headers of the GET, with no body |
| A path that is not in the allow-list, a deleted token | 404 |

Each response has `Content-Type: application/octet-stream`, `Cache-Control: no-store`,
`Access-Control-Allow-Origin: *` and
`Access-Control-Expose-Headers: Content-Range, Content-Length, Accept-Ranges`.

Reasons from the evidence:

- Without `Cache-Control: no-store`, Chromium failed 1 to 2 % of concurrent range reads of one URL
  with `net::ERR_CACHE_OPERATION_NOT_SUPPORTED`, in Electron 35 and 45. `no-store` removed every
  failure (0 of 2,880 per configuration) [M `RT` §3].
- A page from `http://` (the Vite dev server) needs the expose header to read `Content-Range` [M `RT`
  §3]. A page from `file://` read it without the header [M `RT` §3]. Whether a `file://` page needs
  `Access-Control-Allow-Origin` and `corsEnabled` for a custom scheme is [NV] [M `RT` §4].
- A `net.fetch('file://')` passthrough gives status 200 with no `Content-Range`, and it breaks a seek
  past the end of the file [M `RT` §4, `CC` C31, C31a]. The handler does not use it.

The page client accepts a 206 only when the start of `Content-Range` is the start that it asked for.
It accepts a 200 only when the body has exactly the length that it asked for. It treats each other
answer as a read error [M `RT` §7] [agent 10]. Thus a later transport that answers like `file://`
(200, no `Content-Range`) also works [M `CC` C31a].

### 5.6 When the take folder changes while it is open [agent 12] [agent 8] [agent 38]

- The reader uses the snapshot sizes of section 5.3. It does not use bytes that a writer appends after
  the open. A take that is still being written thus plays as it was at the open [Y5].
- A file that a program deletes, renames or replaces after the open gives 404 at its next read. The
  tile of that camera shows the mark `read_error`, and the player sends an `error` event. The other
  tiles continue (question Q3 for the mark).
- A file that a program shortens gives a short read. The page client treats it as a read error.
- The JPEG payload has no checksum in the format. A change of the bytes of a payload that keeps the
  file identity is not found, unless the decode fails.

### 5.7 What the reader reads

The reader asks for these reads only:

- the manifest: `readWhole('recording_manifest.json', 16 MiB)` [agent 11];
- each video sidecar: `readWhole(<csv>, no limit)`;
- each camera file: its head (section 6.9), the range of each frame (section 6.10) and its tail
  (section 6.9).

The reader never writes, moves, renames or creates a file [SFF-799]. `TakeFiles` has no write call.

### 5.8 The place for a server path later [Y2]

A server path is a second implementation of `TakeFiles`, for example `files/http-take-files.ts`. It
uses the same acceptance rule (section 5.5). The changes that the Python route needs are in `RT` §6:
serve the original file, accept HEAD, send `Cache-Control: no-store` and the expose header, do not list
the folder on each request, and leave the route out of the request log. The review of option B with
threads and process splits is open work, not 6a (section 14.4) [Y2].

## 6. The take reader

### 6.1 Order of the open

1. Read the manifest (6.2). If the reader cannot use it, rebuild the links by a scan (6.3).
2. Find the device pairs and group them by `take_uuid` (6.4).
3. Read each video sidecar: header, column line, rows, footer (6.5, 6.6).
4. Read the head of each camera file, and the tail of each finished or repaired file (6.9).
5. Compute the player times (6.8), the usable counts, K and T_k (7.2).
6. Give the state of section 4.4.

### 6.2 The manifest

- The reader uses `recording_manifest.json` to find the files of the take [SFF-730]. It uses
  `cameras[].video` and `cameras[].timing`. It checks that each path names a file of the snapshot and
  that the two files are a device pair (6.4) [SFF-730].
- It uses the manifest only for the take whose `take_uuid` it holds [SFF-867].
- `state` = `recording` makes the take unfinished (6.12) [Y5] [agent 24].
- It does not use `summary` for playback [SFF-729]. It does not check `sha256` [SFF-730].

### 6.3 No manifest, or a manifest that the reader cannot use

When the manifest is missing, is not valid JSON, is not a manifest of this format, or holds another
`take_uuid`, the reader rebuilds the links by a scan of the media folder [SFF-731, SFF-867]. The take
member `manifest` is `missing` only when the file does not exist, else `invalid` [SFF-867]. Each
rebuild gives the take warning `manifest_missing` [SFF-731].

The rebuild needs `<rec>` only to find the folder files [SFF-868]. The player reads no folder file in
6a, so it does not compute `<rec>` [agent 14].

### 6.4 Device pairs, takes and counts

- A device pair is a `.csv` file of the media folder whose first line is
  `# skellyfileformat=video_timing`, with the `.mkv` file of the same stem, whose first bytes are
  `1A 45 DF A3` [SFF-864]. The reader does not read an audio pair in 6a [Y1] [agent 14].
- A camera file with no sidecar is not in the take. A sidecar with no camera file is `invalid` with
  `missing_media`, and it does not count as a camera file [SFF-865].
- The reader groups the pairs by `take_uuid` [SFF-866]. When the folder holds more than one take, the
  player opens the first take in the order of `take_uuid` and gives the folder warning
  `multiple_takes` in the state [agent 13].
- A file whose name ends in `.tmp` is ignored. The folder warning `stray_tmp` goes into the state
  [SFF-790].
- Fewer camera files than `group_size`: the take is `incomplete`, with `incomplete_take`, and the other
  files open. More: `extra_files` [SFF-869]. A refused pair counts as present for these counts
  [SFF-869].
- Two camera files with one `camera_label`: `duplicate_label`, and the reader keeps both [SFF-870].
- Sidecars that disagree on a take key: `take_fact_mismatch`; the reader uses the values of the
  lowest `group_position` [SFF-871]. A refused sidecar is not in this check [SFF-871].
- The camera order is `group_position`, then the bytes of the file name [SFF-890].

### 6.5 The sidecar header and the column line

- The header lines are `# <key>=<value>` [SFF-742]. The reader needs each key of section 8 of the
  format spec. A missing key makes the file `invalid` with `missing_metadata`; a value in a wrong form
  makes it `invalid` with `bad_metadata` [SFF-748].
- Integer forms [SFF-701]; `take_uuid` [SFF-703]; `nominal_rate` with `num` and `den` from 1 to 2^20,
  else `bad_rate` [SFF-750]; `display_rotation` in {0, 90, 180, 270}, else `bad_rotation` [SFF-751];
  the label pattern, else `bad_label` [SFF-753]; a known `clock`, else `bad_metadata` [SFF-772].
- `group_position` at or above `group_size` is read normally [SFF-748].
- A `major` other than 2 makes the file `unsupported_version` [SFF-708]. A higher `minor` reads
  normally: the reader ignores unknown header keys, unknown columns and unknown flag bits [SFF-709].
- `format_prerelease` above 0 gives the file warning `prerelease`, and the file reads normally
  [SFF-891].
- The reader finds each column by its name. A missing column of section 8 makes the file `invalid`
  with `missing_metadata`. A last column that is not `crc32` makes it `invalid` with `bad_metadata`
  [SFF-743] [agent 15] [P7].

### 6.6 Rows, the row CRC and the footer

- The reader uses a row only when it ends with LF, has one field for each column and has a correct
  CRC [SFF-744, SFF-746].
- A last line with no LF is torn. It ends the read, and its bytes count in `torn_bytes` [SFF-746,
  SFF-791].
- A complete row with a wrong CRC makes the file `damaged` with `crc_mismatch`. The read stops at that
  row. The rows before it are usable [SFF-746]. Thus the take plays only to the smallest usable count
  [SFF-754]. The tile of the damaged camera gets the mark of question Q3.
- Each integer of a row has the form of SFF-701, and each integer that is not a time is from 0 to
  2^53 − 1, else the file is `invalid` with `bad_metadata` [SFF-701].
- The reader uses the row index as the position. A `frame` value that is not the position makes the
  file `invalid` with `bad_metadata` [agent 15] [P6].
- The reader reads no data row after the first footer line [SFF-746]. A file whose last line is
  `# end` is `finished`. A file with a `# repair` line and `# end` as its last line is `repaired`. Each
  other file is `unfinished` [SFF-747, SFF-795]. When two states apply, the reader gives the first of
  SFF-886.
- The flags: bit 0 `gap`, bit 1 `filled`, bit 2 `encode_skip`, bit 3 `repeat` [SFF-756]. A usable row
  with `gap` gives the file warning `gap`; with `encode_skip`, the file warning `encode_skip`
  [SFF-887]. The player shows these frames as all other frames.

### 6.7 No-image rows and a lost camera [Y4] [E9]

By the recorder decisions R2 and R3, a damaged frame and a dead camera give rows with no image, so
that each camera has equal rows [E9]. The format draft has no field for such a row: each row is a
frame of the camera file [SFF-754, SFF-740, SFF-759]. Section 13 proposes the field (P1, P2). Until
the user and the recorder spec fix it, this spec reads a no-image row as P1 gives it:

- a row with the flag `no_image` (bit 4) and empty `byte_offset` and `byte_size` is a no-image row;
- a no-image row has no block. The row-to-block rule of SFF-740 counts only the rows with an image;
- a no-image row is usable when the row is usable [SFF-746]. It needs no complete block. It still
  needs a player time (section 6.8).

A lost camera [Y4] [P2]:

- The flag `camera_lost` (bit 5) is set, with `no_image`, on each row from the loss to the end.
- `lostAt` of the camera is the position of the first row with `camera_lost` [agent 23].
- From that row to the end, the tile shows "camera lost at frame N", with N = `lostAt` [Y4].

The representation, the time of such a row and the lost mark are open points for the recorder spec
(section 14.2).

### 6.8 The time axis [SFF-781] [E8]

- The player time of each row of a camera file is its fitted time, when the sidecar is finished or
  repaired and has a fit that holds each position. Else it is `arrival_ns` for every row of the file,
  and the file gets the warning `missing_fit` [SFF-781]. The reader never mixes the two in one file
  [SFF-781].
- The reader uses fit lines only of a finished or repaired sidecar [SFF-747]. A sidecar of an
  interrupted repair is `unfinished`, with `fit` false and `missing_fit`, also with fit lines
  [SFF-798].
- A fit whose segments do not hold each position, in order, with no gap and no overlap, is not
  usable. The file then uses `arrival_ns`, with `missing_fit` [SFF-781] [agent 15].
- The fitted time of position p is `t0_ns` + ⌊d × `period_ps` / 1000⌋. d is the difference of the
  source frame numbers of p and `pos_first` when both rows have one, else p − `pos_first`
  [SFF-777]. The reader computes it with `BigInt` [SFF-777]. It does not read `fitter_params` and does
  not change its behaviour for `fitter` [SFF-780].
- A file whose `clock` is `synthetic` gets no `missing_fit` [SFF-863].
- The reader parses each time as a `BigInt`. A time or a fitted time with a magnitude of 2^53 or more
  makes the file `invalid` with `bad_time` [SFF-706, SFF-887]. Each other time becomes a JavaScript
  number. The times of the CSV rows are already relative to the take start, so each such number is an
  exact integer [SFF-706] [agent 18].
- The player time of a file never decreases [SFF-782]. A decrease makes the file `invalid` with
  `bad_metadata` [agent 15] [P6].
- Each camera file has its own time base by SFF-781. One camera can use fitted times and another
  `arrival_ns` (section 14.3).

### 6.9 The camera file head and tail [agent 16] [agent 17]

- Head: the reader reads the first 64 KiB, and more in steps of 64 KiB when the Tracks element ends
  later. It checks the EBML header, DocType `matroska`, one Segment and the Tracks element. A camera
  file that does not have exactly one video track with CodecID `V_MJPEG` is `invalid` with
  `bad_metadata` [P5]. It notes the track number and the start of the first Cluster.
- It ignores each Matroska element that the format spec does not name [SFF-709].
- Tail, for a finished or repaired file: the reader reads from the end of the payload of the last row
  with an image to the end of the snapshot, in reads of 1 MiB. It walks the elements. When it finds a
  SimpleBlock, the rows and the blocks differ, and the file is `invalid` with `bad_metadata`
  [SFF-759]. A repaired file has no normal end and passes [SFF-794].
- The other half of SFF-759 (a block in the middle that has no row) is found when the frame is read
  (section 6.10). The reader does not walk the whole file at the open. Section 13 proposes the text
  that allows this order (P4). Section 14.3 states the cost.

### 6.10 Reading a frame: trust the CSV, check the block header [SFF-739] [SFF-757] [agent 17]

- The reader takes the byte range of a frame from its row: `byte_offset` and `byte_size` [SFF-757,
  SFF-740, E1].
- It reads one range from the end of the payload of the previous row with an image to the end of the
  payload of this row. For the first row with an image, the range starts at the first Cluster.
- It walks the elements of the range forward. It enters a Cluster (known or unknown size [SFF-740]),
  and it skips each other element of known size. At the SimpleBlock, it parses the track number as an
  EBML variable-size integer, then 2 bytes of timestamp, then 1 byte of flags [SFF-739]. It assumes no
  fixed header length [SFF-739].
- The block is correct when: the track number is the video track; no lacing bit is set [SFF-733]; the
  payload starts at `byte_offset`; and the payload length is `byte_size`.
- Else the rows and the blocks differ: the file becomes `invalid` with `bad_metadata` from then on
  [SFF-759] [P4]. The tile keeps its last image with the mark `read_error`, and the player sends an
  `error` event.
- A frame is the bytes of its block payload [SFF-738]. The reader gives them to the tile unchanged.
- For a run of frames during play, the reader reads one range that holds several frames (section 9).
  The check above runs for each frame of the range.

### 6.11 An unfinished take [Y5]

- A take is unfinished when its manifest has `state` `recording`, or when one or more of its camera
  files is `unfinished` [agent 24]. The player opens it read only, plays the rows and frames that are
  complete, and shows the mark `unfinished` [Y5]. It offers no repair [Y5].
- An unfinished camera file can have no Cues and elements of unknown size [SFF-740]. The reader finds
  its frames from the byte positions of its rows [SFF-740].
- A frame of an unfinished file is usable when its row is usable and its block is complete [SFF-740].
  A block is complete when the end of its payload is not past the snapshot size [agent 12]. The reader
  uses no row with an image after the last complete block, and no block after the last usable row
  [SFF-740].
- The number of usable frames of an unfinished file counts only the usable rows that have a complete
  block, and the usable no-image rows before the first row with an incomplete block [SFF-754] [P1].
- `torn_bytes` of the pair is the bytes of a torn last line of the sidecar, plus the bytes of the
  camera file after its last complete block when the sidecar has no `# end` line [SFF-791].
- Files that a writer still writes: the reader reads the snapshot (section 5.6). It reads each
  complete record in file order, and it checks that it reached the end of the snapshot or a torn
  record [SFF-791].

### 6.12 Equal rows and the multi-camera frames

- Row k of each video sidecar is multi-camera frame k [SFF-754]. With R2 and R3, the finished camera
  files of a take have equal rows [E9, SFF-754].
- When the usable counts differ (an unfinished, damaged or refused file), the multi-camera frames are
  0 to K − 1, with K the smallest usable count of the camera files that the reader reads [SFF-754]. A
  refused file (`invalid`, `unsupported_version`) is not in K and has no frames.

### 6.13 The reader model and the reader result

The state of section 4.4 holds, for each camera file and for the take, the members of the reader
result that the player needs, with the names, states, reasons and warning codes of SFF-885 to
SFF-887. The reader does not give the full result of SFF-885 for the scope `player` (no
`folder_files`, no `links`, no `other_files`, no `legacy`, no privacy member) [agent 14]. Question Q2
asks whether the full result and the JavaScript test adapter wait for a later step.

## 7. The master clock and the frame choice

### 7.1 One clock [E1] [E4]

One clock holds the take time t for all cameras. Each tile shows, for its camera c, the frame that
the rule of section 7.3 gives for t. No tile has its own clock. The evidence: a master clock gave a
spread of 0 frames on 100 % of ticks at N = 4 and N = 8 in all 28 configurations (index-based, on
identical clips) [M `IP` F19]. One `<video>` element per camera stalled tiles at N = 8 and dropped 6 to
8 % of frames at N = 4 [M `IP` F21].

### 7.2 Multi-camera frame time and the frame number [agent 19] [agent 20]

- T_k = the largest p_c(k) over the cameras c that the reader reads. At t = T_k, each camera shows row
  k or a later row.
- The clock range is [T_0, T_(K-1)]. `seekTime` clamps to it.
- k* is the largest k with T_k ≤ t. The controls show "Frame k* / K" (F15) and the seek bar shows k*
  (F14).
- `seekFrame(k)` and `step(n)` set t = T_k, with k clamped to 0 to K − 1.
- At open, t = T_0, or T_k for the `initialFrame` k of the host (F19).

### 7.3 The frame choice: the last frame at or before t [SFF-783] [E4]

For each camera c:

- the chosen row is the largest k < K with p_c(k) ≤ t;
- when two rows have the same player time, the chosen row is the one with the higher position [P3];
- when t < p_c(0), the camera shows no frame [SFF-783];
- the player never computes a frame from its index and the frame rate [SFF-783].

The search is a binary search on integer nanoseconds. The rule is PREV of the evidence: it was exact on
every tick, camera and path (0 mismatches over 456 ticks × 4 cameras, Electron 35.7.5 and 45.2.3) [M
`GF08` §2.1]. PREV never shows a frame from after t, and it has no tie to break in floating-point
seconds [M `GF08` §2.3, §3].

The evidence also suggests a hold limit after the last frame [M `GF08` §3]. SFF-783 has none, and with
R2 and R3 a camera does not end before the others [E9]. The player has no hold limit (section 15,
item 4).

When the chosen row is a no-image row, the tile keeps the image of the last row with an image at or
before the chosen row, and shows the mark `no_frame` [Y4] [agent 23]. When no such row exists, the tile
is black with the mark. The chosen image thus depends only on t, not on the history of the tile.

### 7.4 Play, pause, end and speed [agent 21] [agent 22]

- Play: at each display refresh (`requestAnimationFrame`), t increases by the speed × the elapsed
  `performance.now()` time, in whole nanoseconds.
- Pause: t stays. The tiles do not change [agent 21].
- End: when t reaches T_(K-1), play stops at T_(K-1) (F11). With loop on, t goes to T_0 and play
  continues (F12).
- Play when k* = K − 1 starts from T_0 (F9).
- Speed: a rate of F13. At a rate above 1, the tiles can skip frames (section 9.3).

### 7.5 Seek and scrub [agent 29]

- A drag of the seek bar stops play and calls `seekFrame` for each new value (F14). The release calls
  `seekFrame` again and starts play when play was on before the drag (F14).
- The newest request wins. Each tile has at most one read and decode in flight and one pending target.
  A new target replaces the pending target. There is no queue of old targets.
- When a decode ends, the tile draws it only when no frame of a newer request is on the tile. Then it
  starts the pending target, if there is one.
- The tile thus shows frames during a drag, and it ends on the frame of the last target.

The evidence: a JPEG `ImageDecoder` scrub at 90 frames per second of drag reached the input ceiling of
the harness, about 58 shown frames per second for each tile at N = 4 and N = 8, with a lag of 2 frames
[M `IP` F23].

## 8. The tile [Y3]

### 8.1 Decode [Y3] [agent 25]

- The tile decodes with WebCodecs `ImageDecoder` (`type: 'image/jpeg'`) [Y3, E1]. It closes each
  `VideoFrame` that it does not keep, and the decoder after each image.
- In 6a, the decode runs on the page main thread, as in the evidence: the harness decoded on the page
  and drew on the page with `requestAnimationFrame` [C `scripts/chromium_sync_scrub/harness/harness.mjs`
  on branch `dom/research`, M `IP` F20]. A decode on a worker is not measured (M-PLAY-6).
- Why `ImageDecoder`: at N = 8, 1080p30, it used 1.44 cores against 2.14 for `createImageBitmap`
  (Electron 45.2.3), and it kept the scrub rate at the harness ceiling where `createImageBitmap` fell
  to 49 to 51 [M `IP` F20, F23].
- `<video>`, MSE and the WebCodecs `VideoDecoder` cannot play MJPEG: MJPEG never opened in `<video>`;
  no API accepted an MJPEG codec string [M `CC` C1 to C3, `IP` F13]. The tile does not use them.
- A JPEG with no JFIF or APP0 segment, with no DHT segment, with any marker order, or with bytes after
  the entropy-coded data must decode [SFF-738]. That `ImageDecoder` in Electron 45.3.4 decodes a JPEG
  with no DHT segment is [NV]. T-PLAY-38 checks it. If it fails, this spec changes before the code.
- The tile ignores an EXIF orientation tag [SFF-738]. It applies only `display_rotation`.

### 8.2 Draw and rotation [SFF-751] [E5] [agent 26]

- The canvas backing size is the client size of the tile × `devicePixelRatio`. It changes with the tile
  size (`ResizeObserver`).
- The tile draws on black (F3). It rotates the image clockwise by `display_rotation` [SFF-751, E5],
  then fits the rotated image into the canvas ("contain") (F3). The stored frame is in sensor
  orientation [SFF-735].
- The tile draws with a 2D context and `drawImage(VideoFrame)` with a canvas transform.

### 8.3 Marks [Y4] [Y5]

| Mark | When | Text |
|---|---|---|
| `no_frame` | The chosen row is a no-image row, and the camera is not lost [Y4]. | "no frame" |
| `camera_lost` | The chosen row is at or after `lostAt` [Y4]. | "camera lost at frame N" |
| `unfinished` | The camera file is `unfinished` [Y5] [agent 24]. | "unfinished" |
| `read_error` | Section 5.6 or 6.10 (question Q3). | "read error" |

The tile draws a mark over the image, clearly, in a fixed place [Y4]. With `no_frame` and
`camera_lost`, the image is the last real image [Y4]. Question Q3 asks about marks for a refused file
and a damaged file. The host gets the texts as an option of the tile, with these English defaults, so
that the host can translate them [agent 3].

### 8.4 The frame label [E6] [agent 27]

The tile draws the label in the canvas, from the fields of the frame [E6]. The take holds no overlay
[SFF-737]. The label has the three parts of today (F4 to F6):

| Part | Place | Value |
|---|---|---|
| Frame | top right | `F` and the position of the shown row, with leading zeros to the digits of K (F4) |
| Camera | bottom left | `camera_label` (F5) |
| Time | bottom right | The player time of the shown row: seconds with 3 decimals (`1.234s`), or `HH:MM:SS:FF`, with FF = ⌊fraction of the second × the nominal rate of the camera⌋ (F6, F8) |

- `setTileOptions` turns the label on or off (F7) and sets the time format (F8).
- The label has a fixed size in CSS pixels.
- The tile keeps the text of its last label, so that a test can read it [agent 26].
- `nominalFps` of the state, for "Rec: fps", is the nominal rate of the camera with the lowest
  `group_position`, rounded to 3 decimals as SFF-728 rounds `nominal_fps` [agent 31].

### 8.5 One place [Y3]

Rotation, the label and the marks are in `tile/` only. The player calls the tile. The live preview of
phase 4 calls the same tile [Y3].

### 8.6 The boundary for the live preview of phase 4 [Y3]

`JpegTile` has this interface. Phase 4 uses it and does not design more here:

```ts
class JpegTile {
  constructor(canvas: HTMLCanvasElement, texts?: Partial<MarkTexts>);
  decode(jpeg: Uint8Array): Promise<VideoFrame>;                 // ImageDecoder
  draw(frame: VideoFrame | null, info: TileInfo): void;          // takes ownership of frame
  show(jpeg: Uint8Array, info: TileInfo): Promise<void>;         // decode + draw; newest wins
  setOptions(o: { showLabel: boolean; timeFormat: 'seconds' | 'timecode' }): void;
  close(): void;
}
interface TileInfo {
  rotationCwDeg: 0 | 90 | 180 | 270;      // display_rotation, or rotation_cw_deg of a ring frame
  label: { frame: string; camera: string; time: string } | null;
  mark: { kind: TileMark; frame?: number } | null;
}
```

- The live caller gives the ring JPEG untouched and `rotation_cw_deg` of the frame. It has the same
  meaning as `display_rotation` ([`frame-ring.md`](frame-ring.md) section 3).
- The live caller never gives a frame with an error flag of the ring ([`frame-ring.md`](frame-ring.md)
  section 4). The ring gives no payload for such a frame.
- The live view of today decodes with `createImageBitmap` on a worker and draws with a bitmap
  renderer on an offscreen canvas [C `frame-decode.worker.ts`, `offscreen-renderer.worker.ts`]. `PLAN`
  §5 states the same. By Y3, phase 4 changes it to this tile. Section 15, item 9 lists this.

## 9. Prefetch, back-pressure and memory [agent 28] [agent 29]

### 9.1 Prefetch during play

- Each camera has a queue of decoded frames ahead of t. The queue holds at most
  min(8, max(2, ⌊64 / N⌋)) frames, with N the number of cameras. The evidence used 8 decoded frames
  ahead for each camera at N = 4 and N = 8 [C `harness.mjs` `JpegPlayer`, M `IP` F19, F20].
- Each camera has at most one range read in flight. One read holds the frames that the queue needs,
  up to 4 MiB.
- After a seek, the queue is emptied, and each frame in it is closed.

### 9.2 Back-pressure

- A tile never draws a frame of an older request after a frame of a newer request (section 7.5).
- During play, at each display refresh, the tile draws the frame of the queue with the largest position
  at or before its chosen row, and closes the older frames of the queue. It never draws a frame older
  than the frame on the tile, except after a seek back.

### 9.3 Speed above 1

At a rate above 1, the prefetch reads only the rows that the clock chooses at the next display
refreshes, at the current rate. It skips the rows between them. The cost at 8 times is not measured
(M-PLAY-7).

### 9.4 Memory limits

- Decoded frames held at one time: at most the queue limit + 1 (on the tile) + 1 (in decode) for each
  camera, so at most 64 + 2N for the take.
- Each `VideoFrame` is closed when it leaves the queue or the tile. `close()` of the player closes each
  frame, each decoder and each file.
- The evidence: a working set of 987 MB at N = 8, 1080p30, with `ImageDecoder` and 8 frames ahead
  (Electron 45.2.3) [M `IP` F20].

## 10. Host integration in skellycam-ui

- `CanvasTakePlayer.tsx` (section 4.3) uses the grid of today (F1 to F3), `PlaybackControls.tsx` of
  today (F7 to F17) and the keys of today (F9 to F12, F20) [agent 32].
- The loading message (F18) counts the cameras whose first frame is drawn.
- The host gives `initialFrame` and gets `frame` events for F19.
- How the playback page chooses between the new player and the player of today in 6a is question Q1.
  The recording browser and its backend route do not change in 6a.

## 11. Performance

### 11.1 Versions that the evidence measured

- Electron 35.7.5 with Chromium 134.0.6998.205, Electron 45.2.3 with Chromium 156.0.8078.80, and Chrome
  156 (functional runs only) [M `IP` header, `RT` header].
- One Windows 11 machine: Intel i7-14700K, NVIDIA RTX 3070 (the active Chromium GPU), Intel UHD 770
  present and not used [M `IP` header].
- skellycam-ui pins Electron 45.3.4 [C `package.json`]. That the results hold on 45.3.4 is [NV]. The
  Chromium version of Electron 45.3.4 is [NV].

### 11.2 Measured

| Item | Value | Source |
|---|---|---|
| Frame-exact seek and step, JPEG by range read | 800/800 seeks and 976/976 steps for each decode path and browser | [M `IP` F4] |
| Camera JPEGs out of an MKV by range read | 450 of 450 byte-identical, 720p, 300 frames, decode with both paths (untimed) | [M `IP` F14] |
| Frame choice by time, 4 cameras with different times, gaps, late start, early end | 0 mismatches, 456 ticks × 4 cameras, PREV and NEAREST, Electron 35 and 45, 720p, fixed tick list | [M `GF08` §2.1] |
| Sync spread with a master clock, N = 4 and N = 8, 1080p30 | 0 frames on 100 % of ticks (index-based, identical clips) | [M `IP` F19] |
| Seek latency p50, JPEG range read + `ImageDecoder`, 1080p | 4.6 ms (Electron 45.2.3), 4.4 ms (Electron 35.7.5) | [M `IP` F18] |
| CPU, N = 8, 1080p30 sync, `ImageDecoder` | 1.44 cores (45.2.3), 1.45 cores (35.7.5), Electron processes only | [M `IP` F20] |
| Working set, same case | 987 MB (45.2.3) | [M `IP` F20] |
| Scrub, 90 frames/s of drag, `ImageDecoder` | 58.0 to 58.75 shown/s for each tile at N = 4 and 8 (the input ceiling of the harness), lag 2 frames; 3.05 to 3.20 cores at N = 8 | [M `IP` F23] |
| Transport, `protocol.handle`, 16 × 60 fps × 150 kB, 4 s | 960 reads/s, 0 dropped ticks (median of 5) in both Electrons; 113 to 116 % of one core for all processes; the handler 75 to 78 % of one core in the main process | [M `RT` §5] |
| Small reads (1.5 and 4 kB), concurrency 1 | p50 0.3 to 0.5 ms (`protocol.handle`) | [M `RT` §5] |

Limits of these numbers: the timed JPEG clips were `mjpeg_qsv` re-encodes of about 207 kB, not camera
bytes; the bench read them from a local HTTP server in the Electron main process, not through
`protocol.handle`; one run for each configuration; a warm page cache [M `IP` §3.3, §5]. The JPEG timing
on camera bytes is [NV] [M `IP` §6].

### 11.3 Targets of 6a (to verify with the benchmarks) [agent 37]

| Case | Target | Benchmark |
|---|---|---|
| N = 8, 1080p30, speed 1, 60 s | After 1 s, in 99 % of display refreshes or more, each tile shows its chosen frame; Electron CPU at most 2.0 cores; working set at most 1.5 GB | T-PLAY-59 |
| N = 4, 1080p30 | Seek: all tiles drawn, p50 at most 10 ms, p95 at most 33 ms | T-PLAY-60 |
| N = 8, 1080p30, drag at 90 frames/s, input each 16 ms | At least 50 shown frames/s for each tile | T-PLAY-61 |
| Transport, 16 × 60 fps × 150 kB, 60 s | At most 0.5 % dropped ticks | T-PLAY-58 |
| Main process during the transport case | IPC round trip p95 at most 50 ms | T-PLAY-62 |

### 11.4 Not measured

720p60; 16 cameras of playback (the transport only was measured at 16); the cameras' own JPEG bytes
(timed); Linux and macOS; Electron 45.3.4; a decode on a worker; speed above 1; takes longer than
600 frames; a cold disk; a low-end laptop; a file that a writer still writes; real clock alignment
across cameras (GF08 aligned the clocks by construction) [M `GF08` §3, `IP` §6, `RT` §5].

## 12. Tests

### 12.1 Kinds and runners [agent 35]

- **unit**: the reader, the clock, the frame choice and the scheduling. No browser. Node with
  `node --test --experimental-strip-types`, as the existing test `tests/graceful-python-shutdown.test.mjs`
  [C `package.json` `test:recording-shutdown`]. The decoder and the time source are test doubles.
- **component**: the tile and the player in Electron 45.3.4, with the real `ImageDecoder` and canvas.
  `@playwright/test` 1.65.1 starts a test Electron app (`tests/harness/`) with `_electron.launch`. A test
  Vite config builds the harness page and the harness main process. The tests of the host view are in
  `skellycam-ui/src/components/playback/tests/` and use the same runner.
- **electron**: the handler, in the same test Electron app, with real files.
- **benchmark**: timed runs on the Windows test machine, started by hand. They record results and
  compare them with the targets of 11.3. They do not run in CI.

Today: the UI has one Node test (`test:recording-shutdown`) and one Playwright example
(`e2e/example.spec.ts`). No UI test runs in CI [C `.github/workflows/`].

npm scripts [agent 35]: `test:player:unit` and `test:player:browser`. No new npm package is needed.

### 12.2 Fixtures [Y7] [agent 33]

- The fixture builder is TypeScript in `skellycam-ui/src/player/tests/fixtures/`. It runs in Node. Each
  test builds its takes at run time in a new temporary folder and deletes it after the test. No take,
  JPEG or MKV goes into the repository.
- It writes the files from the format spec: the MKV of section 6 (EBML header, Segment, Info, Tracks
  with one `V_MJPEG` track, Clusters, one JPEG per SimpleBlock), the sidecar of sections 7 and 8 with
  the row CRC (`zlib.crc32` of Node), fit lines and the `# end` line, and the manifest of section 5. It
  does not use the recorder code, so the tests check the recorder and the player against the spec, not
  against each other.
- Synthetic JPEGs: a small baseline JPEG encoder that codes each 8 × 8 block as one flat colour (DC
  coefficients only, 4:4:4). A row of blocks is a barcode of the camera index and the position. Four
  quadrants of four colours show the rotation. The encoder can leave out the DHT segment and the APP0
  segment, add an EXIF orientation tag, and add bytes after the EOI.
- A Node implementation of `TakeFiles` (`tests/fixtures/node-take-files.ts`) reads the temporary
  folder for the unit tests.
- The benchmarks make larger JPEGs at run time with the JPEG encoder of Chromium
  (`OffscreenCanvas.convertToBlob`, quality 0.9) from a noise pattern with a barcode, about 190 kB at
  1080p, near the 192,382 B mean of the C922 at 1080p [M `IP` §3.3] [agent 34].

The takes that the builder makes:

| Fixture | Content |
|---|---|
| `normal` | 4 cameras × 120 rows at 30/1, finished, fit lines, a manifest, rotation 0 |
| `offsets` | 4 cameras with different arrival offsets (0, +7.65 ms, −3 ms, +19.9 ms) and jitter, and two rows 11 µs apart, after `GF08` §1.1 |
| `no_image` | `normal` with no-image rows in camera 1 at rows 10, 40 to 59 and 0 (P1) |
| `lost` | `normal` with camera 2 lost from row 70 to the end (P1, P2) |
| `unfinished` | manifest `state` `recording`; no `# end`; camera 0 with a torn last line; camera 1 with a last block cut in the MKV; camera 3 with an unknown-size Cluster |
| `no_manifest` | `normal` with no manifest; `bad_manifest_*`: not JSON, not a manifest, another `take_uuid` |
| `bad_crc` | `normal` with a wrong CRC in row 50 of camera 1 |
| `rotations` | 4 cameras with `display_rotation` 0, 90, 180 and 270 |
| `no_fit` | `normal` with no fit lines in camera 2; and a fit that does not hold each position |
| `header_*` | one changed sidecar each: leading zero, `+` sign, a `take_uuid` with dashes, row integer 2^53, rate 0/1 and 2^20 + 1, rotation 45, bad label, missing key, missing column, unknown clock, major 3, minor 1 with an unknown key, column and flag bit 7, prerelease 0 and 1, a time of 2^53 |
| `block_*` | a payload offset that is wrong by 1; an extra block in the middle; a block with a lacing bit; an extra block after the last row; a 2-byte track number and 8-byte sizes; a Void element and a Cluster start between two payloads; a codec other than `V_MJPEG` |
| `jpeg_forms` | JPEGs with no DHT, no APP0, an EXIF orientation 6, 1 KiB of bytes after the EOI |
| `pairs` | a lone MKV, a lone sidecar, a sidecar with no mark, a `.tmp` file, an audio pair, two takes |
| `counts` | fewer and more camera files than `group_size`, a duplicate label, a take key that differs |

### 12.3 Test list

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-PLAY-01 | unit | Build `normal`, then parse it back with an independent small parser in the test. | EBML header, one `V_MJPEG` track, one SimpleBlock per row at the CSV offsets; each row CRC is the zlib CRC-32 of its bytes; each JPEG starts with SOI and ends with EOI. |
| T-PLAY-02 | unit | Open `normal` through the manifest. | 4 cameras in `group_position` order; each pair from `cameras[]`; `manifest` `present`; no warning except `prerelease`. |
| T-PLAY-03 | unit | Open `no_manifest`. | The same 4 cameras by a scan; `manifest` `missing`; take warning `manifest_missing`. |
| T-PLAY-04 | unit | Open the three `bad_manifest_*` takes. | `manifest` `invalid`; a rebuild by scan; `manifest_missing`. |
| T-PLAY-05 | unit | `counts`: a manifest path to a deleted sidecar; 3 of 4 files; 5 files for `group_size` 4; one refused pair of 4. | `incomplete` with `incomplete_take`; `extra_files`; the refused pair counts as present, has no tile frames and is not in K. |
| T-PLAY-06 | unit | Open `pairs` with a recording spy on `TakeFiles`. | The lone MKV is not in the take; the lone sidecar is `invalid` with `missing_media` and not counted; a sidecar with no mark is ignored; no read of the `.m4a` file. |
| T-PLAY-07 | unit | Open `pairs` with two takes and a `.tmp` file. | The first take in `take_uuid` order opens; warnings `multiple_takes` and `stray_tmp`; the `.tmp` file is not read. |
| T-PLAY-08 | unit | Open each `header_*` form fixture. | `invalid` with the reason of 6.5 for each: `bad_metadata`, `bad_rate`, `bad_rotation`, `bad_label`, `missing_metadata`; the other cameras open. |
| T-PLAY-09 | unit | Open the version fixtures, and `normal` with one row flagged `gap` and one flagged `encode_skip`. | Major 3: `unsupported_version`, reason null; minor 1: reads with the unknown key, column and flag bit; prerelease 1: warning `prerelease`; prerelease 0: no warning; the flagged rows give the file warnings `gap` and `encode_skip`, and their frames are chosen as other frames. |
| T-PLAY-10 | unit | Times of 2^53 − 1 and of 2^53; `take_start_host_ns` above 2^53. | 2^53 − 1 reads exactly; 2^53 gives `invalid` with `bad_time`; the large take start parses as `BigInt` with no loss. |
| T-PLAY-11 | unit | Open `bad_crc`. | Camera 1 `damaged`, `crc_mismatch`, `rows` 50; K = 50; the other cameras have 120 usable rows. |
| T-PLAY-12 | unit | `unfinished` camera 0 (torn last line of 23 bytes). | The torn row is not used; `torn_bytes` includes the 23 bytes; state `unfinished`. |
| T-PLAY-13 | unit | Footer cases: rows after `# end`; a `# repair` line with `# end` last; a `# repair` line with no `# end`. | No row after the first footer line; `repaired`; `unfinished`. |
| T-PLAY-14 | unit | `normal` with two fit segments, a source frame gap and a `period_ps` with a remainder. | Each fitted time equals an independent `BigInt` computation of SFF-777; a change of `fitter` changes nothing. |
| T-PLAY-15 | unit | `no_fit` and the `unfinished` takes; a sidecar with `clock` `synthetic` and no fit. | Arrival times for the whole file, `missing_fit`, `fit` false; with fit lines in an unfinished file still arrival times; `synthetic`: no `missing_fit`. |
| T-PLAY-16 | unit | A sidecar with a `frame` value that is not the position; a sidecar whose player time decreases at one row. | Both `invalid` with `bad_metadata` (P6). |
| T-PLAY-17 | unit | Open `no_image`; choose frames at the time of each no-image row. | The rows are usable and counted; they map to no block; the choice gives the row and the mark `no_frame`; the image row is the last row with an image before it; for row 0, no image. |
| T-PLAY-18 | unit | Open `lost`. | Camera 2 `lostAt` = 70; each choice at or after T_70 gives `camera_lost` with N = 70 and the image of row 69; K = 120. |
| T-PLAY-19 | unit | `unfinished` with usable counts of 120, 97, 120 and 110. | K = 97; T_k and k* only to 96. |
| T-PLAY-20 | unit | Open `unfinished`. | `take.unfinished` true; camera 1 uses no row after its last complete block; `torn_bytes` adds the bytes after that block; no file is written. |
| T-PLAY-21 | unit | Open `normal` with a `TakeFiles` whose snapshot sizes are smaller than the files: half of the last block and 2 rows are past the snapshot. | The rows and the block past the snapshot are not used; the file is read as unfinished. |
| T-PLAY-22 | unit | Read each frame of `block_*` with a 2-byte track number and 8-byte sizes. | Each payload equals the JPEG that the builder wrote; no fixed header length is used. |
| T-PLAY-23 | unit | Read the frames around a Void element, a Cluster start and an unknown-size Cluster. | Each payload is correct. |
| T-PLAY-24 | unit | `block_*`: a wrong offset; an extra block in the middle; a laced block; an extra block after the last row; a Cues tail. | Wrong offset, middle block and laced block: `invalid` with `bad_metadata` at the read of that frame, and an `error` event; extra block at the end: `invalid` at the open; Cues tail: passes. |
| T-PLAY-25 | unit | Camera file heads: no EBML magic; a codec other than `V_MJPEG`; two tracks. | No EBML magic: not a pair; the two others: `invalid` with `bad_metadata` (P5). |
| T-PLAY-26 | unit | Frame choice on fixed lists: each exact time, 1 ns before and after, equal times, before p(0), after the last. | The largest position with p ≤ t; equal times give the higher position; before p(0) no frame; no use of index × rate (a list with irregular times proves it). |
| T-PLAY-27 | unit | T_k, k* and `step(±1, ±10)` on `offsets`, also at both ends. | T_k = max over cameras of p_c(k); at t = T_k each camera shows row k or later; k* is the largest k with T_k ≤ t; steps clamp to 0 and K − 1. |
| T-PLAY-28 | unit | The clock with a scripted time source: play at each rate of F13, end with loop off and on, play at the last frame, pause. | t advances by rate × elapsed time; stop at T_(K-1); loop to T_0; play at the end starts from T_0; pause keeps t. |
| T-PLAY-29 | unit | 100 seeks within 200 ms to one tile, with a test decoder of random delay 1 to 30 ms. | At most one decode in flight; after the last decode, the tile shows the last target; no draw of an older request after a newer draw. |
| T-PLAY-30 | unit | Play at rates 1 and 8 with a slow test decoder. | The drawn position never goes down during play; each frame that is not drawn is closed. |
| T-PLAY-31 | unit | `offsets`: 456 fixed ticks in a shuffled order (exact times, midpoints, ±1 ns, ±1 ms, inside no-image runs, before T_0, at the end), after `GF08` §1.4. | Each choice equals a brute-force reference written independently in the test. |
| T-PLAY-32 | unit | Scan the imports of each file of `src/player/` and each import of a module file from the rest of `src/`. | Only the imports of section 4.2; the rest of the UI imports only `index.ts`, `react/PlayerTile.tsx`, `main/take-scheme.ts` and `main/bridge.ts`. |
| T-PLAY-33 | unit | `counts`: a duplicate label; a take key that differs in camera 2. | `duplicate_label` and both kept; `take_fact_mismatch` and the values of `group_position` 0. |
| T-PLAY-34 | unit | Label text: K = 9, 120 and 12,000; times 0.0334 s and 3,725.5 s; rates 30/1 and 30000/1001; both formats. | `F` with 1, 3 and 5 digits; `0.033s` and `3725.500s`; timecode `00:00:00:01` and `01:02:05:15` (14 for 30000/1001). |
| T-PLAY-35 | unit | N = 4 and N = 16 with a counting test decoder; play, seek and close. | Open frames never exceed min(8, max(2, ⌊64/N⌋)) + 2 for each camera; 0 open frames after `close()`. |
| T-PLAY-36 | component | A bare page with only `JpegTile` (no host code): show a barcode JPEG. | The canvas pixels of each block equal the block colour within ±8 levels. |
| T-PLAY-37 | component | `rotations`: draw each camera. | The quadrant colours are at the upright corners for 0, 90, 180 and 270. |
| T-PLAY-38 | component | `jpeg_forms`: no DHT, no APP0, bytes after the EOI. | Each decodes; pixels as T-PLAY-36. |
| T-PLAY-39 | component | `jpeg_forms`: EXIF orientation 6 with `display_rotation` 0. | Drawn as stored, not rotated. |
| T-PLAY-40 | component | Label on and off; seconds and timecode. | The kept label text changes as T-PLAY-34; with the label off, no label text and the label regions equal the image pixels. |
| T-PLAY-41 | component | `no_image`: seek into the run of rows 40 to 59, then to row 0. | The barcode shows row 39 with the mark `no_frame`; at row 0, a black tile with the mark. |
| T-PLAY-42 | component | `lost`: seek to rows 69, 70 and 119. | Row 69 normal; rows 70 and 119 show the image of row 69 with "camera lost at frame 70". |
| T-PLAY-43 | component | `unfinished`: open and play to the end. | The `unfinished` mark on the tiles of the unfinished files; play ends at K − 1. |
| T-PLAY-44 | component | `offsets`: the 456 ticks of T-PLAY-31 through `seekTime`, waiting for each draw. | The barcode of each tile equals the reference for each tick. |
| T-PLAY-45 | component | `normal`: play 3 s at 1, pause, play to the end, loop on for one more pass. | After the pause, each barcode equals the choice for `state.time`; the end stops at K − 1; loop starts again from T_0. |
| T-PLAY-46 | component | Host view `CanvasTakePlayer` with today's `PlaybackControls`: each button, each key of F9 to F12, Shift steps, a key in a text input, each speed, a seek drag and release while playing. | Each command changes the state as F9 to F17 and F20 give; the drag shows frames and the release resumes play. |
| T-PLAY-47 | component | Host view grid: 1, 4 and 9 cameras; manual columns 2; reset; drag tile 1 onto tile 3. | Auto tiling as today; 2 columns; reset restores the layout; tiles 1 and 3 swap. |
| T-PLAY-48 | component | Host view: `initialFrame` 50; play 2 s; the loading message; an empty camera list. | The first draw is at frame 50; `frame` events at most 5 per second; the loading count; the empty state. |
| T-PLAY-49 | component | Delete the file of camera 3 during play. | Camera 3 keeps its last image (with the mark `read_error` if the answer to Q3 is yes); an `error` event; the other 3 tiles keep playing. |
| T-PLAY-50 | component | Only if the user answers Q3 with yes: a refused camera file and `bad_crc`. | The marks of Q3 on those tiles. |
| T-PLAY-51 | electron | The range matrix of 5.5 on a 1 MiB file: no range, `a-b`, `a-`, `-n`, past the end, `-0`, malformed, two ranges, HEAD. | Status, bytes and each header as 5.5. |
| T-PLAY-52 | electron | 640 reads of 150 kB at concurrency 16, default session cache. | 0 failed reads [M `RT` §8 item 2]. |
| T-PLAY-53 | electron | Requests for `..`, `%2e%2e`, an absolute path, a `\` path, a file in `annotated_videos/`, a name not in the list, a link to a file outside (a junction to a folder on Windows; a file link on Linux and macOS), a closed token. | Each gets 404; no byte of an outside file reaches the page. |
| T-PLAY-54 | electron | During an open take: append 1 MiB to a camera file; replace a sidecar with a new file of the same name; delete a camera file. | The append: reads within the snapshot unchanged; the replaced and the deleted files: 404 and a read error in the page. |
| T-PLAY-55 | electron | A test variant of the handler answers 200 with the exact length, 200 with the whole file, and 206 with a wrong `Content-Range` start. | The page client accepts only the first; the two others are read errors. |
| T-PLAY-56 | electron | A sparse file of 5 GiB; read 3 ranges past 4 GiB. | The bytes equal the bytes that the test wrote at those offsets. |
| T-PLAY-57 | electron | Open `normal`, play it to the end, seek 50 times, close. | Each file of the folder has the same bytes and modification time as before [SFF-799]. |
| T-PLAY-58 | benchmark | 16 readers × 60 fps × 150 kB for 60 s through the handler; CPU of the main, renderer and GPU processes. | Target 11.3; results recorded [M `RT` §8 item 3]. |
| T-PLAY-59 | benchmark | Play N = 4 and N = 8, 1080p30, 60 s, Chromium JPEGs of about 190 kB; read the barcode of each tile at each refresh. | Target 11.3; results recorded. |
| T-PLAY-60 | benchmark | 200 seeks at N = 1, 4 and 8. | Target 11.3; p50, p95 and maximum recorded. |
| T-PLAY-61 | benchmark | Scrub at 90 frames/s for 8 s at N = 4 and 8. | Target 11.3; shown/s, lag and CPU recorded. |
| T-PLAY-62 | benchmark | IPC round trips and window events of the host while T-PLAY-58 runs. | Target 11.3 [M `RT` §8 item 4]. |
| T-PLAY-63 | benchmark | Cases that nobody measured: 720p60 at N = 4; 720p30 at N = 16; speed 8 at N = 4, 1080p30. | No target; results recorded for the user. |

### 12.4 Decisions and reader rules to tests

| Decision or rule | Tests |
|---|---|
| Y1 | No test for the step order. Video only: T-PLAY-06 (no audio read). |
| Y2 | T-PLAY-51 to T-PLAY-56, T-PLAY-58, T-PLAY-62; the interface: T-PLAY-02 (Node `TakeFiles`) and T-PLAY-44 (Electron `TakeFiles`) run the same reader. |
| Y3 | T-PLAY-36 to T-PLAY-40 |
| Y4 | T-PLAY-17, T-PLAY-18, T-PLAY-41, T-PLAY-42 |
| Y5 | T-PLAY-20, T-PLAY-21, T-PLAY-43 |
| Y6 | T-PLAY-32; T-PLAY-36 mounts the tile in a page with no host code |
| Y7 | T-PLAY-01 (the builder); the parity of 12.5 and the CI of 12.6 |
| E1 | T-PLAY-22, T-PLAY-36, T-PLAY-44, T-PLAY-59 |
| E2 | No test in 6a: the old path does not change (question Q1). |
| E3 | No test: the reader is in the module (T-PLAY-32). |
| E4, SFF-783 | T-PLAY-26, T-PLAY-31, T-PLAY-44 |
| E5, SFF-751 | T-PLAY-08, T-PLAY-37 |
| E6 | T-PLAY-34, T-PLAY-40 |
| E7, SFF-706 | T-PLAY-10 |
| E8, SFF-781 | T-PLAY-14, T-PLAY-15 |
| E9 | T-PLAY-17, T-PLAY-18 (with P1 and P2) |
| SFF-701, SFF-703, SFF-742, SFF-748, SFF-750, SFF-753, SFF-772 | T-PLAY-08 |
| SFF-708, SFF-709, SFF-891 | T-PLAY-09 |
| SFF-721 | T-PLAY-53 (a file in another subfolder is not served) |
| SFF-730 | T-PLAY-02, T-PLAY-05 |
| SFF-733 (no lacing) | T-PLAY-24 |
| SFF-731, SFF-867 | T-PLAY-03, T-PLAY-04 |
| SFF-738 | T-PLAY-38, T-PLAY-39 |
| SFF-739, SFF-757 | T-PLAY-22, T-PLAY-24 |
| SFF-740 | T-PLAY-20, T-PLAY-21, T-PLAY-23 |
| SFF-743, SFF-744, SFF-746 | T-PLAY-08, T-PLAY-11, T-PLAY-12, T-PLAY-13 |
| SFF-747, SFF-795, SFF-798, SFF-886 | T-PLAY-13, T-PLAY-15 |
| SFF-754 | T-PLAY-11, T-PLAY-19 |
| SFF-756, SFF-887 (file warnings) | T-PLAY-09 (`gap`, `encode_skip`, flag bit 7), T-PLAY-15 (`missing_fit`), T-PLAY-17 |
| SFF-759, SFF-794 | T-PLAY-24 |
| SFF-777, SFF-780 | T-PLAY-14 |
| SFF-782 | T-PLAY-16, T-PLAY-26 |
| SFF-790 | T-PLAY-07 |
| SFF-791 | T-PLAY-12, T-PLAY-20 |
| SFF-799 | T-PLAY-57 |
| SFF-863 | T-PLAY-15 |
| SFF-864, SFF-865 | T-PLAY-06, T-PLAY-25 |
| SFF-866 | T-PLAY-07 |
| SFF-868 | No test: 6a reads no folder file, so it does not compute `<rec>` (6.3). |
| SFF-869, SFF-870, SFF-871 | T-PLAY-05, T-PLAY-33 |
| SFF-729 (`summary_stale`), SFF-872 (links), SFF-883 (privacy), SFF-885 and SFF-892 (the full result) | No test in 6a: the player does not compute them (6.13, question Q2). The player never reads `summary` (6.2). |
| SFF-890 | T-PLAY-02 |
| F1 to F21 | T-PLAY-28, T-PLAY-34, T-PLAY-40, T-PLAY-45 to T-PLAY-48 |

Counts: 35 unit, 15 component (one depends on Q3), 7 electron, 6 benchmark: 63 tests.

### 12.5 Parity of the systems [Y7]

- Each unit, component and electron test runs on Windows, Linux and macOS [Y7].
- T-PLAY-53: the outside link is a junction to a folder on Windows, because a file link on Windows
  needs a privilege; it is a file link on Linux and macOS. Both are links that `lstat` reports
  [agent 39] [NV: that `lstat` of Node reports a junction as a link on the runner].
- T-PLAY-56: the test sets the sparse flag with `fsutil sparse setflag` on Windows; Linux and macOS
  make sparse files by a seek past the end.
- The benchmarks run on the Windows test machine. Their runs on Linux and macOS are owed (M-PLAY-3).
- Electron needs a display on Linux. The Linux job runs the component and electron tests under
  `xvfb-run`.

### 12.6 CI [agent 36]

A new workflow `.github/workflows/player.yml`, on the pattern of `.github/workflows/capture.yml` and
`.github/workflows/ring-arm64.yml`:

- Trigger: each push to `dom/player` and to `dom/native-jpeg` that changes `skellycam-ui/src/player/**`,
  `skellycam-ui/src/components/playback/**`, `skellycam-ui/electron/**`, `skellycam-ui/package.json`,
  `skellycam-ui/package-lock.json`, `skellycam-ui/tsconfig.json`, `specs/player.md` or the workflow;
  and by hand.
- `permissions: contents: read`; a concurrency group for each ref with `cancel-in-progress`.
- The same pinned actions as the existing workflows: `actions/checkout` at
  `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1); `actions/setup-node` at
  `949feb2413d6458794dcd2491c4babbbce0c15c1` (v7.1.0) with Node `26.13.1`, as
  `build-installers-pyinstaller.yml`.
- Steps in `skellycam-ui/`: `npm ci`, `npm run test:player:unit`, `npm run test:player:browser`.
- Job `player-windows` on `windows-2025`; job `player-linux` on `ubuntu-24.04`, with `xvfb` installed
  by `apt-get` at one exact version; job `player-macos` on `macos-15`, with its own concurrency group
  and a time limit of 40 minutes, as the macOS job of `capture.yml`.
- The exact `xvfb` package version is taken from the runner image when the workflow is written. This is
  [NV] now.
- The workflow does not run the benchmarks.

## 13. Proposed changes to skellyfileformat

This spec does not edit skellyfileformat. The user decides each text there. An agent wrote each text
[agent 42]. The IDs below are the next free IDs after SFF-893 at commit d67679a. That repository gives
the final IDs.

**P1. No-image rows (new requirement, proposed SFF-894).** Needed for R2 and R3 [E9], Y4. The draft maps
each row to one block [SFF-740, SFF-754, SFF-759].

> **SFF-894** (writer, reader) Bit 4 (16) of `flags` is `no_image`: the camera file holds no frame
> for the row. A writer writes a row with `no_image` for each multi-camera frame for which it stores no
> frame of the camera, for example a frame that failed its capture check, and each multi-camera frame
> after the camera was lost. In such a row, `source_frame_number`, `sample_ns`, `byte_offset` and
> `byte_size` are empty. `arrival_ns` is the time that the writer gives to the multi-camera frame of
> the row. A row with `no_image` has no block. Where SFF-740, SFF-754, SFF-759, SFF-795 and SFF-797
> count rows against blocks, they count only the rows without `no_image`: the j-th row without
> `no_image` belongs to the j-th complete block. A row with `no_image` is usable when the row is usable
> (SFF-746). It needs no block. A reader does not use a row with `no_image` that comes after a row
> whose block is not complete. A player shows no new frame for a row with `no_image`: it holds the
> frame of the last row of the camera with an image at or before the row, and it shows that the camera
> has no frame at that time. `records` of the reader result hold such a row, with `source_frame_number`
> and `sample_ns` null.

**P2. A lost camera (new requirement, proposed SFF-895).** Needed for Y4 ("camera lost at frame N").

> **SFF-895** (writer, reader) Bit 5 (32) of `flags` is `camera_lost`. A writer sets it, together
> with `no_image`, on each row from the first multi-camera frame after the camera was lost to the last
> row of the file. A reader gives the camera file the file warning `camera_lost` when one or more
> usable rows have the flag. A player shows the camera as lost from the first row with `camera_lost`.

Also add `camera_lost` to the file warnings of SFF-887.

**P3. Equal player times (addition to SFF-783).** SFF-782 allows equal player times; SFF-783 does not
say which frame is "last" then.

> When two or more frames of a camera have the same player time, the last frame at or before t is the
> one with the highest position.

**P4. The order of the SFF-759 check in a player (new requirement, proposed SFF-896).** A full walk of
each camera file at the open costs one read for each block.

> **SFF-896** (reader) A player MAY show the frames of a finished or repaired camera file before it
> has counted the blocks of the file (SFF-759). It then checks, for each frame that it reads, that the
> block of the frame is the next block after the block of the previous row with an image (SFF-739),
> and, at the open, that no block follows the block of the last row. When a check fails, the player
> stops showing frames of that camera file and reports the file as `invalid` with the reason
> `bad_metadata`. The reader result of SFF-885 does not use this order.

**P5. The track of a camera file (new requirement, proposed SFF-897).** SFF-732 is a writer rule only.

> **SFF-897** (reader) A reader refuses a camera file that does not have exactly one video track with
> CodecID `V_MJPEG` (state `invalid`, reason `bad_metadata`).

**P6. The position and the order of player times (new requirement, proposed SFF-898).** SFF-754 and
SFF-782 have no reader action.

> **SFF-898** (reader) A reader refuses a video sidecar (state `invalid`, reason `bad_metadata`) when
> the `frame` value of a usable row is not the position of the row, or when the player time of a
> usable row is smaller than the player time of the row before.

**P7. The column line (addition to SFF-748).** SFF-748 names header keys only.

> A reader refuses a timing sidecar whose column line lacks a column of its kind (reason
> `missing_metadata`), or whose last column is not `crc32` (reason `bad_metadata`).

## 14. Measurements, open points, weak points, open work

### 14.1 Measurements owed

| ID | Measurement | Test |
|---|---|---|
| M-PLAY-1 | The targets of 11.3 on Electron 45.3.4 | T-PLAY-58 to T-PLAY-62 |
| M-PLAY-2 | Playback cost on the cameras' own JPEG bytes, on a take of recorder step 5a that the user gives | T-PLAY-59 with that take |
| M-PLAY-3 | The benchmarks on Linux and macOS (the machines of phase 0) | T-PLAY-58 to T-PLAY-63 |
| M-PLAY-4 | 720p60 at N = 4 and 720p30 at N = 16 | T-PLAY-63 |
| M-PLAY-5 | Main-process latency while the handler serves | T-PLAY-62 |
| M-PLAY-6 | Decode on a worker against the page main thread, at N = 8 | a variant of T-PLAY-59 |
| M-PLAY-7 | Speed 8 | T-PLAY-63 |
| M-PLAY-8 | Real clock alignment across cameras in a take of step 5a | a take of the user |

### 14.2 Open points

1. **From the recorder spec** (written on another branch, not visible here): how a no-image row is
   written (P1), the time of such a row, how a lost camera is marked (P2), whether the recorder writes
   live byte offsets that stay correct (SFF-757 is provisional), and the value of `display_rotation`.
   The player spec follows the recorder spec where the recorder spec fixes them first.
2. Question Q1: the route in 6a, against "the switch is 6c" [Y1].
3. Question Q2: the full reader result and the JavaScript test adapter.
4. That `ImageDecoder` decodes a JPEG with no DHT [NV] (T-PLAY-38).
5. The Chromium version of Electron 45.3.4 [NV].
6. A page from `http://` (Vite dev server) that reads the custom scheme was not tested [M `RT` §4].
7. The exact `xvfb` version for the Linux job [NV].
8. The golden folders of skellyfileformat: G1 to G16 exist, each case with a `.player.json` result
   (`../skellyfileformat/golden/README.md`). G1, G4 (four rotations with corner colours), G5 and G6
   (crashed and repaired takes), G7 (no manifest) and G12 (fit vectors) fit the player. Their MKV files
   hold synthetic frames. Y7 says that the player tests build their own takes, so 6a does not use them.
   A later conformance run can read them from a pinned checkout of skellyfileformat, without a copy
   into this repository (question Q2).

### 14.3 Weak points

- SFF-759 is checked late for a block in the middle of a file (6.9, P4). A user can see frames of a
  file that the reader later refuses.
- One bad CSV row in one camera ends the take for all cameras at that row [SFF-746, SFF-754].
- Each file has its own time base [SFF-781, E8]. In one take, one camera can use fitted times and
  another arrival times. A fitted time is not corrected for latency [SFF-781 terms], so the tiles can
  differ by the arrival delay.
- The JPEG payload has no checksum. A changed payload is found only when its decode fails (5.6).
- The page gives the take folder path to the main process. The main process trusts the page as app
  code, as `fileSystem.getFolderContents` does today [C `electron/main/api.ts`] [agent 40].
- All timing evidence is from one Windows machine with an NVIDIA GPU, at 1080p30 and 720p, with JPEG
  re-encodes (11.2).
- The decode runs on the page main thread. A busy page can delay the draws (M-PLAY-6).

### 14.4 Open work for `decisions/open-work.md` [Y2]

- **Option B for the take files (not part of 6a).** Review how the Python server can serve the take
  files with a performance on par with the Electron handler: threads, process splits, no request
  logging on the route, no folder listing per request, `Cache-Control: no-store`, HEAD, and the expose
  header [Y2, M `RT` §5, §6]. The measured gap: the bare FastAPI route was 4 % short and 25 % short
  behind the logging middleware, at 16 × 60 fps × 150 kB.

## 15. Contradictions found

1. **Y1 against the gap of 5a.** Y1 puts the switch between the new player and the `<video>` path in
   6c. Y1 also says that 6a closes the playback gap of recorder step 5a. A 5a take cannot play in
   `<video>` [M `CC` C1]. Thus 6a needs a route for a new take (question Q1).
2. **R2 and R3 [E9] against the format draft.** The draft maps each row to one block and has no field
   for a row with no image [SFF-740, SFF-754, SFF-759]. P1 and P2.
3. **Y4 "gap row" against the format flag `gap`.** The flag `gap` marks a jump of the source frame
   number on a row that has a frame [SFF-756]. This spec calls the row of Y4 a no-image row (1.6).
4. **The evidence against SFF-783 after the last frame.** `GF08` §3 suggests a hold limit and a stale
   flag. SFF-783 holds the last frame with no limit. With R2 and R3, no camera ends early. The spec
   follows SFF-783 and Y4.
5. **The versions.** The evidence measured Electron 35.7.5 and 45.2.3. The pin is 45.3.4 (11.1).
6. **SFF-892 against 6a.** A JavaScript reader gives the scope `player` result in full. The 6a reader
   gives only the members that the player needs (question Q2).
7. **SFF-759 against a fast open.** A count of the blocks at the open needs one read for each block.
   P4.
8. **`RT` §6 against Y2.** `RT` maps a URL to the allowed recording roots. Y2 limits the handler to the
   opened take folder. The spec follows Y2.
9. **`PLAN` §5 and the live view of today against Y3.** They decode with `createImageBitmap` on a
   worker. Y3 puts `ImageDecoder` in the one tile for phase 4 too.
10. **F6 of today against the new rule.** Today all tiles show the CSV time of camera 0, or an estimate
    from frame / fps. The new tiles show the player time of their own frame [SFF-783].
11. **F16 of today.** The warning "Multi-camera sync may not be frame-perfect" describes the player of
    today. Question Q4.
12. **The evidence harness against this spec.** The harness decoded on the page and read through a
    local HTTP server; the transport test used `protocol.handle` with no decode. No run combined the
    two (M-PLAY-1).

## 16. Choices of the agent

Each item fills a gap that the decisions, the format spec and the evidence do not fix. The body marks
each one [agent n].

1. The folder `skellycam-ui/src/player/` and its layout (4.1).
2. The boundary rule: the allowed imports and the scan test (4.2).
3. The module holds the engine, the tile and `PlayerTile`; the controls bar, the grid and the keys stay
   in the host; mark texts are a host option with English defaults (4.3, 8.3).
4. The names of the public interface, the state and the events (4.4).
5. Only erasable TypeScript syntax and `.ts` imports; `allowImportingTsExtensions` (4.2).
6. The scheme `skellycam-take`, its privileges, the URL with a token of 128 bits for each open (5.2).
7. The open: real path, a scan of the root and the media folder only, regular files only, no links or
   junctions, an allow-list by exact relative path, no absolute path to the page (5.3, 5.4).
8. At each first read: compare device and inode with the snapshot, refuse a changed file; cache the
   handle until close (5.4, 5.6).
9. The response table, with HEAD, 416 and `Access-Control-Allow-Origin: *` (5.5).
10. The page client accepts a 206 with the asked start, or a 200 with the exact length (5.5).
11. The manifest read limit of 16 MiB; no limit for a sidecar (5.7).
12. A snapshot of sizes at the open; no use of later bytes; no follow and no reload in 6a (5.6, 6.11).
13. With two or more takes in a folder: open the first in `take_uuid` order (6.4).
14. No read of audio files, folder files or `<rec>` in 6a; the state holds only the result members
    that the player needs (6.3, 6.4, 6.13).
15. A missing column gives `missing_metadata`; `frame` not equal to the position, a decreasing player
    time, and a fit that does not hold each position: the reasons of 6.5, 6.6 and 6.8.
16. A camera file without exactly one `V_MJPEG` video track is refused; the head read in steps of
    64 KiB (6.9).
17. The SFF-759 check at the read of each frame and at the tail; the read range from the previous
    payload end; a mismatch makes the file `invalid` from then on (6.9, 6.10).
18. Times parsed as `BigInt`, checked against 2^53, then kept as JavaScript numbers (6.8).
19. T_k = the largest p_c(k); the clock range [T_0, T_(K-1)]; k* (7.2).
20. A step and a frame seek set t = T_k; `seekTime` clamps (7.2).
21. Pause keeps t; no move to a whole frame (7.4).
22. The end of play and the loop on the clock (7.4).
23. In a no-image row, the image of the last row with an image at or before it; a lost camera keeps
    its last image; N is the first row with `camera_lost` (6.7, 7.3).
24. A take is unfinished when its manifest state is `recording` or a camera file is unfinished; the
    mark goes on the tiles of the unfinished files (6.11, 8.3).
25. The decode on the page main thread (8.1).
26. The canvas size from the tile size × `devicePixelRatio`; contain on black; the label in the canvas
    at a fixed CSS size; the tile keeps the label text for tests (8.2, 8.4).
27. The label parts and the timecode frame field from the nominal rate of the camera (8.4).
28. The prefetch queue of min(8, max(2, ⌊64 / N⌋)) frames; one range read in flight for each camera,
    up to 4 MiB; at a rate above 1, only the rows that the clock will choose (9).
29. Newest wins: one decode in flight and one pending target for each tile; the draw rule (7.5, 9.2).
30. The events and their rate: at most 5 per second during play, at once after a command (4.4).
31. "Rec: fps" from the nominal rate of the camera with the lowest `group_position`, rounded as SFF-728
    (8.4).
32. The grid code and the key code move out of `SyncedVideoPlayer.tsx` into host parts that both
    players use; the new host view `CanvasTakePlayer.tsx` (4.3, 10).
33. The fixture builder in TypeScript in `tests/fixtures/`; temporary folders at run time; the
    flat-block JPEG encoder; the barcode and quadrant patterns; the Node `TakeFiles` (12.2).
34. The benchmark JPEGs from the JPEG encoder of Chromium, about 190 kB at 1080p (12.2).
35. The runners: `node --test` for unit tests; Playwright 1.65.1 `_electron` with Electron 45.3.4 for
    component and electron tests; a test Vite config and a harness app; the host view tests in
    `src/components/playback/tests/`; the npm script names (12.1).
36. The workflow `player.yml`: triggers, jobs, runner labels, pins, `xvfb-run` on Linux, the macOS job
    rules (12.6).
37. The pass thresholds of the test table and the targets of 11.3; a missed benchmark target goes to the
    user and does not stop 6a by itself (2, 11.3).
38. A read error: the mark `read_error`, an `error` event, the other tiles continue (5.6, 6.10).
39. The link case of T-PLAY-53 on Windows is a junction (12.5).
40. The page gives the folder path, and the main process trusts it as app code (5.3, 14.3).
41. The term "no-image row" for the gap row of Y4; rows with the format flag `gap` show as normal
    frames (1.6).
42. The texts P1 to P7 of section 13.

## 17. Questions for the user

Each question has two options and a recommended answer. "Yes" accepts the recommendation.

**Q1. The route for a new take in 6a.** Y1 puts the switch in 6c, but 6a must close the playback gap
of 5a (section 15, item 1).
- Option A: in 6a, the playback page opens a folder in the new player when the folder holds a timing
  sidecar of the format (SFF-864), and in the player of today otherwise. 6c does the rest of the switch
  and the old takes.
- Option B: 6a has no route. A 5a take cannot play in the app until 6c.
- Recommended: A. Do you agree that 6a adds this route and that 6c keeps the rest of the switch?

**Q2. The full reader result and the conformance tests.** SFF-892 gives a JavaScript reader the full
scope `player` result, with the test adapter `bin/read-folder.mjs` of the conformance tests. That needs
the JSON files, the link checks, the privacy member and the legacy recognition, which the player does
not need in 6a.
- Option A: 6a gives only the members that the player needs (6.13). The full result, the adapter and
  a conformance run against the golden folders, from a pinned checkout of skellyfileformat, become an
  open-work item for a later step (with 6c, which reads old takes).
- Option B: 6a also builds the full result and the adapter, and runs the conformance tests.
- Recommended: A. Do you agree that the full result and the conformance run wait for a later step?

**Q3. More tile marks.** Y4 and Y5 name three marks. Three more cases have no mark: a refused camera
file (`invalid` or `unsupported_version`), a damaged file (a bad CSV row), and a read error during play.
- Option A: each gets a text mark on its tile: "camera file not readable: <reason>", "damaged at frame
  N" and "read error". The tile keeps the last real image where it has one. T-PLAY-49 and T-PLAY-50
  test them.
- Option B: no mark; the camera has no tile, or the tile stops with no text.
- Recommended: A. Do you agree to add these three marks?

**Q4. The sync warning of today (F16).** It says "Multi-camera sync may not be frame-perfect". That is
true of the player of today, not of the new player.
- Option A: the host hides the button when the new player plays. The player of today keeps it.
- Option B: the button stays in both.
- Recommended: A. Do you agree to hide it for the new player?

## 18. Decisions of the user

### 18.1 Y1 to Y7 (grilling of 2026-11-19, Q217 to Q226)

The user decided these on 2026-11-19
([ADR-J2BQ](../decisions/entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)). They are binding.

- Y1 (Q217): The player has four steps, tests first: 6a the player for new takes, video only (the take
  reader for the manifest and the CSVs, the master clock, the canvas tiles, play, pause, step and
  scrub); 6b audio in the player (it needs step 5b of the recorder); 6c the switch between the new
  player and the old video-element path, and old takes; 6d the "upgrade recording" converter. Step 6a
  closes the playback gap that recorder step 5a opens, so the two can land together.
- Y2 (Q218): File access for the player: option A now. A handler in the Electron main process serves
  the bytes, limited to the opened take folder. It sits behind a small interface in the page, so a
  server path can be added later without a change of the player. The user also asked for a task for
  later (open work, not part of 6a): review how to implement option B (the Python server serves the
  files), including threading and process splitting, to get its performance on par with the Electron
  handler. Evidence: `research/skellycam_recording/recording_upgrade/results/range_transport/FINDINGS.md`
  on branch `dom/research` (Electron `protocol.handle`: 16 cameras x 60 fps x 150 kB with 0 dropped
  ticks; FastAPI fixed and bare 4 % short, 25 % short behind the logging middleware; `file://` gives
  200 with no `Content-Range`; concurrent ranges need `Cache-Control: no-store`).
- Y3 (Q219): The "JPEG to canvas" tile is built once, with `ImageDecoder`, and is used by the player
  now and by the live preview in phase 4 (which decodes with `createImageBitmap` today). One place for
  rotation and for the frame label.
- Y4 (Q220): A gap: when the frame at time t is a gap row, the tile keeps the last real image and
  marks it clearly as "no frame". For a dead camera the tile shows "camera lost at frame N" from that
  point to the end.
- Y5 (Q221): A take that was never finished: until the repair step (recorder 5c) exists, the player
  opens it read-only, plays the rows and frames that are complete, and shows an "unfinished" mark. No
  repair is offered yet.
- Y6 (Q222): The player is a self-contained TypeScript module inside the skellycam UI
  (`skellycam-ui`), in its own worktree and branch (`dom/player`, off `dom/native-jpeg`), with no
  dependency on the rest of that UI, so the freemocap session can take it into its own UI later.
- Y7 (Q223, final answer): The player's tests build their own small takes in the new format, from the
  format specification, with synthetic JPEGs. (The idea to convert the freemocap sample data was
  dropped by the user.) The tests run on Windows, Linux and macOS (the user requires parity across the
  three systems).

### 18.2 Earlier decisions (cited, not repeated)

The decision list of 2026-11-19 cites these as decided before the grilling. This spec numbers them
E1 to E9 for reference only:

- E1: A canvas player in skellycam-ui replaces the `<video>` player and the H.264 web transcode: HTTP
  range fetch per frame at the CSV byte offset, `ImageDecoder`, one master clock.
- E2: Old recordings keep a `<video>` path.
- E3: skellycam owns the JavaScript reader.
- E4: A player shows, at take time t, the last frame of each camera whose time is at or before t,
  never a frame computed from index and frame rate, and no frame before position 0 (SFF-783).
- E5: The player applies `display_rotation`.
- E6: The player draws the frame label from the sidecar fields (no overlays are recorded).
- E7: A JavaScript reader uses BigInt for 64-bit values (SFF-706).
- E8: The time axis is the fitted time when fit lines exist and cover every position, else
  `arrival_ns` for the whole file with the warning `missing_fit` (SFF-781).
- E9: The recorder decisions R2 and R3 (a dead camera and a damaged frame give gap rows with no image,
  so every camera's CSV has equal rows).
