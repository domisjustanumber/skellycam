# 5FBS — Fixes of the 6a code review

**Status:** proposed, 2026-11-20 (agent; waits for the user).

## Decision

An independent review of the 6a player code
([ADR-1ACK](1ACK-corrections-and-choices-of-the-6a-player-code.md)) gave the findings below. The
agent checked each one and changed [`specs/player.md`](../../specs/player.md) and the code. The new
tests are T-PLAY-74 to T-PLAY-81.

Security (sections 5.3 to 5.6):

1. The handler serves no file with more than one hard link: not in the snapshot, and not at the
   first read. A hard link can name a file outside the take (T-PLAY-77).
2. The handler refuses a relative, UNC or device path before any file system call (T-PLAY-78).
   Consequence: a take on a network share does not open in 6a, also after a dialog pick.
3. When the window navigated or closed during an open, the open fails and no token is made. No test:
   the page that would hold the token is gone.
4. The handler reads each response body in pieces of at most 1 MiB, from the file handle
   (T-PLAY-79).
5. A failed `openTake` closes its files (T-PLAY-75).
6. `setReadFault` stays in the handler interface. ADR-4MJ4 names it, the harness uses it, and only
   code in the main process can call it.

Data shown (sections 6.10 and 10):

7. A block that `ImageDecoder` does not decode: the tile keeps its last image with "damaged at
   frame N" for that frame only, and the next frames show (T-PLAY-74). This is a choice for the
   user: the spec had no rule. Before, the tile showed "read error" for the rest of the session.
8. The loading message also counts a tile that got a mark or black (T-PLAY-80).
9. A take of the new format in a folder that the handler refuses goes to no player. The recording
   browser shows a message and a button that opens the folder dialog (T-PLAY-81 for the route; the
   message is not tested). L7 does not change.

Format (section 6.4):

10. A pair whose `take_uuid` does not read is in no take and does not count (SFF-865, SFF-889,
    T-PLAY-76). This replaces item 8 of ADR-1ACK. The `header_uuid_dashes` case of T-PLAY-08 and
    its spec row now expect the same: 3 cameras and `incomplete_take`.

CI (`.github/workflows/player.yml`):

11. The Linux job does not install a pinned `xvfb`. The `ubuntu-24.04` runner image has it
    (2:21.1.12-1ubuntu1.9 in the first run), and the step prints and checks the installed version.
    An apt pin in `noble-updates` goes away at the next update and would break CI. The image label
    is the pin. This is a choice against the rule "pin each toolchain to one exact version", for the
    user. The test steps run only when `npm ci` passed.

Minor: the sidecar reader no longer decodes the whole file into an unused string; the decoder closes
the first frame when the `VideoFrame` constructor fails.

## Reason

Each finding was checked against the code and the spec. Each fix is the smallest that the spec, the
format spec and L7 allow.

## Open work

For the user, not changed: the token on a second open of the same folder (ADR-1ACK item 12); HTTP
500 for a failed read (ADR-1ACK item 11); each dialog pick is kept with no way to remove it (ADR-1ACK
item 13); a read that starts while a decode runs, for 50 frames/s in a scrub (a change of section
7.5); a network share (UNC path) does not open in 6a, also when the user picked it in the folder
dialog, because UNC paths are refused before any file system call (the alternative: allow a UNC path
only when the main process recorded it from the dialog). See [open-work.md](../open-work.md).
