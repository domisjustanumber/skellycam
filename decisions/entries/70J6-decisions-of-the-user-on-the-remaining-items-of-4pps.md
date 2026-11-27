# 70J6 — Decisions of the user on the remaining items of ADR-4PPS (Q919)

**Status:** absorbed into [`specs/player.md#43-how-a-host-mounts-the-module-agent-3`](../../specs/player.md#43-how-a-host-mounts-the-module-agent-3),
[`specs/player.md#53-which-folders-open-l7-agent-6`](../../specs/player.md#53-which-folders-open-l7-agent-6),
[`specs/player.md#58-what-the-reader-reads`](../../specs/player.md#58-what-the-reader-reads),
[`specs/player.md#84-the-label-and-the-overlay-e6-agent-24`](../../specs/player.md#84-the-label-and-the-overlay-e6-agent-24),
[`specs/player.md#123-test-list`](../../specs/player.md#123-test-list),
[`specs/windows-capture.md#114-read-back-and-current-values-d20-d30`](../../specs/windows-capture.md#114-read-back-and-current-values-d20-d30),
[`specs/windows-capture.md#216-control-changes-by-other-processes-q768-q784-q797`](../../specs/windows-capture.md#216-control-changes-by-other-processes-q768-q784-q797),
[`specs/certify.md#112-the-data-file-u`](../../specs/certify.md#112-the-data-file-u),
2026-11-27 (commit to dom/player-label; was accepted, 2026-11-27 (user, Q919; the coordinator asked the question and
relayed the answer; commit to dom/player-label)).

## Decision

The user wrote on 2026-11-27: "agree to all" (Q910 to Q921). Q919 reads: "the remaining ADR-4PPS items accepted:
the player label comes from the take's capture info with a fallback to camera_label; no saved picked-folders file;
the control-read setting sentence; the Windows OS-key wording." This accepts items 1, 2, 6 and 8 of
[ADR-4PPS](4PPS-choices-of-the-answers-lane-of-q842-to-q856.md), which move here as items 1 to 4. Q919 does not
name items 5 and 7 of ADR-4PPS; they stay there, proposed.

1. **The camera label of the player** (4PPS item 1; `player.md` 8.4 and 5.8). The reader finds the capture info JSON
   by the name `<recording_name>_info.json`, with `recording_name` of the manifest. It reads the file with
   `readWhole` and the limit of the manifest, 16 MiB. A take with no manifest, a missing file, a file that does
   not parse, or a null `os_index` or `os_name` gives the label `camera_label`, with no error and no warning.
2. **The handler of the take scheme** (4PPS item 2; `player.md` 4.3, 5.3, 12.3). `installTakeHandler` takes only
   `recordingsFolder`: with no list file in 6a, `pickedFoldersFile` has no use. T-PLAY-62 checks that a picked
   folder is refused again after a restart of the harness, and that no `picked-take-folders.json` exists.
3. **The setting of the control read** (4PPS item 6). `windows-capture.md` 11.4 and 21.6 say that the product
   read of 11.4 honours `SKELLYCAM_CONTROL_READ=0`, as the restore honours `SKELLYCAM_RESTORE_CONTROLS=0`, so that
   the off half of the check of ADR-J1HD item 1 has a product setting to use. It is not built.
4. **The Windows OS key** (4PPS item 8; `certify.md` 11.2) is written from the code `current_os_key`:
   `platform.release()`, a space and `DisplayVersion` of the registry, `unknown` when it cannot be read.

The details that the user did not decide (which member, the checks of the file, equal labels, how long a pick
lasts, links) are in [ADR-WP77](WP77-choices-of-the-player-label-and-picked-folders-lane.md) (proposed).

## Reason

The words of the user, above. The reasons of the agent are in ADR-4PPS: the manifest already names the take, and a
label is not worth an error, because `camera_label` is always there; an option that nothing reads is dead code;
a setting that certify uses must be a setting that the product reads; the spec said `os.label`, but the code and
ADR-DC43 item 4 use the release.

## Open work

[open-work.md](../open-work.md)
