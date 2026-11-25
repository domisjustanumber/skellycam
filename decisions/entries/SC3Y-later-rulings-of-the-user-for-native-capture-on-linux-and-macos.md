# SC3Y — Later rulings of the user for native capture on Linux and macOS

**Status:** absorbed into
[`specs/unix-capture.md#0-how-to-read-this-spec`](../../specs/unix-capture.md#0-how-to-read-this-spec),
[`specs/unix-capture.md#446-controls-m-15`](../../specs/unix-capture.md#446-controls-m-15),
[`specs/unix-capture.md#4410-approaches-for-exposure-and-for-the-cameras-jpeg-u`](../../specs/unix-capture.md#4410-approaches-for-exposure-and-for-the-cameras-jpeg-u),
[`specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u`](../../specs/unix-capture.md#47-restore-of-the-controls-at-the-close-u),
[`specs/unix-capture.md#49-source-selection-u`](../../specs/unix-capture.md#49-source-selection-u),
[`specs/certify.md#25-checked-camera-models-and-the-local-record-u-a`](../../specs/certify.md#25-checked-camera-models-and-the-local-record-u-a),
[`specs/certify.md#113-how-the-product-uses-it-u`](../../specs/certify.md#113-how-the-product-uses-it-u),
[`specs/camera-requests.md#13b-the-search-at-an-open`](../../specs/camera-requests.md#13b-the-search-at-an-open),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-20 (user; relayed by the supervisor session on 2026-11-20)).

## Decision

The user ruled these points after the cross-spec review of the camera requests spec, the Linux and
macOS capture spec [`specs/unix-capture.md`](../../specs/unix-capture.md) and the certify spec. They
add to [ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md).

1. macOS camera control, in the user's words: "I want to use the widest/best supported route for
   camera control and prefer that over the measurement units for exposure. So if the method that uses
   EV is better than the one that uses seconds, I'd take that." This replaces the rule "exposure only
   where the control gives seconds". The CoreMediaIO routes A1 (`NativeValue`), A2 (`AbsoluteValue`)
   and A3 (`NativeData`) are candidate product routes for exposure, gain and focus. The route of a
   model comes from the evidence (the local full row, then the shipped row; the route that works on
   the most models when several work), and from a fixed order when there is no evidence. Endpoint 0
   and exclusive opens stay certify probes.
2. Named checks of a full certify run, not the summary result, turn native capture on for a model on
   Linux and macOS. The certify spec holds the list. A failed exposure, gain or focus check does not
   block: that control is then absent in the UI, and on Linux the camera gets the warning
   `no_manual_exposure`.
3. A new OS version makes each model unchecked again.
4. The restore at the close is the one allowed call that may turn the camera's own auto exposure
   back on.
5. The public pause route is removed from the server. The internal pause for a record start stays.
6. Ownership: the camera requests spec owns the exposure search (its algorithm, its states and their
   order, its field and endpoint names, its time limits), the 60 fps fall back and the USB link
   lookup. The certify spec owns the check names and the record of checked models
   `camera_checks.json`. The other specs point to them.

## Reason

One owner for each rule removes the contradictions that the review found. The widest working route
gives exposure control on more macOS cameras than a rule on units.

## Consequences

- Question 5 of the capture spec (gain and focus through `NativeValue`) is superseded by item 1.
- The capture spec drops its own exposure search, its USB link lookup and its rows of the record.
