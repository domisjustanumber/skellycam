# F2KY — Rulings of the user after the third consistency check

**Status:** absorbed into
[`specs/unix-capture.md#49-source-selection-u`](../../specs/unix-capture.md#49-source-selection-u),
[`specs/certify.md#113-how-the-product-uses-it-u`](../../specs/certify.md#113-how-the-product-uses-it-u),
[`specs/camera-requests.md#18-ui`](../../specs/camera-requests.md#18-ui),
[`specs/recorder.md#13-non-goals`](../../specs/recorder.md#13-non-goals),
2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, relayed by the supervisor)).

## Decision

The user ruled these points on 2026-11-20:

1. **Native capture turns on for each camera model.** On Linux and macOS, native capture turns on for
   a camera model when the named gate checks pass at the base mode in a `full` run (item 2 of
   [ADR-BVK7](BVK7-certify-rulings-of-the-user-one-test-one-row.md) names the gate). A `verified` OS
   key alone turns on nothing. This replaces the "verified OS" wording of C6 of
   [ADR-KG00](KG00-certify-decisions-of-the-user-on-draft-2.md) and of item 11 of
   [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md). The `verified` row
   of item 7 of ADR-22EJ is a row of the camera model, not of the OS.
2. **"Update Cameras".** One "Update Cameras" button at the top of the camera list adds, closes and
   retries cameras, and does not reopen the other cameras. It is disabled during a recording, with
   the text "Stop the recording first".
3. **The microphone line** of the UI reads "Audio recording is not available yet."
4. **A route with no time unit.** On a control route with no time unit, the exposure shows as "step k
   of 8", the chip as `E:k/8`, and in Auto as "Auto: step k of 8".

The other UI rulings of the same day already have an entry:

- A `too_slow` camera keeps its tile and counts as streaming: Q10 of
  [ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md).
- The row text of a slow camera is "Camera is slow. Try adding more light": G3 of
  [ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md).
- The camera label `Camera <n> · <name>`: Q13 of
  [ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md).
- A virtual camera shows greyed with the label `virtual`, and it cannot be selected: G9 and Q12 of
  [ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md), and item 11 of
  [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md).

## Reason

The user gave these rulings after the third consistency check of the specs. They settle the points of
that check that only the user can decide.

## Consequences

- ADR-KG00 and ADR-22EJ are not on a remote. The text of C6 and of item 11 changes in the same
  commit, as the Rules allow for an entry that is not pushed. Item 11 of ADR-22EJ has no link to this
  entry, because that entry is at its size limit.
- The removal of " Or choose 30 fps." from the server reason is not a ruling of the user. It stays
  proposed (B8 of [ADR-4Z7T](4Z7T-choices-after-the-search-at-each-open.md)).
