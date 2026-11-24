# A56K — Choices of the v1 playback spec: route by codec to the WASM decoder, HTTP range path, one player, decoder build in CI, Dependabot

**Status:** proposed, 2026-11-24 (agent; builds the rules of the owner in
[ADR-X5MZ](X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md)).

## Decision

The draft spec [`player-legacy.md`](../../specs/player-legacy.md) and its test list T-LEG-01 to
T-LEG-63 (44 tests). Section 15 of the spec lists the 36 choices of the agent. Section 16 gives 21
questions for the owner; a "yes" to a question accepts its recommendation. The main choices:

1. **Scope.** FreeMoCap v1.0.25 to v1.8.2, the official sample data and v1 import folders. A v1
   recording is a folder with `synchronized_videos/*.mp4`; a v2 alpha folder is refused with a
   readable text; v0.x is not refused and not supported; no annotated videos (spec 1, 2).
2. **Time file.** `synchronized_videos/timestamps/<stem>_binary.npy`, parsed by the module (`<f8`,
   1-D, the length of the camera). With none, the median header rate and a `~` on the tile (spec 2).
3. **Route by codec** (Q694). The MP4 sample entry decides: `mp4v` and H.264 go to the WASM decoder;
   no WebCodecs route in this step; HEVC and each other codec are refused (spec 3).
4. **Data path** (Q688). A server route opens a folder below allowed roots under a token and serves
   original bytes by range, with the rules of `player.md` 5.4 to 5.6; the page decodes. The Electron
   take-scheme stays for the local app until the option B review (spec 4).
5. **One player** (Q685). v1 plays in the canvas player; a later PR removes the `<video>` player, the
   old video routes and the server transcode `browser_stream.py` (spec 5). This changes E2 and L5 of
   `player.md`.
6. **Frames.** The frame index is the truth: tile c shows frame k* of camera c. A TypeScript MP4 reader
   gives the frame table, cross-checked with FFmpeg's demuxer. Seeks land on the exact time stamp;
   the decoder continues only up to the next key frame. K is the smallest frame count. Locked play:
   all tiles show one frame number on each refresh (spec 6).
7. **Decoder in the page.** One module worker per tile; blocks of 256 KiB, 16 kept; 8 frames ahead;
   planes to the page; a restart after a crash, "decoder failed" after 3 in 60 s (spec 7, 8).
8. **Build.** The recipe in `skellycam-ui/decoder/` (`package.json` with `libav.js` 6.10.9 exact, a
   one-stage `Dockerfile` with `emscripten/emsdk:6.0.8` by tag and digest, `build.sh`, `parts.json`).
   Parts: `avformat`, `avcodec`, `demuxer-mp4`, `decoder-mpeg4`, `parser-mpeg4video`, `decoder-h264`,
   `parser-h264`. CI builds twice, checks `CONFIG_GPL 0`, `CONFIG_NONFREE 0`, `CONFIG_VERSION3 0` and
   the part sets, and caches by recipe hash. The outputs are not committed; the installer workflow
   builds them; they sit outside the `asar` so that a user can replace them (spec 9).
9. **Dependabot.** `npm` and `docker` on `/skellycam-ui/decoder`, `github-actions` on `/`, weekly. A
   weekly workflow reports FFmpeg point releases, libav.js releases and FFmpeg CVEs in one issue. A
   bump PR runs the build, the checks, the conformance test and the player tests on three systems, so
   that it is "review and merge" (spec 10). The npm entry of today has the directory `/`, where no
   `package.json` is.
10. **Test media.** `tools/make_legacy_media.py` makes `mp4v` and H.264 files and their frame hashes
    at test time with PyAV `av==19.0.2`; no media is committed; real v1 files come from a CI download
    of the sample data and from a folder on the owner's machine (spec 13).

## Reason

1. Reliability comes first [ADR-X5MZ item 1]: one decoder for each v1 file gives one code path and the
   pixels of x86-64 FFmpeg on 73,819 of 73,819 frames in 30 files (study section 12.4).
2. The study measured six 720x1280 `mp4v` tiles at a seek p50 of about 36 ms and play with 0 differing
   refreshes (study section 12.4).
3. Chromium cannot decode `mp4v`, so the `<video>` player plays no file that v1 writes (study 11.2).
4. A Dependabot PR gets a read-only token, so committed outputs would stop "review and merge".

## Evidence

The H.264 study, part A: `research/h264_study/part_a/NOTES.md` sections 11 to 13 and
`RESULTS_TABLE.md`, branch `dom/h264-scrub-study`, commit 71caa2d0b. The legacy inventory:
`research/skellycam_recording/docs/legacy_release_inventory_20261115.md`, branch `dom/research`,
commit 7d8f8911b. The Dependabot pages of section 10.6 of the spec, read on 2026-11-24.

## Alternatives rejected

- WebCodecs first for H.264 with the WASM decoder as the fallback: faster on a GPU, but a second
  route with OS-dependent decoders (question 1 of the spec keeps it open).
- Commit the built decoder: binaries in git history, and a Dependabot PR cannot update them.
- One HTTP path only, now: its performance for the new format is not measured.

## Open work

None in [open-work.md](../open-work.md). The questions are in section 16 of the spec.
