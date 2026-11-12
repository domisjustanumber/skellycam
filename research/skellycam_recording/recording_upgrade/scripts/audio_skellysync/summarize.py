"""Condense compat_raw.json (run_matrix.py) into compat_summary.json: one row per variant.
Usage: python -I summarize.py <compat_raw.json> <compat_summary.json>
"""
import json, sys


def g(d, *ks):
    for k in ks:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def sync(s):
    if not s:
        return None
    return f"{s['n_found']}/{s['n_expected']} err {s['err_samples_min']}..{s['err_samples_max']} smp"


def main():
    raw = json.load(open(sys.argv[1]))
    rows = {"_versions": raw.get("_versions")}
    for name, r in raw.items():
        if name.startswith("_"):
            continue
        w, c = r["writer"], r["checks"]
        a = [s for s in c["ffprobe"]["streams"] if s.get("codec_type") == "audio"]
        rows[name] = dict(
            source=r["source"],
            audio=(f"{a[0]['codec_name']} {a[0]['sample_rate']} Hz {a[0]['channels']} ch" if a else "none"),
            audio_kbps=round(w["audio_bytes"] * 8 / (w["frame_count"] / float(eval(w["out_fps"]))) / 1000, 1) if w.get("audio_bytes") else 0,
            video_kbps=round(w["video_bytes"] * 8 / (w["frame_count"] / float(eval(w["out_fps"]))) / 1000, 1),
            write=dict(video_crc=f"{w['video_crc_match']}/{w['video_blocks']}",
                       audio_crc=f"{w.get('audio_crc_match', 0)}/{w.get('audio_blocks', 0)}",
                       scan_ms=w["scan_ms"], codec_delay_ns=g(w, "audio_track", "codec_delay_ns"),
                       seek_preroll_ns=g(w, "audio_track", "seek_preroll_ns"),
                       embed=(f"blocks unchanged {w['after_embed_blocks_unchanged']}, uid same {w['after_embed_uid_same']}"
                              if "embed_ms" in w else None)),
            ffprobe_packets={s.get("codec_type"): s.get("nb_read_packets") for s in c["ffprobe"]["streams"]},
            ffmpeg_decode_rc=c["ffmpeg_decode"]["rc"], ffmpeg_decode_error_lines=c["ffmpeg_decode"]["error_lines"],
            pyav=dict(frames=c["pyav"]["video_frames"], frame_exact=c["pyav"]["video_frame_exact"],
                      sync_L=sync(g(c, "pyav", "sync_L")), sync_R=sync(g(c, "pyav", "sync_R")),
                      channels_ok=g(c, "pyav", "channel_identity", "ok")),
            opencv=dict(count=c["opencv"]["cap_prop_frame_count"], read=c["opencv"]["frames_read"],
                        seeks=c["opencv"]["seeks_match_sequential"],
                        pixels_vs_twin=c["opencv"].get("pixels_identical_to_video_only_twin"),
                        seeks_vs_twin=c["opencv"].get("seeks_identical_to_twin")),
        )
        for key in ("vlc_play", "vlc_seek_7s"):
            v = c.get(key)
            if v:
                rows[name][key] = dict(rc=v["rc"], pngs=v["pngs"], first_frame=v["first_frame_number"],
                                       first_slot=v.get("first_slot"), stale_first_png=v.get("stale_first_png"), audio_decoder=v["log"]["audio_decoder_lines"],
                                       too_late=v["log"]["too_late"], errors=v["log"]["errors"],
                                       wav=v.get("wav"), sync_L=sync(v.get("sync_L_vs_first_png")),
                                       sync_R=sync(v.get("sync_R_vs_first_png")))
        f = c.get("ffplay")
        if f:
            rows[name]["ffplay"] = dict(rc=f.get("rc"), max_abs_av_diff_s=f.get("max_abs_av_diff_s"),
                                        last_av_diff_s=f.get("last_av_diff_s"), clock_end_s=f.get("clock_end_s"))
    json.dump(rows, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(rows, indent=1)[:6000])


if __name__ == "__main__":
    main()
