# FINDINGS: Opus after a crash: seek accuracy and repair (desk test, 2026-11-16)

> **Main-session check (2026-11-16):** re-read from the result files: torn_tail_bytes = 0 for all 8 killed fMP4 (`tails.json`); wc engine error 0 at 20/20 targets for the 12 killed fMP4 rows × E35/E45 (`summary_crash.csv`, ps0 via `timeline_error_samples`); idempotent 16/16 (`idempotent.json`); per-kill loss values (`loss.json`); open times (`open_times.json`) and the 15 min–4 h scaling (`big_fmp4.json` `scale`) as stated. Not re-run.

For Dom's question (2026-11-16) about Opus as the microphone format: "does a crashed file still seek correctly? What is the repair process?"

**Provenance.** A sub-agent ran this on 2026-11-16, about 09:30–11:30 local, on Windows 11 with an i7-14700K. Another session was running skellytracker tests on the same machine at the same time.
- Only synthetic signals were used. No microphone or camera was opened, and no device or driver settings were changed.
- No source files in skellycam, skellycam-phase1 or freemocap were changed. There were no git operations.
- Scripts: `research/skellycam_recording/recording_upgrade/scripts/audio_single_file/opus_crash/`.
- Results: `research/skellycam_recording/recording_upgrade/results/audio_single_file/opus_crash/`.
- Media (rebuildable): `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file\opus_crash\`. The multi-GB files (1.9 GB, 5.8 GB and 4.5 GB fMP4) were deleted at the end; 1.6 GB of rebuildable media remain.

**Labels:** [M] measured here (the result file is named) · [P: path] prior evidence · [C: path:line] code read · [D] derived arithmetic · [K] knowledge, not verified.

**Versions** [M]:
- Python 3.12.13; PyAV 19.0.2; numpy 2.2.6; soundfile 0.13.1; uv 0.13.7. PyAV's libopus is 1.6.1 [P: `audio_skellycam/codecs.json`].
- FFmpeg/ffprobe CLI 9.0.2 (gyan.dev full build).
- VLC 3.0.24 Vetinari, through the CLI and python-vlc 3.0.21203.
- Electron 35.7.5 (Chrome 134.0.6998.205; the skellycam-ui `node_modules` binary, used read-only) and 45.2.3 (Chrome 156.0.8078.80).
- Blender 5.2.3 LTS, headless (`aud` + VSE at 24 fps).
- Pins are exact and the same as the existing scripts: `av==19.0.2`, `numpy==2.2.6`, `soundfile==0.13.1`, `python-vlc==3.0.21203`.

**Files under test.**
- **Mono**, 48 kHz, D9N1 mono settings: libopus 128 kbit/s VBR, 20 ms packets, `application=audio`, complexity 10, pre-skip 312.
  - Mono was chosen because the planned player's WAV path reads 16-bit mono [C: `skellycam_playback/electron/player.js:167`], and the playback study used mono.
  - The earlier kill test was stereo 256 kbit/s [P: `opus/FINDINGS.md`].
- **Signal:** the left channel of the `opus_common` timing signal (seeded noise plus a click every second at 24,000 + k·48,000).
- **Writers**, all PyAV with `flush_packets=1`:

| Name | Container, options |
|---|---|
| `fragpkt` (primary) | MP4 `.m4a`, `movflags=empty_moov+default_base_moof+frag_every_frame` |
| `frag100` | MP4 `.m4a`, `empty_moov+default_base_moof`, `frag_duration=100000` |
| `mka` | Matroska `.mka`, `cluster_time_limit=1` |
| `wav` (reference) | WAV, `rf64=auto` |
| `fragpkt_ps0` | the `fragpkt` files with dOps PreSkip patched to 0 (2 bytes; the `preskip0.py` patch [P: `opus/preskip0.py`]) |

WebM was not run separately; it behaved like MKA in every prior check [P: `opus/FINDINGS.md` §1.3].

**Hard kills** (`make_crash.py` → `make_crash_{short,long,clean}.json`):
- Real-time-paced writer child; one 1,024-sample block, then one CRC'd CSV row, flushed.
- The kill is `TerminateProcess` on the child's own PID (`kill_matrix.terminate`).
- **Short:** 3 kills per writer at 12–55 s, seed 20261116.
- **Long:** 1 kill per writer, written live for 30.5–31.1 min (kill at 1,829–1,867 s).
- **Clean:** one cleanly closed 20.011 s file per writer.
- **16/16 kills landed** (exit code 15).

**Seek method** (`seek_crash.py`, `crash_common.land` = `opus_common.seek_landing`):
- **Targets per file:** 20 inside the decoded length L (0.1 s, 0.5 s, 1 s, 11 random, then L − 2.0/1.5/1.0/0.7/0.4/0.2 s; each with a random 0–47 sample offset). Then 2 past L: half-way into the samples the CSV has but the audio lost, and L + 0.5 s.
- **Error** = source index of the first non-silent sample after the jump − target, in samples (< 0 = early).
- **Files measured:** one short kill per writer (the longest: 29–55 s), the long kill per writer, plus the clean file per writer as the baseline.
- **Long files.** The noise repeats every 2^22 samples (87.4 s), so for long files the search uses a source window (the target ±20/12 s plus the file start).
  - That window was added after a first pass gave false landings on the 30-min files; that pass was discarded.
  - `selftest_land.py` (assert-based, synthetic starts, jumps, inserted silence, targets up to 7·2^22 + 100) passes.
- **ps0 files** are reported on the file timeline (+312), so 0 = exact in file samples. The CSV's `file_sample_offset=312` then maps that to the device [P: `skellycam_playback/FINDINGS.md` §3.1].
- **VLC** takes ms (`set_time`, `--start-time`). Its errors are corrected for the request's ms rounding (≤ 24 samples).

**Readers:**
- **skellycam harness, wc engine:** the planned player's `WcEngine` from `skellycam_playback/electron/player.js`, loaded unchanged. It does the moof/tfdt/trun walk, a 1 s windowed WebCodecs `AudioDecoder` decode, and an 80 ms pre-roll, with output placed by timestamp.
  - `pcm(n, 2 s)` is called at every target and the samples it would schedule are analysed.
  - Served through the same `protocol.handle` single-range handler, in Electron 35 and 45 (`electron/main_crash.cjs`, `electron/crash_page.html`).
  - That engine reads WAV/FLAC/fMP4 only, so **MKA cannot be played by the planned player as designed.**
- **Chromium:** `decodeAudioData` (click offsets over the whole file) and `<audio>` `currentTime` seeks. Rendered `<audio>` content was not re-measured, because prior work found it only coarsely measurable [P: `opus/FINDINGS.md` §2.1].
- **PyAV**, as a careful app would use it: seek 200 ms early, decode, cut at pts = target.
- **ffmpeg** `-ss T -i`.
- **VLC:** seek bar (libvlc `set_time` while playing) and `--start-time`.
- **Blender:** `aud.Sound.limit(T, T+1)` and the VSE strip length.

---

## 0. Short answer

| Question | Answer |
|---|---|
| Does a crashed Opus file still seek correctly? | **Yes, as well as a cleanly closed one, in every reader** [M]. A process kill leaves fMP4 ending exactly on a complete fragment (torn tail 0 bytes in 8/8). Nothing about seeking changes. |
| skellycam's planned player (wc engine) on killed fMP4 | **Sample-exact: 0 samples at 20/20 targets** on each of the killed per-packet, 100 ms and ps0 files, short and 30-min, in E35 and E45 (240/240). WAV: 80/80. The 30-min moof walk takes 114–172 ms [M] |
| Needs repair for skellycam playback? | **No, for process kills** [M]. The player needs 3 rules: clamp to the decoded/indexed length; ignore index entries whose bytes run past EOF (only torn tails from power loss produce them); fit from the CSV rows when the footer is missing (also true for WAV) |
| Needs repair for standard players? | **fMP4: no.** It plays, shows a duration and seeks in VLC, Chromium, FFmpeg/PyAV and Blender, with the same errors as the clean file [M]. **MKA: yes**, an 11-byte in-place Duration write fixes Chromium (NaN duration), ffprobe and Blender (1-frame strip) [M] |
| Real cost of per-packet fragments | **Open time, whether crashed or clean.** On a 30.5-min file, run sequentially: VLC 3.4 s, FFmpeg 1.8 s, Blender seeks up to 4–6 s each; WAV 0.01–0.03 s. An appended mfra does not help (VLC 3.1 s, FFmpeg 1.8 s). Re-fragmenting to 1 s does (0.05–0.07 s) [M] |
| Minimal repair (fMP4) | (1) Truncate to the end of the last complete moof+mdat, after stripping a zero-filled tail: a no-op after process kills, needed only for torn tails. (2) Optionally append an mfra: append-only, idempotent, crash-safe. **Do not remux to plain MP4:** it breaks the planned player's moof walk (every window fails with `range status 416`) [M] |
| 4 GiB | **Irrelevant for fMP4 size fields** [M]. A 4.48 GB, 84 h file (1 s fragments, 12,703 moofs past 4 GiB, 64-bit tfdt up to 1.45·10^10) gives the right duration in ffprobe. PyAV and VLC seek correctly at 84 h, with and without an appended mfra. **The real per-packet limit is fragment count:** open time grows by about 4 s/h (FFmpeg) and 6.5 s/h (VLC), and a 25.8 h per-packet file was impractical (VLC 4.15 GB RAM; remux not finished after 10 min) |

## 1. Loss, file structure and the CSV after a kill (Q2)

### 1.1 Loss and CSV lead (`loss.py` → `loss.json`) [M]

| Writer | Lost per kill (samples; 3 short + 1 long) | ms | CSV lead over the audio |
|---|---|---|---|
| `wav` | 0, 0, 0, 0 | 0 | 0 (4/4) |
| `fragpkt` | 1,464 · 1,656 · 1,912 · 2,168 | 30.5–45.2 | = lost, 4/4 |
| `frag100` | 3,256 · 4,536 · 5,624 · 5,816 | 67.8–121.2 | = lost, 4/4 |
| `mka` | 2,296 · 2,936 · 3,064 · 3,064 | 47.8–63.8 | = lost, 4/4 |

- These agree with the earlier stereo kill test (fragpkt 1,272–2,168; MKA 2,232–3,128; frag100 1,528–5,880) [P: `opus/FINDINGS.md` §1.3].
- **CSV integrity:** all 16 CSVs parse strictly, with 0 torn bytes and 0 CRC failures.
- **No footer:** none of the 16 killed CSVs has a `# fit` or `# end` line (a clean close writes them) [M].

### 1.2 What a kill leaves, and what a clean close would have added (`tails.py` → `tails.json`) [M]
- **fMP4 (both fragmentings):**
  - Every killed file ends exactly at the end of a complete moof+mdat pair. Torn tail: 0 bytes in 8/8, including the 30-min files (91,458 and 18,622 fragments).
  - A clean close rewrites no header byte. In killed frag100 files shorter than the clean one, 0 prefix bytes differ.
  - The close only appends the held last fragment plus an `mfra`: 19,067 B for 1,001 fragments, about 19 B per fragment.
  - The killed file is therefore exactly "the clean file minus the last packet and the mfra".
- **MKA:** a clean close writes, in place:
  - the Segment size (8 B);
  - a SeekHead into the 161-byte leading Void;
  - CRC-32 elements;
  - Info Duration into an 11-byte Void;
  - a Tags DURATION value;
  - and it appends Cues.

  A killed file has an unknown-size Segment and none of these.
- **WAV:** a clean close writes the RIFF and data sizes (2 × 4 B). A killed file has 0xFFFFFFFF.

### 1.3 Torn tails (power-loss and OS-crash shapes a process kill does not make; `seek_crash.py prep torn`) [M]
Five shapes were cut from a killed `fragpkt`/`frag100` file (33 s / 20 s):
- cut mid-mdat;
- cut mid-moof;
- cut 3 bytes into a box header;
- a 4 KiB zero tail;
- cut mid-mdat plus a zero tail.

MKA got a cut mid-block and a zero tail; WAV got a cut odd byte and a zero tail.

| Shape | PyAV / ffmpeg / Chromium `decodeAudioData` | Planned player (wc) | `<audio>` / ffprobe / VLC duration |
|---|---|---|---|
| fMP4 cut mid-moof, in a box header, zero tail | decode to the last complete packet; identical to the intact prefix | exact (0) at all targets | the complete fragments' length (+6.5 ms, §1.4) |
| `fragpkt` cut mid-mdat (half the last packet) | **decodes a full 960-sample frame from half a packet; those 960 samples differ from the intact decode** (20 ms of wrong audio at the end) | exact; it plays the same wrong last 20 ms | L + 6.5 ms, where L includes the 960 wrong samples |
| `frag100` cut mid-mdat (a 5-packet fragment cut in half) | decodes the packets present, plus 960 wrong samples from the half packet | **fails: `EncodingError: Null or empty decoder buffer`** for every window that touches the torn fragment. The trun lists packets past EOF, and their empty data closes the decoder, so the whole 1 s chunk is lost | L + 46.5 ms: 6.5 ms of priming plus 40 ms of packets that are not in the file |
| MKA cut mid-block, zero tail | decodes to the last complete block | n/a | no duration (as killed) |
| WAV odd byte, zero tail | the odd byte is dropped; the zero tail decodes as 2,048 samples of silence (the audio is then 2,048 samples **longer** than the CSV) | exact; past the end `range status 416` | the file length |

### 1.4 The CSV against a crashed audio file (Q2) [M]
- **The CSV leads the audio by the lost samples** (§1.1). Readers report three different lengths for a killed fMP4:
  - the decoded length L;
  - the container duration (ffprobe, libvlc, `<audio>`) = **L + 6.5 ms**, because the 312 priming samples are on the container timeline. ps0 files give exactly L;
  - the CSV cover = L + 30–121 ms.
- **The planned player's moof walk gives L exactly:** last tfdt + trun durations − pre-skip − L = 0 in 8/8 killed fMP4 files.
  - Clean fMP4 files decode 136 samples of end padding past the input (448 with ps0). The CSV `# end samples=` clamps those.
  - With a torn mid-mdat tail the index over-claims. `frag100`: 1,920 samples (960 with a zero tail). `fragpkt`: 0, because decoders make 960 samples from the half packet, but those samples are wrong.
- **Seeking into (L, CSV end] or past it** (2 targets per file, every reader):

| Reader | Opus (fMP4, MKA) | WAV |
|---|---|---|
| wc engine | returns silence, no error | `pcm()` rejects with `range status 416` |
| `<audio>` | `currentTime` clamps to the duration (L + 6.5 ms fMP4, L − 12.5 ms MKA); `ended` fires | same, at L |
| PyAV, ffmpeg `-ss` | 0 samples | 0 samples |
| Blender `aud` | 0 samples | 0 samples |
| VLC seek bar | **ignored**: playback continues from the pre-seek position (2.6–3.2 s) | stops (`Ended`) |
| VLC `--start-time` | ignored: plays the file instead of nothing | plays nothing |

- **What misbehaves without the rules** [C + M]:
  1. **The missing footer.** The planned `parseAudioCsv` leaves `fit = null` when there is no `# fit` line. `makeMap('fit')` then throws a TypeError on the first `toHost`/`toSample` [C: `player.js:37-53`]. The player, or recovery, must fit from the rows. This is the same for a killed WAV.
  2. **The WAV past-end `416` rejection** inside the play loop's async IIFE has no catch [C: `player.js:190-193`]. The loop dies silently, which is harmless at the end of a file. Opus returns silence instead and keeps decoding the last packet for every later chunk.
  3. **The torn `frag100` tail** loses the last chunk (decoder error), as above.
  4. **Nothing else misbehaved:** no reader drifted, and the video side (master clock from the audio output) simply runs on over silence.
- **Reader rule (proposed):** duration = min(CSV cover, indexed length), and stop scheduling there.
  - Index only packets whose bytes end inside the file: one check in the moof walk.
  - Fit the CSV rows only up to that length.

## 2. Seek accuracy on crashed files (Q1)

### 2.1 Killed, not repaired: error in samples over 20 in-range targets (14 spread + 6 in the last 2 s) [M]
Sources: `summary_crash.csv`, `seek_std_crash.json`, `seek_electron_crash_e35/e45.json`, `seek_blender_crash.json`; long-file VLC from `vlc_long.json` / `vlc_long_seq.json`. "= clean" means the clean 20 s file of the same writer gives the same range.

| Reader | WAV killed (29 s, 31 min) | fMP4 per packet killed (52 s, 30.5 min) | ps0 (file timeline) | fMP4 100 ms killed (20 s, 31 min) | MKA killed (54 s, 31 min) |
|---|---|---|---|---|---|
| **skellycam wc engine, E35 + E45** | **0** (80/80) | **0** (80/80) | **0** (80/80) | **0** (80/80) | not supported by the indexer |
| Chromium `decodeAudioData`, every click in the file | 0 | 0 | 0 (+312 in raw file samples) | 0 | 0 (E35) / −24 (E45), = clean |
| Chromium `<audio>` `currentTime` after seek | exact | exact | exact | exact | exact |
| PyAV, cut by pts | 0 | **−312** (all), = clean | 0 | −312, = clean | −48 (1 ms block timestamps), = clean |
| ffmpeg `-ss` | 0 | −312 … −5, = clean* | 0 … +2 | −312 … −5 | −62 … +309 (clean: −19 … +927) |
| VLC seek bar | 0 | short: −943 … −270; 30 min: −559 / −1,045 / −930 (`vlc_long`); clean −1,188 … −270 | −878 … +42 | −1,044 … −270 (one −35,577 on 31 min under load) | −321 … +552 (one −77,112 on 31 min under load); clean −326 … +408 |
| VLC `--start-time` | 0 (13/14 short, one −48; ±4 on 31 min) | −1,171 … −306, = clean | −909 … +7 | −1,076 … −306 | −360 … +552 |
| Blender `aud` `limit` | ±3** | ±3** | ±5** | ±3** | **+287 … +1,167** (clean +406 … +1,196) |
| Blender VSE strip | correct | correct | correct | correct | **1 frame** (clean: correct) |

\* ffmpeg `-ss` on fMP4 lands at −min(t mod 960, 312): it is up to 312 samples (6.5 ms) early, as on clean files.
\** WAV shows the same ±1–3, so it is not a container effect. The likely cause is that `limit()` takes seconds as a float [K].

- **Last 2 s before the torn end:** for every reader the near-end targets land in the same range as mid-file targets (`summary_crash.csv`, columns `near_*`). The truncated last fragment has no effect.
- **Missing mfra and no final moof** make no difference to any reader: the clean files have an mfra, and their errors are the same.
- **Long files** (30.5–31.1 min, 91,458 fragments per packet): seek accuracy is identical to the short files in every reader. VLC was only measurable with the open wait of `vlc_long.py`; see §2.2.
- **The PyAV −312 and ffmpeg −312 on fMP4 are not crash effects.** They are identical on clean, killed, truncated, mfra, remuxed and re-fragmented files, and 0 with ps0.
  - The effect is measured: frame pts on fMP4 Opus (no edit list) sit 312 samples off the trimmed decode, and the decode from 0 has offset 0 in every file [M]. Where in FFmpeg this comes from was not traced [K].
  - An app that maps PyAV pts to time on fMP4 is 6.5 ms early. One that counts decoded samples from 0 is exact.
  - The skellycam player is not affected: it places output by WebCodecs timestamps on the untrimmed timeline [P: `skellycam_playback/FINDINGS.md` §3.1].

### 2.2 Fragment count: open and seek cost on the 30-min killed files [M]
Sources: `open_times.json` (sequential, medians of 3), `vlc_long_seq.json` (sequential), `facts_crash.json`, `facts_repaired.json`.

| 30.5–31.1 min file | FFmpeg open (ffprobe wall) | VLC open | Blender per seek (full decode) | `<audio>` metadata E35 / E45 | wc load E35 / E45 |
|---|---|---|---|---|---|
| WAV killed | 0.008 s (0.03) | 0.02 s | 0.009 s (0.3 s) | 20 / 21 ms | 1 / 14 ms |
| fMP4 per packet, killed | **1.79 s (2.28)** | **3.4 s** | **3.9 s (8.6 s)** | 99 / 238 ms | 168 / 114 ms |
| + mfra appended | 1.84 s (2.29) | 3.1 s | 3.1 s (11.6 s) | 93 / 122 ms | 143 / 127 ms |
| remuxed to plain MP4 | 0.004 s (0.03) | 0.01 s | 0.009 s (2.4 s) | 14 / 8 ms | **fails** (no moof) |
| re-fragmented, 1 s | 0.05 s (0.08) | 0.07 s | 0.08 s (2.4 s) | 103 / 53 ms | 85 / 53 ms |
| fMP4 100 ms, killed | 0.87 s (1.41) | 0.67 s | 0.73 s (4.5 s) | 72 / 118 ms | 101 / 92 ms |
| + mfra | 0.38 s (0.50) | 0.66 s | 0.58 s | 95 / 49 ms | 85 / 53 ms |
| MKA killed | 0.001 s + 0.04 s seek (0.11) | 0.35 s | 0.05 s (2.8 s) | 22 / 29 ms | n/a |
| MKA + Duration | 0.001 s (0.02) | 0.01 s | 0.04 s | 21 / 23 ms | n/a |

- **Parallel load inflates these a lot.** With 3 VLC instances at once, VLC took 24–60 s to open the killed per-packet file (`vlc_long.json`).
  - In the 4-way `std` run, VLC was still opening after the 1.2 s window for 17/20 seek-bar targets on that file, so those are recorded as no landing.
  - `vlc_long.py` waits for Playing and lands −559 … −1,045 there, the same as clean files.
- **Scaling, measured** (`big_fmp4.py scale` → `big_fmp4.json` `scale`). These are prefixes of the killed 25.8 h per-packet file, each cut at a fragment boundary (= a file killed after that many packets), measured one at a time. Both grow linearly: about **4.2 s per hour (ffprobe)** and **6.5 s per hour (VLC open)** [M].

| Per-packet file length | 15 min | 30 min | 1 h | 2 h | 4 h |
|---|---|---|---|---|---|
| ffprobe wall | 1.3 s | 2.0 s | 4.0 s | 8.8 s | 16.9 s |
| VLC open | 1.5 s | 2.9 s | 6.0 s | 12.8 s | 26.3 s |

- **The whole 25.8 h file (4.86 M fragments)** [M: observed by hand during the aborted `big_fmp4.py check`, recorded in `big_fmp4.json` `check_aborted`]:
  - VLC held 4.15 GB of working set while opening it.
  - FFmpeg `-c copy` to plain MP4 had used 589 s of CPU without writing a byte when it was stopped.
  - The PyAV seeks and ffprobe before it took about 28 min in total.
- **This cost is the same for a cleanly closed per-packet file**, which is a killed file plus an mfra: the mfra row. **It is not a crash effect.**
- **Writer side** [M: `big_fmp4.py write`]:
  - An unpaced writer slowed from 3.2 MB/s at 0.2 GB to 0.53 MB/s at 1.9 GB, and its working set grew by about 182 MB at about 4.5 M fragments (about 40 B per fragment). The muxer's per-fragment index for the mfra grows by realloc [K: FFmpeg movenc keeps `frag_info` per fragment; not verified in source].
  - That is still about 25× real time at 25 h, and about 7 MB/h of RAM [D]. It does not matter for takes of a few hours, but it does matter for days-long ones.

## 3. Repair options (Q3) (`repair_crash.py` → `repair.json`; readers re-run on the repaired set: `summary_repaired.csv`, `facts_repaired.json`, `seek_*_repaired*.json`) [M]

"Lossless" means the decoded samples are identical (`numpy.array_equal`) to the killed file's, or, for torn tails, to the intact prefix.

### 3.1 fMP4 (per packet and 100 ms)

| Option | Bytes changed | Time (30.5-min file, 36 MB) | Lossless | In place, crash-safe | What it fixes |
|---|---|---|---|---|---|
| (a) nothing | 0 | 0 | – | – | Nothing is broken after a process kill (§2) |
| (b) truncate the torn tail at the last complete moof+mdat, after stripping a zero-filled tail | 0 after kills (8/8); 3–4,945 B on torn shapes | 0.21 s (5.8 s/GB, Python box walk) | yes, vs the intact prefix: 5/5 per-packet shapes. `frag100` mid-mdat cuts drop the whole torn fragment: 2,880 / 3,840 samples of good audio | yes: one `SetEndOfFile` [K: atomic metadata update] | Torn tails only. It removes the 20 ms of wrong audio decoded from half a packet. It fixes the wc decoder error on the torn `frag100` file (exact at all targets afterwards). Durations become the real length |
| (c) (b) + append an mfra (tfra v1, 64-bit time and offset, one entry per fragment) + mfro | +19 B per fragment: +1.74 MB (+4.8 %) per 30.5 min per packet; +354 kB per 31 min at 100 ms | 0.22 s (5.8–6 s/GB) | yes (6/6 killed files; torn tails as (b)) | append-only. 6 crash-mid-append states (1, 3, 8, half, all-but-1 bytes, all): PyAV count and ffprobe duration unchanged, lossless 6/6. Re-running gives byte-identical output, because it truncates the old mfra first [M: `idempotent.py` → `idempotent.json`, 16/16] | **Nothing measurable for per packet** (VLC open 3.4 → 3.1 s, FFmpeg 1.79 → 1.84 s). 100 ms: FFmpeg open 0.87 → 0.38 s. No seek error changed |
| (d) remux `ffmpeg -c copy -f mp4` (plain MP4, moov at the end) | new file, 26 % smaller | 3.5–3.8 s (100–104 s/GB); `frag100` 2.0 s (69 s/GB) | yes (6/6) | no: new file, then rename | VLC/FFmpeg/Blender open become instant. **Breaks the planned skellycam player:** no moof, so every `pcm()` fails with `range status 416`. `decodeAudioData` stays exact in E35 and E45 (no double pre-skip trim on this remux, unlike FFmpeg's own plain MP4 [P: `opus/FINDINGS.md` §2.1]) |
| (e) re-fragment `-c copy -f mp4 -movflags empty_moov+default_base_moof -frag_duration 1000000` | new file, 25 % smaller, mfra at the end | 3.5–3.7 s (98–100 s/GB); `frag100` 0.67 s (23 s/GB) | yes (6/6) | no: new file, then rename | All open costs gone (VLC 0.07 s, FFmpeg 0.05 s, Blender seek 0.08 s). The wc engine stays exact (0). The only option that fixes standard-player open time and keeps skellycam playback working |

- **Seek errors after any repair** are the same as the killed file's in every reader (`summary_repaired.csv`), apart from VLC noise. One VLC target on the remuxed `frag100` 31-min file landed +8,453 (seek bar) and +11,337 (`--start-time`).
- **`.m4a` needs `-f mp4` for every remux:** the extension alone picks the `ipod` muxer, which refuses Opus [P: `opus/FINDINGS.md` §1.1].

### 3.2 MKA (cluster 1 ms)

| Option | Bytes | Time (31 min, 29 MB) | Lossless | Crash-safe | Fixes |
|---|---|---|---|---|---|
| `dur`: Info Duration (double, ms) into its 11-byte Void | 11 B in place | 0.45 s (a PyAV demux finds the last pts; the last cluster would be enough) | yes | 4 partial states: a torn 11-byte write gives a wrong duration (0 or 53.248 s instead of 54.294) until re-run. All 11 bytes sit at offset 280, inside one 512-byte sector [K: sector writes are usually atomic] | **ffprobe duration** (none → L + 0.5 ms), **Chromium `<audio>` duration** (NaN → L + 0.5 ms), **Blender strip** (1 → 1,303 / 44,810 frames, correct), libvlc length (−13 → 0 ms), VLC open (0.35 → 0.01 s) |
| `dur_seg`: + Segment size | +8 B | same | yes | same | nothing more measured |
| `full`: + Cues (one CuePoint per cluster) appended while the Segment size is still unknown, + SeekHead into the leading Void | +1.62 MB (+5.5 %) appended, 180 B overwritten | 10 s in this Python code (not optimised) | yes | 23 crash states (partial Cues, SeekHead, Duration, Segment size): all lossless | nothing more for these readers. ffmpeg `-ss` then lands later (−7 … +630) |
| remux `ffmpeg -c copy` | new file | 0.17 s (6.7 s/GB) | yes | new file, then rename | the same as `dur` |

- **Torn MKA:** cut to the end of the last complete cluster first (zero tail stripped), then `full`. Lossless against the intact prefix (2/2).
- **The MKA in-place code is not resumable as written:** after a full run, the Voids it looks for are gone. A spec repair would overwrite Duration and Segment size whether a placeholder or a value is there.
- **Blender `aud` seeks on MKA stay late** after every repair (+589 … +959 at the repaired targets). That is a container effect, also on clean files [P: `opus/FINDINGS.md` §2.1].

### 3.3 WAV reference
- `asf_common.repair_in_place` (8 B, 0.005 s) changes nothing a reader showed. Killed WAV is exact everywhere [M, = P: `audio_single_file/FINDINGS.md` §1.3].

### 3.4 The 4 GiB question (`big_fmp4.py` → `big_fmp4.json`)
- **What could overflow, and doesn't** [M, `big_fmp4.json`]:
  - With `default_base_moof`, trun data offsets are relative to the moof. No absolute 32-bit file offset exists anywhere in a fragmented file.
  - FFmpeg writes **tfdt version 1 (64-bit)** in every moof; `grow` asserted it for all 4.86 M moofs. The killed 25.8 h file's last tfdt is 4,666,797,120 > 2^32: 48 kHz passes 2^32 at 24.86 h.
  - The mfra built here uses tfra version 1 (64-bit time and offset).
- **The > 4 GiB file** (`frag1s` / `check_1s`): 6 h written with 1 s fragments and grown ×14 with tfdt/mfhd rewritten. That gives 84 h, 4,483,285,065 B, 302,414 fragments, and 12,703 moofs past 4 GiB. Results:
  - ffprobe duration 302,400.091 s (= 84 h + 14 × 6.5 ms priming), in 9.5 s.
  - PyAV seek to 83.99 h (moofs past 4 GiB): −312, exactly as everywhere (§2.1); open 8.6 s.
  - VLC `--start-time` there: −184, inside its usual range; VLC open 2.9 s.
  - mfra appended (5.7 MB, max moof offset 4,483,284,391): the PyAV seek is unchanged.
  - Remux to plain MP4: `co64` written (no `stco`), the seek in the remux is −312, open 0.48 s; 1,446 s (323 s/GB).
- **The per-packet file never reaches 4 GiB in practice:** that would be about 57 h. Fragment count costs more first:
  - open time is linear at about 4.2 s/h (ffprobe) and 6.5 s/h (VLC) (§2.2);
  - at 25.8 h, VLC needed 4.15 GB of RAM, and FFmpeg's remux had not finished after 10 min;
  - the writer slowed to 0.53 MB/s (§2.2).
- **The planned player's moof walk fetches the whole file to index it** [C: `player.js:111`]. For 1 h that is a 75 MB fetch (fine). For multi-GB files it would need range reads of the moof headers or of an mfra [K].

## 4. Recommendation (proposed; Dom decides)

**(i) skellycam playback:** a crashed per-packet fMP4 needs **no repair** [M].
- The planned player seeks it sample-exactly (240/240), as it does WAV.
- Spec the player rules instead:
  1. Index with the moof walk, and **skip any entry whose bytes end past the file size** (torn tails). That is one comparison in `indexMp4`.
  2. **Duration = min(CSV rows' cover, indexed length).** Stop scheduling there.
  3. **No `# fit` footer** (every crash): fit from the strict-parsed rows, the same as WAV.
  4. **ps0:** add `file_sample_offset` [P].
- **Never remux to plain MP4** for skellycam playback, unless the player also learns to index `stco`/`stsz`.
- **MKA is not playable by the planned player.** That is one more reason to keep fMP4.

**(ii) Standard players:**
- **fMP4 needs no repair to play, show a duration and seek** with clean-file accuracy.
- **The open time of per-packet fragments is a property of the format, not of crashes:** VLC about 3.4 s and FFmpeg about 1.8 s per 30 min, sequentially.
  - If that matters, it is a finalisation choice (re-fragment to 1 s fragments, lossless, about 100 s/GB, about 7.5 s per hour of mono 128k [D: 75 MB/h]), not a crash repair.
  - It would also apply to clean files.
- **MKA needs the 11-byte Duration write.**

**Repair procedure the spec would define (fMP4, proposed):**
1. **Strict-parse the CSV.**
2. **Walk the top-level boxes from offset 0.** Strip trailing zero bytes from the walk range. Find E, the end of the last moof whose following mdat ends within the file.
3. **Truncate to E if E < file size.** That is a no-op after a process kill. It is needed after power loss or an OS crash.
4. **Optional:** append an mfra built from the same walk (tfra v1, entry = tfdt, moof offset, 1, 1, 1; mfro = mfra size). It is idempotent, because step 3 drops an old mfra. It does not speed up per-packet files.
5. **Append to the CSV:** the `# fit` lines from the rows, and `# end rows=… samples=min(cover, L)` with L = the indexed length (last tfdt + trun durations − pre-skip).
6. **No remux.** Re-fragmenting to 1 s is a separate, optional finalisation for standard-player open time.

**MKA:** truncate to the last complete cluster, then overwrite Info Duration (and the Segment size). **WAV:** optional size patch (< 4 GiB).

| | WAV (`rf64=auto`) | Opus fMP4 per packet | Opus fMP4 100 ms | Opus MKA cluster 1 ms |
|---|---|---|---|---|
| Lost per kill | 0 [M, = P] | 30.5–45.2 ms [M] | 67.8–121.2 ms [M] | 47.8–63.8 ms [M] |
| Crash seek: skellycam wc | 0 [M] | **0** [M] | **0** [M] | not playable (indexer) |
| Crash seek: Chromium `currentTime` / `decodeAudioData` | exact / 0 | exact / 0 | exact / 0 | exact / 0 (E45 −24) |
| Crash seek: VLC seek bar | 0 | −1,045 … −270 (= clean) | −1,044 … −270 | −321 … +552 |
| Crash seek: Blender `aud` / strip | ±3 / ok | ±3 / ok | ±3 / ok | +287 … +1,167 / **1 frame** |
| Crash seek: PyAV by pts / ffmpeg `-ss` | 0 / 0 | −312 / −312 … −5 (= clean) | same | −48 / −62 … +309 |
| Duration after kill (ffprobe, `<audio>`) | exact | L + 6.5 ms (priming) | L + 6.5 ms | **none / NaN** |
| Repair needed, skellycam | no | **no** (truncate only for torn tails) | no (torn tail: yes, else the last chunk fails) | n/a |
| Repair needed, standard players | no (< 4 GiB; RF64 header above [P]) | **no** | no | **yes: 11 B Duration** |
| Repair cost | 8–114 B, < 1 ms [P] | 0 B after kills; optional mfra 19 B per fragment, 6 s/GB | same | 11 B, < 0.5 s per 30 min |
| Open time, 30 min (VLC / FFmpeg) | 0.02 / 0.008 s | **3.4 / 1.8 s** (clean too) | 0.67 / 0.87 s | 0.35 / 0.001 s |
| 4 GiB | RF64 header rebuild needed > 4 GiB [P] | no size limit (64-bit tfdt, moof-relative offsets) [M]; fragment count limits it first | same | not tested |

## 5. Remaining risks and tests not done
1. **Power loss and OS crash:** only process kills were run. Torn shapes were synthesised from killed files; real NTFS behaviour (zero-filled extension, reordered writes) was not produced [K].
2. **VLC in a real window, VLC 4, Linux and macOS.** VLC open-time numbers are from the afile output on this machine; they are 7–18× worse under parallel load.
3. **The real skellycam-ui player** does not exist yet; the harness engine is the reference. The 3 player rules in §4 are not in `player.js`; only their need was measured.
4. **The MKA repair is not resumable**, and Duration is not written atomically (§3.2). Neither matters if MKA is not chosen.
5. **Multi-day takes:** writer RAM and CPU grow with the fragment count (§2.2), and VLC needed 4.15 GB to open a 25.8 h per-packet file.
6. **Not run separately:** WebM, stereo, and the ps0 variant of the 100 ms file.

## 6. Files
**Scripts** (`research/skellycam_recording/recording_upgrade/scripts/audio_single_file/opus_crash/`). Each is a uv script with exact pins, run as `uv run --script <script>` from the skellycam repo root.

| Script | Purpose |
|---|---|
| `crash_common.py` | Mono writer, source signal, `land` (seek landing with a long-file source window), ISO BMFF walk, mfra builder, EBML walk |
| `make_crash.py` | Short, long and clean live-written kills |
| `tails.py` | Killed vs clean structure |
| `loss.py` | Loss and CSV lead per kill |
| `seek_crash.py` | `prep` / `std` / `electron [--analyse-only]` / `blender` per set (`crash`, `torn`, `repaired`) |
| `electron/main_crash.cjs`, `electron/crash_page.html` | Electron harness. Loads `../skellycam_playback/electron/player.js` unchanged |
| `blender_inner_crash.py` | Runs inside Blender |
| `repair_crash.py` | Repairs + crash-during-repair states |
| `vlc_long.py [seq]` | VLC open/seek on the 30-min files |
| `open_times.py` | FFmpeg open/seek times |
| `big_fmp4.py write\|grow\|check\|scale\|frag1s\|check_1s` | 4 GiB question, fragment-count scaling (`check` was stopped; `check_x3` was not run) |
| `idempotent.py` | Re-runs the mfra repair on its own output |
| `summarize.py` | Per file × reader summary |
| `selftest_land.py` | Assert-based check of `land` |

**Results** (`research/skellycam_recording/recording_upgrade/results/audio_single_file/opus_crash/`):
- `make_crash_short.json`, `make_crash_long.json`, `make_crash_clean.json`, `loss.json`, `tails.json`;
- `seek_std_{crash,torn,repaired}.json`, `seek_electron_{crash,torn,repaired}_{e35,e45}.json`, `seek_blender_{crash,torn,repaired}.json`;
- `summary_{crash,torn,repaired}.csv`, `facts_{crash,torn,repaired}.json`;
- `repair.json`, `idempotent.json`, `vlc_long.json`, `vlc_long_seq.json`, `open_times.json`, `big_fmp4.json`.

**Media** (rebuildable): `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\audio_single_file\opus_crash\` (`short`, `long`, `clean`, `sets\{crash,torn,repaired}`, `raw`).

## 7. Follow-up (main session, 2026-11-16): fMP4 written live with 1 s fragments

Dom asked: if losing 1–2 s in a crash is acceptable, is 1 s fragmenting during recording the better choice? Script `scripts/audio_single_file/opus_crash/frag1s_kill.py`, result `frag1s_kill.json`. Same child process, pacing and `TerminateProcess` kill as `make_crash.py`. Writer: `empty_moov+default_base_moof`, `frag_duration=1000000`, `flush_packets=1`. 8 kills at 13–50 s plus 1 clean file. Run twice, same kill times.

- **Loss per kill:** 54.5–977.2 ms (run 1) and 257.2–990.5 ms (run 2). The CSV leads the audio by exactly the loss. 16/16 kills landed, and the CSVs had 0 bad rows [M].
- **Torn tail:** 0 bytes in 16/16. Every file ends on a complete top-level box [M].
- **Size:** the clean 20.011 s file is 298,327 B, about 53.7 MB/h mono 128k. The per-packet file is 418,787 B, about 75 MB/h [D].
- **Defect in the proposed repair, step 2 ("strip trailing zero bytes"):** in 2/8 files per run the last Opus byte is 0x00. `crash_common.fmp4_complete_end` then cuts the whole complete last fragment: 14,757 and 14,878 B, about 1 s of good audio. It also cuts the 447-byte mfra of the clean file. The spec repair must strip zeros only when the box walk finds an incomplete or zero-size box. It must never strip from a file whose boxes are all complete. With per-packet fragments the same defect costs one 20 ms packet. §1–§3 are not affected: no killed file there ended in 0x00 (`tails.json` torn 0 in 8/8).
- **Not re-run on these files:** the Electron wc engine and the other readers. Earlier evidence for 1 s fragments: re-fragmented 1 s files are exact in the wc engine and open in 0.05–0.07 s (§2.2, §3.1). The 84 h file written live with 1 s fragments seeks correctly in PyAV and VLC (§3.4).
- **Torn tails from power loss** with multi-packet fragments make the wc engine fail the whole 1 s decode window until the file is truncated (§1.3, the `frag100` case). With 1 s fragments, the truncation repair is therefore needed before skellycam playback after a power loss.

### 7.1 Stereo, 256 kbit/s (main session, 2026-11-16; `FRAG1S_STEREO=1 ... frag1s_kill.py` → `frag1s_stereo_kill.json`)
- Same kill times and method as §7. ffprobe: opus, 2 channels, 48 kHz.
- **Loss per kill:** 54.5–955.8 ms. The CSV leads the audio by exactly the loss. 8/8 kills landed; the CSVs had 0 bad rows [M].
- **Torn tail:** 0 bytes in 8/8. No killed file ended in 0x00 this time [M].
- **Size:** the clean 20.011 s file is 600,176 B, about 108 MB/h [D].
