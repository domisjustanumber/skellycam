# A56K — Choices of the v1 playback spec: frame table and seek rules, the WebCodecs route and its WASM fallback, locked play, decoder build in CI, Dependabot

**Status:** accepted, 2026-11-25 (user, Q801 of
[ADR-2Z2D](2Z2D-answers-of-the-owner-q800-to-q803-and-acceptance-of-the-v1-playback-spec.md); commit to
dom/legacy-player; was proposed, 2026-11-24 (agent; builds the rules and answers of the owner in
[ADR-X5MZ](X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md),
[ADR-8EBK](8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md),
[ADR-0C4Y](0C4Y-answers-of-the-owner-q701-to-q706.md) and
[ADR-VHD3](VHD3-answers-of-the-owner-q694-q717-q718.md))).

## Decision

The draft spec [`player-legacy.md`](../../specs/player-legacy.md), revision 5, and its test list
T-LEG-01 to T-LEG-72 (69 tests). Section 15 of the spec lists the 41 choices of the agent. Section 16
gives the open questions Q699, Q707 to Q716 and Q723 to Q728. The main choices:

1. **Scope.** v1.0.25 and v1.0.31 to v1.8.2, the sample data and import folders; a v2 alpha folder is
   refused; v0.1.0 is not refused, not supported.
2. **Time file.** `<stem>_binary.npy`; T_k is the mean over the cameras, made non-decreasing; with
   none, the median header rate and `~`.
3. **Two lists.** The sample list (each sample, decode order) feeds the routes and gives G; the frame
   table (the frames with M ≤ CTS < M + D, time stamp CTS − M + E) gives k and K. One G rule for both
   routes: the last key sample at or before d whose CTS is at or before that of frame k.
4. **WebCodecs route for H.264** (VHD3). One `VideoDecoder` per tile; codec and description from
   `avcC`; `no-preference`; chunk time stamps by `Math.round`; no reliance on output order. The feed
   mode of the study: continue or reset (`reset` and `configure`); up to 24 extra chunks with waits of
   4 and 2 ms, stopped at the last sample; one flush; after a flush the next request starts at a key
   chunk; 4 kept frames; `decodeQueueSize` below 4 in play. A reclaimed codec gets a new decoder (Q728).
5. **Fallback to the WASM `h264` decoder** (VHD3), per tile, logged once, a detail text, no switch
   back: F1 not supported; F2 a decoder error; F3 no output for 3 s while sent frames are not out or a
   flush is pending, at any point; F4 the frame missing after the flush of a seek that was not
   cancelled; F5 time stamps not unique. Wrong pixels with the right time stamp are not detectable in
   the product. A software decoder inside WebCodecs is not detected.
6. **Locked play.** k* = min(target, the newest ready frame of each live tile); t does not stop; a tile
   rejoins only with a frame at or above k*, so the shown frame never goes down.
7. **Server route details.** Snapshot folders, roots, a root check by path components, identity
   checks, a token life of 30 minutes with one re-open, the Host allow-list, a refused remote bind
   without login or pairing; `null` origin only with the secret header of Q723.
8. **WASM worker.** One per tile; at most 8 decoded frames; any `RuntimeError` is fatal; restarts.
9. **Build.** The recipe in `skellycam-ui/decoder/` (libav.js 6.10.9, FFmpeg 9.0.2 in `ffmpeg.json`,
   `emscripten/emsdk:6.0.8` by tag and digest); parts mov, `mpeg4`, `h264` (the fallback); CI builds
   twice and checks licence flags, component sets, pins and `license.js`.
10. **Dependabot and the watch.** `npm` and `docker` on `/skellycam-ui/decoder`, `github-actions` on
    `/`; a weekly bump PR for an FFmpeg point release (the token of Q704, or the default token with an
    approval click if Q725 is yes); the facts on forks, default branch, 60 days and notices.
11. **Tests.** Synthetic media from PyAV `av==19.0.2`, with a file whose edit cuts frames mid-GOP; the
    x86-64 reference; plane hashes on both routes; fakes for F3, the feed rules, the output order and
    the route independence; component tests for the rejoin, a reclaimed codec and a read error.

## Reason

1. One exact decoder per codec: the WASM decoder gave the pixels of x86-64 FFmpeg on 73,819 of 73,819
   frames; WebCodecs GPU and software outputs were bit-identical to the reference (study 9.2, 12.4).
2. The feed rules are the ones that the study ran exact (`app/wc.mjs` `seekFeed`, 726 of 726 seeks).
3. The edit-list and seek rules follow the FFmpeg 9.0 source (`libavformat/mov.c`).

## Evidence

The H.264 study, part A: `research/h264_study/part_a/NOTES.md` sections 9 to 13, `RESULTS_TABLE.md`,
`app/mp4.mjs` and `app/wc.mjs`, branch `dom/h264-scrub-study`, commit 71caa2d0b. The legacy
inventory, branch `dom/research`, commit 7d8f8911b. The FFmpeg 9.0 source and the README in the
libav.js 6.10.9 tarball. The GitHub pages of spec section 10.7.

## Alternatives rejected

- `prefer-hardware`: 4:2:2 files failed to configure (study 9.2).
- A seek on the time stamp of frame k on the WASM route: with B-frames it can land after frame k.
- An allow-list entry for `null` alone: any page can make a `null` origin.

## Open work

None in [open-work.md](../open-work.md). The questions are in section 16 of the spec.
