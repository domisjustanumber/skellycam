# MCAP as the skellycam recording format: claims checked against current releases (2026-11-13)

Context: Dom asked (2026-11-13) whether an existing standard could replace the skellyfileformat design, now that browser playback is not native anyway and VLC playback is only a nice-to-have. MCAP was the candidate (see `prior_art_sync_recording_20261112.md`). GigE Vision support is planned later; raw GigE pixel formats are deferred (Dom: "the spec can handle it / has options"). Dom is not tied to FLAC.

Provenance: main session. [M] = measured here with `recording_upgrade/scripts/mcap_check/check_mcap.py` (synthetic 28,000 B random payloads, 300 messages; run with `uv run --no-project --python 3.13 --with mcap==1.6.0 --with mcap-protobuf-support==0.6.0 --with foxglove-schemas-protobuf==0.4.0 python -I check_mcap.py <outdir>`). [S] = read from a primary source on the date above. [arith] = arithmetic.

## Versions checked

| Item | Version | Date |
|---|---|---|
| Python `mcap` | 1.6.0 (latest on PyPI) | 2026-10-19 |
| `mcap-protobuf-support` | 0.6.0 | 2026-10-19 |
| `foxglove-schemas-protobuf` | 0.4.0 (MIT) | 2026-07-29 |
| `protobuf` (pulled in) | 7.36.2 | |
| npm `@mcap/core` | 2.4.0 (MIT) | 2026-10-26 |
| MCAP CLI | 0.4.0 (now Rust, `rust/cli`; Windows x64/arm64 binaries) | 2026-10-16 |
| Others released | C++ 2.2.0, Rust 0.26.0, Go 1.10.0, Swift (in repo) | 2026-10 |

## Results

| Claim | Result |
|---|---|
| Message has `channel_id` u16, `sequence` u32 ("optional counter for detecting gaps"), `log_time` u64 ns, `publish_time` u64 ns | [S] spec; [M] round-trip; `sequence = 2**32` is rejected by the writer |
| Message records have no CRC; Chunk has `uncompressed_crc`; DataEnd and Footer have optional CRCs | [S] spec. Python writer defaults: `enable_crcs=True` (chunk CRCs), `enable_data_crcs=False` (no DataEnd CRC unless enabled) [M] |
| Chunk compression can be none; options none, lz4, zstd | [S] spec; [M] `CompressionType` = NONE, LZ4, ZSTD. Python default is ZSTD with `chunk_size=1048576` |
| Message Index offsets are relative to the uncompressed chunk records | [S] spec; [M] 300/300 offsets land on a Message opcode |
| `Writer.flush()` ends the chunk in progress | [S] docstring; [M] flushing after each message gives 300 chunks for 300 messages |
| Per-frame overhead, one chunk per frame, no compression | [M] 196 B/frame raw payload; 220 B/frame wrapped in protobuf `foxglove.CompressedImage`. Unchunked: 33 B/frame (no index). At 28 KB frames 0.7–0.8 %; at 1080p30 passthrough (4.9 MB/s ÷ 30 ≈ 163 KB/frame, `intra_compare` FINDINGS, inferred) about 0.13 % [arith] |
| Metadata (name + string map) and Attachment (name, media type, data) records | [S] spec (Attachments not allowed inside chunks); [M] written and read back |
| Truncated file (cut at 60 % of a chunk-per-frame file) | [M] `StreamReader(emit_chunks=True)`: 180/300 chunks, i.e. every complete chunk before the cut. `NonSeekingReader.iter_messages(log_time_order=False)`: 180/300 messages. **`make_reader()` (seeking, reads the footer) and `NonSeekingReader.iter_messages()` with the default `log_time_order=True`: 0 messages.** A reader of a crashed file must use the streaming path or `mcap recover`. Not a process-kill test |
| `mcap recover` | [S] CLI 0.4.0 `rust/cli/src/commands/recover.rs`: salvages what it can into a valid file, rebuilds indexes and CRCs, counts discarded records; exit 0 clean, 3 lossy (truncated mid-record or records discarded), 1 hard failure. `doctor` and `merge` also exist |
| JS random access for the player | [S] `@mcap/core` 2.4.0 `McapIndexedReader.Initialize({ readable })` with `IReadable { size(): Promise<bigint>; read(offset: bigint, size: bigint): Promise<Uint8Array> }`, which a Range-fetch adapter can implement. JS also has `McapWriter.InitializeForAppending`. Not run in Electron |
| `foxglove.CompressedImage` = `timestamp`, `frame_id`, `data`, `format` (`jpeg` allowed) | [S] docs; [M] protobuf descriptor |
| `foxglove.RawAudio` = `timestamp` (start of block), `data`, `format`, `sample_rate`, `number_of_channels`; formats `pcm-s16`, `g711-alaw`, `g711-ulaw` only; samples interleaved, little-endian; used by Foxglove's Audio panel | [S] docs; [M] descriptor |
| `foxglove.RawImage` encodings: 8-bit Bayer ×4, `mono8`, `mono16`, no packed 10/12-bit | [S] docs. ROS `sensor_msgs` also defines `bayer_*16` [S] `image_encodings.hpp` (rolling) |
| Foxglove opens several MCAP files as one timeline | [S] Foxglove docs/blog: files opened together merge into one source (same format; same schema per topic); equivalent to `mcap merge` |
| rosbag2's default storage is MCAP | [S] rosbag2 README: "The default is `mcap`". The distribution where it became the default was not checked |
| Spec licence | [S] The spec page states none; the spec source (`website/docs/spec/index.md`) is in the repo, whose root LICENSE is MIT. The magic's version byte is ASCII `0` |
| ffmpeg cannot read MCAP | [M] ffmpeg 9.0.2 lists no mcap format. VLC and OpenCV not checked (OpenCV's file reading goes through ffmpeg here) |
| G.711 | [S] ITU-T G.711 is "Pulse code modulation (PCM) of voice frequencies" (11/88); Wikipedia: 8 kHz sampling, 8-bit companded samples (μ-law from 14-bit, A-law from 13-bit linear), 64 kbit/s, 300–3400 Hz band. Telephone quality |
| skellycam mic sample format | Our audio tests encode s16 (`flac_skau` FINDINGS line 19), so `pcm-s16` loses nothing compared with today |

Withdrawn (not verified): "ROS 2 GigE camera drivers publish Bayer images into rosbag2".

## Audio arithmetic

`pcm-s16` at 48 kHz: 96,000 B/s per channel = 0.35 GB/h mono, 0.69 GB/h stereo [arith]. Against four 1080p30 MJPEG cameras at 17.7 GB/h each (inferred, `intra_compare` FINDINGS; per-camera only, not for comparing codecs) = 70.8 GB/h, that is 0.5 % (mono) to 1 % (stereo).

## Decisions (Dom, 2026-11-13)

- **Lichtblick, not Foxglove, is the test reference viewer.** VLC compatibility is dropped.

## Lichtblick and audio

- Lichtblick v1.30.0 (2026-10-22; repo licence reported by GitHub as NOASSERTION, project docs say MPL-2.0) has **no Audio panel and no audio code** [S: git tree at tag v1.30.0].
- Open, unmerged PR #1301 (opened 2026-08-19, last updated 2026-09-28, no review decision; re-opens #1141) adds an Audio panel: `foxglove.RawAudio` auto-detect (`pcm-s16`), manual PCM Float32/Int16 LE, and WAV/MP3/OGG/AAC/FLAC through `AudioContext.decodeAudioData`, WebM through MSE [S: PR body]. Not built or run here.

## Compressed audio options

`foxglove.CompressedAudio` = `timestamp` (start of chunk), `data`, `format` only: no sample rate, channel count or encoder delay field [S docs; M descriptor in foxglove-schemas-protobuf 0.4.0]. Formats: `opus` (one raw packet per message, mono/stereo), `mp4a.40.2` (one AAC-LC ADTS frame per message), `g726-16/24/32/40` and `aal2-g726-*` (8 kHz mono) [S].

Encoder delay in PyAV 19.0.2 (libavcodec 63.1.102) at 48 kHz mono [M]: libopus 312 samples (6.5 ms), frame 960; aac 1024 samples, frame 1024; libmp3lame 1105; flac 0; g726 0 (8 kHz). libvorbis is not in the PyAV wheel.

| Format | In a standard schema? | Lossless? | Royalty status [S] |
|---|---|---|---|
| `pcm-s16` (RawAudio) | yes | yes (no codec) | none needed |
| Opus | CompressedAudio | no | royalty-free: Xiph.Org, Broadcom and Microsoft grant no-charge patent licences (defensive termination); reference code BSD-3. Qualcomm, Huawei, France Telecom and Ericsson filed IPR disclosures with possibly royalty-bearing terms; Xiph says counsel advised these are not needed |
| AAC-LC | CompressedAudio | no | **not free**: Via LA programme active, encoder/decoder end-user products pay $0.98/unit for the first 500k (falling to $0.10), $15,000 initial fee ($1,000 small entity); no fee for distributing AAC bitstreams |
| G.726 | CompressedAudio | no | not checked (1990 ITU ADPCM); telephone band, 8 kHz |
| FLAC | no (custom schema) | yes | royalty-free (RFC 9639) |
| MP3 | no | no | Technicolor/Fraunhofer programme ended 2017-04-23 as the last listed patent expired; Fraunhofer notes some implementation-specific patents may remain |

## Dom 2026-11-13: Opus preferred. Review of mrkbac/lichtblick PR #116 (Audio panel)

[S] = read from the PR and its source at merge commit `70f5900b7a9ecc9b2b223a955615e1abd6220245`. Not built or run.

- **Where it lives:** `mrkbac/lichtblick`, a personal copy (GitHub: not a fork, 0 stars, no releases, default branch `licht`). The author opened and merged the PR within 30 minutes on 2026-11-06; the only review was the CodeRabbit bot. mrkbac is not in upstream's contributor list; one unrelated upstream PR (#1383) is open. Upstream's own audio PR #1301 is still open.
- **It defines no schema.** It reads existing ones: auto-selects topics with `foxglove.RawAudio` or `audio_common_msgs/AudioData(Stamped)`; any other topic with `data` + `format` can be picked by hand. **`foxglove.CompressedAudio` is not in the auto-select list.**
- **Opus:** decoded with WebCodecs `AudioDecoder` (`codec: "opus"`, `sampleRate` and `numberOfChannels` from the message or the panel settings; no `description`, so raw packets and no pre-skip handling). `CompressedAudio` carries no rate or channel fields, so the panel falls back to its defaults, **16000 Hz, 1 channel**, unless changed in the panel settings.
- **Timing:** each message is scheduled from `event.receiveTime` (the MCAP `log_time`), not from the message's `timestamp` field. Playback runs **200 ms behind the playhead** (jitter buffer, `LATENCY_SEC`), plays chunks back to back and re-syncs only when it drifts more than 150 ms (`MAX_DRIFT_SEC`). Pause, seek and speed are followed. Inferred from code: audio sounds about 200 ms after the matching image; good for listening, not for judging A/V sync.

**Proposed audio channel for the profile:** `foxglove.CompressedAudio`, `format: "opus"`, one raw 20 ms Opus packet (960 samples at 48 kHz) per message, `log_time` = time of the packet's first sample on the take's host clock; a Metadata record holds `sample_rate`, `channels` and `pre_skip` (312 with libopus in PyAV 19.0.2). Not `RawAudio` with `format: "opus"`: the panel would auto-select it, but RawAudio is defined for PCM/G.711 only.

## Other open-source Opus schemas (checked 2026-11-13)

| Source | What it defines for Opus |
|---|---|
| `foxglove.CompressedAudio` (MIT; protobuf, FlatBuffers, ROS 2 `foxglove_msgs/msg/CompressedAudio`, JSON, OMG IDL) | `format: "opus"`, one raw packet per message, ~20 ms, mono/stereo; no rate, channel or pre-skip fields [S] |
| ROS 2 `audio_common_msgs` (ros-drivers, `ros2` branch) | `AudioData { uint8[] data }`, `AudioDataStamped { header, audio }`, `AudioInfo { channels, sample_rate, sample_format, bitrate, coding_format ("e.g. WAVE, MP3") }`; nothing Opus-specific [S, msg files] |
| mgonzs13/audio_common (ROS 2) | PCM only: typed sample arrays + `AudioInfo { format, channels, rate, chunk }` [S] |
| Rerun MCAP support | No audio schemas listed [S] |
| RFC 7845 `OpusHead` (Ogg) | The metadata every container copies: version, channel count, pre-skip (48 kHz samples), input sample rate, output gain (Q7.8 dB), mapping family (0 = mono/stereo) [S] |
| Matroska `A_OPUS` | CodecPrivate MUST be `OpusHead`; CodecDelay MUST = pre-skip × 10^9 / 48000; SeekPreRoll SHOULD = 80 ms [S] |
| WebCodecs Opus registration | `description` may be an `OpusHead` (then the stream "is assumed to be in ogg format" and its pre-skip is used); absent = raw packets, pre-skip 0 [S] |

MCAP Channel records carry a `metadata` string map (Python `register_channel(..., metadata: Dict[str, str])`) [M signature], a natural home for the `OpusHead` fields.

## Not done

No process-kill test of an MCAP writer, no Electron Range-read test, no run of the `mcap` CLI binary, no real camera frames.
