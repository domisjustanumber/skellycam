# G5S0 — No camera recordings or camera frames in git, except golden reference files

**Status:** absorbed into
[`AGENTS.md#8-private-data`](../../AGENTS.md#8-private-data),
[`.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames`](../../.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames),
[`tools/check_camera_media.py`](../../tools/check_camera_media.py),
2026-11-17 (commit to dom/native-jpeg; was accepted, 2026-11-17 (user)).

## Decision

1. Do not commit a camera recording (video or audio) or a camera frame (a still image or a raw
   frame from a camera). This rule applies in each repository that uses the agents and ADR kit of
   freemocap/project.
2. The one exception is a golden reference file.
3. A screenshot that shows a camera image is a camera frame. A chart, a diagram or a UI screenshot
   that shows no camera image is not a camera frame.
4. A results folder can hold summaries, for example JSON, CSV and Markdown files. It must not hold
   the media. Large media stays outside the repository.
5. To show a camera frame to the user, give its local path. Do not commit the frame.
6. A skill and a pre-commit check state and enforce the rule.

## Reason

- The user, 2026-11-17: "recording files are large and may contain private information. Do not
  check them into Git unless they are golden reference files. This is the exception that must go
  into an updated skill and pre-commit check."
- The user, the same day, about single still frames from a camera: "frames count too."
- Camera frames were committed by mistake to the research branch on that day.

## Consequences

- Git history is permanent. A recording or a frame that is already committed stays in the history
  until the user approves a history rewrite.
- The choices of the check and of the skill are proposed in
  [ADR-NMM1](NMM1-design-of-the-camera-media-check.md).
