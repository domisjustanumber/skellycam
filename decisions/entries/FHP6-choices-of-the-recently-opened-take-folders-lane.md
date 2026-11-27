# FHP6 — Choices of the recently opened take folders lane

**Status:** proposed, 2026-11-27 (agent, the lane of
[ADR-8J08](8J08-decisions-of-the-user-on-the-recently-opened-take-folders.md); commit to dom/player-recent; waits
for the user).

## Decision

The user decided the feature (ADR-8J08). He did not decide these details.
[`player.md`](../../specs/player.md) 5.10 states them.

1. **Which dialog adds an entry.** Only the folder dialog of the player: the buttons "Select recording folder" and
   "Open the folder dialog" of the recording browser. They call `fileSystem.selectDirectory({player: true})`. The
   other dialogs of the app (the base recording folder, the video folder of the menu) are picks for the run only
   (5.3), add no entry and do not open at the last pick.
2. **A click is an open.** A click that passes the check moves its entry to the top. The dialog opens at the top
   entry. There is one list and no separate "last folder" value, so "Clear list" also clears the dialog folder.
3. **The time of the entry.** A pick adds its entry at the pick, before the player reads the folder. A folder that
   does not play (for example a folder of takes: the player treats a pick as one take folder) is also an entry.
4. **A pick that is no valid entry.** A pick whose real path fails the item rules of the file (for example a UNC
   path, which the handler refuses anyway, 5.3) is a pick for the run and adds no entry. Thus the list holds only
   paths that the read of the file accepts.
5. **The file.** `{"version": 1, "folders": [...]}`, JSON with a 2-space indent and a final LF. The read accepts
   at most 1 MiB. A file that fails the object rules gives an empty list. An item that is not a string, is empty,
   is longer than 32,767 UTF-16 code units, holds a NUL, is not absolute, or starts with two slashes or
   backslashes is left out; a repeat (the same-path rule of 5.3) is left out; then the first 5 stay. The read
   resolves no path and writes nothing. A file of another `version` gives an empty list, and the next change
   replaces it.
6. **The write.** The whole file after each change: a temporary file `recent-take-folders.json.tmp` in the same
   folder, then a rename. Writes run one after the other. A failed write keeps the list in memory and logs one line
   with no path. No message to the user.
7. **A folder replaced by a link.** At the click this is the same as a folder that no longer exists: the same
   message, and the entry leaves the list. Its real path is no longer the stored path.
8. **"Clear list" ends no pick of the run.** A folder of the list that was opened in this run stays readable until
   the app ends, as each pick of 5.3.
9. **The IPC.** Three calls of the bridge of 4.3, on three new channels of `TAKE_CHANNELS`: `recent()`,
   `openRecent(folder)` and `clearRecent()`. The page asks by the path of an entry that `recent()` gave. The main
   process uses only the stored entry with an equal path. A path that is no entry fails with "folder not allowed"
   and changes nothing. A key by path, not by index: a list that changes between the show and the click cannot
   open another folder.
10. **The page sees the paths of the list.** The section shows the folder name, with the full path as its tooltip.
    `selectDirectory` gives the page the path of a pick today too.
11. **The message.** "This folder no longer exists or was moved. It was removed from Recently Opened." In `en`,
    `es`, `zh-CN` and `ar` (Q948 of ADR-318R of `dom/answers-q929`), not checked by a native speaker; the other
    locales fall back to English. The section title "Recently Opened" and the button "Clear list" are in the same
    four locales.
12. **The module.** The rules of the list and of the file are pure functions in `main/recent-folders.ts`
    (Node only, no `electron`). `take-scheme.ts` holds the store, the file and the channels. `TakeHandler` gets
    `recent()` and `recordPick(folder, {recent: true})`. `installTakeHandler` keeps one option,
    `recordingsFolder`: the file path comes from `app.getPath('userData')`, which the harness sets (12.1).
13. **Tests.** T-PLAY-87 (unit: the list and the file), T-PLAY-88 (unit: the check at the click, with real folders
    and a junction or a symbolic link), T-PLAY-89 (electron: across a restart). T-PLAY-62 checks the new rule:
    a pick of the player dialog is refused again after a restart until a click, the only file that holds its path
    is `recent-take-folders.json`, and the page calls add no entry. T-PLAY-85 is unchanged. The harness hook
    `recordPick` passes the second argument. The `defaultPath` of the native dialog is checked by hand.
14. **An entry on a drive that is not connected.** At the click it does not exist, so it leaves the list (Q967 as
    written).

## Reason

1. Q957 names "the folder dialog" of the player. The base recording folder is no folder the player played from.
2. "Recently Opened" names opens, not only dialog picks. One list is the smallest store, and Q967 asks that a
   clear also forgets the dialog folder.
3. Q966: "an entry is the folder picked in the dialog".
4. An entry that the next read leaves out would show once and then go.
5. The file is untrusted input. An absolute, non-UNC path is safe as a `defaultPath` and as a key; the click
   check refuses every other wrong item. 1 MiB holds 5 items of the largest length.
6. A rename keeps the old file whole if the app ends during a write.
7. The check of Q965 fails for both.
8. Q967 names the list and the dialog folder only. A pick for the run is in memory and ends with the app.
9. Q965: the page asks by entry; the main process opens only a stored entry.
10. A name alone does not tell two folders with one name apart.
11. to 14. Q967 asks for a short message and makes no exception; the unit tests run under Node with no Electron;
    the harness cannot drive the native dialog.

## Alternatives rejected

- A check of each entry at the start, to drop missing folders: the message of Q967 would never show, and the start
  would touch each folder, also on a slow or a network drive.

## Open work

[open-work.md](../open-work.md)
