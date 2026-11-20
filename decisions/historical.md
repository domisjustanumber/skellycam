# Decision log: historical entries

These entries are `rejected`, `superseded by XXXX`, `absorbed into <path>#<anchor>`,
`evidence; used by XXXX` or `done`. They are not in the read path. Read an entry here only to find
the reason for a decision. The [index](README.md) has the Active and Proposed entries and the
[Rules](README.md#rules).

### Historical

| # | Decision | Status |
|---|----------|--------|
| [PEJ0](entries/PEJ0-scope-of-the-private-data-check.md) | Private-data check: skip `.ai` and `package-lock.json`, `/home/user` is a placeholder, the hook checks the commit files | absorbed into [`AGENTS.md#8-private-data`](../AGENTS.md#8-private-data), [`tools/check_private_data.py`](../tools/check_private_data.py) |
| [G5S0](entries/G5S0-no-camera-recordings-or-frames-in-git.md) | No camera recordings or camera frames in git, except golden reference files | absorbed into [`AGENTS.md#8-private-data`](../AGENTS.md#8-private-data), [`.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames`](../.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames), [`tools/check_camera_media.py`](../tools/check_camera_media.py) |
| [S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md) | Answers to the bootstrap questions of the kit adoption | superseded by 2S1P |
