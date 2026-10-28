# Reproducibility re-run (stage `critic_reproduce`)

Re-runs the headline benchmarks of `baseline/`, `prototypes/` and `cpp/` with the commands their READMEs document, and
compares the new values with the reported ones. Run 2026-10-28, 05:13-06:02 local, on the same machine, at SkellyCam
HEAD `23ccbf208e43879bfc74fc01049e5af2a623933d` (checkout unchanged, no source file modified). Reference sizes 1920x1080
and 1280x720 BGR, 5 synthetic 60 fps cameras. Verdicts: `../study_state/critic_reproduce_result.json` (summary.md was not written: the agent harness refused report .md files); full comparison table: `comparison.md` /
`comparison.json`.

## Why there is a protect/collect/restore step

Every documented command writes into its own stage's `results/` folder (and `build.bat` into `cpp/build/`), using fixed file
names, so a re-run as documented overwrites the files it is being compared against. `protect_originals.py` therefore
1. `snapshot`: copies `baseline/results`, `prototypes/results`, `cpp/results`, `cpp/build` (355 files) to
   `C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp\repro_backup` and writes a SHA-256 manifest (`originals_manifest.json`);
2. (the documented commands run, in place);
3. `collect`: copies every new or changed file into `rerun/<same relative path>` (`collected_files.json`);
4. `restore`: deletes the new files and restores the changed ones, then re-hashes everything (`restore_check.json`,
   `all_hashes_match_original`). The stage folders are therefore byte-identical to before this re-run, except `cpp/build/`,
   which is restored too (the rebuilt binaries are kept in `rerun/cpp/build/`).

## Commands (all from `C:\Users\Dom\GitHub\freemocap\skellycam`, each in a fresh PowerShell)

```
.venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\protect_originals.py snapshot

# 1. baseline e2e (baseline/README.md: bench_e_e2e.py row + run_with_load.py prefix; BENCH_E2E_REP for repeats)
$env:PYTHONIOENCODING='utf-8'; $env:BENCH_E2E_REP='_repro'
.venv\Scripts\python.exe research\frame_ring_buffer\baseline\run_with_load.py repro_e_e2e_1080p_mjpeg_ui repro_e_e2e_1080p_mjpeg_ui_stdout.log 600 -- .venv\Scripts\python.exe research\frame_ring_buffer\baseline\bench_e_e2e.py 1080p mjpeg ui 30
$env:BENCH_E2E_REP='_repro_rep2'   # same command, name repro_e_e2e_1080p_mjpeg_ui_rep2
$env:BENCH_E2E_REP='_repro'        # then: ... 1080p memcpy ui 30   and   ... 720p mjpeg ui 30   (names repro_e_e2e_<size>_<mode>_ui)
.venv\Scripts\python.exe research\frame_ring_buffer\baseline\summarize_e2e.py

# 2. prototypes (prototypes/README.md: run_all.py with step prefixes)
.venv\Scripts\python.exe research\frame_ring_buffer\prototypes\run_all.py p6_ui p8_e2e_1080p_imdecode_msmf p8_e2e_1080p_imdecode_off p8_e2e_summarize

# 3. C++ vs Python ring (cpp/README.md: build.bat, then run_all.py ring, summarize_load.py, summarize.py)
cmd /c research\frame_ring_buffer\cpp\build.bat
.venv\Scripts\python.exe research\frame_ring_buffer\cpp\run_all.py ring
.venv\Scripts\python.exe research\frame_ring_buffer\cpp\summarize_load.py
.venv\Scripts\python.exe research\frame_ring_buffer\cpp\summarize.py

.venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\protect_originals.py collect
.venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\protect_originals.py restore
.venv\Scripts\python.exe research\frame_ring_buffer\reproducibility\compare.py
```

The cpp prerequisites `uv pip install ... pybind11` (pybind11 3.1.0 was already in `.venv-bench`), `make_inputs.py` and the
cv2 4.8.0 throw-away venv are only needed by the `codec` matrix, which was not re-run, so they were not executed.

## Files

| file | content |
|---|---|
| `protect_originals.py` | snapshot / collect / restore of the original results (see above) |
| `compare.py` | builds `comparison.{json,md}` from the restored originals and `rerun/` |
| `rerun/baseline/results/` | `e_e2e_*_repro*.json`, `load_repro_*.json`, `repro_*_stdout.log`, the re-generated `e_e2e_summary.md` (original + re-run rows) |
| `rerun/prototypes/results/` | re-run `p6_ui_*.json`, `p6_ui_path.md`, `p8_e2e_1080p_imdecode_{msmf,off_passthrough}{,_rep2}.json`, `p8_e2e_summary.md` (re-run rows for these 4 files, original rows for the rest), `load_*.json`, `*_stdout.log`, `run_all_log.txt`, `load_summary.md` (regenerated in place: only the `p6_ui_*`, `p8_e2e_1080p_imdecode_msmf*`, `p8_e2e_1080p_imdecode_off_passthrough*` and `p8_e2e_summarize` rows are from the re-run, and the other rows repeat the original stage's load; `load_summary_rerun.md` lists only re-run steps; clarified 2026-10-28) |
| `rerun/cpp/results/` | `ring_write/*.json`, `ring_spsc/*.json` (+ `_log.txt`), `cpp_comparison.{md,json}` regenerated (only its 1a/1b ring tables and the ring_write / ring_spsc load rows are re-run values; sections 2-4 and the other load rows repeat the original `cpp/results/`), `load_ring_*.json`, `run_all_log.txt`, `load_summary.md` (same mix; clarified 2026-10-28) |
| `rerun/cpp/build/` | the rebuilt binaries |
| `build_stdout.log` | `build.bat` console output |
| `originals_manifest.json`, `collected_files.json`, `restore_check.json` | hashes of the originals, list of re-run outputs, restore verification |
| `load_summary_rerun.md` | machine load of every re-run step (from the `load_*.json` files) |
| `../study_state/critic_reproduce_result.json` | verdicts per headline result, README problems found (structured) |
