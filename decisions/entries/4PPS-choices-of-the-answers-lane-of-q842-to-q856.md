# 4PPS — Choices of the agent that applies the answers Q842 to Q856

**Status:** proposed, 2026-11-26 (agent; applies Q850 to Q852 of
[ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md); commit to dom/answers-q842).

## Decision

The user did not decide these details.

1. **The camera label of the player** ([`player.md`](../../specs/player.md) 8.4, 5.8, item 40 of section 16).
   The reader finds the capture info JSON by the name `<recording_name>_info.json`, with `recording_name` of the
   manifest. It reads the file with `readWhole` and the limit of the manifest, 16 MiB. A take with no manifest, a
   missing file, a file that does not parse, or a null `os_index` or `os_name` gives the label `camera_label`, with
   no error and no warning.
2. **The handler of the take scheme** (`player.md` 4.3, 12.1, 16 item 40). `installTakeHandler` takes only
   `recordingsFolder`: with no list file in 6a, `pickedFoldersFile` has no use. T-PLAY-62 checks that a picked
   folder is refused again after a restart of the harness, and that no `picked-take-folders.json` exists.
3. **The test bounds of the 2 s watch** (`unix-capture.md` 4.10 and T-UNX-75). A suspended camera ends 2.0 to
   2.5 s after its last loop pass, and the third camera has no gap longer than 2.5 s: the old bounds minus 1 s.
   The fake-clock test of the limit (`test_f2_the_watch_limit_is_2_s`) trips nothing at 1.9 s and trips at 2.0 s.
4. **The words of 4.10.** The spec no longer says that the in-process rule "must come first". It says that this
   rule normally comes first, that no rule fixes the order, and that the review of ADR-Q2NY saw it win 24 of 24
   races at 2 s.
5. **The sentences of Q852.** `windows-capture.md` 15 says that no workflow raises the open-file limit (N14T
   item 2). `windows-capture.md` 16.1 says that T-CAP-91 stays a blocking test with no change (R394 item 3,
   N14T item 3), that the clock rule replaces the words of item 8 of ADR-B7YV (2SX2 item 1), and that the blocking
   half of the test under load keeps both cameras `ready` (2AQT). `unix-capture.md` 7 says that each new dependency
   needs a written reason (item 11 of ADR-22EJ).

## Reason

1. The manifest already names the take; a label is not worth an error, because `camera_label` is always there.
2. An option that nothing reads is dead code.
3. The bounds keep the margin of 0.5 s of the old test.
4. With equal limits the old reason no longer holds; the spec must not promise an order that the code does not
   fix.
5. Each sentence states a rule of an accepted entry that no spec stated, so that the entry can be absorbed.

## Open work

[open-work.md](../open-work.md)
