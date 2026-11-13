# MCAP single-writer desk test (2026-11-13)

Provenance: a sub-agent ran this on 2026-11-13, 12:36–12:45 local, on Windows 11 with an i7-14700K and 63.7 GB RAM. It used Python 3.13.18 with mcap 1.6.0, mcap-protobuf-support 0.6.0, foxglove-schemas-protobuf 0.4.0, protobuf 7.36.2, numpy 2.5.4, psutil 7.2.2, av 19.0.2 and pillow 13.0.0; the MCAP CLI 0.4.0; and Electron 35.7.5 (Chrome 134.0.6998.205) with `@mcap/core` 2.4.0. Free disk was 692 GiB. The Lichtblick test's headless browser was busy before real-time run (a): system CPU averaged 16.9 % during (a) and 7.8 % during (b). The main session checked the scale, real-time and kill figures against the JSON files before saving. Scripts: `scripts/mcap_single_writer/` (`msw.py` with subcommands `scale`, `realtime`, `kill` and `selftest`; Electron files adapted from `scripts/mcap_electron/`). [M] = measured, [I] = inferred.

One MCAP file and one writer process for the whole take:
- protobuf;
- 16 cameras as `foxglove.CompressedImage` plus the mic as `foxglove.CompressedAudio` Opus;
- `compression=NONE`, `enable_data_crcs=True`;
- messages written in arrival order.

Chunking strategies:
- (a) one chunk per message;
- (b) one chunk per 33 ms window, holding that window's frames from every camera plus its audio;
- (c) one chunk per 100 ms window;
- (d) 1 MiB size-based chunks, for reference only.

## Short answer

- **One writer process keeps up with 16 real-size cameras** [M]: 16 × 163 KB JPEG at 30 fps plus Opus, 78.4 MB/s, at 14.2 % (a) and 22.0 % (b) of one core. No frame was later than one period.
- **Writer memory, the summary size and open time scale with the number of chunks**. For 16 cameras over 1 hour [M]:

| | (a) per message | (b) 33 ms window | (c) 100 ms window | (d) 1 MiB |
|---|---|---|---|---|
| Chunks | 1,908,000 | 108,000 | 36,000 | 3,457 |
| Writer peak working set | 1,440 MiB | 286 MiB | 133 MiB | 59 MiB |
| `finish()` | 3.36 s | 0.59 s | 0.21 s | 0.015 s |
| Summary | 158.4 MB | 26.2 MB | 8.75 MB | 0.84 MB |
| Electron `Initialize` (3 runs) | 0.75–1.0 s | 0.18–0.28 s | 0.05–0.09 s | not run |
| Renderer JS heap after `Initialize` | +502 MiB | +95 MiB | +32 MiB | not run |
| Per-camera frame table from summary only | 0.1 s, 0 reads | needs 108,000 MessageIndex reads (20.3 s) | 36,000 reads (6.1 s) | not run |
| Overhead per message | 223 B | 107 B | 86 B | 77 B |

- **A killed single writer with (b) loses only the open window** [M]. In 30/30 kills there was 0 loss of flushed data, the file was an exact prefix ending on a window boundary, there were 0 CRC failures and 0 torn bytes, and `mcap recover` exited 0 with the same messages. Messages that had arrived but were not yet on disk: 16–18 (one window) in 29 trials, 34 in 1.

## Details

**Scale runs** (unpaced, 2 KB dummy frames, 330 B dummy Opus; `scale_16cam_{a,b,c,d}.json`, `scale_4cam_{a,b}.json`) [M]:
- Writer memory grows linearly with chunks: about 616 B per chunk for (a), about 1.8–2.0 KB per window chunk for (b) and (c).
- `finish()` also builds the whole summary in memory: about 274 MiB above the pre-`finish()` level for (a).
- A ChunkIndex is 83 B with one channel and 243 B with 17 channels (16 cameras plus the mic).
- For 4 cameras over 1 hour: (a) has a 50.8 MB summary and a 495 MiB peak; (b) has 13.3 MB and 155 MiB.

**Electron** (`electron_16cam_{a,b,c}.json`, `electron_realsize_60s_{a,b}.json`) [M]:
- With a frame table and an exact-range read, one random frame costs 1 request of that frame only, in every strategy (0.8–0.9 ms at real size).
- Reading the whole window instead costs 2.6 MB at real size for (b) (6.9 ms p50). The library's `readMessages` does the same, and on (a) it takes 20.9 ms p50 because version 2.4.0 loops over every chunk index on each call [I, from the library source].
- Building the table from MessageIndex reads (b, c) added 258–282 MiB of renderer private memory outside the JS heap, probably fetch buffers [I, not checked].
- The "cold" open was not cold: the files had just been written and were in the OS cache [I].

**Real-time runs, 60 s** (`realtime_16cam_{a,b}.json`) [M]:

| | (a) | (b) |
|---|---|---|
| Writer CPU (% of one core) | 14.2 | 22.0 |
| Write rate | 78.47 MB/s | 78.41 MB/s |
| Flush latency p50/p99/max | per message: 0.16/0.69/2.0 ms | per window: 3.2/7.8/12.5 ms |
| Camera lateness p99/max (queueing included) | 8.9/13.4 ms | 11.9/17.6 ms |
| Frames late past one period | 0 | 0 |

The background load differed between the two runs, so the CPU comparison is not clean. Neither run used fsync.

**Kill test, (b)** (`kill_b.json`): 30 `TerminateProcess` kills of the writer's own PID (on Windows the uv venv `python.exe` is a launcher), 16 cameras of 2 KB plus the mic, paced, kill delay 0.35–5.85 s. Results are in the short answer above [M].

## Not done

- No Electron run on (d) or on the 4-camera files.
- No compressed chunks, no fsync, no writer queue design, no real-size kill test.
- No Linux, macOS or power-loss test.
- Large media files were deleted.
