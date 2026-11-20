"""Blender probe. Run: blender -b --factory-startup --python probe_blender.py -- MEDIA_DIR

For each MKV in files.json: frame_duration of movie clip, image (MOVIE) and VSE movie strip; render every movie
frame index n (n = scene frame - 1) of a VSE movie strip at 25 % to MEDIA_DIR/blender_out/<file>__q__<n>.png, and a
few frames at 100 % to <file>__x__<n>.png. Compare afterwards with compare_blender.py.
"""

import json
import os
import sys

import bpy

d = sys.argv[sys.argv.index("--") + 1]
out_dir = os.path.join(d, "blender_out")
os.makedirs(out_dir, exist_ok=True)
files = json.load(open(os.path.join(d, "files.json")))["files"]
SIZES = {"S": (640, 480), "L": (1920, 1080)}
EXACT = {"one": [100, 101], "run": [150, 190], "tail": [250, 199], "head": [5, 10],
         "full": [5, 10, 100, 101, 150, 190, 199, 250]}

sc = bpy.context.scene
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGB"
sc.view_settings.view_transform = "Standard"
sc.render.dither_intensity = 0.0  # default dither adds noise to 8-bit output
sc.render.fps, sc.render.fps_base = 30, 1.0
sc.frame_start, sc.frame_end = 1, 400
sed = sc.sequence_editor_create()
res = {"blender": bpy.app.version_string, "avformat": bpy.app.ffmpeg.avformat_version_string}


def render(tag, ns):
    errs = []
    for n in ns:
        sc.frame_set(n + 1)
        sc.render.filepath = os.path.join(out_dir, f"{tag}__{n:03d}.png")
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as e:  # noqa: BLE001
            errs.append(f"n={n}: {e}")
    return errs


for f in files:
    name, path = f["file"][:-4], os.path.join(d, f["file"])
    print("BEGIN", name, flush=True)
    sc.render.resolution_x, sc.render.resolution_y = SIZES[f["cfg"][0]]
    clip = bpy.data.movieclips.load(path)
    img = bpy.data.images.load(path)
    r = {"movieclip_frame_duration": clip.frame_duration, "clip_size": list(clip.size), "fps": clip.fps,
         "image_frame_duration": img.frame_duration, "image_size": list(img.size)}
    for s in list(sed.strips):
        sed.strips.remove(s)
    st = sed.strips.new_movie(name="m", filepath=path, channel=1, frame_start=1)
    r["strip_duration"] = st.frame_final_duration
    sc.render.resolution_percentage = 25
    r["errors"] = render(f"{name}__q", range(300))
    sc.render.resolution_percentage = 100
    r["errors"] += render(f"{name}__x", EXACT[f["pattern"]])
    sed.strips.remove(st)
    bpy.data.movieclips.remove(clip)
    bpy.data.images.remove(img)
    res[name] = r
    print("DONE", name, json.dumps(r), flush=True)

with open(os.path.join(d, "blender_results.json"), "w") as fh:
    json.dump(res, fh, indent=1)
