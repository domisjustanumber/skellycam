import json

res = {
 "lens": "reproducibility: re-run of the headline benchmarks with their documented commands (baseline e2e, best record-path prototype P8, best UI-path prototype P6, C++ vs Python ring after a build.bat rebuild), compared with the reported values; SkellyCam 23ccbf20, synthetic 5x60 fps cameras, 1920x1080 and 1280x720 BGR",
 "issues": [
  {"target": "baseline/README.md, prototypes/README.md, cpp/README.md 'How to run' (and PROVISIONAL.md 'Re-run every benchmark on an idle machine')",
   "severity": "major",
   "problem": "Following the READMEs to re-run a benchmark overwrites the results the reports cite. Every stage writes fixed file names into <stage>/results/ (bench_common.RESULTS, proto_common.RESULTS, run_with_load.py RESULTS, run_matrix.py outdir=HERE/results/<matrix>), appends to run_all_log.txt and _log.txt, and build.bat overwrites cpp/build/. Only bench_e_e2e (BENCH_E2E_REP) and p8 (P8_REP) can rename their outputs. P6 and the cpp matrices cannot.",
   "fix": "Add an output-directory variable (for example FRAME_PIPELINE_RESULTS_DIR) read by bench_common.py, proto_common.py, the three run_with_load.py copies, run_all.py and run_matrix.py, and document it in each README. Until then, document the snapshot/restore procedure in reproducibility/protect_originals.py.",
   "evidence": "reproducibility/originals_manifest.json (355 files hashed before the re-run); reproducibility/collected_files.json (152 files new or changed by the documented commands, e.g. 'changed prototypes/results/p6_ui_skellycamvenv.json', 'changed cpp/results/cpp_comparison.json', 'changed cpp/build/ringbench.exe'); reproducibility/restore_check.json (140 restored, 12 removed, all_hashes_match_original true). Script: reproducibility/protect_originals.py snapshot|collect|restore."},
  {"target": "prototypes/results/p6_ui_path.md 720p rows with the 10 ms relay poll (view_proto, view_proto_640x360, view_proto_threads, jpeg_forward, jpeg_reduced_reencode_threads; skellycamvenv)",
   "severity": "minor",
   "problem": "These rates are not reproducible point values. On an idle machine they fell from 59.4-60.1 to 43.9-45.6 payloads/s (-24% to -26%, outside the 15% tolerance). Over the same re-run, view_proto_threads_poll2ms stayed at 60.1/s at both sizes, and every 1080p row reproduced within 4%. The prototypes README already reports that one row gave 60.0 and 42.6/s at 720p in two venvs. The likely cause is the beat between a 10 ms wake-up and the 16.7 ms frame period; that is an inference, not measured.",
   "fix": "Report the 720p 10 ms-poll rows as a range (about 43-60/s, bimodal) or a median over several runs. Cite only view_proto_threads_poll2ms (60.1/s at 720p and 1080p in both runs) for a '60/s UI' claim.",
   "evidence": "reproducibility/comparison.md section 'P6 UI path': '720p view_proto (skellycamvenv) payloads/s 60.0 -> 44.3 (-26.2%)', '720p view_proto_threads_poll2ms 60.1 -> 60.1', '1080p view_proto_threads_poll2ms 60.1 -> 60.1'. Files: prototypes/results/p6_ui_skellycamvenv.json vs reproducibility/rerun/prototypes/results/p6_ui_skellycamvenv.json. Command: .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\prototypes\\run_all.py p6_ui (P6_RUN_S=10). Load: reproducibility/rerun/prototypes/results/load_p6_ui_skellycamvenv.json, idle, bg mean 2.09%."},
  {"target": "cpp/README.md table 1a, row '1080p, 5', column cpp_one_copy '(1488 / 1478)'",
   "severity": "minor",
   "problem": "The slowest-camera fps did not reproduce for the first run: 1487.6 -> 1207.2 (-18.8%). The _r2 repeat was 1478.0 -> 1400.1 (-5.3%). One writer ran slow (per-writer 1655/1207/1650/1581/1675), while the aggregate rose from 7,645 to 7,768 fps (47.56 -> 48.33 GB/s, +1.6%). In unthrottled 5-writer rows the slowest-writer statistic depends on how the writers share memory bandwidth. The original data shows the same spread (py_seq 1294 vs 1504 between run and _r2).",
   "fix": "In 1a, quote the aggregate GB/s or the median writer next to the slowest writer, or give a range over runs (cpp_one_copy 1207-1488). No conclusion changes: every implementation stays at least 20x above 60 fps.",
   "evidence": "reproducibility/comparison.md section 'C++ vs Python ring': 'write_1080p_n5_cpp_one_copy slowest-camera fps 1487.6 -> 1207.2 (-18.8%)'. Files: cpp/results/ring_write/write_1080p_n5_cpp_one_copy.json vs reproducibility/rerun/cpp/results/ring_write/write_1080p_n5_cpp_one_copy.json (roles[].fps). Command: cmd /c benchmarks\\frame_pipeline\\cpp\\build.bat then .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\run_all.py ring. Load: rerun/cpp/results/load_ring_write.json, idle, bg mean 2.87%."},
  {"target": "baseline/README.md 'What changed in the conclusions' bullet 1: 'The memcpy bracket ... holds 59.99-60.00 fps with 0 frames missed at both sizes'",
   "severity": "minor",
   "problem": "The 5x1080p memcpy re-run had 3 sensor frames never grabbed (0 and 0 in the two original idle runs; 5 in the provisional 2026-10-25 run) at 59.97 fps. Its tick->written p99 was 14.5 ms, against 7.6 ms in the original. The 5x60 pass is unchanged.",
   "fix": "Write '59.97-60.00 fps with 0-3 of about 9,000 sensor frames never grabbed (3 idle runs)'.",
   "evidence": "reproducibility/rerun/baseline/results/e_e2e_summary.md row 'e_e2e_1080p_memcpy_ui_repro.json | 1080p | memcpy | True | 59.97 | 1802 / 1803 | 3 | True | ... | 3.9 / 14.5 / 23.4'. Command: $env:BENCH_E2E_REP='_repro'; .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\run_with_load.py repro_e_e2e_1080p_memcpy_ui repro_e_e2e_1080p_memcpy_ui_stdout.log 600 -- .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\bench_e_e2e.py 1080p memcpy ui 30. Load: idle, bg mean 2.83%."},
  {"target": "baseline/summarize_e2e.py and prototypes/p8_e2e_proto.py --summarize (baseline/README.md e2e row: 'The summary has 8 runs')",
   "severity": "minor",
   "problem": "Both summarizers include every e_e2e_*.json / p8_e2e_*.json in results/, so a documented repeat run (BENCH_E2E_REP) changes the summary. After this stage's 4 repeats, e_e2e_summary.md had 12 rows.",
   "fix": "Pass an explicit file list to the summarizers, or state in the README that repeat files are merged into the summary.",
   "evidence": "reproducibility/rerun/baseline/results/e_e2e_summary.md (12 data rows, including the 4 *_repro*.json rows). Command: .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\summarize_e2e.py."},
  {"target": "cpp/README.md 'How to run' and cpp/build.bat",
   "severity": "minor",
   "problem": "(a) The README lists every prerequisite (pybind11 install, the cv2 4.8.0 throw-away venv, make_inputs.py) without saying that only the codec step needs the venv and the inputs. run_all.py ring ran with exit 0 while neither existed. (b) build.bat prints \"'vswhere.exe' is not recognized as an internal or external command\" (from vcvars64.bat) before 'BUILD OK'. That message is harmless but undocumented. The rebuilt .exe/.pyd files differ by hash from the originals (probably the PE link timestamp, not checked); the .lib is identical. Ring results reproduced, so the binaries behave the same.",
   "fix": "In cpp/README.md, mark which prerequisites each run_all.py step needs, and note the vswhere message as expected.",
   "evidence": "reproducibility/build_stdout.log (vswhere line, 'BUILD OK', MSVC 19.42.34436); reproducibility/rerun/cpp/results/run_all_log.txt ('ring_write exit=0 703s', 'ring_spsc exit=0 754s'); C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp had no venv_cv48 and bench_tmp had no cpp_inputs at the time; reproducibility/collected_files.json lists cpp/build/*.exe and .pyd as 'changed', and not the .lib."},
 ],
 "reproduced": [],
 "summary": "",
}


def rep(result, original, rerun, ok, cmd):
    res["reproduced"].append(dict(result=result, original=original, rerun=rerun, within_tolerance=ok, command=cmd))


E2E = ("PowerShell, from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam: $env:PYTHONIOENCODING='utf-8'; $env:BENCH_E2E_REP='{rep}'; "
       ".venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\run_with_load.py {name} {name}_stdout.log 600 -- "
       ".venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\baseline\\bench_e_e2e.py {args}")
rep("Baseline e2e, real SkellyCam stack, 5x1080p mjpeg + UI, run 1 (baseline/results/e_e2e_1080p_mjpeg_ui.json vs reproducibility/rerun/baseline/results/e_e2e_1080p_mjpeg_ui_repro.json). Load: idle (sys 3.1% before / 3.9% after, mem 35.7%, bg mean 3.36% p95 4.3%); the original was also idle.",
    "53.56 fps min cam; 964 never grabbed; files==recorded True; retrieve 10.12 / put_frame 3.64 / record_frame 1.12 ms; tick->written 23.9 / 34.4 ms; UI 36.9/s; FAIL at 5x60",
    "53.92 fps (+0.7%); 911 never grabbed; files==recorded True; 10.25 / 3.71 / 1.11 ms; 23.9 / 35.1 ms; UI 36.7/s; FAIL at 5x60", True,
    E2E.format(rep="_repro", name="repro_e_e2e_1080p_mjpeg_ui", args="1080p mjpeg ui 30"))
rep("Baseline e2e 5x1080p mjpeg + UI, run 2 (e_e2e_1080p_mjpeg_ui_rep2.json vs e_e2e_1080p_mjpeg_ui_repro_rep2.json). Load idle (bg mean 3.46%, p95 5.2%).",
    "53.57 fps; 964 never grabbed; UI 36.6/s; FAIL", "53.97 fps (+0.7%); 902 never grabbed; UI 37.1/s; FAIL", True,
    E2E.format(rep="_repro_rep2", name="repro_e_e2e_1080p_mjpeg_ui_rep2", args="1080p mjpeg ui 30"))
rep("Baseline e2e 5x1080p memcpy + UI (e_e2e_1080p_memcpy_ui.json vs e_e2e_1080p_memcpy_ui_repro.json). Load idle (bg mean 2.83%).",
    "59.99 fps; 0 never grabbed; UI 39.9/s; tick->written p99 7.6 ms; PASS", "59.97 fps (-0.03%); 3 never grabbed; UI 40.9/s; p99 14.5 ms; PASS", True,
    E2E.format(rep="_repro", name="repro_e_e2e_1080p_memcpy_ui", args="1080p memcpy ui 30"))
rep("Baseline e2e 5x720p mjpeg + UI (e_e2e_720p_mjpeg_ui.json vs e_e2e_720p_mjpeg_ui_repro.json). Load idle (bg mean 2.8%).",
    "60.00 fps; 0 never grabbed; UI 57.0/s; PASS", "60.00 fps; 0 never grabbed; UI 57.5/s; PASS", True,
    E2E.format(rep="_repro", name="repro_e_e2e_720p_mjpeg_ui", args="720p mjpeg ui 30"))
P = ("PowerShell, from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam: $env:PYTHONIOENCODING='utf-8'; .venv\\Scripts\\python.exe "
     "benchmarks\\frame_pipeline\\prototypes\\run_all.py p6_ui p8_e2e_1080p_imdecode_msmf p8_e2e_1080p_imdecode_off p8_e2e_summarize")
rep("Best record-path prototype P8 1080p imdecode + MSMF, 2 runs (prototypes/results/p8_e2e_1080p_imdecode_msmf{,_rep2}.json vs reproducibility/rerun/prototypes/results/ same names). Load idle (bg mean 3.56 / 3.31%).",
    "59.95 / 59.95 fps; 0 / 0 never grabbed; files==produced & consecutive True; UI 47.3 / 46.9/s; recorder CPU 954 / 924%; PASS",
    "59.95 / 59.95 fps; 0 / 0; True; UI 47.2 / 47.4/s; recorder CPU 939 / 954%; PASS", True, P)
rep("P8 1080p imdecode_off + passthrough, 2 runs (p8_e2e_1080p_imdecode_off_passthrough{,_rep2}.json). Load idle (bg mean 2.03 / 2.06%).",
    "59.97 / 59.97 fps; 0 / 0; tick->written median/p99 0.8/1.5 ms; UI 49.6 / 49.9/s; PASS",
    "59.97 / 59.97 fps; 0 / 0; 0.8/1.6 and 0.8/1.4 ms; UI 51.3 / 50.3/s; PASS", True, P)
rep("Best UI-path prototype P6 view_proto_threads_poll2ms (prototypes/results/p6_ui_skellycamvenv.json vs rerun). Load idle (bg mean 2.09%).",
    "1080p 60.1 payloads/s, build 1.96 ms, event loop blocked 0.04 ms; 720p 60.1/s",
    "1080p 60.1/s, build 1.99 ms, blocked 0.04 ms; 720p 60.1/s", True, P)
rep("P6 1080p current path cur_copy_real / view_real (same files)", "51.8 / 57.8 payloads/s", "51.6 / 57.7 payloads/s", True, P)
rep("P6 720p rows with 10 ms polling (view_proto, view_proto_640x360, view_proto_threads, jpeg_forward, jpeg_reduced_reencode_threads; skellycamvenv)",
    "59.4-60.1 payloads/s", "43.9-45.6 payloads/s (-24% to -26%); the README already notes bimodality (60.0 vs 42.6/s across venvs)", False, P)
C = ("PowerShell, from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam: cmd /c benchmarks\\frame_pipeline\\cpp\\build.bat; $env:PYTHONIOENCODING='utf-8'; "
     ".venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\run_all.py ring; .venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\summarize_load.py; "
     ".venv\\Scripts\\python.exe benchmarks\\frame_pipeline\\cpp\\summarize.py")
rep("C++ vs Python ring, write-only 1080p N=1 median put ms: sk_head / cpp_head_port / py_seq / hybrid / cpp_one_copy (cpp/results/cpp_comparison.json ring_write vs reproducibility/rerun/cpp/results/cpp_comparison.json). Rebuilt with build.bat (BUILD OK). Load idle (ring_write bg mean 2.87%, p95 5.0%).",
    "1.326 / 1.276 / 0.147 / 0.147 / 0.146 ms", "1.326 / 1.274 / 0.147 / 0.146 / 0.145 ms", True, C)
rep("Ring write-only 5x1080p slowest-camera fps (run/_r2): sk_head; cpp_head_port; py_seq; hybrid",
    "356/355; 365/369; 1294/1504; 1316/1433", "357/352; 363/371; 1436/1456; 1361/1511", True, C)
rep("Ring write-only 5x1080p cpp_one_copy slowest-camera fps (run/_r2)", "1488 / 1478 (aggregate 47.56 / 48.26 GB/s)",
    "1207 / 1400 (aggregate 48.33 / 48.86 GB/s)", False, C)
rep("Lossless SPSC 5x1080p unthrottled slowest-camera fps (run/_r2): sk_head; py_seq; hybrid; cpp_proc; cpp_thread. Load idle (ring_spsc bg mean 3.12%, p95 5.86%).",
    "243/250; 527/537; 530/526; 543/535; 545/545", "246/243; 536/534; 534/532; 530/538; 539/541", True, C)
rep("SPSC 5x1080p paced 60: all 5 impls 60.0 fps; publish->read median ms sk_head / py_seq / cpp_proc",
    "60.0 fps all; 3.736 / 2.019 / 1.945 ms; PASS", "60.0 fps all; 3.749 / 2.062 / 1.983 ms; PASS", True, C)
rep("SPSC lost / torn frames, all 50 runs", "0 / 0", "0 / 0", True, C)
rep("SPSC 64x64, 1 pair unthrottled fps: sk_head / py_seq / cpp_proc", "12,977 / 347,056 / 1,149,700", "12,992 / 347,424 / 1,133,744", True, C)
res["summary"] = (
    "Every headline result reproduced with the documented commands, on an idle machine "
    "(system CPU 3.0% / memory 35.9% at start 05:13, 4.2% / 35.7% at end 06:02; every measuring step idle, background mean 2.0-3.6%, p95 3.1-5.9%; "
    "reproducibility/load_summary_rerun.md). All 18 pass/fail rows at 5x60 matched, and 130 of 136 throughput rows were within 15% "
    "(reproducibility/comparison.md, built by compare.py). "
    "Baseline 5x1080p mjpeg + UI: 53.92 / 53.97 fps vs 53.56 / 53.57 (FAIL both times, 902-911 vs 964 frames never grabbed). 5x1080p memcpy: 59.97 fps (PASS; 3 frames never grabbed vs 0). 5x720p mjpeg: 60.00 fps. "
    "P8 imdecode + MSMF: 59.95 / 59.95 fps with 0 lost (identical). P8 imdecode_off + passthrough: 59.97 with tick->written 0.8 ms (identical). "
    "P6 poll2ms UI: 60.1/s at both sizes (identical). C++ vs Python ring: all n=1 rows within 2%, SPSC 5x1080p within 3%, 0 lost / 0 torn in 50 runs, so the 'no C++ port needed' verdict holds. "
    "Disk path: files == recorded and consecutive in all 8 e2e re-runs. "
    "Outside tolerance, with no conclusion changed: 5 P6 720p rows with 10 ms polling (about 60 -> 44/s, bimodal timer-phase effect already noted in the prototypes README) and one slowest-writer statistic (cpp_one_copy 5x1080p 1488 -> 1207 fps, aggregate +1.6%). "
    "Main README problem: a documented re-run overwrites the cited result files (no output-dir option). This stage snapshotted 355 files, re-ran, collected the 152 new or changed outputs into reproducibility/rerun/, and restored the originals with all hashes verified (restore_check.json). "
    "Other README problems: summarizers merge repeat runs; cpp prerequisites not mapped to steps; harmless vswhere message from build.bat. "
    "Not re-run: baseline a/b/c/d/f/g, P1-P5, P7, P9/P9b, P10, and the cpp codec/memcpy/micro steps. No real cameras were used. "
    "summary.md could not be written because the agent harness refused report .md files; this JSON and comparison.md carry the content.")
with open(r"C:\Users\Dom\GitHub\freemocap\skellycam\benchmarks\frame_pipeline\study_state\critic_reproduce_result.json", "w", encoding="utf-8") as f:
    f.write(json.dumps(res, indent=1))
print(len(res["issues"]), len(res["reproduced"]))
