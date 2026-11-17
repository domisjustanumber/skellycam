# FINDINGS: float32 for most values, float64 where needed, and ZSTD in freemocap's `<rec>_data.parquet`

Status: research and test report, 2026-11-15, sub-agent study. Refs: DS = freemocap upstream/development-streaming c27fc29902; SFN = upstream/sfn26 3ae9842d89. All freemocap reads used `git show` / `git grep` on those refs; nothing was checked out. Labels: [measured], [code: path:line] (DS unless SFN is named), [knowledge, not verified].

## 0. Versions

- Python 3.12.13 (uv-managed), uv 0.13.7. Every script pins its dependencies with `==` in uv inline metadata, plus `exclude-newer = 2026-11-01`.
  - Writer environment: pyarrow 26.0.0 (the version freemocap's uv.lock pins), numpy 2.4.6 (the lock's version), pandas 2.3.3.
  - Reader environment: pyarrow 26.0.0, polars 2.0.0 (the lock's version; 2.1.0 is newer), polars-runtime-32 2.0.0, duckdb 2.0.0, pandas 2.3.3, fastparquet 2026.9.0, cramjam 2.14.0.
  - Second reader environment: pyarrow 25.0.0 (the version in the freemocap .venv) with pandas 2.3.3.
- Node v24.15.0, npm 10.9.2. Exact versions from freemocap-ui/package-lock.json on DS, all published at least 14 days ago [measured with npm view]:
  - hyparquet 1.25.6 (2026-04-08)
  - hyparquet-compressors 1.1.2 (2026-09-18)
  - fzstd 0.1.1 and hysnappy 1.1.1
  - package.json says `^1.25.6` / `^1.1.2`, so a fresh install without the lockfile would pull newer versions.
- Machine: Intel i7-14700K, 64 GB RAM, Windows 11. Other work may have been running at the same time, so timings are indicative.

## 1. Which rows need float64

Every ChannelKind and unit [code: channel_kind.py:6-26; sample_conventions.py:26-31 lists the units rad, px, 1, s, mm]:

| ChannelKind | units | float32 worst error on real-derived data [measured] | needs f64? |
|---|---|---|---|
| OVERLAY_2D (x, y, visibility) | px, 1 | 6.1e-5 px at 1,230 px | no |
| BOXES_2D | px, 1 | 6.1e-5 px; detector_ran 0/1 exact | no |
| REPROJECTION_ERROR | px or 1 [diagnostic_samples.py:24] | 1.2e-7 px | no |
| RECONSTRUCTION_COVERAGE | 1 (from bools) [reprojection_diagnostics.py:25-26] | 0 (exact) | no |
| TRIANGULATION_WEIGHTS | 1 | 3e-8 | no |
| RAW / MAPPED / LANDMARKS_3D, SEGMENT_ORIGINS, DERIVED_POINTS, KEYPOINTS_3D | mm (px if one camera) [spatial_points.py:58-74] | 1.2e-4 mm at 3.2 m; 8.3e-4 mm at 21.6 m | no |
| ROTATIONS_WORLD / LOCAL | 1 | 3e-8; norm²−1 at most 1.04e-7 against the validator's tolerance of 1e-5 [arrow_schema.py:132, :210] | no |
| JOINT_ANGLES | rad | 5.1e-8 rad | no |
| RIGID_BODY_RESIDUALS | mm (the reference's units) [reconstruction_samples.py:172] | 3e-5 mm | no |
| SEGMENT_LENGTHS / SEGMENT_SCALES / MODEL_SCALE | static; stored in descriptor JSON, not as rows [recording_descriptor.py:76-90; fit_channels.py:18-50] | n/a | no rows |
| OVERLAY_REPROJECTIONS | wire only [overlay_producer.py:60]; not in the file | n/a | n/a |
| **TIMESTAMPS** | **s** [observation_inputs.py:256-267] | as float32: 1.9e-6 s at 37 s, **1.22e-4 s at 1 h, 2.44e-4 s at 2 h** | **yes** |

- Units "s" occur only on TIMESTAMPS [code: observation_samples.py:43, :72; observation_inputs.py:265].
- TIMESTAMPS rows duplicate `timestamp_s`: `timestamp_s=timestamp` and `value=timestamp` [code: observation_samples.py:63, :71].
- The readers that use timing read `timestamp_s`, not `value` [code: playback_queries.py:92-108; saved_observations.py:100-110 uses `timeline.timestamps_s`].
- Future channels could need float64 [knowledge, not verified; the arithmetic is mine]:
  - latitude/longitude in degrees: float32 ulp at 180° is 1.5e-5°, about 1.7 m
  - integer counters above 2^24
  - absolute clocks
- SFN anticipates such channels: "Other sensor quantities declare their own numeric dtype" (tensor-contract.md:278-280, quoted in the prior study).

## 2. Design options

A single Arrow column cannot mix dtypes. Bytes are from section 4: 37 s take, BYTE_STREAM_SPLIT, no dictionary on value columns, ZSTD at pyarrow's default level 1, as a percentage of the current file.

| Design | Schema / descriptor | Size | Main freemocap consequences |
|---|---|---|---|
| **f64** (current) | unchanged | 100% (36.92 MB, default writer); 73.8% with BYTE_STREAM_SPLIT and no dictionary | none |
| **f64w**: float64 column holding values already rounded to float32 | unchanged | 39.8% | No schema, reader, UI or export change. The column claims more precision than it holds, so the file needs a marker. 4% larger than C. |
| **A**: `value` float32 plus `value_f64` float64. Each channel uses exactly one column; the other column is null. | Descriptor `Channel` gains `dtype` (float32 default; TIMESTAMPS float64). Missing data means both columns are null, so the column choice must come from the descriptor, not from which column is non-null. | 36.0% (13.28 MB). An all-null column chunk costs almost nothing. | Changes in every value reader, the UI and exports (section 6). This is the only design that can store float64 in future channels. |
| **B**: `value` float32 plus a float64 column only for time rows | the same as A with a narrower rule | identical bytes to A | Equivalent to A with the rule "units s → float64". The task's "value_f32" naming would also break the UI's fixed column list [playback-parquet.ts:6-14, :40], so keep the name `value` for the float32 column. |
| **C**: single `value` float32; TIMESTAMPS `value` null, time only in `timestamp_s` | `value` becomes float32; the TIMESTAMPS rule is documented | 35.8% (13.23 MB) | Smallest change. No UI change: zod `z.number()` accepts float32 values [playback-parquet.ts:11]. The TIMESTAMPS value becomes NaN in saved channels and exports, so exports need a special case. No future float64 path. |
| **D**: two files, main (float32, no TIMESTAMPS) plus timing (current schema) | two files, two schemas | 36.2% (+136 KB vs C) | publish_parquet replaces a single file atomically [parquet_writer.py:70-91], so two files need a two-file publish. playback_manifest and saved observations must open the second file. Worst ergonomics. |

Not tested: integer fixed-point columns (for example µm stored as int32 with DELTA encoding), and one wide column per channel.

## 3. Test data

- 1108 frames (36.9 s at 30 fps), 28 channels, 15 ChannelKinds, 4,858,580 rows, 1.2% null [measured: results/source_summary.json]. Source: `C:\Users\Dom\Downloads\freemocap_sample_data_h264`. The `~/.cache/freemocap/test_data` copy holds only a ChArUco board, so I did not use it.
- **Real values:**
  - RAW_KEYPOINTS_3D: rtmpose_skeleton_3d, 137 points
  - MAPPED_KEYPOINTS_3D: rtmpose rigid body, 27 points
  - LANDMARKS_3D: mediapipe body and hands, 79 points
  - DERIVED_POINTS: centres of mass, 13
  - JOINT_ANGLES: joint_angles.npy, 23 values, degrees converted to radians
  - SEGMENT_ORIGINS: Blender bone heads, 61, metres converted to mm
  - ROTATIONS_WORLD: Blender bone quaternions, 61, renormalised in float64
- **Derived or synthetic values:**
  - ROTATIONS_LOCAL: spine-relative products of the real quaternions.
  - OVERLAY_2D: the real 3D points projected through the real 3-camera calibration (Rodrigues and k1 distortion), plus N(0, 0.5 px) noise. Visibility is drawn from Beta(8,2), and points out of frame or with visibility below 0.3 are null.
  - BOXES_2D, REPROJECTION_ERROR, RECONSTRUCTION_COVERAGE and TRIANGULATION_WEIGHTS are derived from those projections.
  - RIGID_BODY_RESIDUALS: 12 bone lengths from the real 3D data.
  - TIMESTAMPS: frame/30 plus a per-camera offset and 0.5 ms jitter; synchronized time is the mean of the cameras.
- **Edge values:** I injected −0.0, the smallest float32 subnormal and one null into JOINT_ANGLES.
- **Layout:** batched exactly like ChannelSeries (channel-contiguous, whole frames, at most 65,536 rows, one write_batch per batch), giving 92 row groups. A stand-in descriptor sits under the schema metadata key `freemocap.recording`.
- **Long take:** 9000 frames (5 min, 39.5M rows), made by mirror-tiling the real data with regenerated timestamps. Bytes per frame matched the 37 s take within 3%, so the 1 h figures are linear extrapolations from the 5 min take.
- **Caveat:** SEGMENT_ORIGINS comes from Blender float32 data ×1000, so its float64 form compresses better than true float64 pipeline output. That slightly favours the f64 baseline; the channel is 4% of rows.

## 4. Measurements

pyarrow 26.0.0. Write time is the minimum of 2 runs; read time is the median of 3. "value read" means reading only the value column(s). The default `compression="zstd"` produced files byte-identical to `compression_level=1` in all 15 design × encoding pairs.

**Full matrix:** 5 designs × 3 encodings × 10 codec settings = 150 files. All were bit-exact on round trip: float32 values against the float32-rounded source, float64 rows against the float64 source, null masks, and −0.0 and subnormals preserved [measured: results/matrix_main.csv].

The table covers design C, plus A and the current file for reference. Columns are size as % of current, MB, write time, full read time and value read time.

| Configuration | % | MB | write s | full read s | value read s |
|---|---|---|---|---|---|
| f64 dict zstd (**current**) | 100 | 36.92 | 1.52 | 0.061 | 0.011 |
| f64 plain zstd | 80.6 | 29.77 | 1.32 | 0.058 | 0.009 |
| f64 bss zstd | 73.8 | 27.23 | 1.41 | 0.058 | 0.008 |
| f64w bss zstd | 39.8 | 14.69 | 1.31 | 0.056 | 0.007 |
| C dict zstd | 59.5 | 21.97 | 1.59 | 0.067 | 0.010 |
| C plain zstd | 40.1 | 14.80 | 1.37 | 0.061 | 0.009 |
| **C bss zstd (level 1)** | **35.8** | **13.23** | 1.28 | 0.058 | 0.007 |
| C bss zstd3 | 35.7 | 13.19 | 1.29 | 0.059 | 0.007 |
| C bss zstd9 | 35.4 | 13.07 | 1.42 | 0.063 | 0.009 |
| C bss zstd19 | 34.3 | 12.65 | 4.06 | 0.064 | 0.008 |
| C bss snappy | 40.3 | 14.86 | 1.26 | 0.058 | 0.007 |
| C bss lz4 (LZ4_RAW) | 37.2 | 13.73 | 1.29 | 0.063 | 0.007 |
| C bss gzip | 34.7 | 12.82 | 2.31 | 0.068 | 0.008 |
| C bss brotli | 34.0 | 12.57 | 3.03 | 0.063 | 0.010 |
| C bss none | 70.8 | 26.13 | 1.28–2.30 | 0.06–0.15 | 0.007 |
| A bss zstd / zstd3 | 36.0 / 35.9 | 13.28 / 13.24 | 1.30 / 1.31 | 0.057 | 0.007 |
| D bss zstd (two files) | 36.2 | 13.37 | 1.31 | 0.066 | 0.010 |

- **Where the bytes go (C bss zstd):** `value` 12.13 MB (91.7%), `timestamp_s` 0.33 MB (2.5%, dictionary-encoded by default), string and integer columns 0.56 MB.
- **Codec without BYTE_STREAM_SPLIT:** with no compression, BYTE_STREAM_SPLIT gives no gain on its own; it only helps the codec that follows.
- **5 min take** [measured: results/matrix_long9000.csv; one run each]:

| Configuration | MB (5 min) | estimated GB/h | write s | full read s | value read s |
|---|---|---|---|---|---|
| f64 dict zstd (current) | 291.7 | 3.50 | 12.5 | 1.02 | 0.172 |
| f64 bss zstd | 218.9 | 2.63 | 11.4 | 0.51 | 0.061 |
| f64w bss zstd | 117.3 | 1.41 | 11.0 | 0.48 | 0.045 |
| C dict zstd | 173.6 | 2.08 | 12.3 | 0.48 | 0.054 |
| C plain zstd | 118.4 | 1.42 | 11.2 | 0.47 | 0.043 |
| **C bss zstd** | 105.8 | 1.27 | 11.3 | 0.47 | 0.043 |
| C bss zstd3 | 105.3 | 1.26 | 11.5 | 0.48 | 0.045 |
| C bss zstd9 | 104.2 | 1.25 | 12.2 | 0.47 | 0.055 |
| C bss snappy | 119.9 | 1.44 | 11.3 | 0.47 | 0.045 |
| C bss brotli | 100.1 | 1.20 | 24.9 | 0.48 | 0.057 |
| A bss zstd / zstd3 | 106.2 / 105.7 | 1.27 | 11.0 / 11.5 | 0.48 | 0.044 |

  - Dictionary-encoded float64 also doubles pyarrow's full-read time at 5 min.
- **Read time per reader** on a 37 s file, one run, includes conversion to Arrow [measured: results/readers_*.csv]:

| Reader | Full read |
|---|---|
| pyarrow | ~0.06 s |
| polars | ~0.16 s |
| DuckDB | ~0.25 s |
| fastparquet | ~1.9 s |
| pandas | ~2.2 s (object strings) |
| hyparquet (decode only, without the UI's per-row zod parse) | 1.0–1.5 s; BROTLI 4.2–6.8 s |

## 5. Standardness and reader compatibility

**Spec** [code: fastparquet 2026.9.0's bundled `fastparquet/parquet.thrift`, uv cache environment `read-check-*`]:
- Lines 487-496: `UNCOMPRESSED=0; SNAPPY=1; GZIP=2; LZO=3; BROTLI=4 // Added in 2.4; LZ4=5 // DEPRECATED (Added in 2.4); ZSTD=6 // Added in 2.4; LZ4_RAW=7 // Added in 2.9`.
- Line 481: "Codecs added in format version X.Y can be read by readers based on X.Y and later."
- Lines 468-475: `BYTE_STREAM_SPLIT = 9`, "Encoding for floating-point data".
- Not verified, from knowledge:
  - BYTE_STREAM_SPLIT was added in parquet-format 2.8.0 for FLOAT and DOUBLE, and extended to INT32, INT64 and FIXED_LEN_BYTE_ARRAY in 2.11.0.
  - Parquet's ZSTD is the RFC 8878 frame format.
- pyarrow's `lz4` writes LZ4_RAW. pyarrow's metadata reports it as "LZ4", but hyparquet's thrift parse shows `LZ4_RAW` [measured].

**Read results on all 180 files** (150 configs; D produces two files). Every float column was checked bit by bit, including null masks, and every other column for equality [measured]:

| Reader | Result |
|---|---|
| pyarrow 26.0.0 / 25.0.0 | 180/180 bit-exact; float32 returned as float |
| pandas 2.3.3 (pyarrow engine) on pyarrow 26 / 25 | 180/180 (nulls become NaN, float32 dtype kept) |
| polars 2.0.0 | 180/180 |
| duckdb 2.0.0 | 180/180 |
| fastparquet 2026.9.0 | 110/180. **BYTE_STREAM_SPLIT unsupported** ("NotImplementedError: Encoding 9", every bss file). **UNCOMPRESSED** files fail with "TypeError: an integer is required" whenever they contain TIMESTAMPS rows (D_main passes); not investigated. |
| hyparquet 1.25.6 + hyparquet-compressors 1.1.2 (read the way playback-parquet.ts does) | 165/180 bit-exact. ZSTD, SNAPPY, GZIP, BROTLI and NONE all pass, as do BYTE_STREAM_SPLIT on FLOAT and DOUBLE and dictionary-encoded FLOAT. **All 15 LZ4_RAW files that contain TIMESTAMPS rows fail, including the current float64 schema; only D_main passes.** |

The hyparquet LZ4_RAW failure:
- The failing column is `reference_frame` [measured: probe_lz4_columns.mjs].
- In TIMESTAMPS row groups that column is entirely null, so its dictionary page is empty. LZ4_RAW of 0 bytes is a single 0x00 token.
- `lz4basic` then reads a match offset past the end of input and throws "lz4 offset out of range 0" [code: hyparquet-compressors/src/lz4.js:58-75].
- hyparquet emits chunks without awaiting them, so the error also escapes as an unhandled rejection [measured].
- Newer hyparquet-compressors versions were not tested.

## 6. freemocap code each design would change (DS)

**All float32 designs (A, B, C, D):**
- `arrow_schema.py`: `:25` field type; `:66-67` exact-schema check; `:107-111` scalar finite check; `:193-194`, `:201-211` columnar finite and quaternion checks. These still pass on float32: norm² deviation is at most 1.04e-7 against the 1e-5 tolerance.
- `parquet_reader.py:40-41`: rejects any schema other than SAMPLE_SCHEMA. It must accept both the legacy float64 schema (read old, write new) and the new one.
- `parquet_reader.py:79-102` `static_samples`: builds rows against SAMPLE_SCHEMA, so float64 descriptor values would silently round to float32. It is only called from tests (test_posthoc_global_scale.py:180, test_recording_store.py:607).
- `channel_series.py:25`, `:73`: emit a float32 array (or float32/float64 by channel dtype).
- `observation_samples.py:61-80` (timing rows), `:115`; `reconstruction_samples.py:262-290` (docstring "retain float64 precision"); `diagnostic_samples.py:32`: in-memory float64 is fine; the cast happens at the batch.
- `saved_reconstruction.py:216`, `:260`: the float32 → float64 widening is exact.
- `input_signatures.py:45-57`: needs no code change. Signatures of float32 files are stable but differ from float64-era files of the same take, so bump the signature version. SFN's "accepted Parquet digest" (tensor-contract-audit.md:108) changes too.
- Exports:
  - `arrays.py:215-220` widens exactly; float64 output is kept.
  - `wide_csv.py:79-95` writes the repr of a widened float32, which prints 17 digits (for example 0.10000000149011612). The validators at `:118-141` still pass. Alternative: shortest float32 repr, validated in float32. Decision needed.
  - The "round-trip float64" labels at `:284`, `:297` and `:342` are now misleading.
- Other `value` readers: `notebook.py:38`, `:61`; `recording_health_report.py:131`; `tools/datasets/preparation.py:136`; `storage_batch_benchmark.py:89`.
- `parquet_writer.py:80`: add `use_dictionary=[non-value columns]`, `use_byte_stream_split=[value columns]` and `compression_level=3`.
- SFN: `Channel.tensor_layout()` hard-codes `dtype="float64"` (SFN recording_descriptor.py:57) and is checked by `series_layout.validate_array` (SFN channel_series.py:71-76). That needs a per-channel dtype. Whether skellyforge rejects float32 is unverified (its source is not local).
- The descriptor should state that values are float32-precision; the prior study found no such marker.

**Design-specific changes:**
- **A / B:**
  - Add a `dtype` field to `Channel` (recording_descriptor.py:39-68).
  - SampleValidator selects the column per channel and checks that the other column is null.
  - Every reader above reads the column for the channel's dtype.
  - UI: add `value_f64` to the zod schema and the `columns` list, and coalesce it at playback-parquet.ts:6-14, :40, :71.
  - The notebook pivot needs a coalesced `value`.
- **C:**
  - Set `value=None` in timing rows (observation_samples.py:71).
  - Exports and `read_saved_channel` of TIMESTAMPS must take time from `timestamp_s`.
  - No UI change.
- **D:**
  - Two-file publish and replace (parquet_writer.py:70-91).
  - playback_queries.py:86-108 and saved_observations.py:100-110 must open the timing file.

## 7. Recommendation (proposed, not user-accepted)

| | Proposed: A + bss + zstd3 | Fallback: C + bss + zstd3 | Current |
|---|---|---|---|
| Size, 37 s / estimated 1 h | 13.24 MB (35.9%) / ~1.27 GB | 13.19 MB (35.7%) / ~1.26 GB | 36.92 MB / ~3.50 GB |
| Write / full read (37 s) | 1.31 s / 0.057 s | 1.29 s / 0.059 s | 1.52 s / 0.061 s |
| Readers that pass | pyarrow 25/26, pandas, polars, DuckDB, hyparquet | same | same, plus fastparquet |
| Can store float64 in future channels | yes | no | yes (everything float64) |

- **Codec:** ZSTD at an explicit `compression_level=3`. It is standard Parquet since format 2.4. Level 3 is 0.3% smaller than Arrow's default level 1 at the same speed, and pinning the level stops file bytes depending on Arrow's default. Level 9 saves another 1% for +10% write time; level 19 costs three times the write time for 1.4%.
- **Avoid LZ4/LZ4_RAW:** freemocap-ui's locked hyparquet-compressors fails on it.
- **Avoid BROTLI:** hyparquet decodes it 3–4 times slower.
- **Separate win:** on its own, turning dictionary off for `value` with BYTE_STREAM_SPLIT saves 26% even if float64 is kept.

## 8. Remaining risks and desk tests

1. fastparquet cannot read BYTE_STREAM_SPLIT. If external fastparquet users matter, use `plain` instead: +4.3 points of size (40.1% vs 35.8%).
2. Readers I did not test against BYTE_STREAM_SPLIT on FLOAT, float32 and ZSTD: MATLAB `parquetread`, R arrow, parquet-java/Spark, DuckDB-wasm, and whatever the Blender add-on would use. These are desk tests.
3. The hyparquet LZ4_RAW bug, and the fastparquet uncompressed failure, both appear when a column chunk is entirely null. Neither matters with ZSTD, but it is worth a small upstream report.
4. The 2D, visibility and timing values are synthetic. Real detector output is natively float32 (ONNX) [knowledge, not verified], which would make float32 storage lossless for it.
5. The null fraction here is 1.2%; the prior study's dataset had 63%.
6. Separate from dtype: the UI decodes the whole file into JS rows. That took 1–1.5 s for 4.9M rows here, and a 1 h take is about 484M rows.
7. Not tested:
   - `timestamp_s` encoding variants (the column is 2.5% of the file)
   - BROTLI and GZIP levels other than the default
   - ZSTD level 22
   - float16 (excluded by message-protocol.md)

## Files

Scripts (`C:\Users\Dom\GitHub\freemocap\skellycam\research\skellycam_recording\recording_upgrade\scripts\parquet_dtypes\`):
- `pq_common.py` — data builder and writer
- `write_matrix.py` — `uv run --script write_matrix.py [--frames 9000 --tag long9000 --drop-files --configs ...]`
- `read_check.py` — Python readers, and verification of hyparquet's hashes
- `read_check_pa25.py`
- `hyparquet_check.mjs`
- `probe_lz4_columns.mjs`

Results (`...\recording_upgrade\results\parquet_dtypes\`):
- `matrix_main.csv`, `matrix_long9000.csv`
- `readers_pa26.csv`, `readers_pa25.csv`, `readers_hyparquet.csv`, plus `*_versions.json`
- `precision.json`, `source_summary.json`

Scratch, all rebuildable, under `C:\Users\Dom\AppData\Local\Temp\claude\ca7e9b09df19a3f5\ef960e37-035d-4929-84c6-9e035d622496\scratchpad\parquet_dtypes\`:
- `files\` (2.9 GB of test Parquet)
- `expected\*.arrow`
- `node\` (pinned hyparquet project)
- logs

Nothing was committed and no freemocap ref was checked out.

Not checked: newer hyparquet or hyparquet-compressors, MATLAB, R and Java readers, and skellyforge's `validate_array`. Main risk: fastparquet cannot read BYTE_STREAM_SPLIT, and the 2D and timing values are synthetic.

Main-session check (2026-11-15): `matrix_main.csv` sizes f64/dict/zstd 36,922,482 B; C/bss/zstd 13,234,590; C/bss/zstd3 13,193,607; A/bss/zstd3 13,238,608, all round-trip bit-exact; `readers_hyparquet.csv` shows the LZ4 failures ('lz4 offset out of range 0'). Matches §4-5. The sub-agent could not write this file (harness rule); the main session saved its text. The 2.9 GB of test files in the scratchpad are rebuildable.
