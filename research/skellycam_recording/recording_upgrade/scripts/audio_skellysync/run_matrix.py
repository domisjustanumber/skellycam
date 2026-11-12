"""Write every output variant with the prototype writer, then run all compatibility checks.

Run from PowerShell (VLC 3.0.24 would not start from the Bash tool's sandbox):
  $env:VLC_TMP = "<scratch>/vlctmp"; python -I run_matrix.py <scratch dir with src/> <results json>
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_compat as K  # noqa: E402
import sync_writer as SW  # noqa: E402

VARIANTS = [
    # name, source, start, count, out_fps, kwargs
    ("none_twin", "cam30_48k", 47, 450, None, dict(acodec="none")),
    ("opus_st128", "cam30_48k", 47, 450, None, dict(acodec="opus", embed=True)),
    ("opus_mono64", "cam30_48k", 47, 450, None, dict(acodec="opus", channels="mono")),
    ("flac16_st", "cam30_48k", 47, 450, None, dict(acodec="flac", embed=True)),
    ("flac24_st", "cam30_48k", 47, 450, None, dict(acodec="flac", flac_s32=True)),
    ("vorbis_st", "cam30_48k", 47, 450, None, dict(acodec="vorbis")),
    ("pcm24_st", "cam30_48k", 47, 450, None, dict(acodec="pcm_s24le")),
    ("opus_from44k_poly", "cam30_44k", 47, 450, None, dict(acodec="opus", resampler="poly")),
    ("opus_from44k_swr", "cam30_44k", 47, 450, None, dict(acodec="opus", resampler="swr")),
    ("flac16_44k", "cam30_44k", 47, 450, None, dict(acodec="flac")),
    ("opus_vstart", "cam30_48k_vstart", 47, 450, None, dict(acodec="opus")),
    ("flac16_vstart", "cam30_48k_vstart", 47, 450, None, dict(acodec="flac")),
    ("opus_r1_60to30", "cam60_48k", 94, 450, 30, dict(acodec="opus")),
]


def main():
    sp, out_json = sys.argv[1], sys.argv[2]
    only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    srcs = json.load(open(os.path.join(sp, "src", "sources.json")))
    os.makedirs(os.path.join(sp, "out"), exist_ok=True)
    results = json.load(open(out_json)) if (only and os.path.exists(out_json)) else {}
    results.setdefault("_versions", {})
    import av, cv2
    results["_versions"].update(av=av.__version__, ffmpeg_libs=str(av.library_versions["libavformat"]), cv2=cv2.__version__)
    twin = os.path.join(sp, "out", "none_twin.mkv")
    for name, src, start, count, ofps, kw in VARIANTS:
        if only and name not in only:
            continue
        s = srcs[src]
        dst = os.path.join(sp, "out", name + ".mkv")
        meta = SW.write_synced(os.path.join(sp, "src", s["path"]), dst, start, count, ofps, **kw)
        case = dict(start_frame=start, src_fps=s["fps"], out_fps=ofps or s["fps"], flash_frames=s["flash_frames"],
                    channels=1 if kw.get("channels") == "mono" else 2)
        t = time.perf_counter()
        chk = K.check(dst, case, twin=twin if (src == "cam30_48k" and name != "none_twin") else None,
                      vlc=kw.get("acodec") != "none" or name == "none_twin")
        chk["check_s"] = round(time.perf_counter() - t, 1)
        results[name] = dict(source=src, writer=meta, checks=chk)
        print(name, "done", flush=True)
        json.dump(results, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main()
