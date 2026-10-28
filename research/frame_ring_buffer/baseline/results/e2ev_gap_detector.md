# e2e per-frame analysis: rank-4 drop detector validation, start/stop pause gap, grab-stamp vs capture-time spread

Source: bench_e2e_variants.py dumps (`*_perframe.npz`), real SkellyCam stack at 23ccbf20, 5 synthetic cameras, 30 s recording. Detector values are sums over 5 cameras. T = 16.667 ms (configured 60 fps).

| run | true never grabbed | per_interval_round (grab / retrieve) | accumulated_clock (grab / retrieve) | fractional_sum (grab / retrieve) | skipped ticks in first 10 recorded frames (sum 5 cams) | skipped ticks in last 10 recorded frames | largest single gap in last 10 (ticks) | skipped ticks elsewhere | grab-stamp spread p99 ms | sensor-tick spread median / p99 / max ms |
|---|---|---|---|---|---|---|---|---|---|---|
| e2ev_cvthreads1_1080p_mjpeg_ui | 788 | 56 / 98 | 790 / 790 | 905 / 936 | 1 | 13 | 1 | 774 | 1.29 | 13.32 / 15.58 / 15.58 |
| e2ev_dshowlike_1080p_mjpeg_ui_v2 | 874 | 10 / 26 | 875 / 875 | 926 / 958 | 0 | 10 | 1 | 864 | 2.82 | 12.88 / 15.39 / 20.20 |
| e2ev_extracpu3_1080p_mjpeg_ui | 1732 | 49 / 123 | 1730 / 1735 | 1730 / 1730 | 13 | 14 | 1 | 1705 | 2.37 | 11.55 / 16.28 / 17.05 |
| e2ev_head_1080p_mjpeg_noui_rep2 | 655 | 10 / 12 | 655 / 657 | 766 / 806 | 0 | 12 | 1 | 643 | 2.22 | 10.02 / 16.39 / 16.94 |
| e2ev_head_1080p_mjpeg_ui | 878 | 16 / 50 | 880 / 880 | 940 / 978 | 0 | 11 | 1 | 867 | 2.54 | 12.09 / 14.95 / 14.95 |
| e2ev_nocopycopy+cvthreads1_1080p_mjpeg_ui | 254 | 7 / 21 | 255 / 255 | 410 / 455 | 0 | 0 | 0 | 254 | 1.25 | 8.21 / 16.08 / 16.08 |
| e2ev_nocopycopy_1080p_mjpeg_ui | 170 | 10 / 10 | 175 / 175 | 353 / 472 | 0 | 5 | 1 | 165 | 2.32 | 7.79 / 15.81 / 17.52 |
| e2ev_nocopycopy_1080p_mjpeg_ui_rep2 | 150 | 15 / 16 | 154 / 152 | 329 / 419 | 0 | 5 | 1 | 145 | 1.98 | 7.02 / 15.98 / 17.04 |
