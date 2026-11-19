# 4K7V — Phase 6a spec and test list: the canvas player for new takes (video only)

**Status:** proposed, 2026-11-19 (agent; waits for the user).

## Decision

[`specs/player.md`](../../specs/player.md) is proposed as the spec of step 6a, with its test list
T-PLAY-01 to T-PLAY-63 (35 unit, 15 component, 7 electron, 6 benchmark). It follows the decisions Y1
to Y7 of [ADR-J2BQ](J2BQ-phase-6-player-decisions-y1-to-y7.md), the earlier decisions that they cite,
the format spec of skellyfileformat (draft v2, commit d67679a) and the research evidence of branch
`dom/research`. The user reviews it before any code.

An agent made these choices where the sources leave a gap. Section 16 of the spec states each one in
full, and the body marks each one [agent n]:

1. Folder `skellycam-ui/src/player/` and its layout.
2. The boundary rule and its import scan.
3. Engine, tile and `PlayerTile` in the module; controls, grid and keys in the host.
4. Names of the interface, the state and the events.
5. Erasable TypeScript only; `.ts` imports.
6. Scheme `skellycam-take`; a token for each open.
7. The open: real path, root and media folder only, regular files only, an exact allow-list.
8. Device and inode check at the first read; cached handles.
9. The response table (206, 416, HEAD, `no-store`, CORS headers).
10. The page client accepts 206 with the asked start or 200 with the exact length.
11. Manifest read limit 16 MiB.
12. A snapshot at the open; no reload in 6a.
13. Two or more takes: open the first.
14. No audio, no folder files, no `<rec>`; only the result members that the player needs.
15. Reasons for a missing column, a wrong `frame`, a decreasing time, a broken fit.
16. Exactly one `V_MJPEG` track; the head read.
17. The SFF-759 check at each frame read and at the tail.
18. `BigInt` parse, then numbers.
19. T_k, the clock range, k*.
20. Step and frame seek set t = T_k.
21. Pause keeps t.
22. End and loop.
23. The image in a no-image row; N of a lost camera.
24. When a take is unfinished; where the mark goes.
25. Decode on the page main thread.
26. Canvas size, fit, label in the canvas.
27. Label parts and the timecode frame field.
28. The prefetch queue and range reads.
29. Newest wins.
30. Event rates.
31. "Rec: fps" from the nominal rate.
32. Shared grid and key code in the host; `CanvasTakePlayer.tsx`.
33. The TypeScript fixture builder and the flat-block JPEG encoder.
34. Benchmark JPEGs from the encoder of Chromium.
35. The test runners and npm scripts.
36. The workflow `player.yml`.
37. Pass thresholds and benchmark targets.
38. Read errors.
39. A junction for the link test on Windows.
40. The page gives the folder path.
41. The term "no-image row".
42. The proposed skellyfileformat texts P1 to P7.

Questions for the user (section 17 of the spec; "yes" accepts the recommendation):

- Q1: 6a routes a folder with a format sidecar to the new player, and 6c keeps the rest of the switch.
- Q2: the full reader result, the JavaScript test adapter and a conformance run wait for a later step.
- Q3: three more tile marks: a refused file, a damaged file, a read error.
- Q4: hide the sync warning of today for the new player.

## Reason

Y1 and the rule "spec and tests before code" need an agreed spec and test list before the code of
step 6a.

## Consequences

The spec proposes seven changes to skellyfileformat (P1 to P7). The user decides them in that
repository. P1 and P2 (rows with no image, a lost camera) also depend on the recorder spec, which
another branch writes.

## Open work

See [open-work.md](../open-work.md).
