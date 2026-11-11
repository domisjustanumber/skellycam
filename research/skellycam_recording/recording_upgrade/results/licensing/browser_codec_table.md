| item | Electron 35.7.5 (Chromium 134.0.6998.205) | Electron 45.2.3 (Chromium 156.0.8078.80) | Chrome 156.0.0.0 |
|---|---|---|---|
| video `h264_libx264.mp4` | plays + decodes | plays + decodes | plays + decodes |
| video `hevc_libx265.mp4` | plays + decodes | plays + decodes | plays + decodes |
| video `av1_svt.mp4` | plays + decodes | plays + decodes | plays + decodes |
| video `av1_svt.webm` | plays + decodes | plays + decodes | plays + decodes |
| video `av1_svt.mkv` | plays + decodes | plays + decodes | plays + decodes |
| video `vp9.webm` | plays + decodes | plays + decodes | plays + decodes |
| video `vp9.mp4` | plays + decodes | plays + decodes | plays + decodes |
| video `vp8.webm` | plays + decodes | plays + decodes | plays + decodes |
| video `mjpeg.mkv` | error 4: DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no suppor | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe |
| video `mjpeg.avi` | error 4: DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: open context fa | error 4: PipelineStatus::DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: | error 4: PipelineStatus::DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: |
| video `mjpeg.mp4` | error 4: DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no suppor | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe |
| video `ffv1.mkv` | error 4: DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no suppor | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe |
| video `prores.mov` | error 4: DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no suppor | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe | error 4: PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDe |
| video `utvideo.avi` | error 4: DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: open context fa | error 4: PipelineStatus::DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: | error 4: PipelineStatus::DEMUXER_ERROR_COULD_NOT_OPEN: FFmpegDemuxer: |
| audio `opus.webm` | plays | plays | plays |
| audio `opus.mp4` | plays | plays | plays |
| audio `flac.flac` | plays | plays | plays |
| audio `flac.mp4` | plays | plays | plays |
| audio `aac.m4a` | plays | plays | plays |
| audio `pcm.wav` | plays | plays | plays |
| audio `mp3.mp3` | plays | plays | plays |
| img `still.jpg` | load | load | load |
| img `still.jxl` | error | load | load |
| img `still.avif` | load | load | load |
| img `still.webp` | load | load | load |
| img `still.png` | load | load | load |
| img `still.jp2` | error | error | error |
| canPlayType / MSE `video/mp4; codecs="avc1.42E01E"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/mp4; codecs="hvc1.1.6.L93.B0"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/mp4; codecs="av01.0.04M.08"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/webm; codecs="av01.0.04M.08"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/webm; codecs="vp09.00.10.08"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/mp4; codecs="vp09.00.10.08"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/webm; codecs="vp8"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `video/x-matroska; codecs="av01.0.04M.08"` | '' / False | 'probably' / False | 'probably' / False |
| canPlayType / MSE `video/x-matroska; codecs="avc1.42E01E"` | '' / False | 'probably' / False | 'probably' / False |
| canPlayType / MSE `video/x-msvideo` | '' / False | '' / False | '' / False |
| canPlayType / MSE `audio/webm; codecs="opus"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `audio/mp4; codecs="opus"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `audio/mp4; codecs="mp4a.40.2"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `audio/mp4; codecs="flac"` | 'probably' / True | 'probably' / True | 'probably' / True |
| canPlayType / MSE `audio/flac` | 'probably' / False | 'probably' / False | 'probably' / False |
| canPlayType / MSE `audio/wav` | 'maybe' / False | 'maybe' / False | 'maybe' / False |
| canPlayType / MSE `audio/mpeg` | 'probably' / True | 'probably' / True | 'probably' / True |
| WebCodecs dec / enc `avc1/no-preference` | True / True | True / True | True / True |
| WebCodecs dec / enc `avc1/prefer-hardware` | True / True | True / True | True / True |
| WebCodecs dec / enc `avc1/prefer-software` | True / True | True / True | True / True |
| WebCodecs dec / enc `hevc/no-preference` | True / True | True / True | True / True |
| WebCodecs dec / enc `hevc/prefer-hardware` | True / True | True / True | True / True |
| WebCodecs dec / enc `hevc/prefer-software` | False / False | False / False | False / False |
| WebCodecs dec / enc `av1/no-preference` | True / True | True / True | True / True |
| WebCodecs dec / enc `av1/prefer-hardware` | True / False | True / False | True / False |
| WebCodecs dec / enc `av1/prefer-software` | True / True | True / True | True / True |
| WebCodecs dec / enc `vp9/no-preference` | True / True | True / True | True / True |
| WebCodecs dec / enc `vp9/prefer-hardware` | True / False | True / False | True / False |
| WebCodecs dec / enc `vp9/prefer-software` | True / True | True / True | True / True |
| WebCodecs dec / enc `vp8/no-preference` | True / True | True / True | True / True |
| WebCodecs dec / enc `vp8/prefer-hardware` | False / False | False / False | False / False |
| WebCodecs dec / enc `vp8/prefer-software` | True / True | True / True | True / True |
| ImageDecoder `image/jpeg` | True | True | True |
| ImageDecoder `image/jxl` | False | True | True |
| ImageDecoder `image/avif` | True | True | True |
| ImageDecoder `image/webp` | True | True | True |
| ImageDecoder `image/png` | True | True | True |
| ImageDecoder `image/jp2` | False | False | False |
