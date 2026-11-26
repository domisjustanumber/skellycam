# Phase 6 player specification: step 6a, the canvas player for new takes (video only)

Status: accepted by the user, 2026-11-20 (revision 2;
[ADR-YV3V](../decisions/entries/YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md); the
agent choices are in
[ADR-4K7V](../decisions/entries/4K7V-phase-6a-player-spec-and-test-list.md)). The decisions Y1 to Y7
([ADR-J2BQ](../decisions/entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)), the later decisions
M1 to M10 and L1 to L8, and the answers U1 and U2
([ADR-4HNY](../decisions/entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md))
are accepted. Section 18 gives each one in full. Revision 2 applies them, the faults of an
independent review (section 15.2) and a cross-check against the recorder spec. The failing tests of
step 6a come before the product code of step 6a.

## 0. How to read this spec

Marks:

- **[Yn]**, **[Mn]**, **[Ln]**: a decision of the user, 2026-11-19 (section 18). **[Un]**: an answer
  of the user, 2026-11-20 (section 18.4). The corrections of 2026-11-20 after the acceptance are in
  [ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md) (proposed),
  except U3.
- **[En]**: an earlier decision of the user that the decision list of 2026-11-19 cites (section 18.5).
  This spec numbers them for reference only.
- **[SFF-nnn]**: a requirement of the format spec `../skellyfileformat/spec/SPEC.md`, draft v2, read
  at commit 24949df (`24949df6c22093336c30b279c396ef593648de1e`) of that repository. This spec cites
  it. It does not repeat it. Before 2026-11-21, this spec read commit d67679a, and then commit
  c1028ef ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
- **[F-list]**: the list F-1 to F-10 of format changes, section 13 of `specs/recorder.md`. The format
  holds these changes since commit c1028ef (skellyfileformat ADR-6AT7). The user accepted the details
  of skellyfileformat ADR-5B03 and ADR-76NN.
- **[M file]**: measured; the file holds the result. Each research file is on branch `dom/research`
  at commit fc95be447 of this repository. It is not on this branch. Short names:
  - `RT` = `research/skellycam_recording/recording_upgrade/results/range_transport/FINDINGS.md`;
  - `IP` = `research/skellycam_recording/recording_upgrade/results/intra_playback/FINDINGS.md`;
  - `CC` = `research/skellycam_recording/recording_upgrade/results/chromium_codecs/FINDINGS.md`;
  - `GF08` = `research/skellycam_recording/recording_upgrade/results/chromium_sync_scrub/gapfill/GF08_ts_sync.md`;
  - `PLAN` = `research/NATIVE_JPEG_CAPTURE_PLAN.md`.

  The evidence index `research/skellycam_recording/recording_upgrade/results/EVIDENCE_INDEX.md`
  (sections 2.8 and 2.9) points to these files.
- **[M review]**: an experiment of the independent review of 2026-11-19, in Electron 45.3.4
  (Chrome 156) and Node 24.15. The review holds the result. No file of this repository holds it.
- **[C file]**: a code fact of this branch, read on 2026-11-19.
- **[NV]**: not verified. No evidence proves it.
- **[agent n]**: an agent filled a gap that the decisions, the format spec and the evidence do not
  fix. Section 16, item n, lists each one.
- **[Fn]**: feature n of the player of today (section 3).

This spec uses British spelling. It cites files, not line numbers, except where the evidence cites a
line.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Step 6a gives skellycam-ui a canvas player for takes in the new format: camera JPEGs in MKV, with CSV
timing sidecars [E1]. One master clock drives all cameras. Each tile gets its JPEG by a byte range at
the CSV offset and decodes it with `ImageDecoder` [E1, Y3]. Step 6a closes the playback gap that
recorder step 5a opens, so the two can land together [Y1].

### 1.2 Scope of 6a

6a delivers [Y1]:

- the take reader: the manifest, the video sidecars, the camera files (section 6), with only the
  reader parts that the player needs [L2];
- the master clock and the frame choice (section 7);
- the shared tile, for the player and the live preview (section 8) [Y3, L6];
- play, pause, step, seek, scrub and speed, with each feature of the player of today (section 3);
- the file access through the Electron main process (section 5) [Y2, L7, L8];
- the self-contained module (section 4) [Y6];
- the route: a take folder in the new format opens in the new player, each other folder in the player
  of today (section 10) [L1];
- the tests, with fixtures that the tests build (section 12) [Y7].

### 1.3 What waits for later steps

| Step | Delivers | This spec |
|---|---|---|
| 6b | Audio in the player. It needs recorder step 5b [Y1]. | 6a reads no audio file [agent 14]. |
| 6c | The rest of the switch, old takes, the full reader result and the conformance run [Y1, L1, L2, E2]. | 6a does not read an old take. [`player-legacy.md`](player-legacy.md) (accepted, [ADR-2Z2D](../decisions/entries/2Z2D-answers-of-the-owner-q800-to-q803-and-acceptance-of-the-v1-playback-spec.md)) is the part for FreeMoCap v1 recordings. |
| 6d | The "upgrade recording" converter [Y1]. Cancelled on 2026-11-24 ([ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md), Q705). | None. |
| recorder 5c | The repair step. It can also fill the file of a killed camera process later [M5]. | 6a opens an unfinished take read only and offers no repair [Y5]. |
| phase 4 | The live preview. | Section 8 gives the tile interface that the preview uses [L6]. |
| step 4b | The measurement of the tile with 8 cameras at 60 fps. A worker only if it misses its target [L6]. | Section 8.1. |
| open work | Option B: the Python server serves the take files [Y2]. | Section 5.9 states the place in the module. Section 14.4 gives the item. |

### 1.4 Non-goals

- A change in skellyfileformat. The merged list of the recorder spec holds the proposals (section 13).
- Any feature beyond the features of today (section 3), unless a decision names it. Examples: zoom,
  pan, full screen, frame export, an A-B loop, a camera offset, a seek to a time.
- A change of the player of today [L5], except the one optional prop of `PlaybackControls` [U3]
  (section 10).
- A reload of a take that is still being written. The reader reads a snapshot at open [agent 12].
- The capture info JSON, the processing info JSON, the calibration TOML, the Parquet and the journal.
  The player needs none of them in 6a [agent 14].
- The full reader result of SFF-885 and the JavaScript test adapter [L2].

### 1.5 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| The take folder, the files, the reader rules | `../skellyfileformat/spec/SPEC.md` draft v2 | Section 6 applies the reader rules for the scope `player` [SFF-892]. |
| Missing frames: placeholders, the flag `missing`, `camera_dead`, the short file of a killed process | M1 to M10; the recorder spec and its F-list | Sections 6.7, 7.3, 8.3. |
| The camera states | [`windows-capture.md`](windows-capture.md) section 8.1 | The tile shows each of the eight states (8.3) [L6]. |
| What phase 4 needs from the tile | `specs/preview.md` on branch `dom/preview`, section 11 | Section 8 agrees with it (8.6). |
| The rotation value of a ring frame | [`frame-ring.md`](frame-ring.md) section 3 (`rotation_cw_deg`) | The same meaning as `display_rotation` [SFF-751]. |
| Error flags of a ring frame | [`frame-ring.md`](frame-ring.md) section 4 | A flagged ring frame reaches the tile only as a draw with no new image (8.3). |
| The transport and the header rules | `RT` sections 6 to 8 | Section 5. |
| Frame choice by time, not by index | `GF08`, `IP` P2, [SFF-783], [E4] | Section 7. |

### 1.6 Terms

| Term | Meaning |
|---|---|
| take, take folder, camera file, timing sidecar, device pair, position, multi-camera frame, player time | As in section 1 of the format spec. |
| row | A data row of a video timing sidecar. Row k has position k. Row k is group frame k. |
| usable row | A row that the reader uses [SFF-746, SFF-740]. |
| `missing` row | A row with the flag `missing` [M3]. Its byte fields point at a black placeholder block [M1, M2], except in the short file of a killed camera process, where they are empty and the row has no block [M5]. |
| placeholder | The black JPEG block of a `missing` row, with the size and chroma layout of the camera [M2]. The player never shows it [M9]. |
| real row | A usable row that is not `missing`. Its block holds a camera image. |
| dead camera | A camera with a manifest warning `camera_dead` [M8], or, with no manifest that the reader uses, a camera whose rows are `missing` from one row to the end of the file (7.3). |
| K | The number of multi-camera frames that the player shows: the smallest number of usable frames of the camera files that the reader reads [SFF-754]. |
| take time t | An integer number of nanoseconds, relative to the take start [SFF-705]. The master clock holds it. |
| p_c(k) | The player time of row k of camera c [SFF-781]. A `missing` row with no time has none [M3]. |
| T_k | The time of multi-camera frame k (section 7.2). |
| k* | The frame number that the controls show (section 7.2). |
| the module | The player module of section 4 [Y6]. |
| the host | The program that mounts the module: skellycam-ui now, the freemocap UI later. |
| tile | `Tile`, the canvas that shows one camera (section 8) [Y3, L6]. |
| `TakeFiles` | The page-side interface for the bytes of the opened take (section 5.1) [Y2, L8]. |
| handler | The Electron main-process code behind `TakeFiles` (section 5.2) [Y2]. |

## 2. Steps of phase 6 and the done list of 6a

Phase 6 has four steps: 6a, 6b, 6c and 6d. The tests of a step come first [Y1].

Step 6a is done when:

1. All unit, component and electron tests of section 12 pass on Windows, Linux and macOS, on the
   development machine and in the CI workflow of section 12.6 [Y7].
2. The benchmarks of section 12 run on the Windows test machine, and the results go to an evidence
   entry. A benchmark that misses its target goes to the user. It does not stop 6a by itself
   [agent 36].
3. A take that recorder step 5a writes opens and plays in the app [L1].
4. No code outside `skellycam-ui/src/player/` imports a file of the module, except `index.ts` and
   the two files of `main/`. The boundary test passes (T-PLAY-35).

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
| F6 | Tile overlay, bottom right: the time. It is the CSV time of the first camera for every tile, or an estimate from frame / fps with a `~` in front. A tooltip tells which ("timestamp from recording" or "estimated from frame number"). | `SyncedVideoPlayer` |
| F7 | Setting: show or hide the overlays (default: show). | `PlaybackControls` settings popup |
| F8 | Setting: time format, seconds (`1.234s`) or timecode (`HH:MM:SS:FF`). The default of the player state is timecode. | `PlaybackControls` settings popup |
| F9 | Play and pause: a button and the Space key. Play at the last frame starts again from frame 0. Pause moves to a whole frame. | both |
| F10 | Previous frame and next frame: buttons, the arrow keys (1 frame) and Shift with an arrow key (10 frames). A step stops play. | both |
| F11 | Jump to the start (button, Home): play continues if it was on. Jump to the end (button, End): play stops. | both |
| F12 | Loop on or off (button, L key): at the end, play starts again from frame 0. | both |
| F13 | Speed menu: 0.1, 0.25, 0.5, 1, 1.5, 2, 4 and 8 times. | `PlaybackControls` |
| F14 | Seek bar: a range input in frames, from 0 to the last frame, in steps of 1. A drag stops play and shows each frame during the drag. The release starts play again if play was on before the drag. | both |
| F15 | Text: "Frame k / N"; "Rec: fps" (the recording rate from the backend); the current time (frame / fps); the duration (the longest `<video>` duration). | `PlaybackControls` |
| F16 | A sync information button with a warning tooltip ("Multi-camera sync may not be frame-perfect"). The dismissal is kept in local storage. | `PlaybackControls` |
| F17 | A settings popup that holds F7 and F8. | `PlaybackControls` |
| F18 | A loading message ("loading videos, ready / total") and an empty state ("no videos loaded"). | `SyncedVideoPlayer` |
| F19 | `initialFrame`: one seek when all videos are ready. `onFrameChange`: a callback at about 5 Hz, so the host keeps the frame across page changes. | `SyncedVideoPlayer`, `PlaybackContext` |
| F20 | The keys do nothing while the focus is in any `<input>` (also the seek bar) or a `<textarea>`. | `SyncedVideoPlayer` |
| F21 | The total frame count is the smallest frame count of the videos (duration × fps). | `SyncedVideoPlayer` |

The page `PlaybackPage.tsx` adds host features around the player: a back button, the recording name,
"open folder", a camera count, the total size, a fps chip, and the column and layout settings of
`CamerasViewSettingsOverlay` [C]. They stay host features.

The player of today has no zoom, no pan, no full screen, no audio, no frame export and no camera
offset [C].

### 3.2 What 6a does with each feature

All features stay, on the new engine, except F16 [L4]. These change, because the new engine reads the
time of each frame from its file [SFF-783, E4]:

- F4: the frame number is k* for every tile (section 8.4).
- F6: each tile shows the player time of its own image [L4]. The `~` estimate goes away. The canvas
  gets the tooltip "timestamp from recording" as its `title` [agent 24].
- F9: pause moves to a whole frame, as today: t becomes T_k* [L4].
- F15: "Frame k* / K"; "Rec: fps" from `nominal_rate` [agent 30]; the current time is t; the duration
  is T_(K-1). Both are take times.
- F16: hidden in the new player [L4].
- F21: the total frame count is K [SFF-754].

## 4. The module [Y6]

### 4.1 Folder and layout [agent 1]

The module is the folder `skellycam-ui/src/player/`:

| Path | Content |
|---|---|
| `index.ts` | The public page entry: `openTake`, `electronTakeFiles`, `isTakeFolder`, `Tile` and the types of 4.4 and 8.3. |
| `files/` | `take-files.ts` (the `TakeFiles` interface), `electron-take-files.ts` (the page client of the handler). |
| `reader/` | The take reader: `take.ts`, `manifest.ts`, `sidecar.ts`, `fit.ts`, `matroska.ts`. |
| `clock/` | `clock.ts` (the master clock), `choose.ts` (the frame choice). |
| `tile/` | `tile.ts` (decode and draw), `format.ts` (the overlay text). |
| `main/` | `take-scheme.ts` (the handler, main process), `bridge.ts` (the preload bridge). |
| `tests/` | `unit/`, `browser/`, `bench/`, `fixtures/`, `harness/` (section 12). |

The root `.gitignore` of the repository ignores each file with the name `index.ts` or `tsconfig.json`.
Add `index.ts` and `tsconfig.json` of the module with `git add -f`. Do not change the `.gitignore`
([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)).

### 4.2 The boundary rule [Y6] [agent 2]

A file of the module imports only:

- another file of the module;
- the web platform (WebCodecs `ImageDecoder`, canvas, `fetch`, `BigInt`);
- `electron` and `node:` modules, and only from `main/` and `tests/`;
- `@playwright/test` (1.65.1), and only from `tests/`.

A file of the module does not import React, a file of the rest of skellycam-ui, the `@/` alias,
i18next, Redux, `react-grid-layout`, the UI components of the app or the CSS of the app. T-PLAY-35
checks the imports.

The module uses only TypeScript syntax that a type stripper can remove (no `enum`, no `namespace`, no
parameter properties). Each import names the `.ts` file. Each import of a type only uses
`import type`: under Node type stripping, an import of an interface without `import type` crashes at
load [M review]. The module has its own `src/player/tsconfig.json` with `allowImportingTsExtensions` and
`verbatimModuleSyntax`, so that `tsc -p src/player/tsconfig.json` reports a missing `import type`. The
root `tsconfig.json` gets only `allowImportingTsExtensions`: `verbatimModuleSyntax` in the root file gives
73 errors in the code of today [C, 2026-11-20]. Then Node runs the unit tests with no build step.

### 4.3 How a host mounts the module [agent 3]

The module is the engine and the tile. The controls bar, the tile grid and the keys stay in the host.

A host does these steps:

1. In the main process, before `app` is ready: call `registerTakeScheme()` of `main/take-scheme.ts`.
   After `app` is ready: call `installTakeHandler({ recordingsFolder, pickedFoldersFile })` (5.3).
2. In the preload script: call `exposeTakeBridge(contextBridge, ipcRenderer)` of `main/bridge.ts`.
3. In the page: `const files = await electronTakeFiles(folderPath)`. When `isTakeFolder(files)` is
   false, the host closes `files` and uses its other player (section 10). Else
   `const player = await openTake(files)`.
4. Make one `Tile` on a canvas for each camera of `player.state.cameras`, and give it to the player
   with `player.attachTile(cameraIndex, tile)`. This is the one way to bind a tile.
5. Drive the commands of 4.4 from the host controls. Read the state and the events.
6. Call `player.close()` when the host leaves the take.

The freemocap UI takes the module as a copy of the folder `skellycam-ui/src/player/`. It does the six
steps above, with its own grid and controls. A package publication is not part of 6a.

### 4.4 The public interface [agent 4]

The names below are the names that the tests use. The types are TypeScript.

```ts
openTake(files: TakeFiles): Promise<TakePlayer>
isTakeFolder(files: TakeFiles): Promise<boolean>     // a device pair of SFF-864 exists
electronTakeFiles(folderPath: string): Promise<TakeFiles>

interface TakePlayer {
  readonly state: PlayerState;            // a new object after each change
  play(): void;
  pause(): void;                          // t becomes T_k* [L4]
  step(frames: number): void;             // +1, -1, +10, -10; stops play
  seekFrame(k: number): void;             // the seek bar and the jumps; newest wins
  setSpeed(rate: number): void;           // a rate of F13
  setLoop(on: boolean): void;
  setTileOptions(o: { showLabel: boolean; timeFormat: 'seconds' | 'timecode' }): void;
  attachTile(cameraIndex: number, tile: Tile): () => void;   // returns detach
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
  missingRows: number;                    // usable rows with the flag missing
  deadFrom: number | null;                // N of "camera lost at frame N" (7.3)
  damagedAt: number | null;               // the position of the bad row (6.6)
}
```

Events [agent 29]:

- `state`: after each command, and at most 5 times per second during play.
- `frame`: when k* changes, at most 5 times per second during play, and at once after a step, a seek or
  a pause. The host uses it for F19.
- `error`: a read error, or a file that becomes `invalid` during play (sections 5.7 and 6.10).

## 5. File access [Y2] [L7] [L8]

### 5.1 The page-side interface

```ts
interface TakeFiles {
  readonly folderName: string;                          // for display only
  readonly entries: { path: string; size: number }[];   // the snapshot of 5.4
  readRange(path: string, start: number, end: number, signal?: AbortSignal): Promise<Uint8Array>;
  readWhole(path: string, maxBytes: number): Promise<Uint8Array>;
  close(): Promise<void>;
}
```

- `path` is a path of `entries`, relative to the take folder, with `/` [SFF-885].
- `readRange` gives the bytes from `start` to `end - 1`. It fails when it gets fewer bytes.
- `readWhole` fails when the file has more than `maxBytes` bytes.
- Every file read of the player goes through this interface [L8]. The reader and the clock know only
  it. Thus a server path (5.9) and the Node test implementation (12.2) need no change of the player
  [Y2].
- One shared check suite runs against both implementations: the Node one (T-PLAY-39) and the
  Electron one (T-PLAY-64) [L8].

### 5.2 The handler in the Electron main process [agent 5]

- The scheme is `skellycam-take`. `registerTakeScheme()` registers it as privileged with `standard`,
  `secure`, `supportFetchAPI`, `stream` and `corsEnabled`, as the measured harness did [M `RT` §2].
  The handler uses `protocol.handle` on the default session [M `RT` §1, §4].
- A URL is `skellycam-take://<token>/<path>`. `<token>` is 32 lower-case hexadecimal characters (128
  random bits). Chromium makes the host of a standard scheme lower case [M review], so the token is
  lower case from the start. `<path>` is the relative path, percent-encoded.
- The page client `electronTakeFiles` calls `fetch` with `cache: 'no-store'`. It sends no `Range`
  header for `readWhole`, and `Range: bytes=a-b` for `readRange`. It sends no other form.
- The handler reads with positional reads (`FileHandle.read`). It does no synchronous file call while
  it serves a request.

Why this transport: `protocol.handle` with its own range handler served 16 cameras × 60 fps ×
150 kB with 0 dropped ticks (median of 5, Electron 35.7.5 and 45.2.3). The bare FastAPI route was
about 4 % short, and 25 % short behind the logging middleware of skellycam [M `RT` §5, Y2].

### 5.3 Which folders open [L7] [agent 6]

The handler opens a folder only if the folder is inside the recordings folder or inside a folder that
the user picked in the system folder dialog [L7]:

- The recordings folder is `<home>/skellycam_data/recordings`, the default of the backend
  (`get_default_skellycam_recordings_path` in `skellycam/system/default_paths.py`) [C]. The main
  process computes it from `app.getPath('home')` with the same rule and gives it to
  `installTakeHandler` as `recordingsFolder`.
- A picked folder is a folder that `dialog.showOpenDialog` returned in the main process, through the
  existing call `fileSystem.selectDirectory` [C `electron/main/api.ts`]. The main process adds each
  such folder to a list, and keeps the list in the file `pickedFoldersFile` in the user data folder of
  the app (`app.getPath('userData')`). A folder that the user picked in an earlier run, for example the
  base recording folder of the recording browser, stays allowed [U1].
- Only a dialog pick in the main process adds a folder to the list. No bridge call, IPC message or
  request of a page can add a folder, change the list or read it [U1]. T-PLAY-62 tests this.
- "Inside" compares real paths (`fs.realpath`): the folder is the allowed folder or below it. On
  Windows the comparison ignores case.
- Any other folder: the open fails with the error "folder not allowed", and no token is made.
- A relative path, a UNC path (`\\host\share`) and a device path (`\\?\`, `\\.\`) fail the same way
  before any file system call: a UNC path makes the main process open a network connection ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
  T-PLAY-62 tests it.

### 5.4 Open, tokens and close [agent 5] [agent 7] [agent 12]

1. The page calls the bridge: `open(folderPath)`. The host gives the path, for example the path of a
   recording that the recording browser lists.
2. The main process takes the real path and checks the rule of 5.3. It refuses a path that is not a
   directory.
3. It lists the root of the folder and the media folder `synchronized_videos/` only [SFF-721]. It
   keeps each regular file. It leaves out each symbolic link, each junction and each other special
   file (by `lstat`). It does not follow a media folder that is a link. It also leaves out
   each regular file with more than one hard link: a hard link can name a file outside the take ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
4. It stores, for each kept file: the relative path, the size, the device and the inode (file ID),
   from `stat(path, { bigint: true })`. File IDs can be larger than 2^53. This list is the snapshot. It
   is also the allow-list of the token.
5. It ties the token to the window that asked (`event.sender`). It closes the token when that window
   navigates, reloads, closes, or opens another take [agent 5]. When the window
   navigated or closed during the open, the open fails and no token is made ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
6. It returns `{ token, folderName, entries }`. `entries` holds the relative paths and the sizes only.
   No absolute path goes to the page.
7. `close(token)` closes each cached handle and deletes the token. A request with a deleted token gets
   404.

A request to the scheme does not say which window sent it. The token is the only key: the main
process gives it only to the window that asked, and it ends with that window [NV: that no other page
can learn a token].

### 5.5 The limit to the opened take folder and the reads [Y2] [agent 7] [agent 8]

- The handler decodes `<path>` and compares it, as a string, with the relative paths of the allow-list
  of the token. It serves only an exact match. It never joins a path from the URL onto the folder path.
  Chromium resolves `..`, `%2e%2e` and `\` in the URL before the handler sees it [M review]. Thus the
  rule that matters, and the rule that T-PLAY-57 tests, is: no request can read a byte of a file that
  is not in the allow-list.
- Camera files (`.mkv`): the handler opens each one at its first read and keeps the handle until
  `close(token)`. At the open it compares `stat` (bigint) with the device and inode of the snapshot, and it
  refuses a file with more than one hard link ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
  When they differ, it refuses the file with 404 and keeps no handle.
- Each other file (the manifest, the sidecars): each read opens the file, checks its identity as
  above, reads, and closes it. The handler keeps no handle on such a file. On Windows, a rename over a
  file that a process holds open fails with `EPERM` [M review]; the recorder replaces the manifest with
  a rename (`os.replace`). Thus a take that the player has open does not stop the recorder from
  writing its manifest.

### 5.6 Responses [M `RT` §6] [agent 9]

The handler serves only bytes below the snapshot size of the file, also when the file is now longer.
It reads the body from the file in pieces of at most 1 MiB, so one response does not hold a large
file in the memory of the main process ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).

| Request | Response |
|---|---|
| GET with no `Range` | 200, `Content-Length: <snapshot size>`, `Accept-Ranges: bytes`, the bytes from 0 to the snapshot size |
| GET `bytes=a-b` | 206, `Content-Range: bytes a-e/<snapshot size>`, `Content-Length: e-a+1`, `Accept-Ranges: bytes`; e is b clamped to the snapshot size − 1 |
| `a` at or above the snapshot size; `a > b`; any other `Range` form (suffix, open end, more than one range, malformed) | 416, `Content-Range: bytes */<snapshot size>` |
| A path that is not in the allow-list; a deleted token; a file whose identity changed | 404 |
| Any method other than GET | 405 |

Each response has `Content-Type: application/octet-stream`, `Cache-Control: no-store`,
`Access-Control-Allow-Origin: *` and
`Access-Control-Expose-Headers: Content-Range, Content-Length, Accept-Ranges`.

Reasons from the evidence:

- Without `Cache-Control: no-store`, Chromium failed 1 to 2 % of concurrent range reads of one URL
  with `net::ERR_CACHE_OPERATION_NOT_SUPPORTED`, in Electron 35 and 45. `no-store` removed every
  failure (0 of 2,880 per configuration) [M `RT` §3].
- A page from `http://` (the Vite dev server) needs the expose header to read `Content-Range` [M `RT`
  §3]. Whether a `file://` page needs `Access-Control-Allow-Origin` and `corsEnabled` for a custom
  scheme is [NV] [M `RT` §4].
- A `net.fetch('file://')` passthrough gives 200 with no `Content-Range`, and it breaks a seek past
  the end of the file [M `RT` §4, `CC` C31, C31a]. The handler does not use it.

The page client accepts a 206 only when the start of `Content-Range` is the start that it asked for.
It accepts a 200 only when the body has exactly the length that it asked for. It treats each other
answer as a read error [M `RT` §7] [agent 10]. Thus a later transport that answers like `file://`
(200, no `Content-Range`) also works [M `CC` C31a].

### 5.7 When the take folder changes while it is open [agent 12] [agent 8] [agent 37]

- The reader uses the snapshot sizes. It does not use bytes that a writer appends after the open. A
  take that is still being written thus plays as it was at the open [Y5].
- A camera file that is deleted or renamed after its first read stays readable through its open
  handle [M review for Windows; NV for Linux and macOS, which keep an unlinked file readable by
  design]. A camera file that is deleted, renamed or replaced before its first read, and a sidecar or
  manifest that is replaced, get 404 at the next open.
- A file that a program shortens gives a short read. The page client treats it as a read error.
- A read error gives the mark "read error" on the tile of that camera [L3], and an `error` event. The
  other tiles keep playing [L3].
- The JPEG payload has no checksum in the format. A changed or corrupted payload decodes with no error,
  with grey pixels [M review]. The player cannot find it. Damage is found only from the timing file
  [L3] (6.6).

### 5.8 What the reader reads

- the manifest: `readWhole('recording_manifest.json', 16 MiB)` [agent 11];
- each video sidecar: `readWhole(<csv>, no limit)`;
- each camera file: its head (6.9), the range of each frame that it shows (6.10) and its tail (6.9).

The reader never writes, moves, renames or creates a file [SFF-799]. `TakeFiles` has no write call.

### 5.9 The place for a server path later [Y2]

A server path is a second implementation of `TakeFiles`, for example `files/http-take-files.ts`. It
uses the acceptance rule of 5.6 and passes the shared check suite [L8]. The changes that the Python
route needs are in `RT` §6: serve the original file, send `Cache-Control: no-store` and the expose
header, do not list the folder on each request, and leave the route out of the request log. The review
of option B with threads and process splits is open work, not 6a (14.4) [Y2].

## 6. The take reader

### 6.1 Order of the open

1. Read the manifest (6.2). If the reader cannot use it, rebuild the links by a scan (6.3).
2. Find the device pairs and group them by `take_uuid` (6.4).
3. Read each video sidecar: header, column line, rows, footer (6.5, 6.6).
4. Read the head of each camera file, and the tail of each finished or repaired file (6.9).
5. Compute the player times (6.8), the usable counts, K, T_k and the dead cameras (7.2, 7.3).
6. Give the state of 4.4.

### 6.2 The manifest

- The reader uses `recording_manifest.json` to find the files of the take [SFF-730]. It uses
  `cameras[].video` and `cameras[].timing`. It checks that each path names a file of the snapshot and
  that the two files are a device pair (6.4) [SFF-730].
- It uses the manifest only for the take whose `take_uuid` it holds [SFF-867].
- It reads the warnings `camera_dead` with `last_frame` [M8] (7.3). It adds the code of each warning
  of the manifest to `take.warnings` of the state, for example `camera_file_short` and `take_error`
  (T-PLAY-71) ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)).
  `take.warnings` is the list of the player. It is not the take warnings of the reader result of
  SFF-887: the codes of SFF-727 are not warnings of that result (SFF-895) ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
  SFF-895 asks a reader to parse the `detail` of `camera_file_short`. The player does not parse it,
  because it shows no value of it.
- `state` = `recording` makes the take unfinished (6.11) [Y5].
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
- The reader groups the pairs by `take_uuid` [SFF-866]. A pair whose `take_uuid` does not have the
  form of SFF-703 is in no take, and it does not count in SFF-869 [SFF-865, SFF-889]
  ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). When the folder holds more than one take, the
  player opens the first take in the order of `take_uuid` and gives the folder warning
  `multiple_takes` in the state [agent 13].
- A file whose name ends in `.tmp` is ignored. The folder warning `stray_tmp` goes into the state
  [SFF-790].
- Fewer camera files than `group_size`: the take is `incomplete`, with `incomplete_take`, and the other
  files open. More: `extra_files` [SFF-869]. A refused pair counts as present for these counts
  [SFF-869].
- Two camera files with one `camera_label`: `duplicate_label`, and the reader keeps both [SFF-870].
- Sidecars that disagree on a take key: `take_fact_mismatch`; the reader uses the values of the lowest
  `group_position` [SFF-871]. A refused sidecar is not in this check [SFF-871].
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
- The reader finds each column by its name. The format has no reader rule for a missing column. When a
  column that the player needs is missing, the player cannot read the file: it gives `invalid` with
  `missing_metadata`, as SFF-748 does for a missing key [agent 15]. Section 14.2 lists it for the
  merged list.

### 6.6 Rows, the row CRC and the footer

- The reader uses a row only when it ends with LF, has one field for each column and has a correct
  CRC [SFF-744, SFF-746].
- A last line with no LF is torn. It ends the read, and its bytes count in `torn_bytes` [SFF-746,
  SFF-791].
- A complete row with a wrong CRC makes the file `damaged` with `crc_mismatch`. The read stops at that
  row. The rows before it are usable [SFF-746]. Thus the take plays only to the smallest usable count
  [SFF-754]. `damagedAt` is the position of the bad row. The tile of that camera shows
  "damaged at frame N", with that N, from the open, so that the user sees why the take is short [L3]
  [agent 22].
- Each integer of a row has the form of SFF-701, and each integer that is not a time is from 0 to
  2^53 − 1, else the file is `invalid` with `bad_metadata` [SFF-701]. An empty field is allowed where
  the format allows it, also each time and `source_frame_number` of a `missing` row [M3].
- The reader uses the row index as the position. It does not compare the `frame` value with it; the
  format has no reader rule for it [agent 15].
- The reader reads no data row after the first footer line [SFF-746]. A file whose last line is
  `# end` is `finished`. A file with a `# repair` line and `# end` as its last line is `repaired`. Each
  other file is `unfinished` [SFF-747, SFF-795]. When two states apply, the reader gives the first of
  SFF-886. The reader ignores the keys of the `# end` line that it does not need, also `missing=`
  [SFF-709, M3]. SFF-729 makes a reader compare `missing` of the summary with the `# end` line when
  both hold it (skellyfileformat ADR-76NN item 11). The player does not make
  this comparison: it never reads `summary` (6.2) and it gives no `summary_stale` for any member
  (6.13, L2). The full result of 6c makes it ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
- The flags: bit 0 `gap`, bit 1 `filled`, bit 2 `encode_skip`, bit 3 `repeat` and the flag
  `missing`, bit 4 (16) [SFF-756, M3]. A
  usable row with `gap` gives the file warning `gap`; with `encode_skip`, the file warning
  `encode_skip` [SFF-887]. The player shows the frames with `gap`, `filled`, `encode_skip` or
  `repeat` as all other frames.

### 6.7 `missing` rows, placeholders and the short file [M1 to M5, M9]

- A `missing` row is usable when the row is usable [SFF-746]. It counts in `rows` and in
  `missingRows`.
- In a camera file of M1, each row has one block, also a `missing` row: its byte fields point at the
  placeholder [M1, M3]. Each row then has byte fields, so row k belongs to block k [SFF-740].
- In the short file of a killed camera process [M5], and in the short file of a write error on one
  camera file [U2], the late `missing` rows have empty byte fields and no block [SFF-754]. The
  row-to-block rule counts only the rows with byte fields (`byte_offset` and `byte_size`): the j-th
  row with byte fields belongs to the j-th complete block [SFF-740]. The count of SFF-759 compares
  the rows with byte fields with the blocks [SFF-759].
- The reader refuses the file (`invalid`, `bad_metadata`) when a row has one empty byte field and
  one that is not empty, when a row has empty byte fields and no flag `missing`, or when a row with
  byte fields follows a row with empty byte fields (SFF-759;
  skellyfileformat ADR-76NN item 10) ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
- The player never shows a placeholder [M9]. It never decodes the block of a `missing` row. It reads
  the bytes of a placeholder only as part of a range that it checks (6.10).
- A `missing` row keeps its times and `source_frame_number` for a damaged frame that had them, and has
  them empty for a dead camera [M3]. A row with no time has no player time [M3].
- A dead camera's file is never refused because of its `missing` rows or their empty fields.

### 6.8 The time axis [SFF-781] [E8]

- The player time of each row of a camera file is its fitted time, when the sidecar is finished or
  repaired and has a fit that holds each position. Else it is `arrival_ns` for every row of the file
  that has one, and the file gets the warning `missing_fit` [SFF-781]. The reader never mixes the two
  in one file [SFF-781].
- A `missing` row with no `arrival_ns` has no player time [M3]. A `missing` row with an `arrival_ns`
  has a player time by the rule above.
- The reader uses fit lines only of a finished or repaired sidecar [SFF-747]. A sidecar of an
  interrupted repair is `unfinished`, with `fit` false and `missing_fit`, also with fit lines
  [SFF-798].
- A fit whose segments do not hold each position, in order, with no gap and no overlap, is not usable.
  The file then uses `arrival_ns`, with `missing_fit` [SFF-781] [agent 15].
- The fitted time of position p is `t0_ns` + ⌊d × `period_ps` / 1000⌋. d is the difference of the
  source frame numbers of p and `pos_first` when both rows have one, else p − `pos_first` [SFF-777].
  The reader computes it with `BigInt`. `BigInt` division rounds toward zero, so for a negative
  product x the reader rounds down itself: ⌊x / 1000⌋ = (x − (((x % 1000n) + 1000n) % 1000n)) / 1000n
  [SFF-777]. It does not read `fitter_params` and does not change its behaviour for `fitter`
  [SFF-780].
- A file whose `clock` is `synthetic` gets no `missing_fit` [SFF-863].
- The reader parses each time as a `BigInt`. A time or a fitted time with a magnitude of 2^53 or more
  makes the file `invalid` with `bad_time` [SFF-706, SFF-887]. Each other time becomes a JavaScript
  number. The times of the rows are already relative to the take start, so each such number is an
  exact integer [SFF-706] [agent 18].
- The player time of a file never decreases [SFF-782]. The format gives a reader no action when it
  does. The player does not refuse the file. Its search uses the running maximum of the player times
  of the file, so the search stays defined [agent 15].
- Each camera file has its own time base by SFF-781. One camera can use fitted times and another
  `arrival_ns` (14.3).

### 6.9 The camera file head and tail [agent 16] [agent 17]

- Head: the reader reads the first 64 KiB, and more in steps of 64 KiB when the Tracks element ends
  later. It checks the EBML header, DocType `matroska`, one Segment and the Tracks element. It notes
  the number of the video track and the start of the first Cluster. It ignores each Matroska element
  that the format spec does not name [SFF-709].
- The Segment can have an unknown size [SFF-740]. The recorder writes with PyAV (FFmpeg) and
  `cluster_size_limit=1`: while the file is live, and in the file of a killed process, the Segment has
  an unknown size, and each Cluster has a known size, holds one block and has a CRC-32 child element
  (ID `BF`) [recorder spec 6.3]. A Cluster of unknown size is also allowed [SFF-740]. The reader
  handles each of these forms.
- Tail, for a finished or repaired file: the reader reads from the end of the last block that a row
  points at to the end of the snapshot, in reads of 1 MiB. It walks the elements. When it finds a
  SimpleBlock, the rows and the blocks differ, and the file is `invalid` with `bad_metadata`
  [SFF-759]. A repaired file has no normal end and passes [SFF-794].
- The other half of SFF-759 (a block in the middle that has no row) is found when a frame is read
  (6.10). The reader does not walk the whole file at the open: a full walk costs one read for each
  block. SFF-759 allows this order (F-9, section 13).

### 6.10 Reading a frame: trust the CSV, check the block header [SFF-739] [SFF-757] [agent 17]

- The reader takes the byte range of a frame from its row: `byte_offset` and `byte_size` [SFF-757,
  SFF-740, E1].
- It reads one range from the end of the block of the previous row with byte fields to the end of the
  payload of this row. For the first row with byte fields, the range starts at the first Cluster.
- It walks the elements of the range forward. It enters a Cluster (known or unknown size [SFF-740]),
  and it skips each other element of known size: the Cluster Timestamp, the CRC-32 child, a Void
  element, and the placeholder block of a `missing` row. At the
  SimpleBlock of the row, it parses the track number as an EBML variable-size integer, then 2 bytes of
  timestamp, then 1 byte of flags [SFF-739]. It assumes no fixed header length [SFF-739].
- The block is correct when: the track number is the video track; no lacing bit is set [SFF-733]; the
  payload starts at `byte_offset`; and the payload length is `byte_size`.
- Else the rows and the blocks differ: the file becomes `invalid` with `bad_metadata` from then on
  [SFF-759]. The tile keeps its last image with the mark "camera file not readable: bad_metadata"
  [L3], and the player sends an `error` event.
- A block that `ImageDecoder` does not decode: the tile keeps its last image with the mark "damaged at
  frame N" for that frame only, and the next frames show as usual. The player does not read the
  block again in the session ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)) (proposed).
- A frame is the bytes of its block payload [SFF-738]. The reader gives them to the tile unchanged.
- During play, the reader reads one range that holds several frames (9.1). The check above runs for
  each frame of the range.

### 6.11 An unfinished take [Y5]

- A take is unfinished when its manifest has `state` `recording`, or when one or more of its camera
  files is `unfinished`. The player opens it read only, plays the rows and frames that are complete,
  and shows the mark "unfinished" [Y5]. It offers no repair [Y5].
- Where the mark goes [agent 22]: on the tile of each `unfinished` camera file; and on every tile when
  the manifest has `state` `recording`, also when all files are finished. Thus a take whose manifest
  says `recording` gets a take-level mark.
- An unfinished camera file can have no Cues and elements of unknown size [SFF-740]. The reader finds
  its frames from the byte positions of its rows [SFF-740].
- A frame of an unfinished file is usable when its row is usable and its block is complete [SFF-740].
  A block is complete when the end of its payload is not past the snapshot size [agent 12]. The reader
  uses no row after the first row with byte fields whose block is not complete, also no `missing`
  row with empty byte fields, and no block after the last usable row (SFF-740;
  skellyfileformat ADR-76NN item 1). A `missing` row with empty byte fields before that row needs no block, and it is
  a usable frame [SFF-740, SFF-754].
- `torn_bytes` of the pair is the bytes of a torn last line of the sidecar, plus the bytes of the
  camera file after its last complete block when the sidecar has no `# end` line [SFF-791].
- The reader reads each complete record of the snapshot in file order, and it checks that it reached
  the end of the snapshot or a torn record [SFF-791].

### 6.12 Equal rows and the multi-camera frames

- Row k of each video sidecar is multi-camera frame k [SFF-754]. With M1, the camera files of a take
  have equal rows and equal blocks; the short file of a killed process has equal rows and fewer blocks
  [M1, M5].
- When the usable counts differ (an unfinished, damaged or refused file), the multi-camera frames are
  0 to K − 1, with K the smallest usable count of the camera files that the reader reads [SFF-754]. A
  refused file (`invalid`, `unsupported_version`) is not in K, and its tile shows "camera file not
  readable: <reason>" [L3].

### 6.13 The reader model and the reader result [L2]

The state of 4.4 holds, for each camera file and for the take, the members of the reader result that
the player needs, with the names, states, reasons and warning codes of SFF-885 to SFF-887. The reader
does not give the full result of SFF-885 (no `folder_files`, no `links`, no `other_files`, no
`legacy`, no privacy member). The full result and the conformance run come with 6c [L2].

## 7. The master clock and the frame choice

### 7.1 One clock [E1] [E4]

One clock holds the take time t for all cameras. Each tile shows, for its camera, the image that the
rule of 7.3 gives for t. No tile has its own clock. The evidence: a master clock gave a spread of 0
frames on 100 % of ticks at N = 4 and N = 8 in all 28 configurations (index-based, on identical clips)
[M `IP` F19]. One `<video>` element per camera stalled tiles at N = 8 and dropped 6 to 8 % of frames at
N = 4 [M `IP` F21].

### 7.2 Multi-camera frame time and the frame number [agent 19]

- T_k = max(T_(k-1), the largest p_c(k) over the cameras c whose row k has a player time). Thus T_k
  never goes down, also when the camera with the latest times loses its times, and a row where no
  camera has a time gets T_k = T_(k-1). A take starts at the first group frame [M7], so row 0 has a
  time in at least one camera; when it has none, T_0 is the smallest player time of the take.
- At t = T_k, each camera with a player time at row k shows row k or a later row.
- The clock range is [T_0, T_(K-1)].
- k* is state. `seekFrame(k)` and `step(n)` set k* to k (clamped to 0 to K − 1) and t to T_k*. Thus a
  step moves exactly one frame, also when two values of T_k are equal: a step back does not stick and
  a step forward does not skip.
- During play, k* is the largest k with T_k ≤ t, and not below the k* before (two equal T_k cannot
  move it back).
- At open, k* is 0, or the `initialFrame` of the host (F19), and t = T_k*.

### 7.3 The frame choice [SFF-783] [E4] [M9] [agent 20] [agent 21]

For each camera c, at take time t and frame number k*:

- **Image.** The image is the block of the largest real row k < K whose player time is at or before t.
  `missing` rows are not candidates [M9]. For this search, the player times are the running maximum of
  6.8. When two candidate rows have the same player time, the image is the row with the higher
  position. When no candidate exists (t before the first real row), the tile is black [SFF-783].
- **Mark.** When row k* of camera c is a `missing` row, the tile shows the last image with the mark
  "no frame" [Y4, M9, SFF-783], or "camera lost at frame N" when k* ≥ N of a dead camera [Y4, M8,
  SFF-895]. For a dead camera from N on, "camera lost at frame N" is the text of the "no frame" mark
  of SFF-783: the tile shows one mark, not two ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
- The player never computes a frame from its index and the frame rate [SFF-783].
- The image depends only on t and the mark only on k*, not on the history of the tile.

During play, cameras with different times can make the mark change one display refresh before or after
the image. This is a known effect of a mark from k* and an image from t (14.3).

Dead camera [M8] [agent 21]:

- With a finished manifest that the reader uses: a camera with a warning `camera_dead` is dead. The
  `detail` of the warning is `last_frame=<p> reason=<text>` [SFF-727, SFF-895]. p is the last
  row of the camera that is not `missing`. N = p + 1, the first group frame with no image [M8]. When p
  is `none`, N = 0. A `detail` that does not have this form gives the rule of the next item for that
  camera [agent 21], and the warning `camera_dead` with no frame number [SFF-895]. The take warnings
  of the player hold the code of each manifest warning, so they hold `camera_dead` in each case
  ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)). They are
  the list of the player, not the reader result of SFF-887 (6.2).
- With no manifest that the reader uses, or with a manifest whose `state` is `recording` (it has no
  warnings yet): a camera whose rows are `missing` from one row to the last row of the file is dead.
  N is the first row of that run.
- With a finished manifest and no `camera_dead` for a camera, a run of `missing` rows at the end is
  not a dead camera: the mark is "no frame". This is the case of damaged frames at the end, and of
  the short file of a write error, which has `camera_file_short` and `take_error` and no
  `camera_dead` [recorder spec 7.5].

The search is a binary search on integer nanoseconds. The rule is PREV of the evidence: it was exact on
every tick, camera and path (0 mismatches over 456 ticks × 4 cameras, Electron 35.7.5 and 45.2.3) [M
`GF08` §2.1]. PREV never shows a frame from after t, and it has no tie to break in floating-point
seconds [M `GF08` §2.3, §3].

The evidence also suggests a hold limit after the last frame [M `GF08` §3]. SFF-783 has none, and with
M1 every camera has a row to the end of the take. The player has no hold limit.

### 7.4 Play, pause, end and speed [agent 23]

- Play: at each display refresh (`requestAnimationFrame`), t increases by the speed × the elapsed
  `performance.now()` time, in whole nanoseconds.
- Pause: t becomes T_k*, as today (F9) [L4].
- End: when t reaches T_(K-1), play stops at frame K − 1 (F11). With loop on, k* becomes 0, t becomes
  T_0 and play continues (F12).
- Play when k* = K − 1 starts from frame 0 (F9).
- Speed: a rate of F13. At a rate above 1, the tiles can skip frames (9.3).

### 7.5 Seek and scrub [agent 28]

- A drag of the seek bar stops play and calls `seekFrame` for each new value (F14). The release calls
  `seekFrame` again and starts play when play was on before the drag (F14).
- The newest request wins. Each tile has at most one read and decode in flight and one pending target.
  A new target replaces the pending target. There is no queue of old targets.
- When a decode ends, the tile draws it only when no image of a newer request is on the tile. Then it
  starts the pending target, if there is one.
- The tile thus shows images during a drag, and it ends on the image of the last target.

The evidence: a JPEG `ImageDecoder` scrub at 90 frames per second of drag reached the input ceiling of
the harness, about 58 shown frames per second for each tile at N = 4 and N = 8, with a lag of 2 frames
[M `IP` F23].

## 8. The tile [Y3] [L6]

### 8.1 Decode and thread [L6]

- The tile runs on the main thread of the page. It draws on an `HTMLCanvasElement`. It decodes with
  WebCodecs `ImageDecoder` (`type: 'image/jpeg'`) [Y3, L6]. It closes each `VideoFrame` that it does
  not keep, and the decoder after each image.
- Step 4b measures the tile with 8 cameras at 60 fps. The tile moves to a worker only if that
  measurement misses its target [L6].
- The evidence decoded on the page main thread and drew with `requestAnimationFrame` [C
  `scripts/chromium_sync_scrub/harness/harness.mjs` on branch `dom/research`, M `IP` F20]. At N = 8,
  1080p30, `ImageDecoder` used 1.44 cores against 2.14 for `createImageBitmap` (Electron 45.2.3), and
  it kept the scrub rate at the harness ceiling where `createImageBitmap` fell to 49 to 51 [M `IP` F20,
  F23].
- `<video>`, MSE and the WebCodecs `VideoDecoder` cannot play MJPEG [M `CC` C1 to C3, `IP` F13].
- A JPEG with no JFIF or APP0 segment, with no DHT segment, with any marker order, or with bytes after
  the entropy-coded data must decode [SFF-738]. The recorder stores the DHT that the ring inserted
  [M6], so its files hold a DHT in each frame. A JPEG with no DHT decodes in Chrome 156 when its data
  uses the standard tables of ITU-T T.81 Annex K.3 [M review]. T-PLAY-42 checks both cases.
- A corrupted JPEG decodes with no error, with grey pixels [M review]. The tile does not use the
  decode result to find damage [L3].
- The tile ignores an EXIF orientation tag [SFF-738]. It shows the stored pixels unturned and takes
  the rotation only from `rotationCwDeg` (T-PLAY-43). Chromium applies the tag: for orientation 6,
  `ImageDecoder` gives a `VideoFrame` with `rotation` 90, and `drawImage` turns it. `ImageDecoder` of
  Electron 45.3.4 has no option to ignore the tag. Thus the decoder of the tile undoes it: when the
  frame has a `rotation` or a `flip`, it makes `new VideoFrame(frame, {rotation: r, flip})` with
  r = `rotation` when `flip` is true, else (360 − `rotation`) mod 360, and closes the first frame.
  The result has `rotation` 0 and `flip` false [M: orientations 1 to 8, Electron 45.3.4, 2026-11-20,
  [ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)].

### 8.2 Draw and rotation [SFF-751] [E5] [agent 24]

- The canvas backing size is the client size of the canvas × `devicePixelRatio`. It changes with the
  size (`ResizeObserver`), and the tile then draws again from its kept image.
- The tile draws on black (F3). It rotates the image clockwise by the rotation of the update
  [SFF-751, E5], then fits the rotated image into the canvas ("contain") (F3). The stored frame is in
  sensor orientation [SFF-735].
- The tile draws with a 2D context and `drawImage(VideoFrame)` with a canvas transform.

### 8.3 The tile interface [L6] [agent 25] [agent 26]

```ts
class Tile {
  constructor(canvas: HTMLCanvasElement, options?: Partial<TileOptions>);
  update(u: TileUpdate): Promise<'drawn' | 'superseded'>;   // newest wins
  setOptions(o: Partial<TileOptions>): void;
  close(): void;
}

interface TileOptions {
  showLabel: boolean;                        // F7; default true
  timeFormat: 'seconds' | 'timecode';        // F8; default 'timecode'
  texts: TileTexts;                          // English defaults; the host can translate
}

interface TileUpdate {
  jpeg: Uint8Array | null;                   // null: no new image (see below)
  rotationCwDeg: 0 | 90 | 180 | 270;         // display_rotation, or rotation_cw_deg of a ring frame
  label: TileLabel | null;                   // null: no label
  rateText: string | null;                   // the frame rate text of the camera, shown as given
  cameraState: CameraStateName | null;       // the eight states of windows-capture.md 8.1
  mark: TileMark | null;
  image?: DecodedImage;                      // the decoded image of `jpeg`, made ahead (9.1)
  blank?: boolean;                           // true: drop the image and draw black
  detail?: string | null;                    // a small text under the camera part (player-legacy.md 3.4)
}

interface DecodedImage { displayWidth: number; displayHeight: number; close(): void }  // a VideoFrame fits

interface TileLabel {
  frame: number | null;   // k* for the player; the ring frame number for the preview; null: no frame part
                          // (a preview tile before its first frame, specs/preview-4b.md 5.3 rule 5 [Q1])
  frameDigits: number;    // the digits for the leading zeros (F4)
  camera: string;         // camera_label for the player
  timeNs: number | null;  // the time of the shown image, relative to the start; null: no time part
  nominalFps: number;     // for the timecode frame field
  timeEstimated?: boolean; // true: `~` before the time part (player-legacy.md 2.2)
}

type CameraStateName = 'starting' | 'waiting' | 'failed' | 'checking' | 'too_slow'
                     | 'ready' | 'recording' | 'dead';

type TileMark =
  | { kind: 'not_readable'; reason: string }     // L3
  | { kind: 'read_error' }                       // L3
  | { kind: 'damaged'; frame: number }           // L3
  | { kind: 'camera_lost'; frame: number }       // Y4, M8
  | { kind: 'no_frame' }                         // Y4, M9
  | { kind: 'flagged' }                          // L6: the live preview got a flagged frame
  | { kind: 'unfinished' }                       // Y5
  | { kind: 'decoder_failed' };                  // player-legacy.md 8.2
```

- **One input for both callers.** The player and the live preview give the same `TileUpdate`. The tile
  imports nothing of the take reader [L6]. The player fills `label` and `mark`, with `rateText` and
  `cameraState` null; the preview fills `rateText`, `cameraState` and the mark `flagged`.
- **A draw with no new image** (`jpeg` = null): the tile keeps its last image, with its rotation, and
  draws it again with the new label, rate text, camera state and mark. When the tile has no image yet,
  it draws black. Thus a flagged frame of the preview and a `missing` row of the player keep the last
  image and change only the overlay [L6, M9].
- **Back to black** (`blank` true, `jpeg` null): the tile closes its image and draws black with the new
  overlay. The player uses it when no image applies at t, for example after a seek to a frame before
  the first real row of a camera (7.3, T-PLAY-46)
  ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)).
- **An image made ahead** (`image` with `jpeg`): the tile does not decode. It draws `image` at once and
  owns it: it closes it when a newer image replaces it, or at `close()`. The promise resolves with
  `'drawn'`. `jpeg` holds the bytes of the same frame. The player uses it for the images of its
  prefetch queue (9.1); the preview gives `jpeg` only
  ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)).
- **An image with no JPEG** (`image` with `jpeg` null): an update with `image` and `jpeg` null is a
  new image. The tile draws and owns `image` as above. The v1 player gives it, because it has no JPEG
  (`player-legacy.md` 11.3) [Q742 yes] [ADR-EM6A](../decisions/entries/EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md).
- **The detail text** (`detail`): the tile draws it in small type under the camera part of the
  overlay, also when `showLabel` is off, as the rate text. `timeEstimated` puts a `~` before the time
  part [Q742 yes].
- **One mark.** An update has at most one mark. When more than one applies, the player gives the first
  in the order of the type above [agent 25].
- **Newest wins.** A new `update` supersedes an update whose decode has not ended. The promise of the
  superseded update resolves with `'superseded'`; the promise of a drawn update resolves with
  `'drawn'` after the draw. The preview uses the second as its signal after each draw
  (`specs/preview.md` section 11).
- **No read back** (2026-11-20,
  [ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)): the
  product never reads a tile canvas back (`getImageData`, `toDataURL`, `toBlob`, `readPixels`). After
  10 s of `getImageData` reads of the tile canvases at N = 8, play fell from 57 to 20 display
  refreshes per second and from 100 % to 0 % correct tiles, and it stayed there after the reads
  stopped (the 0 % of the first T-PLAY-66 runs). A test reads tile pixels only to check them.
- **One place.** Rotation, the label text, the rate text, the camera state and the marks are drawn only
  in `tile/` [Y3]. The callers give raw values; the tile formats them (8.4).

Texts (English defaults; `texts` can replace each) [agent 26]:

| Item | Text |
|---|---|
| `not_readable` | "camera file not readable: <reason>" |
| `read_error` | "read error" |
| `damaged` | "damaged at frame N" |
| `camera_lost` | "camera lost at frame N" |
| `no_frame` | "no frame" |
| `flagged` | "flagged frame" |
| `unfinished` | "unfinished" |
| `decoder_failed` | "decoder failed" |
| each camera state | the state name, for example "too_slow" |

### 8.4 The label and the overlay [E6] [agent 24]

The tile draws the overlay in the canvas, from the fields of the update [E6]. The take holds no
overlay [SFF-737].

| Part | Place | Value |
|---|---|---|
| Frame | top right | `F` and `frame` with leading zeros to `frameDigits` digits (F4); none when `frame` is `null` |
| Camera | bottom left | `camera` (F5) |
| Time | bottom right | `timeNs` as seconds with 3 decimals (`1.234s`), or as `HH:MM:SS:FF`, with FF = ⌊fraction of the second × `nominalFps`⌋ (F6, F8) |
| Rate text | under the camera part | `rateText` as given |
| Camera state | top left | the state text |
| Mark | middle, clearly visible | the mark text (Y4) |

- `showLabel` turns the frame, camera and time parts on or off (F7). The rate text, the state and the
  mark stay visible.
- The overlay has a fixed size in CSS pixels.
- The canvas `title` is "timestamp from recording" while the time part shows (F6).
- The tile keeps the text of its last overlay, so that a test can read it.
- For the player: `frame` = k*, `frameDigits` = the digits of K, `camera` = `camera_label`, `timeNs` =
  the player time of the image row, `nominalFps` = the nominal rate of the camera.
- `nominalFps` of the player state, for "Rec: fps", is the nominal rate of the camera with the lowest
  `group_position`, rounded to 3 decimals as SFF-728 rounds `nominal_fps` [agent 30].

### 8.5 One tile, one place [Y3]

The player calls the tile. The live preview of phase 4 calls the same tile [Y3, L6].

### 8.6 Agreement with the step 4a spec

`specs/preview.md` on branch `dom/preview`, section 11, lists what phase 4 needs. This spec gives each
item:

| Need of phase 4 | Here |
|---|---|
| A live source, without the take reader | `Tile.update` takes JPEG bytes; the tile imports nothing of `reader/` (8.3) |
| A frame rate text for each camera | `rateText` (8.3, 8.4) |
| The camera state, each of the eight states | `cameraState` (8.3, 8.4) |
| A flagged-frame mark that keeps the last image | `jpeg` = null with the mark `flagged` (8.3) |
| A rotation for each frame | `rotationCwDeg` of each update (8.2) |
| The main thread, `ImageDecoder`; a worker only if 4b misses its target | 8.1 |
| A signal after each draw | the promise of `update` resolves with `'drawn'` (8.3) |

The live view of today decodes with `createImageBitmap` on a worker and draws with a bitmap renderer on
an offscreen canvas [C `frame-decode.worker.ts`, `offscreen-renderer.worker.ts`]. `PLAN` §5 states the
same. By Y3 and L6, phase 4 changes it to this tile.

## 9. Prefetch, back-pressure and memory [agent 27] [agent 28]

### 9.1 Prefetch during play

- Each camera has a queue of decoded images ahead of t. The player decodes them with its decoder
  (`ImageDecoder` by default, with the orientation rule of 8.1). It gives each image to the tile in
  `TileUpdate.image`, with its JPEG bytes in `jpeg`, so that the tile draws it in the same display
  refresh with no decode (8.3)
  ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)). The queue
  holds at most
  min(8, max(2, ⌊64 / N⌋)) images, with N the number of cameras. The evidence used 8 decoded frames
  ahead for each camera at N = 4 and N = 8 [C `harness.mjs` `JpegPlayer`, M `IP` F19, F20].
- Each camera has at most one range read in flight. One read holds the frames that the queue needs, up
  to 4 MiB. The queue holds only real rows; it skips `missing` rows [M9].
- After a seek, the queue is emptied, and each image in it is closed.

### 9.2 Back-pressure

- A tile never draws an image of an older request after an image of a newer request (7.5).
- During play, at each display refresh, the player gives the tile the image of the queue with the
  largest position at or before the chosen row, and closes the older images of the queue. A tile never
  shows an image older than the image on it, except after a seek back.

### 9.3 Speed above 1

At a rate above 1, the prefetch reads only the rows that the clock chooses at the next display
refreshes, at the current rate. It skips the rows between them. The cost at 8 times is not measured
(M-PLAY-7).

### 9.4 Memory limits

- Decoded images held at one time: at most the queue limit + 1 (kept by the tile) + 1 (in decode) for
  each camera, so at most 64 + 2N for the take.
- Each `VideoFrame` is closed when it leaves the queue or the tile. `close()` of the player closes each
  image, each decoder and each file.
- The evidence: a working set of 987 MB at N = 8, 1080p30, with `ImageDecoder` and 8 frames ahead
  (Electron 45.2.3) [M `IP` F20].

## 10. Host integration in skellycam-ui [L1] [L4] [L5] [agent 31]

- The player of today does not change [L5].
- The new host view is `src/components/playback/CanvasTakePlayer.tsx`. It uses `PlaybackControls.tsx`
  of today as it is [L5], and it does not show the sync information warning of F16 [L4]. For this,
  `PlaybackControls` gets one optional prop `hideSyncInfo`. The player of today does not give it, so
  the player of today does not change. `CanvasTakePlayer` gives `hideSyncInfo` true [U3]. No other
  change of the player of today [L5]. It holds its
  own grid with the behaviour of F1 to F3 and its own keys with the behaviour of F9 to F12 and F20. It
  does not import code from `SyncedVideoPlayer.tsx`.
- The route [L1]: when the user opens a recording, the UI calls `electronTakeFiles(path)` and
  `isTakeFolder(files)` before any backend video call. A folder in the new format opens in
  `CanvasTakePlayer`; each other folder opens in the player of today. The rest of the switch is step
  6c [L1].
- The backend playback list of the recorder spec shows a new-format take with `needs_new_player: true`,
  and its video endpoints give HTTP 409 [recorder spec 10, item 13]. The recording browser shows the
  mark as information only. The mark never stops the UI from opening the take in the new player.
- The loading message (F18) counts the cameras whose first image is drawn, and each camera whose tile
  got a mark or black (a refused file, no real row at t, no frame) ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
- A take of the new format in a folder that the handler refuses (L7) does not go to the player of
  today. The recording browser tells the user to open the folder with the folder dialog and shows a
  button that opens it ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)).
- The host gives `initialFrame` and gets `frame` events for F19.

## 11. Performance

### 11.1 Versions that the evidence measured

- Electron 35.7.5 with Chromium 134.0.6998.205, Electron 45.2.3 with Chromium 156.0.8078.80, and Chrome
  156 (functional runs only) [M `IP` header, `RT` header].
- One Windows 11 machine: Intel i7-14700K, NVIDIA RTX 3070 (the active Chromium GPU), Intel UHD 770
  present and not used [M `IP` header].
- skellycam-ui pins Electron 45.3.4 [C `package.json`]. The review ran its experiments in Electron
  45.3.4 (Chrome 156) and Node 24.15 [M review]. The timing results on 45.3.4 are [NV].
- The CI pins Node 26.13.1 (12.6). Nobody ran the module or its tests on Node 26.13.1 [NV].

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

Limits: the timed JPEG clips were `mjpeg_qsv` re-encodes of about 207 kB, not camera bytes; the bench
read them from a local HTTP server in the Electron main process, not through `protocol.handle`; one
run for each configuration; a warm page cache [M `IP` §3.3, §5]. The JPEG timing on camera bytes is
[NV] [M `IP` §6].

### 11.3 Targets of 6a (to verify with the benchmarks) [agent 36]

| Case | Target | Benchmark |
|---|---|---|
| N = 8, 1080p30, speed 1, 60 s | After 1 s, in 99 % of display refreshes or more, each tile shows its chosen image; Electron CPU at most 2.0 cores; working set at most 1.5 GB | T-PLAY-66 |
| N = 4, 1080p30 | Seek: all tiles drawn, p50 at most 10 ms, p95 at most 33 ms | T-PLAY-67 |
| N = 8, 1080p30, drag at 90 frames/s, input each 16 ms | At least 50 shown frames/s for each tile | T-PLAY-68 |
| Transport, 16 × 60 fps × 150 kB, 60 s | At most 0.5 % dropped ticks | T-PLAY-65 |
| Main process during the transport case | IPC round trip p95 at most 50 ms | T-PLAY-69 |

Step 4b measures the tile with 8 cameras at 60 fps for the live preview [L6]. That measurement is not
part of 6a.

### 11.4 Not measured

720p60; 16 cameras of playback (the transport only was measured at 16); the cameras' own JPEG bytes
(timed); Linux and macOS; timing on Electron 45.3.4; speed above 1; takes longer than 600 frames; a
cold disk; a low-end laptop; a file that a writer still writes; real clock alignment across cameras
(GF08 aligned the clocks by construction) [M `GF08` §3, `IP` §6, `RT` §5].

## 12. Tests

### 12.1 Kinds and runners [agent 34]

- **unit**: the reader, the clock, the frame choice, the scheduling and the `TakeFiles` check suite on
  the Node implementation. No browser. Node with `node --test --experimental-strip-types`, as the
  existing test `tests/graceful-python-shutdown.test.mjs` [C `package.json` `test:recording-shutdown`].
  The decoder and the time source are test doubles.
- **component**: the tile and the player in Electron 45.3.4, with the real `ImageDecoder` and canvas.
  `@playwright/test` 1.65.1 starts a test Electron app (`tests/harness/`) with `_electron.launch`. A
  test Vite config builds the harness page and the harness main process. The tests of the host view are
  in `skellycam-ui/src/components/playback/tests/` and use the same runner.
- **electron**: the handler, in the same test Electron app, with real files. The harness gives
  `installTakeHandler` a temporary `recordingsFolder` and `pickedFoldersFile`. It has two test-only
  hooks: one records a dialog pick, one makes the reads of one path fail.
- **benchmark**: timed runs on the Windows test machine, started by hand. They record results and
  compare them with the targets of 11.3. They do not run in CI.

Today: the UI has one Node test (`test:recording-shutdown`) and one Playwright example
(`e2e/example.spec.ts`). No UI test runs in CI [C `.github/workflows/`].

npm scripts: `test:player:unit` and `test:player:browser`. No new npm package is needed.

### 12.2 Fixtures [Y7] [agent 32]

- The fixture builder is TypeScript in `skellycam-ui/src/player/tests/fixtures/`. It runs in Node. Each
  test builds its takes at run time in a new temporary folder below the test `recordingsFolder` and
  deletes it after the test. No take, JPEG or MKV goes into the repository.
- It writes the files from the format spec and M1 to M10: the MKV of section 6 (EBML header, Segment,
  Info, Tracks with one `V_MJPEG` track, Clusters, one JPEG per SimpleBlock); the sidecar of sections 7
  and 8 with the row CRC (`zlib.crc32` of Node), the flag `missing`, fit lines and the `# end` line
  with `missing=`; and the manifest of section 5 with the warning `camera_dead` and `last_frame`. It
  does not use the recorder code, so the tests check the recorder and the player against the spec, not
  against each other.
- Synthetic JPEGs: the flat-block encoder of 12.2.1. A row of blocks is a barcode of the camera index
  and the position. Four quadrants of four colours show the rotation. Options: the sampling factors;
  no DHT segment (the data still uses the Annex K tables, so it decodes [M review]); the DHT inserted
  before the first SOS, as the ring does [M6]; no APP0 segment; an EXIF orientation tag; bytes after
  the EOI.
- Placeholders [M2]: for each camera file, one black JPEG from the same encoder, with the width, the
  height, the component count and the sampling factors of the SOF segment of the first frame of that
  camera that is not `missing`, made once and written for each `missing` row [F-1 of the recorder
  spec].
- The MKV of the fixtures `unfinished`, `dead_short` and `write_error_short` has the form that FFmpeg
  writes live (6.9): a Segment of unknown size, and one Cluster of known size for each block, with a
  CRC-32 child. The other fixtures have a finished file with known sizes. One `block_*` fixture has a
  Cluster of unknown size.
- A Node implementation of `TakeFiles` (`tests/fixtures/node-take-files.ts`) reads the temporary folder
  for the unit tests.
- The benchmarks make larger JPEGs at run time with the JPEG encoder of Chromium
  (`OffscreenCanvas.convertToBlob`, quality 0.9) from a noise pattern with a barcode, about 190 kB at
  1080p, near the 192,382 B mean of the C922 at 1080p [M `IP` §3.3] [agent 33].

The takes that the builder makes:

| Fixture | Content |
|---|---|
| `normal` | 4 cameras × 120 rows at 30/1, finished, fit lines, a manifest, rotation 0, 4:2:2 |
| `offsets` | 4 cameras with different arrival offsets (0, +7.65 ms, −3 ms, +19.9 ms) and jitter, and two rows 11 µs apart, after `GF08` §1.1 |
| `missing` | `normal` with damaged frames in camera 1 at rows 0, 10 and 40 to 59: `missing` rows with placeholders, times kept at rows 10 and 40 to 59, no time at row 0; `missing=22` |
| `dead` | `normal` with camera 2 dead after row 69: placeholders and `missing` rows with no time from row 70 to 119; the manifest warning `camera_dead` with `last_frame` 69; `missing=50` |
| `dead_no_manifest` | `dead` with no manifest |
| `dead_short` | `normal` with camera 3 from a killed process: 80 blocks in the MKV; rows 80 to 119 `missing` with empty byte fields and no time; a `# repair` line and a `# end` line; the manifest warnings `camera_dead` (`last_frame=79 reason=hang`) and `camera_file_short` (`blocks=80 rows=120`) |
| `write_error_short` | as `dead_short`, for a write error on the file of camera 3: the manifest warnings `camera_file_short` and `take_error`, and no `camera_dead` [U2] |
| `trailing_damage` | `normal` with a manifest, no `camera_dead`, and camera 1 `missing` (with times) from row 115 to 119 |
| `unfinished` | manifest `state` `recording`; no `# end`; usable counts 120, 97, 120 and 110: camera 1 with its last blocks cut in the MKV after row 96, camera 3 with a torn last line after row 109 |
| `recording_finished` | manifest `state` `recording`; each sidecar finished |
| `no_manifest` | `normal` with no manifest; `bad_manifest_*`: not JSON, not a manifest, another `take_uuid` |
| `bad_crc` | `normal` with a wrong CRC in row 50 of camera 1 |
| `rotations` | 4 cameras with `display_rotation` 0, 90, 180 and 270 |
| `no_fit` | `normal` with no fit lines in camera 2; and a fit that does not hold each position |
| `fit_negative` | a fit segment in which a source frame number is below that of `pos_first` (a negative d) |
| `header_*` | one changed sidecar each: leading zero, `+` sign, a `take_uuid` with dashes, row integer 2^53, rate 0/1 and 2^20 + 1, rotation 45, bad label, missing key, missing column, unknown clock, major 3, minor 1 with an unknown key, column and flag bit 7, prerelease 0 and 1, a time of 2^53, a `frame` value that is not the position, a time that decreases |
| `block_*` | a payload offset that is wrong by 1; an extra block in the middle; a block with a lacing bit; an extra block after the last row; a 2-byte track number and 8-byte sizes; a Void element and a Cluster start between two payloads |
| `jpeg_forms` | JPEGs with no DHT, with an inserted DHT, with no APP0, with an EXIF orientation 6, with 1 KiB of bytes after the EOI |
| `pairs` | a lone MKV, a lone sidecar, a sidecar with no mark, a `.tmp` file, an audio pair, two takes |
| `counts` | fewer and more camera files than `group_size`, a duplicate label, a take key that differs |

#### 12.2.1 The flat-block JPEG encoder [agent 32]

The recorder spec uses this description as the model of its placeholder, so it is exact:

- Markers in this order: SOI; optional APP1 (EXIF, only for the EXIF option); one DQT segment with two
  8-bit tables, table 0 (Y) and table 1 (Cb and Cr), each with all 64 entries equal to 16; SOF0
  (baseline sequential DCT, sample precision 8); one DHT segment with the four tables of ITU-T T.81
  Annex K.3 (DC luminance as class 0 id 0, AC luminance as class 1 id 0, DC chrominance as class 0 id
  1, AC chrominance as class 1 id 1), left out by the option "no DHT"; SOS; the entropy-coded data;
  EOI. No APP0, no DRI, no restart marker.
- SOF0 holds the height, the width and the components: either 1 component (id 1, Y) or 3 components
  (ids 1, 2 and 3: Y, Cb, Cr). Each component has its own H and V from 1 to 4, with the sum of H × V
  over the components at most 10 (T.81 B.2.2); the Y component uses quantisation table 0, Cb and Cr use
  table 1. The fixtures use Y 1x1, 2x1 and 2x2 with Cb and Cr 1x1 (4:4:4, 4:2:2 and 4:2:0), and 1
  component.
- SOS holds all components of SOF0, in SOF0 order (interleaved), with Y on DC table 0 and AC table 0,
  Cb and Cr on DC table 1 and AC table 1; Ss = 0, Se = 63, Ah = Al = 0.
- The image is padded to whole MCUs. Each 8 × 8 block holds one flat value v (0 to 255) for its
  component, so its DC coefficient is (v − 128) × 8 / 16, rounded to the nearest integer, and each AC
  coefficient is 0. The encoder codes each block as the DC difference from the previous block of the
  same component (Annex F.1.2.1), then the AC code 0x00 (EOB). It inserts a 0x00 byte after each 0xFF
  byte of the data, and pads the last byte with 1 bits.
- A black placeholder has Y = 0 and Cb = Cr = 128 in each block (Y only for 1 component).

### 12.3 Test list

| ID | Kind | What it does | Pass criterion |
|---|---|---|---|
| T-PLAY-01 | unit | Build `normal` and `missing`, then parse them back with an independent small parser in the test. | One `V_MJPEG` track; one SimpleBlock per row at the CSV offsets; each row CRC is the zlib CRC-32 of its bytes; each JPEG starts with SOI and ends with EOI; the SOF of each placeholder has the size and the sampling factors of the first frame of its camera; `missing=` equals the count of `missing` rows. |
| T-PLAY-02 | unit | Open `normal` through the manifest. | 4 cameras in `group_position` order; each pair from `cameras[]`; `manifest` `present`; no warning except `prerelease`. |
| T-PLAY-03 | unit | Open `no_manifest`. | The same 4 cameras by a scan; `manifest` `missing`; take warning `manifest_missing`. |
| T-PLAY-04 | unit | Open the three `bad_manifest_*` takes. | `manifest` `invalid`; a rebuild by scan; `manifest_missing`. |
| T-PLAY-05 | unit | `counts`: a manifest path to a deleted sidecar; 3 of 4 files; 5 files for `group_size` 4; one refused pair of 4. | `incomplete` with `incomplete_take`; `extra_files`; the refused pair counts as present, is not in K, and gets the mark "camera file not readable". |
| T-PLAY-06 | unit | Open `pairs` with a recording spy on `TakeFiles`. | The lone MKV is not in the take; the lone sidecar is `invalid` with `missing_media` and not counted; a sidecar with no mark is ignored; no read of the `.m4a` file. |
| T-PLAY-07 | unit | Open `pairs` with two takes and a `.tmp` file. | The first take in `take_uuid` order opens; warnings `multiple_takes` and `stray_tmp`; the `.tmp` file is not read. |
| T-PLAY-08 | unit | Open each `header_*` form fixture. | `invalid` with the reason of 6.5 for each: `bad_metadata`, `bad_rate`, `bad_rotation`, `bad_label`, `missing_metadata` (also for the missing column); the other cameras open. A `take_uuid` with dashes: the pair is in no take and does not count, so 3 cameras and `incomplete_take` [SFF-865, SFF-869, SFF-889]. |
| T-PLAY-09 | unit | Open the version fixtures, and `normal` with one row flagged `gap` and one flagged `encode_skip`. | Major 3: `unsupported_version`, reason null; minor 1: reads with the unknown key, column and flag bit; prerelease 1: warning `prerelease`; prerelease 0: no warning; the flagged rows give the file warnings `gap` and `encode_skip`, and their images are chosen as other images. |
| T-PLAY-10 | unit | Times of 2^53 − 1 and of 2^53; `take_start_host_ns` above 2^53. | 2^53 − 1 reads exactly; 2^53 gives `invalid` with `bad_time`; the large take start parses as `BigInt` with no loss. |
| T-PLAY-11 | unit | Open `bad_crc`. | Camera 1 `damaged`, `crc_mismatch`, `rows` 50, `damagedAt` 50; K = 50; the other cameras have 120 usable rows. |
| T-PLAY-12 | unit | Camera 3 of `unfinished` (torn last line). | The torn row is not used; `torn_bytes` includes its bytes; state `unfinished`. |
| T-PLAY-13 | unit | Footer cases: rows after `# end`; a `# repair` line with `# end` last; a `# repair` line with no `# end`. | No row after the first footer line; `repaired`; `unfinished`. |
| T-PLAY-14 | unit | `normal` with two fit segments, a source frame gap and a `period_ps` with a remainder; `fit_negative`. | Each fitted time equals an independent `BigInt` computation of SFF-777 with floor division, also for the negative d; a change of `fitter` changes nothing. |
| T-PLAY-15 | unit | `no_fit` and the `unfinished` takes; a sidecar with `clock` `synthetic` and no fit. | Arrival times for the whole file, `missing_fit`, `fit` false; with fit lines in an unfinished file still arrival times; `synthetic`: no `missing_fit`. |
| T-PLAY-16 | unit | The `header_*` fixtures with a wrong `frame` value and with a decreasing time. | Neither file is refused; the position is the row index; the search over the decreasing file uses the running maximum and gives the same image as a reference that uses it. |
| T-PLAY-17 | unit | Open `missing`; choose at the frame numbers 0, 9, 10, 40, 59 and 60 (t = T_k), with a spy on the reads and the test decoder. | The `missing` rows are usable and counted; each maps to its placeholder block; no placeholder is decoded; at k* = 10 the image is row 9 and at 40 to 59 row 39, each with "no frame"; at k* = 0 the tile is black with "no frame"; at 60 the image is row 60 with no mark. |
| T-PLAY-18 | unit | Open `dead`. | Camera 2 is not refused; `deadFrom` = 70 from the manifest; for k* ≥ 70 the image is row 69 and the mark "camera lost at frame 70"; T_k for k ≥ 70 comes from cameras 0, 1 and 3; K = 120. |
| T-PLAY-19 | unit | Open `dead_no_manifest` and `trailing_damage`. | `dead_no_manifest`: `deadFrom` = 70 from the run of `missing` rows at the end; `trailing_damage`: no dead camera, the mark at rows 115 to 119 is "no frame". |
| T-PLAY-20 | unit | In `missing`: row 10 (a `missing` row with a time) and row 0 (with no time), against a reference; a variant in which no camera has a time at one row. | T_10 uses the time of camera 1 at row 10; T_0 ignores camera 1; at the row with no time T_k = T_(k-1); images as T-PLAY-17. |
| T-PLAY-21 | unit | Open `dead_short`; also a copy whose `camera_dead` has `last_frame=none`. | Camera 3 is `repaired` and not refused; rows 80 to 119 have no block; the SFF-759 count compares 80 rows with byte fields and 80 blocks and passes; the unknown-size Segment and the CRC-32 children are read; `deadFrom` = 80 from `camera_dead`; with `none`, `deadFrom` = 0. |
| T-PLAY-22 | unit | Open `unfinished`. | Usable counts 120, 97, 120 and 110; K = 97; T_k and k* only to 96. |
| T-PLAY-23 | unit | Open `unfinished` and `recording_finished`. | `take.unfinished` true in both; camera 1 uses no row with byte fields after its last complete block; `torn_bytes` adds the bytes after that block; no file is written. |
| T-PLAY-24 | unit | Open `normal` with a `TakeFiles` whose snapshot sizes are smaller than the files: half of the last block and 2 rows are past the snapshot. | The rows and the block past the snapshot are not used; the file is read as unfinished. |
| T-PLAY-25 | unit | Read each frame of `block_*` with a 2-byte track number and 8-byte sizes. | Each payload equals the JPEG that the builder wrote; no fixed header length is used. |
| T-PLAY-26 | unit | Read the frames around a Void element, a Cluster start, a placeholder block and an unknown-size Cluster. | Each payload is correct. |
| T-PLAY-27 | unit | `block_*`: a wrong offset; an extra block in the middle; a laced block; an extra block after the last row; a Cues tail. | Wrong offset, middle block and laced block: `invalid` with `bad_metadata` at the read of that frame, and an `error` event; extra block at the end: `invalid` at the open; Cues tail: passes. |
| T-PLAY-28 | unit | A camera file with no EBML magic. | Not a device pair; the sidecar is `invalid` with `missing_media`. |
| T-PLAY-29 | unit | Frame choice on fixed lists: each exact time, 1 ns before and after, equal times, before the first real row, after the last. | The largest real row with p ≤ t; equal times give the higher position; before the first real row, black; no use of index × rate (a list with irregular times proves it). |
| T-PLAY-30 | unit | T_k on `offsets` with two equal values of T_k; `step(±1, ±10)`, also at both ends and across the equal values. | T_k as 7.2; each step moves k* by exactly the step; no stick and no skip at the equal values; steps clamp to 0 and K − 1. |
| T-PLAY-31 | unit | The clock with a scripted time source: play at each rate of F13, end with loop off and on, play at the last frame, pause. | t advances by rate × elapsed time; stop at frame K − 1; loop to frame 0; play at the end starts from frame 0; pause sets t = T_k*. |
| T-PLAY-32 | unit | 100 seeks within 200 ms to one tile, with a test decoder of random delay 1 to 30 ms. | At most one decode in flight; after the last decode, the tile shows the last target; no draw of an older request after a newer draw. |
| T-PLAY-33 | unit | Play at rates 1 and 8 with a slow test decoder. | The drawn position never goes down during play; each image that is not drawn is closed. |
| T-PLAY-34 | unit | `offsets` and `missing`: 456 fixed ticks in a shuffled order (exact times, midpoints, ±1 ns, ±1 ms, inside `missing` runs, at the start, at the end), after `GF08` §1.4. | Each image and each mark equal a brute-force reference written independently in the test. |
| T-PLAY-35 | unit | Scan the imports of each file of `src/player/` and each import of a module file from the rest of `src/`; load each module file outside `main/` under Node type stripping. The files of `main/` import `electron`, which does not load under Node: the Electron harness loads them, and T-PLAY-55 to T-PLAY-64 use them. | Only the imports of 4.2; each type import is `import type`; each file outside `main/` loads; the rest of the UI imports only `index.ts` and the two files of `main/`. |
| T-PLAY-36 | unit | `counts`: a duplicate label; a take key that differs in camera 2. | `duplicate_label` and both kept; `take_fact_mismatch` and the values of `group_position` 0. |
| T-PLAY-37 | unit | The overlay text of `tile/format.ts`: `frameDigits` 1, 3 and 5; times 0.0334 s and 3,725.5 s; rates 30 and 29.97; both formats; `timeNs` null. | `F` with 1, 3 and 5 digits; `0.033s` and `3725.500s`; timecode `00:00:00:01` and `01:02:05:15` (14 at 29.97); no time part for null. |
| T-PLAY-38 | unit | N = 4 and N = 16 with a counting test decoder; play, seek and close. | Open images never exceed min(8, max(2, ⌊64/N⌋)) + 2 for each camera; 0 open images after `close()`. |
| T-PLAY-39 | unit | The shared `TakeFiles` check suite on the Node implementation: entries, sizes, `readRange` at the start, the middle and the end, a range past the snapshot, `readWhole` with a limit, a path not in the entries. | Each result as 5.1 [L8]. |
| T-PLAY-40 | component | A bare page with only `Tile` (no host code, no reader): one update with a barcode JPEG. | The canvas pixels of each block equal the block colour within ±8 levels; the promise resolves with `'drawn'`. |
| T-PLAY-41 | component | `rotations`: draw each camera. | The quadrant colours are at the upright corners for 0, 90, 180 and 270. |
| T-PLAY-42 | component | `jpeg_forms`: no DHT (Annex K data), inserted DHT, no APP0, bytes after the EOI. | Each decodes; pixels as T-PLAY-40. |
| T-PLAY-43 | component | `jpeg_forms`: EXIF orientation 6 with rotation 0. | Drawn as stored, not rotated. |
| T-PLAY-44 | component | Label on and off; seconds and timecode; the canvas title. | The kept overlay text changes as T-PLAY-37; with the label off, no frame, camera or time text; the title is "timestamp from recording" while the time shows. |
| T-PLAY-45 | component | `Tile` alone: an image, then updates with `jpeg` null and each of the eight camera states, a rate text, the mark `flagged` and no mark; then two quick updates. | The image pixels stay; only the overlay changes; each state text shows; the first of the two quick updates resolves `'superseded'`, the second `'drawn'` [L6]. |
| T-PLAY-46 | component | Player on `missing`: seek to rows 9, 10, 40 to 59 and 0. | The barcode shows row 9 or 39 with "no frame"; the placeholder is never drawn; at row 0 black with "no frame" [M9]. |
| T-PLAY-47 | component | Player on `dead` and `dead_no_manifest`: seek to rows 69, 70 and 119. | Row 69 normal; rows 70 and 119 show the image of row 69 with "camera lost at frame 70", in both takes. |
| T-PLAY-48 | component | `unfinished` and `recording_finished`: open and play to the end. | "unfinished" on the tiles of the unfinished files; on every tile of `recording_finished`; play ends at K − 1. |
| T-PLAY-49 | component | `offsets` and `missing`: the 456 ticks of T-PLAY-34 through `seekFrame` and the clock, with the Electron `TakeFiles` and the real handler, waiting for each draw. | The barcode and the mark of each tile equal the reference for each tick. |
| T-PLAY-50 | component | `normal`: play 3 s at 1, pause, play to the end, loop on for one more pass. | After the pause, t = T_k* and each barcode equals the choice; the end stops at K − 1; loop starts again from frame 0. |
| T-PLAY-51 | component | Host view `CanvasTakePlayer` with today's `PlaybackControls`: each button, each key of F9 to F12, Shift steps, a key while the seek bar has the focus, a key in a text input, each speed, a seek drag and release while playing. | Each command changes the state as F9 to F15 and F17 give; keys do nothing while an `<input>` has the focus; the sync warning button is not shown [L4]; the drag shows images and the release resumes play. |
| T-PLAY-52 | component | Host view grid: 1, 4 and 9 cameras; manual columns 2; reset; drag tile 1 onto tile 3. | Auto tiling as today; 2 columns; reset restores the layout; tiles 1 and 3 swap. |
| T-PLAY-53 | component | Host view: `initialFrame` 50; play 2 s; the loading message; an empty camera list; the route with a folder of today's format and a take folder. | The first draw is at frame 50; `frame` events at most 5 per second; the loading count; the empty state; the old folder opens in today's player and the take in the new one [L1]. |
| T-PLAY-54 | component | `bad_crc`; `counts` with a refused pair; the read fault hook on camera 3 of `normal` during play. | "damaged at frame 50" on camera 1 from the open; "camera file not readable: <reason>" on the refused camera; "read error" on camera 3 with its last image; the other tiles keep playing [L3]. |
| T-PLAY-55 | electron | The range matrix of 5.6 on a file of 1 MiB whose snapshot size is 512 KiB (512 KiB appended after the open): no range, `a-b` inside, `a-b` across the snapshot end, `a` at the snapshot size, a suffix range, an open end, two ranges, a malformed range, a POST. | Status, bytes and headers as 5.6; no byte at or above the snapshot size is served. |
| T-PLAY-56 | electron | 640 reads of 150 kB at concurrency 16, default session cache. | 0 failed reads [M `RT` §8 item 2]. |
| T-PLAY-57 | electron | Requests that try to leave the folder: `..`, `%2e%2e`, `\`, an absolute path, a file in `annotated_videos/`, a name not in the list, a link to a file outside (a junction to a folder on Windows; a file link on Linux and macOS), a token in upper case, a closed token. | No byte of a file outside the allow-list reaches the page; each such request gets 404 or reads an allowed file; the token is 32 lower-case hexadecimal characters. |
| T-PLAY-58 | electron | During an open take: append 1 MiB to a camera file; replace the manifest by a rename (as `os.replace`); delete a camera file after its first read; delete another camera file before its first read. | The append: reads within the snapshot unchanged; the rename succeeds on each system; the first deleted file stays readable; the second gives a read error. |
| T-PLAY-59 | electron | A test variant of the handler answers 200 with the exact length, 200 with the whole file, and 206 with a wrong `Content-Range` start. | The page client accepts only the first; the two others are read errors. |
| T-PLAY-60 | electron | A sparse file of 5 GiB; read 3 ranges past 4 GiB. | The bytes equal the bytes that the test wrote at those offsets. |
| T-PLAY-61 | electron | Open `normal`, play it to the end, seek 50 times, close. | Each file of the folder has the same bytes and modification time as before [SFF-799]. |
| T-PLAY-62 | electron | Open a folder outside the test `recordingsFolder` and not picked; the page calls each bridge and IPC channel of the module with that folder; the same folder after the test hook records a dialog pick; a folder inside the `recordingsFolder`; a link inside the `recordingsFolder` to an outside folder. | Refused with "folder not allowed" and no token, also after the page calls (the list file does not change); allowed after the pick, also after a restart of the harness (the list file); allowed inside; the link is refused [L7, U1]. |
| T-PLAY-63 | electron | Open a take in window A; navigate A; open a take in window B, then open a second take in B; close B. | A's token gets 404 after the navigation; B's first token gets 404 after the second open; B's second token gets 404 after the close. |
| T-PLAY-64 | electron | The shared `TakeFiles` check suite of T-PLAY-39 on the Electron implementation. | The same results as T-PLAY-39 [L8]. |
| T-PLAY-65 | benchmark | 16 readers × 60 fps × 150 kB for 60 s through the handler; CPU of the main, renderer and GPU processes. | Target 11.3; results recorded [M `RT` §8 item 3]. |
| T-PLAY-66 | benchmark | Play N = 4 and N = 8, 1080p30, 60 s, Chromium JPEGs of about 190 kB; read the barcode of each tile at each refresh. | Target 11.3; results recorded. |
| T-PLAY-67 | benchmark | 200 seeks at N = 1, 4 and 8. | Target 11.3; p50, p95 and maximum recorded. |
| T-PLAY-68 | benchmark | Scrub at 90 frames/s for 8 s at N = 4 and 8. | Target 11.3; shown/s, lag and CPU recorded. |
| T-PLAY-69 | benchmark | IPC round trips and window events of the host while T-PLAY-65 runs. | Target 11.3 [M `RT` §8 item 4]. |
| T-PLAY-70 | benchmark | Cases that nobody measured: 720p60 at N = 4; 720p30 at N = 16; speed 8 at N = 4, 1080p30. | No target; results recorded for the user. |
| T-PLAY-71 | unit | Open `write_error_short`; choose at frame numbers 79, 80 and 119. | The take plays to K = 120; camera 3 is `repaired` and not refused; rows 80 to 119 have no block; no dead camera (`deadFrom` null); at 80 and 119 the image is row 79 with "no frame", never "camera lost"; the take warnings hold `camera_file_short` and `take_error` [U2]. |
| T-PLAY-72 | component | Player on `write_error_short`: play from frame 70 to the end. | The other tiles play to the end; camera 3 holds the image of row 79 with "no frame" from frame 80 [U2]. |
| T-PLAY-73 | unit | 40 seeks to frames 1 to 40, one each 5 ms, with a test decoder of 30 ms ([ADR-1ACK](../decisions/entries/1ACK-corrections-and-choices-of-the-6a-player-code.md)). | The tile draws 3 or more images during the seeks (7.5: a finished decode of an older request is drawn when no newer image is on the tile); no older request after a newer one; the last image is frame 40. |
| T-PLAY-74 | unit | One block of `normal` that the decoder rejects; seek to the frames before, at and after it. | The tile keeps the last image with "damaged at frame 30" at frame 30 only; frame 31 shows with no mark; the camera is not refused ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-75 | unit | `openTake` with a `TakeFiles` whose read of a sidecar fails. | `openTake` rejects and closes the files ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-76 | unit | `header_uuid_dashes`. | The pair is in no take (SFF-889); the take is `incomplete` with `incomplete_take` (SFF-869) ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-77 | electron | A hard link in the media folder to a file outside; a hard link made after the open to a file of the snapshot. | The first is not in the entries; a read of the second gets 404 ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-78 | electron | Open a UNC path, a device path to a folder inside the recordings folder, and a relative path. | Each fails with "folder not allowed" ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-79 | electron | A GET with no `Range` of a sparse file of 512 MiB. | 200 with all bytes; the main process grows by less than 200 MB ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-80 | component | Host view on `counts_refused`. | The loading message goes away ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-81 | unit | The route with a bridge double that refuses the folder, and with an old folder. | `not_allowed` for the first (`chooseTakePlayer` still gives `video`); `video` for the second, and the files close ([ADR-5FBS](../decisions/entries/5FBS-fixes-of-the-6a-code-review.md)). |
| T-PLAY-82 | unit | Copies of `dead_short` whose camera 3 has: row 100 with one empty byte field; row 100 with empty byte fields and no flag `missing`; row 78 with empty byte fields and no block, so that row 79 has byte fields after it. Also a copy whose camera 3 has no block. | The first three: camera 3 is `invalid` with `bad_metadata` (SFF-759; skellyfileformat ADR-76NN item 10). No block: camera 3 is `repaired` and not refused, 120 rows, `deadFrom` 0, K = 120, the mark "camera lost at frame 0" (SFF-754) ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)). |

### 12.4 Decisions and reader rules to tests

| Decision or rule | Tests |
|---|---|
| Y1 | No test for the step order. Video only: T-PLAY-06 (no audio read). |
| Y2, L8 | T-PLAY-39, T-PLAY-64 (one suite, two implementations); T-PLAY-55 to T-PLAY-60, T-PLAY-63, T-PLAY-65, T-PLAY-69 |
| Y3, L6 | T-PLAY-40 to T-PLAY-45 |
| Y4, M8, M9 | T-PLAY-17 to T-PLAY-21, T-PLAY-46, T-PLAY-47 |
| Y5 | T-PLAY-22 to T-PLAY-24, T-PLAY-48 |
| Y6 | T-PLAY-35; T-PLAY-40 uses the tile in a page with no host code |
| Y7 | T-PLAY-01 (the builder); the parity of 12.5 and the CI of 12.6 |
| M1, M2, M3 | T-PLAY-01, T-PLAY-17, T-PLAY-20, T-PLAY-26, T-PLAY-46 |
| M4, M6 | T-PLAY-42 (inserted DHT) |
| M5 | T-PLAY-21 |
| U1 | T-PLAY-62 |
| U2 | T-PLAY-71, T-PLAY-72 |
| M7 | T-PLAY-20 (T_0) |
| M10 | No test here: it is a rule of the shared Python reader. |
| L1 | T-PLAY-53 |
| L2 | No test: the scope of the reader (6.13). |
| L3 | T-PLAY-11, T-PLAY-54, T-PLAY-58 |
| L4 | T-PLAY-31, T-PLAY-44, T-PLAY-50, T-PLAY-51 |
| L5 | T-PLAY-51 (today's `PlaybackControls` as it is); no test changes the player of today. |
| L7 | T-PLAY-62 |
| E1 | T-PLAY-25, T-PLAY-40, T-PLAY-49, T-PLAY-66 |
| E2 | T-PLAY-53 (an old folder opens in today's player) |
| E3 | No test: the reader is in the module (T-PLAY-35). |
| E4, SFF-783 | T-PLAY-29, T-PLAY-34, T-PLAY-49 |
| E5, SFF-751 | T-PLAY-08, T-PLAY-41 |
| E6 | T-PLAY-37, T-PLAY-44 |
| E7, SFF-706 | T-PLAY-10 |
| E8, SFF-781 | T-PLAY-14, T-PLAY-15, T-PLAY-20 |
| E9 | Replaced by M1 to M5; tests as M1 to M5 |
| SFF-701, SFF-703, SFF-742, SFF-748, SFF-750, SFF-753, SFF-772 | T-PLAY-08 |
| SFF-708, SFF-709, SFF-891 | T-PLAY-09 |
| SFF-721 | T-PLAY-57 (a file in another subfolder is not served) |
| SFF-730 | T-PLAY-02, T-PLAY-05 |
| SFF-731, SFF-867 | T-PLAY-03, T-PLAY-04 |
| SFF-733 | T-PLAY-27 |
| SFF-738 | T-PLAY-42, T-PLAY-43 |
| SFF-739, SFF-757 | T-PLAY-25, T-PLAY-27 |
| SFF-740 | T-PLAY-21, T-PLAY-23, T-PLAY-24, T-PLAY-26 |
| SFF-744, SFF-746 | T-PLAY-11, T-PLAY-12, T-PLAY-13 |
| SFF-747, SFF-795, SFF-798, SFF-886 | T-PLAY-13, T-PLAY-15 |
| SFF-754 | T-PLAY-11, T-PLAY-22, T-PLAY-82 |
| SFF-756, SFF-887 (file warnings) | T-PLAY-09, T-PLAY-15 |
| SFF-759, SFF-794 | T-PLAY-21, T-PLAY-27, T-PLAY-82 |
| SFF-777, SFF-780 | T-PLAY-14 |
| SFF-782 | T-PLAY-16, T-PLAY-29 |
| SFF-790 | T-PLAY-07 |
| SFF-791 | T-PLAY-12, T-PLAY-23 |
| SFF-799 | T-PLAY-61 |
| SFF-863 | T-PLAY-15 |
| SFF-864, SFF-865 | T-PLAY-06, T-PLAY-28 |
| SFF-866 | T-PLAY-07 |
| SFF-868 | No test: 6a reads no folder file, so it does not compute `<rec>` (6.3). |
| SFF-869, SFF-870, SFF-871 | T-PLAY-05, T-PLAY-36 |
| SFF-729, SFF-872, SFF-883, SFF-885, SFF-892 (the full result) | No test in 6a: the player does not compute them (6.13, L2). The player never reads `summary` (6.2). |
| SFF-890 | T-PLAY-02 |
| F1 to F21 | T-PLAY-31, T-PLAY-37, T-PLAY-44, T-PLAY-50 to T-PLAY-53 |

Counts: 46 unit, 17 component, 13 electron, 6 benchmark: 82 tests.

### 12.5 Parity of the systems [Y7]

- Each unit, component and electron test runs on Windows, Linux and macOS [Y7].
- T-PLAY-57: the outside link is a junction to a folder on Windows, because a file link on Windows
  needs a privilege; it is a file link on Linux and macOS [agent 38] [NV: that `lstat` of Node reports
  a junction as a link on the runner].
- T-PLAY-58: the rename and the delete run on each system. The review measured them on Windows only
  [M review].
- T-PLAY-60: the test sets the sparse flag with `fsutil sparse setflag` on Windows; Linux and macOS
  make sparse files by a seek past the end.
- The benchmarks run on the Windows test machine. Their runs on Linux and macOS are owed (M-PLAY-3).
- Electron needs a display on Linux. The Linux job runs the component and electron tests under
  `xvfb-run`.

### 12.6 CI [agent 35]

A new workflow `.github/workflows/player.yml`, on the pattern of `.github/workflows/capture.yml` and
`.github/workflows/ring-arm64.yml`:

- Trigger: each push to `dom/player` and to `dom/native-jpeg`, and each pull request, that changes
  `skellycam-ui/src/player/**`, `skellycam-ui/src/components/playback/**`, `skellycam-ui/electron/**`,
  `skellycam-ui/package.json`, `skellycam-ui/package-lock.json`, `skellycam-ui/tsconfig.json`,
  `specs/player.md` or the workflow; and by hand.
- `permissions: contents: read`; a concurrency group for each ref with `cancel-in-progress`.
- The same pinned actions as the existing workflows: `actions/checkout` at
  `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1); `actions/setup-node` at
  `949feb2413d6458794dcd2491c4babbbce0c15c1` (v7.1.0) with Node `26.13.1`, as
  `build-installers-pyinstaller.yml` [NV: no test ran on Node 26.13.1].
- Steps in `skellycam-ui/`: `npm ci`, `npm run test:player:unit`, `npm run test:player:browser`.
- Job `player-windows` on `windows-2025`; job `player-linux` on `ubuntu-24.04`, with `xvfb` installed by
  `apt-get` at one exact version; job `player-macos` on `macos-15`, with its own concurrency group and a
  time limit of 40 minutes, as the macOS job of `capture.yml`.
- The exact `xvfb` package version is taken from the runner image when the workflow is written. This is
  [NV] now.
- The workflow does not run the benchmarks.

## 13. Format changes that the player contributes

The one merged list of format changes is section 13 of `specs/recorder.md` (the F-list). It also
holds the rules of M1 to M10. This spec does not repeat that list and does not edit skellyfileformat.
The player contributed three items to it [agent 39]. Since commit c1028ef, the format holds them: item
1 is F-8 and item 3 is F-10 in SFF-783, and item 2 is F-9 in SFF-759 (skellyfileformat ADR-6AT7)
([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)). The text of the format applies. The items as the player proposed them:

1. **Equal player times** (addition to SFF-783): when two or more frames of a camera have the same
   player time, the last frame at or before t is the one with the highest position.
2. **The order of the SFF-759 check in a player**: a player MAY show the frames of a finished or
   repaired camera file before it has counted the blocks of the file. It then checks, for each frame
   that it reads, that the block of the frame is the next block after the block of the previous row
   with byte fields (SFF-739), and, at the open, that no block follows the last block that a row
   points at. When a check fails, the player stops showing images of that camera file and reports the
   file as `invalid` with `bad_metadata`. The reader result of SFF-885 does not use this order.
3. **A `missing` row in a player**: a player never shows the placeholder of a `missing` row as a
   picture. It holds the last real image of the camera and shows a "no frame" mark [M9].

Revision 1 of this spec proposed four more texts (a separate no-image flag, a lost-camera flag, a codec
check, and checks of the `frame` value, the time order and the column line). M1 to M10 replace the
first two. The other two are dropped, because they made this reader stricter than the other readers.
Section 14.2 lists the cases that the format still leaves open.

## 14. Measurements, open points, weak points, open work

### 14.1 Measurements owed

| ID | Measurement | Test |
|---|---|---|
| M-PLAY-1 | The targets of 11.3 on Electron 45.3.4 | T-PLAY-65 to T-PLAY-69 |
| M-PLAY-2 | Playback cost on the cameras' own JPEG bytes, on a take of recorder step 5a that the user gives | T-PLAY-66 with that take |
| M-PLAY-3 | The benchmarks on Linux and macOS (the machines of phase 0) | T-PLAY-65 to T-PLAY-70 |
| M-PLAY-4 | 720p60 at N = 4 and 720p30 at N = 16 | T-PLAY-70 |
| M-PLAY-5 | Main-process latency while the handler serves | T-PLAY-69 |
| M-PLAY-6 | The tile at 8 cameras × 60 fps (step 4b, for the preview) | in step 4b [L6] |
| M-PLAY-7 | Speed 8 | T-PLAY-70 |
| M-PLAY-8 | Real clock alignment across cameras in a take of step 5a | a take of the user |

### 14.2 Open points

1. **The F-list of the recorder spec** is in the format since commit c1028ef (skellyfileformat
   ADR-6AT7). This spec follows the format text: the bit 4 of `missing` and `missing=` before the last
   key of `# end` (F-1), the short file (F-2), and the `detail` forms of `camera_dead` and
   `camera_file_short` (F-5). The user accepted the details of skellyfileformat ADR-76NN ([ADR-3B97](../decisions/entries/3B97-format-sync-to-the-format-commit-with-f1-to-f10.md)).
2. **Cases that the format leaves open**: a missing column that a reader needs; a `frame` value that
   is not the position; a player time that decreases; a camera file whose track is not `V_MJPEG`.
   None of the four is in the merged list F-1 to F-10 of the recorder spec. They stay open. The
   player does not refuse a file for the last three (6.5, 6.6, 6.8). For the first, it cannot read the
   file. The three items that the player gives (section 13) are in that list as F-8, F-9 and F-10.
3. The Chromium version of Electron 45.3.4: `process.versions` gives Chrome 156.0.8078.100 and Node
   24.22.3 (read on the Windows test machine, 2026-11-20). The timing on 45.3.4 is still [NV].
4. A page from `http://` (Vite dev server) that reads the custom scheme was not tested [M `RT` §4].
5. The exact `xvfb` version for the Linux job [NV]; Node 26.13.1 [NV].
6. That no other page can learn a token (5.4) [NV].
7. The golden folders of skellyfileformat: G1 to G16 and G18 exist, each case with a `.player.json`
   result (`../skellyfileformat/golden/README.md`). The conformance run against them comes with 6c
   [L2]. G18 holds `missing` rows, placeholders, short files and a camera file with no block (the case
   `no_block`). G1 to G16 hold no placeholder.

### 14.3 Weak points

- SFF-759 is checked late for a block in the middle of a file (6.9). A user can see images of a file
  that the reader later refuses.
- One bad CSV row in one camera ends the take for all cameras at that row [SFF-746, SFF-754].
- Each file has its own time base [SFF-781, E8]. In one take, one camera can use fitted times and
  another arrival times. A fitted time is not corrected for latency, so the tiles can differ by the
  arrival delay.
- The mark comes from k* and the image from t (7.3). With different camera times, the mark can change
  one display refresh before or after the image.
- With no manifest, damaged frames at the end of a file look like a dead camera (7.3).
- A corrupted JPEG payload decodes with no error, with grey pixels [M review]. The player cannot find
  it (5.7).
- A request to the scheme does not name its window; the token is the only key (5.4).
- A recordings folder that the user set in the settings and never picked in the dialog, outside the
  default folder, is refused until the user picks it once (5.3).
- All timing evidence is from one Windows machine with an NVIDIA GPU, at 1080p30 and 720p, with JPEG
  re-encodes (11.2).
- The decode runs on the page main thread. A busy page can delay the draws (step 4b measures it).
- Pause moves t back to T_k* [L4]. A camera whose image at t was row k* + 1 then shows row k* again.

### 14.4 Open work for `decisions/open-work.md` [Y2]

- **Option B for the take files (not part of 6a).** Review how the Python server can serve the take
  files with a performance on par with the Electron handler: threads, process splits, no request
  logging on the route, no folder listing per request, `Cache-Control: no-store`, and the expose
  header [Y2, M `RT` §5, §6]. The measured gap: the bare FastAPI route was 4 % short and 25 % short
  behind the logging middleware, at 16 × 60 fps × 150 kB.

## 15. Contradictions and review faults

### 15.1 Contradictions found

1. **The evidence against SFF-783 after the last frame.** `GF08` §3 suggests a hold limit and a stale
   flag. SFF-783 holds the last frame with no limit. With M1, no camera ends early. The spec follows
   SFF-783 and Y4.
2. **The versions.** The evidence measured Electron 35.7.5 and 45.2.3. The pin is 45.3.4 (11.1).
3. **SFF-892 against 6a.** A JavaScript reader gives the scope `player` result in full. L2 defers it
   to 6c.
4. **SFF-759 against a fast open.** A count of the blocks at the open needs one read for each block.
   Section 13, item 2.
5. **`RT` §6 against Y2 and L7.** `RT` maps a URL to the allowed recording roots. Y2 limits the
   handler to the opened take folder, and L7 limits the folders that open. The spec follows Y2 and L7.
6. **`PLAN` §5 and the live view of today against Y3 and L6.** They decode with `createImageBitmap` on
   a worker. Y3 and L6 put `ImageDecoder` in the one tile on the main thread.
7. **F6 of today against the new rule.** Today all tiles show the time of camera 0, or an estimate.
   The new tiles show the player time of their own image [SFF-783, L4].
8. **The evidence harness against this spec.** The harness decoded on the page and read through a
   local HTTP server; the transport test used `protocol.handle` with no decode. No run combined the
   two (M-PLAY-1).
9. **M8 against the time rule.** A dead camera's rows have no time, so a choice by time alone would
   show its last image with no mark. The mark comes from k* (7.3).
10. **The recorder spec against the backend route.** The recorder spec says that the UI shows the mark
    `needs_new_player` and plays nothing [recorder spec 10, item 13]. L1 opens such a take in the new
    player; the UI routes by the folder before any backend video call, and the mark is information
    only (10).

The cross-check against the recorder spec on 2026-11-20 also gave: `missing` is bit 4; the live and
short MKV forms of FFmpeg (unknown-size Segment, known-size Clusters with a CRC-32 child); T_k that
never goes down; the dead-camera rules for a manifest in the state `recording` and for the `detail`
form; `camera_dead` in `dead_short`; T-PLAY-35 with `main/` loaded in Electron; the write-error short
file (U2, T-PLAY-71, T-PLAY-72); the exact flat-block encoder (12.2.1). No item was rejected.

### 15.2 Faults of the independent review and what this revision did

| Fault | Change |
|---|---|
| B1: a `missing` row can have no time | T_k from the cameras with a time; the image from real rows; the mark from row k*; a dead camera's file is not refused (6.7, 6.8, 7.2, 7.3). |
| B2: Windows unlink and rename behaviour | `readWhole` opens, reads and closes; handles only for camera files; no claim of 404 for a deleted file with an open handle; T-PLAY-54 and T-PLAY-58 changed (5.5, 5.7). |
| B3: Chromium normalises the URL and lowercases the host | T-PLAY-57 tests only that no request leaves the folder; the token is lower-case hexadecimal (5.2, 5.5). |
| B4: interface imports under type stripping | `import type` and `verbatimModuleSyntax` (4.2, T-PLAY-35). |
| S5 | `electronTakeFiles` is exported from `index.ts` (4.1). |
| S6 | No claim that a decode failure finds damage; "damaged at frame N" from the timing file (5.7, 6.6, 8.1). |
| S7 | Only bytes below the snapshot size (5.6, T-PLAY-55). |
| S8 | Tokens tied to the window (5.4, T-PLAY-63). |
| S9 | k* is state after a step or a frame seek (7.2, T-PLAY-30). |
| S10 | A take-level "unfinished" mark when the manifest says `recording` (6.11, T-PLAY-48). |
| S11 | One shared suite on both `TakeFiles` implementations; T-PLAY-49 goes through the handler (5.1, T-PLAY-39, T-PLAY-64). |
| S12 | The fixture encoder uses the Annex K tables (12.2). |
| Minor items | F20, F15, the F6 tooltip, the default time format, the counts of T-PLAY-22 from the `unfinished` fixture, floor division for a negative d, `stat` with `bigint`, the pull request trigger, Node 26.13.1 marked [NV]. |
| Over-design | One tile binding (`attachTile` with a `Tile`); no React in the module; only GET and `bytes=a-b`; no `seekTime`; the old choice 32 replaced by L5. |

No fault was rejected.

## 16. Choices of the agent

Each item fills a gap that the decisions, the format spec and the evidence do not fix. The body marks
each one [agent n].

1. The folder `skellycam-ui/src/player/` and its layout (4.1).
2. The boundary rule and its scan; erasable TypeScript, `.ts` imports, `import type`,
   `allowImportingTsExtensions` and `verbatimModuleSyntax` (4.2).
3. The module holds the engine and the tile; the controls bar, the grid and the keys stay in the host;
   one tile binding `attachTile(cameraIndex, tile)` (4.3).
4. The names of the public interface, the state and the events (4.4).
5. The scheme `skellycam-take`, its privileges, the token of 32 lower-case hexadecimal characters, tied
   to the window that asked (5.2, 5.4).
6. The recordings folder computed with the backend rule; the list file of picked folders in the user
   data folder (U1 decides that picks are remembered); "inside" by real path, without case on Windows
   (5.3).
7. The open: a scan of the root and the media folder only, regular files only, no links or junctions,
   an allow-list by exact relative path, identities by `stat` with `bigint`, no absolute path to the
   page (5.4, 5.5).
8. Handles only for camera files; each other read opens, reads and closes; an identity check at each
   open (5.5, 5.7).
9. The response table: GET with no range and `bytes=a-b` only, 416 for each other range form, 405 for
   other methods, the snapshot clamp, and the headers (5.6).
10. The page client accepts a 206 with the asked start, or a 200 with the exact length (5.6).
11. The manifest read limit of 16 MiB; no limit for a sidecar (5.8).
12. A snapshot of sizes at the open; no use of later bytes; no follow and no reload in 6a (5.7, 6.11).
13. With two or more takes in a folder: open the first in `take_uuid` order (6.4).
14. No read of audio files, folder files or `<rec>` in 6a (6.3, 6.4).
15. The cases that the format leaves open: a missing needed column gives `missing_metadata`; the
    `frame` value is ignored; a decreasing time is searched by its running maximum; a fit that does
    not hold each position is not used (6.5, 6.6, 6.8).
16. The head read in steps of 64 KiB and the tail read in steps of 1 MiB (6.9).
17. The SFF-759 check at each frame read, from the end of the previous block, and at the tail; a
    mismatch makes the file `invalid` from then on (6.9, 6.10).
18. Times parsed as `BigInt`, checked against 2^53, then kept as JavaScript numbers (6.8).
19. T_k = the largest player time at row k; T_(k-1) when no camera has one; the clock range; k* as
    state after a step or a frame seek, and not moving back during play (7.2).
20. The image from the real rows by time, the mark from row k*; the placeholder is never decoded
    (6.7, 7.3).
21. The dead camera without a manifest: the run of `missing` rows to the end; with a manifest and no
    `camera_dead`, a run at the end is damage (7.3).
22. Where the "unfinished" mark goes (on unfinished files, and on every tile when the manifest says
    `recording`); "damaged at frame N" shows from the open (6.6, 6.11).
23. The end of play and the loop on the clock (7.4).
24. The canvas size from its client size × `devicePixelRatio`; contain on black; the overlay in the
    canvas at a fixed CSS size; the canvas title for F6; the tile keeps the overlay text for tests
    (3.2, 8.2, 8.4).
25. The details of the tile interface: `update` with `jpeg` null, the promise result, one mark for each
    update with the order of the mark kinds (8.3).
26. The default texts and the places of the overlay parts; a camera state shows as its name (8.3,
    8.4).
27. The prefetch queue of min(8, max(2, ⌊64 / N⌋)) images; one range read in flight for each camera, up
    to 4 MiB; at a rate above 1, only the rows that the clock will choose (9).
28. Newest wins: one decode in flight and one pending target for each tile (7.5, 9.2).
29. The events and their rate (4.4).
30. "Rec: fps" from the nominal rate of the camera with the lowest `group_position`, rounded as SFF-728
    (8.4).
31. The new host view `CanvasTakePlayer.tsx` with its own grid and keys, and the route through
    `isTakeFolder` (10).
32. The fixture builder in TypeScript; temporary folders below the test recordings folder; the
    flat-block JPEG encoder with the Annex K tables and its options; the placeholders; the fixtures of
    12.2.
33. The benchmark JPEGs from the JPEG encoder of Chromium, about 190 kB at 1080p (12.2).
34. The runners, the harness and its two test hooks, the npm script names (12.1).
35. The workflow `player.yml`: triggers, jobs, runner labels, pins, `xvfb-run` on Linux, the macOS job
    rules (12.6).
36. The pass thresholds of the test table and the targets of 11.3; a missed benchmark target goes to
    the user and does not stop 6a by itself (2, 11.3).
37. A read error also sends an `error` event; a shortened file is a read error (5.7).
38. The link case of T-PLAY-57 on Windows is a junction (12.5).
39. The wording of the three items that the player contributes to the F-list (13).

## 17. Questions for the user

None open. The user answered the four questions of revision 1 on 2026-11-19 with L1 to L4.

## 18. Decisions of the user

### 18.1 Y1 to Y7 (grilling of 2026-11-19, Q217 to Q226)

The user decided these on 2026-11-19
([ADR-J2BQ](../decisions/entries/J2BQ-phase-6-player-decisions-y1-to-y7.md)). They are binding. M1 to
M10 replace the "gap row with no image" reading of Y4.

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

### 18.2 Missing frames M1 to M10 (2026-11-19)

The user decided these on 2026-11-19
([ADR-4HNY](../decisions/entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)).
They replace the "row with no image" reading of R2, R3 and Y4.

- M1: A missing frame is stored as a black placeholder JPEG block on its row. Cases: a damaged frame,
  and a dead camera whose process still runs (the writer keeps writing placeholders to the end of the
  take). Every camera file then has exactly one block for each group frame, constant block times (no
  time jump), and equal block counts across cameras.
- M2: The placeholder has the same width, height and chroma layout (sampling factors) as that camera's
  own frames, taken from the SOF segment of that camera's first frame. It is made once for each camera
  file, with optimised Huffman tables (measured: 16.5 kB at 1080p 4:2:2, 1.8 GB for one hour at
  30 fps). A different layout breaks Blender; a different size breaks every tool when it is the first
  block.
- M3: The row of a placeholder has the flag `missing` (one new flag bit; the word "gap" keeps its
  format meaning of a jump in the source frame number). The end line of the timing file gets a
  `missing=` count (placed where SFF-745 allows a new key). The manifest says how many rows of each
  camera are placeholders. The row's byte offset and size point at the placeholder block. Which other
  row fields are empty (times, source frame number) is as recorder P-1 says: kept for a damaged frame
  that had them, empty for a dead camera. A row with no time has no player time.
- M4: The format rule "the stored bytes are the camera's bytes" gets two stated exceptions: the
  placeholder on a `missing` row (M1), and the inserted DHT table (M6).
- M5: One case stays short: when a camera process is killed or hangs, nothing can write its video
  file. That file ends early. The main process completes its files (timing rows with `missing`, no
  block) only after the process has ended, and the manifest says that the video file is shorter than
  the row count. Crash repair in step 5c may fill it later. This is the one exception to "one block for
  each row", and readers get the rule: a `missing` row whose byte fields are empty has no block.
- M6: The recorder stores the JPEG bytes with the DHT table that the ring inserted when the camera sent
  none (the ring flag `DHT_INSERTED` says which frames). The format rule changes to allow this one
  insertion.
- M7: A take starts at the first group frame; the first block of a file is never smaller than the
  camera's frames (M2 guarantees it).
- M8: A dead camera is also recorded in the manifest: warning `camera_dead` with `last_frame`. In the
  player, "camera lost at frame N": N is the first group frame with no image from that camera.
- M9: The player never shows the black placeholder as a picture. It shows the last real image with the
  "no frame" mark (Y4), from the `missing` flag. Other programs that ignore the flag see black.
- M10: skellycam's shared reader (`SequentialVideoReader`) needs no change for M1 (tested: 300 of 300
  frames). The interface notes for freemocap and skellytracker say: a placeholder row is black and is
  flagged `missing` in the timing file; "image i is group frame i" stays true, except for a file of a
  killed camera process (M5), which is shorter.

### 18.3 Player decisions L1 to L8 (2026-11-19)

The user decided these on 2026-11-19, after revision 1 of this spec and its review
([ADR-4HNY](../decisions/entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)).

- L1: A take folder in the new format opens in the new player; every other folder opens in today's
  player. The rest of the switch is step 6c.
- L2: 6a builds only the reader parts the player needs. The full reader result and the conformance run
  come with 6c.
- L3: Three more tile marks: "camera file not readable: <reason>", "damaged at frame N", "read error".
  The other tiles keep playing. (A corrupted JPEG decodes with no error, so damage is found from the
  timing file, not from the decoder.)
- L4: The "may not be frame-perfect" warning is hidden in the new player. Each tile shows the time of
  its own frame. Pause moves to a whole frame, as today (the writer's "pause keeps t" is rejected).
- L5: No restructuring of today's player. The new player's view uses today's controls component as it
  is.
- L6: The shared tile runs on the page's main thread with ImageDecoder. Step 4b measures 8 cameras at
  60 fps; a worker only if the target is missed. The tile must also serve the live preview: a live
  source feeds it without the take reader; it shows a per-camera frame rate text, the camera state
  (eight states) and a flagged-frame mark that keeps the last image (a draw with no new image).
- L7: The file handler opens a folder only if it is inside the recordings folder or the user picked it
  in the system folder dialog.
- L8: Y2 stands: every file read of the player goes through one small interface; one shared check suite
  runs against both implementations (Node and Electron).

### 18.4 Answers U1 and U2 (2026-11-20)

The user gave these answers on 2026-11-20, relayed by the supervisor
([ADR-4HNY](../decisions/entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md)):

- U1: A folder that the user picked in the system folder dialog is remembered across restarts of the
  app. A page must not be able to add to the list without a dialog pick.
- U2: A write error on one camera file is a second short-file case: the same short pair as a killed
  process (`missing` rows with empty byte fields and no block, `# repair`, `# end`), with the manifest
  warnings `camera_file_short` and `take_error`, and no `camera_dead`.
- U3 (2026-11-20, relayed by the supervisor): `PlaybackControls` of today gets one optional prop that
  hides the "may not be frame-perfect" sync button. The player of today does not give it, so nothing
  changes there. The view of the new player gives it. No other change of the player of today (L5).

### 18.5 Earlier decisions (cited, not repeated)

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
  so every camera's CSV has equal rows). M1 to M5 replace the "no image" reading.
