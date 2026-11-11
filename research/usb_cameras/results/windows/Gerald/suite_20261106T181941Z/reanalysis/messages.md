# W-MULTI user messages, regenerated offline

Source run: `suite_20261106T181941Z`. Regenerated 2026-11-06T20:56:25Z by `suite/windows/tests/w_multi.py --reanalyze` with the fixed topology_model (original files untouched).
51 message records: 51 messages in 8 distinct texts, 0 without a message (refusal not foreseen).

Ratings (original -> re-analysis): `G-BW|all|mf` yes -> yes, `G-BW|all|ds` no -> partial, `G-BW|all|pyav_ds` no -> partial

## Text 1 (12 records: bandwidth_certain)

Runs: `mf_all_together_001`, `mf_all_together_002`, `mf_all_together_003`, `mf_all_together_004`, `mf_all_together_005`, `mf_all_together_006`, `mf_all_together_007`, `mf_all_together_008`, `mf_all_together_009`, `mf_all_together_010`, `mf_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_016`, `mf_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_017`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 2 (5 records: bandwidth_certain)

Runs: `mf_staggered_011`, `mf_staggered_012`, `mf_staggered_013`, `mf_staggered_014`, `mf_staggered_015`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I opened them both one after another, 2.5 s apart, USB Camera (opened last) failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 3 (10 records: bandwidth_probable)

Runs: `ds_all_together_022`, `ds_all_together_023`, `ds_all_together_030`, `ds_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_038`, `pyav_ds_all_together_044`, `pyav_ds_all_together_045`, `pyav_ds_all_together_046`, `pyav_ds_all_together_047`, `pyav_ds_all_together_048`, `pyav_ds_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_059`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, USB Camera failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 4 (13 records: bandwidth_probable)

Runs: `ds_all_together_024`, `ds_all_together_025`, `ds_all_together_026`, `ds_all_together_027`, `ds_all_together_028`, `ds_all_together_029`, `ds_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_037`, `pyav_ds_all_together_043`, `pyav_ds_all_together_049`, `pyav_ds_all_together_050`, `pyav_ds_all_together_051`, `pyav_ds_all_together_052`, `pyav_ds_pair_c922prostreamw_046d-085c_C922SN01_1280x720_30+usbcamera_4c4a-4a55_2_058`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 5 (8 records: bandwidth_probable)

Runs: `ds_staggered_032`, `ds_staggered_033`, `ds_staggered_034`, `ds_staggered_036`, `pyav_ds_staggered_053`, `pyav_ds_staggered_055`, `pyav_ds_staggered_056`, `pyav_ds_staggered_057`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I opened them both one after another, 2.5 s apart, USB Camera (opened last) failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 6 (1 records: bandwidth_probable)

Runs: `pyav_ds_pair_c922prostreamw_046d-085c_C922SN01_640x480_30+usbcamera_4c4a-4a55_2_061`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 116% of what that USB 2.0 link allows (c922 Pro Stream Webcam 640x480 YUY2 30 fps: 54%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```

## Text 7 (1 records: bandwidth_probable)

Runs: `pyav_ds_pair_c922prostreamw_046d-085c_C922SN01_1920x1080_5+usbcamera_4c4a-4a55_2_062`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, USB Camera failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 123% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1920x1080 YUY2 5 fps: 61%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 1920x1080 MJPEG 5 fps (about 16%).
```

## Text 8 (1 records: bandwidth_probable)

Runs: `pyav_ds_pair_c922prostreamw_046d-085c_C922SN01_1920x1080_5+usbcamera_4c4a-4a55_2_063`

```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error).
At these settings they need about 123% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1920x1080 YUY2 5 fps: 61%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 1920x1080 MJPEG 5 fps (about 16%).
```
