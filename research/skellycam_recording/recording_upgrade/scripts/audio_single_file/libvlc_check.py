"""libvlc (installed VLC 3.0.24 via python-vlc) per file: parsed duration, length while playing, is_seekable,
and where a position seek to 0.5 lands. Dummy audio output. Run by readers.py in its own interpreter.

Usage: python -I libvlc_check.py <paths.json>   -> <paths.json>.out.json
"""
import json
import os
import sys
import time

import vlc


def one(inst, path):
    m = inst.media_new_path(os.path.normpath(path))  # mixed / and \ make libvlc return NULL
    m.parse_with_options(vlc.MediaParseFlag.local, 3000)
    t0 = time.time()
    while m.get_parsed_status() == 0 and time.time() - t0 < 4:
        time.sleep(0.02)
    res = dict(parsed_duration_ms=m.get_duration())
    pl = inst.media_player_new(); pl.set_media(m); pl.play()
    t0 = time.time()
    while pl.get_state() not in (vlc.State.Playing, vlc.State.Ended, vlc.State.Error) and time.time() - t0 < 4:
        time.sleep(0.02)
    time.sleep(0.3)
    res.update(state=str(pl.get_state()), length_ms=pl.get_length(), seekable=bool(pl.is_seekable()))
    pl.set_position(0.5)
    time.sleep(0.4)
    res.update(time_after_pos50_ms=pl.get_time(), pos_after=round(pl.get_position(), 3))
    pl.stop(); pl.release(); m.release()
    return res


if __name__ == "__main__":
    paths = json.load(open(sys.argv[1]))
    inst = vlc.Instance("--aout=dummy", "--no-video", "--quiet")  # "-I dummy" makes libvlc_new fail
    out = dict(vlc=vlc.libvlc_get_version().decode(), python_vlc=vlc.__version__, files={p: one(inst, p) for p in paths})
    json.dump(out, open(sys.argv[1] + ".out.json", "w"), indent=1)
