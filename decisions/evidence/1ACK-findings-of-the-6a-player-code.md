# Findings of the 6a player code

This file holds the evidence of
[ADR-1ACK](../entries/1ACK-corrections-and-choices-of-the-6a-player-code.md).

Item 3: a scratch Electron 45.3.4 app (Chrome 156.0.8078.100) decoded the flat-block barcode JPEG of
the fixtures with the EXIF orientations 1 to 8. For orientation 6 the frame had `rotation` 90, coded
size 256 × 128 and display size 128 × 256, and `drawImage` turned it. The rule of item 3 gave
`rotation` 0 and `flip` false for each orientation (2026-11-20, Windows test machine).

Electron 45.3.4, harness of the 6a tests (2026-11-20): a `protocol.handle` handler that the main
process installs after a page loaded does not serve that page; the page keeps the handler of its
load. After a reload, the page client refused the 200 answer with the whole file and the 206 answer
with a wrong start, and it accepted the 200 answer with the exact length. In a never-shown harness
window under Playwright 1.65.1, `requestAnimationFrame` ran about once per second after a canvas
drew, also with `backgroundThrottling: false`; in a shown window, about 58 times per second. A
window that is shown inactive, with opacity 0 and no mouse events, ran at about 58 times per second.

Profile of the 6a player, first reading (2026-11-20, shown harness window, Electron 45.3.4, Chromium
JPEGs of about 190 kB at 1080p, other work on the machine; scratch marks in the code, not kept).
Medians at N = 1 and N = 4: range read 1.6 and 2.8 ms, `ImageDecoder` decode 2.7 and 3.7 ms, draw at
tile size 0.5 and 0.4 ms, overlay 0.1 ms or less. No EXIF undo ran (the JPEGs have no orientation tag).
The cameras decode at the same time. Seek to an image on each tile: p50 5.2 and 10.0 ms, p95 9.1 and
13 ms. During play, each tile got the image of k* at 100 % of the display refreshes at N = 4 and
N = 8. During a scrub at 90 frames/s, each tile drew 55 to 57 frames/s at N = 8. One 1-pixel
`getImageData` of a tile canvas took 2.1 to 4.5 ms. The barcode reader of the benchmark page makes
about 20 such calls for each tile at each check, so T-PLAY-66 to T-PLAY-68 measure that reader more
than the player.

Test corrections of 2026-11-20 (the supervisor allowed them): T-PLAY-14 (`fit_negative`: the source
frame numbers after row 61 go up, and k* = 60 is not checked, because row 61 is earlier than row 60
and so is the image at T_60 by section 7.3); T-PLAY-52 (the swap is read with a poll, after the
200 ms grid transition); T-PLAY-53 (F18 as today: the message goes away when each camera has drawn
its first image; section 10 asks only that it counts the drawn cameras); T-PLAY-55 (no check for the
byte 0xee, which the test pattern holds at byte 22); T-PLAY-59 (a reload after the handler variant);
the harness window (item above). `IconButton.tsx` and `ButtonSm.tsx` import `TooltipPosition` with
`import type`, so that the module `tsconfig.json` reports no error.
