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
  [`specs/frame-ring.md`](../specs/frame-ring.md). The failing tests of step 2a (T-RING-01 to 33)
  are in `skellycam/tests/frame_ring/`. They fail because the package does not exist, and
  T-RING-32 fails because the old code exists. T-RING-49 needs cameras and is not written. Run the
  T-RING-34 and T-RING-35 set with `uv run pytest -m ring_portable skellycam/tests/frame_ring`.
  Run the timed and kill tests with `-m ring_slow`. `SKELLYCAM_RING_FULL=1` gives the durations of
  the spec, for example 60 s for T-RING-08. The tests use the API of
  [ADR-9G2W](entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md). The user
  decides that entry. Then step 2a writes the code. Before step 2a keeps the change of the
  10 µs wait of the OpenCV loop (item 45), it compares the frame timing before and after the change
  on the four test cameras. It keeps the change only if the grab timing is not worse. Phase 2 makes
  the measurements M1 to M8 of section 11.3 before it fixes a performance number. The build of step
  2b waits for the approval and guidance of the user. Section 13 of the spec holds the open
  questions.
