# Phase 6 player specification: step 6c, part 1, playback of FreeMoCap v1 recordings (draft)

Status: **draft for the review of the owner, revision 3, 2026-11-24. Not accepted.** No test and no
code comes before the owner accepts this spec. The rules of the owner are in
[ADR-X5MZ](../decisions/entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)
(accepted). His answers Q685, Q688, Q697, Q698 and Q700 are in
[ADR-8EBK](../decisions/entries/8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md) (accepted), and
his answers Q701 to Q706 are in [ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md)
(accepted).
Each choice of the agent is in [ADR-A56K](../decisions/entries/A56K-choices-of-the-v1-playback-spec.md)
(proposed). Section 16 gives the open questions. A "yes" to a question accepts its recommendation.

Revision 2 applied an independent review of revision 1 (39 findings) and the answers of 8EBK.
Revision 3 applies the answers of 0C4Y.

This spec extends [`player.md`](player.md) (step 6a, accepted). The rules of `player.md` apply to a v1
recording, unless this spec gives a different rule. Section 14 lists each difference.

## 0. How to read this spec

Marks:

- **[O]**: the words of the owner, 2026-11-24 (section 18,
  [ADR-X5MZ](../decisions/entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)).
  Only his own words have this mark.
- **[X5MZ item 7]**: a standing rule of the owner, as the coordinator listed it (not his exact words).
- **[Qnnn yes]**: a question that the owner answered "yes" on 2026-11-24
  ([ADR-8EBK](../decisions/entries/8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md),
  [ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md)). The text under the
  mark applies that answer.
- **[S n]**: the H.264 study, part A, `research/h264_study/part_a/NOTES.md`, section n, on branch
  `dom/h264-scrub-study` at commit 71caa2d0b. `[S RT]` is its `RESULTS_TABLE.md`. The study files
  `wasm_build.sh`, `app/mp4.mjs`, `app/wasm.mjs` and `app/wasm_worker.mjs` are in the same folder.
  The study ran on one Windows 11 machine (RTX 3070, Electron 45.3.4), on a shared machine. Each time
  is rough.
- **[INV]**: `research/skellycam_recording/docs/legacy_release_inventory_20261115.md` on branch
  `dom/research` at commit 7d8f8911b (a code reading of 87 freemocap release tags; nothing was run).
- **[FF file]**: the FFmpeg 9.0 source inside the libav.js 6.10.9 npm tarball
  (`sources/ffmpeg-9.0.tar.xz`), read on 2026-11-24 (nothing was built or run).
- **[LJ]**: the `README.md` inside the libav.js 6.10.9 npm tarball, read on 2026-11-24.
- **[C file]**: a code fact of this branch, read on 2026-11-24.
- **[D page]**: a page of the GitHub documentation, read on 2026-11-24 (section 10.7 lists the pages).
- **[the review]**: a fact that the independent review of revision 1 found and the agent did not
  check again.
- **[NV]**: not verified. No evidence proves it.
- **[agent n]**: an agent filled a gap. Section 15, item n, lists each one.
- **[Qnnn]** with no "yes": an open question of section 16.
- **6a n.m**: section n.m of [`player.md`](player.md).

This spec uses British spelling.

## 1. Purpose, scope, terms

### 1.1 Purpose

The canvas player of step 6a plays the takes of the new format (camera JPEGs in MKV). This spec adds
the playback of FreeMoCap v1 recordings to the same player. The owner: "Reliable playback is the #1
goal, minimising seek time is #2 goal." [O]. He also said: "old recordings must not be converted -
you gotta play them as-is." [O], "I do not want to do server-side decode." [O], and "I'd like to
maintain the ability for the UI to run on a separte machine to the server, so avoiding uncompressed
frames on the http link is probably necessary." [O]. This spec therefore sends only the original
compressed bytes on the HTTP link, and the page decodes them [agent 10] [Q688 yes].

### 1.2 In scope

| Item | Rule |
|---|---|
| FreeMoCap v1.0.25 and v1.0.31 to v1.8.2, with skellycam 2023.9.1086 to 2025.9.1097 (the writer is byte-identical across these pins) | supported [S 12.1 row 1] [INV] |
| FreeMoCap v1.0.26 to v1.0.30 (skellycam unpinned, or a branch zip that is not available) | the same rules apply; no sample, no code read [S 12.1 row 5] [NV] |
| The official FreeMoCap sample data (a 2022 recording in a v1 folder, with the old names `sesh_..._synced_CamN.mp4`) | supported [S 12.1 row 3] |
| A folder of the v1 "import videos" wizard (`recording_sessions/import_<name>/`, any `.mp4` that the user picked) | supported for the codecs of section 3 [S 12.1 row 4] [INV]; no sample [NV] |
| The take folders of the new format | unchanged: 6a plays them |

### 1.3 Out of scope

- **FreeMoCap v2 builds and skellycam v2 alpha formats.** The owner: "we do not need to maintain
  compatibility with any v2 builds - only v1." [O]. This removes rows 6 to 11 of [S 12.1]: the
  Windows Media Foundation H.264 writer, the Linux PyAV x264 writer, the macOS `avc1` writer, the
  `mp4v`, XVID and MJPG fallbacks in MP4 and AVI, the `.web.mp4` sidecars, and the Rust backend of
  `upstream/sfn26`. These words replace his earlier words "The goal is to support all v1 onwards
  versions" [O]. Section 2.2 tells how the player refuses a v2 alpha folder [agent 3].
- **FreeMoCap v0.0.x and v0.1.0.** They are older than v1. The player does not refuse a v0.1.0
  folder, because it has the v1 form (section 2.2). No test covers it [agent 3] [Q713].
- **The release candidates v1.0.0-rc to v1.0.23-rc.** Out of scope [Q706 yes]. The inventory also
  leaves them out [INV].
- **The annotated videos** (`annotated_videos/*.mp4`). They are a result of the processing, not a
  camera file. The player does not show them in this step [Q700 yes].
- **A conversion** [O "must not be converted"], **a server decode** [O], **a repair** (6a Y5: the
  player offers no repair), **a copy of a file next to the recording** [agent 10]. The "upgrade
  recording" converter, step 6d of 6a 1.3, is cancelled [Q705 yes].
- **A UI page that the server hands to a browser.** The remote UI is the installed Electron app
  [Q701 yes].
- **Audio.** A v1 recording has no audio file of the cameras.

### 1.4 Terms

| Term | Meaning |
|---|---|
| v1 recording | A folder of section 2.2, rule 3. |
| camera file | One `.mp4` file in `synchronized_videos/` of a v1 recording. |
| time file | `synchronized_videos/timestamps/<stem>_binary.npy` of a camera file with the stem `<stem>` (section 2.3). |
| frame table | The list of the frames of one camera file, in presentation order, from its MP4 index (section 6.1). |
| frame k | Entry k of the frame table, from 0. The frame index is the truth (section 6). |
| frame time stamp | The presentation time of a frame in track units, after the edit list (6.1). |
| K | The number of multi-camera frames: the smallest frame count of the cameras that play (section 6.3). |
| k* | The frame number that the controls show (as 6a 7.2). |
| T_k | The take time of multi-camera frame k (section 6.4). |
| the decoder | The custom libav.js variant of section 9: FFmpeg's demuxer and decoders, compiled to WebAssembly (WASM). |
| tile worker | One module worker for one tile, which runs the decoder (section 7). |
| live tile | A tile that takes part in the locked rule of 6.5. |
| the recipe | The build files of the decoder (section 9.1). |

## 2. The v1 recording

### 2.1 Folder and files

A v1 recording is a folder with these items [INV] [S 12.1]:

| Path | Role | Read by the player |
|---|---|---|
| `synchronized_videos/*.mp4` (also `*.MP4`) | the camera files | yes |
| `synchronized_videos/timestamps/<stem>_binary.npy` | the time file of the camera file `<stem>.mp4`: 1-D float64, one value per written frame, `time.perf_counter_ns()` of the capture | yes, when present |
| `synchronized_videos/timestamps/<stem>_timestamps_human_readable.csv` | the same times as text | no [agent 2] |
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
   alpha recordings are not supported".
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
- The values are nanoseconds of `perf_counter_ns`, a monotonic clock of the recording machine, not
  Unix time; they are not comparable across machines or reboots [INV quirks, timestamps]. All
  cameras of one v1 recording are captured on one machine. The agent assumes that the values of the
  cameras are on one clock [NV: the skellycam v1 code was not read for this point]. A float64 holds
  each integer nanosecond up to 2^53 ns (about 104 days of clock time) with no loss. The player rounds
  each value to an integer nanosecond.
- A repeated value means a duplicate frame: the v1 synchronizer writes a copy of a frame for a
  dropped frame [INV quirks, dropped frames]. The player shows it as a frame (section 6.4).

### 2.4 No time file

The official sample data has no time file [S 12.1 row 3]. An import folder has none [S 12.1 row 4].
Then the player uses the header rate (section 6.4). The tiles show the time with a `~` in front, as
the player of today does (feature F6, 6a 3.1) [agent 5].

## 3. Route by codec, not by file extension

### 3.1 The rule (proposed; Q694 open)

The player reads the sample entry of the video track of each camera file from the MP4 index
(section 6.1). It does not use the file extension [S 12.5]. The `mp4v` and `avc1` codecs share the
extension `.mp4` [S 12.5].

| Sample entry | Codec | Route |
|---|---|---|
| `mp4v` with an `esds` object type 0x20 (MPEG-4 Visual) | MPEG-4 Part 2 | the decoder (WASM `mpeg4`) |
| `avc1`, `avc3` | H.264 | the decoder (WASM `h264`) in phase 1 [Q694] |
| `hvc1`, `hev1` | HEVC | refused until a real sample exists [Q700 yes] |
| each other entry (for example `av01`, `vp09`, `mp4v` with another object type, `jpeg`, `mjpa`) | | refused |

The refusal text is "camera file not playable: codec <name> is not supported", with `<name>` the
four characters of the sample entry and the object type, if any. The tile shows it as the mark
`not_readable` of 6a 8.3. The other cameras play.

### 3.2 H.264: the decoder in phase 1, a GPU route decided in phase 2 [agent 6] [Q694]

The agent proposes the decoder only for H.264 in phase 1. A WebCodecs route (GPU) is a phase 2
decision, after a real import sample exists.

For WASM only:

- One decoder for each v1 file gives one code path, one test set and the same pixels on each system.
  The decoder gave the pixels of x86-64 FFmpeg on 73,819 of 73,819 frames in 30 files, H.264 included
  [S 12.4].
- WebCodecs decoders depend on the OS and the GPU. The study measured WebCodecs on one Windows
  machine only [S 12.6].
- Imports have no sample [S 12.1 row 4].
- On short-GOP H.264 at 720p, WASM seeks as fast as the GPU route (65 to 101 ms) [S 13.2].
- At 1080p CRF 18, WebCodecs on the CPU fell behind the clock on 99 to 100 % of refreshes; WASM, one
  worker per tile, kept up (2.1 to 2.3 cores for 6 tiles) [S 13.2].

Against WASM only, the measured cost on long-GOP H.264 (shared machine, ms) [S 12.4] [S RT rows 91,
94]:

| Material | Route | Seek p50 / p95 | Backward step p50 | Start of play |
|---|---|---|---|---|
| H.264 Baseline, GOP 32, 4 tiles (v2 alpha writer) | WASM | 194 to 197 / 341 to 345 | 287 to 291 | |
| same | WebCodecs GPU | 74 | 115 | |
| same | WebCodecs CPU | 173 | 303 | |
| x264 High, B-frames, GOP 250, 3 tiles (stand-in) | WASM | 654 to 660 / 1482 to 1483 | 1531 to 1535 | 1.3 to 1.4 s |
| same | WebCodecs GPU | 221 | 493 | |
| same | WebCodecs CPU | 686 | 1571 | |

- WASM H.264 in play costs about one CPU core for each 1 to 2 tiles [S 12.5].
- An import that the v1 wizard "synchronised" can be an FFmpeg re-encode with the x264 defaults
  (GOP 250 with B-frames). The output of skelly_synchronize is not verified [INV section 5]. Then the
  slow row above can be the common case for imports [NV].
- For `mp4v`, WASM is the only route in Chromium [S 11.2, S 12.5].

### 3.3 Other properties of a camera file

| Property | Rule |
|---|---|
| Pixel format | 8-bit `yuv420p`, `yuv422p`, `yuv444p`, and the `yuvj` forms. Each other format (for example a 10-bit format): refused, "pixel format <name> is not supported" [agent 7]. |
| Colour | The tile uses the colour values of the stream when the stream sets them. For a `yuvj` format, the `VideoFrame` gets full range. Else BT.601 with limited range, the default of FFmpeg for MPEG-4 Part 2 [agent 7] [NV: the colours that Chromium draws]. The identity checks of section 13 are on the decoded planes, not on the drawn colours. |
| Rotation | v1 writes the rotation into the pixels [S 11.1 row 3]. The player applies a `tkhd` matrix of 0, 90, 180 or 270 degrees as `rotationCwDeg`, for each codec. It ignores each other matrix, with the warning `matrix_ignored` [agent 8]. |
| Edit list | Accepted: no `elst`; or zero or more empty edits (media time −1) followed by one edit with media rate 1 and a media time at or above 0. Each other edit list is refused: "edit list not supported" [agent 9]. Section 6.1 gives the frames that an edit keeps. The v1 files have media time 0 [S 11.1]. |
| More than one video track | The first video track plays. Warning `extra_tracks`. |

## 4. Data path [Q688 yes]

### 4.1 The rule

- The owner accepted: "Add the server route (token, allowed folders only, no folder from a request),
  and keep the Electron direct path for now" [Q688 yes].
- The server lists the recordings. It serves the original bytes of the files by HTTP range. The page
  decodes. No decoded or converted video goes on the link. No copy is written next to the recording
  [agent 10].
- The page reads each byte through the `TakeFiles` interface of 6a 5.1. The new implementation is
  `files/http-take-files.ts`, the place that 6a 5.9 keeps for it. It uses the acceptance rule of 6a
  5.6 (a 206 with the asked start, or a 200 with the exact length) and passes the shared check suite
  of 6a 5.1 (T-PLAY-39, T-PLAY-64, and T-LEG-14 here).

### 4.2 The server route [Q688 yes] [agent 10]

| Request | Result |
|---|---|
| `POST /skellycam/playback/open` with `{ "path": <folder> }` | The server takes the real path (`resolve()`). It refuses a folder outside the allowed roots with 403 and "folder not allowed". It makes the snapshot of 6a 5.4: the regular files of the root, of `synchronized_videos/` and of `synchronized_videos/timestamps/`, with their size and file ID; no links, no junctions, no file with more than one hard link. It answers `{ token, folderName, entries }`, with relative paths and sizes only. |
| `GET /skellycam/playback/files/<token>/<path>` | The bytes of 6a 5.6: no `Range` gives 200; `bytes=a-b` gives 206; each other form gives 416; only bytes below the snapshot size. Before each read, the identity check of 6a 5.5 (device and file ID equal to the snapshot; one hard link). Each response has `Content-Type: application/octet-stream`, `Cache-Control: no-store`, `Accept-Ranges: bytes` and `Access-Control-Expose-Headers: Content-Range, Content-Length, Accept-Ranges`. |
| `DELETE /skellycam/playback/open/<token>` | Closes the token. A later request with it gets 404. |
| `OPTIONS` on each route | The CORS preflight answer for the JSON `POST` and for the `Range` header. |

- **Allowed roots** [Q688 yes: "allowed folders only, no folder from a request"]: the skellycam
  recordings folder (6a 5.3), the FreeMoCap v1 data folder `<home>/freemocap_data` (the v1 default
  [INV]), and the folders of a list that only the settings of the server change [agent 10].
- **The root check** compares path components after `resolve()`, not a string prefix. It ignores case
  on Windows and macOS [agent 10].
- **Token.** 128 random bits, 32 lower-case hexadecimal characters (as 6a 5.2). A token ends at
  `DELETE`, at a stop of the server, and after 30 minutes with no request [agent 10]. The token
  scopes one folder. It is not access control (4.4).
- **Expiry in the client** [agent 11]. When a read gets 404 for its token (an expiry or a restart of
  the server), `http-take-files.ts` opens the folder again once and repeats the read. When the new
  snapshot differs from the old one (a size or a file ID), the take ends with the `error` event
  "recording changed on disk". A second 404 is a read error (6a 5.7).
- **No log line for each range request.** Logging made the FastAPI route 25 % short in the transport
  test of 6a 11.2 [6a 14.4].

### 4.3 The Electron `take-scheme` path of 6a [Q688 yes]

- The take-scheme of 6a 5.2 stays for the local app for now [Q688 yes]. It is measured: 16 cameras ×
  60 fps × 150 kB with 0 dropped ticks [6a 11.2].
- The HTTP path of 4.2 serves a UI on another machine, and v1 recordings in both cases.
- Both are implementations of `TakeFiles` and pass one check suite [6a L8].
- The review of option B (open work of 6a 14.4) decides later if the take-scheme goes. A v1 load is
  small: six `mp4v` tiles used 79 Mbit/s of link in the study [S 12.4].

### 4.4 Network exposure [Q701 yes] [Q702 yes]

The remote UI is the installed Electron app on the other machine, not a page that the server hands
to a browser [Q701 yes]. The owner accepted: "Remove the 'any origin' rule for these routes, check
the Host header, and put login or pairing for a remote UI in the spec as a requirement before the
server listens beyond localhost" [Q702 yes].

Code facts of today:

- The server binds to `localhost` (`HOSTNAME = "localhost"` in `skellycam/api/server_constants.py`)
  [C]. A UI on another machine needs a bind to a network address. No such setting exists [C].
- `skellycam/api/middleware/cors.py` sets `allow_origins=["*"]` with `allow_credentials=True`,
  `allow_methods=["*"]` and `allow_headers=["*"]` for the whole app [C]. Thus each web page that the
  user opens in a browser on the server machine can call the server and read the answers, for
  example `list_recordings`. With the route of 4.2, such a page could also open a folder and read the
  camera files.
- A DNS rebinding attack gets around CORS [the review] [NV: not tested against this server].
- `list_recordings`, `list_videos` and `stream_video` of
  `skellycam/api/http/playback/playback_router.py` take a `recording_parent_directory` from the
  request and open each folder below it [C `_resolve_recording_path`]. Section 5 removes the last two
  [Q685 yes].

The token and the allowed roots of Q688 do not close this exposure. These requirements close it
[Q702 yes]. "These routes" are the routes of 4.2 and `list_recordings`.

1. **CORS for these routes.** The rule `allow_origins=["*"]` of `cors.py` does not apply to these
   routes. They answer with `Access-Control-Allow-Origin` only for an origin of the allow-list, and
   they never send `Access-Control-Allow-Credentials`. The allow-list of a packaged app holds only
   the origin of its page. The app loads its page with `loadFile` [C
   `skellycam-ui/electron/main/services/window-manager.ts`], so that origin is the opaque origin
   `null`. A development build adds the origin of its Vite dev server. A request with another
   `Origin` gets 403 "origin not allowed" and no CORS header. A preflight (`OPTIONS`) from another
   origin gets 403 with no CORS header [agent 37].
2. **Host allow-list.** These routes accept a request only when its `Host` header is in the
   allow-list: `localhost`, `127.0.0.1` and `[::1]`, each with the port of the server, and, for a
   bind beyond `localhost`, the host names and addresses that the settings of the server name. Each
   other `Host` gets 403 "host not allowed". This stops a DNS rebinding page, because its requests
   carry the host name of the attacker [agent 37].
3. **Login or pairing before any bind beyond `localhost`.** The server must not listen on an address
   other than `localhost` (and the loopback addresses) until a login or a pairing protects these
   routes. With no such protection configured, the server refuses a bind setting beyond `localhost`
   at start, with the text "a remote UI needs login or pairing; the server listens on localhost
   only". **The design of the login or the pairing is owed** (a separate spec and decision). That
   design must also cover the origin `null`: each sandboxed page and each `file://` page sends
   `null`, so the origin check of item 1 cannot tell the app from such a page. On `localhost`, item 1
   then still lets a sandboxed page with the origin `null` read these routes [agent 37] [NV: not
   tested].

T-LEG-17 to T-LEG-19 test items 1 to 3.

## 5. One player [Q685 yes]

### 5.1 The rule

The owner accepted: "v1 plays in the canvas player, and a later PR removes the old `<video>` player
and the server transcode code" [Q685 yes]. The reasons from the evidence:

- Chromium has no decoder for MPEG-4 Part 2. The `<video>` element does not play a v1 camera file
  (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`) [S 11.2]. Thus the player of today plays no file that v1
  writes.
- The only files that `<video>` can play are H.264 files and, on some systems, HEVC files. H.264 and
  HEVC v2 alpha files are out of scope [O "only v1"]. Imported H.264 goes to the decoder (section 3).
  An HEVC import that `<video>` can play on some systems today gets the refusal of 3.1 [Q700 yes].

### 5.2 What the later PR removes [agent 12]

The list is a code reading of 2026-11-24 [C]. The removal is a separate "code" PR after the legacy
player lands. Each item needs a check at that time.

| Item | File |
|---|---|
| The `<video>` player | `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx` (the type `PlaybackSettings` moves to `PlaybackControls.tsx`) |
| The `video` result of the route | `skellycam-ui/src/components/playback/take-route.ts` (`routeTake`, `chooseTakePlayer`), and the `SyncedVideoPlayer` branch of `skellycam-ui/src/pages/PlaybackPage.tsx` |
| The video loading of the context | `LoadedVideo` and the timestamp fetch of `skellycam-ui/src/contexts/PlaybackContext.tsx`; the `stream_url` use in `RecordingBrowser.tsx` |
| The URLs of the old routes | `playbackVideos`, the stream URL and `playbackTimestamps` in `skellycam-ui/src/services/server/server-helpers/server-urls.ts` |
| The old server routes | `list_videos`, `stream_video`, `get_all_timestamps` of `skellycam/api/http/playback/playback_router.py` (`list_recordings` stays, changed to list v1 recordings and new takes from the allowed roots, with no folder from the request) |
| The server transcode | `skellycam/core/recorders/videos/browser_stream.py` (H.264 fragments from the server), with `skellycam/tests/test_browser_stream.py` and `skellycam/tests/browser_stream_server.py`; only tests use it [C] |
| The sync warning | F16 of `PlaybackControls.tsx` and its prop `hideSyncInfo` (6a 10, U3), because no player shows it |

`video_file_metadata.probe_video_files` and `recording_statistics` stay if another caller uses them
[NV].

The answer Q685 changes accepted text: E2 ("Old recordings keep a `<video>` path") and L5 ("No
restructuring of today's player") of 6a 18. Section 14 lists it.

## 6. Frame accuracy and sync

### 6.1 The frame table and the edit list [agent 13]

- The module reads the MP4 index itself, in TypeScript (`legacy/mp4.ts`): the top-level boxes by
  range reads, then `moov`. It reads `mvhd`, `tkhd`, `mdhd`, `hdlr`, `stsd` (with `esds`, `avcC`),
  `stts`, `ctts`, `stss`, `stsz`, `stsc`, `stco`, `co64` and `elst`, and 64-bit box sizes.
- For each sample, CTS = DTS (from `stts`) + the composition offset (from `ctts`, 0 when absent).
- **The edit list.** Let M be the media time of the one non-empty edit (in track units), D its
  segment duration converted from the movie time scale (`mvhd`) to track units, and E the sum of the
  leading empty edits in track units. With no `elst`, M = 0, E = 0 and the edit covers all samples.
  - The frame table holds each sample with M ≤ CTS < M + D, in the order of CTS (equal CTS: the
    decode order).
  - The frame time stamp of frame k is CTS − M + E.
  - FFmpeg's demuxer does the same [FF `libavformat/mov.c` `mov_fix_index`]: it keeps the key frame
    before the edit start and the frames up to the next key frame after the edit end in its index,
    and it marks each frame with a CTS outside [M, M + D) with `AV_PKT_FLAG_DISCARD`, so that it is
    dropped after decoding. It then offsets the time stamps so that the first kept frame of a video
    track has the time stamp 0, and it sets the start time to E. The study reader uses the same
    time shift: "cts - first edit media time + leading empty edits" [C study `app/mp4.mjs`
    `buildIndex`]. T-LEG-26 compares the two tables on each test file.
- For `mp4v` from v1 there are no B-frames, so the decode order is the presentation order, and
  M = 0 [S 11.1].
- For each frame the table holds: the frame time stamp, the decode position, the key flag (from
  `stss`; all frames are key frames when `stss` is absent), the byte offset and the size.
- The frame count of a camera is the number of frames of its table whose bytes lie inside the
  snapshot size of the file. It is not `duration × fps` (as 6a F21 did).
- The tile worker opens the same file with FFmpeg's own MP4 demuxer, as the study measured
  [S 12.3]. At open, the worker reports the frame count and the time stamps of the kept frames of the
  demuxer index. A difference from the table refuses the camera: "camera file index mismatch"
  [Q714].

### 6.2 Exact seek and step [agent 14]

The player asks the tile worker for frame k. The worker:

1. **Cache.** When frame k is in its kept frames (step 5), it gives it out at once.
2. **Continue.** When the last frame that it gave out is j < k and no key frame is in (j, k] (in
   presentation order), it continues the live decoder. The study continued up to 30 frames ahead; the
   rule here is stricter, as the study advises [S 12.4, S 12.5 product notes].
3. **Seek.** Else it takes from the frame table the key frame G: the last key frame at or before
   frame k in decode order. It seeks with `av_seek_frame` and `AVSEEK_FLAG_BACKWARD` on the frame
   time stamp of **G** (in the time base of the demuxer), not on the time stamp of frame k. Then it
   flushes the decoder. The first packet that the demuxer gives must have the byte offset of G. When
   it does not, the worker seeks again on the key frame before G, once; a second miss is the error of
   step 6.
   - The reason: FFmpeg's mov seek takes the time stamp as a presentation time, subtracts an offset
     (`min_corrected_pts` + `dts_shift`), and searches the index of decode time stamps
     [FF `libavformat/mov.c` `mov_seek_stream`]. With B-frames, a key frame can have a decode time at
     or before the presentation time of frame k and a presentation time after it. A seek on the time
     stamp of frame k could then land on a key frame after frame k. A seek on G itself avoids this.
     The study passed on three synthetic B-frame files only [S 12.4].
4. **Exact frame.** It gives out only the frame whose time stamp **equals** the frame time stamp of
   frame k. The study used a tolerance of 0.45 frame [C study `app/wasm.mjs`]; the rule here is exact.
5. **Keep.** It keeps the decoded frames after frame k for the next forward steps, at most the limit
   of 7.3.
6. **Error.** When the decoder gives out a later frame and no frame with the time stamp of frame k,
   the worker reports it (section 8.2).

- `step(+1)` uses rule 1 or 2 (one more frame). `step(-1)` seeks back and decodes from the key frame:
  at most 11 frames for the GOP of 12 of v1 [S 12.4].
- `seekFrame(k)` and `step(n)` set k* and t as 6a 7.2. The newest request wins (6a 7.5): each tile
  has at most one request in its worker and one pending target.

### 6.3 Cameras with different frame counts [Q700 yes]

- K is the smallest frame count of the cameras that play, as the player of today (F21) and 6a K
  [Q700 yes: "playback length is the smallest frame count of the cameras, with a warning"]. The
  frames from K on are not shown.
- When the counts differ, the take gets the warning `frame_count_differs` with each count. The host
  shows it.
- All v1 samples of one session have equal frame counts [S 11.1]. The v1 synchronizer clips the
  cameras to their overlap [INV quirks]. A difference can come from an import or from a damaged file.
- A refused camera does not count for K (as 6a T-PLAY-05).

### 6.4 The frame-to-time map [agent 16] [Q711]

The frame index is the truth. Tile c shows frame k* of camera c. It never chooses a frame by time.
This differs from 6a 7.3, which chooses by time for the new format. The reason: the v1 synchronizer
already matched the frames of the cameras; frame k of each camera is one moment, and the FreeMoCap
processing uses the frames by index [INV quirks, dropped frames].

The times serve the clock, the labels and the pace only:

- **With one or more usable time files:** v_c(k) is the value of camera c at frame k, in integer
  nanoseconds. The base B is the smallest finite v_c(0) of the cameras. U_k is the mean of the finite
  v_c(k) over the cameras with a usable time file (FreeMoCap v1 takes the mean over the cameras
  [INV `data_loader.py`]). T_k = max(T_(k-1), U_k − B). When no camera has a finite value at row k,
  T_k = T_(k-1). T_0 = U_0 − B, or 0 when U_0 has no value.
- **With no usable time file:** the header rate r_c of camera c is (n_c − 1) × the `mdhd` time scale
  / (the frame time stamp of the last frame − that of the first frame), with n_c its frame count, as
  a rational number. This holds also when `stts` has more than one entry. r is the median of the r_c
  of the cameras; for an even count, the mean of the two middle values. T_k = round(k × 10^9 / r). The
  v1 header rate is a per-camera median of the capture rate, so the cameras can differ [S 12.1
  row 1].
- **Tile label.** A camera with a usable time file shows v_c(k*) − B, or no time part for a frame with
  no time. A camera with no usable time file shows T_k* with a `~` in front.
- **"Rec: fps"** (F15) shows r, rounded to 3 decimals. With time files, r comes from the header
  rates too.
- **Play.** At open, k* = 0 (or the `initialFrame` of the host, F19) and t = T_k*. Play starts at t
  and advances t by the speed × the elapsed time, as 6a 7.4. During play, k* is the frame of 6.5.
  Pause sets t = T_k*. The end and the loop follow 6a 7.4.
- **A gap in the time file** (a stalled capture) plays as a gap of the same length in real time: the
  tiles hold their frame until t reaches the next T_k. This is the recorded time [agent 16].

### 6.5 Synchronised play: the locked rule [agent 17]

- Each tile worker streams decoded frames ahead of the clock, with one credit for each frame, at most
  8 frames ahead [S 12.3].
- At each display refresh, t advances (6.4) and gives the target k_t: the largest k with T_k ≤ t.
- A **live tile** is a tile that has no mark `not_readable`, `read_error` or "decoder failed", and
  that is not in a restart (8.2). A frame that the decoder reported as damaged counts as ready: the
  tile shows its last image with the mark "damaged at frame k".
- The frame that each tile shows is k* = min(k_t, the newest frame that each live tile has ready).
  Thus all live tiles show the same frame number on each refresh. A tile that is not live keeps its
  last image and its mark. It does not hold the others.
- t does not stop for a late tile. When a tile is late, k* stays below k_t. That refresh is "behind
  the clock". The late tile drops each queued frame below k_t, so that it catches up. This is the
  `locked` mode of the study. The study advises it: in the `free` mode at 100 Mbit/s, tiles were one
  frame apart on 1 to 2 refreshes of about 750 [S 12.4].
- At a speed above 1, the decoder still decodes each frame, because the later frames depend on the
  earlier frames. The tiles show a part of the frames. The locked rule then shows the frames that the
  live tiles have ready [NV: the rate at speed 8].

## 7. The decoder in the page

### 7.1 One worker for each tile [S 12.3]

- Each tile has one module worker. The worker loads the decoder, opens the original file with
  FFmpeg's demuxer through a libav.js block reader device, and decodes with FFmpeg's decoder.
- A worker per tile keeps the decoder state of the tile (its place in the GOP and its kept frames).
  A crash stays in one tile. Plain WASM has no threads, so one tile uses at most one core [S 12.3].
- **Bytes.** The worker reads blocks of 256 KiB through `TakeFiles.readRange`, keeps the last 16
  blocks (4 MiB), and reads one block ahead when the reads are sequential [S 12.3]. These values are
  not tuned [S 12.6]. Exact packet ranges from the frame table are a later change after a measurement
  [S 12.5 product notes] [Q714].
- **Out of the worker.** The worker sends the decoded planes, packed, in the format of the decoder
  (I420, I422 or I444), as a transferable buffer [S 12.3]. The page makes a `VideoFrame` and gives it
  to the tile as `TileUpdate.image`. The decoded frames stay inside the browser process. They do not
  go on the HTTP link.

### 7.2 Load of the module and the CSP [agent 18] [Q707]

- The decoder files come with the UI bundle of the Electron app (section 9.4), not from the server
  of the recording [Q697 yes] [Q701 yes].
- The page fetches the WASM file once and lets the HTTP cache keep it. The study fetched and compiled
  it once for each worker (2.4 MB; import 2 to 5 ms, instantiate 19 to 30 ms; all tiles ready with
  the file open in 46 to 73 ms) [S 12.4].
- When libav.js accepts a compiled `WebAssembly.Module`, the page compiles once and gives it to each
  worker [NV: that libav.js 6.10.9 accepts it].
- **The CSP of today blocks the design.** `skellycam-ui/index.html` sets
  `script-src 'self' 'unsafe-inline'; worker-src blob:;` [C]. It has no `'wasm-unsafe-eval'`, so
  Chromium refuses to compile WASM. `worker-src blob:` refuses a module worker from a `'self'` URL,
  and a `blob:` worker takes the CSP of the page [the review] [NV: not tested in Electron 45.3.4].
  The change: `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; worker-src 'self' blob:;`
  [Q707]. T-LEG-43 checks it.

### 7.3 Queues and memory [agent 19]

| Item | Limit | Source |
|---|---|---|
| Decoded frames ahead of the clock, each tile | 8 | [S 12.3] |
| Decoded frames inside the worker, each tile | 8. The worker stops the decode when 8 decoded frames wait. It reads packets in batches of at most 64 KiB, and it keeps the packets that it has not decoded as compressed bytes. | [agent 19]. The study decoded each 64 KiB batch at once: about 50 small frames in one batch [S 12.4] [C study `wasm_worker.mjs` `pump`]. |
| Decoded frames held in the page, each tile | 8 + 1 (on the tile) + 1 (in transfer) | as 6a 9.4 |
| Block cache, each tile | 16 × 256 KiB = 4 MiB | [S 12.3] |
| WASM heap, each tile | measured 24 MiB, no growth [S 12.4]. No build limit: a limit needs a change of the libav.js build files [NV], which is upkeep. The tests check that the heap does not grow (T-LEG-37). | [agent 19] |
| Renderer working set | measured 180 to 400 MB for 1 to 6 tiles [S 12.4]. An estimate for 16 tiles of 720x1280: 0.7 to 1 GB (24 MiB heap + 4 MiB blocks + about 14 MB of frames for each tile, and the module) [the review] [NV] | |

### 7.4 Many cameras [Q700 yes]

- Measured: up to 6 tiles of 720x1280 `mp4v`; the renderer used about 0.76 of a core for 6 tiles in
  play [S 12.4].
- No upper limit on the camera count. The tests and the benchmarks go to 16 tiles of 720x1280. Above
  16 cameras, the host shows the warning "more than 16 cameras: playback is not tested" [Q700 yes:
  "a warning above 16 cameras"].

## 8. Reliability

### 8.1 Open

| Case | Result |
|---|---|
| A camera file with no `moov` (the writer did not finish, or the file is cut) | Refused: "camera file not playable: no index (moov); the recording did not finish". The player offers no repair (6a Y5). |
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
| A fault of the decoder: a rejected libav.js call, a `RuntimeError` (a WASM trap, or an emscripten `abort()` on out of memory), or any exception in the worker | The worker reports "fatal" and ends itself; the page also terminates it. A `RuntimeError` does not end a worker by itself, so this rule is necessary. |
| The worker ends, or gives no answer in 10 s (the page terminates it) | The page starts a new worker for the tile and asks for frame k*. During the restart the tile keeps its last image and is not live (6.5). |
| Two fatal faults at the same frame k | Frame k and the frames up to the next key frame get the mark "damaged at frame k", and the decode starts again at the next key frame. Thus one bad frame does not use up the restarts. |
| The third fatal fault of a tile within 60 s | The tile gets the mark "decoder failed" and makes no more restarts until the player opens again. |
| A tile is late in play | The locked rule of 6.5. |

The other tiles keep playing in each case [6a L3].

### 8.3 What the study measured

Two runs of each script: the same frame hash on each operation of both runs (1,850 operations), no
decoder error, no worker error, no Electron child process lost [S 12.4]. Hours-long files, many
plays in a row and the decoder on macOS, Linux or a weak CPU are not tested [S 12.6].

## 9. The decoder build as a product part

The owner: "yes, lets go with custom libav.js." [O, Q693].

### 9.1 Where the recipe lives [agent 22]

A new folder `skellycam-ui/decoder/`:

| File | Content |
|---|---|
| `package.json`, `package-lock.json` | One dev dependency: `"libav.js": "6.10.9"` (exact). The lock file holds the integrity hash of the tarball. The tarball also holds FFmpeg 9.0 (`sources/ffmpeg-9.0.tar.xz`) [S 12.2]; the build does not use it [Q703 yes]. |
| `ffmpeg.json` | The FFmpeg source of the build [Q703 yes]: `{"version": "9.0.2", "url": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz", "sha256": "<hash>"}`. `build.sh` downloads the tarball outside the container, checks the SHA-256 (a mismatch fails the build), puts it in the `build/` folder of the libav.js source tree, and runs `make FFMPEG_VERSION_MAJOR=9 FFMPEG_VERSION_MINREV=0.2 ...`, the override that [LJ] documents [agent 38]. |
| `Dockerfile` | One stage only: `FROM emscripten/emsdk:6.0.8@sha256:<digest>` and the build steps. |
| `build.sh` | The build steps of the study `wasm_build.sh`, with the part list of 9.2 and the variant name `skellycam-legacy`. |
| `parts.json` | The part list (the input of `mkconfig.js`) and the expected component lists of the checks (9.3). |
| `README.md` | How to build, how to replace the library (9.5), the licences. |

- `build.sh` runs `npm ci` inside the libav.js source tree, as the study does [C study
  `wasm_build.sh`]. That `npm ci` downloads the build tools of libav.js from npm, pinned only by the
  lock file inside the tarball. Dependabot does not watch that lock file (10.1). Whether the build
  works with no network is [NV].
- The outputs (`libav-<version>-skellycam-legacy.mjs`, `.wasm.mjs`, the licence file `license.js`,
  `config.json`, `ffmpeg-config.txt`, and `BUILD_INFO.json` with the input versions, the image digest
  and the SHA-256 of each output) go to `skellycam-ui/decoder/dist/`. Git ignores this folder (9.4).

### 9.2 The part list for v1 only [agent 23]

| Part | v1 needs it | Decision |
|---|---|---|
| `avformat`, `avcodec` | yes | in |
| `demuxer-mp4` (mov) | yes: each v1 file is MP4 | in |
| `decoder-mpeg4`, `parser-mpeg4video` | yes: the v1 writer and the sample data [S 12.1] | in |
| `decoder-h264`, `parser-h264` | for H.264 imports (phase 1 of Q694) | in |
| `decoder-hevc`, `parser-hevc` | HEVC is refused [Q700 yes] | out |
| `demuxer-avi` | no: AVI comes only from the v2 alpha fallbacks [S 12.1 row 9]; the import wizard takes `.mp4` only | out |
| `decoder-msmpeg4v3` | no: no v1 writer uses it | out |
| `demuxer-matroska`, `decoder-mjpeg`, `parser-mjpeg` | no: the new MKV takes play with `ImageDecoder` (6a); MJPEG in AVI is v2 alpha | out |

FFmpeg and libav.js add components on their own. The expected lists must hold them:

| Added component | Why | Source |
|---|---|---|
| `h263` decoder | `mpeg4_decoder_select="h263_decoder qpeldsp"` | [FF `configure`] |
| `iso_media`, `riffdec` (support code of the mov demuxer) | `mov_demuxer_select="iso_media riffdec"` | [FF `configure`] |
| the bit-stream filters `h264_metadata`, `extract_extradata` | the libav.js `decoder-h264` fragment adds them | the study build, `FFMPEG_CONFIGURATION` |
| the protocols `data`, `file` | the libav.js base configuration | the study build |

Neither `mp4v` in MP4 nor H.264 in MP4 needs a bit-stream filter: the `esds` and `avcC` data go to
the decoder as extradata. The study build has `--disable-network`, `--disable-everything` and
`--enable-pthreads`. The study notes say "no threads" [S 12.2]; `--enable-pthreads` appears in the
configuration line all the same [the review reads it as the fiber threads of libav.js] [NV].

This list is smaller than the measured build of the study. The checks and the conformance tests of
section 13 prove it again [NV until they run].

The build keeps the other settings of the study: no external library, plain WASM, no SIMD
(`HAVE_SIMD128 0`), `-Oz`. An `-O3` build decoded no faster and was 3.6 MB instead of 2.4 MB
[S 12.2].

### 9.3 The CI build and its checks [agent 24]

A job `decoder-build` on `ubuntu-24.04` (Docker is on the Linux runners) does these steps:

1. Resolve the digest of the image tag `emscripten/emsdk:<tag>` and compare it with the digest in the
   `Dockerfile`. A difference fails the job.
2. `npm ci` in `skellycam-ui/decoder/` (the tarball by its lock-file integrity).
3. Build in the container. Then build again, clean, and compare the SHA-256 of each output. A
   difference fails the job (a reproducible build) [NV: that the emscripten build is byte-identical
   run to run].
4. Check `config.h` and `config.mak` of the FFmpeg build: `CONFIG_GPL 0`, `CONFIG_NONFREE 0`,
   `CONFIG_VERSION3 0`; the sets of enabled decoders, demuxers, parsers, bit-stream filters and
   protocols each equal the lists of `parts.json` (with the additions of 9.2);
   `FFMPEG_CONFIGURATION` holds `--disable-network` and no `--enable-lib`.
5. Check the size of the WASM file: at most 4 MiB [agent 24].
6. Check the pins: `package.json` has an exact version (no `^`, no `~`, no range); the `FROM` line
   has a tag and a digest; `ffmpeg.json` has an exact version and a SHA-256; the `RELEASE` file of the
   FFmpeg source that the build used reads that version (9.0.2) [Q703 yes].
7. Check that `license.js` has a section for each source that the build links. The built `license.js`
   of the study has sections for ffmpeg, `jrevdct.c`, and emscripten and musl. The tarball also holds
   `emfiberthreads-1.3.tar.gz`, and `license.js` has no section for it [NV: whether the build links
   it].
8. Write `BUILD_INFO.json` and upload the outputs as a workflow artefact.
9. Cache the outputs with the key = the SHA-256 of the files of `skellycam-ui/decoder/` (except
   `dist/` and `README.md`). A cache hit skips steps 2 to 5 and still runs steps 1, 6 and 7. A cache
   that a PR run saves is scoped to that PR.

The conformance tests (T-LEG-24 to T-LEG-26) and the player tests (section 13) then use the artefact
of this job.

### 9.4 How the UI gets the built files [Q697 yes]

The owner accepted: "The 2.4 MB decoder is built by CI from the pinned recipe and packaged with the
UI" (not committed) [Q697 yes].

- `skellycam-ui/decoder/dist/` is in `.gitignore`.
- `npm run decoder:build` builds with Docker. `npm run decoder:fetch` downloads the artefact of the CI
  run for the recipe hash and checks the SHA-256 of each file against `BUILD_INFO.json` [agent 25].
- The installer workflow (`build-installers-pyinstaller.yml`) gets a first job that builds the
  decoder or restores it from the cache. Each installer job downloads it in the same workflow run.
  Thus the 90-day life of an artefact does not matter [agent 25].
- The app puts the decoder files outside the `asar` archive (as `extraResources`), so that a user can
  replace them (9.5) [agent 25].

The alternative that the owner did not take was to commit the outputs. A correction of revision 1:
a workflow of a Dependabot PR gets a read-only `GITHUB_TOKEN` by default, but "You can use the
`permissions` key in your workflow to increase the access for the token" [D troubleshoot]. Thus a
workflow could push the outputs to the PR. It is harder: a commit pushed with `GITHUB_TOKEN` starts
no new workflow run, and Dependabot stops rebasing a branch that another actor pushed to [the review]
[NV].

### 9.5 LGPL duties [agent 26]

FFmpeg in this build is LGPL 2.1 or later [S 12.2]. [LJ]: "FFmpeg is released under the LGPL.
Therefore, if you distribute this library, you must provide sources." The duties of the app:

1. **Licence text.** The app and its release include `license.js` of the build (the LGPL 2.1 text of
   FFmpeg and the other sections of 9.3 step 7). The wrapper functions of libav.js are under the
   "0-clause BSD" licence, "which does not require that the license text itself appear in derivative
   works" [LJ]. (The study notes name it ISC; that is wrong.)
2. **Source.** Each release offers the exact source: the libav.js npm tarball named by its lock-file
   integrity (it holds the libav.js sources in `sources/`), the FFmpeg 9.0.2 tarball of 9.1
   [Q703 yes], and the recipe of 9.1. The release workflow attaches the tarballs to the GitHub
   release, with the same retention as the release.
3. **Replace the library.** The decoder is a separate file that the app loads at run time. The
   `README.md` of 9.1 tells a user how to build a changed library with the recipe and where to put it
   in the installed app. The app checks the SHA-256 of the decoder at load and logs a warning for an
   unknown file. It does not refuse it, because a refusal would stop the replacement.
   - On macOS the app has the hardened runtime and is notarised (`"hardenedRuntime": true`,
     `"notarize": true` in `skellycam-ui/electron-builder.json`) [C]. A file changed in
     `Contents/Resources` breaks the signature. The `README.md` must tell the user how to sign the
     app again with their own identity, or how to run it unsigned [Q709] [NV: the steps].
4. **Modification and reverse engineering.** The app is AGPL-3.0-or-later (`LICENSE`,
   `skellycam-ui/package.json` `"license"`) [C]. Thus its terms permit the modification and reverse
   engineering that LGPL 2.1 section 6 asks for.
5. **No web-served UI.** The UI is the Electron app [Q701 yes], so the source offer and the
   replacement path go with the app and its release.
6. **No GPL part, no non-free part** in the decoder (the checks of 9.3).

This is not legal advice. Question Q699 asks the owner about the patent position.

## 10. Dependabot and upstream monitoring

The owner's condition: "This work must also include suitable dependabot scripts to monitor upstream
repos and trigger build and pr tests so it is minimal work to keep our custom build up to date." [O,
Q693].

### 10.1 The pinned inputs and who watches each one [agent 27]

| Input | Pin | Watched by |
|---|---|---|
| libav.js | `skellycam-ui/decoder/package.json`, exact | Dependabot `npm`, directory `/skellycam-ui/decoder` |
| emsdk image | `skellycam-ui/decoder/Dockerfile`, tag and digest | Dependabot `docker`, directory `/skellycam-ui/decoder` |
| The FFmpeg 9.0.2 tarball [Q703 yes] | `skellycam-ui/decoder/ffmpeg.json`, version and SHA-256 | the weekly workflow of 10.3, which opens a bump PR [Q704 yes] (Dependabot cannot see it) |
| The build tools of libav.js (`npm ci` inside the source tree, 9.1) | the lock file inside the libav.js tarball | nobody directly; a libav.js bump changes them |
| CI actions (checkout, setup-node, cache, upload and download artefact, setup-uv) | full SHA with the version comment on the same line | Dependabot `github-actions`, directory `/` |
| PyAV (makes the test media and the reference, section 13.1) | `pyproject.toml` `av==19.0.2` | not by this work: the Python pins have their own review [NV: no `pip`/`uv` entry in `dependabot.yml` today] |
| Electron (its Chromium draws the tiles) | `skellycam-ui/package.json` | the `npm` entry after its repair (10.6) |

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
- The pages do not say if Dependabot updates the digest of a `FROM` line with a tag and a digest [NV].
  Check 1 of 9.3 fails a PR whose digest does not belong to its tag.

### 10.3 What Dependabot cannot see, and how the gap is covered [agent 29] [Q703 yes] [Q704 yes]

| Gap | Why | Cover |
|---|---|---|
| FFmpeg point releases | The tarball of libav.js 6.10.9 holds FFmpeg **9.0, with no point release** (`ffmpeg-9.0/RELEASE` reads `9.0`) [FF `RELEASE`]. The reference of the study was the FFmpeg 9.0.2 CLI [S 12.4]. | The build uses FFmpeg 9.0.2 through the override [Q703 yes]. The weekly workflow below opens a bump PR for each later point release [Q704 yes]. |
| A security fix of FFmpeg before a libav.js release | FFmpeg is not an npm package, so no npm advisory names it [NV]. | The weekly workflow below: a fix in a point release gives a bump PR; a CVE with no release gives an issue. |
| A security fix of the emsdk image | Dependabot has no security updates for `docker` [D ecosystems]. | The weekly version updates of `docker`. A CVE of the toolchain affects the build machine; the WASM output holds the emscripten runtime and musl parts only [NV]. |
| The build tools of libav.js | pinned by the lock file inside the tarball (10.1) | They change only with a libav.js bump, which the PR pipeline builds. |
| A libav.js release that changes its build or its API | Dependabot gives a version number only. | The PR pipeline of 10.4 builds and tests the bump. |

**The FFmpeg override** [Q703 yes]. [LJ] documents it: "To build against, for instance, FFmpeg 4.3.6,
use `make FFMPEG_VERSION_MAJOR=4 FFMPEG_VERSION_MINREV=3.6`". The same text says that libav.js
"should generally build against any version of FFmpeg in the 4, 5, or 6 series", and that "you should
use the default version unless you have some specific compatibility issue" [LJ]. The recipe pins the
FFmpeg 9.0.2 tarball by its version and its SHA-256 in `ffmpeg.json` (9.1). A build of libav.js
6.10.9 with FFmpeg 9.0.2 is [NV] until the build and the conformance tests of section 13 pass. When a
later libav.js release packs an FFmpeg version at or above the version of `ffmpeg.json`, the bump PR
of that release may drop the override; that is a review point of that PR.

**The weekly workflow** `decoder-upstream.yml` (scheduled each week, and by hand):

1. Reads the FFmpeg version of `ffmpeg.json`.
2. Lists the FFmpeg release tags with `git ls-remote --tags` of the FFmpeg git repository (read
   only, no token).
3. Lists the libav.js release tags of its GitHub repository.
4. Reads the FFmpeg security page (`https://ffmpeg.org/security.html`) and keeps each CVE listed under
   a version newer than the version of `ffmpeg.json`.
5. **A newer FFmpeg point release** of the same major and minor version (for example 9.0.3): the job
   downloads its tarball, computes the SHA-256, writes the new `ffmpeg.json` on the branch
   `decoder/ffmpeg-<version>`, and opens a bump PR, or updates its open PR [Q704 yes]. It pushes and
   opens the PR with the token of the item "The token" below. The PR then starts the pipeline of 10.4.
   A new major or minor FFmpeg version gives an issue, not a PR: libav.js patches FFmpeg by its major
   version [LJ], so that change needs a person.
6. **Each other finding** (a newer libav.js release that Dependabot has not opened yet, a CVE of step
   4 with no release) gives one issue, or updates the open one, with the title "decoder upstream:
   <summary>". The job writes issues with `GITHUB_TOKEN` and `permissions: issues: write`. An issue
   needs no new workflow run.

**Why a token secret.** GitHub: "events triggered by the `GITHUB_TOKEN` will not create a new
workflow run", except some events; for a `pull_request` event of the types `opened`, `synchronize` or
`reopened`, the runs "require approval" first. To start the runs, "use a GitHub App installation
access token or a personal access token instead of `GITHUB_TOKEN`" [D trigger]. Without the token,
each bump PR would wait for a person to approve its runs.

**The token** that the owner must create [Q704 yes] [D fine-grained] [D PAT]:

- **Type:** a fine-grained personal access token.
- **Resource owner:** the owner of the repository (`freemocap`). If the organisation requires approval
  of fine-grained tokens, the token stays `pending` until an organisation administrator approves it;
  until then it "will only be able to read public resources" [D PAT].
- **Repository access:** "Only select repositories", with this one repository only.
- **Repository permissions, and no other:**
  - **Contents: Read and write**, to push the branch `decoder/ffmpeg-<version>` (git push, and the
    git refs and contents endpoints need "Contents" write) [D fine-grained].
  - **Pull requests: Read and write**, to open the PR (`POST /repos/{owner}/{repo}/pulls`) and to
    update it (`PATCH /repos/{owner}/{repo}/pulls/{pull_number}`) [D fine-grained].
  - **Metadata: Read-only.** GitHub lists Metadata as a read-only repository permission [D PAT]
    [NV: that GitHub adds it by itself to each fine-grained token].
  - **Not Workflows.** The job never changes a file in `.github/workflows/`, so it needs no
    "Workflows" permission. A test checks that the job writes only `skellycam-ui/decoder/ffmpeg.json`
    (T-LEG-62).
  - **Not Issues.** The issues of step 6 use `GITHUB_TOKEN`.
- **Expiry:** the longest that the organisation policy allows. The default is "30 days, or less if
  the target has a token lifetime policy set" [D PAT]. The workflow fails with the text "decoder bump
  token missing or expired" when the token does not work, so that the expiry is visible.
- **Secret:** a repository secret for GitHub Actions with the name `DECODER_BUMP_TOKEN`. The
  scheduled workflow is not started by Dependabot, so it can read Actions secrets [D troubleshoot].
- **An alternative of the same scope:** a GitHub App with the same two permissions (Contents and Pull
  requests, read and write), installed on this repository only, with its app ID and private key as
  secrets [D trigger]. GitHub advises an app "for long-lived integrations" [D PAT]. The owner chose a
  token [Q704 yes]; the app stays an option for later.

Limits, said plainly:

- A CVE list seldom names the decoder that it affects. A person must decide if a CVE touches
  `mpeg4`, `h264` or the `mov` demuxer.
- When the format of a page changes, the workflow fails. A failed scheduled run is red in the
  Actions tab [NV: who gets the notice of a failed scheduled run].

### 10.4 The pipeline of a bump PR [agent 30] [Q710]

A Dependabot PR (or a bump PR of 10.3 [Q704 yes]) that changes a file of `skellycam-ui/decoder/` or a workflow starts
these jobs:

1. `decoder-build`: the build, the checks of 9.3 and the artefact.
2. `decoder-conformance` (Linux, Windows, macOS): T-LEG-24 to T-LEG-26 in Node with the new
   artefact.
3. `player-windows`, `player-linux`, `player-macos` of `player.yml`, with the new artefact: the unit,
   component and electron tests of 6a and of this spec.

**Required checks and path filters.** GitHub: when a workflow is skipped by path filtering, its
"Associated checks stay in a "Pending" state and block merging"; the advice is "Avoid requiring
workflows that can be skipped". A job skipped by a conditional "reports "Success"" [D required].
Thus the workflow that holds these jobs has no `paths:` filter. It always runs. A first job finds the
changed paths, and each other job has an `if:` on its result. Then a PR that does not touch the
decoder, for example a `github-actions` bump, is not blocked [Q710].

No step of the pipeline needs a secret. A workflow that Dependabot starts gets a read-only
`GITHUB_TOKEN` by default and only the Dependabot secrets. Its `pull_request` runs are "treated as if
they were opened from a repository fork" [D troubleshoot]. The pull of the emsdk image from Docker Hub
is anonymous [NV: the Docker Hub limits for anonymous pulls on GitHub runners]. Artefact upload and
download use the token of the run. When all checks pass, the bump is "review and merge". When a check
fails, the PR shows which part of the bump broke.

### 10.5 Decoder timing on Linux and macOS [Q708]

The conformance tests prove the pixels on the three systems in CI. They do not prove the timing. The
timing on Linux and macOS is a fact of another system. By the rule of `AGENTS.md` section 4, it comes
only from the self-test: a certify check, with a name in `specs/certify.md` [X5MZ item 7]. The agent
proposes the check name `player-legacy-decode` (decode a generated `mp4v` set in the worker route,
report the seek and play times) [Q708] [NV: not in `specs/certify.md` yet]. Until a report gives the
result, the timing on those systems is [NV].

### 10.6 The `dependabot.yml` of today [Q700 yes]

The present file has one entry: `npm` with directory `/` and a monthly schedule
[C `.github/dependabot.yml`]. The repository root has no `package.json` [C]. The npm manifests of the
UI are in `skellycam-ui/`. The owner accepted the repair [Q700 yes: "repair the Dependabot npm
folder"]: the directory becomes `/skellycam-ui`, in the CI PR of this work.

### 10.7 Documentation read

- [D ecosystems]: "Dependabot supported ecosystems and repositories",
  `https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories`.
- [D options]: "Dependabot options reference",
  `https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference`.
- [D registries]: "Guidance for the configuration of private registries for Dependabot", section
  Docker,
  `https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-private-registries`.
- [D troubleshoot]: "Troubleshooting Dependabot on GitHub Actions",
  `https://docs.github.com/en/code-security/reference/supply-chain-security/troubleshoot-dependabot/dependabot-on-actions`.
- [D required]: "Troubleshooting required status checks",
  `https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks`.
- [D trigger]: "Triggering a workflow" (triggering a workflow from a workflow),
  `https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow`.
- [D fine-grained]: "Permissions required for fine-grained personal access tokens",
  `https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens`.
- [D PAT]: "Managing your personal access tokens",
  `https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens`.

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
| `files/http-take-files.ts` | The HTTP implementation of `TakeFiles` (4.1), with the re-open of 4.2. |

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
// TileMark gets one kind:
| { kind: 'decoder_failed' }   // text "decoder failed" (8.2)
```

### 11.3 A text change of 6a 8.3 [agent 33] [Q715]

6a 8.3 says that `jpeg` holds the bytes of the frame of `image`. The tile code of today already draws
`image` when `jpeg` is null [C `tile/tile.ts` `update`]. The legacy player gives `image` with `jpeg`
null, because it has no JPEG. 6a 8.3 then needs one sentence: "An update with `image` and `jpeg` null
is a new image." This spec does not change `player.md` before the owner accepts it.

### 11.4 Host [agent 34]

- The route of 6a 10 gets one more branch: a v1 folder (2.2) opens in `CanvasTakePlayer` with
  `openLegacyTake`. A v2 alpha folder and an unknown folder show their text of 2.2.
- The `video` branch goes in the later PR of 5.2 [Q685 yes].
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
100 Mbit/s [S 12.4]. H.264: section 3.2.

### 12.2 Targets (proposed; the benchmarks of 13.3 verify them on the Windows test machine) [agent 35]

| Case | Target |
|---|---|
| 6 tiles, `mp4v` 720x1280, GOP 12 | seek p50 ≤ 50 ms, p95 ≤ 100 ms; backward step p50 ≤ 40 ms; forward step p50 ≤ 15 ms |
| Same, play 60 s at speed 1 | 0 refreshes with different frame numbers on the live tiles; after 1 s, at most 1 % of refreshes behind the clock |
| 16 tiles, `mp4v` 720x1280 | play 60 s with at most 1 % behind the clock; renderer working set at most 1.5 GB [NV] |
| H.264 import, 1080p, GOP 30 | no target; results recorded for the owner |

## 13. Tests

### 13.1 Test media [Q698 yes] [Q712] [agent 36]

No camera recording and no camera frame goes into the repository (`AGENTS.md` section 8). The owner
accepted for the real files: "CI downloads the official FreeMoCap sample data, checked by checksum
and never committed. The treadmill take is used only on your machine" [Q698 yes]. The synthetic
media is a proposal [Q712]:

- **Synthetic media at test time.** A new tool `tools/make_legacy_media.py` writes the media into a
  temporary folder at the start of a test run, with PyAV `av==19.0.2` (pinned in `pyproject.toml`,
  libavcodec 63.1.102). The study made its stand-ins in the same way, from real material
  (`py/make_legacy_standins.py`) [S 12.1]. This tool makes the pictures itself: a barcode of the
  camera index and the frame number, on a moving pattern, so that each frame differs. It writes:
  - `mp4v` in MP4 as the v1 writer: FFmpeg's `mpeg4` encoder, tag `mp4v`, GOP 12, no B-frames,
    `yuv420p`, `moov` at the end (no fast start), sizes 720x1280, 640x480 and 1228x574, 30 fps; and
    `mp4v` files with a `tkhd` rotation of 90 and 270;
  - a v1 folder around them: `synchronized_videos/Camera_000_synchronized.mp4` and its time file with
    perf-counter-like values, NaN values, duplicates, a long gap and a short file;
  - H.264 in MP4: `libx264` Baseline GOP 30; High with B-frames, GOP 250 and an edit list (media time
    above 0); a file with a leading empty edit; a file with two non-empty edits (for the refusal); a
    `yuvj420p` file; a 10-bit `yuv420p10le` file and a file with two video tracks (for the refusal
    and the warning);
  - the reference: the SHA-256 of each decoded frame, from a PyAV decode on the **x86-64 Linux** CI
    job only, shared with the other jobs as an artefact. The decoder is the same WASM file on each
    system, so each system compares its decoder output with the one x86-64 reference. The study
    proved bit-exactness only between x86-64 FFmpeg and WASM [S 12.4]; a PyAV decode on arm64 is not
    used as a reference [NV: that arm64 gives the same `mpeg4` pixels].
- **GPL encoders.** `libx264` and `libx265` are GPL. PyAV 19.0.2 is a runtime dependency of the app
  (`pyproject.toml`), and its wheel holds them [C: they open on the Windows development machine,
  2026-11-24]. The app is AGPL-3.0-or-later, which is compatible with GPLv2 or later. The tests use
  them only to make media.
- The encoders `mpeg4`, `libx264` and `libx265` open in PyAV 19.0.2 on the Windows development
  machine (checked 2026-11-24) [NV: on the Linux and macOS wheels].
- **Hash rule.** For each frame: SHA-256 of the Y plane, then the U plane, then the V plane, each as
  its rows of the plane width with no stride padding. This is the rule of the study [S RT terms].
- **Real v1 files** [Q698 yes]:
  - The official FreeMoCap sample data: CI downloads it from the URL in the FreeMoCap v1.8.2 code,
    checks its SHA-256, and keeps it in a temporary folder and in the CI cache. It is never committed.
  - The treadmill session (2024, 6 cameras): only on the machine of the owner, from a folder that an
    environment variable names (`SKELLYCAM_LEGACY_V1_DIR`). The test is skipped when the variable is
    not set.

What only a real v1 file can prove: the box layout that the OpenCV muxer of each v1 version writes
(PyAV's muxer makes the synthetic files, so no synthetic test checks the OpenCV layout), the real bit
rates and sizes, a time file of a real capture with real duplicates, the old names of the sample
data, and the times of 12.2 on real files. The synthetic media proves the decoder, the frame table,
the time map and the faults.

### 13.2 Kinds and runners

- **unit**: Node, `node --test --experimental-strip-types`, as 6a 12.1. No browser. The worker is a
  test double, except in T-LEG-24 to T-LEG-26, which run the real decoder in Node.
- **component**: Electron 45.3.4 with Playwright 1.65.1, as 6a 12.1, with the real decoder in module
  workers.
- **server**: `pytest` of the Python package (`skellycam/tests/`), with files of random bytes.
- **build**: the `decoder-build` job (Linux, Docker).
- **tool**: `uv run pytest tools/tests` (the doc checks), for the CI and Dependabot files.
- **benchmark**: the Windows test machine, by hand, as 6a 12.1. Not in CI.
- **certify**: the check of 10.5 on the other systems [Q708].

Each unit, component and server test runs on Windows, Linux and macOS in CI (6a Y7). One exception:
T-LEG-27 uses real files, so it runs on the Linux CI job (the sample data) and on the owner's machine
(the treadmill session) [Q698 yes]. No test needs a camera. Other systems are tested only through CI,
a runner with no device, and the certify check (`AGENTS.md` section 4).

### 13.3 Test list

"Gen" in the Media column means media from `tools/make_legacy_media.py` at test time. "None" means
bytes that the test builds with no codec data (box structures, NPY headers, file lists).

| ID | Kind | Systems | Media | What it does | Pass criterion |
|---|---|---|---|---|---|
| T-LEG-01 | unit | W, L, M | none | `isLegacyFolder` on file lists: v1 names; sample-data names; import names; `.MP4`; a new take with a manifest; v2 alpha names `<rec>.id-0.idx-0.mp4`; no `synchronized_videos/`; only `annotated_videos/`. | `'v1'`, `'v1'`, `'v1'`, `'v1'`, `null` (6a route), `'v2_alpha'`, `null`, `null`; the texts of 2.2. |
| T-LEG-02 | unit | W, L, M | none | NPY headers: versions 1.0, 2.0, 3.0; `<f8` 1-D; `>f8`; `<f4`; `fortran_order` True; shape `(n, 2)`; a header that is cut; data shorter than the shape. | Only the first three with `<f8` 1-D parse; each other gives `time_file_unusable` with its reason; no exception escapes. |
| T-LEG-03 | unit | W, L, M | none | Time map with time files: 3 cameras with offsets, a NaN in one camera, a row with NaN in all cameras, a duplicate value, a gap of 2 s, a value above 2^53 ns. | T_k as 6.4 against an independent `BigInt` reference; T_k never goes down; the row with no value gives T_(k-1); the gap gives a step of 2 s in T_k; tile labels as 6.4. |
| T-LEG-04 | unit | W, L, M | none | Time map with no time file: header rates 30, 29.97 and 30.5 in 3 cameras; then 4 cameras (30, 29.97, 30.5, 31); then a camera whose `stts` has two entries. | r = 30 for 3 cameras; r = (30 + 30.5) / 2 for 4 cameras; r_c of the two-entry camera as 6.4; T_k = round(k × 10^9 / r); `timeEstimated` true; "Rec: fps" as 6.4. |
| T-LEG-05 | unit | W, L, M | none | One camera with a time file of the wrong length; one with none; one usable. | The usable one gives T_k; the others get `time_file_unusable` (`length`, `missing`) and labels with `~`. |
| T-LEG-06 | unit | W, L, M | none | MP4 index reader on built box trees: `moov` at the end and at the start; `co64`; `stsc` runs; `stss` absent and present; `ctts`; a 64-bit box size; a last box of size 0; `elst` with one edit at media time 0 and at media time 1024, with a leading empty edit, with two non-empty edits; a file with no `moov`; a `moov` past the snapshot; frames past the snapshot; `tkhd` matrices 0, 90, 180, 270 and a shear. | The frame table and the frame time stamps (CTS − M + E, for the frames with M ≤ CTS < M + D) equal a reference that the test computes by hand; `no_moov`, `index_damaged`, `edit_list_not_supported` where 3.3 and 8.1 say; the frame count leaves out the frames past the snapshot; rotations as 3.3; `matrix_ignored` for the shear. |
| T-LEG-07 | unit | W, L, M | none | Codec route on sample entries: `mp4v` 0x20, `mp4v` 0x61, `avc1`, `avc3`, `hvc1`, `hev1`, `av01`, `vp09`, `jpeg`, an unknown entry; and a file named `.avi` with `mp4v` content. | The routes of 3.1; the route depends only on the content; each refusal text names the entry. |
| T-LEG-08 | unit | W, L, M | none | Frame counts 120, 118, 120, and one refused camera. | K = 118; `frame_count_differs` with the three counts; the refused camera is not in K. |
| T-LEG-09 | unit | W, L, M | none | Camera order and labels: `Camera_000`..`Camera_011`; `..._synced_Cam1`..`Cam10`. | Natural order (`Cam2` before `Cam10`); the label is the file stem. |
| T-LEG-10 | unit | W, L, M | none | Seek planner on frame tables with GOP 12, GOP 30, all key frames, and B-frames where a key frame has a decode time before and a presentation time after a target: frames in the kept frames, forward targets inside and across a key frame, backward targets, the first and the last frame. | Rule 1 for a kept frame (no seek); continue only when no key frame is in (j, k]; else a seek on the time stamp of G, the last key frame at or before frame k in decode order; the asked time stamp is the exact table value; a first packet that is not G gives one seek to the key frame before G. |
| T-LEG-11 | unit | W, L, M | none | Worker faults with a fake worker: one fatal fault; a `RuntimeError` that does not end the worker; 3 fatal faults in 60 s at different frames; 2 fatal faults at the same frame; no answer for 10 s; a fault during a seek drag. | A new worker and frame k* after one fault; the worker with the `RuntimeError` is terminated; "decoder failed" at the third fault in 60 s; 2 faults at one frame give "damaged at frame k" up to the next key frame and no third restart; the hung worker ends; the other tiles get each frame; no older target is drawn after a newer one. |
| T-LEG-12 | unit | W, L, M | none | A fake decoder that fails on frame 30, and one that skips the time stamp of frame 30. | "damaged at frame 30" at frame 30 only, with the image of frame 29; frame 31 has no mark; the camera is not refused. |
| T-LEG-13 | unit | W, L, M | none | Each refusal and warning text of sections 2, 3 and 8. | Each text and reason code as the spec gives it. |
| T-LEG-14 | unit | W, L, M | none | The shared `TakeFiles` check suite of 6a 5.1 on `http-take-files.ts` against a Node test server; the answers 200 with the whole file and 206 with a wrong start; a 404 for an expired token, then a re-open with the same snapshot and with a changed snapshot; two 404 in a row. | The results of T-PLAY-39; the two wrong answers are read errors; the first re-open repeats the read and passes; the changed snapshot gives "recording changed on disk"; two 404 give a read error. |
| T-LEG-15 | server | W, L, M | none | The route of 4.2: open, the range table of 6a 5.6, the snapshot, a deleted token, an expired token (a test clock), an unknown path, `..` forms, a link to an outside file, a folder outside the roots, a root whose name is a string prefix of an outside folder, a root in another case (Windows and macOS), a file replaced after the open, a `recording_parent_directory` parameter, a CORS preflight for the `POST` and for `Range`. | Status, bytes and headers as 6a 5.6 and 4.2; 403 "folder not allowed" outside the roots and for the prefix case; the other case is inside on Windows and macOS; the replaced file gets 404; the parameter adds no root; the preflight allows the method and the header; the expose header is on each range answer. |
| T-LEG-16 | server | W, L, M | none | Read 6 files by range for 20 s through the route while a spy counts the bytes that the server reads and sends, and a log capture counts the log lines. | Each response body is a byte range of an original file; no route writes a file; no log line for a range request. |
| T-LEG-17 | server | W, L, M | none | Origin rule of 4.4 item 1 on each route of 4.2 and on `list_recordings`: requests and preflights with `Origin` `https://example.org`, `http://localhost:1234`, `null`, the dev server origin in a development build and in a packaged build, and no `Origin`. | `https://example.org` and `http://localhost:1234`: 403 "origin not allowed", no `Access-Control-Allow-Origin`; `null`: allowed, with `Access-Control-Allow-Origin: null`; the dev origin: allowed only in a development build; no answer has `Access-Control-Allow-Credentials`; other routes of the app keep their CORS rule of today. |
| T-LEG-18 | server | W, L, M | none | Host rule of 4.4 item 2: `Host` `localhost:<port>`, `127.0.0.1:<port>`, `[::1]:<port>`, `localhost:<other port>`, `attacker.example`, `attacker.example:<port>`, a name of the bind settings, and no `Host`. | The first three and the name of the settings: served; each other: 403 "host not allowed", with no byte of a file. |
| T-LEG-19 | server | W, L, M | none | Start the server with a bind setting beyond `localhost` and no login or pairing configured; and with only `localhost`. | The first start refuses the bind with the text of 4.4 item 3 and listens on no address other than the loopback addresses; the second starts normally. |
| T-LEG-20 | build | L | none | The checks of 9.3, steps 4, 5 and 7, on the built outputs. | `CONFIG_GPL 0`, `CONFIG_NONFREE 0`, `CONFIG_VERSION3 0`; the decoder, demuxer, parser, bit-stream filter and protocol sets equal `parts.json` with the additions of 9.2; `--disable-network`; no `--enable-lib`; WASM at most 4 MiB; a licence section for each linked source. |
| T-LEG-21 | build | L | none | Two clean builds of the same recipe. | Equal SHA-256 for each output [NV until it runs]. |
| T-LEG-22 | build | L | none | The pin checks of 9.3, steps 1 and 6. | Exact npm version; a tag and a digest in the `FROM` line; the digest belongs to the tag; `ffmpeg.json` has an exact version and a SHA-256, a wrong SHA-256 fails the build, and the `RELEASE` file of the built FFmpeg reads 9.0.2. |
| T-LEG-23 | build | L | none | The licence files in the outputs and in an app package. | `license.js`, the recipe reference and the source tarball reference are present; the decoder files are outside the `asar`. |
| T-LEG-24 | unit (real decoder) | W, L, M | gen | Decode each frame of the generated `mp4v` files (720x1280, 640x480, 1228x574) in Node with the built decoder. | Each frame hash equals the x86-64 PyAV reference; the frame count equals the table. |
| T-LEG-25 | unit (real decoder) | W, L, M | gen | As T-LEG-24 for the H.264 files, the edit-list files and the `yuvj420p` file. | Each frame hash equals the reference; the edit-list file gives the frames with M ≤ CTS < M + D only. |
| T-LEG-26 | unit (real decoder) | W, L, M | gen | The frame table of `legacy/mp4.ts` against the index of FFmpeg's demuxer in the worker, on each generated file, the edit-list files included. | Equal frame counts and equal frame time stamps; `index_mismatch` for a test file whose `stts` the test changed. |
| T-LEG-27 | component | L (CI, sample data); W (owner machine, treadmill session) | real | Full decode and 100 random seeks + 48 steps per set. | Each frame hash equals a PyAV reference made at test time on that system (x86-64); each seek and step lands on the asked frame. |
| T-LEG-30 | component | W, L, M | gen | 6 tiles of 720x1280 `mp4v`: 100 random seeks (seed 1), the first and the last frame, each key frame and its neighbours, and repeated seeks to a kept frame. | Each tile gives the plane hash of frame k (checked in the decoder client before the draw) and draws its barcode; a seek to a kept frame makes no demuxer seek. |
| T-LEG-31 | component | W, L, M | gen | Steps +1, −1, +10, −10 across key frames and at both ends. | Each step lands on the exact frame on each tile; steps clamp to 0 and K − 1. |
| T-LEG-32 | component | W, L, M | gen | Play 20 s at speed 1, locked, 6 tiles; a test hook notes the frame number of each tile at each refresh, and the hash of each 30th frame. | 0 refreshes with different frame numbers; each hashed frame is exact. The share behind the clock is recorded. |
| T-LEG-33 | component | W, L, M | gen | Cameras with 120, 118 and 120 frames: play to the end, seek to K − 1. | Play stops at frame 117; no frame 118 or 119 is drawn; the warning shows. |
| T-LEG-34 | component | W, L, M | gen | Labels with and with no time files; time format seconds and timecode. | Labels as 6.4; `~` only with no usable time file; the canvas title as 6a 8.4. |
| T-LEG-35 | component | W, L, M | gen | A test hook ends the worker of tile 2 during play, then 3 times in 60 s; a test hook makes tile 3 give "read error" and tile 4 a damaged frame. | Tile 2 shows frame k* again within 1 s after the first end; "decoder failed" at the third; tiles 3 and 4 do not stop play; the live tiles play with 0 different frame numbers among them. |
| T-LEG-36 | component | W, L, M | gen | A camera file cut before its `moov`; a camera file whose last 10 frames lie past the cut. | The first gets the refusal of 8.1 and the others play; the second plays with K from its frame count. |
| T-LEG-37 | component | W, L, M | gen | 16 tiles of 720x1280 `mp4v`: play 30 s, 200 seeks, close. Also one tile of 640x480 with small frames: 50 seeks. | Open `VideoFrame`s ≤ 10 for each tile at each time; decoded frames in each worker ≤ 8; the heap of each worker after the first 10 seeks does not grow; 0 workers and 0 open frames after `close()`; the working set is recorded. |
| T-LEG-38 | component | W, L, M | gen | A page from a second origin plays a generated v1 recording through `http-take-files.ts` from the Python server on the local machine. | It plays and seeks as T-LEG-30; each response is `application/octet-stream` with a byte range of an original file; the bytes on the link are at most the sum of the file sizes plus the repeated block reads. |
| T-LEG-39 | component | W, L, M | gen | Open, play to the end, seek 50 times, close. | Each file of the folder has the same bytes and modification time as before; the folder has no new file. |
| T-LEG-40 | component | W, L, M | gen | The host route: a v1 folder, a new take, a v2 alpha folder, an unknown folder. | The first two open in the canvas player; the others show their text of 2.2. |
| T-LEG-41 | component | W, L, M | gen | `mp4v` and H.264 files with `tkhd` rotations 90 and 270. | The barcode quadrants are upright for both codecs. |
| T-LEG-42 | component | W, L, M | gen | Open a 6-camera recording and count the requests for the WASM file. | One network fetch of the WASM file for the page [NV until 7.2 is checked]. |
| T-LEG-43 | component | W, L, M | gen | The app page with the CSP of 7.2; and a page with the CSP of today. | With the new CSP the decoder compiles and the workers start; with the CSP of today the open fails with a readable error, not a hang. |
| T-LEG-44 | component | W, L, M | gen | The `yuvj420p` file and a `yuv420p` file of the same picture (a grey ramp). | The `VideoFrame` of the `yuvj` file has full range; the drawn pixels of both are within ±8 levels of the expected values. |
| T-LEG-45 | component | W, L, M | gen | The 10-bit file and the file with two video tracks. | The 10-bit camera gets "pixel format yuv420p10le is not supported"; the two-track file plays its first track with `extra_tracks`. |
| T-LEG-46 | component | W, L, M | gen | Play 10 s at speeds 2 and 8, 6 tiles. | The drawn frame number never goes down; 0 refreshes with different frame numbers; the shown rate is recorded. |
| T-LEG-47 | component | W, L, M | gen | The app loads a decoder file whose SHA-256 differs from `BUILD_INFO.json`. | A warning in the log; the decoder still loads. |
| T-LEG-48 | unit | W, L, M | none | `npm run decoder:fetch` with a fake artefact store: a good artefact, one with a wrong SHA-256. | The good one is in `dist/`; the wrong one is refused and `dist/` is unchanged. |
| T-LEG-50 | benchmark | W (test machine) | gen and real | 200 seeks, 48 steps and 60 s of play at 1, 3 and 6 tiles of 720x1280 `mp4v`; and the treadmill session. | The targets of 12.2; p50, p95 and maximum recorded. |
| T-LEG-51 | benchmark | W (test machine) | gen | 16 tiles of 720x1280 `mp4v`, 60 s of play; CPU and working set. | The target of 12.2; results recorded. |
| T-LEG-52 | benchmark | W (test machine) | gen and real | T-LEG-50 through the HTTP route with the link limited to 100 Mbit/s. | Results recorded for the owner. |
| T-LEG-53 | certify | L, M (certify report) | gen | The check `player-legacy-decode` of 10.5 [Q708]. | The report gives the seek and play times; no target until the owner sets one. |
| T-LEG-60 | tool | W, L, M | none | A test of `tools/tests/` reads `.github/dependabot.yml`. | The three entries of 10.2 exist with their directories; the `npm` entry of the UI has `/skellycam-ui`; each directory holds the manifest that its ecosystem reads; the `Dockerfile` has one `FROM` and no `ARG` before it. |
| T-LEG-61 | tool | W, L, M | none | A test of `tools/tests/` reads the workflows. | The workflow of 10.4 has no `paths:` filter and has a changed-paths job; each test job needs `decoder-build`; each action is pinned to a full SHA with a same-line version comment; no job of the bump path uses a secret. |
| T-LEG-62 | tool | W, L, M | none | The logic of `decoder-upstream.yml` on stored text samples (a tag list with 9.0.3 and 9.1.0, a part of the security page, a libav.js tag list), a fake tarball and a fake GitHub API; and a run with no token. | For 9.0.3: one branch and one bump PR with a new `ffmpeg.json` (version and the SHA-256 of the fake tarball), made with the token, and no other changed file (no file in `.github/workflows/`); a second run updates the same PR; for 9.1.0 and for the CVE: one issue with `GITHUB_TOKEN`, updated on a second run; with no token: the job fails with "decoder bump token missing or expired". |
| T-LEG-63 | rehearsal (once) | CI | none | A PR that changes only the libav.js pin (a real bump or a rehearsal on a branch). It needs the approval of the owner, because a PR is visible outside the machine. | Each job of 10.4 runs; the PR is mergeable with no other commit. |

Counts: 18 unit, 19 component, 5 server, 4 build, 3 tool, 3 benchmark, 1 certify, 1 rehearsal:
54 tests.

### 13.4 Rules to tests

| Rule | Tests |
|---|---|
| [O] reliable first | T-LEG-11, T-LEG-12, T-LEG-24 to T-LEG-27, T-LEG-30 to T-LEG-37 |
| [O] short seek | T-LEG-10, T-LEG-30, T-LEG-50 |
| [O] not converted | T-LEG-39 |
| [O] UI on another machine; [O] no server decode | T-LEG-16, T-LEG-38 |
| [O] only v1 | T-LEG-01, T-LEG-40 |
| [O] custom libav.js, Dependabot (Q693) | T-LEG-20 to T-LEG-23, T-LEG-60 to T-LEG-63 |
| [X5MZ item 7] exact pins | T-LEG-22, T-LEG-61 |
| [X5MZ item 7] other systems through certify or CI | T-LEG-53 |
| Q688 yes | T-LEG-14, T-LEG-15 |
| Q685 yes | T-LEG-40 (the removal PR has its own tests) |
| Q697 yes | T-LEG-23, T-LEG-47, T-LEG-48 |
| Q698 yes | T-LEG-27 |
| Q700 yes | T-LEG-07 (HEVC), T-LEG-08, T-LEG-33, T-LEG-60 |
| Q701 yes, Q702 yes | T-LEG-17, T-LEG-18, T-LEG-19 |
| Q703 yes | T-LEG-22, T-LEG-24 to T-LEG-26 |
| Q704 yes | T-LEG-62, T-LEG-63 |
| Q705 yes, Q706 yes | No test: a cancelled step and a scope rule. |
| 2.2, 2.3, 2.4 | T-LEG-01 to T-LEG-05 |
| 3 | T-LEG-07, T-LEG-13, T-LEG-41, T-LEG-44, T-LEG-45 |
| 4 | T-LEG-14 to T-LEG-19, T-LEG-38 |
| 6 | T-LEG-03 to T-LEG-06, T-LEG-08 to T-LEG-10, T-LEG-26, T-LEG-30 to T-LEG-35, T-LEG-46 |
| 7, 8 | T-LEG-11, T-LEG-12, T-LEG-35 to T-LEG-37, T-LEG-42, T-LEG-43 |
| 9, 10 | T-LEG-20 to T-LEG-26, T-LEG-47, T-LEG-48, T-LEG-53, T-LEG-60 to T-LEG-63 |

### 13.5 Measurements owed

| ID | Measurement | Test |
|---|---|---|
| M-LEG-1 | The targets of 12.2 on the reduced build of 9.2 | T-LEG-50, T-LEG-51 |
| M-LEG-2 | The real v1 files through the HTTP route | T-LEG-52 |
| M-LEG-3 | The decoder timing on Linux and macOS | T-LEG-53 (certify) [Q708] |
| M-LEG-4 | Reproducibility of the emscripten build | T-LEG-21 |
| M-LEG-5 | The working set of 16 tiles of 720x1280 | T-LEG-37, T-LEG-51 |

## 14. Differences from `player.md` and accepted text

1. **E2** (6a 18.5): "Old recordings keep a `<video>` path." The answer Q685 yes changes it (section
   5).
2. **L5** (6a 18.3): "No restructuring of today's player." The answer Q685 yes changes it for the
   removal PR of 5.2.
3. **Y1 and L1** (6a 18.1, 18.3): step 6c is "the switch between the new player and the old
   video-element path, and old takes". This spec is the old-takes part, for v1 only [O]. With Q685
   yes, the switch is a removal.
4. **6a 1.3, step 6d** ("The 'upgrade recording' converter"). Cancelled [Q705 yes]. The 6d row of
   6a 1.3 says so and cites
   [ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md).
5. **6a 7.3, frame choice by time.** For v1, the frame index chooses the frame (6.4). The rule of 6a
   7.3 stays for the new format.
6. **6a 8.1, `ImageDecoder` on the main thread.** For v1, the decoder runs in a worker for each tile
   (7.1). The tile still draws on the main thread.
7. **6a 8.3**, the `jpeg` sentence (11.3), and the new mark `decoder_failed` (11.2).
8. **6a 5.4, the snapshot folders.** For v1 the snapshot also lists `synchronized_videos/timestamps/`
   (4.2).
9. **The study advice for H.264** (WebCodecs first, the decoder as the fallback) [S 12.5]. Section 3.2
   proposes the decoder only in phase 1 [Q694].

## 15. Choices of the agent

Each item fills a gap that the rules and answers of the owner and the evidence do not fix. The body
marks each one [agent n].

1. (Decided by Q700 yes: no annotated videos.)
2. The time file `.npy` is the one time source; the CSV copy is not read (2.1).
3. The recognition order of 2.2, the v2 alpha refusal, no refusal of v0.1.0.
4. The NPY rules, "usable" by length, NaN as no time, rounding to integer nanoseconds (2.3).
5. `~` for a time from the header rate (2.4).
6. The decoder for H.264 too in phase 1; a GPU route decided in phase 2 (3.2).
7. The pixel formats, full range for `yuvj`, the colour default (3.3).
8. The `tkhd` rotation for each codec (3.3).
9. The accepted edit lists (3.3).
10. The server route details beyond Q688: the snapshot folders, the root list, the root check by path
    components, the identity check, the preflight, the token life of 30 minutes, no log line per
    range, no copy (4.2).
11. The re-open of an expired token in the client (4.2).
12. The removal list (5.2).
13. The TypeScript MP4 reader, the frame table, the edit list rule, the frame count from the index,
    the cross-check with FFmpeg's demuxer (6.1).
14. The seek rules: cache, continue only up to the next key frame, a seek on the key frame G, exact
    time stamps (6.2).
15. (Decided by Q700 yes: K is the smallest frame count, with a warning.)
16. The time map, the base B, the mean over cameras, the header rate and the median, "Rec: fps", a
    gap plays in real time (6.4).
17. The locked rule, the live tiles, t does not stop (6.5).
18. The WASM load, the module hand-over, the CSP change (7.2).
19. The queue limits, 8 decoded frames inside the worker, no heap limit in the build (7.3).
20. (Decided by Q700 yes: a warning above 16 cameras.)
21. The fault table: fatal faults, restarts, two faults at one frame, 3 faults in 60 s, the answer
    limit of 10 s (8.2).
22. The folder `skellycam-ui/decoder/` and its files (9.1).
23. The part list for v1 and the added components (9.2).
24. The CI build steps, the reproducible build check, the size limit of 4 MiB, the licence check, the
    cache key (9.3).
25. The details of Q697 yes: `decoder:build`, `decoder:fetch`, the installer job, the decoder outside
    the `asar` (9.4).
26. The LGPL duties, the source tarballs on the release, a warning (not a refusal) for an unknown
    decoder file (9.5).
27. The watch table (10.1).
28. The `dependabot.yml` entries (10.2).
29. The weekly upstream workflow and its limits (10.3).
30. The bump pipeline, the always-running workflow (10.4).
31. The module layout (11.1).
32. The interface names (11.2).
33. The text change of 6a 8.3 (11.3).
34. The host route (11.4).
35. The targets (12.2).
36. The synthetic media plan, the x86-64 reference, the hash rule, the test list and its pass
    criteria (13).
37. The concrete form of Q702: the routes it covers, the origin allow-list (`null` and the dev
    origin), 403 texts, no credentials header, the Host allow-list, the refusal of a bind beyond
    `localhost` at start, and the `null`-origin limit that the login or pairing design must cover
    (4.4).
38. The concrete form of Q703 and Q704: `ffmpeg.json`, the download outside the container, the
    `make` variables, the branch name, PR for a point release and issue for a major or minor
    release, the token type, scope, permissions, secret name and the failure text (9.1, 10.3).

## 16. Open questions for the owner

Each question is worded so that "yes" accepts the recommendation. The owner decided Q685, Q688,
Q697, Q698 and Q700
([ADR-8EBK](../decisions/entries/8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md)) and Q701 to
Q706 ([ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md)) on 2026-11-24; they
are not in this list.

- **Q694. H.264 route.** In phase 1, the WASM decoder plays `mp4v` and H.264, with no WebCodecs route;
  a WebCodecs (GPU) route for H.264 is decided in phase 2, after a real import sample exists. Yes?
  (The cost table is in 3.2: on long-GOP H.264, WASM seeks and steps back 2.6 to 3 times slower than
  the GPU, for example 654 to 660 ms per seek and about 1.5 s per backward step at GOP 250 with three
  tiles; on short-GOP 720p H.264 it is as fast as the GPU; at 1080p CRF 18 it keeps up where
  WebCodecs on the CPU does not. The owner is now considering WebCodecs for all H.264 in each
  phase, with WASM for `mp4v`; that is not decided, and section 3 is not rewritten until it is. See
  Q717.)
- **Q699. Patents.** Accept that the build holds the MPEG-4 Part 2 and H.264 decoders, and that their
  patent position is a decision of the owner outside this spec; the technical work does not wait for
  it. Yes? (The libav.js README warns that builds with MPEG-controlled codecs are not made by
  default.)
- **Q707. CSP.** Change the CSP of `skellycam-ui/index.html` to
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; worker-src 'self' blob:;`, so that the
  decoder compiles and the module workers start. Yes?
- **Q708. Timing on other systems.** Add a certify check `player-legacy-decode` to
  `specs/certify.md` (decode a generated `mp4v` set in the worker route, report seek and play times),
  so that the decoder timing on Linux and macOS comes from certify reports. Yes?
- **Q709. macOS replace path.** On the signed and notarised macOS app, the LGPL replace path is: the
  user replaces the decoder file and signs the app again with their own identity (or runs it
  unsigned), as the decoder `README.md` tells. Yes?
- **Q710. Required checks.** The workflow with the decoder and player jobs has no `paths:` filter and
  always runs; its jobs skip by `if:` on a changed-paths job, so that required checks never stay
  "Pending". Yes?
- **Q711. Time map.** The times of 6.4: the mean of the time files over the cameras from the base B,
  made non-decreasing; the median header rate with `~` when no time file is usable; a gap in the
  capture plays as a gap in real time. Yes?
- **Q712. Synthetic test media.** Make the synthetic test media at test time with
  `tools/make_legacy_media.py` and PyAV `av==19.0.2`, in a temporary folder, with the reference from
  the x86-64 Linux CI job only; commit no media. Yes?
- **Q713. Other eras.** Refuse a v2 alpha folder with the text of 2.2; do not refuse a v0.1.0 folder,
  but give it no test and no support. Yes?
- **Q714. Demuxer.** Use FFmpeg's own demuxer in the worker, as measured, and the TypeScript MP4
  reader for the frame table and the route, with a cross-check at open; feed exact packets without
  FFmpeg's demuxer only after a measurement. Yes?
- **Q715. Tile text.** After acceptance, add to 6a 8.3 the sentence of 11.3, the field
  `timeEstimated` and the mark `decoder_failed` of 11.2. Yes?
- **Q716. Spec place.** Keep this spec as the new file `specs/player-legacy.md`, linked from 6a 1.3,
  as the v1 part of step 6c. Yes?
- **Q717. WASM fallback for H.264.** If H.264 goes to WebCodecs, keep the `h264` decoder in the WASM
  build as the fallback when WebCodecs refuses a file (`isConfigSupported` says no) or a decode fails.
  Yes? (Reason: the study advises this fallback, and the decoder was exact on each H.264 file of the
  study [S 12.4, S 12.5]; it costs build size only.)
- **Q718. Phase 2 output format.** Phase 2 writes 8-bit 4:2:0 H.264, so that the GPU decoder applies.
  Yes? (Reason: Chromium sends a 4:2:2 H.264 file to the software decoder; in the study, a set of six
  720p30 GOP 250 tiles with four 4:2:2 tiles (`no-preference`) had a seek p50 of 861 ms, against
  529 ms for six 4:2:0 tiles on the GPU [S RT]. This question belongs to the writer of phase 2, not to the v1 player; this spec lists it as
  the coordinator asked.)

## 17. Not verified

- No real sample of a v1 import, of v1.0.26 to v1.0.30, or of an HEVC file [S 12.6].
- The reduced part list of 9.2 was not built. The study built the larger list [S 12.2].
- A byte-identical rebuild of the decoder (T-LEG-21); a build with no network (9.1).
- A build of libav.js 6.10.9 with FFmpeg 9.0.2 (9.1, 10.3) [Q703 yes].
- That GitHub adds the Metadata permission by itself to a fine-grained token; whether the
  organisation requires approval of fine-grained tokens; the longest token life that its policy
  allows (10.3).
- That an origin `null` is the only origin of the packaged app page in Electron 45.3.4, and the
  design of the login or pairing (4.4).
- Whether the build links `emfiberthreads`, and its licence (9.3 step 7); what `--enable-pthreads`
  does in this build (9.2).
- The decoder timing on Linux and macOS, and on a weak CPU; hours-long files; many plays in a row
  [S 12.6]; 16 tiles of playback and their working set.
- That all cameras of a v1 recording share one clock (2.3).
- The colours that Chromium draws for a `VideoFrame` (3.3).
- That libav.js 6.10.9 accepts a compiled `WebAssembly.Module`; the CSP behaviour in Electron 45.3.4
  (7.2).
- That Dependabot keeps an exact npm pin exact, and updates a `FROM` digest (10.2); the Docker Hub
  limits for anonymous pulls (10.4); who gets the notice of a failed scheduled run (10.3).
- That no npm advisory names an FFmpeg CVE (10.3).
- The behaviour of a pushed commit on a Dependabot branch (9.4).
- A DNS rebinding attack on this server (4.4).
- That arm64 FFmpeg gives the same `mpeg4` pixels as x86-64 (13.1).
- That the PyAV 19.0.2 wheels for Linux and macOS have the `mpeg4`, `libx264` and `libx265` encoders
  (13.1).
- The steps to sign the macOS app again after a replacement (9.5).

Resolved in revision 2 (code or source read on 2026-11-24): the bind address (4.4), the CORS rule
(4.4), the CSP (7.2), the FFmpeg version in the tarball (10.3), the documented FFmpeg override
(10.3), the licence of the libav.js wrapper (9.5), the edit list and seek behaviour of FFmpeg's mov
demuxer (6.1, 6.2), the components that `configure` adds (9.2), the required-check behaviour (10.4).

## 18. The rules and answers of the owner (2026-11-24)

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

The standing rules of the owner, as the coordinator listed them (not his exact words; X5MZ item 7):
exact version pins everywhere (`==` for Python, exact npm versions, CI actions by full SHA, toolchain
images by an exact tag or digest); spec and tests before code; LF line endings; no camera recordings
or frames committed (a test media file needs a decision); other systems are tested only through the
certify process or CI.

The answers of the owner of 2026-11-24
([ADR-8EBK](../decisions/entries/8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md)). His words:
"Q688, Q685, Q697, Q698, Q700 yes". The questions:

- Q688: "Add the server route (token, allowed folders only, no folder from a request), and keep the
  Electron direct path for now?"
- Q685: "v1 plays in the canvas player, and a later PR removes the old `<video>` player and the server
  transcode code?"
- Q697: "The 2.4 MB decoder is built by CI from the pinned recipe and packaged with the UI?" (not
  committed)
- Q698: "CI downloads the official FreeMoCap sample data, checked by checksum and never committed. The
  treadmill take is used only on your machine?"
- Q700: "HEVC refused until a real sample exists; playback length is the smallest frame count of the
  cameras, with a warning; no annotated videos in this step; a warning above 16 cameras; repair the
  Dependabot npm folder?"

The answers of the owner of 2026-11-24
([ADR-0C4Y](../decisions/entries/0C4Y-answers-of-the-owner-q701-to-q706.md)). His words: "Q701 - Q706
agree". The questions, each with the recommendation that he agreed to:

- Q701: "When the UI runs on another machine, is it the installed skellycam app, or a page that the
  server hands to any browser?" Recommendation: the installed Electron app.
- Q702: "Remove the 'any origin' rule for these routes, check the Host header, and put login or
  pairing for a remote UI in the spec as a requirement before the server listens beyond localhost?"
  Recommendation: yes.
- Q703: "Use the documented libav.js override to build against FFmpeg 9.0.2, not the plain 9.0 inside
  the package?" Recommendation: yes (one more pinned input with a checksum).
- Q704: "When FFmpeg publishes a new point release, the weekly job opens a bump PR that runs the full
  build and tests? This needs a token stored as a repository secret, because GitHub does not run
  workflows on a PR opened with the default token." Recommendation: yes; the owner creates the token,
  with the exact minimum permissions stated for him.
- Q705: "Does 'old recordings must not be converted' cancel that step [the 'upgrade recording'
  converter, step 6d of player.md 1.3]?" Recommendation: yes, cancel it.
- Q706: "Leave the v1.0.0-rc to v1.0.23-rc builds out of scope?" Recommendation: yes.
