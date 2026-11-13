# MCAP profile choices: Dom's answers (2026-11-13)

Grilling of the MCAP profile choices listed in skellyfileformat `decisions/open-work.md`. These answers become skellyfileformat decision entries and the inputs to the MCAP spec rewrite. Evidence:
- `mcap_check_20261113.md`;
- `../recording_upgrade/results/mcap_kill/FINDINGS.md` (A);
- `../recording_upgrade/results/mcap_electron/FINDINGS.md` (C).

## Round 1

| # | Question | Answer |
|---|---|---|
| Q1 | One MCAP file per device per take? | **Yes, after round 2.** Dom first preferred a single file and asked about its cost. After desk test D he chose separate files (see Q1b). |
| Q2 | Protobuf message encoding with Foxglove's `.proto` schemas | **Yes** |
| Q3 | Video: `log_time` = arrival, `CompressedImage.timestamp` = driver sample time (unset when absent), `publish_time` = `log_time`, `sequence` = source frame number. Audio: `log_time` = arrival of the callback block, `CompressedAudio.timestamp` = time of the first sample, `sequence` = packet index. One host clock per take | **Yes** |
| Q4 | How a reader recognises the format | **MCAP Header `profile` = `"freemocap"`** (Dom; not `"skellyfileformat"`), plus a Metadata record with `major`/`minor`/`prerelease` |
| Q5 | Drop `legacy_ns` | **Yes** |
| Q6 | Encoder skips as `foxglove.Log` messages (level WARNING, `name = "skellyfileformat.encode_skip"`), no per-frame flag | **Yes** |
| Q7 | Fitted time as fit segments appended at finalisation (custom schema) | **Open.** Dom asked what is appended and why it needs a custom schema. Revised proposal in round 2. |
| Q8 | Opus: channels = the device's (at most 2, downmixed if more); 48 kHz; 20 ms packets; application `audio`; VBR 128 kbit/s mono, 256 kbit/s stereo; complexity 10 | **Yes** |
| Q9 | (F3) `audio_latency_ns` = mic → ADC, subtracted: time of sample n = t0 + n·10⁹/f − L (provisional until test A3) | **Yes** |
| Q10 | (F4) Canonical reader-result JSON | **Open.** Dom asked whether it is needed with a single file. |
| Q11 | (F6) Nominal rate `num/den`, each 1…2²⁰, else `bad_rate` | **Yes** |
| Q12 | (F2) Stale files and folders with several takes | Not answered. It depends on Q1. |

## Round 2

| # | Question | Answer |
|---|---|---|
| Q13a | Fit segments per camera in a Metadata record written before `finish()`: fitter name, version and parameters; raw times kept in every message; fitted time evaluated with integer arithmetic. Supersedes ADR-0YV1 (replaces Q7) | **Yes** (after an explanation with examples) |
| Q13b | Sequence breakpoints, the (position, sequence) pairs where the camera frame number does not increase by 1, per camera in the same record; the Q15 repair rebuilds them and the fit for a crashed file | **Yes** |
| Q14 | Opus: no `OpusHead` as the WebCodecs `description`. A packet's `timestamp` = the time of its first decoded sample (priming included). The reader drops the first `pre_skip` decoded samples itself | **Yes** |
| Q16 | Whole-file data-section CRC on for normally finished files; repaired files write 0 | **Yes** |
| Q17 | fsync about once a second while recording; the cost is measured before the value is fixed | **Yes** |
| Q18 | No chunk compression (`compression = none`) | **Yes.** Dom: compression will likely come later if raw capture is added |
| Q19 | Lichtblick audio checks: mrkbac at `70f5900`, rebuilt with its server address emptied and run offline; Opus picked by hand at 48 kHz; 1x only; sync is judged in skellycam's player; fixing or contributing to Lichtblick needs a separate yes | **Yes** |
| Q1b | One file per take, one writer process, 100 ms window chunks | **No. Q1 = one MCAP file per device per take** (Dom: "separate files is the better way to go"). Evidence: `../recording_upgrade/results/mcap_single_writer/FINDINGS.md` (D) |
| Q20 | Video: each chunk holds exactly `frames_per_chunk` frames (the last may hold fewer), with `frames_per_chunk` in the channel metadata; writers use 1 now; readers handle any value. Audio: 5 Opus packets (100 ms) per chunk | **Yes** |
| Q21 | Topics carry the label: `/cameras/<camera_label>/image`, `/cameras/<camera_label>/log`, `/microphones/<label>/audio`; `camera_label` and hashed `camera_key` carried over from spec v0; duplicate labels in one take are refused | **Yes** |
| Q22 | Metadata record names with a `freemocap.` prefix (`freemocap.format`, `freemocap.recording`, `freemocap.timing`); per-device facts in the channel metadata | Dom asked for more on `freemocap.format`; answered by Q22b |
| Q22b | `freemocap.format` holds `major`, `minor`, `prerelease`; `freemocap.recording` holds the take facts; `freemocap.timing` holds the fit and breakpoints (camera files); per-device facts in the channel metadata; the writer string in the MCAP Header `library` field (for example `"skellycam 2.1.3"`), not a metadata key | **Yes** |

Grilling complete on 2026-11-13. Next: decision entries in skellyfileformat, then the MCAP spec rewrite, then gate 1.
| Q23 | Drop the recording manifest (supersede ADR-41VF item 4); skellycam's own info JSON stays | **Yes** |
| Q24 | (F2) No stale-file rule; writers put one take per folder; readers group files by `take_uuid` and report each take; unfinished files belong to their take | **Yes** |
| Q25 | (F4) Keep the canonical reader-result JSON: file states and reasons, take state, warning codes, per-camera results | **Yes** |
| Q15 | Crash repair in place: cut off the torn tail, then append DataEnd + summary + footer. Readers also read unfinished files in place | **Yes, but only after the user confirms.** skellycam shows "An incomplete recording was found. Would you like to repair it?" and repairs only on yes. |
