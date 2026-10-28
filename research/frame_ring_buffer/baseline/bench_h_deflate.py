"""(h) Cost of websocket permessage-deflate on a real SkellyCam UI payload (REVISION stage, 2026-10-28). NOT SkellyCam code.

Replaces the earlier timing that lived in another session's temp scratchpad (ui_tap_bench_output.txt, 45-82 KB synthetic
payloads). Here the payload is built by SkellyCam's real create_frontend_payload (frontend_payload_bytearray.py L107-197
@23ccbf20) from 5 frame recarrays filled with the baseline synthetic content (synthetic_frames noise=8, the same content as
baseline/bench_d_ui.py, whose 1080p payload median is 337 KB). The compressor is the websockets library's own
PerMessageDeflate extension object, configured the way uvicorn 0.51 negotiates it when ws_per_message_deflate=True
(the default): uvicorn/protocols/websockets/websockets_impl.py L105-106 calls ServerPerMessageDeflateFactory() with no
arguments, so compress_settings=None (zlib defaults) and context takeover on; window bits 15 assumed (a browser that
offers client_max_window_bits could lower it). Whether a given browser negotiates the extension was not checked.

Run (from C:\\Users\\Dom\\GitHub\\freemocap\\skellycam): .venv\\Scripts\\python.exe research\\frame_ring_buffer\\baseline\\bench_h_deflate.py
Output: baseline/results/h_deflate.json and .md
"""
from __future__ import annotations

import multiprocessing.queues  # noqa: F401
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402


def main():
    import bench_common as bc
    from skellycam.core.types.frontend_payload_bytearray import create_frontend_payload
    from websockets.extensions.permessage_deflate import PerMessageDeflate
    from websockets.frames import Frame, OP_BINARY
    import websockets
    rows = []
    for size_name in ("720p", "1080p"):
        h, w = bc.SIZES[size_name]
        frames = {i: bc.synthetic_frames(h, w, n=30, seed=i, noise=8) for i in range(5)}
        recs = {str(i): bc.make_frame_recarray(bc.make_config(i, h, w)) for i in range(5)}
        ext = PerMessageDeflate(remote_no_context_takeover=False, local_no_context_takeover=False,
                                remote_max_window_bits=15, local_max_window_bits=15)
        t_build, t_defl, sizes, out_sizes = [], [], [], []
        for k in range(200):
            for i in range(5):
                np.copyto(recs[str(i)].image[0], frames[i][k % 30])
                recs[str(i)].frame_metadata.frame_number[0] = k
            a = time.perf_counter_ns()
            _, _, payload = create_frontend_payload(latest_frames=recs, display_image_sizes=None)
            payload = bytes(payload)
            b = time.perf_counter_ns()
            f = ext.encode(Frame(OP_BINARY, payload))
            c = time.perf_counter_ns()
            if k >= 20:
                t_build.append(b - a); t_defl.append(c - b); sizes.append(len(payload)); out_sizes.append(len(f.data))
        rows.append(dict(size=size_name, payload_bytes_median=float(np.median(sizes)), deflated_bytes_median=float(np.median(out_sizes)),
                         build=bc.stats_ms(t_build), deflate=bc.stats_ms(t_defl), n=len(t_defl)))
    out = dict(env=bc.env_summary(), websockets_version=websockets.__version__, rows=rows)
    bc.write_json("h_deflate.json", out)
    L = ["# (h) permessage-deflate cost on a real SkellyCam UI payload (5 cameras, create_frontend_payload, websockets PerMessageDeflate)", "",
         f"websockets {websockets.__version__}; zlib defaults (uvicorn ServerPerMessageDeflateFactory() with no arguments), window bits 15, "
         "context takeover on; 180 payloads per size after 20 warm-up. Runs on the event-loop thread in the real server.", "",
         "| size | payload KB (median) | deflated KB | deflate median / p99 ms | build (create_frontend_payload) median ms |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['size']} | {r['payload_bytes_median'] / 1e3:.0f} | {r['deflated_bytes_median'] / 1e3:.0f} | "
                 f"{r['deflate']['median_ms']:.2f} / {r['deflate']['p99_ms']:.2f} | {r['build']['median_ms']:.2f} |")
    bc.write_text("h_deflate.md", "\n".join(L) + "\n") if hasattr(bc, "write_text") else (bc.RESULTS / "h_deflate.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
