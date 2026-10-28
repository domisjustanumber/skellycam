import json,sys
from pathlib import Path
d=Path(sys.argv[1]); s=json.loads((d/"summary.json").read_text()); r=s.get("results",{})
print("error",s.get("error"),"alt",s.get("alt_selected",{}).get("alt"),s.get("alt_selected",{}).get("bytes_per_interval"),"neg",s.get("probe_commit",{}).get("negotiated"))
print({k:r.get(k) for k in ["frames","valid_jpeg","fps_host_after_skip30","bad_headers","err_flag_payloads","overflows","packets","packets_with_error_status","payloads","empty_packets","pts_gaps_ge_1p5_period","host_arrival_gaps_ge_1p5_period","time_to_first_frame_ms","latency_arrival_minus_pts_ms","cpu","pts_delta_ticks_min","pts_delta_ticks_max"]})
print("stream_stats",s.get("stream_stats"),"fit",s.get("device_clock_fit"))
p=d/"pipes.json"
if p.exists():
    for sn in json.loads(p.read_text())["snapshots"]:
        for c in sn["snapshot"] if isinstance(sn["snapshot"],list) else []:
            if c["idProduct"]=="0843": print("PIPES", [(x["bEndpointAddress"],x["type"],x["wMaxPacketSize"],x.get("base_packet_bytes"),x.get("transactions_per_microframe")) for x in c["open_pipes"]], c.get("matched_alt_settings"))
