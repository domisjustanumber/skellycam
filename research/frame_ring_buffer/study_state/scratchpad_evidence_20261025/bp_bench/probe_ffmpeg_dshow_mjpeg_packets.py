"""
MJPEG passthrough capture on Windows without OpenCV: open a webcam through FFmpeg's dshow demuxer (via PyAV),
request vcodec=mjpeg, and read *packets* (compressed JPEG bytes) without decoding them.
Reports packet sizes -> real MJPEG bitrate, packet rate, CPU per packet, and that a packet decodes.

Run:
    cd C:\\Users\\Dom\\GitHub\\freemocap\\skellycam
    .venv\\Scripts\\python.exe -I <scratch>\\bp_bench\\probe_ffmpeg_dshow_mjpeg_packets.py <out_dir> "<camera friendly name>" [WxH] [fps]
"""
import json
import os
import statistics
import sys
import time

import av

out_dir, cam = sys.argv[1], sys.argv[2]
size = sys.argv[3] if len(sys.argv) > 3 else "1280x720"
fps = sys.argv[4] if len(sys.argv) > 4 else "60"
opts = {"vcodec": "mjpeg", "video_size": size, "framerate": fps, "rtbufsize": "256M"}
c = av.open(f"video={cam}", format="dshow", options=opts)
vs = c.streams.video[0]
info = {"camera": cam, "requested": opts, "codec": vs.codec_context.name, "w": vs.codec_context.width,
        "h": vs.codec_context.height, "avg_rate": str(vs.average_rate)}
sizes, arrivals, pts = [], [], []
first_pkt = None
cpu0 = time.process_time()
for i, pkt in enumerate(c.demux(vs)):
    if pkt.size == 0:
        continue
    arrivals.append(time.perf_counter())
    sizes.append(pkt.size)
    pts.append(pkt.pts)
    if first_pkt is None:
        first_pkt = bytes(pkt)
    if len(sizes) >= 660:
        break
cpu = time.process_time() - cpu0
c.close()
arr = arrivals[60:]
gaps = [b - a for a, b in zip(arr, arr[1:])]
dec = av.CodecContext.create("mjpeg", "r")
frames = dec.decode(av.Packet(first_pkt))
info.update({
    "packets": len(sizes), "bytes_median": statistics.median(sizes[60:]), "bytes_max": max(sizes[60:]),
    "MBps_median": statistics.median(sizes[60:]) / statistics.median(gaps) / 1e6,
    "packet_rate_fps": 1 / statistics.median(gaps), "gap_ms_max": max(gaps) * 1e3,
    "starts_with_FFD8": first_pkt[:2] == b"\xff\xd8",
    "cpu_ms_per_packet_demux_only": cpu / len(sizes) * 1e3,
    "first_packet_decodes_to": [frames[0].width, frames[0].height, frames[0].format.name] if frames else None,
})
print(json.dumps(info, indent=2))
with open(os.path.join(out_dir, f"probe_ffmpeg_dshow_mjpeg_{cam.replace(' ', '_')}_{size}_{fps}.json"), "w") as f:
    json.dump(info, f, indent=2)
