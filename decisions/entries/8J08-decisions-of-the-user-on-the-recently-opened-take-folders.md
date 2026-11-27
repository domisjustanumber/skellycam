# 8J08 — Decisions of the user on the recently opened take folders (Q946, Q957, Q959, Q965 to Q968)

**Status:** absorbed into [`specs/player.md#53-which-folders-open-l7-agent-6`](../../specs/player.md#53-which-folders-open-l7-agent-6),
[`specs/player.md#510-recently-opened-folders-agent-41`](../../specs/player.md#510-recently-opened-folders-agent-41),
2026-11-27 (commit to dom/player-recent; was accepted, 2026-11-27 (user, Q946, Q957, Q959, Q965 to Q968; the
supervisor asked the questions and relayed the answers; commit to dom/player-recent)).

## Decision

The words of the user, Q946 and Q957: "the player should remember the last folder it played from"; "yes, and maybe
a 5 most recent folders rememebered in a Recently Opened section, with a UI option to clear the list".

1. **Q946, Q957.** The player remembers the folders that the user opened in it, across restarts. A section
   "Recently Opened" shows the 5 most recent folders. A UI control clears the list.
2. **Q957.** The folder dialog of the player opens at the last folder picked.
3. **Q959.** The app does not open the last take again by itself at its start.
4. **Q965.** A click on an entry of "Recently Opened" opens that folder directly, with no folder dialog. Only the
   main process reads or writes the list. Each entry is the real path stored at the pick. At the click the main
   process checks the path again: it exists, and it still resolves to the same real path. Only then can the page
   read the folder. The page can never add a path to the list.
5. **Q966.** An entry is the folder picked in the dialog. The list is most recent first. A repeat pick moves the
   folder to the top. The sixth folder drops off.
6. **Q967.** "Clear list" empties the list. It also forgets where the dialog opens. A recent folder that no longer
   exists gives a short message at the click, and it leaves the list.
7. **Q968.** The list is one file in the user data folder of the app: `recent-take-folders.json`. An old
   `picked-take-folders.json` stays not read and not deleted.

The details that the user did not decide, and the earlier entries that this decides, are in
[ADR-FHP6](FHP6-choices-of-the-recently-opened-take-folders-lane.md) (proposed).

## Reason

The words of the user, above. A list in the main process with a check at each click keeps the rule of U1 (the page
cannot add a folder) and the rule of ADR-WP77 item 9 (a pick does not follow a link put in its place later).

## Open work

[open-work.md](../open-work.md)
