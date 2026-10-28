Adversarial verifier (libusb_rust area), 2026-10-28 ~03:50Z, Gerald, not elevated, no camera opened.
Binary: rerun agent's scratch build of research/usb_cameras/libusb (uvc_capture_test.exe, libusb 1.0.30 + libuvc d07de4fa + patch 0001).
Runs: uvc_capture_test.exe --frame-qpc-only 5  (dir 20261028T0350Z_verifier_rerun20261027)
      uvc_capture_test.exe --frame-qpc-only 20 (this dir)
Analysis: python ../frame_qpc_drift.py usb_frame_qpc.jsonl  -> analysis.txt (also run on the 5 s run and the earlier 2 s file ../usb_frame_qpc.jsonl)
Finding: residual vs a pure (frame*8+uframe)*125 us model is 0 only for the first ~2.3-3.6 s after START_TRACKING;
afterwards the driver's frame->QPC mapping shifts (hc0 up to +53/+117 us, hc1 down to -641 us over 20 s), and
the returned QPC is later than the QPC read after DeviceIoControl returned in 41/396 (hc0) and 208/396 (hc1) samples.
The earlier 2 s run and the rerun agent's ~0.35 s win_usb_frame_qpc run are too short to see this.
