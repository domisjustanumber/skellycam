# VHD3 — Answers of the owner to Q694, Q717 and Q718: WebCodecs for H.264, the WASM fallback, 8-bit 4:2:0 H.264 later

**Status:** accepted, 2026-11-24 (user; the coordinator asked the questions and relayed the answers).

## Decision

The words of the owner on 2026-11-24: "Q694, Q717, Q718 yes". Earlier the same day, on Q694, he
said: "no I want to pick something now and stick with it for future phases. WebCodecs seems to be the
way to go". The questions that he answered "yes":

1. **Q694.** "Decode H.264 with WebCodecs in every phase, and use the WebAssembly decoder for
   `mp4v`?"
2. **Q717.** "Keep the H.264 decoder in our WebAssembly build, and switch a tile to it when WebCodecs
   refuses the file or fails?"
3. **Q718.** "Fix this now as the format of the later compression stage, so that GPU decode always
   applies?" Context added by the coordinator when he relayed the question, not in the quote:
   "this" is "Phase 2 writes 8-bit 4:2:0 H.264".

## Reason

The answers of the owner.
