# 6MMJ — Choices of the move of T-PRV-25 and of the kit proposal

**Status:** proposed, 2026-11-27 (agent; waits for the user).

## Decision

An agent made these choices when it applied Q964
([ADR-93K1](93K1-decision-of-the-user-on-the-place-of-t-prv-25.md)). The user did not decide them.

1. **The product of the test.** `test_tools_import_no_product.py` finds the packages of the
   repository: each folder with an `__init__.py` in the root or in `src/`, except `tools`. It does
   not name `skellycam`. So the same file is a kit unit for each repository, with no new value in
   `kit.toml`. It parses each `.py` file of `tools/` with `ast`. It finds `import x`, `import x.y as
   z` and `from x.y import z`, also in a function. It ignores a relative import. A second test checks
   these forms on a fixed text.
2. **The tool.** It imports `skellycam` at the top of the file now, not in `build()`. Its command is
   `uv run python skellycam/tests/preview/write_camera_message_fixture.py` (with `--check` for the
   check). The field `source` of `camera-messages.json` gives the new path. That is the only change
   of the fixture file.
3. **The spec.** The kind **tool** of `preview-4b.md` 7.1 now means the test of the fixture tool of
   7.2, in `skellycam/tests/preview/`. ADR-NA1N stays absorbed: the spec cites [Q964] next to each
   changed rule.
4. **The workflows.** `capture.yml` loses the two `tools/` paths and the test path of its three
   selections. Its path `skellycam/tests/**` and its selection `skellycam/tests/preview` cover the
   new place. `player.yml` does not change: it has `skellycam/tests/preview/**` already.
   `doc-checks.yml` does not change (kit text).
5. **The kit proposal.** The rule changes the tool rule and the script rule of the block
   `AGENTS.md#decision-log`. The reason in the rule is that the doc checks install only the dev
   group. `propose` wrote the block, the new file unit and its line in `manifest.toml` into a
   separate worktree of the kit checkout, on a new local branch from the pinned kit commit
   `5fd2a81`, not from the local kit HEAD. The agent also changed "eight" to "nine" test files in
   the copy table of the kit README, and committed the result on that branch. ADR-0AMX says that the
   kit session commits a proposal. The supervisor asked for a local commit. Nothing is pushed.
6. **The fixture file and the ID.** `camera-messages.json` stays in
   `skellycam-ui/src/services/server/preview/tests/`. T-PRV-25 keeps its ID.
7. **How the kit change is made.** The rule is a change of the kit block `AGENTS.md#decision-log`.
   The test is a new kit file unit, `tools/tests/test_tools_import_no_product.py`. The same block
   now says that a tool or a script that imports the product goes to the product package, not to
   `tools/`.
8. **Q930.** Q964 also answers Q930. Item 2 of
   [ADR-6PJ2](6PJ2-decisions-of-the-user-on-q929-to-q941.md) says "Q930: not decided".
9. **Known limits of the enforcing test.** It does not find a dynamic import
   (`importlib.import_module`, `__import__`, `spec_from_file_location`) or a `python -m <package>`
   call. It does not find a namespace package with no `__init__.py`, a package in
   `src/<org>/<pkg>`, or a product that is one module file. It checks only the packages of the
   repository, not the third-party dependencies of the product.
10. **Open question: the kit route for skellytracker.** skellytracker is the only other repository
    with a `kit.toml`. 18 files in its `tools/` import `skellytracker`, and it skips
    `doc-checks.yml`. So the reason of the rule does not hold there, and the new test fails there
    after its `pull`. The user decides the route. The kit commit is not published until then.

## Reason

1. A test that names no package needs no new kit value, and it works in each repository.
2. Under `skellycam/`, the tool can import the product at the top, as the other test helpers do.
3. A supersede of ADR-NA1N must restate each of its other twelve answers. The skill allows a cite of
   the new entry next to the changed rule.
4. The smallest change of the workflows.
5. The pinned commit is on the remote branch of the kit. The local kit HEAD has a commit that no one
   has pushed. A branch from it would carry that commit.

## Alternatives rejected

- A test that names `skellycam`, or a new kit value for the package name: it needs a value in each
  `kit.toml`.
- `--ignore` of T-PRV-25 in `doc-checks.yml`: Q964 replaces it.

## Open work

See [open-work.md](../open-work.md).
