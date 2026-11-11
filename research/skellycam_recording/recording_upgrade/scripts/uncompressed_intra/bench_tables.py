"""Print the compact BENCH.md tables (t1 vs t0 side by side) from results/uncompressed_intra/bench/*.json.

  .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_tables.py
"""
import json
from pathlib import Path

B = Path(__file__).resolve().parents[2] / "results" / "uncompressed_intra" / "bench"
rows = [json.loads(p.read_text()) for p in sorted(B.glob("*.json")) if "encode_fps" in json.loads(p.read_text())]


def s(d, k, f="{:.0f}"):
    st = d["stats"][k]
    return f"{f.format(st['median'])} ({f.format(st['min'])}-{f.format(st['max'])})"


def table(source, res, ver="18.0.0", gpu=False):
    sel = [d for d in rows if d["source"] == source and d["res"] == res and d["av_version"] == ver and (("nvenc" in d["codec"]) == gpu)]
    by = {}
    for d in sel:
        by.setdefault(d["config"], {})[d["threads"]] = d
    print(f"\n### {source} {res} PyAV {ver}\n")
    print("| config | target pix_fmt | KB/frame | t1 enc fps | t1 cores/stream | t1 p99 ms | t0 enc fps | t0 cores/stream | t0 p99 ms | dec fps t1 / t0 | reps x frames |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for c, t in sorted(by.items(), key=lambda kv: -(kv[1].get(0) or kv[1].get(1))["encode_fps"]):
        a, b = t.get(1), t.get(0)
        x = a or b
        print(f"| {c} | {x['target_pix_fmt']} | {x['bytes_per_frame']/1000:.0f} | "
              + (f"{s(a,'encode_fps')} | {s(a,'encode_cpu_cores_per_30fps_stream','{:.2f}')} | {a['stats']['latency_p99']['median']:.1f} | " if a else "- | - | - | ")
              + (f"{s(b,'encode_fps')} | {s(b,'encode_cpu_cores_per_30fps_stream','{:.2f}')} | {b['stats']['latency_p99']['median']:.1f} | " if b else "- | - | - | ")
              + f"{a['stats']['decode_fps']['median'] if a else '-'} / {b['stats']['decode_fps']['median'] if b else '-'} | {x['reps']}x{x['frames']} |")


for src in ("yuyv422", "nv12"):
    table(src, "1080p")
for src in ("bayer12", "bayer12_quad", "bayer8", "raw12_packed"):
    table(src, "1080p")
for src in ("yuyv422", "nv12"):
    table(src, "720p")
for src in ("yuyv422", "nv12", "bayer12", "bayer12_quad"):
    table(src, "1080p", "19.0.2")
print("\n### NVENC (threads=1 on the libav side)\n")
print("| config | source | res | enc fps | cores/stream | p99 ms | KB/frame | dec fps (software) | nvidia-smi before -> after (sessions, util) |")
print("|---|---|---|---|---|---|---|---|---|")
for d in sorted([d for d in rows if "nvenc" in d["codec"]], key=lambda d: (d["res"], d["config"], d["source"])):
    print(f"| {d['config']} | {d['source']} ({d['target_pix_fmt']}) | {d['res']} | {s(d,'encode_fps')} | {s(d,'encode_cpu_cores_per_30fps_stream','{:.2f}')} | "
          f"{d['stats']['latency_p99']['median']:.1f} | {d['bytes_per_frame']/1000:.0f} | {d['decode_fps']:.0f} | {d['nvidia_smi_before']} -> {d['nvidia_smi_after']} |")
