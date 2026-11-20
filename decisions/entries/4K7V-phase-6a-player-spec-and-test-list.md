# 4K7V — Phase 6a spec and test list: the canvas player for new takes (video only)

**Status:** superseded by [4D94](4D94-step-6a-choices-of-the-canvas-player.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-19 (agent; waits for the user)).

## Decision

[`specs/player.md`](../../specs/player.md), revision 2, is proposed as the spec of step 6a, with its
test list T-PLAY-01 to T-PLAY-72 (40 unit, 16 component, 10 electron, 6 benchmark). It follows the
decisions Y1 to Y7 of [ADR-J2BQ](J2BQ-phase-6-player-decisions-y1-to-y7.md), M1 to M10, L1 to L8 and the answers U1 and U2 of
[ADR-4HNY](4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md), the earlier decisions that
they cite, the format spec of skellyfileformat (draft v2, commit d67679a) and the research evidence of
branch `dom/research`. Revision 2 also applies the faults of an independent review (section 15.2 of
the spec). The user reviews it before any code.

An agent made these choices where the sources leave a gap. Section 16 of the spec states each one in
full, and the body marks each one [agent n]:

1. Folder `skellycam-ui/src/player/` and its layout.
2. The boundary rule, its scan, `import type` and `verbatimModuleSyntax`.
3. Engine and tile in the module; controls, grid and keys in the host; one tile binding.
4. Names of the interface, the state and the events.
5. Scheme `skellycam-take`; a lower-case hex token for each open, tied to its window.
6. The recordings folder from the backend rule; picked folders kept by the main process.
7. The open: root and media folder only, regular files only, an exact allow-list, `bigint` identities.
8. Handles only for camera files; other reads open, read and close.
9. The response table (GET, `bytes=a-b`, 416, 405, the snapshot clamp, headers).
10. The page client accepts 206 with the asked start or 200 with the exact length.
11. Manifest read limit 16 MiB.
12. A snapshot at the open; no reload in 6a.
13. Two or more takes: open the first.
14. No audio, no folder files, no `<rec>`.
15. Cases that the format leaves open (missing column, `frame`, a decreasing time, a broken fit).
16. Head and tail read sizes.
17. The SFF-759 check at each frame read and at the tail.
18. `BigInt` parse, then numbers.
19. T_k, the clock range, k* as state.
20. The image from real rows by time, the mark from row k*.
21. A dead camera with no manifest; a trailing run with a manifest is damage.
22. Where the "unfinished" and "damaged" marks show.
23. End and loop.
24. Canvas size, fit, overlay in the canvas, the canvas title.
25. Tile update details: no new image, the promise result, one mark in a fixed order.
26. Default texts and places of the overlay parts.
27. The prefetch queue and range reads.
28. Newest wins.
29. Event rates.
30. "Rec: fps" from the nominal rate.
31. The host view `CanvasTakePlayer.tsx` and the route through `isTakeFolder`.
32. The TypeScript fixture builder, the flat-block JPEG encoder with the Annex K tables, placeholders.
33. Benchmark JPEGs from the encoder of Chromium.
34. The test runners, the harness hooks and npm scripts.
35. The workflow `player.yml`.
36. Pass thresholds and benchmark targets.
37. Read errors.
38. A junction for the link test on Windows.
39. The three items that the player gives to the merged format list.

The spec has no open question. The user answered the four questions of revision 1 with L1 to L4.

## Reason

Y1 and the rule "spec and tests before code" need an agreed spec and test list before the code of
step 6a.

## Consequences

The merged list of proposed skellyfileformat changes is in the recorder spec (branch `dom/recorder`).
The player spec contributes three items to it and follows it when it is final.

## Open work

See [open-work.md](../open-work.md).
