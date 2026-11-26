# X5MZ — Rules of the owner for the playback of FreeMoCap v1 recordings (v1 only, Q693 custom libav.js with Dependabot)

**Status:** accepted, 2026-11-24 (user; the coordinator relayed the words).

## Decision

The owner gave these rules on 2026-11-24. This entry records only his words. The draft spec
[`player-legacy.md`](../../specs/player-legacy.md) applies them. The choices of the agent in that
spec are in [ADR-A56K](A56K-choices-of-the-v1-playback-spec.md) (proposed), not here.

1. **Goals.** "Reliable playback is the #1 goal, minimising seek time is #2 goal."
2. **No conversion.** "old recordings must not be converted - you gotta play them as-is."
3. **UI on another machine.** "I'd like to maintain the ability for the UI to run on a separte
   machine to the server, so avoiding uncompressed frames on the http link is probably necessary."
4. **No server decode.** "I do not want to do server-side decode." There is no fallback to it.
5. **Only v1.** "we do not need to maintain compatibility with any v2 builds - only v1." This replaces
   his earlier words "The goal is to support all v1 onwards versions".
6. **Q693.** "yes, lets go with custom libav.js. This work must also include suitable dependabot
   scripts to monitor upstream repos and trigger build and pr tests so it is minimal work to keep our
   custom build up to date."
7. **Standing rules** (as the coordinator listed them): exact version pins everywhere (`==` for
   Python, exact npm versions, CI actions by full SHA, toolchain images by an exact tag or digest);
   spec and tests before code; LF line endings; no camera recordings or frames committed (a test
   media file needs a decision); other systems are tested only through the certify process or CI.

## Reason

1. The H.264 study, part A (`research/h264_study/part_a/NOTES.md` sections 11 to 13, branch
   `dom/h264-scrub-study`, commit 71caa2d0b) showed that Chromium has no decoder for the MPEG-4 Part 2
   (`mp4v`) files that FreeMoCap v1 writes, and that a custom LGPL variant of libav.js 6.10.9 (FFmpeg
   9.0) decoded each frame of each test file with the pixels of x86-64 FFmpeg. The owner chose that
   route (Q693).
2. The words of the owner are the reasons of items 1 to 5.

## Open work

None in [open-work.md](../open-work.md). The open questions of the draft spec are in its section 16.
