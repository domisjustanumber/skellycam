# Open work

This file holds the open work of the [decision log](README.md). Read the items that apply to your
task. Delete an item when its work is done. The PR that closes an item records the result.

- **The fills that wait for the user.** The user must decide
  [ADR-4A7H](entries/4A7H-other-fills-of-the-kit-adoption.md) and
  [ADR-NMM1](entries/NMM1-design-of-the-camera-media-check.md).
- **Private-data findings.** `tools/check_private_data.py` reports 3 lines in upstream files: an
  email address in `skellycam-ui/src/hooks/floatingOnboarding.tsx` and in
  `skellycam-ui/src/hooks/useDraggableTooltips.tsx`, and a user path in
  `skellycam/tests/reference_recordings/README.md`. The user decides each redaction. Until then,
  `test_repository_has_no_private_data` fails, and a commit that changes one of these files stops
  ([ADR-PEJ0](entries/PEJ0-scope-of-the-private-data-check.md)).
- **CI on PRs to `development-streaming`.** `.github/workflows/test.yml` runs on PRs to `main` and
  `development` only, so the package tests do not run on a PR to `development-streaming`, the PR
  branch of [ADR-S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md). A CI change needs the
  user.
- **Phase 2 of the frame ring.** [ADR-50G8](entries/50G8-phase-2-frame-ring-spec.md) accepts
  [`specs/frame-ring.md`](../specs/frame-ring.md). Nothing is built. Step 2a first writes the failing
  tests of section 12 of the spec. Then it writes the code. Before step 2a keeps the change of the
  10 µs wait of the OpenCV loop (item 45), it compares the frame timing before and after the change
  on the four test cameras. It keeps the change only if the grab timing is not worse. Phase 2 makes
  the measurements M1 to M8 of section 11.3 before it fixes a performance number. The build of step
  2b waits for the approval and guidance of the user. Section 13 of the spec holds the open
  questions.
