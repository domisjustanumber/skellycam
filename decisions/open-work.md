# Open work

This file holds the open work of the [decision log](README.md). Read the items that apply to your
task. Delete an item when its work is done. The PR that closes an item records the result.

- **The bootstrap answers.** The user must answer the questions of
  [ADR-S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md) and decide
  [ADR-NMM1](entries/NMM1-design-of-the-camera-media-check.md).
- **Private-data findings.** `tools/check_private_data.py` reports 15 lines in upstream files:
  `shared/skellycam-logo/skellycam-logo.ai` (3), the `api-reference.mdx` docs (8, an example home-folder path),
  `skellycam-ui/package-lock.json` (1), two `skellycam-ui/src/hooks/*.tsx` files (2) and
  `skellycam/tests/reference_recordings/README.md` (1). The user decides each redaction or skip.
