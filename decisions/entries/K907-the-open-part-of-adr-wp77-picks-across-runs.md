# K907 — The open part of ADR-WP77: picks across runs and the list file

**Status:** proposed, 2026-11-27 (agent, player lane; moved out of
[ADR-WP77](WP77-choices-of-the-player-label-and-picked-folders-lane.md) by the answers lane, Q945 of
[ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md); waits for Q946).

## Decision

The user accepted ADR-WP77 except item 13 and each sentence that says that a pick is never remembered across runs
(Q945). Those choices of the player lane are here, with their text of ADR-WP77. `player.md` 5.3 and the T-PLAY-62
row state them as the code of today. They wait for Q946: the user wants the player to remember the last folder it
played from, and asked what `picked-take-folders.json` does.

1. **(WP77 item 8.)** A pick lasts until the main process ends. A restart of the app ends every pick.
2. **(WP77 item 8.)** A `picked-take-folders.json` of an earlier build is not read and not deleted.
3. **(WP77 item 12.)** T-PLAY-62 checks "no list file" as: from before the page calls to after the restart, no file
   below the temporary folder of the test is added or changed outside the user data folder, and no file below it
   holds the path of the pick. The harness lost its picked-folders file (`PLAYER_HARNESS_PICKED`, `Harness.picked`).
4. **(WP77 item 13.) A list file later?** `player.md` 5.3 states only what is true now: no list file is read or
   written. U1 asked for picks remembered across restarts; ADR-4D94 said that the list file waits for step 6c; Q919
   says "no saved picked-folders file". The lane recommended: never, unless the user asks for remembered folders
   later. Q946 now asks for one remembered folder, so this item waits for its follow-up questions.

## Reason

1. "No saved file" (Q919, [ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md)) leaves the
   memory of the main process as the only store.
2. A delete of the old file would be a write to the user data that nobody asked for.
3. A fixed file name in the check would pass for any other file name. Chromium writes its own files in the user data
   folder during a run, so there the check looks for the path of the pick, not for a changed file.
4. The answers do not agree on the future; only the user can choose.

## Alternatives rejected

- A delete of an old `picked-take-folders.json` at the start: a disk change that nobody asked for.

## Open work

[open-work.md](../open-work.md)
