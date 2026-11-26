# 88HQ — Decisions of the user on Q842 to Q856

**Status:** accepted, 2026-11-26 (user; the coordinator asked the questions and relayed the answers; commit to
dom/answers-q842).

## Decision

The user answered in two messages on 2026-11-26. The first message: "Q845 - what impact will this have on GPU
acceleration of encode/decode of either JPEG or h.264? I seem to recall 4:2:0 and 4:2:2 not accelerating in the
same way. Otherwise agree to Q842-855". The second message: "agree to all, Q856 b". Thus each answer below accepts
the recommendation of its question, and Q856 takes option (b). Q857 to Q862 are questions of skellyspecs. That
repository records them.

1. **Q842.** Push `dom/integration` (e13105855) to the fork, with no PR. The supervisor did it.
2. **Q843.** Item 4 of [ADR-J1HD](J1HD-choices-of-the-control-read-check.md) is accepted: a model that the
   control-read check finds harmed pauses the 1 Hz read during a take on each build, not only on a build with no
   control monitor.
3. **Q844.** Items 1, 2, 3, 5 and 6 of ADR-J1HD are accepted as written: 30 s with the read on and 30 s with
   `SKELLYCAM_CONTROL_READ=0`; the pass rule with the gap limit of 100 ms; the first unit of each model, about
   60 s for each model; the local row `ok` or `harms`.
4. **Q845.** Items 1 to 4 of entry N72V of `dom/jpeg-encode-tests` are accepted as written: YUY2 before NV12, one
   INFO log line for each open, the main process does not refuse the request, and the take records the opened
   format. The order stays a change of one line. The JPEG lane changes the status of N72V on its branch.
5. **Q846.** The fallback to a raw mode gets no UI flag. The log line and the `capture_format` of the take are
   enough for now. The JPEG lane writes the spec sentence on `dom/jpeg-encode-tests`.
6. **Q847.** [ADR-TYH0](TYH0-choices-after-the-acceptance-of-the-v1-playback-spec.md) is accepted: the PR that
   removes the old routes also removes `SyncedVideoPlayer.tsx`, the video loading of `PlaybackContext.tsx` and the
   `stream_url` use of `RecordingBrowser.tsx`; `player-legacy-decode` is a `record-only` check of level `full`; it
   is `not-run` `no-ui` with no app page.
7. **Q848.** The texts of skellyspecs that tell of the conversion of old recordings name only skellysync as the
   converter.
8. **Q849.** Push `dom/nv12-capture-format` (7f67e16) of skellyspecs and merge it to its main now. The supervisor
   does it.
9. **Q850.** The main-process stall watch of [`unix-capture.md`](../../specs/unix-capture.md) 4.10 trips after
   2 s: item 14 of [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md) (accepted) wins
   over item 1 of [ADR-Q2NY](Q2NY-choices-of-code-step-2.md) (proposed, 3 s). The spec, the code and the tests
   change to 2 s.
10. **Q851.** [`player.md`](../../specs/player.md) 8.4 and 5.3 follow the label answer Q11 of
    [ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md) and the ruling of
    [ADR-4D94](4D94-step-6a-choices-of-the-canvas-player.md).
11. **Q852.** One small lane writes the missing spec sentence for each of N14T, R394, 2SX2 and 2AQT, and adds
    docstrings to the tests of [ADR-DC43](DC43-choices-of-fix-lane-5.md) (T-UNX-95, F1, T-UNX-74), so that the
    log can absorb those entries.
12. **Q853.** The next certify lane checks whether
    [ADR-8CP7](8CP7-certify-spec-draft-3-choices-of-the-agent.md) can be absorbed.
13. **Q854.** The next CI lane takes the uv version from the workflows and supersedes
    [ADR-7DE6](7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md) if they differ from it.
14. **Q855.** The JPEG-encode and the preview-4b code lanes start now, each on its test branch. They can run timed
    tests while the machine is idle. An independent review comes before each merge.
15. **Q856.** Option (b): the user adds a Bash permission rule that allows `git push` to his fork. The supervisor
    pushes after each yes of the user.

Items 2, 3 and 6 are in the specs that absorb ADR-J1HD and ADR-TYH0. Item 9 is in `unix-capture.md` 4.10 and
`windows-capture.md` 9.5. Items 10 and 11 are in `player.md`, `windows-capture.md` and the test docstrings.
Items 12 and 13 are in [open-work.md](../open-work.md). Items 1, 4, 5, 7, 8, 14 and 15 are actions, or rules of
another branch or repository.

## Reason

The user gave no reason other than the answers. The agent gave these with the questions: Q850 follows the earlier
decision of the user over a choice that he never accepted; Q843 holds because the harm comes from the requests,
whatever finds the changes.

## Consequences

- With the two limits at 2 s, the in-process rule of `windows-capture.md` 9.5 normally ends a camera with no
  frames first, but no rule fixes the order. When the watch wins, it kills the process with no restore and no clean
  finish of the files. The review of ADR-Q2NY saw the in-process rule win 24 of 24 races at these values.
- `player.md` 5.3 now differs from the code of 6a: `take-scheme.ts` still writes `picked-take-folders.json`
  ([open-work.md](../open-work.md)).

## Open work

[open-work.md](../open-work.md)
