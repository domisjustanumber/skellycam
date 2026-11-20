# C6DE — Stall as no progress, the two limits as starting values, no FAT disk

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor; commit to dom/recorder).

## Decision

The user decided three points after the review of the 5a code. They change
[`specs/recorder.md`](../../specs/recorder.md) by dated notes in sections 1.5, 4.2, 4.3, 5.3, 8.1,
10, 11, 15.1, 15.3 and 18. The spec cites them as [C6DE D1] to [C6DE D3].

- **D1.** A stall is no progress of the writer for the stall limit, not a total time. At the end of a
  take (`end`, and the wait of the main process for each camera), a camera whose writer still writes,
  however slowly, is left to finish. Only a writer with no progress for the stall limit is a disk
  stall: state `failed`, process ended, short file (C6). The same rule applies during the take: a
  `give` that waits on a full queue raises `RecorderStalled` when the writer made no progress for the
  stall limit. The margin of 5 s of the main process stays on top.
- **D2.** The queue of 3 s and the stall limit of 10 s stay as starting values.
- **D3.** A take is refused at its start when the file system of the take folder has a file size
  limit of 4 GiB (FAT). exFAT has no such limit and is accepted. The record start gives HTTP 422
  with a text that names the file system and the limit. When the file system cannot be found, the
  take starts and a warning is logged.

How the code applies them:

- Progress (D1) is a write call on the MKV or the CSV file object, or an `os.fsync` call, that
  returned. The writer thread records the time of each one. This is the smallest sound definition:
  each return means that the OS took bytes or forced them to disk. A `write` or `fsync` call that
  has not returned has not given the disk anything that the writer can count, and a disk that stops
  holds the writer inside such a call, so it cannot count as progress. CPU work (the mux, the SOF
  parse) is not progress, because it does not show that the disk takes data.
- `give` and `end` wait in blocking calls. Each wait ends when the stall limit has passed since the
  start of the wait or since the last progress, whichever is later. Thus a `give` waits at least
  the stall limit before it raises.
- File systems (D3), with the standard library only: on Windows, `GetVolumePathNameW` and
  `GetVolumeInformationW` through `ctypes` (names `FAT`, `FAT32`, `exFAT`, `NTFS`, `ReFS`); on
  Linux, the mount point of the longest prefix in `/proc/self/mountinfo` (types `vfat`, `msdos`,
  `exfat`, `ext4`, ...); on macOS, `f_fstypename` of `statfs` through `ctypes` (`msdos`, `exfat`,
  `apfs`, `hfs`). Refused: `fat`, `fat12`, `fat16`, `fat32`, `vfat`, `msdos`, `umsdos` (any case).
  A FUSE mount (`fuseblk`) is not refused, because its file system is not known.
- `start_take` raises the refusal as `ValueError`. The connection commit gives it as HTTP 422
  (spec section 10 item 13).

## Reason

- D1: a slow disk that keeps up most of the time must not end a take, and must not mark a healthy
  camera `failed` at the stop. Only a disk that stops is an error.
- D2: [ADR-8RES](8RES-r11-measurements-of-the-5a-recorder.md) supports 3 s on one NVMe drive only.
  Nothing measured can choose 10 s.
- D3: one camera at 1080p writes 4 GiB in minutes. A FAT disk would end each camera file there.

## Consequences

- `end` has no fixed time limit while the writer makes progress. The main process needs the
  progress time of each camera to apply its margin; the connection commit sends it.
- The Linux and macOS detection was not run on those systems (macOS is not verified at all).

## Open work

See [open-work.md](../open-work.md).
