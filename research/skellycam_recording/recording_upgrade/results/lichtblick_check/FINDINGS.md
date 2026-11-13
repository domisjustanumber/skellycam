# Lichtblick desk test (2026-11-13)

Provenance: a sub-agent ran this on 2026-11-13. The main session checked the frame-check counts and the blocked third-party request in `sum_up.json` and `sum_mrk.json` before saving. [M] = measured, [I] = inferred.

| | Upstream | mrkbac |
|---|---|---|
| Repo and revision | `lichtblick-suite/lichtblick` v1.30.0 (`fcfc7d559d8e76db36c9730e78049a60f976c2d2`) | `mrkbac/lichtblick` at `70f5900b7a9ecc9b2b223a955615e1abd6220245` (PR #116 Audio panel) |
| Node | 24.15.0 | 26.13.1 (portable) |
| Package manager | yarn 4.17.0 | pnpm 10.34.9 |
| Install + web build | 42 s + 28 s | 72 s + 37 s |

The two web builds were served from localhost and driven with Playwright 1.60.0 (Chromium 148.0.7778.96, headless). The browser blocked every request not going to 127.0.0.1 and used a fake audio sink (no real audio output).

Test take (`make_take.py`): two camera MCAPs and one mic MCAP of 30 s.
- Cameras: `foxglove.CompressedImage` JPEG, 640×360 at 30 fps. Each frame carries its number as a barcode and shows a white flash at each whole second.
- Mic: `foxglove.CompressedAudio` Opus 20 ms with a click at each whole second, plus a `foxglove.RawAudio` `pcm-s16` control file.
- All files share one synthetic clock. They opened as one source with `?ds=remote-file&ds.url=a.mcap,b.mcap,c.mcap`.

Scripts: `scripts/lichtblick_check/` (`make_take.py`, `serve.py`, `instrument.js`, `check_lichtblick.py`, `analyse.py`, `channel_metadata.py`).

## Short answer

- **Lichtblick opens several MCAP files as one timeline**, in both builds [M].
- **Images are correct in both builds**: 37/37 frame-versus-playhead checks in each of the 5 sessions. The checks covered paused, after seeks, playing at 1x, 0.5x and 2x, and after pause and resume [M]. While playing, a new frame is drawn about 35–75 ms after the playhead text passes its time [M].
- **Upstream v1.30.0 has no audio playback.** Raw Messages shows the audio messages [M].
- **mrkbac Audio panel with PCM (`RawAudio pcm-s16`)**: auto-selected, and plays at every speed, across pause and resume and after a seek [M].
- **mrkbac Audio panel with Opus (`CompressedAudio`)** [M]:
  - not auto-selected; the topic must be typed into the panel settings;
  - plays correctly at 1x, even with its "16 kHz" default (Chrome outputs 48 kHz anyway; the label is wrong);
  - **breaks at 0.5x, at 2x, and after pause and resume** until the next seek.
- **The mrkbac build calls `https://licht-server.marko.im/v1/me` on load** [M]. Its build bakes in a default `API_URL` (`packages/suite-base/rspack.ts:212`). This is a privacy leak to a third party unless the build runs offline or is rebuilt with `API_URL` changed.
- **Audio lag behind the playhead at 1x** (mrkbac) [M]: 73–152 ms on the audio clock, and 139–220 ms including the fake sink's 64 ms output latency. This roughly confirms the panel's 200 ms jitter buffer. A real device will differ.

## Details

| Check | Upstream v1.30.0 | mrkbac |
|---|---|---|
| Both cameras in Image panels | yes | yes |
| Frame matches playhead (paused, seeks, 1x/0.5x/2x, pause/resume) | 37/37 per session | 37/37 per session |
| Requests outside localhost | none | `licht-server.marko.im` (blocked) |
| Audio topic | Raw Messages only | Audio panel |
| Metadata records and channel metadata shown | not anywhere found. By code, Metadata reaches only extension panels [I] | yes: the Data Source Info panel has Metadata and Channels tabs, showing the metadata record and the mic channel's `sample_rate`, `channels`, `pre_skip` and `opus_head` |
| Console errors | none | only the blocked request |

Notes on the mrkbac Audio panel with Opus [M]:
- **0.5x**: about 10–16 chunks played in 9.5 s, against about 235 for PCM, so mostly silent.
- **2x**: chunks are scheduled 1–4 s ahead and then cut.
- **Cause**: the decoder's input timestamps step 10 ms (2x) or about 37 ms (0.5x), but Chrome rewrites the output timestamps from the sample count (20 ms steps), and the panel schedules from those. The measurement is [M]; the cause is [I].
- **After pause and resume**: 17 chunks in 4 s, against 287 for PCM. Playback recovers after a seek. Likely cause: a resume does not reset the decoder [I].
- **Pre-skip**: the panel ignores it. The test file's `log_time` already put the first packet 6.5 ms early (the Q14 convention), so the clicks line up. At 1x, the Opus and PCM offsets differ by less than the jitter.

## Other problems

- In both builds, clicking the playback time field pauses playback. Seeking while playing has to use the slider [M].
- mrkbac names the whole source after the last file opened, but lists all files in the File tab [M].

## Not tested

- Real audio output; "plays correctly" means decoded and scheduled at the right rate and time, not listened to.
- Desktop/Electron builds, the file picker and drag-and-drop, and upstream PR #1301.
- Offsets are measured against the playhead text, which may itself lag the internal player time [I].
- To read the flash pixels, the test forced `preserveDrawingBuffer` on WebGL.
