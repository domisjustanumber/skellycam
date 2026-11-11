# GF02 notes (2026-11-10)

The report is `GF02_container_matrix.md`; the merged raw data is `GF02_container_matrix.json`. The work is functional only, so no timing was recorded.

## Run order (repo root)

```
uv run --script research/skellycam_recording/recording_upgrade/scripts/crash_resilience/gapfill/GF02/gf02_partA_write.py --skip-long
uv run --script .../GF02/gf02_partA_write.py --long-only
.venv/Scripts/python.exe .../GF02/gf02_cv2_reader.py <TEMP>/jobs_partA.json <TEMP>/partA_read.json
.venv/Scripts/python.exe .../GF02/gf02_cv2_reader.py <TEMP>/jobs_partA_long.json <TEMP>/partA_long_read.json   # deletes the 4 long files
uv run --script .../GF02/gf02_partB_kills.py
.venv/Scripts/python.exe .../GF02/gf02_cv2_reader.py <TEMP>/jobs_partB.json <TEMP>/partB_read.json
python -I .../GF02/gf02_report.py
```

- `<TEMP>` is `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/GF02/`.
- The reader outputs were copied to `GF02_partA_read.json`, `GF02_partA_long_read.json` and `GF02_partB_read.json`.

## Headline (measured; details and citations in the report)

**Index PTS**
- Index (CFR) PTS gave the exact cv2 count, 11/11 POS_FRAMES seeks and FreeMoCap ok in all 18 index files. That covers MKV, MKV + empty packet, fMP4 per-frame and fMP4 1 s, each on c930e, gap60, drop50 and c922, plus the 54,000-frame MKV and fMP4 1 s files.

**Real PTS**
- Real PTS broke seeks on files with drops in every container.
- Real-PTS MKV also miscounted every c930e input (888 for 891 / 831 / 874; 53,820 for 54,000).

**Frames lost per live paced kill** (6 kills per combination)
- MKV + fp: 1.
- fMP4 per-frame + fp: 1.
- fMP4 1 s + fp: 14–30.
- MKV + fp + empty packet: 0 in 12/12.

**MKV + empty packet: seek defects**
- On unfinalized files, PyAV seeks land 1 frame late (12/12).
- On finalized files, a seek to the last frame returns nothing (8/8).

**Torn tails**
- No torn tail occurred in the 48 paced kills, so torn-tail flagging is untested here.

**`recover()` on real-PTS MKV**
- The recovered file has `r_frame_rate` 125/2 and `avg_frame_rate` 0/0.
- cv2 then counts about 2.1× the frames (12/12).
- Index-PTS MKV and every fMP4 file recover correctly.

## Deviations from the task text

- **Kill points:** 6 per combination (50, 137, 300, 451, 611, 700), one more than the minimum of 5.
- **Kill methods:** the methods alternate between combinations, so each kill point gets both `os._exit` and TerminateProcess across the real/index pair.
- **Writer stream:** `add_mux_stream` instead of recwriter's encoder stream, following JP §4.1. The sidecar format and `recover()` are recwriter's own.
- **Long set:** real-content c930e looped, as in `bench_open_long.py`, with no gap. Its count used `grab()`, and its seeks were checked against the reference hash of input k mod 891.
- **Part B cv2 checks:** one seek per file (k = exact//2). FreeMoCap was not run on killed files.
- **Media kept:** partA (1.6 GB) and partB (1.9 GB) remain under the media folder. The 54,000-frame files were deleted after reading.
