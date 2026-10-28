@echo off
rem DirectShow per-stage HRESULT probe: Kiyo (MJPG 1280x720@30, 640x480@30, YUY2 640x480@30) + C922 control. Run under camlock.
rem usage: kiyo_lens_dshow.bat <out.jsonl>
set E=%~dp0..\build\dshow_open_probe.exe
"%E%" --dev "vid_1532&pid_0e05" --sub MJPG --w 1280 --h 720 --fps 30 >> "%~1"
"%E%" --dev "vid_1532&pid_0e05" --sub MJPG --w 640 --h 480 --fps 30 >> "%~1"
"%E%" --dev "vid_1532&pid_0e05" --sub YUY2 --w 640 --h 480 --fps 30 >> "%~1"
"%E%" --dev "vid_046d&pid_085c" --sub MJPG --w 1280 --h 720 --fps 30 >> "%~1"
