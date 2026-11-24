# A56K — Choices of the v1 playback spec: frame table and seek rules, the WebCodecs route and its WASM fallback, locked play, decoder build in CI, Dependabot

**Status:** proposed, 2026-11-24 (agent; builds the rules and answers of the owner in
[ADR-X5MZ](X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md),
[ADR-8EBK](8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md),
[ADR-0C4Y](0C4Y-answers-of-the-owner-q701-to-q706.md) and
[ADR-VHD3](VHD3-answers-of-the-owner-q694-q717-q718.md)).

## Decision

The draft spec [`player-legacy.md`](../../specs/player-legacy.md), revision 4, and its test list
T-LEG-01 to T-LEG-63 (60 tests). Section 15 of the spec lists the 40 choices of the agent. Section 16
gives the open questions Q699 and Q707 to Q716. The main choices:

1. **Scope.** v1.0.25 and v1.0.31 to v1.8.2, the sample data and import folders; a v1 recording has
   `synchronized_videos/*.mp4`; a v2 alpha folder is refused; v0.1.0 is not refused, not supported.
2. **Time file.** `<stem>_binary.npy` (`<f8`, 1-D, the camera's length); T_k is the mean over the
   cameras from the smallest first value, made non-decreasing; with none, the median header rate and
   `~`.
3. **WebCodecs route for H.264** (VHD3). One `VideoDecoder` per tile on the page main thread; codec and
   description from `avcC`; `hardwareAcceleration: 'no-preference'` (the study: `prefer-hardware`
   failed on 4:2:2); chunks in decode order with the time stamp CTS − M + E in microseconds; seek from
   the key sample G to d, decoder kept live (feed mode), one flush after d + 24.
4. **Fallback to the WASM `h264` decoder** (VHD3), per tile, logged once, shown as a detail text, no
   switch back: F1 not supported; F2 a decoder error; F3 no output within 3 s after a key chunk; F4 the
   frame missing after a flush; F5 time stamps not unique. A software decoder inside WebCodecs is not
   detected; the route reports only what the API gives.
5. **Server route details beyond Q688 and Q702.** Snapshot folders, roots, a root check by path
   components, identity checks, a token life of 30 minutes with one re-open; the origin allow-list
   (`null` for the packaged app), the Host allow-list, a refused remote bind without login or pairing.
6. **Frames.** The frame index is the truth. The TypeScript MP4 reader keeps the frames with
   M ≤ CTS < M + D, as FFmpeg's `mov_fix_index` does. WASM seek: a kept frame, a continue up to the
   next key frame, else a seek on the key frame G itself and a check of the first packet; only the
   exact time stamp is shown.
7. **Locked play.** k* = min(target, the newest ready frame of each live tile); t does not stop.
8. **WASM worker.** One per tile; at most 8 decoded frames; any `RuntimeError` is fatal; restarts;
   "decoder failed" at the third fault in 60 s.
9. **Build.** The recipe in `skellycam-ui/decoder/` (libav.js 6.10.9, FFmpeg 9.0.2 in `ffmpeg.json`,
   a one-stage `Dockerfile` with `emscripten/emsdk:6.0.8` by tag and digest). Parts: mov demuxer,
   `mpeg4` and `h264` (the fallback) with their parsers and the added components. CI builds twice and
   checks licence flags, component sets, pins and `license.js`.
10. **Dependabot.** `npm` and `docker` on `/skellycam-ui/decoder`, `github-actions` on `/`. A weekly
    job opens a bump PR for an FFmpeg point release with a fine-grained token (this repository only;
    Contents and Pull requests read and write) and issues for other findings. The pipeline workflow
    has no `paths:` filter.
11. **Tests.** Synthetic media from PyAV `av==19.0.2`; the reference from the x86-64 Linux job; plane
    hashes on both routes (`VideoFrame.copyTo`, `NV12` split); forced fallback tests.

## Reason

1. One exact decoder per codec: the WASM decoder gave the pixels of x86-64 FFmpeg on 73,819 of 73,819
   frames; WebCodecs GPU and software outputs were bit-identical to the reference (study 9.2, 12.4).
2. The edit-list and seek rules follow the FFmpeg 9.0 source (`libavformat/mov.c`).
3. A required check of a workflow that path filters skip stays pending (GitHub documentation).

## Evidence

The H.264 study, part A: `research/h264_study/part_a/NOTES.md` sections 9 to 13, `RESULTS_TABLE.md`,
`app/mp4.mjs` and `app/wc.mjs`, branch `dom/h264-scrub-study`, commit 71caa2d0b. The legacy
inventory, branch `dom/research`, commit 7d8f8911b. The FFmpeg 9.0 source and the README in the
libav.js 6.10.9 tarball. The GitHub pages of spec section 10.7.

## Alternatives rejected

- `prefer-hardware`: 4:2:2 files failed to configure (study 9.2).
- A seek on the time stamp of frame k on the WASM route: with B-frames it can land after frame k.
- A heap limit in the build: it needs a change of the libav.js build files.

## Open work

None in [open-work.md](../open-work.md). The questions are in section 16 of the spec.
