# NMM1 — Design of the camera media check, the commit skill and the hook install

**Status:** proposed, 2026-11-17 (agent; waits for the user).

## Decision

The rule is [ADR-G5S0](G5S0-no-camera-recordings-or-frames-in-git.md). An agent chose each item
below. The user has not decided them.

1. **Tool.** A new tool `tools/check_camera_media.py`, next to `tools/check_private_data.py`. It uses
   only the standard library and the git CLI. `check_private_data.py` stays a copy of the kit.
   [ADR-PEJ0](PEJ0-scope-of-the-private-data-check.md) later adds local changes to that copy.
2. **Recording types.** `.mp4 .mkv .mka .avi .mov .webm .m4v .m4a .wav .flac .opus .ogg .mp3 .mcap
   .h264 .h265 .mjpeg .mjpg .y4m .yuv`, and `.ts` only when its first bytes are an MPEG transport
   stream. A `.ts` file is usually TypeScript: this repository tracks 87.
3. **Frame types.** `.jpg .jpeg .jpe .raw .bayer .dng .bmp .tif .tiff .ppm .pgm`. NumPy and other
   array dumps are measurements, and the tool does not refuse them.
4. **First bytes.** The tool also refuses a file by its first bytes: JPEG, the MP4 and QuickTime
   `ftyp` box, Matroska and WebM, MCAP, Ogg, FLAC, MP3 with ID3, Y4M, AVI, WAV, TIFF and the MPEG
   transport stream. A renamed recording or JPEG is then also refused.
5. **Images.** A PNG, GIF, WebP or SVG file is not refused. The tool prints a reminder that does not
   stop the commit. The written rule covers a screenshot that shows a camera image.
6. **Golden paths.** `GOLDEN_PATHS` in the tool holds the path prefixes of the golden reference
   files, as `ALLOWED_EMAILS` does in `check_private_data.py`. The kit default is `golden/`. This
   repository sets `()`, because it has no golden reference files.
7. **Modes.** With file arguments (the pre-commit hook) or with no argument (the staged files), the
   tool checks only the files of the commit. A deleted file is not checked. `--all` lists each
   tracked file that the rule refuses. Exit codes: 0, 1 for a refusal, 2 for a usage error.
8. **Skill.** One kit skill, `commit-files`, in `.claude/skills/commit-files/SKILL.md`. The kit had
   no commit skill.
9. **Hook install.** The worktrees of this clone share one `.git/hooks` folder, and the shared
   config already sets `core.hooksPath`, so `pre-commit install` refuses to run. A worktree that
   adopts these rules sets `extensions.worktreeConfig` and its own `core.hooksPath` to the tracked
   folder `.githooks/` ([`AGENTS.md`](../../AGENTS.md#3-install-and-test)). The other worktrees keep
   the shared value.

## Reason

- A sibling tool keeps `check_private_data.py` equal to the kit copy of skellytracker.
- A tracked list of golden paths is not private. A constant in the tool is the form that the kit
  already uses for an allowlist.
- A PNG is often a chart or a UI screenshot. A refusal by extension would stop correct commits.
- A whole-repository scan in the hook would stop each commit while an old file stays in the history.

## Evidence

- A throwaway clone with three linked worktrees, git 2.43.0.windows.1, repository format version 0:
  with `extensions.worktreeConfig` and `core.hooksPath` set in one worktree only, a refusing hook
  in `.githooks/` stopped a commit in that worktree. Commits in the main worktree, in a second
  worktree and in a detached worktree ran no hook.

## Alternatives rejected

- One hook script in the shared `.git/hooks` that exits 0 when the tree has no
  `.pre-commit-config.yaml`: a defect in it stops the commits of each worktree.
- An extension in `check_private_data.py`: each kit sync of skellytracker then has a conflict.
