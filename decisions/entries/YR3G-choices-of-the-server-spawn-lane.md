# YR3G — Choices of the server spawn lane

**Status:** proposed, 2026-11-27 (agent: the UI messages lane on `dom/server-spawn`, a fault found in
[ADR-590X](590X-choices-of-the-ui-messages-lane.md) and confirmed by a review run).

## Decision

The Electron app started the server with `exec` and a `maxBuffer` of 100 MiB. Node then killed the child when its
output passed that size. That can end a take early (Linux, macOS) or leave an orphan server that records with no UI
(Windows). [`recorder.md`](../../specs/recorder.md) 9.3 states the rules. These choices are the lane's:

1. **`spawn` with no shell.** The same path, no arguments, the same working folder and a copy of the same
   environment. A path is no longer read by a shell (`%`, `$`, a backtick or `"` in a path).
2. **stdout to the null device (`'ignore'`).** Nobody read it before: `exec` had no callback, and the app wrote no
   server output to its log. A null device cannot fill or block. The app keeps no copy.
3. **stderr: a pipe, read at all times, with only its last 4096 characters kept** (the port-in-use rule of 9.2).
4. **stdin stays a pipe**, as with `exec`.
5. **No kill anywhere.** The app had none, and gets none.
6. **A path that cannot start fails at the start** (no PID), where the shell before ended at once with an error
   code. The existing retry of the renderer then tries the found candidate. On Windows a path that is not an
   executable image (`.bat`, `.cmd`, `.py`, picked through the "All Files" filter) no longer starts: `spawn` throws
   at once (EINVAL for `.cmd`, EFTYPE for `.py` on Node 26.13.1) and the user sees "Start failed: spawn EINVAL".
   Through `cmd.exe` such a path started.
7. **The test** starts a real Node child that writes 105 MiB to each stream. It is in `test:player:unit` (CI). It
   takes about one second.

## Reason

No output size may stop a recording or detach the server from the app. `spawn` is the smallest change that has no
output limit, and the null device is the smallest drain for output that nobody reads.

## Consequences

- On Windows the PID in the connection menu is now the PID of the server, not of `cmd.exe`.
- The server output still goes to no log of the app. Its own log file (`skellylogs`) is unchanged.
- Questions for the user (a yes accepts each recommendation): (a) Items 1 to 7 as written? (b) The app keeps
  dropping stdout, as before (no copy in the log of the app)? (c) The user tries the packaged app on Windows by
  hand (start, a take, quit) before a merge?

## Open work

See [open-work.md](../open-work.md).
