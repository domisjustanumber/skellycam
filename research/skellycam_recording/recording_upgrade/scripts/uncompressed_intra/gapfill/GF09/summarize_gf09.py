# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""GF09: merge the raw rows into results/uncompressed_intra/gapfill/GF09_qsv_lossless.json and print the Markdown
tables used in GF09_qsv_lossless.md. No measurement happens here.

Run from the repo root:
  uv run --script research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/gapfill/GF09/summarize_gf09.py
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[4] / "results" / "uncompressed_intra" / "gapfill"


def load(n):
    p = R / n
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else None


def main():
    qsv, nv = load("GF09_rows_qsv_pyav19.0.2.json"), load("GF09_rows_nvenc_pyav19.0.2.json")
    e35, e45 = load("GF09_chromium_electron35.json"), load("GF09_chromium_electron45.json")
    opts = load("GF09_avoptions_pyav19.0.2.json")
    out = {"versions": {k: (qsv or nv or {}).get(k) for k in ("av_version", "library_versions", "numpy", "python")},
           "gpu_drivers": load("GF09_gpu_drivers.json"), "frames_per_case": 300,
           "qsv_options_tried": [{"id": r["id"], "options": r["options"]} for r in (qsv or {}).get("rows", [])],
           "qsv_rows": (qsv or {}).get("rows"), "nvenc_rows": (nv or {}).get("rows"),
           "chromium": {}, "avoptions_keyword_hits": (opts or {}).get("keyword_hits"),
           "hw_decoders_in_wheel": (opts or {}).get("hw_decoders_in_wheel"),
           "chromium_media_check": load("GF09_chromium_media_check.json")}
    for tag, d in (("electron35", e35), ("electron45", e45)):
        if d:
            out["chromium"][tag] = {"versions": d["versions"], "results": d["results"]}
    (R / "GF09_qsv_lossless.json").write_text(json.dumps(out, indent=1, default=str))

    print("| encoder | config | input (fed pix_fmt) | opens | QPI used (runtime dump) | VDENC | exact frames /300 (data planes) | max abs diff Y,U,V | PSNR-Y min / mean (background) | profile | pix_fmt | KB/frame |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in (qsv or {}).get("rows", []):
        dump = " ".join(r.get("libav_param_dump", []))
        qpi = next((x.split("QPI:")[1].split(";")[0].strip() for x in r.get("libav_param_dump", []) if "QPI:" in x), "-")
        vd = next((x.split("VDENC:")[1].strip() for x in r.get("libav_param_dump", []) if "VDENC:" in x), "-")
        if r.get("stage") != "ok":
            print(f"| {r['encoder']} | {r['config']} | {r['input']} ({r['pix_fmt_fed']}) | no: {r.get('error')} | - | - | - | - | - | - | - | - |")
            continue
        sw = r["decode"]["sw"]
        print(f"| {r['encoder']} | {r['config']} | {r['input']} ({r['pix_fmt_fed']}) | yes | {qpi} | {vd} | "
              f"{sw.get('frames_exact_data')}/300 | {','.join(str(x) for x in sw.get('max_abs_per_plane', []))} | "
              f"{sw.get('psnr_y_min', '-')} / {sw.get('psnr_y_mean', '-')} | {r['ffprobe'].get('profile')} | {r['ffprobe'].get('pix_fmt')} | "
              f"{r['packet_bytes_mean'] / 1000:.1f} |")
    print()
    print("| case (= timed bench stem) | fed pix_fmt | profile | pix_fmt | sw exact /300 | h264/hevc_cuvid | hwaccel cuda | hwaccel d3d11va | KB/frame |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in (nv or {}).get("rows", []):
        d = r["decode"]

        def cell(k):
            x = d[k]
            if x.get("error") and not x.get("frames_decoded"):
                return f"fails: {x['error'][:60]}"
            return f"{x.get('frames_exact_data')}/{x.get('frames_decoded')} ({x.get('decoded_pix_fmt')})"
        print(f"| {r['bench_file_stem']} | {r['pix_fmt_fed']} | {r['ffprobe'].get('profile')} | {r['ffprobe'].get('pix_fmt')} | "
              f"{d['sw'].get('frames_exact_data')}/300 | {cell('cuvid')} | {cell('cuda')} | {cell('d3d11va')} | {r['packet_bytes_mean'] / 1000:.1f} |")
    print()
    print("| Electron | clip | check | result | decoder (media log) | exact readback (frames 0,1,7) |")
    print("|---|---|---|---|---|---|")
    for tag, d in (("E35", e35), ("E45", e45)):
        if not d:
            continue
        for k, r in d["results"].items():
            clip, mode = k.split("|", 1)
            dec = ", ".join(f"{m['props'].get('kVideoDecoderName')} (platform={m['props'].get('kIsPlatformVideoDecoder')})"
                            for m in r.get("media", {}).values() if m["props"].get("kVideoDecoderName")) or "-"
            rb = r.get("readback")
            rbs = "-" if not rb else " ".join(f"{x.get('k')}:{'exact' if x.get('exact') else ('no' if x.get('compared') else 'n/a')}({x.get('format')})" for x in rb)
            if r["mode"] == "caps":
                res = "canPlayType " + "; ".join(f"{m.split(';')[0]}={v or 'empty'}" for m, v in r["canPlayType"].items() if 'codecs' in m) + \
                      f"; MSE mp4={r['mseIsTypeSupported']}; isConfigSupported " + ", ".join(f"{h}={v}" for h, v in r["isConfigSupported"].items())
            elif r["mode"] == "video":
                res = f"loaded={r.get('ready')}, ended={r.get('ended')}, error={r.get('error')}, decodedFrames={r.get('decodedFrames')}/60, dropped={r.get('droppedFrames')}"
            else:
                res = f"configure: {'ok' if not r.get('errors') else r['errors'][0][:70]}; outputs={r.get('outputs')}/8"
            print(f"| {tag} ({d['versions']['chrome']}) | {clip} | {mode} | {res} | {dec} | {rbs} |")


if __name__ == "__main__":
    main()
