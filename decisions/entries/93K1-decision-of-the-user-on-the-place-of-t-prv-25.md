# 93K1 — Decision of the user on the place of T-PRV-25: no file in `tools/` imports the product

**Status:** absorbed into
[`specs/preview-4b.md#71-kinds`](../../specs/preview-4b.md#71-kinds),
[`specs/preview-4b.md#72-helpers-agent-11-agent-27-agent-28`](../../specs/preview-4b.md#72-helpers-agent-11-agent-27-agent-28),
[`specs/preview-4b.md#74-test-list`](../../specs/preview-4b.md#74-test-list),
[`specs/preview-4b.md#78-counts-and-ci-agent-12`](../../specs/preview-4b.md#78-counts-and-ci-agent-12),
[`AGENTS.md#5-decision-log`](../../AGENTS.md#5-decision-log),
[`tools/tests/test_tools_import_no_product.py`](../../tools/tests/test_tools_import_no_product.py),
2026-11-27 (commit to dom/tools-rule; was accepted, 2026-11-27 (user, Q964; the supervisor relayed
the answer)).

## Decision

Q964. The user wrote on 2026-11-27: "nothing in `tools/` or `tools/tests/` imports the product;
anything that imports `skellycam` lives under `skellycam/`. The fixture script
`tools/write_camera_message_fixture.py` and its test `tools/tests/test_camera_message_fixture.py`
(T-PRV-25) both move to `skellycam/tests/preview/`. One small test in `tools/tests` enforces the
rule. This replaces Q836 (which kept T-PRV-25 in tools/tests)." He added: "and put a kit change in
for this".

1. No file in `tools/` or `tools/tests/` imports `skellycam`. A file that imports `skellycam` is
   under `skellycam/`.
2. The fixture tool and T-PRV-25 are in `skellycam/tests/preview/`:
   `write_camera_message_fixture.py` and `test_camera_message_fixture.py`. T-PRV-25 keeps its ID.
   The fixture file `camera-messages.json` stays in `skellycam-ui/src/services/server/preview/tests/`.
3. `tools/tests/test_tools_import_no_product.py` enforces rule 1.
4. This replaces the part of Q836
   ([ADR-NA1N](NA1N-answers-of-the-user-to-the-questions-of-the-step-4b-tests.md)) that kept
   T-PRV-25 in `tools/tests/`. The `--ignore` of T-PRV-25 in `doc-checks.yml` does not come.
5. The rule goes to the kit, as a kit change of the block `AGENTS.md#decision-log` and a new kit
   file unit for the test.

## Reason

`doc-checks.yml` is kit text. It installs only the dev group, so `skellycam` is not importable there.
It runs all of `tools/tests`, so T-PRV-25 failed there, and Doc checks was red. A move is one local
change. The kit rule keeps each other repository of the kit from the same fault.

## Consequences

- The capture jobs and `test.yml` run T-PRV-25 through their selection of `skellycam/tests`.
- The choices of the agent for this move and for the kit proposal are in
  [ADR-6MMJ](6MMJ-choices-of-the-move-of-t-prv-25-and-of-the-kit-proposal.md).

## Open work

See [open-work.md](../open-work.md).
