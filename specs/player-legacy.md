# Phase 6 player specification: step 6c, part 1, playback of FreeMoCap v1 recordings (draft)

Status: **draft for the review of the owner, 2026-11-24. Not accepted.** No test and no code comes before
the owner accepts this spec. The rules of the owner are in
[ADR-X5MZ](../decisions/entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)
(accepted). Each choice of the agent is in
[ADR-A56K](../decisions/entries/A56K-choices-of-the-v1-playback-spec.md) (proposed). Section 16 gives
the open questions. A "yes" to a question accepts the recommendation of that question.

This spec extends [`player.md`](player.md) (step 6a, accepted). The rules of `player.md` apply to a v1
recording, unless this spec gives a different rule. Section 14 lists each difference.

## 0. How to read this spec

Marks:

- **[O]**: a rule of the owner, 2026-11-24 (section 18,
  [ADR-X5MZ](../decisions/entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)).
- **[S n]**: the H.264 study, part A, `research/h264_study/part_a/NOTES.md`, section n, on branch
  `dom/h264-scrub-study` at commit 71caa2d0b. `[S RT]` is its `RESULTS_TABLE.md`. The study files
  `wasm_build.sh`, `app/wasm.mjs` and `app/wasm_worker.mjs` are in the same folder. The study ran on
  one Windows 11 machine (RTX 3070, Electron 45.3.4), on a shared machine. Each time is rough.
- **[INV]**: `research/skellycam_recording/docs/legacy_release_inventory_20261115.md` on branch
  `dom/research` at commit 7d8f8911b (a code reading of 87 freemocap release tags; nothing was run).
- **[C file]**: a code fact of this branch, read on 2026-11-24.
- **[D page]**: a page of the GitHub documentation, read on 2026-11-24 (section 10.6 lists the pages).
- **[NV]**: not verified. No evidence proves it.
- **[agent n]**: an agent filled a gap. Section 15, item n, lists each one.
- **[P n]**: the open question n of section 16.
- **6a n.m**: section n.m of [`player.md`](player.md).

This spec uses British spelling.

## 1. Purpose, scope, terms

### 1.1 Purpose

The canvas player of step 6a plays the takes of the new format (camera JPEGs in MKV). This spec adds
the playback of FreeMoCap v1 recordings to the same player. The first goal is reliable playback. The
second goal is a short seek time [O]. The player plays each v1 file as it is. It never converts a
file [O]. The UI can run on a different machine than the server. Thus only compressed bytes of the
original files go on the HTTP link [O]. The server does not decode video [O].

### 1.2 In scope

| Item | Rule |
|---|---|
| FreeMoCap v1.0.25 to v1.8.2, with skellycam 2023.9.1086 to 2025.9.1097 (the writer is byte-identical across these pins) | supported [S 12.1 row 1] [INV] |
| FreeMoCap v1.0.26 to v1.0.30 (skellycam unpinned, or a branch zip) | supported by the same rules; no sample [S 12.1 row 5] [NV] |
| The official FreeMoCap sample data (a 2022 recording in a v1 folder, with the old names `sesh_..._synced_CamN.mp4`) | supported [S 12.1 row 3] |
| A folder of the v1 "import videos" wizard (`recording_sessions/import_<name>/`, any `.mp4` that the user picked) | supported for the codecs of section 3 [S 12.1 row 4] [INV]; no sample [NV] |
| The take folders of the new format | unchanged: 6a plays them |

### 1.3 Out of scope

- **FreeMoCap v2 builds and skellycam v2 alpha formats.** The owner: "we do not need to maintain
  compatibility with any v2 builds - only v1." [O]. This removes rows 6 to 11 of [S 12.1]: the
  Windows Media Foundation H.264 writer, the Linux PyAV x264 writer, the macOS `avc1` writer, the
  `mp4v`, XVID and MJPG fallbacks in MP4 and AVI, the `.web.mp4` sidecars, and the Rust backend of
  `upstream/sfn26`. The owner's rule replaces his earlier words "The goal is to support all v1 onwards
  versions" [O]. Section 2.2 tells how the player refuses a v2 alpha folder.
- **FreeMoCap v0.0.x and v0.1.0.** They are older than v1 [O "only v1"]. The player does not refuse
  a v0.1.0 folder, because it has the v1 form (section 2.2). No test covers it.
- **The annotated videos** (`annotated_videos/*.mp4`). They are a result of the processing, not a
  camera file. The player does not show them in this step [P 16] [agent 1].
- **A repair, a conversion, a transcode, a server decode, or a copy of a file** [O].
- **Audio.** A v1 recording has no audio file of the cameras.

### 1.4 Terms

| Term | Meaning |
|---|---|
| v1 recording | A folder of section 2.1. |
| camera file | One `.mp4` file in `synchronized_videos/` of a v1 recording. |
| time file | `synchronized_videos/timestamps/<stem>_binary.npy` of a camera file with the stem `<stem>` (section 2.3). |
| frame table | The list of the frames of one camera file, in presentation order, from its MP4 index (section 6.1). |
| frame k | Entry k of the frame table, from 0. The frame index is the truth (section 6). |
| K | The number of multi-camera frames: the smallest frame count of the cameras that play (section 6.3). |
| k* | The frame number that the controls show (as 6a 7.2). |
| T_k | The take time of multi-camera frame k (section 6.4). |
| the decoder | The custom libav.js variant of section 9: FFmpeg's demuxer and decoders, compiled to WebAssembly (WASM). |
| tile worker | One module worker for one tile, which runs the decoder (section 7). |
| the recipe | The build files of the decoder (section 9.1). |

## 2. The v1 recording

### 2.1 Folder and files

A v1 recording is a folder with these items [INV] [S 12.1]:

| Path | Role | Read by the player |
|---|---|---|
| `synchronized_videos/*.mp4` (also `*.MP4`) | the camera files | yes |
| `synchronized_videos/timestamps/<stem>_binary.npy` | the time file of the camera file `<stem>.mp4`: 1-D float64, one value per written frame, `time.perf_counter_ns()` of the capture | yes, when present |
| `synchronized_videos/timestamps/<stem>_timestamps_human_readable.csv` | the same times as text | no (the `.npy` holds the same values) [agent 2] |
| `synchronized_videos/*.png` | diagnostic plots (Windows only) | no |
| `annotated_videos/`, `output_data/`, `*.toml`, `*.json`, `*.csv`, `*.npy` in the root, `*.blend`, `*.ipynb` | results of the processing | no |

The v1 writer gives the names `Camera_{i:03d}_synchronized.mp4` and
`Camera_{i:03d}_synchronized_binary.npy` [INV]. The sample data and the import folders have other
names [S 12.1 rows 3, 4].

### 2.2 How the player recognises a v1 recording [agent 3]

The player reads only the snapshot of the folder (section 4.2). It applies these rules in this order:

1. A folder with a `recording_manifest.json` or with a device pair of the new format is a take of
   the new format. 6a plays it (6a 10). The rules below do not apply.
2. A folder whose `synchronized_videos/` holds a file name with the form `<rec>.id-<n>.idx-<n>.mp4`
   is a v2 alpha recording [S 12.1 rows 6 to 11]. The player refuses it with the text "FreeMoCap v2
   alpha recordings are not supported" [O "only v1"].
3. A folder whose `synchronized_videos/` holds one or more files with the extension `.mp4` (any case)
   is a v1 recording. FreeMoCap v1 itself finds its videos with `*.mp4` and `*.MP4` in that folder
   [INV quirks, camera order].
4. Each other folder: the text "not a FreeMoCap v1 recording: no synchronized_videos/*.mp4".

The player does not find the era (V1a to V1i) of the recording. It does not need it [INV section 3].
Releases never write their version number into the recording [INV].

### 2.3 The time file [agent 4]

- The player looks for `synchronized_videos/timestamps/<stem>_binary.npy` for each camera file
  `<stem>.mp4`. It uses no other name rule.
- The player parses the NPY format itself: the magic `\x93NUMPY`, the versions 1.0, 2.0 and 3.0, and
  the header dictionary. It accepts only `descr` `'<f8'`, `fortran_order` `False` and a shape `(n,)`.
- A time file is **usable** when the parse passes and n equals the frame count of its camera file
  (section 6.1). Each other time file is not usable. The camera then gets the warning
  `time_file_unusable` with the reason (`missing`, `bad_header`, `dtype`, `shape`, `length`).
- A value that is not finite (NaN, infinity) is a frame with no time.
- The values are nanoseconds on one monotonic clock of the recording machine, not Unix time [INV].
  All cameras of one v1 recording come from one process on one machine, so the values of the cameras
  are comparable [INV]. A float64 holds each integer nanosecond up to 2^53 ns (about 104 days of
  clock time) with no loss. The player rounds each value to an integer nanosecond.
- A repeated value means a duplicate frame: the v1 synchronizer writes a copy of the last frame for a
  dropped frame [INV quirks, dropped frames]. The player shows it as a frame (section 6.4).

### 2.4 No time file

The official sample data has no time file [S 12.1 row 3]. An import folder has none [S 12.1 row 4].
Then the player uses the header rate (section 6.4). The tiles show the time with a `~` in front, as
the player of today does (feature F6, 6a 3.1) [agent 5].

## 3. Route by codec, not by file extension (Q694 open) [P 1] [P 2]

### 3.1 The rule

The player reads the sample entry of the video track of each camera file from the MP4 index
(section 6.1). It does not use the file extension [S 12.5]. The `mp4v` and `avc1` codecs share the
extension `.mp4` [S 12.5].

| Sample entry | Codec | Route |
|---|---|---|
| `mp4v` with an `esds` object type 0x20 (MPEG-4 Visual) | MPEG-4 Part 2 | the decoder (WASM `mpeg4`) |
| `avc1`, `avc3` | H.264 | the decoder (WASM `h264`) [P 1] |
| `hvc1`, `hev1` | HEVC | refused [P 2] |
| each other entry (for example `av01`, `vp09`, `mp4v` with another object type, `jpeg`, `mjpa`) | | refused |

The refusal text is "camera file not playable: codec <name> is not supported", with `<name>` the
four characters of the sample entry and the object type, if any. The tile shows it as the mark
`not_readable` of 6a 8.3. The other cameras play.

### 3.2 Why the decoder for H.264 too (proposed) [agent 6]

The agent proposes WASM only, with no WebCodecs route in this step:

- **Reliability first [O].** One decoder for each v1 file gives one code path, one test set and the
  same pixels on each system. The decoder gave the pixels of x86-64 FFmpeg on 73,819 of 73,819
  frames in 30 files, H.264 included [S 12.4].
- **Parity of the three systems.** WebCodecs decoders depend on the OS and the GPU. HEVC in
  WebCodecs depends on the OS [S 12.5]. The study measured WebCodecs on one Windows machine only
  [S 12.6].
- **Imports are rare and have no sample** [S 12.1 row 4] [NV]. A second route for them adds risk for
  a case that nobody has tested on real material.
- **The cost.** On H.264, a WASM seek is about the time of WebCodecs with its software decoder, and
  2.6 to 3 times the time of the GPU decoder [S 12.4]: Baseline GOP 32, 4 tiles, seek p50 194 to
  197 ms (GPU 74 ms, software 173 ms); x264 GOP 250 with B-frames, 3 tiles, 654 to 660 ms (GPU 221 ms,
  software 686 ms). For `mp4v`, WASM is the only route in Chromium [S 11.2, S 12.5].

The alternative (WebCodecs first, the decoder as the fallback) is the recommendation of the study
[S 12.5]. Question [P 1] lets the owner choose it.

### 3.3 Other properties of a camera file

| Property | Rule |
|---|---|
| Pixel format | 8-bit `yuv420p`, `yuv422p`, `yuv444p` (and the `yuvj` forms). Each other format: refused, "pixel format <name> is not supported" [agent 7]. |
| Colour | The tile draws with the stream colour values when the stream sets them. Else BT.601 with limited range, the default of FFmpeg for MPEG-4 Part 2 [agent 7] [NV: the colours that Chromium gives]. The identity check of section 13 is on the decoded planes, not on the drawn colours. |
| Rotation | v1 writes the rotation into the pixels [S 11.1 row 3]. The player applies a `tkhd` matrix of 0, 90, 180 or 270 degrees as `rotationCwDeg`. It ignores each other matrix, with the warning `matrix_ignored` [agent 8]. |
| Edit list | None, or one edit with rate 1 and a media time at or above 0. A file with more than one edit, or with an empty edit after the first, is refused: "edit list not supported" [agent 9]. The v1 files have media time 0 [S 11.1]. |
| More than one video track | The first video track plays. Warning `extra_tracks`. |

## 4. Data path (Q688 open) [P 3] [P 4]

### 4.1 The rule

- The server lists the recordings. It serves the original bytes of the files by HTTP range. The page
  decodes [O].
- No decoded or converted video goes on the link. No copy is written next to the recording [O].
- The page reads each byte through the `TakeFiles` interface of 6a 5.1. The new implementation is
  `files/http-take-files.ts`, the place that 6a 5.9 keeps for it. It uses the acceptance rule of 6a
  5.6 (a 206 with the asked start, or a 200 with the exact length) and passes the shared check suite
  of 6a 5.1 (T-PLAY-39, T-PLAY-64, and T-LEG-14 here).

### 4.2 The server route (proposed) [agent 10]

The route follows the handler rules of 6a 5.3 to 5.6, on the server:

| Request | Result |
|---|---|
| `POST /skellycam/playback/open` with `{ "path": <folder> }` | The server takes the real path. It refuses a folder outside the allowed roots (below) with 403 and "folder not allowed". It makes the snapshot of 6a 5.4: the regular files of the root, of `synchronized_videos/` and of `synchronized_videos/timestamps/`, with their size and file ID; no links, no junctions, no file with more than one hard link. It answers `{ token, folderName, entries }`, with relative paths and sizes only. |
| `GET /skellycam/playback/files/<token>/<path>` | The bytes of 6a 5.6: no `Range` gives 200; `bytes=a-b` gives 206; each other form gives 416; only bytes below the snapshot size. Each response has `Content-Type: application/octet-stream`, `Cache-Control: no-store`, `Accept-Ranges: bytes`, and the expose header of 6a 5.6. |
| `DELETE /skellycam/playback/open/<token>` | Closes the token. A later request with it gets 404. |

- **Allowed roots** [P 4]: the skellycam recordings folder (6a 5.3), the FreeMoCap v1 data folder
  `<home>/freemocap_data` (the v1 default [INV]), and the folders of a list that only the settings of
  the server change. No request parameter can add a root.
- **Token.** 128 random bits, 32 lower-case hexadecimal characters (as 6a 5.2). A token ends at
  `DELETE`, at a stop of the server, and after 30 minutes with no request [agent 10].
- **CORS.** The route sends `Access-Control-Allow-Origin` for the origin of the UI, so that a page
  from another machine can read `Content-Range` [S 12.3: the study page read the study server from
  another origin] [NV: the exact origin list].
- **No log line for each range request.** Logging made the FastAPI route 25 % short in the transport
  test of 6a 11.2 [6a 14.4].
- **The present routes.** `list_recordings`, `list_videos` and `stream_video` of
  `skellycam/api/http/playback/playback_router.py` take a `recording_parent_directory` from the
  request and open each folder below it [C `playback_router.py` `_resolve_recording_path`]. With a
  UI on another machine, each client on the network can then read each such file of the server. The
  new route does not take a folder from a request. Section 5 proposes the removal of the old routes.
- **Authentication.** The server has none today [NV: whether the server binds to a network address
  other than the local machine]. A UI on another machine needs a network bind. This spec does not
  decide the bind or a login. Section 17 lists it.

### 4.3 The Electron `take-scheme` path of 6a [P 3] [agent 11]

The recommendation: keep both paths for now.

- The take-scheme of 6a 5.2 stays for the local app. It is measured: 16 cameras × 60 fps × 150 kB
  with 0 dropped ticks [6a 11.2].
- The HTTP path of 4.2 serves a UI on another machine, and v1 recordings in both cases.
- Both are implementations of `TakeFiles` and pass one check suite [6a L8]. The player code does not
  change between them.
- The review of option B (open work of 6a 14.4) decides later if the take-scheme goes. A v1 load is
  small: six `mp4v` tiles used 79 Mbit/s of link in the study [S 12.4].

The alternative is one HTTP path for all. It removes the Electron handler, but its performance on the
new format is not measured [6a 14.4].

## 5. One player (Q685 open) [P 5]

### 5.1 The rule (proposed)

A v1 recording plays in the canvas player. The `<video>` player of today then has no role:

- Chromium has no decoder for MPEG-4 Part 2. The `<video>` element does not play a v1 camera file
  (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) [S 11.2]. Thus the player of today plays no file that v1
  writes.
- The only files that `<video>` can play are H.264 files: v2 alpha files, which are out of scope [O],
  and imported files, which section 3 routes to the decoder.

### 5.2 What a removal would remove [agent 12]

The list is a code reading of 2026-11-24 [C]. The removal is a separate "code" PR after the legacy
player lands. Each item needs a check at that time.

| Item | File |
|---|---|
| The `<video>` player | `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx` (the type `PlaybackSettings` moves to `PlaybackControls.tsx`) |
| The `video` result of the route | `skellycam-ui/src/components/playback/take-route.ts` (`routeTake`, `chooseTakePlayer`), and the `SyncedVideoPlayer` branch of `skellycam-ui/src/pages/PlaybackPage.tsx` |
| The video loading of the context | `LoadedVideo` and the timestamp fetch of `skellycam-ui/src/contexts/PlaybackContext.tsx`; the `stream_url` use in `RecordingBrowser.tsx` |
| The URLs of the old routes | `playbackVideos`, the stream URL and `playbackTimestamps` in `skellycam-ui/src/services/server/server-helpers/server-urls.ts` |
| The old server routes | `list_videos`, `stream_video`, `get_all_timestamps` of `skellycam/api/http/playback/playback_router.py` (`list_recordings` stays, changed to list v1 recordings and new takes from the allowed roots) |
| The server transcode | `skellycam/core/recorders/videos/browser_stream.py` (H.264 fragments: a server-side conversion, against [O]), with `skellycam/tests/test_browser_stream.py` and `skellycam/tests/browser_stream_server.py` |
| The sync warning | F16 of `PlaybackControls.tsx` and its prop `hideSyncInfo` (6a 10, U3), because no player shows it |

`video_file_metadata.probe_video_files` and `recording_statistics` stay if another caller uses them
[NV].

This rule changes accepted text: E2 ("Old recordings keep a `<video>` path") and L5 ("No
restructuring of today's player") of 6a 18. Section 14 lists it. A "yes" to [P 5] is the decision
of the owner that changes them.

## 6. Frame accuracy and sync

### 6.1 The frame table [agent 13]

- The module reads the MP4 index itself, in TypeScript (`legacy/mp4.ts`): the top-level boxes by
  range reads, then `moov`. It reads `tkhd`, `mdhd`, `hdlr`, `stsd` (with `esds`, `avcC`), `stts`,
  `ctts`, `stss`, `stsz`, `stsc`, `stco`, `co64` and `elst`, and 64-bit box sizes.
- Frame k is sample number k in presentation order (by composition time, `stts` plus `ctts`). For
  `mp4v` from v1 there are no B-frames, so the decode order is the presentation order [S 11.1].
- For each frame the table holds: the presentation time stamp in track units, the key flag (from
  `stss`; all frames are key frames when `stss` is absent), the byte offset and the size.
- The frame count of a camera is the number of frames of its table whose bytes lie inside the
  snapshot size of the file. It is not `duration × fps` (as 6a F21 did) [agent 13].
- The tile worker opens the same file with FFmpeg's own MP4 demuxer, as the study measured
  [S 12.3]. At open, the module compares the frame count and the time stamps of its table with the
  index of the demuxer. A difference refuses the camera: "camera file index mismatch" [agent 13]
  [P 20].

### 6.2 Exact seek and step [agent 14]

The player asks the tile worker for frame k. The worker:

1. continues the live decoder when the last frame that it gave out is j < k and no key frame is in
   (j, k]. The study continued up to 30 frames ahead; the rule here is stricter, as the study advises
   [S 12.4, S 12.5 product notes];
2. else seeks back to the key frame at or before frame k (`av_seek_frame` with
   `AVSEEK_FLAG_BACKWARD` on the time stamp of frame k), flushes the decoder, and decodes;
3. gives out only the frame whose time stamp **equals** the time stamp of frame k in the table. The
   study used a tolerance of 0.45 frame [C study `wasm.mjs`]; the rule here is exact;
4. keeps the decoded frames after frame k for the next forward steps, at most the queue limit of 7.3;
5. reports an error when the decoder gives out a later frame and no frame with the time stamp of
   frame k (section 8.2).

- `step(+1)` continues the decoder (one frame). `step(-1)` seeks back and decodes from the key frame:
  at most 11 frames for the GOP of 12 of v1 [S 12.4].
- `seekFrame(k)` and `step(n)` set k* and t as 6a 7.2. The newest request wins (6a 7.5): each tile
  has at most one request in its worker and one pending target.

### 6.3 Cameras with different frame counts [P 6] [agent 15]

- K is the smallest frame count of the cameras that play, as the player of today (F21) and 6a K.
  The frames from K on are not shown.
- When the counts differ, the take gets the warning `frame_count_differs` with each count. The host
  shows it.
- All v1 samples of one session have equal frame counts [S 11.1]. The v1 synchronizer clips the
  cameras to their overlap [INV quirks]. A difference can come from an import or from a damaged file.
- A refused camera does not count for K (as 6a T-PLAY-05).

### 6.4 The frame-to-time map [P 7] [agent 16]

The frame index is the truth. Tile c shows frame k* of camera c. It never chooses a frame by time.
This differs from 6a 7.3, which chooses by time for the new format. The reason: the v1 synchronizer
already matched the frames of the cameras; frame k of each camera is one moment, and the FreeMoCap
processing uses the frames by index [INV quirks, dropped frames].

The times serve the clock, the labels and the pace only:

- **With one or more usable time files:** v_c(k) is the value of camera c at frame k, in integer
  nanoseconds. The base B is the smallest finite v_c(0) of the cameras. U_k is the mean of the finite
  v_c(k) over the cameras with a usable time file (as FreeMoCap v1 takes the mean over the cameras
  [INV `data_loader.py`]). T_k = max(T_(k-1), U_k − B). When no camera has a finite value at row k,
  T_k = T_(k-1). T_0 = U_0 − B, or 0 when U_0 has no value.
- **With no usable time file:** r is the median of the header rates of the cameras (each rate is the
  `mdhd` time scale divided by the sample duration, a rational number). T_k = round(k × 10^9 / r).
  The v1 header rate is a per-camera median of the capture rate, so the cameras can differ [S 12.1
  row 1].
- **Tile label.** A camera with a usable time file shows v_c(k*) − B, or no time part for a frame with
  no time. A camera with no usable time file shows T_k* with a `~` in front.
- **"Rec: fps"** (F15) shows r, rounded to 3 decimals [agent 16].
- Play, pause and the end follow 6a 7.4 on these T_k. During play, k* is the largest k with T_k ≤ t.

### 6.5 Synchronised play: the locked rule [agent 17]

- Each tile worker streams decoded frames ahead of the clock, with one credit for each frame, at most
  8 frames ahead [S 12.3].
- At each display refresh, the clock gives a target frame. The frame k* that all tiles show is the
  smallest of the target and the newest frame that each tile has ready. Thus all tiles show the same
  frame number on each refresh. When a tile is late, the clock waits for it. This is the `locked`
  mode of the study. The study advises it: in the `free` mode at 100 Mbit/s, tiles were one frame
  apart on 1 to 2 refreshes of about 750 [S 12.4].
- The count "behind the clock" is the share of refreshes on which k* is below the target. It goes to
  the benchmark results (section 12).
- At a speed above 1, the decoder still decodes each frame, because the later frames depend on the
  earlier frames. The tiles show a part of the frames. The locked rule slows play when the decoders
  cannot keep up [NV: the rate at speed 8].

## 7. The decoder in the page

### 7.1 One worker for each tile [S 12.3]

- Each tile has one module worker. The worker loads the decoder, opens the original file with
  FFmpeg's demuxer through a libav.js block reader device, and decodes with FFmpeg's decoder.
- A worker per tile keeps the decoder state of the tile (its place in the GOP and its kept frames).
  A crash stays in one tile. Plain WASM has no threads, so one tile uses at most one core [S 12.3].
- **Bytes.** The worker reads blocks of 256 KiB through `TakeFiles.readRange`, keeps the last 16
  blocks (4 MiB), and reads one block ahead when the reads are sequential [S 12.3]. These values are
  not tuned [S 12.6]. Exact packet ranges from the frame table are a later change after a measurement
  [S 12.5 product notes] [P 20].
- **Out of the worker.** The worker sends the decoded planes, packed, in the format of the decoder
  (I420, I422 or I444), as a transferable buffer [S 12.3]. The page makes a `VideoFrame` and gives it
  to the tile as `TileUpdate.image`. The decoded frames stay inside the browser process. They do not
  go on the HTTP link [O].

### 7.2 Load of the module [agent 18]

- The module files come with the UI bundle (section 9.4), not from the server of the recording.
- The page fetches the WASM file once and lets the HTTP cache keep it. The study fetched and compiled
  it once for each worker (2.4 MB; import 2 to 5 ms, instantiate 19 to 30 ms; all tiles ready with
  the file open in 46 to 73 ms) [S 12.4].
- When libav.js accepts a compiled `WebAssembly.Module`, the page compiles once and gives it to each
  worker [NV: that libav.js 6.10.9 accepts it].
- A Content Security Policy of the page must allow WASM (`'wasm-unsafe-eval'`) [NV: the policy of the
  app today].

### 7.3 Queues and memory [agent 19]

| Item | Limit | Source |
|---|---|---|
| Decoded frames ahead of the clock, each tile | 8 | [S 12.3] |
| Decoded frames held, each tile | 8 + 1 (on the tile) + 1 (in transfer) | as 6a 9.4 |
| Block cache, each tile | 16 × 256 KiB = 4 MiB | [S 12.3] |
| WASM heap, each tile | measured 24 MiB, no growth [S 12.4]. Proposed maximum 512 MiB (a build flag); a decoder that asks for more fails, and section 8.2 applies | [agent 19] |
| Renderer working set | measured 180 to 400 MB for 1 to 6 tiles [S 12.4] | |

### 7.4 Many cameras [agent 20]

- Measured: up to 6 tiles of 720x1280 `mp4v`; the renderer used about 0.76 of a core for 6 tiles in
  play [S 12.4].
- Proposed: no upper limit on the camera count. The tests and the benchmarks go to 16 tiles. Above 16
  cameras, the host shows the warning "more than 16 cameras: playback is not tested" [NV: 16 tiles].

## 8. Reliability

### 8.1 Open

| Case | Result |
|---|---|
| A camera file with no `moov` (the writer did not finish, or the file is cut) | Refused: "camera file not playable: no index (moov); the recording did not finish". No repair [O]. |
| `moov` at the end of the file | Normal for v1 [S 11.1]. The reader finds it with 1 to 3 range reads; the study read 0.26 to 0.75 MB in 6 to 41 ms for each tile [S 12.4]. |
| A frame whose bytes lie past the snapshot size | Not in the frame count (6.1). |
| An index box that is cut, or a box size that points past its parent | Refused: "camera file index damaged". |
| A refused camera | The mark `not_readable` with the text; the other cameras play (6a L3). |
| No camera plays | The host shows the text of the first refusal and no grid. |

### 8.2 During play and seek [agent 21]

| Fault | Result |
|---|---|
| The decoder reports an error on frame k, or gives out no frame with the time stamp of frame k | The tile keeps its last image with the mark "damaged at frame k" (6a 8.3 `damaged`). The next frame decodes normally. The camera is not refused (as 6a T-PLAY-74). |
| A read error (`readRange` fails) | The mark "read error" with the last image, and an `error` event (6a 5.7). |
| The worker ends (a crash, a WASM trap, out of memory) | The page starts a new worker for the tile and asks for frame k*. During the restart the tile keeps its last image. After 3 restarts in 60 s, the tile gets the mark "decoder failed" and makes no more restarts until the player opens again. |
| A worker gives no answer in 10 s | The page ends the worker. Then the row above applies. |
| A tile is late in play | The locked rule waits (6.5). No tile shows another frame number. |

The other tiles keep playing in each case [6a L3].

### 8.3 What the study measured

Two runs of each script: the same frame hash on each operation of both runs (1,850 operations), no
decoder error, no worker error, no Electron child process lost [S 12.4]. Hours-long files, many
plays in a row and the decoder on macOS, Linux or a weak CPU are not tested [S 12.6].

## 9. The decoder build as a product part

### 9.1 Where the recipe lives [agent 22]

A new folder `skellycam-ui/decoder/`:

| File | Content |
|---|---|
| `package.json`, `package-lock.json` | One dev dependency: `"libav.js": "6.10.9"` (exact). The lock file holds the integrity hash of the tarball. FFmpeg comes inside this tarball (`sources/ffmpeg-9.0.tar.xz`) [S 12.2]. |
| `Dockerfile` | One stage only: `FROM emscripten/emsdk:6.0.8@sha256:<digest>` and the build steps. |
| `build.sh` | The build steps of the study `wasm_build.sh`, with the part list of 9.2 and the variant name `skellycam-legacy`. |
| `parts.json` | The part list (the input of `mkconfig.js`) and the expected decoder, demuxer and parser lists of the checks. |
| `README.md` | How to build, how to replace the library (9.5), the licences. |

The outputs (`libav-<version>-skellycam-legacy.mjs`, `.wasm.mjs`, the licence file, `config.json`,
`ffmpeg-config.txt`, `BUILD_INFO.json` with the input versions, the image digest and the SHA-256 of
each output) go to `skellycam-ui/decoder/dist/`. Git ignores this folder (9.4).

### 9.2 The part list for v1 only [agent 23]

| Part | v1 needs it | Decision |
|---|---|---|
| `avformat`, `avcodec` | yes | in |
| `demuxer-mp4` (mov) | yes: each v1 file is MP4 | in |
| `decoder-mpeg4`, `parser-mpeg4video` | yes: the v1 writer and the sample data [S 12.1] | in |
| `decoder-h264`, `parser-h264` | for H.264 imports [P 1] | in, when [P 1] is yes |
| `decoder-hevc`, `parser-hevc` | for HEVC imports; never tested, no sample [S 12.6] | out [P 2] |
| `demuxer-avi` | no: AVI comes only from the v2 alpha fallbacks [S 12.1 row 9]; the import wizard takes `.mp4` only | out |
| `decoder-msmpeg4v3` | no: no v1 writer uses it; it was in the study build, not tested [S 12.6] | out |
| `demuxer-matroska`, `decoder-mjpeg`, `parser-mjpeg` | no: the new MKV takes play with `ImageDecoder` (6a); MJPEG in AVI is v2 alpha | out |

This list is smaller than the measured build of the study. The checks and the conformance tests of
section 13 prove it again [NV until they run].

The build keeps the settings of the study: no external library, plain WASM, no threads, no SIMD,
`-Oz`. An `-O3` build decoded no faster and was 3.6 MB instead of 2.4 MB [S 12.2].

### 9.3 The CI build and its checks [agent 24]

A job `decoder-build` on `ubuntu-24.04` (Docker is on the Linux runners) does these steps:

1. Resolve the digest of the image tag `emscripten/emsdk:<tag>` and compare it with the digest in the
   `Dockerfile`. A difference fails the job.
2. `npm ci` in `skellycam-ui/decoder/` (the tarball by its lock-file integrity).
3. Build in the container. Then build again, clean, and compare the SHA-256 of each output. A
   difference fails the job (a reproducible build) [NV: that the emscripten build is byte-identical
   run to run].
4. Check `config.h` and `config.mak` of the FFmpeg build: `CONFIG_GPL 0`, `CONFIG_NONFREE 0`,
   `CONFIG_VERSION3 0`; the set of `CONFIG_*_DECODER 1` equals the decoder list of `parts.json`; the
   same for the demuxers and the parsers; `FFMPEG_CONFIGURATION` has no `--enable-lib`.
5. Check the size of the WASM file: at most 4 MiB [agent 24].
6. Check the pins: `package.json` has an exact version (no `^`, no `~`, no range); the `FROM` line
   has a tag and a digest.
7. Write `BUILD_INFO.json` and upload the outputs as a workflow artefact.
8. Cache the outputs with the key = the SHA-256 of the files of `skellycam-ui/decoder/` (except
   `dist/` and `README.md`). A cache hit skips steps 2 to 5 and still runs steps 1 and 6.

The conformance test (T-LEG-24, T-LEG-25) and the player tests (section 13) then use the artefact of
this job.

### 9.4 How the UI gets the built files [P 8] [agent 25]

| Option | For | Against |
|---|---|---|
| A. Build in CI, do not commit (recommended) | No binary in git history. The recipe is the source of truth. The owner's rule for research results (do not commit files that a build can make) points the same way. | Each build of the app needs the CI artefact or a Docker build. A developer needs Docker, or downloads the artefact of the last CI run (`gh run download`). |
| B. Commit the outputs (about 2.4 MB each bump), and let CI rebuild and compare | A plain `npm run dev` works with no Docker. A reviewer sees the change of the bytes in the PR. | A binary in git history at each bump. A Dependabot PR cannot update the outputs, because a workflow of a Dependabot PR gets a read-only `GITHUB_TOKEN` [D troubleshoot]. Then a bump is not "review and merge". |

With option A:

- `skellycam-ui/decoder/dist/` is in `.gitignore`.
- `npm run decoder:build` builds with Docker. `npm run decoder:fetch` downloads the artefact of the CI
  run for the recipe hash and checks the SHA-256 of `BUILD_INFO.json`.
- The installer workflow (`build-installers-pyinstaller.yml`) gets a first job that builds the
  decoder or restores it from the cache. Each installer job downloads it in the same workflow run.
  Thus the 90-day life of an artefact does not matter.
- The app puts the decoder files outside the `asar` archive (as `extraResources`), so that a user can
  replace them (9.5).

### 9.5 LGPL duties [agent 26]

FFmpeg in this build is LGPL 2.1 or later [S 12.2]. The libav.js README says: "FFmpeg is released
under the LGPL. Therefore, if you distribute this library, you must provide sources." The duties of
the app:

1. **Licence text.** The app and its release include the LGPL 2.1 text, the licence file that the
   build writes (`license.js` of the variant), and the licence of the libav.js wrapper [NV: the study
   notes name it ISC; the README of libav.js names "0-clause BSD" for the wrapper functions].
2. **Source.** Each release offers the exact source: the libav.js npm tarball named by its lock-file
   integrity (it holds the FFmpeg and libav.js sources in `sources/`), and the recipe of 9.1. The
   release workflow attaches the tarball to the GitHub release [agent 26].
3. **Replace the library.** The decoder is a separate file that the app loads at run time. The
   `README.md` of 9.1 tells a user how to build a changed library with the recipe and where to put it
   in the installed app. The app checks the SHA-256 of the decoder at load and logs a warning for an
   unknown file. It does not refuse it, because a refusal would stop the replacement.
4. **No GPL part, no non-free part** (the checks of 9.3).

This is not legal advice. Section 16 asks the owner about the patent position [P 15].

## 10. Dependabot and upstream monitoring

The owner's condition: the work "must also include suitable dependabot scripts to monitor upstream
repos and trigger build and pr tests so it is minimal work to keep our custom build up to date" [O].

### 10.1 The pinned inputs and who watches each one [agent 27]

| Input | Pin | Watched by |
|---|---|---|
| libav.js (and FFmpeg inside its tarball) | `skellycam-ui/decoder/package.json`, exact | Dependabot `npm`, directory `/skellycam-ui/decoder` |
| emsdk image | `skellycam-ui/decoder/Dockerfile`, tag and digest | Dependabot `docker`, directory `/skellycam-ui/decoder` |
| CI actions (checkout, setup-node, cache, upload and download artefact, setup-uv) | full SHA with the version comment on the same line | Dependabot `github-actions`, directory `/` |
| PyAV (makes the test media and the reference, section 13.1) | `pyproject.toml` `av==19.0.2` | not by this work: the Python pins have their own review [NV: no `pip`/`uv` entry in `dependabot.yml` today] |
| Electron (its Chromium draws the tiles) | `skellycam-ui/package.json` | the existing `npm` entry, after its repair (10.5) |

### 10.2 The `dependabot.yml` entries (to write in the CI PR) [agent 28]

```yaml
  - package-ecosystem: "npm"
    directory: "/skellycam-ui/decoder"
    schedule:
      interval: "weekly"
    versioning-strategy: "increase"
    groups:
      decoder-npm:
        patterns: ["libav.js"]
  - package-ecosystem: "docker"
    directory: "/skellycam-ui/decoder"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

Facts from the documentation [D ecosystems] [D options] [D registries]:

- `npm`, `docker` and `github-actions` are the `package-ecosystem` values. Version updates are
  supported for all three. Security updates are supported for `npm` and `github-actions`, and **not
  for `docker`**.
- For `github-actions`, the directory `/` makes Dependabot look in `/.github/workflows`. Dependabot
  updates an action pinned to a commit, and it updates the version comment "when the comment is on
  the same line".
- For a Dockerfile: "Dockerfiles may only receive a version update to the first `FROM` directive";
  "Dockerfiles do not receive updates to images specified with the `ARG` directive"; "Dependabot
  doesn't support multi-stage Docker builds". Thus the `Dockerfile` has one stage and one `FROM` with
  the image written in full.
- A default cooldown of 3 days applies to version updates, not to security updates. The default
  `open-pull-requests-limit` is 5.
- `versioning-strategy` `increase`: "Always increase the minimum version requirement to match the new
  version" [NV: that an exact pin stays exact; check 6 of 9.3 fails the PR if it does not].
- The pages that the agent read do not say if Dependabot updates the digest of a `FROM` line with a
  tag and a digest [NV]. Check 1 of 9.3 fails a PR whose digest does not belong to its tag.

### 10.3 What Dependabot cannot see, and how the gap is covered [P 9] [P 10] [agent 29]

| Gap | Why | Cover |
|---|---|---|
| A security fix of FFmpeg before a libav.js release | FFmpeg is inside the libav.js tarball. It is not an npm package, so no npm advisory names it [NV]. | The weekly workflow below. |
| A security fix of the emsdk image | Dependabot has no security updates for `docker` [D ecosystems]. | The weekly version updates of `docker`. A known CVE in the toolchain affects the build machine, not the users: the WASM output holds no toolchain code beyond the emscripten runtime [NV]. |
| An FFmpeg point release (for example 9.0.x) | The tarball of libav.js 6.10.9 is `ffmpeg-9.0.tar.xz` [S 12.2] [NV: which point release it holds]. | The weekly workflow compares it with the FFmpeg release tags. |
| A libav.js release that changes its build or its API | Dependabot gives a version number only. | The PR pipeline of 10.4 builds and tests the bump. |

The weekly workflow `decoder-upstream.yml` (scheduled, and by hand):

1. Reads the FFmpeg version inside the pinned libav.js tarball.
2. Lists the FFmpeg release tags with `git ls-remote --tags` of the FFmpeg git repository (read
   only, no token).
3. Lists the libav.js release tags of its GitHub repository.
4. Reads the FFmpeg security page (`https://ffmpeg.org/security.html`) and keeps each CVE listed under
   a version newer than the pinned FFmpeg version.
5. Opens one issue, or updates the open one, with the title "decoder upstream: <summary>", when it
   finds a newer FFmpeg point release, a newer libav.js release that Dependabot has not opened yet, or
   a CVE of step 4. The job has `permissions: issues: write` and `contents: read` only.

Limits, said plainly:

- The workflow reports. It does not fix. A fix needs a libav.js release, or a change of the recipe
  that takes an FFmpeg source tarball other than the one in libav.js [P 10] [NV: that the libav.js
  build accepts another FFmpeg tarball].
- A CVE list seldom names the decoder that it affects. A person must decide if a CVE touches
  `mpeg4`, `h264` or the `mov` demuxer.
- When the format of a page changes, the workflow fails. A failed scheduled run is red in the
  Actions tab [NV: who gets the notice of a failed scheduled run].

### 10.4 The pipeline of a bump PR [agent 30]

A Dependabot PR that changes a file of `skellycam-ui/decoder/` or a workflow starts these jobs. Each
one is a required check of the PR:

1. `decoder-build`: the build, the checks of 9.3 and the artefact.
2. `decoder-conformance` (Linux, Windows, macOS): T-LEG-24 and T-LEG-25 in Node with the new artefact.
3. `player-windows`, `player-linux`, `player-macos` of `player.yml`, with the new artefact: the unit,
   component and electron tests of 6a and of this spec.

No step of the pipeline needs a secret. A workflow that Dependabot starts gets a read-only
`GITHUB_TOKEN` and only the Dependabot secrets. Its `pull_request` runs are "treated as if they were
opened from a repository fork" [D troubleshoot]. When all checks pass, the bump is "review
and merge". When a check fails, the PR shows which part of the bump broke.

The workflow of today, `player.yml`, gets the path `skellycam-ui/decoder/**` in its filters, and the
`decoder-build` job before its three jobs. Each test job downloads the artefact (`needs:
decoder-build`).

### 10.5 A finding on the `dependabot.yml` of today [P 14]

The present file has one entry: `npm` with directory `/` and a monthly schedule
[C `.github/dependabot.yml`]. The repository root has no `package.json` [C]. The npm manifests are in
`skellycam-ui/` and `skellycam-docs/`. Thus this entry finds no manifest [NV: the Dependabot log of
the repository]. The agent proposes to change the directory to `/skellycam-ui` (and to add
`/skellycam-docs`) in the CI PR of this work.

### 10.6 Documentation read

- [D ecosystems]: "Dependabot supported ecosystems and repositories",
  `https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories`.
- [D options]: "Dependabot options reference",
  `https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference`.
- [D registries]: "Guidance for the configuration of private registries for Dependabot", section
  Docker,
  `https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-private-registries`.
- [D troubleshoot]: "Troubleshooting Dependabot on GitHub Actions",
  `https://docs.github.com/en/code-security/reference/supply-chain-security/troubleshoot-dependabot/dependabot-on-actions`.

## 11. Changes of the module and of the host

### 11.1 Module layout [agent 31]

New files in `skellycam-ui/src/player/`:

| Path | Content |
|---|---|
| `legacy/detect.ts` | The rules of 2.2: `isLegacyFolder(files)` gives `'v1'`, `'v2_alpha'` or `null`. |
| `legacy/mp4.ts` | The MP4 index reader of 6.1 and the codec route of 3.1. |
| `legacy/npy.ts` | The time file parser of 2.3. |
| `legacy/take.ts` | `openLegacyTake(files, options)`: the cameras, K, T_k and the warnings. It gives the `TakePlayer` of 6a 4.4. |
| `legacy/decoder-client.ts` | The page side of a tile worker, with the restarts of 8.2. |
| `legacy/decoder-worker.ts` | The tile worker. It is the only file that imports the decoder. |
| `files/http-take-files.ts` | The HTTP implementation of `TakeFiles` (4.1). |

The boundary rule of 6a 4.2 gets one more allowed import: the decoder files, only from
`legacy/decoder-worker.ts`. T-PLAY-35 checks it.

### 11.2 Interface additions [agent 32]

```ts
openLegacyTake(files: TakeFiles, options?: OpenTakeOptions): Promise<TakePlayer>
isLegacyFolder(files: TakeFiles): Promise<'v1' | 'v2_alpha' | null>
httpTakeFiles(serverUrl: string, folderPath: string): Promise<TakeFiles>

// PlayerState.take gets one field:
kind: 'take' | 'freemocap_v1';
// CameraState.reason gets the codes of sections 3 and 8:
// 'codec_not_supported' | 'pixel_format_not_supported' | 'edit_list_not_supported' | 'no_moov'
// | 'index_damaged' | 'index_mismatch'
// TileLabel gets one optional field:
timeEstimated?: boolean;   // true: the tile shows `~` before the time (2.4)
```

### 11.3 A text change of 6a 8.3 [agent 33]

6a 8.3 says that `jpeg` holds the bytes of the frame of `image`. The tile code of today already draws
`image` when `jpeg` is null [C `tile/tile.ts` `update`]. The legacy player gives `image` with `jpeg`
null, because it has no JPEG. 6a 8.3 then needs one sentence: "An update with `image` and `jpeg` null
is a new image." This spec does not change `player.md` before the owner accepts it.

### 11.4 Host [agent 34]

- The route of 6a 10 gets one more branch: a v1 folder (2.2) opens in `CanvasTakePlayer` with
  `openLegacyTake`. A v2 alpha folder and an unknown folder show their text of 2.2.
- With [P 5] yes, the `video` branch goes (section 5).
- The host shows the take warnings (`frame_count_differs`, `time_file_unusable`, `matrix_ignored`,
  `extra_tracks`) as information, and the warning of 7.4.

## 12. Performance

### 12.1 Measured (the study; shared machine; run 1 / run 2) [S 12.4] [S RT]

| Set | Tiles | Seek p50 / p95 ms | Forward step p50 / p95 | Backward step p50 / p95 | Play, 20 s, locked |
|---|---|---|---|---|---|
| treadmill session, `mp4v` 720x1280 | 6 | 36.5 / 51.7; 35.6 / 50.9 | 8.9 / 11.6; 8.1 / 10.4 | 27.9 / 43.2; 24.7 / 41.5 | 0 differing refreshes, unlimited and 100 Mbit/s |
| FreeMoCap sample data, `mp4v` 720x1280 | 3 | 29.2 / 48.1; 29.8 / 48.6 | 6 / 9.1; 6.9 / 9.6 | 24.2 / 38.1; 24.4 / 39.1 | 0 differing refreshes |

Also: link 79 Mbit/s for the six treadmill tiles; at 100 Mbit/s, 0 to 0.7 % of refreshes behind the
clock (single refreshes at the start); start of play 14 to 50 ms unlimited, 70 to 680 ms at
100 Mbit/s [S 12.4].

### 12.2 Targets (proposed; the benchmarks of 13.4 verify them) [agent 35]

| Case | Target |
|---|---|
| 6 tiles, `mp4v` 720x1280, GOP 12 | seek p50 ≤ 50 ms, p95 ≤ 100 ms; backward step p50 ≤ 40 ms; forward step p50 ≤ 15 ms |
| Same, play 60 s at speed 1 | 0 refreshes with different frame numbers on the tiles; after 1 s, at most 1 % of refreshes behind the clock |
| 16 tiles, `mp4v` 640x480 | play 60 s with at most 1 % behind the clock; renderer at most 4 cores [NV] |
| H.264 import, 1080p, GOP 30 (with [P 1] yes) | no target; results recorded for the owner |

## 13. Tests

### 13.1 Test media [P 11] [P 12] [P 13] [agent 36]

No camera recording and no camera frame goes into the repository (`AGENTS.md` section 8). A test
media file needs a decision of the owner [O]. The proposal:

- **Synthetic media at test time.** A new tool `tools/make_legacy_media.py` writes the media into a
  temporary folder at the start of a test run, with PyAV `av==19.0.2` (pinned in `pyproject.toml`,
  libavcodec 63.1.102). The study made its stand-ins in the same way, from real material
  (`py/make_legacy_standins.py`) [S 12.1]. This tool makes the pictures itself: a barcode of the
  camera index and the frame number, on a moving pattern, so that each frame differs. It writes:
  - `mp4v` in MP4 as the v1 writer: FFmpeg's `mpeg4` encoder, tag `mp4v`, GOP 12, no B-frames,
    `yuv420p`, `moov` at the end (no fast start), sizes 720x1280, 640x480 and 1228x574, 30 fps;
  - a v1 folder around them: `synchronized_videos/Camera_000_synchronized.mp4` and its time file with
    perf-counter-like values, NaN values, duplicates and a short file;
  - H.264 in MP4 (with [P 1] yes): `libx264` Baseline GOP 30, and High with B-frames GOP 250 and an
    edit list. `libx264` is GPL. It makes only test media in CI; nothing of it ships.
  - the reference: the SHA-256 of each decoded frame, from a PyAV decode (x86-64 or arm64 FFmpeg).
  The encoders `mpeg4`, `libx264` and `libx265` open in PyAV 19.0.2 on the Windows development
  machine (checked 2026-11-24) [NV: on Linux and macOS wheels].
- **Hash rule.** For each frame: SHA-256 of the Y plane, then the U plane, then the V plane, each as
  its rows of the plane width with no stride padding. This is the rule of the study [S RT terms].
- **Real v1 files.** Two sources, never committed:
  - The official FreeMoCap sample data: CI downloads it from the URL of the FreeMoCap v1.8.2 code,
    checks its SHA-256, and keeps it in a temporary folder and in the CI cache [P 12].
  - The treadmill session (2024, 6 cameras): only on the machine of the owner, from a folder that an
    environment variable names (`SKELLYCAM_LEGACY_V1_DIR`). The test is skipped when the variable is
    not set [P 13].

What only a real v1 file can prove: the box layout of the OpenCV muxer of each v1 version, the real
bit rates and sizes, a time file of a real capture with real duplicates, the old names of the sample
data, and the times of 12.2 on real files. The synthetic media proves the decoder, the frame table,
the time map and the faults.

### 13.2 Kinds and runners

- **unit**: Node, `node --test --experimental-strip-types`, as 6a 12.1. No browser. The worker is a
  test double, except in T-LEG-24 and T-LEG-25, which run the real decoder in Node.
- **component**: Electron 45.3.4 with Playwright 1.65.1, as 6a 12.1, with the real decoder in module
  workers.
- **server**: `pytest` of the Python package (`skellycam/tests/`), with files of random bytes.
- **build**: the `decoder-build` job (Linux, Docker).
- **tool**: `uv run pytest tools/tests` (the doc checks), for the CI and Dependabot files.
- **benchmark**: the Windows test machine, by hand, as 6a 12.1. Not in CI.

Each unit, component and server test runs on Windows, Linux and macOS in CI (6a Y7). No test needs a
camera. Other systems are tested only through CI, a runner with no device [O] (`AGENTS.md` section 4).

### 13.3 Test list

"Gen" in the Media column means media from `tools/make_legacy_media.py` at test time. "None" means
bytes that the test builds with no codec data (box structures, NPY headers, file lists).

| ID | Kind | Systems | Media | What it does | Pass criterion |
|---|---|---|---|---|---|
| T-LEG-01 | unit | W, L, M | none | `isLegacyFolder` on file lists: v1 names; sample-data names; import names; `.MP4`; a new take with a manifest; v2 alpha names `<rec>.id-0.idx-0.mp4`; no `synchronized_videos/`; only `annotated_videos/`. | `'v1'`, `'v1'`, `'v1'`, `'v1'`, `null` (6a route), `'v2_alpha'`, `null`, `null`; the texts of 2.2. |
| T-LEG-02 | unit | W, L, M | none | NPY headers: versions 1.0, 2.0, 3.0; `<f8` 1-D; `>f8`; `<f4`; `fortran_order` True; shape `(n, 2)`; a header that is cut; data shorter than the shape. | Only the first three with `<f8` 1-D parse; each other gives `time_file_unusable` with its reason; no exception escapes. |
| T-LEG-03 | unit | W, L, M | none | Time map with time files: 3 cameras with offsets, a NaN in one camera, a row with NaN in all cameras, a duplicate value, a value above 2^53 ns. | T_k as 6.4 against an independent `BigInt` reference; T_k never goes down; the row with no value gives T_(k-1); tile labels as 6.4. |
| T-LEG-04 | unit | W, L, M | none | Time map with no time file: header rates 30, 29.97 and 30.5 in 3 cameras. | r is the median (30); T_k = round(k × 10^9 / r); `timeEstimated` true; "Rec: fps" 30.000. |
| T-LEG-05 | unit | W, L, M | none | One camera with a time file of the wrong length; one with none; one usable. | The usable one gives T_k; the others get `time_file_unusable` (`length`, `missing`) and labels with `~`. |
| T-LEG-06 | unit | W, L, M | none | MP4 index reader on built box trees: `moov` at the end and at the start; `co64`; `stsc` runs; `stss` absent and present; `ctts`; a 64-bit box size; a last box of size 0; `elst` with one edit, two edits, an empty edit; a file with no `moov`; a `moov` past the snapshot; frames past the snapshot; `tkhd` matrices 0, 90, 180, 270 and a shear. | The frame table equals a reference that the test computes by hand; `no_moov`, `index_damaged`, `edit_list_not_supported` where 3.3 and 8.1 say; the frame count leaves out the frames past the snapshot; rotations as 3.3; `matrix_ignored` for the shear. |
| T-LEG-07 | unit | W, L, M | none | Codec route on sample entries: `mp4v` 0x20, `mp4v` 0x61, `avc1`, `avc3`, `hvc1`, `hev1`, `av01`, `vp09`, `jpeg`, an unknown entry; and a file named `.avi` with `mp4v` content. | The routes of 3.1 (with the answers to [P 1] and [P 2]); the route depends only on the content; each refusal text names the entry. |
| T-LEG-08 | unit | W, L, M | none | Frame counts 120, 118, 120, and one refused camera. | K = 118; `frame_count_differs` with the three counts; the refused camera is not in K. |
| T-LEG-09 | unit | W, L, M | none | Camera order and labels: `Camera_000`..`Camera_011`; `..._synced_Cam1`..`Cam10`. | Natural order (`Cam2` before `Cam10`); the label is the file stem. |
| T-LEG-10 | unit | W, L, M | none | Seek planner on frame tables with GOP 12, GOP 30 and all key frames: forward targets inside and across a key frame, backward targets, the first and the last frame. | Continue only when no key frame is in (j, k]; else a seek to the key frame at or before k; the asked time stamp is the exact table value. |
| T-LEG-11 | unit | W, L, M | none | Worker faults with a fake worker: one crash; 3 crashes in 60 s; no answer for 10 s; a crash during a seek drag. | A new worker and frame k* after one crash; "decoder failed" after the third; the hung worker ends; the other tiles get each frame; no request of an older target is drawn after a newer one. |
| T-LEG-12 | unit | W, L, M | none | A fake decoder that fails on frame 30, and one that skips the time stamp of frame 30. | "damaged at frame 30" at frame 30 only, with the image of frame 29; frame 31 has no mark; the camera is not refused. |
| T-LEG-13 | unit | W, L, M | none | Each refusal and warning text of sections 2, 3 and 8. | Each text and reason code as the spec gives it. |
| T-LEG-14 | unit | W, L, M | none | The shared `TakeFiles` check suite of 6a 5.1 on `http-take-files.ts` against a Node test server; and the answers 200 with the whole file and 206 with a wrong start. | The results of T-PLAY-39; the two wrong answers are read errors. |
| T-LEG-15 | server | W, L, M | none | The route of 4.2: open, the range table of 6a 5.6, the snapshot, a deleted token, an unknown path, `..` forms, a link to an outside file, a folder outside the roots, a `recording_parent_directory` parameter. | Status, bytes and headers as 6a 5.6; 403 "folder not allowed" outside the roots; no byte of a file outside the snapshot; the parameter adds no root. |
| T-LEG-16 | server | W, L, M | none | Read 6 files by range for 20 s through the route while a spy counts the bytes that the server reads and sends. | Each response body is a byte range of an original file; no route writes a file; no decoded frame (the server imports no video library in this route: a test of the imports). |
| T-LEG-20 | build | L | none | The checks of 9.3, steps 4 and 5, on the built outputs. | `CONFIG_GPL 0`, `CONFIG_NONFREE 0`, `CONFIG_VERSION3 0`; the decoder, demuxer and parser sets equal `parts.json`; no `--enable-lib`; WASM at most 4 MiB. |
| T-LEG-21 | build | L | none | Two clean builds of the same recipe. | Equal SHA-256 for each output [NV until it runs]. |
| T-LEG-22 | build | L | none | The pin checks of 9.3, steps 1 and 6. | Exact npm version; a tag and a digest in the `FROM` line; the digest belongs to the tag. |
| T-LEG-23 | build | L | none | The licence files in the outputs and in an app package. | The LGPL 2.1 text, the variant licence, the wrapper licence and the recipe reference are present; the decoder files are outside the `asar`. |
| T-LEG-24 | unit (real decoder) | W, L, M | gen | Decode each frame of the generated `mp4v` files (720x1280, 640x480, 1228x574) in Node with the built decoder. | Each frame hash equals the PyAV reference; the frame count equals the table. |
| T-LEG-25 | unit (real decoder) | W, L, M | gen | As T-LEG-24 for the H.264 files (with [P 1] yes). | Each frame hash equals the reference; the edit list file gives the frames of the edit only. |
| T-LEG-26 | unit (real decoder) | W, L, M | gen | The frame table of `legacy/mp4.ts` against the index of FFmpeg's demuxer in the worker, on each generated file. | Equal frame counts and equal time stamps; `index_mismatch` for a test file whose `stts` the test changed. |
| T-LEG-27 | component | W (owner machine); L in CI with [P 12] | real | The official sample data and, on the owner machine, the treadmill session: full decode and 100 random seeks + 48 steps per set. | Each frame hash equals a PyAV reference made at test time; each seek and step lands on the asked frame. |
| T-LEG-30 | component | W, L, M | gen | 6 tiles of 720x1280 `mp4v`: 100 random seeks (seed 1), the first and the last frame, each key frame and its neighbours. | Each tile gives the plane hash of frame k (checked in the decoder client before the draw) and draws its barcode. |
| T-LEG-31 | component | W, L, M | gen | Steps +1, −1, +10, −10 across key frames and at both ends. | Each step lands on the exact frame on each tile; steps clamp to 0 and K − 1. |
| T-LEG-32 | component | W, L, M | gen | Play 20 s at speed 1, locked, 6 tiles; a test hook notes the frame number of each tile at each refresh, and the hash of each 30th frame. | 0 refreshes with different frame numbers; each hashed frame is exact. The share behind the clock is recorded. |
| T-LEG-33 | component | W, L, M | gen | Cameras with 120, 118 and 120 frames: play to the end, seek to K − 1. | Play stops at frame 117; no frame 118 or 119 is drawn; the warning shows. |
| T-LEG-34 | component | W, L, M | gen | Labels with and with no time files; time format seconds and timecode. | Labels as 6.4; `~` only with no usable time file; the canvas title as 6a 8.4. |
| T-LEG-35 | component | W, L, M | gen | A test hook ends the worker of tile 2 during play, then 3 times in 60 s. | Tile 2 shows frame k* again within 1 s after the first end; "decoder failed" after the third; the other tiles play with 0 different frame numbers among them. |
| T-LEG-36 | component | W, L, M | gen | A camera file cut before its `moov`; a camera file whose last 10 frames lie past the cut. | The first gets the refusal of 8.1 and the others play; the second plays with K from its frame count. |
| T-LEG-37 | component | W, L, M | gen | 16 tiles of 640x480 `mp4v`: play 30 s, 200 seeks, close. | Open `VideoFrame`s ≤ 10 for each tile at each time; each worker heap ≤ 512 MiB; 0 workers and 0 open frames after `close()`. |
| T-LEG-38 | component | W, L, M | gen | A page from a second origin plays a generated v1 recording through `http-take-files.ts` from the Python server on the local machine. | It plays and seeks as T-LEG-30; each response is `application/octet-stream` with a byte range of an original file; the bytes on the link are at most the sum of the file sizes plus the repeated block reads. |
| T-LEG-39 | component | W, L, M | gen | Open, play to the end, seek 50 times, close. | Each file of the folder has the same bytes and modification time as before; the folder has no new file (no conversion, no copy) [O]. |
| T-LEG-40 | component | W, L, M | gen | The host route: a v1 folder, a new take, a v2 alpha folder, an unknown folder. | The first two open in the canvas player; the others show their text of 2.2; with [P 5] yes, no `<video>` element is made. |
| T-LEG-41 | component | W, L, M | gen | Generated files with `tkhd` rotations 90 and 270 (with [P 1] yes, H.264). | The barcode quadrants are upright. |
| T-LEG-42 | component | W, L, M | gen | Open a 6-camera recording and count the requests for the WASM file. | One network fetch of the WASM file for the page [NV until 7.2 is checked]. |
| T-LEG-50 | benchmark | W (test machine) | gen and real | 200 seeks, 48 steps and 60 s of play at 1, 3 and 6 tiles of 720x1280 `mp4v`; and the treadmill session. | The targets of 12.2; p50, p95 and maximum recorded. |
| T-LEG-51 | benchmark | W (test machine) | gen | 16 tiles of 640x480 `mp4v`, 60 s of play; CPU and working set. | The target of 12.2; results recorded. |
| T-LEG-52 | benchmark | W (test machine) | gen and real | T-LEG-50 through the HTTP route with the link limited to 100 Mbit/s. | Results recorded for the owner. |
| T-LEG-60 | tool | W, L, M | none | A test of `tools/tests/` reads `.github/dependabot.yml`. | The three entries of 10.2 exist with their directories; each directory holds the manifest that its ecosystem reads; the `Dockerfile` has one `FROM` and no `ARG` before it. |
| T-LEG-61 | tool | W, L, M | none | A test of `tools/tests/` reads the workflows. | `player.yml` and the decoder jobs start on `skellycam-ui/decoder/**`; each test job needs `decoder-build`; each action is pinned to a full SHA with a same-line version comment; no job of the bump path uses a secret. |
| T-LEG-62 | tool | W, L, M | none | The parser of `decoder-upstream.yml` on stored text samples (a tag list, a part of the security page) and a fake issue API. | It finds the newer release and the CVE; it opens one issue, and on a second run it updates the same issue. |
| T-LEG-63 | rehearsal (once) | CI | none | A PR that changes only the libav.js pin (a real bump or a rehearsal on a branch). It needs the approval of the owner, because a PR is visible outside the machine. | Each job of 10.4 runs; the PR is mergeable with no other commit. |

Counts: 17 unit, 14 component, 2 server, 4 build, 3 tool, 3 benchmark, 1 rehearsal: 44 tests.

### 13.4 Rules to tests

| Rule | Tests |
|---|---|
| [O] reliable first | T-LEG-11, T-LEG-12, T-LEG-24, T-LEG-27, T-LEG-30 to T-LEG-37 |
| [O] short seek | T-LEG-10, T-LEG-50 |
| [O] no conversion, no copy | T-LEG-39 |
| [O] only compressed bytes on the link; no server decode | T-LEG-16, T-LEG-38 |
| [O] only v1 | T-LEG-01, T-LEG-40 |
| [O] custom libav.js, Dependabot | T-LEG-20 to T-LEG-23, T-LEG-60 to T-LEG-63 |
| [O] exact pins | T-LEG-22, T-LEG-61 |
| 2.2, 2.3, 2.4 | T-LEG-01 to T-LEG-05 |
| 3 | T-LEG-07, T-LEG-13, T-LEG-41 |
| 4 | T-LEG-14 to T-LEG-16, T-LEG-38 |
| 6 | T-LEG-03 to T-LEG-06, T-LEG-08 to T-LEG-10, T-LEG-26, T-LEG-30 to T-LEG-34 |
| 7, 8 | T-LEG-11, T-LEG-12, T-LEG-35 to T-LEG-37, T-LEG-42 |
| 9, 10 | T-LEG-20 to T-LEG-26, T-LEG-60 to T-LEG-63 |

### 13.5 Measurements owed

| ID | Measurement | Test |
|---|---|---|
| M-LEG-1 | The targets of 12.2 on the reduced build of 9.2 | T-LEG-50, T-LEG-51 |
| M-LEG-2 | The real v1 files through the HTTP route | T-LEG-52 |
| M-LEG-3 | The decoder on Linux and macOS (timing) | not in CI; a benchmark run on those systems is owed [NV] |
| M-LEG-4 | Reproducibility of the emscripten build | T-LEG-21 |

## 14. Differences from `player.md` and accepted text

1. **E2** (6a 18.5): "Old recordings keep a `<video>` path." Section 5 proposes one player. A "yes" to
   [P 5] changes it.
2. **L5** (6a 18.3): "No restructuring of today's player." Section 5.2 removes the player of today.
   A "yes" to [P 5] changes it.
3. **Y1 and L1** (6a 18.1, 18.3): step 6c is "the switch between the new player and the old
   video-element path, and old takes". This spec is the old-takes part, for v1 only [O]. With [P 5]
   yes, the switch is a removal.
4. **6a 7.3, frame choice by time.** For v1, the frame index chooses the frame (6.4). The rule of 6a
   7.3 stays for the new format.
5. **6a 8.1, `ImageDecoder` on the main thread.** For v1, the decoder runs in a worker for each tile
   (7.1). The tile still draws on the main thread.
6. **6a 8.3**, the `jpeg` sentence (11.3).
7. **6a 5.4, the snapshot folders.** For v1 the snapshot also lists `synchronized_videos/timestamps/`
   (4.2).
8. **The study advice for H.264** (WebCodecs first, the decoder as the fallback) [S 12.5]. Section 3.2
   proposes the decoder only [P 1].

## 15. Choices of the agent

Each item fills a gap that the rules of the owner and the evidence do not fix. The body marks each
one [agent n].

1. No annotated videos in this step (1.3).
2. The time file `.npy` is the one time source; the CSV copy is not read (2.1).
3. The recognition order of 2.2, the v2 alpha refusal, no refusal of v0.1.0.
4. The NPY rules, "usable" by length, NaN as no time, rounding to integer nanoseconds (2.3).
5. `~` for a time from the header rate (2.4).
6. The decoder for H.264 too; no WebCodecs route in this step (3.2).
7. The pixel formats and the colour default (3.3).
8. The `tkhd` rotation (3.3).
9. The edit list limit (3.3).
10. The server route, the roots, the token life of 30 minutes, no log line per range (4.2).
11. Keep the take-scheme and the HTTP path for now (4.3).
12. The removal list (5.2).
13. The TypeScript MP4 reader, the frame table, the frame count from the index, the cross-check with
    FFmpeg's demuxer (6.1).
14. Exact time stamps, continue only up to the next key frame (6.2).
15. K is the smallest frame count (6.3).
16. The time map, the base B, the mean over cameras, the median header rate, "Rec: fps" (6.4).
17. The locked rule (6.5).
18. The WASM load and the module hand-over (7.2).
19. The queue and memory limits, the heap maximum of 512 MiB (7.3).
20. No camera limit; tests to 16; a warning above 16 (7.4).
21. The fault table, 3 restarts in 60 s, the answer limit of 10 s (8.2).
22. The folder `skellycam-ui/decoder/` and its files (9.1).
23. The part list for v1 (9.2).
24. The CI build steps, the reproducible build check, the size limit of 4 MiB, the cache key (9.3).
25. Option A: build in CI, do not commit; the decoder outside the `asar` (9.4).
26. The LGPL duties, the source tarball on the release, a warning (not a refusal) for an unknown
    decoder file (9.5).
27. The watch table (10.1).
28. The `dependabot.yml` entries (10.2).
29. The weekly upstream workflow and its limits (10.3).
30. The bump pipeline and the required checks (10.4).
31. The module layout (11.1).
32. The interface names (11.2).
33. The text change of 6a 8.3 (11.3).
34. The host route (11.4).
35. The targets (12.2).
36. The test media plan, the hash rule, the real-file sources, the test list and its pass criteria
    (13).

## 16. Open questions for the owner

Each question is worded so that "yes" accepts the recommendation. The numbers Q685, Q688 and Q694 are
the numbers of the owner's question list. The other questions have no number yet.

1. **(Q694) Route by codec.** Route each camera file by its sample entry: `mp4v` and H.264 to the WASM
   decoder, with no WebCodecs route in this step; refuse each other codec with a readable reason.
   Yes? (The other choice: WebCodecs first for H.264, the decoder as the fallback, as the study
   advises. It seeks 2.6 to 3 times faster on the GPU, with a second code path and OS-dependent
   decoders.)
2. **HEVC.** Leave the HEVC decoder out of the build until a real HEVC import is available as a test
   file; an HEVC file gets the refusal. Yes?
3. **(Q688) Data path.** The server lists the recordings and serves the original bytes by range under
   a token; the page decodes; keep the Electron take-scheme for the local app until the option B
   review shows the HTTP route on par, then decide its removal. Yes?
4. **Allowed roots.** The new route opens only folders below the skellycam recordings folder,
   `<home>/freemocap_data`, and the folders of a list that only the server settings change; no
   request parameter adds a folder. Yes?
5. **(Q685) One player.** v1 recordings play in the canvas player; remove the `<video>` player and
   the items of 5.2 in a separate PR after the legacy player lands; this changes E2 and L5. Yes?
6. **Frame count.** K is the smallest frame count; the frames after it are not shown; the take gets a
   warning. Yes?
7. **Time map.** The times of 6.4: the mean of the time files over the cameras from the base B, made
   non-decreasing; the median header rate with `~` when no time file is usable. Yes?
8. **Built files.** Build the decoder in CI and do not commit its outputs; the installer workflow
   builds it; a developer builds it with Docker or downloads the CI artefact. Yes?
9. **Upstream gap.** A weekly workflow opens or updates one issue for a newer FFmpeg point release, a
   newer libav.js release or a listed CVE; it does not fix anything by itself. Yes?
10. **FFmpeg source override.** Do not add a way to build with an FFmpeg tarball other than the one in
    libav.js now; add it only when the weekly workflow finds a security fix that no libav.js release
    holds after 30 days. Yes?
11. **Synthetic test media.** Make the test media at test time with `tools/make_legacy_media.py` and
    PyAV `av==19.0.2`, in a temporary folder; commit no media; use the GPL encoder `libx264` only to
    make test media in CI. Yes?
12. **Sample data in CI.** CI downloads the official FreeMoCap sample data, checks its SHA-256, and
    keeps it only in a temporary folder and the CI cache, for T-LEG-27. Yes?
13. **The treadmill session.** Tests read it only on the owner's machine, from the folder in
    `SKELLYCAM_LEGACY_V1_DIR`; the tests skip it elsewhere. Yes?
14. **Dependabot repair.** Change the present `npm` entry of `dependabot.yml` from `/` (no manifest
    there) to `/skellycam-ui` and add `/skellycam-docs`, in the CI PR of this work. Yes?
15. **Patents.** Accept that the build holds the MPEG-4 Part 2 decoder (and the H.264 decoder with
    question 1 yes), and that their patent position is a decision of the owner outside this spec; the
    technical work does not wait for it. Yes? (The libav.js README warns that builds with
    MPEG-controlled codecs are not made by default.)
16. **Annotated videos.** Do not show `annotated_videos/` in this step. Yes?
17. **Other eras.** Refuse a v2 alpha folder with the text of 2.2; do not refuse a v0.1.0 folder, but
    give it no test and no support. Yes?
18. **Camera count.** No upper limit; tests and benchmarks to 16 cameras; a warning above 16. Yes?
19. **Spec place.** Keep this spec as a new file `specs/player-legacy.md`, linked from 6a 1.3, as the
    v1 part of step 6c. Yes?
20. **Demuxer.** Use FFmpeg's own demuxer in the worker, as measured, and the TypeScript MP4 reader for
    the frame table and the route, with a cross-check at open; feed exact packets without FFmpeg's
    demuxer only after a measurement. Yes?
21. **Tile text.** After acceptance, add to 6a 8.3 the sentence of 11.3 and the field `timeEstimated`
    of 11.2. Yes?

## 17. Not verified

- No real sample of a v1 import, of v1.0.26 to v1.0.30, or of an HEVC file [S 12.6].
- The reduced part list of 9.2 was not built. The study built the larger list [S 12.2].
- A byte-identical rebuild of the decoder (T-LEG-21).
- The decoder on Linux and macOS, and on a weak CPU; hours-long files; many plays in a row [S 12.6].
- 16 tiles of playback.
- The colours that Chromium draws for a `VideoFrame` with no colour values (3.3).
- That libav.js 6.10.9 accepts a compiled `WebAssembly.Module`; the CSP of the app (7.2).
- That Dependabot keeps an exact npm pin exact, and updates a `FROM` digest (10.2).
- That no npm advisory names an FFmpeg CVE; which FFmpeg point release `ffmpeg-9.0.tar.xz` holds;
  that the libav.js build takes another FFmpeg tarball (10.3).
- That the present `npm` entry of `dependabot.yml` finds no manifest (10.5).
- The network bind and the login of the server for a UI on another machine (4.2).
- The licence name of the libav.js wrapper (ISC or 0-clause BSD) (9.5).
- That the PyAV 19.0.2 wheels for Linux and macOS have the `mpeg4`, `libx264` and `libx265` encoders
  (13.1).

## 18. The rules of the owner (2026-11-24)

These are the words of the owner, as relayed by the coordinator
([ADR-X5MZ](../decisions/entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)):

- "Reliable playback is the #1 goal, minimising seek time is #2 goal."
- "old recordings must not be converted - you gotta play them as-is."
- "I'd like to maintain the ability for the UI to run on a separte machine to the server, so avoiding
  uncompressed frames on the http link is probably necessary."
- "I do not want to do server-side decode." (No fallback to it.)
- "we do not need to maintain compatibility with any v2 builds - only v1." (This replaces his earlier
  words "The goal is to support all v1 onwards versions".)
- Q693: "yes, lets go with custom libav.js. This work must also include suitable dependabot scripts to
  monitor upstream repos and trigger build and pr tests so it is minimal work to keep our custom build
  up to date."

The standing rules of the owner, as the coordinator listed them (not his exact words): exact version
pins everywhere (`==` for Python, exact npm versions, CI actions by full SHA, toolchain images by an
exact tag or digest); spec and tests before code; LF line endings; no camera recordings or frames
committed (a test media file needs a decision); other systems are tested only through the certify
process or CI.
