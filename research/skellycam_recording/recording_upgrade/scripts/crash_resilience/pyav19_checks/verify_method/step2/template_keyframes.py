# /// script
# requires-python = ">=3.12"
# dependencies = ["av==19.0.2"]
# ///
import av, glob, json
for f in glob.glob("C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/crash_resilience/bench_tmp/template_*_intra.mkv"):
    with av.open(f) as c:
        s=c.streams.video[0]; ks=[p.is_keyframe for p in c.demux(s) if p.size]
        print(f, s.codec_context.name, s.codec_context.pix_fmt, len(ks), sum(ks))
