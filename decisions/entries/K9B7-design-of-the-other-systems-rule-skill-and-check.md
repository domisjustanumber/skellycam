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
2. **Skill.** `.claude/skills/verify-on-other-systems/SKILL.md`: name the certify check, or add one;
   mark the fact `[NV]` in the spec and in `open-work.md`; tell the user which report gives the
   result; the CI exception; the purpose field; one step that points to sections 5.5 and 5.6 of
   `report-format.md` of the skellycertify repository (relayed by the supervisor). Section 5.6
   states each item of the old checklist of the skill, so the skill keeps only the pointer.
3. **Tool.** `tools/check_other_systems.py`, standard library and the git CLI only, with its test
   `tools/tests/test_other_systems.py`. Its form copies `tools/check_camera_media.py`.
4. **What it scans.** Only a script: `.py .sh .bash .zsh .command .ps1`. It skips `EXEMPT_PATHS`
   (`skellycam/`, `skellycam-ui/`, `skellycam-docs/`, `.github/`) and each path with a `tests`
   folder. A Markdown or text file is not checked. It reads a file with a UTF-16 BOM as UTF-16.
5. **Signals.** No system is special
   ([ADR-C307](C307-script-purpose-field-and-check-names-of-the-certify-spec.md)).
   - A path part (split at each character that is not a letter or a digit) that is `win`,
     `windows`, `win32`, `mac`, `macos`, `osx`, `darwin` or `linux`.
   - In a Python script: `sys.platform` or `platform.system()` with `==`, `!=`, `in`, `not in` or
     `startswith` and a literal.
   - A `probe_*` name is not a signal.
6. **The purpose field.** The comment (`#` or `//`) `script-purpose: <kind> ...` in one of the
   first 5 lines; the kinds of ADR-C307. The text in brackets must not be empty. For `ci`,
   `.github/workflows/<workflow>` must exist. A field in a string or after line 5 does not count.
   A field is checked also on a script with no signal. The refusal line names an old marker.
   - **Name lookup.** A check name is the whole text of a code span of `specs/certify.md` that
     matches `CHECK_NAME` (the docstring states its form), whose first part is in `FIRST_PARTS`
     (the first parts of the name forms of spec 3.1, and `session`, `report`, `pipeline`), and
     whose other parts are not in `GENERIC` (`<check> <name> <group> <condition>`). So
     `<label>:usb3-trial` passes, and a filled-in name, a part of a name (`clock:base`,
     `vvvv:pppp`, `a1-cmio-native:exposure`) and a name form (`system:<check>`) do not.
   - No exact list of the names exists. `catalog.py` holds parts without `<label>:` and not the
     names of 3.6; the tables of the spec lack names such as `<label>:usb3-trial` and
     `<model>:gate:rate`. A new first part in the spec needs a change of `FIRST_PARTS`. An example
     instance that the spec writes in a code span passes.
   - A missing spec refuses each `certify-check`. The refusal line ends with the constant
     `ADD_CHECK_FIRST`.
7. **Modes.** The tool finds the repository root with `git rev-parse --show-toplevel`. With no
   argument, it checks the files that the commit adds (`--diff-filter=A --no-renames`); the
   pre-commit hook runs it so, with `pass_filenames: false`. With file arguments it checks those
   files. `--all` checks each tracked file; the doc test runs it, and CI runs the doc test. Each
   mode gives the same result on each system. Exit codes: 0, 1 for a refusal, 2 for a usage error,
   outside a git repository or with no git (one line, no traceback).

## Reason

- A Python platform guard and a file name are the two forms of a script for a system.
- The product code, its tests, the docs site and CI must name other systems, so the tool skips
  them.
- The decision log names other systems in many entry file names, so a document name is not a
  signal.

## Evidence

- `uv run python tools/check_other_systems.py --all` on the tree of this branch: `other systems: no
  findings (991 files, 8 scripts in scope)`. The 8 scripts are 2 in `decisions/scripts/` and 6 in
  `tools/`. None of them has a signal, so none needs a purpose field.

## Consequences

- The tool misses: an instruction in a shell script or in Markdown (it reads only the path of a
  shell script), a script with no script suffix, a script named for its probe and not for the
  system, a tuple in `startswith`, a guard with the literal first, `os.name`, `match`, and chat. It
  finds a signal in a comment that quotes a guard.
- A Claude Code prompt hook as a backup reminder is not in this change.
- On `dom/research`, `--all` refuses 214 scripts of the research tree (83 while Windows was
  exempt). That branch does not adopt the rule.

## Alternatives rejected

- A phrase check on the specs: many correct lines about a run by hand would fail it.
- A field in a spec template: the specs have no template.
- A Stop hook: it must parse the transcript, and it fires on text that quotes the rule.
- A check relative to the system that runs the tool: the user ruled out an exception for the system
  of the author (Q643 of ADR-C307).
