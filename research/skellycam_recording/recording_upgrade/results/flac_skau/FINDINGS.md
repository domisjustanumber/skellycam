# FLAC packet offsets, and embedding the `.skau` timing sidecar

2026-11-12, Gerald (Windows 11, i7-14700K). Follows Dom's decision (2026-11-12): **FLAC is the default audio codec** for skellycam's microphone file and for skellysync's per-camera audio. Context: `results/audio_skellycam/FINDINGS.md`, `results/audio_skellysync/FINDINGS.md`, `results/sidecar_embedding/FINDINGS.md`. Scripts: `scripts/flac_skau/`. Test media were synthetic (noise + irregular clicks, 48 kHz, 16-bit, 30 s) and stayed in the scratchpad.

**Labels:** [M] measured (result file), [S] primary source, [C] code read, [I] inferred, [NV] not verified.

**Versions:** PyAV 19.0.2 (FFmpeg 9.0.2), `skellycam-phase1` venv; FFmpeg CLI 9.0.2; VLC 3.0.24; Electron 35.7.5 (Chrome 134) and 45.2.3 (Chrome 156).

## 0. Answers
| Question | Answer |
|---|---|
| Can each FLAC packet's byte offset be known while writing? | **Yes.** Native FLAC with `frame_size=1024` and `flush_packets=1`: packet i sits at header length + the sum of earlier packet sizes (1,408/1,408, mono and stereo), and after `mux(i)` the file ends exactly at packet i. No packet is held back, unlike Matroska [M] (§1). |
| Does that live index survive a hard kill? | **Yes.** Every index record matched the killed file's bytes (6/6 kills). A kill between the mux and the index write leaves exactly one frame on disk that isn't indexed [M] (§2). |
| Can `.skau` be embedded in the final file the way the sidecar is in the MKV? | **Yes, by making the final file Matroska audio (`.mka`).** At finalisation the native `.flac` is stream-copied into `.mka` (every FLAC frame byte-identical, decoded audio identical) and the `.skau` is appended as an attachment with the same appender. Players are unaffected, and the locator finds it [M] (§3). |
| Why not embed it in native FLAC? | Metadata blocks must come **before** the audio frames, and each block's length field is 24 bits (16 MB max) [S, RFC 9639 §8.1]. Embedding would mean rewriting the whole file, splitting `.skau` (8.1 MB/h plus the packet table) across blocks for long recordings, and registering an APPLICATION id. There is also a measured reason to prefer `.mka`: VLC drops the last 1,280 samples of a native `.flac` (§4). |
| Does the player decode FLAC by offset? | **Yes,** with WebCodecs `AudioDecoder`, codec `flac`, `description` = `fLaC` + STREAMINFO: whole-file and cold start at packet 700 (no earlier context), in E35 and E45, for both the `.flac` and the `.mka` [M] (§4). |

## 1. Offsets while writing (F1, `flac_skau.json`)
Writer: PyAV encodes 1,024-sample s16 blocks with pts = sample count and muxes each packet as it comes, as the recorder would.

| | Mono | Stereo |
|---|---|---|
| Packets from the encoder | 1,408 (1,407 frames + 1 empty flush packet) | same |
| Header length on disk after the first mux / after close | 8,286 / 8,286 | 8,286 / 8,286 |
| Metadata blocks | STREAMINFO 34 B, VORBIS_COMMENT 44 B, PADDING 8,192 B | same |
| Packet at header + sum(earlier sizes), byte-identical | 1,408/1,408 | 1,408/1,408 |
| File ends exactly at the packet just muxed | 1,408/1,408 | 1,408/1,408 |
| Last packet ends at EOF; decoded = source | yes; yes | yes; yes |

- The encoder's final flush returns one **empty** packet: 1,408 encoder packets against 1,407 demuxed, while every offset and the end of file match [M]. It probably carries the updated STREAMINFO as side data [I]. The index must skip zero-size packets.
- At close FFmpeg rewrites STREAMINFO in place; the header length doesn't change [M].
- Contrast: in Matroska, FFmpeg holds back one packet, so live offsets lag one frame (sidecar FINDINGS §6.1).

## 2. Live index under hard kills (F2, `flac_skau.json`)
The child writes a 16-byte record (offset, size, CRC-32) to an index file after each mux and flushes it. It then calls `os._exit(1)` either right after the record (3 kills) or between the mux and the record (3 kills).

| Kill | Index records | All CRCs match the file | FLAC frames on disk | On disk but not indexed |
|---|---|---|---|---|
| after packet 40 / 137 / 300 | 40 / 137 / 300 | yes | 40 / 137 / 300 | 0 |
| between mux 41 / 138 / 301 and its record | 40 / 137 / 300 | yes | 41 / 138 / 301 | 1 (1,142–1,157 bytes after the last indexed frame) |

So recovery trusts the index and parses at most one more FLAC frame after its end [M]. External `TerminateProcess` timing wasn't tried here. The audio study's kills found the same loss for both methods (`audio_skellycam/FINDINGS.md` §2.2).

## 3. Finalisation into `.mka` with the `.skau` attached (F3; `flac_skau.json`, `recovery_check.json`)
| Check | Mono | Stereo |
|---|---|---|
| PyAV stream copy `.flac` → `.mka` (A_FLAC; CodecPrivate 42 B = `fLaC` + STREAMINFO) | 1,407 blocks, 0 laced | same |
| FLAC frames byte-identical in the `.mka` | 1,407/1,407 | 1,407/1,407 |
| SeekHead spare before → after appending `.skau` | 91 → 75 B | 91 → 75 B |
| Blocks unchanged, Segment UID unchanged after the append | yes, yes | yes, yes |
| Attachment extracted by ffmpeg identical | yes | yes |
| Decoded = source: PyAV on `.mka`, PyAV after append, ffmpeg CLI | yes, yes, yes | yes, yes, yes |
| ffprobe duration | 30.000 s | 30.000 s |
| A 1-hour-sized `.skau` (13.5 MB: 48 B timing + 32 B packet record per block) on a copy | appended, 75 B spare, decoded = source | same |

**Crash recovery** (`recovery_check.json`): killed `.flac` files (STREAMINFO total samples = 0) stream-copy into `.mka` without patching. Results for the kills after 40, 138 and 301 frames:
- the frame bytes are identical;
- the decoded audio equals the killed file and is an exact prefix of the source;
- a `.skau` appended afterwards with 75–77 B to spare [M].

The FLAC STREAMINFO patch from `audio_skellycam` §2.2 isn't needed on this path.

## 4. Readers
**Electron** (`electron_e35.json`, `electron_e45.json`). `AudioDecoder` (`flac`, `description` = `fLaC` + STREAMINFO marked last, or the MKA CodecPrivate), packets fetched by `file://` Range at the indexed offsets:

| File | E35: decoded samples; max abs diff vs source | E45 | Cold start at packet 700 (60 packets) | `<audio>`: duration; seek to 10 s | Locator finds `.skau` (SHA-256) |
|---|---|---|---|---|---|
| native `.flac`, mono / stereo | 1,440,000; 1.56e-5 | 1,440,000; **0** | E35 1.54e-5, E45 0 | 30 s; 10.000 | — |
| `.mka` + `.skau`, mono / stereo | 1,440,000; 1.56e-5 | 1,440,000; **0** | E35 1.54e-5, E45 0 | 30 s; 10.000 | yes, 3 reads, identical |

- E45 is sample-exact. E35 differs by at most 1.56e-5 (about half a 16-bit step at this signal's peak), probably because it scales int16 by 1/32767 instead of 1/32768 [I]. That is a conversion difference, not decode loss.
- Fetching and decoding 30 s packet by packet took 0.59–0.83 s, about 0.4–0.6 ms per packet over `file://` [M]; the player only decodes a window around the playhead.

**VLC 3.0.24** (`vlc_check.json`, `afile` output, s16):

| File | Samples out | Offset | Matches source |
|---|---|---|---|
| native `.flac`, mono | 1,438,720 of 1,440,000 | 0 | identical prefix; **drops the last 1,280 samples (26.7 ms)** |
| `.mka` + `.skau`, mono | 1,440,000 | 0 | identical |
| `.mka` + `.skau`, stereo | 1,440,000 | 0 | identical |

## 5. Design that follows
1. **Record:** native `<rec>.audio.flac` (`frame_size=1024`, `flush_packets=1`, 48 kHz WASAPI, dedicated audio process; `audio_skellycam` §0). Alongside it, the `.skau` timing records per callback block (`audio_skellycam` §4.2) plus a live packet record per FLAC frame: offset, size, first sample, CRC. Crash loss: 0 ms (`audio_skellycam` §2.2).
2. **Finalise:**
   1. stream-copy into `<rec>.audio.mka`;
   2. scan its blocks and check every CRC against the live packet records;
   3. write the packet table with the `.mka` offsets, plus the drift fit, into the `.skau`;
   4. append the `.skau` as an attachment;
   5. verify (decoded sample count, attachment SHA);
   6. then delete the `.flac` (decision S9).
3. **Crash recovery:** the same steps, from the killed `.flac` plus the surviving `.skau` records. No STREAMINFO patch is needed.
4. **One player audio path for every source:** `AudioDecoder('flac', description = CodecPrivate)` on packets fetched by offset from a packet table. That covers skellycam's `.mka` (table in the embedded `.skau`) and skellysync's camera MKV (table in the camera sidecar, `audio_skellysync` §4).
5. **The same appender and locator** as the video sidecar (`sidecar_embedding`). The SeekHead room guarantee holds, because FFmpeg writes the `.mka` too.

## 6. Open
- **S9, closed (Dom, 2026-11-12):** delete the native `.flac` once the `.mka`'s frame CRCs and decoded sample count verify.
- Real-microphone FLAC sizes (synthetic ≈ 172 MB/h mono; `audio_skellycam` §1.3) [NV].
- `TerminateProcess` mid-write for the live packet index [NV] (expected the same, §2).
- Linux/macOS [NV].

## 7. Files
- `scripts/flac_skau/flac_skau.py`: F1–F3; writes `electron_cfg.json`. Run as `python -I flac_skau.py <outdir>` with the `skellycam-phase1` venv.
- `scripts/flac_skau/electron/main.cjs` and `page.html`: run with `FLAC_CFG`/`FLAC_OUT` set and `ELECTRON_RUN_AS_NODE` unset. It loads `../../sidecar_embedding/locator.js`.
- `scripts/flac_skau/checks.py`: `recovery` and `vlc` (the VLC command line is in its docstring).
- Results in this folder: `flac_skau.json`, `recovery_check.json`, `vlc_check.json`, `electron_e35.json`, `electron_e45.json`.
