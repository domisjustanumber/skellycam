# Arduino sync research: sources and downloads

The plan was researched on 2026-10-25 in a temp scratchpad. On 2026-10-28 the research output was moved here and the scratchpad was deleted.

## In this folder

| File | What it is |
| --- | --- |
| [timing_report.md](timing_report.md) | Clock-accuracy research for Arduino Nano/Uno boards (resonators, Timer1 quantization, jitter, baud error) |
| [verify.json](verify.json) | Verifier verdicts on the hardware and reasoning claims (`vHardware`, `vReasoning`) and the two critiques of the draft plan (`critCode`, `critHw`) |

The draft plan the workflow wrote (`final_plan.md`) was identical to [../PLAN.md](../PLAN.md) apart from the title block, so it was not kept.

## Not kept: re-download from the source

These were downloaded or cloned for reference. They are third-party material that can be fetched again, so they are not committed.

| What | Source |
| --- | --- |
| MoCapSTR (firmware and app), read-only clone | <https://github.com/ZClassified/MoCapSTR> at commit `11a9edb92bba0241ce8a5a6afdf48e2606fe10af` (2026-10-02) |
| OpenCV video I/O backends: `cap_dshow.cpp`, `cap_msmf.cpp`, `cap_v4l.cpp`, `cap_avfoundation.mm`, `cap_avfoundation_mac.mm` | <https://github.com/opencv/opencv>, `modules/videoio/src/` (version not recorded) |
| openpnp-capture platform code: `win_platformstream.cpp`, `linux_platformstream.cpp`, `mac_platformstream.mm`, `mac_uvcctrl.mm` | <https://github.com/openpnp/openpnp-capture> (version not recorded) |
| InnoMaker U20CAM-9281M manual and control scripts | <https://github.com/INNO-MAKER/U20CAM-9281M> (manual: `Manual/U20CAM-9281M-V11.pdf`) |
| Arducam global-shutter external-trigger docs | <https://docs.arducam.com/Raspberry-Pi-Camera/Global-Shutter-Camera/external-trigger/> |
| Arduino Nano (A000005) manual and CAD files | <https://www.arduino.cc/en/uploads/Main/ArduinoNanoManual23.pdf>, <https://docs.arduino.cc/static/e3c4fe1f9bee7ec63df398422b3257f4/A000005-cad-files.zip> |
| Arduino Uno R3 (A000066) schematic | <https://docs.arduino.cc/resources/schematics/A000066-schematics.pdf> |
| Arduino Uno R4 Minima (ABX00080) schematic and RA4M1 datasheet | <https://docs.arduino.cc/resources/schematics/ABX00080-schematics.pdf>, <https://docs.arduino.cc/resources/datasheets/ra4m1-datasheet.pdf> |
| Arduino Nano Every (ABX00028) and Uno R4 WiFi (ABX00087) datasheets | <https://docs.arduino.cc> product pages for ABX00028 and ABX00087 |
| ATmega328P datasheet | <https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf> |
| ATmega4809 datasheet | <https://cdn.sparkfun.com/assets/5/d/2/b/3/DS-ATMega4809.pdf> |
| Murata CSTCE16M0V53 resonator datasheet | <https://4donline.ihs.com/images/VipMasterIC/IC/MURE/MURE-S-A0001719029/MURE-S-A0001719029-1.pdf> |

Every other web source is cited inline in [timing_report.md](timing_report.md) and [verify.json](verify.json).
