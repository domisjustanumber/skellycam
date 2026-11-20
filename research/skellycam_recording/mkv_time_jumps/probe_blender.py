"""Blender probe. Run: blender -b --factory-startup --python probe_blender.py -- MEDIA_DIR

For each MKV: report what Blender reads (movie clip, image MOVIE, VSE movie strip, VSE clip strip),
and render the frames in N (0-based movie frame index n = scene frame - 1) to MEDIA_DIR/blender_out/*.png.
Identify the drawn number afterwards with identify_pngs.py.
"""

import json
import os
import sys

import bpy

d = sys.argv[sys.argv.index("--") + 1]
out_dir = os.path.join(d, "blender_out")
os.makedirs(out_dir, exist_ok=True)
FILES = ["full", "B-one", "B-run", "B-tail", "B-tail-dur10", "B-head", "B-head30", "A-one", "A-run"]
N = range(300)  # every movie frame index

sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 640, 480, 25  # 160x120 is enough to identify
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "Standard"
sc.render.fps, sc.render.fps_base = 30, 1.0
sc.frame_start, sc.frame_end = 1, 400
sed = sc.sequence_editor_create()

res = {"blender": bpy.app.version_string, "build_hash": bpy.app.build_hash.decode(),
       "ffmpeg": {"avcodec": bpy.app.ffmpeg.avcodec_version_string, "avformat": bpy.app.ffmpeg.avformat_version_string}}


def render_strip(strip, tag):
    errs = []
    for n in N:
        sc.frame_set(n + 1)
        sc.render.filepath = os.path.join(out_dir, f"{tag}__{n:03d}.png")
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as e:  # noqa: BLE001
            errs.append(f"n={n}: {e}")
    return errs


for name in FILES:
    path = os.path.join(d, f"{name}.mkv")
    r = {}
    clip = bpy.data.movieclips.load(path)
    r["movieclip"] = {"frame_duration": clip.frame_duration, "fps": clip.fps, "frame_start": clip.frame_start}
    img = bpy.data.images.load(path)
    r["image"] = {"source": img.source, "frame_duration": img.frame_duration, "size": list(img.size)}

    for s in list(sed.strips):
        sed.strips.remove(s)
    st = sed.strips.new_movie(name="m", filepath=path, channel=1, frame_start=1)
    r["vse_movie"] = {"frame_final_duration": st.frame_final_duration, "fps": st.fps,
                      "errors": render_strip(st, f"{name}__vsemovie")}
    sed.strips.remove(st)
    st = sed.strips.new_clip(name="c", clip=clip, channel=1, frame_start=1)
    r["vse_clip"] = {"frame_final_duration": st.frame_final_duration, "errors": render_strip(st, f"{name}__vseclip")}
    sed.strips.remove(st)

    # Image datablock (source MOVIE) through a compositor Image node that follows the scene frame.
    tree = bpy.data.node_groups.new("C", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    ni = tree.nodes.new("CompositorNodeImage")
    ni.image = img
    ni.frame_start, ni.frame_offset, ni.frame_duration, ni.use_auto_refresh = 1, 0, img.frame_duration, True
    tree.links.new(ni.outputs[0], tree.nodes.new("NodeGroupOutput").inputs[0])
    sc.compositing_node_group = tree
    sc.render.use_compositing, sc.render.use_sequencer = True, False
    sc.render.resolution_percentage = 100  # the compositor crops (does not scale) the image to the render size
    r["comp_image"] = {"node_frame_duration": ni.frame_duration, "errors": render_strip(None, f"{name}__compimage")}
    sc.render.use_compositing, sc.render.use_sequencer = False, True
    sc.render.resolution_percentage = 25
    sc.compositing_node_group = None
    res[name] = r
    print("DONE", name, json.dumps(r), flush=True)

with open(os.path.join(d, "blender_results.json"), "w") as f:
    json.dump(res, f, indent=1)
