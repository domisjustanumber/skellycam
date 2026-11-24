# A56K — Choices of the v1 playback spec: route by codec to the WASM decoder, frame table and seek rules, locked play, decoder build in CI, Dependabot

**Status:** proposed, 2026-11-24 (agent; builds the rules of the owner in
[ADR-X5MZ](X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md) and his answers in
[ADR-8EBK](8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md)).

## Decision

The draft spec [`player-legacy.md`](../../specs/player-legacy.md), revision 2, and its test list
T-LEG-01 to T-LEG-63 (51 tests). Section 15 of the spec lists the choices of the agent. Section 16
gives the open questions Q694, Q699 and Q701 to Q716; a "yes" accepts the recommendation. The main
choices:

1. **Scope.** v1.0.25 and v1.0.31 to v1.8.2, the sample data and import folders; a v1 recording has
   `synchronized_videos/*.mp4`; a v2 alpha folder is refused; v0.1.0 is not refused and not supported.
2. **Time file.** `synchronized_videos/timestamps/<stem>_binary.npy` (`<f8`, 1-D, the camera's length).
   T_k is the mean over the cameras from the smallest first value, made non-decreasing. With none,
   the median header rate (from the frame time stamps) and `~` on the tile.
3. **Route by codec** (Q694 open). The MP4 sample entry decides: `mp4v` and H.264 go to the WASM
   decoder in phase 1; a GPU route for H.264 is a phase 2 decision; HEVC and other codecs are refused.
4. **Server route details beyond Q688.** The snapshot folders, the roots, a root check by path
   components, the identity check at each read, the CORS preflight and expose header, a token life of
   30 minutes with one re-open in the client, no log line per range request.
5. **Frames.** The frame index is the truth. A TypeScript MP4 reader gives the frame table: the frames
   with M ≤ CTS < M + D, time stamp CTS − M + E, as FFmpeg's `mov_fix_index` does; a cross-check with
   FFmpeg's demuxer at open. Seek: use a kept frame; continue only up to the next key frame; else seek
   on the time stamp of the key frame G itself (FFmpeg's `mov_seek_stream` searches decode times) and
   check the first packet; give out only the exact time stamp.
6. **Locked play.** k* = min(target, the newest ready frame of each live tile); a tile with a read
   error, a refusal, "decoder failed" or in a restart is not live; t does not stop.
7. **Worker.** One per tile; blocks of 256 KiB, 16 kept; at most 8 decoded frames in the worker and 8
   ahead in the page; any `RuntimeError` is fatal; restarts; two faults at one frame mark it damaged;
   "decoder failed" at the third fault in 60 s. No heap limit in the build; the tests check no growth.
8. **Build.** The recipe in `skellycam-ui/decoder/` (libav.js 6.10.9 exact, a one-stage `Dockerfile`
   with `emscripten/emsdk:6.0.8` by tag and digest, `build.sh`, `parts.json`). Parts: mov demuxer,
   `mpeg4` and `h264` decoders and parsers, with the components that `configure` and libav.js add
   (`h263` decoder, `iso_media`, `riffdec`, two bit-stream filters, the `data` and `file` protocols).
   CI builds twice and checks the licence flags, the component sets, `--disable-network`, the size, the
   pins and `license.js`. The decoder sits outside the `asar`; an unknown decoder file gives a warning.
9. **Dependabot.** `npm` and `docker` on `/skellycam-ui/decoder`, `github-actions` on `/`, weekly. A
   weekly workflow reports FFmpeg point releases, libav.js releases and CVEs (an issue in phase 1, a
   PR with Q704). The bump pipeline runs in a workflow with no `paths:` filter, with jobs skipped by
   `if:`, so that required checks never stay pending.
10. **Tests.** Synthetic media at test time with PyAV `av==19.0.2`; the reference from the x86-64 Linux
    job only; decoder timing on Linux and macOS from a certify check `player-legacy-decode` (Q708).

## Reason

1. Reliability comes first [ADR-X5MZ item 1]: one decoder for each v1 file gave the pixels of x86-64
   FFmpeg on 73,819 of 73,819 frames in 30 files (study section 12.4).
2. Six 720x1280 `mp4v` tiles: seek p50 about 36 ms and play with 0 differing refreshes (study 12.4).
3. The edit-list and seek rules follow the FFmpeg 9.0 source of the build (`libavformat/mov.c`).
4. A required check of a workflow that path filters skip stays pending and blocks merging (GitHub
   "Troubleshooting required status checks").

## Evidence

The H.264 study, part A: `research/h264_study/part_a/NOTES.md` sections 11 to 13, `RESULTS_TABLE.md`
and `app/mp4.mjs`, branch `dom/h264-scrub-study`, commit 71caa2d0b. The legacy inventory, branch
`dom/research`, commit 7d8f8911b. The FFmpeg 9.0 source and the README inside the libav.js 6.10.9 npm
tarball, read on 2026-11-24. The GitHub pages of section 10.7 of the spec.

## Alternatives rejected

- WebCodecs first for H.264 now: faster on a GPU, but a second route with OS-dependent decoders and
  no import sample (Q694 keeps phase 2 open).
- A seek on the time stamp of frame k: with B-frames it can land after frame k.
- A heap limit in the build: it needs a change of the libav.js build files.

## Open work

None in [open-work.md](../open-work.md). The questions are in section 16 of the spec.
