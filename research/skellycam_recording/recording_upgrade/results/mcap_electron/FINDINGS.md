# MCAP and Opus in Electron: desk test (2026-11-13)

Provenance: a sub-agent ran this on 2026-11-13 on Windows 11 with an i7-14700K, with Electron 35.7.5 (Chrome 134.0.6998.205; the skellycam-ui binary, used read-only), `@mcap/core` 2.4.0 (exact pin; brings `@foxglove/crc` 0.0.3), and Python 3.13 with mcap 1.6.0, mcap-protobuf-support 0.6.0, foxglove-schemas-protobuf 0.4.0, av 19.0.2 and numpy 2.5.4. There were two identical full runs; ranges cover both. Total CPU during the runs averaged 18.1 % and 11.2 % (idle about 11 %; `run_meta.json`). The main session checked the seek, Opus, real-time and truncation figures against `electron_run1.json` and `electron_run2.json` before saving. Scripts: `scripts/mcap_electron/` (`gen_media.py`, `main.cjs`, `page.html`, `page.js`, `run_electron.ps1`, `analyze_audio.py`). Transport: Electron `protocol.handle` with the single-range handler of the range_transport study (`skr://`); the page loads from `file://`. [M] = measured, [I] = inferred, [arith] = arithmetic.

## Short answer

- **Camera MCAP works in the player path** [M]:
  - Range reads through an `IReadable` work, and `ImageDecoder` decodes every JPEG.
  - 100/100 random seeks returned the right frame.
  - 60 s of 30 fps playback with decode missed no frame.
- **The summary locates every frame without reading a chunk** when there is one chunk per frame [M]. Then a frame costs 1 request; `readMessages` uses 2. The summary does not hold `sequence`. The Nth chunk is the Nth frame in the file, not camera frame number N [M/I].
- **Opus decodes in Chromium, with or without a `description`** [M]:
  - No `description`: nothing is dropped, and the output timestamps match `log_time` exactly.
  - `description` = OpusHead: the decoder drops 312 samples after every configure but does not move the timestamps. The audio then comes out 6.5 ms early.
  - A seek needs 80 ms of pre-roll.
- **Truncated file** [M]: `McapIndexedReader.Initialize` throws. `McapStreamReader` reads every complete chunk and raises no error at the cut. The caller must check `done()`.

## Task 1: Range reads and ImageDecoder

Test file: 281.9 MB, 1,800 frames of 1920×1080 JPEG (149–161 KB), one chunk per frame (`media.json`).

| Measure | Result |
|---|---|
| `Initialize` | 5 requests, 150,281 B (summary 150,215 B, about 83.5 B per chunk index). 31 ms cold, then 3.8–5.7 ms [M]. That is about 9 MB of summary per camera-hour at 30 fps, read in one request [arith] |
| Random frame via `readMessages` | 2 requests. Fetch p50 1.8–1.9 ms, p99 7.9–11.2 ms [M] |
| Random frame via a table built from the chunk indexes | 1 request. Fetch p50 1.2–1.3 ms, p99 5.6–7.0 ms [M] |
| 100 random seeks | 100/100 correct by both methods, in both runs. Checked: sequence, log_time, CRC and the frame code in the pixels [M] |
| `ImageDecoder` | 1920×1080 `I420`, decode p50 2.5–2.6 ms [M] |
| Sequential, fetch only | Table: 823–978 fps (129–153 MB/s). `readMessages`: 560–692 fps [M] |
| Real time 30 fps, 60 s, with decode | 1,800/1,800 correct. Done after due time: p50 8.6–8.9 ms, max 17–29 ms. 0 frames late past the next frame [M] |

## Task 2: Finding frame N

| Method | Cost | Gives |
|---|---|---|
| Summary only: chunk indexes sorted by time | 0 requests, 0.028 ms | Offset and length of each chunk. With one message per chunk, the Nth chunk is the Nth frame of the file [M] |
| Every MessageIndex record | 1,800 × 31 B. 297–306 ms with 16 in parallel | The message offset inside its chunk [M] |
| Every message header | 1,800 small reads. 292–301 ms with 16 in parallel | The real `sequence` [M] |
| One streaming pass | 35 requests, the whole 282 MB, 910–930 ms | Every message with its sequence [M] |

A ChunkIndex holds only times, offsets, lengths and compression, and no `sequence` (`chunk_index_fields`) [M]. With dropped frames, camera frame numbers need about 108,000 small reads per camera-hour (about 18 s with 16 in parallel) or a full scan [arith].

## Task 3: Opus in WebCodecs (Chrome 134)

The test signal was 60 s, 3,001 packets, pre-skip 312, with `log_time` = the time of the first decoded sample of each packet (packet 0 is stamped 6.5 ms before the first input sample). Reading all packets took 2 requests and 9 ms. Decoding all 60 s took about 135 ms [M].

| | (a) no `description` | (b) `description` = OpusHead |
|---|---|---|
| `isConfigSupported` | true | true |
| Decodes raw packets | yes | yes (not treated as Ogg pages) |
| Decoded samples | 2,880,960 (all) | 2,880,648 (312 fewer) |
| Click time from the AudioData timestamps against true time | 0 samples | −312 samples (−6.5 ms) |
| Output timestamps | back to back | back to back from the first input timestamp: generated from sample counts, not taken from each packet |

All [M].

Seek test: 20 random targets, a new decoder each time, comparing the 80 ms after the target with a full decode. Shift was 0 in every trial [M].

| | RMS difference against the full decode, median relative to the signal |
|---|---|
| no `description`, no pre-roll | −8.3 dB |
| no `description`, 4 packets (80 ms) of pre-roll discarded | −30.4 dB |
| OpusHead, no pre-roll | −9.9 dB |
| OpusHead, 4 packets of pre-roll | −31.9 dB |

The codec's own error against the input is about −17.9 dB. So without pre-roll the seek error is about 10 dB louder than the codec error (probably audible). With 80 ms of pre-roll it is about 12 dB quieter (probably inaudible) [I; nobody listened].

## Task 4: Truncated file (cut at 60 %, partway through a chunk)

- `McapIndexedReader.Initialize` throws "Expected MCAP magic …" after 4 requests: it reads the end of the file first [M].
- `McapStreamReader` (8 MiB ranges) reads 1,080 messages, which is every complete chunk. All CRCs pass and the sequence has no gaps. It raises no exception. At the end `done()` is false and `bytesRemaining()` is 93,288 (the partial chunk). 22 requests, 547–624 ms [M].

## Problems found

1. `readMessages` spends 2 requests per frame. Reading the chunk straight from the chunk index takes 1 and is 30–40 % faster for fetching alone [M].
2. `Initialize` reads the whole summary in one request: about 9 MB per camera-hour with one chunk per frame [arith].
3. The summary has no frame `sequence` [M].
4. On a truncated file the stream reader stops without an error [M].
5. With OpusHead as `description`, Chromium drops the pre-skip without moving the timestamps, and does it again after every configure [M]. Without a description the timing is exact [M].

## Not tested

- Electron 45, an HTTP transport, the low-end laptop.
- Several cameras at once, real camera JPEGs, compressed chunks, dropped frames.
- Gaps or jitter in the audio timestamps, and `AudioDecoder.reset()` without a configure.
- A file cut by a writer kill (this was a byte cut only), and a bundled renderer (`nodeIntegration` was on).
- Listening to the audio.
