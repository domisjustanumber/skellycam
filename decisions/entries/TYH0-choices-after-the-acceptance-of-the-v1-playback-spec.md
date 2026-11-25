# TYH0 — Choices after the acceptance of the v1 playback spec: the code that goes with the old routes, and the certify row

**Status:** proposed, 2026-11-25 (agent; applies Q800 and Q803 of
[ADR-2Z2D](2Z2D-answers-of-the-owner-q800-to-q803-and-acceptance-of-the-v1-playback-spec.md)).

## Decision

Items 53 and 54 of section 15 of [`player-legacy.md`](../../specs/player-legacy.md):

1. **The code that goes with the old routes (5.2).** Q800 A removes the three routes, their URLs and
   the `<video>` branch in step 6c part 1. The same PR also removes the code that only these parts
   use: `SyncedVideoPlayer.tsx`, the video loading of `PlaybackContext.tsx` and the `stream_url` use
   of `RecordingBrowser.tsx`. The server transcode and the sync warning stay for the later PR of
   Q685. T-LEG-77 also checks that no UI file names `SyncedVideoPlayer`.
2. **The certify row (`specs/certify.md` 3.1, 3.6.2, 15, 17).** `player-legacy-decode` is a check
   of level `full`. Its row is `record-only`, with the `module` of the pipeline item, so it blocks no
   gate. Its values are in `details.player_legacy_decode`. With no app page it is `not-run` with the
   new reason `no-ui`. Before the code exists, its name is in `details.not_built`. Test T-CERT-135.

## Reason

1. A removed URL with a caller left is broken code.
2. The values of the check are recorded, not judged (spec 10.5), so the row cannot be a gate.
3. The check runs in the page of the app; a certify run from Python alone has no page.

## Alternatives rejected

- Keep `SyncedVideoPlayer.tsx` until the later PR: no caller would use it.
- Level `quick`: two plays of 30 s do not fit the 30 s budget of a quick run.
