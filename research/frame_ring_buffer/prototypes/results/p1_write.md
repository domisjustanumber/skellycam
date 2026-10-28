# P1 - camera write path: decode/capture + publish into shm (5 spawned processes, unthrottled)

RUN_S=10.0s per config after 1 ring lap + 2.0s warm-up; cv2.setNumThreads(1) per process; 30 distinct q90 JPEGs.
`total` = decode/capture + publish per frame. `publish` = everything after the pixels exist (put_frame, or seq commit).

| size | variant | venv | per-cam fps (min) | total median / worst p99 ms | decode/capture median ms | publish median / worst p99 ms | CPU ms/frame | full-frame copies after decode | which copies | in-place / content verified |
|---|---|---|---|---|---|---|---|---|---|---|
| 1080p | cur_imdecode_putframe | skellycamvenv | 97 | 10.202 / 12.558 | 7.934 | 2.217 / 3.537 | 10.245 | 3 | imdecode output -> private recarray (1) + copy.copy (2) + slot assignment (3) | - |
| 1080p | cur_memcpy_putframe | skellycamvenv | 238 | 4.109 / 5.395 | 1.032 | 3.085 / 4.046 | 4.155 | 3 | stand-in memcpy into private (1) + copy.copy (2) + slot assignment (3) | - |
| 1080p | cur_vcap_putframe | skellycamvenv | 85 | 11.670 / 14.165 | 9.029 | 2.618 / 3.891 | 11.605 | 2 | retrieve writes the private recarray in place; copy.copy (1) + slot assignment (2) | - |
| 1080p | cur_memcpy_putdata_nocopycopy | skellycamvenv | 431 | 2.284 / 3.216 | 1.117 | 1.166 / 1.854 | 2.301 | 2 | stand-in memcpy into private (1) + slot assignment (2); copy.copy removed | [True, True, True, True, True] |
| 1080p | cur_memcpy_putdata_u8copyto | skellycamvenv | 428 | 2.280 / 3.248 | 1.113 | 1.167 / 1.846 | 2.317 | 2 | stand-in memcpy into private (1) + np.copyto of the record as uint8 bytes (2); copy.copy removed | [True, True, True, True, True] |
| 1080p | cur_vcap_into_sk_slot | skellycamvenv | 115 | 8.574 / 10.304 | 8.511 | 0.060 / 0.143 | 8.573 | 0 | retrieve writes straight into the SkellyCam ring slot's image field; metadata written in place | [True, True, True, True, True] |
| 1080p | p_imdecode_copyslot | skellycamvenv | 132 | 7.515 / 9.065 | 7.509 | 0.006 / 0.014 | 7.553 | 1 | imdecode output -> slot (1) | - |
| 1080p | p_imdecode_copyslot | benchvenv | 131 | 7.556 / 9.448 | 7.550 | 0.005 / 0.014 | 7.609 | 1 | imdecode output -> slot (1) | - |
| 1080p | p_memcpy_slot | skellycamvenv | 870 | 1.135 / 1.686 | 1.134 | 0.002 / 0.006 | 1.144 | 1 | the stand-in memcpy goes straight into the slot (1) | - |
| 1080p | p_vcap_into_slot | skellycamvenv | 118 | 8.387 / 10.259 | 8.378 | 0.009 / 0.022 | 8.416 | 0 |  | [True, True, True, True, True] |
| 1080p | p_simplejpeg_into_slot | benchvenv | 212 | 4.680 / 6.011 | 4.679 | 0.003 / 0.009 | 4.668 | 0 |  | [True, True, True, True, True] |
| 720p | cur_imdecode_putframe | skellycamvenv | 214 | 4.591 / 5.885 | 3.525 | 1.040 / 1.718 | 4.591 | 3 | imdecode output -> private recarray (1) + copy.copy (2) + slot assignment (3) | - |
| 720p | cur_memcpy_putframe | skellycamvenv | 527 | 1.854 / 2.785 | 0.454 | 1.400 / 2.152 | 1.873 | 3 | stand-in memcpy into private (1) + copy.copy (2) + slot assignment (3) | - |
| 720p | cur_vcap_putframe | skellycamvenv | 205 | 4.765 / 6.290 | 3.719 | 1.033 / 1.807 | 4.823 | 2 | retrieve writes the private recarray in place; copy.copy (1) + slot assignment (2) | - |
| 720p | cur_memcpy_putdata_nocopycopy | skellycamvenv | 967 | 1.014 / 1.655 | 0.486 | 0.526 / 0.925 | 1.017 | 2 | stand-in memcpy into private (1) + slot assignment (2); copy.copy removed | [True, True, True, True, True] |
| 720p | cur_memcpy_putdata_u8copyto | skellycamvenv | 971 | 1.013 / 1.642 | 0.483 | 0.528 / 0.922 | 1.013 | 2 | stand-in memcpy into private (1) + np.copyto of the record as uint8 bytes (2); copy.copy removed | [True, True, True, True, True] |
| 720p | cur_vcap_into_sk_slot | skellycamvenv | 267 | 3.673 / 4.665 | 3.629 | 0.042 / 0.105 | 3.707 | 0 | retrieve writes straight into the SkellyCam ring slot's image field; metadata written in place | [True, True, True, True, True] |
| 720p | p_imdecode_copyslot | skellycamvenv | 282 | 3.469 / 4.611 | 3.465 | 0.004 / 0.009 | 3.496 | 1 | imdecode output -> slot (1) | - |
| 720p | p_imdecode_copyslot | benchvenv | 285 | 3.438 / 4.782 | 3.434 | 0.004 / 0.008 | 3.488 | 1 | imdecode output -> slot (1) | - |
| 720p | p_memcpy_slot | skellycamvenv | 1983 | 0.501 / 0.841 | 0.499 | 0.001 / 0.006 | 0.498 | 1 | the stand-in memcpy goes straight into the slot (1) | - |
| 720p | p_vcap_into_slot | skellycamvenv | 275 | 3.587 / 4.534 | 3.581 | 0.006 / 0.015 | 3.587 | 0 |  | [True, True, True, True, True] |
| 720p | p_simplejpeg_into_slot | benchvenv | 473 | 2.092 / 3.099 | 2.091 | 0.002 / 0.007 | 2.094 | 0 |  | [True, True, True, True, True] |

Environment (per run): {"skellycamvenv": {"time": "2026-10-28 01:45:43", "system_cpu_pct_1s_before_run": 7.1, "executable": "C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\.venv\\Scripts\\python.exe", "simplejpeg": null}, "benchvenv": {"time": "2026-10-28 01:51:35", "system_cpu_pct_1s_before_run": 6.5, "executable": "C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\benchmarks\\frame_pipeline\\.venv-bench\\Scripts\\python.exe", "simplejpeg": "1.9.0"}}
