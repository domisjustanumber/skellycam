# KG00 — Decisions of the user on draft 2 of the certify spec

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor).

## Decision

The user decided these points on 2026-11-20. The spec [`specs/certify.md`](../../specs/certify.md)
(draft 3) marks them [U].

1. **C1 to C9 of [ADR-KY81](KY81-certify-spec-choices-of-the-agent.md) are accepted as recommended
   there** (questions 1 to 9 of section 14 of draft 2):
   - C1: the camera row has the result `partial`, and a camera in use has a result with a reason.
     Point 9 sets the form of the in-use result.
   - C2: "can you jpegs" means the camera's own JPEG frames, passed through unchanged in the capture
     path of the product.
   - C3: the quick settings check: manual -7, one live change to -8, a read-back at once and after
     1 s, and the image must get darker.
   - C4: the product restores the "before" values of each camera at its own close.
   - C5: the file `camera_evidence.json` in the package, with the states `verified` and `known-bad`.
     `verified` needs 3 full reports from 2 systems, or 1 maintainer report. A maintainer accepts each
     row in a pull request.
   - C6: on Linux and macOS, native capture is the default only for a camera model with a `verified`
     row, or after a local passed full run of that model. A `verified` OS alone turns on nothing
     (changed on 2026-11-20 by [ADR-F2KY](F2KY-rulings-of-the-user-after-the-third-consistency-check.md)). Elsewhere OpenCV stays, and the app prompts for a certify run
     of an unknown camera or OS.
   - C7: a camera that is not well after the run gets a cleanup row, and the app shows "Camera
     <name>: wedged, please replug".
   - C8: the disk benchmark in full: 1 GiB, 4 MiB blocks, fsync each second, at most 30 s, in the
     recording folder, deleted after, MB/s reported.
   - C9: on macOS the app asks the camera permission. Certify shows no dialog.
2. **The OpenCV fallback on unverified Linux and macOS is "for now".** The direction: when enough runs
   of native capture pass, OpenCV goes, and new OS versions wait behind the certify test. This is the
   direction, not a requirement of this step.
3. **A camera counts as checked one time for each model** (USB vendor id and product id) on this
   system. A second identical camera, or a replugged camera, is not checked again. The app checks an
   unchecked model when the person first asks the app to open it: freemocap shows a pop-up (about
   30 s). Plugging in alone starts nothing. With no camera detected, the camera rows read "not
   checked", and nothing fails.
4. **skellycam keeps the record of checked models** with its other local certify records.
   `certify_plan("quick")` returns, for the detected cameras, the models that are still unchecked.
   freemocap keeps no record.
5. **Cancel and progress.** `certify()` returns the finished rows on a cancel and marks the rest "not
   run". The progress callback is called with the name of a check before that check starts.
   freemocap writes it to a file for crash reports.
6. **Order inside the full run:** camera identity, modes and frame rates first; long sweeps next;
   checks that can break a camera last. A full run of skellycam of 6 to 11 minutes is accepted.
7. **The exposure rule of the product, which the certify checks must match.** "Auto" always means
   that SkellyCam finds a manual value by a one-shot search. A camera in Auto searches at every open,
   and when the person changes the frame rate. The camera's own auto exposure is never a mode. The
   text for a slow camera is "Camera is slow. Try adding more light". Nothing below 30 fps.
8. **Certify tests native capture only.** OpenCV needs no test.
9. **No in-use result of its own.** The owner of the contract reports these words of the user from
   the session of the contract: "in-use shouldn't be it's own status here just for cameras. skipped
   (busy) will do for both". Format 1.3.0 of `skellycertify` (commit
   [f7a1831](https://github.com/domisjustanumber/skellycertify/blob/f7a18315afb5828da71c9154c2bf0f8cb79bae7f/decisions/entries/D1PW-format-1-3-0.md),
   skellycertify ADR-D1PW, "Alternatives rejected") records the result: a camera that another program
   holds has the summary result `skipped` with the reason `busy`.

**The items of ADR-KY81 that these points rule.** Item 5 (the claims, `partial` and in use): C1, C2.
Item 6 (quick): C3, C4. Item 8 (the disk benchmark): C8. Item 10 (the cleanup row and the notice):
C7. Item 13 (the evidence file, its use, the prompt): C5, C6. Item 12, the macOS permission only: C9.
Item 2 (the phases): point 6 sets the order inside the full run. Point 9 replaces the "in use" row of
item 5. The other items of ADR-KY81, and the
parts of these items that the points do not name, stay `proposed`.

## Reason

The user gave these answers on 2026-11-20, after he read draft 2 and its 9 questions.

## Consequences

The choices of the agent for draft 3 are in
[ADR-8CP7](8CP7-certify-spec-draft-3-choices-of-the-agent.md). Format 1.3.0 of the contract holds
`partial`, `skipped` with `busy` and `cameras-busy`, so no rule of this entry waits for the contract.

## Open work

See [open-work.md](../open-work.md).
