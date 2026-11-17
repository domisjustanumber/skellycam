# PEJ0 — Scope of the private-data check: two skipped file types, one placeholder, commit-time files

**Status:** absorbed into
[`AGENTS.md#8-private-data`](../../AGENTS.md#8-private-data),
[`tools/check_private_data.py`](../../tools/check_private_data.py),
2026-11-17 (commit to dom/native-jpeg; was accepted, 2026-11-17 (user)).

## Decision

1. `tools/check_private_data.py` skips the Adobe Illustrator file
   `shared/skellycam-logo/skellycam-logo.ai` and the generated lock file
   `skellycam-ui/package-lock.json`. It does this with `SKIPPED_SUFFIXES` (`.ai`,
   `package-lock.json`).
2. `/home/user` is a placeholder path. The tool does not report it. It still reports each other name
   after `/home/`, also a name that starts with `user`.
3. The pre-commit hook checks only the files of the commit (`--files`). A finding in an unrelated
   file does not stop a commit.
4. A run without `--files`, also `uv run pytest tools/tests` and CI, reports each finding of the
   repository. The three findings that the user has not decided stay reported
   ([open-work.md](../open-work.md)).

## Reason

- The user, 2026-11-17: apply the scoped fix, so that the hooks can be switched on in the
  `dom/native-jpeg` worktree; skip the logo file and the generated lock file; treat `/home/user` as
  a placeholder; do not change or hide the three other findings.
- The `.ai` file is binary data, and its matches are not addresses. The lock file holds the
  addresses of package authors. `/home/user` is the example path of the four `api-reference.mdx`
  docs.
- The commit-time check of `tools/check_camera_media.py` already uses the files of the commit, for
  the same reason: an old file must not stop an unrelated commit.

## Consequences

- `check_private_data.py` is no longer equal to the kit copy of skellytracker and skellyfileformat.
  The `--files` mode and the two lists are local changes. A kit sync must keep them.
- A finding in a file that the commit changes still stops the commit. A commit that changes one of
  the three files must first resolve its finding.

## Alternatives rejected

- Edit the upstream files: the user did not ask for it.
- Allow the three findings in the tool: that hides them from the whole-repository run.
- Keep the whole-repository scan in the hook: each commit stops while the three findings stay.

## Open work

See [open-work.md](../open-work.md).
