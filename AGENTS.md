# Repository Instructions for the research branch

This branch adopts only one rule of the agents and ADR kit of freemocap/project: the camera
recordings and frames rule. The other kit rules and checks are not adopted on this branch.

## Private Data

Do not commit a camera recording (video or audio) or a camera frame (a still image or a raw frame
from a camera). These files are large, and they can contain private information. The one exception
is a golden reference file: its path starts with an item of `GOLDEN_PATHS` in
`tools/check_camera_media.py`. This branch has no golden paths.

- A screenshot that shows a camera image is a camera frame. A chart, a diagram or a UI screenshot
  that shows no camera image is not a camera frame.
- A results folder can hold summaries, for example JSON, CSV and Markdown files. It must not hold
  the media. Keep large media outside the repository.
- To show a camera frame to the user, give its local path. Do not commit the frame.
- Before each commit, run `git diff --cached --name-only` and examine each path. Then run
  `uv run --no-project python tools/check_camera_media.py`. It must print no refusal line.
- If a recording or a frame is already committed, stop and tell the user the path and the commit.
  `uv run --no-project python tools/check_camera_media.py --all` lists them. Do not delete the
  file, rewrite the history or force-push without the approval of the user.

## Install the hook

Run these two commands once in each worktree of this branch:

```sh
git config extensions.worktreeConfig true
git config --worktree core.hooksPath .githooks
```

The hook in `.githooks/pre-commit` then refuses a commit that adds a camera recording or a camera
frame. Do not run `pre-commit install`. The worktrees of this clone share one `.git/hooks` folder.
The other worktrees keep their own hooks.
