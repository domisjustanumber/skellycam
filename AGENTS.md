# Repository Instructions

<!-- kit:writing-rules -->
All new and changed documentation must use ASD-STE100 Simplified Technical English.
This rule applies to `AGENTS.md`, skills, decision entries and templates.
Use short sentences. Use active voice. Use one instruction per sentence.
Use "must" for a requirement.
Keep technical names, field names, values, formulas, code and YAML unchanged.
<!-- /kit -->

## 1. Purpose

SkellyCam captures synchronized frames from two or more USB cameras, records them, and streams them.
It is the camera backend of FreeMoCap, and it is also usable alone. Its main parts are the Python
package in `skellycam/`, the Electron UI in `skellycam-ui/` and the docs site in `skellycam-docs/`.

| Path | Role |
|---|---|
| `AGENTS.md` | The root instructions file for coding agents |
| `CLAUDE.md` | A local file. Git does not track it, because `.gitignore` ignores it. If you want one, put only `@AGENTS.md` in it ([ADR-XT31](decisions/entries/XT31-kit-adoption-choices-camera-media-check-and-fills.md)). |
| `decisions/` | Decision log ([`README.md`](decisions/README.md)) and its open work ([`open-work.md`](decisions/open-work.md)) |
| `specs/` | The specifications. An accepted decision entry links each one. |
| `tools/` | The doc checks: `check_decision_log.py`, `check_links.py`, `check_private_data.py`, `check_camera_media.py`, `check_line_ends.py` and `check_other_systems.py`, and the kit sync `kit_sync.py`. The build tool `build_info.py` writes the build file of the certify report at each build. Their tests are in `tools/tests/`. |
| `kit.toml` | The values of this repository for the tools, and the kit commit that it took ([section 4](#4-project-rules)) |
| `plans/` | A local working folder. Git ignores it. |
| `.claude/skills/` | The skills ([section 2](#2-skills)) |
| `.githooks/` | The git hooks of a worktree that adopts these rules ([section 3](#3-install-and-test)) |
| `skellycam/` | The Python package and its tests in `skellycam/tests/` |
| `skellycam-ui/` | The Electron and React UI |
| `skellycam-docs/` | The Docusaurus docs site |

## 2. Skills

<!-- kit:skills -->
Load the skill that matches the task.
If your agent does not support skills, read the file `.claude/skills/<skill>/SKILL.md`.
The rules in this file also apply.
<!-- /kit -->

| Skill | Use it to |
|---|---|
| [`commit-files`](.claude/skills/commit-files/SKILL.md) | Make a commit, or add a recording, a camera frame, an image or another large file |
| [`change-decision-log`](.claude/skills/change-decision-log/SKILL.md) | Add a decision entry, change a status, absorb or supersede an entry, or move a row of a log |
| [`verify-on-other-systems`](.claude/skills/verify-on-other-systems/SKILL.md) | Get a fact from another system: another OS, or hardware that the system that you work on does not have |

## 3. Install and Test

Run `uv sync`.
Then run these two commands once in each worktree of this branch ([section 8](#8-private-data)):

```sh
git config extensions.worktreeConfig true
git config --worktree core.hooksPath .githooks
```

Do not run `uv run pre-commit install`. The worktrees of this clone share one `.git/hooks` folder,
and a branch without `.pre-commit-config.yaml` would then fail each commit.
The hooks in `.githooks/` run the pre-commit hooks, the commit-msg hook and the pre-push hook of
`.pre-commit-config.yaml`. Other worktrees keep their own hooks.
Use `uv run` for project commands.
Do not depend on an activated virtual environment.

Run `uv run pytest`.
These tests must pass.
Run `uv run pytest tools/tests` to run only the doc checks.
The doc checks test the decision log, the relative links, the private-data rule, the camera-media
rule, the line ends, the other-systems rule and the kit text.
Report each new test failure to the user.
Fix the failures of one root cause in one PR.

## 4. Project Rules

Pin each Python package, npm package, git revision, CI action and toolchain to one exact version.
Use `==` for Python. Do not use a version range.
Python is `==3.13.18` (`pyproject.toml`).
Do not change code that your task does not need.

<!-- kit:kit-text -->
Some text of this repository comes from the agents and ADR kit of freemocap/project. This is each
file and each block that `kit.toml` lists in `[kit.hashes]`. A block is the text between the lines
`<!-- kit:<name> -->` and `<!-- /kit -->`. Do not delete the marker lines.
`uv run pytest tools/tests` runs `tools/kit_sync.py check`. It fails when such a text is not the
kit text.
To change such a text, add a decision entry, change the text, and run
`uv run python tools/kit_sync.py propose`. It writes the change into the kit checkout in
`../project`. The kit change then needs its own PR to freemocap/project. Its commit subject cites
the entry of this repository.
To take a newer kit, run `uv run python tools/kit_sync.py pull`. Put the kit commit in the body of
the commit that takes it.
<!-- /kit -->

<!-- kit:line-ends -->
Each text file uses LF line ends, on each system. The kit block of `.gitattributes` makes git
write LF, also when `core.autocrlf` is set. Do not change that block.
`tools/check_line_ends.py` fails a commit and CI when the index holds a CRLF line end.
To repair the index, run `git add --renormalize .` and commit the result by itself.
<!-- /kit -->

### Other systems only through certify

<!-- kit:other-systems -->
You can test only on the system that you work on. You can reach each other system only through the
self-test of the project and its report. Another system is another OS, or hardware that the system
that you work on does not have.
When you cannot verify a fact on the system that you work on, do not write a script or a manual
step for a person to run on another system. Add a check to the self-test.
Sections 5.5 and 5.6 of `report-format.md` of the skellycertify repository tell how to add a check,
when a check can exist, and its level.
Mark the fact "not verified" until a report gives its result.
The one exception is a CI runner with no camera. It can still run the checks that need no device.
Load the skill [`verify-on-other-systems`](.claude/skills/verify-on-other-systems/SKILL.md) for
this work.
<!-- /kit -->

The self-test is `skellycam.certify(level)` ([specs/certify.md](specs/certify.md)). Mark a fact not
verified with `[NV]`.
The pre-commit hook runs `tools/check_other_systems.py` on the files that the commit adds, and
`uv run pytest tools/tests` and CI run it on each tracked file. It gives the same result on each
system. It refuses a script outside the product code that names or guards for any system, unless
one of its first 5 lines is the comment `script-purpose: <kind> ...`. The kinds are
`certify-check <name>`, `local-study (<what>)`, `tool (<what>)` and `ci (<workflow>)` (see its
docstring). `<name>` must be a check name of `specs/certify.md`. If the check is not in the spec,
add it to the spec first (see the skill). The result of a `local-study` is a fact about the system
of its author only. Mark it not verified for each other system.
The rule, the skill and the check come from
[ADR-VV4Q](decisions/entries/VV4Q-other-systems-only-through-certify.md),
[ADR-K3BX](decisions/entries/K3BX-certify-check-names-must-be-in-the-certify-spec.md),
[ADR-C307](decisions/entries/C307-script-purpose-field-and-check-names-of-the-certify-spec.md) and
[ADR-K9B7](decisions/entries/K9B7-design-of-the-other-systems-rule-skill-and-check.md).

## 5. Decision Log

<!-- kit:decision-log -->
Read [`decisions/README.md`](decisions/README.md) and
[`open-work.md`](decisions/open-work.md) before you change the code, the CI or these instructions.
For a task in a module with a log, also read the `decisions/README.md` and the
`decisions/open-work.md` of that module. The `AGENTS.md` of the module links to its log.
An entry goes in the log of a module only when each file that its Decision section names or
changes is in that module.
All other entries go in the root log, also each case that you cannot decide.
A new module log needs the approval of the user. The PR that adds it also adds its folder to
`module_logs` in the table `[check_decision_log]` of `kit.toml`.
Each log has a `README.md` with an Active table, a Proposed table and `## Open work`, an
`evidence.md` with the Evidence table, a `historical.md`, an `open-work.md` and its entry files in
`entries/`. The Rules and `template.md` are only in the root log.
All logs have one ID space. Do not add a module name to an ID.
When the scope of a module entry grows to more than one module, a new root entry supersedes it.
A tool is code that a test, a hook, a CI job, a skill or a workflow step runs, or code that writes a
tracked file. It is in the root `tools/`, also when only one module uses it. It has tests.
A script made the evidence for an entry or did its one-off job, and the entry names it. It is in
`scripts/` of the log that holds the entry. Its own tests, if any, are in `scripts/tests/`.
A script does not change after its entry is decided. When a step starts to run it, move it to
`tools/` and add a test.
The [Rules](decisions/README.md#rules) of the index give the rules for reading a log.
Before you add or change an entry, a status or a row of a table, load the skill
[`change-decision-log`](.claude/skills/change-decision-log/SKILL.md). It gives the allowed edits, the status changes and
the other rules for a change that no tool checks. `tools/check_decision_log.py` checks the tables, the IDs and the
limits.
Add one entry for each new decision or measurement.
Get its ID from `uv run python tools/check_decision_log.py --new`.
End each commit subject that adds or changes an entry with `(ADR-<ID>)`.
Cite each entry as a Markdown link with `ADR-<ID>` as the link text, in upper case, for example
[ADR-0001](decisions/entries/0001-decision-log-agents-md-and-private-data.md).
This rule applies to each text that you write: a tracked file, a plan, a PR body and a reply to the
user. In a reply or a plan, the path is relative to the repository root or to the file.
A commit message cannot hold a working link. In the commit body, write `ADR-<ID>` with no link.
Cite an entry of another repository with the repository name and `ADR-<ID>`. Also link it with a
full-SHA permalink when the entry is on the default branch of that repository
(see the [Rules](.claude/skills/change-decision-log/SKILL.md#rules)).
<!-- /kit -->

## 6. Git Rules

<!-- kit:plans-folder -->
- `plans/` is a local working folder. Git ignores it. Do not commit it. Do not cite or link to
  `plans/`, or cite the content of a plan
  ([ADR-0001](decisions/entries/0001-decision-log-agents-md-and-private-data.md)).
  <!-- /kit -->
  <!-- kit:push-and-attribution -->
- Do not push to a git remote without the approval of the user. One approval for a PR covers its
  push, its draft PR and its description.
- Ask the user before any other action that is visible outside this machine, for example a PR
  comment, a later change to a PR description, a change of a draft PR to ready, a release or a
  published image. A force-push is a new push. It needs its own approval.
- Do not add AI attribution, for example a `Co-Authored-By:` trailer, to a commit or a PR. This
  rule overrides a default of a tool or a harness that adds attribution.
  <!-- /kit -->
- Open each PR against `development` of upstream (`freemocap/skellycam`)
  ([ADR-EQY4](decisions/entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md)).
- Put one kind of change in each PR: "code", "docs" and "CI".

## 7. Tool Calls

<!-- kit:tool-calls -->
Before a tool call that needs user permission, write a one-line summary of the call.
The summary must tell what the call does and what it changes.
Write the summary in the message text, not only in the tool description.
<!-- /kit -->

## 8. Private Data

<!-- kit:private-data -->
This repository is public, or it can become public. Git history is permanent
([ADR-0001](decisions/entries/0001-decision-log-agents-md-and-private-data.md)).
Do not write these in a tracked file, a commit message or a PR body:

- a credential, a token, a password or a private key;
- an absolute path in a user folder;
- a hostname or a user name in prose;
- an email address that is not on the allowlist of `tools/check_private_data.py` and `kit.toml`;
- a private URL or a private IP address;
- a raw dump of `env`, `pip list`, `nvidia-smi` or `docker inspect`.

Do not commit a camera recording (video or audio) or a camera frame (a still image or a raw frame
from a camera). These files are large, and they can contain private information. The one exception
is a golden reference file: its path starts with an item of `golden_paths` in the table
`[check_camera_media]` of `kit.toml`. Load the [`commit-files`](.claude/skills/commit-files/SKILL.md)
skill before each commit.

- A screenshot that shows a camera image is a camera frame. A chart, a diagram or a UI screenshot
  that shows no camera image is not a camera frame.
- A results folder can hold summaries, for example JSON, CSV and Markdown files. It must not hold
  the media. Keep large media outside the repository.
- To show a camera frame to the user, give its local path. Do not commit the frame.

- Use paths relative to the repository, for example `../skellyfileformat/spec/`.
- Give a measurement as a summary with its tool and its version.
- A report field or a test fake can contain a hostname.
- Text from `plans/` must obey these rules before it goes into a tracked file.
- To also block a hostname or a user name, put it in `.private-terms` in the repository root. Git
  ignores that file. Do not commit it.
- If you find private data in a tracked file, remove it with a redaction edit. Then tell the user,
  because git history keeps the data. Also revoke a leaked credential.
- The pre-commit hook runs `gitleaks`, `tools/check_private_data.py` and
  `tools/check_camera_media.py` on the files of the commit. CI runs `gitleaks` on each push and PR.
  `uv run pytest tools/tests` and CI run `tools/check_private_data.py` on each file of the
  repository. `.gitleaks.toml` holds the reviewed false positives.
- The commit-msg hook warns about AI attribution. If you are an AI agent and you see
  this warning, tell the user.
- Turn on secret scanning and push protection for a private repository on the day that it becomes
  public.
<!-- /kit -->
