# WP77 — Choices of the player label and picked-folders lane

**Status:** absorbed into
[`specs/player.md#53-which-folders-open-l7-agent-6`](../../specs/player.md#53-which-folders-open-l7-agent-6),
[`specs/player.md#84-the-label-and-the-overlay-e6-agent-24`](../../specs/player.md#84-the-label-and-the-overlay-e6-agent-24),
[`specs/player.md#121-kinds-and-runners-agent-34`](../../specs/player.md#121-kinds-and-runners-agent-34),
[`specs/player.md#123-test-list`](../../specs/player.md#123-test-list),
2026-11-27 (commit to dom/answers-q929; was accepted, 2026-11-27 (user, Q945 of [ADR-318R](318R-decisions-of-the-user-on-q942-to-q955.md), except the part moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md)); was proposed,
2026-11-27 (agent, player lane of Q915 item 5 and Q919 of
[ADR-70J6](70J6-decisions-of-the-user-on-the-remaining-items-of-4pps.md); waits for the user)).

## Decision

The user decided the label rule and "no saved picked-folders file" (ADR-70J6). He did not decide these details.
[`player.md`](../../specs/player.md) 8.4 and 5.3 state them, with a link to this entry.

1. **When the reader reads the capture info.** Once, at the open, only when it uses the manifest (6.2), the
   manifest member `recording_name` is a string that is not empty and holds no `/` and no `\`, and
   `<recording_name>_info.json` is an entry of the snapshot at the root of the take folder. Else no read.
2. **The checks of the file.** A JSON object with `skellyfileformat` `capture_info`, the `take_uuid` of the take and
   an object `camera_configs`. No other check: the checks of SFF-803 (`key_origin`) belong to the full reader
   result of 6c (L2). A file that fails, is missing, is larger than 16 MiB or does not read gives `camera_label` on
   each camera.
3. **The member of a camera.** The member of `camera_configs` whose key is the `camera_key` of the sidecar, as
   SFF-803 links them. `device.os_index` must be a JSON integer from 0 to 2^53 − 1, and `device.os_name` a string
   with a character that is not white space; `os_name` shows as it is. Each other case (no member, no
   `camera_key`, the key `0` of a converted take, a null, absent or wrong value) gives that camera
   `camera_label`; the other cameras keep their labels.
4. **`camera_label`** is the value of the sidecar header, or the empty text for a refused file with none.
5. **No message.** A fallback gives no error, no `error` event and no warning, and the label changes no order,
   state, warning or K.
6. **Equal labels.** Each tile shows its label as it is, with no added text, in the order of `group_position`.
   `duplicate_label` comes only from the `camera_label` of the sidecars (SFF-870).
7. **FreeMoCap v1.** The rule does not apply: the v1 label is the file stem (T-LEG-09 of `player-legacy.md`).
8. **How long a pick lasts.** A reload, a navigation or a close of a window does not end a pick, and each window of
   the run can open the folder. (The end of a pick with the main process, and an old `picked-take-folders.json`,
   moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md) items 1 and 2 by Q945.)
9. **Real paths.** The pick keeps the real path at the pick time and never resolves it again: when the picked
   folder is later replaced by a link, the pick does not follow the link. The handler takes the real path of the
   recordings folder at each open, so a recordings folder that the backend makes later is allowed.
10. **Links.** The rule uses the real path of the asked folder. A link outside every allowed folder that points to
    a folder inside one opens: this is the code of today, and it gives access to no file outside.
11. **The v1 server route.** A pick adds no root to the route of `player-legacy.md` 4.2.
12. **Tests.** T-PLAY-83 and T-PLAY-84 (unit) test items 1 to 6; T-PLAY-85 (electron) tests items 8 and 10;
    T-PLAY-86 (electron) tests item 9. The harness sets the Electron `userData` folder to a folder of the test
    (`PLAYER_HARNESS_USER_DATA`). (The form of the "no list file" check of T-PLAY-62 and the picked-folders file that
    the harness lost moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md) item 3 by Q945.)
13. Moved to [ADR-K907](K907-the-open-part-of-adr-wp77-picks-across-runs.md) item 4 by Q945: it waits for Q946.
14. **Not limited.** `os_name` has no length limit in the label; a long name is cut only by the tile.

## Reason

1. The name comes from the manifest, so with no manifest there is no name; a path with a separator is not a root
   file of the take. One read at the open keeps the snapshot rule of 5.7.
2. A label is cosmetic: the reader checks only what it uses, and the other take's file (another `take_uuid`) must
   not name the cameras.
3. SFF-803 links by the key only. An empty name or a wrong type would show a broken label; `camera_label` is
   always there. skellycam never writes the key `0` (SFF-752).
4. to 6. The label is for people. Added text or a warning for it would be a feature nobody asked for.
7. A v1 folder has no capture info of this format.
8. The main process is shared by the windows, so a pick in its memory holds for each window of the run.
9. A pick that the main process resolves again at each open follows a link that someone puts in place of the
   folder later, so a folder that the user never picked would open. Resolving the recordings folder at each open
   follows the backend, which makes that folder.
10. This is the code of today; the spec did not state it.
11. The v1 route is in the Python server; it has its own list (Q688).
12. A user data folder of the test keeps each test away from the profile of the user.
13. See ADR-K907.
14. The review of the lane noted it; nothing asks for a limit.

## Alternatives rejected

- A scan of the folder for any `*_info.json`: it reads a file that the manifest does not name.
- `Camera <os_index> · ` with an empty name, or a number added to equal labels: a broken or new text.
- A pick that ends with its window: a reload would end it, and the user would pick the folder again.

## Open work

[open-work.md](../open-work.md)
