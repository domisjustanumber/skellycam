# MetadataBufferSizeInKB0 revert, 2026-11-09

Dom decided that testing is tier 0 only (no registry changes from here on, no UVC PTS/SCR testing), and asked for the
11-08 metadata registry value to be reverted so tier-0 results reflect a machine as found.

- `revert.log`, `revert.json`: `remove_uvc_metadata_all.ps1` (elevated, 08:49 local) removed all 26 values (13 camera
  interface instances, current and stale, x 2 device classes) for 046D, 1532 and 4C4A. 0 failures; a non-elevated
  re-query found 0 remaining. No device was restarted.
- Dom replugged all four cameras into the same ports (arrivals 09:25-09:31 local). Instance IDs unchanged, problem
  code 0, Kiyo still SuperSpeed on the Thunderbolt xHCI (Genesys hub USB 3 half, port 4).
- `c922_check_after_replug/`: wincam 1.2 MF capture, C922 MJPG 1280x720@30, 2 s: 62/62 valid frames, 30.03 fps,
  readback ok, **0/62 frames carry UVC metadata** (`with_uvc_metadata` 0, `capture_metadata_attr` false). The revert
  took effect.
