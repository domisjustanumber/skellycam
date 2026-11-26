# 4PPS — Choices of the agent that applies the answers Q842 to Q856

**Status:** proposed, 2026-11-26 (agent; applies Q850 to Q852 of
[ADR-88HQ](88HQ-decisions-of-the-user-on-q842-to-q856.md) and Q863 of
[ADR-3RJJ](3RJJ-decision-of-the-user-on-the-order-of-the-two-stall-rules.md); commit to dom/answers-q842).

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
3. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 3.
4. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 4.
5. **The sentences of Q852.** `windows-capture.md` 15 says that the workflow does not raise the open-file limit
   of its runner (N14T item 2). `windows-capture.md` 16.1 says that T-CAP-91 stays a blocking test with no change (R394 item 3,
   N14T item 3), that the clock rule replaces the words of item 8 of ADR-B7YV (2SX2 item 1), and that the blocking
   half of the test under load keeps both cameras `ready` (2AQT). `unix-capture.md` 7 says that each new dependency
   must be justified (item 11 of ADR-22EJ).
6. **The setting of the control read.** `windows-capture.md` 11.4 and 21.6 say that the product read of 11.4
   honours `SKELLYCAM_CONTROL_READ=0`, as the restore honours `SKELLYCAM_RESTORE_CONTROLS=0`, so that the off half
   of the check of ADR-J1HD item 1 has a product setting to use. It is not built.
7. **The time of the control-read check.** `certify.md` 16 says that its sums and run times leave out the 60 s for
   each model of `<label>:control-read:gaps`; the sums are not recomputed.
8. **The Windows OS key** (`certify.md` 11.2) is written from the code `current_os_key`: `platform.release()`, a
   space and `DisplayVersion` of the registry, `unknown` when it cannot be read.
9. Accepted by Q874 and moved to [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md) item 5.

## Reason

1. The manifest already names the take; a label is not worth an error, because `camera_label` is always there.
2. An option that nothing reads is dead code.
3. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
4. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
5. Each sentence states a rule of an accepted entry that no spec stated, so that the entry can be absorbed.
6. A setting that certify uses must be a setting that the product reads.
7. The new sums would change the run times that the user accepted; that is a question for the user.
8. The spec said `os.label`, but the code and ADR-DC43 item 4 use the release.
9. See [ADR-EQ3K](EQ3K-decisions-of-the-user-on-the-head-start-of-the-stall-watch.md).
## Open work

[open-work.md](../open-work.md)
