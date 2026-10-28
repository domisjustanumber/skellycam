# P9b - camera MJPEG bytes through PyAV's FFmpeg dshow input (vcodec=mjpeg, demux only, no decode), 3 s each

| device | size | framerate option | opened | negotiated rate | delivered fps | packets starting FF D8 / packets | median bytes/frame | CPU ms/packet |
|---|---|---|---|---|---|---|---|---|
| c922 Pro Stream Webcam | 1280x720 | None | yes | 10.0 | 10.3 | 0 / 31 | 1843200.0 | 3.024 |
| c922 Pro Stream Webcam | 1280x720 | 30 | yes | 30.0 | 30.3 | 91 / 91 | 24569.0 | 0.515 |
| c922 Pro Stream Webcam | 1280x720 | 60 | yes | 60.0 | 30.1 | 91 / 91 | 26899.0 | 0.000 |
| c922 Pro Stream Webcam | 1920x1080 | 30 | yes | 30.0 | 30.3 | 91 / 91 | 57063.0 | 0.343 |
| c922 Pro Stream Webcam | 1920x1080 | 60 | no: OSError(5, 'I/O error', 'video=c922 Pro Stream Webcam') | - | - | - | - | - |
| Logitech Webcam C930e | 1280x720 | None | yes | 10.0 | 10.3 | 0 / 31 | 1843200.0 | 0.504 |
| Logitech Webcam C930e | 1280x720 | 30 | yes | 30.0 | 30.4 | 92 / 92 | 63071.0 | 0.000 |
| Logitech Webcam C930e | 1280x720 | 60 | no: OSError(5, 'I/O error', 'video=Logitech Webcam C930e') | - | - | - | - | - |
| Logitech Webcam C930e | 1920x1080 | 30 | yes | 30.0 | 30.4 | 92 / 92 | 116176.0 | 0.510 |
| Logitech Webcam C930e | 1920x1080 | 60 | no: OSError(5, 'I/O error', 'video=Logitech Webcam C930e') | - | - | - | - | - |
| Razer Kiyo Pro | 1280x720 | None | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| Razer Kiyo Pro | 1280x720 | 30 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| Razer Kiyo Pro | 1280x720 | 60 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| Razer Kiyo Pro | 1920x1080 | 30 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| Razer Kiyo Pro | 1920x1080 | 60 | no: OSError(5, 'I/O error', 'video=Razer Kiyo Pro') | - | - | - | - | - |
| USB Camera | 1280x720 | None | yes | 30.0 | 26.0 | 79 / 79 | 27408.0 | 0.396 |
| USB Camera | 1280x720 | 30 | yes | 30.0 | 26.1 | 79 / 79 | 27412.0 | 0.396 |
| USB Camera | 1280x720 | 60 | no: OSError(5, 'I/O error', 'video=USB Camera') | - | - | - | - | - |
| USB Camera | 1920x1080 | 30 | yes | 30.0 | 26.1 | 79 / 79 | 59837.0 | 0.000 |
| USB Camera | 1920x1080 | 60 | no: OSError(5, 'I/O error', 'video=USB Camera') | - | - | - | - | - |
