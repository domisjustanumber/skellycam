---
name: change-decision-log
description: Use this skill before you add a decision entry, change the status of an entry, absorb or supersede an entry, edit a decided entry, or move a row between the tables of a decision log. Use it also when the commit hook prints a decision log reminder.
---

# Change the decision log

This skill uses ASD-STE100 Simplified Technical English.

The [Rules](../../../decisions/README.md#rules) of the index give the rules for reading the log. This skill gives
the rules for a change to a log.
[Section 5](../../../AGENTS.md#5-decision-log) of `AGENTS.md` tells you which log takes an entry.

## Steps

<!-- kit:log-change-steps -->
1. Scan the tables for an entry that already decides the question or holds the measurement.
2. Get the ID of a new entry from `uv run python tools/check_decision_log.py --new`.
3. Write the entry from [template.md](../../../decisions/template.md) in `entries/` of its log.
4. Add its row to the table of its status. An `accepted` entry goes in the Active table of
   `README.md`. An `evidence` entry goes in `evidence.md`. A `proposed` entry goes in the Proposed
   table of `README.md`. Each other status goes in `historical.md`.
5. Apply the [Rules](#rules) to each status change, absorb and edit.
6. Run `uv run python tools/check_decision_log.py`. It must print no error.
<!-- /kit -->

## Rules

<!-- kit:log-change-rules -->
- The body of an entry that is not `proposed` changes only by four edits: a link or anchor repair, a
  typo that does not change the meaning, the redaction of private data, and a change of ID with the
  repair of its citations. Each edit adds `_Edited YYYY-MM-DD (#PR): <kind>._` at the end of the
  entry, for example `re-ID from XXXX`. For a
  change of ID, the renamed entry gets `re-ID from XXXX`, and each repaired entry gets
  `citation repair`. Add these two lines only to an entry that is on upstream `development`. A plain-text
  old path in a decided entry or a script stays, and means the same file at
  its new path.
- An entry in a commit that is not pushed to a remote can change in that commit, in each part. Make
  the correction and report it to the user. Do not write a new entry for it, and do not ask. The
  four edits apply from the first push.
- An absorb document is one of these: the root or a nested `AGENTS.md`, the skills, the normative
  documents, the Rules of the index with [template.md](../../../decisions/template.md), and the
  docstring of a tool in `tools/` for the rules that it checks. The normative documents of this
  repository are these: the specs in `specs/`. A test in `tools/tests/` or in the
  tests of the package is a tool here: its docstring states the rules that it checks.
  `pyproject.toml` is an absorb document for a rule that a test checks. Its `absorbed into` link
  stands beside the link of that test. An accepted entry is absorbed when the absorb
  documents together state all of its rules. Open work of the entry does not stop the absorb when
  `open-work.md` states that work in full. A link to the entry is not
  enough.
- A normative document is binding text. Read each normative document that applies to your task.
  Absorb an accepted entry into a normative document only after you check, entry by entry, that
  the document states each rule of that entry.
- Absorb at landing. The commit group that writes or lands an entry, or that writes the rules of an
  entry into the absorb documents, absorbs the entry in its last commit when the absorb documents
  state all of its rules. This applies in each log, in each skill and without a skill. If an absorb
  document does not state a rule, the entry stays `accepted`. Do not ask the user.
- The status `absorbed into` has one link for each heading that states a rule of the entry. Link a
  heading one time, also when it states two or more rules. Link a file with no anchor only when the
  rule is not under a heading, for example in a tool docstring or a YAML file. When the status
  paragraph is longer than `STATUS_EXEMPTION_LIMIT`, replace the headings of one file with the title
  heading of that file. Start with the file that has the most links. If the paragraph is still too
  long, replace the files of one document with the title heading of its
  main file. A commit that renames a heading repairs each status link to that heading. A change from
  a file link to heading links is a link repair.
- The entry that supersedes an old entry restates each rule of the old entry that stays. A link can
  restate a rule. The link must go to a heading of an absorb document, and that heading must state
  the rule. Link the heading of each kept rule that a heading states. Write text only for a changed
  rule and for a kept rule that no heading states. The commit that changes the text under such a heading cites its own entry next to the
  changed rule. That change does not supersede the entry that links the heading.
- Only these status changes are allowed: `proposed` to `accepted` or `rejected`; `accepted` to
  `superseded by XXXX`, `absorbed into <path>#<anchor>` or `done`; `absorbed into <path>#<anchor>`
  to `superseded by XXXX`; and `evidence` to
  `evidence; used by XXXX` or `evidence; replaced by XXXX`. Use `used by` when entry XXXX is or was
  `accepted` and cites the `evidence` entry for its decision. Use `replaced by` when the `evidence`
  entry XXXX repeats the measurement and its numbers replace the old numbers.
  `done` is for an accepted entry that records a one-off action, with no rule that stays, when the
  action is complete. Each status change adds its date and the PR that made it. In the same PR,
  change the status in the index and move the row to the table for the new status.
- `tools/check_decision_log.py` checks the tables, the status forms, the Section cell, the ID
  alphabet and the size limits. Its docstring states them. `tools/check_links.py` checks the links
  and the full-SHA permalinks. A tool is the source of a rule that it checks.
- A consolidation entry states the rules that stay from a group of entries, and it supersedes each
  entry of the group. It changes no decision.
- When the read path or an index is at 90% of its limit or more, first absorb each accepted entry whose rules
  the absorb documents state. Then
  write each rule that no absorb document states in the absorb document where it belongs, and
  absorb its entry.
- A commit that only makes a workflow, skill, template or tool copy agree with a landed entry
  cites that entry. It needs no entry of its own. A new rule is not a copy.
- Put long evidence in a tracked file in `evidence/` of the log folder, and link to it. A PR that raises a limit
  in the table `[check_decision_log]` of `kit.toml` must add an entry.
- Do not shorten the index row of an entry that you did not write.
- An ID changes only on a `re-ID:` line of `tools/check_decision_log.py`, to the ID of a new `--new`
  run.
- Until a commit is on upstream `development`, cite its PR number and the file path, not its SHA.
  The `ADR-` prefix is for citations only: a file name, a
  heading, an index row and a status line hold the bare ID. Cite a provisional entry of another repo
  by the repo name, the PR number and the slug. Do not edit a decided entry only to add or move the
  prefix or the link.
<!-- /kit -->

In this repository, the rules "A normative document is binding text" and "Do not shorten the index
row of an entry that you did not write" come from
[ADR-N2NH](../../../decisions/entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md).
An absorb into a spec goes into a spec heading.
