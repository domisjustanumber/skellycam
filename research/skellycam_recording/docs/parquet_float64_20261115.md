# Why the freemocap Parquet stores float64 (research)

Status: research report, 2026-11-15. A read-only sub-agent study for plan question R3-Q13; its size numbers were measured in memory with pyarrow 25.0.0 (the freemocap lock pins 26.0.0). The main session checked the schema lines (arrow_schema.py:17,25), the writer options (parquet_writer.py:80) and the introducing commit 21091d6c.

Written for: Dom and agent sessions writing the skellyfileformat Parquet section.

---

Report: why `<rec>_data.parquet` stores `value` and `timestamp_s` as float64

Refs: DS = upstream/development-streaming (c27fc299). SFN = upstream/sfn26 (3ae9842d). SFN has 120 commits that DS lacks; DS has 5 that SFN lacks. All work was read-only. Every "measured-here" number came from the freemocap .venv (pyarrow 25.0.0) run with `python -I`, writing Parquet to BytesIO only.

Short answer: nobody wrote down a reason. float64 arrived in one commit together with the proposal table, and no text explains it. In the canonical file only the time-valued numbers need float64. Coordinates, angles, quaternions and pixels lose nothing measurable at float32. One more finding: if the fold widens float32 into the existing float64 column, the file keeps most of the float32 size saving with no schema change.

1. Where float64 is chosen or enforced (DS)
- The schema: arrow_schema.py:17 `timestamp_s float64 non-null` and :25 `value float64` (nullable), inside SAMPLE_SCHEMA :15-29.
- Writer checks: SampleValidator.accept rejects any batch whose schema is not exactly SAMPLE_SCHEMA (arrow_schema.py:66-67).
  - It hashes timing as `struct.pack("<qd", frame, timestamp)` (:146, :214).
  - It compares timestamps across components bit-for-bit through `view(np.uint64)` (:190).
  - The quaternion unit-norm tolerance is 1e-5 (:132, :210).
- Reader check: parquet_reader.py:40-41 raises "Invalid recording schema" when the file schema differs from SAMPLE_SCHEMA. A float32 `value` file would therefore be rejected on read.
- ChannelSeries: `values: NDArray[np.float64]` (channel_series.py:25), with casts at :52, :66 and :73.
- Other float64 sites:
  - observation_samples.py:115
  - reconstruction_samples.py:262-290, whose docstring says "World landmarks and orientations retain float64 precision and missing frames."
  - diagnostic_samples.py:32
  - saved_reconstruction.py:216, which reads the file back into float64
  - input_signatures.py:45-57, which hashes values as `<f8`. Provenance signatures are taken over values reloaded from the file (saved_reconstruction.py:71).
- Timing values are also stored in `value`. TIMESTAMPS channels put seconds into `value` (`value=timestamp`, observation_samples.py:63-72), for per-camera capture time (observation_inputs.py:226-230) and synchronized time (observation_publication.py:123-127).
- Writer settings: `pq.ParquetWriter(..., compression="zstd")` with no other options (parquet_writer.py:80). So pyarrow's defaults apply, including dictionary encoding on the float columns.
- Exports:
  - arrays.py:175 and :188 (float64)
  - wide_csv.py:118 and :129; the check at :144-147 allows "4 float64 ULPs" of timestamp roundoff (also :297)
  - "round-trip float64" CSV (wide_csv.py:342, publication.py:44, exports/README.md:75, :82, :158)
  - guides.py:158 "Measurement arrays are float64"
- Playback UI: hyparquet reads the file (freemocap-ui/package.json:40), and the reader builds its own Float64Array (playback-parquet.ts:66, :80; playback-data.ts:56). The UI schema check accepts any number (playback-parquet.ts:10-11). Whether hyparquet returns float32 values correctly is not verified.
- Wire (websocket): ChannelBlock data is "packed float32 little-endian" (message_model.py:406-407); `from_float32_rows` packs `<f` (:423-435).
  - Producers cast to float32: channel_helpers.py:24, :29, :126, :179; derived_producer.py:35-43; joint_angles_producer.py:44; overlay_producer.py:51; segment_producer.py:33.
  - Reprojection diagnostics are also float32 (pipeline_diagnostics.py:42).

2. Stated reasons (verbatim)
- History: `git log -S'pa.field("value", pa.float64())'` finds only 21091d6c (jonmatthis, 2026-09-05, message "init posthoc work"). That commit added the same SAMPLE_SCHEMA in recording_data.py:13-25 and the proposal doc at the same moment. The file history of arrow_schema.py starts at 21091d6c. No commit message in DS mentions float64, float32, precision or double; the only matches are 4c4248ee and 996f17f4, which are unrelated.
- The proposal tables give type only, no reason:
  - "| timestamp_s | float64 | Capture/sample time on the shared recording clock, relative seconds |" (recording-data-model-proposal.md:78)
  - "| value | float64, nullable | Numeric component; null for missing data |" (:86)
  - :267 says "Use typed bounded array/Arrow batches before wire float32 packing; do not route disk through CBOR."
- Archived spec 10-serialization-and-tidy-format.md: it says only "`timestamp_s` | float" (:42) and "`value` | float" (:45), plus "Categorical dtypes keep the long format compact under parquet compression." (:59).
- RECORDING_CONTRACT.md and 00-foundation/conventions.md: no dtype statement (grep).
- Nearest thing to a rationale, about the wire, not disk: "pre-serializing sidesteps any float16 downcast (half-precision would be silent measurement loss). float32 only, never float16; scalar floats stay float64." (message-protocol.md:82-84, from 34fa05a1 / cc175796, 2026-08-17).
- Export plan: "Preserve float64 scientific values and null-to-NaN semantics" (secondary-exports.md:544). SFN drops the word "scientific" from that line.

3. Technical need (arithmetic: measured-here with np.spacing)
float32 has a 24-bit significand, so ulp = 2^(floor(log2|x|) - 23) and the worst rounding error is ulp/2. For float64 it is 2^(e - 52).

- timestamp_s
  - Epoch: recording start, not perf_counter. It is read from the CSV column "timestamp.from_recording_start.sec" (skellycam DS 169caf637, recording_timing_reader.py:91, :104), or computed as `frame/fps` (:75), or averaged across cameras (recording_timing.py:44).
  - Resolution by take length:

| Take length | float32 ulp | float32 worst error | float64 ulp |
|---|---|---|---|
| 37 s (sample) | 3.8e-6 s | | |
| 1 h | 2.44e-4 s | 0.12 ms | |
| 2 h | 4.88e-4 s | 0.24 ms | 9.1e-13 s |
| 24 h | 7.8 ms | | |

  - Measured-here over 2 h: 120 Hz intervals quantize to 8.30–8.79 ms instead of 8.333 ms, about ±5% of the interval. Any finite-difference velocity using those timestamps inherits that error. At 1 kHz over 2 h, values stay strictly increasing but carry 0.24 ms error, a quarter of the sample interval.
  - If a clock were perf_counter-based (10 days of uptime ≈ 864,000 s), the float32 ulp would be 62.5 ms: unusable.
  - Verdict: timestamps need float64. The same applies to TIMESTAMPS `value` rows.
  - SFN agrees in its docs: "source nanoseconds must not be squeezed into float32 or float64" (lsl-protocol-audit.md:133-134), and timelines are "float64 timestamps in seconds" (tensor-contract.md:237, :375-376).
- mm coordinates
  - float32 ulp at 1 m is 6.1e-5 mm. At 10 m (10,000 mm, in [8192, 16384)) it is 2^-10 ≈ 9.8e-4 mm, so the worst error is 0.49 µm.
  - Measured-here on real 3D values (freemocap sample data, legacy freemocap_data_by_frame.parquet, 3d_xyz, 1108 frames × 215 points, 262,596 non-null values):
    - largest |coordinate| 21,586 mm; p99 2,154 mm
    - float32 round-trip error at most 8.3e-4 mm, mean 1.5e-5 mm
    - median per-trajectory second-difference std 14.2 mm (this includes real motion, so it is only a loose noise indicator)
  - Verdict: float32 is about 4 orders of magnitude finer than the data's noise.
- Quaternions: ulp near 1 is 1.19e-7. Measured-here on 10^6 random unit quaternions rounded to float32: |norm² - 1| at most 1.0e-7, so they pass the validator's 1e-5 tolerance. Rotation error is at most 1.03e-7 rad.
- Angles: ulp at π is 2.4e-7 rad.
- Pixels: ulp is 1.2e-4 px at 1920 and 2.4e-4 px at 3840. Reprojection error at 5 px has ulp 4.8e-7. Visibility, confidence and the 0/1 detector_ran flag are exact or negligible.
- Where float64 still matters even for coordinates: bit-exact reproducibility.
  - Provenance signatures hash `<f8` values reloaded from the file (input_signatures.py:45-57, saved_reconstruction.py:71, :216).
  - Export validators demand exact float64 equality (wide_csv.py:131, :137-141).
  - A float32 store would make saved-stage replay differ from straight-through float64 computation unless the pipeline rounds at the same point. That is a design cost, not a precision need.

4. Cost (measured-here)
Writer emulation: real ChannelSeries batching (whole frames, ≤65,536 rows, one write_batch each), `compression="zstd"` and all other options left at pyarrow defaults, as in parquet_writer.py:80.

Dataset A: the real 3D values above in tidy-long form, 714,660 rows, 63% null (the face is entirely NaN in this sample). Dataset B adds synthetic data:
- 4 pinhole-camera 2D overlays from the real 3D plus 0.5 px noise, with visibility
- 20 smoothly varying quaternions
- 30 random-walk joint angles
- 5 TIMESTAMPS channels
- 3,700,720 rows in total

Assumptions: 30 fps, timestamps = frame/30 + 0.5 ms jitter, plausible short identity strings.

| Configuration | A file | A % | B file | B % |
|---|---|---|---|---|
| current: value f64, ts f64 | 2.523 MB | 100% | 14.063 MB | 100% |
| value f32, ts f64 | 1.511 MB | 59.9% | 8.357 MB | 59.4% |
| value f32, ts f32 | 1.506 MB | 59.7% | 8.300 MB | 59.0% |
| f64 + BYTE_STREAM_SPLIT, no dictionary on value/ts | 1.968 MB | 78.0% | 10.793 MB | 76.8% |
| f32 + BYTE_STREAM_SPLIT, no dictionary | 0.948 MB | 37.6% | 5.174 MB | 36.8% |

- The `value` column is 95.7% (A) and 95.3% (B) of the current file.
  - In B, `timestamp_s` is 146 kB (1.0%).
  - All string and int columns together are 0.51 MB (3.6%), with `name` the largest at 252 kB.
  - Dictionary encoding already makes the repeated strings nearly free.
- Value column alone, real 3D data (A), bytes per non-null value:

| Encoding | float64 | float32 | float32 widened to float64 |
|---|---|---|---|
| default (dictionary on) | 9.21 | 5.35 | 5.62 |
| no dictionary | 7.45 | 3.59 | 3.90 |
| no dictionary + BYTE_STREAM_SPLIT | 7.07 | 3.19 | 3.67 |

- Two findings from that table:
  - The current default stores float64 values in more than their raw 8 bytes, because dictionary encoding is applied to high-entropy floats. Turning dictionary off for `value` alone saves about 19% of the value column with no precision change.
  - float32 values widened into float64 keep their 29 zero low bits, and zstd removes most of them: 3.90 B vs 3.59 B per value.
- Dropping `timestamp_s` to float32 saves only about 0.4% of the file. It is not worth the precision loss.

5. sfn26
- No change to the on-disk dtypes: SFN arrow_schema.py:15-29 is identical, and `git diff DS SFN -- arrow_schema.py parquet_writer.py` is empty.
- SFN does pin float64 harder:
  - ChannelSeries now runs `series_layout.validate_array(self.values)` (SFN channel_series.py) against `Channel.tensor_layout()`, which declares `dtype="float64"` (SFN recording_descriptor.py:50-62).
  - Whether skellyforge's validate_array rejects other dtypes is not verified; the skellyforge source is not available locally.
- New SFN doc text:
  - "Coordinates retain float64 ... Other sensor quantities declare their own numeric dtype. Conversion must be explicit, not blanket float64 coercion of arbitrary signals." (tensor-contract.md:278-280, added by d613f549)
  - "Epoch timestamps are relative to a declared origin so small intervals are not unnecessarily represented as large absolute floats." (:375-376, added by dd0187dc)
  - "Float64 -> display float32 is tested as an explicit lossy conversion" (:501)
  - "Current numeric payloads and small status codes fit float32 without new loss" (lsl-protocol-audit.md:132-133), about the float32 wire payloads
  - "The accepted Parquet digest remains unchanged." (tensor-contract-audit.md:108)
- SFN also replaces the UI's Float64Array playback path with a Float32 presentation layer that keeps the Float64 source (diff of freemocap-ui/src/services/recording; tensor-contract-audit.md:110).

6. Assessment
- Keep `timestamp_s` float64. TIMESTAMPS `value` rows need float64 for the same reason.
  - float32 gives 0.24 ms error at 2 h and ±5% interval error at 120 Hz, and gets worse as takes grow.
  - It would save about 0.4% of the file.
- For `value`, precision does not require float64 except on time-valued rows (TIMESTAMPS / units "s"). Coordinates, quaternions, angles, pixels and scores lose nothing measurable at float32.
- Options with evidence-backed trade-offs:
  - (a) Keep float64 everywhere; the fold widens journal float32.
    - No schema, validator, reader, signature or export change.
    - The widening itself is exact, and the stored size is close to float32: 3.90 vs 3.59 B per value without dictionary, 5.62 vs 5.35 with the current default.
    - Cost: the column claims more precision than the realtime values have. A float64 posthoc recompute will not be bit-identical to folded realtime data, so provenance and digests must tell them apart.
  - (b) Switch `value` to float32.
    - File drops to about 60% (current writer) or about 37% (with BYTE_STREAM_SPLIT, no dictionary).
    - It breaks time-in-`value` channels unless those move to separate float64 storage.
    - It needs changes at arrow_schema.py:25, parquet_reader.py:40, ChannelSeries and the exports' exact-float64 validators, and SFN's `dtype="float64"`. It also changes the "accepted Parquet digest".
    - Every float64 pipeline result would round on write, so saved-stage replay differs from in-memory results unless rounding is applied consistently.
  - (c) Per-channel dtype in the tidy-long schema. A single Arrow column cannot mix dtypes, so this means a second value column or per-dtype files; that adds complexity for about 40% savings.
  - (d) Independent of dtype: set `use_dictionary` to exclude `value` (and optionally `timestamp_s`) and `use_byte_stream_split` for them. Measured-here, that cuts the file to about 77% with float64 kept and no precision change. This is the cheapest size win available.
- For the journal-fold question: widening float32 to float64 is lossless and keeps the storage saving. The spec should record that a run's values came from float32 so nobody treats them as float64-precise. That marking is not implemented anywhere today (not verified beyond grep).

Not checked: skellyforge's validate_array dtype enforcement, hyparquet's handling of FLOAT columns, any real canonical `_data.parquet` (none exist locally; only legacy-format files), and zstd levels other than pyarrow's default. Risk: dataset B's 2D, quaternion and angle values are synthetic, so their compression ratios are indicative; dataset A uses real values.
