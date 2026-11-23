# 3B97 — Format sync: skellycam follows the format commit that holds F-1 to F-10

**Status:** absorbed into
[`specs/recorder.md#0-how-to-read-this-spec`](../../specs/recorder.md#0-how-to-read-this-spec),
[`specs/recorder.md#66-the-manifest`](../../specs/recorder.md#66-the-manifest),
[`specs/recorder.md#122-test-list`](../../specs/recorder.md#122-test-list),
[`specs/recorder.md#123-conformance-check-against-skellyfileformat`](../../specs/recorder.md#123-conformance-check-against-skellyfileformat),
[`specs/recorder.md#13-proposed-format-changes-one-list-for-the-recorder-and-the-player`](../../specs/recorder.md#13-proposed-format-changes-one-list-for-the-recorder-and-the-player),
[`specs/player.md#0-how-to-read-this-spec`](../../specs/player.md#0-how-to-read-this-spec),
[`specs/player.md#62-the-manifest`](../../specs/player.md#62-the-manifest),
[`specs/player.md#66-rows-the-row-crc-and-the-footer`](../../specs/player.md#66-rows-the-row-crc-and-the-footer),
[`specs/player.md#67-missing-rows-placeholders-and-the-short-file-m1-to-m5-m9`](../../specs/player.md#67-missing-rows-placeholders-and-the-short-file-m1-to-m5-m9),
[`specs/player.md#73-the-frame-choice-sff-783-e4-m9-agent-20-agent-21`](../../specs/player.md#73-the-frame-choice-sff-783-e4-m9-agent-20-agent-21),
[`specs/player.md#123-test-list`](../../specs/player.md#123-test-list),
2026-11-23 (commit to dom/format-sync; was accepted, 2026-11-21 (user; "yes" to each of the nine questions, items 2 and 4 to 10;
commit to dom/format-sync; was proposed, 2026-11-21 (an agent made these choices to bring the
recorder, the player, the specs and the test adapter in line with skellyfileformat commit
`c1028ef185be86f0ac6ccf7f9ac2ce76def13f2d`; branch `dom/format-sync`))).

## Decision

**Limit (ended 2026-11-23).** The format commit `c1028ef` was first only on the machine of the user,
and `recorder.yml` checks the format out by commit, so this branch had to wait for the push of the
format repository. On 2026-11-23 the user pushed the format `main` at
`24949df6c22093336c30b279c396ef593648de1e`, a child of `c1028ef`.

The format holds F-1 to F-10 since `c1028ef` (skellyfileformat ADR-6AT7, decided by the user).
skellyfileformat ADR-5B03 and ADR-76NN are accepted by the user (ADR-76NN in commit `24949df`). The
choices of the agent:

1. **The pin.** Each pin moves from `d67679a` to `24949df` (first to `c1028ef`): the workflow, `sff_expected.py`, the
   docstring of T-REC-37, `specs/recorder.md` and `specs/player.md`.
   [ADR-4K7V](4K7V-phase-6a-player-spec-and-test-list.md) is not changed.
2. **The test adapter.** `write_frame` gives each JPEG to the capture check `check_jpeg` before the
   recorder, as the program does, so the DHT insertion of F-3 is tested. `data` None gives a frame
   with `CAPTURE_ERROR`. `camera_stopped(index, reason)` gives a dead camera to `finish`. The adapter
   gets no reader function (`camera_lost_at`, `short_file_counts`): the reader of skellycam is the
   player, and T-REC-37 runs no test that uses `reader`.
3. **The expected results of T-REC-37.** `test_sft_712_jpeg_bytes[no_dht]`, `test_sft_730_lock_form`
   and `test_sft_771_missing_rows_and_placeholder` pass. The reasons "without audio, ... (F-1)" and
   "(F-6)" go. `test_sft_708_manifest` also needs `add_warning`.
4. **`stored_px`.** The size of the first block that is not a placeholder, else the mode size. The
   fallback to the size of a placeholder goes (SFF-728; ADR-5B03 item 5; ADR-76NN item 12). T-REC-23 gets case 4.
5. **The player refusal of SFF-759.** The player refuses a camera file (`invalid`, `bad_metadata`)
   when a row with byte fields follows a row with empty byte fields (ADR-76NN item 10). The
   other two refusals of that item were already in the reader. T-PLAY-82 tests the three refusals and
   a camera file with no block.
6. **The summary `missing`.** The player does not compare it with the `# end` line. It never reads
   `summary` and gives no `summary_stale` (player spec 6.13, L2). Step 6c does.
7. **The take warnings of the player** are the list of the player, not the reader result of SFF-887
   (SFF-895; ADR-5B03 item 7).
8. **One mark.** For a dead camera from frame N on, "camera lost at frame N" (SFF-895) is the text of
   the "no frame" mark of SFF-783.
9. **The `detail` of `camera_file_short`.** The player does not parse it and shows no value of it,
   although SFF-895 asks a reader to parse it.
10. **Section 13 of the recorder spec.** A table of the SFF numbers and the details replaces the
    proposed rule text. The heading stays, so that the links of
    [ADR-Z3Y7](Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md),
    [ADR-P98T](P98T-step-5a-choices-of-the-recorder-and-its-connection.md) and `historical.md` stay
    correct. The git history and skellyfileformat ADR-6AT7 keep the proposed text.

## Reason

- Items 1 to 3: T-REC-37 must run the tests of the pinned commit through each writer name that they
  use. In the program, the capture check runs before the recorder [ring 5.2].
- Item 4: the format text. The two values differ only when the layout is not the mode size.
- Item 5: without the rule, two readers can map rows to blocks in two ways.
- Items 6 to 9: the scope of the player (L2). A change of the scope is for step 6c.
- Item 10: two copies of one text can disagree.

## Consequences

- A later change of the format needs a new pin, and the expected results of T-REC-37 change in the
  same commit.

## Evidence

- The subset of T-REC-37 through `sff_adapter.py`, pytest 9.2.0, Windows: at `d67679a`, 6 pass, 19
  fail, 5 skip; at `c1028ef` with the old adapter, 7 pass, 21 fail, 5 skip; with the adapter of item
  2, 9 pass, 19 fail, 5 skip. With the audio removed (a scratch wrapper, not kept): 13 pass, 15 fail,
  5 skip; `test_sft_708` fails only on `add_warning`, `test_sft_735` only on audio.
- The player reader (Node 26.13.1) on G18 `take` and `no_block` of the format (a scratch script, not
  kept): the states, rows, `fit` and file warnings of the `.player.json` results; `deadFrom` 7, 8
  and 0, as SFT-773 expects.

## Alternatives rejected

- A Python reader in the adapter: no product uses it.
- A new heading for section 13: it breaks the links of decided entries.
- The placeholder size as `stored_px`: it differs from SFF-728.
