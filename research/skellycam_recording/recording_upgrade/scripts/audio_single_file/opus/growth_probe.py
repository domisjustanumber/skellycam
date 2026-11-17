# /// script
# requires-python = "==3.12.*"
# dependencies = ["av==19.0.2", "numpy==2.2.6"]
# ///
"""Virtual kills: write 4 s of paced-free 1024-sample blocks per Opus writer; after every block copy the file and
count what PyAV decodes from the copy. lag = written - decodable samples. Picks muxer settings before kill_opus.py.
Usage: uv run --script .../opus/growth_probe.py     Output: results/audio_single_file/opus/growth_probe.json
"""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opus_common as O  # noqa: E402
C = O.C

def main():
    d = os.path.join(O.SCRATCH, "growth"); os.makedirs(d, exist_ok=True)
    res = {}
    for name in O.WRITERS:
        path = os.path.join(d, name + O.WRITERS[name][1]); cp = path + ".copy" + O.WRITERS[name][1]
        w = C.PyAVWriter(name, path)
        lags = []
        for k in range(190):
            w.write(O.sig(k * O.BLOCK, O.BLOCK))
            n = (k + 1) * O.BLOCK
            if os.path.exists(path):
                shutil.copyfile(path, cp)
                got = O.decode_all(cp)[0]["samples"]
            else:
                got = 0
            lags.append(n - got)
        w.close()
        tail = lags[20:]
        res[name] = dict(lag_min=min(tail), lag_max=max(tail), lag_ms_max=round(max(tail) / 48, 1), first_block_with_audio=next((i for i, l in enumerate(lags) if l < (i + 1) * O.BLOCK), None))
        print(name, res[name], flush=True)
    os.makedirs(O.RESULTS, exist_ok=True)
    json.dump(res, open(os.path.join(O.RESULTS, "growth_probe.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
