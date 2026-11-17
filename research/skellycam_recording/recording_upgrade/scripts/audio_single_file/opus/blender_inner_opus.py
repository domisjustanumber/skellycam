"""Runs inside Blender (bpy + aud). Per file: audaspace full decode (channel 0 saved as .npy), an audaspace seek
(Sound.limit(T, T + 0.6), channel 0 saved), and a VSE sound strip length (frame_final_duration at the scene fps).
Analysis is done outside Blender (blender_opus.py) with opus_common.

blender -b --factory-startup --python blender_inner_opus.py -- <files.json> <out.json> <npy_dir>
files.json: [[path, seek_s], ...]
"""
import json
import os
import sys

import aud
import bpy
import numpy as np


def main():
    files, out_path, npy = sys.argv[sys.argv.index("--") + 1:]
    scene = bpy.context.scene
    sed = scene.sequence_editor_create()
    strips = sed.strips if hasattr(sed, "strips") else sed.sequences
    fps = scene.render.fps / scene.render.fps_base
    res = dict(blender=bpy.app.version_string, fps=fps, files={})
    for i, (path, seek_s) in enumerate(json.load(open(files))):
        r = dict(seek_s=seek_s)
        try:
            s = aud.Sound(path)
            r["specs"] = list(s.specs)
            x = np.asarray(s.data(), dtype=np.float32)
            x = x[:, 0] if x.ndim == 2 else x
            r["aud_samples"] = int(len(x))
            r["full_npy"] = os.path.join(npy, f"{i:03d}_full.npy"); np.save(r["full_npy"], x)
            y = np.asarray(s.limit(seek_s, seek_s + 0.6).data(), dtype=np.float32)
            y = y[:, 0] if y.ndim == 2 else y
            r["seek_npy"] = os.path.join(npy, f"{i:03d}_seek.npy"); np.save(r["seek_npy"], y)
        except Exception as e:  # noqa: BLE001
            r["aud_error"] = f"{type(e).__name__}: {e}"[:200]
        try:
            st = strips.new_sound(f"s{i}", path, 1, 1)
            r["vse_frame_final_duration"] = st.frame_final_duration
            strips.remove(st)
        except Exception as e:  # noqa: BLE001
            r["vse_error"] = f"{type(e).__name__}: {e}"[:200]
        res["files"][path] = r
    json.dump(res, open(out_path, "w"), indent=1)


main()
