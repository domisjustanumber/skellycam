"""Build per_video_table.md from run*/*_analysis.json (run from the results folder)."""
import json, glob, os
names = {'0100': 'C930e', '1c81': 'C922', 'fbf5': 'Kiyo Pro'}
rows = []
for f in sorted(glob.glob('run*/*_analysis.json')):
    d = json.load(open(f)); run = os.path.normpath(f).split(os.sep)[0]
    for c in d['cameras']:
        gop = ",".join(f"{g}x{n}" for g, n in c['gop_lengths'])
        rows.append(f"| {run} | {names[c['camera_id']]} ({c['camera_id']}) | {c['width']}x{c['height']} | {c['codec']} {c['profile']} L{c['level']/10:.1f} | {c['has_b_frames']} | {c['pict_types'].get('I',0)} I / {c['pict_types'].get('P',0)} P | {gop} | {c['r_frame_rate']} = {c['r_fps']:.3f} | {c['csv_achieved_fps']:.3f} | {c['header_minus_achieved_fps']:+.2f} | {c['nb_frames']} / {c['csv_rows']} | {c['stream_duration_s']:.2f} / {c['csv_span_s']:.2f} | {int(c['stream_bit_rate'])/1e6:.2f} | {c['bits_per_pixel']:.3f} | {c['file_bytes']/1e6:.1f} |")
hdr = ("| Run | Camera | Size | Codec / profile | has_b_frames | Frame types | GOP (len x count) | Header r_frame_rate | Achieved fps (CSV) | Header - achieved | Frames video / CSV | Duration header / CSV span (s) | Bitrate (Mbit/s) | Bits/pixel | File MB |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
open('per_video_table.md', 'w').write(hdr + "\n".join(rows) + "\n")
print(hdr + "\n".join(rows))
