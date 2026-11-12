"""Which audio encoders/muxers the PyAV wheel has, and the bundled libopus version.
Usage: python -I codecs_probe.py <out_json>"""
import ctypes, glob, json, os, sys
import av
names = ["opus", "libopus", "flac", "vorbis", "libvorbis", "aac", "mp3", "libmp3lame", "pcm_s16le", "speex", "libspeex"]
enc = {}
for n in names:
    try:
        c = av.Codec(n, "w")
        enc[n] = dict(resolves_to=c.name, long_name=c.long_name, experimental=bool(c.capabilities & 0x200),
                      sample_formats=[f.name for f in (c.audio_formats or [])], rates=list(c.audio_rates or []))
    except Exception as e:  # noqa: BLE001
        enc[n] = dict(error=str(e)[:100])
libs = os.path.join(os.path.dirname(av.__file__) + ".libs")
op = glob.glob(os.path.join(libs, "libopus*.dll"))
ver = None
if op:
    l = ctypes.CDLL(op[0]); l.opus_get_version_string.restype = ctypes.c_char_p; ver = l.opus_get_version_string().decode()
mux = {m: (m in av.formats_available) for m in ["ogg", "opus", "matroska", "webm", "flac", "wav"]}
json.dump(dict(pyav=av.__version__, library_versions={k: ".".join(map(str, v)) for k, v in av.library_versions.items()},
               encoders=enc, muxers=mux, libopus=ver, wheel_dlls=sorted(os.path.basename(p) for p in glob.glob(os.path.join(libs, "*.dll")))),
          open(sys.argv[1], "w"), indent=1)
print(ver, mux)
