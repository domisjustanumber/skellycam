# XT31 — Kit adoption choices: the camera media check, the commit skill, the hook install and the fills

**Status:** accepted, 2026-11-20 (user: two rulings on review sheet 5 of 2026-11-20; the other items
accepted through the review sheets of 2026-11-20; commit to dom/integration).

## Decision

This entry supersedes [ADR-NMM1](NMM1-design-of-the-camera-media-check.md) and
[ADR-4A7H](4A7H-other-fills-of-the-kit-adoption.md). Each of their items is below. Items 17 and 18
of [ADR-P5VE](P5VE-review-fix-choices.md) (sheet 5) are in
[ADR-P98T](P98T-step-5a-choices-of-the-recorder-and-its-connection.md), which supersedes that entry
in full.

Ruled by the user:

- NMM1 5 is overturned. The camera media check refuses a PNG, GIF, WebP or SVG file, as it refuses
  a camera frame. Each chart, diagram or UI screenshot is allowed by its path. Today the tool prints
  only a reminder for these files, so the tool, its docstring and the `commit-files` skill must
  change ([open-work.md](../open-work.md)).
- The index limit is 24,000 characters, as
  [ADR-N2NH](N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md) sets it. The proposal
  to keep 14,000 (item 13 of the entry F8C0 on `dom/recorder-connection-fix3`) is not used.

Accepted through the review sheets, by a link to the heading or the docstring that states it:

- NMM1 1 to 4, 6, 7: [`check_camera_media.py`](../../tools/check_camera_media.py) (the tool, its
  suffix lists, the first bytes, `GOLDEN_PATHS = ()`, the modes, `--all` and the exit codes).
- NMM1 8: [`commit-files`](../../.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames).
- NMM1 9: [`AGENTS.md` 3](../../AGENTS.md#3-install-and-test).
- 4A7H 1: [`AGENTS.md` 1](../../AGENTS.md#1-purpose), [3](../../AGENTS.md#3-install-and-test) and
  [4](../../AGENTS.md#4-project-rules); `info@freemocap.org` in `ALLOWED_EMAILS` of
  [`check_private_data.py`](../../tools/check_private_data.py).

Accepted through the review sheets, as text:

- 4A7H 1 (the rest): `pre-commit==4.6.2` is in the `dev` group, and `tools/tests` is in
  `testpaths` of `pyproject.toml`.
- 4A7H 2: git does not track `CLAUDE.md`. The `.gitignore` ignores it, and the local file holds only
  `@AGENTS.md`.

No item of these entries is stale.

## Reason

The rulings of the user. The old entries hold the reasons. The sheet named the risk of a reminder
only: a camera screenshot as a PNG can go into a commit by mistake.

## Open work

See [open-work.md](../open-work.md).
