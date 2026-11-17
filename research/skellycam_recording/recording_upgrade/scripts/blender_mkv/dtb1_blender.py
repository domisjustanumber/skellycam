"""DT-B1 (runs inside Blender): does Blender 5.2 open per-camera MJPEG MKVs the way the freemocap addon loads videos?

Run:  blender.exe -b --factory-startup --python dtb1_blender.py -- <jobs.json> <out_dir>
jobs.json: [{"name": ..., "path": ..., "frames": [1-based frame numbers to render]}]

Per file it records what three Blender loaders report:
- bpy.data.images.load (the addon's call: freemocap_blender_addon 73e1b3e core_functions/parquet_scene.py:167)
- bpy.data.movieclips.load (the addon's other call: add_capture_cameras.py:207)
- a VSE movie strip, which is then rendered at the requested frames to PNG for the frame-identity check
  (dtb1_compare.py). The image-texture path itself is not rendered here.
Writes <out_dir>/blender_result.json.
"""
import json
import sys
import traceback
from pathlib import Path

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
jobs = json.loads(Path(args[0]).read_text())
out = Path(args[1])
out.mkdir(parents=True, exist_ok=True)

ff = bpy.app.ffmpeg
result = {
    "blender": bpy.app.version_string,
    "build_hash": bpy.app.build_hash.decode() if isinstance(bpy.app.build_hash, bytes) else str(bpy.app.build_hash),
    "ffmpeg": {k: str(getattr(ff, k)) for k in dir(ff) if k.endswith("version_string") or k == "supported"},
    "files": {},
}

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.use_sequencer = True
scene.render.use_compositing = False
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.render.fps = 30
scene.render.fps_base = 1.0
se = scene.sequence_editor_create()


def guarded(fn):
    try:
        return fn()
    except Exception as exc:  # record, keep going: one file must not hide the others
        return {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}


for job in jobs:
    name, path = job["name"], job["path"]
    rec = {}

    def image_probe():
        img = bpy.data.images.load(path, check_existing=False)
        size = tuple(img.size)  # the addon checks image.size before using the image (parquet_scene.py:168)
        return {"source": img.source, "size": size, "frame_duration": img.frame_duration,
                "colorspace": img.colorspace_settings.name}

    def clip_probe():
        clip = bpy.data.movieclips.load(path)
        return {"size": tuple(clip.size), "frame_duration": clip.frame_duration, "fps": clip.fps,
                "frame_start": clip.frame_start}

    def strip_probe():
        for s in list(se.strips):
            se.strips.remove(s)
        strip = se.strips.new_movie(name="m", filepath=path, channel=1, frame_start=1, fit_method="ORIGINAL")
        w, h = strip.elements[0].orig_width, strip.elements[0].orig_height
        if not w or not h:  # orig size not filled until first use; fall back to the image probe size
            w, h = rec.get("images_load", {}).get("size", (0, 0))
        scene.render.resolution_x, scene.render.resolution_y = int(w), int(h)
        scene.frame_start, scene.frame_end = 1, max(job["frames"])
        info = {"frame_final_duration": strip.frame_final_duration, "fps": strip.fps,
                "orig_size": (strip.elements[0].orig_width, strip.elements[0].orig_height),
                "colorspace": strip.colorspace_settings.name, "rendered": {}}
        for f in job["frames"]:
            scene.frame_set(f)
            png = out / f"{name}_f{f:05d}.png"
            scene.render.filepath = str(png)
            bpy.ops.render.render(write_still=True, scene=scene.name)
            info["rendered"][str(f)] = str(png) if png.exists() else None
        return info

    rec["images_load"] = guarded(image_probe)
    rec["movieclips_load"] = guarded(clip_probe)
    rec["vse_strip"] = guarded(strip_probe)
    result["files"][name] = rec
    print(f"DTB1 {name}: {json.dumps({k: (v if k != 'vse_strip' else {kk: vv for kk, vv in v.items() if kk != 'rendered'}) for k, v in rec.items()})}", flush=True)

(out / "blender_result.json").write_text(json.dumps(result, indent=1))
print("DTB1 done", flush=True)
