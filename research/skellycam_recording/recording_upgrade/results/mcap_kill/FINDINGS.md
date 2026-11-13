# MCAP kill and throughput desk test (2026-11-13)

Provenance: a sub-agent ran this on 2026-11-13, 12:13–12:23 local, on Windows 11 with an i7-14700K (28 logical CPUs). It used Python 3.13.18, `mcap` 1.6.0, `mcap-protobuf-support` 0.6.0, `foxglove-schemas-protobuf` 0.4.0, protobuf 7.36.2, av 19.0.2, numpy 2.5.4, pillow 13.0.0, psutil 7.2.2, and the MCAP CLI 0.4.0 (`mcap-windows-amd64.exe`, SHA-256 `f4f983755fdbc08d7eddc2493ed2b29dc68abd6b411bf3bab6c89d3804d946de`). The main session saved the report after checking the summaries and the overhead arithmetic against the JSON files below. During the throughput run, system CPU averaged 11.4 % and peaked at 34 % [M]. Another desk test (Lichtblick) had two local HTTP servers running at the same time. Script: `scripts/mcap_kill/mcap_kill.py`, with subcommands `media`, `kill` and `throughput`. [M] = measured, [I] = inferred.

## Short answer

- **Kills lost nothing that had been flushed** [M]. There were 120 external `TerminateProcess` kills: 40 of a camera writer paced at 30 fps, 40 of an unpaced camera writer and 40 of a mic writer paced at real time. Every file streamed back as an exact prefix of the source. There were no CRC failures. `mcap recover` exited 0 with the same messages in 120/120.
- **No kill tore a record** [M]: 0 torn bytes in 120/120. The Python writer sends each chunk and its MessageIndex records in one `write()`.
- **The mic audio is sample-exact after a kill** [M]. 636 clicks in the recovered audio were all on the exact sample, after removing the 312-sample pre-skip. PyAV's `opus` decoder does not apply the pre-skip itself.
- **Throughput is not a concern** [M]. Four cameras (1080p-size JPEGs of about 163 KB at 30 fps) plus an Opus mic ran for 120 s with no late frames. Each process used 1.2–2.3 % of one core. The p99 time of `add_message` + `flush` was 0.44 ms or less.
- **One chunk per message costs about 224 B per message** [M]. For video that is 0.14 % of a frame. For Opus at 64 kbit/s (231 B packets) the mic file is 1.94 × its payload: about 80 MB/h instead of about 42 MB/h [I, arith].

## Method

- **Kills.** The child writer loops its source until it is killed. The parent waits a random time and then kills the writer's own PID with `TerminateProcess` (via psutil). A trial counts only if the exit code is non-zero. It was 15 in 120/120.
- **Ground truth.** After each `flush()` returns, the child appends its message count to a separate log file. The parent compares that count with three reads:
  - a streaming read, `NonSeekingReader(validate_crcs=True).iter_messages(log_time_order=False)`;
  - `StreamReader(emit_chunks=True)`, with each chunk's CRC checked again by hand;
  - its own walk of the record framing.
- **"Exact prefix"** means:
  - camera: `sequence` = i, the JPEG bytes are identical to the source frame, and the timestamps are as expected;
  - mic: the Opus bytes are identical to the source packet, and `log_time` = `timestamp` = BASE + i × 20 ms.
- **Media.**
  - Video: 30 distinct 1920×1080 JPEGs of 162,811–163,534 B each.
  - Audio: 120 s of a 440 Hz tone with a one-sample click every 9,601 samples, encoded with libopus at 64 kbit/s. That gives 6,001 packets of 231 B on average, with a pre-skip of 312.
- **Profile used** (test choices only, not decisions):
  - one MCAP file per process, protobuf;
  - camera frames as `foxglove.CompressedImage`, mic packets as `foxglove.CompressedAudio` Opus;
  - `compression=NONE`, `enable_data_crcs=True`, `flush()` after each message;
  - the mic channel metadata holds `sample_rate`, `channels`, `pre_skip`, `output_gain` and `opus_head`.

## Results

**Kill tests** (`kill_cam_paced.json`, `kill_cam_fast.json`, `kill_mic_paced.json`), all [M]:

| | Camera, paced 30 fps | Camera, unpaced | Mic, real time |
|---|---|---|---|
| Kill delay (s) | 0.34–5.91 | 0.08–0.85 | 0.45–5.90 |
| Messages recovered | 11–178 | 467–4,350 | 23–295 |
| Recovered minus logged | 0 in 40/40 | 0 in 31, +1 in 9 | 0 in 40/40 |
| Exact prefix | 40/40 | 40/40 | 40/40 |
| CRC failures | 0 | 0 | 0 |
| Torn bytes after the last complete record | 0 in 40/40 | 0 in 40/40 | 0 in 40/40 |
| `mcap recover` exit; same messages; `doctor` exits 0 on the output | 0; 40/40; 40/40 | 0; 40/40; 40/40 | 0; 40/40; 40/40 |
| `make_reader()` on the killed file | fails 40/40 (`RecordLengthLimitExceeded`) | fails 40/40 | fails 40/40 |

- Mic only: the channel metadata read back intact in 40/40, and 636 clicks were checked, each with a sample error of 0.
- "+1" means the kill landed after `flush()` returned but before the count reached the log. It is not a loss [I].

**Throughput, 120 s** (`throughput.json`), all [M]:

| Process | CPU (% of one core) | Write rate (MB/s) | `add_message` + `flush` p50 / p99 / max (ms) | Late frames | Messages | Overhead (B/message) | File size (bytes) |
|---|---|---|---|---|---|---|---|
| cam0 | 1.38 | 4.90 | 0.204 / 0.417 / 0.746 | 0 | 3,600 | 224.0 | 588,160,865 |
| cam1 | 1.24 | 4.90 | 0.204 / 0.395 / 1.726 | 0 | 3,600 | 224.0 | 588,160,865 |
| cam2 | 2.25 | 4.90 | 0.213 / 0.435 / 1.383 | 0 | 3,600 | 224.0 | 588,160,865 |
| cam3 | 1.68 | 4.90 | 0.202 / 0.390 / 1.845 | 0 | 3,600 | 224.0 | 588,160,865 |
| mic | 1.29 | 0.022 | 0.064 / 0.138 / 0.529 | 0 | 6,000 | 216.9 | 2,686,764 |

- Overhead counts the file size minus the raw payload. Measured against the protobuf-wrapped payload instead, it is 194.5 B per message.
- The maximum lateness was 2.1 ms. After a clean `finish()`, all 5 files open with the seeking reader, and each has as many chunks as messages. `mcap doctor` exits 0.

**A synthetic torn tail** (`throughput.json`, `truncated_copy_recover`) [M]: a copy of cam0 was cut at 60 % of its bytes. The cut leaves 2,161 complete chunks and 16,254 torn bytes.
- The streaming read gives 2,161 messages.
- `mcap recover` exits 3 ("ended in the middle of a record"; "Recovery was lossy") and writes a valid file with the same 2,161 messages.

## Problems found

1. **The writer process is a grandchild of `Popen`** [M]. A uv venv `python.exe` on Windows is a launcher; the real interpreter is its child. The test killed the PID that the writer reported for itself. The FLAC kill test (`flac_skau` FINDINGS §7) called `Popen.kill()`, which probably killed the launcher, so the writer died through the launcher's job object [I, not checked]. Those results still count as external kills, but the kill was less direct than that report says.
2. **Torn records were only tested synthetically** [M]. A process kill never split a write. A power loss or an OS crash can [I, not tested].
3. **A killed file needs the streaming path or `mcap recover`** [M]. The seeking reader fails on every killed file.
4. **Opus overhead with one chunk per packet** [M]: about the size of the payload at 64 kbit/s. A larger mic chunk would cut it, but a kill could then lose up to one chunk [I, not tested].

## Not done

- No power-loss, OS-crash, Linux or macOS test.
- No fsync.
- Memory use and `finish()` time for hour-long files were not measured. The Python writer keeps every chunk index in memory until `finish()`, which is about 108,000 per camera per hour [I].
- Test media were deleted.
