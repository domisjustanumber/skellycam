Adversarial verifier rerun (libusb_rust area), 2026-10-28T03:43-03:46Z, Gerald, not elevated.
Runner: verify_nokhwa.sh c922 pairA pairB  (same COMMON args and faithful nokhwa_probe build as the rerun agent's run_nokhwa_rerun.sh; Kiyo never selected; each capture under camlock).
Note: nokhwa_probe orders cameras by MF index regardless of the order in --cameras match:, so pairA and pairB are the same start order (two repeats), not a reversed-order test.
Analysis: python ver_lat.py <frames_*.jsonl ...> > lat_analysis.txt ; ver_qpc.py recomputes win_usb_frame_qpc residuals ((frame*8+uframe)*1250 vs QPC).
Sample JPEGs kept in scratch only (privacy); luma_dqt.json has mean luma + DQT hash.
