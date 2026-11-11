"""Analyze one skellycam recording folder: inventory, CSV headers, ffprobe stream + per-frame types, bits/pixel,
header rate vs CSV timing, audio, and extract one frame per video (to the raw folder, never the repo).

Usage: analyze_recording.py <recording_folder> <out_dir_for_text> <raw_frames_dir> [frame_index]
Writes <out_dir>/<name>_analysis.json, <name>_ffprobe_<cam>.json, <name>_inventory.txt, <name>_csv_heads.txt.
"""
import csv
import json
import subprocess
import sys
import wave
from collections import Counter
from fractions import Fraction
from pathlib import Path

rec = Path(sys.argv[1])
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
raw = Path(sys.argv[3]); raw.mkdir(parents=True, exist_ok=True)
fidx = int(sys.argv[4]) if len(sys.argv) > 4 else 100
name = rec.name
res = dict(recording=str(rec), name=name)

# ---- inventory
lines = []
for p in sorted(rec.rglob("*")):
    rel = p.relative_to(rec)
    lines.append(f"{'D' if p.is_dir() else 'F'}  {p.stat().st_size if p.is_file() else '':>12}  {rel.as_posix()}")
(out / f"{name}_inventory.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
res["inventory"] = lines
res["web_mp4_present"] = [str(p) for p in rec.rglob("*.web.mp4")]

# ---- CSV heads
heads = []
for c in sorted(rec.rglob("*.csv")):
    with open(c, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        rows = list(r)
    heads.append(dict(file=c.relative_to(rec).as_posix(), columns=len(hdr), rows=len(rows), header=hdr,
                      first_row=rows[0] if rows else None))
(out / f"{name}_csv_heads.txt").write_text(
    "\n\n".join(f"{h['file']}  columns={h['columns']} rows={h['rows']}\n" + ",".join(h["header"]) + "\n" + ",".join(h["first_row"] or [])
                for h in heads) + "\n", encoding="utf-8")
res["csvs"] = [{k: v for k, v in h.items() if k != "first_row"} for h in heads]

# ---- per camera
vids = sorted(p for p in (rec / "synchronized_videos").iterdir() if p.suffix.lower() in (".mp4", ".avi", ".mkv", ".mov"))
cams = []
for v in vids:
    cam_id = v.name.split(".id-")[1].split(".")[0]
    pj = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-show_format",
                                    "-count_packets", "-of", "json", str(v)], capture_output=True, text=True).stdout)
    (out / f"{name}_ffprobe_{cam_id}.json").write_text(json.dumps(pj, indent=1), encoding="utf-8")
    s = pj["streams"][0]
    fr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames", "-show_entries",
                         "frame=pict_type,key_frame,pkt_size", "-of", "csv=p=0", str(v)], capture_output=True, text=True).stdout
    frames = []
    for ln in fr.splitlines():
        parts = ln.strip().split(",")
        if len(parts) < 3:
            continue
        kf, size, pt = parts[0], parts[1], parts[2]
        frames.append((int(kf), int(size), pt))
    types = Counter(f[2] for f in frames)
    keys = [i for i, f in enumerate(frames) if f[0] == 1]
    gops = [b - a for a, b in zip(keys, keys[1:])]
    w, h = int(s["width"]), int(s["height"])
    sizes = [f[1] for f in frames]
    mean_bytes = sum(sizes) / len(sizes)
    rfr = Fraction(s["r_frame_rate"]); afr = Fraction(s["avg_frame_rate"])
    # CSV timing
    csvp = rec / "synchronized_videos" / "timestamps" / "camera_timestamps" / f"{name}.camera{cam_id}.timestamps.csv"
    with open(csvp, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t = [int(float(r["timestamp.perf_counter_ns.ns"])) for r in rows]
    span = (t[-1] - t[0]) / 1e9
    ach = (len(t) - 1) / span
    iv = sorted((b - a) / 1e6 for a, b in zip(t, t[1:]))
    med_iv = iv[len(iv) // 2]
    dur = float(s.get("duration") or pj["format"]["duration"])
    # extract one frame (raw folder only)
    png = raw / f"{name}.{cam_id}.frame{fidx}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v), "-vf", f"select=eq(n\\,{fidx})", "-frames:v", "1", str(png)])
    cams.append(dict(
        camera_id=cam_id, file=v.name, file_bytes=v.stat().st_size,
        codec=s.get("codec_name"), profile=s.get("profile"), level=s.get("level"), pix_fmt=s.get("pix_fmt"),
        has_b_frames=s.get("has_b_frames"), width=w, height=h,
        r_frame_rate=s["r_frame_rate"], r_fps=float(rfr), avg_frame_rate=s["avg_frame_rate"], avg_fps=float(afr) if afr else None,
        time_base=s.get("time_base"), nb_frames=s.get("nb_frames"), nb_read_packets=s.get("nb_read_packets"),
        stream_duration_s=dur, stream_bit_rate=s.get("bit_rate"), format_bit_rate=pj["format"].get("bit_rate"),
        encoder_tag=s.get("tags", {}).get("encoder") or pj["format"].get("tags", {}).get("encoder"),
        handler=s.get("tags", {}).get("handler_name"),
        frames_decoded=len(frames), pict_types=dict(types), keyframe_count=len(keys), keyframes_first=keys[:6],
        gop_lengths=sorted(Counter(gops).items()),
        mean_bytes_per_frame=round(mean_bytes, 1),
        bits_per_pixel=round(mean_bytes * 8 / (w * h), 4),
        i_frame_mean_bytes=round(sum(f[1] for f in frames if f[2] == "I") / max(1, types.get("I", 0)), 1),
        p_frame_mean_bytes=round(sum(f[1] for f in frames if f[2] == "P") / max(1, types.get("P", 0)), 1),
        bitrate_at_header_fps_mbit=round(mean_bytes * 8 * float(rfr) / 1e6, 3),
        target_mbit_trunc_fps=round(int(float(rfr)) * w * h / 1e6, 3),
        csv_rows=len(rows), csv_span_s=round(span, 4), csv_achieved_fps=round(ach, 4),
        csv_median_interval_ms=round(med_iv, 3), csv_min_interval_ms=round(iv[0], 3), csv_max_interval_ms=round(iv[-1], 3),
        csv_intervals_over_50ms=sum(1 for x in iv if x > 50),
        header_minus_achieved_fps=round(float(rfr) - ach, 4),
        header_duration_minus_csv_span_s=round(dur - (span + 1 / ach), 4),
        frame_png=str(png),
    ))
res["cameras"] = cams

# ---- audio
wav = list((rec / "synchronized_videos").glob("*.audio.wav"))
if wav:
    with wave.open(str(wav[0])) as wf:
        res["audio_wav"] = dict(file=wav[0].name, channels=wf.getnchannels(), sampwidth=wf.getsampwidth(),
                                rate=wf.getframerate(), frames=wf.getnframes(), duration_s=wf.getnframes() / wf.getframerate())
    side = json.loads(next((rec / "synchronized_videos").glob("*.audio_timestamps.json")).read_text())
    res["audio_sidecar_keys"] = list(side.keys())
    res["audio_sidecar"] = {k: v for k, v in side.items() if not isinstance(v, list)}
    res["audio_sidecar_list_lengths"] = {k: len(v) for k, v in side.items() if isinstance(v, list)}

(out / f"{name}_analysis.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
for c in cams:
    print(json.dumps({k: v for k, v in c.items() if k not in ("frame_png",)}))
print("web.mp4:", res["web_mp4_present"])
print("audio:", res.get("audio_wav"))
