# K9B7 — Design of the other-systems rule text, its skill and its file check

**Status:** proposed, 2026-11-23 (agent; waits for the user).

## Decision

The rule is [ADR-VV4Q](VV4Q-other-systems-only-through-certify.md). An agent chose each item
below. The user has not decided them.

1. **Rule text.** A block `<!-- kit:other-systems -->` under the heading
   [Other systems only through certify](../../AGENTS.md#other-systems-only-through-certify) in
   section 4 of `AGENTS.md`, with a row in the skill table of section 2. Its sub-rules restate rules
   of [`specs/certify.md`](../../specs/certify.md): `record-only` for a check with no pass rule
   (3.3), a failing check does not break the run (10.5), a check that can block a device runs after
   the safe checks (8.1), a result with a reason code and no private data (9.4). Outside the block,
   one pointer names `skellycam.certify(level)` and the mark `[NV]`.
2. **Skill.** `.claude/skills/verify-on-other-systems/SKILL.md`: name the certify check, or add one
   with the checklist of item 1; mark the fact `[NV]` in the spec and in `open-work.md`; tell the
   user which report gives the result; the CI exception; the two markers.
3. **Tool.** `tools/check_other_systems.py`, standard library and the git CLI only, with its test
   `tools/tests/test_other_systems.py`. Its form copies `tools/check_camera_media.py`.
4. **What it scans.** Only a script: `.py .sh .bash .zsh .command .ps1`. It skips `EXEMPT_PATHS`
   (`skellycam/`, `skellycam-ui/`, `skellycam-docs/`, `.github/`) and each path with a `tests`
   folder. A Markdown or text file is not checked. It reads a file with a UTF-16 BOM as UTF-16.
5. **Signals.**
   - A path part (split at each character that is not a letter or a digit) that is `mac`,
     `macos`, `osx`, `darwin` or `linux`.
   - In a Python script: `sys.platform` with `==`, `!=`, `in` or `not in` and a value that is not
     in `LAB_PLATFORMS`; `sys.platform.startswith` with a value that no lab platform starts with;
     `platform.system()` with `==`, `!=` or `in` and a value that is not in `LAB_SYSTEMS`.
   - So a lab guard passes: `sys.platform != "win32"`, `not sys.platform.startswith("win")` and
     `platform.system() != "Windows"`. This repo sets `LAB_PLATFORMS = ("win32",)` and
     `LAB_SYSTEMS = ("Windows",)`.
   - A `probe_*` name is not a signal: a probe on the lab machine is valid.
6. **Markers.** One of the first 5 lines is a comment (`#` or `//` before the text) with
   `certify-check: <name>` (the script serves that certify check) or
   `other-systems: not applicable (<reason>)`. A marker in a string, an empty name and an empty
   reason do not pass. The tool does not look up the name in `specs/certify.md`.
7. **Modes.** The tool finds the repository root with `git rev-parse --show-toplevel`, so a run
   from a subfolder checks the whole repository. With no argument, it checks the files that the
   commit adds (`--diff-filter=A --no-renames`): a moved file, or a deleted file plus a similar new
   file, is a new file, and a change to an old file does not stop a commit. The pre-commit hook
   runs it so, with `pass_filenames: false`. With file arguments it checks those files. `--all`
   checks each tracked file; the doc test runs it, and CI runs the doc test. Exit codes: 0, 1 for a
   refusal, 2 for a usage error, outside a git repository or with no git (one line, no traceback).

## Reason

- A Python platform guard and a file name are the two forms of the scripts that the rule stops.
- The product code, its tests, the docs site and CI must name other systems, so the tool skips
  them.
- The decision log names other systems in many entry file names, so a document name is not a
  signal.

## Evidence

- `uv run python tools/check_other_systems.py --all` on the tree of this branch: `other systems: no
  findings (989 files, 8 scripts in scope)`. The 8 scripts are 2 in `decisions/scripts/` and 6 in
  `tools/`.

## Consequences

- The tool misses: an instruction in a shell script or in Markdown (it reads only the path of a
  shell script), a script with no script suffix, a script named for its probe and not for the
  system, a tuple in `startswith`, a guard with the literal first, `os.name`, `match`, and chat. It
  refuses a comment that quotes a guard.
- A Claude Code prompt hook as a backup reminder is not in this change.
- On `dom/research`, `--all` refuses 83 scripts of the research tree, most of them in its `linux/`
  and `macos/` folders. That branch does not adopt the rule.

## Alternatives rejected

- A phrase check on the specs: many correct lines about a run by hand would fail it.
- A field in a spec template: the specs have no template.
- A Stop hook: it must parse the transcript, and it fires on text that quotes the rule.
- A lookup of the `certify-check` name in `specs/certify.md`: not in this change.
