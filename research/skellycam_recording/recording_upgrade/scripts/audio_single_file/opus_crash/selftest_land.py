# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6", "soundfile==0.13.1"]
# ///
"""Assert-based check of crash_common.land on synthetic outputs, short and long (> 87 s, where the noise repeats):
output that starts at the target (+d), a jump from the file start to the target (+d, as VLC set_time output looks),
inserted silence after the jump, trailing zeros (trimmed)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crash_common as K  # noqa: E402

f = lambda n0, n: K.sig1(n0, n).astype(np.float64) / 32768  # noqa: E731
for t in (48_000 * 5 + 17, 48_000 * 40 + 3, 63_806_533, 84_956_857, 4_194_304 * 7 + 100):
    for d in (0, 7, -312, 960):
        assert K.land(f(t + d, 48000), t, t)["error_samples"] == d, (t, d, "start")
        y = np.r_[f(0, 28800), f(t + d, 48000)]
        assert K.land(y, t, t)["error_samples"] == d, (t, d, "jump")
        y = np.r_[f(0, 28800), np.zeros(500), f(t + d, 48000), np.zeros(3000)]
        r = K.land(y, t, t)
        assert r["error_samples"] == d and r["silence_after_jump"] == 500 and r["nonzero_len"] == 28800 + 500 + 48000, (t, d, r)
print("selftest_land ok")
