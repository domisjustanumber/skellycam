"""Runs inside Blender (bpy + aud). Per file: aud full length, aud seeks (Sound.limit(T, T + 1.0) at every target,
channel 0 saved as .npy, analysed outside Blender), VSE sound strip length (frame_final_duration at the scene fps)
and the time to open/seek.

blender -b --factory-startup --python blender_inner_crash.py -- <files.json> <out.json> <npy_dir>
files.json: [[path, [target_sample, ...]], ...]
"""
import json
import os
import sys
import time

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
    for i, (path, targets) in enumerate(json.load(open(files))):
        r = dict(seeks=[])
        try:
            t0 = time.perf_counter()
            s = aud.Sound(path)
            r["specs"] = list(s.specs)
            r["aud_length"] = s.length  # samples per channel as audaspace reports it
            r["aud_samples"] = int(len(np.asarray(s.data())))
            r["aud_full_decode_s"] = round(time.perf_counter() - t0, 3)
        except Exception as e:  # noqa: BLE001
            r["aud_error"] = f"{type(e).__name__}: {e}"[:200]
        for k, n in enumerate(targets):
            e = dict(n=n)
            try:
                t0 = time.perf_counter()
                y = np.asarray(aud.Sound(path).limit(n / 48000, n / 48000 + 1.0).data(), dtype=np.float32)
                e["s"] = round(time.perf_counter() - t0, 3)
                y = y[:, 0] if y.ndim == 2 else y
                e["samples"] = int(len(y))
                e["npy"] = os.path.join(npy, f"{i:03d}_{k:02d}.npy"); np.save(e["npy"], y)
            except Exception as ex:  # noqa: BLE001
                e["error"] = f"{type(ex).__name__}: {ex}"[:200]
            r["seeks"].append(e)
        try:
            st = strips.new_sound(f"s{i}", path, 1, 1)
            r["vse_frame_final_duration"] = st.frame_final_duration
            strips.remove(st)
        except Exception as ex:  # noqa: BLE001
            r["vse_error"] = f"{type(ex).__name__}: {ex}"[:200]
        res["files"][path] = r
    json.dump(res, open(out_path, "w"), indent=1)


main()
