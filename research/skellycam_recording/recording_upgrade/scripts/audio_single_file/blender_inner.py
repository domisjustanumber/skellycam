"""Runs inside Blender (bpy + aud). For each audio file: audaspace decode (aud.Sound.data(): sample count and an
exact check against the index signal), an audaspace seek (Sound.limit at 50 %: first sample's index), and a VSE
sound strip (sequence_editor.strips.new_sound: frame_final_duration at the scene fps).

blender -b --factory-startup --python blender_inner.py -- <files.json> <out.json>
files.json: [[path, seek_s], ...]
"""
import json
import sys

import aud
import bpy
import numpy as np

MUL = np.uint64(0x9E3779B97F4A7C15)


def sig(n0, n):
    idx = np.arange(n0, n0 + n, dtype=np.uint64)
    left = (idx & np.uint64(0xFFFF)).astype(np.uint16).view(np.int16)
    right = (((idx * MUL) >> np.uint64(50)).astype(np.int32) - 8192).astype(np.int16)
    return np.stack([left, right], axis=1)


def to_i16(a):
    # audaspace scales s16 by 1/32767 (measured: sample 1 reads 1.0000305 * 32768)
    return np.round(np.asarray(a, dtype=np.float64) * 32767).clip(-32768, 32767).astype(np.int16)


def first_index(x, approx):
    """Index of x[0] in the signal near approx (L carries the low 16 bits), or None."""
    if len(x) == 0:
        return None
    low = int(x[0, 0].view(np.uint16))
    for k in sorted(range(-40, 41), key=abs):
        n = (((approx >> 16) + k) << 16) + low
        if n >= 0 and np.array_equal(sig(n, min(64, len(x))), x[:64]):
            return int(n)
    return None


def main():
    files, out_path = sys.argv[sys.argv.index("--") + 1:]
    scene = bpy.context.scene
    sed = scene.sequence_editor_create()
    strips = sed.strips if hasattr(sed, "strips") else sed.sequences
    fps = scene.render.fps / scene.render.fps_base
    res = dict(blender=bpy.app.version_string, fps=fps, files={})
    for i, (path, seek_s) in enumerate(json.load(open(files))):
        r = {}
        try:
            s = aud.Sound(path)
            r["specs"] = list(s.specs)
            if seek_s < 1000:  # big files: seek only (data() would decode GBs into RAM)
                x = to_i16(s.data())
                if x.ndim == 1:
                    x = x[:, None]
                r["aud_samples"] = int(len(x))
                ref = sig(0, len(x)) if x.shape[1] == 2 else None
                r["aud_exact"] = bool(ref is not None and np.array_equal(x, ref))
            y = to_i16(s.limit(seek_s, seek_s + 0.5).data())
            n = first_index(y, int(seek_s * 48000))
            r["aud_seek"] = dict(target_s=seek_s, first_index=n, error_samples=None if n is None else n - int(round(seek_s * 48000)))
        except Exception as e:  # noqa: BLE001
            r["aud_error"] = f"{type(e).__name__}: {e}"[:200]
        try:
            st = strips.new_sound(f"s{i}", path, 1, 1)
            r["vse_frame_final_duration"] = st.frame_final_duration
            r["vse_expected_frames"] = round(r.get("aud_samples", 0) / 48000 * fps, 3)
            snd = st.sound
            r["sound_samplerate"] = getattr(snd, "samplerate", None)
            r["sound_channels"] = getattr(snd, "channels", None)
            strips.remove(st)
        except Exception as e:  # noqa: BLE001
            r["vse_error"] = f"{type(e).__name__}: {e}"[:200]
        res["files"][path] = r
    json.dump(res, open(out_path, "w"), indent=1)


main()
