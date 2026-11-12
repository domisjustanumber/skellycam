"""Build the Electron test config from the matrix outputs, plus separate audio files (Au1 baselines) by stream copy.
Usage: python -I make_electron_cfg.py <scratch dir> <cfg.json>
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_compat as K  # noqa: E402


def url(p):
    return "file:///" + os.path.abspath(p).replace("\\", "/")


def main():
    sp, cfg_path = sys.argv[1], sys.argv[2]
    out = os.path.join(sp, "out")
    src = json.load(open(os.path.join(sp, "src", "sources.json")))["cam30_48k"]
    case = dict(start_frame=47, src_fps=30, out_fps=30, flash_frames=src["flash_frames"])
    times = K.burst_times(case)
    # separate audio files, stream copy (no re-encode) out of the MKVs
    sep = {}
    for mkv, ext in [("opus_st128", "opus"), ("opus_st128", "webm"), ("opus_st128", "mka"), ("flac16_st", "flac"),
                     ("flac16_st", "mka"), ("pcm24_st", "wav")]:
        dst = os.path.join(out, f"sep_{mkv}.{ext}")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", os.path.join(out, mkv + ".mkv"), "-map", "0:a", "-c", "copy"]
        if ext == "webm":
            cmd += ["-f", "webm"]
        subprocess.run(cmd + [dst], check=True)
        sep[f"{mkv}.{ext}"] = dst
    tests = []
    idx = lambda n: json.load(open(os.path.join(out, n + ".index.json")))
    for name, codec, variants in [("opus_st128", "opus", [(False, False), (True, False), (False, True), (True, True)]),
                                  ("opus_mono64", "opus", [(True, False), (False, True)]),
                                  ("flac16_st", "flac", [(True, False), (False, False)]),
                                  ("flac24_st", "flac", [(True, False)]),
                                  ("vorbis_st", "vorbis", [(True, False)])]:
        ix = idx(name)
        for desc, shift in variants:
            tests.append(dict(name=f"{name}.mkv webcodecs desc={desc} shift_codec_delay={shift}", kind="webcodecs",
                              url=url(os.path.join(out, name + ".mkv")), index=ix, codec=codec, description=desc, shift=shift))
    for name in ["opus_st128", "flac16_st", "pcm24_st", "vorbis_st"]:
        for tag in ["audio", "video"]:
            tests.append(dict(name=f"{name}.mkv <{tag}>", kind="element", url=url(os.path.join(out, name + ".mkv")), tag=tag))
        tests.append(dict(name=f"{name}.mkv decodeAudioData", kind="decodeAudioData", url=url(os.path.join(out, name + ".mkv"))))
    tests.append(dict(name="none_twin.mkv <video>", kind="element", url=url(os.path.join(out, "none_twin.mkv")), tag="video"))
    for k, p in sep.items():
        tests.append(dict(name=f"separate {k} <audio>", kind="element", url=url(p), tag="audio"))
        tests.append(dict(name=f"separate {k} decodeAudioData", kind="decodeAudioData", url=url(p)))
    json.dump(dict(times=times, tests=tests), open(cfg_path, "w"))
    print(len(tests), "tests")


if __name__ == "__main__":
    main()
