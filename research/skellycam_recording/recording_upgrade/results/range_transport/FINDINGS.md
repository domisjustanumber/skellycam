# T-S5: byte-range reads through skellycam's FastAPI route and Electron protocol.handle

2026-11-12. i7-14700K, Windows 11. Electron 35.7.5 (Chrome 134) and 45.2.3 (Chrome 156).
FastAPI 0.162.5, Starlette 1.3.1, uvicorn 0.54.0 with h11 0.16.0 (httptools not installed), anyio 4.14.2,
Python 3.13, PyAV 19.0.2. skellycam-phase1 at 7d06ba2e1.
Results: `semantics.json` (raw HTTP), `electron_functional.json`, `electron_bench.json`, `run_meta.json`.
Scripts: `scripts/range_transport/` (server.py, semantics.py, make_media.py, prep_cfg.py, electron/main.cjs + page.html,
run_electron.ps1, summarize.py). Nothing was installed. Servers were bound to 127.0.0.1 only and stopped afterwards.
Large media files (256 MiB pattern file, 4.69 GB MKV) were deleted afterwards.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked these against the result files: every transport's paced-load reads/s and dropped ticks in `electron_bench.json`, in both versions, and the as-is route's `.mka` note in `semantics.json`.*

## 1. Answer
- Use `protocol.handle` with a hand-written single-range handler. It reads as fast as `file://`, returns 206 + `Content-Range`,
  and kept up with 16 × 60 fps × 150 KB with 0 dropped ticks (median of 5, both Electron versions) [M].
- The FastAPI route as it is today can't serve the player (§3). Fixed, it only just keeps up, and not behind skellycam's
  logging middleware (§5). Keep it only as a fixed fallback for non-Electron use.
- A `net.fetch('file://')` passthrough adds nothing over `file://` and costs more CPU (§4, §5).
- The locator needs no change (§7).

## 2. Method
- **Server ("real" mode):** the real `playback_router`, imported read-only, inside an app built like skellycam's:
  `cors(app)` → routers → `add_middleware(app)`, with skellylogs at TRACE as in `skellycam/__main__.py:99-100`
  (console + file, no websocket queue). The fixed routes `/fixed/{name}` and `/fixed_ns/{name}` sit in the same app.
- **Server ("bare" mode):** only CORSMiddleware (with `expose_headers`) and the fixed routes.
- **Raw HTTP checks:** `semantics.py`, using `http.client`.
- **Electron harness:** the page is loaded from `file://`, like skellycam-ui's packaged build
  (`electron/main/services/window-manager.ts:121` `loadFile`). Two custom schemes are registered privileged
  (standard, secure, supportFetchAPI, stream, corsEnabled):
  - `skr://` has its own Range handler: `fs` read into a Buffer, 206, `Cache-Control: no-store`, ACAO `*`.
  - `skn://` passes the request through to `net.fetch(pathToFileURL(p), {headers})`.
- **Test files:**
  - `cam0.mkv`: 300 × 720p JPEG frames (212–297 KB each) with the `.skfr` sidecar appended by `append_attachment.py`;
  - a 4.69 GB MKV whose FileData starts at 4,685,429,234;
  - flac_skau `.mka` files with an embedded `.skau`;
  - a 256 MiB pattern file in which every 4-byte word encodes its own offset;
  - a 92.7 MB H.264 MP4, which the as-is route serves without transcoding.
- **Benchmark:** each item was run 5 times, with the reps interleaved across transports. Offsets are random.
  "lat" = 150 reads at concurrency 1, or 640 at concurrency 16. "sustained" = 3 s at concurrency 16.
  "paced" = 16 workers, each reading 150 KB on a 60 Hz tick for 4 s (3,840 due); a tick missed while a read is still
  open counts as dropped.
- **CPU:** Electron `cumulativeCPUUsage` delta / wall time, in % of one core; `process_time` delta for uvicorn.
  The GPU process is not included.
- **Load:** two other agents were running Electron/PyAV tests. Machine CPU was 9–17 % (`run_meta.json`).
- **Running the real-mode server:** under `python -I`, skellylogs' console handler raises an encoding error on every log
  line unless `-X utf8` is added.

## 3. skellycam's playback route today
Code read:
- `stream_video` calls `_ensure_web_compatible` on every request [C] (`skellycam/api/http/playback/playback_router.py:420`).
  That probes the file with `cv2.VideoCapture` [C] (`skellycam/core/recorders/videos/fourcc_codec_helpers.py:204-208`).
  For MJPEG it then transcodes to a `.web.mp4` and serves that file instead [C] (`playback_router.py:115-139`).
- Every request also lists the folder [C] (`playback_router.py:407-412`).
- The route is GET only [C] (`:393`). `VIDEO_EXTENSIONS` has no `.mka` [C] (`:34`).
- It returns Starlette `FileResponse` [C] (`:432-437`). In Starlette 1.3.1 that already handles Range:
  `Accept-Ranges`, single range → 206 + `Content-Range` + `Content-Length`, multi-range → multipart,
  unsatisfiable → 416 + `bytes */size` [C] (`starlette/responses.py:318, 364-372, 398-455, 457-478`).
- CORS is `allow_origins=["*"]` with `allow_credentials=True` and no `expose_headers` [C] (`skellycam/api/middleware/cors.py:6-12`).
- Every request is logged twice at API level through `BaseHTTPMiddleware` [C] (`add_middleware.py:14-40`).

Measured (`semantics.json`, `electron_*`):
- **JPEG MKV:** the first request took 2,130 ms (transcode) and returned `.web.mp4` bytes, `Content-Range … /22211068`,
  not the 76.6 MB MKV. Later requests served the cached `.web.mp4`. The locator fails ("bad vint @0") [M].
- **`.mka`:** 404, and it isn't listed [M].
- **H.264 MP4:** explicit, suffix, open-ended and clamped ranges are all correct 206 with exact bytes.
  Past EOF and `bytes=-0` give 416 + `bytes */size`. `bytes=10-5` and `items=` give 400. Multi-range gives 206 multipart.
  HEAD gives 405 [M].
- **Speed:** 16–24 ms per read at concurrency 1, and 66–72 reads/s whatever the size or concurrency.
  16 × 60 fps dropped 95 % of ticks [M].
- **Concurrency:** without `Cache-Control`, Chromium's HTTP cache fails 1–2 % of concurrent ranges to one URL with
  `net::ERR_CACHE_OPERATION_NOT_SUPPORTED` (fetch: "Failed to fetch"), in E35 and E45 [M]. `cache:'no-store'` on the
  client, or `Cache-Control: no-store` from the server, removed every failure (0 of 2,880 per configuration) [M].
  Sequential FLAC reads were also 3–4× slower with the cache on: 1,406 reads took 8.0–9.8 s, against 1.9–2.6 s [M].
- **CORS:** a `file://` page could read `Content-Range` without `Access-Control-Expose-Headers` [M], so Electron doesn't
  apply CORS response filtering to `file://` pages [I]. From an `skr://` page origin, `Content-Range` was `null` on the
  as-is route, and readable on the fixed route, which exposes it [M]. So dev mode (Vite `http://localhost:5173`) needs
  the expose header [I].
- **Logging:** 131,108 requests wrote 81.3 MB of log, about 620 B per request. At 960 reads/s that is about 2 GB/h [M/arith].
- **`localhost` vs `127.0.0.1`:** 4 KB reads at concurrency 1 had p50 2.2–2.3 ms both ways. skellycam-ui uses `localhost`;
  the server here bound 127.0.0.1 only [M].
- **Connections:** the server saw at most 6 connections from the renderer (the counts of 7 include the harness's own CPU poll) [M].
  This matches Chromium's 6-per-host HTTP/1.1 limit [NV]. At concurrency 16, HTTP p50 therefore rises to 17–22 ms (queueing) [M].

## 4. Electron protocol.handle
- **Headers:** the `Range` header reaches the handler unchanged (`req.headers.get('range')`), in E35 and E45 [M]
  (`handler_first_headers`).
- **Own handler (`skr`):** all checks pass in both versions [M]:
  - 206 with exact `Content-Range` / `Content-Length`; suffix and open-ended ranges work;
  - HEAD gives 200 / 206; past EOF and multi-range give 416 + `bytes */size`;
  - ranges past 4 GiB have the right SHA;
  - the locator takes 3 reads with identical SHA (cam0 2.2–2.9 ms, 4.69 GB file 3.8–8.4 ms);
  - FLAC decode is sample-exact (E45) or within 0.51 LSB (E35, as under `file://`);
  - 320 × 150 KB at concurrency 16 gave 0 bad reads.
- **Passthrough (`skn`):** it gives exactly `file://`'s behaviour: 200, no `Content-Range` / `Content-Length`, and
  past-EOF and multi-range fetches throw (`net::ERR_REQUEST_RANGE_NOT_SATISFIABLE`). The bytes are correct [M].
- **Untested [NV]:**
  - whether the `file://` page needs ACAO and `corsEnabled` to read the custom scheme (both were always set);
  - an `http://` page origin fetching the scheme.

## 5. Speed: does 16 × 60 fps × 150 KB (≈ 140 MB/s) keep up?
Medians of 5 runs [min–max]. Full tables in `electron_bench.json`.

| Transport | E35 paced: reads/s, dropped / 3,840 | E45 | E35 sustained c16 reads/s | E45 | CPU at paced load, E35 / E45 (sum of processes, % of a core) |
|---|---|---|---|---|---|
| `file://` | 960, 0 [0–115] | 959, 4 [0–33] | 3,077 | 3,638 | 103 / 121 |
| `skr` | 960, 0 [0–19] | 960, 0 [0–2] | 3,120 | 3,314 | 116 / 113 |
| `skn` | 960, 0 [0–5] | 960, 1 [0–11] | 1,566 | 1,635 | 181 / 215 |
| FastAPI fixed, bare | 922, 143 [65–433] | 922, 146 [0–244] | 890 | 952 | 323 / 273 |
| FastAPI fixed, skellycam middleware | 725, 940 [874–1,314] | 705, 1,020 [870–1,368] | 747 | 717 | 268 / 235 (at < 960/s) |
| FastAPI as is | 72, 3,641 | 70, 3,652 | 70 | 66 | — |

- `file://` and `skr` have about 3× headroom. `skn` has about 1.7×. HTTP has none: the real app falls 25 % short and
  the bare server about 4 % short [M].
- Small reads (1.5 KB, 4 KB) at concurrency 1:
  - `skr` 0.3–0.5 ms p50;
  - `file://` 0.5–0.6 ms;
  - `skn` 0.8–1.0 ms;
  - HTTP fixed 1.1–1.6 ms;
  - as is 16–18 ms.

  Audio needs about 47 reads/s per track, which every working transport covers by a wide margin [M].
- Where the CPU goes:
  - `file://` loading and the `skr` handler both run in the main (browser) process: 60–82 % and 75–78 % of a core at
    the target load [M];
  - the protocol handler runs on the same event loop as the app's IPC, and its effect on UI/IPC latency was not
    measured [NV];
  - HTTP spends 134–144 % of a core in uvicorn, plus 36–60 % in Chromium's network service [M].
- Not tested: the low-end laptop, longer than 4 s paced runs, real JPEG decode at the same time (TP4) [NV].

## 6. What each transport must implement
**Protocol handler (primary):**
- Map the URL to a file under the allowed recording roots only; reject `..` and anything outside them.
- GET, no Range → 200, `Content-Length: size`, `Accept-Ranges: bytes`.
- Single range `bytes=a-b`, `bytes=a-`, `bytes=-n` → 206 with:
  - `Content-Range: bytes s-e/size`;
  - `Content-Length: e-s+1`;
  - `Accept-Ranges: bytes`;
  - `Content-Type: application/octet-stream`.

  Clamp `e` to `size-1`. Read with one positional read into a Buffer for small ranges; stream large ones.
- `s >= size`, `bytes=-0`, malformed or multi-range → 416 + `Content-Range: bytes */size`.
- HEAD → the same headers with no body.
- Add `Cache-Control: no-store`. For a page on another origin, add `Access-Control-Allow-Origin` and
  `Access-Control-Expose-Headers: Content-Range, Content-Length, Accept-Ranges`.
- Cache open file handles and sizes. Close them when recordings change.

**FastAPI route (fallback; changes to `playback_router.py`):**
- Serve the original file. Never transcode for the canvas player: drop `_ensure_web_compatible` from this path
  (phase 1 already removes it).
- Serve `.mka`, and the separate sidecar files while they exist.
- Accept HEAD (`api_route(methods=["GET","HEAD"])`).
- Send `Cache-Control: no-store` (this alone fixes the concurrent failures [M]).
- Send `Access-Control-Expose-Headers: Content-Range, Content-Length, Accept-Ranges`, either in `CORSMiddleware` or on the
  response.
- Don't probe or list the folder on every request; cache path → `stat` per recording.
- Exclude this route from the per-request API logging.
- Starlette 1.3.1 `FileResponse` already does the Range semantics above (§3).
- Even with all of this, HTTP is at its limit for 16 × 60 fps (§5).

**`file://` (last-resort fallback, as in plan row 1.9):** accept 200 without a size. A fetch past EOF throws.

## 7. The locator
- No change is needed. It needs no file size and gets the same 3 reads and identical SHA under 200-without-size
  (`file://`, `skn`) and 206 (HTTP, `skr`), including FileData at 4,685,429,234 [M].
- Changes in the reader that wraps `fetch` (not in the locator):
  1. Return an empty array for 416, and for a fetch that throws because the range is past EOF (`file://`, `skn`).
     Then the locator reports `attachments-past-eof` instead of throwing [I: past-EOF throw measured; the locator path itself not run].
  2. Keep the capped read, and check that a 206's `Content-Range` start equals the requested offset.
- Optional: keep the total size from `Content-Range` when present, to reject a SeekHead position past EOF before reading it.

## 8. Tests to add to TP4 (T-S5)
1. **Range semantics matrix** on the shipped transport and on the fixed route: the probes in `page.html` `semantics()`
   and `semantics.py`, including past-EOF, HEAD, suffix ranges and three ranges past 4 GiB with SHA.
2. **Concurrency with the HTTP cache on** (default session): 640 × 150 KB at concurrency 16 → 0 errors.
   This catches a missing `no-store`.
3. **Paced load:** 16 × 60 fps × 150 KB for ≥ 60 s, on Gerald and the low-end laptop, through `protocol.handle`.
   Pass: dropped ticks ≤ 0.5 %. Record main-process, renderer, GPU (and uvicorn, for the fallback) CPU.
   Repeat with real `ImageDecoder` decode running (joins the TP4 CPU variants).
4. **Main-process responsiveness:** IPC round-trip latency and window-event latency while (3) runs.
5. **Locator + FLAC through the shipped transport** on real TP2 recordings: embedded `.skfr` and `.skau` found in
   3 reads with matching SHA; FLAC decode by offset sample-exact (E45).
6. **Route regression:** a JPEG MKV is served byte-identical (no `.web.mp4` created); `.mka` is served; HEAD → 200.
7. **Non-`file://` origin** (Vite dev): `Content-Range` is readable through the fallback route.
8. **Path safety:** the protocol handler refuses paths outside the recording roots.

## 9. Side observations
- The as-is route's 405 to HEAD showed up in the page as 200 with a length. Chromium's cache likely answered it [I]
  (the server log shows 405).
- From the `skr://` origin, the first request to the as-is route failed with `net::ERR_FAILED` and later ones worked.
  The cause was not isolated [NV]. A likely cause is a cached entry from the `file://` window with a different echoed origin.
