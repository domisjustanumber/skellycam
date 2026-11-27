# FHP6 — Choices of the recently opened take folders lane

**Status:** proposed, 2026-11-27 (agent, the lane of
[ADR-8J08](8J08-decisions-of-the-user-on-the-recently-opened-take-folders.md), with the fixes of its review; commit
to dom/player-recent; waits for the user).

## Decision

The user decided the feature (ADR-8J08). [`player.md`](../../specs/player.md) 5.3 and 5.10 state these details.

1. **Which dialog adds.** Only the folder dialog of the player ("Select recording folder", "Open the folder
   dialog"), through `fileSystem.selectDirectory({player: true})`. The other dialogs are picks for the run only.
2. **The dialog folder.** The top entry; a click that passes the check moves its entry to the top. With an empty
   list: the recordings folder when it is a folder, else the home folder. Never no `defaultPath`: Windows would open
   at its own remembered folder of the program. One list, so "Clear list" also clears the dialog folder.
3. **The time of the entry.** At the pick, before the read: a folder that does not play is also an entry.
4. **The file.** `{"version": 1, "folders": [...]}`, a 2-space indent, a final LF, at most 1 MiB, a regular file
   (a FIFO would block). A wrong file gives an empty list. An item that is not a string, is empty, is longer than
   32,767 UTF-16 code units, holds a NUL, is not absolute or starts with two slashes or backslashes is left out,
   then repeats, then all after the fifth. The two-slash rule is the only device rule; each other wrong path fails
   at the click. The read resolves and writes nothing; another `version` is replaced at the next change. A pick
   that fails the item rules (UNC) adds no entry.
5. **The write.** A `.tmp` file, then a rename; one write after the other; a failed write keeps the list in memory
   and logs one line with no path, with no message.
6. **The check.** Each error of `realpath` or `stat` (missing, no access, busy) is "gone", and the entry leaves the
   list, also a folder replaced by a link. A clear during the check wins: the click fails with "folder not
   allowed" and opens nothing.
7. **What a page can reach.** The calls `recent()`, `openRecent(folder)` and `clearRecent()`. The page asks by the
   path of an entry; the main process opens only the stored entry. It cannot tell a click from a script, so a page
   can reach the dialog picks of this run plus the at most 5 entries, each after its check. A path key, not an
   index: a list that changes between the show and the click cannot open another folder.
8. **"Clear list" ends no pick of the run.**
9. **The UI.** The folder name with the full path as the tooltip and in the accessible name; a group labelled
   "Recently Opened"; the message line is a live region; the focus goes to the folder button when the clicked entry
   or the section goes; names and paths are bidi-isolated for `ar`; a root stays a root (`D:\`). "folder not
   allowed" from a stale list shows no message. The texts in `en`, `es`, `zh-CN` and `ar` (Q948), not checked by
   a native speaker.
10. **The module.** `main/recent-folders.ts` holds the rules and the store (Node only); `take-scheme.ts` the
    channels. `TakeHandler` gets `recent()`, `dialogFolder()` and `recordPick(folder, {recent: true})`.
11. **Tests.** T-PLAY-87, 88 and 90 to 92 (unit), T-PLAY-89 and the new T-PLAY-62 (electron). The native dialog, the
    wiring of `electron/main/api.ts` and the UI section are checked by hand.
12. **A drive that is not connected.** Its entry leaves the list at the click (Q967 as written; Q987 asks the user).
13. **Earlier entries.** ADR-8J08 decides the question of
    [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md) (now rejected). The picks of the run stay as
    [ADR-WP77](WP77-choices-of-the-player-label-and-picked-folders-lane.md) says: not saved, ended by a restart.
    It also answers the sentence of [ADR-4D94](4D94-step-6a-choices-of-the-canvas-player.md) that the list file
    waits for step 6c; the rule of ADR-4D94 that the picks of the run are not saved stays, so no entry supersedes it.

## Reason

1. Q957 names the dialog of the player; the base recording folder is no folder the player played from.
2. "Recently Opened" names opens. Q967 asks that a clear also forgets the dialog folder; with no `defaultPath`
   it would not, on Windows.
3. Q966: "an entry is the folder picked in the dialog". Q988 asks the user.
4. The file is untrusted input. An absolute, non-UNC path is safe as a `defaultPath` and as a key; the check
   refuses each other wrong item. 1 MiB holds 5 items of the largest length.
5. A rename keeps the old file whole if the app ends during a write.
6. Each error means that the folder cannot be opened now; Q967 says it leaves the list. A clear is the later act.
7. Q965: the page asks by entry and cannot add a path.
8. Q967 names the list and the dialog folder only.
9. to 13. Q967 asks for a short message; a name alone does not tell two folders apart; the unit tests run with no
   Electron; the harness cannot drive the native dialog; a full supersede of ADR-4D94 would restate a rule that
   does not change.

## Alternatives rejected

- A check of each entry at the start: the message of Q967 would never show, and the start would touch each folder.
- Only ENOENT and ENOTDIR as "gone": an entry with no access would stay and fail at each click with no message.

## Open work

[open-work.md](../open-work.md)
