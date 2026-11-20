# WB08 — Acceptance of the step 4a preview spec and its test list

**Status:** absorbed into
[`specs/preview.md#phase-4-preview-specification-the-per-camera-websocket-message-and-its-sender-4a`](../../specs/preview.md#phase-4-preview-specification-the-per-camera-websocket-message-and-its-sender-4a),
[`specs/preview.md#91-kinds-and-helpers`](../../specs/preview.md#91-kinds-and-helpers),
[`specs/preview.md#92-test-list`](../../specs/preview.md#92-test-list),
2026-11-20 (commit to dom/integration; was accepted, 2026-11-19 (user)).

## Decision

The user accepted [`specs/preview.md`](../../specs/preview.md) and its test list T-PRV-01 to
T-PRV-24 (step 4a) on 2026-11-19. The spec is the third revision of
[ADR-162X](162X-step-4a-preview-spec-and-agent-choices.md). It applies the decisions P1 to P7 and the
answers A1 to A8 of [ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md).

## Reason

- The user, 2026-11-19. The rule "a spec and a test list before code": the failing tests of step 4a
  come next, then the product code of step 4a.

## Consequences

- The failing tests of step 4a go in `skellycam/tests/preview/` (spec section 9).
- ADR-162X records the agent choices of section 13 of the spec. Its status does not change here.

## Open work

See [open-work.md](../open-work.md).
